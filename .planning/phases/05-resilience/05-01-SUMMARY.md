---
phase: 05-resilience
plan: 01
subsystem: database
tags: [resilience, disconnect, lock, drivers, asyncpg, aiomysql, pyodbc, oracledb, aiosqlite]

# Dependency graph
requires:
  - phase: 04-pool
    provides: "PooledConnection + contador de generación (no usado por este plan; dependencia declarada por la fase)"
provides:
  - "Db.is_disconnect_error(exc) -> bool (hook por defecto False)"
  - "is_disconnect_error por adaptador en los seis motores, mutuamente excluyente con is_lock_error"
  - "tests/_resilience_helpers.py: builders de excepciones por motor + FakeResilientDb (Wave 0 de la fase)"
  - "Bloque RESL-01 de tests/test_resilience.py y par disconnect/lock en los seis tests/test_{motor}.py"
affects: [05-02, 05-03, 05-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Clasificación por señal TIPADA del driver (errno/SQLSTATE/tipo/.full_code); substring solo como refuerzo en MSSQL HY000"
    - "Exclusión mutua disconnect/lock como invariante de corrección (lock -> retry(), disconnect -> reconexión)"
    - "Importación diferida: los drivers opcionales (pyodbc/oracledb) no se importan a nivel de módulo"

key-files:
  created:
    - tests/_resilience_helpers.py
    - tests/test_resilience.py
  modified:
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_postgresql.py
    - tests/test_mssql.py
    - tests/test_oracle.py

key-decisions:
  - "MSSQL: `args[1]` puede ser tupla (dobles) o string (pyodbc real); la extracción del mensaje acepta ambas formas y cae a `str(exc)`"
  - "Oracle: `from oracledb import exceptions` (el atributo `oracledb.exceptions` no existe tras `import oracledb`)"
  - "FakeResilientDb define los públicos con un puente que reenvía al template method cuando 05-02 lo añade"

patterns-established:
  - "Predicado puro de clasificación por adaptador, junto a is_lock_error, con extracción defensiva de args"
  - "Builders de excepciones de driver con firmas reales para tests sin servidor"

requirements-completed: [RESL-01]

# Metrics
duration: 5min
completed: 2026-09-19
---

# Phase 5 Plan 01: Resilience Summary

**`is_disconnect_error` por adaptador en los seis motores (SQLite, MySQL/MariaDB, PostgreSQL, MSSQL, Oracle), con exclusión mutua probada frente a `is_lock_error` y la infraestructura de tests determinista de la fase**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-19T04:46:36Z
- **Completed:** 2026-09-19T04:51:46Z
- **Tasks:** 3 (Task 2 en ciclo TDD: RED + GREEN)
- **Files modified:** 14 (2 creados, 12 modificados)

## Accomplishments

- `Db.is_disconnect_error(exc) -> False` (hook concreto, análogo a `is_lock_error`) y clasificadores reales en los cinco adaptadores con driver propio.
- Clasificación por señal tipada: SQLite (ProgrammingError closed-db / OperationalError disk I/O); MySQL/MariaDB (`InterfaceError` + errno 2006/2013/2055); PostgreSQL (tipos asyncpg `ConnectionDoesNotExistError`/`PostgresConnectionError`/`InterfaceError`); MSSQL (SQLSTATE `08xxx` o `HY000` no-lock con substring verificado); Oracle (`code` en la lista o `full_code` DPY-4011).
- Exclusión mutua probada: los errnos/SQLSTATE/códigos de lock (1213/1205, 1205/1222, ORA-60/54/8177, `locked`/`busy`) quedan explícitamente FUERA del clasificador de disconnect; `InvalidCachedStatementError` no es ni disconnect ni lock.
- `tests/_resilience_helpers.py` listo como Wave 0: builders con firmas reales + variantes `real_*` para `optional_engine` + `FakeResilientDb` con `fail_first`/`disconnect`/`lock`/`tx` y contadores.
- Contrato de importación diferida preservado: `base.py` no importa drivers y `mssql.py`/`oracle.py` no importan `pyodbc`/`oracledb` a nivel de módulo.

## Task Commits

Each task was committed atomically:

1. **Task 1: `tests/_resilience_helpers.py` — builders + FakeResilientDb** — `87ed441` (test)
2. **Task 2: `is_disconnect_error` en los seis motores (TDD)** — `740b971` (test, RED) → `645e4f2` (feat, GREEN)
3. **Task 3: par disconnect/lock por motor + herencia MariaDB** — `43fbbed` (test)

**Plan metadata:** (pendiente) docs(05-01): complete resilience plan

## Files Created/Modified

- `encino_orm/base.py` — hook concreto `is_disconnect_error` por defecto `False`, con docstring de exclusión mutua con lock.
- `encino_orm/sqlite.py` — clasificador closed-db / disk I/O / unable-to-open; `locked`/`busy` fuera.
- `encino_orm/mysql.py` — `_DISCONNECT_ERRNOS = (2006, 2013, 2055)` + `InterfaceError`; 1213/1205 fuera. Heredado por MariaDB.
- `encino_orm/postgresql.py` — clasificador por tipos asyncpg; `InvalidCachedStatementError` excluido.
- `encino_orm/mssql.py` — SQLSTATE `08xxx` o `HY000`/`40001` no-lock con substring verificado; sin importar `pyodbc`.
- `encino_orm/oracle.py` — `_ORA_DISCONNECT_CODES` + `_ORA_DISCONNECT_DPY` (lee `full_code`); rama `InterfaceError` defensiva con `self._oracledb`.
- `tests/_resilience_helpers.py` (nuevo) — builders por motor, variantes `real_*`, `FakeResilientDb`.
- `tests/test_resilience.py` (nuevo) — bloque RESL-01: 34 tests (parametrizados por motor + exclusión mutua + optional_engine).
- `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` — `test_is_disconnect_error` por motor + assert local de exclusión mutua; MariaDB verifica la herencia por identidad.

## Decisions Made

- **MSSQL, extracción del mensaje robusta:** `pyodbc.Error` real expone `args = (sqlstate, "mensaje")` (string), mientras que los dobles usan `(sqlstate, (code, "mensaje"))`. La implementación acepta tupla o string y cae a `str(exc)`; esto cubre la firma real sin romper los dobles.
- **Oracle, import explícito del subpaquete:** `oracledb.exceptions` no queda expuesto como atributo tras `import oracledb` en la versión instalada (4.0.2); `real_oracle_disconnect` usa `from oracledb import exceptions`. Se mantiene dentro de la función (importación diferida).
- **FakeResilientDb, puente 05-01→05-02:** se documenta abajo como desviación.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `FakeResilientDb` no era instanciable con solo los métodos privados en 05-01**
- **Found during:** Task 1 (`tests/_resilience_helpers.py`)
- **Issue:** El plan define `FakeResilientDb(Db)` con implementaciones `_execute`/`_fetch_*` y `exists`, pero en 05-01 `Db.execute`/`execute_insert`/`fetch_all`/`fetch_one`/`fetch_many` siguen siendo `@abstractmethod` (el rename a `_`-prefijados es 05-02). Sin implementar los públicos, la instanciación falla con `TypeError: Can't instantiate abstract class`, incumpliendo el criterio de aceptación de la Task 1.
- **Fix:** Se añadieron los cinco métodos públicos con un puente basado en `_DB_CON_TEMPLATE = hasattr(Db, "_with_reconnect")`. Hoy (05-01) delegan en los privados; cuando 05-02 añada el template method, reenvían a `super()` para NO saltarse la clasificación/reconexión. Así el helper queda listo para 05-02/03/04 sin editar la infraestructura.
- **Files modified:** tests/_resilience_helpers.py
- **Verification:** `FakeResilientDb(fail_first=0)` se instancia y `asyncio.run(f.exists(None))` funciona; `uv run pytest tests/test_resilience.py -q` verde.
- **Committed in:** `87ed441` (Task 1)

**2. [Rule 1 - Bug] `grep -c "unittest.mock"` debía ser 0 y las docstrings contenían el literal**
- **Found during:** Task 1 (verificación de aceptación)
- **Issue:** Las docstrings decían "sin `unittest.mock`"/"No usa `unittest.mock`", de modo que el grep de aceptación devolvía 2 en vez de 0.
- **Fix:** Se reformularon a "sin dobles automáticos de la stdlib" / "No usa dobles automáticos".
- **Files modified:** tests/_resilience_helpers.py
- **Verification:** `grep -c "unittest.mock"` == 0.
- **Committed in:** `87ed441` (Task 1)

**3. [Rule 1 - Bug] PT006 en `tests/test_resilience.py` y formato ruff**
- **Found during:** Task 2 (gate `ruff check`)
- **Issue:** `pytest.mark.parametrize("a, b", ...)` dispara PT006 (se espera una tupla de nombres).
- **Fix:** Argnames como tupla (`("db_cls", "exc_factory")`) y `ruff format`.
- **Files modified:** tests/test_resilience.py
- **Verification:** `uv run ruff check encino_orm tests` y `uv run ruff format --check encino_orm tests` salen 0.
- **Committed in:** `645e4f2` (Task 2)

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 bugs)
**Impact on plan:** El puente de `FakeResilientDb` es la única desviación de diseño; es necesaria para satisfacer el criterio de aceptación de 05-01 y deja el helper operativo para 05-02. Las otras dos son ajustes de verificación/estilo. Sin scope creep.

