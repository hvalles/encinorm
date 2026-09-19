---
phase: 05-resilience
reviewed: 2026-09-19T05:47:27Z
depth: deep
files_reviewed: 11
files_reviewed_list:
  - encino_orm/base.py
  - encino_orm/exceptions.py
  - encino_orm/mssql.py
  - encino_orm/mysql.py
  - encino_orm/oracle.py
  - encino_orm/http/errors.py
  - tests/_resilience_helpers.py
  - tests/test_base.py
  - tests/test_resilience.py
  - tests/test_mssql.py
  - CHANGELOG.md
  - docs/engines.md
findings:
  critical: 0
  warning: 1
  info: 3
  total: 4
status: issues_found
---

# Phase 05: Code Review Report — R2 (fix commit `4fb4ccb`)

**Reviewed:** 2026-09-19T05:47:27Z
**Depth:** deep
**Files Reviewed:** 11 (fix commit scope + files needed to verify call chains)
**Status:** issues_found
**Scope:** `git diff 4fb4ccb^ 4fb4ccb` (HEAD = `4fb4ccb`).
**Verification run:** `uv run pytest -q` → **1023 passed** (10 snapshots); `uv run ruff check encino_orm tests` → clean; `uv run ruff format --check encino_orm tests` → clean; `uv run mypy encino_orm` → clean. No source files modified by this review.

## Summary

The blocker is genuinely fixed and the four targeted MSSQL/taxonomy warnings are closed. `_maybe_recycle` now guards on `in_transaction()` before touching the connection, and I reproduced the original silent-data-loss scenario on real SQLite: `['uno', 'dos']` (previously `['dos']`). The MSSQL classifier now handles the **real** `pyodbc.Error.args == (sqlstate, str)` shape (native code from the trailing `(NNNN)`), and `_MssqlExc` was updated to that shape; real-shape deadlock/lock (`1205`/`1222`/`40001`/`HYT00`) is lock-not-disconnect, and unique/FK/NOT NULL are `IntegrityError`. `_raise_translated` removes the self-referential `__cause__` and preserves the driver cause only when the instance changes.

One new defect is introduced by the WR-03 fix: MSSQL `is_lock_error` now treats **any** SQLSTATE `HYT00` as a lock. `HYT00` is the generic ODBC "Timeout expired" SQLSTATE (login timeout / query timeout), not only lock-timeout 1222. Because `_translate_exception` short-circuits lock errors, a raw `pyodbc.Error` with `HYT00` escapes untranslated — reproduced through the `_maybe_recycle` path — which partially reopens WR-01 and violates RESL-04.

**Verdict: CR-01 CLOSED. WR-01 and WR-06 PARTIAL; all other findings CLOSED. 1 new WARNING + 3 new INFO. Fix N-01 before declaring WR-01/RESL-04 fully closed.**

## Per-Finding Closure

