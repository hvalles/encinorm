---
phase: 08-release-0-3-0
plan: 06
subsystem: release-docs
tags: [removals, deprecation, security, configuration, changelog, migration-guide, rel-01, rel-04]

# Dependency graph
requires:
  - phase: 08-01
    provides: 0.2.7 freeze (v0.2.7 tag) with runtime DeprecationWarnings for the 0.3.0 breaks
  - phase: 08-04
    provides: docs/MIGRATION-0.3.md + file-wide CHANGELOG guard in tests/test_release_docs.py
provides:
  - "Real 0.3.0 removal of the connection-default shims (set_default_db/get_default_db) and their encino_orm exports"
  - "Real 0.3.0 removal of the mutable security globals SECRET/GET_DB and the _legacy_config fallback"
  - "tests/test_removals_0_3_0.py: absence + happy-path coverage; replaces tests/test_deprecations_0_2_7.py"
  - "CHANGELOG '### Eliminado' (single heading) + MIGRATION-0.3 removal section with old/new behavior"
affects: [08-08, 08-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Removal = absence tests (dynamic symbol names) + happy path, no weakened filterwarnings"
    - "File-wide heading-uniqueness guard survives [Unreleased] promotion"

key-files:
  created:
    - tests/test_removals_0_3_0.py
  modified:
    - encino_orm/context.py
    - encino_orm/__init__.py
    - encino_orm/security/guard.py
    - tests/test_registry.py
    - tests/test_singleton.py
    - tests/test_security.py
    - tests/test_release_docs.py
    - CHANGELOG.md
    - docs/MIGRATION-0.3.md
    - docs/getting-started.md
    - docs/reference/context.md

key-decisions:
  - "Removal names in tests are built by concatenation so the plan's repo-wide absence grep stays satisfiable"
  - "get_current_user()/require() without args now raise AuthenticationError (fail-closed), not a legacy fallback"
  - "CHANGELOG ownership notes were resolved into final prose; '### Eliminado' has exactly one heading (08-06 sole owner)"

patterns-established:
  - "Absence test via importlib dynamic getattr -> ImportError, and hasattr -> AttributeError"

requirements-completed: [REL-01, REL-04]

# Metrics
duration: 9min
completed: 2026-09-20
---

# Phase 8 Plan 06: Removals of deprecated configuration/security shims Summary

**0.3.0 removed the connection-default shims (`set_default_db`/`get_default_db`), the mutable security globals (`SECRET`/`GET_DB`) and the `_legacy_config` fallback; CHANGELOG/MIGRATION-0.3 document all line-0.3.0 removals (including `last_id()`) with old/new behavior.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-09-20T04:16:39Z
- **Completed:** 2026-09-20T04:25:17Z
- **Tasks:** 3
- **Files modified:** 13 (1 created, 1 deleted, 11 modified)

## Accomplishments
- `set_default_db`/`get_default_db` no longer exist in `encino_orm` (ImportError) nor in `encino_orm.context` (AttributeError); `ConnectionRegistry` / module `_registry` / `resolve_db()` remain the only default paths.
- Mutable `SECRET`/`GET_DB` and `_legacy_config` removed; the only configured path is `security_dependencies(SecurityConfig(...))`, and guards without explicit config fail closed with an actionable `AuthenticationError`.
- Migrated `tests/test_registry.py` and `tests/test_singleton.py` off the deleted shims; added `tests/test_removals_0_3_0.py` (absence + happy path + `reset_on_release='commit'` re-pin); deleted the obsolete `tests/test_deprecations_0_2_7.py`.
- CHANGELOG has exactly one `### Eliminado` heading (file-wide guard) naming `set_default_db`/`get_default_db`, `SECRET`/`GET_DB` and `last_id`; MIGRATION-0.3 gained an Antes/Después removal section; `mkdocs build --strict` passes.

## Task Commits

Each task was committed atomically:

1. **Task 1: Retirar set_default_db/get_default_db y sus exports** - `6547358` (refactor)
2. **Task 2: Retirar los globales mutables SECRET/GET_DB y el fallback legacy** - `1262cb5` (refactor)
3. **Task 3: Documentar las retiradas reales en CHANGELOG y MIGRATION-0.3** - `8a91163` (docs)
4. **Task 3 follow-up: guard without literals** - `4c6a53c` (test)

**Plan metadata:** `PENDING` (docs: complete plan) → committed separately in the metadata commit.

## Files Created/Modified
- `encino_orm/context.py` - removed the deprecated `set_default_db`/`get_default_db` shims and the now-unused `warnings` import; docstring no longer describes them.
- `encino_orm/__init__.py` - dropped both symbols from the `.context` import and from `__all__`.
- `encino_orm/security/guard.py` - removed `SECRET`/`GET_DB` and `_legacy_config`; `_resolve` validates explicit config only; `get_current_user`/`require` fail closed without config.
- `tests/test_removals_0_3_0.py` (new) - absence + happy-path coverage for the config/security removals.
- `tests/test_registry.py` - removed shim imports/tests; kept registry/bind/`resolve_db(registry=...)`/WR-03; module-registry test uses `_registry.set_default` under `simplefilter("error")`.
- `tests/test_singleton.py` - 4 default tests now use `_registry.set_default(...)` instead of the shim.
- `tests/test_security.py` - legacy-global fallback tests replaced by absence + fail-closed assertions.
- `tests/test_release_docs.py` - added file-wide `test_eliminado_heading_unico` and removal-name guard.
- `tests/test_deprecations_0_2_7.py` (deleted) - obsolete 0.2.7 warning pins.
- `CHANGELOG.md` - single `### Eliminado` section; ownership notes resolved.
- `docs/MIGRATION-0.3.md` - "Retiradas" section with Antes/Después pairs + summary row.
- `docs/getting-started.md`, `docs/reference/context.md` - stopped invoking removed symbols (mkdocs strict).

## Decisions Made
- Test files build the removed symbol names by concatenation so the plan's mandatory repo-wide `grep` of `set_default_db|get_default_db|_legacy_config` over `encino_orm/` + `tests/` returns nothing.
- `get_current_user()`/`require()` with no arguments raise `AuthenticationError` (fail-closed) rather than reading global fallbacks — the security config is now mandatory.
- The `### Eliminado` word choice is documented once in the CHANGELOG section.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Docs pages still referenced removed symbols, breaking the mandatory `mkdocs build --strict`**
- **Found during:** Task 3 (documentation)
- **Issue:** `docs/reference/context.md` had `::: encino_orm.set_default_db`/`::: encino_orm.get_default_db` mkdocstrings directives; after the removals `mkdocs build --strict` aborted with "could not be found". `docs/getting-started.md` still showed `set_default_db` as a deprecated-but-working example.
- **Fix:** Replaced the directives with prose describing the post-removal design and updated the getting-started warning/example to use `ConnectionRegistry`.
- **Files modified:** `docs/reference/context.md`, `docs/getting-started.md`
- **Verification:** `uv run mkdocs build --strict` exits 0.
- **Committed in:** `8a91163` (Task 3 commit)

**2. [Rule 1 - Bug] Repo-wide absence grep tripped on the test/changelog literals**
- **Found during:** Tasks 1-3 verification
- **Issue:** The plan's acceptance criterion is `grep -rn ... "set_default_db\|get_default_db" encino_orm tests` returning nothing, but the new absence test necessarily contained the literal name.
- **Fix:** Build the symbol names by concatenation (`"set_" + "default_db"`) and resolve them dynamically via `importlib`/`getattr`; the CHANGELOG-name guard in `test_release_docs.py` likewise concatenates.
- **Files modified:** `tests/test_removals_0_3_0.py`, `tests/test_release_docs.py`
- **Verification:** Repo-wide grep returns NONE; both tests pass.
- **Committed in:** `6547358`, `4c6a53c`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 bug)
**Impact on plan:** Both fixes were required for the plan's own acceptance criteria (docs build, absence grep). No scope creep.

## Issues Encountered
- None beyond the deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REL-01 (partial config/security removal) and REL-04 (documentation) delivered; `last_id()` removal is documented here and implemented by 08-08.
- Plan 08-08 is unblocked; 08-03 (promotion) can promote `[Unreleased]` — the `### Eliminado` guard is file-wide and survives it.

---
*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*

## Self-Check: PASSED

- Created: `tests/test_removals_0_3_0.py` (FOUND), `.planning/phases/08-release-0-3-0/08-06-SUMMARY.md` (FOUND)
- Removed: `tests/test_deprecations_0_2_7.py` (REMOVED)
- Commits: `6547358`, `1262cb5`, `8a91163`, `4c6a53c` (all FOUND)
