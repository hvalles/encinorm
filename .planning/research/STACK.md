# Stack Research

**Domain:** Tooling stack for production-hardening an async multi-engine Python ORM library (`encino_orm` 0.2.6 → 0.3.0)
**Researched:** 2026-09-17
**Confidence:** HIGH on versions (all verified against PyPI JSON API / GitHub Releases API / installed tooling on 2026-09-17); HIGH on the async-benchmarking limitation (verified by reading plugin source); MEDIUM on concurrency-testing technique (no single standard tool exists); MEDIUM on multi-engine CI topology (design recommendation, not a documented consensus)

## Scope & Framing

This milestone is **not** about adding runtime dependencies to `encino_orm`. It is about the
**quality gate, CI, and release toolchain** that surrounds it. The single most important
constraint shaping every recommendation below:

> The library targets **Python 3.10** (`requires-python = ">=3.10"`, local venv is CPython
> **3.10.18**). Therefore **no 3.11+ APIs may be used in library code or tests** — no
> `asyncio.Barrier`, no `asyncio.timeout`, no `asyncio.TaskGroup`, no `except*`. This
> directly rules out the most commonly recommended concurrency-testing primitives.

A second, equally important framing note:

> **The stated performance goals are CPU/sync-bound, not I/O-bound.** `copy_table` batching,
> placeholder-translation precompilation, and the pool idle-reaper policy are all
> deterministic, synchronous code paths. This matters because **neither major Python
> benchmark plugin can measure coroutines** (verified — see §5). The "we cannot benchmark
> async" problem is largely self-inflicted: the things that need measuring are sync units.

### Current state (verified against the repo)

| Item | State |
|---|---|
| `ruff` | Pinned in dev deps (`ruff>=0.16.8`), installed `0.16.8`. **No `[tool.ruff]` config exists.** |
| `mypy` / `pyright` / `ty` | **Not present anywhere.** No `[tool.mypy]`, no `[tool.pyright]`. |
| `py.typed` | **MISSING.** No `encino_orm/py.typed` marker. PEP 561 blocker for a typed library. |
| `pytest-cov` / `coverage` | **Not present.** No `[tool.coverage]` config. |
| `uv` | **0.8.22 (Sept 2025) — 4 minor versions behind.** `uv audit` / `uv check` do not exist in it. |
| CI | 4-leg Python matrix (3.10–3.13), GHA services for MySQL + PostgreSQL only. No lint/type/cov gates. |
| Python 3.14 | Local system interpreter is 3.14.7; **CI does not test 3.14.** |
| Release | No publish workflow; `docker-compose.yml` contains hardcoded dev credentials. |

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|---|---|---|---|---|
| **uv** | `0.12.15` | Package/lock management, and now **auditing + type-check driver + formatter** | Already the project's manager. 0.12.x adds `uv audit` (OSV-backed, reads `uv.lock` directly), `uv check` (runs `ty`), `uv format`, and `uv lock --check`. These collapse three separate tools into one binary the project already depends on. **Local 0.8.22 must be upgraded first.** | HIGH |
| **ruff** | `0.16.8` | Lint + format | Replaces flake8 + black + isort + pyupgrade + **bandit** in one Rust binary. Already pinned. Critically, its `ASYNC` (flake8-async) and `RUF006` (dangling-task) rules target exactly the async-pool bug class this milestone must fix. | HIGH |
| **mypy** | `2.3.1` | Static type-check gate | The **only** checker with an official pydantic v2 plugin (`plugins = ["pydantic.mypy"]`), which is essential for a library whose public API *is* pydantic models. mypy 2.x adds `--num-workers N` parallel checking (up to 5× on large codebases) — material on 141 files. | HIGH |
| **pytest-cov** | `7.1.0` | Coverage gating | De-facto standard. 7.1.0 fixed `--cov-fail-under` inconsistency when reporting options vary — which matters here because the multi-engine jobs will use different report settings. Requires `coverage>=7.10.6`. | HIGH |
| **coverage** | `7.16.1` | Coverage engine | Pulled by pytest-cov. Needs `parallel = true` + `coverage combine` for the per-engine job topology. | HIGH |
| **pytest-asyncio** | `1.4.0` | Async test execution | Already in use (`asyncio_mode = "auto"`). 1.4.0 adds the `pytest_asyncio_loop_factories` hook (run one test under multiple loop implementations) and 1.2.0 added `--asyncio-debug` — both directly useful for concurrency hardening. **Config is currently incomplete and will emit a warning.** | HIGH |
| **pytest-codspeed** | `5.0.3` | CI performance-regression gate | The only benchmark plugin with a real CI regression *service* behind it. Backward-compatible with the `pytest-benchmark` API, so migration is free. Supports `simulation` (CPU-instruction) mode, which is far less flaky than wall-clock in CI. | MEDIUM |
| **testcontainers** | `4.15.0` | Local + CI engine provisioning for MSSQL / Oracle / Redis / MariaDB | Gives *identical* engine provisioning on Windows dev and Linux CI, driven from Python instead of duplicated YAML. `testcontainers[oracle-free]` uses **`oracledb`** — the same driver the project already ships. | MEDIUM-HIGH |
| **pip-audit** | `2.10.1` | Secondary dependency vulnerability scan | Defense-in-depth with a different advisory source than OSV. **Cannot read `uv.lock`** — must go through `uv export`. Keep secondary to `uv audit`. | MEDIUM-HIGH |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---|---|---|---|---|
| **pytest-benchmark** | `5.3.0` | Local micro-benchmarking with `--benchmark-compare` / `--benchmark-histogram` | Dev-only, local. Use it to iterate on the placeholder-cache and `copy_table` changes. Do **not** use it as a CI gate (see §5). Coexists with pytest-codspeed; codspeed blocks it when enabled. | HIGH |
| **pytest-timeout** | `2.4.0` | Convert pool deadlocks into failures | Required for the concurrency suite. **Must use the `signal` timeout method** (default on POSIX); the `thread` method cannot interrupt a blocked event loop. Unavailable on Windows dev → CI-only guard. | HIGH |
| **pytest-repeat** | `0.9.4` | `--count=N` flake reproduction | Nightly/`workflow_dispatch` job running the pool race tests 50–200×. Not on every PR (too slow). | MEDIUM |
| **pytest-randomly** | `5.0.0` | Random test ordering | Surfaces inter-test state leakage — directly relevant given the global-mutable JWT/secret state called out in `PROJECT.md`. Must be disabled for benchmark runs (`-p no:randomly`). | MEDIUM |
| **pytest-xdist** | `3.8.0` | Wall-clock speedup across 507 tests × 6 engines | Unit/integration jobs only. **Must exclude the concurrency tests** — separate processes cannot exercise in-process pool races. pytest-benchmark auto-disables itself under xdist. | MEDIUM |
| **syrupy** | `6.1.1` | Snapshot testing of generated SQL per dialect | **Highest-leverage idea in this document.** Snapshot the SQL string produced by each of the 6 dialects and assert it against a committed `.ambr` file. This catches dialect drift (the `COUNT(*)` / `AS n` alias bug class) **without a live database** — i.e. on the fast, always-on SQLite-only job. | MEDIUM |
| **hypothesis** | `6.168.0` | Property-based + stateful testing | Two high-value targets: (1) fuzz `_IDENTIFIER_RE` / `_check_identifier` with adversarial table/column names to prove the injection defence; (2) `RuleBasedStateMachine` for `PoolDb.acquire`/`release` invariants. Optional for this milestone. | MEDIUM |
| **zizmor** | `1.30.1` | Static security audit of the workflow YAML itself | Add as a lint job. Detects unpinned actions, template injection, credential persistence — exactly the risks introduced when adding an OIDC publish workflow. | MEDIUM-HIGH |
| **psutil** | `7.2.2` | RSS assertions in pool-leak tests | Only if you want a hard assertion that the reaper actually releases memory. Otherwise use connection-count assertions. | LOW |
| **pre-commit** (`4.6.2`) or **prek** (`0.5.3`) | latest | Local hook parity with CI | Optional. `uv` documents a pre-commit integration. `prek` is a faster Rust reimplementation if the hooks feel slow. | MEDIUM |

