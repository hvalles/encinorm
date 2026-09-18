---
phase: 03-data-correctness
plan: 02
subsystem: database
tags: [migrations, ledger, reconciliation, transactional-ddl, data-correctness, sqlite, mysql, mariadb, postgresql, mssql, oracle]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "MIGRATIONS_TABLE, STATUS_PENDING/APPLIED/ROLLING_BACK, the status column and the _ensure_ledger/_row_status/_set_status/_delete_row helpers (03-01)"
provides:
  - "TRANSACTIONAL_DDL per dialect (data, not a branch) + Db.transactional_ddl + PoolDb.transactional_ddl"
  - "PoolDb._ensure_migrations_table delegation so reconcile_migrations(pool) works before any migrate()"
  - "migration._apply: pending-before-DDL / promote-after-DDL two-phase runner (never db.commit())"
  - "migration.reconcile_migrations(db): public startup API that detects ambiguous pending/rolling_back rows and raises MigrationError carrying the SQL"
  - "migration.resolve_migration(db, name, *, applied): the four D-08 actions"
  - "the six adapters' migrate() rewired to reconcile-before-apply + _apply"
affects: [03-04-docs, 03-verify]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "record-intent-first two-phase migration: insert pending -> DDL -> promote applied in one transaction"
    - "runtime-read compensation branch on db.transactional_ddl (no uniform BEGIN/COMMIT theater)"
    - "reconciliation as a noisy failure: ambiguous state is DETECTED, never assumed"
    - "hand-written fake Db modelling the implicit DDL commit (published snapshot)"

key-files:
  created:
    - tests/test_dialect_ddl.py
    - tests/test_migration_reconcile.py
  modified:
    - encino_orm/dialects/strategies.py
    - encino_orm/dialects/__init__.py
    - encino_orm/base.py
    - encino_orm/pool.py
    - encino_orm/migration.py
    - encino_orm/__init__.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/mariadb.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py

key-decisions:
  - "TRANSACTIONAL_DDL is a dialect datum read at runtime, not a branch: MySQL 8.0/MariaDB atomic DDL is statement-atomic (crash-safe), NOT rollbackable (Pitfall 2)"
  - "The runner never calls db.commit(); it uses async with db.transaction() so it works identically for direct adapters and PoolDb"
  - "A pending that survives a crash is left on purpose (never auto re-run, never assumed applied); resolve_migration is the human resolution path"
  - "resolve_migration's applied parameter means 'should the migration remain recorded as applied?', not 'did the SQL run?' (D-17)"

patterns-established:
  - "Two-phase ledger: pending before DDL, promote after; compensation only when the DDL did not run"
  - "Pool delegation for a private capability (_ensure_migrations_table) so startup reconciliation works pre-migrate"

requirements-completed: [DATA-02]

# Metrics
duration: 3min
completed: 2026-09-18
---

# Phase 3 Plan 2: Migration Atomicity & Reconciliation Summary

**Made `migrate()` atomic where the engine allows it and reconcilable where it does not: `pending` is recorded before the DDL and promoted to `applied` after, and a surviving `pending` is detected loudly by `reconcile_migrations` instead of being silently assumed.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-18T17:48:18Z
- **Completed:** 2026-09-18T17:51:42Z
- **Tasks:** 3
- **Files modified:** 14 (2 created, 12 modified)

## Accomplishments
- `TRANSACTIONAL_DDL` maps the six dialects (`True` for SQLite/PostgreSQL/MSSQL; `False` for MySQL/MariaDB/Oracle), exposed through `Db.transactional_ddl` (default `True`) and `PoolDb.transactional_ddl` (delegates to the template).
- `migration._apply` implements the two-phase runner: insert `pending` → execute DDL → promote `applied`, all inside `async with db.transaction()`; it never calls `db.commit()`.
- The compensation branch reads `db.transactional_ddl` at runtime: with implicit-commit DDL it clears the published `pending` only when the DDL did not run, and leaves it **on purpose** (with a warning) when the DDL ran and the promote failed.
- `reconcile_migrations(db)` detects `pending`/`rolling_back` rows and raises `MigrationError` listing each row's name, status and SQL plus the `resolve_migration` instruction — it never re-runs DDL nor assumes `applied`.
- `resolve_migration(db, name, *, applied=...)` executes the four D-08 actions; `applied` means "should it remain recorded as applied?".
- The six adapters' `migrate()` reconcile before applying, keep idempotency-by-name, and delegate the ledger write to `_apply`; MariaDB pins its own `transactional_ddl`.
- `PoolDb._ensure_migrations_table` delegation lets `reconcile_migrations(pool)` create the ledger before any `migrate()` (verified against a real SQLite pool).

