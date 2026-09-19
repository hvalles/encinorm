---
phase: 04-pool-correctness-concurrency
verified: 2026-09-19T03:58:56Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 8/9
  gaps_closed:
    - "`_size <= max_size` holds across every supported pool lifecycle, including `close()` followed by `connect()` while a caller still holds connections (POOL-02 'admission never exceeds max_size')."
  gaps_remaining: []
  regressions: []
deferred: []
---

# Phase 4: Pool Correctness & Concurrency Verification Report

**Phase Goal:** `PoolDb` is correct under concurrency. Per-connection state lives on a per-connection handle, admission never exceeds `max_size`, `last_id` belongs to the insert that produced it, and release semantics are explicit instead of accidental.
**Verified:** 2026-09-19T03:58:56Z (HEAD `3465a49`)
**Status:** passed
**Re-verification:** Yes — after gap closure (previous: `gaps_found`, 8/9)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 — Under 5 concurrent tasks on a pool of max size 2, live connections never exceed 2 and no `acquire()` fails spuriously | ✓ VERIFIED | `acquire()` reserves `_size` before the `await` and returns the slot on `BaseException` (`pool.py:259-271`). `tests/test_pool_concurrency.py::test_no_overshoot_under_barrier` asserts `_size <= max_size`, `_size == max_size`, peak `_checked_out <= max_size`, handles reused; 5/5 tasks succeed. Stress `test_no_overshoot_repeated` passes `--count=3`. |
| 2 | SC2 — Concurrent pooled inserts each return their own id (no cross-talk); post-hoc `last_id()` emits `DeprecationWarning` | ✓ VERIFIED | `tests/test_pool_concurrency.py::test_concurrent_insert_ids_no_crosstalk` (SQLite file pool, 5 concurrent → ids 1..5, name→id mapping re-checked against rows). Independent live probe: MySQL/PG/MSSQL/Oracle each returned 5 distinct ids with a correct mapping and emitted `DeprecationWarning` from `last_id()`. `PoolDb.last_id()` calls `_warn_last_id_deprecated()` (`pool.py:550`). |
| 3 | SC3 — Release with an open transaction rolls back by default; `reset_on_release="commit"` restores old behavior; standalone `pool.execute(INSERT)` still commits | ✓ VERIFIED | `release()` rolls back unless policy is `"commit"` (`pool.py:319-326`); `"commit"` warns at construction (`pool.py:118-127`); invalid value raises (`pool.py:98-102`). `_run` commits on success / rolls back on error (`pool.py:458-482`). Tests: `test_release_rolls_back_leftover_transaction`, `TestPoolResetOnRelease::test_release_with_reset_on_release_commit_commits`, `TestPoolStandaloneCommit::test_standalone_operation_commits`, `test_standalone_commit_visible_across_connections`. |
| 4 | SC4 — `close()` is idempotent and never closes a connection currently held by a caller | ✓ VERIFIED | `close()` early-returns when `_closed`, drains only `_idle`, keeps `_checked_out` alive; held handles close on release (`pool.py:352-378`, `335-341`). Tests: `TestPoolCloseIdempotent::test_close_closes_idle_only`, `test_release_after_close_closes_driver`, `test_stale_generation_handle_is_closed_on_release`, characterization `test_close_is_idempotent`, `test_close_does_not_close_held_connection`. |
| 5 | SC5 — Idle connections above `min_size` are closed by the lazy reaper; deterministic Python-3.10-compatible concurrency/stress tests pass under `pytest-timeout` | ✓ VERIFIED | `_reap()` invoked on `acquire()` and `release()`, no daemon, bounded by `min_size`, disabled by `idle_timeout=None` (`pool.py:204-247`). `TestPoolReaper` (4 tests) green. `test_pool_concurrency.py` uses only `asyncio.Event` (no 3.11 primitives), `@pytest.mark.timeout(10/20)`, marker `stress` + `pytest-repeat`; `pytest-timeout==2.4.0`/`pytest-repeat==0.9.4` pinned, `timeout=0` global, `--timeout-method=signal` in CI. |
| 6 | POOL-03 — id captured inside the statement on all six engines (incl. renamed physical PK and ignored inserts) | ✓ VERIFIED | `sqlite.py:184-207` (`lastrowid`, `rowcount==0 → None`), `mysql.py:204-226` (rowcount guard), `postgresql.py:205+` (`RETURNING`), `mssql.py:265+` (`OUTPUT INSERTED`), `oracle.py:270+` (`RETURNING INTO`). `Model.insert` uses the physical column `self._col("id")` (`model.py:542`, CR-01 fix). Live probe across SQLite/MySQL/PG/MSSQL/Oracle: 5 concurrent inserts → unique ids + correct mapping. |
| 7 | POOL-03 — Oracle `Model.insert(replace=True)` is executable (ORA-38104 `SET` excludes `conflict_cols`) | ✓ VERIFIED | `builders.py:157-167` excludes conflict columns and fails closed on empty `update_cols`. Real Oracle run: `tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge` passes; snapshot regenerated. |
| 8 | POOL-02/WR-01 — task ownership enforced; child tasks cannot reuse a parent's transaction connection | ✓ VERIFIED | `release()` requires `handle.owner_task is current` (`pool.py:306-308`); `_owned_connection()` fails closed for inherited contextvars (`pool.py:433-449`), used by `_run`/`_run_scoped`. Tests `test_release_de_otra_tarea_no_libera`, `test_tarea_hija_no_comparte_la_conexion_del_padre`; live probe: child `pool.execute()` inside `transaction()` → `ConnectionError`. |
| 9 | POOL-02 — `_size <= max_size` holds across every supported lifecycle (incl. `close()` + `connect()` while holding connections) | ✓ VERIFIED | **Fixed in `3465a49`.** `connect()` now starts from `_size = len(self._checked_out)` and only creates `max(0, min_size - _size)` connections (`pool.py:183-193`). Re-verified live: (a) min_size=1/max_size=2, 2 held → reconnect `_size=2`, live=2, `_size <= max_size`; (b) retained=0 → creates `min_size`; (c) retained=1/min_size=2 → fills to 2; (d) generation increments and released stale handles close with `_size`/`_connections` returning to 0 (no leak). Regression test `tests/test_pool.py::test_reconectar_con_retenidas_no_supera_max_size` (true RED→GREEN: pre-fix repro showed `_size=3 > 2`). |

