---
phase: 02-dialect-seam-engine-parity
plan: 02
subsystem: database
tags: [orm, sql, security, refactor, dialects, upsert, identifier-allowlist]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "Allowlist estricto centralizado (`dialects/identifiers.py`) y barrel `dialects/` de 02-01"
provides:
  - "Seam DML único: `dialects/builders.py` (build_insert/build_update/build_delete/build_upsert)"
  - "Estrategias por dialecto: `dialects/strategies.py` (InsertStrategy + 6 constantes + UPSERT_KIND + strategy_for)"
  - "Accesores tipados de `Query` (`.sql`/`.params`) y property `query` de solo lectura"
  - "`sync_schema` fail-closed ante nombres derivados del catálogo"
  - "`PoolDb.insert` reenvía `conflict` y `schema`"
affects: [02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Seam DML: una sola construcción de INSERT/UPDATE/DELETE en el core; los adaptadores solo eligen estrategia"
    - "Estrategia como DATO congelado (InsertStrategy) en vez de ramas por motor en el builder"
    - "Validación de identificadores en el punto de construcción (antes de que exista SQL)"
    - "Guards `ast` (excluyen docstrings) como control anti-podredumbre de la construcción DML única"
    - "SQL byte-idéntico verificado por las aserciones golden-string existentes SIN editar"

key-files:
  created:
    - encino_orm/dialects/builders.py
    - encino_orm/dialects/strategies.py
    - tests/test_dialect_builders.py
  modified:
    - encino_orm/query.py
    - encino_orm/dialects/__init__.py
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - encino_orm/pool.py
    - encino_orm/model/model.py
    - pyproject.toml
    - tests/test_pool.py
    - tests/test_migrations.py

key-decisions:
  - "MariaDB conserva `UPSERT_KIND['mariadb'] = 'on_conflict'` VERBATIM: hoy cae en el else porque `dialect is Engine.MYSQL` es identidad exacta; se marca como HALLAZGO para una fase posterior, no se arregla aquí"
  - "Los dos separadores del objetivo de conflicto quedan pinados: build_upsert usa ',' (sin espacio, model.py:624) y build_insert usa ', ' (con espacio, postgresql.py:170)"
  - "`excluded` en minúsculas en build_upsert frente a `EXCLUDED` en build_insert: diferencia intencional, preservada byte a byte"
  - "El `S608` se acota a `dialects/builders.py` con la frontera de confianza documentada en el módulo; `noqa` sigue en 0"
  - "`Query.query` pasa a property de solo lectura que devuelve una lista NUEVA; el cambio es aditivo (rebind sigue vivo hasta 02-03)"

patterns-established:
  - "Un único choke point de construcción y validación DML: los 6 adaptadores lo heredan por construcción"
  - "Guards de fuente basados en `ast` (no grep) para literales DML y ramas Engine.*, excluyendo docstrings"
  - "TDD de movimiento puro: la suite golden-string existente es el oráculo de regresión byte-idéntico"

requirements-completed: [DIAL-02, DIAL-04]

# Metrics
duration: 8min
completed: 2026-09-18
---

# Phase 2 Plan 02: Dialect Seam & Engine Parity Summary

**Seam DML único (`dialects/builders.py` + `strategies.py`) que absorbe la construcción de INSERT/UPDATE/DELETE de los 6 adaptadores y la cláusula de conflicto de `Model.upsert`, con SQL byte-idéntico (aserciones golden-string intactas) y validación fail-closed de identificadores.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-18T04:19:31Z
- **Completed:** 2026-09-18T04:27:03Z
- **Tasks:** 5 (2 con ciclo TDD RED→GREEN)
- **Files modified:** 16 (3 creados, 13 modificados)

## Accomplishments

- **DIAL-02 cumplido:** existe UNA sola implementación de la construcción DML (`dialects/builders.py`). Los 6 adaptadores (`sqlite`, `mysql`, `mariadb` por herencia, `postgresql`, `mssql`, `oracle`) delegan vía `_insert_strategy(...)` y ya no construyen SQL DML propio.
- **SQL byte-idéntico:** las aserciones golden-string de `test_postgresql.py`, `test_mssql.py`, `test_oracle.py`, `test_mysql.py` y `test_sqlite.py` pasan **sin editarse**; el diff de esos 5 ficheros sobre todo el plan está vacío.
- **Validación centralizada:** `check_identifier` se aplica a tabla, cada columna, cada columna de `conflict` y al `schema` ANTES de construir el SQL. El rechazo se prueba con spy por adaptador (el driver nunca se alcanza).
- **`schema=` sin relajar la allowlist:** `_qualified()` valida `schema` y `table` por separado y compone `esquema.tabla` (Pitfall 10).
- **DIAL-04 cumplido:** `sync_schema` valida `_table` y las columnas derivadas del catálogo en los 4 puntos de `ALTER TABLE`; un nombre hostil lanza `ValueError` sin ejecutar DDL (spy con lista vacía).
- **`Model.upsert` sin ramas por motor:** la cláusula de conflicto (`ON CONFLICT` / `ON DUPLICATE KEY` / `MERGE`) se construye en `build_upsert`; `tests/test_bulk_upsert.py` pasa sin editarse.
- **`PoolDb.insert` deja de descartar `conflict`** (y reenvía `schema`); PostgreSQL con `replace=True` ya no cae siempre a `columns[0]` a través del pool.
- **Guards `ast` verificados por fallo inducido:** reintroducir temporalmente `Engine.MYSQL` o un literal `MERGE INTO` dentro de `Model.upsert` hace fallar los dos guards; revertido el cambio, vuelven a pasar.
- Gates de Fase 1 intactos: `ruff check`, `ruff format --check`, `mypy encino_orm` salen 0; `noqa` sigue en 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Contratos del seam (InsertStrategy) + accesores de Query** - `2a59c5c` (feat)
2. **Task 2 (RED): tests del builder DML compartido** - `bbefdb6` (test)
3. **Task 2 (GREEN): builder DML compartido con validación** - `31ea898` (feat)
4. **Task 3: los 6 adaptadores delegan en el seam; PoolDb reenvía conflict** - `70e14b0` (refactor)
5. **Task 4 (RED): sync_schema rechaza identificadores del catálogo** - `a27951d` (test)
6. **Task 4 (GREEN): sync_schema valida identificadores del catálogo** - `fbe0d67` (feat)
7. **Task 5 (RED): build_upsert y guards `ast`** - `30a7db7` (test)
8. **Task 5 (GREEN): Model.upsert construye su conflicto en el seam** - `0d28e93` (feat)

**Plan metadata:** `docs(02-02): complete ... plan` (hash en `git log`)

_Note: las tareas 2, 4 y 5 siguieron el ciclo TDD RED → GREEN._

## Files Created/Modified

- `encino_orm/dialects/builders.py` (nuevo) - `build_insert`/`build_update`/`build_delete`/`build_upsert`, único punto de construcción DML; `_qualified` (schema) y `_merge_sql` compartido.
- `encino_orm/dialects/strategies.py` (nuevo) - `InsertStrategy` congelado, 6 constantes por dialecto, `UPSERT_KIND`/`UPSERT_KINDS`/`strategy_for`.
- `tests/test_dialect_builders.py` (nuevo) - SQL por dialecto/modo, rechazo con spy, casos de `build_upsert` y 2 guards `ast`.
- `encino_orm/query.py` - accesores `.sql`/`.params`, property `query` de solo lectura (lista nueva), `ignore_duplicated` por constructor; `rebind` intacto.
- `encino_orm/dialects/__init__.py` - barrel que re-exporta builders, estrategias y `check_identifier`.
- `encino_orm/base.py` - firmas abstractas `insert`/`delete`/`update` con `schema=` keyword-only.
- `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` - `insert`/`update`/`delete` delegan en el seam; hook `_insert_strategy`; `_prepare` y ledger de `migrate` usan `.sql`/`.params`.
- `encino_orm/pool.py` - `PoolDb.insert` refleja la firma abstracta completa (conflict + schema); `delete`/`update` reenvían `schema`.
- `encino_orm/model/model.py` - `sync_schema` fail-closed; `Model.upsert` delega en `build_upsert`.
- `pyproject.toml` - `S608` acotado a `dialects/builders.py` con la frontera de confianza documentada.
- `tests/test_pool.py` - `FakeDb` con la firma completa + aserciones de reenvío de `conflict`/`schema`.
- `tests/test_migrations.py` - rechazo de columna hostil del catálogo (spy) + camino feliz.

## Decisions Made

- **MariaDB = `on_conflict` (preservado verbatim).** Hoy `Model.upsert` ramifica con `dialect is Engine.MYSQL` (identidad exacta), así que MariaDB cae en el `else`. Reproducirlo es el criterio de aceptación; se documenta con comentario en `strategies.py` como HALLAZGO a verificar en una fase posterior.
- **Separadores de conflicto pinados por tests.** `build_upsert` usa `','.join(conflict)` (sin espacio, `model.py:624`); `build_insert` usa `", ".join` (con espacio, `postgresql.py:170`). Ambos quedan asegurados por aserciones literales.
- **`excluded` minúsculas vs `EXCLUDED` mayúsculas.** Diferencia intencional entre `build_upsert` y `build_insert`, preservada byte a byte.
- **Guards `ast` en lugar de grep.** El docstring de `Model.upsert` menciona `ON CONFLICT`/`ON DUPLICATE KEY`; un `grep == 0` daría un falso positivo. Los guards excluyen docstrings y se verificaron por fallo inducido.
- **`S608` acotado al módulo nuevo.** La frontera de confianza se documenta en `builders.py`; no se añade ninguna otra regla y `noqa` sigue en 0.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Corrección de fixture de test] El test de rechazo de `sync_schema` llamaba a `execute` antes del nombre hostil**
- **Found during:** Task 4 (GREEN)
- **Issue:** El `fake_existing` del test RED devolvía `{"id","a","b", hostil}`, pero el modelo tiene columnas implícitas (`created_at`/`updated_at`) que no estaban en el dict; el bucle "added" llamaba a `execute` antes de llegar al bucle "dropped", así que `ejecutados == []` nunca se cumplía.
- **Fix:** El fake deriva el catálogo de `T1._column_map()` (todas las columnas del modelo ya existen) y añade solo el nombre hostil, de modo que el único candidato a `DROP` es el malicioso.
- **Files modified:** `tests/test_migrations.py`
- **Verification:** `uv run pytest tests/test_migrations.py -k sync_schema -q` → 2 passed.
- **Committed in:** `fbe0d67` (Task 4 GREEN)

