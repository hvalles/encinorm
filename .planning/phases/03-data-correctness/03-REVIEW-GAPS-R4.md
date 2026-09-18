---
phase: 03-data-correctness
reviewed: 2026-09-18T22:05:00Z
depth: deep
scope: gap-closure round 4 (d9369aa..HEAD, 91f6dc2)
files_reviewed: 7
files_reviewed_list:
  - encino_orm/model/model.py
  - encino_orm/model/cached.py
  - tests/test_scope_softdelete.py
  - tests/test_cached_model.py
  - CHANGELOG.md
  - docs/guide.md
  - docs/design/5-security.md
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 3: Gap-Closure Round 4 Code Review Report

**Reviewed:** 2026-09-18T22:05:00Z
**Depth:** deep (cross-file call-chain tracing + runtime reproduction on real `SqliteDb`)
**Range:** `d9369aa..HEAD` (`91f6dc2`)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Round 4 delivers the two code fixes it promised and they are genuine RED→GREEN:

- **SEC-01 / CR-R3-01** (`_scoped_dml` in `Model.update`/`delete`): verified correct for all three
  DML branches (`do_update`, `do_delete` physical, `do_delete` logical). Placeholder contiguity,
  `ignore_duplicated` preservation, scope read inside the retried closure, and the no-scope
  byte-identity path all hold. Reproduced at runtime: physical delete and scope-field updates no
  longer cross tenants.
- **WR-R3-02** (`_union` hashable + `_invalidate_after_write`): the pre-fix code fails with
  `TypeError: unhashable type: 'list'` after the commit (verified by running the new test against a
  `d9369aa` worktree); it passes after.

However, the round-4 **claim that WR-R3-01 is "resuelto por construcción"** is not true. The
`CachedModel` pre-write probe (`_resolve_pk_values`) builds its `WHERE` from the **raw** non-PK
value while the DML writes the **serialized** value. For non-PK write keys of type
`datetime`/`Decimal`/`list`/`dict`, the probe matches no row (or raises and is swallowed), so the
cache entry is **never invalidated** — the exact stale-read symptom CR-01/WR-R3-01 were meant to
close. Reproduced at runtime (see CR-R4-01). This is a round-3 residual, but round 4 explicitly
claims it closed and the docs repeat the claim, so it is in scope.

Everything else (non-scoped byte-identity, docs re wording of WR-R3-03/04, `last_id()` note,
deterministic-filter note) is accurate, with one stale planning artifact left behind
(STATE.md:168).

Full suite: `845 passed` (10 snapshots). `ruff check` / `ruff format --check` / `mypy` all clean.

## Critical Issues

### CR-R4-01: `CachedModel` probe does not serialize non-PK write keys → cache never invalidated after a committed write (stale reads)

**File:** `encino_orm/model/cached.py:84-94` (probe), compared with `encino_orm/model/model.py:736` (DML key) and `:692` (`load` key)
**Related claims:** `.planning/phases/03-data-correctness/03-11-SUMMARY.md:67` ("WR-R3-01 resuelto por construcción: la sonda y la escritura ven el mismo conjunto de filas"), `docs/guide.md:513-520`, `docs/design/5-security.md:212-220`

**Issue:** `_resolve_pk_values` builds the multi-row probe with the **raw** attribute value:

```python
# encino_orm/model/cached.py:87-89
for k in write_keys:
    eq = Filter.eq(k, getattr(self, k))     # <-- raw value, NO _serialize
    cond = eq if cond is None else cond & eq
```

but the DML it is compensating for binds the **serialized** value
(`model.py:736`: `key_dict[self._col(k)] = _serialize(val)`), and `Model.load`'s pre-check also
serializes (`model.py:692`). `Filter`/`search` never serialize (only `_col`/`_serialize` do), so:

- `datetime`/`date` columns are stored as TEXT (`_serialize` → `isoformat(sep=" ")`); binding a
  `datetime` object matches nothing.
- `Decimal`/`list`/`dict` columns are stored as TEXT/JSON; binding the Python object raises
  (`Error binding parameter ... type 'decimal.Decimal' is not supported` / `type 'list' is not
  supported`), which the broad `except Exception` at `cached.py:101-107` swallows and returns
  `None`.

In both cases `_resolve_pk_values` returns `None`, `_invalidate_pks` returns early
(`cached.py:155-156`), and the row's cached entry survives a **committed** write. The next
`load(keys=<PK>)` serves the pre-write row until the TTL (default 300 s). For a soft-delete by such
a key, a deleted row stays visible — a correctness/visibility defect, not merely a perf issue.

**Reproduction (real `SqliteDb`, `CachedModel`, no scope needed):**