### Development Tools

| Tool | Purpose | Notes |
|---|---|---|
| `ruff check --statistics` | Produce a **baseline** of existing violations before turning gates on | Run this first. Do not turn on `ANN`/`D`/`PL` wholesale across 141 files in one PR. |
| `mypy --num-workers 4` | Parallel type checking (mypy 2.x) | Implicitly enables the new native parser. Use `--python-version 3.10` explicitly. |
| `uvx ty check` / `uv check` | Sub-second local type feedback | **Not a gate.** `ty` is `0.0.82` — pre-1.0, explicitly experimental. Use it for editor-speed iteration only. |
| `uv lock --check` | Lockfile drift gate | Verified present even in uv 0.8.22. Equivalent to `--locked`. |
| `uv export --format requirements-txt --no-emit-project --no-hashes` | Bridge `uv.lock` → `pip-audit` | The only way to get pip-audit to audit the locked set. |
| `uv build --no-sources` | Produce `dist/` | Officially recommended by uv before publishing, so the sdist/wheel build does not depend on `tool.uv.sources`. |

## Installation

```bash
# 0. Prerequisite: upgrade uv (0.8.22 → 0.12.15) to get `uv audit` / `uv check` / `uv format`
uv self update

# 1. Core gates — add to the existing [dependency-groups] dev
uv add --dev mypy pytest-cov coverage

# 2. Concurrency hardening
uv add --dev pytest-timeout pytest-repeat

# 3. Benchmarking (CI gate + local micro-benchmarks)
uv add --dev pytest-codspeed pytest-benchmark

# 4. Security scanning (CI-only tools, keep out of the dev group if preferred)
uv add --dev pip-audit zizmor

# 5. Multi-engine provisioning
uv add --dev "testcontainers[mssql,oracle-free,redis,mysql]"

# 6. Optional / deferred
uv add --dev syrupy            # dialect SQL snapshots — recommend adopting
uv add --dev hypothesis        # identifier fuzzing + pool state machine
uv add --dev pytest-randomly   # test-order randomisation
```

