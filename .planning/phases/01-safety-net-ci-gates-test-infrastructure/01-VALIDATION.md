---
phase: 1
slug: safety-net-ci-gates-test-infrastructure
status: approved
nyquist_compliant: true
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
| 01-01-01 | 01-01 | 1 | CI-03 | — | ruff pinned exactly; base config present | config | `uv run ruff --version` + `tomllib` asserts | ❌ W0 | ⬜ pending |
| 01-01-02 | 01-01 | 1 | CI-03 | — | Format commit is mechanical and excluded from blame | CI job | `uv run ruff format --check encino_orm tests` + `.git-blame-ignore-revs` assert | ❌ W0 | ⬜ pending |
| 01-01-03 | 01-01 | 1 | CI-03 | T-01-06 | Source findings fixed; suppressions scoped and named | source | `uv run ruff check encino_orm` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01-01 | 1 | CI-03 | T-01-06 | Tests findings fixed; blocking lint job wired | CI job | `uv run ruff check encino_orm tests` + YAML parse | ❌ W0 | ⬜ pending |
| 01-02-01 | 01-02 | 2 | CI-04, CI-07 | T-01-01 | Dev dependencies verified legitimate before install | packaging | PyPI resolution probe | ❌ W0 | ⬜ pending |
| 01-02-02 | 01-02 | 2 | CI-04 | T-01-04 | `py.typed` ships in the wheel; mypy ratchet blocks regressions | packaging + CI job | wheel namelist + `uv run mypy encino_orm` + typecheck-job extras assert | ❌ W0 | ⬜ pending |
| 01-02-03 | 01-02 | 2 | CI-07 | T-01-01 | Lockfile integrity and vulnerability scanning block merge | CI job | `uv lock --check` + `uv audit --help` + YAML parse | ✅ / ❌ W0 | ⬜ pending |
| 01-03-01 | 01-03 | 3 | CI-06 | — | Pytest config hardened; resulting failures fixed | config | `uv run pytest -q` + `tomllib` asserts | ❌ W0 | ⬜ pending |
| 01-03-02 | 01-03 | 3 | CI-06 | — | `integration` / `optional_engine` markers applied per map | CI job | `uv run pytest --collect-only -q -m "integration"` (non-zero) | ❌ W0 | ⬜ pending |
| 01-03-03 | 01-03 | 3 | CI-05, CI-06 | T-01-05 | Coverage combine + no-drop ratchet; config regression guards | CI job + unit | `coverage combine` + `coverage report` + `tests/test_pytest_config.py` | ❌ W0 | ⬜ pending |
| 01-04-01 | 01-04 | 4 | CI-01 | T-01-03 | Required engine absent → `pytest.fail`, not skip | unit | `uv run pytest -q` + `from tests.conftest import` asserts | ❌ W0 | ⬜ pending |
| 01-04-02 | 01-04 | 4 | CI-02 | T-01-03 | Optional-engine skips are marked, so unmarked skips are detectable | unit | `uv run pytest -q` + skip-site scan | ❌ W0 | ⬜ pending |
| 01-04-03 | 01-04 | 4 | CI-02, CI-08 | T-01-02 | `skipped > 0` in JUnit XML → non-zero exit; publish gated on CI | unit + CI proof | `tests/test_ci_harness.py` + `needs: [ci]` + YAML parse | ❌ W0 | ⬜ pending |
| 01-05-01 | 01-05 | 5 | CI-09 | — | Checkout cap and overshoot race characterized | characterization | `uv run pytest tests/test_pool_characterization.py -x` | ❌ W0 | ⬜ pending |
| 01-05-02 | 01-05 | 5 | CI-09 | — | `last_id` scoping and release semantics characterized | characterization | same file | ❌ W0 | ⬜ pending |
| 01-05-03 | 01-05 | 5 | CI-09 | — | `close()` behavior characterized; file is a working safety net | characterization | same file + full suite + `check_skips.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tools/ci/check_skips.py` — the JUnit-XML skip gate (CI-02); checked-in script so it is unit-testable
- [ ] `tests/test_ci_harness.py` — unit tests for `required_engines()`, `engine_unavailable()`, and `check_skips.total_skipped()` (CI-01, CI-02)
- [ ] `tests/test_pytest_config.py` — config regression guards for the hardened pytest options and markers (CI-06)
- [ ] `tests/test_pool_characterization.py` — the four pool invariants against the **unmodified** implementation (CI-09)
- [ ] `encino_orm/py.typed` — empty PEP 561 marker (CI-04)
- [ ] `.git-blame-ignore-revs` — does not exist today (CI-03)
- [ ] Dev dependencies: `uv add --dev mypy pytest-cov coverage pip-audit`
- [ ] `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage]` sections in `pyproject.toml` — none exist today
- [ ] JUnit XML fixtures (clean, with skips, with failures) for the gate's unit tests
- [ ] Framework install: none — pytest 9.1.1 is already installed and configured

*(No existing test infrastructure covers any Phase-1 requirement; this phase builds it. All Wave 0 artifacts are created by tasks in waves 1–5 — there is no separate Wave 0 execution pass.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Required engine absent makes the CI job fail, not skip | CI-01 | Requires an absent engine; local has all six running | `ENCINO_ORM_REQUIRE_ENGINES=postgresql ENCINO_ORM_POSTGRES_PORT=1 uv run pytest tests/test_postgresql.py` → non-zero exit |
| Publish cannot run while gates are red | CI-08 | Requires a GitHub Actions run against a deliberately failing ref | Push a tag on a deliberately-failing branch; assert the `publish` job is skipped |
| All five phase success criteria | CI-01…CI-09 | Each gate must be proven by **induced failure**; a green run proves nothing | Break each gate deliberately (bad marker, unregistered marker, coverage drop, removed engine service) and confirm CI goes red |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 8s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-17
