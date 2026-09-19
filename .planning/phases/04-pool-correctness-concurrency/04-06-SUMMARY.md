---
phase: 04-pool-correctness-concurrency
plan: 06
subsystem: testing
tags: [pytest, concurrency, asyncio, event-barrier, pool, sqlite, pytest-timeout, pytest-repeat, stress]

# Dependency graph
requires:
  - phase: 04-pool-correctness-concurrency
    provides: "04-01 (handle PooledConnection + acquire sin carrera), 04-03 (semantica de liberacion), 04-04 (reaper + close idempotente), 04-05 (EventBarrier/FakeDb/BlockingFakeDb + pytest-timeout/pytest-repeat + marker stress)"
provides:
  - "tests/test_pool_concurrency.py con la carrera de admision determinista, ids concurrentes sin cruce, commit standalone visible y variante de estres"
  - "Propiedades AFIRMADAS del comportamiento final del pool (no caracterizacion): `_size <= max_size`, ids propios por tarea, commit entre conexiones"
affects: [pool-concurrency-tests, verify-work]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Barrera determinista 3.10 (EventBarrier sobre asyncio.Event) con release() explicito cuando solo max_size tareas alcanzan connect()"
    - "Fakes a mano + monkeypatch.setitem(pool_module._ENGINES, ...) (sin unittest.mock)"
    - "Timeout por marker (`@pytest.mark.timeout`) y variante de estres (`@pytest.mark.stress` + `@pytest.mark.repeat`)"
    - "Test negativo no colgante con `asyncio.wait_for` en vez de depender de que pytest-timeout mate el proceso"

key-files:
  created:
    - tests/test_pool_concurrency.py
  modified: []

key-decisions:
  - "El test de admision libera los handles adquiridos (cada worker hace acquire -> sleep(0) -> release) para que las tareas en espera progresen: 5 tareas se sirven con solo 2 conexiones y el gather no cuelga. Se asserta `len(set(handles)) == max_size` (handles reutilizados), no 5 handles distintos, que seria inalcanzable con max_size=2."
  - "Con la reserva-antes-del-await solo max_size tareas alcanzan connect(), asi que la barrera parties=5 NO se libera sola: se llama `barrier.release()` explicitamente (mismo patron que la caracterizacion de Fase 1). El release es incondicional, de modo que el test no puede colgarse."
  - "El valor RED no se reproduce en vivo: el fix vive en pool.py (04-01...04-04) y este plan solo puede crear tests/test_pool_concurrency.py. Se documenta el baseline historico (Fase 1: `_size == 5` y cruce de ids) como RED y la corrida actual como GREEN."
  - "EventBarrier no es reutilizable por diseno (el Event queda activado); se documenta con test_event_barrier_is_single_use y el soak crea una barrera nueva por ciclo. No se edita tests/_pool_helpers.py (es de 04-05)."

patterns-established:
  - "Los tests de barrera afirman `_size <= max_size` y el pico de `_checked_out`; el test negativo de parties desajustado usa asyncio.wait_for(0.5s)"
  - "El soak `--count=100` queda como comando local documentado; no se anade a ci.yml en esta fase (T-04-06-04)"

requirements-completed: [POOL-07]

# Metrics
duration: 20min
completed: 2026-09-19
---

# Phase 4 Plan 06: Tests deterministas de concurrencia y estrés del pool Summary

**`tests/test_pool_concurrency.py` afirma el comportamiento final del pool: `acquire()` nunca supera `max_size` bajo una barrera `asyncio.Event`, los inserts concurrentes devuelven cada uno su propio id sin cruce, el commit standalone sigue visible entre conexiones y existe una variante de estrés `pytest-repeat` tras el marker `stress`**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-19T03:00:00Z (aprox.)
- **Completed:** 2026-09-19T03:21:34Z
- **Tasks:** 3
- **Files modified:** 1 (creado)

## Accomplishments

