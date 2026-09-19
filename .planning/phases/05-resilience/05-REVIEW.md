---
phase: 05-resilience
reviewed: 2026-09-18T23:59:00Z
depth: deep
files_reviewed: 24
files_reviewed_list:
  - encino_orm/base.py
  - encino_orm/exceptions.py
  - encino_orm/__init__.py
  - encino_orm/sqlite.py
  - encino_orm/mysql.py
  - encino_orm/mariadb.py
  - encino_orm/postgresql.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - encino_orm/pool.py
  - encino_orm/http/errors.py
  - tests/_resilience_helpers.py
  - tests/test_resilience.py
  - tests/test_base.py
  - tests/test_index.py
  - tests/test_sqlite.py
  - tests/test_mysql.py
  - tests/test_mariadb.py
  - tests/test_postgresql.py
  - tests/test_mssql.py
  - tests/test_oracle.py
  - pyproject.toml
  - docs/engines.md
  - CHANGELOG.md
findings:
  critical: 1
  warning: 7
  info: 4
  total: 12
status: issues_found
---

# Phase 05: Code Review Report — Resilience (RESL-01…04)

**Reviewed:** 2026-09-18T23:59:00Z
**Depth:** deep
**Files Reviewed:** 24
**Status:** issues_found
**Scope:** `git diff e355389..HEAD` (commits `87ed441..a53a3af`). Full suite run: `1018 passed`, `ruff check`/`ruff format --check` clean, `mypy` clean on the eight core/adaptor modules (the removed ratchet entries are legitimately fixed).

## Summary

The phase delivers the four intended capabilities: per-engine `is_disconnect_error` (RESL-01), the `_with_reconnect` template with the A2 write policy (RESL-02), opt-in `pre_ping`/`max_connection_lifetime` (RESL-03) and an additive public taxonomy plus a single translation point (RESL-04). The core template method is well-designed and its tests are deterministic (hand doubles, no `sleep`, no `unittest.mock`). Mutual exclusion disconnect/lock holds for the synthetic cases and for the *real* `oracledb`/`pyodbc` disconnect shapes I reproduced locally.

However, the proactive recycling hook (`_maybe_recycle`) is invoked **before** the transaction guard and **outside** the translation `try`. This is a real integrity hole, not a theoretical one: I reproduced silent loss of a committed write in a SQLite transaction. Two further issues degrade classification/translation on SQL Server because the phase's MSSQL tests use an `args` shape that does not match the real `pyodbc` driver, so they assert behavior that the real driver will not produce.

**Verdict: request changes — one blocker (data-integrity / RESL-02 + RESL-03 violated), seven warnings.**

### Top 3 findings

1. **CR-01** — `_maybe_recycle()` reconnects while a transaction is open, silently discarding uncommitted work and breaking atomicity (RESL-02/03 incomplete).
2. **WR-01** — A proactive reconnect failure in `_maybe_recycle()` escapes **untranslated** (raw driver exception), violating the RESL-04 contract.
3. **WR-02/WR-03** — MSSQL classification/translation is validated against a synthetic `(sqlstate, (code, msg))` shape; real `pyodbc.Error.args` is `(sqlstate, str)`, so `_native_code` never matches and integrity violations become `ProgrammingError`.

---

## Critical Issues

### CR-01: `_maybe_recycle()` reconnects inside an open transaction — silent data loss / atomicity violation

**File:** `encino_orm/base.py:273-295` (hook called at `encino_orm/base.py:337`)

**Issue:** `_with_reconnect` runs `await self._maybe_recycle()` **before** the `try` and therefore before any `in_transaction()` check. `_maybe_recycle` itself has no transaction guard, so when `max_connection_lifetime` is exceeded or `pre_ping` sees a dead probe, it calls `_reconnect()` → `close()` + `connect()`. `close()` on an open transaction rolls it back; the subsequent `fn()` then executes on a **new** connection, outside the transaction. The `commit()` at the end of `Db.transaction()` commits only what ran after the recycle. This contradicts the phase's own stated contract ("reconecta una sola vez y **solo** cuando no hay transacción abierta", `REQUIREMENTS.md:58`) and threat `T-05-02-02`, and it is reachable with the opt-in options added by this very phase.

**Minimal reproduction (real SQLite, run and confirmed):**

