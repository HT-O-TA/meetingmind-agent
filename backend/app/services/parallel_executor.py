"""并行执行引擎 - 支持依赖感知、结果汇聚、错误隔离

功能：
1. 依赖拓扑排序：按 parallel_groups 构建执行波次
2. 波次并行执行：asyncio.gather + 独立超时控制
3. 结果汇聚：收集所有任务结果，传递依赖上下文
4. 完整性检查：统计 completed/failed/skipped，触发降级或 replan
"""
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from app.core.logger import app_logger


@dataclass
class ExecutionResult:
    """并行执行结果"""
    total: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    failed_task_ids: List[str] = field(default_factory=list)
    all_failed: bool = False
    partial_failure: bool = False
    failure_rate: float = 0.0


class ParallelExecutor:
    """并行执行引擎 - 真正的 asyncio.gather 并行"""

    def __init__(
        self,
        max_workers: int = 3,
        task_timeout: float = 60.0,
        failure_threshold: float = 0.3,
    ):
        self._max_workers = max_workers
        self._task_timeout = task_timeout
        self._failure_threshold = failure_threshold

    async def execute(
        self,
        tasks: Dict[str, Any],
        parallel_groups: List[List[str]],
        execute_fn: Callable,
        state: Any,
        all_tasks: Dict,
    ) -> ExecutionResult:
        """执行并行任务

        Args:
            tasks: 任务字典 {task_id: task_dict}
            parallel_groups: 并行分组列表
            execute_fn: 单任务执行函数 async fn(state, task, all_tasks) -> Any
            state: AgentState
            all_tasks: 完整任务字典（用于依赖传递）

        Returns:
            ExecutionResult: 执行结果统计
        """
        result = ExecutionResult(total=len(tasks))

        # Phase 1: 依赖拓扑排序 - 构建执行波次
        waves = self._build_waves(tasks, parallel_groups)
        app_logger.info(
            f"[ParallelExecutor] 构建了 {len(waves)} 个执行波次, "
            f"总任务数: {result.total}"
        )

        # Phase 2-3: 逐波执行 + 结果汇聚
        for wave_idx, wave_task_ids in enumerate(waves):
            ready_tasks = [
                (tid, tasks[tid])
                for tid in wave_task_ids
                if tid in tasks and tasks[tid].get("status") == "pending"
            ]

            if not ready_tasks:
                continue

            if len(ready_tasks) == 1:
                # 单任务直接执行
                await self._execute_single_with_timeout(
                    execute_fn, state, ready_tasks[0][1], all_tasks, result
                )
            else:
                # 多任务并行执行
                await self._execute_wave_parallel(
                    execute_fn, state, ready_tasks, all_tasks, result, wave_idx
                )

        # Phase 4: 完整性检查
        result.all_failed = result.completed == 0 and result.total > 0
        result.failure_rate = result.failed / result.total if result.total > 0 else 0.0
        result.partial_failure = 0 < result.failed < result.total

        if result.all_failed:
            app_logger.warning(
                f"[ParallelExecutor] 全部任务失败 ({result.failed}/{result.total}), 建议触发 replan"
            )
        elif result.partial_failure:
            app_logger.warning(
                f"[ParallelExecutor] 部分任务失败 ({result.failed}/{result.total}), "
                f"失败率: {result.failure_rate:.1%}, 失败任务: {result.failed_task_ids}"
            )

        return result

    def _build_waves(
        self,
        tasks: Dict[str, Any],
        parallel_groups: List[List[str]],
    ) -> List[List[str]]:
        """构建执行波次

        每个 parallel_group 作为一个波次，组内任务并行执行。
        不在任何组中的任务按 execution_order 串行执行（各自一个波次）。
        """
        waves: List[List[str]] = []
        grouped_ids = set()

        # 并行组作为独立波次
        for group in parallel_groups:
            valid_group = [tid for tid in group if tid in tasks]
            if valid_group:
                waves.append(valid_group)
                grouped_ids.update(valid_group)

        # 未分组的任务各自一个波次（串行）
        for tid, task in tasks.items():
            if tid not in grouped_ids and task.get("status") == "pending":
                waves.append([tid])

        return waves

    async def _execute_wave_parallel(
        self,
        execute_fn: Callable,
        state: Any,
        ready_tasks: List[tuple],
        all_tasks: Dict,
        result: ExecutionResult,
        wave_idx: int,
    ):
        """并行执行一个波次的任务"""
        app_logger.info(
            f"[ParallelExecutor] 波次 {wave_idx + 1}: 并行执行 {len(ready_tasks)} 个任务"
        )

        # 限制并行度
        semaphore = asyncio.Semaphore(self._max_workers)

        async def execute_with_limit(task_id: str, task: Any):
            async with semaphore:
                return await self._execute_single_with_timeout(
                    execute_fn, state, task, all_tasks, result, return_on_error=True
                )

        # 并行执行
        exec_results = await asyncio.gather(
            *[execute_with_limit(tid, task) for tid, task in ready_tasks],
            return_exceptions=True,
        )

        # 处理结果
        for (task_id, _), exec_res in zip(ready_tasks, exec_results):
            if isinstance(exec_res, Exception):
                app_logger.error(
                    f"[ParallelExecutor] 任务 {task_id} 执行异常: {exec_res}"
                )
                if task_id in all_tasks:
                    all_tasks[task_id]["status"] = "failed"
                    all_tasks[task_id]["error"] = str(exec_res)
                result.failed += 1
                result.failed_task_ids.append(task_id)
            elif exec_res is not None and isinstance(exec_res, bool) and exec_res:
                result.completed += 1
            else:
                # execute_fn 内部已处理状态
                task = all_tasks.get(task_id, {})
                if task.get("status") == "completed":
                    result.completed += 1
                elif task.get("status") == "failed":
                    result.failed += 1
                    result.failed_task_ids.append(task_id)
                else:
                    result.skipped += 1

    async def _execute_single_with_timeout(
        self,
        execute_fn: Callable,
        state: Any,
        task: Any,
        all_tasks: Dict,
        result: ExecutionResult,
        return_on_error: bool = False,
    ) -> Any:
        """带超时的单任务执行"""
        task_id = task.get("task_id", "unknown")
        try:
            await asyncio.wait_for(
                execute_fn(state, task, all_tasks),
                timeout=self._task_timeout,
            )
            if task.get("status") == "completed":
                if not return_on_error:
                    result.completed += 1
                return True
            elif task.get("status") == "failed":
                if not return_on_error:
                    result.failed += 1
                    result.failed_task_ids.append(task_id)
                return False
            else:
                if not return_on_error:
                    result.skipped += 1
                return None
        except asyncio.TimeoutError:
            app_logger.error(
                f"[ParallelExecutor] 任务 {task_id} 超时 ({self._task_timeout}s)"
            )
            task["status"] = "failed"
            task["error"] = f"任务超时 ({self._task_timeout}s)"
            if not return_on_error:
                result.failed += 1
                result.failed_task_ids.append(task_id)
            return False
        except Exception as e:
            app_logger.error(f"[ParallelExecutor] 任务 {task_id} 执行失败: {e}")
            task["status"] = "failed"
            task["error"] = str(e)
            if not return_on_error:
                result.failed += 1
                result.failed_task_ids.append(task_id)
            return False


_executor_instance: Optional[ParallelExecutor] = None


def get_parallel_executor() -> ParallelExecutor:
    """获取全局 ParallelExecutor 实例"""
    global _executor_instance
    if _executor_instance is None:
        from app.core.config import settings
        _executor_instance = ParallelExecutor(
            max_workers=getattr(settings, "MAX_PARALLEL_WORKERS", 3),
            task_timeout=getattr(settings, "TASK_TIMEOUT_SECONDS", 60),
        )
    return _executor_instance
