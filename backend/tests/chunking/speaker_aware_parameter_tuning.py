"""
SPEAKER_AWARE_HYBRID 参数调优实验

策略：说话人感知的混合分块（带语气词过滤）
- 优先保持段落/语义连贯性
- 说话人切换 = "加分项"（接近块大小限制时优先切分）
- 说话人切换 ≠ "强制项"（内容连贯且块还小时合并）
- 严格遵守最大/最小块大小限制
- 过滤语气词和纯噪音内容
"""

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Tuple

import numpy as np
from tqdm import tqdm

# 尝试导入 jieba，没有的话用简单分词
try:
    import jieba
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False


class SpeakerAwareHybridChunker:
    """
    说话人感知的混合分块器（带语气词过滤）
    
    特征：
    1. 过滤纯语气词行和短行
    2. 语义相似度计算时去除语气词
    3. 说话人切换作为切分加分项而非强制项
    4. 支持块大小限制和重叠
    """

    # 语气词集合（来自2x3实验）
    TONE_WORDS = {
        '嗯', '啊', '哦', '唉', '对', '好', '是', '呃', '哎', '额', '行',
        '嗯哼', '啊哈', '对对对', '嗯嗯', '嗯嗯嗯', '对对对', '是是是',
        '啊啊', '嗯嗯嗯嗯', '对对对', '行行行', '可以可以', '好好好'
    }

    # 语义相似度计算时的停用词
    SIMILARITY_STOPWORDS = {
        '的', '了', '和', '与', '及', '或', '是', '在', '有', '为', '对', '中',
        '需要', '进行', '包括', '以及', '一个', '这个', '那个', '我们', '他们'
    }

    def __init__(
        self,
        min_chunk_size: int = 80,
        max_chunk_size: int = 400,
        chunk_overlap: int = 50,
        semantic_threshold: float = 0.6,
        speaker_switch_bonus: float = 0.2
    ):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.semantic_threshold = semantic_threshold
        self.speaker_switch_bonus = speaker_switch_bonus

    def _is_tone_only(self, content: str) -> bool:
        """判断是否为纯语气词内容"""
        if len(content) < 3:
            return True
        
        # 去除标点和空格
        content_clean = re.sub(r'[。！？，、；：\s]+', '', content)
        if not content_clean:
            return True
        
        # 去除语气词
        for tone in self.TONE_WORDS:
            content_clean = content_clean.replace(tone, '')
        
        return len(content_clean) == 0

    def _filter_tone_words(self, text: str) -> str:
        """从文本中移除语气词"""
        result = text
        for tone in self.TONE_WORDS:
            result = result.replace(tone, '')
        # 清理多余空格
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def _tokenize_for_similarity(self, text: str) -> List[str]:
        """轻量语义相似度分词（已过滤语气词）"""
        # 先过滤语气词
        text = self._filter_tone_words(text)
        
        if HAS_JIEBA:
            tokens = jieba.lcut(text)
        else:
            # 简单分词：按非中文字符分割
            tokens = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9_]{2,}', text)

        cleaned_tokens = []
        for token in tokens:
            token = token.lower().strip()
            if not token or token in self.SIMILARITY_STOPWORDS:
                continue
            if len(token) == 1 and re.match(r'[\u4e00-\u9fa5a-zA-Z]', token):
                continue
            cleaned_tokens.append(token)
        return cleaned_tokens

    def _lexical_similarity(self, text1: str, text2: str) -> float:
        """基于词频余弦相似度的本地语义近似"""
        tokens1 = self._tokenize_for_similarity(text1)
        tokens2 = self._tokenize_for_similarity(text2)

        if not tokens1 or not tokens2:
            return 0.0

        count1 = Counter(tokens1)
        count2 = Counter(tokens2)
        common = set(count1.keys()) & set(count2.keys())

        dot = sum(count1[token] * count2[token] for token in common)
        norm1 = np.sqrt(sum(v * v for v in count1.values()))
        norm2 = np.sqrt(sum(v * v for v in count2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

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

    def _count_info_chars(self, text: str) -> int:
        """计算有效信息字符数（去除语气词）"""
        cleaned = self._filter_tone_words(text)
        return len(cleaned)

    def chunk_document(self, content: str) -> Tuple[List[str], Dict[str, Any]]:
        """
        说话人感知的混合分块（带语气词过滤）

        Returns:
            (chunks_list, metadata_dict)
        """
        utterances = self._parse_speaker_document(content)

        if not utterances:
            return [], {}

        # 第一阶段：按语义分块
        raw_chunks = []
        current_speaker = utterances[0][0]
        current_content = [utterances[0][1]]
        current_length = len(utterances[0][1])
        current_info_length = self._count_info_chars(utterances[0][1])
        speaker_switches_in_chunk = 0
        cut_sentences = 0
        total_sentences = 0

        for i in range(1, len(utterances)):
            speaker, text = utterances[i]
            text_len = len(text)
            text_info_len = self._count_info_chars(text)

            # 统计句子
            sentences = re.split(r'[。！？!?]', text)
            total_sentences += len([s for s in sentences if s.strip()])

            # 计算语义相似度（基于过滤后的文本）
            current_text = ' '.join(current_content)
            similarity = self._lexical_similarity(current_text, text)

            # 说话人切换检测
            speaker_switched = (speaker != current_speaker)
            if speaker_switched:
                similarity -= self.speaker_switch_bonus  # 降低相似度，促进切分

            # 计算是否需要切分（使用实际字符长度）
            would_exceed = (current_length + text_len) > self.max_chunk_size
            has_min_size = current_length >= self.min_chunk_size
            low_similarity = similarity < self.semantic_threshold

            # 切分决策
            should_split = False
            if has_min_size and (would_exceed or low_similarity):
                should_split = True
            elif would_exceed and not has_min_size:
                # 超过最大但还没到最小，必须切分但要合并
                should_split = True

            if should_split:
                # 保存当前 chunk
                chunk_text = ' '.join(current_content).strip()
                if chunk_text:
                    # 检查句子是否被切断
                    if not chunk_text.endswith(('。', '！', '？', '.', '!', '?')):
                        cut_sentences += 1

                    raw_chunks.append(chunk_text)

                # 开始新 chunk
                current_speaker = speaker
                current_content = [text]
                current_length = text_len
                current_info_length = text_info_len
                speaker_switches_in_chunk = 0
            else:
                # 合并
                current_content.append(text)
                current_length += text_len
                current_info_length += text_info_len
                if speaker_switched:
                    speaker_switches_in_chunk += 1
                    current_speaker = speaker

        # 处理最后一个 chunk
        if current_content:
            chunk_text = ' '.join(current_content).strip()
            if chunk_text:
                if not chunk_text.endswith(('。', '！', '？', '.', '!', '?')):
                    cut_sentences += 1
                raw_chunks.append(chunk_text)

        # 第二阶段：添加重叠（真正在块之间添加重叠内容）
        if self.chunk_overlap > 0 and len(raw_chunks) > 1:
            chunks = []
            for i, chunk in enumerate(raw_chunks):
                if i > 0:
                    # 添加前一个块的末尾作为重叠
                    prev_chunk = raw_chunks[i - 1]
                    overlap_text = prev_chunk[-self.chunk_overlap:] if len(prev_chunk) > self.chunk_overlap else prev_chunk
                    chunk = overlap_text + " " + chunk
                chunks.append(chunk)
        else:
            chunks = raw_chunks

        # 计算元数据
        chunk_sizes = [len(c) for c in chunks]
        info_densities = [self._count_info_chars(c) / max(len(c), 1) for c in chunks]
        
        metadata = {
            'chunk_count': len(chunks),
            'avg_chunk_size': np.mean(chunk_sizes) if chunks else 0,
            'chunk_size_std': np.std(chunk_sizes) if chunks else 0,
            'semantic_completeness': 1 - (cut_sentences / max(total_sentences, 1)),
            'speaker_switches_in_chunk': speaker_switches_in_chunk,
            'avg_info_density': np.mean(info_densities) if info_densities else 0
        }

        return chunks, metadata


class RetrievalSimulator:
    """模拟检索评估器（使用 TF-IDF）"""

    def __init__(self, chunks: List[str]):
        self.chunks = chunks
        self.chunk_tokens = [self._tokenize(c) for c in chunks]

    def _tokenize(self, text: str) -> Counter:
        if HAS_JIEBA:
            tokens = jieba.lcut(text)
        else:
            tokens = re.findall(r'[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9_]{2,}', text)
        return Counter([t.lower() for t in tokens if t and len(t) > 1])

    def _compute_similarity(self, query_tokens: Counter, chunk_idx: int) -> float:
        chunk_tokens = self.chunk_tokens[chunk_idx]
        common = set(query_tokens.keys()) & set(chunk_tokens.keys())
        dot = sum(query_tokens[t] * chunk_tokens[t] for t in common)
        norm_q = np.sqrt(sum(v * v for v in query_tokens.values()))
        norm_c = np.sqrt(sum(v * v for v in chunk_tokens.values()))
        if norm_q == 0 or norm_c == 0:
            return 0.0
        return dot / (norm_q * norm_c)

    def retrieve(self, query: str, top_k: int = 5) -> List[int]:
        query_tokens = self._tokenize(query)
        scores = []
        for i in range(len(self.chunks)):
            scores.append((self._compute_similarity(query_tokens, i), i))
        scores.sort(reverse=True, key=lambda x: x[0])
        return [i for _, i in scores[:top_k]]


class ParameterTuningExperiment:
    """参数调优实验主类"""

    # 优化后的参数网格（基于数据集特征）
    PARAM_GRID = {
        'min_chunk_size': [50, 80, 100],        # 单条发言短，需要更小的最小值
        'max_chunk_size': [300, 400, 500],      # 10条合并约300字符
        'chunk_overlap': [30, 50, 80],          # 重叠不宜太大
        'semantic_threshold': [0.5, 0.6, 0.7],  # 降低阈值促进合并
        'speaker_switch_bonus': [0.1, 0.2, 0.3] # 避免过度切分
    }

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.results: List[Dict[str, Any]] = []

    def load_documents(self, max_docs: int = None) -> List[Tuple[str, str]]:
        """加载会议文档"""
        docs = []
        doc_files = sorted(list(self.data_dir.glob('*.md')))
        
        if max_docs:
            doc_files = doc_files[:max_docs]
        
        for file_path in tqdm(doc_files, desc="加载文档"):
            try:
                content = file_path.read_text(encoding='utf-8')
                docs.append((file_path.name, content))
            except Exception as e:
                print(f"Warning: Failed to load {file_path.name}: {e}")

        return docs

    def _generate_simple_queries(self, content: str, num_queries: int = 3) -> List[str]:
        """从文档中生成简单测试查询"""
        # 提取有效内容（过滤语气词后的句子）
        sentences = re.split(r'[。！？!?]', content)
        valid_sentences = []
        
        for s in sentences:
            s = s.strip()
            if len(s) > 10:
                # 过滤掉纯语气词
                cleaned = re.sub(r'[嗯啊哦对呃哎行是\s]+', '', s)
                if len(cleaned) > 5:
                    valid_sentences.append(s)
        
        queries = []
        for s in valid_sentences[:num_queries]:
            # 取句子前半部分作为查询
            mid = len(s) // 2
            queries.append(s[:mid])

        return queries if queries else ["会议内容"]

    def run_single_config(
        self,
        docs: List[Tuple[str, str]],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """运行单个参数配置的测试"""
        chunker = SpeakerAwareHybridChunker(
            min_chunk_size=config['min_chunk_size'],
            max_chunk_size=config['max_chunk_size'],
            chunk_overlap=config['chunk_overlap'],
            semantic_threshold=config['semantic_threshold'],
            speaker_switch_bonus=config['speaker_switch_bonus']
        )

        all_chunks = []
        all_metadata = []
        all_queries = []
        chunk_to_doc = {}  # 记录 chunk 来自哪个文档
        chunk_offset = 0

        start_time = time.time()

        # 分块所有文档
        for doc_name, content in docs:
            chunks, metadata = chunker.chunk_document(content)
            all_chunks.extend(chunks)
            all_metadata.append(metadata)

            for i in range(len(chunks)):
                chunk_to_doc[chunk_offset + i] = doc_name
            chunk_offset += len(chunks)

            # 生成查询
            queries = self._generate_simple_queries(content)
            for q in queries:
                all_queries.append((q, doc_name))

        # 模拟检索评估
        if all_chunks:
            simulator = RetrievalSimulator(all_chunks)

            recalls = []
            precisions = []
            mrr_total = 0.0

            for query, relevant_doc in all_queries:
                top_indices = simulator.retrieve(query, top_k=5)

                # 检查是否命中相关文档
                found = False
                first_rank = None
                for rank, idx in enumerate(top_indices):
                    if chunk_to_doc[idx] == relevant_doc:
                        found = True
                        if first_rank is None:
                            first_rank = rank + 1

                recalls.append(1.0 if found else 0.0)
                precisions.append(1.0 / 5.0 if found else 0.0)

                if first_rank:
                    mrr_total += 1.0 / first_rank

            metrics = {
                'recall_at_5': np.mean(recalls) if recalls else 0,
                'precision_at_5': np.mean(precisions) if precisions else 0,
                'mrr': mrr_total / len(all_queries) if all_queries else 0
            }
        else:
            metrics = {'recall_at_5': 0, 'precision_at_5': 0, 'mrr': 0}

        processing_time = time.time() - start_time

        # 汇总分块质量指标
        avg_chunk_count = np.mean([m['chunk_count'] for m in all_metadata])
        avg_chunk_size = np.mean([m['avg_chunk_size'] for m in all_metadata])
        avg_chunk_std = np.mean([m['chunk_size_std'] for m in all_metadata])
        avg_semantic_completeness = np.mean([m['semantic_completeness'] for m in all_metadata])
        avg_info_density = np.mean([m['avg_info_density'] for m in all_metadata])

        result = {
            'config': config,
            'chunking': {
                'avg_chunk_count': avg_chunk_count,
                'avg_chunk_size': avg_chunk_size,
                'chunk_size_std': avg_chunk_std,
                'semantic_completeness': avg_semantic_completeness,
                'avg_info_density': avg_info_density
            },
            'retrieval': metrics,
            'performance': {
                'processing_time': processing_time,
                'docs_per_second': len(docs) / processing_time if processing_time > 0 else 0
            }
        }

        return result

    def run(self, max_docs: int = None, save_interval: int = 20):
        """运行完整参数调优实验"""
        from itertools import product

        print("=" * 80)
        print("SPEAKER_AWARE_HYBRID 参数调优实验")
        print("(带语气词过滤 + 说话人感知)")
        print("=" * 80)

        # 生成所有参数组合
        combinations = list(product(
            self.PARAM_GRID['min_chunk_size'],
            self.PARAM_GRID['max_chunk_size'],
            self.PARAM_GRID['chunk_overlap'],
            self.PARAM_GRID['semantic_threshold'],
            self.PARAM_GRID['speaker_switch_bonus']
        ))

        # 过滤无效组合
        valid_combinations = []
        for min_size, max_size, overlap, threshold, bonus in combinations:
            if min_size < max_size:  # 确保 min < max
                valid_combinations.append((min_size, max_size, overlap, threshold, bonus))

        total_configs = len(valid_combinations)
        print(f"\n参数组合总数: {total_configs}")
        print(f"参数网格: {self.PARAM_GRID}")

        # 加载文档
        docs = self.load_documents(max_docs=max_docs)
        print(f"加载文档数: {len(docs)}")

        if len(docs) == 0:
            print("错误: 未找到文档!")
            return

        # 遍历参数组合
        print("\n开始参数调优...")
        print("-" * 80)
        
        pbar = tqdm(total=total_configs, desc="参数组合", unit="config")
        
        for idx, (min_size, max_size, overlap, threshold, bonus) in enumerate(valid_combinations):
            config = {
                'min_chunk_size': min_size,
                'max_chunk_size': max_size,
                'chunk_overlap': overlap,
                'semantic_threshold': threshold,
                'speaker_switch_bonus': bonus
            }

            result = self.run_single_config(docs, config)
            self.results.append(result)

            # 定期保存
            if (idx + 1) % save_interval == 0:
                self.save_results()
                pbar.set_postfix({'已保存': f'{idx + 1}'})

            pbar.update(1)

        pbar.close()
        
        self.save_results()
        self.print_summary()

    def save_results(self, output_path: Path = None):
        """保存实验结果"""
        if output_path is None:
            output_path = self.data_dir.parent / "speaker_aware_experiment_results.json"

        output_data = {
            'experiment_name': 'SPEAKER_AWARE_HYBRID 参数调优',
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'param_grid': self.PARAM_GRID,
            'total_combinations': len(self.results),
            'results': self.results
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\n结果已保存到: {output_path}")

    def print_summary(self):
        """打印实验总结"""
        if not self.results:
            print("\n没有可用结果")
            return

        print("\n" + "=" * 100)
        print("实验结果 TOP 15 (按 MRR 排序)")
        print("=" * 100)

        # 按 MRR 排序
        sorted_results = sorted(
            self.results,
            key=lambda x: x['retrieval']['mrr'],
            reverse=True
        )

        headers = ["排名", "min", "max", "overlap", "threshold", "bonus", "Recall@5", "MRR", "块大小", "信息密度"]
        print(f"{headers[0]:<5} {headers[1]:<5} {headers[2]:<5} {headers[3]:<7} {headers[4]:<9} {headers[5]:<7} {headers[6]:<9} {headers[7]:<7} {headers[8]:<9} {headers[9]:<10}")
        print("-" * 100)

        for rank, r in enumerate(sorted_results[:15], 1):
            cfg = r['config']
            ret = r['retrieval']
            chunk = r['chunking']
            print(
                f"{rank:<5} "
                f"{cfg['min_chunk_size']:<5} "
                f"{cfg['max_chunk_size']:<5} "
                f"{cfg['chunk_overlap']:<7} "
                f"{cfg['semantic_threshold']:<9.2f} "
                f"{cfg['speaker_switch_bonus']:<7.2f} "
                f"{ret['recall_at_5']:<9.2%} "
                f"{ret['mrr']:<7.3f} "
                f"{chunk['avg_chunk_size']:<9.0f} "
                f"{chunk['avg_info_density']:<10.2%}"
            )

        # 最佳配置
        best = sorted_results[0]
        print("\n" + "=" * 100)
        print("推荐最佳配置:")
        print("=" * 100)
        for k, v in best['config'].items():
            print(f"  {k}: {v}")
        print(f"\n  分块质量:")
        print(f"    平均块大小: {best['chunking']['avg_chunk_size']:.0f}")
        print(f"    块大小标准差: {best['chunking']['chunk_size_std']:.0f}")
        print(f"    语义完整性: {best['chunking']['semantic_completeness']:.2%}")
        print(f"    平均信息密度: {best['chunking']['avg_info_density']:.2%}")
        print(f"\n  检索质量:")
        print(f"    Recall@5: {best['retrieval']['recall_at_5']:.2%}")
        print(f"    MRR: {best['retrieval']['mrr']:.3f}")
        print(f"\n  处理性能:")
        print(f"    总耗时: {best['performance']['processing_time']:.2f}s")


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='SPEAKER_AWARE_HYBRID 参数调优实验')
    parser.add_argument('--data_dir', type=str, 
                       default=r'F:\project\meetingmind-agent\backend\tests\chunking\data\meeting_docs_with_speaker',
                       help='会议文档目录路径')
    parser.add_argument('--max_docs', type=int, default=None,
                       help='最大文档数量（用于快速测试）')
    parser.add_argument('--save_interval', type=int, default=20,
                       help='保存间隔')
    
    args = parser.parse_args()
    
    data_dir = Path(args.data_dir)
    experiment = ParameterTuningExperiment(data_dir)
    experiment.run(max_docs=args.max_docs, save_interval=args.save_interval)


if __name__ == "__main__":
    main()
