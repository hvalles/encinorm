<!-- refreshed: 2026-09-17 -->
# Architecture

**Analysis Date:** 2026-09-17

## System Overview

`encino_orm` is an async, multi-engine ORM. A single abstract `Db` interface is
implemented by six driver adapters (SQLite, MySQL, MariaDB, PostgreSQL, SQL
Server, Oracle). On top of the driver layer sits an optional pydantic-based ORM
layer (`Model`), and further optional product layers (REST, GraphQL, RBAC/JWT,
introspection/codegen) that are imported lazily so the core never hard-depends
on FastAPI, Strawberry, PyJWT or Redis.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                     Optional product layers (lazy imports)                │
├────────────────────┬───────────────────┬───────────────┬─────────────────┤
│  HTTP / REST        │  GraphQL          │  Security     │  Introspection  │
│  `encino_orm/http`  │ `encino_orm/      │ `encino_orm/  │ `encino_orm/    │
│  FastAPI            │  graphql`         │  security`    │  introspection` │
│                     │  Strawberry       │ FastAPI+PyJWT │ codegen         │
└─────────┬──────────┴─────────┬─────────┴───────┬───────┴────────┬────────┘
          │                    │                 │                │
          ▼                    ▼                 ▼                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        ORM layer  `encino_orm/model/`                     │
│  Model · Filter · QueryBuilder · Records · Column/Constraint/domain types │
│  references (1:1, 1:N) · scope · hooks · CachedModel · Index              │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ uses implicit connection resolution
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                Connection & context  `pool.py` · `context.py`             │
│  PoolDb · create_db · session · set_default_db · bind · resolve_db        │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│           Core abstractions  `base.py` · `query.py` · `engine.py`         │
│  Db (ABC) · Query · Engine · SqlFunctions · Migration · QueryTracer       │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ implemented by
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│     Driver adapters (native placeholders / DDL / last_id per engine)      │
│  `sqlite.py` `mysql.py` `mariadb.py` `postgresql.py` `mssql.py` `oracle.py`│
└──────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| `Db` | Abstract async DB interface: lifecycle, transactions, DML builders, DQL, migrations, introspection hooks, deadlock retry | `encino_orm/base.py` |
| `Query` | SQL + params container; rewrites `{n}` placeholders to `%(parameter_000n)s`; reusable via `rebind` | `encino_orm/query.py` |
| `Engine` | Enum of supported engines + `engine_of()`/`is_*()` helpers | `encino_orm/engine.py` |
| `SqlFunctions` | Portable SQL fragment builders (`db.fn.now()`, `date_add`, `geo_distance`, …) | `encino_orm/sql.py` |
| `SqliteDb` | SQLite adapter over `aiosqlite` (`?` placeholders) | `encino_orm/sqlite.py` |
| `MysqlDb` | MySQL adapter over `aiomysql` (`%s` placeholders) | `encino_orm/mysql.py` |
| `MariadbDb` | MySQL protocol drop-in; adjusts `LONGTEXT`→`json` introspection | `encino_orm/mariadb.py` |
| `PostgresDb` | PostgreSQL adapter over `asyncpg` (`$n` placeholders) | `encino_orm/postgresql.py` |
| `MssqlDb` | SQL Server adapter over `aioodbc`/`pyodbc` | `encino_orm/mssql.py` |
| `OracleDb` | Oracle adapter over `oracledb` thin mode | `encino_orm/oracle.py` |
| `PoolDb` | Connection pool with per-task transaction affinity via `contextvar` | `encino_orm/pool.py` |
| `session` | Async context manager binding a pooled connection ambiently | `encino_orm/pool.py` |
| `resolve_db` | Implicit connection resolution chain | `encino_orm/context.py` |
| `Model` | Declarative pydantic model with CRUD, relations, hooks, schema DDL | `encino_orm/model/model.py` |
| `Filter` | Composable, immutable WHERE-condition tree → SQL fragment | `encino_orm/model/filter.py` |
| `QueryBuilder` | Join/group/aggregate/subquery builder over models | `encino_orm/model/query_builder.py` |
| `Records` | Paginated result DTO (`rows`, `total`, `limit`, `page`) | `encino_orm/model/records.py` |
| `types` / `domain` / `constraint` | Logical datatype → per-engine DDL; reusable type presets | `encino_orm/model/types.py`, `domain.py`, `constraint.py` |
| `CachedModel` | `Model` whose `load()` persists through a `CacheBackend` | `encino_orm/model/cached.py` |
| `Migration` | Versioned schema migrations + directory loader | `encino_orm/migration.py` |
| `copy_database` | Cross-engine table/database data copy with type translation | `encino_orm/transfer.py` |
| `QueryTracer`/`OtelQueryTracer` | Query timing/metrics and OpenTelemetry spans | `encino_orm/observability.py` |
| `create_crud` | Mounts typed REST CRUD + introspection router | `encino_orm/http/__init__.py`, `routes.py`, `registry.py` |
| `build_schema` | Builds a Strawberry schema with queries/mutations per model | `encino_orm/graphql/schema.py` |
| RBAC + JWT | Tri-state permissions, FastAPI guards, token emit/verify | `encino_orm/security/` |
| Codegen | Introspect DB tables → generate `Model` source files | `encino_orm/introspection/` |
| CLI | `encino_orm generate models` and `encino_orm copy` | `encino_orm/cli.py` |