- `test_no_overshoot_under_barrier` (POOL-02): 5 tareas compiten con `max_size=2` bajo `BlockingFakeDb` + `EventBarrier(parties=5)`; se asserta `_size <= _max_size`, `_size == max_size`, pico de `_checked_out <= max_size` y handles reutilizados. Marcado `concurrency` + `timeout(10)`.
- `test_barrier_releases_only_with_matching_parties`: test negativo NO colgante que demuestra que una barrera con más `parties` que tareas nunca se libera, acotado con `asyncio.wait_for(0.5s)` (no depende de que pytest-timeout mate el proceso).
- `test_concurrent_insert_ids_no_crosstalk` (POOL-03): 5 inserts concurrentes sobre `PoolDb("sqlite")` real devuelven ids 1..5 distintos con mapeo `nombre -> id` verificado contra las filas.
- `test_standalone_commit_visible_across_connections` (POOL-04): `pool.execute(INSERT)` standalone es visible desde otra conexión del pool.
- `test_execute_insert_inside_transaction_uses_held_connection`: `execute_insert` dentro de `transaction()` usa la conexión retenida y devuelve ids correlativos.
- `test_no_overshoot_repeated` (POOL-07): variante de estrés `@pytest.mark.stress` + `@pytest.mark.repeat(5)` que pasa también en la corrida normal.
- `test_event_barrier_is_single_use`: documenta que `EventBarrier` no es reutilizable; el soak crea una barrera nueva por ciclo.

## Task Commits

Each task was committed atomically:

1. **Task 1: Carrera de admisión determinista bajo `EventBarrier`** — `3a7dda8` (test)
2. **Task 2: Ids concurrentes sin cruce y commit standalone visible** — `e7c7700` (test)
3. **Task 3: Variante de estrés `pytest-repeat` tras el marker `stress`** — `a93c851` (test)

**Plan metadata:** (docs: complete plan) — ver commit final

## Files Created/Modified

- `tests/test_pool_concurrency.py` (NUEVO) — 224 líneas. Cabecera en español con las restricciones duras (piso 3.10, sin dobles automáticos, determinismo, timeout por marker); 6 tests + 1 fixture `sqlite_pool(tmp_path)`. No toca `tests/test_pool.py` ni `tests/test_pool_characterization.py` (verificado: `git diff --numstat` vacío).

## Verification (gates de fin de plan)

| Gate | Resultado |
|------|-----------|
| `uv run pytest tests/test_pool_concurrency.py -q` | **11 passed** (el `repeat(5)` expande a 5 items) |
| `uv run pytest tests/test_pool_concurrency.py -q -m concurrency` | **3 passed**, 8 deselected, en 0.68 s (< 30 s) |
| `uv run pytest tests/test_pool_concurrency.py -q -m stress` | **5 passed** (sin fallo de `--strict-markers`) |
| `uv run pytest tests/test_pool_concurrency.py -q -m "not stress"` | **6 passed** |
| `uv run pytest -q` | **904 passed** in 21.43s (10 snapshots passed) |
| `uv run pytest -q -m "not integration and not optional_engine"` | **819 passed**, 85 deselected |
| `uv run pytest -q -m stress --count=3` | **5 passed** |
| AST check (`Barrier`/`TaskGroup`/`asyncio.timeout` en código) | `OK: sin primitivas 3.11 en codigo` |
| `git diff --numstat tests/test_pool.py tests/test_pool_characterization.py` | VACÍO |
| `uv run ruff check encino_orm tests` | All checks passed |
| `uv run ruff format --check encino_orm tests` | 117 files already formatted |
| `uv run mypy encino_orm` | Success: no issues found in 60 source files |
| `filterwarnings = ["error"]` intacto | Sí (no se tocó `pyproject.toml`) |
| Greps de aceptación | `EventBarrier`=5, `@pytest.mark.timeout`=4, `@pytest.mark.concurrency`=3, `execute_insert`=5, `@pytest.mark.stress`=1, `pytest.mark.repeat`=1 |

### Evidencia RED/GREEN

