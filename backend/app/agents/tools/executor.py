"""工具执行器 - 统一执行工具调用"""
from typing import Dict, List, Any, Optional
import time
import asyncio
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import ToolExecutionResult
from app.services.performance_metrics import get_performance_metrics
from app.agents.tools.meeting_tools import (
    MeetingSearchTool,
    TodoExtractionTool,
    MinutesGenerationTool,
    ControversyDetectionTool,
    QAAnswerTool,
    DocumentContentTool,
    DocumentSearchTool,
    TextProcessorTool
)

class ToolExecutor:
    """
    工具执行器
    
    统一管理工具的执行，包括：
    1. 单工具执行
    2. 批量执行
    3. 并行执行
    4. 执行结果缓存
    5. 错误处理和重试
    """
    
    def __init__(self):
        self.registry = get_tool_registry()
        self._cache: Dict[str, Any] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history = 1000
        # 工具实例缓存
        self._tool_instances: Dict[str, Any] = {}
        self.supported_tool_ids = {
            "search_meeting",
            "extract_todos",
            "generate_minutes",
            "detect_controversies",
            "answer_question",
            "get_document_content",
            "search_document",
            "text_processor",
            "jira_create_issue",
            "jira_get_issue",
            "jira_update_issue",
        }

    def get_supported_tool_ids(self) -> List[str]:
        """获取执行器实际支持的工具ID"""
        return sorted(self.supported_tool_ids)
    
    async def execute(
        self,
        tool_id: str,
        params: Dict[str, Any],
        llm_service=None,
        vector_search_service=None,
        context: Optional[Dict[str, Any]] = None,
        enable_cache: bool = True,
        retry_count: int = 3,
    ) -> ToolExecutionResult:
        """
        执行单个工具
        
        Args:
            tool_id: 工具ID
            params: 参数
            llm_service: LLM服务
            vector_search_service: 向量搜索服务
            context: 上下文
            enable_cache: 是否启用缓存
            retry_count: 重试次数
            
        Returns:
            执行结果
        """
        start_time = time.time()
        
        # 获取工具（先按ID查找，再按名称查找）
        tool = self.registry.get(tool_id)
        if not tool:
            # 尝试按名称查找（支持中文名称）
            tool = self.registry.get_by_name(tool_id)
        
        if not tool:
            return ToolExecutionResult(
                tool_id=tool_id,
                success=False,
                error=f"工具 {tool_id} 不存在",
            )
        
        # 检查工具状态
        _status = tool.metadata.status
        _status_val = _status.value if hasattr(_status, "value") else str(_status)
        if _status_val != "active":
            return ToolExecutionResult(
                tool_id=tool_id,
                success=False,
                error=f"工具 {tool_id} 当前状态为 {_status_val}",
            )
        
        # 生成缓存键
        cache_key = self._generate_cache_key(tool_id, params)
        
        # 检查缓存
        if enable_cache and tool.metadata.cacheable and cache_key in self._cache:
            app_logger.info(f"[Executor] 使用缓存结果: {tool_id}")
            cached_result = self._cache[cache_key]
            return ToolExecutionResult(
                tool_id=tool_id,
                success=True,
                result=cached_result,
                execution_time=0,
                cached=True,
            )
        
        # 执行工具（带重试）
        for attempt in range(retry_count):
            try:
                # 获取工具实例并执行
                result = await self._execute_tool(tool_id, params, llm_service, vector_search_service)
                
                if result is not None:
                    execution_time = time.time() - start_time
                    
                    # 更新缓存
                    if enable_cache and tool.metadata.cacheable:
                        self._cache[cache_key] = result
                    
                    # 记录执行历史
                    self._record_execution(tool_id, params, result, True)
                    
                    # 记录工具执行性能指标
                    get_performance_metrics().record_tool_execution(
                        tool_id=tool_id,
                        success=True,
                        latency_ms=execution_time * 1000,
                        retry_count=attempt
                    )
                    
                    return ToolExecutionResult(
                        tool_id=tool_id,
                        success=True,
                        result=result,
                        execution_time=execution_time,
                        cached=False,
                    )
            
            except Exception as e:
                app_logger.error(f"[Executor] 工具 {tool_id} 执行失败 (尝试 {attempt + 1}/{retry_count}): {e}")
                if attempt == retry_count - 1:
                    execution_time = time.time() - start_time
                    self._record_execution(tool_id, params, None, False, str(e))
                    return ToolExecutionResult(
                        tool_id=tool_id,
                        success=False,
                        error=f"执行失败: {str(e)}",
                        execution_time=execution_time,
                        metadata={
                            "error_category": getattr(e, "category", e.__class__.__name__),
                            "status_code": getattr(e, "status_code", None),
                            "retryable": bool(getattr(e, "retryable", False)),
                        },
                    )
                
                # 指数退避等待后重试: 1s, 2s, 4s
                await asyncio.sleep(2 ** attempt)
        
        return ToolExecutionResult(
            tool_id=tool_id,
            success=False,
            error="执行失败",
        )
    
    async def _execute_tool(
        self,
        tool_id: str,
        params: Dict[str, Any],
        llm_service=None,
        vector_search_service=None
    ) -> Any:
        """
        执行具体的工具
        
        Args:
            tool_id: 工具ID或工具名称
            params: 参数
            llm_service: LLM服务
            vector_search_service: 向量搜索服务
            
        Returns:
            执行结果
        """
        # 先获取工具，确定实际的工具ID
        tool = self.registry.get(tool_id)
        if not tool:
            tool = self.registry.get_by_name(tool_id)
        
        if not tool:
            app_logger.warning(f"[Executor] 未找到工具: {tool_id}")
            return None
        
        # 使用实际的工具ID
        actual_tool_id = tool.metadata.tool_id
        
        # 根据工具ID创建并执行对应的工具实例
        tool_instance = await self._get_tool_instance(actual_tool_id, llm_service, vector_search_service)
        
        if tool_instance:
            app_logger.info(f"[Executor] 执行工具: {tool_id} (实际ID: {actual_tool_id})")
            
            # 转换参数为工具期望的格式
            result = await tool_instance.execute(**params)
            
            # 统一返回格式
            if hasattr(result, 'result'):
                return result.result
            return result
        
        app_logger.warning(f"[Executor] 未找到工具实现: {tool_id}")
        return None
    
    async def _get_tool_instance(
        self,
        tool_id: str,
        llm_service=None,
        vector_search_service=None
    ):
        """
        获取或创建工具实例
        
        Args:
            tool_id: 工具ID
            llm_service: LLM服务
            vector_search_service: 向量搜索服务
            
        Returns:
            工具实例
        """
        # 检查缓存
        if tool_id in self._tool_instances:
            return self._tool_instances[tool_id]
        
        # 根据工具ID创建实例
        try:
            if tool_id not in self.supported_tool_ids:
                app_logger.warning(f"[Executor] 工具未在执行器支持列表中: {tool_id}")
                return None

            if tool_id == "search_meeting":
                if not vector_search_service:
                    app_logger.warning("[Executor] search_meeting 需要 vector_search_service")
                    return None
                instance = MeetingSearchTool(vector_search_service)
            elif tool_id == "extract_todos":
                if not llm_service:
                    app_logger.warning("[Executor] extract_todos 需要 llm_service")
                    return None
                instance = TodoExtractionTool(llm_service)
            elif tool_id == "generate_minutes":
                if not llm_service:
                    app_logger.warning("[Executor] generate_minutes 需要 llm_service")
                    return None
                instance = MinutesGenerationTool(llm_service)
            elif tool_id == "detect_controversies":
                if not llm_service:
                    app_logger.warning("[Executor] detect_controversies 需要 llm_service")
                    return None
                instance = ControversyDetectionTool(llm_service)
            elif tool_id == "answer_question":
                if not llm_service:
                    app_logger.warning("[Executor] answer_question 需要 llm_service")
                    return None
                instance = QAAnswerTool(llm_service)
            elif tool_id == "get_document_content":
                instance = DocumentContentTool()
            elif tool_id == "search_document":
                if not vector_search_service:
                    app_logger.warning("[Executor] search_document 需要 vector_search_service")
                    return None
                instance = DocumentSearchTool(vector_search_service)
            elif tool_id == "text_processor":
                instance = TextProcessorTool()
            elif tool_id.startswith("jira_"):
                from app.agents.tools.enterprise_tools import execute_jira_tool
                class JiraToolAdapter:
                    async def execute(self, **kwargs):
                        return await execute_jira_tool(tool_id, kwargs)
                instance = JiraToolAdapter()
            else:
                app_logger.warning(f"[Executor] 未知工具: {tool_id}")
                return None
            
            # 缓存实例
            self._tool_instances[tool_id] = instance
            return instance
            
        except Exception as e:
            app_logger.error(f"[Executor] 创建工具实例失败 {tool_id}: {e}")
            return None
    
    async def execute_batch(
        self,
        tasks: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        parallel: bool = False,
    ) -> List[ToolExecutionResult]:
        """
        批量执行工具
        
        Args:
            tasks: 任务列表，每个任务包含 tool_id 和 params
            context: 上下文
            parallel: 是否并行执行
            
        Returns:
            执行结果列表
        """
        if parallel:
            # 并行执行
            tasks_coroutines = [
                self.execute(task["tool_id"], task.get("params", {}), context)
                for task in tasks
            ]
            return await asyncio.gather(*tasks_coroutines)
        else:
            # 顺序执行
            results = []
            for task in tasks:
                result = await self.execute(task["tool_id"], task.get("params", {}), context)
                results.append(result)
            return results
    
    async def execute_parallel_group(
        self,
        tool_ids: List[str],
        params_list: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, ToolExecutionResult]:
        """
        并行执行一组工具
        
        Args:
            tool_ids: 工具ID列表
            params_list: 参数列表（与tool_ids对应）
            context: 上下文
            
        Returns:
            tool_id -> result 的映射
        """
        if len(tool_ids) != len(params_list):
            raise ValueError("tool_ids 和 params_list 长度必须一致")
        
        # 创建协程
        coroutines = [
            self.execute(tool_id, params, context)
            for tool_id, params in zip(tool_ids, params_list)
        ]
        
        # 并行执行
        results = await asyncio.gather(*coroutines)
        
        # 构建结果映射
        return {
            tool_id: result
            for tool_id, result in zip(tool_ids, results)
        }
    
    async def _execute_with_builtin(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]],
    ) -> Optional[Any]:
        """使用内置执行器执行工具"""
        try:
            # 对于内置工具，直接调用
            return execute_builtin_tool(tool_id, params, context)
        except Exception as e:
            app_logger.warning(f"[Executor] 内置执行器执行失败: {tool_id}, {e}")
            return None
    
    def _generate_cache_key(self, tool_id: str, params: Dict[str, Any]) -> str:
        """生成缓存键"""
        import hashlib
        import json
        
        # 将参数转换为字符串并排序
        param_str = json.dumps(params, sort_keys=True, default=str)
        key_str = f"{tool_id}:{param_str}"
        
        # 使用 SHA-256 生成稳定幂等键，避免可构造的 MD5 碰撞。
        return hashlib.sha256(key_str.encode()).hexdigest()
    
    def _record_execution(
        self,
        tool_id: str,
        params: Dict[str, Any],
        result: Any,
        success: bool,
        error: str = "",
    ):
        """记录执行历史"""
        self._execution_history.append({
            "tool_id": tool_id,
            "params": params,
            "result": result,
            "success": success,
            "error": error,
            "timestamp": time.time(),
        })
        
        # 限制历史记录数量
        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]
    
    def get_execution_history(
        self,
        tool_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取执行历史"""
        history = self._execution_history
        
        if tool_id:
            history = [h for h in history if h["tool_id"] == tool_id]
        
        return history[-limit:]
    
    def clear_cache(self):
        """清除缓存"""
        self._cache.clear()
        app_logger.info("[Executor] 缓存已清除")
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取执行统计"""
        total = len(self._execution_history)
        success = sum(1 for h in self._execution_history if h["success"])
        
        tool_stats = {}
        for h in self._execution_history:
            tool_id = h["tool_id"]
            if tool_id not in tool_stats:
                tool_stats[tool_id] = {"total": 0, "success": 0}
            tool_stats[tool_id]["total"] += 1
            if h["success"]:
                tool_stats[tool_id]["success"] += 1
        
        return {
            "total_executions": total,
            "successful_executions": success,
            "success_rate": success / total if total > 0 else 0,
            "cache_size": len(self._cache),
            "by_tool": tool_stats,
        }


# 全局执行器实例
_executor: Optional[ToolExecutor] = None

def get_tool_executor() -> ToolExecutor:
    """获取全局工具执行器"""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor
