---
phase: 01-safety-net-ci-gates-test-infrastructure
plan: 05
subsystem: testing
tags: [pool, characterization, concurrency, asyncio-event-barrier, pool-02, pool-03, pool-04, pool-06, ci-09, d-09]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-03: harness endurecido (`--strict-markers`, `filterwarnings=[\"error\"]`) y el marker `concurrency` registrado"
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-04: `tools/ci/check_skips.py` y la invocacion requerida `-m \"not optional_engine\"`"
provides:
  - "`tests/test_pool_characterization.py`: especificacion de comportamiento de `PoolDb` (checkout cap, overshoot race, `last_id` scoping, release semantics, `close()`) contra la implementacion SIN modificar — la red de seguridad que la Fase 4 debe hacer invertir"
affects: ["Fase 4 (POOL-01…POOL-07): el refactor debe ACTUALIZAR, no borrar, cada asercion que invierta"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Barrera determinista con `asyncio.Event` (piso 3.10) que libera en la ULTIMA llegada, nunca por temporizador"
    - "Fakes escritos a mano que registran cada llamada (incluido `is_alive`) para caracterizar efectos, no implementacion"
    - "Aserción que caracteriza un defecto y nombra el requisito POOL que la invertira"

key-files:
  created:
    - tests/test_pool_characterization.py
  modified: []

key-decisions:
  - "La carrera de `acquire()` se reproduce con una barrera hecha con `asyncio.Event` (no `Barrier`/`TaskGroup`/`timeout`, inexistentes en 3.10) que libera en la ultima de 5 llegadas: determinista, sin `sleep`."
  - "Cada aserción que se espera invertir en Fase 4 lleva un comentario en español que nombra el requisito POOL; las que no deben invertir (cap secuencial, idempotencia de `close()`, retencion de `_stats`) se caracterizan igual pero sin marca de inversion."
  - "El `FakeDb` propio registra `is_alive` en `calls` (a diferencia del de `tests/test_pool.py`) para que la asercion 'release() no comprueba liveness' sea real y no vacua."

patterns-established:
  - "Characterization-first: la red de seguridad del pool se escribe contra la implementacion actual antes del refactor (Hard Ordering Constraint 1)"
  - "Test de carrera con marker `concurrency` y barrera sin temporizador (T-01-13)"

requirements-completed: [CI-09]

# Metrics
duration: 3min
completed: 2026-09-17
---

# Phase 1 Plan 05: Caracterizacion de invariantes del pool

**19 tests que fijan el comportamiento actual (defectuoso incluido) de `PoolDb` — cap de checkout, carrera de overshoot con `_size=5` sobre `max_size=2`, scoping de `last_id` con cache compartido entre tareas, semantica de `release()` y `close()` que cierra una conexion en uso — contra la implementacion sin modificar, con una barrera determinista de `asyncio.Event` y sin tocar `encino_orm/pool.py`.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-09-17T23:44:46Z
- **Completed:** 2026-09-17T23:48:13Z
- **Tasks:** 3
- **Files modified:** 1 (creado: `tests/test_pool_characterization.py`)

## Accomplishments

- **CI-09 satisfecho antes de cualquier refactor del pool** (Hard Ordering Constraint 1): el fichero fija el comportamiento de la implementacion actual, no el deseado.
- **La carrera de overshoot queda reproducida de forma determinista.** Con `min_size=0, max_size=2` y 5 tareas concurrentes de `acquire()`, el `_size` observado es **exactamente 5**. Todas las tareas pasan la comprobacion `_size < _max_size` antes de que ninguna incremente `_size`, porque `_create_connection()` es un punto de `await` (pool.py:114-124).
- **La barrera es determinista y compatible con el piso 3.10.** `EventBarrier` libera en la ultima de `parties` llegadas; no hay `sleep` ni temporizador, asi que el test no puede volverse flaky. No aparece ninguna primitiva de 3.11 en el fichero.
- **`last_id`, `release()` y `close()` quedan caracterizados en sus cuatro/cinco casos** respectivamente, incluidos los defectos (cache de pool compartido entre tareas, `release()` sin commit/rollback ni liveness, `close()` cerrando una conexion en uso, doble `release()` aliasando la misma conexion).
- **`encino_orm/pool.py` y `tests/test_pool.py` intactos** (`git diff --stat` vacio): CI-09 es red de seguridad, no un arreglo.
- **Cero skips introducidos**: la invocacion requerida produce 540 passed / 13 deselected y `check_skips.py` sale 0, asi que el fichero no puede disparar el gate CI-02 de 01-04.

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: scaffold + fakes + barrera + checkout cap + carrera de overshoot** — `9314a57` (test)
2. **Task 2: `last_id` scoping y release semantics** — `78193ca` (test)
3. **Task 3: `close()` + verificacion de la red de seguridad completa** — `66a7e88` (test)

**Plan metadata:** (este commit) (docs: complete plan)

## Files Created/Modified

- `tests/test_pool_characterization.py` — **nuevo**; 19 tests en 5 clases: `TestPoolCheckoutCap` (3), `TestPoolAcquireOvershootRace` (1, `concurrency`), `TestPoolLastIdScoping` (6), `TestPoolReleaseSemantics` (4), `TestPoolClose` (5). Incluye `FakeDb`, `BlockingFakeDb`, `EventBarrier` y los fixtures `fake_engine`, `blocking_engine`, `pool`, `single_pool`.

## Comportamiento caracterizado (medido)

| Invariante | Caso | Comportamiento actual |
|-----------|------|-----------------------|
| Checkout cap | `min_size=2` | `connect()` crea exactamente `min_size`; `_size == _min_size` |
| Checkout cap | secuencial hasta `max_size=3` | `_size == _max_size`, `len(_connections) == _max_size` |
| Checkout cap | `max_size=1`, conexion retenida, `acquire(timeout=0.1)` | `PoolExhaustedError`; tras `release()`, el siguiente `acquire` reutiliza la MISMA conexion |
| Overshoot race | 5 tareas / `max_size=2` | **`_size == 5`** (`> _max_size`) |
| `last_id` | dentro de transaccion | lee de la conexion retenida: `rid == 42`, `("last_id",)` en `db.calls` |
| `last_id` | fuera de transaccion | lee el cache del pool: `_last_id == 42`; `last_id()` no toca la conexion liberada |
| `last_id` | entre tareas | otra tarea que no inserto observa `42` (cache de pool compartido) |
| `last_id` | `INSERT`/`REPLACE` vs `SELECT` | el prefijo es case-insensitive y fija `_last_id`; `SELECT` lo deja intacto |
| `release()` | bookkeeping | registra `_last_used[db]` y reencola; `acquire()` devuelve el MISMO objeto |
| `release()` | transaccion abierta | NO emite `commit` ni `rollback` |
| `release()` | liveness | NO llama `is_alive` |
| `release()` | doble | la cola guarda 2 referencias: `conn_a is conn_b` |
| `close()` | normal | `is_connected=False`, `_size=0`, `_connections` vacio, `_last_used={}`, conexion `closed=True` |
| `close()` | idempotente | segunda llamada no lanza; estado sin cambios |
| `close()` | conexion retenida | **cierra la conexion que el llamador aun mantiene** (`held.closed is True`) |
| `close()` | nunca conectado | no lanza; `is_connected=False` |
| `close()` | `_stats` | NO se resetea (`creates` conserva su valor) |

## Aserciones que se esperan INVERTIR en Fase 4

| # | Asercion (actual) | Requisito | Como invierte |
|---|-------------------|-----------|---------------|
| 1 | `assert p._size > p._max_size` (observado `5 > 2`) | **POOL-02** | Pasa a `p._size <= p._max_size`: `acquire()` reserva el cupo antes del `await` y nunca supera `max_size`. |
| 2 | `assert single_pool._last_id == 42` y `assert rid == 42` (fuera de transaccion) | **POOL-03** | Desaparece el cache de pool: el id se captura DENTRO del insert (`RETURNING`/`SCOPE_IDENTITY`/`lastrowid`) por conexion/tarea; un `last_id()` post-hoc queda deprecado. |
| 3 | `assert stale == 42` (otra tarea ve el id anterior) | **POOL-03** | La otra tarea ya no observa el id de un insert ajeno (sin cruce entre tareas). |
| 4 | `assert ("commit",) not in conn.calls` / `assert ("rollback", None) not in conn.calls` | **POOL-04** | `release()` revierte por defecto → aparece `("rollback", None)`; con `reset_on_release="commit"` aparece `("commit",)`. |
| 5 | `assert held.closed is True` | **POOL-06** | Pasa a `held.closed is False`: `close()` nunca cierra una conexion en uso. |
| 6 | `assert conn_a is conn_b` (doble `release()`) | **POOL-02/POOL-06** | El doble `release()` deja de duplicar la referencia en la cola (liberacion ligada a la propiedad de la tarea). |

**Aserciones que NO se esperan invertir (la Fase 4 debe preservarlas):** cap secuencial (`_size == _max_size`), reutilizacion de la conexion liberada, `PoolExhaustedError` con timeout, `_last_used` registrado por `release()`, ausencia de comprobacion de liveness en `release()`, idempotencia de `close()` y retencion de `_stats`.

## Verification (plan-level)

| Comando | Resultado |
|---------|-----------|
| `uv run pytest tests/test_pool_characterization.py -q -x` | `19 passed` |
| `uv run pytest tests/test_pool_characterization.py --collect-only -q -m "concurrency"` | `1/19 tests collected` (la carrera) |
| `uv run pytest -q` | **`553 passed`** (534 preexistentes + 19 nuevos) |
| `uv run pytest -q -m "not optional_engine"` | `540 passed, 13 deselected` |
| `uv run pytest -q --junitxml=char-junit.xml -m "not optional_engine"` + `check_skips.py char-junit.xml` | **`OK: 0 tests omitidos.`** (exit 0) |
| `uv run ruff check tests tools` | `All checks passed!` (exit 0) |
| `uv run ruff format --check tests tools` | `49 files already formatted` (exit 0) |
| `uv run mypy encino_orm` | `Success: no issues found in 56 source files` (exit 0) |
| `git diff --stat -- encino_orm/pool.py tests/test_pool.py` | sin salida (intactos) |
| `git status --porcelain` tras las pruebas | limpio (`char-junit.xml` eliminado con `pathlib.Path(...).unlink(missing_ok=True)`) |
| Substrings prohibidos (`asyncio.Barrier`, `pytest.skip`) | ausentes |

## Induced-failure proof (la red de seguridad puede fallar)

Se cambio temporalmente la asercion de la carrera `assert p._size > p._max_size` por `assert p._size == 0`, se confirmo el fallo y se revirtio:

```text
$ uv run pytest tests/test_pool_characterization.py -q
>       assert p._size == 0  # INDUCED FAILURE (temporal)
E       assert 5 == 0
E        +  where 5 = <encino_orm.pool.PoolDb object at 0x000001308B6382E0>._size
FAILED tests/test_pool_characterization.py::TestPoolAcquireOvershootRace::test_concurrent_acquire_overshoots_max_size
1 failed, 18 passed in 0.31s

$ # asercion restaurada
$ uv run pytest tests/test_pool_characterization.py -q
19 passed in 0.28s
```

El fallo induce, ademas, **mide** el valor real: `_size == 5`.

## Decisions Made

- **`asyncio.Event` y no temporizador.** La barrera libera en la ultima llegada; el numero de tareas DEBE igualar `parties` (comentado en el fichero), de modo que un desajuste cuelga el test en vez de enmascarar la carrera. Es la mitigacion de T-01-13.
- **`FakeDb` propio, no importado de `tests/test_pool.py`.** Evita acoplar la caracterizacion al fichero que la Fase 4 tambien tocara; ademas registra `is_alive` para que la asercion de "sin liveness" sea real.
- **No se "arregla" nada (D-09).** Ninguna asercion describe un comportamiento deseado pero ausente; todas reproducen lo observado, incluido lo defectuoso.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `Query` importado sin uso en el commit de Task 1**
- **Found during:** Task 1, en la primera corrida de `ruff check`
- **Issue:** el plan pide importar `Query` para los tests de Task 2, pero Task 1 se commitea solo. `ruff` F401 (`imported but unused`) bloquea el gate de lint, que es bloqueante (01-01).
- **Fix:** se importo `PoolDb, PoolExhaustedError` en Task 1 y se anadio `Query` en el commit de Task 2, donde pasa a usarse. Sin cambio de comportamiento.
- **Files modified:** `tests/test_pool_characterization.py`
- **Verification:** `uv run ruff check tests/test_pool_characterization.py` → exit 0 en ambos commits.
- **Committed in:** `9314a57` (Task 1) y `78193ca` (Task 2)

---

**Total deviations:** 1 auto-fixed (bloqueante, de orden de import).
**Impact on plan:** Nulo sobre el alcance o el comportamiento; el fichero queda lint-clean en cada commit atomico.

## Issues Encountered

- **`state.record-metric` / `state.add-decision` no aceptan argumentos posicionales** en esta version del SDK: hubo que usar `--phase/--plan/--duration/--tasks/--files` y `--phase/--summary`. La primera decision se anadio con el placeholder `[Phase ?]` y se corrigio a mano a `[Phase 01]` en `STATE.md`.
- **`char-junit.xml` se elimino con `pathlib`**, no con `rm`, tal y como exige W5: en el host Windows `subprocess.run(['rm', ...])` lanzaria `FileNotFoundError`. `git status` quedo limpio.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **La Fase 4 (POOL-01…POOL-07) ya tiene su red de seguridad.** Cualquier refactor del pool debe hacer fallar estas aserciones y luego actualizarlas (nunca borrarlas); la tabla "Aserciones que se esperan INVERTIR" nombra el requisito responsable de cada inversion.
- **La Fase 1 queda con los 5 planes completos** (01-01…01-05). La suite local pasa a **553** y el gate JUnit sigue en 0 skips.
- **Recordatorio para todo fichero nuevo:** debe nacer `ruff check`/`ruff format`-clean, mypy-clean bajo el ratchet y libre de warnings (la suite corre con `filterwarnings = ["error"]`).

---

*Phase: 01-safety-net-ci-gates-test-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `tests/test_pool_characterization.py` existe en disco.
- Los commits `9314a57`, `78193ca` y `66a7e88` existen en el historial.
- El fichero contiene las cinco clases: `TestPoolCheckoutCap`, `TestPoolAcquireOvershootRace`, `TestPoolLastIdScoping`, `TestPoolReleaseSemantics`, `TestPoolClose` (grep = 5).
- `uv run pytest -q` → `553 passed`; `uv run pytest tests/test_pool_characterization.py -q` → `19 passed`.
- `check_skips.py char-junit.xml` → `OK: 0 tests omitidos.`; `git diff --stat -- encino_orm/pool.py tests/test_pool.py` → sin salida.
- `uv run ruff check tests tools` → exit 0; `uv run ruff format --check tests tools` → exit 0; `uv run mypy encino_orm` → exit 0.