**2. [Rule 1 - Precisión del criterio] `pytest -k sync_schema` habría seleccionado 0 tests**
- **Found during:** Task 4 (RED)
- **Issue:** El criterio de aceptación usa `-k sync_schema`, pero la clase se llama `TestSyncSchema` (sin guion bajo) y los métodos existentes no contienen `sync_schema`; el comando pasaba en vacío (Pitfall ya visto en Fase 1).
- **Fix:** Los dos tests nuevos se nombraron `test_sync_schema_...` para que `-k sync_schema` seleccione de verdad y el criterio sea no vacuo.
- **Files modified:** `tests/test_migrations.py`
- **Verification:** `-k sync_schema` selecciona 2 tests.
- **Committed in:** `a27951d` (Task 4 RED) y `fbe0d67` (GREEN)

---

**Total deviations:** 2 auto-fixed (ambos correcciones de test/criterio, sin impacto en el alcance ni en el SQL generado).
**Impact on plan:** Ninguno. El SQL, la validación y los guards quedan exactamente como el plan exige.

## Issues Encountered

None — aparte de las dos correcciones anteriores. El refactor de los adaptadores no requirió iteración: la suite golden-string pasó al primer intento.

## Verification Evidence

- `uv run pytest -q -m "not integration and not optional_engine"` → **591 passed, 41 deselected**.
- `uv run pytest -q` (suite completa, extras + servicios locales) → **632 passed**.
- Diff de `tests/test_{postgresql,mssql,oracle,mysql,sqlite}.py` sobre `92a9a46..HEAD` → **vacío** (byte-identidad).
- `uv run pytest tests/test_dialect_builders.py tests/test_migrations.py tests/test_pool.py tests/test_bulk_upsert.py -q` → **104 passed**.
- Guards `ast`: pasan; fallan al reintroducir temporalmente `Engine.MYSQL` o `"MERGE INTO x"` dentro de `Model.upsert` (revertido).
- `uv run ruff check encino_orm tests` exit 0; `uv run ruff format --check encino_orm tests` exit 0 (110 ficheros); `uv run mypy encino_orm` exit 0 (60 ficheros).
- `grep -rn "\.query\[0\]\|\.query\[1\]" encino_orm/` → vacío; `grep -rn "noqa" encino_orm/` → vacío.
- `grep` de literales DML (`INSERT INTO|MERGE INTO|DELETE FROM|UPDATE `) sobre los 5 adaptadores → sin coincidencias (todo el DML vive en `dialects/builders.py`).
- `grep -rn "noqa" encino_orm/dialects/` → vacío.

