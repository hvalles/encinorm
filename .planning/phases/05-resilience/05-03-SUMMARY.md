---
phase: 05-resilience
plan: 03
subsystem: database
tags: [resilience, pre_ping, max_connection_lifetime, monotonic, sqlite, mysql, postgresql, mssql, oracle]

# Dependency graph
requires:
  - phase: 05-resilience
    provides: "05-02 — `_with_reconnect` template method + `_reconnect`/`_is_reconnectable`/`_connect_kwargs`/`_connected_at`"
provides:
  - "`Db.pre_ping` / `Db.max_connection_lifetime` (opt-in, defaults `False`/`None`)"
  - "`Db._resilience_opts` — pop de las opciones antes de guardar/reenviar kwargs al driver"
  - "`Db._should_recycle` — reciclado por EDAD de conexión con `time.monotonic()`"
  - "`Db._maybe_recycle` enganchado al entrar en `_with_reconnect`"
  - "Wiring de `_resilience_opts` en los cinco `connect()` con driver propio"
affects: [05-04, 06, 07, 08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chequeo proactivo PEREZOSO y por operación (sin daemon/`asyncio.Task`)"
    - "`time.monotonic()` como único reloj de edad (mismo que el pool)"
    - "Opt-in por kwargs de `connect()`, nunca por constructor"
    - "Pop de opciones ANTES de reenviar kwargs al driver"

key-files:
  created: []
  modified:
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - tests/test_resilience.py

key-decisions:
  - "Defaults conservadores pre_ping=False / max_connection_lifetime=None: pre_ping añade un round-trip por operación y el coste es opt-in"
  - "max_connection_lifetime mide EDAD de conexión (semántica pool_recycle), no inactividad; la inactividad es del reaper del pool (Fase 4)"
  - "_resilience_opts hace pop ANTES de guardar en _connect_kwargs y reenviar al driver; un valor <= 0 falla cerrado con ValueError"
  - "_maybe_recycle reconecta INMEDIATAMENTE cuando is_alive() es False (Pitfall 5), y es no-op con _connected_at is None"
  - "El chequeo vive al entrar en _with_reconnect: perezoso, sin daemon; el reciclado a nivel de pool queda para RELI-03 (v2)"

patterns-established:
  - "Política de reciclado opt-in para conexiones directas, reutilizando is_alive() de los seis adaptadores"
  - "Tests de envejecimiento deterministas por asignación de _connected_at, sin temporizadores reales"

requirements-completed: [RESL-03]

# Metrics
duration: 3min
completed: 2026-09-19
---

# Phase 5 Plan 3: pre_ping + max_connection_lifetime Summary

**Política opt-in `pre_ping`/`max_connection_lifetime` para conexiones directas, con reciclado por edad en `time.monotonic()`, reconexión inmediata cuando la sonda falla y pop de las opciones antes de reenviar kwargs al driver.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-19T05:14:11Z
- **Completed:** 2026-09-19T05:16:44Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- `Db` expone `pre_ping`/`max_connection_lifetime` (opt-in), `_resilience_opts`, `_should_recycle` y `_maybe_recycle`, y el chequeo proactivo queda enganchado al entrar en `_with_reconnect` (RESL-03).
- Los cinco adaptadores con driver propio (SQLite/MySQL/PostgreSQL/MSSQL/Oracle) consumen las opciones antes de guardarlas en `_connect_kwargs` y de reenviarlas al driver; MariaDB hereda de `MysqlDb`.
- `pre_ping` reconecta INMEDIATAMENTE cuando `is_alive()` devuelve False (Pitfall 5) y el default `False` no sondea en el camino caliente (contador `is_alive_calls` caracterizado).
- `max_connection_lifetime` recicla por EDAD con `time.monotonic()`, es no-op sin conexión previa y falla cerrado (`<= 0` → `ValueError`); SQLite `:memory:` sigue rechazando el reciclado.
- `pool.py` intacto: las opciones llegan a cada conexión física vía `PoolDb(..., **conn_kwargs)` → `connect()` (A6).

## Task Commits

Each task was committed atomically:

1. **Task 1: pre_ping/max_connection_lifetime + `_resilience_opts`/`_should_recycle`/`_maybe_recycle` en base.py** - `99b0f22` (feat)
2. **Task 2: wiring de `_resilience_opts` en los cinco adaptadores** - `71232ef` (feat)
3. **Task 3: bloque RESL-03 en tests/test_resilience.py** - `0458927` (test)

**Plan metadata:** (este commit) docs(05-03): completa el plan de resiliencia RESL-03

## Files Created/Modified
- `encino_orm/base.py` - atributos de clase opt-in, `_resilience_opts`, `_should_recycle`, `_maybe_recycle`; enganche en `_with_reconnect`
- `encino_orm/sqlite.py` - `connect()` hace pop de las opciones antes de resolver `database`
- `encino_orm/mysql.py` - `connect()` hace pop antes de `aiomysql.connect(**kwargs)`
- `encino_orm/postgresql.py` - `connect()` hace pop antes de `asyncpg.connect(**kwargs)`
- `encino_orm/mssql.py` - `connect()` hace pop antes de construir `conn_str`
- `encino_orm/oracle.py` - `connect()` hace pop antes de construir `dsn`
- `tests/test_resilience.py` - clase `TestResilienceLifetime` (10 tests, selector `-k lifetime`)

## Decisions Made
- **Defaults conservadores** `pre_ping=False`/`max_connection_lifetime=None`: el coste de `pre_ping` es un round-trip por operación y debe ser opt-in.
- **Edad, no inactividad:** `max_connection_lifetime` usa `time.monotonic() - _connected_at` (semántica `pool_recycle`); la inactividad es del reaper del pool (Fase 4).
- **Pop antes del driver:** `_resilience_opts` devuelve el dict limpio para que `_connect_kwargs` no contenga las claves y `aiomysql`/`asyncpg`/`conn_str`/`dsn` no reciban datos de más.
- **Sin daemon:** el chequeo es perezoso y por operación, al entrar en `_with_reconnect`; sin `asyncio.Task`/`create_task`.
- **`_resilience_helpers.py` sin cambios:** `is_alive_calls` ya existía desde 05-01 (2 ocurrencias), así que no se editó.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] El comando `<verify>` del Task 1 instancia el ABC y falla**
- **Found during:** Task 1
- **Issue:** `uv run python -c "from encino_orm.base import Db; d=Db.__new__(Db); ..."` lanza `TypeError: Can't instantiate abstract class Db` (el `__new__` de `object` rechaza clases abstractas). El comando de verificación del plan era inválido por construcción.
- **Fix:** Se ejecutó el equivalente sin instanciar (`assert Db.pre_ping is False and Db.max_connection_lifetime is None`) y se conservaron los `grep` de aceptación, que son la comprobación real.
- **Files modified:** ninguno (solo cambió el comando de verificación).
- **Verification:** `uv run python -c "from encino_orm.base import Db; assert Db.pre_ping is False and Db.max_connection_lifetime is None; print('lifetime opts OK')"` sale 0.

