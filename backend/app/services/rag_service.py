"""RAG 服务：整合向量检索 + LLM 生成 + 知识图谱增强"""
from typing import List, Optional, Dict
from app.services.vector_search_service import VectorSearchService
from app.services.llm_service import LLMService
from app.services.knowledge_graph import enhance_search_results
from app.core.logger import app_logger
from app.core.config import settings


class RAGService:
    """RAG 服务类，整合检索与生成"""

    def __init__(self, vector_service: VectorSearchService, llm_service: LLMService = None, enable_evaluation: bool = False):
        self.vector_service = vector_service
        self.llm_service = llm_service or LLMService()
        self.enable_evaluation = enable_evaluation
        self._evaluator = None
    
    def _get_evaluator(self):
        """延迟加载评估器"""
        if self._evaluator is None and self.enable_evaluation:
            try:
                from app.services.ragas_evaluator import get_ragas_evaluator
                self._evaluator = get_ragas_evaluator()
            except Exception as e:
                app_logger.warning(f"无法加载评估器: {e}")
                self.enable_evaluation = False
        return self._evaluator

    async def ask(
        self,
        question: str,
        top_k: int = 5,
        meeting_id: Optional[int] = None,
        department: Optional[str] = None,
        similarity_threshold: float = 0.0,
        use_llm: bool = True,
    ) -> Dict:
        """
        RAG 问答：检索相关片段 + LLM 生成回答

        Args:
            question: 用户问题
            top_k: 检索返回数量
            meeting_id: 指定会议ID（可选）
            department: 指定部门（可选）
            similarity_threshold: 相似度阈值
            use_llm: 是否使用 LLM 生成回答

        Returns:
            包含 answer、chunks、mode 等信息的字典
        """
        # 1. 向量语义检索
        search_results = await self.vector_service.search_by_text(
            query_text=question,
            top_k=top_k,
            meeting_id=meeting_id,
            department=department,
            similarity_threshold=similarity_threshold,
        )

        # 2. 使用知识图谱增强检索结果
        if settings.ENABLE_KNOWLEDGE_GRAPH:
            try:
                search_results = await enhance_search_results(question, search_results, depth=2)
                app_logger.info(f"[RAG] 知识图谱增强完成，结果数: {len(search_results)}")
            except Exception as e:
                app_logger.warning(f"[RAG] 知识图谱增强失败: {e}")

        # 3. 提取文本片段
        chunks = [r["chunk_text"] for r in search_results if r.get("chunk_text")]

        # 4. 如果没有检索到结果
        if not chunks:
            return {
                "answer": "抱歉，我在知识库中没有找到与您问题相关的内容。",
                "chunks": [],
                "count": 0,
                "mode": self.vector_service.use_pgvector if hasattr(self.vector_service, 'use_pgvector') else "unknown",
            }

        # 5. LLM 生成回答
        if use_llm:
            try:
                answer = await self.llm_service.generate_answer(
                    question=question,
                    context=chunks,
                )
            except Exception as e:
                app_logger.error(f"LLM 生成失败: {e}")
                # 如果 LLM 失败，降级为直接返回检索结果
                answer = "抱歉，AI 生成回答失败。以下是检索到的相关内容：\n\n" + "\n\n".join(
                    [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
                )
        else:
            # 不使用 LLM 时，直接拼接检索结果
            answer = "以下是检索到的相关内容：\n\n" + "\n\n".join(
                [f"[{i+1}] {c}" for i, c in enumerate(chunks[:3])]
            )

        result = {
            "answer": answer,
            "chunks": search_results,
            "count": len(search_results),
            "mode": self.vector_service.use_pgvector if hasattr(self.vector_service, 'use_pgvector') else "unknown",
        }

        # 如果启用评估，添加评估指标
        if self.enable_evaluation and self._get_evaluator():
            contexts = [r["chunk_text"] for r in search_results if r.get("chunk_text")]
            try:
                metrics = await self._evaluator.evaluate(
                    query=question,
                    answer=answer,
                    contexts=contexts
                )
                result["evaluation"] = {
                    "metrics": metrics.to_dict(),
                    "avg_score": metrics.avg_score()
                }
            except Exception as e:
                app_logger.warning(f"评估失败: {e}")

        return result