```python
when = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
await Ev(d, cache=cache, slug="s1", cuando=when, nombre="Viejo").insert()
loaded = await Ev(d, cache=cache, slug="s1").load(keys=["slug"])
pk_key = loaded._cache_key(("id",))
await Ev(d, cache=cache, cuando=when, nombre="Nuevo").update(keys=["cuando"], data=["nombre"])
# DB row:  {'id': 1, 'nombre': 'Nuevo'}      (write committed, count=1)
# cache:   still b'... "nombre": "Viejo" ...'  (NOT invalidated)
```

Measured breadth: `datetime` → not invalidated; `Decimal` → not invalidated (warning logged);
`list` → not invalidated (warning logged); `date` → happened to match on this Python build but is
not guaranteed (deprecated default adapter). Scalar `str`/`int` non-PK keys are unaffected, which
is why the existing suite is green.

**Fix:** serialize the probe value exactly as the DML does, e.g.:

```python
from .model import _serialize  # already imported in module scope of model.py; import in cached.py

for k in write_keys:
    eq = Filter.eq(k, _serialize(getattr(self, k)))
    cond = eq if cond is None else cond & eq
```

Then add a regression that uses a `datetime` (or `Decimal`) non-PK write key and asserts the cached
PK entry is gone after `update`/`delete` (this test fails today).

## Warnings

### WR-R4-01: No regression covers the physical-delete branch under `scope()` although SEC-01 changed it

**File:** `encino_orm/model/model.py:776-779` (physical branch) vs `tests/test_scope_softdelete.py:174-185`

**Issue:** The round-4 plan states SEC-01 covers `do_update`, `do_delete` physical **and**
`do_delete` logical, but the only delete regression added is the logical one
(`test_cr_r3_01_delete_no_cruza_tenant` calls `delete(keys=["grupo"])` with the default
`physical=False`). A future refactor could drop `_scoped_dml` from the `physical` branch
(`model.py:778-779`) without any test failing. I verified the branch works today via a manual probe
(only the in-scope row is deleted), so this is a coverage gap, not a live bug.

**Fix:** add a test mirroring the logical one with `physical=True` and assert the out-of-scope row
still exists in the table (`fetch_one` on its `id`).

### WR-R4-02: `_invalidate_after_write` does not structurally guarantee "never raises" — only the `_union` call is guarded

**File:** `encino_orm/model/cached.py:141-146` (`_invalidate_after_write`), `:155-165` (`_invalidate_pks`)

**Issue:** The docstring/SUMMARY claim the helper means a committed write can never be reported as
failed ("no puede fallar una escritura commiteada", "nunca falla"). The `try/except` wraps only
`self._union(*probe_lists)`. The subsequent `await self._invalidate_pks(pks)` is unguarded, and
inside it `if any(v is None for v in values.values())` (`:159`) and
`pk_keys = list(type(self)._pk_fields())` (`:157`) run **outside** the per-key `try`. A probe that
ever yields a non-dict entry would raise `AttributeError`/`TypeError` out of the helper, after the
commit. Today every producer (`_resolve_pk_values`, `_union`, the fallback comprehension) yields
`dict`s, so this is latent — but the documented fail-open boundary is not enforced by construction.

**Fix:** move the guard to the whole invalidation step, e.g. wrap the `await self._invalidate_pks(...)`
call in the same `try`, or make `_invalidate_pks` defensive (`for values in pk_values: if not
isinstance(values, dict): continue`) so the boundary is structural rather than incidental.

### WR-R4-03: Stale planning artifact contradicts the corrected `last_id()` note (IN-R3-01)

**File:** `.planning/STATE.md:168`

**Issue:** Round 4 fixed `CHANGELOG.md` so the compensation fallback no longer names Oracle
("Si `last_id()` falla (o no expone un id utilizable)…"), but the decision log still asserts the old,
disproven rationale: *"fallback {name, status: pending} para Oracle (last_id()==0)"*. It directly
contradicts the corrected CHANGELOG and the round-3 finding IN-R3-01. Planning artifacts are the
project's durable context, so this will re-seed the inaccuracy in later phases.

**Fix:** reword `STATE.md:168` to match the CHANGELOG (fallback covers a failed/unusable
`last_id()`, not Oracle specifically).

## Info

### IN-R4-01: Stale RED docstring left in a GREEN test

**File:** `tests/test_cached_model.py:457-462`

**Issue:** The docstring of `test_wr_r3_02_union_no_rompe_fail_open` still says *"HOY lanza
`TypeError: unhashable type: 'list'` DESPUÉS del commit"* — that describes the pre-fix RED state and
is now false, misleading future readers about what the test asserts.

**Fix:** drop the "HOY lanza…" sentence; keep the description of the guaranteed post-fix behavior.

### IN-R4-02: The `_invalidate_after_write` fallback branch is never exercised

**File:** `encino_orm/model/cached.py:143-145`

