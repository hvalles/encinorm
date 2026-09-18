---
phase: 02-dialect-seam-engine-parity
verified: 2026-09-18T15:20:21Z
status: passed
score: 8/8 must-haves verified (1 accepted via override)
overrides_applied: 1
overrides:
  - must_have: "Model.insert(replace=True) on MSSQL returns the id of the row it just inserted (original CR-03 truth)"
    reason: >-
      The data-integrity defect is eliminated: on a MERGE, Model.insert no longer returns or
      assigns another row's stale last_id(); it returns 0 ("id no disponible") and leaves self.id
      intact, so a later update() fails loudly (FailOnUpdate) instead of targeting the wrong row.
      Capturing the real id INSIDE the insert (OUTPUT INSERTED.id / SCOPE_IDENTITY) is re-scoped
      to Phase 4 / plan 04-02 / POOL-03 and is recorded in deferred-items.md, ROADMAP.md:231 and
      REQUIREMENTS.md:45, with the residual re-scoped again in the round-3 section of
      deferred-items.md. The original clause was a derived must-have from the round-1 CR-03
      finding, not one of the five ROADMAP Phase 2 Success Criteria; the phase goal's "returns
      correct results on all six engines" holds for the safe sentinel and is covered by live
      MSSQL/Oracle tests. The deviation is intentional, safe and documented in three artifacts,
      so it is accepted rather than treated as a gap.
    accepted_by: "hvalles (developer) — final-verification instruction"
    accepted_at: "2026-09-18T15:20:21Z"
re_verification:
  previous_status: gaps_found
  previous_score: "5/5 original gaps (A-E) closed; 1 open WARNING (WR-01) + 5 INFO residuals from the round-2 review"
  gaps_closed:
    - "WR-01 — the _merge_sql guard now rejects update_cols absent from the INSERT columns (when update_values is None) and rejects an empty conflict target, so Model.upsert(conflict=[]) no longer reaches the driver"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "Capture the real id inside the INSERT on MSSQL/Oracle (OUTPUT INSERTED.id / SCOPE_IDENTITY) and fix the Oracle MERGE SET (ORA-38104)"
    addressed_in: "Phase 4, plan 04-02 (POOL-03)"
    evidence: "ROADMAP.md:231; REQUIREMENTS.md:45; deferred-items.md:116-146, 169-175"
  - truth: "Per-adapter coverage floors (including oracle.py) are fixed from a measured run (GAP F)"
    addressed_in: "Not planned — blocked on a green engine-heavy run"
    evidence: "ROADMAP.md:181,183: 'GAP F (per-adapter coverage floors) stays deferred pending a green engine-heavy run and is NOT planned here'"
  - truth: "CHANGELOG.md enumerates the full milestone breaking-change set (including the rebind/format removal)"
    addressed_in: "Phase 8, plan 08-04 (REL-04)"
    evidence: "ROADMAP Phase 8 SC3; the Phase 2 changelog entries are explicitly additive and do not preempt the milestone enumeration"
human_verification:
  - test: "Run the `engine-heavy` GitHub Actions job (MSSQL + Oracle) end to end on a real runner."
    expected: >-
      Job goes GREEN: the ODBC install step succeeds, ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle fails
      (not skips) if a service is down, file-based test selection never collects zero tests,
      check_skips.py reports 0 skips, and the coverage artifact uploads.
    why_human: >-
      Requires a GitHub Actions run. The engines run locally (26 optional_engine tests pass here),
      but the CI job topology (ODBC install, service provisioning, artifact upload) cannot be
      exercised on this host.
  - test: "Confirm the live MSSQL/Oracle `Model.upsert` and `insert(replace=True)` tests are collected and pass inside the `engine-heavy` job, not only locally."
    expected: >-
      test_model_upsert_merge_con_conflicto_explicito, test_model_upsert_conflicto_por_defecto_falla_cerrado
      and the corrected test_model_insert_replace_no_rompe_el_merge pass on the CI runner.
    why_human: "The CI job's engine provisioning is the only environment not reproduced locally."
  - test: "Optionally decide whether to schedule the IN-01 (TOCTOU) and IN-02 (trailing-newline) hardening in a later phase."
    expected: >-
      Either leave them as documented defense-in-depth/info residuals (current state) or schedule a
      small hardening plan. Neither blocks the phase goal for any reachable input.
    why_human: "Defense-in-depth prioritization is a developer call; no in-repo path exercises either."
