---
phase: 08-release-0-3-0
plan: 08
subsystem: release
tags: [rel-01, last_id, execute_insert, removal, deprecation, pool, base]

# Dependency graph
requires:
  - phase: 08-release-0-3-0
    provides: "08-01 tagged v0.2.7 with the runtime DeprecationWarnings; 08-06 removed the config/security shims"
provides:
  - "Db/PoolDb without the post-hoc last_id() API and without _warn_last_id_deprecated"
  - "tests/test_last_id_removed.py guard (absence of last_id + execute_insert happy path)"
  - "engine + pool tests asserting the absence of last_id instead of its deprecation warning"
affects: [08-03, release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Id capture only via execute_insert(qry) / Model.insert() return; post-hoc last_id() retired"
    - "Private _last_id_value() kept as an internal adapter hook (not public API)"

key-files:
  created:
    - tests/test_last_id_removed.py
  modified:
    - encino_orm/base.py
    - encino_orm/pool.py
    - tests/test_pool.py
    - tests/test_pool_characterization.py
    - tests/test_d_recommendations.py
    - tests/test_sqlite.py
    - tests/test_postgresql.py
    - tests/test_mysql.py
    - tests/test_mariadb.py
    - tests/test_mssql.py
    - tests/test_oracle.py

key-decisions:
  - "Fold PoolDb.last_id() removal into Task 1 as a Rule 3 blocking fix: removing the base helper orphaned its only consumer, and keeping it would leave pool.py unimportable / F821"
  - "Keep the private _last_id_value() hook and the PooledConnection.last_id field (internal, scope-bounded); only the public post-hoc API is retired"
  - "Rewrite TestPoolLastIdScoping as TestPoolExecuteInsertScoping rather than deleting the characterization, so the id-scoping coverage survives under the new API"

patterns-established:
  - "Absence guards assert hasattr(...) is False plus pytest.raises(AttributeError) on access; guard docstrings avoid the retired call literal so the repo-wide grep stays satisfiable"

requirements-completed: [REL-01]

# Metrics
duration: 5min
completed: 2026-09-20
---

# Phase 8 Plan 08: Retire post-hoc last_id() Summary

**Post-hoc `last_id()` removed from `Db` and `PoolDb`; the id is only obtainable via `execute_insert(qry)` or `Model.insert()`, with pool and six-engine tests migrated to absence assertions.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-09-20T04:38:14Z
- **Completed:** 2026-09-20T04:43:09Z
- **Tasks:** 3
- **Files modified:** 12 (1 created, 11 modified)

## Accomplishments
- `_warn_last_id_deprecated()` and `Db.last_id()` are gone from `encino_orm/base.py`; `import warnings` removed as it became unused.
- `PoolDb.last_id()` and its helper import are gone from `encino_orm/pool.py`; the package stays importable and ruff-clean.
- New `tests/test_last_id_removed.py` guards the absence of both methods and pins the `execute_insert` happy path (returns ids 1 then 2 on SQLite `:memory:`).
- The entire `TestPoolLastIdScoping` class was rewritten as `TestPoolExecuteInsertScoping` (5 tests) using `execute_insert`; the `_last_id_value` double comment no longer names the retired method.
- The six engine test files swap `test_last_id_deprecated` for `test_last_id_retirado` (absence), dropping the obsolete PostgreSQL `_reset`/INSERT setup.
- Full suite green under `filterwarnings = ["error"]`: `1124 passed, 38 deselected`.
- Repo-wide guards satisfied: no `.last_id()` in `tests/`, no `def last_id` / `_warn_last_id_deprecated` in `encino_orm/`.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): add failing test for last_id removal** - `e7aa99b` (test)
2. **Task 1 (GREEN): retire Db.last_id and centralized deprecation helper** - `d426d3c` (feat)
3. **Task 2: migrate pool tests off last_id and assert PoolDb removal** - `d2d5227` (test)
4. **Task 3: replace engine last_id deprecation tests with absence assertions** - `c7c30dc` (test)
5. **Guard docstring follow-up (grep literal)** - `d4aceea` (test)

**Plan metadata:** (docs commit, this SUMMARY + STATE/ROADMAP)

_Note: Task 1 followed the RED/GREEN cycle (test commit then feat commit)._

