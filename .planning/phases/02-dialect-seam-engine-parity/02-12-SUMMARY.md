---
phase: 02-dialect-seam-engine-parity
plan: 12
subsystem: documentation
tags: [changelog, deferred-items, ownership, roadmap, requirements, gap-closure, wr-01, wr-02]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "the round-3 fixes the changelog must describe: QueryBuilder _table validation (02-10) and the merge fail-closed guard + stale last_id decision (02-11)"
provides:
  - "CHANGELOG.md [Unreleased] ### Corregido entries for the 02-07 Query cardinality contract and for CR-01/CR-02/CR-03 (old + new behaviour)"
  - "deferred-items.md with the false 'no unowned items' claim removed and ORA-38104 + the last_id capture owned by Phase 4 / plan 04-02 / POOL-03"
  - "a round-3 section in deferred-items.md documenting the closed BLOCKER/WARNING and the residual owners"
  - "ROADMAP.md 04-02 ownership of the Oracle MERGE SET fix (ORA-38104) plus the round-3 gap-closure narrative"
  - "REQUIREMENTS.md POOL-03 traceability note for the ORA-38104 ownership"
affects: [phase-04, phase-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Document an observable behaviour change in the existing [Unreleased] section immediately (the 02-06/02-08 practice), without preempting the Phase 8 milestone enumeration"
    - "Every open deferral carries an explicit owner (phase / plan / requirement) recorded in all three of deferred-items.md, ROADMAP.md and REQUIREMENTS.md"
    - "Acceptance checks scope a section count to [Unreleased] instead of a global grep, because historical ### Corregido headings exist in 0.2.6 and earlier"

key-files:
  created: []
  modified:
    - CHANGELOG.md
    - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md

key-decisions:
  - "Extend the existing [Unreleased] ### Corregido section (created by 02-06, extended by 02-08) rather than creating a second heading; the enumeration of milestone breaking changes (including the rebind/format removal) stays owned by Phase 8 / 08-04"
  - "Frame the CR-02 merge render as a fail-closed, not a semantic upsert improvement: an auto-PK upsert is inexpressible on MSSQL/Oracle by construction and now fails loudly"
  - "State explicitly that the MERGE columns[0] fallback (ORA-38104 family) remains uncorrected and owned by Phase 4 / 04-02, so the documentation does not claim it fixed"
  - "Assign ORA-38104 and the last_id capture to Phase 4 / plan 04-02 / POOL-03 in all three artifacts (deferred-items, ROADMAP, REQUIREMENTS) so the owner is not fictitious"

patterns-established:
  - "A deferral log that claims no unowned items must be verifiable; the false claim is removed and every open item now names its owner in the log and the roadmap"

requirements-completed: [DIAL-02, DIAL-05]

# Metrics
duration: 2 min
completed: 2026-09-18
---

# Phase 02 Plan 12: Gap Closure Round 3 — Changelog & Ownership Documentation Summary

**Closed GAP E / WR-02 by documenting the 02-07 `Query` cardinality change and the CR-01/CR-02/CR-03 behaviour changes in the existing `[Unreleased] ### Corregido` section, and closed GAP D / WR-01 by removing the false "no unowned items" claim and assigning ORA-38104 and the `last_id` capture to Phase 4 / `04-02` / POOL-03 across `deferred-items.md`, `ROADMAP.md` and `REQUIREMENTS.md`.**

## Performance

- **Duration:** 2 min (109 s)
- **Started:** 2026-09-18T14:42:29Z
- **Completed:** 2026-09-18T14:44:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- **WR-02 closed.** `CHANGELOG.md` now carries four new bullets at the end of the existing `[Unreleased] ### Corregido` list (no duplicate heading): (1) the `Query` cardinality contract — values with no `{n}` now raise `ValueError` instead of being silently dropped, and `{00}` normalizes to `parameter_0000`; (2) CR-01 — `QueryBuilder` validates the model and `join()` `_table` names with the strict allowlist, fail-closed before any SQL; (3) CR-02 — the merge render rejects a conflict column absent from the INSERT (`no está en el INSERT`) instead of emitting `ON (dst.<col> = src.<col>)`; (4) CR-03 — `Model.insert(replace=True)` on MSSQL/Oracle returns `0` ("id no disponible") and leaves `self.id` intact. `rebind` does not appear anywhere in the file, so the Phase 8 enumeration is not preempted.
- **WR-01 closed.** `deferred-items.md` no longer contains the false sentence "Ya NO queda ningún item de la Fase 02 sin dueño". The ORA-38104 item is now `PENDIENTE — DUEÑO: Fase 4, plan 04-02 (POOL-03)` with a `Dueño` rationale (why the MERGE `SET` fix is a Phase 4 precondition and why it is not fixed in this round), and a new round-3 section records CR-01/CR-02/CR-03 as closed with the residual `last_id` capture explicitly owned by Phase 4.
- **Owner recorded in all three artifacts.** `ROADMAP.md`'s `04-02` bullet now declares it owns the Oracle MERGE `SET` fix (ORA-38104) and references plan `02-12`; `REQUIREMENTS.md`'s POOL-03 bullet carries the traceability note (its traceability row `| POOL-03 | Phase 4 | Pending |` is unchanged). The Phase 2 section gains the round-3 gap-closure narrative (three BLOCKER + two WARNING, parallel wave 1, docs wave 2, GAP F still deferred).
- **No false claim of a fix.** Both the changelog CR-03 bullet and the deferred-items round-3 section state that the MERGE `columns[0]` fallback remains uncorrected and owned; 02-11 only added a fail-closed guard that does not change valid SQL.

## Task Commits

Each task was committed atomically:

1. **Task 1: Register the Query cardinality contract and CR-01/CR-02/CR-03 in CHANGELOG.md** - `e113ff2` (docs)
2. **Task 2: Assign owners to ORA-38104 and last_id, fix the false claim, trace in ROADMAP/REQUIREMENTS** - `0cda72e` (docs)

**Plan metadata:** `pending` (docs: complete plan)

## Files Created/Modified
- `CHANGELOG.md` - four bullets appended to the existing `[Unreleased] ### Corregido` section; `[0.2.6]` and earlier untouched (`git diff --numstat` = 30 insertions, 0 deletions).
- `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` - header claim corrected; ORA-38104 heading marked with owner and given a `Dueño` section; new `## Encontrados y cerrados en la ronda de gap closure 3 (02-10…02-12)` section.
- `.planning/ROADMAP.md` - `04-02` bullet extended with the ORA-38104 ownership; new round-3 gap-closure paragraph after the round-1/round-2 waves line. Plan list and Phase 8 untouched.
- `.planning/REQUIREMENTS.md` - POOL-03 bullet gained the ORA-38104 ownership note; requirement text and traceability status unchanged.

## Decisions Made
- **Extend, do not duplicate.** The `[Unreleased]` section already had a `### Corregido` heading from 02-06/02-08; the round's entries were appended there, and the Phase 8 (`08-04`) milestone enumeration remains the sole owner of the full breaking-change list.
- **Document CR-02 as fail-closed, not a fix of upsert semantics.** An auto-PK upsert is inexpressible on MSSQL/Oracle by construction; the documentation says so instead of implying the default conflict now works.
- **Three-way ownership.** Assigning the owner only in the deferral log would be a fictitious owner; the roadmap plan bullet and the requirement traceability were both updated.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. The plan's referenced `ROADMAP.md:178` line had already been extended by 02-10/02-11 to include the round-2 waves line; the round-3 paragraph was placed immediately after that line, as intended.

## Known Stubs
None.

## Threat Flags
None — this plan is documentation-only and reduces the threat surface. Mitigations T-02-62 (false unowned-items claim removed), T-02-63 (cardinality change documented without a duplicate heading, `rebind` absent), T-02-64 (owner declared in ROADMAP and REQUIREMENTS, not fictitious) and T-02-65 (MERGE `columns[0]` fallback explicitly documented as uncorrected and owned) from the plan's threat register are all implemented. No new trust-boundary surface was introduced.

## Next Phase Readiness
- GAP D / WR-01 and GAP E / WR-02 are closed; the round-2 verification findings now have no open BLOCKER or WARNING.
- Full suite `787 passed`; DB-free suite `707 passed` (10 snapshots); `ruff check` / `ruff format --check` / `mypy encino_orm` exit 0; `# noqa` count still 0. The plan is documentation-only, so no source or snapshot changed.
- `tests/__snapshots__/` untouched (`git diff --stat` empty); no code path changed by this plan.

## Self-Check: PASSED

- All four modified files (`CHANGELOG.md`, `deferred-items.md`, `ROADMAP.md`, `REQUIREMENTS.md`) exist on disk.
- Both task commits (`e113ff2`, `0cda72e`) exist in git history.
- Task 1 verify passed: exactly one `### Corregido` in `[Unreleased]`; `cardinalidad`, `parameter_0000`, `nombre de tabla`, `no está en el INSERT`, `id no disponible` present; `rebind` absent from the whole file; `git diff --numstat CHANGELOG.md` = 30 insertions / 0 deletions.
- Task 2 verify passed: `Ya NO queda ningún item` absent; `04-02` ×4 in `deferred-items.md`; `ORA-38104` present in `ROADMAP.md` and `REQUIREMENTS.md`; round-3 section present; `| POOL-03 | Phase 4 | Pending |` intact.
- Plan-level verification re-run: full suite `787 passed`; DB-free `707 passed`; ruff/format/mypy exit 0; `noqa` count 0.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*
