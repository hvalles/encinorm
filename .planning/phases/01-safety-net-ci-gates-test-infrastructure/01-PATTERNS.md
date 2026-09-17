# Phase 1: Safety Net — CI Gates & Test Infrastructure - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 10 (6 new, 4 modified)
**Analogs found:** 8 / 10

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tools/ci/check_skips.py` | utility (CLI script) | file-I/O / transform | `encino_orm/cli.py` | role-match |
| `tests/test_ci_harness.py` | test | unit + file-I/O | `tests/test_cli.py` + `tests/test_pool.py` | exact |
| `tests/test_pool_characterization.py` | test | event-driven / concurrency | `tests/test_pool.py` | exact |
| `tests/test_pytest_config.py` | test | config regression guards | `tests/test_ci_harness.py` | role-match |
| `tests/conftest.py` (modify) | config / test fixture | request-response | `tests/conftest.py` (self) + skip pattern in `tests/test_postgresql.py` | exact |
| `encino_orm/py.typed` (new) | config (packaging marker) | none | — | no analog |
| `pyproject.toml` (modify) | config | none | `pyproject.toml` (self) | exact |
| `.github/workflows/ci.yml` (modify) | config / CI | event-driven | `.github/workflows/ci.yml` (self) | exact |
| `.github/workflows/release.yml` (modify) | config / CI | event-driven | `.github/workflows/release.yml` (self) | exact |
| `.git-blame-ignore-revs` (new) | config | none | — | no analog |

---

## Pattern Assignments

### `tools/ci/check_skips.py` (utility, file-I/O / transform)

**Analog:** `encino_orm/cli.py` — the only checked-in, stdlib-only, runnable script with a `main(argv) -> int` contract. `tools/` does not exist yet (verified), so this script establishes the directory.

**Module docstring pattern** (`encino_orm/cli.py:1-5`) — Spanish prose, states purpose and usage:
```python
"""CLI de encino_orm (solo stdlib `argparse`).

Subcomandos: `encino_orm generate models <engine> [tablas...]` y
`encino_orm copy <src-engine> <dst-engine> [tablas...]`.
"""
```

**Imports pattern** (`encino_orm/cli.py:7-11`) — stdlib only, no third-party:
```python
import argparse
import asyncio
import sys
```
For `check_skips.py`, only `sys` + `xml.etree.ElementTree` are needed (see RESEARCH §Pattern 2 sketch).

**`main(argv) -> int` contract** (`encino_orm/cli.py:123-138`) — the repo convention is a pure function returning an exit code, with the argument vector injected (so it is unit-testable), and errors printed to `sys.stderr`:
```python
def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    ...
        except Exception as exc:  # pragma: no cover - depende del entorno
            print(f"error: {exc}", file=sys.stderr)
            return 1
    parser.print_help()
    return 1
```

**Error/output convention** (`encino_orm/cli.py:129-136`) — failures go to `sys.stderr`; success messages use plain `print`. Mirror this in the gate: `print(..., file=sys.stderr)` + `return 1` on failure, `print("OK...")` + `return 0` on success.

**Gap to fill from RESEARCH (no repo analog):** `cli.py` is registered as a console-script (`pyproject.toml:38-39`), so it has **no** `if __name__ == "__main__"` block anywhere in the repo (verified by grep). `tools/ci/check_skips.py` is invoked as `python tools/ci/check_skips.py junit.xml`, so it needs the entry block from RESEARCH §Pattern 2:
```python
if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

---

### `tests/test_ci_harness.py` (test, unit + file-I/O)

