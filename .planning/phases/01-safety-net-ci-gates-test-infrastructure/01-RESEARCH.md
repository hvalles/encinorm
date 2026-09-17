# Phase 1: Safety Net — CI Gates & Test Infrastructure - Research

**Researched:** 2026-09-17
**Domain:** CI quality gates, static analysis tooling, pytest hardening, coverage ratcheting, and pool characterization testing for a Python 3.10+ async multi-engine ORM
**Confidence:** HIGH — every numeric baseline in this document was measured on this machine today (ruff 0.16.8, mypy 2.3.1, pytest 9.1.1, coverage 7.16.1, CPython 3.10.18); tool/API claims verified against PyPI and official docs.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** El interruptor de motores requeridos exige **MySQL + PostgreSQL** en Fase 1 — exactamente los servicios que ya existen en `.github/workflows/ci.yml`. Queda **extensible** para que Fase 2 (DIAL-08) añada MariaDB, Redis, MSSQL y Oracle sin rediseño.
- **D-02:** Los motores no requeridos (MariaDB, Redis, MSSQL, Oracle) se omiten con un **marker explícito** (p. ej. `optional_engine`). El gate de tests omitidos falla **solo por skips NO marcados** — así un motor ausente legítimo no produce falsos positivos.
- **D-03:** El interruptor se activa **solo en CI mediante variable de entorno** (p. ej. `ENCINO_ORM_REQUIRE_ENGINES`). En local, un motor ausente sigue saltando. Se descarta la auto-detección porque un fallo de servicio degradaría silenciosamente a verde — el anti-patrón que motiva la fase.
- **D-04:** Estructura de umbrales: **piso global bajo (ratchet) + piso alto por dialecto**. El piso alto aplica al seam `dialects/` y a los builders compartidos, para que SQLite no enmascare rutas dialectales.
- **D-05:** La cobertura arranca como **ratchet no-baja**: se fija el baseline del estado actual y el gate falla solo si la cobertura **baja**. No se exigen números absolutos en Fase 1.
- **D-06:** Fase 1 monta el **mecanismo** (`parallel = true`, `COVERAGE_FILE` por job, `coverage combine`, ratchet global). El **piso por dialecto se define en Fase 2**, cuando el seam `dialects/` exista al que aplicarlo.
- **D-07:** `filterwarnings = ["error", ...]` con una **allowlist acotada, explícita y comentada** para warnings conocidos y justificados. Cualquier warning nuevo falla.
- **D-08:** Registrar los markers `integration`, `optional_engine`, `concurrency` y `benchmark`. Aplicar `integration` a los tests de motor real para que el comando documentado en `README.md:130` (`uv run pytest -m "not integration"`) funcione de verdad.
- **D-09:** Alcance de Fase 1: **config endurecida + arreglos mínimos** de las incompatibilidades que aparezcan (markers no registrados, warnings, `xfail`), en commits **separados y bisectables**. No se reescriben asserts genéricos (`pytest.raises(Exception)`) ni asserts de estado privado en esta fase.

### the agent's Discretion

- La selección exacta de reglas de `ruff` a habilitar en el primer ruleset (la investigación recomienda empezar por `E/W/F/I/UP/B/C4/SIM/PERF/FURB/ASYNC/RUF/S/PT` y diferir `ANN`/`D`/`PL`).
- El valor numérico exacto del piso global inicial del ratchet (se fija contra el baseline medido).
- La versión exacta de `uv` a fijar (la investigación apunta a 0.12.15 como mínimo con `uv audit`).
- La forma concreta del gate post-run sobre JUnit-XML.

### Deferred Ideas (OUT OF SCOPE)

- **Matriz multi-motor completa (MariaDB/Redis/MSSQL/Oracle)** — es DIAL-08, Fase 2. Fase 1 solo deja el interruptor extensible.
- **Piso de cobertura por dialecto** — se define en Fase 2 sobre el seam `dialects/`.
- **Reescritura de asserts genéricos y de estado privado** — no entra en Fase 1; los tests de caracterización del pool (plan 01-05) capturan el comportamiento actual tal cual.
- **`uv check` / `ty` como gate** — pre-1.0 y experimental; la investigación recomienda mantenerlo local hasta comparar su ruido contra mypy.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CI-01 | `ENCINO_ORM_REQUIRE_ENGINES` switch fails instead of skipping a required engine | §Switch Design — `engine_unavailable()` helper in `tests/conftest.py`; 8 existing `pytest.skip` call sites enumerated; MySQL+PG = 28 integration tests |
| CI-02 | Post-run JUnit-XML gate fails the job if `skipped > 0` | §JUnit Gate — verified XML shape, verified deselected tests are excluded, `-m "not optional_engine"` resolves the D-02 tension |
| CI-03 | `ruff` (lint + format) configured and blocking in CI | §Ruff — measured baselines (61/101 files reformatted; 128 source errors; 102 test errors) and the exact ignore list required |
| CI-04 | `mypy` non-strict with ratchet passes; `py.typed` marker exists | §Mypy — measured 81/124/458 errors at three strictness levels; `py.typed` wheel inclusion verified by building the wheel |
| CI-05 | `pytest-cov` with `parallel = true` + `coverage combine` per engine and a low ratchet floor | §Coverage — measured **88% local / 83% CI-equivalent** baseline; floor must use the 83% figure |
| CI-06 | pytest config hardened (`--strict-markers`, `xfail_strict`, `filterwarnings=["error"]`, both loop scopes, declared markers) | §Pytest Hardening — all four hardening knobs verified safe against the current suite (0 warnings, 0 xfails, only `asyncio` marker in use) |
| CI-07 | Dependency/vulnerability scan runs in CI | §Dependency Scanning — `uv audit` confirmed in 0.12.x docs, confirmed **absent** in local 0.8.22; `uv lock --check` confirmed working in 0.8.22; `uv export` bridge confirmed |
| CI-08 | Release workflow depends on CI | §Release Gate — cross-file `needs:` is impossible; verified `workflow_call` reusable-workflow pattern from GitHub docs |
| CI-09 | Pool invariant characterization tests exist before the refactor | §Pool Characterization — current behavior of all four invariants measured empirically; overshoot race reproduced deterministically |
</phase_requirements>

## Summary

Phase 1 is a **configuration-and-instrumentation phase**: it changes no ORM behavior. Its entire risk is that the gates are added in a way that either (a) fails on day one, (b) passes vacuously, or (c) destroys the reviewability of every later phase. This research removes all three risks by measuring the real baseline before anything is turned on.

Three findings dominate the plan:

1. **The coverage floor must be set from the CI-equivalent measurement (83%), not the local one (88%).** All six engines are running in local Docker today, so a local coverage run exercises MariaDB/MSSQL/Oracle code that CI cannot reach. `oracle.py` alone falls from 59% to 16% when the optional-engine test files are excluded. A ratchet pinned at the local number would fail on the first CI run. Both numbers are measured in §Coverage.

2. **The `skipped > 0` gate cannot see markers, so the gate and the `optional_engine` marker must be reconciled at the *invocation* level.** JUnit XML records counts, not markers. Running the required-engine job with `-m "not optional_engine"` deselects the 13 optional-engine integration tests — verified that deselected tests are entirely absent from the XML — so `skipped > 0` then means, by construction, an *unmarked* skip. This satisfies D-02 without a custom pytest plugin.

3. **`STACK.md`'s mypy configuration is not "non-strict" and must not be copied verbatim.** It produces **458 errors across 41 files**; the roadmap plan 01-02 says "mypy non-strict". The measured ladder is 81 → 124 → 458 errors for defaults → `--check-untyped-defs` → STACK.md's config. Phase 1 should land at the bottom of that ladder with an explicit per-module ratchet, exactly as CI-04 describes.

