---
phase: 02-dialect-seam-engine-parity
plan: 07
subsystem: database
tags: [query, cardinality-contract, placeholder, design-doc, source-guard, gap-closure]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "immutable/hashable Query with with_params() (02-03) and the published design-doc update (D-05)"
provides:
  - "Query cardinality contract enforced at construction with no carve-out: values with no placeholder raise ValueError instead of being silently dropped"
  - "Placeholder compilation from the normalized index (int(m.group(1))): {0} and {00} resolve to the same key the params dict holds, so no KeyError escapes the adapter"
  - "docs/design/0-design.md §2.1 synchronized with the real implementation and a with_params() example that executes as written"
  - "TestDesignDocSync source guard that fails if the published doc diverges from encino_orm/query.py or documents rebind as live"
affects: [02-08, 02-09, phase-06, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Enforce a documented contract at the single construction point, with a compatibility test pinning the legitimate empty case"
    - "Normalize an input index before compiling so validation and compilation cannot disagree"
    - "Source guard reads the published doc and reproduces its example in code, making documentation truth executable"

key-files:
  created: []
  modified:
    - encino_orm/query.py
    - tests/test_query.py
    - docs/design/0-design.md

key-decisions:
  - "The 'indices and' carve-out is removed, not documented: set() != set(range(0)) is already False, so the empty/empty case needs no special condition and values-with-no-placeholder is a contract error"
  - "Compilation uses int(m.group(1)); the plan's D-04 contract is unchanged ({n} input, no named-dict mode) and rebind/format stay deleted"
  - "The design-doc with_params() example is made self-contained on a template with placeholders, and the placeholder-free reuse is shown to raise ValueError rather than silently drop"

patterns-established:
  - "Source guard for published docs: read the markdown file and assert both the sketch text and the executed example match the code"

requirements-completed: [DIAL-05]

# Metrics
duration: 3 min
completed: 2026-09-18
---

# Phase 02 Plan 07: Gap Closure — Query Cardinality Contract (WR-01 / WR-02 / WR-07) Summary

**Enforced the `Query` cardinality contract without carve-outs and compiled placeholders from the normalized index, so `Query("SELECT 1", [1])` raises `ValueError` and `{00}` resolves to `parameter_0000` instead of leaking a `KeyError`; the published design doc is now truthful and locked by a source guard**

## Performance

- **Duration:** 3 min (169 s)
- **Started:** 2026-09-18T13:34:00Z
- **Completed:** 2026-09-18T13:36:49Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Removed the `if indices and ...` carve-out in `Query.__init__`: a non-empty `values` list with zero `{n}` placeholders now raises `ValueError` (`placeholders [] no cuadran con 1 parámetros`) instead of storing parameters every `_prepare` silently discards (WR-01, T-02-39).
- Compilation now derives from the normalized index (`f"%(parameter_000{int(m.group(1))})s"`), so validation and compilation cannot disagree: `Query("a={00}", [7])` yields `sql == "a=%(parameter_0000)s"` with `params == {"parameter_0000": 7}`, and `_to_positional(q.sql, q.params) == ("a=?", [7])` — no `KeyError` from the adapter (WR-02, T-02-40).
- The `Query(sql, [])` compatibility path is preserved and pinned by tests: migrations, `list_tables` without filter and raw DDL all keep working (T-02-42).
- `docs/design/0-design.md` §2.1 now shows the enforced check and `int(m.group(1))` compilation, and the `with_params()` example is self-contained on a template that has placeholders with true expected output; `TestDesignDocSync` reproduces the example in code and fails if the doc regresses (WR-07, T-02-41).

## Task Commits

Each task was committed atomically (Task 1 followed the RED/GREEN TDD cycle):

1. **Task 1 RED: failing tests for Query cardinality contract holes** - `a953970` (test)
2. **Task 1 GREEN: enforce contract and compile from normalized index** - `c058bba` (feat)
3. **Task 2: sync design doc §2.1 and lock with a source guard** - `6433b31` (docs)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified
- `encino_orm/query.py` - dropped the `indices and` carve-out, compiled from `int(m.group(1))`, updated the docstring to state the enforced contract and `int()` normalization
- `tests/test_query.py` - new `TestContractEnforcement` (5 tests: silent-drop now raises, compatibility preserved, `{00}` normalized + translator round-trip, `{0}`/`{00}` no collision, `with_params` over a placeholder-free template raises) and new `TestDesignDocSync` (3 tests: sketch matches code, example executes to the documented values, `rebind` not documented as live)
- `docs/design/0-design.md` - §2.1 sketch and `with_params()` example corrected; migration note and the rest of the document untouched

## Decisions Made
- **Remove the carve-out rather than document it.** `set() != set(range(0))` is already `False`, so the `indices and` guard was both redundant and wrong; enforcing the contract is the D-04 behaviour the docstring already promised. The `Query(sql, [])` path is unaffected and covered by a compatibility test.
- **Normalize at compile time.** Using `int(m.group(1))` in the substitution lambda means `{0}` and `{00}` produce the same placeholder and the same params key — the adapter translator is the oracle (`_to_positional` imported directly, an accepted white-box pattern in this repo).
- **Make the doc example self-contained.** The old example reused a placeholder-free `SELECT` and claimed an INSERT result; it now builds `q` on an `insert ... values ({0},{1})` template and shows the real output, plus the `ValueError` that placeholder-free reuse raises.

## Deviations from Plan

None - plan executed exactly as written. The mandatory pre-check of `Query(` construction sites (Task 1 step E) found no latent silent-drop site: every caller passing non-empty values (`base.py:158`/`:177` count wrappers, `model.py:561` inline `insert_many`, the adapter `columns_of` queries, the migration-ledger `{{0}}` queries) supplies matching `{n}` placeholders; every placeholder-free site passes `[]`.

## Issues Encountered
None. `ruff format` reformatted the new doc-sync assertion in `tests/test_query.py` during Task 2; the formatted result still passes and the format gate is green.

## Known Stubs
None.

## Threat Flags
None — this plan reduces the threat surface. Mitigations T-02-39…T-02-42 from the plan's threat register are all implemented and covered by regression tests; no new trust-boundary surface was introduced.

## Next Phase Readiness
- GAP 2 (the `Query` cardinality contract holes) and the WR-07 doc gap are closed: both reproductions from `02-VERIFICATION.md` no longer reproduce (`Query('SELECT 1',[1])` raises `ValueError`; `Query('a={00}',[7])` compiles to `parameter_0000` and `_to_positional` resolves it).
- Full suite `731 passed` (baseline 723 + 8 new regression tests); DB-free selection `670 passed, 61 deselected`; `ruff check`/`ruff format --check`/`mypy encino_orm` exit 0; `noqa` count still 0; `mkdocs build --strict` exits 0.
- Ready for `02-08` / `02-09`; no files owned by other gap-closure plans were touched.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 3 modified files and this SUMMARY exist on disk.
- All 3 task commits (`a953970`, `c058bba`, `6433b31`) exist in git history.
- Plan-level verification re-run: `tests/test_query.py` 32 passed; DB-free suite 670 passed; full suite 731 passed; both WR-01/WR-02 reproductions no longer reproduce; ruff/format/mypy exit 0; `noqa` count 0; `mkdocs build --strict` exit 0.
