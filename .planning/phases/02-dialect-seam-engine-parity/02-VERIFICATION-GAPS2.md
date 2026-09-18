---
phase: 02-dialect-seam-engine-parity
verified: 2026-09-18T14:54:58Z
status: superseded
score: 5/5 original gaps (A-E) closed; 1 open WARNING (WR-01) + 5 INFO residuals from the round-2 review
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: "2/5 original gaps fully closed, 2 partial, 1 deferred; 0/5 new findings closed"
  gaps_closed:
    - "GAP A / CR-01 — QueryBuilder validates model_class._table (constructor) and other._table (join) with the strict allowlist"
    - "GAP B / CR-02 — the merge render fails closed when a conflict column is absent from the INSERT columns"
    - "GAP C / CR-03 — Model.insert(replace=True) on MSSQL/Oracle no longer returns or assigns another row's stale id"
    - "GAP D / WR-01 — the deferral log no longer claims zero unowned items; ORA-38104 and the last_id capture are owned by Phase 4 / 04-02 / POOL-03 in deferred-items.md, ROADMAP.md and REQUIREMENTS.md"
    - "GAP E / WR-02 — the 02-07 Query cardinality change is recorded in CHANGELOG.md [Unreleased] ### Corregido"
  gaps_remaining:
    - "WR-01 (round-2 review) — the _merge_sql fail-closed guard only checks conflict_cols: absent update_cols and empty conflict_cols still emit invalid MERGE SQL, and Model.upsert(conflict=[]) reaches the driver with ON ()"
  regressions: []
