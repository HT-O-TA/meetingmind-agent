"""错误处理与容错系统 - 支持重试机制、降级策略和熔断机制"""
import asyncio
import time
from typing import Dict, List, Any, Optional, Callable, Tuple
from enum import Enum
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
from app.core.logger import app_logger


class RetryStatus(str, Enum):
    """重试状态"""
    PENDING = "pending"
    RETRYING = "retrying"
    SUCCESS = "success"
    FAILED = "failed"


class CircuitBreakerState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 熔断状态
    HALF_OPEN = "half_open" # 半开状态


class FallbackStrategy(str, Enum):
    """降级策略"""
    RETURN_DEFAULT = "return_default"
    RETURN_CACHE = "return_cache"
    THROW_EXCEPTION = "throw_exception"
    CALL_ALTERNATE = "call_alternate"


@dataclass
class RetryRecord:
    """重试记录"""
    operation_id: str
    max_retries: int
    current_retry: int
    status: RetryStatus
    last_error: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()


@dataclass
class CircuitBreakerState:
    """熔断器状态记录"""
    name: str
    state: CircuitBreakerState
    failure_count: int
    success_count: int
    last_failure_time: Optional[datetime]
    reset_timeout: int  # 熔断重置超时时间（秒）
    failure_threshold: int  # 失败阈值
    success_threshold: int  # 成功阈值
    
    def __post_init__(self):
        if self.state is None:
            self.state = CircuitBreakerState.CLOSED


class RetryManager:
    """重试管理器"""
    
    def __init__(self):
        self._records: Dict[str, RetryRecord] = {}
        self._default_max_retries = 3
        self._default_backoff_base = 1.0  # 指数退避基数
    
    async def execute_with_retry(
        self,
        operation_id: str,
        func: Callable,
        max_retries: Optional[int] = None,
        backoff_base: Optional[float] = None,
        retry_on_exceptions: Optional[List[Exception]] = None,
        args: Optional[List[Any]] = None,
        kwargs: Optional[Dict[str, Any]] = None
    ) -> Any:
        """执行带重试的操作"""
        max_retries = max_retries or self._default_max_retries
        backoff_base = backoff_base or self._default_backoff_base
        args = args or []
        kwargs = kwargs or {}
        
        record = RetryRecord(
            operation_id=operation_id,
            max_retries=max_retries,
            current_retry=0,
            status=RetryStatus.PENDING,
            last_error=None,
            start_time=datetime.now()
        )
        self._records[operation_id] = record
        
        for attempt in range(max_retries + 1):
            try:
                record.status = RetryStatus.RETRYING
                record.current_retry = attempt
                
                if attempt > 0:
                    # 指数退避等待
                    delay = backoff_base * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    app_logger.debug(f"[Retry] 第 {attempt} 次重试 {operation_id}，等待 {delay:.2f}s")
                
                # 执行操作
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                record.status = RetryStatus.SUCCESS
                record.end_time = datetime.now()
                app_logger.debug(f"[Retry] {operation_id} 成功，共重试 {attempt} 次")
                return result
                
            except Exception as e:
                record.last_error = str(e)
                
                # 检查是否需要重试
                if attempt >= max_retries:
                    record.status = RetryStatus.FAILED
                    record.end_time = datetime.now()
                    app_logger.error(f"[Retry] {operation_id} 失败，已达最大重试次数 {max_retries}")
                    raise
                
                # 检查是否在重试异常列表中
                if retry_on_exceptions and not isinstance(e, tuple(retry_on_exceptions)):
                    record.status = RetryStatus.FAILED
                    record.end_time = datetime.now()
                    app_logger.error(f"[Retry] {operation_id} 失败，异常类型不在重试列表中")
                    raise
                
                app_logger.warning(f"[Retry] {operation_id} 第 {attempt} 次尝试失败: {e}")
        
        raise RuntimeError("重试逻辑错误")
    
    def get_record(self, operation_id: str) -> Optional[RetryRecord]:
        """获取重试记录"""
        return self._records.get(operation_id)
    
    def get_all_records(self) -> List[RetryRecord]:
        """获取所有重试记录"""
        return list(self._records.values())
    
    def clean_old_records(self, hours: int = 24):
        """清理旧记录"""
        cutoff_time = datetime.now() - datetime.timedelta(hours=hours)
        self._records = {
            op_id: record for op_id, record in self._records.items()
            if record.start_time > cutoff_time
        }


class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, name: str, failure_threshold: int = 5, success_threshold: int = 3, reset_timeout: int = 60):
        self._name = name
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._reset_timeout = reset_timeout
    
    def _should_trip(self) -> bool:
        """判断是否应该熔断"""
        return self._failure_count >= self._failure_threshold
    
    def _should_reset(self) -> bool:
        """判断是否应该重置"""
        if self._last_failure_time is None:
            return False
        
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self._reset_timeout
    
    def _try_acquire(self) -> bool:
        """尝试获取熔断器许可"""
        if self._state == CircuitBreakerState.OPEN:
            if self._should_reset():
                self._state = CircuitBreakerState.HALF_OPEN
                self._success_count = 0
                app_logger.info(f"[CircuitBreaker] {self._name} 进入半开状态")
            else:
                app_logger.warning(f"[CircuitBreaker] {self._name} 已熔断，拒绝请求")
                return False
        
        return True
    
    def record_success(self):
        """记录成功"""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self._success_threshold:
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                app_logger.info(f"[CircuitBreaker] {self._name} 恢复正常状态")
        elif self._state == CircuitBreakerState.CLOSED:
            self._failure_count = 0
    
    def record_failure(self):
        """记录失败"""
        if self._state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            self._last_failure_time = datetime.now()
            app_logger.info(f"[CircuitBreaker] {self._name} 进入熔断状态")
        elif self._state == CircuitBreakerState.CLOSED:
            self._failure_count += 1
            if self._should_trip():
                self._state = CircuitBreakerState.OPEN
                self._last_failure_time = datetime.now()
                app_logger.info(f"[CircuitBreaker] {self._name} 触发熔断")
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """执行受保护的操作"""
        if not self._try_acquire():
            raise CircuitBreakerError(f"熔断器 {self._name} 已熔断")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
    
    def get_state(self) -> Dict[str, Any]:
        """获取熔断器状态"""
        return {
            "name": self._name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "failure_threshold": self._failure_threshold,
            "success_threshold": self._success_threshold,
            "reset_timeout": self._reset_timeout
        }


