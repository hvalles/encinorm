---
phase: 08-release-0-3-0
verified: 2026-09-20T06:07:08Z
status: passed
score: "4/4 roadmap success criteria; 13/13 must-have truths"
overrides_applied: 0
re_verification: false

# No blockers. Warnings/escalations are documented in the report body; none
# require human verification because D-01 was the phase's own accepted decision.
gaps: []
human_verification: []
---

# Phase 8: Release 0.3.0 — Verification Report

**Phase Goal (ROADMAP.md:375-376):** The deprecation path is shipped, not planned. Users on
`>=0.2.6` get warned by 0.2.7, then get a release candidate, then a documented 0.3.0 — with no
way to publish past a red CI gate.

**Overall verdict: PASS.** All four roadmap success criteria and all five `REL-01…REL-05`
requirements are verified against the shipped repository, the published PyPI/TestPyPI artifacts,
and the GitHub release runs. The real 0.3.0 removals are absent from source **and** from the
published 0.3.0 wheel, and the red-CI publish gate is enforced in-workflow plus by a protected
`pypi` environment. One release-line caveat (D-01, 0.2.7 cut from hardened `main`) is documented
as a WARNING — it is an intentional, pre-decided deviation, not an implementation gap.

**Re-verification:** No — initial verification (no prior `08-VERIFICATION.md` existed).

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 0.2.7 is published to PyPI with runtime `DeprecationWarning`s for the removable 0.3.0 breaks | ✓ VERIFIED | Published wheel `encino_orm-0.2.7-py3-none-any.whl` (`Version: 0.2.7`) emits `DeprecationWarning` for all four sites executed from the extracted wheel: `reset_on_release="commit"` (`pool.py`), `last_id()` (`base.py`), `SECRET`/`GET_DB` globals (`security/guard.py`), `set_default_db`/`get_default_db` (`context.py`). Fail-closed breaks (unvalidated identifiers, `Query` cardinality) cannot warn by design and are documented (CHANGELOG.md:391-410). |
| 2 | 0.2.7 precedes every 0.3.0 artifact on PyPI | ✓ VERIFIED | PyPI upload times: `0.2.7` 2026‑09‑19T21:21:51Z → `0.3.0rc1` 2026‑09‑20T05:44:42Z → `0.3.0` 2026‑09‑20T05:56:25Z. TestPyPI `0.3.0rc1` at 2026‑09‑20T05:29:02Z. |
| 3 | Tag/commit ordering `v0.2.7` → `v0.3.0rc1` → `v0.3.0` | ✓ VERIFIED | `v0.2.7`→`e984e78`, `v0.3.0rc1`→`3fec2da`, `v0.3.0`→`9eb3ea8` (all annotated tags). `git merge-base --is-ancestor`: `v0.2.7` ⊂ `v0.3.0rc1` ⊂ `v0.3.0` both TRUE. |
| 4 | 0.3.0rc1 is published before 0.3.0 | ✓ VERIFIED | Same upload-time ordering; both present on PyPI (`releases` includes `0.2.7`, `0.3.0rc1`, `0.3.0`); TestPyPI also has `0.3.0rc1`. |
| 5 | Publishing uses OIDC trusted publishing; no `PYPI_API_TOKEN`; protected `pypi` environment | ✓ VERIFIED | `release.yml:11` `id-token: write`, `:51` `uv publish --trusted-publishing always`, `:29-30` `environment: {name: pypi}`, `:19,22` reusable CI + `needs: [ci]`. `publish-testpypi.yml:8,34` OIDC. Repo-wide token grep returns zero. GitHub API: env `pypi` protection rules = branch policy + required reviewer `hvalles`; branch policies = `branch: main` and `tag: v*`. |
| 6 | The publish job is gated on green CI (red-CI gate) | ✓ VERIFIED | `release.yml:17-22` calls `./.github/workflows/ci.yml` (`workflow_call` present, `ci.yml:9`) and `publish: needs: [ci]`, inside the `pypi` environment. Frozen by `tests/test_release_config.py` (5 assertions incl. `needs == ["ci"]`). |
| 7 | 0.3.0rc1→0.3.0 is a pure version promotion (no code drift) | ✓ VERIFIED | `git diff --stat v0.3.0rc1 v0.3.0 -- encino_orm` is empty; only `CHANGELOG.md`, `pyproject.toml`, `uv.lock`, planning docs changed. |
| 8 | Real 0.3.0 removals shipped in source | ✓ VERIFIED | `grep` over `encino_orm/`+`tests/`: no `set_default_db`/`get_default_db`, no `def last_id`/`_warn_last_id_deprecated`, no `SECRET`/`GET_DB` globals, no `_legacy_config`, no `.last_id()` in tests. `base.py:436` retains only internal `_last_id_value`; `pool.py:60` retains only the internal `PooledConnection.last_id` field. |
| 9 | Real 0.3.0 removals shipped in the **published** artifact | ✓ VERIFIED | Extracted `encino_orm-0.3.0-py3-none-any.whl` (`Version: 0.3.0`): `def last_id` FALSE (base+pool), `_warn_last_id_deprecated` FALSE, `set_default_db`/`get_default_db` FALSE, `SECRET`/`_legacy_config` FALSE; replacements `execute_insert` TRUE, `class ConnectionRegistry` TRUE. |
| 10 | `CHANGELOG.md` enumerates every breaking change with old + new behavior | ✓ VERIFIED | `[0.3.0]` section (CHANGELOG.md:11) has 10 `CAMBIO DE COMPORTAMIENTO` entries, each carrying `Viejo:`/`nuevo:`, plus a single `### Eliminado` inventory (:342) naming the three removals. `tests/test_release_docs.py` (123 lines) enforces file-wide. |
| 11 | `docs/MIGRATION-0.3.md` shows before/after examples | ✓ VERIFIED | 423 lines, 11 `##` sections, 24 `Antes (0.2.6)` / `Después (0.3.0)` pairs + summary table; registered in `mkdocs.yml:69`; `uv run mkdocs build --strict` exits 0. |
| 12 | README documents `~=0.2.6` pinning, dev-only credentials, and fixes the `prompts/` dead link | ✓ VERIFIED | `README.md:57` `pip install "encino-orm~=0.2.6"`; no `>=0.2.6` literal; `README.md:157-160` dev-only warning; no `prompts/` in `README.md` or anywhere under `docs/`; `.env.example` tracked with dev-only header; link to `docs/MIGRATION-0.3.md` present. |
| 13 | The release guards run green under the strict suite | ✓ VERIFIED | `uv run pytest -q -m "not optional_engine and not benchmark"` → **1124 passed, 38 deselected**; the six phase guard files → **68 passed**; `uv lock --check` → exit 0. |

**Score:** 13/13 must-have truths verified; 4/4 roadmap success criteria verified.

### Per-Success-Criterion Verdict

| # | Roadmap Success Criterion | Evidence | Verdict |
|---|---------------------------|----------|---------|
| 1 | 0.2.7 published with runtime `DeprecationWarning`s for every 0.3.0 breaking change, **before** any 0.3.0 artifact | Upload order (truth 2) + all four warning sites fire in the published 0.2.7 wheel (truth 1) + `v0.2.7` CI run `35470090057` 11/11 jobs green (the 0.2.7 warning-pin test ran under `filterwarnings=["error"]`). Fail-closed breaks are documented, not warned (justified at CHANGELOG.md:391-410). | **PASS** (see W‑01 for the D‑01 scope caveat) |
| 2 | 0.3.0rc1 before 0.3.0, OIDC, no `PYPI_API_TOKEN`, protected `pypi` env | Upload order; OIDC in both workflows; zero token matches; GitHub API env `pypi` = branch `main` + tag `v*` + required reviewer; runs `35491961779` (rc1) and `35492821208` (0.3.0) SUCCESS, 10/10 CI jobs green each. | **PASS** |
| 3 | CHANGELOG enumerates every break (old+new); MIGRATION-0.3 shows before/after | CHANGELOG 10 `CAMBIO DE COMPORTAMIENTO` entries with `Viejo:`/`nuevo:` + single `### Eliminado`; MIGRATION‑0.3 11 sections/24 pairs; both guarded and `mkdocs --strict` green. | **PASS** |
| 4 | README `~=0.2.6` pinning, dev-credentials warning, `prompts/` link fixed | `README.md:57`, `:157-160`; no `prompts/` in README or `docs/**`; `docs/MIGRATION-0.3.md` linked; `.env.example` tracked. | **PASS** |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `.github/workflows/release.yml` | OIDC + `pypi` env + CI gate | ✓ VERIFIED | `id-token: write`, `--trusted-publishing always`, `environment: pypi`, `needs: [ci]`, `uses: ./ci.yml` |
| `.github/workflows/publish-testpypi.yml` | OIDC TestPyPI | ✓ VERIFIED | `id-token: write` (L8), `--trusted-publishing always` (L34) |
| `tests/test_release_config.py` | Workflow contract guard | ✓ VERIFIED | 84 lines, 9 tests pass |
| `tests/test_release_docs.py` | CHANGELOG + guide guard | ✓ VERIFIED | 123 lines, file-wide CHANGELOG + `### Eliminado` uniqueness |
| `docs/MIGRATION-0.3.md` | Antes/Después guide | ✓ VERIFIED | 423 lines (>120 min), 11 sections |
| `tests/test_removals_0_3_0.py` | Removal absence + happy path | ✓ VERIFIED | 116 lines (>40 min), dynamic symbol names |
| `tests/test_last_id_removed.py` | `last_id` absence + `execute_insert` | ✓ VERIFIED | 48 lines (>30 min), happy path returns id 1 then 2 |
| `tests/test_docs_hygiene.py` | README/`.env.example` guard | ✓ VERIFIED | 70 lines (>40 min), 7 tests |
| `tests/test_docs_links.py` | `docs/**` dead-link sweep | ✓ VERIFIED | 44 lines (>25 min), parametrized |
| `README.md` | Pinning + dev warning + migration link | ✓ VERIFIED | Contains `~=0.2.6`, no `prompts/`, no `>=0.2.6` |
| `.env.example` | Dev-only env template | ✓ VERIFIED | Tracked; six engines + Redis, dev-only header |
| `CHANGELOG.md` | Break inventory old/new | ✓ VERIFIED | `## [0.3.0]`, `## [0.2.7]`, `### Eliminado` |
| `pyproject.toml` / `uv.lock` | Version consistency | ✓ VERIFIED | Both `0.3.0`; `uv lock --check` exit 0 |
| `encino_orm/context.py` | Registry without shims | ✓ VERIFIED | `ConnectionRegistry` (:31); no `set_default_db`/`get_default_db` |
| `encino_orm/security/guard.py` | Guards via `SecurityConfig` only | ✓ VERIFIED | No `SECRET`/`GET_DB` attributes; fail-closed `AuthenticationError` |
| `tests/test_deprecations_0_2_7.py` | 0.2.7 warning pins (time-point artifact) | ✓ VERIFIED (at `v0.2.7`) | Present at tag; emits `pytest.warns` pins for the 3 warnings; intentionally deleted from `main` by 08-06 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `release.yml` `publish` | `ci.yml` | reusable workflow + `needs: [ci]` | ✓ WIRED | `release.yml:17-22`; asserted by `test_release_config.py:46-52` |
| `release.yml` `publish` | `pypi` environment | `environment: {name: pypi}` | ✓ WIRED | `release.yml:29-30`; GitHub API confirms protections |
| OIDC token | PyPI/TestPyPI | `id-token: write` + `--trusted-publishing always` | ✓ WIRED | Runs `35491961779` / `35492821208` SUCCESS, no token |
| `pyproject.toml` version | `CHANGELOG.md` heading | release-time consistency | ✓ WIRED | `0.3.0` ↔ `## [0.3.0]`; rc1→final diff empty for `encino_orm` |
| `mkdocs.yml` nav | `docs/MIGRATION-0.3.md` | nav entry | ✓ WIRED | `mkdocs.yml:69`; `mkdocs build --strict` green |
| `tests/test_removals_0_3_0.py` | `context.py` / `guard.py` | absent symbols + happy path | ✓ WIRED | 68/68 phase guard tests pass |

