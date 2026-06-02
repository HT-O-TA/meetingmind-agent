"""Query优化器 - Query分解 + HyDE + 扩展"""
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from app.core.logger import app_logger
from app.core.config import settings


class QueryComplexity(str, Enum):
    """Query复杂度"""
    SIMPLE = "simple"       # 简单查询
    MEDIUM = "medium"      # 中等查询
    COMPLEX = "complex"    # 复杂查询


@dataclass
class SubQuery:
    """子查询"""
    query: str
    reasoning: str
    order: int
    dependencies: List[int] = field(default_factory=list)


@dataclass
class HyDEResult:
    """HyDE结果"""
    original_query: str
    hypothetical_documents: List[str]
    expanded_query: str
    reasoning: str


@dataclass
class ExpandedQuery:
    """扩展后的Query"""
    original: str
    sub_queries: List[SubQuery] = field(default_factory=list)
    hyde_result: HyDEResult = None
    synonyms: List[str] = field(default_factory=list)
    related_terms: List[str] = field(default_factory=list)
    complexity: QueryComplexity = QueryComplexity.SIMPLE


class QueryDecomposer:
    """Query分解器 - 复杂问题拆分为子问题"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    def _classify_complexity(self, query: str) -> QueryComplexity:
        """判断Query复杂度"""
        complexity_indicators = {
            QueryComplexity.COMPLEX: ["和", "与", "比较", "对比", "以及", "而且", "或者", "哪些", "分别", "各"],
            QueryComplexity.MEDIUM: ["什么", "怎么", "如何", "为什么", "原因", "结果", "影响"]
        }
        
        query_lower = query.lower()
        
        for indicator in complexity_indicators[QueryComplexity.COMPLEX]:
            if indicator in query_lower:
                return QueryComplexity.COMPLEX
        
        for indicator in complexity_indicators[QueryComplexity.MEDIUM]:
            if indicator in query_lower:
                return QueryComplexity.MEDIUM
        
        return QueryComplexity.SIMPLE
    
    async def decompose(self, query: str) -> List[SubQuery]:
        """
        分解复杂Query
        
        Args:
            query: 原始查询
            
        Returns:
            子查询列表
        """
        complexity = self._classify_complexity(query)
        
        if complexity == QueryComplexity.SIMPLE:
            return [SubQuery(
                query=query,
                reasoning="简单查询，无需分解",
                order=0
            )]
        
        llm = self._get_llm()
        if llm is None:
            return [SubQuery(
                query=query,
                reasoning="LLM不可用，返回原始查询",
                order=0
            )]
        
        try:
            prompt = f"""请将以下复杂问题分解为多个简单子问题。

复杂问题：{query}

分解要求：
1. 每个子问题应该可以独立回答
2. 子问题之间按逻辑顺序排列
3. 如果有依赖关系，标注依赖的子问题编号
4. 考虑可能需要检索的不同方面

输出格式（JSON数组）：
[
  {{
    "query": "子问题内容",
    "reasoning": "为什么需要这个子问题",
    "order": 顺序号,
    "dependencies": [依赖的子问题序号]
  }}
]

只输出JSON："""
            
            response = await llm._call(prompt)
            
            sub_queries = self._parse_response(response)
            
            if sub_queries:
                return sub_queries
            
        except Exception as e:
            app_logger.error(f"Query decomposition failed: {e}")
        
        return [SubQuery(
            query=query,
            reasoning="分解失败，返回原始查询",
            order=0
        )]
    
    def _parse_response(self, response: str) -> List[SubQuery]:
        """解析LLM响应"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                
                sub_queries = []
                for i, item in enumerate(data):
                    sq = SubQuery(
                        query=item.get("query", ""),
                        reasoning=item.get("reasoning", ""),
                        order=item.get("order", i),
                        dependencies=item.get("dependencies", [])
                    )
                    sub_queries.append(sq)
                
                return sorted(sub_queries, key=lambda x: x.order)
                
        except json.JSONDecodeError as e:
            app_logger.warning(f"Failed to parse decomposition response: {e}")
        
        return []
    
    async def multi_step_reasoning(self, query: str) -> str:
        """多步推理Query改写"""
        llm = self._get_llm()
        if llm is None:
            return query
        
        try:
            prompt = f"""对于以下问题，请先退后一步思考更广泛的概念，然后再具体回答。

问题：{query}

步骤：
1. 识别问题的核心概念
2. 扩展到更广泛的背景
3. 逐步聚焦到具体问题

输出格式：
[扩展背景]: 更广泛的概念和背景
[核心问题]: 具体要解决的问题
[补充信息]: 可能需要的补充查询
"""
            
            return await llm._call(prompt)
            
        except Exception as e:
            app_logger.error(f"Multi-step reasoning failed: {e}")
            return query