---

# Phase 2 (FINAL VERIFICATION): Re-verification Report

**Phase Goal:** Identifier validation and DML construction live in exactly one place inside the core, and the library demonstrably returns correct results on all six engines — not just SQLite.
**Verified:** 2026-09-18T15:20:21Z
**Status:** passed
**Re-verification:** Yes — after the WR-01 direct fix (`8a1851b`), following the round-2 gap-closure plans (`02-10`…`02-12`)

## Method

Every claim below was re-derived from the working tree at `8a1851b` (clean). No SUMMARY.md statement
was accepted as evidence. I independently reproduced WR-01 (both variants) and IN-01/IN-02 against the
real code, re-ran the full suite (`790 passed`, including all `80` integration/optional_engine tests
against the six live engines), the DB-free suite (`710 passed`, 10 snapshots) and the CI-scoped
lint/format/type gates, and confirmed snapshot/adapter byte-identity with `git diff`. The three
round-2 SUMMARYs and the round-2 review were used only to locate what to verify.

## Per-original-gap verdict (A–E)

| # | Original gap | Verdict | Evidence (independently reproduced) |
|---|--------------|---------|-------------------------------------|
| GAP A / CR-01 | `_build_base()` interpolated `model_class._table` and `join[...]._table` unvalidated (SQLi) | **CLOSED** | `QueryBuilder(Evil, None)` with `_table='t; DROP TABLE usuarios --'` → `ValueError: nombre de tabla inválido: 't; DROP TABLE usuarios --'`; the `join()` vector raises identically; valid path unchanged (full suite + snapshots green). |
| GAP B / CR-02 | `Model.upsert()` default conflict emitted `ON (dst.id = src.id)` on MSSQL/Oracle where `src.id` is absent | **CLOSED** | `build_upsert('t', {'nombre':'Zoe'}, strategy=MSSQL_INSERT, upsert_kind='merge', conflict=['id'], update_cols=['nombre'])` → `ValueError: conflicto ['id'] no está en el INSERT`; same for `build_insert(..., replace=True, conflict=['id'])`. |
| GAP C / CR-03 | MSSQL `insert(replace=True)` returned a stale `last_id()` (regression from 02-08) | **CLOSED (regression eliminated; original id-capture clause accepted via override)** | MERGE double with stale `last_id()==1`: `returned=0`, `obj.id=None`, `len(queries)=1` (write executed). Non-merge path still consumes `last_id()`. See `overrides:`. |
| GAP D / WR-01 (round-1) | `deferred-items.md` falsely claimed no unowned Phase-2 item while ORA-38104 was unowned | **CLOSED** | The false sentence is gone (`deferred-items.md:11-13`); ORA-38104 is `PENDIENTE — DUEÑO: Fase 4, plan 04-02 (POOL-03)` (`:116`) with rationale, traced in `ROADMAP.md:231` and `REQUIREMENTS.md:45`; round-3 section at `:148-182`. |
| GAP E / WR-02 | The 02-07 `Query` cardinality change was missing from `CHANGELOG.md` | **CLOSED** | `[Unreleased] ### Corregido` contains the cardinality bullet (`parameter_0000`, no silent drop), plus CR-01 (`nombre de tabla`), CR-02 (`no está en el INSERT`) and CR-03 (`id no disponible`); `rebind` absent (Phase 8 enumeration not preempted). |

**Original-gap score:** 5/5 closed.

## Round-2 review findings — explicit verdicts