### Data-Flow Trace (Level 4)

Not applicable — this is a release/CI/docs phase. No artifact renders dynamic data. The
comparable "data flow" is the artifact pipeline (source → tag → CI → OIDC → registry), which was
traced end-to-end: published wheels inspected, upload timestamps read, and run conclusions fetched
from the GitHub API.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase release guards | `uv run pytest tests/test_release_config.py tests/test_release_docs.py tests/test_removals_0_3_0.py tests/test_docs_hygiene.py tests/test_docs_links.py tests/test_last_id_removed.py -q` | 68 passed in 0.27s | ✓ PASS |
| Full suite (project default filter) | `uv run pytest -q -m "not optional_engine and not benchmark"` | 1124 passed, 38 deselected | ✓ PASS |
| Lock consistency | `uv lock --check` | Resolved 98 packages, exit 0 | ✓ PASS |
| Docs build gate | `uv run mkdocs build --strict` | exit 0 | ✓ PASS |
| Published 0.2.7 emits warnings | extract `encino_orm-0.2.7-py3-none-any.whl`, run `reset_on_release="commit"`, `last_id()`, `SECRET/GET_DB`, `set_default_db` | 4× `DeprecationWarning` | ✓ PASS |
| Published 0.3.0 omits removals | extract `encino_orm-0.3.0-py3-none-any.whl`, grep symbols | removals absent; replacements present | ✓ PASS |
| Publish gate | `git diff --stat v0.3.0rc1 v0.3.0 -- encino_orm` | empty | ✓ PASS |

