"""Observabilidad: `trace_id` por request y tracer de consultas (opt-in)."""

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


class QueryTracer:
    """Registra consultas con timing, params y `trace_id`; opcionalmente métricas.

    Uso:

    ```python
    tracer = QueryTracer(collect_metrics=True)
    tracer.record("sqlite", "fetch_all", sql, params, 0.012)
    print(tracer.stats)   # {"queries": 1, "errors": 0, "rows": 0}
    ```
    """

    def __init__(self, logger=None, *, level=logging.DEBUG, collect_metrics=True):
        self.logger = logger or logging.getLogger("encinorm")
        self.level = level
        self.collect_metrics = collect_metrics
        self._counters = {"queries": 0, "errors": 0, "rows": 0}

    def record(self, engine, method, sql, params, elapsed, error=None, rows=None):
        if self.collect_metrics:
            self._counters["queries"] += 1
            if error is not None:
                self._counters["errors"] += 1
            if rows is not None:
                self._counters["rows"] += rows
        extra = f" error={error!r}" if error is not None else ""
        self.logger.log(
            self.level,
            "%s %s (%.4fs) trace_id=%r sql=%r params=%r%s",
            engine, method, elapsed, current_trace_id(), sql, params, extra,
        )

    @property
    def stats(self) -> dict:
        return dict(self._counters)

    def reset(self):
        self._counters.update({"queries": 0, "errors": 0, "rows": 0})
