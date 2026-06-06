import os
import re
import time
from pathlib import Path
from typing import List, Tuple, Dict
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class ExperimentChunker:
    TONE_WORDS = {'嗯', '啊', '哦', '唉', '对', '好', '是', '呃', '哎', '额', '行', '嗯哼', '啊哈', '对对对', '嗯嗯', '嗯嗯嗯'}
    
    def __init__(self):
        self.chunk_size = 512
        self.overlap = 64
        self.similarity_threshold = 0.6
        self.max_chunk_size_b2 = 800
        self.max_chunk_size_b3 = 1000
        self.min_chunk_size_b3 = 50  # 最小块大小阈值
        self.merge_threshold_b3 = 0.3  # 小碎片合并相似度阈值
    
    def parse_md_file(self, file_path: Path) -> List[Tuple[str, str, str]]:
        """解析带说话人信息的md文件，返回(timestamp, speaker, content)列表"""
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
        """构建纯文本内容（不过滤，仅去除标签）"""
        return '\n'.join(content for _, _, content in lines)
    
    def build_filtered_content(self, lines: List[Tuple[str, str, str]]) -> str:
        """构建过滤后的纯文本内容（去除标签+过滤语气词）"""
        filtered = self.filter_lines(lines)
        return '\n'.join(content for _, _, content in filtered)
    
    def get_speaker_content_pairs(self, lines: List[Tuple[str, str, str]], filtered: bool = False) -> List[Tuple[str, str]]:
        """获取(speaker, content)列表供B3使用"""
        target_lines = self.filter_lines(lines) if filtered else lines
        return [(speaker, content) for _, speaker, content in target_lines]
    
    def count_tone_chars(self, text: str) -> int:
        """计算文本中语气词字符数"""
        count = 0
        for tone in self.TONE_WORDS:
            count += text.count(tone) * len(tone)
        return count
    
    def calculate_info_density(self, text: str) -> float:
        """计算有效信息密度 = (总字符数 - 语气词字符数) / 总字符数"""
        if not text:
            return 0.0
        total_chars = len(text)
        tone_chars = self.count_tone_chars(text)
        return (total_chars - tone_chars) / max(total_chars, 1)
    
    def b1_fixed_size_chunking(self, text: str) -> List[str]:
        """B1: 固定大小分块"""
        chunks = []
        i = 0
        while i < len(text):
            chunk = text[i : i + self.chunk_size]
            if chunk.strip():
                chunks.append(chunk.strip())
            i += (self.chunk_size - self.overlap)
        return chunks
    
    def b2_similarity_chunking(self, text: str) -> List[str]:
        """B2: 混合相似度分块"""
        if not text.strip():
            return []
        
        if '\n\n' in text:
            paras = text.split('\n\n')
        else:
            paras = text.split('\n')
        
        paras = [p.strip() for p in paras if p.strip()]
        if not paras:
            return []
        
        merged = [paras[0]]
        vectorizer = CountVectorizer(token_pattern=r'(?u)\b\w+\b')
        
        for i in range(1, len(paras)):
            prev = merged[-1]
            curr = paras[i]
            
            try:
                corpus = [prev, curr]
                X = vectorizer.fit_transform(corpus)
                sim = cosine_similarity(X[0:1], X[1:2])[0][0]
            except:
                sim = 0.0
            
            if sim >= self.similarity_threshold and len(prev) + len(curr) + 1 <= self.max_chunk_size_b2:
                merged[-1] = prev + " " + curr
            else:
                merged.append(curr)
        
        return merged
    
    def b3_speaker_chunking(self, lines: List[Tuple[str, str]]) -> List[str]:
        """B3: 说话人切割分块 - 严格按说话人切换切分，包含小碎片合并"""
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
    
    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """合并小碎片：将小于阈值的块与相邻块合并"""
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
        """按最大长度切分，保持语义边界优先"""
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
    
    def analyze_chunks(self, chunks: List[str], is_b3: bool = False) -> Dict[str, float]:
        """分析块的各项指标"""
        if not chunks:
            return {
                'chunk_count': 0,
                'avg_chunk_size': 0.0,
                'chunk_size_std': 0.0,
                'noise_chunk_rate': 0.0,
                'avg_speaker_switches': None,
                'info_density': 0.0,
                'processing_time': 0.0
            }
        
        chunk_sizes = [len(chunk) for chunk in chunks]
        
        noise_count = sum(1 for chunk in chunks if self.is_tone_only(chunk))
        noise_chunk_rate = noise_count / len(chunks)
        
        info_density = np.mean([self.calculate_info_density(chunk) for chunk in chunks])
        
        avg_speaker_switches = None
        
        return {
            'chunk_count': len(chunks),
            'avg_chunk_size': np.mean(chunk_sizes),
            'chunk_size_std': np.std(chunk_sizes),
            'noise_chunk_rate': noise_chunk_rate,
            'avg_speaker_switches': avg_speaker_switches,
            'info_density': info_density,
            'processing_time': 0.0
        }
    
    def run_experiment(self, md_files: List[Path]) -> Dict[str, Dict[str, str]]:
        """运行完整实验，返回各实验组结果"""
        results = {
            'A1B1': [],
            'A1B2': [],
            'A1B3': [],
            'A2B1': [],
            'A2B2': [],
            'A2B3': []
        }
        
        for file_path in md_files:
            lines = self.parse_md_file(file_path)
            if not lines:
                continue
            
            raw_content = self.build_raw_content(lines)
            filtered_content = self.build_filtered_content(lines)
            raw_pairs = self.get_speaker_content_pairs(lines, filtered=False)
            filtered_pairs = self.get_speaker_content_pairs(lines, filtered=True)
            
            total_chars = len(raw_content)
            
            start = time.time()
            chunks_a1b1 = self.b1_fixed_size_chunking(raw_content)
            time_a1b1 = (time.time() - start) / max(total_chars, 1) * 1000
            
            start = time.time()
            chunks_a1b2 = self.b2_similarity_chunking(raw_content)
            time_a1b2 = (time.time() - start) / max(total_chars, 1) * 1000
            
            start = time.time()
            chunks_a1b3 = self.b3_speaker_chunking(raw_pairs)
            time_a1b3 = (time.time() - start) / max(total_chars, 1) * 1000
            
            start = time.time()
            chunks_a2b1 = self.b1_fixed_size_chunking(filtered_content)
            time_a2b1 = (time.time() - start) / max(total_chars, 1) * 1000
            
            start = time.time()
            chunks_a2b2 = self.b2_similarity_chunking(filtered_content)
            time_a2b2 = (time.time() - start) / max(total_chars, 1) * 1000
            
            start = time.time()
            chunks_a2b3 = self.b3_speaker_chunking(filtered_pairs)
            time_a2b3 = (time.time() - start) / max(total_chars, 1) * 1000
            
            def get_result(chunks, processing_time):
                result = self.analyze_chunks(chunks)
                result['processing_time'] = processing_time
                return result
            
            results['A1B1'].append(get_result(chunks_a1b1, time_a1b1))
            results['A1B2'].append(get_result(chunks_a1b2, time_a1b2))
            results['A1B3'].append(get_result(chunks_a1b3, time_a1b3))
            results['A2B1'].append(get_result(chunks_a2b1, time_a2b1))
            results['A2B2'].append(get_result(chunks_a2b2, time_a2b2))
            results['A2B3'].append(get_result(chunks_a2b3, time_a2b3))
        
        return self._aggregate_results(results)
    
    def _aggregate_results(self, results: Dict[str, List[Dict[str, float]]]) -> Dict[str, Dict[str, str]]:
        """汇总所有文件的结果"""
        aggregated = {}
        
        for group, file_results in results.items():
            if not file_results:
                aggregated[group] = {k: "N/A" for k in ['chunk_count', 'avg_chunk_size', 'chunk_size_std', 
                                                        'noise_chunk_rate', 'avg_speaker_switches', 
                                                        'info_density', 'processing_time']}
                continue
            
            metrics = {}
            for key in ['chunk_count', 'avg_chunk_size', 'chunk_size_std', 
                        'noise_chunk_rate', 'info_density', 'processing_time']:
                values = [r[key] for r in file_results]
                mean = np.mean(values)
                std = np.std(values)
                metrics[key] = f"{mean:.2f} ± {std:.2f}"
            
            speaker_switches_values = [r['avg_speaker_switches'] for r in file_results]
            if all(v is None for v in speaker_switches_values):
                metrics['avg_speaker_switches'] = "N/A"
            else:
                metrics['avg_speaker_switches'] = "0.00 ± 0.00"
            
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
    
    chunker = ExperimentChunker()
    
    print("\n开始运行实验...")
    results = chunker.run_experiment(md_files)
    
    print("\n" + "="*85)
    print("2×3 因子实验结果汇总（修正版）")
    print("="*85)
    print(f"实验文件数: {len(md_files)}")
    print("="*85)
    
    headers = ["实验组", "块数", "平均块大小", "块大小标准差", 
               "噪音块率", "平均说话人切换", "有效信息密度", "处理时间(ms/k字符)"]
    
    print(f"\n{'|'.join([h.center(12) for h in headers])}")
    print("-" * (12 * len(headers) + (len(headers)-1)))
    
    for group in ['A1B1', 'A1B2', 'A1B3', 'A2B1', 'A2B2', 'A2B3']:
        r = results[group]
        row = [
            group.center(12),
            r['chunk_count'].center(12),
            r['avg_chunk_size'].center(12),
            r['chunk_size_std'].center(12),
            r['noise_chunk_rate'].center(12),
            r['avg_speaker_switches'].center(12),
            r['info_density'].center(12),
            r['processing_time'].center(12)
        ]
        print("|".join(row))
    
    print("\n" + "="*85)
    print("实验组说明:")
    print("  A1: 无过滤 | A2: 有过滤")
    print("  B1: 固定大小分块 | B2: 混合相似度分块 | B3: 说话人切割分块")
    print("\n指标说明:")
    print("  - 所有组的'平均说话人切换'为 N/A（块内说话人信息不可直接获取）")
    print("  - B3策略包含小碎片合并机制（最小块大小阈值=50字符）")
    print("="*85)

if __name__ == "__main__":
    main()