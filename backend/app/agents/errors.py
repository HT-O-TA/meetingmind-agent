"""错误分类与恢复策略系统
"""
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
from enum import Enum
from dataclasses import dataclass
from functools import wraps


class ErrorSeverity(Enum):
    """错误严重程度"""
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4
    FATAL = 5


class ErrorCategory(Enum):
    """错误分类"""
    LLM_ERROR = "llm"
    TOOL_ERROR = "tool"
    RETRIEVAL_ERROR = "retrieval"
    PARSE_ERROR = "parse"
    VALIDATION_ERROR = "validation"
    DATABASE_ERROR = "database"
    NETWORK_ERROR = "network"
    TIMEOUT_ERROR = "timeout"
    MEMORY_ERROR = "memory"
    UNKNOWN_ERROR = "unknown"


@dataclass
class ErrorInfo:
    """错误信息"""
    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    original_exception: Optional[Exception] = None
    timestamp: float = 0
    context: Dict[str, Any] = None
    retry_count: int = 0
    max_retries: int = 3
    
    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()
        if self.context is None:
            self.context = {}


@dataclass
class RecoveryStrategy:
    """恢复策略"""
    name: str
    description: str
    max_retries: int = 3
    retry_delay: float = 1.0  # 秒
    exponential_backoff: bool = True
    fallback_action: Optional[Callable] = None


