---
phase: 03-data-correctness
verified: 2026-09-18T23:30:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 19/22
  previous_report: 03-VERIFICATION-FINAL.md
  gaps_closed:
    - "CR-01 (DATA-03): cross-key write from a PK-less instance left the PK-cached entry stale — closed by 03-06/03-08 and independently reproduced at HEAD"
    - "CR-02/CR-R3-01 (SEC-01): Model.update/delete did not carry the scope() predicate in the DML — closed by 03-11 and independently reproduced"
    - "CR-R4-01 (DATA-03): the invalidation probe bound raw non-PK values instead of the serialized DML value, so datetime/Decimal/list/dict write keys left the cache stale — closed by ec47f3a and independently reproduced"
    - "WR-01 residual (DATA-02): pre-DDL compensation could delete another runner's pending row — closed by 03-07/03-09 (identity-based delete with documented fallback)"
    - "WR-R3-02: _union raised TypeError after a committed write for unhashable PKs — closed by 03-12"
    - "IN-01: rollback re-issue documented in docstring + reconciliation error — closed by 03-07"
    - "WR-R3-03/WR-R3-04/IN-R3-01/IN-R3-03: docs/CHANGELOG overclaims and inaccurate Oracle note — closed by 03-13 + ec47f3a (STATE.md)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Real implicit-commit DDL ambiguity on MySQL/MariaDB/Oracle: kill the process between the DDL and the promote, then call reconcile_migrations(db) on restart"
    expected: "The surviving pending row is detected and MigrationError is raised carrying the migration SQL; the DDL is never auto re-run and applied is never assumed"
    why_human: "Environment-limited (informational, non-blocking): no live MySQL/MariaDB/Oracle server here. The automated test models implicit commit faithfully with a published-snapshot fake Db; real driver timing is not programmatically verifiable in this environment."
  - test: "Run the ledger bootstrap twice against a real MySQL/MariaDB ledger created without the status column"
    expected: "The second run does not fail; status is present after the first run (idempotent ALTER)"
    why_human: "Environment-limited (informational, non-blocking): the portable catalog-check recipe needs a live MySQL/MariaDB server; Oracle/MSSQL legacy-ALTER paths are verified by construction only."
  - test: "Confirm the documented multi-process cache limitation matches the deployment topology"
    expected: "docs/guide.md §10's 'no pub/sub; stale bounded by TTL' matches operational behavior"
    why_human: "Deployment topology and doc accuracy are not programmatically verifiable."
---

# Phase 3: Data Correctness — Final Verification Report (round 4 closure)