- **GREEN (corrida actual):** `_size == 2` con `max_size=2` y 5 tareas; ids `{1,2,3,4,5}` sin cruce; commit standalone visible.
- **RED (baseline histórico de Fase 1, `01-05-SUMMARY.md:88`):** con `min_size=0, max_size=2` y 5 tareas, el pool pre-refactor observaba `_size == 5`; el cache `_last_id` compartido devolvía el id de otra tarea. **No se reproduce en vivo en este plan** porque el fix vive en `pool.py` (04-01…04-04) y `files_modified` prohíbe editar `pool.py`; la caracterización de Fase 1 conserva la evidencia del defecto.

## Deviations from Plan

### Ajustes automáticos

**1. [Rule 3 - Ajuste para evitar un test colgante] El cuerpo literal del plan era contradictorio**

- **Found during:** Task 1.
- **Issue:** El `<action>` pedía `parties=5` sobre `connect()` con 5 tareas y `assert len(set(handles)) == 5`, pero con `max_size=2` y la reserva-antes-del-await solo 2 tareas alcanzan `connect()`: la barrera `parties=5` nunca se libera y `asyncio.gather` se colgaría; además 5 handles distintos son inalcanzables con 2 conexiones.
- **Fix:** El propio plan marcaba "AJUSTA" y daba la forma correcta. Se implementó cada worker como `acquire -> sleep(0) -> release` (las 2 con cupo se liberan y sirven a las 3 en espera), se llama `barrier.release()` explícitamente (incondicional → el test no puede colgarse) y se asserta `len(set(handles)) == max_size` (handles reutilizados) en vez de 5 distintos. El pico de `_checked_out` se asserta `<= max_size`.
- **Files modified:** `tests/test_pool_concurrency.py`.
- **Committed in:** `3a7dda8`.

**2. [Rule 3 - Documentar la no-reutilizabilidad] `EventBarrier` no soporta reutilización por diseño**

- **Found during:** Task 3.
- **Issue:** El plan ofrecía "test de reutilización O documentar la limitación". `EventBarrier` deja el `Event` activado tras la primera liberación, así que un segundo ciclo `wait()` retorna de inmediato.
- **Fix:** Se añadió `test_event_barrier_is_single_use` que documenta la limitación y se confirmó que el soak crea una barrera nueva por ciclo. No se editó `tests/_pool_helpers.py` (es de 04-05).
- **Files modified:** `tests/test_pool_concurrency.py`.
- **Committed in:** `a93c851`.

---

**Total deviations:** 2 auto-fijadas (Rule 3)
**Impact on plan:** Sin cambio de alcance; el fichero entregado cumple todos los `must_haves`. El plan ya anticipaba ambos ajustes ("AJUSTA"/"o documenta la limitación").

## Issues Encountered

- El acceptance `grep -c "@pytest.mark.timeout"` cuenta también las menciones en docstrings (4 en vez de 2 decoradores); el criterio es `>= 1` y se cumple. El chequeo AST es docstring-safe y confirmó que no hay primitivas 3.11 en código.

## Known Stubs

None. Los tests usan `FakeDb`/`BlockingFakeDb` reales y un `PoolDb("sqlite")` sobre fichero temporal; no hay datos mock que fluyan a UI ni componentes sin fuente.

## Threat Flags

None — no se introduce superficie de red/auth/acceso a ficheros nueva. El plan solo crea un fichero de tests. Las mitigaciones del `<threat_model>` (T-04-06-01 timeout + test negativo no colgante; T-04-06-02 ids propios; T-04-06-03 aserciones del comportamiento final; T-04-06-04 `repeat(5)` sin `ci.yml`; T-04-06-05 AST sin primitivas 3.11) están aplicadas y verificadas.

## Next Phase Readiness

- POOL-07 queda cubierto por tests que AFIRMAN el comportamiento final, no por la inversión de la caracterización.
- La suite completa (904) y los gates (ruff/mypy/format) están verdes; `tests/test_pool_concurrency.py` puede entrar en `/gsd-verify-work` de la fase.
- Sin blockers.

---
*Phase: 04-pool-correctness-concurrency*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `tests/test_pool_concurrency.py`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-06-SUMMARY.md`
- FOUND commit: `3a7dda8`
- FOUND commit: `e7c7700`
- FOUND commit: `a93c851`