**Primary recommendation:** Land every gate as its own commit, each measured-green against a locally reproducible command before it reaches CI. Pin the coverage floor at **82** (one point under the measured 83% CI-equivalent baseline) with a comment recording the measurement and deferring the raise to Phase 2. Reuse `ci.yml` as a `workflow_call` reusable workflow for CI-08 rather than duplicating gates inside `release.yml`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Lint / format gate (CI-03) | CI / Build tooling | Developer workstation | Pure tooling concern; no runtime artifact. Runs as a dedicated job so a format failure cannot hide a test failure. |
| Type-check gate (CI-04) | CI / Build tooling | Packaging (PEP 561) | `py.typed` is a *packaging* artifact (ships in the wheel) while mypy is a CI gate. The two must land together or the marker is meaningless. |
| Coverage collection + ratchet (CI-05) | CI / Build tooling | — | Aggregation across jobs; no library code involved. `[tool.coverage]` is repo config, not runtime. |
| pytest hardening (CI-06) | Test harness (`pyproject.toml` + `tests/conftest.py`) | CI | Configuration lives in the test tier; CI merely inherits it. |
| Required-engine switch (CI-01) | Test harness (`tests/conftest.py` + engine fixtures) | CI (env var) | The skip/fail decision belongs in the test fixture, not the workflow. The workflow only supplies the env var. |
| JUnit skip gate (CI-02) | CI / Build tooling | Test harness (produces the XML) | A post-run assertion over a build artifact. Must be a checked-in script, not inline YAML, so it is itself testable. |
| Dependency/vulnerability scan (CI-07) | CI / Build tooling | Packaging (`uv.lock`) | Audits the locked dependency set; touches no library code. |
| Release depends on CI (CI-08) | CI / Release orchestration | — | Workflow-graph concern only. |
| Pool characterization tests (CI-09) | Test tier (`tests/test_pool.py` or a sibling file) | — | These are *behavioral specifications of the current implementation*, not CI config. They must pass unmodified and become the safety net for Phase 4. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Provenance |
|---------|---------|---------|--------------|------------|
| `ruff` | `0.16.8` | Lint + format | Already a dev dependency and installed locally (verified `ruff 0.16.8`). Replaces flake8/black/isort/pyupgrade/bandit in one binary. | [VERIFIED: local `ruff --version`; PyPI JSON API 0.16.8 released 2026-09-16] |
| `mypy` | `2.3.1` | Static type gate | Only checker with an official pydantic v2 plugin (`pydantic.mypy`), which matters for a library whose public surface is pydantic models. | [VERIFIED: PyPI JSON API, 2.3.1 released 2026-08-15; ran mypy 2.3.1 in this session] |
| `pytest-cov` | `7.1.0` | Coverage gating | De-facto standard; 7.1.0 fixed `--cov-fail-under` inconsistency across reporting options. | [VERIFIED: PyPI JSON API, 7.1.0 released 2026-03-21] |
| `coverage` | `7.16.1` | Coverage engine | Pulled by pytest-cov; `parallel = true` + `coverage combine` is the documented multi-job pattern. `coverage report --fail-under` confirmed present. | [VERIFIED: PyPI JSON API 7.16.1 released 2026-09-13; `coverage report --help` shows `--fail-under=MIN`] |
| `uv` | `0.12.15` | Package/lock manager + `uv audit` + `uv lock --check` | Project's existing manager. `uv audit` is confirmed present in the current CLI reference and confirmed **absent** in the local 0.8.22. | [VERIFIED: PyPI JSON API, 0.12.15 released 2026-09-15; `uv audit --help` → `error: unrecognized subcommand 'audit'` locally; docs.astral.sh/uv/reference/cli/ documents `uv audit`] |
| `pip-audit` | `2.10.1` | Secondary vulnerability scan (different advisory source than OSV) | Cannot read `uv.lock`; must be fed via `uv export`. | [VERIFIED: PyPI JSON API, 2.10.1 released 2026-06-10; `uv export --format requirements-txt --no-emit-project --no-hashes` produces 155 lines with exit 0 locally] |

### Supporting

| Library | Version | Purpose | When to Use | Provenance |
|---------|---------|---------|-------------|------------|
| `pytest-asyncio` | `1.4.0` (already installed) | Async test execution | Already in use with `asyncio_mode = "auto"`. Both `asyncio_default_fixture_loop_scope` and `asyncio_default_test_loop_scope` confirmed as valid ini keys via `pytest --help`. | [VERIFIED: `pytest_asyncio.__version__ == 1.4.0`; `pytest --help` lists both options] |
| `pytest-timeout` | `2.4.0` | Convert pool deadlocks into failures | **Not needed in Phase 1** — POOL-07 (Phase 4) owns it. Defer. | [CITED: STACK.md §Supporting] |
| `zizmor` | `1.30.1` | Static security audit of workflow YAML | **Not in Phase 1 scope.** Worth adding when OIDC publishing lands (Phase 8). | [CITED: STACK.md §Supporting] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ruff format` | `black` + `isort` | Superseded for ~2 years; two tools, two configs, 10–100× slower. Rejected. |
| `mypy` | `pyright` / `basedpyright` | No pydantic plugin; running it as a second *blocking* gate doubles triage. Advisory only. |
| `uv audit` | `pip-audit` alone | `pip-audit` cannot read `uv.lock` and needs an export step; `uv audit` reads the lock directly. Use `uv audit` primary, `pip-audit` as cross-check. |
| `mypy` | `uv check` / `ty` (`0.0.82`) | Pre-1.0, explicitly experimental, non-portable suppressions. Local-only (already deferred by CONTEXT). |
| Reusable `workflow_call` for CI-08 | Inline duplicated gates in `release.yml` | Duplication drifts. Reusable workflow is DRY and is the documented GitHub pattern. |

**Installation:**

```bash
# 0. Prerequisite — local uv must be upgraded (0.8.22 lacks `uv audit`)
uv self update 0.12.15

# 1. Gates
uv add --dev mypy pytest-cov coverage pip-audit
```

**Version verification (run before writing the Standard Stack table into any plan):**

```bash
uv --version                                  # expect >= 0.12.15 after upgrade
uv run ruff --version                         # expect 0.16.8
uv run mypy --version                         # expect 2.3.1
uv run pytest --version                       # expect 9.1.1
uv run coverage --version                     # expect 7.16.1
```

**Pin `ruff` exactly.** `ruff>=0.16.8` in `[dependency-groups].dev` lets CI resolve a newer ruff whose formatter output differs, producing a spurious `ruff format --check` failure on an unrelated PR. Recommend `ruff==0.16.8` (or `>=0.16.8,<0.17`) so the format-only commit stays stable. [ASSUMED — reasoning from ruff's versioned formatter output; not verified against a specific ruff changelog entry in this session.]

## Package Legitimacy Audit

All packages below are existing, widely-deployed dependencies already present in the project or explicitly named by the project's own prior research. None are newly-discovered names.

| Package | Registry | Age | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-------------|-----------|-------------|
| `mypy` | PyPI | ~13 yrs | github.com/python/mypy | not run (tool unavailable) | Approved — `[ASSUMED]` verification level |
| `pytest-cov` | PyPI | ~13 yrs | github.com/pytest-dev/pytest-cov | not run | Approved — `[ASSUMED]` |
| `coverage` | PyPI | ~18 yrs | github.com/nedbat/coveragepy | not run | Approved — `[ASSUMED]` |
| `pip-audit` | PyPI | ~4 yrs | github.com/pypa/pip-audit | not run | Approved — `[ASSUMED]` |
| `ruff` | PyPI | ~3 yrs | github.com/astral-sh/ruff | not run | Already a project dependency — `[VERIFIED: local install]` |
| `uv` | PyPI / standalone | ~3 yrs | github.com/astral-sh/uv | not run | Already the project's tool — `[VERIFIED: local install 0.8.22]` |

**Packages removed due to slopcheck `[SLOP]` verdict:** none
**Packages flagged as suspicious `[SUS]`:** none

> **slopcheck was unavailable in this environment**, so every newly-added package is tagged `[ASSUMED]` and the planner should gate each `uv add` behind a `checkpoint:human-verify` task, or at minimum confirm each package name resolves on PyPI before adding it. All five names above are long-established packages already named in `.planning/research/STACK.md` and, in the case of `ruff`, already declared in `pyproject.toml`.

## Architecture Patterns

### System Architecture Diagram

```text
Developer push / PR / tag
        │
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ .github/workflows/ci.yml   (gains `on: workflow_call`)            │
│                                                                   │
│  job: lint        ruff check + ruff format --check   ──┐          │
│  job: typecheck   mypy encino_orm (py.typed)         ──┤          │
│  job: deps        uv lock --check, uv audit,         ──┤ blocking │
│                   pip-audit (via uv export)          ──┤          │
│  job: test  (matrix 3.10–3.13)                        ─┤          │
│    ├ services: mysql, postgres                        │          │
│    ├ env ENCINO_ORM_REQUIRE_ENGINES=mysql,postgresql  │          │
│    ├ pytest -m "not optional_engine"                  │          │
│    │    --junitxml=junit.xml --cov ... ──► junit.xml  │          │
│    ├ step: python tools/ci/check_skips.py junit.xml   │          │
│    │        exit 1 if skipped > 0                     │          │
│    └ upload .coverage.py${{matrix.python-version}} ───┤          │
│  job: coverage   download artifacts → coverage combine│          │
│                  → coverage report --fail-under=82  ──┘          │
└───────────────────────────────────────────────────────────────────┘
        │
        │  reuse via `uses: ./.github/workflows/ci.yml`
        ▼
