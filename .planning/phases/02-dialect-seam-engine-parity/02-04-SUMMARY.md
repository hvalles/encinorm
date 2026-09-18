---
phase: 02-dialect-seam-engine-parity
plan: 04
subsystem: database
tags: [orm, aggregates, count, pagination, dialect-parity, integration-tests, tdd]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "Seam DML (`dialects/`) y `Query` inmutable con accesores tipados (02-02/02-03)"
provides:
  - "Los SIETE lectores de agregados aliasan `AS n` y leen `row[\"n\"]` (DIAL-03 completo, no 3 sitios)"
  - "Guard de fuente que falla si reaparece una lectura por texto de expresión"
  - "Tests de integración por motor para `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` + los 5 agregados del `QueryBuilder` en los 6 motores"
  - "`Model.search` delega la paginación en `fetch_many` (portable en MSSQL/Oracle)"
  - "`sync_schema` emite `ADD <col> <tipo>` (portable en los 6 motores)"
affects: [02-05, 03, 04, 07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Contrato de resultado de agregados independiente del motor: alias fijo `n` en minúsculas en el SQL, nunca normalización de claves en el adaptador"
    - "Paginación delegada al adaptador (`fetch_many`) en lugar de `LIMIT/OFFSET` inline en la capa ORM"
    - "Guard de fuente (texto sobre `encino_orm/**/*.py`) para impedir la reintroducción de un patrón prohibido"
    - "Fake de `Db` mínimo (`_RecordingDb`) para fijar la forma del SQL sin motor"

key-files:
  created:
    - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md
  modified:
    - encino_orm/base.py
    - encino_orm/model/model.py
    - encino_orm/model/query_builder.py
    - tests/test_aggregates.py
    - tests/test_query_builder.py
    - tests/test_postgresql.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_graphql.py

key-decisions:
  - "El alias del wrapper de conteo pasa de `_encino_orm_count` a `encino_orm_count`: Oracle rechaza identificadores que empiezan por `_` (ORA-00911)."
  - "La paginación de `Model.search` se delega en `fetch_many` en vez de emitir `LIMIT/OFFSET`: SQL Server y Oracle usan `OFFSET … FETCH NEXT` y solo el adaptador conoce su sintaxis."
  - "`sync_schema` emite `ADD <col> <tipo>` (sin la palabra `COLUMN`): es la forma válida en los seis motores."
  - "El filtro `name=` de `list_tables` queda fuera de alcance (roto en 4 de 6 motores por alias-en-WHERE); documentado en `deferred-items.md`."
  - "SQLite no lleva marker `integration`: sus aserciones de paridad corren en cada corrida como red de seguridad barata."

patterns-established:
  - "TDD en el arreglo del alias: commit RED de tests (bfaf4a4) seguido del commit GREEN de implementación (ccc8a8a)"
  - "Un único fake `_RecordingDb` por fichero de test unitario para verificar la forma del SQL agregado sin motor"

requirements-completed: [DIAL-03, DIAL-09]

# Metrics
duration: 8min
completed: 2026-09-18
---

# Phase 2 Plan 04: Alias `AS n` en los siete agregados + paridad por motor Summary

**Los siete lectores de agregados (`list_tables`, `Model.count` y `QueryBuilder.count/sum/avg/min/max`) aliasan la expresión como `n` y leen `row["n"]`; más tests de integración reales de `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` y de los cinco agregados del builder en los seis motores.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-18T04:37:02Z
- **Completed:** 2026-09-18T04:44:42Z
- **Tasks:** 3 (la tarea 1 con ciclo TDD RED → GREEN)
- **Files modified:** 12 (11 modificados, 1 creado)

## Accomplishments

- **DIAL-03 cumplido en su totalidad real (7 sitios, no 3).** El bug no era de `count`/`paginate`/`list_tables` sino de **todo lector de agregados**: `QueryBuilder.sum/avg/min/max` fallaban con el mismo `KeyError` en PostgreSQL, SQL Server y Oracle. Los siete sitios usan ahora el alias fijo `n` (minúsculas) y leen `row["n"]`. El arreglo vive en el SQL, **no** en la capa de fetch de ningún adaptador (Pitfall D).
- **Guard anti-regresión.** `tests/test_aggregates.py` recorre `encino_orm/**/*.py` y falla si reaparece `row["COUNT(*)"]` o `row[f"SUM(|AVG(|MIN(|MAX("`. Reintroducir un lector por expresión rompe el test.
- **DIAL-09 cumplido.** Los seis ficheros de motor (`test_sqlite/mysql/mariadb/postgresql/mssql/oracle.py`) ejercitan `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` contra el motor real, más `QueryBuilder.count/sum/avg/min/max`. Los seis motores corren en local y los tests se ejecutaron de verdad.
- **Tres bugs cross-engine preexistentes descubiertos y arreglados** (los tests de integración exigidos por el plan no podían pasar sin ellos): paginación `LIMIT/OFFSET` inline en `Model.search`, `ADD COLUMN` en `sync_schema` y el alias `_encino_orm_count`. Ver *Deviations*.
- Gates de Fase 1 intactos: `ruff check` / `ruff format --check` / `mypy encino_orm` salen 0; `noqa` sigue en 0; `filterwarnings = ["error"]` activo.
- Suite completa: **694 passed** (baseline 663 + 31 tests nuevos).

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): tests del alias de agregados** - `bfaf4a4` (test)
2. **Task 1 (GREEN): alias `AS n` en los 7 lectores** - `ccc8a8a` (feat)
3. **Task 2: paridad PG / MSSQL / Oracle + 3 fixes cross-engine** - `1a5d621` (test)
4. **Task 3: paridad SQLite / MySQL / MariaDB** - `fa59665` (test)