| ID | Status | Evidence |
|----|--------|----------|
| **CR-01** | **CLOSED** | Guard at `encino_orm/base.py:299-300` runs before `_should_recycle`/`pre_ping`. Real-SQLite repro now yields `['uno','dos']`. New tests `test_lifetime_no_recicla_dentro_de_transaccion` / `test_pre_ping_no_reconecta_dentro_de_transaccion` fail on `4fb4ccb^` and pass on `4fb4ccb` (`connects==1, closes==0, is_alive_calls==0`). No path reconnects/commits inside an open tx: the reactive path already guarded at `base.py:369-370`, and `MssqlDb.is_alive()` no longer commits (WR-07). Normal recycling outside tx is unaffected (lifetime/pre_ping tests pass). |
| **WR-01** | **PARTIAL** | `base.py:360-363` wraps `_maybe_recycle` and routes failures through `_raise_translated`; the new test asserts `ConnectionLostError` with the pymysql driver as `__cause__`. Exactly-once preserved (no second `_reconnect` on the failed-proactive path). **But** MSSQL `HYT00` failures are classified as lock and escape raw (see N-01), and a failed `_reconnect` leaves `_connected_at=None`, so no later auto-recovery is attempted (residual secondary effect from the original finding). |
| **WR-02** | **CLOSED** | `mssql.py:155-157`: whole `23000` class → `IntegrityError`. `mssql_fk_violation` (547) and `mssql_not_null` (515) added to `_TRANSLATE_CASES` and pass; they failed on `4fb4ccb^`. |
| **WR-03** | **CLOSED** | `_sqlstate`/`_message`/`_native_code` handle `(sqlstate, str)`; native code extracted from trailing `(NNNN)` (`mssql.py:88-102`). `_MssqlExc` updated to the real shape. Verified real-shape: deadlock `40001/1205` and lock timeout `HYT00/1222` → lock, not disconnect; `23000/2627/547/515` → `IntegrityError`; `08S01`/`HY000`-kill → `ConnectionLostError`. The original `mssql_integrity` test also fails on `4fb4ccb^`, confirming the old shape masked the bug. Caveat: the `HYT00` fallback is over-broad (N-01). |
| **WR-04** | **CLOSED** | `CHANGELOG.md` now states "**REEMPLAZO, no solo aditivo**" and `docs/engines.md:177-181` documents the replacement + `__cause__`. |
| **WR-05** | **CLOSED** | `OperationalError(EncinoOrmError)` (`exceptions.py:17`); no caller/test relied on the old `QueryError` base (grep: only `test_base.py` updated). `http/errors.py` only registers `QueryError` → `OperationalError` falls to the generic 500; docs/CHANGELOG updated. |
| **WR-06** | **PARTIAL** | Oracle list extended with `12570/12571/12170/1034` (`oracle.py:30-45`); MySQL now treats raw `ConnectionResetError`/`BrokenPipeError` as disconnect (`mysql.py:94-97`). **Remaining:** MSSQL `HY000` mid-query detection still depends on English message markers (`mssql.py:135-144`); the localized-message sub-item of WR-06 is unaddressed. |
| **WR-07** | **CLOSED** | `MssqlDb.is_alive()` no longer commits (`mssql.py:202-221`). Pool safety verified: `PoolDb.release()` (`pool.py:324-331`), `_run` success/except (`pool.py:471-484`) and `session()` (`pool.py:596-606`) roll back/commit leftover state, so the probe's implicit transaction is cleaned by the owner path. No other adapter `is_alive()` commits. |
| **IN-01** | **CLOSED** | `_DB_CON_TEMPLATE` removed; public overrides call `super()` unconditionally (`tests/_resilience_helpers.py:439-454`). No remaining references. |
| **IN-02** | **CLOSED** | `_with_reconnect(..., *, is_read)` renamed; all production call sites use `is_read=`. One stale test override remains (N-02). |
| **IN-03** | **CLOSED** | `_resilience_opts` validates `lifetime` before assigning `pre_ping`/`max_connection_lifetime` (`base.py:249-261`). |
| **IN-04** | **CLOSED** | `_raise_translated` (`base.py:307-317`). Verified: lock path re-raises the same instance with `__cause__ is None`; translated path chains the driver and is not self-referential. |

### Test quality (RED→GREEN)

Genuine. Applying only the test changes onto the pre-fix source produces **12 failures** (`105 passed`), including the CR-01 tests, the WR-01 translation test, the WR-02 FK/NOT NULL cases, the real-shape MSSQL lock/unique cases and the WR-05 hierarchy assertion. Tests remain deterministic (hand doubles, no `sleep`/network/`unittest.mock`).

## New Findings

### N-01 (WARNING): MSSQL `HYT00` is treated as a lock → raw driver exception escapes

**File:** `encino_orm/mssql.py:104-109` (line 109), reachable via `encino_orm/base.py:360-363` and `base.py:367-368`.

**Issue:** `is_lock_error` returns `True` for any SQLSTATE `HYT00`. `HYT00` is the generic ODBC *Timeout expired* SQLSTATE used for **login timeouts and query timeouts**, not only lock timeout 1222 (which already carries native code 1222 and is caught by the first branch). Because `_translate_exception` short-circuits lock errors by returning the same instance, a `pyodbc.Error` with `HYT00` escapes the adapter untranslated and `retry()` retries a non-lock timeout up to `MAX_TRIES`. This is a regression: on `4fb4ccb^`, `HYT00` fell through to `_translate_error` → `OperationalError`.

**Repro (run, confirmed):**

