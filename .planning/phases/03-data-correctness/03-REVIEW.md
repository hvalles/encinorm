---
phase: 03-data-correctness
reviewed: 2026-09-18T00:00:00Z
depth: deep
files_reviewed: 18
files_reviewed_list:
  - encino_orm/migration.py
  - encino_orm/base.py
  - encino_orm/pool.py
  - encino_orm/dialects/strategies.py
  - encino_orm/dialects/__init__.py
  - encino_orm/__init__.py
  - encino_orm/sqlite.py
  - encino_orm/postgresql.py
  - encino_orm/mysql.py
  - encino_orm/mariadb.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - encino_orm/model/cached.py
  - encino_orm/model/model.py
  - encino_orm/model/cache_backend.py
  - tests/test_migrations.py
  - tests/test_migration_reconcile.py
  - tests/test_cached_model.py
  - tests/test_cache_backend.py
  - tests/test_dialect_ddl.py
findings:
  critical: 1
  warning: 2
  info: 4
  total: 7
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-09-18
**Depth:** deep
**Files Reviewed:** 18 (+ 5 test files)
**Status:** issues_found

## Summary

Phase 3 substantially delivers its stated goals: the rollback ledger bug is fixed (`rollback_migration` deletes `{name}` and never writes `:down`), `migrate()` records intent first (`pending` → DDL → `applied`) and reconciles loudly, the six adapters share the uniform `status` column with a catalog-checked idempotent `ALTER`, `CachedModel` invalidates after commit on `update`/`delete`/`upsert`, and `MemoryCacheBackend` is LRU-bounded. I verified the phase-relevant tests pass (52 passed) and `ruff` is clean on the touched modules.

The runner claims hold under inspection: `migration.py` never calls `db.commit()` (it uses `async with db.transaction()` only), `migrate()` cannot silently skip reconciliation (it calls `reconcile_migrations` before the idempotency check, and `reconcile_migrations` itself re-ensures the ledger), idempotency-by-name is preserved, and in a transactional-DDL engine a `pending` row does not survive a normal failure because the transaction rollback removes it. The `ALTER` race guard swallows only when the column ends up present, so it does not hide real errors.

The serious problem is in cache invalidation: the invalidation key is derived from the *write* keys, but `load()` caches under the *read* keys — the two domains are not the same. I reproduced a stale read with a PK-cached row followed by `upsert(conflict=["rfc"])`, and also with `update(keys=["rfc"])` / `delete(keys=["rfc"])`. This directly violates the phase's core guarantee ("`CachedModel` nunca sirve una fila obsoleta tras una escritura").

I also found a concurrency hazard in the migration compensation path that can delete another process's ledger row on implicit-commit engines, and a fail-open gap in `_invalidate`.

## Critical Issues

### CR-01: `CachedModel` invalidation key domain does not match the `load()` cache key domain → stale reads survive writes

**File:** `encino_orm/model/cached.py:31-42` (and the write overrides at `:71-91`)

**Issue:** `_invalidate(keys)` deletes exactly `self._cache_key(keys)`, where `keys` are the *caller-supplied write keys* (`update`/`delete`) or `upsert`'s `conflict`. But `load()` caches under the *caller-supplied read keys* (`encino_orm/model/cached.py:44-50`; default `_pk_fields()`). These are independent domains, so any write whose identifying key differs from the key used at `load()` time leaves the previously-cached entry untouched. Decision D-11's premise ("`load()` solo cachea por clave de PK") is false: `load(keys=...)` is public and caches under arbitrary keys, and the phase's own test suite relies on that (`load(keys=["rfc"])`).

Reproduced on real SQLite (`SqliteDb`) with a model whose `_primary_key` is the default `("id",)`:

```
inserted id= 1
cached under PK key, present: True
PK cache entry after upsert: STALE PRESENT
load() returned nombre = Viejo        # DB actually holds "Nuevo"
```

And the sibling paths:

```
update(keys=['rfc']) with PK-cached row: PK entry STALE PRESENT; load() -> 'Viejo'
delete(keys=['rfc']) with PK-cached row: PK entry STALE PRESENT; load() -> 'Viejo'
update() default keys (control):         PK entry invalidated;    load() -> 'Nuevo'
```

The `upsert` case is the most reachable: upserting by a natural unique key (the documented reason `conflict=` exists) while the row was cached by its PK is the normal usage pattern.

**Fix:** Invalidate every key domain a row can be cached under, not just the write keys. At minimum, delete the PK-keyed entry as well; the complete fix is to key the cache by the PK domain only (derive the row first when the requested keys are not the PK), since arbitrary read-key caching cannot be invalidated by a write.

```python
def _cache_keys(self, keys=None) -> set[str]:
    """Claves bajo las que puede estar cacheada esta fila: las del llamador y
    la de la PK (dominio por defecto de `load()`)."""
    out: set[str] = set()
    for candidate in (keys, type(self)._pk_fields()):
        normalized = self._normalize_keys(candidate, type(self)._pk_fields())
        try:
            out.add(self._cache_key(normalized))
        except AttributeError:
            pass  # la instancia no tiene ese campo; no hay clave que borrar
    return out

async def _invalidate(self, keys=None) -> None:
    cache = self._cache
    if cache is None:
        return
    try:
        for key in self._cache_keys(keys):
            await cache.delete(key)
    except Exception as exc:
        logger.warning("no se pudo invalidar la caché de %s: %r", self._table, exc)
```

Note this still leaves the case "cached via `load(keys=["rfc"])`, written via the PK" stale. For the phase's guarantee to be true, restrict the cache to the PK domain in `load()` (or document the limitation prominently and add a regression test for the non-PK read case). Whichever is chosen, add a test that caches under one key domain and writes under another.

## Warnings

### WR-01: `_apply` compensation can delete a ledger row it does not own (concurrent `migrate()`)

**File:** `encino_orm/migration.py:93-99`

**Issue:** On an implicit-commit engine, if the `pending` INSERT itself fails (`ddl_done` stays `False`), the compensation unconditionally runs `DELETE ... WHERE name = {name}`. Under concurrent `migrate("v1")` on MySQL/MariaDB/Oracle, process B's duplicate-name insert failure makes B delete the row that process A just published (A's `pending` was committed by the DDL's implicit commit, and A may even have already promoted it to `applied`). A's promote then updates 0 rows, so the DDL is applied but the ledger record is gone — exactly the "schema changed without a record" failure this phase exists to eliminate. `_apply` cannot distinguish "I created this row" from "someone else did".

**Fix:** Make the compensation delete conditional on ownership/state, and only when this call actually inserted the row. Track that the INSERT returned successfully and, for the duplicate-insert path, do nothing (the row belongs to someone else):

```python
except Exception:
    if not db.transactional_ddl and not ddl_done:
        if inserted:
            async with db.transaction():
                await db.execute(db.delete(MIGRATIONS_TABLE, {"name": name}))
    ...
```

Alternatively serialize migrations with an advisory lock (out of scope for this phase, but the compensation should not be allowed to delete a row it did not insert). At minimum, document that concurrent `migrate()` is unsupported.

### WR-02: `_invalidate` fail-open does not cover key derivation

**File:** `encino_orm/model/cached.py:36-38`

**Issue:** Only `cache.delete(...)` sits inside the `try`. `self._normalize_keys(...)` and `self._cache_key(...)` run before it and can raise (e.g. `AttributeError` from `getattr(self, k)` if the key is not a model field). Because `_invalidate` runs after the commit, such an exception would surface to the caller as a failure of an already-successful write, contradicting D-12's fail-open contract.

**Fix:** Move key derivation inside the `try` (as shown in the CR-01 snippet), so any derivation failure is downgraded to the same warning.

## Info

### IN-01: `resolve_migration` omits the "retry the rollback" half of the D-08 action