## Issues Encountered

- Los seis contenedores Docker estaban arriba, así que se pudo correr la suite completa (incluida integración) como gate de cierre: 950 passed. No se detectó regresión del camino de lock.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RESL-01 completo: `is_disconnect_error` listo para que 05-02 lo consuma desde `_with_reconnect`.
- `tests/_resilience_helpers.py` ya expone `FakeResilientDb` con `fail_first`, `disconnect`, `lock`, `tx`, contadores y `_connect_kwargs`/`_connected_at`, sin necesidad de editar la infraestructura en 05-02/03/04.
- `is_lock_error` y `retry()` intactos; `TestD4AutoRetry` y los tests de lock siguen verdes.
- Gate `uv run mypy encino_orm` sin cambios (ratchet sin tocar); `pyproject.toml`/`uv.lock` intactos.

## Self-Check

- [x] `tests/_resilience_helpers.py` existe y `FakeResilientDb` es instanciable
- [x] `tests/test_resilience.py` existe con 34 tests RESL-01
- [x] Los seis adaptadores exponen `is_disconnect_error`
- [x] `uv run pytest -q` → 950 passed
- [x] `uv run pytest -q -m "not integration and not optional_engine"` → 862 passed
- [x] `uv run ruff check encino_orm tests` → 0; `uv run ruff format --check encino_orm tests` → 0
- [x] `uv run mypy encino_orm` → Success
- [x] Commits `87ed441`, `740b971`, `645e4f2`, `43fbbed` presentes

## Self-Check: PASSED

---
*Phase: 05-resilience*
*Completed: 2026-09-19*
