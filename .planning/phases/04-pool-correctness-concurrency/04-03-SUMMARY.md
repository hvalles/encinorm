---
phase: 04-pool-correctness-concurrency
plan: 03
subsystem: database
tags: [asyncio, pool, concurrency, transaction, commit, rollback, deprecation, warnings, pytest]

# Dependency graph
requires:
  - phase: 04-pool-correctness-concurrency
    provides: "Handle `PooledConnection`, admisión sin carrera y `release()` con ownership (04-01); `execute_insert` y `last_id()` deprecado (04-02)"
provides:
  - "`PoolDb.execute`/`PoolDb._run` cierran la transacción EXPLÍCITAMENTE (commit en éxito, rollback en error) antes de liberar (POOL-04)"
  - "Política `reset_on_release` kw-only en `PoolDb.__init__`: `\"rollback\"` (default) revierte el sobrante; `\"commit\"` lo confirma y está DEPRECADO"
  - "`DeprecationWarning` enganchado a la POLÍTICA `\"commit\"` (constructor), NO a `in_transaction()` (resuelve A1/Pitfall 4)"
  - "Validación fail-closed: `reset_on_release` fuera de `{\"rollback\", \"commit\"}` → `ValueError` (no se expone `\"none\"`, A2)"
  - "Caracterización POOL-04 invertida con evidencia RED/GREEN"
