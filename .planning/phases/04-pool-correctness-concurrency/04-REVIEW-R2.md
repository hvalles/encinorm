---
phase: 04-pool-correctness-concurrency
reviewed: 2026-09-19T03:45:32Z
depth: deep
round: 2
commit_reviewed: e572e8c
files_reviewed: 11
files_reviewed_list:
  - encino_orm/pool.py
  - encino_orm/model/model.py
  - encino_orm/mysql.py
  - encino_orm/sqlite.py
  - encino_orm/__init__.py
  - encino_orm/dialects/builders.py
  - encino_orm/postgresql.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - tests/test_pool.py
  - tests/test_sqlite.py
  - tests/test_types.py
  - CHANGELOG.md
  - docs/engines.md
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 4: Code Review Report (Round 2 — fix commit `e572e8c`)

**Reviewed:** 2026-09-19T03:45:32Z
**Depth:** deep
**Commit:** `e572e8c` (`fix(04): cierra los Critical de la revisión (CR-01/CR-02) y endurece el pool (WR-01..08)`)
**Files Reviewed:** 11 source + 3 docs/test
**Status:** issues_found

## Summary

The two Critical defects are genuinely fixed. `Model.insert` now requests the
**physical** PK column (`self._col("id")`), and I confirmed with a live builder
probe that PostgreSQL, MSSQL and Oracle all render the correct capture clause
against a renamed auto-PK (`RETURNING legacy_id` / `OUTPUT INSERTED.legacy_id` /
`RETURNING legacy_id INTO :ret_id`, with `id_column="legacy_id"`). `execute_insert`
in SQLite/MySQL now returns `None` on a no-op insert; I confirmed SQLite's
`rowcount` is `0` for an ignored `INSERT OR IGNORE` and `1` for a real insert, so
the fix does not regress legitimate inserts, and MySQL/MariaDB share the same
code path. The WR-02/06/07/08 fixes are correct and verified. WR-01 is only
**half** closed: `release()` now enforces ownership, but child tasks still
inherit `_current_connection` and can run statements on the parent's connection
through `_run`'s early-return (verified live) — the exact interleaving the phase's
POOL-02 claim rules out. WR-03's `_closed` branch is defensively correct but
effectively unreachable, and accounting stays consistent.

The full suite passes (`823 passed, 85 deselected`), `ruff check`,
`ruff format --check` and `mypy encino_orm` are clean. The two new tests are true
RED→GREEN, though the CR-01 test only exercises the `Model` layer (no builder or
driver assertion).

## Per-finding status (prior review)