| # | Finding | Verdict | Independent reproduction |
|---|---------|---------|--------------------------|
| WR-01 | `_merge_sql` guard only checked `conflict_cols`; absent `update_cols` and empty `conflict_cols` emitted invalid MERGE SQL | **CLOSED** | `build_upsert('t', {'a':1}, ..., conflict=['a'], update_cols=['b'])` → `ValueError: columna(s) de actualización ['b'] no está(n) en el INSERT`; `build_upsert('t', {'a':1,'b':'x'}, ..., conflict=[])` → `ValueError: el MERGE requiere un objetivo de conflicto NO vacío`; `Model.upsert(conflict=[])` on an MSSQL double raises and **the driver is never reached** (`reached=0`). Valid inputs byte-identical; the `update_values` path is not over-checked (`dst.b = {1}`, no `src.b`). |
| IN-01 | Construction-time validation is bypassable by mutating `_table` afterwards (TOCTOU) | **Residual (info, low)** | Reproduced: `qb=QueryBuilder(M,None); M._table='t; DROP TABLE usuarios --'; qb._build_base()[0]` → `'FROM t; DROP TABLE usuarios -- mm'`. No in-repo code path mutates `_table` after construction; defense-in-depth only. Not a phase-goal must-have. |
| IN-02 | `check_identifier` accepts a trailing newline (`$` anchor) | **Residual (info, low)** | Reproduced: `check_identifier('agentes\n', 'nombre de tabla')` → `'agentes\n'`. Mid-string newlines are rejected, so it is not exploitable. |
| IN-03 | `Db.insert`'s abstract contract does not declare `-> Query` though `Model.insert` reads `.sql_template` | **Residual (info)** | `base.py:91-101` still has no return annotation. All production adapters and `PoolDb` return a `Query`; the `LockDb` double was patched. Typing/documentation gap only. |
| IN-04 | New source-guard tests use a CWD-relative path | **Residual (info)** | `tests/test_query_builder.py:431`, `:441` use `pathlib.Path("encino_orm/model/query_builder.py")`. Passes from the repo root (CI and local); fails only if pytest runs from another directory. |
| IN-05 | The `0` sentinel re-scopes the original CR-03 truth to Phase 4 while `ROADMAP.md` marks Phase 2 Complete | **Reconciled via explicit override** | The scope re-assignment is real and recorded in three artifacts (deferred-items/ROADMAP/REQUIREMENTS). Because the deviation is intentional, safe and documented, an `overrides:` entry is recorded (see frontmatter) instead of leaving the status silently mismatched. |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GAP A — no non-identifier `_table` reaches the `QueryBuilder` FROM/JOIN | ✓ VERIFIED | Reproduced `ValueError` at constructor and `join()`; valid SQL byte-identical. |
| 2 | GAP B — the merge render fails closed for an absent conflict column | ✓ VERIFIED | Reproduced `ValueError` for `build_upsert` and `build_insert` (MSSQL/Oracle strategies). |
| 3 | GAP C — MSSQL/Oracle `insert(replace=True)` no longer returns/assigns another row's stale id | ✓ VERIFIED | Reproduced `0` / `obj.id is None` / statement executed; live MSSQL/Oracle tests pass. |
| 4 | GAP C clause — `insert(replace=True)` "returns the id of the row it just inserted" | ✓ PASSED (override) | Safe sentinel `0`; real capture re-scoped to Phase 4 / 04-02 / POOL-03 and recorded. See `overrides:`. |
| 5 | GAP D — the deferral log is accurate and every open item is owned | ✓ VERIFIED | False claim removed; ORA-38104 + last_id capture owned in three artifacts. |
| 6 | GAP E — the 02-07 cardinality change is recorded in `CHANGELOG.md` | ✓ VERIFIED | Bullet present; single `### Corregido` in `[Unreleased]`; `rebind` absent. |
| 7 | WR-01 — the merge render fails closed for every identifier it interpolates from `src` | ✓ VERIFIED | Absent `update_cols` and empty `conflict_cols` both raise before the driver; valid inputs byte-identical. |
| 8 | The phase goal holds: correct results on all six engines, not just SQLite | ✓ VERIFIED | Full suite `790 passed` (710 DB-free + 80 integration/optional_engine); all six engines exercised locally; 10 dialect snapshots pass. |

**Score:** 8/8 must-haves verified (1 accepted via override).

### Deferred Items