class HyDEGenerator:
    """HyDE (Hypothetical Document Embeddings) 生成器"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def generate_hypothetical_doc(
        self,
        query: str,
        num_docs: int = 3
    ) -> HyDEResult:
        """
        生成假设性文档
        
        Args:
            query: 查询问题
            num_docs: 生成文档数量
            
        Returns:
            HyDEResult
        """
        llm = self._get_llm()
        
        if llm is None:
            return HyDEResult(
                original_query=query,
                hypothetical_documents=[query],
                expanded_query=query,
                reasoning="LLM不可用"
            )
        
        try:
            prompt = f"""请为以下问题生成{num_docs}个假设性的详细回答。

问题：{query}

要求：
1. 每个回答应该详细、完整，假设这是从知识库中检索到的真实内容
2. 回答应该包含具体的信息、数据、例子
3. 多个回答可以有不同的角度或侧重点

输出格式（JSON数组）：
[
  {{
    "answer": "详细的假设性回答",
    "focus": "回答的侧重点"
  }}
]

只输出JSON："""
            
            response = await llm._call(prompt)
            
            docs = self._parse_response(response, num_docs)
            
            if docs:
                combined = "\n\n".join(docs)
                return HyDEResult(
                    original_query=query,
                    hypothetical_documents=docs,
                    expanded_query=combined,
                    reasoning="基于假设性文档扩展"
                )
            
        except Exception as e:
            app_logger.error(f"HyDE generation failed: {e}")
        
        return HyDEResult(
            original_query=query,
            hypothetical_documents=[query],
            expanded_query=query,
            reasoning="生成失败，使用原始查询"
        )
    
    def _parse_response(self, response: str, num_docs: int) -> List[str]:
        """解析假设性文档"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                data = json.loads(response[start:end])
                
                docs = []
                for item in data[:num_docs]:
                    if isinstance(item, dict):
                        docs.append(item.get("answer", str(item)))
                    else:
                        docs.append(str(item))
                
                return docs
                
        except json.JSONDecodeError:
            pass
        
        return []
    
    async def embed_hypothetical(
        self,
        query: str,
        embed_func
    ) -> List[List[float]]:
        """对假设性文档进行嵌入"""
        result = await self.generate_hypothetical_doc(query)
        
        vectors = []
        for doc in result.hypothetical_documents:
            vec = embed_func(doc)
            vectors.append(vec)
        
        return vectors


class QueryExpander:
    """Query扩展器 - 同义词、相关词扩展"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
        self._synonym_cache: Dict[str, List[str]] = {}
    
    def _get_llm(self):
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def expand(self, query: str) -> ExpandedQuery:
        """
        扩展Query
        
        Args:
            query: 原始查询
            
        Returns:
            ExpandedQuery
        """
        complexity = self._classify_complexity(query)
        
        decomposer = QueryDecomposer(self._llm)
        hyde = HyDEGenerator(self._llm)
        
        sub_queries = await decomposer.decompose(query)
        hyde_result = await hyde.generate_hypothetical_doc(query)
        
        synonyms = await self._expand_synonyms(query)
        related = await self._expand_related_terms(query)
        
        return ExpandedQuery(
            original=query,
            sub_queries=sub_queries,
            hyde_result=hyde_result,
            synonyms=synonyms,
            related_terms=related,
            complexity=complexity
        )
    
    def _classify_complexity(self, query: str) -> QueryComplexity:
        """判断复杂度"""
        if any(kw in query for kw in ["和", "与", "比较", "以及"]):
            return QueryComplexity.COMPLEX
        if any(kw in query for kw in ["什么", "怎么", "为什么"]):
            return QueryComplexity.MEDIUM
        return QueryComplexity.SIMPLE
    
    async def _expand_synonyms(self, query: str) -> List[str]:
        """扩展同义词"""
        llm = self._get_llm()
        if llm is None:
            return []
        
        try:
            prompt = f"""为以下查询生成同义词或表达变体：