**Analogs:** `tests/test_cli.py` (testing a checked-in script's helpers + `main()`), `tests/test_pool.py` (fixture/monkeypatch style).

**Imports + class organization** (`tests/test_cli.py:1-8`) — import the private helpers directly (white-box is an accepted pattern, per CONTEXT §Established Patterns); group assertions into plain `Test*` classes:
```python
import asyncio

import pytest

from encino_orm.cli import _build_parser, _conn_kwargs, main
from encino_orm.query import Query
from encino_orm.sqlite import SqliteDb


class TestConnKwargs:
    def test_sqlite(self):
        ...
```

**Script-under-test invocation** (`tests/test_cli.py:36-61`) — drive `main()` in-process, use `tmp_path` for files, assert the exit code and the produced artifact:
```python
    def test_end_to_end(self, tmp_path):
        db_file = tmp_path / "app.db"
        ...
        code = main([
            "generate", "models", "sqlite",
            "--database", str(db_file), "--folder", str(out),
        ])
        assert code == 0
        text = (out / "agentes.py").read_text(encoding="utf-8")
        assert "class Agentes(Model):" in text

    def test_no_command_returns_nonzero(self):
        assert main([]) == 1
```
For `test_ci_harness.py`, the same shape applies: write fixture XML documents (clean / with skips / with failures) into `tmp_path`, call `check_skips.total_skipped(path)` and `check_skips.main(["prog", str(path)])`, assert counts and exit codes. RESEARCH §Validation Architecture names the exact test names: `-k require_engines`, `-k check_skips`.

**Monkeypatch-fixture pattern for the engine switch** (`tests/test_pool.py:84-95`) — use `monkeypatch.setenv` for `ENCINO_ORM_REQUIRE_ENGINES` (analogous to `monkeypatch.setitem`):
```python
@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb


@pytest.fixture
async def pool(fake_engine):
    p = PoolDb("fake", min_size=2, max_size=5)
    await p.connect()
    yield p
    await p.close()
```

**Negative/failure-path tests** — `tests/test_pool.py:162-169` shows the repo's preferred failure assertion (`pytest.raises`), and `tests/test_cli.py:60-61` shows asserting a non-zero return:
```python
    def test_commit_raises(self, pool):
        with pytest.raises(ConnectionError):
            await pool.commit()
```
For the switch, the unit test must assert `pytest.fail.Exception` (or `Failed`) is raised when the engine is required, and `pytest.skip.Exception` when it is not.

**RESEARCH-provided fixtures to author (no analog):** sample JUnit XML documents. Shape is verified in RESEARCH §Pattern 2:
```xml
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="0" skipped="13" tests="19" ...>
    <testcase classname="..." name="..." time="0.001" />
```
Author three minimal documents: `skipped="0"`, `skipped="N"` (multiple `<testsuite>` elements to prove the sum), and a failing suite (to prove failures are *not* counted as skips).

---

### `tests/test_pool_characterization.py` (test, event-driven / concurrency)

**Analog:** `tests/test_pool.py` — exact match. It already contains the hand-written `FakeDb`, the `fake_engine` monkeypatch fixture, the `pool` fixture, and private-state assertions.

**Hand-written fake (prefer over `unittest.mock`, per CONTEXT §Reusable Assets)** (`tests/test_pool.py:11-81`) — the FakeDb records every call in `self.calls` and exposes the state the pool inspects (`is_connected`, `is_alive`, `in_transaction`, `last_id`):
```python
class FakeDb:
    def __init__(self):
        self.connected = False
        self.closed = False
        self.calls = []
        self._last = 0
        self._in_tx = False

    @property
    def is_connected(self):
        return self.connected

    async def connect(self, **kwargs):
        self.connected = True
    ...
    async def execute(self, qry):
        self.calls.append(("execute", qry))
        self._last = 42
        self._in_tx = True
        return 1

    async def last_id(self):
        self.calls.append(("last_id",))
        return self._last
```

**Engine registration + fixtures** (`tests/test_pool.py:84-95`) — reuse verbatim; the characterization file should define its own `FakeDb` subclass or import-share, but keep the `monkeypatch.setitem(pool_module._ENGINES, ...)` seam:
```python
@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb
```

**Private-state assertion style (accepted white-box)** (`tests/test_pool.py:100-119`) — assert directly on `_size`, `_connections`, and identity of reused connections:
```python
    async def test_connect_creates_min_size(self, pool):
        assert pool.is_connected is True
        assert pool._size == 2
        assert len(pool._connections) == 2
    ...
    async def test_max_size_creates_and_reuses(self, pool):
        conns = [await pool.acquire() for _ in range(5)]
        assert pool._size == 5
        assert len(pool._connections) == 5
        await pool.release(conns[0])
        reused = await pool.acquire()
        assert reused is conns[0]
```

**Sequential cap / `PoolExhaustedError` pattern** (`tests/test_pool.py:185-199`) — hold the only connection, assert timeout raises, then assert release restores availability:
```python
    async def test_acquire_timeout_raises(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()
        conn = await p.acquire()  # mantiene la única conexión
        with pytest.raises(PoolExhaustedError):
            await p.acquire(timeout=0.1)
        await p.release(conn)
        conn2 = await p.acquire(timeout=0.1)
        assert conn2 is conn
        await p.release(conn2)
        await p.close()
```

**`last_id` scoping inside/outside transaction** (`tests/test_pool.py:150-159`) — the existing test already characterizes the in-transaction case (`("last_id",)` in `db.calls`, `rid == 42`). The characterization file must add the *outside-transaction* case, which reads the pool-level cache (`encino_orm/pool.py:256-260`):
```python
    async def last_id(self):
        db = _current_connection.get()
        if db is not None:
            return await db.last_id()
        return self._last_id
```

**`close()` behavior to characterize** (`encino_orm/pool.py:152-160`, assertion style from `tests/test_pool.py:137-146`) — `close()` marks disconnected, drains the queue, closes every tracked connection, clears `_connections` and `_last_used`, and resets `_size` to 0. Characterize both the normal path and the **held-connection** path (a connection acquired but not released before `close()`). Existing analog:
```python
    async def test_close(self, pool):
        db = await pool.acquire()
        await pool.release(db)
        await pool.close()
        assert pool.is_connected is False
        assert pool._size == 0
        assert len(pool._connections) == 0
        assert db.closed is True
```

**Invariant to add — overshoot race (measured deterministic, RESEARCH §Sources):** concurrent `acquire()` on `max_size=2` yields `_size == 5`. The race is at `encino_orm/pool.py:114-124`: `get_nowait()` → `QueueEmpty` → `await self._create_connection()` (an await point) before `self._size += 1`. Characterize with a barrier built from `asyncio.Event` (Python 3.10 floor — **not** `asyncio.Barrier`, per RESEARCH §State of the Art) and a `FakeDb.connect` that blocks on that event. Assert the observed `_size > max_size` exactly as the current implementation behaves; add a comment that this is the pre-refactor baseline for Phase 4.

**Release semantics to characterize** (`encino_orm/pool.py:148-150`): `release()` only records `_last_used` and re-queues; it does **not** commit or check liveness. Pair with the double-`release` behavior. Also characterize the autocommit path in `_run`/`execute` (`encino_orm/pool.py:191-242`) which commits when `in_transaction()` is true — `tests/test_pool.py:202-213` (`TestPoolStandaloneCommit`) is the closest existing analog:
```python
    async def test_standalone_operation_commits(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()
        await p.execute(Query("INSERT 1", []))
        conn = next(iter(p._connections))
        assert any(c == "execute" for c, _ in conn.calls)
        assert ("commit",) in conn.calls
        await p.close()
```

> **Rule for this file (CONTEXT D-09 / deferred):** capture behavior **as-is**. Do not "fix" any surprising result, do not rewrite broad `pytest.raises`, and do not soften private-state assertions. These tests must pass unmodified against the current implementation.

---

### `tests/conftest.py` (modify) (config / test fixture, request-response)

**Analog:** the file itself (`tests/conftest.py:1-22`) plus the skip-on-connection-failure pattern in `tests/test_postgresql.py:58-78`.

**Current file to extend** (`tests/conftest.py:1-22`) — keep the Windows event-loop policy guard and existing fixtures untouched:
```python
import asyncio
import sys

import pytest

from encino_orm.sqlite import SqliteDb

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def db():
    return SqliteDb()


@pytest.fixture
async def connected_db():
    db = SqliteDb()
    await db.connect(database=":memory:")
    yield db
    await db.close()
```

**The skip site the helper must replace** (`tests/test_postgresql.py:63-67`) — the exact shape across all 8 sites (also `test_mysql.py:22-25`, `test_mariadb.py:35-38`, `test_mssql.py:121-124` and `:132-135`, `test_oracle.py:103`, `test_redis_cache.py:25-35`):
```python
    admin = PostgresDb()
    try:
        await admin.connect(**cfg, database="postgres")
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")
```

**Replacement helper (from RESEARCH §Pattern 1)** — add to `conftest.py`; call sites change `pytest.skip(...)` → `engine_unavailable("<engine>", e)`:
```python
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
The helper's return type is `None` (it always raises), matching the local style of annotated public functions with unannotated private helpers (`AGENTS.md` §Function Design). The docstrings are Spanish prose, one summary line — matching `encino_orm/cli.py:1-5` and `tests/test_pool.py:191` comments.

**Marker application style (RESEARCH §Marker application map):** use module-level `pytestmark = pytest.mark.integration` only for all-live files (`test_mysql.py`, `test_redis_cache.py`); use class-level decorators in mixed files (`test_postgresql.py`, `test_mariadb.py`, `test_mssql.py`, `test_oracle.py`). Do **not** add `integration` to the unit-only classes (`TestPostgresInternal`, `TestMssqlInternal`, `TestOracleInternal`, `TestMariadbLifecycle`'s pure-unit siblings) so their free coverage is preserved.

---

### `pyproject.toml` (modify) (config)

**Analog:** the file itself. Preserve existing sections and append new tool tables.

**Current pytest section to harden** (`pyproject.toml:41-44`):
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
```

**Current dev dependency group to extend** (`pyproject.toml:46-55`) — `ruff>=0.16.8` is already present; add `mypy`, `pytest-cov`, `coverage`, `pip-audit`. Pin ruff per RESEARCH (`==0.16.8` or `>=0.16.8,<0.17`):
```toml
[dependency-groups]
dev = [
    "pytest>=9.1.1",
    "pytest-asyncio>=1.4.0",
    "httpx>=0.27",
    "mkdocs>=1.6",
    "mkdocs-material>=9.5",
    "mkdocstrings[python]>=0.26",
    "ruff>=0.16.8",
]
```

**Sections to add (verbatim sketches in RESEARCH §Code Examples):** `[tool.ruff]` + `[tool.ruff.lint]` + `[tool.ruff.lint.per-file-ignores]` + `[tool.ruff.lint.isort]`; `[tool.mypy]` + `[[tool.mypy.overrides]]`; `[tool.coverage.run]` + `[tool.coverage.report]`; and the hardened `[tool.pytest.ini_options]` (add `asyncio_default_fixture_loop_scope`, `asyncio_default_test_loop_scope`, `addopts`, `xfail_strict`, `filterwarnings`, `markers`). **Do not copy `.planning/research/STACK.md`'s mypy block** — RESEARCH measured it at 458 errors; use the non-strict ladder.

**Comment style (project convention, `AGENTS.md` §Comments):** explanatory Spanish comments above non-obvious config, especially the ratchet floors — record the measured baseline and the phase that raises it (e.g. coverage `fail_under = 82` with a comment naming the 83% CI-equivalent measurement and Phase 2).

---

### `.github/workflows/ci.yml` (modify) (config / CI, event-driven)

**Analog:** the file itself. Extend, don't rewrite.

**Trigger block to extend for CI-08** (`ci.yml:3-6`) — add `workflow_call`:
```yaml
on:
  push:
    branches: [main]
  pull_request:
```

**Top-level settings to preserve** (`ci.yml:8-13`) — `permissions: contents: read` and the `concurrency` group must stay:
```yaml
permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

**Existing test job structure** (`ci.yml:16-23`) — keep the matrix and `timeout-minutes: 15` (RESEARCH §Pattern 2 cost note says do not lower it):
```yaml
  test:
    name: Python ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    timeout-minutes: 15
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]
```

**Service-container block** (`ci.yml:25-52`) — the MySQL + PostgreSQL health-checked services are the exact required engines for D-01; new gate jobs do **not** need them, only `test` does.

**uv setup + install steps to copy into new jobs** (`ci.yml:54-65`):
```yaml
    steps:
      - name: Checkout
        uses: actions/checkout@v5

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      - name: Install dependencies
        run: uv sync --extra http --extra security --extra graphql
