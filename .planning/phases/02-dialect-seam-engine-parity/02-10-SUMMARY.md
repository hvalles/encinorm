---
phase: 02-dialect-seam-engine-parity
plan: 10
subsystem: database
tags: [sql-injection, identifier-validation, query-builder, allowlist, gap-closure, cr-01]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "single-sourced strict identifier allowlist (dialects/identifiers.py) and QueryBuilder alias validation at all three entry points (02-06)"
provides:
  - "QueryBuilder.__init__ validates model_class._table with the STRICT allowlist (fail-closed, unconditional)"
  - "QueryBuilder.join validates other._table with the STRICT allowlist before the duplicate-alias check"
  - "documented identifier contract for QueryBuilder plus a source guard pinning the two strict _table validations"
  - "characterization tests for every expression interpolation position (select/group_by/order_by/sort_by/aggregates/column alias)"
affects: [02-11, phase-06, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Validate identifiers at the public boundary (constructor/join) so no unvalidated _table reaches FROM/JOIN"
    - "Strict allowlist (check_identifier) for table names and aliases; dot-tolerant _COLUMN_RE only for expression positions, documented as deliberate and never unified"
    - "Source guard (inspect.getsource + file read) pins the validation points so reintroducing an unvalidated _table breaks a test"

key-files:
  created: []
  modified:
    - encino_orm/model/query_builder.py
    - tests/test_query_builder.py

key-decisions:
  - "Table-name validation is UNCONDITIONAL (no `if cls._table:` guard as in _build_column_map): an empty/non-str _table now raises ValueError fail-closed instead of emitting invalid `FROM  mm`"
  - "join() validates the JOIN target's _table next to the alias and BEFORE the duplicate check, so a hostile target fails as an invalid identifier, not as a duplicate alias"
  - "Expression positions keep the dot-tolerant _COLUMN_RE by decision (Pitfall 10): unifying it would be a behaviour change and relaxing it would reopen the injection surface; the sweep fixes that decision with tests instead of changing it"

patterns-established:
  - "The QueryBuilder module now declares its identifier contract in _build_base (strict for _table/alias, dot-tolerant for expressions) and a source guard enforces it"

requirements-completed: [DIAL-01, DIAL-02]

# Metrics
duration: 4 min
completed: 2026-09-18
---

# Phase 02 Plan 10: Gap Closure Round 2 — QueryBuilder `_table` Choke Point (CR-01) Summary

**Closed the reproduced CR-01 SQL-injection vector through the model `_table`: `QueryBuilder.__init__` and `join()` now validate table names with the strict allowlist, so `QueryBuilder(Evil, None)` with `_table = 't; DROP TABLE usuarios --'` raises `ValueError` before any SQL or driver call, while legitimate SQL stays byte-identical.**

## Performance

- **Duration:** 4 min (225 s)
- **Started:** 2026-09-18T14:25:22Z
- **Completed:** 2026-09-18T14:29:07Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `QueryBuilder.__init__` now calls `check_identifier(model_class._table, "nombre de tabla")` (unconditional, fail-closed). The literal payload from the verification report — a dynamically created model with `_table = "t; DROP TABLE usuarios --"` — raises `ValueError` in the constructor, where previously `_build_base()[0]` returned `'FROM t; DROP TABLE usuarios -- mm'`.
- `QueryBuilder.join()` now calls `check_identifier(other._table, "nombre de tabla")` next to the alias validation and before the duplicate check, so a hostile JOIN target fails as an invalid identifier (tested with a valid alias, so the failure can only come from the `_table`).
- A recording `Db` double proves the driver is never reached: `await QueryBuilder(Evil, fake).all()` raises `ValueError` with `fake.queries == []`.
- The legitimate path is byte-identical: `QueryBuilder(Agente, None)._build_base()[0] == "FROM agentes mm"` and a valid table JOIN still emits `JOIN regiones r ON ...`. No snapshot or per-engine golden string changed.
- The sweep documents and pins the module's identifier contract: every expression position (`select`/`group_by`/`order_by`/`sort_by`/`sum`/`avg`/`min`/`max`/column alias) rejects hostile payloads through `_safe_column` and accepts `mm.agente`; a source guard asserts exactly two strict `_table` validations and that `_build_base` only interpolates the already-validated references. `_table` is confirmed as the last interpolation point that needed the strict allowlist.

## Task Commits

Each task was committed atomically (TDD: failing test, then implementation):

1. **Task 1 RED: failing regression tests for unvalidated QueryBuilder `_table`** - `d4df155` (test)
2. **Task 1 GREEN: validate QueryBuilder table names with the strict allowlist** - `d82649d` (feat)
3. **Task 2 RED: failing sweep evidence for QueryBuilder interpolation points** - `0da8d63` (test)
4. **Task 2 GREEN: declare the QueryBuilder identifier contract in `_build_base`** - `5fc034a` (docs)

**Plan metadata:** `pending` (docs: complete plan)

_Note: Task 2's GREEN change is documentation-only (the module contract comment), so its commit type is `docs` rather than `feat`. The plan-level RED/GREEN gate is satisfied by Task 1's `test` → `feat` sequence._

## Files Created/Modified
- `encino_orm/model/query_builder.py` - `check_identifier(model_class._table, "nombre de tabla")` in `__init__`; `check_identifier(other._table, "nombre de tabla")` in `join()`; identifier-contract comment in `_build_base`. `_COLUMN_RE` and `_safe_column` untouched.
- `tests/test_query_builder.py` - new `TestTablaInjection` (6 tests) and `TestBarridoDeIdentificadores` (10 tests); `create_model` import added.

## Decisions Made
- **Unconditional table validation.** Unlike `_build_column_map`'s `if cls._table:` guard, `QueryBuilder` rejects an empty/non-str `_table` fail-closed: a model with no table cannot produce valid SQL, so `FROM  mm` is never emitted.
- **Strict allowlist for table names, dot-tolerant for expressions.** A table name is always a bare identifier (qualified names go through the builders' `schema=` parameter), so `check_identifier` is used; `_COLUMN_RE` is kept for expression positions and deliberately not unified (Pitfall 10).
- **Validate before the duplicate check.** A hostile JOIN target must fail as an invalid identifier, not as a duplicate alias — the invariant 02-06 established for aliases is extended to `_table`.
- **Aggregate test uses a fake db.** `sum/avg/min/max` call `_ensure_db()` before `_safe_column`, so `db=None` would raise from `_ensure_db` and mask the column check; the test supplies a fake db and asserts the `"nombre de columna inválido"` message.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Known Stubs
None.

## Threat Flags
None — this plan reduces the threat surface. Mitigations T-02-53 (constructor `_table`), T-02-54 (join target `_table`), T-02-55 (expression positions characterized) and T-02-56 (empty `_table` fail-closed) from the plan's threat register are all implemented and covered by regression tests. No new trust-boundary surface was introduced.

## Next Phase Readiness
- GAP A / CR-01 (round 2) is closed: no non-identifier `_table` reaches the `QueryBuilder` `FROM`/`JOIN`; validation lives at the public boundary with the already-centralized strict allowlist, and the sweep confirms it was the last unvalidated interpolation point.
- Full suite `774 passed` (baseline 758 + 16 new tests); DB-free suite `699 passed` (683 + 16); `ruff check`/`ruff format --check`/`mypy encino_orm` exit 0; `noqa` count still 0; 10 snapshots pass and `tests/__snapshots__/` is untouched.
- `02-11` (merge upsert / MSSQL stale id, CR-02/CR-03) runs in the same wave and touches `dialects/builders.py`, `model/model.py`, `tests/test_dialect_builders.py`, `tests/test_mssql.py`, `tests/test_oracle.py` — none of which this plan modified.

## TDD Gate Compliance

| Task | RED | GREEN | Status |
|------|-----|-------|--------|
| Task 1 (`_table` validation) | `d4df155` (test) | `d82649d` (feat) | Pass |
| Task 2 (sweep + contract) | `0da8d63` (test) | `5fc034a` (docs) | Pass (GREEN is doc-only; see note) |

Plan-level RED (`test(02-10)`) and GREEN (`feat(02-10)`) commits are both present.

## Self-Check: PASSED

- Both modified files and this SUMMARY exist on disk.
- All 4 task commits (`d4df155`, `d82649d`, `0da8d63`, `5fc034a`) exist in git history.
- Plan-level verification re-run: `tests/test_query_builder.py` 40 passed; DB-free suite 699 passed; full suite 774 passed; both `<verify><automated>` commands exit 0; CR-01 reproducer raises `ValueError: nombre de tabla inválido: 't; DROP TABLE usuarios --'`; `QueryBuilder(Agente, None)._build_base()[0] == "FROM agentes mm"`; `git diff --stat tests/__snapshots__/` empty; ruff/format/mypy exit 0; `noqa` count 0.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*
