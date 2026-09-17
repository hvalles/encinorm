# Testing Patterns

**Analysis Date:** 2026-09-17

## Test Framework

**Runner:**
- pytest >= 9.1.1, configured in `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  pythonpath = ["."]
  ```
- Async support: `pytest-asyncio >= 1.4.0`. Despite `asyncio_mode = "auto"`, tests still declare `@pytest.mark.asyncio` explicitly (see "Patterns" below).
- No custom markers are registered (`markers = [...]` absent), and no `pytest.ini`, `setup.cfg`, or `tox.ini` exists.

**Assertion Library:**
- Plain `assert` statements (pytest's assertion rewriting). `pytest.approx` is **not** used; comparisons are exact.
- Exception assertions use `pytest.raises(...)`; the `match=` argument is not used.

**Run Commands:**
```bash
uv run pytest                         # Full suite (SQLite + MySQL + PostgreSQL + optional engines)
uv run pytest tests/test_mssql.py     # Single engine suite
uv run pytest tests/test_oracle.py
uv run pytest tests/test_mariadb.py
uv run pytest -q                      # Command used by CI (.github/workflows/ci.yml:79)
```

**Coverage:**
- **No coverage tooling is configured.** There is no `pytest-cov` dependency, no `[tool.coverage]` section, no `.coveragerc`, and no coverage step in CI. `.gitignore` ignores `.coverage`/`htmlcov/`, but no command produces them.

## Test File Organization

**Location:**
- Single top-level `tests/` directory (not co-located with source). `tests/__init__.py` and `tests/conftest.py` exist.
- One file per feature/engine: `tests/test_crud.py`, `tests/test_sqlite.py`, `tests/test_postgresql.py`, `tests/test_pool.py`, `tests/test_security.py`, `tests/test_graphql.py`.
- Review-driven files are named after the design recommendation batch they address: `tests/test_d_recommendations.py`, `tests/test_e_recommendations.py`, `tests/test_f_recommendations.py`, `tests/test_g_recommendations.py`, plus `tests/test_improvements.py` and `tests/test_issues.py`.

**Naming:**
- Files: `tests/test_<feature>.py`.
- Classes: `Test<Feature>` in PascalCase (e.g., `TestPostgresInternal`, `TestPostgresLifecycle`, `TestParsing`, `TestRegistry`, `TestPool`, `TestRetry`).
- Functions: `test_<snake_case_description>`, English, behavior-focused (`test_transaction_commits_on_success`, `test_ignore_duplicated`, `test_no_command_returns_nonzero`).

**Structure:**
```
tests/
├── __init__.py
├── conftest.py                    # Shared db + connected_db fixtures
├── test_<feature>.py              # Grouped Test<Feature> classes
├── test_<engine>.py               # Per-engine integration tests (skip if unavailable)
└── test_<x>_recommendations.py    # Review batch regressions
```

## Test Structure

**Suite Organization:**
```python
import pytest

from encino_orm import Query, SqliteDb
from encino_orm.model import Model


class Agente(Model):
    _table = "agentes"
    agente: str | None = None


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_sort_by(self, db):
        await Agente(db, agente="a", region_id=2).insert()
        rows = await Agente(db).search(sort_by=["-region_id"])
        assert [r.region_id for r in rows] == [2]
```
(Pattern taken from `tests/test_crud.py:20-115`.)

**Shared fixtures (`tests/conftest.py`):**
```python
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
- `db` is an unconnected `SqliteDb` for unit-level checks.
- `connected_db` is an async, `:memory:`-backed connection for CRUD tests.
- Windows event-loop policy is set at import time for `win32` (`tests/conftest.py:8-9`).

**Patterns:**
- Fixtures use `yield` for teardown (close the connection/pool): `tests/conftest.py:21`, `tests/test_postgresql.py:77-78`, `tests/test_pool.py:94-95`.
- Feature-local fixtures override the shared `db` fixture to seed DDL (e.g., `tests/test_crud.py:36-44`, `tests/test_improvements.py:33-36`).
- Fixtures return pre-seeded models or the connection directly; tests destructure at the top of the method.
- Test bodies follow Arrange → Act → Assert with no `setup_method`/`teardown_method`; lifecycle is entirely fixture-driven.
- Temporary files use the built-in `tmp_path` fixture (e.g., `tests/test_cli.py:36-56`, `tests/test_from_db.py:171-217`).

## Mocking

**Framework:** `monkeypatch` (pytest built-in). `unittest.mock` / `MagicMock` / `AsyncMock` are **not used anywhere** in `tests/`.

**Patterns:**
```python
@pytest.mark.asyncio
async def test_retry_on_lock_error(self, monkeypatch):
    db = SqliteDb()

    async def no_sleep(*a, **k):
        return 0

    monkeypatch.setattr(db, "wait", no_sleep)

    calls = {"n": 0}

    async def op():
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception("database is locked")
        return "ok"

    result = await db.retry(op, tries=5)
    assert result == "ok"
    assert calls["n"] == 3
```
(`tests/test_improvements.py:55-75`.)

**Hand-written fakes instead of mock objects:**
```python
class FakeDb:
    def __init__(self):
        self.connected = False
        self.calls = []
    ...
    async def fetch_all(self, qry):
        self.calls.append(("fetch_all", qry))
        return [{"q": qry}]


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb
```
(`tests/test_pool.py:11-87`.) Fakes record calls in a list and expose `is_connected`, `transaction`, etc. Prefer this approach over patching library internals.

**What to Mock:**
- Non-deterministic or slow side effects: sleep/backoff (`monkeypatch.setattr(db, "wait", no_sleep)`).
- Registry/dispatch tables for isolated unit tests (`monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)`).
- Availability checks are handled by skipping, not mocking (see "Test Types").

**What NOT to Mock:**
- The database engine under test. Real SQLite (`:memory:`) is used by default; MySQL/PostgreSQL use real services via `docker-compose.yml` / CI service containers.
- `Query`, `Filter`, and model objects are exercised directly.

## Fixtures and Factories

**Test Data:**
- Models are declared at module scope with real `_table` names and Spanish domain fields (`Region`, `Agente`, `Ciudad` in `tests/test_crud.py:20-33`).
- Reusable DDL strings are module constants, e.g. `AGENTE_DDL` in `tests/test_improvements.py:27-30`.
- Constraint helpers are created at import time: `STR_50 = make_constraint(str, max_length=50)` (`tests/test_crud.py:17`).
- Per-engine reset helpers are module-level async functions: `async def _reset(db, name, ddl)` (`tests/test_mysql.py:36`, `tests/test_postgresql.py:81`).
- Seed helpers are private module functions or methods: `_seed`, `_seed_permissions`, `_cursor` (`tests/test_query_builder.py:37`, `tests/test_security.py:41`, `tests/test_issues.py:47`).

**Location:**
- No `fixtures/` or `factories/` directory. Fixtures live in `tests/conftest.py` (shared) or inline in each `tests/test_*.py` (local).

## Coverage

**Requirements:** None enforced. No coverage threshold, no CI coverage report.

**View Coverage:**
- Not applicable — install `pytest-cov` and run `uv run pytest --cov=encino_orm` if needed; there is no existing command to reuse.

## Test Types

**Unit Tests:**
- Pure logic and SQL builders, no live connection: `TestPostgresInternal` in `tests/test_postgresql.py:17-55` asserts generated SQL and `_rowcount` parsing; `TestParsing`/`TestRegistry` in `tests/test_crud.py:54-102`.
- White-box tests import private helpers directly: `from encino_orm.postgresql import _rowcount, _to_postgres` (`tests/test_postgresql.py:6`), `from encino_orm.cli import _build_parser, _conn_kwargs, main` (`tests/test_cli.py:5`). This is an accepted pattern here.
- Some async unit tests run the coroutine via `asyncio.run(...)` when no async fixture is wanted (`tests/test_cli.py:39-48`, `tests/test_transfer.py:209`).

**Integration Tests:**
- SQLite is always available (`:memory:` or `tmp_path` files) and runs by default.
- MySQL, MariaDB, PostgreSQL, SQL Server, and Oracle tests connect using environment variables with defaults and call `pytest.skip(...)` when the server is unreachable:
  ```python
  admin = PostgresDb()
  try:
      await admin.connect(**cfg, database="postgres")
  except Exception as e:
      pytest.skip(f"PostgreSQL no disponible: {e}")
  ```
  (`tests/test_postgresql.py:58-78`; same pattern in `tests/test_mysql.py:25`, `tests/test_mariadb.py:38`, `tests/test_mssql.py:124-135`, `tests/test_oracle.py:103`, `tests/test_redis_cache.py:28-35`.)
- Connection config is read from env with defaults, e.g. `POSTGRES_CONFIG` in `tests/test_postgresql.py:8-14` using `ENCINO_ORM_POSTGRES_HOST/PORT/USER/PASSWORD/DB`. CI injects these in `.github/workflows/ci.yml:68-78`.
- `docs/docker.md` documents the container setup for each engine; `docker-compose.yml` defines the local services.

**E2E Tests:**
- No browser E2E framework. HTTP layers are tested in-process with `httpx` ASGI transport:
  ```python
  transport = ASGITransport(app=app)
  async with AsyncClient(transport=transport, base_url="http://test") as client:
      resp = await client.get("/api/regiones")
  ```
  (`tests/test_crud.py:133-134`, `tests/test_pagination_limits.py:25`.)
- GraphQL is exercised against an in-memory schema (`tests/test_graphql.py`).
- CLI end-to-end uses `tmp_path` plus a real SQLite file (`tests/test_cli.py:36-58`).

## Common Patterns

**Async Testing:**
```python
class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, pg_connected_db):
        db = pg_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False