```python
db = SqliteDb()
await db.connect(database=path, max_connection_lifetime=10)
async with db.transaction():
    await db.execute(Query("INSERT INTO t (v) VALUES ('uno')", []))
    db._connected_at -= 11                      # simulate lifetime expiry mid-tx
    await db.execute(Query("INSERT INTO t (v) VALUES ('dos')", []))
rows = await db.fetch_all(Query("SELECT v FROM t ORDER BY id", []))
# ACTUAL:   [{'v': 'dos'}]   <-- 'uno' silently lost
# EXPECTED: [{'v': 'uno'}, {'v': 'dos'}]
```

Also confirmed with the test double: `FakeResilientDb(tx=True)` + elapsed lifetime ⇒ `connects=2, closes=1`; `pre_ping=True` + `tx=True` ⇒ `is_alive_calls=1, connects=2`. The same path is reachable through `PoolDb` (pooled drivers run the same public wrappers), so pool transactions are affected too when the options are configured.

**Fix:** make the proactive recycle transaction-aware before touching the connection:

```python
async def _maybe_recycle(self) -> None:
    if self._connected_at is None:
        return
    # Un reciclado proactivo NUNCA puede tocar una transacción abierta:
    # cerrar la conexión la revertiría en silencio.
    if await self.in_transaction():
        return
    if self._should_recycle():
        await self._reconnect()
        return
    if self.pre_ping and not await self.is_alive():
        await self._reconnect()
```

Add a regression test asserting `connects == 0` when `tx=True` with an elapsed lifetime (currently no test covers the proactive path with `tx=True`).

---

## Warnings

### WR-01: Proactive reconnect failure escapes untranslated (RESL-04 violation)

**File:** `encino_orm/base.py:337` and `encino_orm/base.py:291-295`

**Issue:** `_maybe_recycle()` is called outside the `try`, so any exception it raises bypasses `_translate_exception`. If `_should_recycle()` or the `pre_ping` probe triggers `_reconnect()` and `connect()` fails (server down), the raw driver exception propagates to the caller. RESL-04 requires driver exceptions not to leave the adapter.

**Reproduction (run and confirmed):**

```python
db = FakeReconnectFalla(); await db.connect()
db.pre_ping = True; db.falla_connect = True; db._connected = False
await db.fetch_one(Query("SELECT 1", []))
# ACTUAL:   pymysql.err.OperationalError leaks untranslated
# EXPECTED: encino_orm.exceptions.ConnectionLostError (or OperationalError)
```

A secondary effect: `_reconnect()` runs `close()` first (setting `_connected_at = None`) and then a failing `connect()`, leaving the object permanently "never connected"; every later operation raises a plain library `ConnectionError` and will not attempt recovery.

**Fix:** move `_maybe_recycle()` inside the `try`, or wrap its body so failures route through `_translate_exception`. Since a failed proactive recycle is itself a disconnect, translating it to `ConnectionLostError` is consistent. E.g.:

```python
try:
    await self._maybe_recycle()
    return await fn()
except Exception as exc:
    ...
```

### WR-02: MSSQL `_translate_error` maps SQLSTATE `23000` (non-unique) to `ProgrammingError`

**File:** `encino_orm/mssql.py:135`

**Issue:** `is_unique_violation` only recognizes `23000` + native code 2601/2627. Every other integrity violation (FK 547, NOT NULL 515, CHECK) falls through to `sqlstate in (..., "23000")` → `ProgrammingError`. These are integrity errors and should be `IntegrityError`.

**Reproduction (run and confirmed):**

```python
db._translate_exception(_MssqlExc("23000", 547, "FK violation"))  # -> ProgrammingError (wrong)
db._translate_exception(_MssqlExc("23000", 515, "NOT NULL"))      # -> ProgrammingError (wrong)
```

**Fix:** treat the whole `23000` class as integrity; keep the unique/check distinction only for messaging:

```python
if sqlstate == "23000":
    return IntegrityError(str(exc))
if sqlstate in ("42000", "42S02", "42S22"):
    return ProgrammingError(str(exc))
```

### WR-03: MSSQL classification is tested against a shape the real driver never produces

**File:** `tests/_resilience_helpers.py:202-210`, `encino_orm/mssql.py:62-66`

**Issue:** `_MssqlExc` fabricates `args = (sqlstate, (code, message))`. The real `pyodbc.Error` (aioodbc re-raises it unchanged) has `args = (sqlstate, message_str)`. I reproduced a real error locally:

```
pyodbc.Error.args == ('08001', '[08001] [Microsoft][ODBC Driver 18 ...] ...')
int(e.args[1][0])  -> ValueError: invalid literal for int() with base 10: 'C'
```

