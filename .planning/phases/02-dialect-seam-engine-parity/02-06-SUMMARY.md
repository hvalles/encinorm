---
phase: 02-dialect-seam-engine-parity
plan: 06
subsystem: database
tags: [sql-injection, identifier-validation, query-builder, ddl, allowlist, gap-closure]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "single-sourced identifier allowlist (dialects/identifiers.py) and shared DML builders (dialects/builders.py)"
provides:
  - "QueryBuilder alias validation through the strict allowlist at all three entry points (constructor, join, join_subquery)"
  - "default pydantic field name validated at the single column-map construction point, inherited by to_ddl/insert_many/indexes_ddl"
  - "fail-closed indexes_ddl resolution of unmapped index columns (no raw caller-string interpolation)"
  - "regression tests reproducing the literal CR-01 UNION payload and the WR-06 hostile field name, with a driver spy proving zero queries"
affects: [02-07, 02-08, 02-09, phase-06, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Validate identifiers at the single construction point so every downstream consumer inherits the check"
    - "Fail-closed fallback: reject an unmapped/non-identifier spec instead of interpolating it verbatim"
    - "Driver spy (recording fake Db) proves validation happens before any query is executed"

key-files:
  created: []
  modified:
    - encino_orm/model/query_builder.py
    - encino_orm/model/model.py
    - encino_orm/model/types.py
    - tests/test_query_builder.py
    - tests/test_identifiers.py
    - tests/test_index.py
    - CHANGELOG.md

key-decisions:
  - "QueryBuilder aliases go through the STRICT allowlist (check_identifier), not the dot-tolerant _COLUMN_RE; a legitimate alias is always a bare identifier, so no escape hatch is added"
  - "The default pydantic field name is validated once in _build_column_map so to_ddl, insert_many and indexes_ddl inherit the check without per-consumer changes"
  - "indexes_ddl is now fail-closed for unmapped non-identifier specs; this is a deliberate public behaviour change documented in CHANGELOG.md [Unreleased]"
  - "Each task followed the RED/GREEN TDD cycle (failing test committed before the fix), producing four bisectable commits"

patterns-established:
  - "Alias/identifier validation happens before the duplicate check so a hostile alias fails as an invalid identifier, not as a duplicate"

requirements-completed: [DIAL-01, DIAL-02]

# Metrics
duration: 2 min
completed: 2026-09-18
---

# Phase 02 Plan 06: Gap Closure — Identifier Choke Point (CR-01 / WR-06) Summary

**Closed the reproduced `QueryBuilder` alias SQL-injection primitive (CR-01) and the unvalidated default-column-name / `indexes_ddl` bypass (WR-06), making the identifier allowlist a real choke point without relaxing it**

## Performance

- **Duration:** 2 min (179 s)
- **Started:** 2026-09-18T13:28:06Z
- **Completed:** 2026-09-18T13:31:05Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- `QueryBuilder(alias=)`, `join(alias=)` and `join_subquery(alias=)` now validate through `check_identifier(alias, "alias")`; the literal payload `'mm WHERE 1=0 UNION SELECT nombre FROM usuarios --'` raises `ValueError` before any SQL is built, and a recording `Db` double proves `fetch_all`/`fetch_many` receive zero calls.
- The default pydantic field name is validated in `_build_column_map` (the single point where the map is built), so `to_ddl()`, `Model.insert_many()` and `indexes_ddl()` are fail-closed for non-identifier names without touching those consumers.
- `indexes_ddl` no longer interpolates an unmapped caller string verbatim: it resolves against the column map or validates the spec, and the deliberate public behaviour change is recorded in `CHANGELOG.md` `[Unreleased]`.
- Legitimate paths are byte-identical: aliases `mm`/`r`/`sq1_mm`, `Column(name=...)` mappings and simple unmapped index identifiers still produce the same SQL; the existing `join`/`join_subquery`/`test_column_mapping` tests pass unedited.

## Task Commits

Each task was committed atomically (TDD: failing test, then implementation):

1. **Task 1 RED: failing regression tests for QueryBuilder alias injection** - `6ef8c43` (test)
2. **Task 1 GREEN: validate QueryBuilder aliases with the strict allowlist** - `b2ad59e` (feat)
3. **Task 2 RED: failing regression tests for default column name and index columns** - `00042c1` (test)
4. **Task 2 GREEN: validate default column names and close indexes_ddl raw fallback** - `f58fcf5` (feat)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified
- `encino_orm/model/query_builder.py` - import + `check_identifier(alias, "alias")` in `__init__`, `join()` and `join_subquery()`; derived alias structures built from the validated value
- `encino_orm/model/model.py` - `_build_column_map` validates the default field name (`col = check_identifier(name, "nombre de columna")`)
- `encino_orm/model/types.py` - `indexes_ddl` resolves unmapped index columns through `check_identifier` (both the plain and `(col, "ASC"|"DESC")` branches)
- `tests/test_query_builder.py` - `_RecordingDb` gains `fetch_all`/`fetch_many`; new `TestAliasInjection` (7 tests)
- `tests/test_identifiers.py` - new `TestNombreDeColumnaPorDefecto` (4 tests)
- `tests/test_index.py` - two new `TestIndexesDdl` tests for the unmapped-column fail-closed path
- `CHANGELOG.md` - `### Corregido` section under `[Unreleased]`

## Decisions Made
- **Strict allowlist for aliases, no escape hatch.** A legitimate table alias is always a bare identifier; `_COLUMN_RE`'s dot tolerance is for qualified column expressions only and was left untouched.
- **One validation point for column names.** Validating the default field name in `_build_column_map` covers DDL and the inline multi-row `insert_many` DML without duplicating the check.
- **`indexes_ddl` fail-closed is deliberate.** An unmapped spec that is not a simple identifier now raises instead of passing through; documented in `CHANGELOG.md` with the additive/ownership note (Phase 8 / `08-04` owns the breaking-change enumeration).
- **CHANGELOG entry also mentions the default-column-name validation** in the same `[Unreleased]` entry, since both are public fail-closed changes shipped by this plan.

## Deviations from Plan

None - plan executed exactly as written. The four-commit TDD shape (RED then GREEN per task) follows the tasks' `tdd="true"` attribute; the plan's `<action>` blocks already bundled each task's tests and implementation, so the RED/GREEN split is the canonical TDD rendering of the same work.

## Issues Encountered
None.

## Known Stubs
None.

## Threat Flags
None — this plan reduces the threat surface. Mitigations T-02-34…T-02-38 from the plan's threat register are all implemented and covered by regression tests; no new trust-boundary surface was introduced.

## Next Phase Readiness
- GAP 1 (phase goal clause 1: identifier validation as a real choke point) is closed: both reproduced bypasses now raise `ValueError` before the driver, and the allowlist keeps a single strict definition (source guard green).
- Full suite `723 passed` (baseline 710 + 13 new regression tests); `ruff check`/`ruff format --check`/`mypy encino_orm` exit 0; `noqa` count still 0.
- Ready for `02-07` (Query cardinality contract), which owns `query.py`, `tests/test_query.py` and `docs/design/0-design.md` — untouched by this plan.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 7 modified files and this SUMMARY exist on disk.
- All 4 task commits (`6ef8c43`, `b2ad59e`, `00042c1`, `f58fcf5`) exist in git history.
- Plan-level verification re-run: targeted files 58 passed; DB-free suite 662 passed; full suite 723 passed; both CR-01 and WR-06 reproductions raise `ValueError`; ruff/format/mypy exit 0; `noqa` count 0.

