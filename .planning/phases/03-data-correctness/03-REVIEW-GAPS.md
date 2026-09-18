---
phase: 03-data-correctness
reviewed: 2026-09-18T13:30:00Z
depth: deep
scope: gap-closure round 2 (09d8f56..HEAD)
files_reviewed: 8
files_reviewed_list:
  - encino_orm/model/cached.py
  - encino_orm/migration.py
  - tests/test_cached_model.py
  - tests/test_redis_cache.py
  - tests/test_migration_reconcile.py
  - docs/guide.md
  - docs/design/5-security.md
  - CHANGELOG.md
findings:
  critical: 2
  warning: 3
  info: 3
  total: 8
status: issues_found
---

# Phase 3: Gap-Closure Round 2 Code Review Report

**Reviewed:** 2026-09-18
**Depth:** deep (cross-file call-chain tracing + runtime reproduction)
**Range:** `09d8f56..HEAD` (`2058f92`)
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The round-2 fixes do what they claim for the **single-row, unique-write-key** case:

- **CR-01 (canonical PK cache domain):** `load()` now writes only under the row's PK; a non-PK read queries the DB and re-caches under the PK. `update`/`delete`/`upsert` resolve the affected row's real PK (instance if the write keys are the PK, otherwise a bound scope-aware `super().load`) and delete exactly that entry. Verified by 5 new RED→GREEN tests.
- **WR-01 (migration ownership):** the `inserted` flag + compare-and-delete `{name, status: pending}` closes the reported duplicate-insert path. Verified RED→GREEN.
- **IN-01 (docs):** `resolve_migration`'s docstring and `reconcile_migrations`' error text name `rollback_migration`. Verified.

However, the canonical-domain fix introduces/leaves two **data-correctness/security gaps** that the round's own documentation overclaims against, plus a residual migration race:

1. **Multi-row writes invalidate only one PK entry.** `Model.update(keys=[...])`/`delete(keys=[...])` affect **all** matching rows, but `_resolve_pk_values` resolves exactly one row (via `fetch_one`). Reproduced: two PK-cached rows, `update(keys=["grp"])` updates both, only one cache entry is deleted; `load()` on the other returns stale data.
2. **The cache is not namespaced by `scope()` and the hit path bypasses scope.** A cache hit short-circuits `current_scope()`. Reproduced: tenant A's non-PK read populates the canonical PK entry; tenant B's `load(id=...)` returns A's row, and tenant B's `update()` **writes** A's row. This is pre-existing but the canonical-domain change widens it (non-PK reads now populate the shared PK entry) and the docs now assert scope-awareness.

All 9 new tests are genuine regressions: they **fail on `09d8f56`** (verified in an isolated worktree) and pass on HEAD. Targeted suite: `33 passed`. Docs anchor fix (`#54-cache-opcional`) is correct per Python-Markdown slugify.

## Critical Issues

### CR-01: Multi-row writes invalidate only one PK entry → stale cache reads

**File:** `encino_orm/model/cached.py:71` (probe), `:98` (single-key delete), `:142-144` / `:153-155` / `:165-167` (write paths)

**Issue:** `_resolve_pk_values` resolves the row with `probe = await super().load(keys=write_keys)` (`:71`), which is `Model.load` → `fetch_one` → **one** arbitrary row. But `Model.update`/`delete` build `WHERE <write keys>` (`model.py:697-733`, `:735-758`) and affect **every** matching row. The cache domain is the PK, so each affected row may have its own PK entry; only the single probed PK is deleted (`_invalidate_pk`, `:98`). The un-probed rows keep serving stale data until TTL.

Concrete reproduction (real `SqliteDb`, default PK `id`, non-unique write key `grp`):

```
rows: id=1 grp=G nombre=A, id=2 grp=G nombre=B
load(id=1), load(id=2)            -> both PK entries cached
update(keys=["grp"])              -> 2 rows updated
cache after: id=1 entry deleted, id=2 entry STILL PRESENT
load(id=2)                        -> nombre "B"   (DB holds "NUEVO")
```