Consequences on real SQL Server (masked by the synthetic tests): `_native_code` returns `None`; therefore `is_lock_error` is **always False**, `is_unique_violation` is **always False**, and `is_disconnect_error`'s `_native_code in (1205, 1222)` exclusion is a no-op. A real deadlock is classified as neither lock nor disconnect and is translated to `OperationalError`, so `retry()` no longer retries MSSQL deadlocks, and a real UNIQUE violation becomes `ProgrammingError`. `real_mssql_disconnect()` only exercises the `08xxx` path, so it does not catch any of this.

**Fix:** classify by SQLSTATE for the non-`08` cases (e.g. deadlock `40001` / message "(1205)", lock timeout `HYT00` / "(1222)") instead of relying on the `args[1]` tuple, or extract the native code from the trailing `(NNNN)` in the message string. Update `_MssqlExc` to use the real `(sqlstate, str)` shape and add a regression test.

### WR-04: Translation replaces driver exception types — "additive" taxonomy is only additive for library classes

**File:** `encino_orm/base.py:165-188`, `tests/test_index.py:174`

**Issue:** RESL-04's docs/CHANGELOG frame the taxonomy as additive, but `_with_reconnect` now *replaces* driver exceptions: `sqlite3.IntegrityError` becomes `encino_orm.exceptions.IntegrityError` (proven by the required edit of `test_index.py` from `sqlite3.IntegrityError` to the library class). Existing user code with `except sqlite3.IntegrityError:` / `except asyncpg.UniqueViolationError:` silently stops catching. `__cause__` preserves diagnosis but not `except` matching. This is a breaking change for a `0.x` release and should be called out explicitly as such, not folded under "aditiva".

**Fix:** state the replacement explicitly in `CHANGELOG.md`/`docs/engines.md` (it already has a behavior-change note for reconnection; the translation note leads with "taxonomía aditiva"). Optionally document that callers must catch the library types or inspect `__cause__`.

### WR-05: `OperationalError(QueryError)` maps infrastructure failures to HTTP 400

**File:** `encino_orm/exceptions.py:17-18`, `encino_orm/http/errors.py:20-22`

**Issue:** `_translate_error` defaults to `OperationalError` for any unrecognized driver failure (connection refused, timeouts, server-side operational errors). Because `OperationalError` subclasses `QueryError`, `install_error_handlers` returns **400 Bad Request** for conditions the client did not cause. `ConnectionLostError` correctly stays 500, but the generic operational bucket is now mislabeled. The CHANGELOG documents the 400 mapping, but the mapping is semantically wrong.

**Fix:** either map `OperationalError` to 500 (separate handler), or don't derive it from `QueryError` (derive from `EncinoOrmError`), and document the chosen status.

### WR-06: Disconnect code lists have gaps → reconnect false negatives

**File:** `encino_orm/oracle.py:28-30`, `encino_orm/mysql.py:28`

**Issue:**
- Oracle `_ORA_DISCONNECT_CODES` omits common transport failures: ORA-12570/12571 (TNS packet reader/writer failure), ORA-12170 (TNS connect timeout), ORA-01034 (ORACLE not available). These arrive mid-operation and will not trigger reconnect.
- MySQL only recognizes aiomysql `OperationalError` errnos 2006/2013/2055 and `InterfaceError`. A bare socket error surfaced as `ConnectionResetError`/`BrokenPipeError` (not an aiomysql type) is not a disconnect and is translated to a plain `OperationalError`, so no reconnect happens.
- MSSQL `HY000` mid-query detection depends on English message markers; localized messages (I reproduced a Spanish SQL Server message locally) will not match. The docs acknowledge localization, but there is no code/SQLSTATE fallback for the `HY000` KILL case.

**Fix:** extend the Oracle list (12570, 12571, 12170, 1034) and add `OSError`/`ConnectionResetError` handling for MySQL. For MSSQL, prefer SQLSTATE/native-code detection over message markers where possible.

### WR-07: MSSQL `is_alive()` commits, making it unsafe as a `pre_ping` probe

**File:** `encino_orm/mssql.py:179-192` (line 189), reachable via `encino_orm/base.py:294`

**Issue:** `MssqlDb.is_alive()` issues `SELECT 1` and then `await self._connection.commit()`. With `pre_ping=True`, `_maybe_recycle` calls `is_alive()` on every operation, including inside a transaction, committing any pending transaction state. (This is pre-existing code, but RESL-03 makes it reachable on the hot path; the CR-01 guard would also prevent the in-transaction case — fix both.) The same probe is used by `PoolDb.acquire()` for idle handles, where the commit is benign.

