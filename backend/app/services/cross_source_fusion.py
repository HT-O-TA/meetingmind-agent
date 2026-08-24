"""跨源融合 - 文档候选与记忆候选的统一融合

设计目标（对应 docs/总结.md 检索记忆层）：
文档候选和记忆候选不会各自取完 Top-K 后直接拼接，而是：
1. 转换成统一候选结构 UnifiedCandidate
2. 各来源内部先归一化分数（min-max）
3. 跨来源加权融合（语义相关性、原始排名、记忆置信度、重要性、会议匹配度）
4. 可选：用同一个精排模型重新排序
5. 全局截取 Top-K
6. 输出保留 document_id/chunk_id 或 memory_id，用于生成可追溯引用
"""
from typing import List, Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum
from app.core.logger import app_logger


class CandidateSource(str, Enum):
    """候选来源"""
    DOCUMENT = "document"  # 文档分块
    MEMORY = "memory"      # 长期记忆


@dataclass
class UnifiedCandidate:
    """统一候选结构

    文档候选和记忆候选统一转换为该结构后参与跨源融合。
    输出保留 doc_id/chunk_id 或 memory_id，用于生成可追溯引用。
    """
    source: CandidateSource
    content: str
    raw_score: float                       # 原始检索分数
    normalized_score: float = 0.0          # 来源内部归一化后的分数（0-1）
    rank: int = 0                          # 来源内的原始排名（从1开始）
    # 引用追溯（二选一）
    document_id: Optional[int] = None
    chunk_id: Optional[int] = None
    memory_id: Optional[str] = None
    # 融合加权因子
    semantic_relevance: float = 0.0        # 语义相关性（来自检索分数）
    memory_confidence: float = 0.0         # 记忆置信度（仅记忆候选有）
    importance: float = 0.5                # 重要性（默认 0.5）
    meeting_match: float = 0.0             # 当前会议匹配度
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    final_score: float = 0.0               # 融合后最终分数

    def get_reference(self) -> Dict[str, Any]:
        """获取可追溯引用"""
        if self.source == CandidateSource.DOCUMENT:
            return {
                "type": "document",
                "document_id": self.document_id,
                "chunk_id": self.chunk_id,
            }
        else:
            return {
                "type": "memory",
                "memory_id": self.memory_id,
            }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "content": self.content[:200],  # 截断避免输出过大
            "final_score": round(self.final_score, 4),
            "reference": self.get_reference(),
        }


