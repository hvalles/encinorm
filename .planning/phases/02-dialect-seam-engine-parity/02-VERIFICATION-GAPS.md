---
phase: 02-dialect-seam-engine-parity
verified: 2026-09-18T14:07:19Z
status: gaps_found
score: 2/5 original gaps fully closed, 2 partial, 1 deferred; 0/5 new findings closed
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 29/32 must-haves verified
  gaps_closed:
    - "GAP 2 — Query cardinality contract (silent param drop + {00} KeyError) and the published design-doc example"
    - "GAP 4 — Db.list_tables(name=) filter on the four engines where it was dead"
  gaps_remaining:
    - "GAP 1 (partial) — QueryBuilder alias and default column name fixed, but the model _table still reaches FROM/JOIN unvalidated (CR-01)"
    - "GAP 3 (partial) — inline LIMIT / MariaDB upsert / PG insert conflict target fixed, but the merge upsert (CR-02) and MSSQL stale last_id (CR-03) survive"
  regressions:
    - "CR-03 — MSSQL Model.insert(replace=True) now silently returns a stale primary key (it used to fail loudly with error 10713); 02-08 introduced this data-integrity exposure"
gaps:
  - truth: "Identifier validation is a real choke point inside the core (phase goal clause 1); no identifier reaches SQL interpolation without passing the single allowlist"
    status: failed
    reason: >-
      The public `alias=`/`join(alias=)`/`join_subquery(alias=)` vectors are closed, but `_build_base()`
      still interpolates the model class's `_table` (and each join target's `_table`) with no validation.
      `Model._table` is only validated inside `Model._build_column_map()`, which `QueryBuilder` never
      triggers (it calls `_column_map()` only for `select("alias.*")`). Same defect class the round was
      chartered to eliminate.
    artifacts:
      - path: "encino_orm/model/query_builder.py"
        issue: "`:189` `sql = f\"FROM {self._model_class._table} {self._alias}\"` and `:195` `JOIN {join['model_class']._table}` interpolate unvalidated table names."
    missing:
      - "Validate `model_class._table` in `QueryBuilder.__init__` and `other._table` in `join()`, or force `_column_map()` before building SQL."
      - "Regression test with a dynamically created model whose `_table` is `'t; DROP TABLE usuarios --'`, asserting `ValueError`."

  - truth: "The library returns correct results on all six engines (phase goal clause 2); Model.upsert works with its documented default conflict"
    status: failed
    reason: >-
      `Model.upsert()` documents `conflict=None` as 'primary key'. For an auto-PK model the PK `id` is
      excluded from `data`, so the MERGE `src` derived table has no `id` column, yet the generated `ON`
      clause is `dst.id = src.id`. Live-reproduced on both merge engines. The defect is untested on
      MSSQL/Oracle and is not logged in `deferred-items.md`.
    artifacts:
      - path: "encino_orm/model/model.py"
        issue: "`:604` `conflict_cols = [self._col(c) for c in conflict]` with `:588-589` defaulting `conflict` to `_pk_fields()`; `:616-624` passes it to `build_upsert` for the `merge` render."
      - path: "encino_orm/dialects/builders.py"
        issue: "`:41-42`, `:220` — `_merge_sql` emits `ON (dst.<c> = src.<c>)` for every conflict column without checking it exists in the `src` SELECT list."
    missing:
      - "Fail closed in `build_upsert` for the `merge` render when a conflict column is absent from the insert columns, or derive the default from a data/UNIQUE column, or require an explicit `conflict=` on MSSQL/Oracle."
      - "Log the item in `deferred-items.md` with an owner."
      - "Add MSSQL/Oracle regression coverage for `Model.upsert()`."

  - truth: "Model.insert(replace=True) on MSSQL returns the id of the row it just inserted"
    status: failed
    reason: >-
      02-08 made the MSSQL MERGE executable by appending `;`, but `MssqlDb.execute` only refreshes
      `_last_id` for statements whose text starts with `INSERT`. A `MERGE` never refreshes it, and
      `Model.insert` unconditionally consumes `last_id()` and assigns it to `self.id`. Live-reproduced:
      after inserting Ana (id=1), `insert(replace=True)` for Zoe returns 1 and sets `z.id = 1`. A
      subsequent `obj.update()` would target Ana's row. This is a regression introduced by this round
      (the call previously failed loudly with error 10713).
    artifacts:
      - path: "encino_orm/mssql.py"
        issue: "`:252` refreshes `_last_id` only for `INSERT`; `:314-315` `last_id()` returns the cached value."
      - path: "encino_orm/model/model.py"
        issue: "`:508` always consumes `last_id()`; `:512-515` assigns it to `self.id` for an auto-PK model."
    missing:
      - "Capture the id inside the MERGE (`OUTPUT INSERTED.id`, `SCOPE_IDENTITY()`) or refresh `_last_id` for `MERGE`."
      - "At minimum, assert the current (wrong) value in the existing test so CI fails when it is corrected, and document the unreliable id."
    note: "The general fix is owned by Phase 4 (POOL-03 / SC2: capture last_id inside the insert). Because 02-08 introduced this exposure, it is reported as a regression rather than silently deferred."

  - truth: "The phase's deferral log is accurate and every deferred Phase-2 item has an owner"
    status: failed
    reason: >-
      `deferred-items.md` states 'Ya NO queda ningún item de la Fase 02 sin dueño', but the Oracle
      ORA-38104 entry is marked PENDIENTE and its 'sugerencia para una fase futura' names no phase; no
      later milestone phase (3–8) mentions ORA-38104 or the Oracle MERGE. The CR-02 `Model.upsert`
      defect is not logged at all.
    artifacts:
      - path: ".planning/phases/02-dialect-seam-engine-parity/deferred-items.md"
        issue: "`:10-11` claims no unowned item; `:114-135` ORA-38104 is PENDIENTE with no owner; no entry for CR-02."
    missing:
      - "Assign an owner (phase/plan ID) to ORA-38104 and to the CR-02 merge-upsert defect, or reword the header."

  - truth: "The 02-07 Query cardinality behaviour change is recorded in CHANGELOG.md (0.x hard project constraint)"
    status: failed
    reason: >-
      `Query("SELECT 1", [1])` was previously accepted (value silently dropped) and now raises
      `ValueError`; `{00}` compiles to a different placeholder key. The three 02-07 commits
      (`a953970`, `c058bba`, `6433b31`) touched no `CHANGELOG.md`; 02-06 and 02-08 added `### Corregido`
      entries. Phase 8 SC3 owns the complete milestone enumeration, but the round's own practice was to
      log each `[Unreleased]` entry immediately.
    artifacts:
      - path: "CHANGELOG.md"
        issue: "`[Unreleased]` has no entry for the 02-07 cardinality change (nor for the `rebind`/`format` removal, already deferred to Phase 8)."
    missing:
      - "Add an `[Unreleased]` bullet describing the enforced cardinality contract and the `{00}` normalization."

