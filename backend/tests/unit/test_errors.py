"""单元测试 - 错误恢复模块"""
import pytest
import asyncio
from app.agents.errors import (
    ErrorRecoveryManager, ErrorCategory, ErrorSeverity,
    with_error_recovery
)


class TestErrorRecoveryManager:
    def test_handle_error_classifies_llm(self):
        mgr = ErrorRecoveryManager()
        exc = Exception("LLM API rate limit exceeded")
        info = mgr.handle_error(exc, {})
        assert info.category == ErrorCategory.LLM_ERROR

    def test_handle_error_classifies_timeout(self):
        mgr = ErrorRecoveryManager()
        exc = asyncio.TimeoutError()
        info = mgr.handle_error(exc, {})
        assert info.category == ErrorCategory.TIMEOUT_ERROR

    def test_handle_error_classifies_unknown(self):
        mgr = ErrorRecoveryManager()
        exc = Exception("some random error")
        info = mgr.handle_error(exc, {})
        assert info.category == ErrorCategory.UNKNOWN_ERROR

    def test_error_history_grows(self):
        mgr = ErrorRecoveryManager()
        for i in range(5):
            mgr.handle_error(Exception(f"error {i}"), {})
        assert len(mgr.error_history) == 5

    def test_get_error_stats(self):
        mgr = ErrorRecoveryManager()
        mgr.handle_error(Exception("llm error"), {})
        stats = mgr.get_error_stats()
        assert "total_errors" in stats
        assert stats["total_errors"] == 1

    def test_get_recent_errors(self):
        mgr = ErrorRecoveryManager()
        for i in range(5):
            mgr.handle_error(Exception(f"e{i}"), {})
        recent = mgr.get_recent_errors(3)
        assert len(recent) == 3

    @pytest.mark.asyncio
    async def test_execute_with_recovery_no_exception(self):
        mgr = ErrorRecoveryManager()

        async def success():
            return "ok"

        result = await mgr.execute_with_recovery(success)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_execute_with_recovery_retries_on_exception(self):
        mgr = ErrorRecoveryManager()
        # Use zero delay to keep the test fast
        for strategy in mgr.strategies.values():
            strategy.retry_delay = 0
            strategy.max_retries = 1
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("llm persistent error")

        with pytest.raises(Exception, match="llm persistent error"):
            await mgr.execute_with_recovery(
                always_fail,
                Exception("llm persistent error")
            )


class TestWithErrorRecoveryDecorator:
    @pytest.mark.asyncio
    async def test_decorator_passes_through_on_success(self):
        mgr = ErrorRecoveryManager()

        @with_error_recovery(mgr)
        async def success_func():
            return 42

        result = await success_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_decorator_triggers_recovery_on_failure(self):
        mgr = ErrorRecoveryManager()
        # Use zero delay to keep the test fast
        for strategy in mgr.strategies.values():
            strategy.retry_delay = 0
        call_count = 0

        @with_error_recovery(mgr)
        async def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("llm transient error")
            return "recovered"

        result = await fail_once()
        assert result == "recovered"
        assert call_count == 2