gaps:
  - truth: "The merge render fails closed for every identifier it interpolates from the src derived table (round-2 review WR-01)"
    status: failed
    reason: >-
      The new guard in `_merge_sql` (builders.py:46-51) rejects only conflict columns absent from the
      INSERT columns. Two adjacent inputs still emit a MERGE that references a nonexistent `src`
      column or an empty conflict target, and both reach the driver. Independently reproduced below.
      Loud driver errors, not silent corruption — hence WARNING, not BLOCKER — but the guard is the
      round's stated single choke point and the round advertised it as fail-closed.
    artifacts:
      - path: "encino_orm/dialects/builders.py"
        issue: "`:46-51` guards `conflict_cols` only; `:229` emits `dst.<c> = src.<c>` for every `update_cols` with no membership check; `:54` renders `ON ()` when `conflict_cols` is empty."
      - path: "encino_orm/model/model.py"
        issue: "`:610-611` substitutes the PK only when `conflict is None`; an explicit `conflict=[]` passes straight to `build_upsert` and emits `ON ()`."
      - path: "tests/test_dialect_builders.py"
        issue: "`:435-450` `test_no_emite_returning` already constructs the absent-`update_cols` statement but asserts only `\"RETURNING\" not in ...`, so CI stays green over it."
    missing:
      - "Extend the `_merge_sql` guard to reject `update_cols` (when `update_values is None`) that are absent from `columns`, and reject an empty `conflict_cols`."
      - "Add DB-free tests mirroring `TestMergeConflictGuard` for both cases."
  - truth: "Phase 2's recorded status matches the original CR-03 gap truth: 'Model.insert(replace=True) on MSSQL returns the id of the row it just inserted' (round-2 review IN-05)"
    status: partial
    reason: >-
      The dangerous behaviour is gone (no stale/wrong id), but the original truth remains literally
      false: `Model.insert` returns `0` and leaves `self.id` intact on a MERGE, and the id capture is
      deferred to Phase 4 / `04-02` / POOL-03. `ROADMAP.md:66` and the completion table (`:412`) mark
      Phase 2 "Complete (12/12)" while that clause is unmet, and no `overrides:` entry records the
      deviation. This is a status/traceability mismatch, not a code defect.
    artifacts:
      - path: "encino_orm/model/model.py"
        issue: "`:521-533` returns `0` / leaves `self.id` intact when the executed statement is a MERGE."
      - path: ".planning/ROADMAP.md"
        issue: "`:66` and `:412` mark Phase 2 Complete while the original CR-03 clause is deferred to Phase 4."
    missing:
      - "Record an explicit `overrides:` entry for the re-scoped CR-03 truth, or correct the Phase 2 status note to state that the id capture is deferred (not delivered)."
  - truth: "Identifier validation is a construction-time choke point that cannot be bypassed (round-2 review IN-01)"
    status: partial
    reason: >-
      Validation runs in `QueryBuilder.__init__`/`join()` but `_build_base()` re-reads
      `self._model_class._table` at build time, so mutating the class attribute after construction
      re-opens the injection vector. No in-repo code path does this, so the real-world risk is low
      (defense-in-depth only). Reproduced below.
    artifacts:
      - path: "encino_orm/model/query_builder.py"
        issue: "`:55` validates at construction; `:208`/`:214` re-read the class attribute at build time."
    missing:
      - "Capture the validated table name in `__init__`/`join` (e.g. `self._table = check_identifier(...)`) and use the captured value in `_build_base`/join, or re-validate in `_build_base`."
  - truth: "The strict identifier allowlist rejects every non-identifier, including a trailing newline (round-2 review IN-02)"
    status: partial
    reason: >-
      `IDENTIFIER_RE` uses `$`, which matches before a final newline, so
      `check_identifier(\"agentes\\n\", ...)` returns `\"agentes\\n\"`. Mid-string newlines are still
      rejected, so it is not exploitable, but it now also gates `_table` (the CR-01 fix). Reproduced
      below.
    artifacts:
      - path: "encino_orm/dialects/identifiers.py"
        issue: "`:21` `IDENTIFIER_RE = re.compile(r\"^[A-Za-z_][A-Za-z0-9_]*$\")` — `$` matches before a trailing newline."
    missing:
      - "Use `\\Z` instead of `$` (or `re.fullmatch`), plus a characterization test."
  - truth: "The abstract `Db.insert` contract declares the `Query` return that `Model.insert` now consumes (round-2 review IN-03)"
    status: partial
    reason: >-
      `Model.insert` binds `db.insert(...)` and reads `.sql_template` (`model.py:521`), but the
      abstract `Db.insert` signature (`base.py:91-101`) has no return annotation or docstring, so the
      contract is implicit. A custom `Db`/test double returning a non-`Query` breaks with
      `AttributeError` (exactly what happened to `LockDb` and was patched in
      `tests/test_d_recommendations.py`). All production adapters and `PoolDb` return a `Query`.
    artifacts:
      - path: "encino_orm/base.py"
        issue: "`:91-101` `def insert(...): ...` has no `-> Query` annotation."
    missing:
      - "Annotate `Db.insert(...) -> Query` (and document the return)."
  - truth: "Source-guard tests resolve their paths independently of the process CWD (round-2 review IN-04)"
    status: partial
    reason: >-
      `tests/test_query_builder.py:431` and `:441` read
      `pathlib.Path(\"encino_orm/model/query_builder.py\")`, which resolves against the CWD and fails
      with `FileNotFoundError` if pytest is invoked from another directory. The sibling guard in
      `tests/test_dialect_builders.py:785` correctly uses
      `Path(__file__).resolve().parents[1]`. CI and the local run pass because both invoke pytest
      from the repo root.
    artifacts:
      - path: "tests/test_query_builder.py"
        issue: "`:431`, `:441` use a CWD-relative path."
    missing:
      - "Mirror the existing convention: `(Path(__file__).resolve().parents[1] / \"encino_orm/model/query_builder.py\")`."
deferred:
  - truth: "Per-adapter coverage floors (including oracle.py) are fixed from a measured run (GAP F)"
    addressed_in: "Not planned — blocked on a green engine-heavy run"
    evidence: "ROADMAP Phase 2 gap-closure note and round-3 narrative: 'GAP F (per-adapter coverage floors) stays deferred pending a green engine-heavy run and is NOT planned here'. Legitimately deferred."
  - truth: "Capture the real id inside the INSERT on MSSQL/Oracle (OUTPUT INSERTED.id / SCOPE_IDENTITY) and fix the Oracle MERGE SET (ORA-38104)"
    addressed_in: "Phase 4, plan 04-02 (POOL-03)"
    evidence: "ROADMAP.md:231; REQUIREMENTS.md:45; deferred-items.md:116-146. The round re-scoped CR-03 to a safe failure and documented the deferral."
  - truth: "CHANGELOG.md enumerates the full milestone breaking-change set (including the rebind/format removal)"
    addressed_in: "Phase 8 (08-04, REL-04)"
    evidence: "ROADMAP Phase 8 SC3 + plan 08-04; the round-2 changelog entries are explicitly additive."
