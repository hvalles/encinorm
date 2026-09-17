# Coding Conventions

**Analysis Date:** 2026-09-17

## Naming Patterns

**Files:**
- Modules are `snake_case.py` (e.g., `encino_orm/query_builder.py`, `encino_orm/cache_backend.py`).
- One public concept per module; engine adapters are named after the database (`encino_orm/sqlite.py`, `encino_orm/postgresql.py`, `encino_orm/mssql.py`, `encino_orm/oracle.py`, `encino_orm/mariadb.py`).
- Private/internal helper modules are prefixed with `_` (e.g., `encino_orm/_rows.py`).

**Classes:**
- `PascalCase` (e.g., `Db`, `Model`, `SqliteDb`, `PostgresDb`, `PoolDb`, `QueryBuilder`, `CachedModel`).
- Public abstract base is `Db` in `encino_orm/base.py`; per-engine concrete classes suffix with `Db` (`MysqlDb`, `MssqlDb`, `OracleDb`, `MariadbDb`).
- Value objects are frozen dataclasses: `Column` (`encino_orm/model/column.py`), `Constraint` (`encino_orm/model/constraint.py`), `Index` (`encino_orm/model/index.py`), `Migration` (`encino_orm/migration.py`).
- Pydantic `BaseModel` is used for data-bearing models: `Model` (`encino_orm/model/model.py:132`) and `Records` (`encino_orm/model/records.py:31`).

**Functions / Methods:**
- `snake_case` for all functions and methods (`fetch_all`, `fetch_one`, `create_table`, `insert_many`, `batch_has_many`).
- Private helpers use a single leading underscore (`_serialize`, `_base_type`, `_column_map`, `_prepare`, `_rowcount`).
- Dunder-prefixed attributes signal class-private state set via `object.__setattr__` (`__exists`, `__loading`, `__dirties` in `encino_orm/model/model.py:83-105`).

**Variables:**
- `snake_case`. Domain vocabulary is Spanish in SQL-facing and model code (`tabla`, `agentes`, `regiones`, `ciudades` in `tests/test_crud.py`) and English for infrastructure (`db`, `engine`, `query`, `rows`).
- Boolean flags read as predicates (`ignore_duplicated`, `replace`, `include_deleted`, `physical`).

**Constants:**
- `UPPER_SNAKE_CASE` (`MAX_TRIES`, `WAITERS`, `MAX_WAIT` in `encino_orm/base.py:16-18`; `DEFAULT_LIMIT`, `MAX_LIMIT` in `encino_orm/model/records.py:3-4`).
- Module-private constants use a leading underscore (`_IDENTIFIER_RE`, `_PLACEHOLDER_RE`, `_MISSING`, `_FIELD_ADAPTERS`, `_COLUMN_MAPS` in `encino_orm/model/model.py:28-31`).
- Type/DDL domain presets are exported from `encino_orm/model/domain.py` as `STR_10`, `STR_50`, `TEXT`, `INT`, `BOOL`, `DATETIME`, `JSON`, etc., and re-exported from `encino_orm/model/__init__.py`.

**Types:**
- Modern PEP 604 unions: `str | None`, `list[str] | None` (e.g., `encino_orm/base.py:54`, `encino_orm/model/records.py`).
- Forward references are quoted strings (`def cursor(cls, db: Db = None, **values) -> "Model":` in `encino_orm/model/model.py:170`).
- `Annotated[...]` is the public way to attach `Column` metadata (`tests/test_improvements.py:12`).

## Code Style

**Formatting:**
- No formatter is configured. There is **no** `ruff`, `black`, `flake8`, `isort`, `mypy`, or `pre-commit` config anywhere in the repo (`pyproject.toml` has no `[tool.ruff]`/`[tool.black]`; no `setup.cfg`, `tox.ini`, `.flake8`, `.ruff.toml`, or `.pre-commit-config.yaml`).
- De-facto style is PEP 8 with a practical line limit near 88 chars; a small number of lines exceed it (notably `encino_orm/security/permissions.py`, ~78 lines > 88). Match the surrounding file rather than imposing a new limit.
- **Since Phase 1 the enforced limit is `[tool.ruff].line-length = 100`** (deliberate: at 88 the source baseline was 195 ruff findings vs 128 at 100, and the smaller mechanical reformat diff was preferred). The config is the source of truth; this bullet's 88-char description is historical.
- Indentation is 4 spaces; blank line between top-level definitions; two blank lines between top-level classes/functions.
- Trailing commas and implicit string concatenation are used in multi-line calls/SQL (e.g., `tests/test_postgresql.py:45-48`).
- Multiple parameters per line are kept aligned when a signature is long (`encino_orm/base.py:95-96`, `encino_orm/model/model.py:118-119`).