## Files Created/Modified
- `tests/test_last_id_removed.py` - Absence guard for `Db`/`PoolDb.last_id` + `execute_insert` happy path.
- `encino_orm/base.py` - Removed `_warn_last_id_deprecated()` and `Db.last_id()`; dropped `import warnings`; re-documented `_last_id_value()` as internal.
- `encino_orm/pool.py` - Removed `PoolDb.last_id()` and the `_warn_last_id_deprecated` import; updated the `_current_connection` comment to name `execute_insert()`.
- `tests/test_pool.py` - Deleted the two deprecated-last_id tests.
- `tests/test_pool_characterization.py` - Rewrote the scoping class around `execute_insert`; fixed the double's comment.
- `tests/test_d_recommendations.py` - Dropped the `pool.last_id() == 0` assertion.
- `tests/test_sqlite.py`, `tests/test_postgresql.py`, `tests/test_mysql.py`, `tests/test_mariadb.py`, `tests/test_mssql.py`, `tests/test_oracle.py` - `test_last_id_deprecated` → `test_last_id_retirado`.

## Decisions Made
- **Task-boundary deviation (Rule 3):** the base-helper removal orphaned `PoolDb.last_id()`; leaving the method or its import would make `pool.py` unimportable (ImportError) or ruff-fail (F821). The `PoolDb.last_id()` removal was therefore folded into Task 1's GREEN commit, and Task 2 focused on the test migration plus the `PoolDb` absence assertion. Documented as a deviation below.
- **Keep the private hook:** `_last_id_value()` and `PooledConnection.last_id` are internal details, not enumerated breaks; retiring them would force touching all six adapters in this plan (out of scope threshold).
- **Rewrite, don't delete, the pool characterization:** converting `TestPoolLastIdScoping` to `execute_insert` preserves CI-09's id-scoping safety net under the new contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Removed the orphaned `PoolDb.last_id()` in Task 1**
- **Found during:** Task 1 (GREEN — removing `_warn_last_id_deprecated`)
- **Issue:** `encino_orm/pool.py:9` imported `_warn_last_id_deprecated` and `PoolDb.last_id()` called it. Removing the helper from `base.py` made the whole package unimportable (`ImportError`), so Task 1's `uv run pytest tests/test_last_id_removed.py` could not pass. Removing only the import left `PoolDb.last_id` referencing an undefined name (ruff F821).
- **Fix:** Removed `PoolDb.last_id()` and the helper import in the same Task 1 commit, keeping the package importable and ruff-clean. Task 2 then owned the pool/deprecation test migration and the explicit `PoolDb` absence assertion.
- **Files modified:** `encino_orm/pool.py`
- **Verification:** `uv run pytest tests/test_last_id_removed.py -q` → 2 passed; `import encino_orm.pool` succeeds; `not hasattr(PoolDb, "last_id")`.
- **Committed in:** `d426d3c` (Task 1 GREEN)

**2. [Rule 1 - Bug] Guard docstrings matched the repo-wide grep literal**
- **Found during:** Task 3 verification (`grep -rn "\.last_id()" tests/`)
- **Issue:** `tests/test_last_id_removed.py` docstrings wrote `Db.last_id()`/`PoolDb.last_id()`, which the textual acceptance grep flags even though they are prose.
- **Fix:** Rephrased the docstrings to "la API post-hoc `last_id()` de `Db`/`PoolDb`", removing the dot-prefixed literal.
- **Files modified:** `tests/test_last_id_removed.py`
- **Verification:** `grep -rn --exclude-dir=__pycache__ "\.last_id()" tests/` → no matches.
- **Committed in:** `d4aceea`

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Both necessary to keep the package importable and the textual guards satisfiable. The Rule 3 fix moved the `PoolDb.last_id()` production removal from Task 2 into Task 1; the intended end state (no `PoolDb.last_id`) is unchanged.

## Issues Encountered
None beyond the deviations above.

## Out-of-Scope Observation
- `docs/design/0-design.md:410` (`print(await db.last_id())`) and `docs/design/8-pk.md:36` still describe the pre-0.3.0 design. They are historical design docs, outside this plan's `files_modified`; `docs/MIGRATION-0.3.md` intentionally shows the old call as an "Antes" example. No action taken here.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REL-01 retirada is complete: no public post-hoc `last_id()` remains, and the replacement path (`execute_insert` / `Model.insert`) is green across the suite.
- Ready for 08-03 (0.3.0rc1/0.3.0 promotion), which depends on the removals landing before promotion.

---
*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*

## Self-Check: PASSED

- FOUND: tests/test_last_id_removed.py
- FOUND: .planning/phases/08-release-0-3-0/08-08-SUMMARY.md
- FOUND: e7aa99b, d426d3c, d2d5227, c7c30dc, d4aceea
- Full suite: 1124 passed, 38 deselected (`-m "not optional_engine and not benchmark"`)
- Repo-wide guards: no `.last_id()` in `tests/`; no `def last_id`/`_warn_last_id_deprecated` in `encino_orm/`