deferred:
  - truth: "Per-adapter coverage floors (including oracle.py) are fixed from a measured run"
    addressed_in: "Not planned — blocked on a green engine-heavy run"
    evidence: "ROADMAP Phase 2 gap-closure note: 'GAP 5 (per-adapter coverage floors) stays deferred pending a green engine-heavy run and is NOT planned here'. Legitimately deferred, not a gap."
  - truth: "CHANGELOG.md enumerates the breaking `rebind`/`format` removal and the 0.3.0 version wording"
    addressed_in: "Phase 8 (Release 0.3.0)"
    evidence: "ROADMAP Phase 8 SC3 ('CHANGELOG.md enumerates every breaking change with old and new behavior') + plan 08-04. This covers the removal; the 02-07 cardinality entry (WR-02) is still reported as a gap because it was a same-round omission."

human_verification:
  - test: "Run the `engine-heavy` GitHub Actions job (MSSQL + Oracle) end to end on a real runner."
    expected: "Job goes GREEN: ODBC install step succeeds, `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle` fails (not skips) if a service is down, file-based test selection never collects zero tests, `check_skips.py` reports 0 skips, and the coverage artifact uploads."
    why_human: "Requires a GitHub Actions run; only structural wiring was verified locally."
  - test: "Induced-failure check: remove the MariaDB service from the `test` job on a scratch branch and push."
    expected: "The `test` job goes RED, not skip."
    why_human: "Requires a live CI run."
  - test: "Probe the ad-hoc parameter ceilings for MSSQL (2100) and Oracle (65535) inside `engine-heavy`."
    expected: "The measured value is annotated next to the constant in `dialects/strategies.py`, replacing 'NO verificado empíricamente'."
    why_human: "Requires the heavy engines; constants are documented but unverified."
  - test: "Decide whether `engine-heavy` runs per-PR or only on push to main + workflow_dispatch."
    expected: "A recorded decision; advisory (`continue-on-error`) is forbidden."
    why_human: "Cost/time trade-off."
  - test: "Decide whether CR-01, CR-02 and CR-03 are accepted as overrides or opened as gap-closure plans."
    expected: "An explicit decision recorded in frontmatter (`overrides:`) or a follow-up plan."
    why_human: "Whether the phase's goal clauses must be made literally true now, or the defects accepted as pre-existing/regression work for later phases, is a developer call."
