---
phase: 04-pool-correctness-concurrency
reviewed: 2026-09-19T03:36:09Z
depth: deep
files_reviewed: 34
files_reviewed_list:
  - encino_orm/pool.py
  - encino_orm/base.py
  - encino_orm/context.py
  - encino_orm/query.py
  - encino_orm/sqlite.py
  - encino_orm/mysql.py
  - encino_orm/mariadb.py
  - encino_orm/postgresql.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - encino_orm/dialects/builders.py
  - encino_orm/dialects/strategies.py
  - encino_orm/dialects/identifiers.py
  - encino_orm/model/model.py
  - encino_orm/migration.py
  - encino_orm/transfer.py
  - encino_orm/__init__.py
  - tests/test_pool.py
  - tests/test_pool_characterization.py
  - tests/test_pool_concurrency.py
  - tests/_pool_helpers.py
  - tests/test_dialect_builders.py
  - tests/test_d_recommendations.py
  - tests/test_migration_reconcile.py
  - tests/test_sqlite.py
  - tests/test_mysql.py
  - tests/test_postgresql.py
  - tests/test_mssql.py
  - tests/test_oracle.py
  - tests/test_mariadb.py
  - pyproject.toml
  - .github/workflows/ci.yml
  - CHANGELOG.md
  - docs/engines.md
  - docs/guide.md
findings:
  critical: 2
  warning: 8
  info: 4
  total: 14
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-09-19T03:36:09Z
**Depth:** deep (cross-file call-chain tracing, live repro runs)
**Files Reviewed:** 34
**Status:** issues_found

## Summary

Phase 4's core mechanics are real and mostly correct. I verified with live
reproductions that `acquire()` no longer overshoots `max_size` under the
deterministic `EventBarrier` race, that a failed `_create_connection()` returns
its reserved slot, that double-release is deduplicated, that `close()` is
idempotent and leaves held connections alive, that the lazy reaper keeps
`min_size` and never runs below it, that `reset_on_release="rollback"` is the
default and `"commit"` warns, and that `execute`/`_run` commit/rollback
explicitly. `uv run pytest -q -m "not integration and not optional_engine"`
passes (819 passed, 85 deselected); `ruff check`, `ruff format --check`, and
`mypy encino_orm` all pass.

However, the id-capture work (POOL-03) is **not complete**, and the pool's
"task ownership" claim (POOL-02) is only half-implemented. Two defects are
critical: `Model.insert` interpolates the literal column name `id` into
`RETURNING`/`OUTPUT INSERTED`, so any model that maps its `id` field to a
different physical column (a supported feature) fails on PostgreSQL, MSSQL and
Oracle; and an `INSERT ... OR IGNORE`/`INSERT IGNORE` that is ignored still
returns a stale/nonzero id that `Model.insert` assigns to `self.id`, so a
subsequent `update()` can target another row. The pool also has a narrow
`_reap()`/`close()` race that can leak an idle connection past `close()`, and
neither `owner_task` nor the contextvar actually enforces per-task ownership
(child tasks inherit `_current_connection`).

## Critical Issues

### CR-01: `Model.insert` uses the literal `"id"` as the returning column, breaking renamed auto-PKs on PostgreSQL/MSSQL/Oracle

**File:** `encino_orm/model/model.py:539` (docstring at `:501-503`)

**Issue:** `returning = "id" if auto else None` hardcodes the *field* name, not
the physical column name. The codebase explicitly supports renaming the `id`
column (`tests/test_types.py:19`:
`id: Annotated[int, Column(name="legacy_id")] = None`; `_build_column_map`
reads `Column.name`). For such a model `_is_auto_pk()` is `True`, so the
builder emits `RETURNING id` (PostgreSQL), `OUTPUT INSERTED.id` (MSSQL) or
`RETURNING id INTO :ret_id` (Oracle) against a table whose PK is `legacy_id`.

Minimal repro (DB-free, verified):

