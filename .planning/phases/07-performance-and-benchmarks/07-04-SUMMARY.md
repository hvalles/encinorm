---
phase: 07-performance-and-benchmarks
plan: 04
subsystem: observability
tags: [memory, deque, maxlen, weakref, tracer, perf-04]

# Dependency graph
requires: []
provides:
  - "encino_orm/observability.py: QueryTracer._latencies acotado con deque(maxlen=latency_window), default 1024, guard latency_window >= 1"
  - "encino_orm/model/model.py: _FIELD_ADAPTERS/_COLUMN_MAPS como WeakKeyDictionary (no retienen clases de modelo)"
  - "tests/test_observability.py: ventana acotada + reset() conserva maxlen"
  - "tests/test_model.py: no-retención de clases tras perderlas (población/drop/gc)"
affects: [verify-phase-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Histograma de latencia acotado: deque(maxlen=latency_window); percentiles operan sobre la ventana móvil"
    - "Caches delegados de Model con WeakKeyDictionary para permitir liberar clases redefinidas (tests/reload/plugins)"

key-files:
  created: []
  modified:
    - encino_orm/observability.py
    - tests/test_observability.py
    - tests/test_model.py

key-decisions:
  - "El default de `latency_window` es 1024 (MAX_LATENCY_SAMPLES): suficiente para percentiles estables sin crecimiento ilimitado"
  - "`latency_window < 1` falla cerrado con ValueError (no se admite una ventana vacía)"
  - "`reset()` vacía estadísticas pero conserva el tamaño de la ventana (no la desmonta)"

patterns-established:
  - "Estructuras de observabilidad con memoria acotada + test de regresión de no-retención"

requirements-completed: [PERF-04]

# Metrics
duration: 8min
completed: 2026-09-19
---

# Phase 7: Performance & Benchmarks — Plan 04 Summary

**`QueryTracer._latencies` pasa a una ventana acotada (`deque(maxlen=latency_window)`) y los caches delegados de `Model` dejan de retener clases (WeakKeyDictionary), con tests de regresión de memoria.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-09-19
- **Tasks:** 2/2
- **Files modified:** 3

## Accomplishments

- `QueryTracer` acumula latencias sin crecimiento de memoria ilimitado: `_latencies` es un `deque(maxlen=latency_window)` (default `MAX_LATENCY_SAMPLES = 1024`); `latency_window < 1` lanza `ValueError`; `reset()` limpia estadísticas conservando la ventana.
- Los percentiles operan sobre la ventana móvil, así que la mediana/p95 siguen siendo significativas bajo carga sostenida.
- `_FIELD_ADAPTERS`/`_COLUMN_MAPS` usan `WeakKeyDictionary`, de modo que las clases de modelo redefinidas (tests, reload, plugins) pueden liberarse.
- Tests de regresión: ventana acotada + `reset()` conservando `maxlen` (`tests/test_observability.py`) y no-retención de clases tras perderlas (`tests/test_model.py`).

## Task Commits

1. **Task 1: Ventana de latencia acotada (deque maxlen) + tests** - `6cf670e` (perf)
2. **Task 2: Test de no-retención de clases en los caches weak de Model** - `6cf670e` (perf, mismo commit)

**Plan metadata:** `6cf670e` (perf: ventana de latencia acotada + test de no-retención)

_Nota: ambas tareas aterrizaron en un único commit atómico (`6cf670e`), que tocó `observability.py`, `tests/test_observability.py` y `tests/test_model.py`._

## Files Created/Modified

- `encino_orm/observability.py` — `_latencies: deque[float] = deque(maxlen=latency_window)`; guard `latency_window >= 1`.
- `tests/test_observability.py` — ventana acotada + `reset()` conserva `maxlen`.
- `tests/test_model.py` — `assert isinstance(..., WeakKeyDictionary)` + población/drop/gc (no retención).

## Decisions Made

- Ventana por defecto 1024; el valor se parametriza vía `latency_window` y falla cerrado si es `< 1`.
- `reset()` conserva el tamaño de la ventana (no la desmonta) para no perder la garantía de acotación.

## Deviations from Plan

- Ambas tareas del plan se commitearon juntas en `6cf670e` en lugar de dos commits separados. El resultado final es idéntico y el commit es atómico respecto al estado verde de la suite.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

- PERF-04 cerrado; verificado en `07-VERIFICATION.md` (truth 4) contra fuente: `observability.py:85` (`deque(maxlen=...)`) y `model.py:30` (`WeakKeyDictionary`).
- Sin bloqueos.

---
*Phase: 07-performance-and-benchmarks*
*Completed: 2026-09-19*
