"""DSPy优化的RAG管道（实验性模块，需要配置 DSPy 环境才能使用）"""
from typing import List, Optional, Dict, Any

# DSPy 是可选依赖，未安装时整个模块降级为空实现
try:
    import dspy
    from dspy import Example, ChainOfThought, Module, Predict, Signature
    _DSPY_AVAILABLE = True
except ImportError:
    _DSPY_AVAILABLE = False
    Module = object  # 占位，避免 NameError


class RAGQuestionAnswering(Module):
    """DSPy RAG问答模块"""

    def __init__(self):
        if not _DSPY_AVAILABLE:
            return
        super().__init__()

        # 检索器（name 参数已移除，DSPy Predict/ChainOfThought 不接受 name）
        self.retrieve = Predict(
            Signature(
                """
                context: str
                query: str
                ---
                relevant_passages: str
                """
            )
        )

        # 问答器
        self.generate_answer = ChainOfThought(
            Signature(
                """
                context: str
                question: str
                ---
                answer: str
                """
            )
        )

    def forward(self, question: str, context: str) -> str:
        """执行RAG问答"""
        retrieved = self.retrieve(context=context, query=question)
        answer = self.generate_answer(
            context=retrieved.relevant_passages,
            question=question
        )
        return answer.answer


class DSPyRAGService:
    """DSPy优化的RAG服务"""

    def __init__(self):
        from app.services.embedding_service import EmbeddingService
        from app.services.llm_service import LLMService
        self.embedding_service = EmbeddingService()
        self.llm_service = LLMService()
        # DocumentService 需要 db session，不在此处实例化
        self._document_service = None

        if _DSPY_AVAILABLE:
            self._init_dspy()
            self.rag_pipeline = RAGQuestionAnswering()
        else:
            self.rag_pipeline = None

    def _get_document_service(self, db=None):
        """按需创建 DocumentService（需要传入 db session）"""
        if db is None:
            raise RuntimeError("DocumentService requires a db session")
        from app.services.document_service import DocumentService
        return DocumentService(db)

    def _init_dspy(self):
        """初始化DSPy配置"""
        if not _DSPY_AVAILABLE:
            return
        from app.core.config import settings

        # 配置LLM（只传 model 和 api_key，temperature/max_tokens 不是构造参数）
        try:
            if "ollama" in settings.LLM_MODEL.lower() or "qwen" in settings.LLM_MODEL.lower():
                # 使用 dspy.OllamaLocal 或兼容 OpenAI 接口
                lm = dspy.OpenAI(
                    model=settings.LLM_MODEL,
                    api_key=settings.LLM_API_KEY or "ollama",
                    api_base=getattr(settings, "LLM_BASE_URL", "http://localhost:11434/v1"),
                )
            else:
                lm = dspy.OpenAI(
                    model=settings.LLM_MODEL,
                    api_key=settings.LLM_API_KEY,
                )
            dspy.configure(lm=lm)
        except Exception as e:
            from app.core.logger import app_logger
            app_logger.warning(f"[DSPy] LLM 配置失败，DSPy 功能不可用: {e}")

        # ColBERTv2 检索器为可选配置，跳过占位 URL
        colbert_url = getattr(settings, "COLBERT_URL", None)
        if colbert_url and "your-colbert-server" not in colbert_url:
            try:
                dspy.configure(rm=dspy.ColBERTv2(url=colbert_url))
            except Exception as e:
                from app.core.logger import app_logger
                app_logger.warning(f"[DSPy] ColBERTv2 配置失败: {e}")

    def optimize_prompt(self, examples: List[Dict[str, str]]):
        """使用DSPy优化提示模板"""
        if not _DSPY_AVAILABLE or self.rag_pipeline is None:
            return self.rag_pipeline

        train_examples = [
            Example(
                question=ex["question"],
                context=ex["context"],
                answer=ex["answer"]
            ).with_inputs("question", "context")
            for ex in examples
        ]

        # 正确导入路径：dspy.teleprompt
        try:
            from dspy.teleprompt import BootstrapFewShot
        except ImportError:
            from dspy.optim import BootstrapFewShot  # 旧版本回退

        optimizer = BootstrapFewShot(metric=self._rag_metric)
        self.rag_pipeline = optimizer.compile(
            self.rag_pipeline,
            trainset=train_examples
        )
        return self.rag_pipeline

    def _rag_metric(self, example, prediction, trace=None):
        """RAG评估指标"""
        # dspy.evaluate.answer_exact_match 在部分版本不存在，使用简单实现
        try:
            from dspy.evaluate import answer_exact_match
            return answer_exact_match(example, prediction)
        except (ImportError, AttributeError):
            pred_answer = getattr(prediction, "answer", str(prediction)).strip().lower()
            gold_answer = getattr(example, "answer", "").strip().lower()
            return pred_answer == gold_answer

    async def query(self, question: str, top_k: int = 5, db=None) -> Dict[str, Any]:
        """执行DSPy优化的RAG查询"""
        if not _DSPY_AVAILABLE or self.rag_pipeline is None:
            return {"answer": "", "context": "", "retrieved_docs": []}

        doc_service = self._get_document_service(db)

        # DocumentService 没有 search_documents 方法，使用 list_documents
        docs_result, _, _ = await doc_service.list_documents(page=1, page_size=top_k)
        context = "\n\n".join([doc.content for doc in docs_result if doc.content])

        answer = self.rag_pipeline(question=question, context=context)

        return {
            "answer": answer,
            "context": context,
            "retrieved_docs": [doc.id for doc in docs_result]
        }

    async def compare_with_traditional(self, question: str, db=None) -> Dict[str, Any]:
        """对比传统RAG和DSPy优化的RAG"""
        # 使用 generate_answer 替代不存在的 generate_with_context
        traditional_result = await self.llm_service.generate_answer(
            question=question,
            context=[]
        )

        dspy_result = await self.query(question, db=db)

        return {
            "traditional": traditional_result,
            "dspy_optimized": dspy_result
        }


