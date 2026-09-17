# Codebase Structure

**Analysis Date:** 2026-09-17

## Directory Layout

```
db/
├── encino_orm/            # Library source (the installed package)
│   ├── model/             # ORM layer: Model, Filter, QueryBuilder, types, relations
│   ├── graphql/           # Optional Strawberry GraphQL layer
│   ├── http/              # Optional FastAPI REST CRUD layer
│   ├── security/          # Optional RBAC + JWT layer
│   └── introspection/     # DB introspection + model codegen
├── tests/                 # pytest suite (unit + integration per engine)
├── docs/                  # MkDocs user/API/design documentation
│   ├── design/            # Internal architecture design documents
│   └── reference/         # API reference pages (mkdocstrings)
├── prompts/               # Development prompt history and analysis notes
├── dist/                  # Built wheels/sdists (generated, committed artifacts)
├── site/                  # Built MkDocs HTML output (generated, committed)
├── .github/workflows/     # CI, docs, release, publish workflows
├── .planning/codebase/    # GSD codebase map documents (this directory)
├── pyproject.toml         # Packaging, deps, extras, pytest config, CLI script
├── mkdocs.yml             # Documentation site configuration
├── docker-compose.yml     # Local test databases + Redis
├── uv.lock                # uv lockfile
├── README.md              # Project overview and quick start
├── CHANGELOG.md           # Release history
└── LICENSE                # MIT
```

## Directory Purposes

**`encino_orm/`:**
- Purpose: The installable library (`packages = ["encino_orm"]`,
  `pyproject.toml:5`).
- Contains: Core abstractions, driver adapters, connection management, ORM layer,
  and optional product layers.
- Key files: `__init__.py` (public API), `base.py` (Db ABC), `query.py`,
  `engine.py`, `pool.py`, `context.py`, `sql.py`, `migration.py`,
  `transfer.py`, `observability.py`, `cli.py`.

**`encino_orm/model/`:**
- Purpose: ORM layer — declarative models, filters, query builder, schema DDL.
- Contains: `model.py` (1083 lines, the largest module), `filter.py`,
  `query_builder.py`, `records.py`, `references.py`, `column.py`,
  `constraint.py`, `domain.py`, `types.py`, `index.py`, `scope.py`, `hooks.py`,
  `cached.py`, `cache_backend.py`, `exceptions.py`, `__init__.py`.
- Key files: `model.py` (CRUD/relations/schema), `types.py` (DDL_MAP),
  `filter.py` (predicate tree).

**`encino_orm/graphql/`:**
- Purpose: Optional Strawberry GraphQL layer generated from models.
- Contains: `schema.py` (schema factory), `types.py` (ObjectType/Input),
  `filters.py` (filter input types), `resolvers.py` (session/DataLoader
  helpers), `scalars.py` (datatype→GraphQL mapping), `__init__.py`.
- Key files: `schema.py`, `resolvers.py`.

**`encino_orm/http/`:**
- Purpose: Optional FastAPI REST CRUD layer generated from models.
- Contains: `routes.py` (CRUD route generator), `registry.py` (model registry +
  introspection endpoints), `parsing.py` (query-string filter/sort parsing),
  `errors.py` (exception→HTTP mapping), `__init__.py` (`create_crud`).
- Key files: `routes.py`, `registry.py`.

**`encino_orm/security/`:**
- Purpose: Optional RBAC + JWT security layer.
- Contains: `models.py` (`Rol`, `Roldet`, `RolUsuario`), `permissions.py`
  (`PermissionSet`), `guard.py` (FastAPI dependencies), `jwt.py` (PyJWT
  wrapper), `exceptions.py`, `__init__.py`.
- Key files: `permissions.py`, `guard.py`, `models.py`.

**`encino_orm/introspection/`:**
- Purpose: Database-first reverse engineering (tables → models).
- Contains: `tables.py` (`list_tables`/`columns_of` delegation), `types.py`
  (`ColumnSpec`, raw-type normalization, preset resolution), `codegen.py`
  (source file generation), `__init__.py`.
- Key files: `codegen.py`, `types.py`.

**`tests/`:**
- Purpose: pytest suite; SQLite always runs, other engines skip if unavailable.
- Contains: 46 test modules, one per feature/engine area, plus `conftest.py`
  and `__init__.py`.
- Key files: `conftest.py` (fixtures `db`, `connected_db`), `test_model.py`,
  `test_sqlite.py`, `test_postgresql.py`, `test_mysql.py`, `test_graphql.py`,
  `test_security.py`, `test_pool.py`, `test_transfer.py`, `test_from_db.py`,
  `test_crud.py`.

**`docs/`:**
- Purpose: MkDocs documentation source (`mkdocs.yml` nav).
- Contains: User guides (`getting-started.md`, `guide.md`,
  `integrations.md`, `engines.md`, `docker.md`, `credits.md`),
  `design/` (12 internal design docs `0-design.md` … `a-xpress.md`,
  `has_many.md`), `reference/` (10 API reference pages under
  `docs/reference/`).
