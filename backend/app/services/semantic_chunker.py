"""LLM语义分块器 + 父子块关系管理"""
import json
import re
import math
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


@dataclass
class Chunk:
    """文档块"""
    chunk_id: str
    content: str
    parent_id: Optional[str] = None
    child_ids: List[str] = field(default_factory=list)
    level: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "parent_id": self.parent_id,
            "child_ids": self.child_ids,
            "level": self.level,
            "metadata": self.metadata
        }


class ChunkingStrategy(str, Enum):
    """分块策略"""
    FIXED_SIZE = "fixed_size"           # 固定大小
    SEMANTIC = "semantic"             # 语义分块（LLM驱动）
    SEMANTIC_HYBRID = "semantic_hybrid"  # 混合策略
    PARAGRAPH = "paragraph"           # 段落分块
    RECURSIVE = "recursive"           # 递归分块
    SPEAKER_AWARE_HYBRID = "speaker_aware_hybrid"  # 说话人感知混合分块（实验最佳）


@dataclass
class ChunkingConfig:
    """分块配置（基于SPEAKER_AWARE_HYBRID参数调优实验）"""
    strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC_HYBRID
    min_chunk_size: int = 50
    max_chunk_size: int = 300
    chunk_overlap: int = 30
    semantic_threshold: float = 0.7
    use_llm_split: bool = True
    preserve_structure: bool = True
    build_hierarchy: bool = True