human_verification:
  - test: "Run the `engine-heavy` GitHub Actions job (MSSQL + Oracle) end to end on a real runner."
    expected: "Job goes GREEN: the ODBC install step succeeds, `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle` fails (not skips) if a service is down, file-based test selection never collects zero tests, `check_skips.py` reports 0 skips, and the coverage artifact uploads."
    why_human: "Requires a GitHub Actions run; only structural wiring was verified locally (MSSQL/Oracle do run locally, but the CI job topology cannot be exercised here)."
  - test: "Confirm the new live MSSQL/Oracle `Model.upsert` and `insert(replace=True)` tests are collected and pass inside the `engine-heavy` job, not only locally."
    expected: "`test_model_upsert_merge_con_conflicto_explicito`, `test_model_upsert_conflicto_por_defecto_falla_cerrado` and the corrected `test_model_insert_replace_no_rompe_el_merge` pass on the CI runner."
    why_human: "The CI job's engine provisioning is the only environment not reproduced locally."
  - test: "Decide the disposition of WR-01 and IN-05."
    expected: "Either fix the `_merge_sql` guard (reject absent `update_cols` and empty `conflict_cols`) and correct the Phase 2 status note, or record explicit `overrides:` for the re-scoped CR-03 truth and the incomplete guard."
    why_human: "Whether the phase's goal clauses must be made literally true now, or the residuals accepted as documented WARNING/INFO items for later phases, is a developer call."
---

> **SUPERSEDED** — este reporte es histórico. La verificación vigente y aprobada es `02-VERIFICATION-FINAL.md` (status: passed). Se conserva como registro de la evolución de los gaps.

# Phase 2 (GAP-CLOSURE ROUND 2): Re-verification Report

**Phase Goal:** Identifier validation and DML construction live in exactly one place inside the core, and the library demonstrably returns correct results on all six engines — not just SQLite.
**Verified:** 2026-09-18T14:54:58Z
**Status:** gaps_found
**Re-verification:** Yes — after the round-2 gap-closure plans (`02-10`…`02-12`, commits `d4df155`..`765ac66`)

## Method

Every claim below was re-derived from the working tree at `765ac66` (clean). No SUMMARY.md statement
was accepted as evidence. I re-ran the full suite (`787 passed`) and the DB-free suite
(`707 passed`, 10 snapshots), independently reproduced CR-01/CR-02/CR-03, WR-01, IN-01 and IN-02
against the real code, confirmed the snapshot/adapter byte-identity with `git diff`, and re-ran the
lint/type gates. The three round-2 SUMMARYs were used only to locate what to verify.

## Per-original-gap verdict (A–E)

