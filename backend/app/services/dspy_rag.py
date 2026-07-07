"""DSPy优化的RAG管道"""
import dspy
from dspy import Example, ChainOfThought, Module, Predict, Signature
from typing import List, Optional, Dict, Any
from app.services.embedding_service import EmbeddingService
from app.services.document_service import DocumentService
from app.services.llm_service import LLMService


class RAGQuestionAnswering(Module):
    """DSPy RAG问答模块"""
    
    def __init__(self):
        super().__init__()
        
        # 检索器
        self.retrieve = Predict(
            Signature(
                """
                context: str
                query: str
                ---
                relevant_passages: str
                """
            ),
            name="Retriever"
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
            ),
            name="AnswerGenerator"
        )
    
    def forward(self, question: str, context: str) -> str:
        """执行RAG问答"""
        # 从上下文中检索相关段落
        retrieved = self.retrieve(context=context, query=question)
        
        # 生成答案
        answer = self.generate_answer(
            context=retrieved.relevant_passages,
            question=question
        )
        
        return answer.answer


class DSPyRAGService:
    """DSPy优化的RAG服务"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.document_service = DocumentService()
        self.llm_service = LLMService()
        
        # 初始化DSPy
        self._init_dspy()
        
        # 创建RAG管道
        self.rag_pipeline = RAGQuestionAnswering()
    
    def _init_dspy(self):
        """初始化DSPy配置"""
        from app.core.config import settings
        
        # 配置LLM
        llm_config = {
            "model": settings.LLM_MODEL,
            "api_key": settings.LLM_API_KEY,
            "temperature": settings.LLM_TEMPERATURE,
            "max_tokens": settings.LLM_MAX_TOKENS
        }
        
        # 根据模型类型选择不同的provider
        if "qwen" in settings.LLM_MODEL.lower():
            dspy.configure(lm=dspy.Ollama(model=settings.LLM_MODEL))
        else:
            dspy.configure(lm=dspy.OpenAI(**llm_config))
        
        # 配置检索器
        dspy.configure(rm=dspy.ColBERTv2(url="http://your-colbert-server:8893/api/search"))
    
    def optimize_prompt(self, examples: List[Dict[str, str]]):
        """使用DSPy优化提示模板"""
        # 创建训练示例
        train_examples = [
            Example(
                question=ex["question"],
                context=ex["context"],
                answer=ex["answer"]
            ).with_inputs("question", "context")
            for ex in examples
        ]
        
        # 使用DSPy的优化器
        from dspy.optim import BootstrapFewShot
        
        optimizer = BootstrapFewShot(metric=self._rag_metric)
        self.rag_pipeline = optimizer.compile(
            self.rag_pipeline,
            trainset=train_examples
        )
        
        return self.rag_pipeline
    
    def _rag_metric(self, example, prediction, trace=None):
        """RAG评估指标"""
        from dspy.evaluate import answer_exact_match
        
        return answer_exact_match(example, prediction)
    
    async def query(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """执行DSPy优化的RAG查询"""
        # 1. 检索相关文档
        docs = await self.document_service.search_documents(
            query=question,
            top_k=top_k
        )
        
        # 2. 构建上下文
        context = "\n\n".join([doc.content for doc in docs])
        
        # 3. 使用DSPy生成答案
        answer = self.rag_pipeline(question=question, context=context)
        
        return {
            "answer": answer,
            "context": context,
            "retrieved_docs": [doc.id for doc in docs]
        }
    
    async def compare_with_traditional(self, question: str) -> Dict[str, Any]:
        """对比传统RAG和DSPy优化的RAG"""
        # 传统RAG
        traditional_result = await self.llm_service.generate_with_context(
            question=question,
            context=""  # 会自动检索
        )
        
        # DSPy优化的RAG
        dspy_result = await self.query(question)
        
        return {
            "traditional": traditional_result,
            "dspy_optimized": dspy_result
        }


class DSPyChainOfThought(Module):
    """DSPy思维链模块"""
    
    def __init__(self):
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
            ),
            name="ChainOfThought"
        )
    
    def forward(self, question: str, context: str = "") -> str:
        """执行思维链推理"""
        result = self.cot(question=question, context=context)
        return result.answer


class DSPyReAct(Module):
    """DSPy ReAct模块"""
    
    def __init__(self):
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
            ),
            name="ReActThought"
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
            ),
            name="ReActSummary"
        )
    
    def forward(self, question: str, max_steps: int = 5) -> str:
        """执行ReAct推理"""
        history = ""
        observations = ""
        
        for step in range(max_steps):
            # 生成思考和动作
            result = self.thought(question=question, history=history)
            
            # 模拟动作执行（实际中会调用工具）
            observation = f"工具执行结果: {result.action_input}"
            observations += f"\n步骤{step+1}: {result.thought} -> {observation}"
            
            # 更新历史
            history += f"\n步骤{step+1}: {result.thought} | {result.action}"
            
            # 检查是否应该结束
            if "结束" in result.thought or "总结" in result.thought:
                break
        
        # 生成最终答案
        final = self.summary(
            question=question,
            thought_history=history,
            observations=observations
        )
        
        return final.final_answer


# 全局实例
dspy_rag_service = DSPyRAGService()