---

# Phase 2 (GAP-CLOSURE ROUND): Re-verification Report

**Phase Goal:** Identifier validation and DML construction live in exactly one place inside the core, and the library demonstrably returns correct results on all six engines — not just SQLite.
**Verified:** 2026-09-18T14:07:19Z
**Status:** gaps_found
**Re-verification:** Yes — after the `02-06`…`02-09` gap-closure round (HEAD `c63881f`)

## Method

Every claim below was re-derived from the working tree at `c63881f`. No SUMMARY.md statement was
accepted as evidence. The full suite was executed (`758 passed`, including the live MSSQL and Oracle
engines), the DB-free suite (`683 passed`, 10 snapshots), and the CR-01/CR-02/CR-03 reproductions were
run independently against the real drivers. `git show` was used to confirm what each gap-closure commit
actually touched.

## Per-original-gap verdict

| # | Original gap | Verdict | Evidence |
|---|--------------|---------|----------|
| GAP 1 | `QueryBuilder` alias + default pydantic column name unvalidated (injection) | **PARTIALLY CLOSED** | Alias is validated at all three entry points (`query_builder.py:53,104,119`) and the default field name is validated in `_build_column_map` (`model.py:235`); the literal UNION payload raises `ValueError`. But the sibling `_table` path is still unvalidated — see CR-01. The goal clause is therefore still false. |
| GAP 2 | `Query` cardinality not enforced; `{00}` KeyError; design doc wrong | **CLOSED** | `Query("SELECT 1",[1])` raises `ValueError: placeholders [] no cuadran con 1 parámetros`; `Query("a={00}",[7]).sql == 'a=%(parameter_0000)s'` with matching `params`; `docs/design/0-design.md:95-109` now uses a placeholder-bearing template and states the contract. Locked by `TestDesignDocSync`. |
| GAP 3 | `all()/first()/exists()` inline LIMIT; MariaDB upsert `ON CONFLICT`; PG `insert(replace=True)` non-PK target | **PARTIALLY CLOSED** | No inline `LIMIT` remains in `query_builder.py` (only comments at `:245,256,303`); `UPSERT_KIND['mariadb'] == 'on_duplicate'` and the builder emits `ON DUPLICATE KEY UPDATE`; `Model.insert` derives the conflict from the PK for `suffix` (`model.py:499-503`). The three named defects are fixed. But CR-02 and CR-03 keep the six-engine parity clause false. |
| GAP 4 | `list_tables(name=)` dead on 4/6 engines | **CLOSED** | `base.py:151-174` wraps the base SQL in a derived table (`encino_orm_tables`), filters `LOWER(name) LIKE LOWER({0})` with a bound value; `test_list_tables_filtrado_por_nombre` exists in all six engine files (12 matches for the two new per-engine test names across 6 files). |
| GAP 5 | Adapter coverage floors pending `engine-heavy` | **DEFERRED (not a gap)** | Explicitly kept out of the gap-closure round by ROADMAP (`GAP 5 … is NOT planned here`). |

