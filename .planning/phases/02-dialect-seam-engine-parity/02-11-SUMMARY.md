---
phase: 02-dialect-seam-engine-parity
plan: 11
subsystem: database
tags: [dialect-seam, merge, upsert, mssql, oracle, last-id, gap-closure, cr-02, cr-03]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "shared DML builders (dialects/builders.py) + UPSERT_KIND map (02-02) and the MSSQL/Oracle MERGE made executable at the driver boundary (02-08)"
provides:
  - "fail-closed guard in _merge_sql: every conflict column must be present in the INSERT columns, else an actionable ValueError (single choke point for build_insert/build_upsert)"
  - "Model.upsert documents that on merge dialects the conflict target must be a data column and an auto-PK model requires an explicit conflict="
  - "Model.insert does not consume or assign last_id() when the executed statement is a MERGE (returns 0, leaves obj.id intact)"
  - "first live Model.upsert coverage on MSSQL and Oracle (previously zero) plus the corrected MSSQL insert(replace=True) id semantics"
affects: [02-12, phase-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail closed at the shared render choke point instead of deriving a silent default: a conflict column absent from the INSERT columns is a caller error, not a value to guess"
    - "Decide by the executed statement text (MERGE vs INSERT), never by a cached driver value that only INSERT refreshes"
    - "Declare driver-boundary id semantics in the docstring and pin them with a double that returns a deliberately stale last_id()"

key-files:
  created: []
  modified:
    - encino_orm/dialects/builders.py
    - encino_orm/model/model.py
    - tests/test_dialect_builders.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_d_recommendations.py

key-decisions:
  - "CR-02: fail closed in _merge_sql (the single point shared by build_insert and build_upsert) rather than deriving a default conflict column; the error names the missing column and tells the caller to pass conflict= with a data column"
  - "CR-03: Model.insert stops consuming/assigning last_id() on a MERGE, returning 0 ('id no disponible') and leaving obj.id untouched; capturing the real id (OUTPUT INSERTED.id) is owned by Phase 4 / POOL-03"
  - "Zero SQL change for valid inputs: the guard only adds rejection; snapshots, golden strings and encino_orm/mssql.py / oracle.py are untouched"
  - "Oracle is covered for the same defect class by the DB-free double (dialect=oracle) because the Oracle merge path is still non-executable today (ORA-38104, characterized, owner Phase 4)"

patterns-established:
  - "A regression introduced by a driver-boundary fix is closed by making the core decide from the statement it built, not by re-reading driver state the fix did not update"

requirements-completed: [DIAL-02, DIAL-09]

# Metrics
duration: 4 min
completed: 2026-09-18
---

# Phase 02 Plan 11: Gap Closure Round 2 — Merge Conflict Guard & Stale `last_id` (CR-02/CR-03) Summary

**The shared MERGE render now fails closed with an actionable `ValueError` when a conflict column is absent from the INSERT, and `Model.insert(replace=True)` on MSSQL/Oracle no longer returns or assigns another row's stale id — with the first live `Model.upsert` coverage on both merge engines.**

## Performance

- **Duration:** 4 min (247 s)
- **Started:** 2026-09-18T14:32:02Z
- **Completed:** 2026-09-18T14:36:09Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- **CR-02 closed.** `_merge_sql` — the single render point shared by `build_insert` and `build_upsert` — now rejects any conflict column absent from the INSERT columns with `ValueError("conflicto ['id'] no está en el INSERT; en MERGE el objetivo debe ser una columna presente en los datos (pasa conflict=...)")`. The `src` derived table only carries the `data` columns, so the previously emitted `ON (dst.id = src.id)` referenced a nonexistent column (MSSQL 207 / ORA-00904).
- **Live `Model.upsert` coverage added on both merge engines (was zero).** `Model.upsert(conflict=["nombre"])` is executable and idempotent on live MSSQL and Oracle (two calls leave one row with the latest `monto`), and `Model.upsert()` with the documented default (PK) now fails closed with the actionable `ValueError` instead of a driver error.
- **CR-03 closed.** `Model.insert` captures the `Query` it executed and, when its `sql_template` starts with `MERGE`, returns `None` without calling `last_id()`. The method returns `0` ("id no disponible") and leaves `self.id` intact, so a later `obj.update()` can no longer target another row. The non-merge paths (plain INSERT and PostgreSQL `replace`) still consume `last_id()` exactly as before.
- **Byte-identity preserved.** `git diff --stat tests/__snapshots__/` is empty and `encino_orm/mssql.py` / `encino_orm/oracle.py` are unchanged; the guard only adds rejection for invalid input.
- **Oracle covered for the same defect class** via the DB-free double (`dialect="oracle"`) and a live test that pins `zoe.id is None` while the pre-existing ORA-38104 characterization stays intact.

## Task Commits

Each task followed the RED/GREEN TDD cycle:

1. **Task 1 RED: failing tests for the merge conflict guard (CR-02)** - `c2f0fd0` (test)
2. **Task 1 GREEN: fail closed in the merge render for absent conflict columns** - `b42a4ce` (feat)
3. **Task 2 RED: failing tests for stale `last_id` on MERGE (CR-03)** - `897a3a4` (test)
4. **Task 2 GREEN: `Model.insert` does not consume a stale `last_id` on MERGE** - `ab234eb` (feat)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified
- `encino_orm/dialects/builders.py` - `_merge_sql` computes `missing = [c for c in conflict_cols if c not in columns]` and raises an actionable `ValueError`; Spanish comment documents the reproduced defect and the fail-closed choice.
- `encino_orm/model/model.py` - `Model.upsert` docstring declares the merge-dialect conflict contract; `Model.insert` gained a docstring plus the MERGE decision (`startswith("MERGE")` → `None`), and assignment/return now guard on `new_id is not None`.
- `tests/test_dialect_builders.py` - new `TestMergeConflictGuard` (5 tests) and `_ModelDbMerge` + `TestModelInsertMergeNoConsumeIdObsoleto` (3 tests).
- `tests/test_mssql.py` - `from typing import ClassVar`; `_MergeModel`; two live upsert tests; `test_model_insert_replace_no_rompe_el_merge` rewritten to assert `devuelto == 0`, `zoe.id is None`, `zoe.id != ana.id` and one Zoe row.
- `tests/test_oracle.py` - two live upsert tests; `test_model_insert_replace_no_asigna_id_ajeno` (ORA-38104 characterization + `zoe.id is None`).
- `tests/test_d_recommendations.py` - `LockDb.insert` returns a real `Query` instead of a tuple (Rule 3 fix).

## Decisions Made
- **Fail closed at the single choke point, not a silent default.** Deriving a "representative" conflict column would reintroduce the same semantic defect CR-02 denounces; the model does not reliably declare UNIQUEs. An auto-PK `Model.upsert()` is inexpressible on MSSQL/Oracle by construction (the PK does not travel in the INSERT) and now fails loudly.
- **Do not "refresh" `_last_id` for MERGE.** In the reproduced scenario the MERGE matches an existing row (it does not insert), so the identity is NULL anyway; capturing the real id requires `OUTPUT INSERTED.id`, owned by Phase 4 / POOL-03.
- **No SQL change.** Both fixes are Python guards/decisions; valid-input SQL is byte-identical and the committed MERGE snapshots (in-column conflict target) do not trip the guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `LockDb` double returned a tuple from `insert()`**
- **Found during:** Task 2 GREEN (full-suite run)
- **Issue:** `tests/test_d_recommendations.py::TestD4AutoRetry` uses a hand-written `LockDb(Db)` whose `insert()` returned `("INSERT", tabla, data)`. The new `Model.insert` reads `qry.sql_template`, so the test failed with `AttributeError: 'tuple' object has no attribute 'sql_template'` at `model.py:521`.
- **Fix:** `LockDb.insert` now returns `Query("INSERT INTO p VALUES ({0})", [1])`, matching the real `Db.insert` contract (the same stale-double class 02-08 aligned for the abstract signature).
- **Files modified:** `tests/test_d_recommendations.py`
- **Verification:** DB-free suite `707 passed` (was `1 failed, 706 passed`); full suite `787 passed`.
- **Committed in:** `ab234eb` (Task 2 GREEN)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The fix is directly caused by the Task 2 change and is confined to a test double; no production behaviour or SQL changed. No scope creep.

## Issues Encountered
- The plan's DB-free acceptance for Task 2 assumed no other double returned a non-`Query` from `insert()`; `LockDb` did. Resolved as the Rule 3 deviation above.

## Known Stubs
None.

## Threat Flags
None — this plan reduces the threat surface. Mitigations T-02-57 (fail-closed `_merge_sql`), T-02-58 (actionable error before the driver), T-02-59 (no stale id assigned on MERGE), T-02-60 (identifier allowlist unchanged) and T-02-61 (snapshots/golden strings untouched) from the plan's threat register are all implemented and covered by regression tests. No new trust-boundary surface was introduced.

## TDD Gate Compliance

| Task | RED | GREEN | Status |
|------|-----|-------|--------|
| Task 1 (CR-02 merge guard) | `c2f0fd0` (test) | `b42a4ce` (feat) | Pass |
| Task 2 (CR-03 stale last_id) | `897a3a4` (test) | `ab234eb` (feat) | Pass |

RED evidence captured before each fix:
- **CR-02 DB-free:** `DID NOT RAISE ValueError` for the absent-conflict render; `Model.upsert` default-PK double also did not raise.
- **CR-02 live:** MSSQL `ProgrammingError 42S22 "Invalid column name 'id'. (207)"`; Oracle `oracledb.exceptions.DatabaseError: ORA-00904: "SRC"."ID": invalid identifier`.
- **CR-03 DB-free:** `assert 1 == 0` (the stale `last_id()` value).
- **CR-03 live MSSQL:** `assert 1 == 0` (the id of Ana returned for Zoe).

## Next Phase Readiness
- GAP B / CR-02 and GAP C / CR-03 are closed: the merge render cannot emit `ON (dst.<c> = src.<c>)` for a column absent from `src`, and `Model.insert(replace=True)` no longer silently hands back another row's id.
- Full suite `787 passed` (baseline 774 + 13 new tests: 8 DB-free + 5 live); DB-free suite `707 passed`; `ruff check` / `ruff format --check` / `mypy encino_orm` exit 0; `# noqa` count still 0; 10 snapshots pass and `tests/__snapshots__/` is untouched.
- Oracle's ORA-38104 MERGE limitation remains a characterized, documented pre-existing defect owned by Phase 4 (POOL-03), which also owns capturing the real id inside the insert.

## Self-Check: PASSED

- All 6 modified files and this SUMMARY exist on disk.
- All 4 task commits (`c2f0fd0`, `b42a4ce`, `897a3a4`, `ab234eb`) exist in git history.
- Plan-level verification re-run: `tests/test_dialect_builders.py` 68 passed; `-m integration -k "model_upsert"` 5 passed; `-m integration -k "insert_replace"` 6 passed; DB-free 707 passed; full 787 passed; `git diff --stat tests/__snapshots__/` empty; `git diff --stat encino_orm/mssql.py encino_orm/oracle.py` empty; both `<verify><automated>` python checks print OK; ruff/format/mypy exit 0; `noqa` count 0.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*
