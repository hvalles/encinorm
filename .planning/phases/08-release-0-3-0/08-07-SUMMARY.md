---
phase: 08-release-0-3-0
plan: 07
subsystem: docs
tags: [rel-05, docs, dead-links, prompts, mkdocs, guard, release]

# Dependency graph
requires:
  - phase: 08-04
    provides: docs/MIGRATION-0.3.md as the tracked migration guide (a valid repoint target)
provides:
  - "docs/**/*.md free of the gitignored prompts/ path (9 documents)"
  - "tests/test_docs_links.py: parametrized source guard sweeping docs/**/*.md"
  - "REL-05 completed (README half delivered by 08-05, docs/** half by this plan)"
affects: [08-08, 08-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dead path to gitignored content replaced by tracked prose, not by deleting the affordance"
    - "Parametrized pathlib sweep frozen at import; assert message names the offending file"

key-files:
  created:
    - tests/test_docs_links.py
  modified:
    - docs/credits.md
    - docs/docker.md
    - docs/design/5-security.md
    - docs/design/6-from_db.md
    - docs/design/7-missing.md
    - docs/design/8-pk.md
    - docs/design/9-singleton.md
    - docs/design/a-xpress.md
    - docs/design/has_many.md

key-decisions:
  - "prompts/ citations rewritten as tracked prose ('análisis técnico interno (no distribuido)') rather than deleted, preserving the sentence meaning and technical content"
  - "The guard sweeps docs/**/*.md ONLY; README.md stays with 08-05 (tests/test_docs_hygiene.py) so the two wave-3 plans never deadlock"
  - "REL-05 marked complete because both halves now exist: 08-05 (README pinning/dev-credentials) + 08-07 (docs/** dead-link removal + guard)"

requirements-completed: [REL-05]

# Metrics
duration: 2min
completed: 2026-09-20
---

# Phase 8 Plan 07: docs/** `prompts/` dead-link removal Summary

**Removed every gitignored `prompts/` citation from the 9 tracked `docs/` pages and added a parametrized `docs/**/*.md` guard that names any offending file.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-20T04:26:30Z
- **Completed:** 2026-09-20T04:28:38Z
- **Tasks:** 2
- **Files modified:** 10 (9 docs modified, 1 test created)

## Accomplishments
- 14 `prompts/` citations across 9 `docs/` pages rewritten as tracked prose; zero remain under `docs/`
- New `tests/test_docs_links.py` sweeps all 30 `docs/**/*.md` pages, names the offender on failure, and is deliberately disjoint from the README guard
- `uv run mkdocs build --strict` remains green; full suite green (`1124 passed, 38 deselected`)
- REL-05 closed: the README half (08-05) and the `docs/**` half (08-07) are both delivered

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite `prompts/` citations in design docs and doc pages** - `3640fbf` (docs)
2. **Task 2: Dead-link guard for `docs/**`** - `5887efd` (test)

**Plan metadata:** _(this commit)_ (docs: complete plan)

## Files Created/Modified
- `tests/test_docs_links.py` - DB-free, no-network parametrized guard over `docs/**/*.md`; asserts `prompts/` is absent and excludes README.md
- `docs/credits.md` - AI role prose no longer cites `prompts/analisys-*.md`
- `docs/docker.md` - image-size detail repointed to tracked prose
- `docs/design/5-security.md` - two citations replaced by tracked prose
- `docs/design/6-from_db.md` - two citations replaced by tracked prose
- `docs/design/7-missing.md` - citation replaced by tracked prose
- `docs/design/8-pk.md` - citation replaced by tracked prose
- `docs/design/9-singleton.md` - citation replaced by tracked prose
- `docs/design/a-xpress.md` - two citations replaced by tracked prose
- `docs/design/has_many.md` - citation replaced by tracked prose

## Decisions Made
- Rewrote (`análisis técnico interno (no distribuido)`) instead of deleting the reference, so users still learn that an internal analysis underpins each design doc; the content of `prompts/` is unavailable (gitignored) so nothing was migrated.
- Kept `analisys-NN` tokens that are NOT path-shaped (e.g. `(analisys-06)` table headers): the guard targets the `prompts/` path that 404s, not the bare label; this keeps the diff minimal and the technical meaning intact.
- Guard scope is `docs/**/*.md` exactly; `README.md` is 08-05's responsibility, confirmed by an explicit test that the sweep excludes it.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. The guard's failure path was verified by temporarily adding `docs/__tmp_prompts_probe.md` (which failed, named the file) and deleting it afterward.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REL-05 is complete; `docs/**` no longer contains dead `prompts/` links and the guard prevents regressions.
- Ready for the remaining release plans (08-08) and `uv run mkdocs build --strict` remains a valid CI gate.

---
*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*

## Self-Check: PASSED
- FOUND: tests/test_docs_links.py
- FOUND: .planning/phases/08-release-0-3-0/08-07-SUMMARY.md
- FOUND: 3640fbf
- FOUND: 5887efd