Do **not** add these to `[project.optional-dependencies]`. All of the above are
dev/CI-only and must never appear in the library's runtime dependency graph (the
import-lazy contract in `PROJECT.md` depends on this).

---

## Hardening Goal → Tool Mapping

This is the section the roadmap should read first.

| `PROJECT.md` goal | Tool / mechanism | Gate type |
|---|---|---|
| `ruff` (lint + format) configured | `ruff check --output-format=github` + `ruff format --check` | **Blocking** CI job |
| `mypy` configured | `mypy encino_orm` with pydantic plugin + `py.typed` | **Blocking** CI job (ratcheted) |
| `pytest-cov` with report + threshold | `pytest --cov --cov-fail-under=NN --cov-branch` | **Blocking**, threshold ratcheted |
| CI gates for lint / types / coverage | 3 dedicated jobs + `ci-success` aggregator with `needs:` | Branch protection on the aggregator |
| Multi-engine CI matrix (MariaDB, MSSQL, Oracle, Redis) | GHA `services:` (MariaDB, Redis) + separate non-matrix job (MSSQL, Oracle); testcontainers locally | **Blocking** for MariaDB/Redis; MSSQL/Oracle can start as `continue-on-error: true` |
| Pool races (`acquire()`, `last_id`, commit/rollback) | Hand-rolled 3.10-compatible barrier + `asyncio.gather` invariant loops + `pytest-timeout` | **Blocking** on the SQLite/in-process job |
| `last_id()` correctness per connection | Deterministic interleaving test + `asyncio.gather` cross-talk assertion | **Blocking** |
| Security: identifier validation in all 6 dialects | ruff `S608` + `hypothesis` identifier fuzzing + per-dialect unit tests | **Blocking** |
| `copy_table` batching | `pytest-codspeed` benchmark on the sync batch-build path | **Blocking** (regression vs. baseline) |
| Placeholder precompilation/caching | `pytest-codspeed` benchmark on the translation function | **Blocking** |
| Pool idle reaper | `pytest-codspeed` benchmark + connection-count assertion | Blocking assertion; benchmark advisory |
| Benchmarks with **measurable numeric targets** in CI | CodSpeed `mode: simulation` + committed baseline | **Blocking** on regression |
| Dependency/security scanning | `uv lock --check` + `uv audit` (+ `pip-audit` cross-check) + Dependabot + `zizmor` | **Blocking** for lock check; `uv audit` blocking; Dependabot continuous |
| Trusted publishing / OIDC for PyPI | `pypa/gh-action-pypi-publish@release/v1` with `id-token: write` | Release workflow only |
| Dev credentials marked dev-only | `docker-compose.yml` header + a CI `zizmor`/grep check for secrets | Advisory |
| `CHANGELOG.md` documents 0.3.0 breakage | Hand-written; `uv version --bump minor` for the number only | Manual review |

---

## Configuration Sketches

These are prescriptive starting points, not final configs. Each is annotated with *why*.

### `pyproject.toml` — ruff

```toml
[tool.ruff]
target-version = "py310"          # must match requires-python; drives UP-rule rewrites
line-length = 100                 # 88 forces ugly wraps on the long dialect SQL strings

[tool.ruff.lint]
select = [
    "E", "W", "F",                # pycodestyle + pyflakes
    "I",                          # isort
    "UP",                         # pyupgrade
    "B", "C4", "SIM", "PIE", "RET", "RSE", "PERF", "FURB",
    "ASYNC",                      # flake8-async  <-- core: catches blocking calls in async fns
    "RUF",                        # Ruff-specific <-- RUF006 = dangling asyncio task
    "S",                          # flake8-bandit <-- S608 = hardcoded SQL expression
    "PT",                         # flake8-pytest-style (507 test fns)
    "BLE", "TRY", "LOG", "G", "TID", "N", "ARG", "PTH", "SLF", "TC",
]
# Deliberately NOT enabled in this milestone: "ANN", "D", "PL".
# Rationale: 141 files, ~507 tests. Enabling them wholesale produces an unreviewable diff
# and buries the real findings. Ratchet them in as separate phases.

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "ARG001", "ARG002"]   # asserts are the point; fixtures take unused args
"docs/**"  = ["E501"]

[tool.ruff.lint.isort]
known-first-party = ["encino_orm"]
```

**Why `S` instead of `bandit`:** ruff's `S` rules are a reimplementation of flake8-bandit
running in the same pass as everything else. Verified locally: `ruff rule S608` returns
`hardcoded-sql-expression`, whose docstring explicitly targets SQL string building. Adding
standalone `bandit` would be a second tool, a second config, and a second CI job for a
subset of the same coverage.