class DSPyChainOfThought(Module):
    """DSPy思维链模块"""

    def __init__(self):
        if not _DSPY_AVAILABLE:
            return
        super().__init__()

        self.cot = ChainOfThought(
            Signature(
                """
                question: str
                context: str
                ---
                reasoning: str
                answer: str
                """
            )
        )

    def forward(self, question: str, context: str = "") -> str:
        """执行思维链推理"""
        result = self.cot(question=question, context=context)
        return result.answer


class DSPyReAct(Module):
    """DSPy ReAct模块"""

    def __init__(self):
        if not _DSPY_AVAILABLE:
            return
        super().__init__()

        self.thought = Predict(
            Signature(
                """
                question: str
                history: str
                ---
                thought: str
                action: str
                action_input: str
                """
            )
        )

        self.summary = Predict(
            Signature(
                """
                question: str
                thought_history: str
                observations: str
                ---
                final_answer: str
                """
            )
        )

    def forward(self, question: str, max_steps: int = 5) -> str:
        """执行ReAct推理"""
        history = ""
        observations = ""

        for step in range(max_steps):
            result = self.thought(question=question, history=history)

            observation = f"工具执行结果: {result.action_input}"
            observations += f"\n步骤{step+1}: {result.thought} -> {observation}"
            history += f"\n步骤{step+1}: {result.thought} | {result.action}"

            if "结束" in result.thought or "总结" in result.thought:
                break

        final = self.summary(
            question=question,
            thought_history=history,
            observations=observations
        )

        return final.final_answer


# 全局实例（延迟初始化，避免 import 时连接外部服务）
_dspy_rag_service: Optional["DSPyRAGService"] = None


def get_dspy_rag_service() -> "DSPyRAGService":
    """获取全局 DSPyRAGService 实例（懒加载）"""
    global _dspy_rag_service
    if _dspy_rag_service is None:
        _dspy_rag_service = DSPyRAGService()
    return _dspy_rag_service


# 向后兼容别名（不在模块级立即实例化，避免 import 时副作用）
dspy_rag_service = None  # 使用 get_dspy_rag_service() 代替