**Plan metadata:** `docs(02-04): complete ... plan` (hash en `git log`)

_Note: la tarea 1 siguió el ciclo TDD RED → GREEN (gate RED y GREEN presentes)._

## Files Created/Modified

- `encino_orm/base.py` - `list_tables` y `paginate` envuelven el conteo como `SELECT COUNT(*) AS n FROM (...) encino_orm_count` y leen `row["n"]`.
- `encino_orm/model/model.py` - `Model.count` con `AS n`; `Model.search` delega la paginación en `fetch_many`; `sync_schema` usa `ADD <col> <tipo>`.
- `encino_orm/model/query_builder.py` - `count`/`sum`/`avg`/`min`/`max` con `AS n` y lectura de `row["n"]` (semántica vacía preservada: `sum`→0, `avg`/`min`/`max`→None).
- `tests/test_aggregates.py` - `_RecordingDb`, forma `AS n` de `Model.count` y de los 5 agregados, semántica vacía, `Model.count`/`paginate` sobre SQLite y el guard de fuente.
- `tests/test_query_builder.py` - forma `AS n` de los agregados del builder; `test_count_sum_exists` ampliado con `avg`/`min`/`max`.
- `tests/test_postgresql.py`, `tests/test_mssql.py`, `tests/test_oracle.py` - clase `*Parity` con las cinco APIs + los cinco agregados del `QueryBuilder` contra el motor real.
- `tests/test_sqlite.py`, `tests/test_mysql.py`, `tests/test_mariadb.py` - la misma cobertura; SQLite además aserta `alter_types → NotImplementedError`.
- `tests/test_graphql.py` - `CountingDb` cuenta también `fetch_many` para seguir midiendo el N+1 tras delegar la paginación.
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` (nuevo) - el filtro `name=` de `list_tables` roto en 4 de 6 motores.

## Decisions Made

- **Alias `n` como contrato de resultado.** El label que devuelve cada driver no es estable (asyncpg minúsculas, `_rows.py:14` fuerza minúsculas en MSSQL/Oracle). El alias fijo en minúsculas en el SQL es la única solución correcta; se prohíbe normalizar claves en un adaptador.
- **`encino_orm_count` en vez de `_encino_orm_count`.** Oracle rechaza identificadores que empiezan por `_` salvo citados (ORA-00911). El alias nuevo es válido en los seis motores y se aplicó a `list_tables` y `paginate` a la vez.
- **Paginación delegada al adaptador.** `Model.search` usaba `LIMIT {n} OFFSET {m}` inline, inválido en SQL Server y Oracle. Ahora llama a `fetch_many`, que cada adaptador ya implementa con su sintaxis. El conteo de consultas del N+1 no cambia.
- **`ADD <col> <tipo>` portable.** La palabra `COLUMN` es inválida en SQL Server y Oracle; omitirla funciona en los seis motores y no altera SQLite/MySQL/PostgreSQL.
- **El filtro `name=` de `list_tables` queda fuera de alcance.** Es un defecto preexistente distinto del bug `COUNT(*)`; arreglarlo tocaría `_tables_sql` en seis adaptadores. Documentado en `deferred-items.md`.
- **SQLite sin marker `integration`.** Sus aserciones de paridad corren en cada corrida (incluida la selección rápida `not integration`), como red de seguridad barata.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `Model.search` emitía `LIMIT/OFFSET` inline (inválido en MSSQL/Oracle)**
- **Found during:** Task 2 (`test_count_paginate_and_list_tables` de SQL Server).
- **Issue:** `Model.search` construía `... LIMIT {limit} OFFSET {offset}` dentro del SQL. SQL Server falla con `Incorrect syntax near 'LIMIT'`; Oracle no reconoce `LIMIT`. La paginación de `Model.paginate` era, por tanto, inutilizable en 2 de 6 motores.
- **Fix:** con `limit` fijado, `search` llama a `db.fetch_many(Query(sql, params), limit, page)`; sin límite sigue usando `fetch_all`. `fetch_many` ya implementa la sintaxis correcta por adaptador.
- **Files modified:** `encino_orm/model/model.py`
- **Verification:** `TestMssqlParity` / `TestOracleParity::test_count_paginate_and_list_tables` pasan; suite completa en verde.
- **Committed in:** `1a5d621` (Task 2)

**2. [Rule 1 - Bug] `sync_schema` emitía `ALTER TABLE … ADD COLUMN` (inválido en MSSQL/Oracle)**
- **Found during:** Task 2 (`test_sync_schema_adds_missing_column` de SQL Server).
- **Issue:** `Incorrect syntax near the keyword 'COLUMN'`. `ADD COLUMN` no es válido en T-SQL ni en Oracle; el camino de añadir columnas estaba roto en esos motores.
- **Fix:** `ALTER TABLE {tabla} ADD {col} {ddl}` — forma aceptada por los seis motores.
- **Files modified:** `encino_orm/model/model.py`
- **Verification:** `test_sync_schema_adds_missing_column` pasa en los seis motores.
- **Committed in:** `1a5d621` (Task 2)

**3. [Rule 1 - Bug] El alias del wrapper de conteo `_encino_orm_count` es inválido en Oracle**
- **Found during:** Task 2 (`list_tables` de Oracle).
- **Issue:** `ORA-00911: invalid character`. Oracle no admite identificadores que empiecen por `_` sin comillas dobles; `list_tables` y `Db.paginate` lo usaban.
- **Fix:** alias renombrado a `encino_orm_count` en ambos sitios.
- **Files modified:** `encino_orm/base.py`
- **Verification:** `test_count_paginate_and_list_tables` de Oracle pasa.
- **Committed in:** `1a5d621` (Task 2)

**4. [Rule 3 - Blocking] `CountingDb` de `test_graphql.py` no contaba `fetch_many`**
- **Found during:** Task 2, al correr la suite completa tras delegar la paginación en `fetch_many`.
- **Issue:** el test de N+1 asertaba `fetch_count == 2` y obtenía 1: la consulta de lista de GraphQL pasa por `Model.search(limit=…)`, que ahora usa `fetch_many`, y `CountingDb` solo instrumentaba `fetch_all`. El comportamiento (2 consultas, sin N+1) es correcto; el contador estaba incompleto.
- **Fix:** `CountingDb.fetch_many` incrementa el mismo contador y delega en `super()`.
- **Files modified:** `tests/test_graphql.py`
- **Verification:** `tests/test_graphql.py` → 19 passed.
- **Committed in:** `1a5d621` (Task 2)

---

**Total deviations:** 4 auto-fixed (3 bugs de portabilidad cross-engine, 1 blocking de instrumentación de test).
**Impact on plan:** Los tres bugs cross-engine son exactamente la clase que la fase existe para eliminar ("resultados correctos en los seis motores") y eran **bloqueantes** para las aserciones de integración que el plan exige. El cuarto es de instrumentación de test, sin cambio de comportamiento. Sin scope creep: no se tocó `_tables_sql` ni el filtro `name=` (documentado como diferido).

## Issues Encountered

- El filtro `name=` de `list_tables` resultó roto en PostgreSQL, MySQL, SQL Server y Oracle (alias referenciado en `WHERE`). No se arregló por estar fuera del alcance del plan; registrado en `deferred-items.md` y los tests de paridad usan `list_tables(limit=1000)` sin filtro.
- Oracle `system` tiene 136 tablas en `user_tables`, así que el `limit=50` por defecto no incluía `TEST_PARITY`; se subió el límite en los tests de paridad.

## Verification Evidence

- `uv run pytest -q` → **694 passed** (baseline 663 + 31 nuevos).
- `uv run pytest -q -m "not integration and not optional_engine"` → **633 passed, 61 deselected**.
- `uv run pytest tests/test_sqlite.py tests/test_postgresql.py tests/test_mysql.py tests/test_mssql.py tests/test_mariadb.py tests/test_oracle.py -q` → **109 passed**.
- `uv run pytest tests/test_aggregates.py tests/test_query_builder.py -q` → 21 passed.
- Guard: `grep -rn 'row\["COUNT(\*)"\]\|row\[f"SUM(\|row\[f"AVG(\|row\[f"MIN(\|row\[f"MAX(' encino_orm/` → vacío.
- `inspect.getsource` de los 7 lectores → 7 ocurrencias de `AS n`.
- `uv run ruff check encino_orm tests` exit 0; `uv run ruff format --check encino_orm tests` exit 0 (111 ficheros); `uv run mypy encino_orm` exit 0 (60 ficheros).
- `grep -rc "noqa" encino_orm/` → 0.

## Known Stubs

None — no se introdujo ningún valor hardcodeado, placeholder ni componente sin fuente de datos. `list_tables(limit=1000)` en los tests es un límite explícito para incluir la tabla de prueba, no un stub.

## Threat Flags

None — el cambio cae dentro del `<threat_model>` del plan (T-02-20…T-02-24). El alias en el SQL refuerza T-02-20/T-02-21; no se añadió superficie de confianza nueva.

## TDD Gate Compliance

- RED: `bfaf4a4` (`test(02-04): add failing test for aggregate result alias`) — 5 tests fallando con `KeyError: 'COUNT(*)'` y el guard de fuente.
- GREEN: `ccc8a8a` (`feat(02-04): alias the seven aggregate readers as n`) — 21 passed.
- REFACTOR: no aplica.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 02-05 hereda los seis motores con paridad de `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` y los snapshots syrupy pendientes.
- **Registrado para una fase futura:** el filtro `name=` de `list_tables` está roto en 4 de 6 motores (ver `deferred-items.md`); su arreglo pertenece a la introspección, no a esta fase.
- La promoción de MariaDB/Redis y el job `engine-heavy` para MSSQL/Oracle siguen siendo de 02-05; los markers `optional_engine` se conservan.

---

## Self-Check: PASSED

- `encino_orm/base.py` — FOUND
- `encino_orm/model/model.py` — FOUND
- `encino_orm/model/query_builder.py` — FOUND
- `tests/test_aggregates.py` — FOUND
- `tests/test_query_builder.py` — FOUND
- `tests/test_postgresql.py` — FOUND
- `tests/test_mssql.py` — FOUND
- `tests/test_oracle.py` — FOUND
- `tests/test_sqlite.py` — FOUND
- `tests/test_mysql.py` — FOUND
- `tests/test_mariadb.py` — FOUND
- `tests/test_graphql.py` — FOUND
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` — FOUND
- Commit `bfaf4a4` — FOUND
- Commit `ccc8a8a` — FOUND
- Commit `1a5d621` — FOUND
- Commit `fa59665` — FOUND
