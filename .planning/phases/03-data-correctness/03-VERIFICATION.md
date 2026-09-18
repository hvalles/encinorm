---
superseded_by: 03-VERIFICATION-FINAL2.md
superseded_at: 2026-09-18T23:30:00Z
superseded_reason: >
  Round-2 verification (pre-03-06..03-13). Its gaps were closed by gap-closure rounds 2-4 and
  independently re-verified in 03-VERIFICATION-FINAL2.md. Retained for history only.
phase: 03-data-correctness
verified: 2026-09-18T18:05:00Z
status: gaps_found
score: 19/22 must-haves verified
overrides_applied: 0
gaps:
  - truth: "CachedModel.update() / delete() / upsert() never leave a stale cached row readable (roadmap SC3; DATA-03 'sin lecturas obsoletas')"
    status: failed
    reason: >
      `_invalidate(keys)` deletes exactly the key derived from the WRITE keys, but `load(keys=...)`
      is public and caches under the READ keys (default `_pk_fields()`). The two key domains diverge
      whenever a write's identifying key differs from the key used at `load()` time, so the previously
      cached entry survives. D-11's premise ("load() solo cachea por clave de PK") is false. The phase's
      own test model (`_primary_key = ("rfc",)`) makes both domains coincide, masking the bug; the bug
      reproduces with the default `("id",)` PK.
    artifacts:
      - path: "encino_orm/model/cached.py"
        issue: >
          `_invalidate` (lines 31-42) and the `update`/`delete`/`upsert` overrides (71-91) invalidate
          only `self._cache_key(keys)`; `load` (44-69) caches under `self._cache_key(keys)` for the
          caller-supplied read keys. No code path invalidates the other domain.
    missing:
      - "Invalidate every key domain a row can be cached under (at minimum the PK key in addition to the write keys), or restrict `load()` to the PK domain so arbitrary read-key entries cannot exist"
      - "A regression test that caches under one key domain and writes under another (e.g. default-PK model: `load()` then `upsert(conflict=['rfc'])`; and `load(keys=['rfc'])` then `update()`)"
  - truth: "A failed/concurrent migrate() leaves a reconcilable state, never a schema change without a ledger record (DATA-02 intent)"
    status: partial
    reason: >
      WR-01: on implicit-commit engines, `_apply`'s pre-DDL compensation unconditionally deletes
      `WHERE name={name}`. Under concurrent `migrate(<same name>)` on MySQL/MariaDB/Oracle, process B's
      duplicate-insert failure can delete the row process A just published, leaving the DDL applied with
      no ledger record — exactly the failure DATA-02 exists to eliminate. Requires concurrent `migrate()`
      (an operator misuse), so it is a residual concurrency hazard rather than a single-process failure.
    artifacts:
      - path: "encino_orm/migration.py"
        issue: "`_apply` (lines 93-99) cannot distinguish 'I created this row' from 'someone else did'."
    missing:
      - "Make the pre-DDL compensation conditional on this call having inserted the row (track the INSERT success), or document that concurrent migrate() is unsupported and serialize it"
  - truth: "resolve_migration executes the four D-08/D-17 actions (03-02 must-have)"
    status: partial
    reason: >
      IN-01: D-08's `rolling_back` + `applied=True` row specifies "Restaurar `applied` Y reintentar el
      rollback". The implementation only restores `applied`; the operator must re-issue
      `rollback_migration`. The state transitions for all four rows are correct; the retry-rollback half
      of the fourth action is not automated. The plan scoped it this way (03-02 Task 2) and the docstring
      was trimmed to match, so it is a spec/implementation deviation, not a coding error.
    artifacts:
      - path: "encino_orm/migration.py"
        issue: "`resolve_migration` (lines 195-220) restores `applied` without retrying the down."
    missing:
      - "Either invoke `rollback_migration` after restoring, or state explicitly in the docstring and the reconciliation error text that the rollback must be re-issued"
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

# Phase 3: Data Correctness Verification Report