```
(`tests/test_postgresql.py:86-92`.)

**Note on `@pytest.mark.asyncio`:** Although `asyncio_mode = "auto"` makes the marker redundant, it is the dominant convention (present in nearly every async test). A few async tests omit it and rely on auto mode (`tests/test_engine.py`, `tests/test_sql_functions.py`, and one test in `tests/test_model.py`). **Use the explicit `@pytest.mark.asyncio` decorator for new async tests** to match the majority.

**Error Testing:**
```python
with pytest.raises(ValueError):
    ...
with pytest.raises(KeyError):
    r.get("inexistente")
```
(`tests/test_crud.py:101-102`, `tests/test_improvements.py:89-90`.) `match=` is not used, so assert exception messages separately only when necessary.

**Fixture-Based Teardown:**
```python
@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Ciudad(d, nombre="tmp").create_table()
    yield d
    await d.close()
```
(`tests/test_crud.py:36-44`.)

**Cross-Engine Parameterization:** There is no `@pytest.mark.parametrize` usage. Engine coverage is achieved through separate files and skip-guarded fixtures rather than parameterized cases.

## CI Test Execution

`.github/workflows/ci.yml`:
- Matrix over Python `3.10`, `3.11`, `3.12`, `3.13`; `fail-fast: false`.
- Service containers for MySQL 8.0 and PostgreSQL 16 with health checks.
- `uv sync --extra http --extra security --extra graphql`, then `uv run pytest -q`.
- MySQL/PostgreSQL credentials and host env vars are set on the test step.
- No lint, type-check, or coverage gate runs in CI.

**Known gap:** `README.md:130` documents `uv run pytest -m "not integration"`, but no `integration` marker is registered in `pyproject.toml` and no test uses `@pytest.mark.integration`. Integration tests are gated by `pytest.skip()` on connection failure instead, so that documented command does not do what it implies.

---

*Testing analysis: 2026-09-17*