```python
from typing import Annotated, ClassVar
from encino_orm.model import Column, Model
from encino_orm.dialects.builders import build_insert
from encino_orm.dialects.strategies import POSTGRES_INSERT, MSSQL_INSERT

class Legacy(Model):
    _table = "legacy"
    _fields_disabled: ClassVar[list] = ["enabled", "created_at", "updated_at"]
    id: Annotated[int, Column(name="legacy_id")] = None
    nota: str | None = None

# Legacy._is_auto_pk() -> True ; Legacy._col("id") -> "legacy_id"
build_insert("legacy", {"nota": "x"}, strategy=POSTGRES_INSERT, returning="id").sql_template
# -> "INSERT INTO legacy (nota) VALUES ({0}) RETURNING id"   <-- column does not exist
build_insert("legacy", {"nota": "x"}, strategy=MSSQL_INSERT, returning="id").sql_template
# -> "INSERT INTO legacy (nota) OUTPUT INSERTED.id VALUES ({0})"
```

On PostgreSQL this raises `UndefinedColumnError`, on MSSQL "Invalid column
name", on Oracle ORA-00904. SQLite/MySQL/MariaDB are unaffected because
`execute_insert` reads `cursor.lastrowid` and ignores `id_column`. The old
`last_id()` path did not reference the column, so this is a Phase 4 regression.
No test covers a renamed auto-PK insert (the `Legacy` model is only used for
DDL assertions), which is why the suite stays green.

**Fix:**

```python
# Physical column name, consistent with _column_map()/data building above.
returning = self._col("id") if auto else None
```

The builder already sets `id_column=returning`, so this also fixes
PostgreSQL's `row[qry.id_column]` lookup. Add a regression test that inserts a
model with `Column(name=...)` on an auto PK.

### CR-02: Ignored inserts return a stale/zero id and `Model.insert` assigns it to `self.id`

**File:** `encino_orm/sqlite.py:196`, `encino_orm/mysql.py:219`, `encino_orm/model/model.py:549-552`

**Issue:** `execute_insert` returns `cursor.lastrowid` unconditionally when
`qry.returns_id`. For `INSERT OR IGNORE` (SQLite) an ignored insert leaves
`lastrowid` pointing at the *previous* successful insert; for `INSERT IGNORE`
(MySQL/MariaDB) `lastrowid` is `0`. `Model.insert` then does
`if auto and new_id is not None: self.id = new_id`, so the model that was
*not* inserted adopts another row's id (SQLite) or `0` (MySQL) and is marked
`__exists=True`. A subsequent `update()`/`delete()` on that instance targets
the wrong row.

Minimal repro (verified against the real SQLite adapter):

```python
q1 = pool.insert("t", {"nombre": "a"}, returning="id")
assert await pool.execute_insert(q1) == 1
q2 = pool.insert("t", {"nombre": "a"}, ignore_duplicated=True, returning="id")
# q2.sql_template == "INSERT OR IGNORE INTO t (nombre) VALUES ({0})"
assert await pool.execute_insert(q2) == 1   # <-- stale: row "a" already exists
```