## New findings from the gap-closure code review

| # | Finding | Verdict | Reproduction (independent) |
|---|---------|---------|----------------------------|
| CR-01 | `_build_base()` interpolates `_table` unvalidated | **STILL OPEN (BLOCKER)** | `QueryBuilder(Evil, None)._build_base()[0]` → `'FROM t; DROP TABLE usuarios -- mm'` where `Evil._table = 't; DROP TABLE usuarios --'`. Source: `query_builder.py:189,195`. |
| CR-02 | `Model.upsert()` default conflict emits `ON (dst.id = src.id)` on MSSQL/Oracle where `src.id` is absent | **CONFIRMED OPEN (BLOCKER)** | Live: MSSQL → `ProgrammingError 42S22 "Invalid column name 'id'. (207)"`; Oracle → `DatabaseError ORA-00904: "SRC"."ID": invalid identifier`. Generated SQL: `MERGE INTO t AS dst USING (SELECT … AS nombre, … AS enabled) AS src ON (dst.id = src.id) …`. |
| CR-03 | MSSQL `insert(replace=True)` returns a stale `last_id()` | **CONFIRMED OPEN (BLOCKER, regression)** | Live: `Ana insert() -> id 1`; `Zoe insert(replace=True) -> id 1, obj.id=1`. `mssql.py:252` refreshes `_last_id` only for `INSERT`; the existing test asserts no id. |
| WR-01 | `deferred-items.md` claims no unowned item while ORA-38104 is PENDIENTE and CR-02 is unlogged | **CONFIRMED OPEN (WARNING)** | `deferred-items.md:10-11` vs `:114-135`; no later phase (3–8) mentions ORA-38104. |
| WR-02 | 02-07 cardinality change absent from `CHANGELOG.md` | **CONFIRMED OPEN (WARNING)** | `git show --stat a953970 c058bba 6433b31` → no `CHANGELOG.md`; `[Unreleased]` has no cardinality bullet. |

### Inversion — three ways the "closed" claims could still be wrong

1. **Alias validation could be bypassable through a defaulted alias.** Checked: `_next_subquery_alias()`
   derives from the validated `self._alias` and the final alias is re-validated (`:119`). `join()`
   validates before the duplicate check (`:104`). Closed.
2. **The `Query` contract could reject legitimate callers.** The round claims every non-empty `fields`
   site has matching placeholders. Verified indirectly: the full suite (including migrations, bulk
   upsert and the six adapters) passes `758` with no changes to call sites. Closed.
3. **`list_tables(name=)` could still fail on Oracle because of the derived-table alias.** Verified the
   alias is `encino_orm_tables` (no leading underscore) and the case is normalised with `LOWER()` on
   both sides; the Oracle per-engine test is in the suite. Closed.

### Confirmation-bias counter

- **Partially met requirement:** GAP 1 and GAP 3 are each only partially closed — the named vectors are
  fixed but the goal clauses they were meant to restore remain false (CR-01, CR-02/CR-03).
- **A test that passes but does not test the stated behaviour:** `tests/test_mssql.py::test_model_insert_replace_no_rompe_el_merge`
  (`:330-342`) asserts only that the MERGE is executable; it never asserts the returned id, which is
  precisely the CR-03 defect. CI stays green over it.
