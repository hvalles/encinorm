---
phase: 04-pool-correctness-concurrency
plan: 01
subsystem: database
tags: [asyncio, pool, concurrency, contextvars, dataclass, pytest]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "Red de seguridad de caracterización (`tests/test_pool_characterization.py`) y gates de CI (ruff/mypy/pytest)"
provides:
  - "Handle `PooledConnection` con driver, last_id, last_used, generation, checked_out y owner_task (POOL-01)"
  - "`acquire()` con reserva-antes-de-await que nunca supera `max_size` (POOL-02)"
  - "`release()` con ownership vía `_checked_out` y dedupe del doble release (POOL-02)"
  - "`_current_connection` guarda el handle; `resolve_db()` desenvaina `.driver`"
  - "`PoolDb.last_id()` fuera de transacción devuelve 0 (sin cache de id a nivel de pool)"
affects: [04-02, 04-03, 04-04, 04-05, 04-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Handle por conexión (@dataclass eq=False) para estado de pool hashable por identidad"
    - "Reserva de cupo antes del await + devolución en except BaseException"
    - "Ownership de conexión por conjunto `_checked_out` + contextvar con handle"

key-files:
  created: []
  modified:
    - encino_orm/pool.py
    - encino_orm/context.py
    - tests/test_pool.py
    - tests/test_pool_characterization.py
    - tests/test_d_recommendations.py

key-decisions:
  - "`PooledConnection` es `@dataclass(eq=False)` (no frozen) para conservar hash por identidad en los sets del pool"
  - "`_current_connection` guarda el handle; `resolve_db()` desenvaina `.driver` (Pitfall 8)"
  - "`last_id()` fuera de transacción devuelve 0 (Open Question 3)"
  - "`session()` NO fija `_current_connection`; ata el driver con `bind()` (Open Question 2)"

patterns-established:
  - "Pool handle: estado por conexión concentrado, sin cache compartido entre tareas"
  - "Admisión sin carrera: reserva de `_size` antes del await, devolución en fallo"
  - "release() idempotente por pertenencia a `_checked_out`"

requirements-completed: [POOL-01, POOL-02]

# Metrics
duration: 7min
completed: 2026-09-18
---

# Phase 4 Plan 01: Pool Correctness & Concurrency Summary

**Handle `PooledConnection` con estado por conexión, admisión del pool sin carrera (reserva-antes-de-await) y `release()` con ownership; `resolve_db()` desenvaina `.driver` y el cache de id a nivel de pool desaparece.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-18T23:10:16Z
- **Completed:** 2026-09-18T23:17:25Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `PooledConnection` concentra `driver`, `last_id`, `last_used`, `generation`, `checked_out` y `owner_task`; `PoolDb` ya no expone `_last_id` ni `_last_used`.
- `acquire()` reserva `_size` **antes** del `await` y devuelve el cupo en `except BaseException`; bajo barrera determinista `_size` pasa de 5 (baseline) a `<= max_size`.
- `release()` usa `_checked_out` como única fuente de propiedad: el doble `release()` no duplica la referencia en la cola y registra `logger.warning`.
- `_current_connection` guarda el handle y `resolve_db()` devuelve `conn.driver`, de modo que `Model`/`engine_of` siguen viendo un `Db` con `.dialect`.
- `last_id()` fuera de transacción devuelve `0`; se eliminó el bloque de `execute()` que escribía el cache compartido.

## Task Commits

Each task was committed atomically:

1. **Task 1: Handle `PooledConnection` y migración del estado por conexión** - `f9b9af7` (feat)
2. **Task 2: `acquire()` reserva-antes-de-await y `release()` con ownership (POOL-02)** - `2b5a364` (fix)
3. **Task 3: Migrar el scoping de `last_id` y documentar `session()`** - `d7a0886` (test)

**Plan metadata:** (commit final de docs de la fase)

## Files Created/Modified
- `encino_orm/pool.py` - `PooledConnection`, `acquire`/`release` con reserva y ownership, `_checkout`, `_as_handle`, contextvar con handles, `logger`.
- `encino_orm/context.py` - `resolve_db()` desenvaina `handle.driver`.
- `tests/test_pool.py` - tests del handle, `last_id()` scoping, `resolve_db()`, `session()`; migración a `handle.driver`.
- `tests/test_pool_characterization.py` - inversión de POOL-02 (overshoot y doble release), `last_id` sin cache, migración a handles, `EventBarrier.release()`.
- `tests/test_d_recommendations.py` - D3: insert standalone sin id a nivel de pool.

## RED / GREEN Evidence (POOL-02)

`uv run pytest tests/test_pool_characterization.py -k "overshoot or double_release" -q`

- **RED** (antes del fix de `acquire()`): `assert 5 <= 2` en el test de overshoot (`_size == 5`) y `assert 2 == 1` en el doble release (cola con dos referencias).
- **GREEN** (después): `2 passed, 19 deselected` — `_size == 2 <= max_size`, cola con una sola referencia y 3 tareas agotando su `timeout`.

## Decisions Made
- `@dataclass(eq=False)`: los handles deben ser hashables por identidad para vivir en `_connections`/`_checked_out`; un dataclass con `eq=True` sería unhashable.
- `needs_check = self._idle_timeout is None or handle.is_idle_for(self._idle_timeout)`: preserva la semántica de `_needs_check` (con `idle_timeout=None` siempre se comprueba liveness) sin reintroducir el estado por conexión en el pool.
- Open Question 2: `session()` no fija `_current_connection` (evita un cambio observable no confirmado).
- Open Question 3: `last_id()` fuera de transacción → `0`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] El test de overshoot arreglado colgaba con `parties=5`**
- **Found during:** Task 2 (POOL-02)
- **Issue:** El plan pedía conservar `EventBarrier(parties=5)` con 5 tareas que solo hacen `acquire()` sin liberar. Con la reserva-antes-de-await solo `max_size=2` tareas alcanzan `connect()`, así que la barrera nunca llega a 5 y las 2 tareas quedan bloqueadas para siempre (las otras 3 esperan en la cola).
- **Fix:** Se mantiene `parties=5` y las 5 tareas, pero se libera la barrera explícitamente (`EventBarrier.release()`, añadido) y las tareas usan `acquire(timeout=0.5)`; se asserta además que 3 tareas agotan el timeout. Reproduce RED (`_size == 5`) y GREEN (`_size == 2`) sin colgarse.
- **Files modified:** `tests/test_pool_characterization.py`
- **Verification:** RED/GREEN arriba.
- **Committed in:** `2b5a364` (Task 2)

