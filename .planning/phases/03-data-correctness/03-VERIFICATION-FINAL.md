---
superseded_by: 03-VERIFICATION-FINAL2.md
superseded_at: 2026-09-18T23:30:00Z
superseded_reason: >
  Round-2 final verification (after 03-06/03-07). Its BLOCKER (CR-01) and residuals were closed by
  gap-closure rounds 3-4 plus the post-review CR-R4-01 fix (ec47f3a), and independently re-verified
  in 03-VERIFICATION-FINAL2.md. Retained for history only.
phase: 03-data-correctness
verified: 2026-09-18T18:27:00Z
status: gaps_found
score: 19/22 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 19/22
  gaps_closed: []
  gaps_remaining:
    - "CachedModel.update()/delete()/upsert() never leave a stale cached row readable (CR-01 not fully closed)"
    - "A failed/concurrent migrate() leaves a reconcilable state (WR-01 residual)"
    - "resolve_migration executes the four D-08/D-17 actions (IN-01 retry-rollback half)"
  regressions: []
gaps:
  - truth: "CachedModel.update() / delete() / upsert() never leave a stale cached row readable (roadmap SC3; DATA-03 'sin lecturas obsoletas')"
    status: failed
    reason: >
      The CR-01 fix invalidates the PK key domain by deriving it from the WRITE INSTANCE's own
      field values (`self._cache_key(pk_keys)`). When the write instance does not carry the PK —
      the canonical `upsert(conflict=["rfc"])` / `update(keys=["rfc"])` on a fresh instance whose
      auto-`id` is still `None` — the derived key is `tabla:[id=None]`, which does NOT match the
      entry `load()` cached under `tabla:[id=1]`. The stale PK entry survives and the next `load()`
      returns the OLD value while the DB holds the NEW one. The fix only works when the write
      instance already holds the PK (e.g. the inserted/loaded instance), which is exactly the case
      the new regression test exercises. Independently reproduced on real SQLite (see Behavioral
      Spot-Checks A2/B2/C2). The pre-fix defect and the current defect share the same symptom
      (PK-cached entry survives a cross-key write); the fix is incomplete, not a new bug.
    artifacts:
      - path: "encino_orm/model/cached.py"
        issue: >
          `_invalidate` (lines 43-62) computes the PK-domain key from the current instance
          (`self._cache_key(dominio)`), so an instance with `id=None` derives a key that was never
          written. It never derives the affected row's real PK (no post-write lookup).
      - path: "tests/test_cached_model.py"
        issue: >
          `test_invalidate_also_pk_domain_cr01` (lines 176-193) writes with `c` — the instance
          returned by `insert()`, which carries `c.id`. It never exercises a write instance whose
          PK is unset, so it passes while the stated behavior still fails for that path.
    missing:
      - "Derive the affected row's real PK after the write when the write keys are not the PK (e.g. re-read the row by the write keys, then invalidate its PK key), OR restrict `load()` to the PK domain so arbitrary read-key entries cannot exist"
      - "A regression test where the write instance does NOT carry the PK: default-PK model, `load()` (caches under id), then `upsert(conflict=['rfc'])` / `update(keys=['rfc'])` / `delete(keys=['rfc'])` from an instance with `id=None`; assert the PK entry is gone and the next `load()` returns the NEW value"
  - truth: "A failed/concurrent migrate() leaves a reconcilable state, never a schema change without a ledger record (DATA-02 intent)"
    status: partial
    reason: >
      WR-01 unchanged by the CR-01 fix: on implicit-commit engines `_apply`'s pre-DDL compensation
      unconditionally deletes `WHERE name={name}` when the DDL did not run. Under concurrent
      `migrate(<same name>)` on MySQL/MariaDB/Oracle, process B's duplicate-insert failure can
      delete the row process A just published, leaving the DDL applied with no ledger record.
      Requires concurrent `migrate()` (operator misuse); the single-process phase goal is met.
    artifacts:
      - path: "encino_orm/migration.py"
        issue: "`_apply` (lines 93-99) cannot distinguish 'I created this row' from 'someone else did'."
    missing:
      - "Make the pre-DDL compensation conditional on this call having inserted the row, or document that concurrent migrate() is unsupported and serialize it"
  - truth: "resolve_migration executes the four D-08/D-17 actions (03-02 must-have)"
    status: partial
    reason: >
      IN-01 unchanged: D-08's `rolling_back` + `applied=True` row specifies 'Restaurar applied Y
      reintentar el rollback'. `resolve_migration` only restores `applied`; the operator must
      re-issue `rollback_migration`. The state transitions for all four rows are correct and the
      docstring documents the action it performs, but neither the docstring nor the reconciliation
      error text states that the rollback must be re-issued.
    artifacts:
      - path: "encino_orm/migration.py"
        issue: "`resolve_migration` (lines 195-220) restores `applied` without retrying the down."
    missing:
      - "Either invoke `rollback_migration` after restoring, or state explicitly in the docstring and the reconciliation error text that the rollback must be re-issued"
