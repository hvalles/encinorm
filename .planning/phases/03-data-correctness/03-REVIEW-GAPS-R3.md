---
phase: 03-data-correctness
reviewed: 2026-09-18T21:05:00Z
depth: deep
scope: gap-closure round 3 (c8f440d..HEAD, 26d2b75)
files_reviewed: 7
files_reviewed_list:
  - encino_orm/model/cached.py
  - encino_orm/migration.py
  - tests/test_cached_model.py
  - tests/test_migration_reconcile.py
  - docs/guide.md
  - docs/design/5-security.md
  - CHANGELOG.md
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 3: Gap-Closure Round 3 Code Review Report

**Reviewed:** 2026-09-18T21:05:00Z
**Depth:** deep (cross-file call-chain tracing + runtime reproduction)
**Range:** `c8f440d..HEAD` (`26d2b75`)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Round 3 correctly closes the *narrow* forms of the reported findings, and I verified the new
regressions are genuine RED→GREEN (reasoning below; full suite `841 passed`, targeted suites
`37 passed`).

What is **not** closed is the interaction between the round-3 cache fix and `scope()`:

- **CR-01 multi-row is closed only without a `scope()`.** With a scope active, `_resolve_pk_values`
  resolves only the caller's tenant, while `super().update`/`delete` still write **all** tenants'
  matching rows (the core DML does not carry the scope predicate). Verified at runtime: T1's
  `update(keys=["grupo"])` modified T2's row and left T2's cache stale (`B` vs DB `PWNED`).
- The root cause is a pre-existing **cross-tenant write** in `Model.update`/`Model.delete` for
  non-PK write keys, which the round-3 CHANGELOG/security doc now claims is closed.
- `_union` is a new, unguarded step in the invalidation path that breaks the documented D-12
  fail-open guarantee for list/dict-valued PKs (verified: `TypeError` after the commit).

All migration-side claims (WR-01 identity compensation, IN-01 root-exception preservation, IN-02
behavioural test) hold, with one doc inaccuracy about Oracle's `last_id()`.

## Critical Issues

### CR-R3-01: `scope()` is not applied to `update`/`delete` DML → cross-tenant modification and deletion for non-PK write keys

**File:** `encino_orm/model/model.py:724-729` (`do_update`), `encino_orm/model/model.py:748-753` (`do_delete`)
**Related round-3 code:** `encino_orm/model/cached.py:90-100` (the probe that assumes the write is scope-bounded), `CHANGELOG.md:16-17`, `docs/design/5-security.md:206-207`

**Issue:** `Model.update`/`Model.delete` only *pre-check* scope existence with `self.load(keys=keys)`
(`model.py:699-702`, `:737-740`); the executed DML is `UPDATE/DELETE ... WHERE <key_dict>` with
**no scope predicate**. When `keys` is a non-PK (non-unique) column, every matching row across every
tenant is modified. This is pre-existing, but round 3 (a) claims CR-02 closed "la lectura cruzada y
la escritura cruzada de tenant" and (b) builds `_resolve_pk_values` on the premise that the write
affects exactly the rows `search` returns — which is false under scope.

**Reproduction (real `SqliteDb`, plain `Model`, no cache needed):**

```
rows: id=1 tenant=1 grupo=G titulo=A1, id=2 tenant=2 grupo=G titulo=B1
with scope(Filter.eq("tenant_id", 1)):
    await Doc(d, grupo="G", titulo="PWNED").update(keys=["grupo"])
# -> update count = 2 ; row 2 (tenant 2) titulo == "PWNED"   (cross-tenant write)
with scope(Filter.eq("tenant_id", 1)):
    await Doc(d, grupo="D").delete(keys=["grupo"])
# -> both tenant 1 and tenant 2 rows with grupo=D get enabled=False
```

The same call on `CachedModel` under `scope(T1)` updates 2 rows (T1 + T2) and leaves T2's cached
entry stale (`T2 cached view: B` vs `T2 DB truth: PWNED`), i.e. it also breaks CR-01's "TODAS las
filas afectadas" guarantee.

**Fix:** apply the active scope to the DML WHERE clause, not just to the pre-check. Build the
`WHERE` from `key_dict` **AND** `current_scope().map_fields(self._column_map()).to_sql()` (bound
params, as `search` does), or route the write through a `Query` that includes the scope fragment.
Once the write is scope-bounded, the round-3 probe and the write see the same row set.

## Warnings

### WR-R3-01: CR-01 multi-row invalidation is incomplete under `scope()` → stale tenant cache after a cross-tenant write