**2. [Rule 1 - Bug] `is_idle_for(None)` invertía la comprobación de liveness**
- **Found during:** Task 1
- **Issue:** El plan especifica `handle.is_idle_for(None) == False`, pero `_needs_check` original devolvía `True` cuando `idle_timeout is None` (siempre comprobar liveness). Usar `not handle.is_idle_for(None)` devolvía conexiones caídas, rompiendo `test_acquire_replaces_dead_connection`.
- **Fix:** `needs_check = self._idle_timeout is None or handle.is_idle_for(self._idle_timeout)` en la rama `else` de `acquire`.
- **Files modified:** `encino_orm/pool.py`
- **Verification:** `tests/test_pool.py` verde.
- **Committed in:** `f9b9af7` (Task 1)

**3. [Rule 3 - Ordering] Migración de `TestPoolLastIdScoping` en Task 1 en vez de Task 3**
- **Found during:** Task 1
- **Issue:** Eliminar `_last_id` del pool rompe inmediatamente las lecturas de `_last_id` en `tests/test_pool_characterization.py`. La verify de Task 2 exige ese fichero verde completo, mientras que el plan asigna la reescritura a Task 3.
- **Fix:** La migración semántica de `TestPoolLastIdScoping` se adelantó al commit de Task 1; Task 3 cubrió el resto (test de `session()`, D3 y docstrings). Sin cambio de alcance, solo de orden.
- **Files modified:** `tests/test_pool_characterization.py`, `tests/test_pool.py`, `tests/test_d_recommendations.py`
- **Verification:** Todas las verify por tarea verdes.
- **Committed in:** `f9b9af7` / `d7a0886`

---

**Total deviations:** 3 auto-fixed (1 Rule 1, 2 Rule 3)
**Impact on plan:** Necesarias para que las verify no cuelguen y para preservar la semántica de liveness. Sin scope creep: `reset_on_release` (04-03), reaper/generación/`close()` idempotente (04-04) y `execute_insert`/deprecación (04-02) quedan intactos.

## Issues Encountered
- `grep -c "_last_used" tests/test_pool_characterization.py` devuelve `1` porque el NOMBRE del test preservado (`test_release_records_last_used_and_requeues`, exigido por el plan) contiene el substring. No queda ningún acceso `p._last_used` (`grep -c "p\._last_used"` == 0). La aserción se migró a `handle.last_used`.
- `PoolDb.close()` sigue cerrando las conexiones retenidas (caracterización `test_close_closes_held_connection` intacta, `held.driver.closed is True`); su corrección es POOL-06 en 04-04.

## Threat Flags

Ninguna superficie nueva. Se preservó `PoolExhaustedError` con el mensaje actual (solo `timeout` y `max_size`, sin `conn_kwargs`). T-04-01-05 (`close()` sobre un handle en uso) permanece `accept` temporal hasta 04-04.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Base de la fase lista: 04-02 puede enganchar `execute_insert`/`last_id` por conexión al `handle.last_id`, y 04-03/04-04 al `release()`/`close()`/`_checked_out`.
- Gates verdes: `uv run pytest -q` (857 passed), `uv run ruff check encino_orm tests`, `uv run ruff format --check encino_orm tests`, `uv run mypy encino_orm`.

## Self-Check: PASSED

- FOUND: `encino_orm/pool.py` (`class PooledConnection`, `_checked_out`, `except BaseException`)
- FOUND: `encino_orm/context.py` (`.driver` en `resolve_db`)
- FOUND: commits `f9b9af7`, `2b5a364`, `d7a0886`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-01-SUMMARY.md`