```
New jobs (`lint`, `typecheck`, `deps`, `coverage`) reuse the Checkout + Install uv steps; add `version: "0.12.15"` to the `setup-uv` `with:` per RESEARCH assumption A1 (verify the input name first).

**Env-var injection pattern** (`ci.yml:67-78`) — append `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql` to this existing `env:` map and change the run command to `uv run pytest -q -m "not optional_engine" --junitxml=junit.xml --cov=encino_orm --cov-branch --cov-report=`:
```yaml
      - name: Run tests
        env:
          ENCINO_ORM_MYSQL_HOST: 127.0.0.1
          ENCINO_ORM_MYSQL_PORT: "3306"
          ...
          ENCINO_ORM_POSTGRES_DB: encino_orm_test
        run: uv run pytest -q
```
Then add the post-run gate step from RESEARCH §Pattern 2 (`if: always()`, `uv run python tools/ci/check_skips.py junit.xml`) and the `COVERAGE_FILE` env + `actions/upload-artifact` with `include-hidden-files: true`.

**Hard rule (RESEARCH §Anti-Patterns):** never add `continue-on-error: true` to any gate job.

---

### `.github/workflows/release.yml` (modify) (config / CI, event-driven)

**Analog:** the file itself.

**Trigger + permissions to preserve** (`release.yml:3-11`):
```yaml
on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