**Issue:** The new `except Exception` fallback (concatenate the probes) is dead in the test suite:
with the `repr` fingerprint in place, `_union` no longer raises for `list`/`dict` PKs, so the test
only proves the `repr` path. The fail-open guard itself is untested and could regress silently.

**Fix:** add a small unit test that monkeypatches `CachedModel._union` to raise and asserts the
committed write still succeeds and `_invalidate_pks` is still called (e.g., via a spy backend).

---

## Verified Guarantees (TRUE)

- **`_scoped_dml` Query validity:** `build_update` emits `SET` params `0..len(set)-1` then `WHERE`
  params contiguously (`dialects/builders.py:169-173`); `build_delete` likewise (`:184-186`). The
  helper shifts the scope fragment by exactly `len(qry.fields)` and concatenates
  `qry.fields + sparams`, so the new `Query`'s cardinality contract revalidates (`query.py:58-67`).
  `ignore_duplicated` is carried over (`model.py:127-131`). No builder/adapter change — works for
  all six engines (the appended clause is plain SQL and adapters compile placeholders generically).
- **No-scope byte identity:** `_scoped_dml` is only reached when `current_scope() is not None`
  (`model.py:747-749`, `:775-783`); the no-scope `Query` is the builder's object untouched. Control
  test `test_cr_r3_01_sin_scope_sigue_sin_acotar` and the 845-pass suite (10 snapshots) confirm.
- **Scope read inside the retried closure:** `current_scope()` is called inside `do_update`/
  `do_delete` (`model.py:747`, `:775`), so a `_transactional` retry re-reads the ambient scope.
- **SEC-01 / CR-R3-01 (update + logical delete):** `a722648` tests are true RED→GREEN — run against
  a `d9369aa` worktree they fail (`'PWNED' == 'B1'`, `False is True`), pass at HEAD.
- **Physical delete under scope:** manual runtime probe → only the in-scope row removed
  (`remaining: [{'id': 2, 'tenant_id': 2}]`); scope-field self-update only touches the in-scope row.
- **Pre-check `load` vs scoped DML consistency:** both use the same predicate (write key
  serialized via `_serialize` + scope mapped via `_column_map`), so `FailOnUpdate` (count==0) and
  the early `delete` no-op cannot disagree for scalar keys.
- **WR-R3-02:** `repr` fingerprint is stable and collision-free for DB scalar PKs (`repr(1)`≠
  `repr("1")`), and is strictly *more* precise than the old value tuple (which merged `1` and
  `1.0`). `test_wr_r3_02_...` is a true RED→GREEN (verified on the base worktree).
- **WR-R3-03:** `CHANGELOG.md:14-19` now says the cache no longer **enables** a cross-tenant write
  and points to SEC-01 for the actual DML closure; the contradictory "única entrada" bullet is gone
  (`:132-142` now says "sus entradas"). No remaining "escritura cruzada cerrada" overclaim.
- **WR-R3-04:** writer/reader same-`scope()` residual documented in `docs/guide.md:532-539` and
  `docs/design/5-security.md:228-234`.
- **IN-R3-03:** deterministic-filter caveat documented (`guide.md:527-530`, `5-security.md:236-239`).
- **Upsert residual:** explicitly documented (`guide.md:541-546`, `5-security.md:241-244`) — the
  round-4 docs do **not** overclaim upsert isolation.
- **Empty scope fragment / empty key set:** `scope(Filter.raw("", []))` and `keys=[]` already fail
  earlier in `load` (`model.py:694-702`) / the builder, so `_scoped_dml` introduces no new
  invalid-SQL path.
- **No debug artifacts / dead imports** in the changed source; `ruff`, `ruff format --check`, and
  `mypy` are clean.

## Status of Round-4 Findings

| Finding | Status |
|---------|--------|
| **CR-R3-01 / SEC-01** (scope on `update`/`delete` DML) | **CLOSED** for scalar keys; verified RED→GREEN + runtime physical/logical/self-field probes. |
| **WR-R3-01** (probe under-covers the write) | **NOT CLOSED — residual**: the probe does not serialize non-PK write values, so `datetime`/`Decimal`/`list`/`dict` write keys leave the cache stale (CR-R4-01). |
| **WR-R3-02** (`_union` fail-open) | **CLOSED** for the `repr` path; the `except` fallback is untested (IN-R4-02). |
| **WR-R3-03** (CHANGELOG overclaim) | **CLOSED.** |
| **WR-R3-04** (writer/reader scope) | **CLOSED** (documented). |
| **IN-R3-01** (Oracle `last_id()`) | **PARTIAL**: CHANGELOG fixed, `.planning/STATE.md:168` still stale (WR-R4-03). |
| **IN-R3-02** (non-PK regression) | **CLOSED** for update + logical delete; physical-delete branch still untested (WR-R4-01). |
| **IN-R3-03** (deterministic digest) | **CLOSED** (documented). |

---

_Reviewed: 2026-09-18T22:05:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
