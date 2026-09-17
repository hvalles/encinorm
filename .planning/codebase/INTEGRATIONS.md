# External Integrations

**Analysis Date:** 2026-09-17

## APIs & External Services

**Databases (primary integration surface):**
- SQLite - Embedded file/in-memory database, core dependency.
  - SDK/Client: `aiosqlite` (declared in `pyproject.toml`; used in `encino_orm/sqlite.py`)
  - Auth: none; connection kwarg `database` (default `:memory:`), WAL + foreign keys enabled on connect.
- MySQL - Core dependency.
  - SDK/Client: `aiomysql` (`encino_orm/mysql.py`)
  - Auth: `host`, `port`, `user`, `password`, `db` kwargs; test env vars `ENCINO_ORM_MYSQL_*` (`tests/test_mysql.py`).
- MariaDB - Core dependency, reuses the MySQL driver.
  - SDK/Client: `aiomysql` (`encino_orm/mariadb.py`)
  - Auth: same kwargs as MySQL; test env vars `ENCINO_ORM_MARIADB_*` (`tests/test_mariadb.py`).
- PostgreSQL - Core dependency.
  - SDK/Client: `asyncpg` (`encino_orm/postgresql.py`)
  - Auth: `host`, `port`, `user`, `password`, `database` kwargs; test env vars `ENCINO_ORM_POSTGRES_*` (`tests/test_postgresql.py`).
- SQL Server - Optional extra `mssql`.
  - SDK/Client: `aioodbc` + `pyodbc` (`encino_orm/mssql.py`)
  - Auth: builds an ODBC connection string (`DRIVER`, `SERVER`, `UID`, `PWD`, `DATABASE`); TLS on by default (`Encrypt=yes`, `TrustServerCertificate=no`), overridable via `encrypt` / `trust_server_certificate`. Requires ODBC Driver 18 for SQL Server on the host.
- Oracle - Optional extra `oracle`.
  - SDK/Client: `oracledb` in async thin mode (`encino_orm/oracle.py`)
  - Auth: `host`, `port`, `service_name`, `user`, `password`; builds DSN with `oracledb.makedsn`.

**Cache:**
- Redis - Optional extra `cache`.
  - SDK/Client: `redis.asyncio` (lazy import in `encino_orm/model/cache_backend.py`, class `RedisCacheBackend`)
  - Auth: URL-based, default `redis://localhost`; test env var `ENCINO_ORM_REDIS_URL` (`tests/test_redis_cache.py`).

**GraphQL:**
- No external service. `strawberry-graphql` (extra `graphql`) generates an in-process schema in `encino_orm/graphql/schema.py`; resolvers use `strawberry.dataloader.DataLoader` for batch loading (`encino_orm/graphql/resolvers.py`). The host app serves the schema.

**REST:**
- No external service. `fastapi` (extras `http`/`security`) generates an `APIRouter` of CRUD routes via `create_crud()` in `encino_orm/http/__init__.py`; the host app mounts it. Default prefix `/api`.

**Observability (optional, undeclared):**
- OpenTelemetry - `OtelQueryTracer` in `encino_orm/observability.py` lazily imports `opentelemetry.trace` and emits one span per query (`db.system`, `db.operation`, `db.statement`, `db.elapsed_ms`, `db.rows`). The `opentelemetry-api` package is **not** a declared dependency; the application must install and configure the `TracerProvider`/exporter.

## Data Storage

**Databases:**
- Six relational engines supported through one async `Db` interface: SQLite, MySQL, MariaDB, PostgreSQL, SQL Server, Oracle.
  - Connection: per-engine kwargs passed to `create_db(engine, **kwargs)` (`encino_orm/pool.py`); test suite reads `ENCINO_ORM_*` env vars.
  - Client: engine-specific adapters (`encino_orm/sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`).
  - Migrations: versioned via `Migration`/`apply_migrations` (`encino_orm/migration.py`), tracked in the `_encino_orm_migrations` table on each engine.
  - Schema: `create_table`, `diff_schema`, `sync_schema`; introspection/codegen in `encino_orm/introspection/`.
  - Pooling: `PoolDb` (`encino_orm/pool.py`) manages a connection pool with per-`contextvar` transactional connections and stats.

**File Storage:**
- Local filesystem only (SQLite database files). No object storage integration.

**Caching:**
- In-memory `MemoryCacheBackend` (default, `encino_orm/model/cache_backend.py`).
- Redis `RedisCacheBackend` (optional extra `cache`), consumed by `CachedModel` (`encino_orm/model/cached.py`) and `HasMany` collection caching.
- `Filter.digest()` (SHA-1) is used as a stable cache key component.

## Authentication & Identity