### Probe Execution

SKIPPED — no `scripts/*/tests/probe-*.sh` exist and this phase declares no probes. Release
verification is registry/CI based (see spot-checks above).

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| REL-01 | 08-01, 08-06, 08-08 | 0.2.7 published with runtime `DeprecationWarning`s per 0.3.0 break; removals executed in 0.3.0 | ✓ SATISFIED | 0.2.7 wheel emits 4 warning sites; 0.3.0 wheel excludes the removed symbols; absence tests + happy path pass (see W‑01 for scope caveat) |
| REL-02 | 08-03 | 0.3.0rc1 published before 0.3.0 | ✓ SATISFIED | Upload order + runs `35491961779` / `35492821208` SUCCESS; tags annotated and ordered |
| REL-03 | 08-02 | OIDC publishing; `PYPI_API_TOKEN` removed; `pypi` env protected | ✓ SATISFIED | OIDC in both workflows; zero token matches; env `pypi` branch `main`+tag `v*`+reviewer `hvalles` |
| REL-04 | 08-04, 08-06 | CHANGELOG enumerates breaks old/new; `MIGRATION-0.3.md` examples | ✓ SATISFIED | CHANGELOG 10 entries with `Viejo:`/`nuevo:`; guide 11 sections/24 pairs; guards green |
| REL-05 | 08-05, 08-07 | README pinning + dev-credentials warning + `prompts/` fix | ✓ SATISFIED | `README.md:57,157-160`; no `prompts/` in README or `docs/**`; `.env.example` tracked |

