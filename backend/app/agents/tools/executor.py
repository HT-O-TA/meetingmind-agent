"""工具执行器 - 统一执行工具调用"""
from typing import Dict, List, Any, Optional
import time
import asyncio
from app.core.logger import app_logger
from app.agents.tools.registry import get_tool_registry
from app.agents.tools.tool_metadata import ToolExecutionResult
from app.agents.tools.builtin import execute_builtin_tool

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
    
    async def execute(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        enable_cache: bool = True,
        retry_count: int = 3,
    ) -> ToolExecutionResult:
        """
        执行单个工具
        
        Args:
            tool_id: 工具ID
            params: 参数
            context: 上下文
            enable_cache: 是否启用缓存
            retry_count: 重试次数
            
        Returns:
            执行结果
        """
        # 获取工具
        tool = self.registry.get(tool_id)
        if not tool:
            return ToolExecutionResult(
                tool_id=tool_id,
                success=False,
                error=f"工具 {tool_id} 不存在",
            )
        
        # 检查工具状态
        if tool.metadata.status.value != "active":
            return ToolExecutionResult(
                tool_id=tool_id,
                success=False,
                error=f"工具 {tool_id} 当前状态为 {tool.metadata.status.value}",
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
                # 首先尝试内置工具执行器
                result = await self._execute_with_builtin(tool_id, params, context)
                
                if result is not None:
                    # 更新缓存
                    if enable_cache and tool.metadata.cacheable:
                        self._cache[cache_key] = result
                    
                    # 记录执行历史
                    self._record_execution(tool_id, params, result, True)
                    
                    return ToolExecutionResult(
                        tool_id=tool_id,
                        success=True,
                        result=result,
                        execution_time=0,
                    )
                
                # 使用工具的execute方法
                result = await tool.execute(params, context)
                
                # 更新缓存
                if enable_cache and tool.metadata.cacheable and result.success:
                    self._cache[cache_key] = result.result
                
                # 记录执行历史
                self._record_execution(tool_id, params, result.result if result.success else None, result.success)
                
                return result
            
            except Exception as e:
                app_logger.error(f"[Executor] 工具 {tool_id} 执行失败 (尝试 {attempt + 1}/{retry_count}): {e}")
                if attempt == retry_count - 1:
                    self._record_execution(tool_id, params, None, False, str(e))
                    return ToolExecutionResult(
                        tool_id=tool_id,
                        success=False,
                        error=f"执行失败: {str(e)}",
                    )
                
                # 等待后重试
                await asyncio.sleep(0.5 * (attempt + 1))
        
        return ToolExecutionResult(
            tool_id=tool_id,
            success=False,
            error="执行失败",
        )
    
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
        
        # 生成MD5哈希
        return hashlib.md5(key_str.encode()).hexdigest()
    
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