**File:** `encino_orm/model/cached.py:90-100` (`self.search(filter=cond, include_deleted=True)`), `:187-226` (write paths)
**Issue:** `_resolve_pk_values` reuses `Model.search`, which applies `_effective_filter` (scope
included). The write it is compensating for does **not** apply scope (CR-R3-01), so the probe
under-covers: rows written outside the caller's tenant are never invalidated. This is a direct
residual of the CR-01 fix, independent of the security impact of CR-R3-01.
**Reproduction:** see CR-R3-01 (cached variant): after T1's `update(keys=["grupo"])`, T2's cached
entry still returns `B` while the DB holds `PWNED`.
**Fix:** fix CR-R3-01 so the write is scope-bounded (probe then matches the write). If cross-tenant
writes are intended, `_resolve_pk_values` must resolve the affected PKs **without** the scope
predicate (e.g. a dedicated bound query on the raw key columns) and invalidate them in every
scope namespace, which is impossible with a scope-namespaced key — another reason to scope the DML.

### WR-R3-02: `_union` is not fail-open — `TypeError` after a committed write for unhashable PK values

**File:** `encino_orm/model/cached.py:109-128` (`_union`), called at `:198`, `:211`, `:225` outside any `try`
**Issue:** `_union` does `seen.add(tuple(sorted(item.items())))`. For a PK whose field type is
`list`/`dict` (pydantic allows it; `_from_db` JSON-decodes it at `model.py:310-311`), the value is
unhashable and `seen.add` raises `TypeError`. `_resolve_pk_values` and `_invalidate_pks` are
individually wrapped in `try/except`, but `_union` is not, so the exception propagates **after the
write is committed**, violating the documented D-12 fail-open ("la escritura ya está commiteada:
propagar daría un fallo falso al llamador").
**Reproduction (real `SqliteDb`):** a `CachedModel` with `_primary_key=("k",)`, `k: list`; after
`load()` and a committed `update()`, `update()` raises `TypeError: unhashable type: 'list'` while
the DB row already holds the new value.
**Fix:** make the fingerprint hashable and guard the call, e.g.
`fingerprint = tuple(sorted((k, repr(v)) for k, v in item.items()))`, and/or wrap
`self._union(...)` in `try/except Exception` with a warning so the invalidation path can never fail
a committed write.

### WR-R3-03: CHANGELOG/security doc overclaim "cross-tenant write closed" and contradict the retained "única entrada" bullet

**File:** `CHANGELOG.md:16-17`, `CHANGELOG.md:119` vs `CHANGELOG.md:131-138`, `docs/design/5-security.md:206-207`
**Issue:** (a) "cerrando la lectura cruzada y **la escritura cruzada de tenant** (CR-02)" and "ni la
escritura cruzada se habilita" read as "cross-tenant writes are prevented". They are not (CR-R3-01):
the cache no longer *enables* one, but a non-PK `update`/`delete` crosses tenants regardless of the
cache. (b) The `[Unreleased]` section still contains the round-2 bullet "antes de invalidar esa
**única** entrada" (`:119`) alongside the new "TODAS las filas afectadas" bullet (`:131`), a direct
contradiction. `docs/guide.md:522-527` is the only place phrased correctly ("ni como habilitador de
una escritura cruzada").
**Fix:** reword to "el acierto de caché ya no habilita una escritura cruzada" and state explicitly
that non-PK writes under `scope()` still cross tenants until CR-R3-01 is fixed; supersede/rewrite
the `:119` bullet.

### WR-R3-04: A write under a different (or no) scope cannot invalidate scoped entries

**File:** `encino_orm/model/cached.py:23-36` (`_cache_key_for`), `docs/guide.md:522-527`, `docs/design/5-security.md:224-226`
**Issue:** Because the key is namespaced by the *writer's* `current_scope()`, a legitimate
same-row update performed outside the reader's scope (e.g. an admin/maintenance path, or simply
without `scope()`) deletes only the unscoped key and leaves every scoped entry stale until TTL.
The docs only warn that an unscoped **read** shares the entry; the write-side consequence is
undocumented.
**Fix:** document that writers must run under the same `scope()` as readers (or invalidate all
namespaces / disable `CachedModel` for multi-tenant apps). Optionally provide a
`scope=all`/namespace-scan invalidation hook.

## Info

### IN-R3-01: "Oracle devuelve 0" is inaccurate — Oracle's ledger INSERT returns a usable `last_id()`

**File:** `encino_orm/migration.py:104`, `CHANGELOG.md:144`, `03-09-SUMMARY.md:15`
**Issue:** The docstring/CHANGELOG assert the fallback exists for Oracle because `last_id()==0`.
But `ORACLE_INSERT.returning_id=True` (`encino_orm/dialects/strategies.py:41-46`) makes the ledger
INSERT (no `id` column in `data`) emit `RETURNING id INTO :ret_id`
(`encino_orm/dialects/builders.py:145-146`), and the ledger id is
`NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY` (`encino_orm/oracle.py:341`), so `_last_id` is set
and the identity branch is taken. The fallback is effectively dead for all six engines and only
reachable when `db.last_id()` itself raises. The residual is narrower than documented, not wider —
but the claim is wrong.
**Fix:** state that the fallback covers a failed `last_id()` (best-effort degradation), not Oracle
specifically, or name the engine that actually returns 0.

### IN-R3-02: No regression covers the non-PK cross-tenant write hole

**File:** `tests/test_cached_model.py:381` (`test_cr02_scope_bloquea_escritura_cruzada`)
**Issue:** The only "cross-tenant write" test writes by the **PK** (`update()` with default keys), so
it exercises the cache-hit enabler only. No test uses a non-unique write key under `scope()`, which
is exactly the path CR-R3-01/WR-R3-01 exploit — the same scaffolding gap round 2 flagged for CR-01.
**Fix:** add a regression that, under `scope(tenant=1)`, runs `update(keys=["grupo"])` and asserts
tenant 2's row is unchanged (this test fails until CR-R3-01 is fixed).

### IN-R3-03: `Filter.digest()` is order-nondeterministic for set-built scope filters

**File:** `encino_orm/model/filter.py:158-166` (`digest`), used by `cached.py:35`
**Issue:** `Filter.in_(field, values)` stores `tuple(values)`; a `set` yields a
`PYTHONHASHSEED`-dependent order, so the same scope produces different cache keys in different
processes. This is only a robustness note (multi-process invalidation is already documented as
unsupported) but it makes the "stable fingerprint" claim in `_cache_key_for`'s docstring too strong.
**Fix:** normalize `in_` inputs (sorted when comparable) before hashing, or document that scope
filters must be deterministic.

---

## Verified Guarantees (TRUE)

- **CR-01 multi-row (no scope):** `_resolve_pk_values` returns every matching PK and
  `_invalidate_pks` deletes each; `test_cr01_multifila_invalida_todas_las_pks` fails on the
  pre-fix single-row probe and passes now. Verified in code and at runtime.
- **CR-02 cache-hit read isolation:** the scope digest is part of the key (`cached.py:33-35`);
  `test_cr02_scope_no_aislado_no_sirve_otro_tenant` is a true regression (old key was scope-blind).
- **CR-02 cache-hit write-enabler closed (PK keys):** `test_cr02_scope_bloquea_escritura_cruzada`
  passes because tenant B's `load(id=1)` misses and `Model.update` raises `FailOnUpdate`.
- **CR-02 key compatibility:** with no scope the raw string is byte-identical to the old format
  (`cached.py:33-35`), and `insert_many(cache=)` namespaces consistently (`cached.py:253`).
- **WR-01 identity compensation:** `ledger_id` is captured *after the INSERT and before the DDL*
  (`migration.py:106-109`), so a later promotion/DDL `lastrowid` change cannot corrupt it;
  `PoolDb.last_id()` resolves the same affinity connection as the INSERT
  (`pool.py:300-304`, `:188-196`). `test_wr01_compensacion_no_borra_la_fila_reinsertada` is a true
  RED→GREEN (old compare-and-delete deleted B's row).
- **IN-01 root-exception preservation:** the compensation has its own `try/except Exception` that
  only logs, and the outer bare `raise` re-raises the original (`migration.py:124-135`, `:144`);
  verified by `test_in01_compensacion_fallida_no_enmascara_el_error_raiz`.
- **IN-02:** the `__doc__` substring assertion was removed and replaced with a behavioural
  `reconcile_migrations` no-raise assertion (`test_migration_reconcile.py:344-350`).
- **WR-02 union narrows (does not eliminate) the TOCTOU:** before/after probes are unioned and the
  docs state the residual (`docs/guide.md:529-535`, `docs/design/5-security.md:219-222`). A
  three-transaction interleaving (key moves A→B→C around the write) still leaves the written row
  un-invalidated, consistent with the documented residual.
- **Test health:** `uv run pytest -q` → `841 passed` (10 snapshots); targeted
  `tests/test_cached_model.py tests/test_migration_reconcile.py` → `37 passed`. No debug artifacts
  in the changed source.

## Status of Round-3 Findings

| Finding | Status |
|---------|--------|
| **CR-01** (multi-row invalidation) | **CLOSED without `scope()`**; **RESIDUAL under `scope()`** (WR-R3-01), root cause CR-R3-01. |
| **CR-02** (scope-namespaced cache) | **CLOSED** for the cache-hit read and the PK-key write-enabler; **NOT closed for non-PK cross-tenant DML** (CR-R3-01); overclaimed in CHANGELOG (WR-R3-03). |
| **WR-01** (compensation ownership) | **CLOSED** for engines with a usable `last_id()` (which includes Oracle — IN-R3-01); fallback residual documented and effectively unreachable. |
| **WR-02** (probe/write TOCTOU) | **ACOTADO** — window narrowed by the before/after union, not eliminated; residual documented accurately. |
| **WR-03** (docs overclaim) | **PARTIAL** — multi-row/scope wording fixed, but a new "escritura cruzada cerrada" overclaim and the stale "única entrada" bullet remain (WR-R3-03). |
| **IN-01** (compensation masks root error) | **CLOSED.** |
| **IN-02** (docstring assertion) | **CLOSED.** |

---

_Reviewed: 2026-09-18T21:05:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