- Key files: `docs/design/0-design.md` (core architecture), `docs/engines.md`
  (how to add an engine), `docs/reference/model.md`.

**`prompts/`:**
- Purpose: Chronological development prompts and readiness analyses
  (not part of the shipped package or docs site).
- Contains: Numbered prompt files `0.md`–`27.md`, `analisys-01.md` …
  `analisys-14bp.md`, `publish.md`.
- Key files: `prompts/analisys-07.md` (referenced from `README.md:16` as the
  readiness status).

**`dist/`:**
- Purpose: Build artifacts (wheels + sdists). Generated, committed.
- Contains: `encino_orm-0.2.1`, `0.2.4`, `0.2.5` `.whl`/`.tar.gz`.
- Note: Versions lag `pyproject.toml` (`0.2.6`); regenerated on release.

**`site/`:**
- Purpose: Rendered MkDocs HTML. Generated, committed.
- Contains: `index.html`, `assets/`, and one directory per docs page
  (`guide/`, `design/`, `reference/`, `getting-started/`, …).
- Note: Do not hand-edit; regenerate with MkDocs.

**`.github/workflows/`:**
- Purpose: Automation.
- Contains: `ci.yml` (matrix Python 3.10–3.13, MySQL+Postgres services),
  `docs.yml` (MkDocs build/deploy), `release.yml`, `publish-testpypi.yml`.

**`.planning/codebase/`:**
- Purpose: GSD codebase map consumed by planning/execution commands.
- Contains: `STACK.md`, `INTEGRATIONS.md`, `ARCHITECTURE.md`, `STRUCTURE.md`
  (and `CONVENTIONS.md`, `TESTING.md`, `CONCERNS.md` when those focuses run).

## Key File Locations

**Entry Points:**
- `encino_orm/__init__.py`: Public package API and re-exports.
- `encino_orm/model/__init__.py`: ORM public surface.
- `encino_orm/cli.py`: CLI `main()` (console script target).
- `encino_orm/pool.py`: `create_db()` async factory and `session()` context
  manager.
- `encino_orm/http/__init__.py`: `create_crud()` FastAPI router factory.
- `encino_orm/graphql/schema.py`: `build_schema()` Strawberry schema factory.

**Configuration:**
- `pyproject.toml`: Packaging (`hatchling`), dependencies, optional extras
  (`http`, `security`, `graphql`, `cache`, `mssql`, `oracle`, `all-db`),
  console script, pytest config (`asyncio_mode = "auto"`, `testpaths = ["tests"]`).
- `mkdocs.yml`: Docs site nav and mkdocstrings options.
- `docker-compose.yml`: Local MySQL/MariaDB/Postgres/MSSQL/Oracle/Redis for
  integration tests.
- `tests/conftest.py`: Shared fixtures and Windows event-loop policy.

**Core Logic:**
- `encino_orm/base.py`: `Db` ABC, retry/transaction template, raw pagination.
- `encino_orm/query.py`: `Query` value object and placeholder rewriting.
- `encino_orm/engine.py`: `Engine` enum + `engine_of`/`is_*` helpers.
- `encino_orm/sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`,
  `mssql.py`, `oracle.py`: driver adapters.
- `encino_orm/pool.py`, `encino_orm/context.py`: pooling and implicit
  connection resolution.
- `encino_orm/model/model.py`: `Model` — CRUD, relations, hooks, schema.
- `encino_orm/model/filter.py`, `model/query_builder.py`: query construction.
- `encino_orm/model/types.py`: logical datatype → per-engine `DDL_MAP`.
- `encino_orm/sql.py`: portable SQL function fragments (`db.fn.*`).

**Testing:**
- `tests/conftest.py`: fixtures.
- `tests/test_sqlite.py`, `tests/test_mysql.py`, `tests/test_postgresql.py`,
  `tests/test_mssql.py`, `tests/test_oracle.py`: engine adapters.
- `tests/test_model.py`, `tests/test_crud.py`, `tests/test_query_builder.py`,
  `tests/test_has_many.py`, `tests/test_references.py`: ORM behavior.
- `tests/test_graphql.py`, `tests/test_crud.py`, `tests/test_security.py`:
  optional layers.

**Documentation:**
- `docs/index.md`, `docs/getting-started.md`, `docs/guide.md`,
  `docs/integrations.md`, `docs/engines.md`.
- `docs/design/`: internal design rationale.
- `docs/reference/`: API reference.

## Naming Conventions

**Files:**
- Core modules: lowercase, no separators — `base.py`, `pool.py`, `sqlite.py`,
  `postgresql.py`, `observability.py`, `migration.py`.
- Adapter files match the engine name: `mysql.py`, `mariadb.py`, `mssql.py`,
  `oracle.py`.