class ErrorRecoveryManager:
    """错误恢复管理器"""
    
    def __init__(self):
        self.strategies: Dict[ErrorCategory, RecoveryStrategy] = self._init_default_strategies()
        self.error_history: List[ErrorInfo] = []
        self.max_history_size = 1000
        
    def _init_default_strategies(self) -> Dict[ErrorCategory, RecoveryStrategy]:
        """初始化默认恢复策略"""
        return {
            ErrorCategory.LLM_ERROR: RecoveryStrategy(
                name="llm_recovery",
                description="LLM 错误恢复策略",
                max_retries=3,
                retry_delay=2.0,
                exponential_backoff=True
            ),
            ErrorCategory.TOOL_ERROR: RecoveryStrategy(
                name="tool_recovery",
                description="工具错误恢复策略",
                max_retries=2,
                retry_delay=1.0,
                exponential_backoff=True
            ),
            ErrorCategory.RETRIEVAL_ERROR: RecoveryStrategy(
                name="retrieval_recovery",
                description="检索错误恢复策略",
                max_retries=3,
                retry_delay=0.5,
                exponential_backoff=True
            ),
            ErrorCategory.TIMEOUT_ERROR: RecoveryStrategy(
                name="timeout_recovery",
                description="超时恢复策略",
                max_retries=2,
                retry_delay=0.5,
                exponential_backoff=True
            ),
            ErrorCategory.NETWORK_ERROR: RecoveryStrategy(
                name="network_recovery",
                description="网络错误恢复策略",
                max_retries=3,
                retry_delay=3.0,
                exponential_backoff=True
            ),
            ErrorCategory.PARSE_ERROR: RecoveryStrategy(
                name="parse_recovery",
                description="解析错误恢复策略",
                max_retries=2,
                retry_delay=0.5,
                exponential_backoff=False
            ),
            ErrorCategory.VALIDATION_ERROR: RecoveryStrategy(
                name="validation_recovery",
                description="验证错误恢复策略",
                max_retries=1,
                retry_delay=0,
                exponential_backoff=False
            ),
            ErrorCategory.DATABASE_ERROR: RecoveryStrategy(
                name="database_recovery",
                description="数据库错误恢复策略",
                max_retries=3,
                retry_delay=1.0,
                exponential_backoff=True
            ),
            ErrorCategory.UNKNOWN_ERROR: RecoveryStrategy(
                name="unknown_recovery",
                description="未知错误恢复策略",
                max_retries=1,
                retry_delay=0.5,
                exponential_backoff=False
            )
        }
    
    def classify_error(self, exception: Exception) -> Tuple[ErrorCategory, ErrorSeverity]:
        """根据异常类型分类错误
        
        Args:
            exception: 异常对象
            
        Returns:
            (错误分类, 严重程度)
        """
        from sqlalchemy.exc import SQLAlchemyError, OperationalError

        # aiohttp 不是核心运行依赖。仅在已安装时识别其网络异常，避免
        # 错误处理器在处理原始异常时再次因可选依赖缺失而失败。
        try:
            from aiohttp import ClientError
            network_errors = (ClientError, ConnectionError)
        except ImportError:
            network_errors = (ConnectionError,)

        exc_type = type(exception).__name__

        if "Timeout" in exc_type or isinstance(exception, asyncio.TimeoutError):
            return ErrorCategory.TIMEOUT_ERROR, ErrorSeverity.WARNING
        
        if isinstance(exception, network_errors):
            return ErrorCategory.NETWORK_ERROR, ErrorSeverity.ERROR
        
        if isinstance(exception, (SQLAlchemyError, OperationalError)):
            return ErrorCategory.DATABASE_ERROR, ErrorSeverity.ERROR
        
        if "parse" in exc_type.lower() or "json" in str(exception).lower():
            return ErrorCategory.PARSE_ERROR, ErrorSeverity.WARNING
        
        if "validate" in exc_type.lower() or "validation" in str(exception).lower():
            return ErrorCategory.VALIDATION_ERROR, ErrorSeverity.WARNING
        
        if "llm" in str(exception).lower() or "openai" in str(exception).lower():
            return ErrorCategory.LLM_ERROR, ErrorSeverity.ERROR
        
        if "retrieval" in str(exception).lower() or "embedding" in str(exception).lower():
            return ErrorCategory.RETRIEVAL_ERROR, ErrorSeverity.ERROR
        
        return ErrorCategory.UNKNOWN_ERROR, ErrorSeverity.ERROR
    
    def handle_error(
        self, 
        exception: Exception, 
        context: Optional[Dict[str, Any]] = None
    ) -> ErrorInfo:
        """处理并记录错误
        
        Args:
            exception: 异常对象
            context: 错误上下文
            
        Returns:
            错误信息对象
        """
        category, severity = self.classify_error(exception)
        
        error_info = ErrorInfo(
            category=category,
            severity=severity,
            message=str(exception),
            original_exception=exception,
            context=context or {},
            timestamp=time.time()
        )
        
        self.error_history.append(error_info)
        
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
        
        return error_info
    
    async def execute_with_recovery(
        self,
        func: Callable,
        exception: Optional[Exception] = None,
        *args,
        **kwargs
    ) -> Any:
        """执行函数，失败时自动重试

        Args:
            func: 要执行的函数
            exception: 触发恢复的原始异常（None 表示首次执行）
            *args, **kwargs: 传递给 func 的参数

        Returns:
            函数执行结果
        """
        error_info = self.handle_error(exception, kwargs) if exception else None

        if error_info is None:
            return await func(*args, **kwargs)

        strategy = self.strategies.get(error_info.category, self.strategies[ErrorCategory.UNKNOWN_ERROR])

        error_info.retry_count += 1

        if error_info.retry_count > strategy.max_retries:
            raise exception

        delay = strategy.retry_delay
        if strategy.exponential_backoff:
            delay = delay * (2 ** (error_info.retry_count - 1))

        await asyncio.sleep(delay)

        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if error_info.retry_count >= strategy.max_retries:
                raise
            error_info_next = self.handle_error(e, kwargs)
            error_info_next.retry_count = error_info.retry_count
            return await self.execute_with_recovery(func, e, *args, **kwargs)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """获取错误统计信息
        
        Returns:
            统计信息字典
        """
        category_counts = {cat.value: 0 for cat in ErrorCategory}
        severity_counts = {sev.value: 0 for sev in ErrorSeverity}
        recent_errors = []
        
        for err in self.error_history[-100:]:
            category_counts[err.category.value] += 1
            severity_counts[err.severity.value] += 1
            recent_errors.append({
                "category": err.category.value,
                "severity": err.severity.value,
                "message": err.message[:100],
                "timestamp": err.timestamp
            })
        
        return {
            "total_errors": len(self.error_history),
            "category_counts": category_counts,
            "severity_counts": severity_counts,
            "recent_errors": recent_errors[-20:]
        }
    
    def get_recent_errors(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的错误
        
        Args:
            limit: 返回数量限制
            
        Returns:
            错误列表
        """
        return [
            {
                "category": err.category.value,
                "severity": err.severity.value,
                "message": err.message,
                "timestamp": err.timestamp,
                "retry_count": err.retry_count
            }
            for err in self.error_history[-limit:]
        ]
    
    def clear_history(self):
        """清空错误历史"""
        self.error_history = []


def with_error_recovery(recovery_manager: ErrorRecoveryManager):
    """装饰器 - 自动错误恢复

    Args:
        recovery_manager: 错误恢复管理器

    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return await recovery_manager.execute_with_recovery(
                    func, e, *args, **kwargs
                )
        return wrapper
    return decorator