┌───────────────────────────────────────────────────────────────────┐
│ .github/workflows/release.yml  (trigger: push tag v*)             │
│   job: ci       uses: ./.github/workflows/ci.yml                   │
│   job: publish  needs: [ci]  →  uv build --no-sources → uv publish │
└───────────────────────────────────────────────────────────────────┘
```

Reading the diagram: a tag push enters `release.yml`, which *calls* `ci.yml` as a reusable workflow; `publish` cannot start until every gate inside it is green. A PR enters `ci.yml` directly. The JUnit gate is a step *inside* the matrix test job (each leg produces its own XML), while coverage combines across legs in a separate job.

### Recommended Project Structure

```text
.github/workflows/
├── ci.yml                     # gains `on: workflow_call` + 4 gate jobs
└── release.yml                # gains `ci:` job + `needs: [ci]` on publish

tools/ci/
└── check_skips.py             # JUnit-XML skip gate (checked in, unit-testable)

tests/
├── conftest.py                # + engine_unavailable() helper, marker declarations
├── test_pool_characterization.py   # NEW — CI-09 (or appended to test_pool.py)
├── test_ci_harness.py         # NEW — tests for the switch helper + skip gate
└── (engine files)             # + class-level @pytest.mark.integration

encino_orm/
└── py.typed                   # NEW — PEP 561 marker

.git-blame-ignore-revs         # NEW — records the format-only commit SHA
pyproject.toml                 # + [tool.ruff], [tool.mypy], [tool.coverage], hardened pytest ini
```

### Pattern 1: Required-engine switch (CI-01) — invert skip to fail at the fixture boundary

**What:** A single helper in `tests/conftest.py` that every engine fixture calls instead of calling `pytest.skip` directly. It reads `ENCINO_ORM_REQUIRE_ENGINES` and either fails or skips.

**When to use:** Every one of the 8 existing skip sites.

**Current skip sites (all verified):**

| File:line | Engine | Marker needed |
|-----------|--------|---------------|
| `tests/test_mysql.py:25` | mysql | `integration` |
| `tests/test_postgresql.py:67` | postgresql | `integration` |
| `tests/test_mariadb.py:38` | mariadb | `integration` + `optional_engine` |
| `tests/test_mssql.py:124` | mssql | `integration` + `optional_engine` |
| `tests/test_mssql.py:135` | mssql | `integration` + `optional_engine` |
| `tests/test_oracle.py:103` | oracle | `integration` + `optional_engine` |
| `tests/test_redis_cache.py:28` | redis | `integration` + `optional_engine` |
| `tests/test_redis_cache.py:35` | redis | `integration` + `optional_engine` |

**Shape:**

```python
# tests/conftest.py
import os
import pytest