查询：{query}

要求：
1. 生成5-10个同义词或相近表达
2. 考虑口语化和书面语表达
3. 考虑不同的表述方式

输出格式（JSON数组）：
["同义词1", "同义词2", ...]

只输出JSON："""
            
            response = await llm._call(prompt)
            
            return self._parse_list_response(response)
            
        except Exception as e:
            app_logger.error(f"Synonym expansion failed: {e}")
            return []
    
    async def _expand_related_terms(self, query: str) -> List[str]:
        """扩展相关术语"""
        llm = self._get_llm()
        if llm is None:
            return []
        
        try:
            prompt = f"""为以下查询识别相关的术语和概念：

查询：{query}

要求：
1. 识别5-10个相关术语、概念、缩写
2. 包括上下位词、相关领域术语
3. 包括常见的相关实体名称

输出格式（JSON数组）：
["术语1", "术语2", ...]

只输出JSON："""
            
            response = await llm._call(prompt)
            
            return self._parse_list_response(response)
            
        except Exception as e:
            app_logger.error(f"Related terms expansion failed: {e}")
            return []
    
    def _parse_list_response(self, response: str) -> List[str]:
        """解析列表响应"""
        try:
            start = response.find('[')
            end = response.rfind(']') + 1
            if start != -1 and end != 0:
                return json.loads(response[start:end])
        except:
            pass
        return []


class QueryOptimizer:
    """Query优化器 - 综合Query处理"""
    
    def __init__(self):
        self._decomposer = QueryDecomposer()
        self._hyde = HyDEGenerator()
        self._expander = QueryExpander()
    
    async def optimize(
        self,
        query: str,
        enable_decompose: bool = True,
        enable_hyde: bool = True,
        enable_expand: bool = True
    ) -> ExpandedQuery:
        """
        优化Query
        
        Args:
            query: 原始查询
            enable_decompose: 是否启用分解
            enable_hyde: 是否启用HyDE
            enable_expand: 是否启用扩展
            
        Returns:
            ExpandedQuery
        """
        result = ExpandedQuery(original=query)
        
        if enable_decompose:
            result.sub_queries = await self._decomposer.decompose(query)
        
        if enable_hyde:
            result.hyde_result = await self._hyde.generate_hypothetical_doc(query)
        
        if enable_expand:
            result.synonyms = await self._expander._expand_synonyms(query)
            result.related_terms = await self._expander._expand_related_terms(query)
        
        result.complexity = self._expander._classify_complexity(query)
        
        return result
    
    def get_search_queries(self, expanded: ExpandedQuery) -> List[str]:
        """
        获取搜索查询列表
        
        Args:
            expanded: 扩展后的Query
            
        Returns:
            搜索查询列表
        """
        queries = set()
        
        queries.add(expanded.original)
        
        for sq in expanded.sub_queries:
            queries.add(sq.query)
        
        if expanded.hyde_result:
            queries.update(expanded.hyde_result.hypothetical_documents)
        
        queries.update(expanded.synonyms)
        queries.update(expanded.related_terms)
        
        return list(queries)


_query_optimizer: Optional[QueryOptimizer] = None


def get_query_optimizer() -> QueryOptimizer:
    """获取Query优化器"""
    global _query_optimizer
    if _query_optimizer is None:
        _query_optimizer = QueryOptimizer()
    return _query_optimizer
