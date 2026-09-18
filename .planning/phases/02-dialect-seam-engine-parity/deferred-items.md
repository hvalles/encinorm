# Deferred Items — Phase 02 (Dialect Seam & Engine Parity)

Items discovered during execution that are **out of scope** for the plan that found
them. They are logged here, not fixed, per the executor scope boundary.

## Cerrados en la ronda de gap closure

Items that `02-VERIFICATION.md` / `02-REVIEW.md` flagged and that the gap-closure
plans (`02-06`…`02-09`) take ownership of. The three entries below are closed:
`list_tables(name=)` by `02-09`; WR-03 and WR-04 by `02-08`. **Ya NO queda ningún
item de la Fase 02 sin dueño** — este era el último diferido huérfano.

### `Db.list_tables(name=...)` — filtro roto en 4 de 6 motores (GAP 4) — CERRADO

- **Found in:** 02-04 (Task 2/3), al añadir cobertura de `list_tables` por motor.
- **Causa raíz confirmada:** `Db.list_tables` (`encino_orm/base.py`) añadía
  `" AND name LIKE {0}"` al SQL base de `_tables_sql()`. Ahí `name` es un
  **alias de SELECT** (`tablename AS name`, `table_name AS name`,
  `TABLE_NAME AS name`), y PostgreSQL, MySQL, SQL Server y Oracle NO permiten
  referenciar un alias de columna en `WHERE` (solo `ORDER BY`/`HAVING`); solo
  SQLite tiene una columna real `name`.
- **Evidencia RED capturada en 02-09** (con el código previo al fix): PostgreSQL
  `asyncpg.exceptions.UndefinedColumnError: column "name" does not exist`; Oracle
  `oracledb.exceptions.DatabaseError: ORA-00907: missing right parenthesis`. El
  log original citaba `ORA-00911`; el error real del catálogo es ORA-00907, misma
  causa raíz (el filtro inválido se anida dentro del wrapper de conteo).
- **Solución aplicada (02-09):** envolver el SQL base en una **tabla derivada** —
  `SELECT * FROM (<base>) encino_orm_tables WHERE LOWER(name) LIKE LOWER({0})` —
  de modo que `name` pase a ser una columna REAL de la derivada, válido en los
  seis dialectos. Comparación con `LOWER()` en AMBOS lados (Oracle devuelve los
  nombres en MAYÚSCULAS; PostgreSQL es sensible por defecto) y valor del filtro
  **ligado** como `{0}`, nunca interpolado. El camino SIN filtro queda
  byte-idéntico: `test_list_tables_snapshot` no cambia y el `.ambr` solo GANA la
  entrada filtrada.
- **Motores cubiertos:** los seis. Snapshot DB-free del SQL filtrado por dialecto
  (`tests/test_sql_snapshots.py::test_list_tables_filtered_snapshot`, entrada
  nueva del `.ambr`) más un test de integración por motor
  (`test_list_tables_filtrado_por_nombre`) en `tests/test_sqlite.py`,
  `test_mysql.py`, `test_mariadb.py`, `test_postgresql.py`, `test_mssql.py` y
  `test_oracle.py`. La cobertura por motor pasa a existir en los seis ficheros.
- **Cierre:** el item deja de ser un diferido huérfano; DIAL-03 deja de ser
  parcial.

### WR-03 — `QueryBuilder.all()/first()/exists()` emitted inline `LIMIT`

- **Found by:** `02-REVIEW.md` WR-03 (same defect class as the `Model.search` fix
  of this phase). Recorded here as **found and closed**: the reviewer noted the
  item was fixed but never logged in this file.
- **Root cause:** `QueryBuilder` appended `LIMIT n OFFSET m` / `LIMIT 1` to the
  SQL it sent to the driver. `LIMIT` is invalid T-SQL / Oracle syntax (they use
  `OFFSET … FETCH NEXT`), so `limit().all()`, `first()` and `exists()` raised a
  syntax error on MSSQL and Oracle. The per-engine parity tests only exercised
  the aggregates, so CI stayed green over a broken path.
- **Impact:** three public `QueryBuilder` entry points broken on 2 of 6 engines,
  with zero coverage on any engine.
- **Closed by:** plan `02-08` Task 1 — pagination is delegated to the adapter
  (`fetch_many`/`fetch_one`, the pattern already proven in `Model.search`) and a
  new per-engine test (`test_query_builder_limit_first_exists`) covers
  `limit().all()`, `first()` and `exists()` on all six engines.
- **Evidence:** `tests/test_query_builder.py` (DB-free `LIMIT not in template`
  guards) plus the six per-engine parity files; `git diff --stat
  tests/__snapshots__/` must stay empty (adapter-level SQL is unchanged).

### WR-04 — `Model.upsert` on MariaDB emitted `ON CONFLICT`

- **Found by:** `02-REVIEW.md` WR-04 while reviewing the byte-identity-preserving
  refactor of `UPSERT_KIND`.