def required_engines() -> set[str]:
    """Motores que DEBEN estar disponibles. Se activa solo en CI (D-03)."""
    raw = os.getenv("ENCINO_ORM_REQUIRE_ENGINES", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

def engine_unavailable(engine: str, exc: Exception) -> None:
    """Falla si el motor es requerido; si no, omite. Reemplaza a pytest.skip."""
    if engine.lower() in required_engines():
        pytest.fail(
            f"{engine} es un motor requerido (ENCINO_ORM_REQUIRE_ENGINES) "
            f"pero no está disponible: {exc!r}"
        )
    pytest.skip(f"{engine} no disponible: {exc}")
```

**Important nuance (Pitfall 1):** the existing fixtures wrap connection setup in a bare `except Exception`. That means a typo'd env var, a renamed driver, or an `ImportError` all currently degrade to *skip*. Phase 1 must not fix this (that is Pitfall 1 item 2 and is not in CI-01's scope), but the switch makes it moot in CI: any failure reaching `engine_unavailable()` for a required engine becomes a hard failure. Document the bare-`except` narrowing as a Phase 2 follow-up.

### Pattern 2: JUnit skip gate (CI-02) — `-m` deselect + XML parse

**What:** Run the required-engine job with `-m "not optional_engine"`, emit `--junitxml`, then parse it and exit non-zero if any `<testsuite>` reports `skipped > 0`.

**Why `-m` and not a custom plugin:** JUnit XML carries no marker information, so a pure XML gate cannot distinguish "legitimate optional-engine skip" from "required engine silently skipped". Deselecting the optional-engine tests before the run removes the ambiguity at the source. **Verified:** a run with `-m "not asyncio"` on `tests/test_pool.py` produced `tests="1"` for 1 passed + 20 deselected — deselected tests do not appear in the XML at all.

**Verified XML shape (pytest 9.1.1):**

```xml
<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="0" skipped="13" tests="19" time="26.699" ...>
    <testcase classname="..." name="..." time="0.001" />
```

**Gate script shape (`tools/ci/check_skips.py`):**

```python
"""Falla si algún test fue omitido (CI-02). Ver .planning/phases/01-*/01-RESEARCH.md."""
import sys
import xml.etree.ElementTree as ET

def total_skipped(path: str) -> int:
    root = ET.parse(path).getroot()
    # pytest puede emitir varios <testsuite>; se suman todos.
    return sum(int(ts.get("skipped", 0)) for ts in root.iter("testsuite"))

def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "junit.xml"
    skipped = total_skipped(path)
    if skipped:
        print(f"FALLO: {skipped} test(s) omitidos. Un skip en CI es un gate roto.", file=sys.stderr)
        return 1
    print("OK: 0 tests omitidos.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

**Workflow step:**

```yaml
      - name: Run tests
        env:
          ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql
        run: >
          uv run pytest -q -m "not optional_engine"
          --junitxml=junit.xml
          --cov=encino_orm --cov-branch
          --cov-report=
        # --cov-report= evita el reporte por job; el combine lo hace el job de coverage

      - name: Gate — ningún test omitido
        if: always()
        run: uv run python tools/ci/check_skips.py junit.xml
```

`if: always()` ensures the gate reports the skip count even when pytest already failed for another reason.

**Cost note (measured):** an induced connection failure is slow — pointing `ENCINO_ORM_POSTGRES_PORT` at a closed port made `tests/test_postgresql.py` take **26.7 s** (vs 1.5 s) because of connection timeouts. A genuinely missing required engine will therefore add ~20–30 s per affected file before failing. `ci.yml`'s `timeout-minutes: 15` has room, but do not lower it.

### Pattern 3: Coverage combine across matrix legs (CI-05, mechanism only per D-06)

```toml
[tool.coverage.run]
source_pkgs = ["encino_orm"]
branch = true
parallel = true          # REQUIRED: cada job escribe su propio archivo

[tool.coverage.report]
precision = 1
show_missing = true
fail_under = 82          # ratchet: baseline CI medido = 83% (ver §Coverage)
exclude_also = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
]
```

```yaml
      - name: Run tests
        env:
          COVERAGE_FILE: .coverage.py${{ matrix.python-version }}
        run: uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=

      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-py${{ matrix.python-version }}
          path: .coverage.py${{ matrix.python-version }}*
          include-hidden-files: true   # OBLIGATORIO: .coverage.* es un archivo oculto
```

> **Verified gotcha:** `actions/upload-artifact` excludes hidden files by default. `include-hidden-files: true` is required or the `.coverage.py3.10` data file is silently never uploaded and `coverage combine` finds nothing. [VERIFIED: `actions/upload-artifact` README, line 436 — "If you need to upload hidden files, you can use the `include-hidden-files` input."]

```yaml
  coverage:
    needs: [test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/setup-uv@v5
        with: { version: "0.12.15", enable-cache: true }
      - run: uv sync --group dev
      - uses: actions/download-artifact@v4
        with: { pattern: coverage-py*, merge-multiple: true }
      - run: uv run coverage combine
      - run: uv run coverage report          # aplica fail_under de pyproject
```

**`[tool.coverage.paths]`:** not required while every job checks out to the same absolute path on the same runner (`/home/runner/work/...`). Add it only if coverage is ever combined across machines with different checkout paths. [ASSUMED — reasoning from coverage.py's documented `combine` behavior; not exercised in this session because combining was done in-process.]

### Pattern 4: Reusable-workflow release gate (CI-08)

**Critical constraint:** `needs:` cannot reference a job in a *different* workflow file. There is no way to write `release.yml: publish: needs: [ci.yml's job]`. The three valid mechanisms are (1) `on: workflow_call` reusable workflow, (2) `workflow_run` trigger, (3) duplicating the gates inline.

**Recommended (1):** add `workflow_call` to `ci.yml`'s triggers, then call it from `release.yml`.

```yaml
# ci.yml — top
on:
  push:
    branches: [main]
  pull_request:
  workflow_call:            # <- añadido para CI-08

# release.yml
jobs:
  ci:
    uses: ./.github/workflows/ci.yml
    # `./` = mismo commit que el caller (verificado en docs de GitHub)
  publish:
    needs: [ci]
    runs-on: ubuntu-latest
    steps: [...]
```

**Verified from GitHub docs:** `./.github/workflows/{filename}` references the workflow *at the same commit as the caller*; reusable workflows are called at job level with `uses:`, not from a step; up to 10 levels of nesting; service containers are permitted inside reusable workflows. `secrets: inherit` is available if ever needed (CI needs none today).

**Rejected alternative — `workflow_run`:** a `workflow_run`-triggered workflow executes against the default branch, not the pushed tag, which is wrong for publishing a tagged artifact. Rejected.

### Anti-Patterns to Avoid

- **Turning on `ruff format` and `ruff check` in the same commit.** The format commit touches 61 of 101 files; mixing it with rule fixes makes both unreviewable and unbisectable (Pitfall 12).
- **Copying `STACK.md`'s `[tool.mypy]` block verbatim.** It is not non-strict; it yields 458 errors. See §Mypy.
- **Pinning the coverage floor from a local run.** Local has all six engines; CI has two. See §Coverage.
- **Implementing the skip gate as inline YAML.** It becomes untestable; a checked-in script can have its own unit test.
- **Using `continue-on-error: true` on any of the new gate jobs.** That recreates the exact "green CI that verifies nothing" failure this phase exists to eliminate.
- **Setting `--strict-markers` and assuming it validates `-m` expressions.** It does not — verified: `pytest --strict-markers -m "integration"` silently deselected all 510 tests with no error. The marker only becomes meaningful once it is *applied* to tests.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Test result reporting | A custom result serializer | `pytest --junitxml=` | Built-in, schema-stable, already verified to carry `skipped`/`tests`/`errors`/`failures` per suite. |
| Coverage merging across jobs | A custom `.coverage` merger | `coverage combine` with `[tool.coverage.run] parallel = true` | The only supported path; handles the `.coverage.<host>.<pid>.<rand>` naming. |
| Skip-vs-fail policy | A custom pytest plugin | A 10-line helper in `conftest.py` + `pytest.fail` / `pytest.skip` | The policy is per-fixture, not per-session; a plugin adds surface for no gain. |
| Release gating | A job that polls the GitHub Checks API for CI status | `on: workflow_call` + `jobs.<id>.uses` + `needs:` | Native, race-free, and works on tag refs. Polling has TOCTOU and token-scope problems. |
| Formatting / import sorting | `black` + `isort` | `ruff format` + ruff's `I` rules | One binary, one config, one CI step. |
| Type checking pydantic models | Custom validators or `# type: ignore` everywhere | `mypy` with `plugins = ["pydantic.mypy"]` | The plugin understands `BaseModel` field/validator interaction; a hand-rolled checker cannot. |
| Dependency vulnerability data | A hand-maintained CVE list | `uv audit` (OSV) + `pip-audit` (PyPA advisory DB) | Two independent advisory sources; both maintained upstream. |

**Key insight:** every item in this phase is a *known solved problem with an official tool*. The failure mode is not "we built the wrong thing" — it is "we configured the right thing so loosely that it never fires". Effort belongs in the *verification steps* (prove each gate fails when it should), not in the implementation.

## Runtime State Inventory

> Phase 1 is configuration + tests only. It changes no stored data, no service configuration, and no OS registrations. Included here to state that explicitly rather than leave it unexamined.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | **None.** No database schema, collection name, key, or `user_id` is renamed by this phase. | None — verified by reading all phase requirements (CI-01…CI-09) and the phase boundary in `01-CONTEXT.md` (`"No entrega correcciones de comportamiento del ORM"`). |
| Live service config | **None.** No external service configuration changes. The `ENCINO_ORM_REQUIRE_ENGINES` env var is supplied per-job in `ci.yml` and does not exist anywhere else. | None — verified by grep: no existing reference to `ENCINO_ORM_REQUIRE_ENGINES` in the repo. |
| OS-registered state | **None.** No Task Scheduler entries, pm2 processes, launchd plists, or systemd units reference anything this phase touches. | None — verified: the repo contains no such registrations. |
| Secrets / env vars | **None added.** The phase introduces one new *non-secret* env var (`ENCINO_ORM_REQUIRE_ENGINES`). Existing `ENCINO_ORM_<ENGINE>_*` names are unchanged. `PYPI_API_TOKEN` is untouched in Phase 1 (REL-03 / Phase 8 owns it). | None — but note `release.yml` currently reads `secrets.PYPI_API_TOKEN`; the reusable-workflow change must not alter secret handling. |
| Build artifacts | **One.** Adding `encino_orm/py.typed` changes the wheel contents. **Verified by building the wheel locally:** hatchling includes `encino_orm/py.typed` automatically under the existing `[tool.hatch.build.targets.wheel] packages = ["encino_orm"]` — no `pyproject.toml` change is required. | None — verified by `uv build --wheel` and inspecting the archive. Stale `dist/` artifacts (0.2.1/0.2.4/0.2.5) are gitignored. |

## Common Pitfalls

### Pitfall 1: Green CI that verifies nothing — dialect suites silently skip (Pitfall 1)

**What goes wrong:** CI reports success while zero tests executed against four of the six engines. A skipped suite is a passing suite.
**Why it happens:** "Skip when the service isn't there" is correct for local dev and wrong for CI; both paths share one fixture.
**How to avoid:** The required-engine switch (CI-01) *plus* the JUnit gate (CI-02). Either alone is insufficient: the switch is bypassed if someone deletes the env var; the gate is bypassed if the optional-engine skips are not deselected first.
**Warning signs:** CI duration does not grow after adding an engine; `NNN skipped` in the summary with nobody able to name them; the local and CI skip counts match.
**Verification for this phase:** Success criterion 1 ("removing a required engine's CI service makes its job fail") must be demonstrated, not assumed.

### Pitfall 2: Aggregate coverage that masks untested dialect paths (Pitfall 2)

**What goes wrong:** A `fail_under` number passes while the broken dialect path is untested. `model/model.py:792` (`return row["COUNT(*)"]`) is *executed* by the SQLite suite, so coverage marks it covered — and it raises `KeyError` on PostgreSQL. The bug and the coverage come from the same line.
**Why it happens:** Coverage is computed over *shared* lines, so dialect-specific *behavior* is invisible. One engine's tests pay for another's untested lines.
**How to avoid:** Per-engine coverage runs combined with `coverage combine` (union, still not per-dialect) makes the illusion explicit; per-dialect integration tests (Phase 2, DIAL-09) are the real fix; per-module floors on the six adapters are the Phase-2 mechanism D-04 describes.
**Warning signs:** `pytest --cov` reports a high number but no engine test asserts on `count`/`paginate`/`list_tables`; coverage does not change when an engine's test file is deleted; `# pragma: no cover` appears in dialect branches.
**Phase-1 boundary:** Phase 1 builds the mechanism only (D-06). Do **not** attempt the per-dialect floor here — no `dialects/` seam exists yet.

### Pitfall 2b: Setting the coverage floor from a local run (NEW — measured in this session)

**What goes wrong:** The local floor is set at 88% and CI fails immediately at 83%.
**Why it happens:** All six engines run in local Docker; CI provides only MySQL and PostgreSQL, so four engine test files are excluded and `oracle.py` coverage collapses from 59% to 16%.
**How to avoid:** Use the CI-equivalent measurement (83%) as the ratchet baseline. Record the measurement and the reason in a comment next to `fail_under`.
**Warning signs:** the coverage job is red on the very first PR; someone lowers the number without recording why.

### Pitfall 3: Big-bang lint/type/coverage gates across 101 files (Pitfall 12)

**What goes wrong:** A whole-repo `ruff format` diff makes every other change unreviewable and conflicts with every open branch; a strict mypy config produces hundreds of errors and the pragmatic response is `# type: ignore` everywhere, turning the gate into decoration.
**Why it happens:** The tools are trivial to *enable* and expensive to *adopt*.
**How to avoid:** Three isolated mechanical commits: (1) `ruff format` only, registered in `.git-blame-ignore-revs`; (2) `ruff check` with a narrow ruleset + `per-file-ignores`; (3) `mypy` at the lowest measured level with a per-module ratchet and `--warn-unused-ignores`. Separate CI jobs so a format failure cannot hide a test failure.
**Warning signs:** a lint PR containing logic changes; `# type: ignore` count increasing release over release; mypy excluded from CI "for now".
**Baseline for the ratchet:** `# type: ignore` = **0**, `# noqa` = **0** today. Any increase is visible.

### Pitfall 4: `pytest-asyncio` loop-scope ambiguity and hidden cross-test state (Pitfall 15)

**What goes wrong:** `asyncio_mode = "auto"` is set but `asyncio_default_fixture_loop_scope` is unset. If a future change moves to a session-scoped loop, a leaked pool or the `set_default_db` singleton survives across tests and produces order-dependent failures.
**How to avoid:** Set **both** `asyncio_default_fixture_loop_scope = "function"` and `asyncio_default_test_loop_scope = "function"` explicitly. Both keys are confirmed valid in pytest-asyncio 1.4.0 (`pytest --help` lists them).
**Verified:** the current suite emits **zero warnings**, and a full run under `-W error` passes (510 passed). So enabling `filterwarnings = ["error"]` is free today.
**Warning signs:** deprecation warnings in the pytest summary; failures that disappear when a test runs alone; tests that pass in file order and fail under shuffling.

### Pitfall 5: `PT011` versus D-09 — a real conflict the planner must resolve

**What goes wrong:** Pitfall 24 recommends enabling ruff's `PT011` (`pytest-raises-too-broad`) to prevent `pytest.raises(Exception)` rot. D-09 explicitly forbids rewriting those asserts in Phase 1. Enabling `PT011` without an ignore list makes the lint job red on day one (25 violations in `tests/`).
**How to avoid:** Select `PT` but add `"tests/**" = ["PT011", "B017"]` to `per-file-ignores`, with an inline comment naming the follow-up phase. This keeps the *rule set* honest (it will catch new violations once the ignores are lifted) while honoring D-09. **Do not** silently drop `PT` — `PT012`/`PT018`/`PT006` are genuinely useful and cost nothing.
**Warning signs:** someone removes `PT` entirely to make the job green; the `per-file-ignores` entry has no comment.

### Pitfall 6: `S608` flooding the bandit ruleset (Pitfall 10)

**What goes wrong:** Enabling ruff's `S` (flake8-bandit) rules produces 38 `S608` (`hardcoded-sql-expression`) hits — every dialect builder interpolates SQL by design. The reflex is to add `# nosec` everywhere and the check becomes decoration.
**How to avoid:** Scope it. Add `S608` to `per-file-ignores` for the dialect builder modules only (`encino_orm/{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py`, `encino_orm/base.py`, `encino_orm/model/model.py`, `encino_orm/transfer.py`), with a comment stating these are the intentional interpolators and that Phase 2 centralizes and validates them. Keep the rest of `S` active — it catches real things: `S102` (`exec` in `http/routes.py:73` and `graphql/schema.py:100` — CFG-03, Phase 6), `S105` (hardcoded password), `S311` (`random` in `base.py:70`, used for jittered backoff — legitimate), `S324` (`sha1` in `model/cached.py:20` and `model/filter.py:167` — cache keys, not security).
**Warning signs:** `# nosec` count growing; `S` deselected entirely.

## Code Examples

### Ruff configuration (measured against the real baseline)

```toml
# Source: measured on this repo with ruff 0.16.8, 2026-09-17
[tool.ruff]
target-version = "py310"     # must match requires-python; drives UP-rule rewrites
line-length = 100            # at 88 the baseline is 195 source errors vs 128 at 100

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4", "SIM", "PERF", "FURB",
          "ASYNC", "RUF", "S", "PT"]
# Deliberately NOT enabled in this milestone: "ANN", "D", "PL".
# Rationale: 101 files / 507 tests; enabling them wholesale produces an
# unreviewable diff and buries the real findings.

[tool.ruff.lint.per-file-ignores]
# D-09: no se reescriben asserts genéricos en Fase 1. PT011/B017 se levantan en Fase 4.
"tests/**" = ["S101", "PT011", "B017", "ARG001", "ARG002"]
# S608: interpoladores SQL intencionales. La validación centralizada llega en Fase 2 (DIAL-02).
"encino_orm/sqlite.py"     = ["S608"]
"encino_orm/mysql.py"      = ["S608"]
"encino_orm/mariadb.py"    = ["S608"]
"encino_orm/postgresql.py" = ["S608"]
"encino_orm/mssql.py"      = ["S608"]
"encino_orm/oracle.py"     = ["S608"]
"encino_orm/base.py"       = ["S608"]
"encino_orm/transfer.py"   = ["S608"]
"encino_orm/model/model.py" = ["S608"]
# S102: handlers generados con exec(); se sustituyen en Fase 6 (CFG-03).
"encino_orm/http/routes.py"    = ["S102"]
"encino_orm/graphql/schema.py" = ["S102"]

[tool.ruff.lint.isort]
known-first-party = ["encino_orm"]
```

**Measured error counts at this configuration:**

| Scope | Ruleset | line-length | Errors |
|-------|---------|-------------|--------|
| `encino_orm/` | full proposed | 100 | **128** |
| `encino_orm/` | full proposed | 88 | **195** |
| `encino_orm/` | narrow `E,F,I,UP,PT,B` | 100 | **52** |
| `tests/` | narrow `E,F,I,UP,PT,B` (ignoring S101) | 100 | **102** |
| `encino_orm/` + `tests/` | full proposed | 100 | **1479** (1044 of them `S101` in tests) |

**Practical landing order:** the format-only commit first (61 files), then `ruff check --fix` for the 23 auto-fixable findings, then hand-fix the remainder. Two realistic options for the blocking job:
- **Option A (recommended):** narrow ruleset (`E,F,I,UP,B,C4,SIM,PERF,FURB,ASYNC,RUF,S,PT`) and fix the ~128 source findings. This is the honest gate — every selected rule is enforced everywhere.
- **Option B (faster):** start with `E,F,I,UP,PT,B` (~52 source + ~102 test findings) and ratchet the remaining families in later. The ruleset is smaller but still catches unused imports, import order, and pyupgrade drift.

Either is defensible; Option A better matches STACK.md's intent and the phase goal ("a signal that would have caught the `COUNT(*)` bug" — `ASYNC`/`RUF` target exactly this bug class).

### Mypy configuration (measured three-level ladder)

```toml
# Source: measured on this repo with mypy 2.3.1, 2026-09-17
[tool.mypy]
python_version = "3.10"
files = ["encino_orm"]
ignore_missing_imports = true
plugins = ["pydantic.mypy"]
warn_unused_ignores = true      # evita la podredumbre de # type: ignore

# RATCHET: módulos que aún arrastran errores. Quitar entradas a medida que se
# limpian; NUNCA añadir sin justificación. Baseline 2026-09-17: 85 errores en 21 archivos.
[[tool.mypy.overrides]]
module = [
    "encino_orm.model.model",       # 43 errores
    "encino_orm.pool",              # 12
    "encino_orm.model.query_builder",  # 10
    "encino_orm.security.models",   # 8
    "encino_orm.model.cached",      # 8
]
ignore_errors = true
```

**Measured error ladder (mypy 2.3.1, `--python-version 3.10`):**

| Configuration | Errors | Files |
|---------------|--------|-------|
| defaults + `--ignore-missing-imports` | **81** | 20 |
| defaults + pydantic plugin | **85** | 21 |
| + `--check-untyped-defs` | **124** | 21 |
| `STACK.md`'s proposed config | **458** | 41 |

**Error breakdown at the 81-error level:** `assignment` 23, `var-annotated` 15, `attr-defined` 15, `valid-type` 5, `name-defined` 5, `union-attr` 4, `override` 3, `misc` 3, `arg-type` 3, plus singles. Concentrated in `model/model.py` (43), `pool.py` (12), `query_builder.py` (10).

**Two viable Phase-1 shapes:**
- **Ratchet via `ignore_errors` overrides** (sketch above): the gate is blocking for the ~30 clean modules and green immediately. Weakness: the five excluded modules are unchecked until the overrides are lifted.
- **Fix the cheap categories, override the rest:** the 15 `var-annotated` and 23 `assignment` errors are mostly mechanical annotations; fixing them lets `pool.py` and `query_builder.py` into the checked set. `model/model.py`'s 43 errors stay overridden (it is the file Phase 2/3 rewrite heavily anyway).

The five `name-defined` errors are all `Name "child.__name__" is not defined` in `graphql/resolvers.py` and `graphql/types.py` — an artifact of the `exec()`-generated handler pattern (CFG-03, Phase 6). Override `encino_orm.graphql.*` with a comment pointing at CFG-03 rather than papering over it with `# type: ignore`.

### pytest configuration (hardened)

```toml
# Source: verified against pytest 9.1.1 + pytest-asyncio 1.4.0 on this repo, 2026-09-17
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"   # pytest-asyncio 1.4 exige ambos explícitos
asyncio_default_test_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
xfail_strict = true                                # hoy no hay ningún xfail; es gratis
filterwarnings = [
    "error",
    # Allowlist acotada y comentada (D-07). Añadir solo con justificación escrita.
]
markers = [
    "integration: requiere un motor real (MySQL/PostgreSQL en CI; opcionales en local)",
    "optional_engine: motor no requerido en Fase 1 (MariaDB/Redis/MSSQL/Oracle); ver D-02",
    "concurrency: tests de pool/carreras; se excluyen de corridas con xdist",
    "benchmark: medidos por pytest-codspeed; excluidos de corridas normales",
]
```

**Verified safe today:** 0 xfails, 0 `@pytest.mark.skip`, 0 `skipif`, 0 `importorskip`, 0 warnings under `-W error`, and the only marker in use is `pytest.mark.asyncio` (306 occurrences). Enabling all four knobs costs nothing right now.

**`filterwarnings = ["error"]` residual risk:** the allowlist is empty locally, but the CI matrix runs Python 3.10–3.13. A version-specific `DeprecationWarning` on 3.12/3.13 would fail that leg only. **Verified:** `encino_orm/` contains **no** `sys.platform`, `os.name`, `platform.system`, or `datetime.utcnow()` usages, so the usual 3.12 deprecation triggers are absent. If a leg fails, add a narrowly-scoped, commented `ignore::DeprecationWarning:<module>` entry rather than weakening the global rule.

### Marker application map (CI-08's `integration` marker + D-02's `optional_engine`)

| File | Class | Tests | `integration` | `optional_engine` |
|------|-------|-------|---------------|-------------------|
| `test_mysql.py` | TestMysqlLifecycle | 5 | ✅ | — |
| | TestMysqlBuildersAndQueries | 7 | ✅ | — |
| | TestMysqlMigrations | 3 | ✅ | — |
| `test_postgresql.py` | TestPostgresInternal | 6 | — (unit) | — |
| | TestPostgresLifecycle | 4 | ✅ | — |
| | TestPostgresBuildersAndQueries | 7 | ✅ | — |
| | TestPostgresMigrations | 2 | ✅ | — |
| `test_mariadb.py` | `test_mariadb_is_mysql_subclass` / `_ddl_map_` | 2 | — (unit) | — |
| | TestMariadbLifecycle | 3 | ✅ | ✅ |
| `test_mssql.py` | TestMssqlInternal | 11 | — (unit) | — |
| | TestMssqlLifecycle | 4 | ✅ | ✅ |
| `test_oracle.py` | TestOracleInternal | 9 | — (unit) | — |
| | TestOracleLifecycle | 3 | ✅ | ✅ |
| `test_redis_cache.py` | TestRedisCacheBackend | 2 | ✅ | ✅ |
| | TestCachedModelRedis | 1 | ✅ | ✅ |

**Totals:** `integration` = **41** tests; `optional_engine` = **13** (a subset of `integration`); required-engine integration = **28**.
`-m "not integration"` → 469 tests (this is what `README.md:130` should select).
`-m "not optional_engine"` → 497 tests (this is what the required-engine CI job runs).

**Application style:** use module-level `pytestmark = pytest.mark.integration` only for files where *every* class is live (`test_mysql.py`, `test_redis_cache.py`); use class-level decorators in the mixed files. This preserves free coverage from the 28 optional-engine *unit* tests, which pass without any live engine and should keep running in the required job.

### `.git-blame-ignore-revs`

```bash
# 1. Commit the format-only change
git commit -m "style: ruff format (mecánico, sin cambios de lógica)"
# 2. Record its SHA (the file does not exist yet — verified)
git rev-parse HEAD >> .git-blame-ignore-revs
git commit -am "chore: registrar el commit de formato en .git-blame-ignore-revs"
# 3. Enable locally (GitHub honors the file automatically)
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `flake8` + `black` + `isort` + `pyupgrade` + `bandit` | `ruff` (`check` + `format`, rule families `S`, `UP`, `ASYNC`, `RUF`) | ~2024 | One binary, one config, one CI step. |
| `coverage report --fail-under` as a single global number | Per-job `COVERAGE_FILE` + `coverage combine` + ratcheted floor | coverage 6+ / pytest-cov 5+ | Required for the multi-engine topology; the single number cannot express per-dialect floors. |
| `bandit` as a standalone CI job | ruff's `S` rules, scoped by `per-file-ignores` | ruff 0.1+ | Same checks, same pass, no second config. |
| `pip-audit` reading `requirements.txt` | `uv audit` reading `uv.lock` directly (OSV) | uv 0.12 | No export step; audits the locked set including extras/groups. |
| `pypa/gh-action-pypi-publish@master` | `@release/v1` / OIDC trusted publishing | 2023+ | `master` is sunset. Phase 8 concern (REL-03). |
| `asyncio.Barrier` for concurrency tests | Hand-rolled `asyncio.Event` barrier | Python 3.11 | Project floor is 3.10; `Barrier`/`TaskGroup` are unavailable. Phase 4 concern. |

**Deprecated/outdated in this repo:**
- `ruff>=0.16.8` unconfigured — installed but doing nothing. This phase activates it.
- `README.md:130`'s `uv run pytest -m "not integration"` — **verified to be a no-op today** (selects all 510 tests because no test carries the marker). This phase makes it real (D-08).
- `asyncio_default_fixture_loop_scope` unset — pytest-asyncio's documented configuration warning trigger.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `astral-sh/setup-uv@v5` accepts a `version:` input to pin the uv version in CI | §Pattern 3 | CI installs whatever uv version the action defaults to; `uv audit` availability becomes non-deterministic. Mitigation: verify the input name against the action's README before writing the workflow. |
| A2 | `uv audit` exits non-zero when it finds a vulnerability | §Dependency Scanning | If it exits zero on findings, CI-07 is decorative. Must be verified empirically immediately after the uv upgrade — the local 0.8.22 cannot test this. |
| A3 | `[tool.coverage.paths]` is unnecessary when all jobs share the same GHA checkout path | §Pattern 3 | `coverage combine` produces empty/wrong results. Mitigation: the first CI run will show it immediately; add `paths` if `combine` reports "No data to combine". |
| A4 | `filterwarnings = ["error"]` will not fail on Python 3.12/3.13 CI legs | §pytest configuration | A version-specific deprecation warning fails one matrix leg. Mitigation: the narrow, commented `ignore` entry D-07 already permits. |
| A5 | Pinning `ruff` exactly is necessary to keep the format-only commit stable | §Standard Stack | A newer ruff reformats differently and `ruff format --check` fails on an unrelated PR. Low cost to pin either way. |
| A6 | Fixing the `var-annotated`/`assignment` mypy errors is "mechanical" | §Mypy | Some may require real type decisions, expanding scope beyond D-09's "minimal fixes". Mitigation: default to the `ignore_errors` ratchet and treat fixes as optional. |
| A7 | The 4-engine CI job can absorb ~20–30 s of connection-timeout cost when a required engine is missing | §Pattern 2 | If multiple required engines are missing simultaneously, the fail path could approach `timeout-minutes: 15`. Mitigation: measure the real failure path on the first deliberate-failure run. |

## Open Questions

1. **Does `uv audit` report pre-existing vulnerabilities in the current locked set?**
   - What we know: `uv audit` audits "known vulnerabilities, as well as 'adverse' statuses such as deprecation and quarantine" (official CLI reference). `pip-audit` exists as a cross-check. `PyJWT<2.13` is capped and `aiomysql<0.3.2` is capped, both flagged in `CONCERNS.md`.
   - What's unclear: whether the audit is clean today. It cannot be run until uv ≥ 0.12.15 is installed.
   - Recommendation: make CI-07's job **blocking from day one but with an explicit, commented `--ignore-until-fixed` allowlist** for any pre-existing finding, each entry naming the phase that fixes it. Do not use `continue-on-error` — that would repeat the phase's core anti-pattern. If the audit is clean, delete the allowlist.

2. **What is the exact CI coverage number on Linux, across four Python versions?**
   - What we know: 83% on Windows with MySQL+PostgreSQL only (475 tests).
   - What's unclear: whether Linux/3.10–3.13 shifts it. `encino_orm/` has no platform conditionals (verified), so the drift should be ~0.
   - Recommendation: set `fail_under = 82` provisionally, then raise it to the measured CI value in the same plan once the first green run reports it. Record both numbers in the config comment.

3. **Should the JUnit gate live in `tools/ci/` or inline in the workflow?**
   - What we know: a checked-in script is unit-testable; inline YAML is not.
   - What's unclear: whether the repo wants a `tools/` tree (it currently has none).
   - Recommendation: `tools/ci/check_skips.py` + a `tests/test_ci_harness.py` that exercises it against fixture XML. This is the only new top-level directory the phase introduces.

4. **Is the `integration` marker's `README.md` command verified anywhere in CI?**
   - What we know: `-m "not integration"` is a documented command that currently does nothing.
   - What's unclear: nothing functionally — but the phase should add a regression guard so it cannot silently revert.
   - Recommendation: add a CI step (or a test) asserting `pytest --collect-only -m "integration"` selects a non-zero count. A one-line check that would have caught the current bug.

5. **Does the phase need to touch `docs.yml` or `publish-testpypi.yml`?**
   - What we know: `docs.yml` runs `uv sync --group dev`, so every new dev dependency is installed there too. `publish-testpypi.yml` is a manual TestPyPI publisher.
   - What's unclear: whether `mkdocs build --strict` is sensitive to anything ruff changes. Docstrings are Spanish prose; `ruff format` does not alter string contents, and no `D` rules are enabled.
   - Recommendation: leave both untouched in Phase 1, but run `mkdocs build --strict` locally once after the format commit to confirm. REL-03 (Phase 8) owns `publish-testpypi.yml`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | CI-07 (`uv audit`, `uv lock --check`) | ⚠️ present but **too old** | **0.8.22** (need ≥ 0.12.15) | `uv lock --check` **works today** (verified, exit 0). `uv audit` **absent** (`error: unrecognized subcommand 'audit'`). Fallback: `pip-audit` via `uv export --format requirements-txt --no-emit-project --no-hashes` (verified, 155 lines, exit 0). |
| Docker | Local multi-engine verification (5 of 6 engines) | ✅ | running | — |
| MySQL 8.0 | CI-01 required engine | ✅ | container `db-mysql-1` on 3306 | — |
| PostgreSQL 16 | CI-01 required engine | ✅ | container `db-postgres-1` on 5432 | — |
| MariaDB 11 | D-02 optional engine (local only) | ✅ | container `db-mariadb-1` on 3307 | `optional_engine` marker |
| SQL Server 2022 | D-02 optional engine (local only) | ✅ | container `db-mssql-1` on 1433 | `optional_engine` marker |
| Oracle XE | D-02 optional engine (local only) | ✅ | container `db-oracle-1` on 1521 | `optional_engine` marker |
| Redis | D-02 optional engine (local only) | ✅ | container `db-redis-1` on 6379 | `optional_engine` marker |
| CPython 3.10.18 | Project floor, local venv | ✅ | 3.10.18 | — |
| CPython 3.14.7 | System interpreter | ✅ | 3.14.7 | Not a CI leg |
| `git` | `.git-blame-ignore-revs` | ✅ | 2.51.0.windows.1 | — |
| `ruff` | CI-03 | ✅ | 0.16.8 (installed, unconfigured) | — |
| `mypy` | CI-04 | ❌ | — | None — must be added as a dev dependency |
| `pytest-cov` / `coverage` | CI-05 | ❌ | — | None — must be added as dev dependencies |
| `pip-audit` | CI-07 | ❌ | — | `uv audit` (once uv is upgraded) |

**Missing dependencies with no fallback:**
- `mypy`, `pytest-cov`, `coverage`, `pip-audit` — all must be added to `[dependency-groups].dev`. All are Phase-1 requirements; none block the other plans.
- `uv` upgrade to ≥ 0.12.15 — **blocks CI-07's primary mechanism**. The `uv lock --check` half of CI-07 works today.

**Missing dependencies with fallback:**
- `uv audit` → `pip-audit` via `uv export` (a different, equally valid advisory source). This means CI-07 can ship even if the uv upgrade is deferred, but the roadmap's 01-01 sequence puts the upgrade first, which is correct.

**Local verification note (important for the plan's verification steps):** because all six engines are running locally, **a local run produces 0 skips today** (verified: `510 passed, 0 skipped`). The JUnit gate and the required-engine switch therefore cannot be validated locally by simply "not having an engine". To prove they work, the verifier must *induce* the failure — e.g. `ENCINO_ORM_POSTGRES_PORT=1 uv run pytest tests/test_postgresql.py` (verified: 6 passed, 13 skipped in 26.7 s) and confirm that with `ENCINO_ORM_REQUIRE_ENGINES=postgresql` the same command fails instead. Every success criterion in this phase needs an induced-failure demonstration.

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json`, so this section is included (treated as enabled).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (to be hardened by 01-03) |
| Quick run command | `uv run pytest -q -m "not optional_engine"` |
| Full suite command | `uv run pytest -q` |
| Coverage run | `uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=term-missing` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CI-01 | Required engine absent → `pytest.fail`, not skip | unit | `uv run pytest tests/test_ci_harness.py -k require_engines -x` | ❌ Wave 0 |
| CI-01 | Required engine absent → job fails (integration proof) | manual/CI | `ENCINO_ORM_REQUIRE_ENGINES=postgresql ENCINO_ORM_POSTGRES_PORT=1 uv run pytest tests/test_postgresql.py` → non-zero exit | ❌ manual demonstration |
| CI-02 | `skipped > 0` in JUnit XML → non-zero exit | unit | `uv run pytest tests/test_ci_harness.py -k check_skips -x` | ❌ Wave 0 |
| CI-02 | Gate passes on a clean run | unit | fixture XML with `skipped="0"` | ❌ Wave 0 |
| CI-03 | `ruff format --check` clean | CI job | `uv run ruff format --check encino_orm tests` | ❌ config Wave 0 |
| CI-03 | `ruff check` clean | CI job | `uv run ruff check encino_orm tests` | ❌ config Wave 0 |
| CI-04 | `py.typed` ships in the wheel | packaging | `uv build --wheel && python -c "import zipfile,glob; assert any('py.typed' in n for n in zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]).namelist())"` | ❌ Wave 0 (verified manually in research) |
| CI-04 | `mypy encino_orm` clean under the ratchet | CI job | `uv run mypy encino_orm` | ❌ config Wave 0 |
| CI-05 | `coverage report --fail-under=82` passes; a deliberate coverage drop fails | CI job | `uv run coverage report` | ❌ config Wave 0 |
| CI-06 | `--strict-markers` rejects an unregistered marker | unit | `uv run pytest --strict-markers -k test_strict_marker_probe` (negative test in `test_ci_harness.py`) | ❌ Wave 0 |
| CI-06 | `filterwarnings=["error"]` turns a warning into a failure | unit | probe test emitting `warnings.warn` | ❌ Wave 0 |
| CI-06 | `-m "integration"` selects a non-zero count | CI job | `uv run pytest --collect-only -q -m "integration"` | ❌ Wave 0 |
| CI-07 | `uv lock --check` clean | CI job | `uv lock --check` (verified working in 0.8.22) | ✅ command exists |
| CI-07 | `uv audit` clean | CI job | `uv audit` (needs uv ≥ 0.12.15) | ❌ after upgrade |
| CI-08 | Publish cannot run while gates are red | CI proof | push a tag on a deliberately-failing branch; assert `publish` is skipped | ❌ manual demonstration |
| CI-09 | Pool overshoot is characterized | characterization | `uv run pytest tests/test_pool_characterization.py -x` | ❌ Wave 0 |
| CI-09 | `last_id` scoping is characterized | characterization | same file | ❌ Wave 0 |
| CI-09 | Release semantics are characterized | characterization | same file | ❌ Wave 0 |
| CI-09 | `close()` behavior is characterized | characterization | same file | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest -q` (7.5 s locally — cheap enough to run on every commit)
- **Per wave merge:** `uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=term-missing` plus `uv run ruff check` + `uv run ruff format --check` + `uv run mypy encino_orm`
- **Phase gate:** full suite green, coverage ≥ 82, `ruff`/`mypy` clean, and all five success criteria demonstrated with an induced failure before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tools/ci/check_skips.py` — the JUnit-XML skip gate (CI-02)
- [ ] `tests/test_ci_harness.py` — unit tests for `required_engines()`, `engine_unavailable()`, and `check_skips.total_skipped()` (CI-01, CI-02, CI-06)
- [ ] `tests/test_pool_characterization.py` — the four pool invariants against the unmodified implementation (CI-09)
- [ ] `encino_orm/py.typed` — empty PEP 561 marker (CI-04)
- [ ] `.git-blame-ignore-revs` — does not exist (verified)
- [ ] Dev dependencies: `uv add --dev mypy pytest-cov coverage pip-audit`
- [ ] `[tool.ruff]`, `[tool.mypy]`, `[tool.coverage]` sections — none exist today (verified)
- [ ] Test fixtures: sample JUnit XML documents (clean, with skips, with failures) for the gate's unit tests
- [ ] Framework install: none — pytest 9.1.1 is already installed and configured

*(No existing test infrastructure covers any Phase-1 requirement; this phase builds it.)*

## Security Domain

> `security_enforcement` is absent from config, so this section is included (absent = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface changes. `encino_orm/security/` is untouched; CFG-02 (Phase 6) owns it. |
| V3 Session Management | no | Unchanged. |
| V4 Access Control | no | Unchanged. |
| V5 Input Validation | no (indirect) | No validation code is added. Phase 1 *enables* `S608` linting which will inform DIAL-02's validation work. |
| V6 Cryptography | no | Unchanged. `S324` (`sha1` in `model/cached.py:20`, `model/filter.py:167`) will be *reported* by ruff and must be triaged as cache-key usage, not security. |
| **V14 Configuration** | **yes** | Dependency vulnerability scanning (`uv audit` + `pip-audit`), lockfile integrity (`uv lock --check`), and immutable CI gate configuration. This is the primary ASVS surface of the phase. |
| **V10 Malicious Code / Supply Chain** | **yes** | Workflow action pinning (`actions/checkout@v5`, `astral-sh/setup-uv@v5` are mutable tags today); `uv audit`'s OSV advisory feed; the release workflow gaining a hard dependency on CI so a compromised or broken state cannot publish. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Vulnerable transitive dependency reaches a release | Tampering / Info Disclosure | `uv lock --check` (blocking) + `uv audit` (OSV) + `pip-audit` cross-check. Two independent advisory sources. |
| CI gate silently degraded to a no-op (the phase's core anti-pattern) | Repudiation / Elevation | Induced-failure verification for every gate; `continue-on-error` forbidden on gate jobs; `--strict-markers`; JUnit `skipped > 0` gate. |
| Release published from an ungated commit | Tampering | `release.yml` `publish` gains `needs: [ci]` via a `workflow_call` reusable workflow (CI-08). |
| Mutable action tags (`@v5`) resolve to a different commit later | Tampering / Supply Chain | Pin actions to full commit SHAs. **Deferred:** STACK.md recommends `zizmor` for this; it is not in Phase 1 scope, but the reusable-workflow change is the right moment to note it. |
| `# nosec` / `# type: ignore` accumulation defeats the new gates | Repudiation | `--warn-unused-ignores` (mypy) + `RUF100` (ruff, included via `RUF`) + a zero baseline of both today. |
| Secrets leaked into CI logs | Info Disclosure | No new secrets. `ENCINO_ORM_REQUIRE_ENGINES` is not sensitive. `PYPI_API_TOKEN` handling is unchanged in Phase 1. |
| Unpinned `uv` in CI pulls a future version with different behavior | Tampering | Pin `version:` on `astral-sh/setup-uv` (assumption A1 — verify the input name). |

## Sources

### Primary (HIGH confidence — verified in this session)

- **Local empirical measurement (2026-09-17, CPython 3.10.18, Windows):**
  - `ruff 0.16.8`: `ruff check --statistics` at four ruleset/line-length combinations; `ruff format --check` (61 of 101 files would be reformatted)
  - `mypy 2.3.1` via `uv run --with`: 81 / 85 / 124 / 458 errors at four strictness levels; error codes and per-file distribution
  - `pytest 9.1.1` + `pytest-asyncio 1.4.0`: 510 tests collected, 510 passed / 0 skipped locally; `-W error` clean; `--strict-markers` behavior with `-m`; JUnit XML schema and `skipped` attribute; deselected tests absent from XML
  - `coverage 7.16.1` via `uv run --with`: **88%** with all engines, **83%** CI-equivalent (branch coverage); per-module table
  - `uv 0.8.22`: `uv audit` absent; `uv lock --check` exit 0; `uv export --format requirements-txt --no-emit-project --no-hashes` exit 0 / 155 lines
  - `uv build --wheel` with a temporary `encino_orm/py.typed` → marker present in the archive (test reverted, working tree clean)
  - Pool probe script: deterministic overshoot (max_size=2 → size=5), `close()` with a held connection, double-close, `last_id` scoping, sequential cap + `PoolExhaustedError`
  - Docker: all six engine containers running
  - `git`: 2.51.0; `.git-blame-ignore-revs` absent; three pre-existing uncommitted changes (`.gitignore`, `pyproject.toml`, `uv.lock`)

- **PyPI JSON API** (`https://pypi.org/pypi/<pkg>/json`, checked 2026-09-17): `uv 0.12.15` (2026-09-15), `mypy 2.3.1` (2026-08-15), `pytest-cov 7.1.0` (2026-03-21), `coverage 7.16.1` (2026-09-13), `pip-audit 2.10.1` (2026-06-10), `ruff 0.16.8` (2026-09-16), `pytest 9.1.1` (2026-06-19), `pytest-asyncio 1.4.0` (2026-05-26)

- **uv CLI Reference** (`https://docs.astral.sh/uv/reference/cli/`): `uv audit` — "Audit the project's dependencies. Dependencies are audited for known vulnerabilities, as well as 'adverse' statuses such as deprecation and quarantine." Options verified: `--frozen`, `--ignore`, `--ignore-until-fixed`, `--no-extra`, `--no-group`, `--no-dev`, `--only-dev`, `--only-group`, `--python-platform`. Also `--locked` ("Assert that the uv.lock will remain unchanged").

- **GitHub Docs — Reusing workflows** (`https://docs.github.com/en/actions/sharing-automations/reusing-workflows`): `on: workflow_call` requirement; `./.github/workflows/{filename}` resolves to the caller's commit; reusable workflows are invoked at *job* level via `uses:`; up to 10 levels of nesting; `secrets: inherit`; `permissions` can only be maintained or reduced through the chain; `cache-mode` propagation.

### Secondary (MEDIUM confidence)

- `.planning/research/STACK.md` — version-verified config sketches for ruff/mypy/pytest-cov/uv. **Correction applied:** its `[tool.mypy]` block is *not* non-strict and yields 458 errors on this codebase (measured). Its `[tool.ruff]` line-length of 100 is confirmed better than 88 (128 vs 195 source errors).
- `.planning/research/PITFALLS.md` — Pitfalls 1, 2, 12, 15, 18, 24 all confirmed against the code. **Correction applied:** Pitfall 2 states `coverage.py`'s `fail_under` is "config-only (not a CLI/report parameter)" — `coverage report --fail-under=MIN` **does** exist (verified via `coverage report --help`).
- `.planning/codebase/TESTING.md`, `.planning/codebase/CONCERNS.md` — test structure and tooling debt, all cross-checked against the live repo.

### Tertiary (LOW confidence — flagged for validation)

- `astral-sh/setup-uv@v5`'s `version:` input name (assumption A1) — not verified in this session.
- `uv audit`'s exit-code semantics on findings (assumption A2) — cannot be tested until uv is upgraded.
- Cross-machine `coverage combine` behavior without `[tool.coverage.paths]` (assumption A3) — not exercised.

## Metadata

**Confidence breakdown:**
- **Standard stack: HIGH** — every version verified on PyPI; ruff/mypy/coverage/pytest exercised locally at those versions.
- **Architecture: HIGH** — the gate topology, the JUnit/`-m` reconciliation, and the reusable-workflow pattern are each verified empirically or against official docs.
- **Pitfalls: HIGH** — all six phase-relevant pitfalls were re-confirmed against the live code, and two of them (`PT011` vs D-09, STACK.md's mypy strictness) were found to be new tensions that the roadmap does not name.
- **Baselines: HIGH** — every number (61 files, 128/102/52 ruff errors, 81/124/458 mypy errors, 88%/83% coverage, 41/13 integration/optional counts) is a direct measurement, reproducible with the commands given.

**Research date:** 2026-09-17
**Valid until:** 2026-10-17 (30 days). Re-measure the coverage baseline and the ruff/mypy error counts if more than two weeks elapse, or immediately after any commit that changes `encino_orm/`.