**Phase Goal:** Migrations and the read cache stop lying. A rolled-back migration can be re-applied, a
failed `migrate()` leaves a reconcilable state, and cached rows are never stale after a write.
**Verified:** 2026-09-18T18:05:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | After `rollback_migration`, the `{name}` row is gone and no `{name}:down` row is written | ✓ VERIFIED | `grep ":down" encino_orm/migration.py` = 0; `test_rollback_ledger_deletes_row_and_inserts_no_down` passes |
| 2 | Re-applying the same migration after rollback re-runs its `up` | ✓ VERIFIED | `test_reapply_after_rollback` passes (52-test phase run) |
| 3 | The row is `rolling_back` while the `down` runs | ✓ VERIFIED | `test_rollback_marks_rolling_back_during_down` passes; `migration.py:139` sets status before `down` |
| 4 | `status` exists in all six engines' ledger and is added idempotently to legacy tables | ✓ VERIFIED | `status` DDL present in sqlite/postgresql/mysql/mssql/oracle; `_ensure_status_column` in all 5 edited adapters (MariaDB inherits MySQL); `test_ensure_status_is_idempotent` passes |
| 5 | An already-`applied` migration remains a no-op (idempotency by name) | ✓ VERIFIED | `test_migrate_is_idempotent` passes; `migrate()` returns on existing row |
| 6 | `migrate()` inserts `pending` before the DDL and promotes to `applied` after | ✓ VERIFIED | `migration.py:65-108` `_apply`; `test_aplicacion_exitosa_promueve_a_applied` passes |
| 7 | With `transactional_ddl=False`, a failure after the DDL leaves a `pending` that `reconcile_migrations` detects (raising with the SQL) | ✓ VERIFIED | `test_commit_implicito_deja_pending_y_reconcile_lo_detecta` passes; `_apply` leaves pending on purpose (`migration.py:100-106`) |
| 8 | With `transactional_ddl=True`, the same failure leaves no `pending` | ✓ VERIFIED | `test_ddl_transaccional_no_deja_pending` passes |
| 9 | `resolve_migration(db, name, applied=...)` implements the four D-08/D-17 state transitions | ✓ VERIFIED (see IN-01) | Four tests (`pending`/`rolling_back` × `True`/`False`) pass; retry-rollback half of row 4 is not automated (WARNING) |
| 10 | The runner never calls `db.commit()`; works with a direct adapter and `PoolDb` | ✓ VERIFIED | `grep "db.commit()" encino_orm/migration.py` = 0; uses `async with db.transaction()` only; pool reconcile test passes |
| 11 | `reconcile_migrations(pool)` works before any `migrate()` (pool delegates `_ensure_migrations_table`) | ✓ VERIFIED | `PoolDb._ensure_migrations_table` (pool.py:226-228); `test_reconcile_migrations_on_pool_ensures_ledger` passes against a real SQLite pool |
| 12 | `CachedModel.update()` never leaves a stale cached row readable | ✗ FAILED | **CR-01 reproduced**: default-PK model, `load()` then `update(keys=["rfc"])` leaves the PK entry stale; next `load()` returns `Viejo` while the DB holds `Nuevo` |
| 13 | `CachedModel.delete()` never leaves a stale cached row readable | ✗ FAILED | Same root cause as #12 (identical `_invalidate(keys)` path); review reproduced `delete(keys=['rfc'])` leaving the PK entry stale |
| 14 | `CachedModel.upsert()` never leaves a stale cached row readable | ✗ FAILED | **CR-01 reproduced**: `load()` (PK) then `upsert(conflict=["rfc"])` leaves the PK entry `STALE PRESENT`; `load()` returns `Viejo` vs DB `Nuevo` |
| 15 | `insert_many(cache=...)` invalidates the PK key in `rows`; without `cache=` it does not invalidate | ✓ VERIFIED | `test_insert_many_invalidates` / `test_insert_many_without_cache_does_not_invalidate` pass |
| 16 | A `cache.delete` failure is fail-open (warning, no propagation) | ✓ VERIFIED | `test_invalidate_fail_open` passes; independently reproduced: `_invalidate(['nonexistent_field'])` logged the AttributeError and did not propagate |
| 17 | Plain `insert` does not invalidate; `save` is covered by delegation to `update` | ✓ VERIFIED | No `insert` override in `cached.py`; `save` (model.py:535-541) calls `self.update(...)` → dispatches to `CachedModel.update` |
| 18 | `MemoryCacheBackend` evicts the LRU entry when exceeding `max_size` (default 1024) | ✓ VERIFIED | `test_lru_evicts_least_recently_used`, `test_max_size_is_respected`, `test_default_max_size_is_1024` pass |
| 19 | `get`/`set` update recency; `len(cache._store)` still reflects entry count; TTL still works | ✓ VERIFIED | `move_to_end` in get/set; `test_store_len_is_preserved`, `test_expiration_still_works` pass; `test_cached_model.py` `len(_store)` invariant passes |
| 20 | `MemoryCacheBackend` dev/test-only contract documented in the docstring | ✓ VERIFIED | `cache_backend.py:13-19`; `grep "dev/test"` ≥ 1 |
| 21 | `docs/guide.md` documents the dev/test contract, LRU bound, and local (non-distributed) invalidation | ✓ VERIFIED | `docs/guide.md:492-513` |
| 22 | `CHANGELOG.md` documents the phase's incompatible changes without duplicating `### Corregido` | ✓ VERIFIED | `CHANGELOG.md:77-106` (4 entries); exactly one `### Corregido` inside `[Unreleased]` |