**File:** `encino_orm/migration.py:216-220`

**Issue:** The D-08 table specifies `rolling_back` + `applied=True` → "Restaurar `applied` **y reintentar el rollback**". The implementation only restores `applied`; the operator must remember to call `rollback_migration` again. The docstring was trimmed to match the code, so this is a spec/implementation gap rather than a coding error.

**Fix:** Either invoke `rollback_migration` after restoring, or state explicitly in the docstring (and in the reconciliation error text) that the rollback must be re-issued.

### IN-02: `_apply` logs a misleading "quedó en pending" warning when the `up` is non-DDL on an implicit-commit engine

**File:** `encino_orm/migration.py:100-106`

**Issue:** On MySQL/MariaDB/Oracle the implicit commit that publishes `pending` only happens for DDL. If the `up` is DML and the promote fails, `db.transaction()` rolls back the DML *and* the `pending` row, yet the code still logs "migración %s quedó en 'pending'". No row survives, so the message is false. `ddl_done` is also a misnomer for a DML migration.

**Fix:** Only emit that warning when the row is actually known to have survived (or rename the flag to `up_done` and re-read the row status before warning).

### IN-03: `MemoryCacheBackend(max_size<=-1)` raises `KeyError`

**File:** `encino_orm/model/cache_backend.py:42-43`

**Issue:** `while len(self._store) > self._max_size: self._store.popitem(last=False)` with a negative `max_size` drains the store and then calls `popitem` on an empty `OrderedDict`, raising `KeyError`. `max_size=0` is fine (stores nothing).

**Fix:** Validate the constructor argument (`if max_size < 0: raise ValueError(...)`) or guard the loop with `while self._store and len(self._store) > self._max_size:`.

### IN-04: Redundant ledger bootstrap on every `migrate()`

**File:** `encino_orm/migration.py:175` + each adapter's `migrate()`

**Issue:** `migrate()` calls `_ensure_migrations_table()`, then `reconcile_migrations()` which calls `_ensure_ledger(db)` again — two catalog checks and a `CREATE TABLE IF NOT EXISTS` per migration call. Harmless but wasteful, and it duplicates the ledger-bootstrap responsibility in six adapters (a known deferred refactor).

**Fix:** Have `reconcile_migrations` assume the caller bootstrapped (or make `_ensure_ledger` idempotent-cheap with a per-instance flag). Low priority.

---

## Notes on areas that checked out

- **Two-phase runner / transactional-DDL engines.** In a transactional engine a `pending` cannot survive a normal failure: `Db.transaction()` (`base.py:45-52`) rolls back the whole unit (pending INSERT + DDL) on exception, and `_apply` deliberately does not compensate there (`migration.py:107`). `PoolDb` delegates to the underlying adapter's transaction (`pool.py:187-196`), so the same holds through a pool.
- **`migrate()` never skips reconciliation** and stays idempotent by name (`sqlite.py:224-235` and the five siblings).
- **The runner never calls `db.commit()`** — verified in `migration.py`; adapters commit their own connection only inside `_ensure_migrations_table`.
- **Idempotent `ALTER`.** The catalog check is per-dialect correct (`columns_of` lowercases on SQL Server/Oracle via `_rows.py`; PostgreSQL/Oracle bind the table name). The verify-then-swallow guard re-reads the catalog and re-raises only when `status` is still absent, so it swallows the duplicate-column race and not a real error.
- **`resolve_migration`** maps all four D-08 state/`applied` combinations correctly and rejects non-ambiguous/unknown states.
- **LRU** is exact for `max_size >= 0`; `get`/`set`/`delete` contain no `await` in their critical sections, so they are atomic within the event loop.
- **Security.** No new injection surface: interpolated identifiers are module constants validated with `check_identifier`, and `name`/`status` are always bound. The `MigrationError` carries only the developer's SQL template (`qry.sql`), not bound parameters or connection strings.

---

_Reviewed: 2026-09-18_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