| # | Original gap | Verdict | Evidence |
|---|--------------|---------|----------|
| GAP A / CR-01 | `_build_base()` interpolated `model_class._table` and `join[...]._table` unvalidated (SQLi) | **CLOSED** | `query_builder.py:55` and `:115` call `check_identifier(..., "nombre de tabla")`. Independent reproduction: `QueryBuilder(Evil, None)` with `_table='t; DROP TABLE usuarios --'` → `ValueError: nombre de tabla inválido: 't; DROP TABLE usuarios --'`; the `join()` vector raises identically; the valid path is byte-identical (`'FROM agentes mm'`, `'... JOIN regiones r ON mm.region_id = r.id'`). Residuals IN-01/IN-02 below. |
| GAP B / CR-02 | `Model.upsert()` default conflict emitted `ON (dst.id = src.id)` on MSSQL/Oracle where `src.id` is absent | **CLOSED (defect eliminated; truth re-scoped)** | `builders.py:46-51` rejects any conflict column absent from the INSERT columns. Independent reproduction (MSSQL + Oracle strategies, and `build_insert`): `ValueError: conflicto ['id'] no está en el INSERT; ...`. The invalid `ON (dst.id = src.id)` can no longer be produced for the documented default; the docstring (`model.py:603-608`) now states that a merge-dialect auto-PK upsert requires an explicit data-column `conflict=` and otherwise fails closed. Live coverage added on both engines. |
| GAP C / CR-03 | MSSQL `insert(replace=True)` returned a stale `last_id()` (regression from 02-08) | **CLOSED (regression eliminated; original id-capture truth deferred — IN-05)** | `model.py:521-533`: on a MERGE it returns `None` from `do_insert`, skips `last_id()`, leaves `self.id` intact and returns `0`. Independent reproduction with a MERGE double whose `last_id()` returns the stale `1`: `returned = 0`, `obj.id = None`, `len(queries) = 1` (the write still executed). The non-merge path still consumes `last_id()` (verified in-suite). The original wording "returns the id of the row it just inserted" is **not** met; it is documented and owned by Phase 4 / `04-02`. |
| GAP D / WR-01 | `deferred-items.md` falsely claimed no unowned Phase-2 item while ORA-38104 was unowned | **CLOSED** | The sentence "Ya NO queda ningún item ... sin dueño" is gone (`deferred-items.md:11-13` now says the open items all have an explicit owner). ORA-38104 is `PENDIENTE — DUEÑO: Fase 4, plan 04-02 (POOL-03)` (`:116`) with a `Dueño` rationale; a round-3 section exists (`:148-182`). The owner is traced in `ROADMAP.md:231` and `REQUIREMENTS.md:45`; `| POOL-03 | Phase 4 | Pending |` is intact. |
| GAP E / WR-02 | The 02-07 `Query` cardinality change was missing from `CHANGELOG.md` | **CLOSED** | `[Unreleased] ### Corregido` now has exactly one heading and contains `cardinalidad` + `parameter_0000` (cardinality), `nombre de tabla` (CR-01), `no está en el INSERT` (CR-02) and `id no disponible` (CR-03). `rebind` is absent from the whole file (Phase 8 enumeration not preempted). `git diff --numstat CHANGELOG.md` = 30 insertions / 0 deletions. |

**Original-gap score:** 5/5 closed.

## Round-2 review findings — explicit verdicts