**Score:** 19/22 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/migration.py` | `MIGRATIONS_TABLE`, status constants, corrected `rollback_migration`, `_apply`, `reconcile_migrations`, `resolve_migration` | ✓ VERIFIED | All present; `_down`=0, `db.commit()`=0; helpers `_ensure_ledger`/`_row_status`/`_set_status`/`_delete_row` exist |
| `encino_orm/sqlite.py` | ledger `status` + idempotent `_ensure_status_column` + two-phase `migrate()` | ✓ VERIFIED | `status TEXT NOT NULL DEFAULT 'applied'`; `_ensure_status_column` defined+called; `reconcile_migrations(self)` + `_apply` |
| `encino_orm/postgresql.py` | same (no explicit commit) | ✓ VERIFIED | `status VARCHAR(20)`; `_ensure_status_column`; two-phase `migrate()` |
| `encino_orm/mysql.py` | same via `_execute_raw` | ✓ VERIFIED | `status VARCHAR(20)`; `_ensure_status_column`; `_apply` |
| `encino_orm/mssql.py` | same via `_execute_raw` | ✓ VERIFIED | `status NVARCHAR(20)`; `_ensure_status_column`; `_apply` |
| `encino_orm/oracle.py` | same via `_execute_raw` (PL/SQL escaped) | ✓ VERIFIED | `status VARCHAR2(20)`; `_ensure_status_column`; `_apply` |
| `encino_orm/mariadb.py` | explicit `transactional_ddl` | ✓ VERIFIED | `transactional_ddl = TRANSACTIONAL_DDL["mariadb"]` |
| `encino_orm/dialects/strategies.py` | `TRANSACTIONAL_DDL` map | ✓ VERIFIED | `{sqlite:True, mysql:False, mariadb:False, postgresql:True, mssql:True, oracle:False}` |
| `encino_orm/base.py` | `Db.transactional_ddl = True` | ✓ VERIFIED | base.py:24 |
| `encino_orm/pool.py` | `transactional_ddl` property + `_ensure_migrations_table` delegation | ✓ VERIFIED | pool.py:92-98, 226-228 |
| `encino_orm/model/cached.py` | `_invalidate`, write overrides, `_cache_key_for`, `insert_many` override | ⚠️ ORPHANED-BUG (see CR-01) | Artifacts exist and are wired, but the invalidation domain is wrong → stale reads |
| `encino_orm/model/model.py` | `insert_many(..., cache=None)` signature parity | ✓ VERIFIED | model.py:543-551 |
| `encino_orm/model/cache_backend.py` | bounded LRU + dev/test docstring | ✓ VERIFIED | `OrderedDict`, `move_to_end`, `popitem(last=False)`, `max_size=1024` |
| `tests/test_migrations.py` | rollback/reapply/ensure_status regressions | ✓ VERIFIED | 3 tests pass |
| `tests/test_migration_reconcile.py` | fake-Db state machine + pool ledger test | ✓ VERIFIED | 11 tests pass |
| `tests/test_dialect_ddl.py` | DB-free map/attr/pool asserts | ✓ VERIFIED | 7 tests pass |
| `tests/test_cached_model.py` | invalidation + fail-open | ✓ VERIFIED (domain-masked) | 9 tests pass, but the model pins `_primary_key=("rfc",)` so write/read domains coincide |
| `tests/test_cache_backend.py` | DB-free LRU/TTL | ✓ VERIFIED | 6 tests pass |
| `docs/guide.md` | dev/test + multi-process limitation | ✓ VERIFIED | §10 |
| `CHANGELOG.md` | four breaking-change entries | ✓ VERIFIED | `[Unreleased] ### Corregido` |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `migration.py::rollback_migration` | `Db.transaction()` | `async with db.transaction()` | ✓ WIRED | present |
| adapters `::migrate` | `migration.py::reconcile_migrations` + `_apply` | module import | ✓ WIRED | 5 adapters call `reconcile_migrations(self)`; MariaDB inherits MySQL |
| `migration.py::_apply` | `Db.transactional_ddl` | runtime read | ✓ WIRED | migration.py:94/100/107 |
| `pool.py::transactional_ddl` | `self._template.transactional_ddl` | property | ✓ WIRED | pool.py:92-98 |
| `migration.py::_ensure_ledger` | `PoolDb._ensure_migrations_table` | pool delegation | ✓ WIRED | pool.py:226-228 |
| `cached.py::update`/`delete`/`upsert` | `CacheBackend.delete` | `_invalidate(keys)` | ✗ PARTIAL | The call fires, but under the WRITE key only; the `load()` READ key (default PK) is not covered → CR-01 |
| `cached.py::insert_many` | `CacheBackend.delete` | `_cache_key_for(pk, row)` | ✓ WIRED | PK domain matches `load(keys=<PK>)` |
| `cache_backend.py::set` | `OrderedDict.popitem(last=False)` | LRU eviction | ✓ WIRED | cache_backend.py:42-43 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `CachedModel.load` | `raw` (cache bytes) | `cache.get(self._cache_key(keys))` where `keys` = caller read keys | Yes (real payload written by a prior `load`) | ⚠️ HOLLOW on write: `_invalidate` deletes a different key, so the entry survives and is served stale |
| `CachedModel._invalidate` | delete key | `self._cache_key(normalized_write_keys)` | Deletes the write-key domain only | ✗ DISCONNECTED from the read-key domain written by `load(keys=...)` |
| `MemoryCacheBackend` | `_store` | in-process OrderedDict | Real entries; bounded by LRU | ✓ FLOWING |
| ledger `status` | `status` column | `_apply` inserts `pending`, promotes `applied` | Real DB writes via bound params | ✓ FLOWING |