permissions:
  contents: read
  id-token: write          # para trusted publishing (OIDC) si se usa
```

**Jobs block to restructure for CI-08** (`release.yml:13-19`) — add a `ci` job that `uses: ./.github/workflows/ci.yml`, and make `publish` depend on it:
```yaml
jobs:
  publish:
    name: Build and publish
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v5
```
Becomes:
```yaml
jobs:
  ci:
    uses: ./.github/workflows/ci.yml
  publish:
    needs: [ci]
    name: Build and publish
    runs-on: ubuntu-latest
    steps: [...]
```

**Secret handling must not change** (`release.yml:35-38`): `UV_PUBLISH_TOKEN: ${{ secrets.PYPI_API_TOKEN }}`. The reusable-workflow call needs no `secrets: inherit` today (RESEARCH §Runtime State Inventory). The existing inline comments documenting the OIDC alternative must be preserved.

---

## Shared Patterns

### Spanish prose for docstrings and comments
**Source:** `encino_orm/cli.py:1-5`, `encino_orm/pool.py:26-28`, `tests/test_pool.py:191` (`# mantiene la única conexión`)
**Apply to:** `tools/ci/check_skips.py`, `tests/conftest.py` helper, all new `pyproject.toml` comments.
Comments explain *why*, not *what*. Module docstrings are one summary line plus optional paragraphs; no `Args:`/`Returns:` sections (`AGENTS.md` §Comments).