| # | Finding | Verdict | Independent reproduction |
|---|---------|---------|--------------------------|
| WR-01 | The `_merge_sql` fail-closed guard only checks `conflict_cols`; absent `update_cols` and empty `conflict_cols` still emit invalid MERGE SQL | **CONFIRMED OPEN (WARNING)** | `build_upsert('t', {'a':1}, strategy=MSSQL_INSERT, upsert_kind='merge', conflict=['a'], update_cols=['b'])` → no raise, emits `... ON (dst.a = src.a) WHEN MATCHED THEN UPDATE SET dst.b = src.b ...` where `src.b` does not exist. `Model.upsert(conflict=[])` on an MSSQL double → no raise, emits `... ON () WHEN MATCHED THEN UPDATE SET ...` and calls `execute` (reaches the driver). See `gaps[0]`. |
| IN-01 | Construction-time validation is bypassable by mutating `_table` afterwards (TOCTOU) | **CONFIRMED (residual, low)** | `M._table='ok_tabla'; qb=QueryBuilder(M,None); M._table='t; DROP TABLE usuarios --'; qb._build_base()[0]` → `'FROM t; DROP TABLE usuarios -- mm'`. No in-repo code path mutates `_table` after building a `QueryBuilder`; defense-in-depth only. See `gaps[2]`. |
| IN-02 | `check_identifier` accepts a trailing newline (`$` anchor) | **CONFIRMED (residual, low)** | `check_identifier('agentes\n', 'nombre de tabla')` → returns `'agentes\n'`; mid-string newlines are still rejected, so it is not exploitable. It now also gates `_table`. See `gaps[3]`. |
| IN-03 | `Db.insert`'s abstract contract does not declare `-> Query` though `Model.insert` reads `.sql_template` | **CONFIRMED (info)** | `base.py:91-101` has no return annotation; `model.py:521` reads `qry.sql_template`. All production adapters and `PoolDb` return a `Query`; a non-`Query` double breaks with `AttributeError` (the `LockDb` patch in `tests/test_d_recommendations.py`). See `gaps[4]`. |
| IN-04 | New source-guard tests use a CWD-relative path | **CONFIRMED (info)** | `tests/test_query_builder.py:431`, `:441` use `pathlib.Path("encino_orm/model/query_builder.py")`; the sibling guard `tests/test_dialect_builders.py:785` uses `Path(__file__).resolve().parents[1]`. Passes from the repo root only. See `gaps[5]`. |
| IN-05 | The `0` sentinel re-scopes the original CR-03 truth to Phase 4 while `ROADMAP.md` marks Phase 2 Complete | **CONFIRMED (status/traceability mismatch)** | `ROADMAP.md:66` and the completion table `:412` say "Complete (12/12, 2026-09-18)"; `model.py:521-533` returns `0` on MERGE and the id capture is deferred. No `overrides:` entry records the deviation. See `gaps[1]`. |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GAP A — no non-identifier `_table` reaches the `QueryBuilder` FROM/JOIN | ✓ VERIFIED | Reproduced `ValueError` at constructor and join; valid SQL byte-identical; driver spy never reached (in-suite). |
| 2 | GAP B — the merge render fails closed for an absent conflict column | ✓ VERIFIED | Reproduced `ValueError` for MSSQL/Oracle strategies and `build_insert`; valid merge SQL unchanged. |
| 3 | GAP C — MSSQL/Oracle `insert(replace=True)` no longer returns/assigns another row's stale id | ✓ VERIFIED | Reproduced `0` / `obj.id is None` / statement executed; live MSSQL test asserts the same. |
| 4 | GAP D — deferral log accurate; every open Phase-2 item owned | ✓ VERIFIED | False claim removed; ORA-38104 + last_id capture owned in three artifacts. |
| 5 | GAP E — 02-07 cardinality change recorded in CHANGELOG | ✓ VERIFIED | Bullet present; single `### Corregido`; `rebind` absent. |
| 6 | The merge render fails closed for every interpolated `src` identifier (WR-01) | ✗ FAILED | `update_cols` absent and empty `conflict_cols` still emit invalid MERGE SQL that reaches the driver. |
| 7 | Phase 2 status matches the original CR-03 truth (IN-05) | ? UNCERTAIN | Code is safe but the original truth is unmet; needs an override or a roadmap correction (developer decision). |
| 8 | Identifier validation is bypass-proof (IN-01) | ? UNCERTAIN | TOCTOU only; no in-repo path (developer decision on defense-in-depth). |
| 9 | The strict allowlist rejects every non-identifier (IN-02) | ? UNCERTAIN | Trailing-newline looseness; not exploitable. |