affects: [04-04, 04-06, 08-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Template `try/except BaseException/else/finally` para cerrar la transacción antes de liberar (Correction #5)"
    - "Política de liberación configurable en el constructor con warning de deprecación determinista (`pytest.warns`)"
    - "Warning de deprecación enganchado a la POLÍTICA, no a `in_transaction()` (MSSQL/Oracle marcan `_in_tx=True` tras un SELECT)"

key-files:
  created: []
  modified:
    - encino_orm/pool.py
    - tests/test_pool.py
    - tests/test_pool_characterization.py
    - docs/guide.md
    - CHANGELOG.md

key-decisions:
  - "El orden safety-critical de Correction #5 se respeta: commit/rollback explícito en `execute`/`_run` (Task 1) ANTES de invertir `release()` a rollback-por-defecto (Task 2)"
  - "El warning se engancha a la POLÍTICA `reset_on_release=\"commit\"` en el constructor, no a la mera presencia de `in_transaction()` (MSSQL/Oracle marcan `_in_tx=True` tras un SELECT; engancharlo a `in_transaction()` rompería `filterwarnings=[\"error\"]`)"
  - "`reset_on_release` es keyword-only para no colisionar con `**conn_kwargs` del driver"
  - "Se usa `except BaseException` (no `Exception`) para que una cancelación tampoco deje la transacción abierta; se re-lanza siempre el error raíz"
  - "No se expone `\"none\"` (fail-closed): es el comportamiento accidental que la fase elimina (A2)"

patterns-established:
  - "Cierre explícito de la transacción en el wrapper del pool antes de `release()`; `release()` solo trata el sobrante del llamador"
  - "Deprecación de política de configuración: warning en el constructor + valor default silencioso + `ValueError` para valores desconocidos"

requirements-completed: [POOL-04]

# Metrics
duration: 3min
completed: 2026-09-19
---

# Phase 4 Plan 03: Semántica de liberación del pool (`reset_on_release`) Summary

**`PoolDb.execute`/`_run` cierran la transacción explícitamente (commit en éxito, rollback en error) antes de liberar, y `release()` aplica `reset_on_release` (rollback por defecto; `"commit"` deprecado con `DeprecationWarning`), con la caracterización POOL-04 invertida y las regresiones de autocommit intactas.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-09-19T03:01:45Z
- **Completed:** 2026-09-19T03:04:30Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `execute`/`_run` cierran la transacción explícitamente con `try/except BaseException/else/finally`: commit en éxito, rollback en error (con re-lanzado del error raíz), `release()` en `finally`. Ya no queda una transacción abierta cuando la operación lanza ni ante `CancelledError`.
- `PoolDb.__init__` acepta `reset_on_release` kw-only ∈ `{"rollback" (default), "commit"}`; `release()` revierte (o confirma, si se opta por el comportamiento deprecado) el sobrante DESPUÉS del cierre explícito.
- `reset_on_release="commit"` emite `DeprecationWarning` en el constructor; el default `"rollback"` es silencioso. Un valor desconocido lanza `ValueError` (no se expone `"none"`).
- Caracterización POOL-04 invertida: `test_release_does_not_commit_or_rollback` → `test_release_rolls_back_leftover_transaction`, con evidencia RED/GREEN.
- `TestPoolAutocommit` y `TestPoolStandaloneCommit` permanecen SIN editar y verdes: un `pool.execute(INSERT)` standalone sigue siendo visible entre conexiones.

## Task Commits

Each task was committed atomically:

1. **Task 1: Commit/rollback explícito en `execute`/`_run` (PASO i)** - `722ee84` (feat)
2. **Task 2: Política `reset_on_release` + `DeprecationWarning` + inversión de la caracterización** - `47124f8` (feat)
3. **Task 3: Documentar la semántica de liberación y cerrar los gates** - `79a60c1` (docs)

**Plan metadata:** (commit final de docs del plan)

## Files Created/Modified
- `encino_orm/pool.py` - `import warnings`; `reset_on_release` kw-only con validación y warning; `release()` aplica la política al sobrante; `_run`/`execute` reescritos con el template explícito.
- `tests/test_pool.py` - `TestPoolStandaloneRollback` (rollback en error con/sin transacción abierta) y `TestPoolResetOnRelease` (política commit con `pytest.warns`, valor inválido, SELECT sin warning); `import warnings`.
- `tests/test_pool_characterization.py` - inversión de POOL-04 en `TestPoolReleaseSemantics`; docstring de estado actualizado a 04-03.
- `docs/guide.md` - nueva subsección "Pool de conexiones (`PoolDb`)" con la semántica de liberación y la política deprecada.
- `CHANGELOG.md` - entrada de CAMBIO DE COMPORTAMIENTO en la sección `[Unreleased] ### Corregido` existente (sin duplicar encabezado).

## RED / GREEN Evidence (inversión de POOL-04)

- **RED:** con `encino_orm/pool.py` en el estado de la Task 1 (sin política en `release()`), `tests/test_pool_characterization.py::TestPoolReleaseSemantics::test_release_rolls_back_leftover_transaction` FALLA con `AssertionError: assert ('rollback', None) in []` (la conexión no registró ninguna llamada al liberar). Ejecutado con `uv run pytest ... -k release_rolls_back_leftover -q`.
- **GREEN:** con la política aplicada en `release()` (Task 2), el mismo test PASA (`1 passed`). Evidencia capturada restaurando `pool.py` desde una copia temporal (sin tocar el índice git).
- **Resolución de A1:** el `DeprecationWarning` se engancha a `reset_on_release="commit"` (constructor), no a `in_transaction()`. `test_select_leftover_does_not_warn` libera una conexión con `_in_tx=True` y el default `"rollback"` y verifica que NO se emite `DeprecationWarning` (bajo `filterwarnings=["error"]` y con `warnings.catch_warnings(record=True)`).

## Verification Gates

- `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` → **60 passed**
- `uv run pytest tests/test_pool.py -k "autocommit or standalone" -q` → **7 passed** (regresión POOL-04 sin editar)
- `uv run pytest tests/test_pool.py -k "reset_on_release or autocommit or standalone" -q` → **9 passed**
- `uv run pytest -q -m "not integration and not optional_engine"` → **801 passed, 85 deselected**
- `uv run ruff check encino_orm tests` → **All checks passed!**
- `uv run ruff format --check encino_orm tests` → **116 files already formatted**
- `uv run mypy encino_orm` → **Success: no issues found in 60 source files**
- `grep -rn "noqa" encino_orm/` → vacío (0)
- `grep -c "reset_on_release" encino_orm/pool.py` → 7 (>= 3); `grep -c "except BaseException"` → 3
- `grep -c "reset_on_release" docs/guide.md` → 3; `grep -ci "revierte\|rollback" docs/guide.md` → 5
- `sed -n '/## \[Unreleased\]/,/## \[0.2.6\]/p' CHANGELOG.md | grep -c "reset_on_release"` → 1; `grep -c "### Corregido"` → 1
- `filterwarnings = ["error"]` intacto en `pyproject.toml`
- **No ejecutado (instrucción del ejecutor):** `pytest -m integration`. El ratchet de mypy de `encino_orm.pool` NO se retira (ownership de 04-04).

## Decisions Made
- Orden obligatorio (Correction #5): primero el cierre explícito en `execute`/`_run`, después la política en `release()`. `TestPoolAutocommit`/`TestPoolStandaloneCommit` son la red de seguridad y no se editaron.
- El warning de deprecación vive en el constructor (determinista y testeable con `pytest.warns`); nunca se dispara por un `in_transaction()` verdadero tras una lectura en MSSQL/Oracle.
- `reset_on_release` es keyword-only: evita una posible colisión con `**conn_kwargs` del driver y deja claro que es política del pool.
- La validación fail-closed se coloca al inicio de `__init__`, antes de resolver el motor.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `pytest.warns(DeprecationWarning)` sin `match` rompía `ruff check` (PT030)**
- **Found during:** Task 2
- **Issue:** `uv run ruff check encino_orm tests` falló con 1 hallazgo `PT030` ("`pytest.warns(DeprecationWarning)` is too broad, set the `match` parameter") en el test de la política `"commit"`.
- **Fix:** Se añadió `match="reset_on_release='commit'"` al `pytest.warns`.
- **Files modified:** `tests/test_pool.py`
- **Verification:** `uv run ruff check encino_orm tests` sale 0.
- **Committed in:** `47124f8` (Task 2)

---

**Total deviations:** 1 auto-fixed (1 Rule 3)
**Impact on plan:** Necesaria para que el gate de lint quedase verde; sin scope creep. No se tocó `pyproject.toml`, `uv.lock`, `ci.yml`, `tests/_pool_helpers.py` (04-05) ni `tests/test_pool_concurrency.py` (04-06).

## Issues Encountered
- El docstring de `tests/test_pool_characterization.py` describía POOL-04 como pendiente; se actualizó a 04-03 (dentro del fichero de ownership del plan) para no dejar documentación de estado obsoleta.
- La evidencia RED se obtuvo restaurando temporalmente `encino_orm/pool.py` al commit de la Task 1 desde una copia de seguridad y volviendo a la copia actual; el árbol quedó verificado (`git diff --stat` con solo los cambios esperados y 60 tests verdes tras restaurar).

## TDD Gate Compliance
El plan es `type: execute` con tareas `tdd="true"`, pero el flujo RED/GREEN se materializó como evidencia de caracterización (inversión de `test_release_rolls_back_leftover_transaction`) en lugar de commits `test(...)`/`feat(...)` separados por tarea. No hay commits de gate RED independientes; la evidencia RED/GREEN está registrada arriba.

## Threat Flags
Ninguna superficie nueva fuera del threat model. Las mitigaciones del registro están cubiertas:
- T-04-03-01 (pérdida silenciosa de escrituras standalone): orden Correction #5 respetado; `TestPoolAutocommit`/`TestPoolStandaloneCommit` verdes sin editar.
- T-04-03-02 (transacción dejada abierta): `reset_on_release` rollback por defecto; `"commit"` deprecado y documentado.
- T-04-03-03 (warning por cada SELECT en MSSQL/Oracle): warning enganchado a la política; `test_select_leftover_does_not_warn` bajo `filterwarnings=["error"]`.
- T-04-03-04 (error que deja la transacción abierta): `except BaseException` con rollback y re-lanzado; `test_standalone_error_rolls_back`.
- T-04-03-05 (`"none"` reintroducido): `ValueError` fail-closed; `test_invalid_reset_on_release_raises`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- La semántica de liberación es explícita y configurable; 04-04 (reaper + `close()` idempotente) puede apoyarse en `release()` como punto de aplicación de la política.
- El `DeprecationWarning` de la política sigue el patrón determinista ya usado por `last_id()` (04-02).
- Gates verdes. El ratchet de mypy de `encino_orm.pool` queda pendiente para 04-04 (no se retiró aquí).

## Self-Check: PASSED

- FOUND: `encino_orm/pool.py` (`reset_on_release`, `except BaseException`, `await handle.driver.rollback()`)
- FOUND: `tests/test_pool.py` (`TestPoolStandaloneRollback`, `TestPoolResetOnRelease`)
- FOUND: `tests/test_pool_characterization.py` (`test_release_rolls_back_leftover_transaction`)
- FOUND: `docs/guide.md` (`reset_on_release`)
- FOUND: `CHANGELOG.md` (entrada en `[Unreleased] ### Corregido`)
- FOUND: commits `722ee84`, `47124f8`, `79a60c1`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-03-SUMMARY.md`
