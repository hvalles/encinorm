---
phase: 08-release-0-3-0
plan: "04"
subsystem: docs
tags: [changelog, migration-guide, mkdocs, release-notes, rel-04]

requires:
  - phase: 08-01
    provides: "Deprecation-warning line 0.2.7 and the [Unreleased] entries whose ownership handoff 08-04 consumes"
provides:
  - "CHANGELOG.md [Unreleased] with an explicit Viejo:/nuevo: pair per breaking entry"
  - "docs/MIGRATION-0.3.md (Antes/Después guide for all 0.3.0 breaks)"
  - "tests/test_release_docs.py source guard (file-wide CHANGELOG + guide + nav)"
affects: [08-03, 08-06, 08-07, 08-08]

tech-stack:
  added: []
  patterns:
    - "File-wide CHANGELOG source guard that survives [Unreleased] promotion"
    - "Migration guide as Antes (0.2.6) / Después (0.3.0) pairs mirroring docs/trust-boundaries.md"

key-files:
  created:
    - docs/MIGRATION-0.3.md
    - tests/test_release_docs.py
  modified:
    - CHANGELOG.md
    - mkdocs.yml

key-decisions:
  - "Rewrote every CAMBIO DE COMPORTAMIENTO entry with an explicit Viejo:/nuevo: pair and removed the fulfilled 'Nota de ownership -> 08-04' handoff notes"
  - "Migration guide enumerates all accumulated 0.3.0 breaks (11 sections, 24 Antes/Después pairs), not only the deprecated shims"
  - "CHANGELOG guard scans the WHOLE file (>=10 marks), independent of [Unreleased], so 08-03's promotion cannot turn CI red"

patterns-established:
  - "Source-only release guards: DB-free pathlib assertions, no subprocess, no network"

requirements-completed: [REL-04]

duration: 3 min
completed: 2026-09-20
---

# Phase 8 Plan 04: Release documentation Summary

**Full 0.2.6→0.3.0 break enumeration in `CHANGELOG.md` plus a Spanish `docs/MIGRATION-0.3.md` Antes/Después guide, frozen by a file-wide source guard**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-20T03:22:33Z
- **Completed:** 2026-09-20T03:26:04Z
- **Tasks:** 3
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- `CHANGELOG.md` `[Unreleased]` now declares old/new behavior for every breaking
  entry; all 10 `CAMBIO DE COMPORTAMIENTO` marks carry an explicit
  `Viejo:`/`nuevo:` pair, and the fulfilled "Nota de ownership" handoff notes to
  08-04 are gone.
- `docs/MIGRATION-0.3.md` (340 lines, 11 `##` sections, 24 Antes/Después pairs)
  documents the accumulated breaks from Phases 2–7: `Query` cardinality and
  `rebind` removal, identifier allowlist, `PoolDb.acquire()` handle, pool
  release/close/reaping, `last_id()`, cache key/domain, migrations ledger,
  error taxonomy, connection recycling and CFG-01/CFG-02 shims.
- The guide is registered in `mkdocs.yml` (`Desarrolladores` nav) and
  `uv run mkdocs build --strict` passes.
- `tests/test_release_docs.py` (6 tests) freezes the enumeration, the guide
  structure and the nav entry; the CHANGELOG guard is file-wide so it survives
  08-03's `[Unreleased]` → `[0.3.0rc1]` promotion.

## Task Commits

Each task was committed atomically:

1. **Task 1: Complete CHANGELOG break enumeration** - `f8851b5` (docs)
2. **Task 2: Create docs/MIGRATION-0.3.md and register in MkDocs nav** - `2c46703` (docs)
3. **Task 3: Source guard for enumeration and guide** - `68781b4` (test)

**Plan metadata:** `PENDING` (docs: complete plan)

## Files Created/Modified
- `CHANGELOG.md` - `[Unreleased]` entries rewritten with explicit old/new behavior; ownership handoff notes removed
- `docs/MIGRATION-0.3.md` - Spanish migration guide with Antes/Después pairs and a summary table
- `mkdocs.yml` - added `Guía de migración 0.3: MIGRATION-0.3.md` under `Desarrolladores`
- `tests/test_release_docs.py` - 6 DB-free source guards (guide, nav, file-wide CHANGELOG)

## Decisions Made
- Kept the `REL-01 (Fase 8)` reference in the CFG-01 entry (it points at the
  removal work owned by 08-06/08-08) but removed every "no prejuzga la
  enumeración … 08-04" note, so no pending handoff remains in `[Unreleased]`.
- Added explicit `Viejo:`/`nuevo:` prose to entries that previously only implied
  the change (cache key format, error taxonomy, recycling) so each break is
  self-describing for the test and for readers.
- Did NOT touch the `### Eliminado` heading (sole owner: 08-06); removals are
  referenced in prose only.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REL-04 is satisfied and machine-guarded; 08-03 can promote `[Unreleased]`
  without breaking CI.
- 08-06 adds `test_eliminado_heading_unico` to the same file; 08-05/08-07 own the
  `prompts/` sweep (this plan deliberately does not reference `prompts/`).

## Self-Check: PASSED

- `docs/MIGRATION-0.3.md` — FOUND
- `tests/test_release_docs.py` — FOUND
- `CHANGELOG.md` — FOUND
- `mkdocs.yml` — FOUND
- Commits `f8851b5`, `2c46703`, `68781b4` — FOUND
- `uv run pytest tests/test_release_docs.py -q` — 6 passed
- `uv run pytest -q -m "not optional_engine and not benchmark"` — 1071 passed, 38 deselected

---
*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*