**Why `ASYNC` and `RUF` are non-negotiable here:** this is a concurrency library whose
stated defects are pool races and per-task state cross-talk. `RUF006`
(`asyncio-dangling-task`, verified via `ruff rule RUF006`) flags `asyncio.create_task()`
whose result is not retained — the exact pattern that causes tasks to be garbage-collected
mid-flight. `ASYNC` flags blocking calls and missing checkpoints in async functions.

### `pyproject.toml` — mypy

```toml
[tool.mypy]
python_version = "3.10"
plugins = ["pydantic.mypy"]       # official pydantic v2 plugin — the reason mypy wins here
files = ["encino_orm"]
# Ratchet phase 1 (achievable now):
check_untyped_defs = true
disallow_incomplete_defs = true
disallow_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_return_any = true
warn_unreachable = true
strict_equality = true
# NOT yet: strict = true  — defer to a later phase once the core is clean

[[tool.mypy.overrides]]
# Optional lazy layers are imported behind try/except and must not be required at type-check time.
module = ["fastapi.*", "strawberry.*", "jwt.*", "redis.*", "aioodbc.*", "oracledb.*"]
ignore_missing_imports = true
```

**mypy 2.0 breaking changes you will hit on the first run** (verified from the official mypy
blog): `--local-partial-types` is now on by default, `--strict-bytes` is now on by default
(`bytearray`/`memoryview` no longer assignable to `bytes`), `--allow-redefinition` now
follows the *new* semantics, and `--python-version 3.9` support was dropped. Since the
project is 3.10+, the last one is free. Expect a substantial first-run error count; that
is normal and is why the ratchet matters.

### `pyproject.toml` — coverage

```toml
[tool.coverage.run]
source_pkgs = ["encino_orm"]
branch = true
parallel = true                              # REQUIRED: per-engine jobs combine later
# pytest-cov 7.0 dropped subprocess measurement. If subprocess coverage is ever needed:
# patch = ["subprocess"]

[tool.coverage.report]
precision = 1
show_missing = true
exclude_also = [
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
]
```

**Do not chase a single global `--cov-fail-under` number.** With 6 engines and
engine-conditional skips, one global number is simultaneously too strict for the SQLite-only
job and too lax for the PostgreSQL job. The `COUNT(*)` bug is the proof: the suite looked
covered, but the dialect path was not. Instead:

1. **Per-engine jobs** write `COVERAGE_FILE=.coverage.${{ matrix.engine }}`.
2. A `coverage` job downloads all artifacts, runs `coverage combine`, then
   `coverage report` + `coverage xml`.
3. The **global floor** is a low ratchet (start ~65–70%) that only guards against regression.
4. The **meaningful metric** is per-module: gate `encino_orm/db/*.py` (the 6 adapters)
   at a high floor, since those are the files where dialect bugs hide.

