"""Observabilidad: `trace_id` por request, tracer de consultas (opt-in) y
puente opcional a OpenTelemetry."""

import contextvars
import logging
from contextlib import contextmanager

_trace_id_var = contextvars.ContextVar("encinorm_trace_id", default=None)


@contextmanager
def trace_id(value):
    """Establece el `trace_id` para el bloque/corutina (visible en los logs)."""
    token = _trace_id_var.set(value)
    try:
        yield
    finally:
        _trace_id_var.reset(token)


def current_trace_id():
    """Devuelve el `trace_id` activo, o `None`."""
    return _trace_id_var.get()


def _percentile(samples, p):
    """Percentil `p` (0..1) por interpolación lineal sobre muestras ordenadas."""
    if not samples:
        return None
    s = sorted(samples)
    idx = (len(s) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _latency_summary(samples):
    if not samples:
        return {"count": 0}
    return {
        "count": len(samples),
        "min": min(samples),
        "max": max(samples),
        "avg": sum(samples) / len(samples),
        "p50": _percentile(samples, 0.50),
        "p90": _percentile(samples, 0.90),
        "p99": _percentile(samples, 0.99),
    }


class QueryTracer:
    """Registra consultas con timing, params y `trace_id`; opcionalmente métricas
    y un histograma de latencia (percentiles).

    Uso:

    ```python
    tracer = QueryTracer(collect_metrics=True)
    tracer.record("sqlite", "fetch_all", sql, params, 0.012)
    print(tracer.stats)          # {"queries": 1, "errors": 0, "rows": 0}
    print(tracer.latency_stats)  # {"count": 1, "min": ..., "p50": ...}
    ```
    """

    def __init__(self, logger=None, *, level=logging.DEBUG, collect_metrics=True):
        self.logger = logger or logging.getLogger("encinorm")
        self.level = level
        self.collect_metrics = collect_metrics
        self._counters = {"queries": 0, "errors": 0, "rows": 0}
        self._latencies = []

    def record(self, engine, method, sql, params, elapsed, error=None, rows=None):
        if self.collect_metrics:
            self._counters["queries"] += 1
            if error is not None:
                self._counters["errors"] += 1
            if rows is not None:
                self._counters["rows"] += rows
            if elapsed is not None:
                self._latencies.append(float(elapsed))
        extra = f" error={error!r}" if error is not None else ""
        self.logger.log(
            self.level,
            "%s %s (%.4fs) trace_id=%r sql=%r params=%r%s",
            engine, method, elapsed, current_trace_id(), sql, params, extra,
        )

    @property
    def stats(self) -> dict:
        return dict(self._counters)

    @property
    def latency_stats(self) -> dict:
        """Resumen de latencia (percentiles) de las consultas registradas."""
        return _latency_summary(self._latencies)

    def reset(self):
        self._counters.update({"queries": 0, "errors": 0, "rows": 0})
        self._latencies.clear()


class OtelQueryTracer:
    """Puente opcional a OpenTelemetry: registra cada consulta como un span.

    Requiere `opentelemetry-api` (no es dependencia de encinorm). El
    `TracerProvider` (SDK/exportador) lo configura la aplicación; encinorm solo
    crea los spans.

    Uso:

    ```python
    tracer = OtelQueryTracer(tracer_name="encinorm")
    tracer.record("sqlite", "fetch_all", sql, params, 0.012, rows=10)
    ```
    """

    def __init__(self, tracer_name: str = "encinorm", collect_metrics=True):
        self._name = tracer_name
        self.collect_metrics = collect_metrics
        self._tracer = None

    def _ensure_tracer(self):
        if self._tracer is None:
            try:
                from opentelemetry import trace as otel_trace
            except ImportError as exc:  # pragma: no cover - depende del entorno
                raise ImportError(
                    "opentelemetry-api no está instalado; agrégalo para usar "
                    "OtelQueryTracer"
                ) from exc
            self._tracer = otel_trace.get_tracer(self._name)
        return self._tracer

    def record(self, engine, method, sql, params, elapsed, error=None, rows=None):
        tracer = self._ensure_tracer()
        from opentelemetry import trace as otel_trace

        with tracer.start_as_current_span(f"{engine}.{method}") as span:
            span.set_attribute("db.system", engine)
            span.set_attribute("db.operation", method)
            span.set_attribute("db.statement", sql)
            if elapsed is not None:
                span.set_attribute("db.elapsed_ms", elapsed * 1000)
            if rows is not None:
                span.set_attribute("db.rows", rows)
            if error is not None:
                span.record_exception(error)
                span.set_status(otel_trace.Status(otel_trace.StatusCode.ERROR))
