---
phase: 02-dialect-seam-engine-parity
plan: 09
subsystem: database
tags: [dialect-seam, list-tables, introspection, derived-table, oracle, postgresql, gap-closure, snapshots]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "per-engine parity classes + shared _reset/_seed_parity helpers from 02-04; DB-free dialect snapshots (syrupy spy) from 02-05; gap-closure round 02-06…02-08"
provides:
  - "Db.list_tables(name=...) filters on a REAL column of a derived table (alias encino_orm_tables) with a bound value and LOWER() on both sides — works on all six engines (was dead on 4/6)"
  - "DB-free snapshot pinning the filtered list_tables SQL for all six dialects (new .ambr entry); the unfiltered path stays byte-identical"
  - "test_list_tables_filtrado_por_nombre per-engine coverage in all six engine test files"
  - "deferred-items.md: the last orphaned Phase-2 item is CLOSED; no phase-2 item remains unowned"
affects: [02-verification, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Filter a SELECT alias by wrapping the base SQL in a derived table instead of rewriting each adapter's _tables_sql() hook"
    - "Portable case-insensitive comparison: LOWER() on both sides, because Oracle uppercases catalog names and PostgreSQL is case-sensitive by default"
    - "Byte-identity discipline: a deliberate SQL change gains a NEW snapshot entry while the existing unfiltered snapshot is the regression oracle"

key-files:
  created: []
  modified:
    - encino_orm/base.py
    - tests/test_sql_snapshots.py
    - tests/__snapshots__/test_sql_snapshots.ambr
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_postgresql.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md

key-decisions:
  - "Wrap the base SQL in a derived table (encino_orm_tables) rather than rewrite five _tables_sql() signatures: one core file, the hook contract is untouched, and the unfiltered path stays byte-identical"
  - "Compare with LOWER(name) LIKE LOWER({0}): Oracle returns catalog names in UPPERCASE and PostgreSQL is case-sensitive by default, so the SAME name= cannot work on six engines without normalisation"
  - "The filter value stays bound as {0}; check_identifier is deliberately NOT applied to name because it is a filter VALUE (contains %), not an identifier"
  - "The derived-table alias is encino_orm_tables (no leading _, Oracle ORA-00911), mirroring the existing encino_orm_count alias"
  - "The generated list_tables SQL is a DELIBERATE change; it is pinned by a new DB-free snapshot while the existing unfiltered snapshot is left untouched as the byte-identity oracle"

patterns-established:
  - "Fix a SELECT-alias-in-WHERE defect by wrapping, not by widening the adapter hook"
  - "Case-normalise catalog comparisons at the SQL seam (LOWER both sides) instead of in Python"

requirements-completed: [DIAL-03, DIAL-09]

# Metrics
duration: 3 min
completed: 2026-09-18
---

# Phase 02 Plan 09: Gap Closure — `list_tables(name=)` on a Derived Table Summary

**`Db.list_tables(name=...)` now filters on a real column of a derived table with a bound, case-normalised value on all six engines — closing the last orphaned Phase-2 deferral (GAP 4) with per-engine integration coverage and a DB-free dialect snapshot**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-18T13:54:27Z
- **Completed:** 2026-09-18T13:57:17Z
- **Tasks:** 2
- **Files modified:** 10 (+ SUMMARY.md)

## Accomplishments
- **GAP 4 closed.** The `name=` filter of `Db.list_tables` was dead on 4 of 6 engines because `name` is a SELECT **alias** (`tablename AS name`, `table_name AS name`, `TABLE_NAME AS name`) and PostgreSQL/MySQL/SQL Server/Oracle forbid referencing a column alias in `WHERE`. It now wraps the base SQL in a derived table — `SELECT * FROM (<base>) encino_orm_tables WHERE LOWER(name) LIKE LOWER({0})` — so the filter targets a **real** column, valid in all six dialects.
- **Bound value preserved.** The pattern travels as `{0}` (`params.append(f"%{name}%")`); the literal never appears in the SQL. `check_identifier` is deliberately not applied to `name` (it is a value containing `%`, not an identifier).
- **Uniform case-insensitivity.** `LOWER()` on both sides makes the same `name="test_parity"` work on Oracle (uppercase catalog names) and PostgreSQL (case-sensitive by default). `LOWER` exists in all six dialects.
- **Deliberate SQL change, documented and pinned.** A new DB-free snapshot (`test_list_tables_filtered_snapshot`) freezes the filtered SQL per dialect (new `.ambr` entry only); the existing unfiltered snapshot (`test_list_tables_snapshot`) is the byte-identity oracle and was left untouched.
- **Per-engine coverage in all six files.** `test_list_tables_filtrado_por_nombre` asserts a hit (`total >= 1`, `"test_parity"` present) and a miss (`total == 0`, `rows == []`) against the real engines, using the lowercase name on purpose.
- **Last orphan closed.** `deferred-items.md` now marks the item CLOSED under the existing `## Cerrados en la ronda de gap closure` section (no duplicate heading) and states that no Phase-2 item remains unowned.

## Deliberate SQL Change

The SQL emitted by `Db.list_tables` **changed on purpose**. The filter is no longer appended to the base SQL as `AND name LIKE {0}`; it is applied to a derived table:

- Before (filtered): `<base> AND name LIKE {0}` — references a SELECT alias → `UndefinedColumnError` (PostgreSQL) / syntax error (Oracle).
- After (filtered): `SELECT * FROM (<base>) encino_orm_tables WHERE LOWER(name) LIKE LOWER({0})`, wrapped for the count as `SELECT COUNT(*) AS n FROM (<filtered>) encino_orm_count`.
- Unfiltered path: **unchanged** — `sql = base`, same count wrapper, byte-identical to before (pinned by `test_list_tables_snapshot`, whose `.ambr` entry was not modified).

The change is visible in `tests/__snapshots__/test_sql_snapshots.ambr`: `git diff` adds the `test_list_tables_filtered_snapshot` entry (46 insertions, 0 deletions) and touches nothing else.

## Task Commits

Task 1 followed the RED/GREEN TDD cycle:

1. **Task 1 RED: failing tests for the `list_tables` name filter** - `036bd4e` (test)
2. **Task 1 GREEN: filter on a derived table with a bound value** - `81d5410` (feat)
3. **Task 2: per-engine coverage on six engines + close the deferral** - `8b9fb75` (test)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified
- `encino_orm/base.py` - `list_tables` wraps the base SQL in a derived table when `name` is set; `LOWER(name) LIKE LOWER({0})`; Spanish comment explaining the alias defect and the case-normalisation
- `tests/test_sql_snapshots.py` - `test_list_tables_filtered_snapshot` (syrupy) + 3 DB-free guards (bound value, no wrap when unfiltered, no wrap when `name=""`)
- `tests/__snapshots__/test_sql_snapshots.ambr` - new entry `test_list_tables_filtered_snapshot` for the six dialects (existing 9 entries untouched)
- `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` - `test_list_tables_filtrado_por_nombre` in each `Test<Engine>Parity` class (18 added lines each, purely additive)
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` - the orphaned `list_tables(name=)` item moved into `## Cerrados en la ronda de gap closure` and marked CLOSED by 02-09

## Decisions Made
- **Wrap, don't widen the hook.** Rewriting `_tables_sql(name: str | None)` in five adapters would change the optional-introspection contract and the byte-identity of the unfiltered path; wrapping solves it in one core file.
- **`LOWER()` on both sides at the SQL seam.** Portable across the six dialects and keeps the filter value bound; doing it in Python would require fetching the full catalog.
- **`encino_orm_tables` alias.** No leading `_` (Oracle `ORA-00911`), consistent with `encino_orm_count`.
- **Keep existing markers.** SQLite's parity class is intentionally unmarked (it is the always-on safety net), so `-m integration` selects the other five engines while SQLite's test runs in every suite. The plan's phrase "`integration` en los seis" did not match the tree; existing markers were preserved as instructed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Evidence correction] Oracle RED error is `ORA-00907`, not `ORA-00911`**
- **Found during:** Task 2 (capturing RED evidence)
- **Issue:** The plan (and the original `deferred-items.md` log) predicted `ORA-00911` for Oracle. Reverting `base.py` to the pre-fix version and running the new per-engine test produced `oracledb.exceptions.DatabaseError: ORA-00907: missing right parenthesis` instead.
- **Fix:** No code change — the fix is identical and independent of the exact Oracle error. The actual error (ORA-00907) is recorded in `deferred-items.md` and this SUMMARY; the root cause (invalid filter referencing a SELECT alias, nested inside the count wrapper) is unchanged.
- **Files modified:** `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md`
- **Verification:** RED output captured for PostgreSQL (`UndefinedColumnError: column "name" does not exist`) and Oracle (`ORA-00907`); GREEN output `5 passed` with `-m integration -k list_tables_filtrado`.
- **Committed in:** `8b9fb75` (Task 2 commit)

### Deviations accepted (not auto-fixed)

**2. [Plan sequencing artifact] Task 1's automated integration clause needs Task 2's tests**
- **Found during:** Task 1 (running `<verify><automated>`)
- **Issue:** Task 1's automated verify includes `uv run pytest -q -m integration -k "list_tables_filtrado"`, but at Task 1 time no per-engine test exists yet (it is added by Task 2), so the selector collects 0 tests (pytest exit 5).
- **Decision:** Not a functional defect. The clause was run after Task 2 added the per-engine tests; it then passed (`5 passed, 753 deselected`). The Task 1 acceptance criteria (snapshot suite, DB-free suite, source guard, ruff, mypy) all passed at Task 1 time.
- **Files modified:** none

**3. [Plan detail adjustment] SQLite parity class has no `integration` marker**
- **Found during:** Task 2 (adding per-engine tests)
- **Issue:** The plan states "`integration` en los seis", but `TestSqliteParity` (and the rest of `test_sqlite.py`) carries no `integration` marker — SQLite runs in every suite by design.
- **Decision:** Preserve the existing markers (the plan's authoritative instruction). The new SQLite test is therefore unmarked and runs in the always-on/DB-free suite; the other five are selected by `-m integration`. No marker was added or removed.
- **Files modified:** none

---

**Total deviations:** 1 auto-fixed (evidence correction) + 2 documented adjustments
**Impact on plan:** No scope creep. The single auto-fix is a documentation correction (ORA-00907 vs ORA-00911); the two adjustments reconcile the plan's wording with the tree without changing behavior. The byte-identity criterion holds: the unfiltered snapshot is untouched.

## Issues Encountered
- The RED evidence required temporarily restoring the pre-fix `base.py` (`git show HEAD~1:encino_orm/base.py`) to capture the real driver errors, then restoring the committed fix with `git checkout HEAD -- encino_orm/base.py`. Working tree confirmed clean afterwards.

## Known Stubs
None.

## Threat Flags
None — no new trust-boundary surface. The plan's mitigations are implemented: T-02-48 (value stays bound; tests assert `fields == ["%snap%"]` and no literal in the template), T-02-49 (filter on a real derived-table column, covered on six engines), T-02-50 (alias `encino_orm_tables` without a leading `_`), T-02-51 (`.ambr` only gains the new entry; the unfiltered snapshot is the byte-identity oracle), T-02-52 (`grep -c` == 1 per engine file for the new test name).

## Next Phase Readiness
- GAP 4 (partial) of `02-VERIFICATION.md` is closed: `list_tables(name=)` works on all six engines with a per-engine regression test and a DB-free dialect snapshot; DIAL-03 is no longer partial.
- `deferred-items.md` leaves no Phase-2 item unowned.
- Verification: full suite `758 passed` (baseline 748 + 10 new tests: 4 DB-free + 6 per-engine); `uv run pytest tests/test_sql_snapshots.py -q` → 10 snapshots / 13 passed; `-m integration -k list_tables_filtrado` → 5 passed; DB-free suite → 683 passed; `ruff check` / `ruff format --check` / `mypy encino_orm` exit 0; `noqa` count still 0; `.ambr` diff is additive only.
- Phase 02 has no remaining plans (02-01…02-09 all executed); ready for phase verification.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 10 modified files and this SUMMARY exist on disk.
- Task commits exist in git history: `036bd4e`, `81d5410`, `8b9fb75`.
- Plan-level verification re-run: full `758 passed`; snapshots 10 passed; integration `-k list_tables_filtrado` 5 passed; DB-free 683 passed; source guard OK; ruff/format/mypy exit 0; noqa 0; `.ambr` additive only.