### `pyproject.toml` — pytest

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"   # silences the pytest-asyncio 1.4 warning
asyncio_default_test_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
timeout = 120                                     # requires pytest-timeout; CI-only safety net
markers = [
    "concurrency: pool/race tests — excluded from xdist runs",
    "benchmark: measured by pytest-codspeed; excluded from normal runs",
    "engine(name): requires a specific live engine",
]
addopts = "-ra --strict-markers"
```

**Why `asyncio_default_*_loop_scope` is required:** pytest-asyncio 1.4.0 changed the
warning text for an *unset* `asyncio_default_fixture_loop_scope` — i.e. it still warns.
Verified from the 1.4.0 changelog. Setting both explicitly is the documented fix.

**Why `--strict-markers`:** without it, `@pytest.mark.engine("oracle")` silently becomes a
no-op if the marker is not registered, and the engine tests quietly stop running. That is
precisely the failure mode that let the multi-engine gap persist.

---

## What NOT to Use

| Avoid | Why | Use Instead | Confidence |
|---|---|---|---|
| **`bandit`** (standalone) | Duplicates ruff's `S` rules in a second tool/config/job. No coverage ruff lacks. | ruff `select = ["S"]` | HIGH |
| **`black` + `isort` + `flake8`** | Superseded by ruff for ~2 years. Three tools, three configs, 10–100× slower. | `ruff format` + `ruff check` | HIGH |
| **`pyright` as the *primary* CI gate** | Excellent checker, but has **no pydantic plugin** — it cannot validate model field/validator interactions the way `pydantic.mypy` can. Running it as a second *blocking* gate doubles error triage on 141 files. | mypy 2.3.1 as the gate; pyright/basedpyright in the editor or as an advisory job | MEDIUM-HIGH |
| **`ty` (`0.0.82`) as a CI gate** | Pre-1.0, versioned `0.0.x`, self-described as experimental. It will produce false positives you cannot suppress portably. | `uv check` / `uvx ty check` for fast local iteration only | HIGH |
| **`asv` (airspeed velocity)** | Heavyweight commit-tracked benchmark database; no first-class async support; would duplicate CodSpeed. Only justified if you need offline long-horizon historical charts. | pytest-codspeed for CI, pytest-benchmark for local | MEDIUM |
| **`pytest-benchmark` OR `pytest-codspeed` for async end-to-end DB timing** | **Verified limitation.** pytest-benchmark 5.3.0 has *zero* async handling — the strings `async`/`asyncio`/`coroutine`/`await` appear **nowhere** in its README or full changelog. pytest-codspeed's `BenchmarkFixture.__call__` is literally `return target(*args, **kwargs)` — passing a coroutine function returns an un-awaited coroutine and "benchmarks" only coroutine-object creation. | Benchmark the **sync** units (SQL build, placeholder translation, batch sizing). For end-to-end latency, write an explicit `time.perf_counter` harness inside an async test with a loose budget assertion. | HIGH |
| **`anyio` + its pytest plugin** | A second async test runner layered on top of pytest-asyncio's `asyncio_mode = "auto"`. The library is asyncio-only (`contextvars` + `asyncio` primitives) and does not target trio. Adding it buys nothing and risks fixture/loop-scope conflicts. | pytest-asyncio 1.4 alone | MEDIUM-HIGH |
| **`safety`** | Requires an account for the useful tier; weaker advisory coverage than OSV; replaced by `uv audit`. | `uv audit` (OSV) + `pip-audit` cross-check | MEDIUM |
| **`python-semantic-release` (10.6.2) in *this* milestone** | Generates `CHANGELOG.md` from commit messages. This milestone's explicit requirement is to *explain breaking changes* — a generated commit-log digest is the wrong artifact and adds Conventional-Commits ceremony on top of a brownfield history that does not follow it. | `uv version --bump minor` for the number + a hand-written `CHANGELOG.md` | MEDIUM-HIGH |
| **`pytest-xdist` for concurrency tests** | Each worker is a separate process. In-process pool races (`acquire()` overshoot, `_last_id` cross-talk) **cannot be observed across processes** — xdist will make the race tests pass by accident. | Run concurrency tests in a single-process job; use xdist only for the unit/integration jobs | HIGH |
| **`asyncio.Barrier` / `asyncio.timeout` / `TaskGroup` in tests** | 3.11+ APIs. `requires-python = ">=3.10"` and the local venv is **3.10.18**. | Hand-rolled `asyncio.Event`-based barrier (~15 lines) | HIGH |
| **GHA service containers for MSSQL/Oracle in the 4-leg matrix** | Oracle Free cold-start is 60–120 s and MSSQL ~1 GB RAM. Multiplying that by 4 Python versions costs 5–10 CI-minutes per run for zero extra coverage (the dialect behaviour does not vary by Python version). | A **separate, single-Python-version** engine job | MEDIUM |
| **Pinning actions to branch pointers** (`@v5`, `@master`) | `pypa/gh-action-pypi-publish@master` is **sunset** (verified in its README). Mutable tags are a supply-chain risk. | Pin to full commit SHAs, or `@release/v1` for the pypi-publish action specifically, and let Dependabot (`github-actions` ecosystem) bump them | HIGH |

---

## Stack Patterns by Variant

**If the multi-engine matrix must stay cheap (recommended):**
- Keep MySQL + PostgreSQL + MariaDB + Redis as GHA `services:` (no per-Python-version matrix for the DBs; run them on one leg).
- Add a separate `engine-matrix` job on Python 3.12 only, `timeout-minutes: 30`, with MSSQL and Oracle as `services:` and generous `--health-retries`.
- Because: dialect behaviour is a function of the *server*, not the Python version. The 4-leg matrix exists to catch interpreter-level issues; engine coverage does not need to be duplicated into it.

**If Docker-in-CI reliability is a concern:**
- Use `testcontainers-python` inside the job instead of `services:`. You get explicit, code-level readiness control (`container.wait_for_logs(...)`) rather than `--health-cmd` string guessing.
- Because: `services:` health checks are strings in YAML; testcontainers readiness is testable Python. But it needs the Docker socket on the runner, which `ubuntu-latest` provides.

**If you want dialect regression coverage without live engines:**
- Use **syrupy** SQL snapshots on the always-on SQLite-only job. Snapshot the SQL string each adapter generates for `count`, `paginate`, `list_tables`, `insert`, etc.
- Because: the `COUNT(*)` / `AS n` alias bug is a *string-generation* bug. A committed `.ambr` snapshot per dialect catches it in seconds with no containers at all. This is the cheapest possible insurance against the exact defect that motivated this milestone.

**If the local Windows dev loop is the priority:**
- Use the existing `docker-compose.yml` for MariaDB/MSSQL/Oracle/Redis, and have the test suite resolve DSNs from env vars and **skip** (not fail) any engine whose DSN is unset.
- Because: `asyncio.WindowsSelectorEventLoopPolicy()` in `tests/conftest.py` already makes local runs a different environment from CI. Tests that hard-fail on a missing engine will make Windows development unbearable and push people toward `-k "not integration"`, which is how coverage silently rots.

---

## Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| `pytest@9.1.1` | `pytest-asyncio@1.4.0` | pytest-asyncio 1.4.0 raised its floor to **pytest >= 8.4.0**. Satisfied. |
| `pytest@9.1.1` | `pytest-cov@7.1.0` | pytest-cov 7.x requires **coverage >= 7.10.6**. Pairs with `coverage@7.16.1`. |
| `pytest@9.1.1` | `pytest-benchmark@5.3.0` | 5.3.0 CI tests against pytest 9.1.1 and Python 3.10–3.14. |
| `pytest@9.1.1` | `pytest-codspeed@5.0.3` | Supported range is Python 3.9–3.15. |
| `pytest-codspeed@5.0.3` | `pytest-benchmark@5.3.0` | Coexist, but codspeed **blocks** pytest-benchmark when `--codspeed` is active. Only one measures per run. |
| `mypy@2.3.1` | `pydantic@2.13.4` | Via `plugins = ["pydantic.mypy"]`. Keep mypy pinned — 2.x changed defaults mid-series. |
| `mypy@2.3.1` | `python_version = "3.10"` | mypy 2.0 dropped `--python-version 3.9`. 3.10 is the floor, matching `requires-python`. |
| `ruff@0.16.8` | `target-version = "py310"` | Must match `requires-python` or `UP` rules will suggest 3.11+ syntax the library cannot use. |
| `uv@0.12.15` | `uv.lock` | `uv audit` / `uv check` / `uv format` **do not exist in 0.8.22** (verified locally). Upgrade is a hard prerequisite for the audit gate. |
| `testcontainers[mssql]@4.15.0` | `aioodbc` / `pyodbc` | **Driver mismatch.** The extra pulls `pymssql` + `sqlalchemy` and `get_connection_url()` returns a `mssql+pymssql` SQLAlchemy URL. Read `get_container_host_ip()` / `get_exposed_port(1433)` / the SA password instead — do not use the connection URL. |
| `testcontainers[oracle-free]@4.15.0` | `oracledb>=2.0` | The extra requires `oracledb>=3`; the project pins `>=2.0`. Resolution takes the newer version — verify no driver API break in the Oracle adapter. |
| `mcr.microsoft.com/mssql/server` | GHA `ubuntu-latest` | amd64-only image. Fine on GHA and on x64 Windows dev; requires emulation on Apple Silicon. |
| `gvenzl/oracle-free:23-slim` | GHA `ubuntu-latest` | The image ships its own `HEALTHCHECK`, so GHA can use it without a custom `--health-cmd`. Expect 60–120 s cold start. |
| `pyright@1.1.414` / `basedpyright@1.40.1` | `pydantic@2.13.4` | Works, but without a pydantic plugin. Use advisory, not as a gate. |

---

## Sources

### Version authority (all checked 2026-09-17)
- **PyPI JSON API** (`https://pypi.org/pypi/<pkg>/json`) — authoritative current versions + upload dates for: `ruff 0.16.8`, `mypy 2.3.1`, `pyright 1.1.414`, `basedpyright 1.40.1`, `pytest 9.1.1`, `pytest-asyncio 1.4.0`, `pytest-cov 7.1.0`, `coverage 7.16.1`, `pytest-benchmark 5.3.0`, `pytest-codspeed 5.0.3`, `testcontainers 4.15.0`, `pip-audit 2.10.1`, `uv 0.12.15`, `hatchling 1.32.3`, `anyio 4.15.1`, `hypothesis 6.168.0`, `pytest-xdist 3.8.0`, `pytest-timeout 2.4.0`, `zizmor 1.30.1`, `python-semantic-release 10.6.2`, `pytest-randomly 5.0.0`, `pytest-repeat 0.9.4`, `oracledb 26.0.0`, `pyodbc 5.3.0`, `syrupy 6.1.1`, `pre-commit 4.6.2`, `ty 0.0.82`. **Confidence: HIGH**
- **GitHub Releases API** — `astral-sh/setup-uv v10.1.0`, `pypa/gh-action-pypi-publish v1.14.2`, `actions/checkout v7.0.1`, `actions/setup-python v7.0.0`, `codecov/codecov-action v7.1.1`, `CodSpeedHQ/action v5.2.1`, `actions/dependency-review-action v5.0.0`, `github/codeql-action v2.27.0`, `astral-sh/ruff-action v4.1.0`, `google/osv-scanner-action v2.6.0`, `j178/prek v0.5.3`. **Confidence: HIGH**