**Root cause (Level 4):** the write path (`_invalidate`) and the read path (`load`) derive cache keys from
two independent inputs. The wiring is present but the two ends speak different key domains. This is the
data-flow disconnect behind CR-01.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase tests (migrations, reconcile, cached, cache_backend, dialect_ddl) | `uv run pytest tests/test_migrations.py tests/test_migration_reconcile.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_dialect_ddl.py -q` | 52 passed | ✓ PASS |
| Full suite with all six engines | `uv run pytest -q` | 824 passed, 0 skipped (20.7s) | ✓ PASS |
| Idempotency + rollback regressions | `pytest test_sqlite.py::...test_migrate_is_idempotent` + `-k "reapply_after_rollback or rollback_ledger or ensure_status"` | 3 passed | ✓ PASS |
| CR-01: default-PK, `load()` then `upsert(conflict=['rfc'])` | repro script on real `SqliteDb` | PK entry `STALE PRESENT`; `load()` → `Viejo`, DB → `Nuevo` | ✗ FAIL |
| CR-01 mirror: default-PK, `load(keys=['rfc'])` then `update()` | repro script on real `SqliteDb` | rfc entry `STALE PRESENT`; `load(keys=['rfc'])` → `Viejo`, DB → `Nuevo` | ✗ FAIL |
| WR-02: `_invalidate(['nonexistent_field'])` | repro script | Logged warning, did **not** propagate → fail-open holds | ✓ PASS (WR-02 not reproducible) |
| IN-03: `MemoryCacheBackend(max_size=-1)` | repro script | `KeyError: 'dictionary is empty'` | ✗ FAIL (INFO-level) |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | — | No `scripts/*/tests/probe-*.sh` exist; phase declares no probes (not a migration/tooling phase in the probe sense) | SKIPPED (N/A) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DATA-01 | 03-01 | `rollback_migration` ledger corrected: re-applying after rollback works | ✓ CLOSED | Truths 1–3, 5; regression tests pass |
| DATA-02 | 03-01, 03-02 | `migrate()` atomic or records intent + reconciles at startup (`transactional_ddl`) | ✓ CLOSED (WR-01 residual) | Truths 4, 6–11; full suite with all engines passes; concurrent-migrate hazard remains (WR-01) |
| DATA-03 | 03-03 | `CachedModel` invalidates cache on `update` and `delete` (store-then-invalidate), no stale reads | ✗ STILL OPEN | Truths 12–14 FAILED (CR-01 reproduced). Invalidation fires, but only for the write key domain; cross-domain writes leave a readable stale row |
| DATA-04 | 03-05, 03-04 | `MemoryCacheBackend` bounded or documented dev/test-only | ✓ CLOSED | Truths 18–22; LRU + docstring + guide + CHANGELOG |