The test scaffolding masks this: `DDL_PK.rfc` was changed to `TEXT UNIQUE` (`tests/test_cached_model.py:44`, acknowledged in `03-06-SUMMARY.md:88`), so no test exercises a non-unique write key, and the docs now assert "borran esa **única** entrada" (`docs/guide.md:512`, `docs/design/5-security.md:209`, `CHANGELOG.md:106`) — false for multi-row writes.

**Fix:** Resolve **all** affected PKs for a non-PK write key and delete each entry. Sketch:

```python
async def _resolve_pk_values(self, keys) -> list[dict] | None:
    ...
    if write_keys == pk_keys:
        values = {k: getattr(self, k) for k in pk_keys}
        return [values] if all(v is not None for v in values.values()) else None
    if any(getattr(self, k) is None for k in write_keys):
        return None
    # SELECT only the PK columns for EVERY matching row (bound params + scope)
    rows = await type(self).search(keys=..., columns=pk_keys)   # or a dedicated query
    pks = [{k: r[k] for k in pk_keys} for r in rows]
    return pks or None
```

`_invalidate_pk` then deletes every PK in the list. If multi-row invalidation is intentionally out of scope, the write keys must be validated as unique and the limitation documented + tested; the current docs claim otherwise.

### CR-02: Cache is not scoped by `scope()`; the hit path bypasses tenant filtering → cross-tenant read and write

**File:** `encino_orm/model/cached.py:21-25` (`_cache_key_for` has no scope), `:117-129` (hit path returns without consulting `current_scope()`)

**Issue:** The cache key is `sha1(table:[pk=...])` only. The cache-hit path (`:119-129`) returns the cached object before `super().load()` ever applies `current_scope()` (`model.py:675-680`). Therefore:

- Tenant B can read tenant A's row via a cache entry populated by A.
- `Model.update`/`delete` only pre-check existence through `self.load(keys=keys)` (`model.py:699-702`, `:737-740`) — which is `CachedModel.load`, so a cache hit reports `__exists=True` and the subsequent `UPDATE ... WHERE id=?` (no scope predicate) succeeds across tenants.

Concrete reproduction:

```
row: id=1 tenant=A nombre="secreto-A"
tenant A: with scope(tenant=A): Item(rfc="R1").load(keys=["rfc"])   # canonical entry [id=1] written
tenant B: with scope(tenant=B): Item(id=1).load()   -> nombre "secreto-A", __exists True
tenant B: with scope(tenant=B): Item(id=1, nombre="PWNED").update() -> count 1; DB row now PWNED
control (cache=None): tenant B update -> FailOnUpdate
```

The control proves the cache hit is the enabler of the cross-tenant write. This is pre-existing (a PK read by A already cached under `[id=1]`), but the canonical-domain change makes **every** read — including non-PK reads — populate the shared PK entry, so the exposure surface is broadened. The new docs assert the resolution is "con `scope`" (`docs/guide.md:512`, `docs/design/5-security.md:209`), which is true only on the miss path; the hit path and the key itself are scope-blind.

**Fix:** Namespace the cache key by the active scope, e.g. include a stable fingerprint of `current_scope()` (`filter.to_sql()` fragment + params) in `_cache_key_for`, and/or re-check scope on the hit path. At minimum, the security doc must state that the cache is shared across scopes and that multi-tenant apps must disable `CachedModel` or key the cache externally.

## Warnings

### WR-01: WR-01 residual — compare-and-delete can still delete a foreign pending row (ownership is a local boolean, not a row identity)

**File:** `encino_orm/migration.py:92` (`inserted = True`), `:99`, `:106-109`

**Issue:** `inserted` records that *this call once inserted a row*, not that the row currently present is ours. The compensation deletes on `{name, status='pending'}`. Sequence:

1. Runner A: `INSERT pending` succeeds (`inserted=True`).
2. A's DDL fails **before** the implicit commit (e.g. connection/driver error) → `db.transaction()` rollback removes A's pending row.
3. Runner B: `INSERT pending` succeeds and commits (B's DDL not yet run).
4. A's compensation runs `DELETE ... WHERE name=? AND status='pending'` → **deletes B's row**.

The compare-and-delete therefore does not fully guarantee "a concurrent runner's re-claimed row is never deleted" as `03-07-SUMMARY.md:15,63` claims. The window is narrow and requires a rollback-then-reinsert interleaving, so this is a residual rather than the original bug (the reported duplicate-insert path is genuinely fixed).

**Fix:** Compare-and-delete on the inserted row's identity, not just `(name, status)`. Capture the ledger row id after the INSERT (`db.last_id()` works for MySQL/MariaDB; Oracle's ledger id needs a `RETURNING`/`SELECT` since `last_id()` is 0 there) and delete `{"id": ledger_id}`. If that is not portable, serialize `migrate()` with an advisory lock, or document that concurrent `migrate()` is unsupported.

### WR-02: TOCTOU between the PK probe and the write can invalidate the wrong entry

**File:** `encino_orm/model/cached.py:71` + `:142-144` (probe, then `super().update`)

**Issue:** The probe (`super().load`) and the write run in **separate** transactions unless the caller holds an outer one. Between them another transaction can move the write key to a different row. Example: probe by `rfc="R1"` finds `id=1`; concurrently `id=1.rfc` is changed and `id=2` receives `R1`; `super().update(keys=["rfc"])` then modifies `id=2`, but `_invalidate_pk` deletes `id=1` → `id=2`'s entry stays stale. This is inherent to resolve-then-write, but the round's guarantee ("resolve the affected row's real PK") is stated without qualification.

**Fix:** Resolve the PK inside the same transaction as the write (wrap both in `db.transaction()`), or re-probe after the write and invalidate both candidates. At minimum document the TOCTOU limitation next to the fail-open note.

### WR-03: Docs/CHANGELOG overclaim single-entry invalidation and scope-awareness

**File:** `docs/guide.md:505` ("toda escritura puede invalidar la única entrada posible"), `:512` ("borran esa única clave"), `docs/design/5-security.md:209` ("borra esa única entrada"), `CHANGELOG.md:104-106` ("resuelven la PK real ... antes de invalidar esa única entrada")

**Issue:** The claims are only true when the write keys identify exactly one row and the cache is single-tenant. Both are false in the general case (CR-01, CR-02). The security design doc in particular omits that the cache is not namespaced by `scope()`.

**Fix:** Qualify with "cuando las claves de escritura identifican una sola fila" and add a tenant-isolation caveat (cache key does not include `scope()`; disable `CachedModel` for multi-tenant apps or provide a scoped key).

## Info

### IN-01: Compensation failure masks the original DDL exception

**File:** `encino_orm/migration.py:106-109`

**Issue:** The compensating `async with db.transaction(): await db.execute(delete)` runs inside the `except` block. If it raises (connection lost, etc.), the new exception replaces the root DDL error surfaced to the caller (the original remains only as `__context__`). This is pre-existing structure but the block was rewritten in this round.

**Fix:** Wrap the compensation in `try/except Exception as exc: logger.warning(...)` and re-raise the original, or use `raise <new> from <original>` to preserve an explicit chain.

### IN-02: IN-01 test asserts a docstring substring, not behavior

**File:** `tests/test_migration_reconcile.py:280-282`

**Issue:** `assert "rollback_migration" in (resolve_migration.__doc__ or "")` passes/fails on documentation text and is brittle to any wording change. It is a docs finding, so some doc assertion is defensible, but it does not verify the retry path.

**Fix:** Keep the `reconcile_migrations` error-text test; replace/augment this one with a behavioral test that `resolve_migration(applied=True)` on a `rolling_back` row leaves it `applied` (already covered by `test_rolling_back_true_restaura_applied`) and assert the documented follow-up only where it is load-bearing.

### IN-03: Test scaffolding hides the multi-row gap; delete test lacks a post-delete assertion

**File:** `tests/test_cached_model.py:44` (`rfc TEXT UNIQUE`), `:262-276` (delete test)