### stdlib-only tooling
**Source:** `encino_orm/cli.py:7-9` (`argparse`, `asyncio`, `sys` only)
**Apply to:** `tools/ci/check_skips.py` (`sys`, `xml.etree.ElementTree` only). Do not add a third-party dependency for the gate — RESEARCH §Don't Hand-Roll explicitly rejects custom serializers/plugins.

### `main(argv) -> int` + stderr-on-failure
**Source:** `encino_orm/cli.py:123-138`, consumed by `tests/test_cli.py:51-61`
**Apply to:** `tools/ci/check_skips.py`. Return an int exit code; the `__main__` block raises `SystemExit`. Failures print to `sys.stderr`.

### Env-var configuration namespace
**Source:** `tests/test_mysql.py:7-13`, `tests/test_postgresql.py:8-14`, `tests/test_redis_cache.py:8` — every engine reads `ENCINO_ORM_<ENGINE>_<FIELD>` with a default; CI injects them (`ci.yml:67-78`).
**Apply to:** the new `ENCINO_ORM_REQUIRE_ENGINES` var (D-03) — non-secret, comma-separated, lowercased, empty default so local runs skip as today.

### Skip-on-connection-failure → fail-when-required
**Source:** `tests/test_postgresql.py:64-67` (and 7 sibling sites)
**Apply to:** every engine fixture via `engine_unavailable()`. Keep the bare `except Exception` for now (CONTEXT D-09 / RESEARCH Pitfall 1) — only the skip/fail decision changes.