**2. [Rule 1 - Bug] Los literales `time.time()`, `asyncio.Task` y `sleep` en docstrings rompían los greps de aceptación**
- **Found during:** Task 1 y Task 3
- **Issue:** Las anotaciones de los docstrings citaban literalmente `time.time()`/`asyncio.Task` (base.py) y `sleep` (test_resilience.py); los criterios de aceptación son `grep` literales y exigen 0 coincidencias.
- **Fix:** Se reformularon los comentarios ("nunca el reloj de pared", "sin daemon ni tarea de fondo", "sin temporizadores reales ni pausas") sin cambiar el comportamiento.
- **Files modified:** `encino_orm/base.py`, `tests/test_resilience.py`.
- **Verification:** los tres greps devuelven 0.

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Ambos son ajustes de verificación/redacción; no cambian el comportamiento ni el alcance. El diseño se ejecutó exactamente como estaba especificado.

## Issues Encountered
Ninguno. El flag `tdd="true"` del Task 1 se materializó con una sonda RED (`pre_ping`/`_resilience_opts` ausentes → `False False`) y GREEN tras implementar, porque el plan asigna el bloque de tests a la Task 3 (los `<files>` del Task 1 son solo `base.py`).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- RESL-03 completo; `05-04` (taxonomía pública + `_translate_exception`) puede consumir `_maybe_recycle`/`_reconnect` sin cambios.
- Gates de cierre verdes: `uv run pytest -q` (974 passed), `uv run ruff check encino_orm tests`, `uv run ruff format --check encino_orm tests`, `uv run mypy encino_orm` (Success, 60 files).
- `git diff --stat encino_orm/pool.py` vacío; `filterwarnings = ["error"]` intacto; sin dependencias nuevas.

---
*Phase: 05-resilience*
*Completed: 2026-09-19*

## Self-Check: PASSED