| ID | Status | Evidence |
|----|--------|----------|
| CR-01 renamed auto-PK `returning` | **CLOSED** | `model.py:542` `returning = self._col("id")`. Live builder probe: PG `... RETURNING legacy_id`, MSSQL `... OUTPUT INSERTED.legacy_id ...`, Oracle `... RETURNING legacy_id INTO :ret_id`, all with `id_column="legacy_id"`. Test `test_insert_usa_la_columna_fisica_de_la_pk_auto` is true RED→GREEN (pre-fix `db.returning == "id"`). |
| CR-02 ignored insert stale id | **CLOSED** | `sqlite.py:196-204` and `mysql.py:222` return `None` when `rowcount == 0`. Live SQLite probe: ignored `rowcount=0/lastrowid=1`, real insert `rowcount=1/lastrowid=3`, `INSERT OR REPLACE` `rowcount=1`. `Model.insert` no longer assigns `self.id` and returns `0`. PostgreSQL (`RETURNING` + `ON CONFLICT DO NOTHING` → `None`), MSSQL/Oracle (unique-violation → `None`) are unaffected. Test is true RED→GREEN. |
| WR-01 ownership | **PARTIAL** | `release()` guard added (`pool.py:300-308`), foreign/duplicate release blocked and test RED→GREEN. **But** `_run` (`pool.py:434-438`) still early-returns to the inherited handle without an owner check; live repro: child task inside `pool.transaction()` executes on the parent's driver. See N-01. |
| WR-02 size validation | **CLOSED** | `pool.py:106-109` rejects `min_size<0`, `max_size<1`, `min_size>max_size`. Scanned every `PoolDb(...)` construction in repo/tests: none use a now-invalid config; suite green. |
| WR-03 `_reap()`/`close()` race | **CLOSED** | `pool.py:237-245` closes `keep` when `_closed`. `_size` is not decremented there, which is consistent because `close()` already reset `_size = len(_checked_out)` excluding idle handles. Note: the branch is effectively unreachable (see N-05). |
| WR-04 MSSQL `replace=True` | **CLOSED** | CHANGELOG documents the new `ValueError` for single-data-column `replace=True`; verified MSSQL and Oracle both raise `MERGE sin columnas actualizables...`. |
| WR-05 `acquire()` return type | **CLOSED** | CHANGELOG entry added (handle, `.driver`, re-export). `docs/guide.md` was not updated (was an optional part of the suggested fix) — minor. |
| WR-06 error masking | **CLOSED** | Guarded `in_transaction()`/rollback in `_run` (`pool.py:448-454`), `release()` (`319-326`) and `session()` (`573-579`). Live repro: driver raising on `in_transaction()` during cleanup still surfaces the root `ValueError`, not the probe error. |
| WR-07 `session()` cancellation | **CLOSED** | `pool.py:570` `except BaseException`. Live repro: `CancelledError` inside `session()` triggered `rollback` before re-raising. |
| WR-08 docs `last_id` | **CLOSED** | `docs/engines.md:65-80` now shows `insert(..., returning=...)`, `execute_insert`, and `last_id` marked DEPRECATED; checklist updated to `execute_insert()`. |
| IN-01 dead state | **PARTIAL** | `owner_task` now enforced in `release()`, but `PooledConnection.last_id` (`pool.py:59`) is still never read in production (only asserted at `tests/test_pool.py:131`). See N-03. |
| IN-02 `execute` duplication | **CLOSED** | `pool.py:493-496` delegates to `_run`; commit/rollback/early-return now have a single implementation. |
| IN-03 re-export | **CLOSED** | `PooledConnection` imported and added to `__all__` in `encino_orm/__init__.py`. |
| IN-04 test-double contract | **OPEN** | `tests/_pool_helpers.py:58` and `tests/test_pool_characterization.py:75` still define `insert(tabla, data, ignore_duplicated, replace)` without `conflict`/`schema`/`returning`. `tests/test_pool.py`'s own `FakeDb` was already updated. See N-04. |

## Warnings

### WR2-01 (N-01): child tasks still share the parent's pooled connection — `_run` early-return skips the ownership check

**File:** `encino_orm/pool.py:434-438` (reproduced against the fix commit)