**Score:** 9/9 truths verified

### Deferred Items

None.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `encino_orm/pool.py` | `PooledConnection` handle, reserve-before-await `acquire`, ownership `release`, `reset_on_release`, lazy `_reap`, idempotent `close`, generation, bounded `connect()` | ✓ VERIFIED | 611 lines; all mechanisms present and wired; `connect()` now bounds bootstrap by retained handles. |
| `encino_orm/base.py` | `execute_insert`, `_last_id_value`, centralized `_warn_last_id_deprecated`, deprecated `last_id()` | ✓ VERIFIED | Lines 15-23, 112-170. |
| `encino_orm/query.py` | `returns_id`/`id_column` metadata excluded from `__eq__`/`__hash__` | ✓ VERIFIED | Present; snapshots confirm byte-identical SQL when `returning=None`. |
| `encino_orm/dialects/builders.py` | `build_insert(returning=)` opt-in + `check_identifier` + ORA-38104 fix | ✓ VERIFIED | Lines 90-173. |
| `encino_orm/model/model.py` | `Model.insert` captures id via `execute_insert`, physical PK column | ✓ VERIFIED | Lines 536-558. |
| `encino_orm/migration.py` | `_apply` captures `ledger_id` with `execute_insert` + fallback | ✓ VERIFIED | Lines 92-126. |
| `encino_orm/context.py` | `resolve_db()` unwraps `handle.driver` | ✓ VERIFIED | Lines 49-55. |
| `encino_orm/__init__.py` | `PooledConnection` re-exported | ✓ VERIFIED | Lines 35, 55. |
| `tests/test_pool.py`, `tests/test_pool_characterization.py`, `tests/test_pool_concurrency.py`, `tests/_pool_helpers.py` | Assert final behavior | ✓ VERIFIED | 82 pool tests pass (incl. new reconnect regression); concurrency tests assert `_size <= max_size`, own ids, standalone commit. |
| `pyproject.toml`, `.github/workflows/ci.yml` | timeout/repeat deps, `stress` marker, `timeout=0`, `--timeout-method=signal` | ✓ VERIFIED | Pins present; marker registered; signal in both CI jobs. |
| `CHANGELOG.md`, `docs/guide.md`, `docs/engines.md` | Document breaking changes / deprecations | ✓ VERIFIED | Entries for close/reaper, `reset_on_release`, `acquire()` return type, MSSQL single-column `replace=True` `ValueError`, ORA-38104, `last_id` deprecation. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `PoolDb.acquire` | `PoolDb._create_connection` | reserve `_size` before await, refund on `BaseException` | ✓ WIRED | `pool.py:259-271` |
| `PoolDb.connect` | `PoolDb._checked_out` | bootstrap bounded by retained handles (`_size = len(_checked_out)`) | ✓ WIRED | `pool.py:183-193` |
| `PoolDb.transaction` | `_current_connection` | sets handle, yields `handle.driver` | ✓ WIRED | `pool.py:385-394` |
| `PoolDb._run` | `_owned_connection` | owner check / fail-closed for child tasks | ✓ WIRED | `pool.py:456-461`, `438-454` |
| `PoolDb.release` | `_checked_out` + `_reset_on_release` | ownership dedupe + rollback/commit leftover | ✓ WIRED | `pool.py:306-326` |
| `PoolDb._run`/`execute` | `PoolDb.release` | commit on success / rollback on error before release | ✓ WIRED | `pool.py:458-482` |
| `PoolDb.acquire`/`release` | `PoolDb._reap` | lazy reaping on the acquire/release path | ✓ WIRED | `pool.py:254, 331` |
| `Model.insert` | `Db.execute_insert` | `returning=self._col("id")`, consumes id | ✓ WIRED | `model.py:542-548` |
| `resolve_db` | `_current_connection` | returns `conn.driver` for handles | ✓ WIRED | `context.py:49-55` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `PoolDb.execute_insert` | returned id | per-driver `lastrowid`/`RETURNING`/`OUTPUT`/`RETURNING INTO` on the same statement | Yes | ✓ FLOWING |
| `Model.insert` | `self.id` | `execute_insert(qry)` return; physical PK column requested | Yes (live probe on 5 engines) | ✓ FLOWING |
| `PoolDb._reap` | `_idle`/`_size` | queue drain + `is_idle_for(idle_timeout)` | Yes | ✓ FLOWING |
| `PoolDb.acquire`/`connect` | `_size` | reserved before `_create_connection`; bootstrap bounded by retained handles | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| New reconnect regression | `uv run pytest tests/test_pool.py -q -k reconectar` | 1 passed | ✓ PASS |
| Pool-focused suite | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py tests/test_pool_concurrency.py -q` | 82 passed | ✓ PASS |
| Full suite | `uv run pytest -q` | 910 passed, 10 snapshots | ✓ PASS |
| Real-engine suite (MSSQL+Oracle required) | `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle uv run pytest tests/test_mssql.py tests/test_oracle.py -q` | 50 passed | ✓ PASS |
| Stress variant | `uv run pytest tests/test_pool_concurrency.py -q -m stress --count=3` | 5 passed | ✓ PASS |
| Concurrent ids on real engines (independent probe) | `uv run python <probe>` | MySQL/PG/MSSQL/Oracle: unique ids, mapping OK, `DeprecationWarning` OK | ✓ PASS |
| Reconnect accounting probe (gap re-check) | `uv run python <probe>` (min_size=1/max_size=2, hold 2, close, connect) | `_size=2 <= max_size=2`, live=2; retained=0 creates `min_size`; retained=1/min_size=2 fills to 2; release returns `_size`/`_connections` to 0 | ✓ PASS |
| Lint / types | `uv run ruff check encino_orm tests`; `uv run mypy encino_orm` | All checks passed; Success 60 files | ✓ PASS |

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` exist and the phase declares no probes (it is a pool/library phase, not a migration/tooling phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| POOL-01 | 04-01 | `PooledConnection` handle consolidating per-connection state | ✓ SATISFIED | `pool.py:45-77`; `_last_id` removed from `PoolDb`; `last_id` field retained per requirement (unused for capture — Info). |
| POOL-02 | 04-01 | Race-free `acquire()`; never exceeds `max_size` | ✓ SATISFIED | Reserve-before-await + ownership + size validation + bounded `connect()` bootstrap (`3465a49`) verified; live reconnect probe and regression test pass. |
| POOL-03 | 04-02 | id captured inside the insert per connection/task; `last_id()` deprecated | ✓ SATISFIED | Six `execute_insert` impls, `returning` opt-in, `Model.insert` physical PK, ORA-38104 fix; live probe on 5 engines. |
| POOL-04 | 04-03 | `reset_on_release` policy with rollback default + warning + CHANGELOG | ✓ SATISFIED | `pool.py:95-127, 319-326`; tests + CHANGELOG entry. |
| POOL-05 | 04-04 | Generation counter + lazy reaper above `min_size`, no daemon | ✓ SATISFIED | `pool.py:204-247, 335-341, 365`; `TestPoolReaper` + stale-generation test. |
| POOL-06 | 04-04 | `close()` idempotent, never closes in-use connection | ✓ SATISFIED | `pool.py:352-378`; `TestPoolCloseIdempotent` + characterization inversion. |
| POOL-07 | 04-05, 04-06 | Deterministic 3.10-compatible concurrency/stress tests + `pytest-timeout` | ✓ SATISFIED | `tests/_pool_helpers.py`, `tests/test_pool_concurrency.py`; pins + marker + CI signal. |

**Orphaned requirements:** none — REQUIREMENTS.md maps only POOL-01…07 to Phase 4, and all are declared in plan frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX` markers in phase-modified sources | ℹ️ Info | Clean; debt-marker gate passes. |
| `encino_orm/pool.py` | 59 | `PooledConnection.last_id` is dead state (never read in production) | ℹ️ Info | Required by POOL-01's field list; no behavioral impact. |
| `encino_orm/pool.py` | 238-243 | `_reap()` `if self._closed` branch is effectively unreachable | ℹ️ Info | Harmless defense-in-depth (N-05); accounting consistent. |
| `encino_orm/pool.py` | 551 | `last_id()` bypasses `_owned_connection()` ownership check | ℹ️ Info | A child task can read the parent's deprecated id; no statement interleaving. |
| `encino_orm/pool.py` | 179-193 | Double `connect()` (without an intervening `close()`) still creates a duplicate batch of `min_size` connections; `_size` is reset to `len(_checked_out)` so the counter under-reports | ⚠️ WARNING | Pre-existing misuse (also broken before Phase 4, which over-counted instead). Not a success criterion (admission is `acquire()`); see residuals. |

### Re-verification Detail

The previous verification found exactly one gap (truth #9): the POOL-02 invariant `_size <= max_size` was violated by `close()` + `connect()` while connections were held, because `connect()` unconditionally bootstrapped `min_size` more connections.

Commit `3465a49` closes it:

```python
self._closed = False
self._size = len(self._checked_out)          # retained handles count toward the cap
to_create = max(0, self._min_size - self._size)
for _ in range(to_create):
    handle = await self._create_connection()
    self._connections.add(handle)
    self._size += 1
    await self._idle.put(handle)
```

Accounting was re-checked by reasoning and live probes:
- **Retained = max_size** → `to_create = 0`; `_size == max_size`, no new connections.
- **Retained = 0** (all released before `close()`) → `_size = 0`, creates `min_size` (unchanged behavior).
- **Retained = 1, min_size = 2** → creates 1, reaching `min_size`.
- **Generation** increments in `close()`; new handles carry the current generation, retained ones are stale and are closed (not re-queued) on release; `_size`/`_connections` return to 0 with no leak.
- Fresh (never-connected) `connect()` still bootstraps `min_size`.

The regression test `test_reconectar_con_retenidas_no_supera_max_size` is true RED→GREEN (pre-fix the same scenario produced `_size=3 > max_size=2`, reproduced independently in the previous round).

No regression: pool suite 82 passed, full suite 910 passed, ruff and mypy clean.

### Assessed Residuals (non-blocking)

- **Double `connect()`** (calling `connect()` twice without an intervening `close()`) still duplicates connections and now makes `_size` under-report (`len(_checked_out)` ignores the already-idle first batch). This misuse was already broken before Phase 4 (it over-counted instead); it is outside the phase's success criteria and has no test. A one-line hardening would use `len(self._connections)` instead of `len(self._checked_out)` (identical at reconnect time, since `close()` drains `_idle`, but also correct for double-connect), or guard `connect()` with `if self._connected: return`. Suggested for a future pool-quality pass, not a blocker.
- Child tasks are rejected fail-closed (`ConnectionError`) when reusing a pool transaction connection ✓.
- `PooledConnection.last_id` retained per POOL-01 but unused for capture ✓.
- `_reap()`'s `if self._closed` branch is defensive/unreachable (N-05) ✓.
- MSSQL single-data-column `replace=True` `ValueError` documented in `CHANGELOG.md` ✓.
- `encino_orm.pool` retained in the mypy ratchet with the 5-error residual and its cause documented ✓; no coverage floor for `pool.py` (documented decision) ✓.

### Human Verification Required

None. All must-haves are programmatically verified (unit/concurrency/stress tests plus independent live probes on real SQLite, MySQL, MariaDB, PostgreSQL, MSSQL and Oracle engines).

### Gaps Summary

The single gap from the previous verification is closed at HEAD `3465a49`, with a true RED→GREEN regression test and consistent `_size`/`_checked_out`/`_connections`/generation accounting across reconnect scenarios. All nine must-haves (the five ROADMAP success criteria plus the plan-level truths for POOL-01…07) are verified. No regressions and no remaining must-have gaps. The only residual is the pre-existing double-`connect()` misuse, documented above as a non-blocking suggestion.

---

_Verified: 2026-09-19T03:58:56Z_
_Verifier: the agent (gsd-verifier)_
