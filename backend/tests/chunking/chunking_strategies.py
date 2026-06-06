import os
import re
import numpy as np
from typing import List, Dict, Any
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from transformers import AutoTokenizer
    HAS_TOKENIZER = True
except ImportError:
    HAS_TOKENIZER = False

_tokenizer = None

def get_tokenizer():
    """延迟加载tokenizer"""
    global _tokenizer
    if _tokenizer is None and HAS_TOKENIZER:
        try:
            _tokenizer = AutoTokenizer.from_pretrained("bert-base-chinese")
        except Exception as e:
            print(f"提示: 无法加载BERT tokenizer，将使用字符切分模式: {e}")
    return _tokenizer

class SpeakerChunking:
    def __init__(self, min_chunk_size: int = 100, max_chunk_size: int = 1000):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
    
    def chunk(self, text: str) -> List[str]:
        chunks = []
        current_speaker = None
        current_chunk = []
        
        speaker_patterns = [
            r'^\[(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*([A-Za-z0-9_]+):\s*(.*)',
            r'^\[(\d{2}:\d{2}:\d{2}\.\d{2})\]\s*([A-Za-z0-9_]+):\s*(.*)',
            r'^\[(\d{2}:\d{2}\.\d{2,3})\]\s*([A-Za-z0-9_]+):\s*(.*)',
            r'^\[(\d{2}:\d{2}:\d{2})\]\s*([A-Za-z0-9_]+):\s*(.*)',
            r'^\[(\d{2}:\d{2}\.\d{2,3})\]\s*(.*)',
            r'^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)',
            r'^(\d{2}:\d{2}:\d{2})\s*([A-Za-z0-9_]+):\s*(.*)',
        ]
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            matched = False
            speaker = None
            content = line
            
            for pattern in speaker_patterns:
                match = re.match(pattern, line)
                if match:
                    if len(match.groups()) == 3:
                        speaker = match.group(2)
                        content = match.group(3)
                    else:
                        speaker = f"SPEAKER_{len(chunks)}"
                        content = match.group(2)
                    matched = True
                    break
            
            if speaker and speaker != current_speaker:
                if current_chunk:
                    chunk_text = "\n".join(current_chunk)
                    chunks.append(chunk_text)
                    current_chunk = []
                current_speaker = speaker
            
            current_chunk.append(content)
        
        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            chunks.append(chunk_text)
        
        return self._merge_small_chunks(chunks)
    
    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        result = []
        buffer = []
        
        for chunk in chunks:
            buffer.append(chunk)
            buffer_text = "\n".join(buffer)
            
            if len(buffer_text) >= self.min_chunk_size or len(buffer) >= 3:
                result.append(buffer_text)
                buffer = []
        
        if buffer:
            if result:
                result[-1] += "\n" + "\n".join(buffer)
            else:
                result.append("\n".join(buffer))
        
        return result

class HybridChunking:
    def __init__(self, similarity_threshold: float = 0.7, max_chunk_size: int = 1000, 
                min_paragraph_len: int = 10, noise_patterns: List[str] = None):
        self.similarity_threshold = similarity_threshold
        self.max_chunk_size = max_chunk_size
        self.min_paragraph_len = min_paragraph_len
        self.noise_patterns = noise_patterns or [
            r'^(嗯\.?|嗯嗯\.?|对\.?|对对对\.?|是\.?|行\.?|啊\.?|哦\.?)$',
            r'^[嗯啊哦对是行]+[\.\?！!]*$',
        ]
        self.vectorizer = TfidfVectorizer(
            max_features=2000,
            ngram_range=(1, 2),
            stop_words=None
        )
    
    def _is_noise(self, text: str) -> bool:
        """判断是否为噪音段落"""
        text = text.strip()
        # 长度过短且符合噪音模式
        if len(text) <= 10:
            for pattern in self.noise_patterns:
                if re.match(pattern, text):
                    return True
            # 额外检查：只有单个字符或重复字符
            if len(text) <= 5:
                # 检查是否只是单个语气词
                noise_chars = {'嗯', '啊', '哦', '对', '是', '行', '好', '嗯', '哦', '啊', '哈', '哎', '唉'}
                chars = set(text.replace('.', '').replace('。', '').replace('!', '').replace('！', ''))
                if chars and chars.issubset(noise_chars):
                    return True
        return False
    
    def chunk(self, text: str) -> List[str]:
        paragraphs = self._split_into_paragraphs(text)
        paragraphs = [p for p in paragraphs if not self._is_noise(p)]
        return self._merge_similar_paragraphs(paragraphs)
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """分割文本为段落，自动过滤噪音并合并相关内容"""
        paragraphs = []
        
        # 按换行符分割
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # 累积非噪音行形成段落
        current_paragraph = []
        
        for line in lines:
            if not self._is_noise(line):
                current_paragraph.append(line)
                # 达到一定长度就形成段落
                if len(" ".join(current_paragraph)) >= 200:
                    paragraphs.append(" ".join(current_paragraph))
                    current_paragraph = []
        
        if current_paragraph:
            paragraphs.append(" ".join(current_paragraph))
        
        return paragraphs
    
    def _merge_similar_paragraphs(self, paragraphs: List[str]) -> List[str]:
        if len(paragraphs) < 2:
            return paragraphs
        
        result = [paragraphs[0]]
        
        for i in range(1, len(paragraphs)):
            prev = result[-1]
            curr = paragraphs[i]
            
            similarity = self._compute_similarity(prev, curr)
            combined = prev + " " + curr
            
            if similarity >= self.similarity_threshold and len(combined) <= self.max_chunk_size:
                result[-1] = combined
            else:
                result.append(curr)
        
        return result
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        try:
            vectors = self.vectorizer.fit_transform([text1, text2])
            return cosine_similarity(vectors)[0, 1]
        except Exception as e:
            return 0.0

class FixedSizeChunking:
    def __init__(self, chunk_size: int = 512, overlap: int = 64, use_tokenizer: bool = False):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.use_tokenizer = use_tokenizer and HAS_TOKENIZER
    
    def chunk(self, text: str) -> List[str]:
        if self.use_tokenizer:
            return self._chunk_by_tokens(text)
        else:
            return self._chunk_by_chars(text)
    
    def _chunk_by_chars(self, text: str) -> List[str]:
        chunks = []
        text = text.replace('\n', ' ')
        
        for i in range(0, len(text), self.chunk_size - self.overlap):
            chunk = text[i:i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
        
        return chunks
    
    def _chunk_by_tokens(self, text: str) -> List[str]:
        chunks = []
        
        tokenizer = get_tokenizer()
        if tokenizer is None:
            return self._chunk_by_chars(text)
        
        tokens = tokenizer.encode(text, add_special_tokens=False)
        stride = self.chunk_size - self.overlap
        
        for i in range(0, len(tokens), stride):
            chunk_tokens = tokens[i:i + self.chunk_size]
            if chunk_tokens:
                chunk = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
                chunks.append(chunk.strip())
        
        return chunks