**Issue:** The `UNIQUE` addition (acknowledged in `03-06-SUMMARY.md:88`) means no test uses a non-unique write key, so CR-01 cannot be caught. Also `test_cr01_delete_without_instance_pk_invalidates_pk_entry` asserts only that the cache entry is gone — not that the row was deleted or that a subsequent read reflects it.

**Fix:** Add a regression test with a non-unique write key asserting **all** affected PK entries are invalidated (this test will fail until CR-01 is fixed). Strengthen the delete test to assert `getattr(await load(...), "__exists") is False` / row count.

---

## Verified Guarantees (TRUE)

- **CR-01 canonical domain (single-row / unique write keys):** `load(keys=<non-PK>)` never writes a non-PK key and writes only the PK key; verified in code (`cached.py:103-138`) and by `test_cr01_non_pk_read_caches_under_pk_only`.
- **CR-01 write invalidation from an instance without the PK:** `update`/`delete`/`upsert` with `id=None` resolve the real PK and delete that entry. 5 new tests RED on `09d8f56`, GREEN on HEAD (verified in an isolated worktree).
- **Fail-open preserved:** `_invalidate_pk` wraps both key derivation and `cache.delete` in `try/except` (`cached.py:97-101`); `test_invalidate_fail_open` passes. This also closes the original **WR-02**.
- **`insert_many(cache=)` and `_cache_key_for` intact:** unchanged; `test_insert_many_invalidates` / `..._without_cache_...` pass.
- **WR-01 reported duplicate-insert scenario:** no DELETE is emitted when the INSERT fails (`inserted` stays `False`); verified by `test_insert_duplicado_no_borra_la_fila_ajena` (RED→GREEN) and by the emitted compare-and-delete `{name, status: pending}` in `test_compensacion_borra_solo_la_fila_pending_propia`.
- **Compare-and-delete SQL fidelity:** real `build_delete` joins all keys with `AND` (`dialects/builders.py:176-186`); the fake ledger models this faithfully (`test_migration_reconcile.py:107-116`), so the test cannot pass while production emits a single-key delete.
- **IN-01 docs:** both `resolve_migration.__doc__` and the `reconcile_migrations` error text name `rollback_migration`. The documented retry is safe **iff** the `down` did not run (the text says so explicitly); re-emitting `rollback_migration` requires status `applied`, restores `rolling_back`, and its own failure compensation restores `applied`, so the sequence is repeatable.
- **Docs anchor:** `#54-cache-opcional` matches Python-Markdown's default `toc` slugify (accents stripped); the commit `2058f92` corrected a genuinely broken anchor.
- **Test suite:** `uv run pytest tests/test_cached_model.py tests/test_redis_cache.py tests/test_migration_reconcile.py -q` → `33 passed`.

## Status of Earlier Findings

| Finding | Status |
|---------|--------|
| **CR-01** (cache key domain mismatch) | **CLOSED** for the reported single-row/`id=None` scenario; **new residuals CR-01 (multi-row) and CR-02 (scope) remain**. |
| **WR-01** (compensation deletes unowned ledger row) | **CLOSED** for the reported duplicate-insert scenario; **residual ownership race remains** (WR-01 above). |
| **WR-02** (`_invalidate` fail-open does not cover key derivation) | **CLOSED** (`_invalidate_pk` derivation inside `try`). |
| **IN-01** (`resolve_migration` omits retry instruction) | **CLOSED** (docstring + reconcile error text). |
| **IN-02** (misleading "quedó en pending" warning on non-DDL `up`) | **STILL OPEN** — `migration.py:110-116` unchanged, out of this round's scope. |
| **IN-03** (`MemoryCacheBackend(max_size<=-1)` raises `KeyError`) | **STILL OPEN** — `cache_backend.py:42-43` unchanged, out of this round's scope. |
| **IN-04** (redundant ledger bootstrap) | **STILL OPEN** — out of this round's scope. |

---

_Reviewed: 2026-09-18_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