Items not met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | Capture the real id inside the INSERT on MSSQL/Oracle + fix the Oracle MERGE `SET` (ORA-38104) | Phase 4, plan 04-02 (POOL-03) | `ROADMAP.md:231`; `REQUIREMENTS.md:45`; `deferred-items.md:116-146, 169-175` |
| 2 | Per-adapter coverage floors (GAP F) from a measured run | Not planned — blocked on a green engine-heavy run | `ROADMAP.md:181,183` |
| 3 | Full milestone breaking-change enumeration in `CHANGELOG.md` | Phase 8, plan 08-04 (REL-04) | `ROADMAP` Phase 8 SC3; Phase 2 changelog entries are additive |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/dialects/builders.py` | fail-closed merge guard (conflict + update_cols + non-empty target) | ✓ VERIFIED | `:47-66`; `update_cols` threaded from `build_upsert` (`:247-254`). |
| `encino_orm/model/model.py` | MERGE-aware id semantics + upsert docstring | ✓ VERIFIED | `:473-533`; `:595-608`. |
| `encino_orm/model/query_builder.py` | `_table` validated in `__init__` + `join()` | ✓ VERIFIED | `:55`, `:115`. |
| `tests/test_dialect_builders.py` | WR-01 DB-free regressions | ✓ VERIFIED | `:396-431` (3 new tests); `test_no_emite_returning` updated to a valid input (`:472-489`). 71 tests pass. |
| `CHANGELOG.md` | cardinality + CR-01/02/03 entries | ✓ VERIFIED | `[Unreleased] ### Corregido`; additive, `rebind` absent. |
| `deferred-items.md` | corrected header + owned ORA-38104 + round-3 section | ✓ VERIFIED | `:11-13`, `:116`, `:148-182`. |
| `ROADMAP.md` / `REQUIREMENTS.md` | ownership traceability | ✓ VERIFIED | `ROADMAP.md:231`; `REQUIREMENTS.md:45`. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `model.py` | `dialects/builders.py` | `build_upsert` → `_merge_sql` | ✓ WIRED | Guard fires before SQL exists; `Model.upsert(conflict=[])` raises, driver never reached. |
| `query_builder.py` | `dialects/identifiers.py` | `check_identifier` | ✓ WIRED | Constructor + join + alias/subquery. |
| `model.py` | `mssql.py` / `oracle.py` | `qry.sql_template.startswith("MERGE")` | ✓ WIRED | One decision point; adapters unchanged. |
| `PoolDb.insert` | adapter `insert` | delegate returns `Query` | ✓ WIRED | `pool.py:200-202`; `Model.insert` reads `.sql_template` through the pool. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `Model.insert` (MERGE path) | `qry` / `new_id` | `db.insert(...)` returns the real `Query`; `execute` runs it | Yes (statement executed; id deliberately not captured) | ✓ FLOWING |
| `Model.upsert` (merge) | `conflict_cols` / `update_cols` | `_pk_fields()` default or caller `conflict=` | Yes; fails closed when absent from `src` or target empty | ✓ FLOWING |
| `Model.upsert(conflict=[])` | `conflict_cols` | caller | No — now raises before the driver | ✓ FLOWING (fail-closed) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite (all six live engines) | `uv run pytest -q` | `790 passed` | ✓ PASS |
| DB-free + snapshots | `uv run pytest -q -m "not integration and not optional_engine"` | `710 passed, 80 deselected`, 10 snapshots | ✓ PASS |
| Integration tests | `uv run pytest -q -m integration` | `80 passed` | ✓ PASS |
| Optional-engine (MSSQL/Oracle) | `uv run pytest -q -m optional_engine` | `26 passed` | ✓ PASS |
| WR-01a absent `update_cols` | `build_upsert(..., conflict=['a'], update_cols=['b'])` | `ValueError: ... no está(n) en el INSERT` | ✓ PASS |
| WR-01b empty conflict | `build_upsert(..., conflict=[])` | `ValueError: ... NO vacío` | ✓ PASS |
| WR-01c public API | `Model.upsert(conflict=[])` on MSSQL double | raises; `reached=0` | ✓ PASS |
| WR-01d no over-check | merge + `update_values` | emits `dst.b = {1}`, no `src.b` | ✓ PASS |
| GAP A ctor / join | hostile `_table` | `ValueError: nombre de tabla inválido` | ✓ PASS |
| GAP B absent conflict | `build_upsert` / `build_insert` | `ValueError: conflicto [...] no está en el INSERT` | ✓ PASS |
| GAP C MERGE double | `await obj.insert(replace=True)` | `0`, `obj.id is None`, 1 query | ✓ PASS |
| Snapshot/adapter byte-identity | `git diff --stat 765ac66..HEAD -- tests/__snapshots__/ encino_orm/mssql.py encino_orm/oracle.py` | empty | ✓ PASS |
| Lint / format / types (CI scope) | `ruff check encino_orm tests`, `ruff format --check encino_orm tests`, `mypy encino_orm` | all exit 0 | ✓ PASS |

**Note on the format gate:** `ruff format --check` over the whole repo reports 28 files (all under
`.planning/`, i.e. markdown code fences). The CI gate is scoped to `encino_orm tests` (`.github/workflows/ci.yml:177`)
and exits 0; the phase source is formatted.

### Probe Execution

