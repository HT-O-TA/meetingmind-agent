"""Agent 追踪集成 - 在 Agent 执行链路中自动记录追踪数据"""
import time
import asyncio
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Dict, Any, Optional, List
from app.agents.monitor import get_monitor, AgentMonitor
from app.core.observability import get_observability_system


def trace_agent_node(node_name: str, component_type: str = "agent"):
    """
    Agent 节点追踪装饰器
    
    在 Agent 节点执行前后自动记录追踪 span，记录：
    - 执行时间
    - Token 消耗
    - 重试次数
    - 输出/错误信息
    
    Args:
        node_name: 节点名称（用于追踪显示）
        component_type: 组件类型（planner/retriever/tool/llm/reflection）
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            monitor = get_monitor()
            metrics = get_observability_system().get_metrics_collector()
            
            span_id = monitor.start_span(node_name)
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                
                duration = time.time() - start_time
                monitor.finish_span(span_id, {
                    "component_type": component_type,
                    "duration_ms": duration * 1000,
                })
                
                if component_type == "planner":
                    metrics.track_planner(duration)
                elif component_type == "retriever":
                    metrics.track_retriever("hybrid", duration)
                elif component_type == "reflection":
                    metrics.track_reflection("continue", duration)
                elif component_type == "tool":
                    metrics.track_tool(node_name, duration, success=True)
                elif component_type == "llm":
                    metrics.track_llm("qwen-max", duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                monitor.update_span_error(span_id, str(e))
                monitor.finish_span(span_id, {
                    "component_type": component_type,
                    "error": str(e),
                })
                
                if component_type == "tool":
                    metrics.track_tool(node_name, duration, success=False)
                
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            monitor = get_monitor()
            metrics = get_observability_system().get_metrics_collector()
            
            span_id = monitor.start_span(node_name)
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                duration = time.time() - start_time
                monitor.finish_span(span_id, {
                    "component_type": component_type,
                    "duration_ms": duration * 1000,
                })
                
                if component_type == "planner":
                    metrics.track_planner(duration)
                elif component_type == "retriever":
                    metrics.track_retriever("hybrid", duration)
                elif component_type == "reflection":
                    metrics.track_reflection("continue", duration)
                elif component_type == "tool":
                    metrics.track_tool(node_name, duration, success=True)
                elif component_type == "llm":
                    metrics.track_llm("qwen-max", duration)
                
                return result
            except Exception as e:
                duration = time.time() - start_time
                monitor.update_span_error(span_id, str(e))
                monitor.finish_span(span_id, {
                    "component_type": component_type,
                    "error": str(e),
                })
                
                if component_type == "tool":
                    metrics.track_tool(node_name, duration, success=False)
                
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


class AgentTraceContext:
    """
    Agent 追踪上下文管理器
    
    用于在代码块中手动记录追踪 span
    """
    
    def __init__(self, operation_name: str, component_type: str = "agent", parent_span_id: Optional[str] = None):
        self.operation_name = operation_name
        self.component_type = component_type
        self.parent_span_id = parent_span_id
        self.span_id = None
        self.start_time = None
        self.monitor = get_monitor()
        self.metrics = get_observability_system().get_metrics_collector()
    
    async def __aenter__(self):
        self.span_id = self.monitor.start_span(self.operation_name, parent_id=self.parent_span_id)
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type:
            self.monitor.update_span_error(self.span_id, str(exc_val))
            status = "failed"
        else:
            status = "completed"
        
        self.monitor.finish_span(self.span_id, {
            "component_type": self.component_type,
            "duration_ms": duration * 1000,
            "status": status,
        })
        
        self._record_metrics(duration, exc_type is None)
        
        return False
    
    def __enter__(self):
        self.span_id = self.monitor.start_span(self.operation_name, parent_id=self.parent_span_id)
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type:
            self.monitor.update_span_error(self.span_id, str(exc_val))
            status = "failed"
        else:
            status = "completed"
        
        self.monitor.finish_span(self.span_id, {
            "component_type": self.component_type,
            "duration_ms": duration * 1000,
            "status": status,
        })
        
        self._record_metrics(duration, exc_type is None)
        
        return False
    
    def _record_metrics(self, duration: float, success: bool):
        """记录指标"""
        if self.component_type == "planner":
            self.metrics.track_planner(duration)
        elif self.component_type == "retriever":
            self.metrics.track_retriever("hybrid", duration)
        elif self.component_type == "reflection":
            self.metrics.track_reflection("continue" if success else "retry", duration)
        elif self.component_type == "tool":
            self.metrics.track_tool(self.operation_name, duration, success)
        elif self.component_type == "llm":
            self.metrics.track_llm("qwen-max", duration)
        elif self.component_type == "agent":
            self.metrics.track_agent_request(self.operation_name, duration, success)
    
    def update_tokens(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        """更新 Token 信息"""
        if self.span_id:
            self.monitor.update_span_tokens(self.span_id, prompt_tokens, completion_tokens)
    
    def update_cost(self, cost_usd: float):
        """更新成本信息"""
        if self.span_id:
            self.monitor.update_span_cost(self.span_id, cost_usd)
    
    def update_retry(self, retry_count: int):
        """更新重试次数"""
        if self.span_id:
            self.monitor.update_span_retry(self.span_id, retry_count)
    
    def update_output(self, output: str):
        """更新输出信息"""
        if self.span_id:
            self.monitor.update_span_output(self.span_id, output)
    
    def update_error(self, error: str):
        """更新错误信息"""
        if self.span_id:
            self.monitor.update_span_error(self.span_id, error)


@dataclass
class ExecutionStep:
    """执行步骤记录"""
    step_id: str
    step_name: str
    component_type: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "running"
    prompt: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    retry_count: int = 0
    reflection_count: int = 0
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    parent_step_id: Optional[str] = None
    children: List["ExecutionStep"] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.input_data is None:
            self.input_data = {}
        if self.output_data is None:
            self.output_data = {}
    
    def finish(self, status: str = "completed"):
        """结束步骤"""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "step_id": self.step_id,
            "step_name": self.step_name,
            "component_type": self.component_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "prompt": self.prompt,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "retry_count": self.retry_count,
            "reflection_count": self.reflection_count,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "error": self.error,
            "parent_step_id": self.parent_step_id,
            "children": [child.to_dict() for child in self.children],
        }


class AgentExecutionTracer:
    """
    Agent 执行链路追踪器
    
    记录 Agent 执行的完整过程，包括：
    - Question → Planner → Retriever → Tool → Reflection → LLM → Answer
    - 每一步的 Prompt/Latency/Token/Cost
    - 工具输入输出
    - 重试次数/反思次数
    """
    
    def __init__(self):
        self.monitor = get_monitor()
        self.metrics = get_observability_system().get_metrics_collector()
        self.active_trace_id: Optional[str] = None
        self.current_steps: Dict[str, ExecutionStep] = {}
        self.trace_history: List[Dict[str, Any]] = []
        self.max_history = 100
    
    def start_trace(self, question: str) -> str:
        """
        开始新的追踪
        
        Args:
            question: 用户问题
            
        Returns:
            追踪 ID
        """
        trace_id = f"trace_{uuid.uuid4().hex[:16]}"
        self.active_trace_id = trace_id
        
        root_step = ExecutionStep(
            step_id=f"step_question_{uuid.uuid4().hex[:8]}",
            step_name="Question",
            component_type="input",
            start_time=time.time(),
            input_data={"question": question},
        )
        self.current_steps[root_step.step_id] = root_step
        
        return trace_id
    
    def start_step(self, step_name: str, component_type: str, parent_step_id: Optional[str] = None) -> str:
        """
        开始新的执行步骤
        
        Args:
            step_name: 步骤名称
            component_type: 组件类型（planner/retriever/tool/llm/reflection/answer）
            parent_step_id: 父步骤 ID
            
        Returns:
            步骤 ID
        """
        step_id = f"step_{component_type}_{uuid.uuid4().hex[:8]}"
        step = ExecutionStep(
            step_id=step_id,
            step_name=step_name,
            component_type=component_type,
            start_time=time.time(),
            parent_step_id=parent_step_id,
        )
        
        if parent_step_id and parent_step_id in self.current_steps:
            self.current_steps[parent_step_id].children.append(step)
        
        self.current_steps[step_id] = step
        
        return step_id
    
    def update_step_prompt(self, step_id: str, prompt: str):
        """更新步骤的 Prompt"""
        if step_id in self.current_steps:
            self.current_steps[step_id].prompt = prompt
    
    def update_step_tokens(self, step_id: str, prompt_tokens: int, completion_tokens: int):
        """更新步骤的 Token 信息"""
        if step_id in self.current_steps:
            step = self.current_steps[step_id]
            step.prompt_tokens = prompt_tokens
            step.completion_tokens = completion_tokens
            step.total_tokens = prompt_tokens + completion_tokens
    
    def update_step_cost(self, step_id: str, cost_usd: float):
        """更新步骤的成本信息"""
        if step_id in self.current_steps:
            self.current_steps[step_id].cost_usd = cost_usd
    
    def update_step_retry(self, step_id: str, retry_count: int):
        """更新步骤的重试次数"""
        if step_id in self.current_steps:
            self.current_steps[step_id].retry_count = retry_count
    
    def update_step_reflection(self, step_id: str, reflection_count: int):
        """更新步骤的反思次数"""
        if step_id in self.current_steps:
            self.current_steps[step_id].reflection_count = reflection_count
    
    def update_step_input(self, step_id: str, input_data: Dict[str, Any]):
        """更新步骤的输入数据"""
        if step_id in self.current_steps:
            self.current_steps[step_id].input_data.update(input_data)
    
    def update_step_output(self, step_id: str, output_data: Dict[str, Any]):
        """更新步骤的输出数据"""
        if step_id in self.current_steps:
            self.current_steps[step_id].output_data.update(output_data)
    
    def update_step_error(self, step_id: str, error: str):
        """更新步骤的错误信息"""
        if step_id in self.current_steps:
            self.current_steps[step_id].error = error
    
    def finish_step(self, step_id: str, status: str = "completed"):
        """
        结束步骤
        
        Args:
            step_id: 步骤 ID
            status: 状态（completed/failed）
        """
        if step_id in self.current_steps:
            step = self.current_steps[step_id]
            step.finish(status)
            
            self.metrics.track_agent_request(
                task_type=step.component_type,
                latency_seconds=step.duration_ms / 1000,
                success=(status == "completed")
            )
    
    def end_trace(self, answer: Optional[str] = None) -> Dict[str, Any]:
        """
        结束追踪
        
        Args:
            answer: 最终答案
            
        Returns:
            完整的追踪数据
        """
        if self.current_steps:
            first_step = list(self.current_steps.values())[0]
            last_end_time = max(step.end_time or time.time() for step in self.current_steps.values())
            first_step.end_time = last_end_time
            first_step.duration_ms = (last_end_time - first_step.start_time) * 1000
            first_step.status = "completed"
        
        if answer:
            answer_step = ExecutionStep(
                step_id=f"step_answer_{uuid.uuid4().hex[:8]}",
                step_name="Answer",
                component_type="output",
                start_time=time.time(),
                end_time=time.time(),
                duration_ms=0,
                status="completed",
                output_data={"answer": answer},
            )
            self.current_steps[answer_step.step_id] = answer_step
        
        root_steps = [
            step for step in self.current_steps.values() 
            if step.parent_step_id is None
        ]
        
        trace_data = {
            "trace_id": self.active_trace_id,
            "start_time": min(step.start_time for step in self.current_steps.values()) if self.current_steps else time.time(),
            "end_time": max(step.end_time or time.time() for step in self.current_steps.values()) if self.current_steps else time.time(),
            "status": "completed" if all(s.status == "completed" for s in self.current_steps.values()) else "failed",
            "steps": [step.to_dict() for step in root_steps],
            "summary": self._calculate_summary(),
        }
        
        self.trace_history.append(trace_data)
        if len(self.trace_history) > self.max_history:
            self.trace_history = self.trace_history[-self.max_history:]
        
        self.active_trace_id = None
        self.current_steps.clear()
        
        return trace_data
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """计算追踪摘要"""
        total_tokens = sum(step.total_tokens for step in self.current_steps.values())
        total_cost = sum(step.cost_usd for step in self.current_steps.values())
        total_duration_ms = sum(step.duration_ms or 0 for step in self.current_steps.values())
        total_retries = sum(step.retry_count for step in self.current_steps.values())
        total_reflections = sum(step.reflection_count for step in self.current_steps.values())
        
        component_stats = {}
        for step in self.current_steps.values():
            if step.component_type not in component_stats:
                component_stats[step.component_type] = {
                    "count": 0,
                    "total_duration_ms": 0,
                    "total_tokens": 0,
                    "total_cost_usd": 0,
                }
            component_stats[step.component_type]["count"] += 1
            component_stats[step.component_type]["total_duration_ms"] += step.duration_ms or 0
            component_stats[step.component_type]["total_tokens"] += step.total_tokens
            component_stats[step.component_type]["total_cost_usd"] += step.cost_usd
        
        return {
            "total_steps": len(self.current_steps),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "total_duration_ms": total_duration_ms,
            "total_retries": total_retries,
            "total_reflections": total_reflections,
            "component_stats": component_stats,
        }
    
    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """获取指定追踪数据"""
        for trace in self.trace_history:
            if trace["trace_id"] == trace_id:
                return trace
        return None
    
    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的追踪数据"""
        return self.trace_history[-limit:]
    
    def get_timeline(self, trace_id: str = None) -> Dict[str, Any]:
        """
        获取 Agent Timeline 数据
        
        Args:
            trace_id: 追踪 ID（可选，默认获取最近一次）
            
        Returns:
            Timeline 数据
        """
        if trace_id:
            trace = self.get_trace(trace_id)
        else:
            trace = self.trace_history[-1] if self.trace_history else None
        
        if not trace:
            return {"error": "No trace found"}
        
        all_steps = []
        
        def flatten_steps(steps):
            for step in steps:
                all_steps.append({
                    "step_id": step["step_id"],
                    "step_name": step["step_name"],
                    "component_type": step["component_type"],
                    "start_time": step["start_time"],
                    "duration_ms": step["duration_ms"] or 0.0,
                    "status": step["status"],
                    "total_tokens": step["total_tokens"] or 0,
                    "cost_usd": step["cost_usd"] or 0.0,
                    "retry_count": step["retry_count"] or 0,
                    "reflection_count": step["reflection_count"] or 0,
                })
                if step.get("children"):
                    flatten_steps(step["children"])
        
        flatten_steps(trace["steps"])
        
        all_steps.sort(key=lambda x: x["start_time"])
        
        return {
            "trace_id": trace["trace_id"],
            "start_time": trace["start_time"],
            "end_time": trace["end_time"],
            "total_duration_ms": trace["summary"]["total_duration_ms"],
            "total_tokens": trace["summary"]["total_tokens"],
            "total_cost_usd": trace["summary"]["total_cost_usd"],
            "timeline": all_steps,
        }