deferred: []
human_verification:
  - test: "Real implicit-commit DDL ambiguity on MySQL/MariaDB/Oracle: kill the process between the DDL and the promote (or simulate it), then call `reconcile_migrations(db)` on restart"
    expected: "The surviving `pending` row is detected and `MigrationError` is raised carrying the migration SQL; the DDL is never auto re-run and `applied` is never assumed"
    why_human: "Requires killing a process mid-migration against a real non-transactional-DDL engine; the automated test models this with a fake `Db` (published-snapshot), which cannot prove the real implicit-commit timing"
  - test: "Run `migrate()` twice (or `_ensure_status_column` twice) against a real MySQL/MariaDB ledger created without the `status` column"
    expected: "The second run does not fail; the catalog shows `status` after the first run (idempotent ALTER)"
    why_human: "The portable catalog-check recipe is not exercisable without a live MySQL/MariaDB server in this environment; Oracle/MSSQL legacy-ALTER paths are verified by construction only"
  - test: "Visual/user-facing confirmation that the documented multi-process cache limitation (docs/guide.md §10) is accurate for the deployment topology (no pub/sub; stale bounded by TTL)"
    expected: "Documentation matches operational behavior"
    why_human: "Deployment topology and doc accuracy are not programmatically verifiable"
---

# Phase 3: Data Correctness — Final Verification Report

