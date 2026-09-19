---
phase: 04-pool-correctness-concurrency
plan: 04
subsystem: database
tags: [asyncio, pool, concurrency, reaper, idle-timeout, close, generation, mypy, ruff, changelog]

# Dependency graph
requires:
  - phase: 04-pool-correctness-concurrency
    provides: "Handle `PooledConnection`, admisión sin carrera y `release()` con ownership (04-01); `execute_insert`/`last_id()` deprecado (04-02); cierre explícito y `reset_on_release` (04-03)"
provides:
  - "Reaper PEREZOSO `PoolDb._reap()` (sin daemon) que cierra ociosas por encima de `min_size`; invocado en `acquire()`/`release()`; `idle_timeout=None` lo desactiva (POOL-05)"
  - "Contador `_generation` por handle + `_closed`: `close()` idempotente que NUNCA cierra una conexión en uso; las retenidas se cierran al liberarse (POOL-06)"
  - "`release()` cierra (no reencola) handles con pool cerrado o generación obsoleta; `connect()` reabre el pool para el ciclo close/reconnect (A6)"
  - "Caracterización `test_close_closes_held_connection` → `test_close_does_not_close_held_connection` invertida con evidencia RED/GREEN"
  - "Ratchet de mypy de `encino_orm.pool`: entrada conservada con el residual (5 errores de tipado) y su causa escritos; PT011/B017 diferidos con justificación; sin piso de cobertura para pool.py"