**Issue:** `release()` now enforces `handle.owner_task is asyncio.current_task()`,
but `_run()` still returns straight into `_current_connection.get()` for **any**
task that inherited the contextvar. `asyncio.create_task()` copies the context,
so a child task spawned inside `pool.transaction()` runs on the parent's
connection. This is the second half of the prior WR-01, and the new comment in
`release()` claims it is prevented ("una tarea hija ... podría intercalar
sentencias en la conexión del padre") — it is not.

Live repro (DB-free, fake engine):

```python
async with p.transaction():
    parent = _current_connection.get()
    async def child():
        await p.execute("SELECT 1")   # lands on parent.driver via _run early-return
        return _current_connection.get() is parent
    assert await asyncio.create_task(child()) is True
# parent.driver.calls == [('begin',), ('execute', 'SELECT 1')]
```

**Impact:** two tasks interleave statements on one driver connection, defeating
transactional atomicity (a child's work is committed/rolled back with the
parent). Requires the user to spawn a child task inside `transaction()`; no test
covers it. Severity is WARNING (borderline Critical: it is the atomicity
guarantee POOL-02 claims).

**Fix:** add the same owner check to the early-return:

```python
async def _run(self, method: str, *args):
    handle = _current_connection.get()
    if handle is not None:
        if handle.owner_task is not asyncio.current_task():
            raise ConnectionError(
                "conexión de pool en uso por otra tarea; no se puede compartir"
            )
        return await getattr(handle.driver, method)(*args)
    ...
```

Alternatively document explicitly that a pool-bound connection must not be used
from child tasks.

## Info

### IN2-01 (N-02): ignored `insert(ignore_duplicated=True)` still marks the instance as existing

**File:** `encino_orm/model/model.py:552-556`

**Issue:** after an ignored insert, `new_id is None` and `self.id` stays `None`,
but `_set_private(self, "__exists", True)` runs unconditionally. The object
claims to represent a persisted row it does not. Impact is low: `update()`/
`delete()` raise `FailOnUpdate` on a `None` PK (`model.py:740-741`, `773-775`),
so the prior cross-row corruption vector is gone. Pre-existing, not introduced
by this commit, but it is the residual semantic half of CR-02.

**Fix:** `_set_private(self, "__exists", True)` only when the insert actually
persisted (e.g. `if not (ignore_duplicated and new_id is None): ...`), or
document that the caller must reload after an ignored insert.

### IN2-02 (N-03): `PooledConnection.last_id` is still dead state (IN-01 residual)

**File:** `encino_orm/pool.py:59`

**Issue:** `last_id` is never read or written in production; only
`tests/test_pool.py:131` asserts its default. `owner_task` is now used, so only
half of IN-01 was addressed.

**Fix:** remove the field (or wire it into the per-connection id path if it is
still intended).

### IN2-03 (N-04): helper test doubles still omit the `returning`/`schema` contract (IN-04)

**File:** `tests/_pool_helpers.py:58`, `tests/test_pool_characterization.py:75`

**Issue:** both `insert` doubles lack `conflict`/`schema`/`returning`. No current
test routes `PoolDb.insert(..., returning=...)` through them, so the suite is
green, but the next such test raises `TypeError` instead of exercising the path.

**Fix:** align the signatures with `Db.insert` (as `tests/test_pool.py:51-64`
already does).

### IN2-04 (N-05): `_reap()`'s `if self._closed` branch is effectively unreachable

**File:** `encino_orm/pool.py:237-245`

**Issue:** the drain loop and the `keep` re-enqueue contain no `await`, so
`close()` cannot interleave between them. `close()` drains `_idle`
synchronously, and `release()` after `close()` never re-enqueues, so `_reap()`
can only see `_closed=True` with an empty `_idle`. The branch is harmless
defensive code; `_size`/`_connections` accounting remains consistent (verified
by reasoning; the reset `_size = len(_checked_out)` excludes idle handles).

**Fix:** none required; keep as defense-in-depth or drop with a comment.

## Verification performed

- `uv run pytest -q -m "not integration and not optional_engine"` → **823 passed, 85 deselected**, 10 snapshots passed.
- `uv run ruff check encino_orm tests` → All checks passed.
- `uv run ruff format --check encino_orm tests` → 117 files already formatted.
- `uv run mypy encino_orm` → Success: no issues found in 60 source files.
- Live probes: builder `RETURNING`/`OUTPUT INSERTED` for renamed PK (PG/MSSQL/Oracle); SQLite `rowcount`/`lastrowid` for ignored vs real insert; WR-06 root-error preservation; WR-07 cancellation rollback; child-task contextvar inheritance (N-01).
- Test triage: `test_insert_usa_la_columna_fisica_de_la_pk_auto` and
  `TestInsertIgnoreDuplicado` are true RED→GREEN; `test_release_de_otra_tarea_no_libera`
  and `test_pool_rechaza_tamanos_incoherentes` are true RED→GREEN. The CR-01 test
  only proves the `Model` layer passes the physical column — it does not assert
  the builder SQL/`id_column` or the drivers (covered here by manual probe).

## Verdict

**Ship the Critical fixes (CR-01/CR-02 CLOSED).** WR-01 is **PARTIAL**: ownership
is enforced on release but the inherited-contextvar execution path remains, so the
POOL-02 atomicity claim is not yet true. 5 new findings (0 Critical, 1 Warning,
4 Info); no regression introduced by the fixes to the previously verified pool
mechanics.

---

_Reviewed: 2026-09-19T03:45:32Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
_Round: 2_