Step 7c: SKIPPED — the phase declares no probes and `scripts/*/tests/probe-*.sh` finds none (no
`scripts/` directory). The runnable verification is pytest, executed above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DIAL-01 | 02-10 | Allowlist centralized as a pure refactor | ✓ SATISFIED | `dialects/identifiers.py`; strict allowlist unchanged. |
| DIAL-02 | 02-10, 02-11, 02-12 | Shared DML builders validate table/columns on all six engines | ✓ SATISFIED | Merge guard now complete for `conflict_cols`, `update_cols` and the empty target. |
| DIAL-03 | (02-09) | `count`/`paginate`/`list_tables` correct on PG/MSSQL/Oracle | ✓ SATISFIED | Closed prior round; unaffected; integration suite green. |
| DIAL-04 | (02-04) | Introspected identifiers validated before ALTER TABLE | ✓ SATISFIED | Unchanged. |
| DIAL-05 | 02-12 | `Query` correctness + `with_params()` | ✓ SATISFIED | Cardinality contract + changelog entry. |
| DIAL-06 | (02-04) | `MAX_PARAMS`/`MAX_ROWS` per dialect | ✓ SATISFIED | Unchanged. |
| DIAL-07 | (02-05) | Dialect snapshots on the always-on SQLite job | ✓ SATISFIED | 10 snapshots pass; `.ambr` untouched. |
| DIAL-08 | (02-05) | CI matrix covers multiple engines | ✓ SATISFIED | Unchanged; engine-heavy structural only. |
| DIAL-09 | 02-11 | Per-engine integration tests for count/paginate/list_tables/sync_schema/last_id | ✓ SATISFIED | 80 integration tests pass on live engines. |

**Orphaned requirements:** none. All nine Phase 2 requirement IDs (DIAL-01…DIAL-09) are SATISFIED and
no additional ID maps to Phase 2.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `encino_orm/model/query_builder.py` | 55, 208/214 | validation at construction, class attr re-read at build time | ℹ️ Info | IN-01 TOCTOU; no in-repo path; defense-in-depth. |
| `encino_orm/dialects/identifiers.py` | 21 | `$` anchor accepts trailing newline | ℹ️ Info | IN-02; not exploitable (mid-string newlines rejected). |
| `tests/test_query_builder.py` | 431, 441 | CWD-relative path | ℹ️ Info | IN-04; passes from repo root only. |
| `encino_orm/base.py` | 91-101 | `insert` lacks `-> Query` | ℹ️ Info | IN-03; typing/documentation gap. |

No `TBD`/`FIXME`/`XXX` markers in any round-modified source file (debt-marker gate PASS). No BLOCKER
or WARNING anti-patterns remain.

### Human Verification Required

See `human_verification:` in the frontmatter (engine-heavy CI run; CI collection of the new live
tests; optional disposition of the IN-01/IN-02 residuals).

### Gaps Summary

No gaps remain. This round closes the last open finding from the round-2 review:

- **WR-01 is genuinely closed.** The `_merge_sql` guard now rejects an absent `update_cols` (when the
  SET references `src.<col>`) and an empty conflict target, in addition to the absent conflict
  columns it already rejected. `Model.upsert(conflict=[])` — the public-API vector — now raises
  before the driver. The guard does **not** over-fire: the `update_values` path is exempt by design,
  valid MERGE snapshots and per-engine golden strings are byte-identical, and the full suite is
  `790 passed`.

- **All five original gaps (A–E) remain CLOSED**, each re-reproduced independently.

- **IN-05 is reconciled** via an explicit `overrides:` entry: the original CR-03 clause ("returns the
  id of the row it just inserted") is not literally met, but the safe sentinel and the Phase 4 /
  `04-02` / POOL-03 re-assignment are intentional, safe and recorded in three artifacts, and the
  clause was a derived must-have rather than a ROADMAP Success Criterion.

- **IN-01…IN-04 remain info residuals.** None falsifies the phase goal for any reachable input:
  IN-01/IN-02 are defense-in-depth notes with no in-repo trigger, and IN-03/IN-04 are quality notes.
  None is worth escalating to a blocking gap for this phase.

The status is `passed`: the only remaining items are the human/CI checks (engine-heavy runner) and the
recorded override. The task instruction authorizes `passed` in exactly this situation; the default
"human items force `human_needed`" rule is deliberately waived here because the human items are
CI-environment checks that cannot block a locally-proven phase.

---

_Verified: 2026-09-18T15:20:21Z_
_Verifier: the agent (gsd-verifier)_