## Known Stubs

None — no se introdujo ningún valor hardcodeado, placeholder ni componente sin fuente de datos.

## Threat Flags

None — la superficie nueva (`build_upsert`) cae dentro del mismo límite de confianza ya registrado (T-02-33) y usa el mismo `check_identifier`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- El seam DML es el único punto de construcción y validación: 02-03 (DIAL-05) puede cerrar la inmutabilidad de `Query` y añadir `with_params()` sin tocar ningún adaptador (ya leen `.sql`/`.params`), y 02-04 puede aplicar el alias `AS n` sin reabrir los builders.
- `dialects/__init__.py` es el barrel donde 02-05 añadirá `MAX_PARAMS`/`MAX_ROWS`.
- Hallazgo abierto (no arreglado a propósito): MariaDB hereda `on_conflict` de `Model.upsert`; verificar en una fase posterior si MariaDB soporta `ON CONFLICT`.
- Hallazgo abierto: `Model.insert_many` (`model.py:544`) y `transfer.copy_table` (`transfer.py:151`) siguen construyendo DML en línea, fuera del seam por diseño (DIAL-06 en 02-03 y PERF-01 en Fase 7).

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- `encino_orm/dialects/builders.py` — FOUND
- `encino_orm/dialects/strategies.py` — FOUND
- `tests/test_dialect_builders.py` — FOUND
- `.planning/phases/02-dialect-seam-engine-parity/02-02-SUMMARY.md` — FOUND
- Commit `2a59c5c` — FOUND
- Commit `bbefdb6` — FOUND
- Commit `31ea898` — FOUND
- Commit `70e14b0` — FOUND
- Commit `a27951d` — FOUND
- Commit `fbe0d67` — FOUND
- Commit `30a7db7` — FOUND
- Commit `0d28e93` — FOUND