## Pattern Overview

**Overall:** Layered async ORM with pluggable driver adapters and optional
lazily-imported product layers.

**Key Characteristics:**
- Single abstract interface (`Db`) + concrete adapter per engine; behavior that
  differs by dialect (placeholders, DDL types, `last_id`, upsert syntax) is
  localized in the adapter or in `model/types.py` / `model/model.py` branches.
- SQL injection defense is systemic: every execution path goes through `Query`,
  and identifiers are validated against `_IDENTIFIER_RE` before interpolation
  (`base.py:60`, `model/model.py:29`, `model/query_builder.py:10`,
  `model/filter.py:5`, `transfer.py:15`).
- Optional integrations are never imported at package import time; they are
  imported inside functions (`encino_orm/http/__init__.py:20`,
  `encino_orm/security/guard.py:36`, `encino_orm/cli.py:87`).
- Per-request/per-task state is carried in `contextvars`, not globals
  (`pool.py:29`, `context.py:23`, `model/scope.py:11`, `observability.py:8`).

## Layers

**Core abstractions:**
- Purpose: Define the engine-agnostic contracts and value objects.
- Location: `encino_orm/base.py`, `encino_orm/query.py`, `encino_orm/engine.py`,
  `encino_orm/sql.py`, `encino_orm/exceptions.py`
- Contains: `Db` ABC, `Query`, `Engine`, `SqlFunctions`, `Weekday`, exception hierarchy.
- Depends on: stdlib + `model.records` (lazy, in `list_tables`/`paginate`).
- Used by: every other layer.

**Driver adapters:**
- Purpose: Translate the abstract contract to a concrete DB driver.
- Location: `encino_orm/sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`,
  `mssql.py`, `oracle.py`, helper `_rows.py`
- Contains: `connect/close/is_alive/in_transaction/commit/rollback/save_point`,
  `insert/delete/update` builders, `execute/fetch_*`, `last_id`, `migrate*`,
  `_tables_sql`, `columns_of`, `is_lock_error`, `_prepare` (placeholder rewrite).
- Depends on: driver libs (`aiosqlite`, `aiomysql`, `asyncpg`, `aioodbc`, `oracledb`).
- Used by: `pool.py`, `transfer.py`, `introspection/`, `cli.py`.

**Connection & context:**
- Purpose: Manage pooling and implicit connection resolution.
- Location: `encino_orm/pool.py`, `encino_orm/context.py`
- Contains: `PoolDb`, `create_db`, `session`, `set_default_db`, `get_default_db`,
  `bind`, `resolve_db`, `_current_connection` contextvar.
- Depends on: all driver adapters, `base.py`, `exceptions.py`.
- Used by: `model/model.py` (via `resolve_db`), `http/`, `graphql/`.

**ORM layer:**
- Purpose: Declarative models, queries, relations, schema.
- Location: `encino_orm/model/`
- Contains: `Model`, `Filter`, `QueryBuilder`, `Records`, `Column`, `Constraint`,
  `Index`, `domain` presets, `references`, `scope`, `hooks`, `cached`,
  `cache_backend`, `types`, `exceptions`.
- Depends on: `base.py`, `context.py`, `engine.py`, `query.py`, pydantic.
- Used by: optional product layers, `security/models.py`, `transfer.py`, `cli.py`.

**Infrastructure services:**
- Purpose: Migrations, data transfer, observability.
- Location: `encino_orm/migration.py`, `encino_orm/transfer.py`, `encino_orm/observability.py`
- Depends on: `Db`, `Query`, `introspection`.
- Used by: application code, `cli.py`.

**Optional product layers:**
- Purpose: Expose ORM models over HTTP/GraphQL, enforce RBAC/JWT, reverse-engineer models.
- Location: `encino_orm/http/`, `encino_orm/graphql/`, `encino_orm/security/`,
  `encino_orm/introspection/`
- Depends on: `model/`, `pool.py`, optional third-party libs.
- Used by: end-user applications.

## Data Flow

### Primary Request Path — `Model.insert()`

1. `Model.insert()` validates fields with pydantic `TypeAdapter` and stamps
   `created_at`/`updated_at` (`model/model.py:465`).
2. Fields are serialized to engine-neutral values (`_serialize`) and mapped to
   physical column names via `_column_map()` (`model/model.py:34`, `:226`, `:476`).
3. `Db.insert(table, data, ...)` builds a `Query` (no I/O) — e.g.
   `sqlite.py:127`, `postgresql.py` `insert` builder.
4. `_transactional("insert", do_insert)` runs lifecycle hooks, opens a
   transaction, executes with deadlock `retry()`, commits, then fires
   `after_commit` (`model/model.py:415`).
5. `Db.execute(qry)` calls `_prepare(qry)` to rewrite `%(parameter_000n)s` to the
   driver's native placeholder, then executes (`sqlite.py:98`, `:166`;
   `postgresql.py:22`).
6. `last_id()` resolves the new surrogate key; the instance is marked
   `__exists=True` and `__dirties` is cleared (`model/model.py:485`).

### Implicit Connection Resolution

`Model._get_db()` calls `resolve_db()`, which resolves in this order
(`context.py:47`):

1. explicit `db` passed to the constructor/method (`model/model.py:195`)
2. active pool transaction — `_current_connection` contextvar (`pool.py:29`)
3. ambient `bind()` / `session()` — `_ambient_db` contextvar (`context.py:23`)
4. process default — `set_default_db()` global (`context.py:20`)
5. otherwise raises `ConnectionError`.

### Query Construction Path — `Filter` / `QueryBuilder`

1. `Filter.eq("age", 18) & Filter.ge("monto", 0)` builds an immutable tree
   (`model/filter.py:32`).
2. `filter.map_fields(_column_map())` maps logical fields to physical columns
   (`model/filter.py:138`).
3. `filter.to_sql()` emits a fragment with `{n}` placeholders + params
   (`model/filter.py:154`).
4. `QueryBuilder` assembles `JOIN`/`WHERE`/`GROUP BY`/`HAVING`/`ORDER BY`,
   shifting placeholder indices when combining fragments
   (`model/query_builder.py:13`, `:168`).
5. Execution goes through `Db.fetch_all`/`fetch_one` (`model/query_builder.py:222`).

### Optional Layer Flow

- REST: `create_crud(pool, models)` builds a FastAPI `APIRouter`, registers
  routes per model and `/models` introspection
  (`http/__init__.py:13`, `http/routes.py:77`). Handlers are synthesized with
  `exec` from `model._primary_key` (`http/routes.py:25`).
- GraphQL: `build_schema(models)` builds Strawberry object/input/filter types and
  query/mutation fields; resolvers get the connection from
  `context_value={"db": db}` and use per-request `DataLoader` for relations to
  avoid N+1 (`graphql/schema.py:162`, `graphql/resolvers.py:26`).
- Security: `get_current_user`/`require` are FastAPI dependencies that decode a
  Bearer JWT and load a tri-state `PermissionSet` (`security/guard.py:34`, `:56`,
  `security/permissions.py:15`).
- Codegen: `generate_model(db, table)` introspects columns and writes a `Model`
  source file (`introspection/codegen.py:60`), driven by the CLI
  (`cli.py:86`).

**State Management:**
- Transaction affinity: `_current_connection` contextvar (`pool.py:29`).
- Ambient connection: `_ambient_db` contextvar via `bind`/`session`
  (`context.py:23`).
- Row-level multi-tenancy: `_scope_var` contextvar via `scope()`
  (`model/scope.py:11`); combined into every `search`/`count`/`paginate`/`load`
  through `_effective_filter` (`model/model.py:734`).
- Trace correlation: `_trace_id_var` contextvar (`observability.py:8`).
- Process default connection: module global `_default_db` (`context.py:20`).

## Key Abstractions

**`Db` (ABC):**
- Purpose: Uniform async contract across engines; owns retry/transaction template.
- Examples: `encino_orm/base.py:15`, `encino_orm/sqlite.py:32`,
  `encino_orm/postgresql.py:42`, `encino_orm/pool.py:40`
- Pattern: Template Method — `transaction()` and `retry()` are concrete in the
  base; drivers implement the primitives; `PoolDb` delegates.

**`Query`:**
- Purpose: Safe, reusable SQL+params envelope.
- Examples: `encino_orm/query.py:1`, constructed throughout
  `model/model.py` and all adapters.
- Pattern: Value object with placeholder re-binding (`format`/`rebind`); adapters
  translate to native placeholders in `_prepare`.

**`Model` (pydantic `BaseModel`):**
- Purpose: Declarative table mapping with CRUD, relations, hooks, DDL.
- Examples: `encino_orm/model/model.py:132`, `encino_orm/security/models.py:16`
- Pattern: Active Record + class-level metadata (`_table`, `_primary_key`,
  `_references_def`, `_has_many_def`, `_indexes`) collected in
  `__init_subclass__`; private state stored via `object.__setattr__` helpers
  (`model/model.py:79`).

**`Filter`:**
- Purpose: Immutable, composable predicate tree.
- Examples: `encino_orm/model/filter.py:32`, `encino_orm/http/parsing.py:35`
- Pattern: Composite — `&`/`|`/`~` build nested nodes; `to_sql` emits
  parameterized fragments; `digest()` gives stable cache keys.

**`CacheBackend` (Protocol):**
- Purpose: Pluggable cache for `CachedModel`.
- Examples: `encino_orm/model/cache_backend.py:5`, `MemoryCacheBackend` (`:11`),
  `RedisCacheBackend` (`:35`)
- Pattern: Structural typing (Protocol) + lazy optional import of `redis`.

## Entry Points

**Public API:**
- Location: `encino_orm/__init__.py:1`
- Triggers: `import encino_orm`
- Responsibilities: Re-export `Db`, `Query`, `Engine`, all adapters, `PoolDb`,
  `create_db`, `session`, context helpers, migrations, observability, exceptions.

**Model package API:**
- Location: `encino_orm/model/__init__.py:1`
- Triggers: `from encino_orm.model import Model, Filter, ...`
- Responsibilities: Export ORM surface, domain type presets, hooks, exceptions.

**CLI:**
- Location: `encino_orm/cli.py:123`, registered as console script
  `encino_orm = "encino_orm.cli:main"` (`pyproject.toml:39`)
- Triggers: `encino_orm generate models <engine> [tables...]`,
  `encino_orm copy <src-engine> <dst-engine> [tables...]`
- Responsibilities: Async wrapper around `introspection.generate_model` and
  `transfer.copy_database`.

**User model subclassing:**
- Location: any `class MyModel(Model): _table = "..."` (e.g.
  `tests/test_model.py:10`, `encino_orm/security/models.py:16`)
- Triggers: class definition (`__init_subclass__` hook collection)
- Responsibilities: Declares table mapping, constraints, relations, indexes.

**FastAPI router factory:**
- Location: `encino_orm/http/__init__.py:13`
- Triggers: `create_crud(pool, models)`
- Responsibilities: Builds and returns an `APIRouter` with CRUD + introspection.

**GraphQL schema factory:**
- Location: `encino_orm/graphql/schema.py:162`
- Triggers: `build_schema(models)`
- Responsibilities: Returns a `strawberry.Schema`.

## Architectural Constraints

- **Threading / concurrency:** Single-threaded `asyncio`; per-task state uses
  `contextvars` (`pool.py:29`, `context.py:23`, `model/scope.py:11`,
  `observability.py:8`). `tests/conftest.py:8` sets the Windows selector event
  loop policy.
- **Global state:** module-level `_default_db` (`context.py:20`) and security
  config globals `SECRET` / `GET_DB` (`security/guard.py:14-15`) are
  process-wide mutable singletons. Class-level caches `_FIELD_ADAPTERS` and
  `_COLUMN_MAPS` are `weakref.WeakKeyDictionary` keyed by model class
  (`model/model.py:30-31`).
- **Optional dependencies:** core imports must never pull FastAPI, Strawberry,
  PyJWT, redis, or the MSSQL/Oracle drivers. Violating this breaks `import
  encino_orm` in a minimal install. Lazy-import pattern is used in
  `base.py:25`, `context.py:49`, `http/__init__.py:20`, `security/guard.py:36`,
  `security/jwt.py:31`, `model/cache_backend.py:44`, `cli.py:87`.
- **Placeholder contract:** every adapter receives `Query.query[0]` with
  `%(name)s` placeholders and rewrites via a module-level `_PLACEHOLDER_RE` +
  `_to_<engine>()` function (`sqlite.py:22`, `mysql.py:33`,
  `postgresql.py:22`, `mssql.py:20`, `oracle.py:20`).
- **Identifier validation:** dynamic table/column/identifier interpolation must
  pass `_IDENTIFIER_RE` checks (`base.py:60`, `model/model.py:29`,
  `query_builder.py:10`, `filter.py:5`, `transfer.py:15`, `sql.py:8`).
- **Circular imports:** intentionally broken with function-local imports
  (`context.py:49`, `base.py:144`, `model/model.py:797`, `model/cached.py:7`).
- **Upsert dialect branching:** `Model.upsert` branches to
  `ON DUPLICATE KEY` (MySQL), `MERGE` (MSSQL/Oracle), or
  `ON CONFLICT` (others) (`model/model.py:596-624`).

## Anti-Patterns

### Direct SQL string interpolation

**What happens:** Building SQL with f-strings and user-controlled values outside
`Query`.
**Why it's wrong:** Defeats the parameterization guarantee and the identifier
validation that every core path relies on (`query.py`, `base.py:60`).
**Do this instead:** Build a `Query(sql_with_{n}_placeholders, params)` and let
the adapter translate placeholders (`sqlite.py:98`).

### Eager import of optional integrations

**What happens:** `import fastapi` / `import strawberry` / `import jwt` at module
top level in core files.
**Why it's wrong:** Breaks the core install (no extras) and the documented
lazy-import contract.
**Do this instead:** Import inside the function that needs it, matching
`http/__init__.py:20`, `security/guard.py:36`, `security/jwt.py:31`.

### Adding engine branches outside the adapter

**What happens:** Scattering `if engine == "..."` logic across model code beyond
the necessary DDL/upsert cases.
**Why it's wrong:** The design localizes dialect differences to adapters and
`model/types.py`; spreading branches makes new-engine support costly (see
`docs/engines.md`).
**Do this instead:** Put dialect behavior in the adapter (`_prepare`,
`columns_of`, `last_id`) or in the `DDL_MAP` in `model/types.py:41`.

### Mutable default / shared class state

**What happens:** Mutating class-level containers such as `_indexes` or
`_references_def` in place.
**Why it's wrong:** Class attributes are shared across all instances and
subclasses. The codebase deliberately copies (`add_index` uses
`cls._indexes = list(cls._indexes) + [idx]`, `model/model.py:162`).
**Do this instead:** Rebind to a new collection as `add_index` does.

## Error Handling

**Strategy:** A single exception root (`EncinoOrmError`) with domain subclasses;
adapters translate driver errors to `ConnectionError`/`QueryError`; model
operations raise `ValidationError`/`FailOnUpdate`/`RelationshipError`; the HTTP
layer maps these to status codes.

**Patterns:**
- Exception hierarchy: `exceptions.py:1` (core) and `model/exceptions.py:1`
  (ORM) both root at `EncinoOrmError`; `security/exceptions.py:6` likewise.
- Transaction rollback on failure: `Db.transaction()` rolls back and re-raises
  (`base.py:41`); `_transactional` fires `after_transaction_fail` hooks
  (`model/model.py:424`).
- Deadlock retry: `Db.retry()` re-runs on `is_lock_error()` with jittered waits
  (`base.py:78`); each adapter implements `is_lock_error` (e.g.
  `sqlite.py:43`, `mysql.py:55`, `postgresql.py:53`).
- HTTP mapping: `install_error_handlers` maps `ValidationError`→422,
  `FailOnUpdate`/`QueryError`→400 (`http/errors.py:7`).
- Auth errors: `AuthenticationError`/`AuthorizationError` mapped to 401/403 by
  guards (`security/guard.py:48`, `:68`).

## Cross-Cutting Concerns

**Logging:** stdlib `logging` under the `"encino_orm"` logger (`base.py:10`);
each adapter logs SQL with timing and `trace_id` at DEBUG (`sqlite.py:17`,
`mysql.py:19`, `postgresql.py:17`, `mssql.py:15`, `oracle.py:15`). `QueryTracer`
and `OtelQueryTracer` provide opt-in structured metrics/spans
(`observability.py:52`, `:103`).

**Validation:** pydantic v2 is the single source of validation. Models are
`BaseModel` subclasses (`model/model.py:132`); field constraints come from
`Annotated[...]` metadata (`model/constraint.py:78`); explicit per-field checks
run through cached `TypeAdapter`s in `Model.validate()` (`model/model.py:433`).
`Model.cursor()` constructs instances without validation for read/schema ops
(`model/model.py:170`).

**Authentication / Authorization:** Optional `security` package. JWT is a thin
PyJWT wrapper with an algorithm allowlist and access/refresh type checks
(`security/jwt.py:17`, `:59`). RBAC is tri-state (first explicit value wins,
deny by default) resolved once per request into `PermissionSet`
(`security/permissions.py:22`, `:33`). FastAPI dependencies are built by
`get_current_user` and `require` (`security/guard.py:34`, `:56`).

**Connection lifecycle:** `create_db(engine, **kwargs)` is the async factory
(`pool.py:269`); `session(db)` is the request-scoped async context manager that
acquires/releases pooled connections and binds them ambiently (`pool.py:278`).

**Observability:** `trace_id(value)` context manager propagates a correlation id
into all adapter logs (`observability.py:12`, `:21`).

---

*Architecture analysis: 2026-09-17*
