import pytest

from encinorm.observability import (
    OtelQueryTracer,
    QueryTracer,
    current_trace_id,
    trace_id,
)


class TestTraceId:
    def test_default_none(self):
        assert current_trace_id() is None

    def test_context_manager(self):
        with trace_id("req-123"):
            assert current_trace_id() == "req-123"
        assert current_trace_id() is None


class TestQueryTracer:
    def test_record_and_stats(self):
        t = QueryTracer(collect_metrics=True)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        t.record("sqlite", "fetch_all", "SELECT 2", [], 0.02, error=ValueError("x"))
        assert t.stats == {"queries": 2, "errors": 1, "rows": 0}

    def test_rows_metric(self):
        t = QueryTracer(collect_metrics=True)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01, rows=5)
        assert t.stats["rows"] == 5

    def test_no_metrics(self):
        t = QueryTracer(collect_metrics=False)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        assert t.stats == {"queries": 0, "errors": 0, "rows": 0}

    def test_reset(self):
        t = QueryTracer(collect_metrics=True)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        t.reset()
        assert t.stats == {"queries": 0, "errors": 0, "rows": 0}


class TestLatencyHistogram:
    def test_latency_stats(self):
        t = QueryTracer(collect_metrics=True)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        t.record("sqlite", "fetch_all", "SELECT 2", [], 0.03)
        t.record("sqlite", "fetch_all", "SELECT 3", [], 0.02)
        s = t.latency_stats
        assert s["count"] == 3
        assert s["min"] == 0.01
        assert s["max"] == 0.03
        assert abs(s["avg"] - 0.02) < 1e-9
        assert s["p50"] == 0.02

    def test_latency_stats_empty(self):
        t = QueryTracer(collect_metrics=True)
        assert t.latency_stats == {"count": 0}

    def test_latency_reset(self):
        t = QueryTracer(collect_metrics=True)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        t.reset()
        assert t.latency_stats == {"count": 0}

    def test_latency_disabled_when_no_metrics(self):
        t = QueryTracer(collect_metrics=False)
        t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
        assert t.latency_stats == {"count": 0}


class TestOtelQueryTracer:
    def test_requires_opentelemetry(self):
        t = OtelQueryTracer()
        with pytest.raises(ImportError):
            t.record("sqlite", "fetch_all", "SELECT 1", [], 0.01)