- **An uncovered error path:** `Model.upsert()` is never exercised in `tests/test_mssql.py` or
  `tests/test_oracle.py` (`grep upsert` → 0 matches), so CR-02 is uncovered on both merge engines.

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite (all six live engines) | `uv run pytest -q` | `758 passed` | ✓ PASS |
| DB-free suite + snapshots | `uv run pytest -q -m "not integration and not optional_engine"` | `683 passed, 75 deselected`, 10 snapshots | ✓ PASS |
| GAP 1 alias rejection | `QueryBuilder(Agente, None, alias='mm WHERE 1=0 UNION SELECT nombre FROM usuarios --')` | `ValueError: alias inválido` | ✓ PASS |
| GAP 1 default column name | dynamic model with field `'a; DROP TABLE x --'` → `_column_map()` | `ValueError: nombre de columna inválido` | ✓ PASS |
| GAP 2 cardinality + `{00}` | `Query('SELECT 1',[1])` / `Query('a={00}',[7])` | `ValueError` / `parameter_0000` + matching params | ✓ PASS |
| GAP 3a inline LIMIT | `grep -n LIMIT encino_orm/model/query_builder.py` | only comments (`:245,256,303`) | ✓ PASS |
| GAP 3b MariaDB upsert | `build_upsert(..., upsert_kind=UPSERT_KIND['mariadb'], ...)` | `ON DUPLICATE KEY UPDATE` | ✓ PASS |
| GAP 4 list_tables filter | `base.py:151-174` + 12 per-engine test matches | derived table, bound value | ✓ PASS |
| CR-01 | `QueryBuilder(Evil, None)._build_base()[0]` | `'FROM t; DROP TABLE usuarios -- mm'` | ✗ FAIL |
| CR-02 | live `Model.upsert()` on MSSQL + Oracle | MSSQL 207 / Oracle ORA-00904 | ✗ FAIL |
| CR-03 | live MSSQL `insert(replace=True)` after Ana | returns `1`, `obj.id == 1` | ✗ FAIL |
| Debt-marker gate | `grep TBD/FIXME/XXX` over phase-modified files | 0 hits | ✓ PASS |

## Probe Execution

Step 7c: SKIPPED — no probe scripts are declared by the phase and `scripts/*/tests/probe-*.sh` finds none.
The runnable verification is pytest, executed above.

## Requirements Coverage

All nine requirement IDs were already satisfied at the original verification and are unaffected by the
findings above (the open items are against the phase goal's two broad clauses, not against DIAL-01…09):

| Requirement | Status | Note |
| ----------- | ------ | ---- |
| DIAL-01, DIAL-02 | ✓ SATISFIED | Allowlist single-sourced; DML builders single-sourced and validating. CR-01 is a SELECT-builder choke-point gap outside the letter of DIAL-02. |
| DIAL-03, DIAL-09 | ✓ SATISFIED | `list_tables(name=)` now works on all six engines; aggregate readers aliased `AS n`; per-engine coverage exists. |
| DIAL-04, DIAL-05, DIAL-06, DIAL-07, DIAL-08 | ✓ SATISFIED | Unchanged from the original verification. |

**Orphaned requirements:** none.

## Gaps Summary

The gap-closure round did real work and closed three of the five original gaps outright (GAP 2, GAP 4,
and — for the paths named — the individual items of GAP 1 and GAP 3). It also added genuine regression
coverage for aliases, the `Query` contract, MariaDB upsert, PostgreSQL conflict targets and the
`list_tables` filter, and the full suite is green at `758` against all six live engines.

However, the round's central claim — that identifier validation is now a real choke point and that
six-engine parity holds — is still not true, and one of the round's fixes introduced a new defect:

- **Goal clause 1 (choke point)** remains false because `QueryBuilder._build_base()` interpolates the
  model `_table` (and join targets' `_table`) with no validation (CR-01). The alias fix did not close
  the defect class it was chartered to close.
- **Goal clause 2 (six-engine correctness)** remains false because `Model.upsert()` with its documented
  default conflict generates invalid MERGE SQL on MSSQL and Oracle (CR-02), and MSSQL
  `insert(replace=True)` now silently returns another row's id (CR-03) — a regression introduced by
  making the MERGE executable.
- The round's own deferral log is inaccurate (WR-01) and one behaviour change is undocumented (WR-02).

Because CR-01, CR-02 and CR-03 falsify the phase goal's two clauses, and because CR-03 is a regression
introduced by this round, the status is **`gaps_found`**. CR-03's general fix is naturally owned by
Phase 4 (POOL-03 / SC2), and WR-02's full enumeration by Phase 8 (SC3), but neither is a reason to
accept the current state: the phase should either fix CR-01/CR-02/CR-03 or record explicit overrides.

---

_Verified: 2026-09-18T14:07:19Z_
_Verifier: the agent (gsd-verifier)_