**Orphaned requirements:** none. All four IDs (DATA-01…DATA-04) are claimed by plans and accounted for.
`REQUIREMENTS.md` traceability marks all four "Complete" — DATA-03's mark is not backed by the code
(correctness claim falsified below).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `encino_orm/model/cached.py` | 31-42, 71-91 | Cache-key domain mismatch (write keys vs read keys) | 🛑 BLOCKER | Stale reads survive writes (CR-01) |
| `encino_orm/migration.py` | 93-99 | Unconditional compensation DELETE can delete another process's row | ⚠️ WARNING | Concurrent `migrate()` can drop a ledger record (WR-01) |
| `encino_orm/migration.py` | 195-220 | D-08 row 4 "retry rollback" not automated | ⚠️ WARNING | Operator must re-issue `rollback_migration` (IN-01) |
| `encino_orm/migration.py` | 100-106 | Warning "quedó en 'pending'" is false for a DML `up` on implicit-commit engines | ℹ️ INFO | Misleading log only (IN-02) |
| `encino_orm/model/cache_backend.py` | 42-43 | `max_size < 0` raises `KeyError` instead of validating | ℹ️ INFO | Nonsensical config; no production impact (IN-03) |
| `encino_orm/migration.py` | 175 + adapters | Redundant ledger bootstrap per `migrate()` | ℹ️ INFO | Wasteful, harmless (IN-04) |
| `encino_orm/model/cached.py` | 36-38 | `_normalize_keys` outside the `try` (WR-02) | ℹ️ INFO — NOT A GAP | Independently reproduced: `_cache_key` is evaluated inside the `try`, and `_normalize_keys` does not raise for realistic inputs; fail-open holds |
| — | — | `TBD`/`FIXME`/`XXX` debt markers in phase files | ✓ none | `grep` over the 10 modified modules returned none |

### Human Verification Required

1. **Real implicit-commit DDL ambiguity (MySQL/MariaDB/Oracle)**
   **Test:** Kill the process between the DDL and the promote (or simulate on a live engine), then call `reconcile_migrations(db)` on restart.
   **Expected:** The surviving `pending` is detected and `MigrationError` carries the SQL; the DDL is never auto re-run and `applied` is never assumed.
   **Why human:** The automated test models this with a fake `Db` published-snapshot; real implicit-commit timing needs a live engine and process kill.

2. **Idempotent `ALTER TABLE ADD status` on MySQL/MariaDB (and Oracle/MSSQL)**
   **Test:** Run the ledger bootstrap twice against a real ledger created without `status`.
   **Expected:** Second run does not fail; `status` present after the first.
   **Why human:** The portable catalog-check recipe is not exercisable here for the non-SQLite engines; Oracle/MSSQL legacy-ALTER paths are verified by construction only.

3. **Operational accuracy of the multi-process cache limitation**
   **Test:** Confirm `docs/guide.md` §10's "no pub/sub; stale bounded by TTL" matches the deployment topology.
   **Expected:** Documentation matches operational behavior.
   **Why human:** Deployment topology and doc accuracy are not programmatically verifiable.

### Gaps Summary

The phase substantially delivers DATA-01, DATA-02 and DATA-04, and the migration half of the goal is
genuinely achieved: `rollback_migration` deletes `{name}` and never writes `:down`; the two-phase
`pending → DDL → applied` runner with `reconcile_migrations`/`resolve_migration` and the six-engine
`status` column all exist and pass 824 tests with all six engines live.

**DATA-03 fails the phase goal clause "cached rows are never stale after a write."** CR-01 is a real,
independently reproduced defect, not a theoretical concern: `load()` caches under the caller's read keys
(default the PK), while `_invalidate` deletes under the caller's write keys. When the two differ — e.g.
caching by PK and upserting by a natural unique key, or caching by a natural key and updating by PK —
the old entry survives and the next `load()` serves it. Both directions were reproduced on real SQLite.
The phase's test model pins `_primary_key = ("rfc",)`, which forces both domains to coincide and hides
the bug. This is the exact "read cache lies" failure the phase exists to eliminate.

WR-01 (concurrent-migrate compensation) and IN-01 (D-08 retry-rollback half) are warnings that do not
block the single-process goal but should be closed or explicitly accepted. WR-02 is a false positive —
fail-open holds.

Because a must-have truth is FAILED, the phase must not proceed to Phase 4 until CR-01 is fixed (or an
override is recorded with a documented reason). No later milestone phase addresses cache invalidation or
migration concurrency, so neither gap is deferrable.

---

_Verified: 2026-09-18T18:05:00Z_
_Verifier: the agent (gsd-verifier)_