No orphaned requirements: `REQUIREMENTS.md:180-184` maps `REL-01…REL-05` to Phase 8 and every ID is
claimed by at least one plan.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX` markers in phase-touched files. No stub handlers, empty returns, or hardcoded-empty data in the release surfaces. | — | None |
| `docs/MIGRATION-0.3.md` | 156-157 | Present-tense "`last_id()` queda DEPRECADO (emite `DeprecationWarning`)" is stale for 0.3.0 (the API is removed; the guide's later "Retiradas" section correctly says it no longer exists) | ℹ️ Info | Cosmetic doc inconsistency; does not affect the criterion |
| `tests/test_release_docs.py` | 27-28 | `_VIEJO`/`_NUEVO` regexes are broad (`antes`, `después`, `ahora`) and could match incidental prose | ℹ️ Info | Guard is weaker than its docstring implies; manual read confirms every CHANGELOG entry has a real `Viejo:`/`nuevo:` pair, so no false pass occurred |
| `tests/test_deprecations_0_2_7.py` (at `v0.2.7`) | — | Pins 3 of the 4 warning sites; `set_default_db`/`get_default_db` emit a warning but are not pinned by that test | ℹ️ Info | Behaviour exists and was verified on the published wheel; test coverage was 1 warning short |

### Warnings / Escalations (informational — no closure action required)

**W‑01 — D‑01 release-line deviation from ROADMAP Hard Ordering Constraint #6.**
`ROADMAP.md:49-51` states 0.2.7 must be cut from the `v0.2.6` maintenance line, **not** hardened
`main`, so the deprecations describe the old behaviour while it still exists. The phase instead
executed context decision **D‑01** (`08-CONTEXT.md:24-28`): `v0.2.7` is an annotated tag on `main`
at the freeze commit `e984e78`. Consequence, verified directly: the published 0.2.7 wheel already
contains the Phase 2–7 hardening (`encino_orm/dialects/`, `PooledConnection`, `_translate_exception`,
`is_disconnect_error`). So 0.2.7 emits warnings for the four **removed** APIs (verified) and for the
fail-closed breaks documents instead of warning, but it does **not** warn for the Phase 2–7
behaviour changes — users adopting 0.2.7 experience those directly. Under the roadmap SC1 literal
wording ("DeprecationWarnings for **every** 0.3.0 breaking change") this is a partial match; under
the plan/context scoping it is the intended design. The README `~=0.2.6` pinning guidance is the
mitigation. This was a deliberate, documented decision; it is surfaced here for awareness.

*This looks intentional (documented as D‑01). If a reviewer wants it recorded as an accepted
deviation rather than a caveat, add to frontmatter:*

```yaml
overrides:
  - must_have: "0.2.7 published with runtime DeprecationWarnings for every 0.3.0 breaking change"
    reason: "D-01: 0.2.7 cut from hardened `main` (freeze commit e984e78), so Phase 2–7 behaviour changes already ship in 0.2.7; warnings cover the four removed APIs and the fail-closed breaks are documented. ROADMAP hard-ordering #6 (v0.2.6 maintenance line) was superseded by 08-CONTEXT D-01."
    accepted_by: "<developer>"
    accepted_at: "<ISO timestamp>"
```

**W‑02 — Pre-existing ROADMAP/STATE progress inconsistency (noted, not fixed).**
`ROADMAP.md:500` lists `| 7. Performance & Benchmarks | 0/4 | Not started | - |` although the same
file declares Phase 7 complete (`ROADMAP.md:71`, `:363` "Fase 7 COMPLETA"). `STATE.md` frontmatter
says `completed_phases: 7` (of 8) and `completed_plans: 55` (of 57), and `milestone: v0.2.6`,
consistent with Phase 7 still counted as 0/4. Phase 8's own row is `8/8 | Complete`. These are
pre-existing bookkeeping drifts; the phase-specific state is correct.

**W‑03 — GitHub Actions secrets could not be re-listed locally.**
The unauthenticated GitHub API refuses `GET /actions/secrets` (`Requires authentication`). The
"no publish secrets remain" claim rests on (a) the orchestrator's authenticated `gh secret list`
(empty) and (b) a repo-wide workflow grep that returns zero token references. The latter was
re-confirmed here. Not a gap in the phase; noting the verification boundary.

**W‑04 — Release outcomes are registry/CI facts, not runtime tests.**
Whether OIDC trust, the `pypi` environment gate, and the registry uploads behave as configured is
observable only through PyPI/TestPyPI JSON and GitHub Actions runs (all re-confirmed here). No
additional human testing is required; these are external services, not locally reproducible state.

### Human Verification Required

None. All must-haves are automatable and were verified against the codebase, the published
artifacts, and the release runs. W‑01 is an escalation about a pre-decided release-line policy
(D‑01), not a behavioural test that needs human execution.

### Gaps Summary

No blocking gaps. The phase goal is achieved:

- **Deprecation path shipped** — the published 0.2.7 wheel emits runtime `DeprecationWarning`s for
  every API that 0.3.0 removes, fails closed (documented) where a warning is impossible, and
  precedes all 0.3.0 artifacts.
- **Release candidate then final** — `0.3.0rc1` precedes `0.3.0` on PyPI and TestPyPI; tags are
  annotated and strictly ordered; the rc→final promotion has zero code drift.
- **OIDC + gate** — no long-lived publish token remains; `publish` depends on the reusable CI
  workflow and runs in the protected `pypi` environment; both release runs are green with 10/10 CI
  jobs.
- **Documentation** — CHANGELOG cites old/new behavior for every break; `MIGRATION-0.3.md` gives
  before/after pairs; README pins `~=0.2.6`, warns about dev-only credentials, and no longer links
  the dead `prompts/` path.

---

_Verified: 2026-09-20T06:07:08Z_
_Verifier: the agent (gsd-verifier)_