**Phase Goal:** Migrations and the read cache stop lying. A rolled-back migration can be re-applied, a
failed `migrate()` leaves a reconcilable state, and cached rows are never stale after a write.
**Verified:** 2026-09-18T18:27:00Z
**Status:** gaps_found
**Re-verification:** Yes — after the CR-01 fix (`8206e75`)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After `rollback_migration`, the `{name}` row is gone and no `{name}:down` row is written | ✓ VERIFIED | `grep ":down" encino_orm/migration.py` = 0; `test_rollback_ledger_deletes_row_and_inserts_no_down` passes |
| 2 | Re-applying the same migration after rollback re-runs its `up` | ✓ VERIFIED | `test_reapply_after_rollback` passes |
| 3 | The row is `rolling_back` while the `down` runs | ✓ VERIFIED | `migration.py:139`; `test_rollback_marks_rolling_back_during_down` passes |
| 4 | `status` exists in all six engines' ledger and is added idempotently to legacy tables | ✓ VERIFIED | `status` DDL in sqlite/postgresql/mysql/mssql/oracle; `_ensure_status_column`; `test_ensure_status_is_idempotent` passes |
| 5 | An already-`applied` migration remains a no-op (idempotency by name) | ✓ VERIFIED | `test_migrate_is_idempotent` passes |
| 6 | `migrate()` inserts `pending` before the DDL and promotes to `applied` after | ✓ VERIFIED | `migration.py:65-108` `_apply`; `test_aplicacion_exitosa_promueve_a_applied` passes |
| 7 | With `transactional_ddl=False`, a failure after the DDL leaves a `pending` that `reconcile_migrations` detects (raising with the SQL) | ✓ VERIFIED | `test_commit_implicito_deja_pending_y_reconcile_lo_detecta` passes |
| 8 | With `transactional_ddl=True`, the same failure leaves no `pending` | ✓ VERIFIED | `test_ddl_transaccional_no_deja_pending` passes |
| 9 | `resolve_migration(db, name, applied=...)` implements the four D-08/D-17 state transitions | ✓ VERIFIED (IN-01 residual) | Four tests pass; retry-rollback half of row 4 is not automated (WARNING) |
| 10 | The runner never calls `db.commit()`; works with a direct adapter and `PoolDb` | ✓ VERIFIED | `grep "db.commit()" encino_orm/migration.py` = 0; pool reconcile test passes |
| 11 | `reconcile_migrations(pool)` works before any `migrate()` | ✓ VERIFIED | `pool.py:226-228`; `test_reconcile_migrations_on_pool_ensures_ledger` passes |
| 12 | `CachedModel.update()` never leaves a stale cached row readable | ✗ FAILED | Fix works only when the write instance carries the PK (A1/C1). With `id=None` on the write instance (A2/C2) the PK entry survives and `load()` returns `Viejo` vs DB `Nuevo` |
| 13 | `CachedModel.delete()` never leaves a stale cached row readable | ✗ FAILED | Same root cause as #12 (identical `_invalidate` path); C2 reproduced |
| 14 | `CachedModel.upsert()` never leaves a stale cached row readable | ✗ FAILED | **CR-01 still open**: `load()` (PK) then `upsert(conflict=['rfc'])` with an instance whose `id` is unset leaves the PK entry `STALE PRESENT`; `load()` → `Viejo`, DB → `Nuevo` (B2) |
| 15 | `insert_many(cache=...)` invalidates the PK key in `rows`; without `cache=` it does not | ✓ VERIFIED | `test_insert_many_invalidates` / `test_insert_many_without_cache_does_not_invalidate` pass; independently reproduced (F) |
| 16 | A `cache.delete` failure is fail-open (warning, no propagation) | ✓ VERIFIED | `test_invalidate_fail_open` passes; independently reproduced (E): warning logged, `update()` returned 1 |
| 17 | Plain `insert` does not invalidate; `save` is covered by delegation to `update` | ✓ VERIFIED | No `insert` override; `save` (model.py:535-541) calls `self.update(...)` |
| 18 | `MemoryCacheBackend` evicts the LRU entry when exceeding `max_size` (default 1024) | ✓ VERIFIED | `test_lru_evicts_least_recently_used`, `test_max_size_is_respected`, `test_default_max_size_is_1024` pass |
| 19 | `get`/`set` update recency; `len(cache._store)` reflects entry count; TTL still works | ✓ VERIFIED | `move_to_end` in get/set; LRU/TTL tests pass |
| 20 | `MemoryCacheBackend` dev/test-only contract documented in the docstring | ✓ VERIFIED | `cache_backend.py:13-19` |
| 21 | `docs/guide.md` documents the dev/test contract, LRU bound, and local (non-distributed) invalidation | ✓ VERIFIED | `docs/guide.md:492-513` |
| 22 | `CHANGELOG.md` documents the phase's incompatible changes without duplicating `### Corregido` | ✓ VERIFIED | `[Unreleased] ### Corregido` (4 entries) |