class CircuitBreakerError(Exception):
    """熔断器错误"""
    pass


class FallbackManager:
    """降级管理器"""
    
    def __init__(self):
        self._strategies: Dict[str, Tuple[FallbackStrategy, Any]] = {}
    
    def register_fallback(
        self,
        operation_id: str,
        strategy: FallbackStrategy,
        fallback_value: Optional[Any] = None,
        alternate_func: Optional[Callable] = None
    ):
        """注册降级策略"""
        self._strategies[operation_id] = (strategy, fallback_value, alternate_func)
        app_logger.info(f"[Fallback] 注册降级策略: {operation_id} -> {strategy.value}")
    
    async def execute_with_fallback(
        self,
        operation_id: str,
        func: Callable,
        *args, **kwargs
    ) -> Any:
        """执行带降级的操作"""
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            app_logger.warning(f"[Fallback] {operation_id} 执行失败，触发降级: {e}")
            
            if operation_id not in self._strategies:
                raise
            
            strategy, fallback_value, alternate_func = self._strategies[operation_id]
            
            if strategy == FallbackStrategy.RETURN_DEFAULT:
                return fallback_value
            elif strategy == FallbackStrategy.RETURN_CACHE:
                return self._get_cache_value(operation_id)
            elif strategy == FallbackStrategy.THROW_EXCEPTION:
                raise
            elif strategy == FallbackStrategy.CALL_ALTERNATE and alternate_func:
                if asyncio.iscoroutinefunction(alternate_func):
                    return await alternate_func(*args, **kwargs)
                else:
                    return alternate_func(*args, **kwargs)
            else:
                raise
    
    def _get_cache_value(self, operation_id: str) -> Any:
        """获取缓存值（简化实现）"""
        # 实际实现中可以连接到缓存系统
        return None


class FaultToleranceSystem:
    """容错系统"""
    
    def __init__(self):
        self._retry_manager = RetryManager()
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._fallback_manager = FallbackManager()
    
    def get_retry_manager(self) -> RetryManager:
        """获取重试管理器"""
        return self._retry_manager
    
    def get_fallback_manager(self) -> FallbackManager:
        """获取降级管理器"""
        return self._fallback_manager
    
    def get_or_create_circuit_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        reset_timeout: int = 60
    ) -> CircuitBreaker:
        """获取或创建熔断器"""
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                reset_timeout=reset_timeout
            )
        
        return self._circuit_breakers[name]
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """获取熔断器"""
        return self._circuit_breakers.get(name)
    
    def get_all_circuit_breakers(self) -> List[Dict[str, Any]]:
        """获取所有熔断器状态"""
        return [cb.get_state() for cb in self._circuit_breakers.values()]
    
    async def execute_protected(
        self,
        operation_id: str,
        func: Callable,
        retry_config: Optional[Dict[str, Any]] = None,
        circuit_breaker_name: Optional[str] = None,
        fallback_strategy: Optional[FallbackStrategy] = None,
        fallback_value: Optional[Any] = None,
        *args, **kwargs
    ) -> Any:
        """执行受保护的操作（组合重试、熔断、降级）"""
        # 包装函数：先应用熔断，再应用重试，最后应用降级
        async def wrapped_func():
            if circuit_breaker_name:
                cb = self.get_or_create_circuit_breaker(circuit_breaker_name)
                return await cb.execute(func, *args, **kwargs)
            else:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                else:
                    return func(*args, **kwargs)
        
        # 应用重试
        if retry_config:
            retry_result = await self._retry_manager.execute_with_retry(
                operation_id,
                wrapped_func,
                **retry_config
            )
        else:
            retry_result = await wrapped_func()
        
        # 应用降级（如果配置了）
        if fallback_strategy:
            self._fallback_manager.register_fallback(
                operation_id,
                fallback_strategy,
                fallback_value
            )
            return await self._fallback_manager.execute_with_fallback(
                operation_id,
                lambda: retry_result
            )
        
        return retry_result


# 全局容错系统实例
fault_tolerance_system = FaultToleranceSystem()


def get_fault_tolerance_system() -> FaultToleranceSystem:
    """获取容错系统实例"""
    return fault_tolerance_system


def retry_decorator(max_retries: int = 3, backoff_base: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            retry_manager = get_fault_tolerance_system().get_retry_manager()
            return await retry_manager.execute_with_retry(
                func.__name__,
                func,
                max_retries=max_retries,
                backoff_base=backoff_base,
                args=args,
                kwargs=kwargs
            )
        
        def sync_wrapper(*args, **kwargs):
            # 同步函数包装为异步执行
            import asyncio
            return asyncio.run(async_wrapper(*args, **kwargs))
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
