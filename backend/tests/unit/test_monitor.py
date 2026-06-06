"""单元测试 - 监控模块"""
import pytest
import asyncio
import time
from app.agents.monitor import AgentMonitor, monitor_timing


class TestAgentMonitor:
    def test_record_and_get_metric(self):
        mon = AgentMonitor()
        mon.record_metric("test.latency", 0.5, "s")
        assert "test.latency" in mon.metrics
        assert mon.metrics["test.latency"][-1].value == 0.5

    def test_start_and_finish_span(self):
        mon = AgentMonitor()
        span_id = mon.start_span("test_span")
        assert span_id in mon.active_spans
        mon.finish_span(span_id, {"result": "ok"})
        assert span_id not in mon.active_spans
        assert len(mon.span_history) == 1

    def test_get_all_metrics(self):
        mon = AgentMonitor()
        mon.record_metric("a", 1.0, "s")
        mon.record_metric("b", 2.0, "s")
        all_m = mon.get_all_metrics()
        assert "a" in all_m
        assert "b" in all_m

    def test_get_monitor_status(self):
        mon = AgentMonitor()
        mon.record_metric("x", 1.0, "s")
        status = mon.get_monitor_status()
        assert "metrics_count" in status
        assert status["metrics_count"] >= 1

    def test_get_metric_stats(self):
        mon = AgentMonitor()
        mon.record_metric("latency", 0.1, "s")
        mon.record_metric("latency", 0.3, "s")
        stats = mon.get_metric_stats("latency")
        assert stats["count"] == 2
        assert abs(stats["avg"] - 0.2) < 1e-9


class TestMonitorTimingDecorator:
    @pytest.mark.asyncio
    async def test_none_monitor_passthrough_async(self):
        @monitor_timing(monitor=None)
        async def my_func():
            return "hello"

        result = await my_func()
        assert result == "hello"

    def test_none_monitor_passthrough_sync(self):
        @monitor_timing(monitor=None)
        def my_func():
            return "world"

        result = my_func()
        assert result == "world"

    @pytest.mark.asyncio
    async def test_with_monitor_records_metric(self):
        mon = AgentMonitor()

        @monitor_timing(monitor=mon, name="test_op")
        async def my_func():
            return 99

        result = await my_func()
        assert result == 99
        assert "func.test_op" in mon.metrics

    def test_with_monitor_records_metric_sync(self):
        mon = AgentMonitor()

        @monitor_timing(monitor=mon, name="sync_op")
        def my_func():
            return "sync"

        result = my_func()
        assert result == "sync"
        assert "func.sync_op" in mon.metrics