_execution_tracer: Optional[AgentExecutionTracer] = None


def get_execution_tracer() -> AgentExecutionTracer:
    """获取执行链路追踪器实例"""
    global _execution_tracer
    if _execution_tracer is None:
        _execution_tracer = AgentExecutionTracer()
    return _execution_tracer


def trace_agent_execution(func):
    """
    Agent 执行追踪装饰器
    
    自动记录完整的执行链路
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        tracer = get_execution_tracer()
        question = kwargs.get("question", str(args[0]) if args else "")
        
        trace_id = tracer.start_trace(question)
        
        try:
            result = await func(*args, **kwargs)
            
            answer = getattr(result, "answer", None) if hasattr(result, "answer") else str(result)
            tracer.end_trace(answer)
            
            return result
        except Exception as e:
            tracer.end_trace(f"Error: {str(e)}")
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        tracer = get_execution_tracer()
        question = kwargs.get("question", str(args[0]) if args else "")
        
        trace_id = tracer.start_trace(question)
        
        try:
            result = func(*args, **kwargs)
            
            answer = getattr(result, "answer", None) if hasattr(result, "answer") else str(result)
            tracer.end_trace(answer)
            
            return result
        except Exception as e:
            tracer.end_trace(f"Error: {str(e)}")
            raise
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper