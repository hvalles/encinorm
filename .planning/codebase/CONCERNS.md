# Codebase Concerns

**Analysis Date:** 2026-09-17

## Tech Debt

**Dynamic code generation via `exec()` (REST + GraphQL layers):**
- Issue: HTTP route handlers and GraphQL resolvers are built by string-concatenating Python source and running it through `exec()` at registration time.
- Files: `encino_orm/http/routes.py:65-74`, `encino_orm/graphql/schema.py:85-101`
- Impact: No static analysis, no IDE navigation, no type checking, and syntax errors surface only at runtime. Debugging generated handlers requires printing the source. Signature derivation from `_primary_key` is brittle for composite keys.
- Fix approach: Replace `exec()` with closures/factories that take the PK fields as explicit parameters, or use `functools.partial` + a single handler that receives `**path_params`. `_create_resolver` (`encino_orm/graphql/schema.py:108-116`) already demonstrates the closure pattern that should be used everywhere.

**No linting, formatting, or type-checking tooling:**
- Issue: There is no `ruff`, `flake8`, `black`, `mypy`, or `pre-commit` configuration anywhere in the repo (verified: no config files, no entries in `pyproject.toml`, no CI step).
- Files: `pyproject.toml`, `.github/workflows/ci.yml`
- Impact: Style drift, unused imports, and type regressions are caught only by tests. Broad `except Exception` and dead code can accumulate undetected.
- Fix approach: Add `ruff` (lint + format) and `mypy` as dev dependencies, add a `lint` job to `.github/workflows/ci.yml`, and run `ruff check` + `mypy encino_orm` in CI.

**No coverage measurement or gate:**
- Issue: 507 test functions exist but there is no `pytest-cov` dependency, no `.coveragerc`/`[tool.coverage]`, and no coverage step in CI. `pyproject.toml` has no coverage settings.
- Files: `pyproject.toml:38-46`, `.github/workflows/ci.yml:67-79`
- Impact: Untestable or untested code paths (see Test Coverage Gaps) go unnoticed; no baseline for regression.
- Fix approach: Add `pytest-cov`, run `uv run pytest --cov=encino_orm --cov-report=term-missing`, and publish to Codecov or fail under a threshold.

**Duplicated dialect builders across six engine modules:**
- Issue: `insert`/`delete`/`update` (and migrations-table helpers) are copy-pasted across `encino_orm/sqlite.py`, `encino_orm/mysql.py`, `encino_orm/mariadb.py`, `encino_orm/postgresql.py`, `encino_orm/mssql.py`, `encino_orm/oracle.py`. Only the upsert/merge branch differs meaningfully.
- Impact: Fixes applied to one dialect (e.g., identifier validation) are easily missed in the others; divergence is already visible (MySQL/MariaDB have no `conflict` parameter; PostgreSQL's `replace` picks `columns[0]` as a fallback conflict target).
- Fix approach: Extract a shared builder in `encino_orm/base.py` with dialect hooks for the INSERT-conflict clause, and keep only the dialect-specific fragment overrides.

**Internal notes directory referenced by public docs:**
- Issue: `README.md` points readers to `prompts/analisys-07.md` for "readiness state", but `prompts/` is gitignored and not distributed.
- Files: `README.md:16`, `.gitignore:29`
- Impact: Published docs link to content that does not exist for users or CI checkouts.
- Fix approach: Move readiness/status content into `docs/` (tracked) and remove the `prompts/` reference from `README.md`.

## Known Bugs

**`COUNT(*)` column lookup fails on PostgreSQL (and likely SQL Server/Oracle):**
- Symptoms: `Model.count()`, `Model.paginate()`, `QueryBuilder.count()`, and `Db.list_tables()` raise `KeyError: 'COUNT(*)'` when run against PostgreSQL. asyncpg returns unquoted lowercase keys (`count`), while the code assumes the literal alias `COUNT(*)`.
- Files: `encino_orm/model/model.py:790-792`, `encino_orm/model/query_builder.py:240-242`, `encino_orm/base.py:151`
- Trigger: `await SomeModel.cursor(postgres_db).count()` or `.paginate()` against a real PostgreSQL connection. Note `Db.paginate` (`encino_orm/base.py:168-172`) already uses the correct `AS n` alias, showing the intended pattern.
- Workaround: Use `Db.paginate` (aliased) or raw `Query` with an explicit alias; do not use `Model.count`/`paginate` on PostgreSQL.
- Fix approach: Alias the count column (`SELECT COUNT(*) AS n`) in all three sites and read `row["n"]`, or add a dialect-aware result-key normalization in `PostgresDb.fetch_one`. Add integration coverage.

**Migration rollback leaves the migration marked as applied:**
- Symptoms: After `rollback_migration`, re-running `apply_migration` for the same `Migration` is a no-op, so the schema change is never re-applied. The rollback is recorded under a different name (`"{name}:down"`), and the original `name` row is never deleted.
- Files: `encino_orm/migration.py:25-29`, `encino_orm/sqlite.py:219-233` (and the equivalent `migrate` in `mysql.py`, `postgresql.py`, `mssql.py`, `oracle.py`)
- Trigger: `apply_migration(db, m)` → `rollback_migration(db, m)` → `apply_migration(db, m)` (second apply does nothing).
- Fix approach: On rollback, delete the `{name}` row from `_encino_orm_migrations` after executing `down`, and record the rollback separately (or not at all). Add a test asserting re-application after rollback.

**`migrate()` is not atomic:**
- Symptoms: `migrate` executes the DDL, then inserts the migration record, then commits. If the process dies or the insert fails after the DDL, the schema is changed but unrecorded (or vice versa on engines with implicit DDL commits).
- Files: `encino_orm/sqlite.py:219-233`, `encino_orm/mysql.py:243-258`, `encino_orm/postgresql.py:230-245`, `encino_orm/mssql.py:312-327`, `encino_orm/oracle.py:309-324`
- Trigger: Failure between `await self.execute(qry)` and the record insert.
- Fix approach: Wrap DDL + record insert in a transaction where the engine supports transactional DDL (PostgreSQL, SQLite, SQL Server); for MySQL/Oracle, record intent first with a status column and reconcile on startup.

**`CachedModel` never invalidates cached rows on update/delete:**
- Symptoms: After `update()` or `delete()`, `load()` keeps returning the stale cached payload until the TTL expires (default 300s).
- Files: `encino_orm/model/cached.py:22-47` (only writes on load); no `cache.delete` call exists anywhere in `encino_orm/` (verified by grep).
- Trigger: `CachedModel.load()` → `update()` → `load()` returns old data.
- Fix approach: Override `update`/`delete` in `CachedModel` to call `await self._cache.delete(self._cache_key(keys))` after a successful write, and add a test for invalidation.

## Security Considerations

**Public builder API interpolates table/column identifiers without validation:**
- Risk: `Db.insert`, `Db.delete`, and `Db.update` accept `tabla: str` and dict keys and embed them directly into SQL via f-strings. If an application passes a table or column name derived from user input, it is a SQL-injection vector.
- Files: `encino_orm/mysql.py:143-179`, `encino_orm/postgresql.py:146-183`, `encino_orm/mssql.py:180-230`, `encino_orm/oracle.py:190-227`, `encino_orm/sqlite.py:135-162`
- Current mitigation: The `Model` layer validates table/column names at class-definition time (`encino_orm/model/model.py:227,239,246-249`) and `transfer.build_ddl` validates (`encino_orm/transfer.py:105,108,111,143`), but the low-level `Db` builders themselves do not.
- Recommendations: Apply the existing `Db._check_identifier` (`encino_orm/base.py:59-64`) to `tabla` and every key in `insert`/`update`/`delete` across all dialects. Document these builders as trusted-input-only in the meantime.

**Raw SQL escape hatches:**
- Risk: `Filter.raw(sql, params)` (`encino_orm/model/filter.py:114-116`) and direct `Query(sql, ...)` accept arbitrary SQL. These are documented features but can be misused with untrusted input.
- Files: `encino_orm/model/filter.py:114-116`, `encino_orm/query.py:1-34`, `encino_orm/sql.py:32-37`
- Current mitigation: `Filter` field names are validated by `_safe_field` (`encino_orm/model/filter.py:26-29`); `filter_from_str` (`encino_orm/http/parsing.py:35-60`) only maps a fixed operator whitelist and never emits `raw`. GraphQL filter inputs (`encino_orm/graphql/filters.py`) expose typed operators, not raw SQL.
- Recommendations: Add a lint/rule or doc warning that `raw`/`Query` must never receive user-controlled strings; keep the HTTP/GraphQL parsers free of `raw`.

**SQL fragments returned by `db.fn.*` are trusted text:**
- Risk: `SqlFunctions` methods return SQL fragments intended for string interpolation. Column names are validated (`encino_orm/sql.py:43-48`), but callers could interpolate untrusted values into `amount`/`unit` (only `unit` is whitelisted via `_check_unit`).
- Files: `encino_orm/sql.py:62-81`
- Current mitigation: `_col` validation, `_check_unit`, and `date_format` quoting/escaping.
- Recommendations: Document clearly that `amount` and any non-whitelisted argument must be developer-controlled; prefer parameter binding for values.

**JWT/secret configuration lives in mutable module globals:**
- Risk: `SECRET` and `GET_DB` in `encino_orm/security/guard.py` are process-wide mutable globals. If unset, `_resolve` fails closed (good), but a misconfigured or later-overwritten global affects every request in the process.
- Files: `encino_orm/security/guard.py:13-31`
- Current mitigation: Fail-closed on missing config; `verify_token` requires `exp` and rejects refresh tokens as access tokens; `_ALLOWED_ALGORITHMS` blocks `none`/algorithm confusion (`encino_orm/security/jwt.py:17-28,59-72`).
- Recommendations: Prefer passing `secret`/`get_db` explicitly per dependency; if globals stay, freeze them after startup.

**Hardcoded credentials in dev infrastructure and long-lived PyPI token:**
- Risk: `docker-compose.yml` hardcodes `admin` passwords for MySQL/PostgreSQL/MSSQL/Oracle, which encourages copy-paste into real environments. The release workflows use a static `PYPI_API_TOKEN` secret instead of OIDC trusted publishing.
- Files: `docker-compose.yml:4-35`, `.github/workflows/release.yml:35-38`, `.github/workflows/publish-testpypi.yml`
- Current mitigation: Compose is dev-only; comments document the OIDC alternative.
- Recommendations: Add a prominent "dev-only credentials" warning to `docker-compose.yml`, and migrate release workflows to `uv publish --trusted-publishing always` with `id-token: write`.

**Migration files execute arbitrary code:**
- Risk: `migrations_from_dir` loads and executes every `*.py` in a directory via `importlib` `exec_module`.
- Files: `encino_orm/migration.py:38-55`
- Current mitigation: By-design behavior for migrations; path is caller-supplied.
- Recommendations: Document that the migrations directory must be trusted/version-controlled and never writable by untrusted parties.

## Performance Bottlenecks

**`copy_table` performs one INSERT round-trip per row:**
- Problem: Copying a table loops over rows and calls `dst.execute(dst.insert(table, data))` per row.
- Files: `encino_orm/transfer.py:155-167`
- Cause: No use of the existing `Model.insert_many` bulk path (`encino_orm/model/model.py:520-546`); no batching or `executemany`.
- Improvement path: Batch rows (e.g., 500-1000) into multi-value INSERTs, or reuse the bulk-insert SQL generator; measure against large tables.

**Every query re-parses placeholders with regex per call:**
- Problem: `_to_postgres`/`_to_positional`/`_to_named` run a regex substitution over the SQL on every execute/fetch.
- Files: `encino_orm/postgresql.py:22-29`, `encino_orm/sqlite.py:22-29`, `encino_orm/oracle.py:18-35`
- Cause: Placeholder translation happens at execution time rather than at `Query` construction.
- Improvement path: Pre-compute the translated SQL once (cache on the `Query` instance or compile at build time).

**Unbounded metric/latency accumulation:**
- Problem: `QueryTracer._latencies` appends every recorded query duration and is never trimmed unless `reset()` is called manually.
- Files: `encino_orm/observability.py:71,80-81,98-100`
- Cause: No ring buffer or sampling.
- Improvement path: Use a bounded deque or periodic reservoir sampling; expose a configurable max sample size.

**In-memory cache has no size bound and no active expiry:**
- Problem: `MemoryCacheBackend._store` grows without limit; expired entries are only removed when the same key is read.
- Files: `encino_orm/model/cache_backend.py:11-32`
- Cause: No max-size/LRU eviction or background sweep.
- Improvement path: Add an optional max-size with LRU eviction, or document it as dev/test-only (as the docstring suggests).

## Fragile Areas

**Connection pool `acquire()` has a check-then-act race:**
- Files: `encino_orm/pool.py:111-146`
- Why fragile: When the queue is empty and `self._size < self._max_size`, the code `await`s `_create_connection()` before incrementing `_size`. Two concurrent acquirers can both pass the size check and both create connections, exceeding `max_size`. `_size`/`_connections` are mutated across `await` points with no `asyncio.Lock`.
- Safe modification: Guard pool bookkeeping with an `asyncio.Lock`, or reserve a slot (increment `_size`) before awaiting connection creation.
- Test coverage: No concurrency test exists for the pool (`tests/test_pool.py` exercises sequential acquire/release only).

**Shared `_last_id` on `PoolDb` across concurrent inserts:**
- Files: `encino_orm/pool.py:63,229-242,256-260`
- Why fragile: `_last_id` is a single attribute on the pool, updated after any INSERT. Under concurrency, `pool.last_id()` can return another task's insert id.
- Safe modification: Store last-id per connection (already available via `_current_connection` inside transactions); for non-transactional use, return it from the same connection that performed the insert.
- Test coverage: Not tested concurrently.

**Implicit commit in `PoolDb._run`/`execute` can silently commit partial work:**
- Files: `encino_orm/pool.py:199-204,239-242`
- Why fragile: If any operation leaves a transaction open, the pool commits it before returning the connection. Mixing raw `Query` DML with model APIs outside `pool.transaction()` can commit unexpected partial state.
- Safe modification: Roll back instead of committing on release, or require explicit transaction management for writes.
- Test coverage: No test asserts the rollback-on-release behavior.

**Process-wide default connection singleton:**
- Files: `encino_orm/context.py:19-34,47-61`
- Why fragile: `set_default_db()` stores a process-global connection/pool; `resolve_db()` silently falls back to it. In multi-tenant or test-isolation scenarios, an unbound `Model` can resolve to the wrong database.
- Safe modification: Prefer `bind()`/`session()` (contextvars) over `set_default_db()`; add a teardown/`set_default_db(None)` in tests.
- Test coverage: `tests/test_singleton.py` exists but focuses on the singleton path itself.

**GraphQL `build_schema` mutates the module namespace:**
- Files: `encino_orm/graphql/schema.py:167-176`
- Why fragile: Each call `setattr`s generated types onto `encino_orm.graphql.schema` under `model.__name__`. Building two schemas with same-named models in one process overwrites types and can leak state across tests.
- Safe modification: Register generated types in a local namespace/`types` module namespace unique per build rather than mutating the library module.
- Test coverage: `tests/test_graphql.py` builds schemas but does not assert isolation across builds.

**Module-level field-adapter cache holds strong references:**
- Files: `encino_orm/model/model.py:434-449`
- Why fragile: `_FIELD_ADAPTERS` is a module-global dict keyed by class, holding `TypeAdapter`s forever. Dynamically generated model classes (codegen, tests) accumulate and are never released.
- Safe modification: Use a `WeakKeyDictionary` or cache on the class itself.
- Test coverage: Not tested.

**`sync_schema` interpolates catalog-derived column names:**
- Files: `encino_orm/model/model.py:877,885,896,900`
- Why fragile: `col` comes from database introspection (`_existing_columns_info`) and is interpolated into `ALTER TABLE` without the `_IDENTIFIER_RE` validation applied elsewhere. Exotic column names (spaces, quotes) break or could inject.
- Safe modification: Validate `col` with `_IDENTIFIER_RE` (or quote identifiers per dialect) before building the ALTER statement.
- Test coverage: `tests/test_migrations.py:111-153` covers happy-path add/drop/change only.

## Scaling Limits

**Connection pool does not shrink and has no background reaper:**
- Current capacity: `min_size=2`, `max_size=10` by default (`encino_orm/pool.py:48`); `min_size` connections stay open for the process lifetime.
- Limit: Idle connections above `min_size` are only closed lazily during `acquire()` (`encino_orm/pool.py:103-109,140-146`). Bursts pin up to `max_size` connections indefinitely.
- Scaling path: Add an idle-reaper task or close excess connections on `release()` when the queue already holds enough idle connections.

**No reconnect for direct (non-pool) connections:**
- Current capacity: Direct `Db` instances hold one connection; `is_alive()` exists but nothing calls it automatically.
- Limit: A dropped connection surfaces as an error on the next query; callers must reconnect manually.
- Scaling path: Add a health check/reconnect in `Db.retry` or a `with_reconnect` wrapper; document that `PoolDb` is required for resilience.

## Dependencies at Risk

**`aiomysql` pinned below 0.3.2:**
- Risk: `aiomysql>=0.2,<0.3.2` (`pyproject.toml:16`) blocks upstream fixes and is a slow-moving project.
- Impact: MySQL/MariaDB driver bugs cannot be picked up without editing the constraint.
- Migration plan: Track aiomysql releases, widen the cap after CI passes, or evaluate `asyncmy` as an alternative driver behind the same `Db` interface.

**Tight `pydantic>=2.13.4` lower bound:**
- Risk: Forces a very recent pydantic; combined with `Annotated` subclassing workarounds in `encino_orm/model/constraint.py` and `encino_orm/model/model.py:444` (Python 3.13 fix in 0.2.6), pydantic upgrades are likely to break constraint construction.
- Impact: Users on older-but-supported pydantic cannot install; pydantic majors require re-validation.
- Migration plan: Pin a tested range (e.g., `>=2.13,<3`) and add a CI matrix entry for the minimum supported pydantic.

**`PyJWT>=2.8,<2.13` upper cap and unpinned optional extras:**
- Risk: `PyJWT` capped (`pyproject.toml:22`); `asyncpg`, `aiosqlite`, `fastapi`, `strawberry-graphql`, `redis`, `oracledb`, `aioodbc`, `pyodbc` have no upper bounds.
- Impact: Unbounded optional deps can introduce breaking changes on a fresh `uv sync`; the JWT cap blocks security fixes.
- Migration plan: Add tested upper bounds for optional extras and run a scheduled dependency-update job.

**No dependency/security scanning in CI:**
- Risk: No `pip-audit`, Dependabot, or `uv lock --check` step.
- Impact: Vulnerable or outdated pinned deps go unnoticed.
- Migration plan: Add Dependabot config and a `pip-audit` CI step.

## Missing Critical Features

**Automatic cache invalidation:**
- Problem: No write-through/write-invalidate path exists for `CachedModel`.
- Files: `encino_orm/model/cached.py`, `encino_orm/model/cache_backend.py`
- Blocks: Safe use of caching in production (stale reads).

**Coverage and static-analysis gates:**
- Problem: CI runs only `pytest -q`; no lint, type, or coverage gate.
- Files: `.github/workflows/ci.yml:67-79`
- Blocks: Enforcing code quality and preventing untested regressions.

**Multi-DB integration coverage in CI:**
- Problem: CI starts only MySQL and PostgreSQL services (`ci.yml:25-52`); SQL Server, Oracle, MariaDB, and Redis are unavailable, so those suites skip.
- Files: `.github/workflows/ci.yml:25-52`, `tests/test_mssql.py:124,135`, `tests/test_oracle.py:103`, `tests/test_mariadb.py:38`, `tests/test_redis_cache.py:28,35`
- Blocks: Catching dialect-specific regressions (like the `COUNT(*)` bug) before release.

## Test Coverage Gaps

**`count()`/`paginate()`/`list_tables()` on non-SQLite engines:**
- What's not tested: No integration test calls `Model.count()`, `Model.paginate()`, `QueryBuilder.count()`, or `Db.list_tables()` against PostgreSQL/MySQL/MSSQL/Oracle (grep of `tests/test_postgresql.py`, `test_mysql.py`, `test_mssql.py`, `test_oracle.py`, `test_mariadb.py` finds no such calls).
- Files: `encino_orm/model/model.py:790-792`, `encino_orm/model/query_builder.py:240-242`, `encino_orm/base.py:151`
- Risk: The `COUNT(*)` key mismatch ships undetected; any change to count/pagination is unverified cross-engine.
- Priority: High

**Pool concurrency and race conditions:**
- What's not tested: Concurrent `acquire()` exceeding `max_size`, shared `_last_id` under parallel inserts, release after connection close, `close()` with checked-out connections.
- Files: `encino_orm/pool.py:111-160`
- Risk: Silent pool over-subscription and wrong `last_id` values in production.
- Priority: High

**Cache invalidation on writes:**
- What's not tested: `CachedModel` behavior after `update`/`delete` (only load/populate/hit are covered).
- Files: `encino_orm/model/cached.py`, `tests/test_cached_model.py:26-59`
- Risk: Stale reads ship as "working" behavior.
- Priority: High

**Migration rollback bookkeeping:**
- What's not tested: Re-applying a migration after rollback (the existing test only asserts the `down` SQL ran).
- Files: `tests/test_migrations.py:50-61`, `encino_orm/migration.py:25-29`
- Risk: Rollback path is effectively one-way and broken silently.
- Priority: Medium

**REST `register_crud` generated handlers:**
- What's not tested: Composite-PK path handlers, `PUT` field filtering, soft-delete vs `physical` delete via generated routes. Only list/pagination limits and single-PK routes appear covered (`tests/test_crud.py`, `tests/test_pagination_limits.py`, `tests/test_pk.py`).
- Files: `encino_orm/http/routes.py:25-111`
- Risk: `exec`-generated handlers fail only in production for composite keys.
- Priority: Medium

**`sync_schema` destructive paths:**
- What's not tested: `drop_missing=True` against real PostgreSQL/MySQL, and `alter_types=True` (only the SQLite `NotImplementedError` is asserted).
- Files: `encino_orm/model/model.py:855-908`, `tests/test_migrations.py:136-153`
- Risk: Schema mutations against live databases are unverified.
- Priority: Medium

**Security guard dependencies end-to-end:**
- What's not tested: `get_current_user`/`require` against a live FastAPI app with valid/expired/malformed tokens and anonymous access.
- Files: `encino_orm/security/guard.py:34-71`, `tests/test_security.py`
- Risk: Authorization wiring regressions go unnoticed.
- Priority: Medium

---

*Concerns audit: 2026-09-17*