**Score:** 19/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/migration.py` | ledger constants, corrected `rollback_migration`, `_apply`, `reconcile_migrations`, `resolve_migration` | ✓ VERIFIED | All present; `:down`=0, `db.commit()`=0 |
| `encino_orm/sqlite.py` | ledger `status` + idempotent `_ensure_status_column` + two-phase `migrate()` | ✓ VERIFIED | `status TEXT NOT NULL DEFAULT 'applied'` |
| `encino_orm/postgresql.py` | same (no explicit commit) | ✓ VERIFIED | `status VARCHAR(20)` |
| `encino_orm/mysql.py` | same via `_execute_raw` | ✓ VERIFIED | `status VARCHAR(20)` |
| `encino_orm/mssql.py` | same via `_execute_raw` | ✓ VERIFIED | `status NVARCHAR(20)` |
| `encino_orm/oracle.py` | same via `_execute_raw` (PL/SQL escaped) | ✓ VERIFIED | `status VARCHAR2(20)` |
| `encino_orm/mariadb.py` | explicit `transactional_ddl` | ✓ VERIFIED | `TRANSACTIONAL_DDL["mariadb"]` |
| `encino_orm/dialects/strategies.py` | `TRANSACTIONAL_DDL` map | ✓ VERIFIED | six-engine map |
| `encino_orm/base.py` | `Db.transactional_ddl = True` | ✓ VERIFIED | base.py:24 |
| `encino_orm/pool.py` | `transactional_ddl` property + `_ensure_migrations_table` delegation | ✓ VERIFIED | pool.py:92-98, 226-228 |
| `encino_orm/model/cached.py` | `_invalidate` (two key domains), write overrides, `_delete_cached`, `insert_many` override | ⚠️ PARTIAL-BUG | `_delete_cached` extraction and the PK-domain attempt are present and wired, but the PK key is derived from the instance and misses when the write instance lacks the PK → CR-01 residual |
| `encino_orm/model/model.py` | `insert_many(..., cache=None)` signature parity | ✓ VERIFIED | model.py:543-551 |
| `encino_orm/model/cache_backend.py` | bounded LRU + dev/test docstring | ✓ VERIFIED | `OrderedDict`, `move_to_end`, `popitem(last=False)`, `max_size=1024` |
| `tests/test_cached_model.py` | invalidation + fail-open + CR-01 regression | ⚠️ PARTIAL | 10 tests pass, but the CR-01 regression uses a PK-carrying write instance and does not cover the `id=None` write path |
| `tests/test_migrations.py` / `test_migration_reconcile.py` / `test_dialect_ddl.py` / `test_cache_backend.py` | phase regressions | ✓ VERIFIED | 43 tests pass |
| `docs/guide.md` | dev/test + multi-process limitation | ✓ VERIFIED | §10 |
| `CHANGELOG.md` | four breaking-change entries | ✓ VERIFIED | `[Unreleased] ### Corregido` |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `migration.py::rollback_migration` | `Db.transaction()` | `async with db.transaction()` | ✓ WIRED | present |
| adapters `::migrate` | `reconcile_migrations` + `_apply` | module import | ✓ WIRED | 5 adapters; MariaDB inherits MySQL |
| `migration.py::_apply` | `Db.transactional_ddl` | runtime read | ✓ WIRED | migration.py:94/100/107 |
| `pool.py::transactional_ddl` | `self._template.transactional_ddl` | property | ✓ WIRED | pool.py:92-98 |
| `cached.py::update`/`delete`/`upsert` | `CacheBackend.delete` | `_invalidate(keys)` → `_delete_cached` | ⚠️ PARTIAL | Fires for the write-key domain and for the PK domain **only if the instance holds the PK**; the `id=None` write path derives a key that was never written → CR-01 residual |
| `cached.py::insert_many` | `CacheBackend.delete` | `_cache_key_for(pk, row)` | ✓ WIRED | PK domain matches `load(keys=<PK>)` |
| `cache_backend.py::set` | `OrderedDict.popitem(last=False)` | LRU eviction | ✓ WIRED | cache_backend.py:42-43 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `CachedModel.load` | `raw` (cache bytes) | `cache.get(self._cache_key(read_keys))` | Yes | ⚠️ HOLLOW on cross-key write: when the write instance's PK is unset, `_invalidate` deletes `[id=None]` while `load()` cached `[id=1]`; the stale entry is served |
| `CachedModel._invalidate` | delete key | `self._cache_key(write_keys)` + `self._cache_key(pk_keys)` | The PK key is derived from the instance, not from the affected row | ✗ DISCONNECTED when `self` lacks the PK |
| `MemoryCacheBackend` | `_store` | in-process OrderedDict | Real entries; bounded by LRU | ✓ FLOWING |
| ledger `status` | `status` column | `_apply` inserts `pending`, promotes `applied` | Real DB writes via bound params | ✓ FLOWING |