class SemanticChunker:
    """LLM驱动的语义分块器"""

    _SIMILARITY_STOPWORDS = {
        "的", "了", "和", "与", "及", "或", "是", "在", "有", "为", "对", "中",
        "需要", "进行", "包括", "以及", "一个", "这个", "那个", "我们", "他们",
        "the", "a", "an", "and", "or", "of", "to", "in", "for", "with", "is", "are",
    }
    
    def __init__(self, llm_service=None, config: ChunkingConfig = None):
        self._llm = llm_service
        self._config = config or ChunkingConfig()
        self._tokenizer = None
    
    def _get_llm(self):
        """获取LLM服务"""
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    def _get_tokenizer(self):
        """获取分词器"""
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
                model_name = settings.EMBEDDING_MODEL
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_name,
                    trust_remote_code=True
                )
            except Exception as e:
                app_logger.warning(f"Could not load tokenizer: {e}")
                self._tokenizer = None
        return self._tokenizer
    
    def _count_tokens(self, text: str) -> int:
        """计算近似token数量"""
        tokenizer = self._get_tokenizer()
        if tokenizer:
            return len(tokenizer.encode(text))
        return max(1, len(text) // 4)

    def _size(self, text: str) -> int:
        """分块大小统一按字符数控制，避免上传流程依赖tokenizer。"""
        return len(text or "")
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """按段落分割"""
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子分割"""
        if not text:
            return []
        sentence_pattern = r'[^.!?。！？\n]+[.!?。！？]?'
        sentences = re.findall(sentence_pattern, text)
        return [s.strip() for s in sentences if s.strip()]

    def _tokenize_for_similarity(self, text: str) -> List[str]:
        """轻量语义相似度分词，优先中文词，兼容英文单词。"""
        try:
            import jieba
            tokens = jieba.lcut(text)
        except Exception:
            tokens = re.findall(r'[\u4e00-\u9fa5]{1,}|[a-zA-Z0-9_]+', text)

        cleaned_tokens = []
        for token in tokens:
            cleaned = token.lower().strip()
            if not cleaned or cleaned.isspace():
                continue
            if cleaned in self._SIMILARITY_STOPWORDS:
                continue
            if not re.search(r'[\u4e00-\u9fa5a-zA-Z0-9]', cleaned):
                continue
            if len(cleaned) == 1 and re.match(r'[\u4e00-\u9fa5a-zA-Z]', cleaned):
                continue
            cleaned_tokens.append(cleaned)

        return cleaned_tokens

    def _lexical_similarity(self, left: str, right: str) -> float:
        """基于词频余弦相似度的本地语义近似。"""
        left_tokens = self._tokenize_for_similarity(left)
        right_tokens = self._tokenize_for_similarity(right)
        if not left_tokens or not right_tokens:
            return 0.0

        left_counts = Counter(left_tokens)
        right_counts = Counter(right_tokens)
        common = set(left_counts) & set(right_counts)
        dot = sum(left_counts[token] * right_counts[token] for token in common)
        left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
        right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return dot / (left_norm * right_norm)

    def _with_overlap(self, chunks: List[str]) -> List[str]:
        """为相邻块增加字符级重叠上下文。"""
        if self._config.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped = [chunks[0]]
        for index in range(1, len(chunks)):
            prefix = chunks[index - 1][-self._config.chunk_overlap:]
            current = chunks[index]
            if prefix and not current.startswith(prefix):
                current = f"{prefix}{current}"
            overlapped.append(current)
        return overlapped

    def _make_chunks(
        self,
        doc_id: str,
        texts: List[str],
        source: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Chunk]:
        """将文本列表转换为 Chunk 对象。"""
        metadata = extra_metadata or {}
        return [
            Chunk(
                chunk_id=f"{doc_id}_{idx}",
                content=text.strip(),
                level=0,
                metadata={
                    "source": source,
                    "chars": self._size(text),
                    **metadata,
                },
            )
            for idx, text in enumerate(texts)
            if text and text.strip()
        ]
    
    async def semantic_split(self, text: str, doc_id: str) -> List[Chunk]:
        """
        LLM驱动的语义分块
        
        Args:
            text: 文档文本
            doc_id: 文档ID
            
        Returns:
            分块列表
        """
        llm = self._get_llm()
        
        if llm is None or not self._config.use_llm_split:
            return self._fallback_chunking(text, doc_id)
        
        try:
            text_size = self._size(text)
            
            if text_size <= self._config.max_chunk_size:
                return [Chunk(
                    chunk_id=f"{doc_id}_0",
                    content=text,
                    level=0,
                    metadata={"chars": text_size, "source": "semantic_single"}
                )]
            
            prompt = f"""请将以下文档分割成语义连贯的块。每个块应该：
1. 讨论一个完整的主题或子主题
2. 长度在{self._config.min_chunk_size}-{self._config.max_chunk_size}字之间
3. 保持上下文连贯性
4. 如果是嵌套结构（如章节），标注层级

文档：
{text}

输出格式（JSON数组）：
[
  {{
    "content": "块内容",
    "level": 0或1或2,
    "topic": "简短主题描述"
  }}
]

只输出JSON，不要其他内容："""
            
            response = await llm.chat(
                messages=[
                    {"role": "system", "content": "你是专业的文档语义分块助手，只输出JSON数组。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            
            chunks = self._parse_llm_response(response, doc_id)
            
            if chunks:
                return chunks
            
        except Exception as e:
            app_logger.error(f"Semantic chunking failed: {e}")
        
        return self._local_semantic_chunking(text, doc_id)
    
    def _parse_llm_response(self, response: str, doc_id: str) -> List[Chunk]:
        """解析LLM响应"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                
                chunks = []
                for i, item in enumerate(data):
                    chunk = Chunk(
                        chunk_id=f"{doc_id}_{i}",
                        content=item.get("content", ""),
                        level=item.get("level", 0),
                        metadata={
                            "topic": item.get("topic", ""),
                            "source": "llm_split"
                        }
                    )
                    chunks.append(chunk)
                
                return chunks
                
        except json.JSONDecodeError as e:
            app_logger.warning(f"Failed to parse LLM response: {e}")
        
        return []
    
    def _fallback_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """降级分块策略（基于规则）"""
        if self._config.strategy == ChunkingStrategy.FIXED_SIZE:
            return self._fixed_size_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.PARAGRAPH:
            return self._paragraph_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.RECURSIVE:
            return self._recursive_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.SEMANTIC:
            return self._local_semantic_chunking(text, doc_id)
        else:
            return self._hybrid_chunking(text, doc_id)
    
    def _fixed_size_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """固定大小分块"""
        chunk_size = max(1, self._config.max_chunk_size)
        overlap = max(0, min(self._config.chunk_overlap, chunk_size - 1))
        step = max(1, chunk_size - overlap)
        
        chunk_texts = []
        for i in range(0, len(text), step):
            chunk_text = text[i:i + chunk_size]
            if chunk_text:
                chunk_texts.append(chunk_text)
        
        return self._make_chunks(doc_id, chunk_texts, "fixed_size")
    
    def _paragraph_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """段落分块"""
        paragraphs = self._split_by_paragraphs(text)
        if not paragraphs:
            paragraphs = self._split_by_sentences(text) or [text]
        
        chunk_texts = []
        current_chunk = []
        current_size = 0
        
        for para in paragraphs:
            para_size = self._size(para)

            if para_size > self._config.max_chunk_size:
                if current_chunk:
                    chunk_texts.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0
                chunk_texts.extend(
                    chunk.content
                    for chunk in self._recursive_chunking(para, f"{doc_id}_p{len(chunk_texts)}")
                )
                continue
            
            if current_size + para_size > self._config.max_chunk_size and current_chunk:
                chunk_texts.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_size = para_size
            else:
                current_chunk.append(para)
                current_size += para_size

        if current_chunk:
            chunk_texts.append("\n\n".join(current_chunk))

        return self._make_chunks(
            doc_id,
            self._with_overlap(chunk_texts),
            "paragraph",
            {"paragraph_based": True},
        )

    def _recursive_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """递归分块：按标题、段落、句子、标点、字符逐级切分。"""
        separators = [
            r'\n(?=#{1,6}\s+)',
            r'\n\s*\n',
            r'(?<=[。！？.!?])',
            r'(?<=[；;])',
            r'(?<=[，,])',
            '',
        ]

        def split_recursive(segment: str, separator_index: int = 0) -> List[str]:
            segment = segment.strip()
            if not segment:
                return []
            if self._size(segment) <= self._config.max_chunk_size:
                return [segment]
            if separator_index >= len(separators):
                return [
                    segment[i:i + self._config.max_chunk_size]
                    for i in range(0, len(segment), self._config.max_chunk_size)
                ]

            separator = separators[separator_index]
            if separator:
                parts = [part.strip() for part in re.split(separator, segment) if part.strip()]
            else:
                parts = [
                    segment[i:i + self._config.max_chunk_size]
                    for i in range(0, len(segment), self._config.max_chunk_size)
                ]

            if len(parts) <= 1 and separator:
                return split_recursive(segment, separator_index + 1)

            chunks = []
            current = ""
            for part in parts:
                if self._size(part) > self._config.max_chunk_size:
                    if current:
                        chunks.append(current.strip())
                        current = ""
                    chunks.extend(split_recursive(part, separator_index + 1))
                    continue

                candidate = f"{current}\n\n{part}".strip() if current else part
                if self._size(candidate) <= self._config.max_chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current.strip())
                    current = part

            if current:
                chunks.append(current.strip())
            return chunks

        chunk_texts = split_recursive(text)
        return self._make_chunks(doc_id, self._with_overlap(chunk_texts), "recursive")

    def _local_semantic_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """本地语义分块：用相邻句/段相似度决定分块边界。"""
        units = self._split_by_paragraphs(text)
        if len(units) <= 1:
            units = self._split_by_sentences(text)
        if not units:
            return []

        chunk_texts = []
        current_units = []
        current_size = 0
        similarity_scores = []

        for unit in units:
            unit_size = self._size(unit)
            if unit_size > self._config.max_chunk_size:
                if current_units:
                    chunk_texts.append("\n\n".join(current_units))
                    current_units = []
                    current_size = 0
                chunk_texts.extend(chunk.content for chunk in self._recursive_chunking(unit, f"{doc_id}_s{len(chunk_texts)}"))
                continue

            similarity = 1.0
            if current_units:
                similarity = self._lexical_similarity("\n\n".join(current_units[-2:]), unit)
                similarity_scores.append(similarity)

            should_break = (
                current_units
                and current_size >= self._config.min_chunk_size
                and (
                    current_size + unit_size > self._config.max_chunk_size
                    or similarity < self._config.semantic_threshold
                )
            )

            if should_break:
                chunk_texts.append("\n\n".join(current_units))
                current_units = [unit]
                current_size = unit_size
            else:
                current_units.append(unit)
                current_size += unit_size

        if current_units:
            chunk_texts.append("\n\n".join(current_units))

        avg_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else None
        return self._make_chunks(
            doc_id,
            self._with_overlap(chunk_texts),
            "local_semantic",
            {"semantic_threshold": self._config.semantic_threshold, "avg_similarity": avg_similarity},
        )
    
    def _hybrid_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """混合策略：保留段落结构，使用本地语义相似度决定合并边界。"""
        units = self._split_by_paragraphs(text)
        if len(units) <= 1:
            units = self._split_by_sentences(text)
        if not units:
            return []

        chunk_texts = []
        current_units = []
        current_size = 0

        for unit in units:
            unit_size = self._size(unit)
            if unit_size > self._config.max_chunk_size:
                if current_units:
                    chunk_texts.append("\n\n".join(current_units))
                    current_units = []
                    current_size = 0
                chunk_texts.extend(chunk.content for chunk in self._recursive_chunking(unit, f"{doc_id}_h{len(chunk_texts)}"))
                continue

            similarity = (
                self._lexical_similarity("\n\n".join(current_units[-2:]), unit)
                if current_units else 1.0
            )
            should_break = (
                current_units
                and current_size >= self._config.min_chunk_size
                and (
                    current_size + unit_size > self._config.max_chunk_size
                    or similarity < self._config.semantic_threshold
                )
            )

            if should_break:
                chunk_texts.append("\n\n".join(current_units))
                current_units = [unit]
                current_size = unit_size
            else:
                current_units.append(unit)
                current_size += unit_size

        if current_units:
            chunk_texts.append("\n\n".join(current_units))

        return self._make_chunks(
            doc_id,
            self._with_overlap(chunk_texts),
            "semantic_hybrid",
            {"semantic_threshold": self._config.semantic_threshold},
        )

    # ==================== SPEAKER_AWARE_HYBRID 分块器 ====================

    # 语气词集合（来自2x3实验）
    _TONE_WORDS = {
        '嗯', '啊', '哦', '唉', '对', '好', '是', '呃', '哎', '额', '行',
        '嗯哼', '啊哈', '对对对', '嗯嗯', '嗯嗯嗯', '对对对', '是是是',
        '啊啊', '嗯嗯嗯嗯', '对对对', '行行行', '可以可以', '好好好'
    }

    def _is_tone_only(self, content: str) -> bool:
        """判断是否为纯语气词内容"""
        if len(content) < 3:
            return True

        content_clean = re.sub(r'[。！？，、；：\s]+', '', content)
        if not content_clean:
            return True

        for tone in self._TONE_WORDS:
            content_clean = content_clean.replace(tone, '')

        return len(content_clean) == 0

    def _filter_tone_words(self, text: str) -> str:
        """从文本中移除语气词"""
        result = text
        for tone in self._TONE_WORDS:
            result = result.replace(tone, '')
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _parse_speaker_document(self, content: str) -> List[Tuple[str, str]]:
        """解析带说话人标记的会议文档，并过滤噪音"""
        lines = content.strip().split('\n')
        utterances = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 匹配格式：[时间] 说话人ID: 内容
            match = re.match(r'\[([^\]]+)\]\s*(\d+)\s*[:：]\s*(.*)', line)
            if match:
                speaker = match.group(2)
                text = match.group(3).strip()

                # 过滤纯语气词和短内容
                if len(text) < 3:
                    continue
                if self._is_tone_only(text):
                    continue

                utterances.append((speaker, text))

        return utterances

    def _tokenize_for_similarity(self, text: str) -> List[str]:
        """轻量语义相似度分词（已过滤语气词）"""
        text = self._filter_tone_words(text)

        tokens = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9_]{2,}', text)

        cleaned_tokens = []
        for token in tokens:
            token = token.lower().strip()
            if not token or token in self._SIMILARITY_STOPWORDS:
                continue
            if len(token) == 1 and re.match(r'[\u4e00-\u9fa5a-zA-Z]', token):
                continue
            cleaned_tokens.append(token)
        return cleaned_tokens

    def _speaker_aware_similarity(self, text1: str, text2: str) -> float:
        """基于词频余弦相似度的语义近似"""
        tokens1 = self._tokenize_for_similarity(text1)
        tokens2 = self._tokenize_for_similarity(text2)

        if not tokens1 or not tokens2:
            return 0.0

        count1 = Counter(tokens1)
        count2 = Counter(tokens2)
        common = set(count1.keys()) & set(count2.keys())

        dot = sum(count1[token] * count2[token] for token in common)
        norm1 = math.sqrt(sum(v * v for v in count1.values()))
        norm2 = math.sqrt(sum(v * v for v in count2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _speaker_aware_hybrid_chunking(self, text: str, doc_id: str) -> List[Chunk]:
        """
        说话人感知的混合分块（带语气词过滤 + 失败回退）

        策略：
        - 优先保持语义连贯性
        - 说话人切换 = "加分项"（接近块大小限制时优先切分）
        - 说话人切换 ≠ "强制项"（内容连贯且块还小时合并）
        - 无说话人信息时回退为纯语义分块
        """
        # 尝试解析说话人文档
        utterances = self._parse_speaker_document(text)

        # 回退机制：无说话人信息时使用纯语义分块
        if not utterances:
            app_logger.info(f"[SpeakerAware] 文档 {doc_id} 无说话人信息，回退为纯语义分块")
            return self._local_semantic_chunking(text, doc_id)

        # 第一阶段：按语义分块
        raw_chunks = []
        current_speaker = utterances[0][0]
        current_content = [utterances[0][1]]
        current_length = len(utterances[0][1])
        speaker_switches_in_chunk = 0

        # 从配置获取参数
        min_size = self._config.min_chunk_size
        max_size = self._config.max_chunk_size
        threshold = self._config.semantic_threshold
        speaker_switch_bonus = 0.1  # 轻微惩罚说话人切换

        for i in range(1, len(utterances)):
            speaker, content = utterances[i]
            content_len = len(content)

            # 计算语义相似度
            current_text = ' '.join(current_content)
            similarity = self._speaker_aware_similarity(current_text, content)

            # 说话人切换检测，降低相似度
            speaker_switched = (speaker != current_speaker)
            if speaker_switched:
                similarity -= speaker_switch_bonus

            # 切分决策
            would_exceed = (current_length + content_len) > max_size
            has_min_size = current_length >= min_size
            low_similarity = similarity < threshold

            should_split = False
            if has_min_size and (would_exceed or low_similarity):
                should_split = True
            elif would_exceed and not has_min_size:
                should_split = True

            if should_split:
                # 保存当前 chunk
                chunk_text = ' '.join(current_content).strip()
                if chunk_text:
                    raw_chunks.append(chunk_text)

                # 开始新 chunk
                current_speaker = speaker
                current_content = [content]
                current_length = content_len
                speaker_switches_in_chunk = 0
            else:
                # 合并
                current_content.append(content)
                current_length += content_len
                if speaker_switched:
                    speaker_switches_in_chunk += 1
                    current_speaker = speaker

        # 处理最后一个 chunk
        if current_content:
            chunk_text = ' '.join(current_content).strip()
            if chunk_text:
                raw_chunks.append(chunk_text)

        # 第二阶段：添加块间重叠
        overlap = self._config.chunk_overlap
        if overlap > 0 and len(raw_chunks) > 1:
            chunks_with_overlap = []
            for i, chunk in enumerate(raw_chunks):
                if i > 0:
                    prev_chunk = raw_chunks[i - 1]
                    overlap_text = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
                    chunk = overlap_text + " " + chunk
                chunks_with_overlap.append(chunk)
        else:
            chunks_with_overlap = raw_chunks

        # 计算元数据
        info_densities = []
        for chunk in chunks_with_overlap:
            cleaned = self._filter_tone_words(chunk)
            info_densities.append(len(cleaned) / max(len(chunk), 1))

        return self._make_chunks(
            doc_id,
            chunks_with_overlap,
            "speaker_aware_hybrid",
            {
                "semantic_threshold": threshold,
                "speaker_switch_bonus": speaker_switch_bonus,
                "avg_info_density": sum(info_densities) / len(info_densities) if info_densities else 0,
                "has_speaker_info": True,
            },
        )

    def _merge_tiny_chunks(self, chunks: List[str]) -> List[str]:
        """合并过小块，减少碎片化。"""
        if not chunks:
            return []

        merged = []
        buffer = ""
        for chunk in chunks:
            if not buffer:
                buffer = chunk
                continue

            candidate = f"{buffer}\n\n{chunk}"
            if self._size(buffer) < self._config.min_chunk_size or self._size(candidate) <= self._config.max_chunk_size:
                buffer = candidate
            else:
                merged.append(buffer)
                buffer = chunk

        if buffer:
            if merged and self._size(buffer) < self._config.min_chunk_size:
                candidate = f"{merged[-1]}\n\n{buffer}"
                if self._size(candidate) <= self._config.max_chunk_size:
                    merged[-1] = candidate
                else:
                    merged.append(buffer)
            else:
                merged.append(buffer)
        return merged
    
    def build_hierarchy(self, chunks: List[Chunk]) -> List[Chunk]:
        """构建父子块层级关系"""
        if not self._config.build_hierarchy or len(chunks) < 3:
            return chunks
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                continue
            
            if chunk.level > chunks[i-1].level:
                chunk.parent_id = chunks[i-1].chunk_id
                chunks[i-1].child_ids.append(chunk.chunk_id)
            
            elif chunk.level == chunks[i-1].level and chunks[i-1].parent_id:
                chunk.parent_id = chunks[i-1].parent_id
            
            elif chunk.level < chunks[i-1].level:
                parent_idx = i - 1
                while parent_idx >= 0:
                    if chunks[parent_idx].level == chunk.level:
                        chunk.parent_id = chunks[parent_idx].chunk_id
                        chunks[parent_idx].child_ids.append(chunk.chunk_id)
                        break
                    parent_idx -= 1
        
        return chunks
    
    async def chunk_document(
        self,
        text: str,
        doc_id: str,
        metadata: Dict[str, Any] = None
    ) -> List[Chunk]:
        """
        文档分块主入口
        
        Args:
            text: 文档文本
            doc_id: 文档ID
            metadata: 文档元数据
            
        Returns:
            分块列表
        """
        if not text or not text.strip():
            return []
        
        if self._config.strategy == ChunkingStrategy.FIXED_SIZE:
            chunks = self._fixed_size_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.PARAGRAPH:
            chunks = self._paragraph_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.RECURSIVE:
            chunks = self._recursive_chunking(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.SEMANTIC:
            chunks = await self.semantic_split(text, doc_id)
        elif self._config.strategy == ChunkingStrategy.SPEAKER_AWARE_HYBRID:
            chunks = self._speaker_aware_hybrid_chunking(text, doc_id)
        else:
            chunks = self._hybrid_chunking(text, doc_id)
        
        for chunk in chunks:
            chunk.metadata.update(metadata or {})
        
        chunks = self.build_hierarchy(chunks)
        
        return chunks


class HierarchicalChunker:
    """层级分块器 - 保留文档结构"""
    
    def __init__(self, semantic_chunker: SemanticChunker = None):
        self._semantic_chunker = semantic_chunker or SemanticChunker()
    
    def _parse_headings(self, text: str) -> List[Tuple[str, int, str]]:
        """解析标题层级
        
        Returns:
            [(heading_text, level, position), ...]
        """
        patterns = [
            (r'^#{1}\s+(.+)$', 1),
            (r'^#{2}\s+(.+)$', 2),
            (r'^#{3}\s+(.+)$', 3),
            (r'^#{4}\s+(.+)$', 4),
            (r'^#{5}\s+(.+)$', 5),
            (r'^#{6}\s+(.+)$', 6),
        ]
        
        headings = []
        for line_num, line in enumerate(text.split('\n'), 1):
            for pattern, level in patterns:
                match = re.match(pattern, line.strip())
                if match:
                    headings.append((match.group(1), level, line_num))
                    break
        
        return headings
    
    def _extract_section(self, text: str, start: int, end: int) -> str:
        """提取文本段落"""
        lines = text.split('\n')
        return '\n'.join(lines[start:end])
    
    async def chunk_with_hierarchy(
        self,
        text: str,
        doc_id: str,
        metadata: Dict[str, Any] = None
    ) -> List[Chunk]:
        """
        保留层级结构的分块
        
        Args:
            text: 文档文本
            doc_id: 文档ID
            metadata: 元数据
            
        Returns:
            层级分块列表
        """
        headings = self._parse_headings(text)
        
        if not headings:
            return await self._semantic_chunker.chunk_document(text, doc_id, metadata)
        
        chunks = []
        doc_lines = text.split('\n')
        total_lines = len(doc_lines)
        
        for i, (heading, level, line_num) in enumerate(headings):
            start = line_num
            end = headings[i+1][2] if i+1 < len(headings) else total_lines
            
            section_text = '\n'.join(doc_lines[start-1:end])
            
            if self._semantic_chunker._count_tokens(section_text) < 100:
                continue
            
            section_chunks = await self._semantic_chunker.chunk_document(
                section_text,
                f"{doc_id}_{i}",
                {**(metadata or {}), "heading": heading, "heading_level": level}
            )
            
            for chunk in section_chunks:
                chunk.metadata["parent_heading"] = heading
                chunk.metadata["parent_level"] = level
            
            chunks.extend(section_chunks)
        
        chunks = self._semantic_chunker.build_hierarchy(chunks)
        
        return chunks


_semantic_chunker: Optional[SemanticChunker] = None


def build_chunking_config_from_settings() -> ChunkingConfig:
    """从全局配置构建语义分块配置（统一使用SPEAKER_AWARE_HYBRID策略）"""
    return ChunkingConfig(
        strategy=ChunkingStrategy.SPEAKER_AWARE_HYBRID,
        min_chunk_size=settings.SEMANTIC_CHUNK_MIN_SIZE,
        max_chunk_size=settings.SEMANTIC_CHUNK_MAX_SIZE,
        chunk_overlap=settings.SEMANTIC_CHUNK_OVERLAP,
        semantic_threshold=settings.SEMANTIC_CHUNK_THRESHOLD,
        use_llm_split=False,
        preserve_structure=False,
        build_hierarchy=False,
    )


def get_semantic_chunker() -> SemanticChunker:
    """获取语义分块器"""
    global _semantic_chunker
    if _semantic_chunker is None:
        _semantic_chunker = SemanticChunker(config=build_chunking_config_from_settings())
    return _semantic_chunker


def get_hierarchical_chunker() -> HierarchicalChunker:
    """获取层级分块器"""
    return HierarchicalChunker(get_semantic_chunker())
