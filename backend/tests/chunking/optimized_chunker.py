import os
import re
import time
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from tqdm import tqdm
import numpy as np

try:
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    print("请安装sklearn: pip install scikit-learn")
    raise

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    print("警告: 未安装sentence-transformers，B2将使用TF-IDF方法")
    print("如需使用语义embedding，请安装: pip install sentence-transformers")
    HAS_SENTENCE_TRANSFORMERS = False


class OptimizedExperimentChunker:
    """优化版分块器，支持多种语义优化策略"""
    
    TONE_WORDS = {'嗯', '啊', '哦', '唉', '对', '好', '是', '呃', '哎', '额', '行', '嗯哼', '啊哈', '对对对', '嗯嗯', '嗯嗯嗯'}
    
    def __init__(self, use_embedding: bool = True):
        self.chunk_size = 512
        self.overlap = 64
        self.similarity_threshold = 0.6
        self.max_chunk_size_b2 = 800
        self.max_chunk_size_b3 = 1000
        self.min_chunk_size_b3 = 50
        
        # 语义完整性阈值
        self.semantic_overlap_size = 50  # 重叠窗口大小
        
        # Embedding模型
        self.use_embedding = use_embedding and HAS_SENTENCE_TRANSFORMERS
        self.embedding_model = None
        if self.use_embedding:
            print("正在加载语义embedding模型...")
            try:
                self.embedding_model = SentenceTransformer(r'F:\project\meetingmind\backend\model\paraphrase-multilingual-MiniLM-L12-v2')
                print("模型加载完成！")
            except Exception as e:
                print(f"模型加载失败: {e}")
                print("回退到TF-IDF方法")
                self.use_embedding = False
    
    def parse_md_file(self, file_path: Path) -> List[Tuple[str, str, str]]:
        """解析带说话人信息的md文件"""
        lines = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[(\d{2}:\d{2}\.\d{2})\]\s*(\d+):\s*(.*)', line)
                if match:
                    timestamp = match.group(1)
                    speaker = match.group(2)
                    content = match.group(3).strip()
                    lines.append((timestamp, speaker, content))
        return lines
    
    def is_tone_only(self, content: str) -> bool:
        """判断是否为纯语气词内容"""
        if len(content) < 3:
            return True
        content_clean = re.sub(r'[。！？，、；：\s]+', '', content)
        if not content_clean:
            return True
        for tone in self.TONE_WORDS:
            content_clean = content_clean.replace(tone, '')
        return len(content_clean) == 0
    
    def filter_lines(self, lines: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
        """过滤纯语气词行和短行"""
        filtered = []
        for timestamp, speaker, content in lines:
            if len(content) < 3:
                continue
            if self.is_tone_only(content):
                continue
            filtered.append((timestamp, speaker, content))
        return filtered
    
    def build_raw_content(self, lines: List[Tuple[str, str, str]]) -> str:
        """构建纯文本内容"""
        return '\n'.join(content for _, _, content in lines)
    
    def build_filtered_content(self, lines: List[Tuple[str, str, str]]) -> str:
        """构建过滤后的纯文本内容"""
        filtered = self.filter_lines(lines)
        return '\n'.join(content for _, _, content in filtered)
    
    def get_speaker_content_pairs(self, lines: List[Tuple[str, str, str]], filtered: bool = False) -> List[Tuple[str, str]]:
        """获取(speaker, content)列表"""
        target_lines = self.filter_lines(lines) if filtered else lines
        return [(speaker, content) for _, speaker, content in target_lines]
    
    def count_tone_chars(self, text: str) -> int:
        """计算文本中语气词字符数"""
        count = 0
        for tone in self.TONE_WORDS:
            count += text.count(tone) * len(tone)
        return count
    
    def calculate_info_density(self, text: str) -> float:
        """计算有效信息密度"""
        if not text:
            return 0.0
        total_chars = len(text)
        tone_chars = self.count_tone_chars(text)
        return (total_chars - tone_chars) / max(total_chars, 1)
    
    # ==================== B1: 语义锚点分块（优化版） ====================
    def b1_fixed_size_chunking(self, text: str) -> List[str]:
        """B1: 固定大小分块（原始版）"""
        chunks = []
        i = 0
        while i < len(text):
            chunk = text[i : i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
            i += (self.chunk_size - self.overlap)
        return chunks
    
    def _find_semantic_boundary(self, text: str, start: int, end: int) -> int:
        """在[start, end)范围内寻找最佳语义边界"""
        min_context = 50  # 最少保留的字符数
        
        # 优先在句子边界切分（句号、问号、感叹号）
        for pos in range(end - 1, max(start + min_context, end - 100), -1):
            if text[pos] in '。！？':
                return pos + 1
        
        # 其次在逗号/分号处切分
        for pos in range(end - 1, max(start + min_context, end - 150), -1):
            if text[pos] in '，；':
                return pos + 1
        
        # 在换行处切分
        for pos in range(end - 1, start, -1):
            if text[pos] == '\n':
                return pos + 1
        
        # 在空格处切分
        for pos in range(end - 1, start, -1):
            if text[pos] == ' ':
                return pos + 1
        
        return end
    
    def b1_semantic_chunking(self, text: str) -> List[str]:
        """B1优化版: 语义锚点分块"""
        chunks = []
        i = 0
        
        with tqdm(total=len(text), desc="B1语义切分", leave=False) as pbar:
            while i < len(text):
                end_pos = min(i + self.chunk_size, len(text))
                boundary = self._find_semantic_boundary(text, i, end_pos)
                
                chunk = text[i:boundary].strip()
                if chunk:
                    chunks.append(chunk)
                
                pbar.update(boundary - i)
                i = boundary
        
        return chunks
    
    # ==================== B2: 语义embedding分块（优化版） ====================
    def b2_tfidf_chunking(self, text: str) -> List[str]:
        """B2: TF-IDF相似度分块（原始版）"""
        if not text.strip():
            return []
        
        paras = text.split('\n') if '\n' in text else [text]
        paras = [p.strip() for p in paras if p.strip()]
        if not paras:
            return []
        
        merged = [paras[0]]
        vectorizer = CountVectorizer(token_pattern=r'(?u)\b\w+\b')
        
        for i in range(1, len(paras)):
            prev = merged[-1]
            curr = paras[i]
            try:
                X = vectorizer.fit_transform([prev, curr])
                sim = cosine_similarity(X[0:1], X[1:2])[0][0]
            except:
                sim = 0.0
            
            if sim >= self.similarity_threshold and len(prev) + len(curr) + 1 <= self.max_chunk_size_b2:
                merged[-1] = prev + " " + curr
            else:
                merged.append(curr)
        
        return merged
    
    def b2_embedding_chunking(self, text: str) -> List[str]:
        """B2优化版: 基于语义embedding的分块"""
        if not text.strip():
            return []
        
        sentences = self._split_into_sentences(text)
        if len(sentences) <= 1:
            return [text.strip()]
        
        print(f"  计算 {len(sentences)} 个句子的语义embedding...")
        embeddings = self.embedding_model.encode(sentences, show_progress_bar=False)
        
        chunks = [sentences[0]]
        
        for i in range(1, len(sentences)):
            sim = cosine_similarity([embeddings[i-1]], [embeddings[i]])[0][0]
            
            if sim >= self.similarity_threshold and len(chunks[-1]) + len(sentences[i]) <= self.max_chunk_size_b2:
                chunks[-1] = chunks[-1] + " " + sentences[i]
            else:
                chunks.append(sentences[i])
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """将文本拆分为句子"""
        sentences = re.split(r'[。！？\n]+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def b2_similarity_chunking(self, text: str) -> List[str]:
        """B2: 智能选择分块方法"""
        if self.use_embedding and self.embedding_model:
            return self.b2_embedding_chunking(text)
        return self.b2_tfidf_chunking(text)
    
    # ==================== B3: 说话人+语义完整性分块（优化版） ====================
    def b3_speaker_chunking(self, lines: List[Tuple[str, str]]) -> List[str]:
        """B3: 说话人切割分块（原始版）"""
        if not lines:
            return []
        
        chunks = []
        current_speaker = None
        current_content = []
        
        for speaker, content in lines:
            if current_speaker is None:
                current_speaker = speaker
            
            if speaker != current_speaker:
                chunk_text = " ".join(current_content)
                if chunk_text.strip():
                    chunks.extend(self._split_by_max_size(chunk_text, self.max_chunk_size_b3))
                current_content = []
                current_speaker = speaker
            
            current_content.append(content)
        
        if current_content:
            chunk_text = " ".join(current_content)
            if chunk_text.strip():
                chunks.extend(self._split_by_max_size(chunk_text, self.max_chunk_size_b3))
        
        chunks = self._merge_small_chunks(chunks)
        return chunks
    
    def _is_complete_semantic_unit(self, text: str) -> bool:
        """检查文本是否为完整的语义单元"""
        if not text:
            return False
        return any(marker in text for marker in '。！？')
    
    def b3_semantic_chunking(self, lines: List[Tuple[str, str]]) -> List[str]:
        """B3优化版: 说话人+语义完整性分块"""
        if not lines:
            return []
        
        chunks = []
        current_speaker = None
        current_content = []
        current_length = 0
        
        for speaker, content in lines:
            if current_speaker is None:
                current_speaker = speaker
            
            should_split = False
            
            if speaker != current_speaker:
                if current_length >= 80:
                    if self._is_complete_semantic_unit(" ".join(current_content)):
                        should_split = True
            
            if current_length >= self.max_chunk_size_b3:
                should_split = True
            
            if should_split:
                chunk_text = " ".join(current_content)
                if chunk_text.strip():
                    sub_chunks = self._split_by_max_size(chunk_text, self.max_chunk_size_b3)
                    chunks.extend(sub_chunks)
                current_content = []
                current_length = 0
                current_speaker = speaker
            
            current_content.append(content)
            current_length += len(content)
        
        if current_content:
            chunk_text = " ".join(current_content)
            if chunk_text.strip():
                chunks.extend(self._split_by_max_size(chunk_text, self.max_chunk_size_b3))
        
        chunks = self._merge_small_chunks(chunks)
        return chunks
    
    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """合并小碎片"""
        if len(chunks) <= 1:
            return chunks
        
        merged = []
        i = 0
        
        while i < len(chunks):
            current = chunks[i]
            
            if len(current) >= self.min_chunk_size_b3:
                merged.append(current)
                i += 1
            else:
                if i == len(chunks) - 1:
                    if merged:
                        merged[-1] = merged[-1] + " " + current
                    else:
                        merged.append(current)
                    i += 1
                else:
                    next_chunk = chunks[i + 1]
                    merged.append(current + " " + next_chunk)
                    i += 2
        
        return merged
    
    def _split_by_max_size(self, text: str, max_size: int) -> List[str]:
        """按最大长度切分"""
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        remaining = text
        
        while len(remaining) > max_size:
            split_pos = remaining.rfind('。', 0, max_size)
            if split_pos == -1:
                split_pos = remaining.rfind('，', 0, max_size)
            if split_pos == -1:
                split_pos = max_size
            
            chunks.append(remaining[:split_pos+1].strip())
            remaining = remaining[split_pos+1:].strip()
        
        if remaining:
            chunks.append(remaining)
        
        return chunks
    
    def add_semantic_overlap(self, chunks: List[str]) -> List[str]:
        """为chunks添加语义重叠"""
        if len(chunks) <= 1:
            return chunks
        
        enhanced = []
        
        for i, chunk in enumerate(chunks):
            enhanced_chunk = chunk
            
            if i > 0:
                prev_end = chunks[i-1][-self.semantic_overlap_size:]
                if prev_end.strip():
                    enhanced_chunk = prev_end + " " + enhanced_chunk
            
            if i < len(chunks) - 1:
                next_start = chunks[i+1][:self.semantic_overlap_size]
                if next_start.strip():
                    enhanced_chunk = enhanced_chunk + " " + next_start
            
            enhanced.append(enhanced_chunk)
        
        return enhanced
    
    def calculate_semantic_completeness(self, chunk: str) -> float:
        """计算语义完整性得分"""
        score = 0.0

        if chunk.endswith(('。', '！', '？')):
            score += 0.3

        if 50 <= len(chunk) <= 1000:
            score += 0.3

        incomplete_patterns = [r'的[，。]', r'是[，。]', r'我觉[得得][，。]']
        for pattern in incomplete_patterns:
            if re.search(pattern, chunk):
                return score

        score += 0.2

        return score
    
    def analyze_chunks(self, chunks: List[str]) -> Dict[str, float]:
        """分析块的各项指标"""
        if not chunks:
            return {
                'chunk_count': 0,
                'avg_chunk_size': 0.0,
                'chunk_size_std': 0.0,
                'noise_chunk_rate': 0.0,
                'info_density': 0.0,
                'semantic_completeness': 0.0,
                'processing_time': 0.0
            }
        
        chunk_sizes = [len(chunk) for chunk in chunks]
        noise_count = sum(1 for chunk in chunks if self.is_tone_only(chunk))
        info_density = np.mean([self.calculate_info_density(chunk) for chunk in chunks])
        semantic_score = np.mean([self.calculate_semantic_completeness(chunk) for chunk in chunks])
        
        return {
            'chunk_count': len(chunks),
            'avg_chunk_size': np.mean(chunk_sizes),
            'chunk_size_std': np.std(chunk_sizes),
            'noise_chunk_rate': noise_count / len(chunks),
            'info_density': info_density,
            'semantic_completeness': semantic_score,
            'processing_time': 0.0
        }
    
    def run_experiment(self, md_files: List[Path], enable_overlap: bool = False) -> Dict[str, Dict[str, str]]:
        """运行完整实验"""
        results = {
            'B1原始': [],
            'B1优化': [],
            'B2原始': [],
            'B2优化': [],
            'B3原始': [],
            'B3优化': []
        }
        
        print(f"\n开始处理 {len(md_files)} 个文件...")
        
        for file_path in tqdm(md_files, desc="处理文件"):
            lines = self.parse_md_file(file_path)
            if not lines:
                continue
            
            raw_content = self.build_raw_content(lines)
            filtered_content = self.build_filtered_content(lines)
            raw_pairs = self.get_speaker_content_pairs(lines, filtered=False)
            filtered_pairs = self.get_speaker_content_pairs(lines, filtered=True)
            
            total_chars = len(raw_content)
            
            with tqdm(total=6, desc=f"分块策略", leave=False) as pbar:
                start = time.time()
                chunks_b1_raw = self.b1_fixed_size_chunking(raw_content)
                time_b1_raw = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
                
                start = time.time()
                chunks_b1_opt = self.b1_semantic_chunking(filtered_content)
                time_b1_opt = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
                
                start = time.time()
                chunks_b2_raw = self.b2_tfidf_chunking(raw_content)
                time_b2_raw = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
                
                start = time.time()
                chunks_b2_opt = self.b2_similarity_chunking(filtered_content)
                time_b2_opt = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
                
                start = time.time()
                chunks_b3_raw = self.b3_speaker_chunking(raw_pairs)
                time_b3_raw = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
                
                start = time.time()
                chunks_b3_opt = self.b3_semantic_chunking(filtered_pairs)
                time_b3_opt = (time.time() - start) / max(total_chars, 1) * 1000
                pbar.update(1)
            
            if enable_overlap:
                chunks_b1_raw = self.add_semantic_overlap(chunks_b1_raw)
                chunks_b1_opt = self.add_semantic_overlap(chunks_b1_opt)
                chunks_b2_raw = self.add_semantic_overlap(chunks_b2_raw)
                chunks_b2_opt = self.add_semantic_overlap(chunks_b2_opt)
                chunks_b3_raw = self.add_semantic_overlap(chunks_b3_raw)
                chunks_b3_opt = self.add_semantic_overlap(chunks_b3_opt)
            
            def get_result(chunks, processing_time):
                result = self.analyze_chunks(chunks)
                result['processing_time'] = processing_time
                return result
            
            results['B1原始'].append(get_result(chunks_b1_raw, time_b1_raw))
            results['B1优化'].append(get_result(chunks_b1_opt, time_b1_opt))
            results['B2原始'].append(get_result(chunks_b2_raw, time_b2_raw))
            results['B2优化'].append(get_result(chunks_b2_opt, time_b2_opt))
            results['B3原始'].append(get_result(chunks_b3_raw, time_b3_raw))
            results['B3优化'].append(get_result(chunks_b3_opt, time_b3_opt))
        
        return self._aggregate_results(results)
    
    def _aggregate_results(self, results: Dict[str, List[Dict[str, float]]]) -> Dict[str, Dict[str, str]]:
        """汇总结果"""
        aggregated = {}
        
        for group, file_results in results.items():
            if not file_results:
                aggregated[group] = {k: "N/A" for k in ['chunk_count', 'avg_chunk_size', 
                    'chunk_size_std', 'noise_chunk_rate', 'info_density', 'semantic_completeness', 'processing_time']}
                continue
            
            metrics = {}
            for key in ['chunk_count', 'avg_chunk_size', 'chunk_size_std', 
                        'noise_chunk_rate', 'info_density', 'semantic_completeness', 'processing_time']:
                values = [r[key] for r in file_results]
                mean = np.mean(values)
                std = np.std(values)
                metrics[key] = f"{mean:.2f} ± {std:.2f}"
            
            aggregated[group] = metrics
        
        return aggregated


def main():
    base_dir = Path(r"F:\project\meetingmind\backend\tests\AliMeeting")
    md_dir = base_dir / "meeting_docs_with_speaker"
    
    md_files = list(md_dir.glob("*.md"))
    print(f"找到 {len(md_files)} 个md文件")
    
    if len(md_files) == 0:
        print("未找到任何md文件")
        return
    
    chunker = OptimizedExperimentChunker(use_embedding=True)
    
    print("\n" + "="*100)
    print("分块策略优化实验")
    print("="*100)
    
    results = chunker.run_experiment(md_files, enable_overlap=False)
    
    print("\n" + "="*100)
    print("实验结果汇总（不含重叠）")
    print("="*100)
    
    headers = ["策略", "块数", "平均块大小", "块大小标准差", "噪音块率", 
               "信息密度", "语义完整性", "处理时间(ms/k字符)"]
    
    print(f"\n{'|'.join([h.center(13) for h in headers])}")
    print("-" * (13 * len(headers) + (len(headers)-1)))
    
    for group in ['B1原始', 'B1优化', 'B2原始', 'B2优化', 'B3原始', 'B3优化']:
        r = results[group]
        row = [
            group.center(13),
            r['chunk_count'].center(13),
            r['avg_chunk_size'].center(13),
            r['chunk_size_std'].center(13),
            r['noise_chunk_rate'].center(13),
            r['info_density'].center(13),
            r['semantic_completeness'].center(13),
            r['processing_time'].center(13)
        ]
        print("|".join(row))
    
    print("\n" + "="*100)
    print("策略说明:")
    print("  B1: 固定大小分块 | B2: 相似度分块 | B3: 说话人分块")
    print("  原始: 基础实现 | 优化: 语义优化版本")
    print("="*100)
    
    print("\n优化效果对比:")
    print("-" * 80)
    
    def parse_metric(metric_str):
        mean = float(metric_str.split('±')[0].strip())
        return mean
    
    improvements = {
        'B1': {
            '块数变化': f"{(parse_metric(results['B1原始']['chunk_count']) - parse_metric(results['B1优化']['chunk_count'])) / parse_metric(results['B1原始']['chunk_count']) * 100:.1f}%",
            '语义完整性提升': f"{(parse_metric(results['B1优化']['semantic_completeness']) - parse_metric(results['B1原始']['semantic_completeness'])) * 100:.1f}%"
        },
        'B2': {
            '块数变化': f"{(parse_metric(results['B2原始']['chunk_count']) - parse_metric(results['B2优化']['chunk_count'])) / parse_metric(results['B2原始']['chunk_count']) * 100:.1f}%",
            '语义完整性提升': f"{(parse_metric(results['B2优化']['semantic_completeness']) - parse_metric(results['B2原始']['semantic_completeness'])) * 100:.1f}%"
        },
        'B3': {
            '块数变化': f"{(parse_metric(results['B3原始']['chunk_count']) - parse_metric(results['B3优化']['chunk_count'])) / parse_metric(results['B3原始']['chunk_count']) * 100:.1f}%",
            '语义完整性提升': f"{(parse_metric(results['B3优化']['semantic_completeness']) - parse_metric(results['B3原始']['semantic_completeness'])) * 100:.1f}%"
        }
    }
    
    for strategy, stats in improvements.items():
        print(f"{strategy}策略:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
    
    print("-" * 80)


if __name__ == "__main__":
    main()