**Root cause (Level 4):** the write path derives the "PK domain" key from the *write instance's* field
values. The read path derives it from the *cached row's* values. They coincide only when the write
instance already carries the PK. The fix needs a post-write row lookup (or a PK-only `load()` cache
domain) to close the gap.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase tests (migrations, reconcile, cached, cache_backend, dialect_ddl) | `uv run pytest tests/test_migrations.py tests/test_migration_reconcile.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_dialect_ddl.py -q` | 53 passed | ✓ PASS |
| Full suite | `uv run pytest -q` | 825 passed (10 snapshots) | ✓ PASS |
| Gates | `ruff check` / `ruff format --check` / `mypy encino_orm` | exit 0; `noqa`=0 | ✓ PASS |
| CR-01 A1: default-PK, `load()` (PK) then `update(keys=['rfc'])`, write instance HAS id | repro on real `SqliteDb` | pk entry deleted; `load()` → `Nuevo`; DB → `Nuevo` | ✓ FIXED for this path |
| CR-01 A2: same but write instance LACKS id | repro on real `SqliteDb` | pk entry `STALE PRESENT`; `load()` → `Viejo`; DB → `Nuevo` | ✗ FAIL |
| CR-01 B1: `load()` (PK) then `upsert(conflict=['rfc'])`, instance HAS id | repro | pk entry deleted; `load()` → `Nuevo` | ✓ FIXED for this path |
| CR-01 B2: same but instance LACKS id | repro | pk entry `STALE PRESENT`; `load()` → `Viejo`; DB → `Nuevo` | ✗ FAIL |
| CR-01 C1/C2: `load()` (PK) then `delete(keys=['rfc'])`, instance HAS / LACKS id | repro | pk deleted / pk `STALE PRESENT` | ✓ / ✗ |
| Key derivation | repro | cached key (`id=1`) `86bc683c…` ≠ derived key (`id=None`) `18aade66…` | ✗ FAIL |
| Reverse residual: `load(keys=['rfc'])` then `update()` by PK | repro | rfc entry survives; `load(keys=['rfc'])` → `Viejo2` vs DB `Nuevo2` | ✗ FAIL (residual) |
| WR-02: fail-open on `cache.delete` failure | repro (E) | warning logged, no propagation, write committed | ✓ PASS (fail-open holds) |
| IN-03: `MemoryCacheBackend(max_size=-1)` | repro | `KeyError: 'dictionary is empty'` | ✗ FAIL (INFO-level) |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | — | No `scripts/*/tests/probe-*.sh` exist; the phase declares no probes | SKIPPED (N/A) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DATA-01 | 03-01 | `rollback_migration` ledger corrected: re-applying after rollback works | ✓ CLOSED | Truths 1–3, 5; regression tests pass |
| DATA-02 | 03-01, 03-02 | `migrate()` atomic or records intent + reconciles at startup | ✓ CLOSED (WR-01 residual) | Truths 4, 6–11; 825 tests pass; concurrent-migrate hazard remains |
| DATA-03 | 03-03 | `CachedModel` invalidates cache on `update` and `delete` (store-then-invalidate), no stale reads | ✗ STILL OPEN | Truths 12–14 FAILED. The fix closes the PK-carrying write path but not the canonical `upsert(conflict=...)` with an unset auto-PK |
| DATA-04 | 03-05, 03-04 | `MemoryCacheBackend` bounded or documented dev/test-only | ✓ CLOSED | Truths 18–22 |

**Orphaned requirements:** none. All four IDs are claimed by plans and accounted for.

### Finding Verdicts

| Finding | Verdict | Assessment |
| ------- | ------- | ---------- |
| **CR-01** | ✗ **NOT CLOSED (BLOCKER)** | The fix invalidates the PK domain only when the write instance carries the PK. `upsert(conflict=['rfc'])` (the documented reason `conflict=` exists) and `update(keys=['rfc'])` on an instance whose auto-`id` is `None` still leave the PK-cached entry stale (B2/A2/C2). Independently reproduced on real SQLite. |
| **WR-01** | ⚠️ **REAL RESIDUAL (WARNING)** | `_apply`'s pre-DDL compensation deletes `WHERE name={name}` without proving ownership; concurrent `migrate()` on MySQL/MariaDB/Oracle can drop another process's ledger row. Not reachable in the supported single-process flow, so it does not block the phase goal, but it is a genuine concurrency hazard and no later milestone phase owns it (Phase 4 is pool concurrency; Phase 7 is perf/bounded structures; Phase 8 is release). Keep recorded. |
| **WR-02** | ✓ **NOT A GAP** | `_invalidate` calls `_normalize_keys`/`_cache_key` outside the `try`, but it only runs after `super().update/delete/upsert` succeeded with the same keys, so key derivation cannot raise for those paths. `_delete_cached` still wraps `cache.delete` and preserves fail-open. Reproduced (E). |
| **IN-01** | ⚠️ **SPEC DEVIATION (LOW)** | D-08 row 4's "retry the rollback" half is not automated and not stated in the docstring or the reconciliation error text. The state machine is otherwise correct; no stale reads or lost ledger records. Recorded as a residual. |
| **IN-03** | ℹ️ **INFO** | `MemoryCacheBackend(max_size=-1)` raises `KeyError` instead of validating. Dev/test-only backend; nonsensical config; no production impact. Recorded as a residual. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `encino_orm/model/cached.py` | 43-62 | PK-domain key derived from the write instance, not from the affected row | 🛑 BLOCKER | Stale PK-cached entry survives a cross-key write (CR-01 residual) |
| `tests/test_cached_model.py` | 176-193 | Regression test writes with a PK-carrying instance only | ⚠️ WARNING | Test passes while the stated behavior still fails for `id=None` writes |
| `encino_orm/migration.py` | 93-99 | Unconditional compensation DELETE can delete another process's row | ⚠️ WARNING | Concurrent `migrate()` can drop a ledger record (WR-01) |
| `encino_orm/migration.py` | 195-220 | D-08 row 4 "retry rollback" not automated | ⚠️ WARNING | Operator must re-issue `rollback_migration` (IN-01) |
| `encino_orm/model/cache_backend.py` | 42-43 | `max_size < 0` raises `KeyError` instead of validating | ℹ️ INFO | Nonsensical config; no production impact (IN-03) |
| — | — | `TBD`/`FIXME`/`XXX` debt markers in phase files | ✓ none | grep over the modified modules returned none |

