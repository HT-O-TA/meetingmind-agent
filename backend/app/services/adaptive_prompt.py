"""自适应Prompt构建器 + 上下文压缩"""
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from app.core.logger import app_logger
from app.core.config import settings


class QueryType(str, Enum):
    """Query类型分类"""
    FACTUAL = "factual"           # 事实性问题
    SUMMARY = "summary"          # 总结性问题
    COMPARISON = "comparison"     # 对比性问题
    REASONING = "reasoning"      # 推理性问题
    LIST = "list"               # 列表性问题
    DEFINITION = "definition"    # 定义性问题
    PROCEDURAL = "procedural"   # 步骤性问题
    GENERAL = "general"         # 通用问题


@dataclass
class PromptTemplate:
    """Prompt模板"""
    query_type: QueryType
    system_prompt: str
    user_template: str
    use_cot: bool = False
    few_shot_examples: List[Dict[str, str]] = field(default_factory=list)
    max_context_tokens: int = 4000


@dataclass  
class CompressedContext:
    """压缩后的上下文"""
    original_chunks: List[str]
    compressed_chunks: List[str]
    preservation_ratio: float
    key_info_preserved: List[str]
    removed_redundancy: List[str]


class AdaptivePromptBuilder:
    """自适应Prompt构建器 + 上下文压缩"""
    
    def __init__(self, llm_service=None):
        self._llm = llm_service
        self._templates = self._init_templates()
        self._tokenizer = None
    
    def _init_templates(self) -> Dict[QueryType, PromptTemplate]:
        """初始化Prompt模板"""
        return {
            QueryType.FACTUAL: PromptTemplate(
                query_type=QueryType.FACTUAL,
                system_prompt="""你是一个精确的信息提取助手。你的任务是：
1. 仔细阅读提供的上下文
2. 找出与问题直接相关的具体信息
3. 如果上下文中没有答案，明确说明"上下文未提供此信息"
4. 回答要简洁准确，引用来源""",
                user_template="""基于以下上下文回答问题。如果上下文中没有相关信息，请明确说明。

上下文：
{context}

问题：{question}

要求：
1. 只使用上下文中的信息
2. 用[来源]标注信息来源
3. 简洁准确地回答""",
                use_cot=False
            ),
            
            QueryType.SUMMARY: PromptTemplate(
                query_type=QueryType.SUMMARY,
                system_prompt="""你是一个专业的会议记录助手。你的任务是：
1. 全面理解会议内容
2. 提取关键信息：主题、讨论点、决议、待办
3. 结构化组织信息
4. 保持原文要点""",
                user_template="""请总结以下会议内容，生成结构化的会议纪要：

上下文：
{context}

要求：
1. 包含：会议主题、参会人员、讨论内容、决议事项、待办事项
2. 按重要性排序
3. 引用关键引述[来源]""",
                use_cot=False
            ),
            
            QueryType.COMPARISON: PromptTemplate(
                query_type=QueryType.COMPARISON,
                system_prompt="""你是一个分析助手。比较不同选项时：
1. 识别比较维度
2. 客观呈现各选项的特点
3. 突出差异点
4. 基于上下文给出建议""",
                user_template="""比较以下内容并回答问题：

上下文：
{context}

问题：{question}

请从以下维度比较：
1. 各自特点
2. 优缺点
3. 适用场景
4. 结论/建议""",
                use_cot=True
            ),
            
            QueryType.REASONING: PromptTemplate(
                query_type=QueryType.REASONING,
                system_prompt="""你是一个逻辑推理助手。进行推理时：
1. 明确已知前提
2. 逐步推导
3. 说明推理过程
4. 给出最终结论
5. 标注推理所依赖的上下文信息""",
                user_template="""请基于上下文进行推理分析：

上下文：
{context}

问题：{question}

要求：
1. 列出已知信息
2. 展示推理步骤
3. 给出结论
4. 标注依据[来源]""",
                use_cot=True,
                few_shot_examples=[
                    {"context": "A项目需要3天，B项目需要5天", "answer": "1. 已知：A项目3天，B项目5天\n2. 推理：A比B少2天\n3. 结论：先做A效率更高"}
                ]
            ),
            
            QueryType.LIST: PromptTemplate(
                query_type=QueryType.LIST,
                system_prompt="""你是一个信息整理助手。列出项目时：
1. 按逻辑分类组织
2. 每项简洁明了
3. 标注来源
4. 必要时提供简要说明""",
                user_template="""请列出以下内容：

上下文：
{context}

问题：{question}

列出所有相关项目，并用编号组织""",
                use_cot=False
            ),
            
            QueryType.DEFINITION: PromptTemplate(
                query_type=QueryType.DEFINITION,
                system_prompt="""你是一个专业术语解释助手。解释概念时：
1. 给出清晰定义
2. 提供必要的背景
3. 举例说明
4. 引用权威来源""",
                user_template="""请解释以下概念：

上下文：
{context}

问题：{question}

要求：
1. 给出精确定义
2. 提供背景信息
3. 如有多个定义，列出各来源的不同版本
4. 引用来源[来源]""",
                use_cot=False
            ),
            
            QueryType.PROCEDURAL: PromptTemplate(
                query_type=QueryType.PROCEDURAL,
                system_prompt="""你是一个流程指导助手。描述步骤时：
1. 清晰列出先后顺序
2. 说明每步要点
3. 标注注意事项
4. 注明所需资源/时间""",
                user_template="""请描述以下流程/步骤：

上下文：
{context}

问题：{question}

要求：
1. 列出详细步骤
2. 每步标注序号
3. 说明关键点
4. 引用来源[来源]""",
                use_cot=False
            ),
            
            QueryType.GENERAL: PromptTemplate(
                query_type=QueryType.GENERAL,
                system_prompt="""你是一个有帮助的助手。回答问题时：
1. 充分利用上下文
2. 回答全面但简洁
3. 如需更多信息，说明需求
4. 引用来源""",
                user_template="""基于以下上下文回答问题：

上下文：
{context}

问题：{question}

要求：
1. 充分利用上下文信息
2. 回答完整准确
3. 引用相关来源""",
                use_cot=False
            )
        }
    
    def _get_tokenizer(self):
        """获取分词器"""
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
                model_name = settings.EMBEDDING_MODEL
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_name, 
                    trust_remote_code=True
                )
            except Exception as e:
                app_logger.warning(f"Could not load tokenizer: {e}")
                self._tokenizer = None
        return self._tokenizer
    
    def _count_tokens(self, text: str) -> int:
        """估算token数量"""
        tokenizer = self._get_tokenizer()
        if tokenizer:
            return len(tokenizer.encode(text))
        return len(text) // 4
    
    async def classify_query(self, query: str) -> QueryType:
        """
        识别Query类型
        
        Args:
            query: 用户问题
            
        Returns:
            QueryType
        """
        keywords = {
            QueryType.FACTUAL: ["是什么", "谁", "多少", "哪个", "什么时间", "什么地方"],
            QueryType.SUMMARY: ["总结", "概括", "摘要", "主要内容", "要点"],
            QueryType.COMPARISON: ["比较", "对比", "区别", "差异", "哪个更好", "异同"],
            QueryType.REASONING: ["为什么", "原因", "推理", "分析", "所以", "因此"],
            QueryType.LIST: ["列出", "有哪些", "都有什么", "哪些"],
            QueryType.DEFINITION: ["定义", "概念", "是什么意思", "解释"],
            QueryType.PROCEDURAL: ["步骤", "流程", "怎么做", "如何进行", "方法"]
        }
        
        query_lower = query.lower()
        
        for qtype, kws in keywords.items():
            for kw in kws:
                if kw in query_lower:
                    return qtype
        
        return QueryType.GENERAL
    
    async def compress_context(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        max_tokens: int = 4000
    ) -> CompressedContext:
        """
        上下文压缩
        
        使用LLM识别并保留关键信息，删除冗余
        
        Args:
            chunks: 检索到的文档块
            query: 查询问题
            max_tokens: 最大token数
            
        Returns:
            CompressedContext
        """
        if not chunks:
            return CompressedContext(
                original_chunks=[],
                compressed_chunks=[],
                preservation_ratio=1.0,
                key_info_preserved=[],
                removed_redundancy=[]
            )
        
        original_texts = [c.get("chunk_text", "") for c in chunks]
        original_str = "\n\n".join(f"[{i+1}] {t}" for i, t in enumerate(original_texts))
        original_tokens = self._count_tokens(original_str)
        
        if original_tokens <= max_tokens:
            return CompressedContext(
                original_chunks=original_texts,
                compressed_chunks=original_texts,
                preservation_ratio=1.0,
                key_info_preserved=original_texts,
                removed_redundancy=[]
            )
        
        llm = self._get_llm()
        if llm is None:
            ratio = max_tokens / original_tokens
            kept = original_texts[:int(len(original_texts) * ratio)]
            return CompressedContext(
                original_chunks=original_texts,
                compressed_chunks=kept,
                preservation_ratio=ratio,
                key_info_preserved=kept,
                removed_redundancy=original_texts[int(len(original_texts) * ratio):]
            )
        
        try:
            prompt = f"""你是一个上下文压缩助手。请从以下上下文中提取与问题相关的信息，删除冗余内容。

问题：{query}

上下文：
{original_str}

要求：
1. 保留与问题直接相关的信息
2. 删除重复、冗余的表述
3. 合并相似内容
4. 保持原文的关键数据和引用
5. 输出格式：JSON，包含压缩后的文本列表

输出JSON格式：
{{"compressed": ["内容1", "内容2", ...], "removed": ["被删除的冗余内容"]}}
"""
            
            result = await llm._call(prompt)
            parsed = self._parse_json_response(result)
            
            if parsed and "compressed" in parsed:
                compressed = parsed["compressed"]
                removed = parsed.get("removed", [])
                new_tokens = self._count_tokens("\n\n".join(compressed))
                
                return CompressedContext(
                    original_chunks=original_texts,
                    compressed_chunks=compressed,
                    preservation_ratio=new_tokens / original_tokens if original_tokens > 0 else 1.0,
                    key_info_preserved=compressed,
                    removed_redundancy=removed
                )
            
        except Exception as e:
            app_logger.error(f"Context compression failed: {e}")
        
        ratio = max_tokens / original_tokens if original_tokens > 0 else 1.0
        kept = original_texts[:max(1, int(len(original_texts) * ratio))]
        
        return CompressedContext(
            original_chunks=original_texts,
            compressed_chunks=kept,
            preservation_ratio=ratio,
            key_info_preserved=kept,
            removed_redundancy=original_texts[len(kept):]
        )
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """解析JSON响应"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end != 0:
                return json.loads(response[start:end])
        except:
            pass
        return None
    
    def _get_llm(self):
        """获取LLM服务"""
        if self._llm is None:
            try:
                from app.services.llm_service import LLMService
                self._llm = LLMService()
            except Exception as e:
                app_logger.warning(f"Could not load LLM service: {e}")
        return self._llm
    
    async def build_prompt(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        query_type: QueryType = None,
        add_citations: bool = True
    ) -> Tuple[str, str]:
        """
        构建自适应Prompt
        
        Args:
            query: 用户问题
            retrieved_chunks: 检索到的文档块
            query_type: 指定query类型（可选）
            add_citations: 是否添加引用标注
            
        Returns:
            (system_prompt, user_prompt)
        """
        if query_type is None:
            query_type = await self.classify_query(query)
        
        template = self._templates.get(query_type, self._templates[QueryType.GENERAL])
        
        compressed = await self.compress_context(
            chunks=retrieved_chunks,
            query=query,
            max_tokens=template.max_context_tokens
        )
        
        context_parts = []
        for i, chunk in enumerate(compressed.compressed_chunks):
            source_id = retrieved_chunks[i].get("chunk_id", i + 1)
            doc_id = retrieved_chunks[i].get("document_id", "")
            if add_citations:
                context_parts.append(f"[文档{doc_id}:{source_id}] {chunk}")
            else:
                context_parts.append(chunk)
        
        context_str = "\n\n".join(context_parts)
        
        system_prompt = template.system_prompt
        
        if template.few_shot_examples:
            system_prompt += "\n\n示例：\n"
            for ex in template.few_shot_examples:
                system_prompt += f"问题：{ex.get('question', '示例问题')}\n"
                system_prompt += f"回答：{ex.get('answer', '')}\n\n"
        
        if template.use_cot:
            system_prompt += "\n\n请逐步推理，展示思考过程。"
        
        user_prompt = template.user_template.format(
            context=context_str,
            question=query
        )
        
        return system_prompt, user_prompt
    
    async def build_stream_prompt(
        self,
        query: str,
        retrieved_chunks: List[Dict[str, Any]],
        query_type: QueryType = None
    ) -> Dict[str, Any]:
        """构建流式响应的Prompt"""
        system_prompt, user_prompt = await self.build_prompt(
            query=query,
            retrieved_chunks=retrieved_chunks,
            query_type=query_type
        )
        
        return {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": True
        }


class ContextCompressor:
    """独立的上下文压缩器（轻量级）"""
    
    def __init__(self):
        self._tokenizer = None
    
    def _get_tokenizer(self):
        if self._tokenizer is None:
            try:
                from transformers import AutoTokenizer
                model_name = settings.EMBEDDING_MODEL
                self._tokenizer = AutoTokenizer.from_pretrained(
                    model_name,
                    trust_remote_code=True
                )
            except:
                self._tokenizer = None
        return self._tokenizer
    
    def count_tokens(self, text: str) -> int:
        tokenizer = self._get_tokenizer()
        if tokenizer:
            return len(tokenizer.encode(text))
        return len(text) // 4
    
    def compress_by_ratio(
        self,
        chunks: List[str],
        max_ratio: float = 0.5
    ) -> List[str]:
        """
        按比例压缩上下文
        
        Args:
            chunks: 文档块列表
            max_ratio: 最大保留比例
            
        Returns:
            压缩后的块列表
        """
        if max_ratio >= 1.0:
            return chunks
        
        keep_count = max(1, int(len(chunks) * max_ratio))
        return chunks[:keep_count]
    
    def compress_by_relevance(
        self,
        chunks: List[Dict[str, Any]],
        query: str,
        max_chunks: int = 5
    ) -> List[Dict[str, Any]]:
        """
        按相关性压缩
        
        Args:
            chunks: 带分数的文档块
            query: 查询
            max_chunks: 最大保留数量
            
        Returns:
            压缩后的块列表
        """
        if len(chunks) <= max_chunks:
            return chunks
        
        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.get("score", 0),
            reverse=True
        )
        
        return sorted_chunks[:max_chunks]
    
    def compress_by_token_limit(
        self,
        chunks: List[str],
        max_tokens: int = 4000
    ) -> List[str]:
        """
        按token限制压缩
        
        Args:
            chunks: 文档块列表
            max_tokens: 最大token数
            
        Returns:
            压缩后的块列表
        """
        result = []
        current_tokens = 0
        
        for chunk in chunks:
            chunk_tokens = self.count_tokens(chunk)
            if current_tokens + chunk_tokens <= max_tokens:
                result.append(chunk)
                current_tokens += chunk_tokens
            else:
                remaining = max_tokens - current_tokens
                if remaining > 100:
                    truncated = chunk[:remaining * 4]
                    result.append(truncated + "...")
                break
        
        return result


_adaptive_prompt_builder: Optional[AdaptivePromptBuilder] = None
_context_compressor: Optional[ContextCompressor] = None


def get_adaptive_prompt_builder() -> AdaptivePromptBuilder:
    """获取自适应Prompt构建器"""
    global _adaptive_prompt_builder
    if _adaptive_prompt_builder is None:
        _adaptive_prompt_builder = AdaptivePromptBuilder()
    return _adaptive_prompt_builder


def get_context_compressor() -> ContextCompressor:
    """获取上下文压缩器"""
    global _context_compressor
    if _context_compressor is None:
        _context_compressor = ContextCompressor()
    return _context_compressor
