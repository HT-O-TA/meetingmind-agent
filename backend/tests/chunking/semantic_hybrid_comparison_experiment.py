"""
SEMANTIC_HYBRID vs RECURSIVE 分块策略对比实验
基于已有评估框架实现
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass

import numpy as np
from tqdm import tqdm

# 添加项目路径
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.semantic_chunker import (
    SemanticChunker,
    ChunkingConfig,
    ChunkingStrategy,
)


@dataclass
class ExperimentResult:
    """单次实验结果"""
    strategy: str
    config: Dict[str, Any]
    chunk_count: int
    avg_chunk_size: float
    std_chunk_size: float
    semantic_completeness: float
    processing_time: float
    recall_at_5: float = 0.0
    precision_at_5: float = 0.0
    mrr: float = 0.0


class ChunkingExperiment:
    """分块策略对比实验"""

    def __init__(self, docs_dir: Path):
        self.docs_dir = docs_dir
        self.results: List[ExperimentResult] = []

        # 加载测试文档
        self.documents = self._load_documents()

        # 生成测试查询（基于实际内容）
        self.test_queries = self._generate_test_queries()

    def _load_documents(self) -> List[Tuple[str, str]]:
        """加载测试文档"""
        documents = []
        md_files = list(self.docs_dir.glob("*.md"))
        txt_files = list(self.docs_dir.glob("*.txt"))
        all_files = md_files + txt_files

        print(f"找到 {len(all_files)} 个文档")

        for file_path in all_files[:50]:  # 使用前50个文档进行实验
            try:
                content = file_path.read_text(encoding="utf-8")
                if content.strip():
                    documents.append((file_path.name, content))
            except Exception as e:
                print(f"读取 {file_path} 失败: {e}")

        print(f"成功加载 {len(documents)} 个文档")
        return documents

    def _generate_test_queries(self) -> List[str]:
        """生成测试查询"""
        queries = [
            "会议讨论了什么主题？",
            "预算是多少？",
            "有哪些人参加了会议？",
            "做出了什么决定？",
            "下一步计划是什么？",
            "存在什么问题？",
            "解决方案是什么？",
            "时间安排如何？",
            "地点在哪里？",
            "讨论了哪些具体事项？",
        ]
        return queries

    def _calculate_semantic_completeness(self, chunks: List[str]) -> float:
        """计算语义完整性得分"""
        if not chunks:
            return 0.0

        scores = []
        for chunk in chunks:
            score = 0.0
            # 检查是否有完整句子
            if any(punc in chunk for punc in ["。", "！", "？", ".", "!", "?"]):
                score += 0.4
            # 检查块长度是否适中
            if 100 <= len(chunk) <= 1000:
                score += 0.3
            # 检查是否有实质性内容（非纯语气词）
            if len(chunk.strip()) > 20:
                score += 0.3
            scores.append(score)

        return np.mean(scores)

    def _evaluate_retrieval(self, chunks: List[str]) -> Tuple[float, float, float]:
