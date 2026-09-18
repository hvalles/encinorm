---
phase: 03-data-correctness
plan: 05
subsystem: database
tags: [cache, lru, ordereddict, memory-cache, dev-test-contract, data-correctness, mypy]

# Dependency graph
requires: []
provides:
  - "MemoryCacheBackend acotado con LRU (OrderedDict + move_to_end + popitem(last=False), max_size=1024 por defecto)"
  - "Docstring con el contrato dev/test-only y la limitacion de invalidacion no distribuida (D-14)"
  - "tests/test_cache_backend.py DB-free: LRU, max_size, len(_store), delete y expiracion TTL"
affects: [03-04-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LRU en stdlib: OrderedDict.move_to_end marca uso y popitem(last=False) desaloja la menos usada en O(1)"
    - "Cota por while len(store) > max_size (desaloja hasta respetar el limite), no un if de una sola expulsion"

key-files:
  created:
    - tests/test_cache_backend.py
  modified:
    - encino_orm/model/cache_backend.py

key-decisions:
  - "LRU puro con max_size=1024 por defecto (D-13): sin purga de expirados antes de desalojar, como se decidio"
  - "El contrato dev/test-only se declara en el docstring de la clase, en espanol y sin secciones Args/Returns (D-14)"
  - "Se anota _store como OrderedDict[str, tuple[bytes, float | None]]: anotar max_size convierte __init__ en funcion tipada y activa el chequeo de cuerpo de mypy (el modulo no estaba en el ratchet)"

patterns-established:
  - "Backend en memoria acotado: get y set actualizan la recencia; la cota es defensa contra crecimiento sin limite (Pitfall 17)"

requirements-completed: [DATA-04]

# Metrics
duration: 5min
completed: 2026-09-18
---

# Phase 3 Plan 5: MemoryCacheBackend LRU + dev/test contract Summary

**`MemoryCacheBackend` ahora es un `OrderedDict` acotado con LRU (`max_size=1024` por defecto, `move_to_end` en `get`/`set`, `popitem(last=False)` al desbordar) y su docstring declara explicitamente el contrato dev/test-only.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-18T17:41:15Z
- **Completed:** 2026-09-18T17:46:24Z
- **Tasks:** 1
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- `MemoryCacheBackend._store` deja de ser un `dict` sin cota: pasa a `OrderedDict` y gana `__init__(max_size=1024)`, eliminando la acumulacion indefinida de claves nunca releidas (Pitfall 17).
- `get` marca la entrada como recientemente usada con `move_to_end` **solo si sigue viva** (la ruta de expiracion sigue haciendo `pop` y devolviendo `None`); `set` escribe, mueve al final y desaloja con `while len(store) > max_size: popitem(last=False)`.
- El docstring declara el contrato dev/test-only: backend en memoria, una instancia por proceso, invalidacion local no distribuida, y `RedisCacheBackend` para produccion (D-14).
- `tests/test_cache_backend.py` cubre LRU (desaloja la menos usada, no la mas antigua por insercion), `max_size`, `_max_size` por defecto, `len(_store)`, `delete` y expiracion TTL con reloj inyectado.

## Task Commits

Each task was committed atomically:

1. **Task 1: LRU acotado en `MemoryCacheBackend` (D-13/D-14)** - `2984c21` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `encino_orm/model/cache_backend.py` - `OrderedDict` import; `__init__(max_size=1024)` con `_store` anotado; `get`/`set` con `move_to_end`; desalojo LRU; docstring dev/test-only. `RedisCacheBackend` intacto.
- `tests/test_cache_backend.py` - 6 tests DB-free (`@pytest.mark.asyncio` explicito), sin fixtures de BD.

## Decisions Made
- LRU puro con `max_size=1024` (D-13): se descarta la purga de expirados antes de desalojar, tal como se decidio; la expiracion se sigue evaluando solo al releer la misma clave.
- El contrato dev/test vive en el docstring de la clase (D-14); la documentacion de usuario (`docs/guide.md`) es de 03-04.
- `_store` se anota explicitamente porque la firma tipada de `__init__` activa el chequeo de cuerpo de mypy en un modulo que no estaba en el ratchet.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `_store` sin anotacion de tipo rompia el gate de mypy**
- **Found during:** Task 1 (LRU acotado en `MemoryCacheBackend`)
- **Issue:** `uv run mypy encino_orm` fallo con `encino_orm\model\cache_backend.py:23: error: Need type annotation for "_store" [var-annotated]`. El `__init__` original era totalmente sin anotaciones (mypy no revisaba su cuerpo); al anotar `max_size: int` la funcion pasa a ser tipada y el cuerpo se chequea, exponiendo el `OrderedDict()` sin parametrizar.
- **Fix:** `self._store: OrderedDict[str, tuple[bytes, float | None]] = OrderedDict()`. Sin `# type: ignore`, preservando el invariante `noqa`=0 y el conteo de supresiones inline en 0.
- **Files modified:** `encino_orm/model/cache_backend.py`
- **Verification:** `uv run mypy encino_orm` → `Success: no issues found in 60 source files`.
- **Committed in:** `2984c21` (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/type)
**Impact on plan:** Necesario para mantener el gate de tipos verde; no cambia el comportamiento ni el alcance.

## Issues Encountered
- La corrida completa de la suite local reporto `770 passed, 36 skipped` (806 recolectados), frente a `741 passed, 59 skipped` de 03-03. La diferencia de skips (23) es ambiental (disponibilidad de los servicios de motor/Redis en la maquina local), no un cambio de comportamiento del codigo: 0 fallos y los 6 tests nuevos pasan.
- `state.record-metric`/`state.add-decision` no aceptan la forma posicional del agente (`phase plan duration tasks files`); se invocaron con flags (`--phase --plan --duration --tasks --files` y `--phase --summary`), que es la forma que documenta `execute-plan.md`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DATA-04 (parte de codigo) entregado: la cota LRU y el contrato dev/test-only estan en el codigo y con tests.
- 03-04 (docs) puede describir el contrato real (`MemoryCacheBackend(max_size=1024)` con LRU, invalidacion local) y el `CHANGELOG.md`.
- Sin blockers. `RedisCacheBackend` no se toco (Redis ya acota y expira).

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- `encino_orm/model/cache_backend.py` y `tests/test_cache_backend.py` existen en disco.
- El commit de tarea `2984c21` existe en el historial.
- `uv run pytest tests/test_cache_backend.py tests/test_cached_model.py -q` → 15 passed.
- `uv run pytest -q` → 770 passed, 36 skipped, 0 failed.
- `uv run ruff check encino_orm tests` / `ruff format --check encino_orm tests` / `uv run mypy encino_orm` → exit 0; `noqa` en `encino_orm/` = 0.
- Greps de aceptacion: `OrderedDict`=2, `move_to_end`=2, `popitem(last=False)`=1, `max_size`=4, `dev/test`=1.