**Fix:** remove the `commit()` from `is_alive()` (a liveness probe must not mutate transaction state); if a transaction must be reset after probing, do it in the pool/release path that already owns that responsibility.

---

## Info

### IN-01: Dead `_DB_CON_TEMPLATE` compatibility shim in the test helper

**File:** `tests/_resilience_helpers.py:332-334`, `tests/_resilience_helpers.py:437-460`

**Issue:** `_DB_CON_TEMPLATE = hasattr(Db, "_with_reconnect")` is now always `True`, so the `else` branches in every public override are unreachable dead code. The comment ("Mientras … 05-01") is stale.

**Fix:** delete the shim and have `FakeResilientDb` call `super().execute(...)` unconditionally.

### IN-02: `retry` parameter name shadows the `retry()` method

**File:** `encino_orm/base.py:297`

**Issue:** `_with_reconnect(self, fn, *, retry: bool)` uses the same name as `Db.retry`. It is currently harmless (the method is not called inside), but it is a readability trap.

**Fix:** rename to `is_read` or `replay_on_reconnect`.

### IN-03: `_resilience_opts` mutates `pre_ping` before validating `max_connection_lifetime`

**File:** `encino_orm/base.py:249-257`

**Issue:** `self.pre_ping` is assigned before the `lifetime <= 0` validation raises, so a rejected `connect(max_connection_lifetime=0, pre_ping=True)` still flips `pre_ping` on the instance.

**Fix:** validate both values before assigning either.

### IN-04: Self-referential `__cause__` on lock / non-reconnectable re-raises

**File:** `encino_orm/base.py:342`, `:344`, `:355`

**Issue:** When `_translate_exception(exc)` returns the same instance (lock, already-library, or `EncinoOrmError`), `raise ... from exc` sets `exc.__cause__ = exc`. CPython's traceback printer tolerates this (verified), but it is malformed and can confuse third-party exception serializers/observability tooling that walk `__cause__` without cycle detection.

**Fix:** only chain when the translated object is a different instance:

```python
translated = self._translate_exception(exc)
if translated is exc:
    raise
raise translated from exc
```

---

## Requirement Verification

| Req | Status | Evidence / gap |
|-----|--------|----------------|
| **RESL-01** — per-engine disconnect vs lock, mutually exclusive | **TRUE for synthetic cases; INCOMPLETE on real MSSQL** | Disjointness verified for all six engines; real `oracledb` (`DPY-6005`) and real `pyodbc` `08xxx` disconnect shapes reproduced and classified correctly. Gaps: WR-03 (real `pyodbc` shape breaks `_native_code`, so MSSQL deadlocks/unique violations are misclassified) and WR-06 (localized `HY000`, missing Oracle/MySQL codes). |
| **RESL-02** — reconnect exactly once, only outside a transaction; A2 policy; separate from `retry()` | **INCOMPLETE** | `_with_reconnect` itself is correct: exactly one reconnect, no loop, tx guard on the failure path, reads re-execute, pre-execution writes execute, mid-statement writes reconnect-and-re-raise, locks returned by identity, SQLite `:memory:` rejected, `PoolDb` does not wrap itself. **But** `_maybe_recycle` reconnects inside transactions (CR-01), violating "solo cuando no hay transacción abierta". |
| **RESL-03** — `pre_ping` + `max_connection_lifetime` for direct connections | **INCOMPLETE** | Defaults off, opts popped before forwarding to the driver, `time.monotonic`, fail-closed validation, `:memory:` rejection, pool forwards options to physical connections — all verified. Gap: the proactive hook has no transaction guard (CR-01) and leaks untranslated failures (WR-01); MSSQL probe commits (WR-07). |
| **RESL-04** — public taxonomy + single translation point + lock short-circuit | **TRUE for the tested paths; INCOMPLETE** | Additive library classes verified; `_translate_exception` order (lock → EncinoOrmError → disconnect → adapter) verified; chaining verified; HTTP mapping documented. Gaps: WR-01 (untranslated proactive path), WR-02 (MSSQL 23000), WR-04 (breaking replacement of driver types), WR-05 (400 for operational failures). |

**Test quality:** RED→GREEN structure is genuine (helpers landed in `87ed441` before the implementation), tests are deterministic (no `sleep`, no network, no `unittest.mock`), Python 3.10 floor respected, MariaDB inheritance asserted by identity. Coverage gaps: no test for the proactive path with `tx=True` (CR-01), no test for proactive reconnect failure translation (WR-01), no real-shape MSSQL lock/integrity test (WR-03).

---

_Reviewed: 2026-09-18T23:59:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
