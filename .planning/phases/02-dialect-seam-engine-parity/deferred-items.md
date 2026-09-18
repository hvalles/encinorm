# Deferred Items — Phase 02 (Dialect Seam & Engine Parity)

Items discovered during execution that are **out of scope** for the plan that found
them. They are logged here, not fixed, per the executor scope boundary.

## Found during 02-04 (aggregate result alias + per-engine parity)

### `Db.list_tables(name=...)` filter is broken on every engine except SQLite

- **Found in:** Task 2/3 when adding per-engine `list_tables` integration coverage.
- **Symptom:** PostgreSQL raises `asyncpg.exceptions.UndefinedColumnError: column "name" does not exist`;
  Oracle raises `oracledb.exceptions.DatabaseError: ORA-00911` (same root cause).
- **Root cause:** `Db.list_tables` (`encino_orm/base.py`) appends
  `" AND name LIKE {0}"` to the *base* SQL returned by `_tables_sql()`. The
  `name` there is a SELECT **alias** (`tablename AS name`, `table_name AS name`,
  `TABLE_NAME AS name`), and PostgreSQL, MySQL, SQL Server and Oracle do **not**
  allow a column alias to be referenced in `WHERE` (only `ORDER BY`/`HAVING`).
  It only works on SQLite, where `sqlite_master.name` is a real column.
- **Impact:** the documented `name=` filter of `list_tables` is dead on 4 of 6
  engines. The unfiltered path (the one this phase required) works and is now
  covered per engine.
- **Suggested fix (future phase):** push the filter into `_tables_sql()` (e.g.
  `_tables_sql(name: str | None)`) so each adapter filters on its real catalog
  column, or wrap the base SQL in a derived table before filtering.
- **Not fixed in 02-04:** the plan scoped DIAL-03 to the `COUNT(*)` alias; the
  `name` filter is a distinct pre-existing defect and touching `_tables_sql` in
  six adapters would widen this plan's blast radius.
- **Closed by:** plan `02-09` (gap-closure round) — see
  `## Cerrados en la ronda de gap closure`.

## Cerrados en la ronda de gap closure

Items that `02-VERIFICATION.md` / `02-REVIEW.md` flagged and that the gap-closure
plans (`02-06`…`02-09`) take ownership of. The `list_tables(name=)` item above is
closed by `02-09`; the two entries below are closed by `02-08`.

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