- Test files: `test_<area>.py`, snake_case (`test_query_builder.py`,
  `test_scope_softdelete.py`, `test_d_recommendations.py`).
- Docs: kebab-case for guides (`getting-started.md`, `has_many.md`), numbered
  for design (`0-design.md`, `a-xpress.md`).

**Directories:**
- Lowercase single words: `model/`, `http/`, `graphql/`, `security/`,
  `introspection/`, `tests/`, `docs/`.
- No `src/` layout; the package lives at the repo root.

**Python symbols:**
- Classes: `PascalCase` (`Model`, `PoolDb`, `QueryBuilder`, `SqlFunctions`,
  `CachedModel`).
- Public functions/methods: `snake_case` (`create_db`, `fetch_all`,
  `build_schema`, `register_crud`).
- Private helpers: leading underscore (`_prepare`, `_to_postgres`,
  `_ensure_connected`, `_shift_placeholders`).
- Class-level metadata on models: leading underscore class vars (`_table`,
  `_primary_key`, `_fields_disabled`, `_references_def`, `_has_many_def`,
  `_indexes`).
- Domain type presets: `UPPER_SNAKE` (`STR_100`, `INT_POS`, `CURRENCY`,
  `DATETIME`, `JSON`).
- Exceptions: `PascalCase` ending in `Error` (`ConnectionError`, `QueryError`,
  `ValidationError`, `PoolExhaustedError`).
- Test classes: `Test<Feature>`; test functions `test_<behavior>`.

## Where to Add New Code

**New Feature (core ORM behavior):**
- Primary code: `encino_orm/model/model.py` for `Model` methods, or a new
  `encino_orm/model/<feature>.py` module exported from
  `encino_orm/model/__init__.py`.
- Tests: `tests/test_<feature>.py`; add engine-specific cases to the matching
  `tests/test_<engine>.py`.

**New Database Engine:**
- Implementation: create `encino_orm/<engine>.py` subclassing `Db` and
  implementing the abstract methods plus `_prepare`, `_tables_sql`,
  `columns_of`, `is_lock_error`, `last_id`.
- Registration: add to `_ENGINES` in `encino_orm/pool.py:17`, add an `Engine`
  member in `encino_orm/engine.py:6`, and add a `DDL_MAP` entry in
  `encino_orm/model/types.py:41`.
- Export: add the class to `encino_orm/__init__.py`.
- Tests: add `tests/test_<engine>.py`.
- Reference: follow `docs/engines.md`.

**New HTTP Endpoint / CRUD Variant:**
- Implementation: `encino_orm/http/routes.py` (per-model routes) or
  `encino_orm/http/registry.py` (introspection endpoints).
- Export: `encino_orm/http/__init__.py`.

**New GraphQL Field/Resolver:**
- Implementation: `encino_orm/graphql/schema.py` (queries/mutations) or
  `encino_orm/graphql/types.py` (object/input fields).
- Helpers: `encino_orm/graphql/resolvers.py`.

**New Security Rule / Operation:**
- Implementation: `encino_orm/security/permissions.py` (`OPS`,
  `PermissionSet`), `encino_orm/security/guard.py` (dependencies).
- Tests: `tests/test_security.py`.

**New Type / Constraint Preset:**
- Implementation: `encino_orm/model/domain.py` (preset), `encino_orm/model/types.py`
  (`DDL_MAP`), `encino_orm/model/constraint.py` (`make_constraint`).
- Introspection mapping: `encino_orm/introspection/types.py` (`_PRESET`).

**New Migration / Schema Helper:**
- Implementation: `encino_orm/migration.py`.
- Tests: `tests/test_migrations.py`.

**Utilities:**
- Shared helpers: `encino_orm/base.py` (generic) or a new small module at
  `encino_orm/<name>.py`. Row-tuple conversion helpers live in
  `encino_orm/_rows.py`.

**Documentation:**
- User/API docs: `docs/` and add a nav entry in `mkdocs.yml`.
- Internal design rationale: `docs/design/`.

## Special Directories

**`site/`:**
- Purpose: Rendered MkDocs output.
- Generated: Yes (`mkdocs build`).
- Committed: Yes.

**`dist/`:**
- Purpose: Build artifacts from `python -m build` / hatch.
- Generated: Yes.
- Committed: Yes (release snapshots; can lag `pyproject.toml` version).

**`.planning/codebase/`:**
- Purpose: GSD map documents.
- Generated: Yes (by `/gsd-map-codebase`).
- Committed: Yes.

**`prompts/`:**
- Purpose: Development history/analysis notes; not part of the package.
- Generated: No (hand-written).
- Committed: Yes.

**`__pycache__/`, `.pytest_cache/`, `.venv/`:**
- Purpose: Runtime/build caches and virtualenv.
- Generated: Yes.
- Committed: No (excluded via `.gitignore`).

---

*Structure analysis: 2026-09-17*