**Phase Goal:** Migrations and the read cache stop lying. A rolled-back migration can be re-applied, a
failed `migrate()` leaves a reconcilable state, and cached rows are never stale after a write.
**Verified:** 2026-09-18T23:30:00Z
**Status:** passed
**Re-verification:** Yes — supersedes `03-VERIFICATION.md` and `03-VERIFICATION-FINAL.md` (both marked
`superseded_by: 03-VERIFICATION-FINAL2.md`). Verified at HEAD `ec47f3a` (post-round-4 CR-R4-01 fix).

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | **SC1/DATA-01** After `rollback_migration`, the `{name}` row is gone and no `{name}:down` row is written | ✓ VERIFIED | `grep ":down" encino_orm/migration.py` = 0; `test_rollback_ledger_deletes_row_and_inserts_no_down` passes; independent repro: ledger row `None` after rollback |
| 2 | **SC1/DATA-01** Re-applying the same migration after rollback re-runs its `up` (RED→GREEN) | ✓ VERIFIED | `test_reapply_after_rollback` passes; independent repro on real `SqliteDb`: second `apply_migration` succeeds with `status='applied'` |
| 3 | **SC1/DATA-01** The row is `rolling_back` while the `down` runs | ✓ VERIFIED | `migration.py:175`; `test_rollback_marks_rolling_back_during_down` passes |
| 4 | **SC2/DATA-02** `status` column exists in all six engines' ledger and is added idempotently to legacy tables | ✓ VERIFIED | `status` DDL in sqlite/mysql/postgresql/mssql/oracle; `_ensure_status_column` in all five; `test_ensure_status_is_idempotent` passes |
| 5 | **SC2/DATA-02** `migrate()` inserts `pending` before the DDL and promotes to `applied` after | ✓ VERIFIED | `migration.py:95-114` `_apply`; `test_aplicacion_exitosa_promueve_a_applied` passes |
| 6 | **SC2/DATA-02** With `transactional_ddl=False`, a failure after the DDL leaves a `pending` that `reconcile_migrations` detects (raising with the SQL) | ✓ VERIFIED | `test_commit_implicito_deja_pending_y_reconcile_lo_detecta` passes; `reconcile_migrations` raises `MigrationError` carrying `sql_text` |
| 7 | **SC2/DATA-02** With `transactional_ddl=True`, the same failure leaves no `pending` | ✓ VERIFIED | `test_ddl_transaccional_no_deja_pending` passes; `TRANSACTIONAL_DDL` map correct (sqlite/pg/mssql True; mysql/mariadb/oracle False) |
| 8 | **SC2/DATA-02** The six adapters' `migrate()` ensure the ledger, reconcile first, and delegate to `_apply`; `PoolDb` delegates too | ✓ VERIFIED | `migrate()` in sqlite/mysql/postgresql/mssql/oracle + `pool.py:306`; MariaDB inherits MySQL; `test_reconcile_migrations_on_pool_ensures_ledger` passes |
| 9 | **SC2/DATA-02** Pre-DDL compensation only deletes the row THIS call inserted (identity), preserving another runner's row | ✓ VERIFIED | `migration.py:116-135` (`inserted` + `{id: ledger_id}`, compare-and-delete fallback); `test_insert_duplicado_no_borra_la_fila_ajena`, `test_wr01_compensacion_no_borra_la_fila_reinsertada` pass |
| 10 | **SC2/DATA-02** A failed compensation does not mask the root DDL error | ✓ VERIFIED | `migration.py:132-144`; `test_in01_compensacion_fallida_no_enmascara_el_error_raiz` passes |
| 11 | **SC2/DATA-02** `resolve_migration` implements the four D-08/D-17 state transitions and documents the rollback re-issue | ✓ VERIFIED | `migration.py:234-264`; four tests + `test_reconcile_error_text_instruye_reintentar_rollback` pass |
| 12 | **SC3/DATA-03** `CachedModel.update()` never leaves a stale cached row readable, incl. a write instance whose PK is unset (`id=None`) | ✓ VERIFIED | `cached.py:209-221`; `test_cr01_update_without_instance_pk_invalidates_pk_entry` passes; independent repro: PK entry gone, next `load()` returns NEW value |
| 13 | **SC3/DATA-03** `CachedModel.delete()` (logical and physical) never leaves a stale cached row readable, incl. `id=None` | ✓ VERIFIED | `cached.py:223-234`; `test_cr01_delete_without_instance_pk_invalidates_pk_entry` passes; independent repro: PK entry gone |
| 14 | **SC3/DATA-03** `CachedModel.upsert(conflict=[...])` never leaves a stale cached row readable, incl. `id=None` | ✓ VERIFIED | `cached.py:236-248`; `test_cr01_upsert_without_instance_pk_invalidates_pk_entry` passes; independent repro (incl. `datetime` conflict key): PK entry gone, `load()` fresh |
| 15 | **SC3/DATA-03** Invalidation covers ALL rows a non-unique non-PK write key affects (multi-row) | ✓ VERIFIED | `cached.py:94-104` (`search` multi-row) + `_invalidate_pks`; `test_cr01_multifila_invalida_todas_las_pks` passes; independent repro: both T1 rows invalidated |
| 16 | **SC3/DATA-03** The invalidation probe binds the SERIALIZED write value, so `datetime`/`Decimal`/JSON keys invalidate (CR-R4-01) | ✓ VERIFIED | `cached.py:92` `Filter.eq(k, _serialize(getattr(self, k)))`; `test_cr_r4_01_clave_serializada_invalida_entrada` passes; independent repro: `datetime` and `Decimal` keys invalidate, `load()` fresh |
| 17 | **SC3/DATA-03** The cache key is namespaced by the active `scope()`; a hit never serves another tenant (CR-02) | ✓ VERIFIED | `cached.py:33-35`; `test_cr02_scope_no_aislado_no_sirve_otro_tenant`, `test_cr02_mismo_scope_si_acierta`, `test_cr02_clave_depende_del_scope` pass |
| 18 | **SC3/DATA-03** Invalidation is fail-open: a cache/union failure never fails a committed write | ✓ VERIFIED | `cached.py:43-52`, `137-169`; `test_invalidate_fail_open`, `test_wr_r3_02_union_no_rompe_fail_open` pass; `_invalidate_pks` skips non-dict entries (`:164`) |
| 19 | **SC3/DATA-03** `insert_many(cache=...)` invalidates the PK key; without `cache=` it does not; plain `insert` does not invalidate | ✓ VERIFIED | `cached.py:250-276`; `test_insert_many_invalidates`, `test_insert_many_without_cache_does_not_invalidate` pass |
| 20 | **SC4/DATA-04** `MemoryCacheBackend` is bounded by LRU (`max_size=1024` default) and documented dev/test-only | ✓ VERIFIED | `cache_backend.py:12-46` (`OrderedDict`, `move_to_end`, `popitem(last=False)`); `test_lru_evicts_least_recently_used`, `test_max_size_is_respected`, `test_default_max_size_is_1024` pass; independent repro: 5 sets → 3 entries |
| 21 | **SEC-01** `Model.update` applies the active `scope()` to the DML WHERE (non-PK keys cannot modify another tenant's rows) | ✓ VERIFIED | `model.py:743-755` `_scoped_dml`; `test_cr_r3_01_update_no_cruza_tenant` passes; independent repro: T2 row unchanged |
| 22 | **SEC-01** `Model.delete` (logical AND physical) applies the active `scope()` to the DML | ✓ VERIFIED | `model.py:772-784`; `test_cr_r3_01_delete_no_cruza_tenant`, `test_cr_r3_01_delete_fisico_no_cruza_tenant` pass; independent repro: T2 row survives both |
| 23 | **SEC-01** Without an active `scope()` the DML is byte-identical to before (no regression) | ✓ VERIFIED | `_scoped_dml` only reached when `current_scope() is not None` (`model.py:747-749`, `:775-783`); `test_cr_r3_01_sin_scope_sigue_sin_acotar` passes; independent repro: 2 rows updated |
| 24 | **SEC-01** The scope predicate is bound (never interpolated) and placeholder-contiguous | ✓ VERIFIED | `_scoped_dml` (`model.py:115-131`) shifts `{n}` by `len(qry.fields)`; `Query` cardinality contract revalidates; code review R4 confirmed builder/param contiguity |
| 25 | **Cross-cutting** The runner never calls `db.commit()`; works with a direct adapter and `PoolDb` | ✓ VERIFIED | `grep "db.commit()" encino_orm/migration.py` = 0; pool reconcile test passes |
| 26 | **Cross-cutting** No unresolved debt markers in phase-modified modules | ✓ VERIFIED | `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` grep over migration.py, cached.py, cache_backend.py, model.py, pool.py = none |

**Score:** 5/5 must-haves verified (SC1/DATA-01, SC2/DATA-02, SC3/DATA-03, SC4/DATA-04, SEC-01); 26/26
granular truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/migration.py` | ledger constants, corrected `rollback_migration`, two-phase `_apply`, `reconcile_migrations`, `resolve_migration` | ✓ VERIFIED | All present; `:down`=0, `db.commit()`=0; identity-based compensation + documented fallback |
| `encino_orm/model/cached.py` | canonical PK cache domain, scope-namespaced key, multi-row serialized probe, fail-open invalidation | ✓ VERIFIED | `_serialize` probe at `:92`; `_union` hashable at `:130`; `_invalidate_after_write`/`_invalidate_pks` fail-open |
| `encino_orm/model/cache_backend.py` | bounded LRU + dev/test-only docstring | ✓ VERIFIED | `max_size=1024`, `popitem(last=False)`, docstring `:13-19` |
| `encino_orm/model/model.py` | `_scoped_dml` on update/delete; `insert_many(cache=)` parity | ✓ VERIFIED | `:115-131`, `:743-784` |
| `encino_orm/base.py` / `pool.py` | `Db.transactional_ddl=True`; `PoolDb.transactional_ddl` property + ledger delegation | ✓ VERIFIED | base.py:24; pool.py:92-98, 226-228 |
| `encino_orm/dialects/strategies.py` | `TRANSACTIONAL_DDL` six-engine map | ✓ VERIFIED | `:75-82` |
| sqlite/postgresql/mysql/mariadb/mssql/oracle adapters | ledger `status` DDL + idempotent `_ensure_status_column` + two-phase `migrate()` | ✓ VERIFIED | All six present; correct per-dialect types |
| `tests/test_cached_model.py` | invalidation, CR-01/CR-02, multi-row, serialized key, fail-open regressions | ✓ VERIFIED | 22 tests pass, incl. `test_cr_r4_01_...` |
| `tests/test_migrations.py` / `test_migration_reconcile.py` / `test_cache_backend.py` / `test_scope_softdelete.py` / `test_dialect_ddl.py` | phase regressions | ✓ VERIFIED | 64 tests pass |
| `docs/guide.md` / `docs/design/5-security.md` / `CHANGELOG.md` | dev/test contract, scope/upsert/TOCTOU/multi-process residuals | ✓ VERIFIED | §10 `guide.md:499-560`; `5-security.md:205-247`; CHANGELOG entries truthful |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `migration.py::rollback_migration` | `Db.transaction()` | `async with db.transaction()` | ✓ WIRED | present |
| adapters `::migrate` | `reconcile_migrations` + `_apply` | module import | ✓ WIRED | 5 adapters; MariaDB inherits MySQL |
| `migration.py::_apply` | `Db.transactional_ddl` | runtime read | ✓ WIRED | migration.py:116, 136 |
| `pool.py::transactional_ddl` | `self._template.transactional_ddl` | property | ✓ WIRED | pool.py:92-98 |
| `cached.py::update`/`delete`/`upsert` | `CacheBackend.delete` | `_resolve_pk_values` → `_invalidate_after_write` → `_invalidate_pks` | ✓ WIRED | Works for PK and non-PK write keys, multi-row, scope-aware, serialized |
| `cached.py::_cache_key_for` | `current_scope().digest()` | key namespacing | ✓ WIRED | cached.py:33-35 |
| `model.py::update`/`delete` | `_scoped_dml` | scope read inside retried closure | ✓ WIRED | model.py:747-749, 775-783 |
| `cache_backend.py::set` | `OrderedDict.popitem(last=False)` | LRU eviction | ✓ WIRED | cache_backend.py:42-43 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `CachedModel.load` | `raw` (cache bytes) | `cache.get(self._cache_key_for(pk, pk_values))` | Yes | ✓ FLOWING — canonical PK domain; non-PK reads query DB then recache under PK |
| `CachedModel._resolve_pk_values` | probe rows | `self.search(filter=serialized keys, scope-aware, include_deleted=True)` | Real DB rows | ✓ FLOWING — serialized value matches the DML bind (CR-R4-01) |
| `CachedModel._invalidate_pks` | delete key | `_cache_key_for(pk_keys, values)` from the resolved row | Real affected-row PKs | ✓ FLOWING |
| `MemoryCacheBackend` | `_store` | in-process OrderedDict | Real entries; LRU-bounded | ✓ FLOWING |
| ledger `status` | `status` column | `_apply` inserts `pending`, promotes `applied` | Real DB writes via bound params | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase suites | `uv run pytest tests/test_migrations.py tests/test_migration_reconcile.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_dialect_ddl.py tests/test_scope_softdelete.py -q` | 86 passed | ✓ PASS |
| Full suite | `uv run pytest -q` | 847 passed (10 snapshots) | ✓ PASS |
| Gates | `ruff check` / `ruff format --check` / `mypy encino_orm` | all clean (115 formatted, 60 source files) | ✓ PASS |
| Independent repro (17 checks) | real `SqliteDb`: DATA-01/02/03/04 + SEC-01 + CR-R4-01 | 17/17 PASS | ✓ PASS |
| Independent repro (scope) | real `SqliteDb`: multi-row invalidation under scope; writer/reader scope residual | 7/7 PASS (residual confirmed & documented) | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| — | — | No `scripts/*/tests/probe-*.sh` exist; the phase declares no probes | SKIPPED (N/A) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| DATA-01 | 03-01 | `rollback_migration` ledger corrected; re-applying after rollback works | ✓ SATISFIED | Truths 1–3; `test_reapply_after_rollback`, `test_rollback_ledger_deletes_row_and_inserts_no_down`; independent repro |
| DATA-02 | 03-01, 03-02, 03-07, 03-09 | `migrate()` atomic or records intent + reconciles at startup | ✓ SATISFIED | Truths 4–11; `TRANSACTIONAL_DDL`; identity compensation; reconcile; 86 targeted + 847 full tests |
| DATA-03 | 03-03, 03-06, 03-08, 03-12, ec47f3a | `CachedModel` invalidates cache on `update`/`delete` (store-then-invalidate), no stale reads | ✓ SATISFIED | Truths 12–19; canonical PK domain, multi-row, serialized probe, scope namespace, fail-open; independent repro |
| DATA-04 | 03-05, 03-04 | `MemoryCacheBackend` bounded or documented dev/test-only | ✓ SATISFIED | Truths 20; LRU + docstring + guide §10 |
| SEC-01 | 03-11, 03-13 | `Model.update`/`delete` apply the active `scope()` to the DML (no cross-tenant writes with non-PK keys) | ✓ SATISFIED | Truths 21–24; `_scoped_dml`; RED→GREEN tests; independent repro |

**Orphaned requirements:** none. All five IDs are claimed by plans and marked Complete in
`REQUIREMENTS.md`; implementation evidence confirms them.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `tests/test_cached_model.py` | 487-488, 513-514 | Stale "HOY lanza TypeError / liga la list cruda" RED docstrings in now-GREEN tests (IN-R4-01) | ℹ️ INFO | Misleading comment only; no behavior impact |
| `encino_orm/model/cached.py` | 143-149 | `_invalidate_after_write` fallback branch (`except`) is not exercised by any test (IN-R4-02) | ℹ️ INFO | Coverage gap on the fail-open fallback; the `repr` path is tested |
| — | — | `TBD`/`FIXME`/`XXX` debt markers in phase files | ✓ none | grep over the modified modules returned none |

No BLOCKER or WARNING-severity anti-patterns remain. The two INFO items are test-hygiene notes, not
correctness defects.

### Documented Residuals (assessed — none violates a success criterion or requirement)

| Residual | Status | Assessment |
| -------- | ------ | ---------- |
| **WR-02 probe/write TOCTOU** | Documented | Narrowed by unioning pre- and post-write probes; not eliminated. Documented in `guide.md:548-554` and `5-security.md:222-225`. Does **not** violate SC3 (canonical store-then-invalidate holds; requires a 3-transaction interleaving). |
| **`upsert` conflict keys are global (not scope-bounded)** | Documented | `upsert` is outside SEC-01's literal text (`Model.update`/`delete`). Documented in `guide.md:541-546`, `5-security.md:241-244`, with the `(tenant, clave)` mitigation. ⚠️ WARNING: a genuine cross-tenant vector under `scope()` remains for `upsert`, but it is a known, documented limitation with an explicit schema-level mitigation and is owned as a residual — not a SC violation. |
| **Oracle migration-ledger `last_id()` fallback** | Corrected | `STATE.md:168` and `CHANGELOG.md:158-161` now state the fallback covers a failed/unusable `last_id()` (Oracle exposes it via `RETURNING id INTO`), not Oracle specifically. Residual assigned to Phase 4 / `04-02` / POOL-03. |
| **Multi-process cache invalidation unsupported** | Documented | `guide.md:556-560`, `CHANGELOG.md:128-131`. Invalidation is process-local; stale entries bounded by TTL. Does not violate SC4 (backend bounded/documented). |
| **Writer/reader must share the same `scope()`** | Documented | `guide.md:532-539`, `5-security.md:228-234`. Independently reproduced: an unscoped write leaves a scoped entry stale. Explicitly documented; not a SC violation. |

### Human Verification (informational — environment-limited, non-blocking)

The three items below were carried over from the prior verification. They require live
MySQL/MariaDB/Oracle servers not available in this environment. The automated suite models implicit
commit faithfully with a published-snapshot fake `Db`, and the code paths are verified by construction
plus real-SQLite reproduction. They are recorded as informational and do not change the verdict.

1. **Real implicit-commit DDL ambiguity (MySQL/MariaDB/Oracle)** — kill the process between the DDL and
   the promote, then call `reconcile_migrations(db)`; expect a `pending` detection raising
   `MigrationError` with the SQL, never auto re-run.
2. **Idempotent `ALTER TABLE ADD status`** — run the ledger bootstrap twice against a real
   MySQL/MariaDB ledger created without `status`; expect no failure.
3. **Multi-process cache limitation accuracy** — confirm `docs/guide.md` §10 matches the deployment
   topology (no pub/sub; stale bounded by TTL).

### Gaps Summary

No gaps. All five must-haves are verified against the actual codebase at HEAD `ec47f3a`, with
independent reproduction on real `SqliteDb` for every data-correctness and security claim:

- **DATA-01 / SC1** — rollback deletes the row (never writes `{name}:down`) and re-application
  succeeds; verified by code, tests, and independent repro.
- **DATA-02 / SC2** — two-phase `pending`→DDL→`applied` with per-dialect `TRANSACTIONAL_DDL`,
  identity-based pre-DDL compensation (with documented fallback), and `reconcile_migrations` at
  startup; the four `resolve_migration` transitions and the rollback re-issue are documented.
- **DATA-03 / SC3** — the cache domain is canonical (PK), invalidation is multi-row, scope-namespaced,
  serialized (CR-R4-01), post-commit, and fail-open. The canonical `id=None` cross-key write paths
  (update/upsert/delete) and `datetime`/`Decimal`/JSON write keys all invalidate correctly.
- **DATA-04 / SC4** — `MemoryCacheBackend` is LRU-bounded and documented dev/test-only.
- **SEC-01** — `Model.update`/`delete` (logical and physical) append the active `scope()` as bound
  parameters to the DML; without a scope the DML is unchanged. RED→GREEN tests and independent repro.

The only remaining items are documented residuals (TOCTOU, `upsert` scope, multi-process cache,
writer/reader scope) and two INFO-level test-hygiene notes. None is a BLOCKER; none contradicts a
success criterion or requirement. The phase may proceed to Phase 4.

---

_Verified: 2026-09-18T23:30:00Z_
_Verifier: the agent (gsd-verifier)_