```python
# real pyodbc shape
e = PyodbcLike("HYT00", "[HYT00] Login timeout expired")
db._translate_exception(e) is e        # True -> raw driver exception escapes
# through _maybe_recycle's reconnect-failure path:
await db.fetch_one(Query("SELECT 1", []))  # raises PyodbcLike, untranslated
```

Also affects the normal `fn()` path: a query timeout (`HYT00`) is not reconnectable (`is_disconnect_error` returns `False` because `is_lock_error` is checked first) and is re-raised raw. Violates RESL-04 and reopens part of WR-01.

**Fix:** require the lock-timeout signal for `HYT00`, don't treat the bare SQLSTATE as lock:

```python
def is_lock_error(self, exc: Exception) -> bool:
    if self._native_code(exc) in (1205, 1222):
        return True
    if self._sqlstate(exc) == "40001":      # serialization failure / deadlock victim
        return True
    if self._sqlstate(exc) == "HYT00":      # only lock-wait timeout, not login/query timeout
        return "lock" in self._message(exc).lower()
    return False
```

**Coverage:** add a `HYT00` case with **no** trailing native code (login/query timeout) asserting it is not lock, is translated to `OperationalError`/`ConnectionLostError`, and does not escape raw. `tests/test_mssql.py:114` only covers the synthetic `(HYT00, (1222, ...))` shape, so it cannot catch this.

### N-02 (INFO): stale `retry=` override in a test double

**File:** `tests/test_resilience.py:400-402`

**Issue:** `_PoolEspia._with_reconnect(self, fn, *, retry)` still uses the pre-IN-02 keyword and calls `super()._with_reconnect(fn, retry=retry)`. The body is never executed today (`PoolDb.execute` goes through `_run`, not `_with_reconnect`), so the suite passes, but if `PoolDb` ever routes through `_with_reconnect` the call raises `TypeError: unexpected keyword argument 'retry'`.

**Fix:** rename to `is_read` (and pass `is_read=is_read`) or drop the override in favour of asserting `_with_reconnect` is never called.

### N-03 (INFO): `test_mssql.py` still asserts the synthetic `args` shape

**File:** `tests/test_mssql.py:93-115`

**Issue:** These tests build `args = (sqlstate, (code, msg))`, the shape the review proved the real driver never produces. They now exercise the compatibility branch only, and the real shape is covered solely through `_resilience_helpers._MssqlExc`. Not a bug (the synthetic branch is intentionally supported), but the unit tests for `is_unique_violation`/`is_lock_error` give a false sense of driver fidelity.

**Fix:** switch these to the real `(sqlstate, f"{msg} ({code})")` shape, or add a comment that the synthetic branch is compatibility-only.

### N-04 (INFO): direct MSSQL `_in_tx` suppresses proactive recycling

**File:** `encino_orm/mssql.py:357,390,412,427,447`; guard at `encino_orm/base.py:299-300`

**Issue:** `MssqlDb` sets `_in_tx = True` after **every** statement (including reads), and `commit()`/`rollback()` are the only resets. A direct (non-pool) `MssqlDb` used with raw `execute`/`fetch_*` outside an explicit transaction therefore reports `in_transaction() == True` after its first call, so the CR-01 guard makes `pre_ping`/`max_connection_lifetime` a no-op until the user commits. The guard is conservative and correct (the driver really is in an implicit transaction), but RESL-03's opt-in recycling is silently ineffective in this usage; the docs/CHANGELOG do not mention it. Oracle is affected only after a write (its `_fetch_*` do not set `_in_tx`).

**Fix:** document the caveat (or reset/commit the implicit transaction in the direct-connection lifecycle), so `max_connection_lifetime` is not assumed to fire on every operation.

## Verification Notes

- The pre-existing repo-wide `ruff format --check .` reports 45 files to reformat, but CI scopes the check to `encino_orm tests` (`ci.yml:180`), which is clean; the 45 files are identical at `4fb4ccb^` (pre-existing, out of scope).
- `_with_reconnect`'s bare `raise` inside `_raise_translated` correctly re-raises the active exception (verified for the lock path); all call sites are inside `except` blocks.
- CR-01 guard's `in_transaction()` is local state in every adapter (`sqlite`/`mysql`/`postgresql` driver property, `mssql`/`oracle` `_in_tx`), so it adds no I/O and cannot itself raise on a dead connection.

---

_Reviewed: 2026-09-19T05:47:27Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