### Hand-written fakes over `unittest.mock`
**Source:** `tests/test_pool.py:11-87` (`FakeDb`, `fake_engine` via `monkeypatch.setitem`)
**Apply to:** `tests/test_pool_characterization.py`; `tests/test_ci_harness.py` uses `monkeypatch.setenv` for the switch.

### White-box assertions are accepted
**Source:** `tests/test_pool.py:100-119` (`pool._size`, `pool._connections`), `tests/test_postgresql.py:20` (`_to_postgres`), `tests/test_cli.py:5` (`_build_parser`)
**Apply to:** both new test files and the characterization suite. Import private helpers directly.

### GitHub Actions house style
**Source:** `ci.yml` / `release.yml` — `actions/checkout@v5`, `astral-sh/setup-uv@v5`, `enable-cache: true`, explicit `name:` on every job/step, `permissions: contents: read`, `concurrency` group with `cancel-in-progress`.
**Apply to:** new jobs in `ci.yml` and the new `ci` job in `release.yml`. Pin the uv `version:` input once assumption A1 is confirmed.

### Isolated, bisectable mechanical commits
**Source:** CONTEXT D-09 + RESEARCH §Anti-Patterns; `git config blame.ignoreRevsFile .git-blame-ignore-revs`
**Apply to:** the `ruff format`-only commit (61 files) must land alone and be recorded in `.git-blame-ignore-revs` before any rule fixes.

---

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `encino_orm/py.typed` | config (packaging) | none | PEP 561 marker is an empty file; no precedent in repo. Verified by RESEARCH that hatchling includes it automatically under `packages = ["encino_orm"]` — no `pyproject.toml` change needed. |
| `.git-blame-ignore-revs` | config | none | File does not exist (verified); no repo precedent. Use the RESEARCH §`.git-blame-ignore-revs` procedure (commit format-only change, `git rev-parse HEAD >> .git-blame-ignore-revs`, then `git config blame.ignoreRevsFile`). |
| `tools/ci/` directory | — | — | The repo has no `tools/` tree today (verified). `check_skips.py` is its first inhabitant; `cli.py` is the closest script convention but lives inside the package. |
| Sample JUnit XML fixtures for `test_ci_harness.py` | test fixture | file-I/O | No XML fixtures exist in the repo; shape verified in RESEARCH §Pattern 2. |

---

## Metadata

**Analog search scope:** `encino_orm/`, `tests/`, `.github/workflows/`, repo root (`pyproject.toml`, `.gitignore`, `README.md`)
**Files scanned:** 14 read (`cli.py`, `pool.py`, `conftest.py`, `test_pool.py`, `test_postgresql.py`, `test_mysql.py`, `test_mariadb.py`, `test_mssql.py`, `test_redis_cache.py`, `test_cli.py`, `ci.yml`, `release.yml`, `pyproject.toml`, `.gitignore`) + targeted greps for `__main__`/`cli`/`check_skips`
**Pattern extraction date:** 2026-09-17
**Sources of record for non-analog material:** `01-RESEARCH.md` §Pattern 1–4, §Code Examples, §Marker application map, §`.git-blame-ignore-revs`