**Linting:**
- Not detected. CI (`.github/workflows/ci.yml`) runs only `uv run pytest -q`; there is no lint/type-check gate.
- The only automated style signal is `[tool.pytest.ini_options]` in `pyproject.toml`.

## Import Organization

**Order:**
1. Standard library (`import asyncio`, `import logging`, `from contextlib import asynccontextmanager`).
2. Third-party (`import pytest`, `from pydantic import BaseModel`, `import aiosqlite`, `from fastapi import FastAPI`).
3. Local package imports.

**Local import style is mixed:**
- Sibling modules inside a package use relative imports (`from .query import Query` in `encino_orm/base.py:8`; `from .exceptions import ...` in `encino_orm/model/model.py:17`).
- Cross-package imports use absolute form (`from encino_orm.base import Db`, `from encino_orm.context import resolve_db` in `encino_orm/model/model.py:12-15`).
- Deferred imports are used deliberately to avoid optional-dependency and circular-import costs: `from .sql import SqlFunctions` inside `Db.fn` (`encino_orm/base.py:25`), `from .model.records import Records` inside methods (`encino_orm/base.py:144`), and `from fastapi.responses import JSONResponse` inside `install_error_handlers` (`encino_orm/http/errors.py:9`).

**Path Aliases:**
- None. Imports resolve against the repo root because `pyproject.toml` sets `pythonpath = ["."]`.

## Error Handling

**Exception hierarchy:**
- Core exceptions derive from `EncinoOrmError` in `encino_orm/exceptions.py`: `ConnectionError`, `QueryError`, `UnsupportedEngineError`, `MigrationError`, `PoolExhaustedError`.
- Model/domain exceptions live in `encino_orm/model/exceptions.py`: `ModelError`, `FailOnUpdate`, `ValidationError`, `NotFoundError`, `RelationshipError`, `DuplicateReferenceError`, `DuplicateAliasError`, `DuplicateColumnAliasError`.
- Security exceptions live in `encino_orm/security/exceptions.py`.

**Patterns:**
- Raise specific library exceptions with f-string messages in Spanish (e.g., `raise ConnectionError("No hay conexión activa a la base de datos.")` in `encino_orm/sqlite.py:96`, `encino_orm/mysql.py:103`, `encino_orm/postgresql.py:111`, `encino_orm/mssql.py:133`, `encino_orm/oracle.py:127`).
- `ValueError` is reserved for invalid identifiers/arguments, always with the offending value via `!r` (e.g., `raise ValueError(f"nombre de tabla inválido: {table!r}")` in `encino_orm/sqlite.py:110`; `_check_identifier` in `encino_orm/base.py:60-64`).
- Optional capabilities raise `NotImplementedError` with an explanatory message rather than silently no-op (`_tables_sql`/`columns_of` in `encino_orm/base.py:128-140`; `sql.uuid()` on SQLite in `encino_orm/sql.py:168`).
- Retry logic distinguishes retryable lock errors through an overridable predicate (`is_lock_error`) instead of broad exception catching (`encino_orm/base.py:74-92`).
- Transaction cleanup uses `try/except Exception: await self.rollback(); raise` so the original exception is preserved (`encino_orm/base.py:41-48`).
- HTTP boundaries map exceptions to status codes centrally in `encino_orm/http/errors.py` (`ValidationError` → 422, `FailOnUpdate` → 400, `QueryError` → 400) rather than per-route try/except.
- `raise ... from` chaining is not used; original exceptions are re-raised or skipped.

**SQL-injection guards:**
- Identifiers are validated by regex before interpolation. Reuse the existing pattern (`_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` in `encino_orm/base.py:12` and `encino_orm/model/model.py:29`; `_COLUMN_RE` in `encino_orm/sql.py:8`). Never interpolate an unvalidated identifier.
- Values are always passed as bound parameters through `Query` (`encino_orm/query.py`), never string-formatted into SQL.

## Logging

**Framework:** stdlib `logging` with the fixed logger name `"encino_orm"`.