### Official documentation
- **uv CLI Reference** (`https://docs.astral.sh/uv/reference/cli/`) — verified `uv lock --check` ("Asserts that the `uv.lock` would remain unchanged… Equivalent to `--locked`"), `uv audit` ("Dependencies are audited for known vulnerabilities, as well as 'adverse' statuses such as deprecation and quarantine"; OSV service via `api.osv.dev`; `--ignore`, `--ignore-until-fixed`), `uv check` ("Currently, this type checks Python code using **ty**"; `--fix`), `uv format`. **Confidence: HIGH**
- **uv — Building and publishing a package** (`https://docs.astral.sh/uv/guides/package/`, page dated 2026-09-02) — `uv build --no-sources` recommendation; `uv publish` trusted-publishing support with post-publish token revocation; **"`uv publish` does not currently generate attestations; attestations must be created separately"**. **Confidence: HIGH**
- **uv — Using uv with Dependabot** (`https://docs.astral.sh/uv/guides/integration/dependabot/`, dated 2026-03-20) — `package-ecosystem: "uv"` is supported and updates `uv.lock`; pair `exclude-newer` with Dependabot `cooldown.default-days`. **Confidence: HIGH**
- **uv — Dependabot** and the tracked caveat `astral-sh/uv#2512` for known gaps. **Confidence: MEDIUM**
- **GitHub Actions — About service containers** (`https://docs.github.com/en/actions/using-containerized-services/about-service-containers`) — service containers require a **Linux** runner; `localhost:<port>` access when running directly on the runner; `ports`, `env`, `options`, and the newer `command`/`entrypoint` keys. **Confidence: HIGH**
- **pypa/gh-action-pypi-publish `release/v1` README** — `master` is **sunset**; trusted publishing requires `permissions: id-token: write` and **no** username/password; `environment: {name: pypi, url: ...}`; Docker-based ⇒ Linux-only; trusted publishing unavailable from inside a reusable workflow; **attestations (Sigstore/PEP 740) are on by default** for all Trusted Publishing projects, opt out with `attestations: false`; separate build and publish jobs with artifact handoff. **Confidence: HIGH**
- **PyPI — Publishing with a Trusted Publisher** (`https://docs.pypi.org/trusted-publishers/`) — OIDC exchange; PyPI mints a 15-minute project-scoped token. **Confidence: HIGH**
- **mypy blog — 2.0 / 2.1 / 2.2 / 2.3 release notes** (May–July 2026) — 2.0 enables `--local-partial-types` and `--strict-bytes` by default, changes `--allow-redefinition` semantics, drops `--python-version 3.9`, adds parallel checking via `--num-workers` (up to 5× at 8 workers) and the experimental native parser. **Confidence: HIGH**
- **pytest-asyncio changelog + README** (`1.0.0`–`1.4.0`) — `event_loop` fixture removed in 1.0; `event_loop_policy` fixture override deprecated in 1.4 in favour of the `pytest_asyncio_loop_factories` hook; `--asyncio-debug` added in 1.2; `asyncio_default_fixture_loop_scope` still warns when unset in 1.4; pytest floor raised to 8.4.0; Python 3.9 dropped in 1.3. **Confidence: HIGH**
- **pytest-cov changelog** — 7.0.0 dropped subprocess measurement (migrate with `patch = subprocess`), requires coverage ≥ 7.10.6; 7.1.0 fixed `--cov-fail-under` consistency across reporting options. **Confidence: HIGH**
- **pytest-timeout README** — designed to catch deadlocked/hanging tests, *not* for precise timing; may hard-terminate via `os._exit()`; `signal` vs `thread` methods. **Confidence: HIGH**
- **CodSpeed docs — Writing Benchmarks in Python / pytest-codspeed reference** — `@pytest.mark.benchmark` and the `benchmark` fixture; `--codspeed-mode auto|simulation|walltime|memory`; backward-compatible with pytest-benchmark; **"Using `actions/setup-python` to install python and not `uv install` is critical for tracing to work properly"**; xdist and sharded-benchmark support; `CodSpeedHQ/action@v5` with `mode: simulation`. **Confidence: HIGH**
- **testcontainers-python** (`testcontainers[mssql]` = `pymssql>=2` + `sqlalchemy`; `testcontainers[oracle]` and `[oracle-free]` = `oracledb>=3`; `SqlServerContainer` defaults to `mcr.microsoft.com/mssql/server:2019-latest`, `dialect='mssql+pymssql'`; `OracleFreeContainer` defaults to `gvenzl/oracle-free:slim`). **Confidence: HIGH**
- **pip-audit README + changelog** — 2.10.1; `--osv-url`, `--vulnerability-service=esms`; **no `uv.lock` support** (no `uv` mention anywhere in README or changelog). **Confidence: HIGH**
- **astral-sh/ty docs** (`https://docs.astral.sh/ty/`, dated 2026-09-17) — "10x–100x faster than mypy and Pyright", Astral-backed, `uvx ty check`. Version `0.0.82` ⇒ pre-1.0. **Confidence: HIGH**
- **ruff rules index via installed binary** (`ruff linter`, `ruff rule <CODE>` on the project's own `ruff 0.16.8`) — authoritative rule-family list and rule semantics for `ASYNC100`, `RUF006` (`asyncio-dangling-task`), `S608` (`hardcoded-sql-expression`), `PT012`. **Confidence: HIGH**
- **ruff configuration docs via Context7** (`/astral-sh/docs`, `/websites/astral_sh_ruff`) — `[tool.ruff]` / `[tool.ruff.lint]` / `[tool.ruff.format]` schema, `target-version`, `per-file-ignores`, `extend-select`. **Confidence: HIGH**
- **pytest-benchmark README + full CHANGELOG** — 5.3.0; `--benchmark-precision`/`--benchmark-confidence`; `compare --between`; auto-disables under xdist. **The strings `async`/`asyncio`/`coroutine`/`await` do not appear in the README or anywhere in the changelog.** **Confidence: HIGH**
- **pytest-codspeed source** (`src/pytest_codspeed/plugin.py`, `instruments/walltime.py`, `CHANGELOG.md` on `master`) — `BenchmarkFixture.__call__` is `return target(*args, **kwargs)`; **zero occurrences of `async`/`asyncio`/`coroutine`/`await` in the plugin, the walltime instrument, or the changelog**. **Confidence: HIGH**
- **Docker Compose / `docker-compose.yml`** — inspected: hardcoded `admin` passwords for MySQL, MariaDB, PostgreSQL, MSSQL (`Admin_123`), Oracle, Redis. Confirms the "dev-only credentials" concern in `PROJECT.md`. **Confidence: HIGH**

### Repository inspection
- `pyproject.toml` — dev group contents; absence of any `[tool.ruff]`, `[tool.mypy]`, `[tool.pyright]`, `[tool.coverage]`; pytest config has only `asyncio_mode`, `testpaths`, `pythonpath`.
- `.github/workflows/ci.yml` — 4-leg matrix (3.10–3.13), `services:` for MySQL + PostgreSQL only, `astral-sh/setup-uv@v5`, single `uv run pytest -q` step, no gates.
- `.venv/pyvenv.cfg` — CPython **3.10.18**, `uv = 0.8.22`.
- `.planning/PROJECT.md`, `.planning/codebase/STACK.md` — goals, constraints, current state.
- Absence of `encino_orm/py.typed` (glob over `encino_orm/**/{py.typed,*.pyi}` → no matches).

---

## Gaps & Open Questions

1. **`uv check` / `ty` stability is unproven.** `uv check` is a new command driving a `0.0.x`
   type checker. It is documented but its error surface on a 141-file pydantic codebase is
   unknown. *Resolve during the phase that wires type checking:* run `uvx ty check` once and
   compare its error set against mypy's. If `ty` is noisy, keep it local-only as planned.
2. **CodSpeed licensing for this project is unverified.** CodSpeed is free for open-source
   projects; the `PROJECT.md` framing is "internal use and PyPI publication" against the
   public `hvalles/encinorm` repo. *Resolve before committing to it as a blocking gate:*
   confirm the repo is public (then it is free) or budget for it. Fallback: a committed
   `pytest-benchmark --benchmark-json` baseline compared with `--benchmark-compare-fail=15%`
   in a dedicated job — weaker, but dependency-free.
3. **Whether `@pytest.mark.benchmark` on an async test measures the awaited body is
   unverified.** Reading the source, the plugin wraps `item.runtest`, and pytest-asyncio
   drives coroutines from `pytest_pyfunc_call` (inside `runtest`), so the awaited execution
   *should* fall inside the measured region — but it also includes event-loop setup/teardown.
   **MEDIUM confidence, needs empirical validation.** Do not build a gate on it until
   measured.
4. **Optimal MSSQL/Oracle CI topology is a judgement call.** No authoritative source compares
   `services:` vs `testcontainers` for heavy engines. The recommendation (separate
   single-version job) is reasoned, not cited. *Revisit after the first full CI run:* measure
   actual cold-start times and decide whether Oracle belongs on every PR or only on `main`.
5. **No off-the-shelf asyncio race detector exists.** The concurrency section prescribes
   *techniques* (deterministic barriers, gather-based invariant loops, repeat, timeout)
   rather than a library, because the ecosystem has not produced one. If the hand-rolled
   barrier proves awkward on Python 3.10, `hypothesis`'s `RuleBasedStateMachine` is the
   strongest fallback.
6. **`pytest-randomly` interaction with the existing suite is unknown.** `tests/conftest.py`
   installs a Windows event-loop policy at import time and the suite has ~507 functions with
   likely order dependencies. Adding random ordering may surface a large number of
   pre-existing failures. *Triage before enabling as a gate.*
7. **`basedpyright` vs `pyright` for the advisory job was not deeply compared.** Both are
   current (`1.40.1` / `1.1.414`). `basedpyright` has stricter defaults and
   `reportUnnecessaryTypeIgnoreComment`, which is more useful when ratcheting. Not verified
   for pydantic v2 edge cases.
8. **`oracledb` major-version bump risk.** The project pins `oracledb>=2.0`; the
   `testcontainers[oracle-free]` extra requires `>=3`, and PyPI shows `26.0.0`. Resolving the
   extra will move the Oracle adapter onto a much newer driver. *Verify the Oracle adapter
   against the resolved version before relying on it in CI.*

---
*Stack research for: production-hardening an async multi-engine Python ORM (`encino_orm` 0.3.0)*
*Researched: 2026-09-17*
