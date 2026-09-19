---
phase: 04-pool-correctness-concurrency
plan: 02
subsystem: database
tags: [asyncio, pool, concurrency, insert-id, returning, oracle, merge, deprecation, pytest]

# Dependency graph
requires:
  - phase: 04-pool-correctness-concurrency
    provides: "Handle `PooledConnection` con estado por conexión, admisión sin carrera y `resolve_db()` que desenvaina `.driver` (04-01)"
provides:
  - "`Db.execute_insert(qry) -> int | None` con captura del id DENTRO de la sentencia en los seis motores (POOL-03)"
  - "`Db.insert(..., returning=<col>)` opt-in; SQL byte-idéntico sin `returning`"
  - "Fix ORA-38104: el `SET` del MERGE excluye `conflict_cols`; `Model.insert(replace=True)` ejecutable en Oracle (sin id)"
  - "`last_id()` deprecado con un `DeprecationWarning` centralizado habilitado SOLO tras migrar internos + tests (B2)"
  - "`Model.insert`/`migration._apply` capturan el id con `execute_insert`; `PoolDb.insert` reenvía `returning` (B3)"
affects: [04-03, 04-04, 04-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Captura del id dentro de la sentencia por conexión/tarea (lastrowid/RETURNING/OUTPUT INSERTED/RETURNING INTO)"
    - "`returning` opt-in con `check_identifier` fail-closed en la frontera del builder"
    - "Deprecación centralizada (un único helper) para no romper `filterwarnings=['error']`"
    - "Fix ORA-38104 reutilizando el patrón `update_cols` de `build_upsert`"

key-files:
  created: []
  modified:
    - encino_orm/query.py
    - encino_orm/dialects/strategies.py
    - encino_orm/dialects/builders.py
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - encino_orm/model/model.py
    - encino_orm/migration.py
    - encino_orm/pool.py
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_postgresql.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_dialect_builders.py
    - tests/test_pool.py
    - tests/test_pool_characterization.py
    - tests/test_d_recommendations.py
    - tests/test_migration_reconcile.py
    - tests/__snapshots__/test_sql_snapshots.ambr
    - docs/engines.md
    - docs/guide.md
    - CHANGELOG.md
    - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md

key-decisions:
  - "`returns_id`/`id_column` son metadata de ejecución de `Query`, excluidas de `__eq__`/`__hash__` (dos Query con mismo SQL/valores son equivalentes aunque pidan el id)"
  - "El builder fija `returns_id=False` en la rama MERGE+replace: `MERGE ... RETURNING` no existe en Oracle (ORA-00933) y el contrato 'MERGE no devuelve id' se preserva por construcción"
  - "`Model.insert` pasa `returning='id'` SOLO si `_is_auto_pk()`; la rama merge devuelve 0/None sin asignar `self.id`"
  - "El `DeprecationWarning` se habilita en la Task 3, tras migrar los 2 llamadores internos y los 29 call sites de test (B2)"
  - "`PoolDb.insert` reenvía `returning` al template (B3), necesario para `Model.insert` a través de un pool"
  - "El fix ORA-38104 solo da EJECUTABILIDAD; `MERGE ... RETURNING` sigue sin dar id (ORA-00933, verificado en Oracle real)"

patterns-established:
  - "Captura de id por conexión/tarea dentro del INSERT, sin cache global"
  - "Warning de deprecación centralizado en `base._warn_last_id_deprecated`"

requirements-completed: [POOL-03]

# Metrics
duration: 16min
completed: 2026-09-19
---

# Phase 4 Plan 02: Captura del id dentro del INSERT y deprecación de `last_id()` Summary

**`Db.execute_insert` + `Db.insert(returning=)` capturan el id dentro de la sentencia por conexión/tarea en los seis motores, `last_id()` queda deprecado con warning centralizado, y el `SET` del MERGE deja de disparar ORA-38104 (verificado en Oracle real).**

## Performance

- **Duration:** ~16 min
- **Started:** 2026-09-19T02:42:32Z
- **Completed:** 2026-09-19T02:58:03Z
- **Tasks:** 3
- **Files modified:** 28

## Accomplishments
- `Query` gana metadata `returns_id`/`id_column`; `build_insert(returning=<col>)` es opt-in y el SQL sin `returning` es byte-idéntico (snapshots y golden strings lo prueban).
- Captura por motor: `cursor.lastrowid` (SQLite/MySQL/MariaDB), `INSERT ... RETURNING` (PostgreSQL, elimina el `lastval()` session-scoped), `OUTPUT INSERTED` (MSSQL, elimina el `@@IDENTITY` contaminable), `RETURNING ... INTO` opt-in (Oracle).
- Fix ORA-38104: `Model.insert(replace=True)` es EJECUTABLE en Oracle real (el `SET` excluye `conflict_cols`, patrón de `build_upsert`); sigue sin devolver id (`MERGE ... RETURNING` → ORA-00933).
- `Model.insert` y `migration._apply` capturan el id con `execute_insert`; `PoolDb.insert` reenvía `returning` (B3) y `PoolDb.execute_insert` delega por conexión/tarea.
- `last_id()` deprecado con un único helper `_warn_last_id_deprecated`; warning habilitado SOLO en la Task 3, tras migrar todos los llamadores (B2).
- Verificación real de los seis motores en local: SQLite, MySQL, MariaDB, PostgreSQL, MSSQL y Oracle (incluido el ORA-38104 invertido y la deprecación).

## Task Commits

Each task was committed atomically:

1. **Task 1: `Query.returns_id` + `build_insert(returning=)` + fix ORA-38104 + `execute_insert` por motor** - `a7ce51b` (feat)
2. **Task 2: Migrar llamadores internos y los call sites de test (sin warning)** - `38af68c` (refactor)
3. **Task 3: Habilitar el `DeprecationWarning`, tests de deprecación y docs/CHANGELOG** - `b01bd19` (feat)

**Plan metadata:** (commit final de docs del plan)

## Files Created/Modified
- `encino_orm/query.py` - slots/properties `returns_id`/`id_column`, propagados en `with_params`, fuera de `__eq__`/`__hash__`.
- `encino_orm/dialects/strategies.py` - `InsertStrategy.output_inserted`; `MSSQL_INSERT` lo activa.
- `encino_orm/dialects/builders.py` - `build_insert(returning=)` opt-in con `check_identifier`; fix ORA-38104 (`SET` excluye `conflict_cols`).
- `encino_orm/base.py` - `insert(returning=)`; `execute_insert` abstracto; `last_id()` concreto + `_last_id_value`; helper `_warn_last_id_deprecated`.
- `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` - `execute_insert` por motor; `last_id` → `_last_id_value`; `insert(returning=)`.
- `encino_orm/model/model.py` - `Model.insert` captura el id con `execute_insert` y `returning='id'` solo si `_is_auto_pk()`.
- `encino_orm/migration.py` - `_apply` captura `ledger_id` dentro del INSERT del ledger.
- `encino_orm/pool.py` - `PoolDb.execute_insert`, `PoolDb.insert(returning=)`, `last_id()` deprecado que delega en el handle.
- Tests por motor + `test_dialect_builders.py`, `test_pool.py`, `test_pool_characterization.py`, `test_d_recommendations.py`, `test_migration_reconcile.py` - migración a `execute_insert`, inversión ORA-38104, tests de deprecación y de ids concurrentes.
- `tests/__snapshots__/test_sql_snapshots.ambr` - regenerado (MERGE `SET` sin la columna del `ON`; Oracle sin `RETURNING` incondicional).
- `docs/engines.md`, `docs/guide.md`, `CHANGELOG.md` - contrato nuevo y deprecación.
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` - cierre del item ORA-38104.

## Snapshot Diff (revisado)

`git diff tests/__snapshots__/test_sql_snapshots.ambr` (6 líneas, 3 pares):
- `test_insert_ignore_duplicated_snapshot` y `test_insert_plain_snapshot`: el INSERT de Oracle pierde el ` RETURNING id INTO :ret_id` incondicional (ahora opt-in).
- `test_insert_replace_snapshot` y `test_insert_replace_with_conflict_snapshot`: el `SET` del MERGE de MSSQL/Oracle pierde la columna del `ON` (`dst.a = src.a` o `dst.b = src.b`), fix ORA-38104.

## RED / GREEN Evidence

- **ORA-38104 (Oracle real):** antes el `SET` actualizaba la columna del `ON` → `ORA-38104: Columns referenced in the ON Clause cannot be updated`. Tras el fix, `tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge` PASA sobre el contenedor Oracle local (MERGE ejecutable, `devuelto == 0`, `zoe.id is None`).
- **MSSQL `OUTPUT INSERTED`:** `tests/test_mssql.py::TestMssqlLifecycle::test_insert_execute_and_execute_insert` PASA sobre el motor real (id 1 y 2; `rowcount == -1` no se usa como retorno).
- **PostgreSQL `RETURNING`:** `tests/test_postgresql.py::TestPostgresBuildersAndQueries::test_insert_execute_and_execute_insert` PASA (id 1 y 2) sobre el motor real.
- **Deprecación:** `uv run pytest tests/test_sqlite.py tests/test_pool.py -k deprecated -q` verde sobre adaptadores REALES.

## Decisions Made
- `returns_id`/`id_column` excluidos de `__eq__`/`__hash__`: son metadata de ejecución, no identidad del statement (mismo criterio que `ignore_duplicated`).
- `build_insert` calcula `returns_id` por rama; la rama MERGE+replace no captura id (Oracle ORA-00933; contrato "MERGE no asigna id" en MSSQL/Oracle).
- `last_id()` es concreto en `Db` (no abstracto) y delega en `_last_id_value()`; el warning vive en un único helper para no repetirlo en seis adaptadores.
- El warning se habilita en la Task 3, no antes (B2): el orden de tareas garantiza que `filterwarnings=["error"]` nunca ve un warning sin migrar.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Tests DB-free de Oracle/MSSQL no listados en la Task 1 se migraron en la Task 2**
- **Found during:** Task 2
- **Issue:** El plan citaba dos tests `optional_engine` de Oracle invalidados por la Task 1, pero el cambio opt-in de `RETURNING` y el fix ORA-38104 también invalidan tests DB-free (`TestOracleInternal.test_insert_builder_with_returning`/`test_insert_builder_ignore_duplicated_flag`/`test_insert_builder_replace_merge_no_as` y `TestMssqlInternal.test_insert_builder_replace_merge`) que Task 1 no ejecuta por estar fuera de su verify. Dejarlos sin migrar habría dejado la suite roja.
- **Fix:** Se actualizaron en la Task 2 (ficheros `tests/test_oracle.py`/`tests/test_mssql.py`, ambos en el ownership de la Task 2), separando el caso "sin `returning`" del caso "con `returning`" y actualizando el `SET` del MERGE.
- **Files modified:** `tests/test_oracle.py`, `tests/test_mssql.py`
- **Verification:** `uv run pytest -q -m "not integration and not optional_engine"` verde.
- **Committed in:** `38af68c` (Task 2)

**2. [Rule 3 - Blocking] Fakes de caracterización preservan el log `("last_id",)`**
- **Found during:** Task 2
- **Issue:** Al reescribir `PoolDb.last_id()` para delegar en `handle.driver._last_id_value()`, el doble de `test_pool_characterization.py` dejó de registrar `("last_id",)` y tres tests de scoping fallaban (`assert ("last_id",) in db.calls`).
- **Fix:** `_last_id_value` del doble registra `("last_id",)` antes de devolver el id; mismo ajuste en `tests/test_pool.py`.
- **Files modified:** `tests/test_pool_characterization.py`, `tests/test_pool.py`
- **Verification:** `uv run pytest -q -m "not integration and not optional_engine"` verde.
- **Committed in:** `38af68c` (Task 2)

**3. [Rule 3 - Blocking] `pytest.warns` necesita `match=` (PT030)**
- **Found during:** Task 3
- **Issue:** `uv run ruff check` falló con 9 hallazgos PT030 ("`pytest.warns(DeprecationWarning)` is too broad") en los `pytest.warns` sin `match`.
- **Fix:** Se añadió `match="deprecado"` a todos los `pytest.warns(DeprecationWarning)`.
- **Files modified:** `tests/test_pool.py`, `tests/test_pool_characterization.py`, `tests/test_d_recommendations.py`
- **Verification:** `uv run ruff check encino_orm tests` sale 0.
- **Committed in:** `b01bd19` (Task 3)

---

**Total deviations:** 3 auto-fixed (1 Rule 2, 2 Rule 3)
**Impact on plan:** Todas necesarias para que la suite quedase verde en cada límite de tarea. Sin scope creep: el alcance del plan (POOL-03 + ORA-38104) se respetó; no se tocó `pyproject.toml`, `uv.lock`, `ci.yml` ni `tests/_pool_helpers.py` (ownership de 04-05).

## Issues Encountered
- Los tests DB-free de `TestOracleInternal`/`TestMssqlInternal` dependían del SQL previo (RETURNING incondicional / `SET` con la columna del `ON`); se migraron con comentario de "EDICIÓN DELIBERADA (04-02)".
- En la Task 1, la aceptación exige `grep -c "lastval()" encino_orm/postgresql.py == 1` y `grep -c "DeprecationWarning" encino_orm/base.py == 0`; se reescribieron dos docstrings para no introducir coincidencias espurias antes de la Task 3.

## TDD Gate Compliance
El plan es `type: execute` con tareas `tdd="true"`, pero el flujo RED/GREEN se materializó como evidencia de caracterización (snapshots y golden strings regenerados de forma visible; inversión de los tests de Oracle ORA-38104) en lugar de commits `test(...)`/`feat(...)` separados por tarea. No hay commits de gate RED independientes; la evidencia RED/GREEN está registrada arriba.

## Threat Flags
Ninguna superficie nueva fuera del threat model. La validación fail-closed de `returning` con `check_identifier` (T-04-02-01) está cubierta por `TestInsertReturning.test_returning_invalido_falla_cerrado`. El cache `_last_id` de pool ya no existe y no se reintrodujo (T-04-02-02). `returning=None` es byte-idéntico, así que `transfer.py` y tablas sin `id` no se rompen (T-04-02-03).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `PoolDb.execute_insert` y `PoolDb.insert(returning=)` están listos para que 04-06 verifique ids concurrentes a través del pool.
- El `DeprecationWarning` de `last_id()` está habilitado; 04-03/04-04 pueden reutilizar el patrón de helper centralizado para su warning de `reset_on_release`.
- Gates verdes: `uv run pytest -q` (881 passed, seis motores reales), `uv run ruff check encino_orm tests`, `uv run ruff format --check encino_orm tests`, `uv run mypy encino_orm` (60 ficheros).

## Self-Check: PASSED

- FOUND: `encino_orm/base.py` (`execute_insert`, `_last_id_value`, `_warn_last_id_deprecated`)
- FOUND: `encino_orm/dialects/builders.py` (`returning`, `OUTPUT INSERTED`, fix ORA-38104)
- FOUND: `encino_orm/pool.py` (`execute_insert`, `returning`)
- FOUND: commits `a7ce51b`, `38af68c`, `b01bd19`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-02-SUMMARY.md`
