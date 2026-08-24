"""查询路由服务 - 四层查询路由架构"""
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.services.llm_service import LLMService


class QueryType(str, Enum):
    COMMON_SENSE = "common_sense"
    KNOWLEDGE_BASE = "knowledge_base"
    REAL_TIME = "real_time"
    CALCULATION = "calculation"
    CODE = "code"


class RetrievalStrategy(str, Enum):
    DENSE_ONLY = "dense_only"
    SPARSE_ONLY = "sparse_only"
    HYBRID = "hybrid"
    GRAPH = "graph"


class QueryRewriteResult(BaseModel):
    original_query: str
    rewritten_query: str
    intent: str
    entities: List[str]
    filters: Dict[str, Any]


class RoutingDecision(BaseModel):
    query_type: QueryType
    need_retrieval: bool
    retrieval_strategy: RetrievalStrategy
    rewrite_result: Optional[QueryRewriteResult] = None


class QueryRouter:
    def __init__(self):
        self.llm_service = LLMService()

    async def route(self, query: str) -> RoutingDecision:
        """
        四层查询路由：
        1. Query Routing - 判断查询类型
        2. Query Rewriting - 重写查询
        3. Retrieval Strategy Selection - 选择检索策略
        4. 生成路由决策

        Args:
            query: 用户原始查询

        Returns:
            路由决策
        """
        routing_prompt = f"""
你是一个智能查询路由器，请根据用户查询进行分类和分析：

**查询类型定义：**
- common_sense: 常识问题，不需要检索（如"什么是人工智能"）
- knowledge_base: 需要从知识库检索的问题（如"项目A的进度如何"）
- real_time: 需要实时API的问题（如"今天天气如何"）
- calculation: 需要计算的问题（如"1+1等于几"）
- code: 需要编写代码的问题（如"写一个Python函数"）

**输入查询：** {query}

请输出JSON格式的分析结果：
{{
    "query_type": "查询类型",
    "need_retrieval": true/false,
    "retrieval_strategy": "dense_only/sparse_only/hybrid/graph",
    "rewritten_query": "优化后的查询",
    "intent": "查询意图描述",
    "entities": ["识别到的实体"],
    "filters": {{}}
}}
"""

        response = await self.llm_service.generate_text(
            prompt=routing_prompt,
            max_tokens=500,
            temperature=0.1,
        )

        try:
            import json
            result = json.loads(response)
        except:
            result = self._parse_fallback(query)

        query_type = QueryType(result.get("query_type", "knowledge_base"))
        need_retrieval = result.get("need_retrieval", True)
        retrieval_strategy = RetrievalStrategy(result.get("retrieval_strategy", "hybrid"))

        rewrite_result = QueryRewriteResult(
            original_query=query,
            rewritten_query=result.get("rewritten_query", query),
            intent=result.get("intent", ""),
            entities=result.get("entities", []),
            filters=result.get("filters", {}),
        )

        return RoutingDecision(
            query_type=query_type,
            need_retrieval=need_retrieval,
            retrieval_strategy=retrieval_strategy,
            rewrite_result=rewrite_result,
        )

    def _parse_fallback(self, query: str) -> Dict[str, Any]:
        """解析失败时的降级处理"""
        return {
            "query_type": "knowledge_base",
            "need_retrieval": True,
            "retrieval_strategy": "hybrid",
            "rewritten_query": query,
            "intent": "未知意图",
            "entities": [],
            "filters": {},
        }

    async def rewrite_query(self, query: str, context: str = "") -> str:
        """
        查询重写 - 将模糊查询转换为结构化搜索条件

        Args:
            query: 原始查询
            context: 上下文信息

        Returns:
            重写后的查询
        """
        rewrite_prompt = f"""
将以下用户查询重写为更适合检索的形式：

原始查询：{query}
上下文：{context}

请输出优化后的查询，使其更精确、更完整，包含更多关键词。
"""

        response = await self.llm_service.generate_text(
            prompt=rewrite_prompt,
            max_tokens=200,
            temperature=0.1,
        )

        return response.strip()


query_router = QueryRouter()