**Score:** 5/5 original gaps verified; WR-01 FAILED; IN-01/IN-02/IN-05 UNCERTAIN (WARNING, human decision); IN-03/IN-04 info-only.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/model/query_builder.py` | `_table` validated in `__init__` + `join()` | ✓ VERIFIED | `:55`, `:115`; 6 `check_identifier` references; contract comment in `_build_base`. |
| `encino_orm/dialects/builders.py` | fail-closed merge guard | ⚠️ PARTIAL | `:46-51` guards conflict columns only (WR-01). |
| `encino_orm/model/model.py` | MERGE-aware id semantics + upsert docstring | ✓ VERIFIED | `:473-533` insert; `:595-608` upsert contract. |
| `CHANGELOG.md` | cardinality + CR-01/02/03 entries | ✓ VERIFIED | 30 insertions, 0 deletions, one `### Corregido` in `[Unreleased]`. |
| `deferred-items.md` | corrected header + owned ORA-38104 | ✓ VERIFIED | `:11-13`, `:116`, `:148-182`. |
| `ROADMAP.md` / `REQUIREMENTS.md` | ownership traceability | ✓ VERIFIED | `ROADMAP.md:231`, `REQUIREMENTS.md:45`. |
| `tests/test_query_builder.py` | CR-01 regression + sweep | ✓ VERIFIED (path caveat IN-04) | `TestTablaInjection` (6) + `TestBarridoDeIdentificadores` (10) = 16 pass. |
| `tests/test_dialect_builders.py` | CR-02/CR-03 DB-free regressions | ✓ VERIFIED | `TestMergeConflictGuard` (5) + `TestModelInsertMergeNoConsumeIdObsoleto` (3) = 8 pass. |
| `tests/test_mssql.py`, `tests/test_oracle.py` | live upsert + id-semantics coverage | ✓ VERIFIED | 11 `model_upsert`/`insert_replace` tests pass on live engines. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `query_builder.py` | `dialects/identifiers.py` | `check_identifier` | ✓ WIRED | 6 call sites; constructor + join + join_subquery alias. |
| `model.py` | `dialects/builders.py` | `build_upsert` → `_merge_sql` | ✓ WIRED | guard fires before SQL exists. |
| `model.py` | `mssql.py` / `oracle.py` | `qry.sql_template.startswith("MERGE")` | ✓ WIRED | one decision point; adapters unchanged. |
| `PoolDb.insert` | adapter `insert` | delegate returns `Query` | ✓ WIRED | `pool.py:200-202`; `Model.insert` reads `.sql_template` through the pool. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `Model.insert` (MERGE path) | `qry` / `new_id` | `db.insert(...)` returns the real `Query`; `execute` runs it | Yes (statement executed; id deliberately not captured) | ✓ FLOWING |
| `Model.upsert` (merge) | `conflict_cols` | `_pk_fields()` default or caller `conflict=` | Yes; fails closed when absent from `src` | ✓ FLOWING |
| `Model.upsert(conflict=[])` | `conflict_cols` | caller | No — renders `ON ()` | ✗ HOLLOW (WR-01) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite (all six live engines) | `uv run pytest -q` | `787 passed` | ✓ PASS |
| DB-free + snapshots | `uv run pytest -q -m "not integration and not optional_engine"` | `707 passed, 10 snapshots` | ✓ PASS |
| CR-01 constructor | `QueryBuilder(Evil, None)` | `ValueError: nombre de tabla inválido` | ✓ PASS |
| CR-01 join | `.join(Evil, 'h', ...)` | `ValueError: nombre de tabla inválido` | ✓ PASS |
| CR-01 valid path | `QueryBuilder(Agente, None)._build_base()[0]` | `'FROM agentes mm'` | ✓ PASS |
| CR-02 absent conflict | `build_upsert(..., conflict=['id'])` | `ValueError: ... no está en el INSERT` | ✓ PASS |
| CR-03 MERGE double | `await obj.insert(replace=True)` | `0`, `obj.id is None`, 1 query | ✓ PASS |
| WR-01a absent update_cols | `build_upsert(..., conflict=['a'], update_cols=['b'])` | no raise; `dst.b = src.b` | ✗ FAIL |
| WR-01b empty conflict | `Model.upsert(conflict=[])` | no raise; `ON ()` reaches driver | ✗ FAIL |
| IN-01 TOCTOU | mutate `_table` after construction | `FROM t; DROP TABLE usuarios -- mm` | ✗ FAIL |
| IN-02 trailing newline | `check_identifier('agentes\n', ...)` | returns `'agentes\n'` | ✗ FAIL |
| Byte-identity | `git diff --stat d4df155~1..HEAD -- tests/__snapshots__/ encino_orm/mssql.py encino_orm/oracle.py` | empty | ✓ PASS |
| Debt-marker gate | `grep TBD/FIXME/XXX` over round-modified source | 0 hits | ✓ PASS |
| Lint / format / types | `ruff check`, `ruff format --check`, `mypy encino_orm` | all exit 0; `noqa` = 0 | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — the phase declares no probes and `scripts/*/tests/probe-*.sh` finds none (no `scripts/` directory). The runnable verification is pytest, executed above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DIAL-01 | 02-10 | Allowlist centralized as a pure refactor | ✓ SATISFIED | `dialects/identifiers.py`; unchanged strict allowlist. |
| DIAL-02 | 02-10, 02-11, 02-12 | Shared DML builders validate table/columns on all six engines | ✓ SATISFIED | builders guard + CR-01/CR-02 fixes; WR-01 is an adjacent-input incompleteness, not a regression of valid DML. |
| DIAL-03 | (02-09) | `count`/`paginate`/`list_tables` correct on PG/MSSQL/Oracle | ✓ SATISFIED | Closed in the prior round; unaffected. |
| DIAL-04 | (02-04) | Introspected identifiers validated before ALTER TABLE | ✓ SATISFIED | Unchanged. |
| DIAL-05 | 02-12 | `Query` correctness + `with_params()` | ✓ SATISFIED | Cardinality contract + changelog entry. |
| DIAL-06 | (02-04) | `MAX_PARAMS`/`MAX_ROWS` per dialect | ✓ SATISFIED | Unchanged. |
| DIAL-07 | (02-05) | Dialect snapshots on the always-on SQLite job | ✓ SATISFIED | 10 snapshots pass; `.ambr` untouched. |
| DIAL-08 | (02-05) | CI matrix covers multiple engines | ✓ SATISFIED | Unchanged; engine-heavy structural only. |
| DIAL-09 | 02-11 | Per-engine integration tests for count/paginate/list_tables/sync_schema/last_id | ✓ SATISFIED | New live MSSQL/Oracle upsert + id-semantics tests pass. |

