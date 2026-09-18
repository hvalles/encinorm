---
phase: 02-dialect-seam-engine-parity
plan: 08
subsystem: database
tags: [dialect-seam, query-builder, pagination, upsert, mariadb, postgresql, mssql, oracle, gap-closure]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "shared DML builders (dialects/builders.py) + UPSERT_KIND data map (dialects/strategies.py) from 02-02; identifier choke point from 02-06"
provides:
  - "QueryBuilder.all()/first()/exists() delegate pagination to the adapter (fetch_many/fetch_one); no inline LIMIT anywhere in the core"
  - "UPSERT_KIND['mariadb'] = 'on_duplicate' (MariaDB emits ON DUPLICATE KEY UPDATE), pinned by unit + live-engine tests"
  - "Model.insert(replace=True) derives the conflict target from the model PK only for strategy.kind == 'suffix' (PostgreSQL); conflict=None for merge (MSSQL/Oracle)"
  - "MSSQL/Oracle MERGE executable at the driver boundary (terminating ';' and 'FROM dual') without changing adapter-level SQL"
  - "per-engine coverage of limit().all()/first()/exists() on all six engines (previously zero)"
affects: [02-09, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pagination is an adapter concern: the core builds dialect-agnostic SQL and lets fetch_many/fetch_one apply the engine syntax"
    - "Dialect data (UPSERT_KIND, strategy.kind) decides the conflict render; no per-engine branch in the model"
    - "Byte-identity-preserving runtime fixes: rewrite only the SQL sent to the driver, never _prepare/builder output"

key-files:
  created: []
  modified:
    - encino_orm/model/query_builder.py
    - encino_orm/model/model.py
    - encino_orm/dialects/strategies.py
    - encino_orm/dialects/builders.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - tests/test_query_builder.py
    - tests/test_dialect_builders.py
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_postgresql.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_d_recommendations.py
    - CHANGELOG.md
    - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md

key-decisions:
  - "QueryBuilder.all() delegates to fetch_many(limit, page) when limit() is set and to fetch_all otherwise; first()/exists() drop the inline LIMIT 1 and rely on fetch_one's fetchone()"
  - "UPSERT_KIND['mariadb'] changes from 'on_conflict' to 'on_duplicate': MariaDB does not implement ON CONFLICT; this is dialect data, not a branch"
  - "Model.insert derives the conflict target from _pk_fields() ONLY when strategy.kind == 'suffix' (PostgreSQL); merge (MSSQL/Oracle) keeps conflict=None because the MERGE src has no auto-PK id"
  - "The merge fallback (columns[0]) remains deliberately unfixed: changing the SET clause would change the byte-identity-pinned adapter SQL; the Oracle ORA-38104 it causes is logged in deferred-items.md"
  - "MSSQL MERGE terminating ';' and Oracle 'FROM dual' are applied at the driver boundary only, so golden strings/snapshots stay byte-identical"

patterns-established:
  - "A dialect defect found while adding engine coverage is fixed at the driver boundary (execute) when the adapter-level SQL is frozen by snapshots"
  - "Integration tests use a dedicated model whose serialized values the target driver can actually bind, instead of asserting a result the library cannot produce"

requirements-completed: [DIAL-02, DIAL-03, DIAL-09]

# Metrics
duration: 14 min
completed: 2026-09-18
---

# Phase 02 Plan 08: Gap Closure — Engine Parity Defects (WR-03 / WR-04 / WR-05) Summary

**QueryBuilder pagination delegated to the adapter on all six engines, MariaDB upsert switched to `ON DUPLICATE KEY UPDATE`, and PostgreSQL `insert(replace=True)` conflict targets derived from the model PK — with MSSQL/Oracle `MERGE` made executable at the driver boundary while every pinned snapshot and golden string stayed byte-identical**

## Performance

- **Duration:** 14 min
- **Started:** 2026-09-18T13:38:08Z (approx., after 02-07 metadata commit)
- **Completed:** 2026-09-18T13:52:00Z (approx.)
- **Tasks:** 3
- **Files modified:** 17 (+ SUMMARY.md)

## Accomplishments
- `QueryBuilder.all()`, `first()` and `exists()` no longer emit an inline `LIMIT`: `all()` delegates to `fetch_many(limit, page)` (falling back to `fetch_all` when unpaginated) and `first()`/`exists()` rely on `fetch_one`'s `fetchone()`. The core contains no `LIMIT` (source-guarded), so the three paths are valid on all six engines (SQL Server and Oracle now use `OFFSET … FETCH NEXT`).
- `UPSERT_KIND["mariadb"]` is now `"on_duplicate"` (data, not a branch); MariaDB emits `ON DUPLICATE KEY UPDATE` instead of the unsupported `ON CONFLICT`. Verified against the live MariaDB 11 engine with a UNIQUE **data** column: `count() == 1` and `monto == 99.0` after the upsert.
- `Model.insert(replace=True)` passes the model's primary key as the conflict target only when the dialect renders `ON CONFLICT … DO UPDATE` (`strategy.kind == "suffix"`, PostgreSQL). For `merge` (MSSQL/Oracle) it keeps `conflict=None`, so no `src.id` is referenced. Against live PostgreSQL with a natural-PK model, `ON CONFLICT (codigo)` genuinely fires and replaces in place.
- The six per-engine files now cover `limit().all()`, `first()` and `exists()` (previously zero coverage on every engine), plus the new DB-free `LIMIT not in template` guards.
- The deliberate SQL changes are recorded in `CHANGELOG.md` `[Unreleased] ### Corregido` (additive) and `deferred-items.md`; the only pre-existing assertion edited is `tests/test_dialect_builders.py` (`UPSERT_KIND["mariadb"]`), visibly commented.

## Task Commits

Each task followed the RED/GREEN TDD cycle:

1. **Task 1 RED: failing tests for dialect-correct QueryBuilder pagination** - `0d4c084` (test)
2. **Task 1 GREEN: delegate QueryBuilder pagination to the adapter** - `97917ac` (feat)
3. **Task 2 RED: failing tests for MariaDB upsert ON DUPLICATE KEY** - `398e18f` (test)
4. **Task 2 style: ruff format the new parity tests** - `7fc9f5e` (style)
5. **Task 2 GREEN: emit ON DUPLICATE KEY UPDATE for MariaDB upsert** - `4a2a359` (feat)
6. **Task 3 RED: failing tests for Model.insert conflict target** - `cb2d6b8` (test)
7. **Task 3 GREEN: derive insert conflict target from the PK for suffix** - `7e00c31` (feat)
8. **Task 3 fix: resolve insert strategy only when replace is set** - `d40cc8a` (fix)
9. **Task 3 docs: log MSSQL/Oracle MERGE findings in deferred-items** - `7c6cd7f` (docs)

**Plan metadata:** `pending` (docs: complete plan)

_Note: TDD tasks produced RED then GREEN commits; the extra `fix`/`style` commits are the deviation fixes described below._

## Files Created/Modified
- `encino_orm/model/query_builder.py` - `all()` delegates to `fetch_many`; `first()`/`exists()` drop `LIMIT 1`
- `encino_orm/dialects/strategies.py` - `UPSERT_KIND["mariadb"] = "on_duplicate"` + rewritten rationale comment
- `encino_orm/model/model.py` - `Model.insert` derives `conflict` from `_pk_fields()` only for `suffix`+`replace`; strategy resolved only when `replace`
- `encino_orm/dialects/builders.py` - corrected the false "first column is the PK" comment in both the `suffix` and `merge` branches
- `encino_orm/mssql.py` - terminate `MERGE` with `;` at the driver boundary (error 10713 otherwise)
- `encino_orm/oracle.py` - inject `FROM dual` into the `MERGE` `USING` subquery at the driver boundary (ORA-00923 otherwise)
- `tests/test_query_builder.py` - `_RecordingDbPaginado` + `TestPaginacionDelegadaAlAdaptador` (4 tests)
- `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` - `test_query_builder_limit_first_exists` in each parity class
- `tests/test_dialect_builders.py` - MariaDB upsert unit tests; `_ModelDbRegistrador` + `TestModelInsertConflictTarget`
- `tests/test_mariadb.py` - `_UpsertModel` + `_UPSERT_DDL` + `test_model_upsert_on_duplicate_key`
- `tests/test_postgresql.py` - `_NaturalPkModel` + `_NATURAL_PK_DDL` + `test_model_insert_replace_con_pk_natural`
- `tests/test_mssql.py` / `tests/test_oracle.py` - `test_model_insert_replace_no_rompe_el_merge` (+ `_MergeModel` on Oracle)
- `tests/test_d_recommendations.py` - stale `LockDb.insert` double aligned with the abstract `Db.insert` signature
- `CHANGELOG.md` - `[Unreleased] ### Corregido` extended with the three corrections + the MERGE runtime fixes
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` - WR-03/WR-04 verified present; new section logging the MSSQL/Oracle MERGE findings

## Decisions Made
- **Pagination is an adapter concern.** The core builds dialect-agnostic SQL; `fetch_many`/`fetch_one` apply `LIMIT/OFFSET` vs `OFFSET … FETCH NEXT`. This mirrors the `Model.search` fix from this phase.
- **`UPSERT_KIND["mariadb"]` is corrected as data.** Only the conflict clause changes; `MARIADB_INSERT` stays identical to `MYSQL_INSERT`.
- **Conflict target derived from the PK only for `suffix`.** Deriving it for `merge` would turn an executable (if semantically wrong) fallback into a hard failure (`ON (dst.id = src.id)` with no `src.id`).
- **The `merge` fallback is left as-is.** Excluding the ON column from the MERGE `SET` would change the byte-identity-pinned adapter SQL; the resulting Oracle ORA-38104 is documented as pending.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] MSSQL `MERGE` was not executable (error 10713)**
- **Found during:** Task 3 (MSSQL engine guard)
- **Issue:** `Model.insert(replace=True)` raised `pyodbc.ProgrammingError` 10713 ("A MERGE statement must be terminated by a semi-colon (;)"). `builders._merge_sql` omits the terminator that SQL Server requires; the MERGE had never been executed by an existing test.
- **Fix:** append `;` to the prepared SQL inside `MssqlDb.execute` only when the statement starts with `MERGE`, so `_prepare`/golden strings/snapshots keep the byte-identical SQL.
- **Files modified:** `encino_orm/mssql.py`
- **Verification:** `tests/test_mssql.py::TestMssqlParity::test_model_insert_replace_no_rompe_el_merge` failed with 10713 before and passes after.
- **Committed in:** `7e00c31` (Task 3 GREEN)

**2. [Rule 3 - Blocking] Oracle `MERGE` `USING (SELECT …)` missing `FROM dual` (ORA-00923)**
- **Found during:** Task 3 (Oracle engine guard)
- **Issue:** `Model.insert(replace=True)` raised `ORA-00923: FROM keyword not found where expected`; Oracle requires a source in the `USING` subquery.
- **Fix:** a module-level regex injects `FROM dual` into the `USING (SELECT …) src` clause inside `OracleDb.execute` only, preserving byte-identity of the builder output.
- **Files modified:** `encino_orm/oracle.py`
- **Verification:** `tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge` moved from ORA-00923 to the deeper ORA-38104 (documented) — the fix is exercised by the test.
- **Committed in:** `7e00c31` (Task 3 GREEN)

**3. [Rule 1 - Bug] `Model.insert` broke a `Db` double without an `Engine` dialect**
- **Found during:** Full-suite run after Task 3 GREEN
- **Issue:** resolving `strategy_for(engine_of(db))` unconditionally made `Model.insert()` raise `ValueError: 'fake' is not a valid Engine` for the `LockDb` double (`dialect = "fake"`) in `test_d_recommendations.py`.
- **Fix:** resolve the strategy only when `replace` is set; the normal path never touches the dialect. Also aligned the stale `LockDb.insert` double with the abstract `Db.insert` signature (which has had `conflict` since 02-02).
- **Files modified:** `encino_orm/model/model.py`, `tests/test_d_recommendations.py`
- **Verification:** full suite `748 passed` (was `1 failed, 747 passed`).
- **Committed in:** `d40cc8a` (Task 3 fix)

### Deviations accepted (not auto-fixed)

**4. [Rule 4-adjacent - documented] Oracle `merge` fallback is not executable (ORA-38104)**
- **Found during:** Task 3 (Oracle engine guard)
- **Issue:** with `conflict=None`, `build_insert` targets `columns[0]` (`enabled`) and `_merge_sql` also updates that same column in `WHEN MATCHED THEN UPDATE SET`; Oracle forbids updating an ON-clause column. The plan described the fallback as "incorrect but executable" — true on MSSQL, false on Oracle.
- **Decision:** not fixed. Excluding the ON column from the `SET` would change the byte-identity-pinned adapter SQL (golden strings + snapshots). Logged in `deferred-items.md` with a suggested future fix; the Oracle engine test is a **characterization** that pins ORA-38104.
- **Files modified:** `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md`, `tests/test_oracle.py`
- **Committed in:** `cb2d6b8` (RED), `7c6cd7f` (docs)

**5. [Plan detail adjustment] PostgreSQL natural-PK integration model adapted**
- **Found during:** Task 3 (PostgreSQL engine guard)
- **Issue:** the plan's literal model/DDL could not produce the asserted result: `Model._serialize` turns `bool`→`int` and `datetime`→`str` (asyncpg rejects them for `BOOLEAN`/`TIMESTAMP`), and `Model.insert` always calls `last_id()` (`lastval()` is undefined without a sequence). Declaring `codigo` first also masked WR-05 because `columns[0]` would then be the PK.
- **Fix:** `_NaturalPkModel` disables the inherited `id`/`enabled`/`created_at`/`updated_at`, declares `monto` before `codigo`, and the DDL adds an auxiliary `id SERIAL` (whose default `nextval` makes `last_id()` work). This makes the intended RED (`no unique or exclusion constraint matching the ON CONFLICT specification`) and GREEN (`count() == 1`, `monto == 99.0`) both real.
- **Files modified:** `tests/test_postgresql.py`
- **Committed in:** `cb2d6b8` (RED)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 bug) + 2 documented adjustments
**Impact on plan:** The two blocking fixes were required for the planned engine guards to be genuinely executable; both are confined to the driver boundary, so the plan's byte-identity criterion holds (snapshots and golden strings untouched). The Oracle ORA-38104 remains a documented pre-existing defect rather than a silent one.

## Issues Encountered
- The plan assumed MSSQL/Oracle `MERGE` was executable and that MSSQL/Oracle integration tests would not run locally ("no son ejecutables en local"); in this environment all six engines run locally, so the pre-existing MERGE defects surfaced immediately. Both are now either fixed at the driver boundary (MSSQL `;`, Oracle `FROM dual`) or characterized and logged (Oracle ORA-38104).

## Known Stubs
None.

## Threat Flags
None — no new trust-boundary surface. The driver-boundary rewrites operate on the SQL template (bound parameters only), never on values, and introduce no interpolation of untrusted input. Mitigations T-02-43…T-02-47 from the plan's threat register are implemented and covered.

## Next Phase Readiness
- GAP 3 (BLOCKER) of `02-VERIFICATION.md` is closed: the three engine-parity defects are fixed, each with a regression test that fails before and passes after; `limit().all()`/`first()`/`exists()` are covered on all six engines.
- Full suite `748 passed` (baseline 731 + 17 new tests); DB-free `678 passed` (9 snapshots); integration `70 passed`; `ruff check`/`ruff format --check`/`mypy encino_orm` exit 0; `noqa` count still 0; `git diff --stat tests/__snapshots__/` empty.
- Ready for `02-09` (the `list_tables(name=)` closure), which owns the remaining item in `deferred-items.md`.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 17 modified files and this SUMMARY exist on disk.
- Task commits exist in git history: `0d4c084`, `97917ac`, `398e18f`, `7fc9f5e`, `4a2a359`, `cb2d6b8`, `7e00c31`, `d40cc8a`, `7c6cd7f`.
- Plan-level verification re-run: targeted 84 passed; DB-free 678 passed; integration 70 passed; full 748 passed; snapshots empty; both source guards OK; ruff/format/mypy exit 0; noqa 0.