### Human Verification Required

1. **Real implicit-commit DDL ambiguity (MySQL/MariaDB/Oracle)**
   **Test:** Kill the process between the DDL and the promote (or simulate on a live engine), then call `reconcile_migrations(db)` on restart.
   **Expected:** The surviving `pending` is detected and `MigrationError` carries the SQL; the DDL is never auto re-run and `applied` is never assumed.
   **Why human:** The automated test models this with a fake `Db` published-snapshot; real implicit-commit timing needs a live engine and a process kill.

2. **Idempotent `ALTER TABLE ADD status` on MySQL/MariaDB (and Oracle/MSSQL)**
   **Test:** Run the ledger bootstrap twice against a real ledger created without `status`.
   **Expected:** Second run does not fail; `status` present after the first.
   **Why human:** The portable catalog-check recipe is not exercisable here for the non-SQLite engines; Oracle/MSSQL legacy-ALTER paths are verified by construction only.

3. **Operational accuracy of the multi-process cache limitation**
   **Test:** Confirm `docs/guide.md` §10's "no pub/sub; stale bounded by TTL" matches the deployment topology.
   **Expected:** Documentation matches operational behavior.
   **Why human:** Deployment topology and doc accuracy are not programmatically verifiable.

### Gaps Summary

The migration half of the phase remains genuinely achieved (DATA-01 and DATA-02; 825 tests, all gates
green), and DATA-04 is closed. The CR-01 fix (`8206e75`) is a real but **incomplete** improvement: it
now invalidates the PK key domain **when the write instance already carries the PK** (A1/B1/C1), but the
canonical cross-key write from a fresh instance still leaves the PK-cached entry readable.

The stated requirement — "with a DEFAULT-PK model, `load()` (caches under `id`) then a write by a
DIFFERENT key (`update(keys=['rfc'])` / `upsert(conflict=['rfc'])`) must invalidate the `id` entry, and
a subsequent `load()` must return the NEW value" — is **not met**. Independently reproduced on real
SQLite:

```
[A2 update(keys=['rfc']) instance LACKS id] pk_before=True pk_after=True load='Viejo' db='Nuevo'
[B2 upsert(conflict=['rfc']) instance LACKS id] pk_before=True pk_after=True load='Viejo' db='Nuevo'
[C2 delete(keys=['rfc']) instance LACKS id] pk_before=True pk_after=True
cached PK key (id=1) = 86bc683c…   key derived from no-id write = 18aade66…   match = False
```

The new regression test `test_invalidate_also_pk_domain_cr01` uses `c` — the instance returned by
`insert()`, which holds `c.id` — so it exercises exactly the case the fix handles and never the
`id=None` write path. The reverse residual (`load(keys=['rfc'])` then `update()` by PK) also remains and
is unreachable to invalidate without a row lookup; the task's "impossible by construction" note applies
to that half, but not to A2/B2/C2, where the write *does* know the natural key and could derive the PK.

Because a must-have truth is FAILED, **DATA-03 remains OPEN and the phase must not proceed to Phase 4
until CR-01 is fully closed** (or an override is recorded). No later milestone phase addresses cache
invalidation correctness, so this gap is not deferrable. WR-01 and IN-01 are recorded residuals; WR-02
is a false positive; IN-03 is INFO-level.

---

_Verified: 2026-09-18T18:27:00Z_
_Verifier: the agent (gsd-verifier)_