class CrossSourceFusion:
    """跨源融合器

    融合流程：
    1. 各来源内部归一化分数（min-max）
    2. 跨来源加权融合：
       final = w1*语义相关性 + w2*原始排名 + w3*记忆置信度 + w4*重要性 + w5*会议匹配度
    3. 可选：BGE-Reranker 精排
    4. 全局截取 Top-K
    """

    # 跨来源融合权重
    W_SEMANTIC = 0.35       # 语义相关性
    W_RANK = 0.20           # 原始排名
    W_MEMORY_CONF = 0.15    # 记忆置信度
    W_IMPORTANCE = 0.15     # 重要性
    W_MEETING_MATCH = 0.15  # 会议匹配度

    def __init__(self, reranker=None):
        """
        Args:
            reranker: 可选的 BGE-Reranker 实例（注入，避免循环导入）
        """
        self._reranker = reranker

    def fuse(
        self,
        document_candidates: List[UnifiedCandidate],
        memory_candidates: List[UnifiedCandidate],
        top_k: int = 10,
        current_meeting_id: Optional[str] = None,
        use_reranker: bool = False,
        query: str = "",
    ) -> List[UnifiedCandidate]:
        """跨源融合主入口

        Args:
            document_candidates: 文档候选列表
            memory_candidates: 记忆候选列表
            top_k: 最终返回数量
            current_meeting_id: 当前会议ID（用于计算会议匹配度）
            use_reranker: 是否使用 BGE-Reranker 精排
            query: 原始查询（reranker 需要）

        Returns:
            融合后的 Top-K 候选列表
        """
        # 1. 各来源内部归一化
        self._normalize_within_source(document_candidates)
        self._normalize_within_source(memory_candidates)

        # 2. 计算会议匹配度
        if current_meeting_id:
            for c in document_candidates + memory_candidates:
                c.meeting_match = self._calc_meeting_match(c, current_meeting_id)

        # 3. 跨来源加权融合
        all_candidates = document_candidates + memory_candidates
        for c in all_candidates:
            c.final_score = self._weighted_fusion(c)

        # 4. 可选：BGE-Reranker 精排
        if use_reranker and self._reranker and query and all_candidates:
            try:
                all_candidates = self._rerank(query, all_candidates)
            except Exception as e:
                app_logger.warning(f"[CrossSourceFusion] Reranker 精排失败，使用融合分数排序: {e}")
                all_candidates.sort(key=lambda c: c.final_score, reverse=True)
        else:
            all_candidates.sort(key=lambda c: c.final_score, reverse=True)

        # 5. 全局截取 Top-K
        result = all_candidates[:top_k]

        app_logger.info(
            f"[CrossSourceFusion] 融合完成: "
            f"文档候选 {len(document_candidates)} 条, "
            f"记忆候选 {len(memory_candidates)} 条, "
            f"输出 Top-{top_k}"
        )
        return result

    @staticmethod
    def _normalize_within_source(candidates: List[UnifiedCandidate]):
        """来源内部归一化分数（min-max 归一化到 0-1）"""
        if not candidates:
            return
        scores = [c.raw_score for c in candidates]
        min_s, max_s = min(scores), max(scores)
        for i, c in enumerate(candidates):
            c.rank = i + 1  # 排名从1开始
            if max_s == min_s:
                c.normalized_score = 1.0
            else:
                c.normalized_score = (c.raw_score - min_s) / (max_s - min_s)
            c.semantic_relevance = c.normalized_score

    @staticmethod
    def _calc_meeting_match(candidate: UnifiedCandidate, current_meeting_id: str) -> float:
        """计算当前会议匹配度

        如果候选的来源会议与当前会议一致，匹配度为 1.0，否则 0.0。
        生产环境可替换为更精细的会议相关度计算。
        """
        meta_meeting = candidate.metadata.get("meeting_id")
        if meta_meeting and str(meta_meeting) == str(current_meeting_id):
            return 1.0
        return 0.0

    def _weighted_fusion(self, c: UnifiedCandidate) -> float:
        """跨来源加权融合

        final = w1*语义相关性 + w2*原始排名倒数 + w3*记忆置信度 + w4*重要性 + w5*会议匹配度
        """
        rank_score = 1.0 / c.rank if c.rank > 0 else 0.0  # 排名倒数（排名越靠前分越高）
        return (
            self.W_SEMANTIC * c.semantic_relevance
            + self.W_RANK * rank_score
            + self.W_MEMORY_CONF * c.memory_confidence
            + self.W_IMPORTANCE * c.importance
            + self.W_MEETING_MATCH * c.meeting_match
        )

    def _rerank(self, query: str, candidates: List[UnifiedCandidate]) -> List[UnifiedCandidate]:
        """使用 BGE-Reranker 精排

        将跨源融合后的候选统一送入 reranker 重新打分，
        确保文档和记忆在同一精排标准下排序。
        """
        if not self._reranker:
            return candidates

        # 调用 reranker 对 query 和所有候选内容重新打分
        # reranker 接口预期：rerank(query, documents) -> List[float]
        documents = [c.content for c in candidates]
        rerank_scores = self._reranker.rerank(query, documents)

        for c, score in zip(candidates, rerank_scores):
            c.final_score = float(score)

        candidates.sort(key=lambda c: c.final_score, reverse=True)
        return candidates

    @staticmethod
    def from_document_result(doc_result: Dict[str, Any]) -> UnifiedCandidate:
        """将文档检索结果转为统一候选结构"""
        return UnifiedCandidate(
            source=CandidateSource.DOCUMENT,
            content=doc_result.get("content") or doc_result.get("chunk_text", ""),
            raw_score=doc_result.get("score", 0.0),
            document_id=doc_result.get("document_id"),
            chunk_id=doc_result.get("chunk_id"),
            metadata={
                "meeting_id": doc_result.get("meeting_id"),
                "department": doc_result.get("department"),
            },
        )

    @staticmethod
    def from_memory_result(mem_result: Dict[str, Any]) -> UnifiedCandidate:
        """将记忆检索结果转为统一候选结构"""
        return UnifiedCandidate(
            source=CandidateSource.MEMORY,
            content=mem_result.get("content", ""),
            raw_score=mem_result.get("score", 0.0),
            memory_id=mem_result.get("memory_id"),
            memory_confidence=mem_result.get("confidence", 0.5),
            importance=mem_result.get("importance", 0.5),
            metadata={
                "meeting_id": mem_result.get("meeting_id"),
                "type": mem_result.get("type"),
            },
        )