**Orphaned requirements:** none.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `encino_orm/dialects/builders.py` | 46-51, 229 | guard covers `conflict_cols` only | ⚠️ Warning | WR-01: absent `update_cols` / empty `conflict_cols` emit invalid MERGE SQL. |
| `encino_orm/dialects/identifiers.py` | 21 | `$` anchor accepts trailing newline | ℹ️ Info | IN-02: not exploitable; now gates `_table`. |
| `tests/test_query_builder.py` | 431, 441 | CWD-relative path | ℹ️ Info | IN-04: fails if pytest runs from another directory. |

No `TBD`/`FIXME`/`XXX` markers in any round-modified source file (debt-marker gate PASS).

### Human Verification Required

See `human_verification:` in the frontmatter (engine-heavy CI run; CI collection of the new live tests; disposition decision for WR-01 and IN-05).

### Gaps Summary

The round is a **genuine closure of the five original gaps**. All of CR-01, CR-02, CR-03, WR-01 and
WR-02 are closed, with independent reproductions: the `_table` injection vector is dead at both the
constructor and `join()`; the merge render rejects absent conflict columns before the driver; MSSQL
`insert(replace=True)` no longer hands back another row's id; the deferral log is accurate and owned;
and the cardinality change is in the changelog. The full suite is green at `787` against all six live
engines, snapshots and adapters are byte-identical, and lint/format/type gates pass.

Two caveats keep the status at `gaps_found`:

1. **WR-01 (WARNING, open).** The new fail-closed guard is narrower than the round advertises: it
   checks only `conflict_cols`. `build_upsert(..., update_cols=["b"])` with `b` absent from the INSERT
   still emits `dst.b = src.b`, and `Model.upsert(conflict=[])` — reachable through the public API —
   emits `ON ()` and reaches the driver. These are loud driver errors, not silent corruption, but the
   guard is the round's stated single choke point and should be completed (or explicitly accepted).
2. **IN-05 (status/traceability).** The original CR-03 truth ("returns the id of the row it just
   inserted") remains literally unmet while `ROADMAP.md` marks Phase 2 Complete and no override
   records the deviation. The code is safe and the deferral is documented, but the status should be
   made honest via an `overrides:` entry or a corrected status note.

IN-01 and IN-02 are low-risk residuals (TOCTOU on post-construction `_table` mutation with no in-repo
path; trailing-newline looseness in the allowlist). IN-03 and IN-04 are info-only quality notes. None
of these falsify the phase goal for valid inputs; they are recorded so they are not lost.

---

_Verified: 2026-09-18T14:54:58Z_
_Verifier: the agent (gsd-verifier)_
