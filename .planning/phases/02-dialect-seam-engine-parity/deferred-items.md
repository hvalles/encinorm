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