**Auth Provider:**
- Custom, library-provided (no third-party identity provider).
  - Implementation: JWT via `PyJWT` in `encino_orm/security/jwt.py`.
    - Access tokens: `emit_token` / `verify_token` (claim `type: "access"`, default 900s TTL).
    - Refresh tokens: `emit_refresh` / `verify_refresh` (claim `type: "refresh"`, default 604800s TTL).
    - Algorithm allowlist (`HS*`, `RS*`, `ES*`, `PS*`) rejects `"none"` on both emit and verify.
  - RBAC: tri-state (`True`/`False`/`None`) permission model with deny-by-default and role ordering; `PermissionSet` in `encino_orm/security/permissions.py`.
  - FastAPI guard: `get_current_user` / `require` dependencies in `encino_orm/security/guard.py`; resolve the bearer token from `Authorization: Bearer`. Anonymous requests map to role `Público`.
  - Persistence: `Rol`, `Roldet`, `RolUsuario` models in `encino_orm/security/models.py` (tables `roles`, `roles_det`, `roles_usuario`); seeded via `seed_roles` with `Administrador`, `Usuario Interno`, `Público`.
  - Credential hashing/login is explicitly out of scope: the host application authenticates the user and calls `emit_token`.

## Monitoring & Observability

**Error Tracking:**
- None. No Sentry/rollbar-style SDK is integrated. Errors surface as `EncinoOrmError` subclasses in `encino_orm/exceptions.py` (`ConnectionError`, `QueryError`, `UnsupportedEngineError`, `MigrationError`, `PoolExhaustedError`).

**Logs:**
- Python `logging` under the `encino_orm` logger (`encino_orm/base.py`).
- `QueryTracer` (`encino_orm/observability.py`) logs each query with timing, params and `trace_id`, and optionally collects counters (`queries`/`errors`/`rows`) and a latency histogram (`min`, `max`, `avg`, `p50`, `p90`, `p99`).
- Request correlation via `trace_id` contextvar (`trace_id`, `current_trace_id`).
- Optional OpenTelemetry spans via `OtelQueryTracer` (see above).

## CI/CD & Deployment

**Hosting:**
- Library: PyPI (`encino-orm`); release workflow `.github/workflows/release.yml` publishes on `v*` tags.
- Docs: GitHub Pages (`https://hvalles.github.io/encinorm/`), deployed by `.github/workflows/docs.yml`.
- No application runtime hosting is provided by this repository.

**CI Pipeline:**
- GitHub Actions, `.github/workflows/ci.yml`:
  - Matrix Python 3.10–3.13 on `ubuntu-latest`.
  - Service containers: `mysql:8.0` (port 3306) and `postgres:16-alpine` (port 5432) with health checks.
  - Steps: `actions/checkout@v5`, `astral-sh/setup-uv@v5` (cache enabled), `uv sync --extra http --extra security --extra graphql`, `uv run pytest -q`.
  - Credentials injected as `ENCINO_ORM_MYSQL_*` and `ENCINO_ORM_POSTGRES_*` env vars.
- Pre-release: `.github/workflows/publish-testpypi.yml` (`workflow_dispatch`) publishes to TestPyPI.

## Environment Configuration

**Required env vars (test/integration, all with defaults in `tests/`):**

| Engine | Variables | Defaults |
|--------|-----------|----------|
| MySQL | `ENCINO_ORM_MYSQL_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| MariaDB | `ENCINO_ORM_MARIADB_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3307` / `root` / `admin` / `encino_orm_test` |
| PostgreSQL | `ENCINO_ORM_POSTGRES_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `5432` / `postgres` / `admin` / `encino_orm_test` |
| SQL Server | `ENCINO_ORM_MSSQL_HOST/PORT/USER/PASSWORD/DB/DRIVER/TRUST_CERT` | `127.0.0.1` / `1433` / `sa` / `Admin_123` / `encino_orm_test` / `ODBC Driver 18 for SQL Server` / `true` |
| Oracle | `ENCINO_ORM_ORACLE_HOST/PORT/SERVICE/USER/PASSWORD` | `127.0.0.1` / `1521` / `XEPDB1` / `system` / `admin` |
| Redis | `ENCINO_ORM_REDIS_URL` | `redis://127.0.0.1:6379` |

Documented in `docs/docker.md` and `docs/design/a-xpress.md`.

**Secrets location:**
- GitHub Actions repository secrets: `PYPI_API_TOKEN` (`.github/workflows/release.yml`), `TEST_PYPI_API_TOKEN` (`.github/workflows/publish-testpypi.yml`); OIDC Trusted Publishing is documented as the tokenless alternative.
- Runtime JWT secret is provided by the host application via `encino_orm.security.guard.SECRET` (no built-in secret storage).
- No `.env` file present in the repository (`.gitignore` excludes `.env`).
- Credentials in `docker-compose.yml` are local development defaults only (`admin` / `Admin_123`, MySQL/MariaDB root).

## Webhooks & Callbacks

**Incoming:**
- None. The library exposes no HTTP endpoints of its own; FastAPI routes generated by `create_crud()` (`encino_orm/http/routes.py`) are mounted and served by the host application.

**Outgoing:**
- None. No outbound HTTP client calls, webhook dispatch, or event publishing exist in the codebase. All I/O is database/cache protocol traffic through the async drivers.

---

*Integration audit: 2026-09-17*