- **Root cause:** `UPSERT_KIND["mariadb"] = "on_conflict"` reproduced the old
  `dialect is Engine.MYSQL` identity branch verbatim, so MariaDB got
  PostgreSQL/SQLite's `ON CONFLICT` syntax. MariaDB 11 (the CI image promoted to
  a **required** engine by `02-05`) expects `ON DUPLICATE KEY UPDATE`.
- **Impact:** `Model.upsert()` broken on one of the six engines, and CI green
  because `tests/test_mariadb.py` never exercised `upsert`.
- **Closed by:** plan `02-08` Task 2 — `UPSERT_KIND["mariadb"]` becomes
  `"on_duplicate"` (data, not a branch; `build_upsert`'s `on_duplicate` render is
  unchanged and already byte-identical to MySQL's), plus a MariaDB integration
  test that upserts on a UNIQUE **data** column (the auto-PK `id` is omitted from
  the INSERT, so the conflict target must be a value present in `data`).
- **Evidence:** `tests/test_dialect_builders.py` (map value + exact SQL, and the
  one deliberately-edited existing assertion at `:502`), `tests/test_mariadb.py`.
- **CHANGELOG wording for Phase 8 to reuse:** "`Model.upsert()` en MariaDB emite
  `ON DUPLICATE KEY UPDATE` en vez de `ON CONFLICT`, que MariaDB no implementa
  (el camino estaba roto)."

## Encontrados durante 02-08 (ejecución del MERGE en MSSQL/Oracle)

Defectos **preexistentes** del render `merge` que aparecieron al añadir la
cobertura de motor de `Model.insert(replace=True)` (Task 3). El plan asumía que
la sentencia era ejecutable en ambos motores; no lo era.

### MSSQL — `MERGE` sin `;` terminal (error 10713)

- **Síntoma:** `pyodbc.ProgrammingError` 10713: "A MERGE statement must be
  terminated by a semi-colon (;)".
- **Causa:** `builders._merge_sql` no añade `;`, y SQL Server lo exige.
- **Estado:** **CORREGIDO** en 02-08 (Rule 3, desbloqueaba el test de motor). Se
  añade `;` SOLO al SQL que va al driver en `MssqlDb.execute`, de modo que
  `_prepare`, golden strings y snapshots conservan el SQL byte-idéntico.
- **Cobertura:** `tests/test_mssql.py::TestMssqlParity::test_model_insert_replace_no_rompe_el_merge`
  (fallaba con 10713 antes del fix).

### Oracle — `USING (SELECT …)` sin `FROM dual` (ORA-00923)

- **Síntoma:** `oracledb.exceptions.DatabaseError: ORA-00923: FROM keyword not
  found where expected`.
- **Causa:** `builders._merge_sql` emite `USING (SELECT {n} AS c, …) src`; Oracle
  exige una fuente (`FROM dual`) en ese subquery.
- **Estado:** **CORREGIDO** en 02-08 (Rule 3) a nivel de driver en
  `OracleDb.execute` (regex que inserta `FROM dual`), preservando byte-identidad
  de `_prepare`/snapshots/golden strings.
- **Cobertura:** `tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge`
  (caracteriza el fallo restante; ver abajo).

### Oracle — el fallback `merge` actualiza la columna del `ON` (ORA-38104) — PENDIENTE

- **Síntoma (tras el fix de `FROM dual`):** `ORA-38104: Columns referenced in the
  ON Clause cannot be updated: "DST"."ENABLED"`.
- **Causa:** cuando `conflict=None`, `build_insert` resuelve el objetivo a
  `columns[0]` (`enabled`) y `_merge_sql` incluye TODAS las columnas de `data` en
  el `WHEN MATCHED THEN UPDATE SET`, incluida `enabled`, que es la misma columna
  del `ON`. Oracle prohíbe actualizar una columna del `ON` del `MERGE`.
- **Impacto:** `Model.insert(replace=True)` **no es ejecutable en Oracle** para un
  modelo de PK autoincremental (el caso que 02-08 documenta). Es el fallback
  `merge` preexistente, ya reconocido como semánticamente incorrecto; en Oracle
  además no es ejecutable.
- **NO corregido en 02-08:** exigiría excluir la columna del `ON` del `SET` en
  `builders._merge_sql`, lo que cambiaría el SQL del adaptador (golden strings y
  snapshots pinados byte a byte por el criterio de 02-08). Queda DOCUMENTADO.
- **Sugerencia para una fase futura:** excluir de `set_sql` las columnas de
  `conflict_cols` (como ya hace `build_upsert` con `update_cols`) y regenerar los
  snapshots de forma visible; entonces `Model.insert(replace=True)` en Oracle
  sería ejecutable.
- **Cobertura actual:** `tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge`
  caracteriza ORA-38104 (falla si el builder se corrige, para forzar la
  actualización del test).