affects: [04-06, 08-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Reaper perezoso: drenar la cola recolectando `keep` y `to_close`, reencolar los `keep` DESPUÉS del bucle (reencolar dentro del bucle nunca vacía la cola) y cerrar los drivers FUERA del bucle (T-04-04-04)"
    - "Cierre idempotente que respeta al tenedor: solo `_idle` se cierra en `close()`; `_checked_out` se cierra al liberarse"
    - "Generación como invalidación de handles tras close/reconnect: `release()` cierra los obsoletos en vez de reencolarlos"

key-files:
  created: []
  modified:
    - encino_orm/pool.py
    - tests/test_pool.py
    - tests/test_pool_characterization.py
    - pyproject.toml
    - CHANGELOG.md

key-decisions:
  - "El reaper NO reencola dentro del bucle de drenado: el sketch del plan lo hacía y producía un bucle infinito (el handle reencolado vuelve a `get_nowait()`); se recolectan `keep`/`to_close` y se reencola/cierra después"
  - "`connect()` pone `_closed = False` (reabre el pool): sin esto, un `connect()` tras `close()` dejaría todos los handles nuevos cerrándose al liberarse (fuga), y el escenario close/reconnect de A6 no funcionaría"
  - "Semántica de generación (A6): `_generation` se asigna por handle en `_create_connection()` y se incrementa en `close()`; `release()` cierra si `_closed` o `handle.generation != _generation`"
  - "El ratchet de mypy de `encino_orm.pool` NO se retira: quedan 5 errores de TIPADO ajenos al pool (3 `var-annotated` + 2 `override` de property sobre atributos escribibles de `Db`); los `override` exigen `base.py` (fuera de alcance) y `# type: ignore` inline está prohibido"
  - "PT011/B017 se DIFIEREN a una fase de calidad posterior (~147 asserts ajenos a POOL-01…07; levantarlos enterraría los cambios reales del pool) — Open Question 4"
  - "Sin piso de cobertura para `encino_orm/pool.py` en esta fase: un piso mal calibrado bloquea CI y el fichero de tests del pool crecerá (Open Question 5)"

patterns-established:
  - "Reaper perezoso sin daemon: el coste de cerrar ociosas se paga en el camino que ya adquiere/libera"
  - "Idempotencia de `close()` con guard `_closed` y contador de generación para invalidar handles vivos"

requirements-completed: [POOL-05, POOL-06]

# Metrics
duration: 8min
completed: 2026-09-19
---

# Phase 4 Plan 04: Reaper perezoso y `close()` idempotente Summary

**Reaper perezoso que cierra las ociosas por encima de `min_size` (invocado en `acquire`/`release`, sin daemon) y `close()` idempotente que nunca cierra una conexión en uso — las retenidas se cierran al liberarse — con contador de generación que invalida handles obsoletos tras close/reconnect, caracterización POOL-06 invertida con evidencia RED/GREEN y gates verdes.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-09-19T03:07:17Z
- **Completed:** 2026-09-19T03:15:03Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `PoolDb._reap()`: reaper PEREZOSO (sin daemon ni `asyncio.Task`), invocado al ENTRAR en `acquire()` y al SALIR de `release()`. Drena `_idle` y cierra las conexiones con `idle_timeout` superado solo por encima de `min_size`; `idle_timeout=None` lo desactiva. Los drivers se cierran fuera del bucle de drenado.
- `PoolDb.close()` idempotente: la segunda llamada es no-op; solo cierra las ociosas y deja intactas las retenidas (`_checked_out`), que se cierran al liberarse. `_stats` NO se resetea.
- Contador `_generation` asignado por handle en `_create_connection()` e incrementado en `close()`; `release()` cierra en vez de reencolar handles con pool cerrado o generación obsoleta. `connect()` reabre el pool (`_closed=False`).
- Caracterización POOL-06 invertida: `test_close_closes_held_connection` → `test_close_does_not_close_held_connection` (nuevo assert `held.driver.closed is False`; tras `release`, `True`).
- Task 3: ratchet de mypy de `encino_orm.pool` intentado retirar y conservado con su residual documentado; comentario de PT011/B017 actualizado con la justificación del diferimiento; CHANGELOG ampliado en la sección `[Unreleased] ### Corregido` existente.

## Task Commits

Each task was committed atomically:

1. **Task 1: Reaper perezoso de ociosas por encima de `min_size` (POOL-05)** - `7c8b558` (feat)
2. **Task 2: `close()` idempotente que respeta al tenedor + contador de generación (POOL-06)** - `157d6f3` (feat)
3. **Task 3: Retirar/documentar el ratchet de mypy, documentar `close()`/reaper y cerrar los gates** - `ce24b4c` (docs)

**Plan metadata:** (commit final de docs del plan)

## Files Created/Modified
- `encino_orm/pool.py` - `_reap()`; `_closed` en `__init__` y guard de `close()`; `_generation += 1` en `close()`; rama `_closed`/generación en `release()`; `_closed = False` en `connect()`.
- `tests/test_pool.py` - `TestPoolReaper` (4 tests: ociosidad/min_size, `idle_timeout=None`, recientes, disparo desde `acquire()`) y `TestPoolCloseIdempotent` (3 tests: close solo ociosas, release tras close, generación obsoleta).
- `tests/test_pool_characterization.py` - inversión de POOL-06 en `TestPoolClose`; docstring de estado actualizado a 04-04.
- `pyproject.toml` - comentario de PT011/B017 con el diferimiento; comentario del ratchet de mypy con el residual de `encino_orm.pool` y su causa.
- `CHANGELOG.md` - nueva entrada de CAMBIO DE COMPORTAMIENTO en `[Unreleased] ### Corregido` (sin duplicar encabezado).

## RED / GREEN Evidence (inversión de POOL-06)

- **RED:** con `encino_orm/pool.py` restaurado temporalmente al estado de la Task 1 (commit `7c8b558`, `close()` aún cierra lo retenido) y la aserción NUEVA en el árbol, `tests/test_pool_characterization.py::TestPoolClose::test_close_does_not_close_held_connection` FALLA con `AssertionError: assert True is False` en `assert held.driver.closed is False`. Ejecutado con `uv run pytest ... -k does_not_close_held -q`.
- **GREEN:** con el `close()` nuevo (Task 2), el mismo test PASA (`1 passed`). La copia restaurada se verificó por `sha256` (`RESTORED: OK`) y el árbol volvió a mostrar solo los cambios esperados (`git diff --stat`).
- **Semántica de generación elegida (A6):** `_generation` es un contador del pool asignado por handle en `_create_connection()`; `close()` lo incrementa para invalidar los handles vivos, y `release()` cierra (no reencola) un handle si `self._closed` o `handle.generation != self._generation`. El test `test_stale_generation_handle_is_closed_on_release` cubre el ciclo close/reconnect.

## Decisions Made
- **Reaper sin reencolar dentro del bucle:** el sketch de `04-RESEARCH.md`/plan reencolaba el handle no reapeado con `put_nowait`/`put` dentro del `while`; como la cola es FIFO y sin cota, el handle vuelve a salir en la siguiente iteración y el bucle nunca vacía `_idle` (bucle infinito reproducido). Se recolectan `keep`/`to_close` y se reencola/cierra DESPUÉS del bucle.
- **`connect()` reabre el pool (`_closed=False`):** necesario para el escenario close/reconnect descrito en el behavior; sin ello, los handles nuevos se cerrarían al liberarse (fuga de conexiones).
- **Ratchet de mypy conservado:** ver Task 3 abajo; el residual es de tipado, no de la corrección del pool.
- **PT011/B017 diferidos** y **sin piso de cobertura** para `pool.py` (Open Questions 4 y 5).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Bucle infinito en `_reap()` por reencolar dentro del bucle de drenado**
- **Found during:** Task 1 (verify `uv run pytest tests/test_pool.py -k reap`)
- **Issue:** el sketch del plan reencolaba el handle no reapeado (`put_nowait`/`put`) dentro del `while` que drena `_idle`. Con una cola FIFO sin cota, el handle vuelve a `get_nowait()` en la iteración siguiente y el bucle nunca termina (el test colgó y `--timeout` lo capturó en `put_nowait`).
- **Fix:** recolectar los handles a conservar en `keep` y los reapeados en `to_close`; tras el bucle, `put_nowait` de los `keep` y `close()` de los `to_close` (los drivers siguen cerrándose FUERA del bucle).
- **Files modified:** `encino_orm/pool.py`
- **Verification:** `uv run pytest tests/test_pool.py -k reap -q` → 4 passed; `tests/test_pool.py tests/test_pool_characterization.py` → 67 passed.
- **Committed in:** `7c8b558` (Task 1)

**2. [Rule 2 - Missing Critical] `connect()` no reabría el pool tras `close()`**
- **Found during:** Task 2 (diseño del ciclo close/reconnect de A6)
- **Issue:** el plan solo pedía `_closed = True` en `close()`; sin resetearlo en `connect()`, un pool reconectado cerraría TODOS los handles nuevos al liberarlos (fuga), y el escenario "handle obsoleto tras un `connect()` posterior" no podría reutilizar las conexiones nuevas.
- **Fix:** `connect()` fija `self._closed = False` al inicio; los handles de la generación anterior siguen cerrándose por el desajuste de `_generation`.
- **Files modified:** `encino_orm/pool.py`
- **Verification:** `test_stale_generation_handle_is_closed_on_release` y el resto de la suite del pool verdes.
- **Committed in:** `157d6f3` (Task 2)

---

**Total deviations:** 2 auto-fixed (1 Rule 1, 1 Rule 2)
**Impact on plan:** Ambas necesarias para que el reaper no cuelgue y para que el ciclo close/reconnect sea correcto. Sin scope creep: no se tocaron `base.py`, `uv.lock`, `ci.yml`, `tests/_pool_helpers.py` (04-05) ni `tests/test_pool_concurrency.py` (04-06).

## Issues Encountered
- La primera versión de los tests del reaper asumía `_size == 4` adquiriendo 3 conexiones con `min_size=1` (el `connect()` ya deja 1 ociosa, así que con 3 adquisiciones `_size` era 3). Se corrigió a 4 adquisiciones. Era un error de autoría del test, no del plan.
- La inversión de `test_release_does_not_commit_or_rollback` mencionada en el prompt ya estaba hecha en 04-03 (`test_release_rolls_back_leftover_transaction`), así que no se tocó.
- El script de evidencia RED/GREEN imprimió `warning: Failed to set cwd to temp dir` (ruido de `uv`), sin efecto en el resultado.

## Task 3 — Residual del ratchet de mypy

`uv run mypy encino_orm` sale 0 porque la entrada del ratchet sigue activa. Al retirarla temporalmente, aparecen **5 errores en `encino_orm/pool.py`** (los mismos que documentaba el ratchet):

| Error | Línea | Causa | ¿Se puede arreglar en 04-04? |
|-------|-------|-------|------------------------------|
| `var-annotated` `_idle` | 123 | `asyncio.Queue()` sin anotación | Sí, pero fuera del alcance de la Task 3 (`files`: `pyproject.toml`, `CHANGELOG.md`) |
| `var-annotated` `_connections` | 124 | `set()` sin anotación | idem |
| `var-annotated` `_checked_out` | 125 | `set()` sin anotación | idem |
| `override` `dialect` | 137 | property de solo lectura sobre `Db.dialect: str = ""` (atributo escribible) | No: exige cambiar `base.py` (fuera de `files_modified`) |
| `override` `transactional_ddl` | 151 | property de solo lectura sobre `Db.transactional_ddl: bool = True` | No: idem |

Decisión: **NO retirar la entrada** (el plan lo autoriza explícitamente si mypy no queda limpio) y dejar la causa escrita en el comentario del bloque `[[tool.mypy.overrides]]` para que el ratchet no mienta. La convención del repo prohíbe `# type: ignore` inline (`grep -rn "noqa" encino_orm/` sigue vacío y el conteo de supresiones inline en `encino_orm/` es 0).

## Task 3 — Otras decisiones de alcance

- **PT011/B017 (Open Question 4):** NO se levantan en esta fase; se difieren a una fase de calidad posterior con la razón escrita en `pyproject.toml` (~147 asserts `pytest.raises(Exception)`/`pytest.raises` sin `match=` ajenos a POOL-01…07; el diff mecánico enterraría los cambios reales del pool).
- **Piso de cobertura (Open Question 5):** NO se añade piso para `encino_orm/pool.py` en `tools/ci/check_coverage_floors.py` (un piso mal calibrado bloquea CI y el fichero de tests del pool crecerá).

## Verification Gates

- `uv run pytest tests/test_pool.py -k "reap" -q` → **4 passed**
- `uv run pytest tests/test_pool_characterization.py -k "close" -q` → **5 passed** (aserción invertida)
- `uv run pytest tests/test_pool.py -k "close or generation" -q` → **5 passed**
- `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` → **67 passed**
- `uv run pytest -q -m "not integration and not optional_engine"` → **808 passed, 85 deselected**
- `uv run pytest -q` (suite completa, end-of-plan) → **893 passed**
- `uv run ruff check encino_orm tests` → **All checks passed!**
- `uv run ruff format --check encino_orm tests` → **116 files already formatted**
- `uv run mypy encino_orm` → **Success: no issues found in 60 source files**
- `uv lock --check` → **Resolved 98 packages** (exit 0)
- `grep -c "def _reap"` → 1; `grep -c "await self._reap()"` → 2; `grep -c "_closed"` → 6; `grep -c "_generation"` → 4
- `sed -n '/## \[Unreleased\]/,/## \[0.2.6\]/p' CHANGELOG.md | grep -ci "close()"` → 2; `... | grep -ci "reaper\|ocios"` → 4; `... | grep -c "### Corregido"` → 1
- `grep -c "PT011" pyproject.toml` → 2 (comentario + valor)
- `filterwarnings = ["error"]` intacto; `grep -rn "noqa" encino_orm/` → 0
- **No ejecutado (instrucción del ejecutor):** `pytest -m integration`.

## TDD Gate Compliance

El plan es `type: execute` con tareas `tdd="true"`, pero el flujo RED/GREEN se materializó como evidencia de caracterización (inversión de `test_close_does_not_close_held_connection`) en lugar de commits `test(...)`/`feat(...)` separados por tarea. No hay commits de gate RED independientes; la evidencia RED/GREEN está registrada arriba (mismo patrón que 04-03).

## Threat Flags

Ninguna superficie nueva fuera del threat model. Las mitigaciones del registro están cubiertas:
- T-04-04-01 (cerrar una conexión en uso): `close()` solo cierra `_idle`; `_checked_out` intacto; `test_close_does_not_close_held_connection` invertida + `test_close_closes_idle_only`.
- T-04-04-02 (acumulación de ociosas): `_reap()` limitado por `min_size`; tests de ociosidad, `min_size` e `idle_timeout=None`.
- T-04-04-03 (handle obsoleto reencolado): `_generation` + `_closed`; `release()` cierra en vez de reencolar; test de generación obsoleta.
- T-04-04-04 (reaper con `await` en el drenado): drivers cerrados fuera del bucle; el fix del bucle infinito refuerza que el drenado no reencola dentro del `while`.
- T-04-04-05 (ratchet mintiendo): entrada conservada solo con el residual documentado y su causa; PT011/B017 y el piso de cobertura registrados.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- POOL-05/06 cubiertos; 04-06 (tests de concurrencia/estrés) puede apoyarse en el reaper, la generación y el `close()` respetuoso con el tenedor.
- El ratchet de mypy de `encino_orm.pool` queda con su residual de tipado documentado (no bloqueante); una fase de calidad posterior puede retirarlo arreglando las anotaciones de `pool.py` y las properties de `Db` en `base.py`.
- Gates verdes; sin blockers.

## Self-Check: PASSED

- FOUND: `encino_orm/pool.py` (`_reap`, `_closed`, `_generation`, rama de `release()`)
- FOUND: `tests/test_pool.py` (`TestPoolReaper`, `TestPoolCloseIdempotent`)
- FOUND: `tests/test_pool_characterization.py` (`test_close_does_not_close_held_connection`)
- FOUND: `pyproject.toml` (comentario PT011/B017 + residual de `encino_orm.pool`)
- FOUND: `CHANGELOG.md` (entrada en `[Unreleased] ### Corregido`)
- FOUND: commits `7c8b558`, `157d6f3`, `ce24b4c`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-04-SUMMARY.md`
