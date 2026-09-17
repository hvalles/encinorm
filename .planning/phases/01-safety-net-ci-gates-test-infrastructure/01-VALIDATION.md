---
phase: 1
slug: safety-net-ci-gates-test-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (hardened by plan 01-03) |
| **Quick run command** | `uv run pytest -q -m "not optional_engine"` |
| **Full suite command** | `uv run pytest -q` |
| **Coverage run command** | `uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=term-missing` |
| **Estimated runtime** | ~7.5 seconds (local, full suite) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -q -m "not optional_engine"`
- **After every plan wave:** Run full suite + `uv run coverage report` + `uv run ruff check` + `uv run ruff format --check` + `uv run mypy encino_orm`
- **Before `/gsd-verify-work`:** Full suite must be green and all five phase success criteria demonstrated with an **induced failure**
- **Max feedback latency:** ~8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01-01 | 1 | CI-03 | — | Format commit is mechanical and excluded from blame | CI job | `uv run ruff format --check encino_orm tests` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01-01 | 1 | CI-03 | — | Narrow ruleset blocks merge on violations | CI job | `uv run ruff check encino_orm tests` | ❌ W0 | ⬜ pending |
| 01-02-01 | 01-02 | 1 | CI-04 | T-01-04 | `py.typed` ships in the built wheel (PEP 561) | packaging | `uv build --wheel && python -c "import zipfile,glob; assert any('py.typed' in n for n in zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]).namelist())"` | ❌ W0 | ⬜ pending |
| 01-02-02 | 01-02 | 1 | CI-04 | T-01-04 | mypy ratchet blocks regressions; no silent ignores | CI job | `uv run mypy encino_orm` | ❌ W0 | ⬜ pending |
| 01-02-03 | 01-02 | 1 | CI-07 | T-01-01 | Lockfile integrity is enforced | CI job | `uv lock --check` | ✅ | ⬜ pending |
| 01-02-04 | 01-02 | 1 | CI-07 | T-01-01 | Known-vulnerable dependencies block merge | CI job | `uv audit` (requires uv ≥ 0.12.15) | ❌ W0 | ⬜ pending |
| 01-03-01 | 01-03 | 1 | CI-06 | — | Unregistered markers are rejected | unit | `uv run pytest --strict-markers -k test_strict_marker_probe` | ❌ W0 | ⬜ pending |
| 01-03-02 | 01-03 | 1 | CI-06 | — | Warnings fail the suite | unit | probe test emitting `warnings.warn` | ❌ W0 | ⬜ pending |
| 01-03-03 | 01-03 | 1 | CI-06 | — | `-m "integration"` selects a non-zero count | CI job | `uv run pytest --collect-only -q -m "integration"` | ❌ W0 | ⬜ pending |
| 01-03-04 | 01-03 | 1 | CI-05 | T-01-05 | Coverage drop below the ratchet fails CI | CI job | `uv run coverage report --fail-under=82` | ❌ W0 | ⬜ pending |
| 01-04-01 | 01-04 | 1 | CI-01 | T-01-03 | Required engine absent → `pytest.fail`, not skip | unit | `uv run pytest tests/test_ci_harness.py -k require_engines -x` | ❌ W0 | ⬜ pending |
| 01-04-02 | 01-04 | 1 | CI-02 | T-01-03 | `skipped > 0` in JUnit XML → non-zero exit | unit | `uv run pytest tests/test_ci_harness.py -k check_skips -x` | ❌ W0 | ⬜ pending |
| 01-04-03 | 01-04 | 1 | CI-02 | T-01-03 | Gate passes on a clean run | unit | fixture XML with `skipped="0"` | ❌ W0 | ⬜ pending |
| 01-04-04 | 01-04 | 1 | CI-08 | T-01-02 | Publish cannot run while gates are red | CI proof | push tag on a failing branch; assert `publish` is skipped | ❌ W0 | ⬜ pending |
| 01-05-01 | 01-05 | 1 | CI-09 | — | Pool checkout overshoot is characterized | characterization | `uv run pytest tests/test_pool_characterization.py -x` | ❌ W0 | ⬜ pending |
| 01-05-02 | 01-05 | 1 | CI-09 | — | `last_id` scoping is characterized | characterization | same file | ❌ W0 | ⬜ pending |
| 01-05-03 | 01-05 | 1 | CI-09 | — | Release semantics are characterized | characterization | same file | ❌ W0 | ⬜ pending |
| 01-05-04 | 01-05 | 1 | CI-09 | — | `close()` behavior is characterized | characterization | same file | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tools/ci/check_skips.py` — the JUnit-XML skip gate (CI-02); checked-in script so it is unit-testable
- [ ] `tests/test_ci_harness.py` — unit tests for `required_engines()`, `engine_unavailable()`, and `check_skips.total_skipped()` (CI-01, CI-02, CI-06)
- [ ] `tests/test_pool_characterization.py` — the four pool invariants against the **unmodified** implementation (CI-09)
- [ ] `encino_orm/py.typed` — empty PEP 561 marker (CI-04)
- [ ] `.git-blame-ignore-revs` — does not exist today (CI-03)
- [ ] Dev dependencies: `uv add --dev mypy pytest-cov coverage pip-audit`
- [ ] `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage]` sections in `pyproject.toml` — none exist today
- [ ] JUnit XML fixtures (clean, with skips, with failures) for the gate's unit tests
- [ ] Framework install: none — pytest 9.1.1 is already installed and configured

*(No existing test infrastructure covers any Phase-1 requirement; this phase builds it.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Required engine absent makes the CI job fail, not skip | CI-01 | Requires an absent engine; local has all six running | `ENCINO_ORM_REQUIRE_ENGINES=postgresql ENCINO_ORM_POSTGRES_PORT=1 uv run pytest tests/test_postgresql.py` → non-zero exit |
| Publish cannot run while gates are red | CI-08 | Requires a GitHub Actions run against a deliberately failing ref | Push a tag on a deliberately-failing branch; assert the `publish` job is skipped |
| All five phase success criteria | CI-01…CI-09 | Each gate must be proven by **induced failure**; a green run proves nothing | Break each gate deliberately (bad marker, unregistered marker, coverage drop, removed engine service) and confirm CI goes red |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 8s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