**Patterns:**
- One module-level logger per engine/observability module: `logger = logging.getLogger("encino_orm")` (`encino_orm/base.py:10`, `encino_orm/observability.py:67`).
- Lazy `%`-style formatting, never f-strings, so formatting is skipped when the level is disabled: `logger.debug("sqlite %s (%.4fs) trace_id=%r sql=%r params=%r", ...)` (`encino_orm/sqlite.py:18`, mirrored in `encino_orm/mysql.py:20`, `encino_orm/postgresql.py:18`, `encino_orm/mssql.py:16`, `encino_orm/oracle.py:16`).
- Query tracing is pluggable via `QueryTracer` / `OtelQueryTracer` in `encino_orm/observability.py`; correlation uses `trace_id()` / `current_trace_id()`.

## Comments

**When to Comment:**
- Comments explain *why*, in Spanish, and are placed inline above the relevant logic (e.g., `# bool se almacena como int/tinyint en todos los motores` in `encino_orm/model/model.py:69`; `# normaliza a UTC-naive para almacenamiento uniforme entre motores` in `encino_orm/model/model.py:36`).
- Section separators are used in large modules: `# --- temporales ---` in `encino_orm/sql.py:50`.
- Data-shape contracts are documented next to the fields (e.g., inline comments on `Column` in `encino_orm/model/column.py:6-7`).
- Avoid commented-out code; the codebase favors explanatory comments and deferred-import rationale.

**JSDoc/TSDoc equivalent (docstrings):**
- Triple-quoted **Spanish prose**, one summary line followed by optional paragraphs.
- No structured `Args:` / `Returns:` / `Raises:` sections (no Google or Sphinx/NumPy style detected anywhere in `encino_orm/`).
- Docstrings include runnable examples in fenced code blocks where the API is subtle (`SqlFunctions` in `encino_orm/sql.py:30-38`).
- Not every function is documented; docstrings are concentrated on public API and non-obvious behavior.

## Function Design

**Size:** Small, single-purpose helpers at module top (e.g., `_serialize`, `_base_type`, `_int`). Large classes such as `Model` (`encino_orm/model/model.py`, 1083 lines) are acceptable because methods are individually small and grouped by concern (CRUD, relations, schema, batching).

**Parameters:**
- Public APIs prefer keyword-only arguments for flags/optional behavior: `def insert(self, *, ignore_duplicated: bool = False, replace: bool = False)` (`encino_orm/model/model.py:465`), `insert_many(cls, db=None, rows: list[dict] = None, *, chunk: int = 500)` (`encino_orm/model/model.py:506`).
- Mutable defaults are never used; `None` sentinels are normalized inside the body (e.g., `normalize_limit_page` in `encino_orm/model/records.py:14-28`).
- `**kwargs` is used for engine connection options (`async def connect(self, **kwargs)` in `encino_orm/base.py:30`).

**Return Values:**
- Public methods are annotated, including return types (`-> int`, `-> "Model"`, `-> dict | None`).
- Methods that mutate and return self for chaining are annotated `-> "Model"` (`add_reference`, `add_has_many` in `encino_orm/model/model.py:325-351`).
- Private helpers are frequently unannotated; follow the file's local density rather than forcing annotations everywhere.

## Module Design

**Exports:**
- Each package declares an explicit `__all__` listing its public API: `encino_orm/__init__.py:39-80` and `encino_orm/model/__init__.py`.
- Public symbols are re-exported from the top-level package so users can write `from encino_orm import Model, Query, SqliteDb`.

**Barrel Files:**
- `encino_orm/__init__.py`, `encino_orm/model/__init__.py`, `encino_orm/graphql/__init__.py`, `encino_orm/http/__init__.py`, `encino_orm/introspection/__init__.py`, `encino_orm/security/__init__.py` are barrels. Add new public symbols to both the import block and `__all__`.

**Design patterns to follow:**
- Abstract capability via `ABC` + `@abstractmethod` in `encino_orm/base.py`; concrete engines implement the same surface.
- `@asynccontextmanager` for scoped resources (`Db.transaction` in `encino_orm/base.py:41`, `PoolDb.transaction` in `encino_orm/pool.py:162`, `session()` in `encino_orm/pool.py:277`).
- `contextvars` for ambient state (`encino_orm/context.py`, `encino_orm/model/scope.py`, `encino_orm/pool.py:2`).
- `@dataclass(frozen=True)` for immutable value/config objects.
- `str, Enum` / `IntEnum` for closed sets (`Engine` in `encino_orm/engine.py:6`, `Weekday` in `encino_orm/sql.py:11`).

---

*Convention analysis: 2026-09-17*