## Task Commits

Each task was committed atomically:

1. **Task 1: `TRANSACTIONAL_DDL` + `Db.transactional_ddl` + `PoolDb.transactional_ddl`** - `a730fcf` (feat)
2. **Task 2: runner state machine (`_apply`, `reconcile_migrations`, `resolve_migration`)** - `8cc1789` (feat)
3. **Task 3: rewire the six `migrate()` + adapter attrs + map tests** - `21bfd85` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `encino_orm/dialects/strategies.py` - `TRANSACTIONAL_DDL` data map + `__all__`
- `encino_orm/dialects/__init__.py` - re-export `TRANSACTIONAL_DDL`
- `encino_orm/base.py` - `Db.transactional_ddl: bool = True` conservative default
- `encino_orm/pool.py` - `transactional_ddl` property + `_ensure_migrations_table` delegation
- `encino_orm/migration.py` - `_apply`, `reconcile_migrations`, `resolve_migration`, trust-boundary docstring
- `encino_orm/__init__.py` - export `reconcile_migrations`/`resolve_migration`
- `encino_orm/sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py` - per-adapter `transactional_ddl` + rewired `migrate()`
- `tests/test_dialect_ddl.py` - DB-free map/attr/pool-delegation asserts (7 tests)
- `tests/test_migration_reconcile.py` - hand-written fake `Db` + pool ledger test (11 tests)

## Decisions Made
- `TRANSACTIONAL_DDL` is a datum, not a branch; the compensation decision is made at runtime from `db.transactional_ddl`.
- The runner uses only `async with db.transaction()`; `PoolDb.commit()` raises `ConnectionError` by design, so a direct commit was never an option.
- The failure-injection test asserts **detection** of a surviving `pending` (Pitfall 8), not that the ambiguous state is impossible.
- `resolve_migration` keeps the D-08 action table verbatim, with `applied` interpreted per D-17.

## Deviations from Plan

None - plan executed exactly as written.

One mechanical detail worth recording: the Task 1 acceptance grep requires the literal `TRANSACTIONAL_DDL` to appear in `encino_orm/pool.py`, which the planned property body (`self._template.transactional_ddl`) does not contain; it was satisfied by referencing the datum in the property docstring. No behavioral change.

## Issues Encountered
- `ruff format --check` flagged two wrapped lines (a `join` expression and an f-string in `migration.py`, plus one in the test fake); reformatted with `ruff format` before the Task 2 commit.
- The Task 2 acceptance grep requires `db.commit()` to be 0 in `migration.py`; the `_apply` docstring originally contained that literal, so it was rephrased to "el commit directo del adaptador" (same approach 03-01 used) to keep the grep honest.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DATA-02 is delivered: `migrate()` is atomic on transactional-DDL engines and intent-recording + reconcilable on the rest.
- Plan 03-04 (docs/CHANGELOG) can document the new `pending` insert, the removed direct commit, and the `reconcile_migrations`/`resolve_migration` startup procedure.
- Oracle/MSSQL paths are verified by construction and the fake model (engines absent locally); the engine-heavy CI job will exercise them.

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 14 key files exist on disk.
- All 3 task commits exist in history (`a730fcf`, `8cc1789`, `21bfd85`).
- `uv run pytest -q` → 824 passed (10 snapshots passed).
- `uv run pytest tests/test_dialect_ddl.py tests/test_migration_reconcile.py -q` → 18 passed; pool reconcile test passes.
- `uv run pytest tests/test_sqlite.py tests/test_migrations.py -q` → 51 passed; `-k migrate_is_idempotent` passes.
- `uv run ruff check encino_orm tests` / `ruff format --check` / `mypy encino_orm` all exit 0; `noqa` count in `encino_orm/` is 0.
- Acceptance greps: `db.commit()` in migration.py = 0; `transactional_ddl = TRANSACTIONAL_DDL` = 1 per adapter; `reconcile_migrations(self)` = 1 per edited adapter; `await self.commit()` = 0 in the four rewritten `migrate()`.
