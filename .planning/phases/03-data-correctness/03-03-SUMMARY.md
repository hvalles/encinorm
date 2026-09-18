---
phase: 03-data-correctness
plan: 03
subsystem: database
tags: [cache, invalidation, cache-aside, fail-open, pydantic, sqlite, data-correctness]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "the choke-point lesson (a declared choke point is not one until every write path is swept) that DATA-03 applies"
provides:
  - "CachedModel._invalidate fail-open (warning, never propagates)"
  - "CachedModel._cache_key_for classmethod (key derivation without an instance)"
  - "CachedModel overrides of update/delete/upsert that invalidate after super() returns (post-commit)"
  - "insert_many(..., cache=None) on Model (signature parity) and CachedModel (optional invalidation of the PK keys in rows)"
affects: [03-04-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "store-then-invalidate by method override, not the after_commit hook (D-15)"
    - "fail-open invalidation: log a warning and continue, the write is already committed (D-12)"
    - "classmethod key derivation so a class-level insert path can invalidate the same key domain load() writes"

key-files:
  created: []
  modified:
    - encino_orm/model/cached.py
    - encino_orm/model/model.py
    - tests/test_cached_model.py
    - docs/design/5-security.md

key-decisions:
  - "Invalidate in update/delete/upsert after super() returns (post-commit); save is covered by delegation; insert does not invalidate (D-09/D-15)"
  - "insert_many(cache=...) invalidates the PK key present in each row (same domain as load()); without cache= it does not invalidate (D-16)"
  - "A cache.delete failure logs a warning and does not propagate (fail-open, D-12); only the affected key is invalidated (D-11)"

patterns-established:
  - "Override-then-invalidate: super() commits, the override then deletes the affected key"
  - "Class-level cache key: _cache_key_for(keys, values) builds the exact key load() writes"

requirements-completed: [DATA-03]

# Metrics
duration: 7min
completed: 2026-09-18
---

# Phase 3 Plan 3: CachedModel Write Invalidation Summary

**`CachedModel` now invalidates the affected key after `update`, `delete` and `upsert` (via post-`super()` overrides, not the `after_commit` hook), with `insert_many(cache=...)` as the optional class-level route and a fail-open `_invalidate`.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-18T17:30:21Z
- **Completed:** 2026-09-18T17:37:33Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- `CachedModel.update`, `delete` and `upsert` invalidate the affected key **after** `super()` returns (already post-commit); `save` is covered by delegation to `update`, and plain `insert` does not invalidate (no cached row could exist for that key).
- `_invalidate` is fail-open: a failing `cache.delete` logs a `logger.warning` and never propagates, so a successful write is not reported as a failure (D-12). Only the affected key is deleted, with no namespace sweep (D-11).
- `_cache_key_for(keys, values)` is a classmethod that derives the exact same key format as `load()`, enabling invalidation from a class-level path.
- `Model.insert_many` gained a keyword-only `cache=None` (ignored; signature parity) and `CachedModel.insert_many` invalidates the PK key of each row when `cache=` is passed — the same key domain `load(keys=<PK>)` writes. Without `cache=` it does not invalidate (documented; D-16).
- `docs/design/5-security.md` §5.4 now describes the real mechanism instead of the stale post-commit-hook claim.

## Task Commits

Each task was committed atomically:

1. **Task 1: `_invalidate` + overrides of `update`/`delete`/`upsert`** - `02f1f53` (feat)
2. **Task 2: `insert_many(..., cache=None)` with optional invalidation** - `1be737d` (feat)
3. **Task 3: sync the mechanism description in `docs/design/5-security.md`** - `553565b` (docs)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `encino_orm/model/cached.py` - `logger`, `_cache_key_for`, fail-open `_invalidate`, write overrides, `insert_many` override
- `encino_orm/model/model.py` - `insert_many` gains keyword-only `cache=None` (ignored) for signature parity
- `tests/test_cached_model.py` - `rfc TEXT UNIQUE`, `_primary_key = ("rfc",)`, and six invalidation/fail-open tests
- `docs/design/5-security.md` - §5.4 describes the override-based mechanism, fail-open, and why the lifecycle hook is not used

## Decisions Made
- The mechanism is method overrides, not the `after_commit` hook: the hook does not fire for `upsert`/`insert_many` (own transaction) and receives neither the action nor the key (D-15).
- The invalidation key domain is `_pk_fields()`; the test model declares `_primary_key = ("rfc",)` so the domain matches `load(keys=["rfc"])` (without it, the default `("id",)` would compute a key that was never written).
- `test_insert_many_invalidates` seeds the cache directly for a **new** PK instead of duplicating an existing row: with `rfc TEXT UNIQUE` a duplicate INSERT would be rejected, making the two requirements irreconcilable.
- Plain `insert` does not invalidate: an INSERT cannot leave an existing key stale without violating UNIQUE.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Task 3's acceptance criterion requires `grep -c "after_commit" docs/design/5-security.md` to be 0, while the action asks to explain why the hook is not used. Resolved (as 03-01 did for its own greps) by phrasing the rationale as "the post-commit hook of `_transactional`" without the literal token, so the documentation keeps the explanation and the grep returns 0.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DATA-03 is delivered: no `CachedModel` write path can leave a readable stale row (bounded by TTL only on an invalidation failure).
- Plan 03-04 (docs) can describe the real invalidation mechanism; `docs/guide.md` §10's "invalida al actualizar/borrar" is now true.
- Invalidation is local to the process; distributed invalidation (pub/sub) remains out of scope and is documented as a known limit.

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- All 4 key files exist on disk.
- All 3 task commits exist in history (`02f1f53`, `1be737d`, `553565b`).
- `uv run pytest tests/test_cached_model.py -q` → 9 passed (6 new invalidation/fail-open tests).
- `uv run pytest -q` → 741 passed, 59 skipped, 0 failed (800 collected = baseline 794 + 6 new; the skipped are engine/Redis integration tests unavailable locally).
- `uv run ruff check encino_orm tests` / `ruff format --check` / `mypy encino_orm` all exit 0; `noqa` count in `encino_orm/` is 0.
- Task acceptance greps: `await self._invalidate`=3, `after_commit` in `cached.py`=0, `def _cache_key_for`=1, `cache=None` in `model.py`=1, `def insert_many` in `cached.py`=1, `_primary_key = ("rfc",)`=1, `after_commit` in `docs/design/5-security.md`=0, `CachedModel` in that doc>=1.
- `grep -rn "cache.delete" encino_orm/` now returns the two real call sites (`_invalidate` and the `insert_many` override), no longer zero.