`Model.insert(ignore_duplicated=True)` on that second row sets `self.id = 1`
(the first row's id), after which `self.update()` rewrites row 1. This is a
pre-existing defect that POOL-03's new contract (`None` == "id no disponible")
should have closed but did not.

**Fix:** treat a no-op insert as "id unavailable":

```python
# sqlite.py
cursor = await self._connection.execute(sql, values)
if qry.returns_id and cursor.rowcount == 0:
    new_id = None          # ignored by OR IGNORE
else:
    new_id = cursor.lastrowid if qry.returns_id else None
```

Mirror with `cursor.rowcount == 0` in `mysql.py` (and consider returning
`None` when `lastrowid == 0`). Add a regression test asserting
`Model.insert(ignore_duplicated=True)` returns `0` and does not assign
`self.id` when the row already exists.

## Warnings

### WR-01: `owner_task` is recorded but never enforced; child tasks inherit the parent's pooled connection

**File:** `encino_orm/pool.py:63, 190-195, 284-292, 359, 436`

**Issue:** `_checkout()` stores `handle.owner_task = asyncio.current_task()`,
but `release()` only checks `handle not in self._checked_out` and never
compares `owner_task`. Any task that obtains a handle reference can release
another task's in-use connection. Worse, `_current_connection` is a
`ContextVar` and `asyncio.create_task()` copies the current context, so a child
task spawned inside `pool.transaction()` silently runs on the parent's
connection (verified: `child inherited parent handle: True`). This contradicts
the phase's stated "task ownership via `_current_connection`" (POOL-02): the
pool cannot detect a foreign/child release, and two tasks can interleave
statements on one connection, defeating the atomicity the contextvar was meant
to protect.

**Fix:** enforce ownership in `release()`:

```python
current = asyncio.current_task()
if handle not in self._checked_out or handle.owner_task is not current:
    logger.warning("release() de una conexión ajena o duplicada: %r", handle)
    return
```

Optionally document that child tasks must not use a pool-bound connection
inside a transaction, or bind the handle only for the exact owning task.

### WR-02: `min_size > max_size` (and negative sizes) is not validated, so `connect()` exceeds `max_size`

**File:** `encino_orm/pool.py:88-109, 177-181`

**Issue:** `__init__` validates `reset_on_release` but not the size arguments.
`connect()` creates `min_size` connections unconditionally. Verified:

```python
p = PoolDb("sqlite", min_size=5, max_size=2, database=":memory:")
await p.connect()
p._size  # -> 5, p._max_size == 2
```

This violates POOL-02's stated invariant `_size <= max_size SIEMPRE`. Negative
`min_size`/`max_size` are likewise accepted.

**Fix:** fail closed in `__init__`:

```python
if min_size < 0 or max_size < 1 or min_size > max_size:
    raise ValueError(
        f"tamaños de pool inválidos: min_size={min_size!r}, max_size={max_size!r}"
    )
```

### WR-03: `_reap()`/`close()` race can leave an idle connection open and uncounted after `close()`

**File:** `encino_orm/pool.py:230-233, 328-354`

**Issue:** `_reap()` drains `_idle` synchronously, then `await`s
`handle.driver.close()` for the stale handles, and only afterwards re-enqueues
the `keep` list (`for handle in keep: self._idle.put_nowait(handle)`). If
`close()` runs during that await, it drains `_idle` (empty at that moment),
sets `_closed=True`, and computes `_size = len(_checked_out)`. `_reap()` then
resumes and puts the `keep` handles back into the closed pool's queue without
closing their drivers. Those connections leak (never closed, not counted in
`_size`), breaking POOL-06's "`close()` closes the idle connections".

**Fix:** re-check `_closed` after the awaits before re-enqueueing, or close
the `keep` handles when the pool is closed:

```python
for handle in keep:
    if self._closed:
        self._connections.discard(handle)
        await handle.driver.close()
    else:
        self._idle.put_nowait(handle)
```

### WR-04: MSSQL `replace=True` on a single-data-column model now raises `ValueError` (undocumented behavior change)

**File:** `encino_orm/dialects/builders.py:160-166`; `CHANGELOG.md`

**Issue:** the ORA-38104 fix excludes the conflict column from the MERGE `SET`
and fails closed when nothing remains. For a typical surrogate-PK model with a
single data column (`{"nombre": ...}`), the fallback conflict column is
`columns[0]` and `update_cols` becomes empty, so both MSSQL and Oracle now
raise `ValueError("MERGE sin columnas actualizables...")`. On MSSQL this case
previously produced a valid (if semantically odd) MERGE. Verified:

```python
build_insert("t", {"nombre": "x"}, strategy=MSSQL_INSERT, replace=True)
# ValueError: MERGE sin columnas actualizables
```

The CHANGELOG documents the Oracle ORA-38104 fix but not this MSSQL regression.

**Fix:** either allow an MSSQL MERGE with an empty `SET` (omit the
`WHEN MATCHED THEN UPDATE` branch when `update_cols` is empty) or explicitly
document the new `ValueError` in `CHANGELOG.md` as an incompatible change for
single-column `replace=True`.

### WR-05: `PoolDb.acquire()` return type changed from `Db` to `PooledConnection` without a CHANGELOG entry

**File:** `encino_orm/pool.py:235`

**Issue:** `acquire()` is public and used to return a `Db`. It now returns a
`PooledConnection` handle; only `handle.driver` is a `Db`. The tests were
migrated (`tests/test_pool.py`, `test_pool_characterization.py`), but the
CHANGELOG's Phase 4 entries never mention this breaking API/return-type change.
The project constraint in `AGENTS.md` requires incompatible changes to be
documented in `CHANGELOG.md`.

**Fix:** add a CHANGELOG bullet noting that `PoolDb.acquire()` now returns a
`PooledConnection` (use `.driver` for the raw `Db`; `release()` accepts both),
and document the handle in `docs/guide.md`.

### WR-06: `_run`/`execute` can mask the original error if `in_transaction()` raises in the `except` block

**File:** `encino_orm/pool.py:418-424, 469-474`

**Issue:** the error path does
`except BaseException: if await handle.driver.in_transaction(): await handle.driver.rollback(); raise`.
If the connection is broken, `in_transaction()` itself may raise (e.g.
`MysqlDb.in_transaction` calls `get_transaction_status()` on a dead handle;
asyncpg's `is_in_transaction()` can raise `InterfaceError`). The new exception
then replaces the root cause, contradicting the inline comment "Se re-lanza
siempre el error raíz, sin enmascararlo". `release()` calls
`in_transaction()` again in its `finally`, so a second raise is possible.

**Fix:** guard the cleanup:

```python
except BaseException:
    try:
        if await handle.driver.in_transaction():
            await handle.driver.rollback()
    except Exception:
        logger.warning("no se pudo revertir el sobrante al liberar", exc_info=True)
    raise
```

Apply the same guard to `execute` and to the `in_transaction()` probe in
`release()`.

### WR-07: `session()` catches only `Exception`, so cancellation bypasses its explicit commit/rollback

**File:** `encino_orm/pool.py:556-564`

**Issue:** unlike `_run`/`execute` (which catch `BaseException`), `session()`
uses `except Exception`. On `asyncio.CancelledError` the `else`/`except`
branches are skipped and only `release()` runs. With the default `"rollback"`
policy that is safe, but with the deprecated `reset_on_release="commit"` a
cancelled session commits whatever the caller had half-written. The two
release paths in the same file are inconsistent.

**Fix:** catch `BaseException` in `session()` to mirror `_run`/`execute`, or
call `rollback()` unconditionally in the cancellation path.

### WR-08: `docs/engines.md` still documents `last_id` as part of the adapter contract

**File:** `docs/engines.md:65, 75, 254`

**Issue:** the adapter skeleton still lists `async def last_id(self) -> int:
...` (line 75) and the checklist still requires "`last_id()` correcto"
(line 254), while the new contract makes `execute_insert` the abstract method
and `last_id` a deprecated concrete helper (`Db.last_id`, `base.py:157`).
`insert` is also shown without the new `returning=` parameter (line 65). The
section "2. Implementa la captura del id" was updated, but the skeleton and
checklist contradict it.

**Fix:** replace `last_id` with `async def execute_insert(self, qry: Query) ->
int | None` in the skeleton, add `returning=` to the `insert` signature, and
update the checklist item to `execute_insert()`.

## Info

### IN-01: `PooledConnection.last_id` and `owner_task` are dead state

**File:** `encino_orm/pool.py:59, 63`

**Issue:** `last_id` is never read or written; `owner_task` is written in
`_checkout`/`release` but never compared (see WR-01). Both fields were in the
POOL-01 plan but carry no behavior.

**Fix:** either use `owner_task` for the ownership check (WR-01) and remove
`last_id`, or remove both fields to keep the handle minimal.

### IN-02: `PoolDb.execute` duplicates `_run` logic

**File:** `encino_orm/pool.py:462-482`

**Issue:** `execute` re-implements the `_current_connection` early-return and
the commit/rollback/`release` sequence already encoded in `_run`. The two can
drift (e.g. WR-06 must be fixed in both places).

**Fix:** `return await self._run("execute", qry)`.

### IN-03: `PooledConnection` is not re-exported from the package

**File:** `encino_orm/__init__.py`

**Issue:** `acquire()` returns a `PooledConnection` (public API) but the class
is only importable from `encino_orm.pool`, while `PoolDb`, `create_db` and
`session` are re-exported. Tests reach into `encino_orm.pool`.

**Fix:** add `PooledConnection` to the import block and `__all__`.

### IN-04: Test doubles do not match the real `insert`/`execute_insert` contract

**File:** `tests/_pool_helpers.py:52-56`, `tests/test_pool_characterization.py:69-70`

**Issue:** both `FakeDb.insert` implementations omit `schema=`/`returning=`
(and the characterization one omits `conflict=`), so any future test that
routes `PoolDb.insert` through these doubles raises `TypeError` instead of
exercising the path. The real `Db.insert` contract now includes `returning`.

**Fix:** align the doubles' `insert` signature with `Db.insert` and have
`execute_insert` honour `qry.returns_id` (return `None` when not requested).

## POOL requirement verification

| Req | Verdict | Evidence / gap |
|-----|---------|----------------|
| POOL-01 (`PooledConnection` handle) | TRUE | Handle concentrates driver/generation/checked_out/last_used; `_last_id` removed from `PoolDb`. `last_id` field is dead (IN-01). |
| POOL-02 (race-free admission, `_size <= max_size`) | PARTIAL | Reservation-before-await verified; failed create returns capacity; double release deduped. Not enforced: `owner_task`/contextvar ownership (WR-01) and `min_size > max_size` (WR-02). |
| POOL-03 (per-engine id capture, `last_id` deprecated) | PARTIAL | Six `execute_insert` implementations + `returning` opt-in + ORA-38104 fix verified; `DeprecationWarning` centralized. Broken for renamed PK columns (CR-01) and ignored inserts (CR-02). |
| POOL-04 (`reset_on_release`, explicit close in `execute`/`_run`) | TRUE | Default `"rollback"`, `"commit"` warns at construction, invalid value raises; `execute`/`_run` commit on success and roll back on error. Error-path masking risk (WR-06). |
| POOL-05 (lazy reaper above `min_size`) | TRUE | `_reap` invoked on `acquire`/`release`, no daemon, keeps `min_size`, `idle_timeout=None` disables. Race with `close()` (WR-03). |
| POOL-06 (idempotent `close()`, never closes in-use) | PARTIAL | Held connections stay alive and close on release; second `close()` no-op; stale generations close on release. Concurrent `_reap` can leak (WR-03). |
| POOL-07 (deterministic 3.10-compatible tests) | TRUE | `EventBarrier` uses only `asyncio.Event`; no `unittest.mock`; `pytest-timeout`/`pytest-repeat` pinned and registered; stress test deterministic. |

## Verification performed

- `uv run pytest -q tests/test_pool.py tests/test_pool_characterization.py tests/test_pool_concurrency.py` -> 78 passed.
- `uv run pytest -q -m "not integration and not optional_engine"` -> 819 passed, 85 deselected, 10 snapshots passed.
- `uv run ruff check encino_orm tests` -> All checks passed.
- `uv run ruff format --check encino_orm tests` -> 117 files already formatted.
- `uv run mypy encino_orm` -> Success: no issues found in 60 source files.
- Live repros: admission barrier (no overshoot), ignored-insert stale id (CR-02), renamed-PK `RETURNING` SQL (CR-01), `min_size > max_size` overshoot (WR-02), child-task contextvar inheritance (WR-01).

---

_Reviewed: 2026-09-19T03:36:09Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
