---
phase: 02-dialect-seam-engine-parity
verified: 2026-09-18T05:09:52Z
status: gaps_found
score: 29/32 must-haves verified
overrides_applied: 0
re_verification: false
gaps:
  - truth: "No identifier reaches SQL interpolation inside the core without passing the single allowlist (phase goal clause: 'Identifier validation ... live in exactly one place inside the core')"
    status: failed
    reason: >-
      The allowlist is single-sourced (verified), but it is NOT a choke point. `QueryBuilder`'s public
      `alias=` constructor parameter and the `alias` argument of `join()`/`join_subquery()` are stored
      unvalidated and interpolated straight into `FROM`/`JOIN`. Reproduced on the current tree:
      `QueryBuilder(T, None, alias='mm WHERE 1=0 UNION SELECT nombre FROM usuarios --')._build_base()[0]`
      returns `'FROM t mm WHERE 1=0 UNION SELECT nombre FROM usuarios --'`. `all()` prepends `SELECT *`,
      so the executed statement is a valid single-statement UNION — a working SQL-injection primitive
      through a documented public parameter. Separately, `_build_column_map` validates `cls._table` and
      an explicit `Column(name=...)` override but never the *default* (pydantic field) name, so
      `to_ddl()` and `Model.insert_many()` interpolate unvalidated identifiers (reproduced with a
      dynamically created model whose field name is `'a; DROP TABLE x --'`). Both bypasses are
      pre-existing (introduced before this phase), but the phase's stated deliverable is a single
      validation choke point, so the goal clause does not hold as a functional statement.
    artifacts:
      - path: "encino_orm/model/query_builder.py"
        issue: "`:49` `self._alias = alias` (never validated); `:101` and `:112` store `join`/`join_subquery` aliases unvalidated; `:178`, `:184`, `:192` interpolate them into `FROM`/`JOIN`. `_safe_column` is applied to column expressions only."
      - path: "encino_orm/model/model.py"
        issue: "`:231` `col = name` — the default column name is never validated; only the explicit `Column(name=...)` override is (`:235`). Consumed by `to_ddl` (`model/types.py`) and `insert_many` (`:556`)."
    missing:
      - "Validate the alias in `QueryBuilder.__init__`, `join()` and `join_subquery()` (e.g. `check_identifier(alias, 'alias')`, or extend `_safe_column` to cover aliases)."
      - "Validate the default field name in `_build_column_map`: `col = check_identifier(name, 'nombre de columna')` so `to_ddl`/`insert_many` inherit the check."
      - "Regression tests mirroring `TestAdaptadoresRechazanAntesDelDriver` (`tests/test_dialect_builders.py:283-302`): assert `ValueError` for `QueryBuilder(Model, db, alias='x; DROP TABLE t --')`, for `join(Other, 'a b', on)`, and for a dynamically created model with a non-identifier field name."

  - truth: "The library returns correct results on all six engines (phase goal clause: '... demonstrably returns correct results on all six engines — not just SQLite')"
    status: failed
    reason: >-
      The scoped parity work (count/paginate/list_tables/sync_schema/last_id + the five QueryBuilder
      aggregates) is genuinely fixed and verified live on all six engines. However three engine-parity
      defects of exactly the class this phase exists to eliminate survive, none of them covered by the
      new per-engine tests (verified: `grep -n '\\.limit(|\\.first()|\\.exists()|upsert'` returns zero
      matches in all six `tests/test_<engine>.py`): (1) `QueryBuilder.all()/first()/exists()` still emit
      `LIMIT`, invalid on MSSQL/Oracle — the same bug the phase fixed in `Model.search`; (2)
      `Model.upsert` on MariaDB emits `ON CONFLICT` (unsupported), and MariaDB was promoted to a
      *required* CI engine by this same phase precisely to catch dialect drift; (3) PostgreSQL
      `Model.insert(replace=True)` with no explicit `conflict` targets `columns[0]`, which for an
      auto-PK model is `enabled`, not the PK — PostgreSQL rejects it. (2) and (3) are preserved
      deliberately for byte-identity and (2) is documented in code as a HALLAZGO, but (1) and (2) are
      absent from `deferred-items.md`, so the phase's own deferral log is incomplete.
    artifacts:
      - path: "encino_orm/model/query_builder.py"
        issue: "`:236` `sql += f\" LIMIT {self._limit_n} OFFSET {offset}\"`, `:242` `LIMIT 1`, `:287` `LIMIT 1` — invalid T-SQL / Oracle."
      - path: "encino_orm/dialects/strategies.py"
        issue: "`:57` `UPSERT_KIND['mariadb'] = 'on_conflict'` — MariaDB does not implement `ON CONFLICT` (it needs `ON DUPLICATE KEY UPDATE`). Documented as a finding in a code comment only."
      - path: "encino_orm/dialects/builders.py"
        issue: "`:89-91` `target = ... else (columns[0] if columns else 'id')` with a comment asserting the first column is the PK. For an auto-PK model `columns[0]` is the first declared column (`enabled`), so PG `Model.insert(replace=True)` is rejected."
    missing:
      - "Route `QueryBuilder.all()/first()/exists()` through `fetch_many`/`fetch_one` (as `Model.search` now does) so pagination is dialect-correct; add `limit(2).all()`/`first()`/`exists()` to the six parity classes."
      - "Add the MariaDB `upsert` and `QueryBuilder.limit` items to `deferred-items.md` with the same evidence used for `list_tables(name=)`, and pin the current (broken) shape or `xfail(strict=True)` in `tests/test_mariadb.py`."
      - "Derive the default conflict target from the model primary key (`Model.insert` already knows `_pk_fields()`), or correct the `builders.py` comment and require the caller to pass `conflict`; add a PostgreSQL assertion for `insert(replace=True)` without an explicit `id`."

  - truth: "The `Query` cardinality contract stated in the docstring and in `docs/design/0-design.md` is enforced at construction (documented contract: the detected `{n}` set must be exactly `range(len(values))`, otherwise `ValueError`)"
    status: partial
    reason: >-
      Two reachable cases violate the documented contract. (1) `Query('SELECT 1', [1])` is accepted
      silently — `if indices and indices != set(range(len(values)))` short-circuits when there are no
      placeholders — so the parameter is stored and then dropped by every `_prepare`. (2) A leading-zero
      index (`{00}`) is normalised with `int()` for validation but compiled with the RAW captured text,
      so `Query('a={00}', [7])` yields `sql='a=%(parameter_00000)s'` with `params={'parameter_0000': 7}`
      and the adapter raises `KeyError: 'parameter_00000'` instead of the promised clean `ValueError`.
      Both were reproduced. The plan's explicit `<behavior>` cases (dispersed indices, duplicates,
      out-of-range, unused parameter) all pass; these two are contract-vs-docstring gaps, not
      plan-blocking.
    artifacts:
      - path: "encino_orm/query.py"
        issue: "`:56` `if indices and indices != set(range(len(values)))` — the `indices and` carve-out silently accepts unused params when the template has no placeholders; `:62` compiles with `m.group(1)` verbatim instead of `int(m.group(1))`, so `{00}` produces a key that does not exist."
      - path: "docs/design/0-design.md"
        issue: "`:95-104` the `with_params()` example is factually wrong and demonstrates the silent drop."
    missing:
      - "Either enforce the contract (drop the `indices and` carve-out and compile from the normalised index: `f'%(parameter_000{int(m.group(1))})s'`), or document the carve-out explicitly and add tests pinning both behaviours."

  - truth: "`docs/design/0-design.md` documents the new `Query` API accurately (D-05: the published site must not document a non-existent result)"
    status: partial
    reason: >-
      The migration note is correct and `rebind` is no longer documented as a live API, but the
      `with_params()` example reuses `q = Query('SELECT * FROM usuarios', [])` and then claims
      `q2.sql` becomes an INSERT statement. Actual behaviour on this tree:
      `Query('SELECT * FROM usuarios', []).with_params(['Grupo B', 0]).sql == 'SELECT * FROM usuarios'`.
      Both comments in the code fence are false, and `mkdocs build --strict` cannot catch it.
    artifacts:
      - path: "docs/design/0-design.md"
        issue: "`:95-104` — wrong expected `q2.sql`/`q2.params`, and the example teaches a reuse pattern whose parameters are silently discarded (see previous gap)."
    missing:
      - "Use a template that actually contains placeholders (e.g. `Query('insert into grupos (grupo, enabled) values ({0},{1})', ['Grupo A', 1])`) and correct the expected output."

  - truth: "`Db.list_tables` returns correct results on all six engines (DIAL-03)"
    status: partial
    reason: >-
      The unfiltered path is fixed and covered per engine. The documented `name=` filter is dead on 4 of
      6 engines: `list_tables` appends `AND name LIKE {0}` to the *base* SQL, but `name` is a SELECT
      alias there (`tablename AS name`), and PostgreSQL/MySQL/SQL Server/Oracle do not allow a column
      alias in `WHERE` (PostgreSQL `UndefinedColumnError`, Oracle `ORA-00911`). Only SQLite has a real
      `name` column. The phase logged this in `deferred-items.md` with an accurate root cause, and the
      new parity tests deliberately avoid the filter (`list_tables(limit=1000)`), so DIAL-03's
      filtered path is unverified and broken on 4 engines. Not covered by any later roadmap phase.
    artifacts:
      - path: "encino_orm/base.py"
        issue: "`:151-154` appends `AND name LIKE {0}` to the base SQL returned by `_tables_sql()`; `name` is an alias in 5 of 6 dialects."
      - path: ".planning/phases/02-dialect-seam-engine-parity/deferred-items.md"
        issue: "Item is logged but no later phase owns the fix."
    missing:
      - "Push the filter into `_tables_sql(name)` so each adapter filters on its real catalog column, or wrap the base SQL in a derived table before filtering; add per-engine `name=` coverage."

deferred:
  - truth: "The breaking removal of `Query.rebind`/`Query.format` is documented in `CHANGELOG.md` (hard project constraint for 0.x breaks)"
    addressed_in: "Phase 8 (Release 0.3.0)"
    evidence: "ROADMAP Phase 8 Success Criterion 3: '`CHANGELOG.md` enumerates every breaking change with old and new behavior, and `MIGRATION-0.3.md` shows before/after examples'; plan 08-04 owns it. `CHANGELOG.md` `[Unreleased]` is currently empty, and `docs/design/0-design.md:107` says `rebind` was removed in 0.3.0 while `pyproject.toml` still declares 0.2.6 — both are Phase 8's responsibility per D-01."

human_verification:
  - test: "Run the `engine-heavy` GitHub Actions job (MSSQL + Oracle) end to end on a real runner."
    expected: "The job goes GREEN: the `msodbcsql18` + `unixodbc-dev` install step succeeds, `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle` causes `engine_unavailable()` to `pytest.fail` (not skip) if a service is down, `tests/test_mssql.py` + `tests/test_oracle.py` run by file selection (never zero tests), `check_skips.py junit.xml` reports 0 skips, and the `coverage-heavy` artifact uploads."
    why_human: "Requires a GitHub Actions run; cannot be executed from this host (no `gh`, no push). Only the structural wiring was verified locally (job exists, services declared, ODBC step present, `FREEPDB1` set, file-based selection, `continue-on-error` absent)."
  - test: "Induced-failure check: on a scratch branch, remove the MariaDB service from the `test` job and push."
    expected: "The `test` job goes RED, not skip — `engine_unavailable()` must fail when the engine is in `ENCINO_ORM_REQUIRE_ENGINES`."
    why_human: "Requires a live CI run. This is validation row 02-05-02; precedent exists from Phase 1 (run #25) but it has not been repeated for the MariaDB/Redis promotion."
  - test: "Probe the ad-hoc parameter ceilings for MSSQL and Oracle inside `engine-heavy` (build an INSERT with growing N and record the first failing N)."
    expected: "The measured value is annotated next to the corresponding constant in `encino_orm/dialects/strategies.py`, replacing the current 'NO verificado empíricamente' provenance."
    why_human: "Requires the heavy engines; `LIMITS['mssql'].max_params=2100` and `LIMITS['oracle'].max_params=65535` are documented but unverified, and `insert_many` now derives its chunk from them."
  - test: "Decide whether `engine-heavy` runs on every PR or only on `push` to `main` + `workflow_dispatch`, based on measured duration."
    expected: "A recorded decision. The forbidden option is making the job advisory (`continue-on-error`)."
    why_human: "Cost/time trade-off; Oracle takes 60-120 s to start."
  - test: "Fix the per-adapter coverage floors (including `oracle.py`) from the first green `engine-heavy` run."
    expected: "`tools/ci/check_coverage_floors.py` `FLOORS` gains adapter entries with real measured values."
    why_human: "In the CI-equivalent run `oracle.py` measures ~16% because Oracle is deselected locally; a floor set now would be fiction. The `coverage-heavy` artifact wiring already exists to feed this."
  - test: "Decide whether CR-01 / WR-03 / WR-04 / WR-05 are accepted as pre-existing deviations (add `overrides:` entries) or opened as gap-closure plans."
    expected: "An explicit decision recorded in this file's frontmatter (`overrides:`) or in a follow-up plan."
    why_human: "These are pre-existing defects the phase did not introduce and partially planned around (the plan explicitly documents `sql.py`/`query_builder.py` `_COLUMN_RE` as a deliberately different allowlist). Accepting vs blocking is a developer call, not a code fact."
---

# Phase 2: Dialect Seam & Engine Parity — Verification Report

**Phase Goal:** Identifier validation and DML construction live in exactly one place inside the core, and the library demonstrably returns correct results on all six engines — not just SQLite.
**Verified:** 2026-09-18T05:09:52Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Method

No previous `02-VERIFICATION.md` existed → initial mode. Must-haves were merged from the ROADMAP Phase 2 Success Criteria (5, non-negotiable) and the `must_haves` frontmatter of all five PLANs (25), plus two truths derived from the phase goal's own clauses (the roadmap SCs operationalise the goal but do not exhaust its wording). Every claim was re-derived from the working tree at `aa5a471`; no SUMMARY.md statement was accepted as evidence. The full suite was executed (`710 passed`), including all 61 integration tests against the live local engines (MySQL, MariaDB, PostgreSQL, MSSQL, Oracle, Redis) — so the parity claims were checked against real drivers, not mocks.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | ROADMAP SC1 — `_check_identifier` lives in exactly one module and all six adapters import it, existing suite passing unchanged | ✓ VERIFIED | `grep -rn '\^[A-Za-z_][A-Za-z0-9_]*\$' encino_orm/` → exactly one hit (`dialects/identifiers.py:21`); `grep _IDENTIFIER_RE` → 0 hits; all 5 adapter `savepoint` call sites delegate through `Db._check_identifier` → `check_identifier` (`base.py:59-62`). Engine golden-string files have `0` deleted lines over the phase range; full suite `710 passed`. |
| 2 | ROADMAP SC2 — `insert`/`update`/`delete` reject an invalid table/column with `ValueError` before the driver, on all six engines; `sync_schema` rejects introspection-derived names | ✓ VERIFIED | All six adapters delegate to `dialects/builders.py` (`build_insert`/`build_update`/`build_delete`); `check_identifier` runs before the SQL string is built. `TestAdaptadoresRechazanAntesDelDriver` has one spy test per adapter (6). `sync_schema` has 4 `check_identifier` calls (`model.py:867,875,886,896`) and a spy test asserting `execute` is never called (`test_migrations.py:156-179`). |
| 3 | ROADMAP SC3 — `count`/`paginate`/`list_tables` correct on PostgreSQL, SQL Server and Oracle, no `KeyError: 'COUNT(*)'` | ✓ VERIFIED | All 7 readers alias `AS n` and read `row["n"]` (`base.py:158,177`; `model.py:775`; `query_builder.py:248,256,264,272,280`); `grep 'row\["COUNT(\*)"\]'` → 0. `TestPostgresParity`/`TestMssqlParity`/`TestOracleParity` ran green against the live engines. |
| 4 | ROADMAP SC4 — `Query` immutable/hashable, `with_params()` returns a copy (`rebind` deleted), per-dialect `MAX_PARAMS`/`MAX_ROWS`, committed SQL snapshots on the always-on SQLite job | ✓ VERIFIED | `q.sql = ...`/`q.fields = ...` raise `AttributeError`; `with_params` returns a new object and leaves the original intact; `hasattr(Query,'rebind')`/`'format'` are `False`; `grep 'def rebind' encino_orm/` → 0. `LIMITS` covers 6 dialects with provenance; 6 adapters + `PoolDb` expose the constants; `insert_many` derives the chunk. `tests/__snapshots__/test_sql_snapshots.ambr` is tracked (`git ls-files`) and not ignored (`git check-ignore` exit 1); 9 snapshots pass inside the DB-free selection. |
| 5 | ROADMAP SC5 — CI matrix runs per-engine integration tests for `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` on MariaDB, Redis, MSSQL and Oracle | ✓ VERIFIED | `.github/workflows/ci.yml`: `test` job has `mariadb` (3307:3306) + `redis` services, `--extra cache`, `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql,mariadb,redis`; `engine-heavy` job (line 252) has mssql+oracle services, `msodbcsql18` install, `ENCINO_ORM_REQUIRE_ENGINES: mssql,oracle`, `FREEPDB1`, file-based selection (`pytest -q tests/test_mssql.py tests/test_oracle.py`); `coverage` `needs: [test, engine-heavy]`. `optional_engine` count is 0 in `test_mariadb.py`/`test_redis_cache.py` and 2 in each of `test_mssql.py`/`test_oracle.py`. All 61 integration tests pass locally. Live CI run is a human item. |
| 6 | 02-01 — exactly ONE allowlist definition in `encino_orm/` | ✓ VERIFIED | Source guard test present (`tests/test_identifiers.py:79`, `rglob` over the package) and the manual grep returns exactly one file. |
| 7 | 02-01 — all 6 former duplicators import the shared definition | ✓ VERIFIED | `base.py`, `sqlite.py`, `mysql.py`, `model/model.py`, `model/types.py`, `transfer.py` all import/use `check_identifier`; `transfer.py`'s local regex + checker are gone. |
| 8 | 02-01 — observable behaviour identical, existing suite passes without editing a test | ✓ VERIFIED | `git diff --numstat 9dc2acf HEAD` over `test_postgresql/mssql/oracle/mysql/sqlite.py` → `+N 0` deletions each; `test_bulk_upsert.py` untouched. |
| 9 | 02-01 — invalid-identifier error messages keep the exact Spanish text | ✓ VERIFIED | Labels preserved (`nombre de tabla`, `nombre de columna`, `columna`, `columna de orden`, `nombre de índice`, `savepoint`); `check_identifier` reproduces `f"{label} inválido: {value!r}"`. The one behavioural nuance (`"tabla\n"` is still accepted because of the `$` anchor) is documented as a deliberate pure-refactor preservation with a characterisation test. |
| 10 | 02-02 — ONE implementation of INSERT/UPDATE/DELETE construction | ✓ VERIFIED | `dialects/builders.py` is the only module with DML literals; `grep 'INSERT INTO\|MERGE INTO\|DELETE FROM'` over the 5 adapters → 0 hits. |
| 11 | 02-02 — `Model.upsert`'s conflict clause lives in the seam; no dialect branch / DML literal in `upsert` | ✓ VERIFIED | `model.py:597` calls `build_upsert`; `UPSERT_KIND`/`strategy_for` supply the dialect data. Two `ast` guards pass (`test_dialect_builders.py:538,553`), docstrings excluded. |
| 12 | 02-02 — six adapters reject a malicious table/column with `ValueError` before the driver | ✓ VERIFIED | 6 spy tests (`TestAdaptadoresRechazanAntesDelDriver`); builders validate table, every column, every conflict column and `schema` before building the SQL. |
| 13 | 02-02 — generated SQL byte-identical (golden-string assertions pass unedited) | ✓ VERIFIED | 0 deletions in the 5 engine test files over the phase range. |
| 14 | 02-02 — `sync_schema` validates introspection-derived names before `ALTER TABLE` | ✓ VERIFIED | 4 `check_identifier` calls + spy test asserting zero `execute` calls on a hostile catalog name. |
| 15 | 02-02 — `PoolDb.insert` stops dropping `conflict` (and forwards `schema=`) | ✓ VERIFIED | `pool.py:82-89` exposes `MAX_PARAMS`/`MAX_ROWS` from the template; `PoolDb.insert` reflects the full abstract signature; `tests/test_pool.py` asserts forwarding. |
| 16 | 02-03 — `Query` immutable; entry contract stays `Query(sql_{n}, [values])` | ✓ VERIFIED | Private `__slots__` + read-only properties; `AttributeError` on assignment to `sql`/`fields`/`ignore_duplicated` and on a typo (no `__dict__`). |
| 17 | 02-03 — `with_params()` returns a new copy; `rebind` no longer exists | ✓ VERIFIED | Reproduced: `with_params([9])` yields `{'parameter_0000': 9}` while the original keeps `1`; `not hasattr(Query, 'rebind')`; source guard for `def rebind(`. |
| 18 | 02-03 — compilation detects the REAL `{n}` by regex, accepts duplicates, rejects invalid cardinality with a clear error | ✓ VERIFIED | `Query('a={0} AND b={2}', [1,2])` and `Query('a={0}', [1,2])` both raise `ValueError` naming indices and count; `{1}`-before-`{0}` and duplicate `{0}` compile correctly. (Two edge cases outside the plan's explicit behaviour block are reported as a partial gap: unused params with no placeholders, and `{00}`.) |
| 19 | 02-03 — `__hash__` raises an explicit `TypeError` on a non-hashable parameter | ✓ VERIFIED | `hash((sql_template, tuple(fields)))` inside a `try/except TypeError` that re-raises a Spanish explanation. |
| 20 | 02-03 — six dialects expose `MAX_PARAMS`/`MAX_ROWS` with provenance; `insert_many` derives its chunk | ✓ VERIFIED | `LIMITS` has 6 entries, each with a non-empty `provenance`; adapters read from `LIMITS`; `PoolDb` delegates; `insert_many` computes `min(MAX_PARAMS // n_cols, MAX_ROWS)` with a documented `500` fallback. `tests/test_engine.py -k max_params` → 4 passed. |
| 21 | 02-03 — the published docs describe the new API; `rebind` is not documented as live (D-05) | ✓ VERIFIED | `docs/design/0-design.md` has no `def rebind`; `with_params` appears 7×; `mkdocs build --strict` exit 0. (The `with_params` *example* is factually wrong — separate partial gap.) |
| 22 | 02-04 — the SEVEN aggregate readers are correct on PostgreSQL, SQL Server and Oracle | ✓ VERIFIED | 7 `AS n` sites + `row["n"]` reads; live parity tests for PG/MSSQL/Oracle pass. |
| 23 | 02-04 — no aggregate reader indexes by expression text | ✓ VERIFIED | Source guard in `tests/test_aggregates.py` over `encino_orm/**/*.py`; grep for `row["COUNT(*)"]` / `row[f"SUM(` … → 0. |
| 24 | 02-04 — per-engine integration tests for `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` in all six engines | ✓ VERIFIED | A `Test<Engine>Parity` class exists in each of the six files; each calls all five APIs; the 5 `QueryBuilder` aggregates appear 4× in each file. 61 integration tests ran green. |
| 25 | 02-04 — the fix lives in the SQL, not in an adapter's fetch-key normalisation | ✓ VERIFIED | No `_normalize_keys` or engine branch in any fetch path; `_rows.py` lower-casing is pre-existing. |
| 26 | 02-05 — per-dialect snapshots run DB-free in the always-on SQLite job and fail on drift | ✓ VERIFIED | `tests/test_sql_snapshots.py` + committed `.ambr`; 9 snapshots pass inside `-m "not integration and not optional_engine"`; `.ambr` is tracked and not git-ignored. |
| 27 | 02-05 — the CI matrix runs MariaDB + Redis as required services and MSSQL/Oracle in a dedicated job | ✓ VERIFIED (structure) | See SC5. Live run is a human item. |
| 28 | 02-05 — removing an engine service from a required job makes the job FAIL, not skip | ? UNCERTAIN | `conftest.py` `engine_unavailable()` calls `pytest.fail` when the engine is in `ENCINO_ORM_REQUIRE_ENGINES` and `check_skips.py` fails on `skipped > 0` — but the induced-failure test has not been run in CI. Human item. |
| 29 | 02-05 — per-module coverage floors are applied over `coverage json` and fail closed | ✓ VERIFIED | Ran `coverage run` + `coverage json` + `tools/ci/check_coverage_floors.py` → `OK: 3 modulo(s) cumplen su piso.` exit 0. Manually dropping a mapped module and forcing 0% both return 1 with `FALLO:` lines. 7 unit tests via `-k check_coverage_floors`. |
| 30 | 02-05 — no gate job uses `continue-on-error` | ✓ VERIFIED | `grep -c continue-on-error .github/workflows/ci.yml` → 0. |
| G1 | GOAL CLAUSE 1 — no identifier reaches SQL interpolation inside the core without passing the single allowlist | ✗ FAILED | `QueryBuilder` alias bypass (CR-01) and unvalidated default column names (WR-06), both reproduced. See gaps. |
| G2 | GOAL CLAUSE 2 — the library returns correct results on all six engines | ✗ FAILED | `QueryBuilder.all()/first()/exists()` emit `LIMIT` (invalid on MSSQL/Oracle); MariaDB `upsert` emits `ON CONFLICT`; PostgreSQL `Model.insert(replace=True)` targets a non-PK column. None covered by the new parity tests. See gaps. |

**Score:** 29/32 truths verified (5/5 ROADMAP Success Criteria; 24/25 plan truths; 0/2 goal-derived truths)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/dialects/identifiers.py` | Single allowlist + checker | ✓ VERIFIED | 28 lines, stdlib only, exactly one definition (source-guarded). |
| `encino_orm/dialects/__init__.py` | Barrel | ✓ VERIFIED | Re-exports identifiers, builders, strategies, limits. |
| `encino_orm/dialects/strategies.py` | `InsertStrategy` + 6 constants + `UPSERT_KIND` + `LIMITS` | ✓ VERIFIED | Frozen dataclasses; 6 dialects; provenance on every limit. |
| `encino_orm/dialects/builders.py` | `build_insert/update/delete/upsert` | ✓ VERIFIED | 213 lines; validates before building; `S608` scoped per-file. |
| `encino_orm/query.py` | Immutable, hashable value object | ✓ VERIFIED | 130 lines; `with_params`; `rebind`/`format` deleted. |
| `tools/ci/check_coverage_floors.py` | Fail-closed coverage gate | ✓ VERIFIED | `FLOORS` = 100/95/95; missing module → exit 1. |
| `tests/test_sql_snapshots.py` + `.ambr` | Committed DB-free snapshots | ✓ VERIFIED | Tracked, 6 dialects per operation, 9 pass. |
| `tests/test_identifiers.py` | accept/reject + single-source guard | ✓ VERIFIED | Present and passing. |
| `tests/test_dialect_builders.py` | Per-dialect SQL + spy rejection + `ast` guards | ✓ VERIFIED | 57 tests; guards verified passing. |
| `tests/test_query.py` | Immutability/`with_params`/cardinality/hash | ✓ VERIFIED | 24 tests. |
| `.github/workflows/ci.yml` | `test` extended + `engine-heavy` + floors | ✓ VERIFIED | Structural wiring confirmed; live run pending. |
| `encino_orm/model/query_builder.py` | (implicit) shared validation | ✗ STUB (security) | Alias interpolation bypasses the allowlist — see CR-01 gap. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `base.py` | `dialects/identifiers.py` | `Db._check_identifier` delegates | ✓ WIRED | `base.py:59-62`. |
| `transfer.py` | `dialects/identifiers.py` | local copy removed, shared imported | ✓ WIRED | No local regex/checker remains. |
| `model/model.py` | `dialects/identifiers.py` | `sync_schema` + column map | ✓ WIRED | 4 calls in `sync_schema`; `_col` validates. |
| 6 adapters | `dialects/builders.py` | `build_*` via `_insert_strategy()` | ✓ WIRED | All 6; no DML literals left in adapters. |
| `model/model.py` | `dialects/builders.py` | `Model.upsert` → `build_upsert` | ✓ WIRED | `model.py:597`. |
| `pool.py` | `base.py` | `PoolDb.insert` full signature | ✓ WIRED | `conflict` + `schema` forwarded; asserted in `tests/test_pool.py`. |
| `query_builder.py` | `dialects/identifiers.py` | alias validation | ✗ NOT_WIRED | Alias never passes through any validator (CR-01). |
| `model/model.py` | `dialects/identifiers.py` | default field name validation | ✗ NOT_WIRED | `_build_column_map:231` assigns `col = name` unvalidated (WR-06). |
| `tests/test_sql_snapshots.py` | `tests/__snapshots__/*.ambr` | syrupy comparison | ✓ WIRED | 9 snapshots pass; `.ambr` committed. |
| `.github/workflows/ci.yml` | `tests/conftest.py` | `ENCINO_ORM_REQUIRE_ENGINES` | ✓ WIRED | `mysql,postgresql,mariadb,redis` / `mssql,oracle`. |
| `.github/workflows/ci.yml` | `tools/ci/check_coverage_floors.py` | `coverage json` → script | ✓ WIRED | Step present in the `coverage` job. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `QueryBuilder.count/sum/avg/min/max` | `row["n"]` | real DB aggregate, aliased `AS n` | Yes (live engines) | ✓ FLOWING |
| `Model.count` / `Db.list_tables` / `Db.paginate` | `row["n"]` | real DB aggregate | Yes | ✓ FLOWING |
| `builders.build_*` | `Query` → adapter `_prepare` | caller data, bound params | Yes (integration tests pass) | ✓ FLOWING |
| `QueryBuilder.all()/first()/exists()` | `_limit_n` → inline `LIMIT` | real query, invalid dialect syntax | Yes but rejected by MSSQL/Oracle | ✗ DISCONNECTED (dialect) |
| `insert_many` chunk | `MAX_PARAMS`/`MAX_ROWS` | `LIMITS` constants | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| DB-free suite + snapshots | `uv run pytest -q -m "not integration and not optional_engine"` | `649 passed, 61 deselected`, 9 snapshots passed | ✓ PASS |
| Full suite against live engines | `uv run pytest -q` | `710 passed` | ✓ PASS |
| Integration tests (incl. MSSQL/Oracle/Redis) | `uv run pytest -q -m integration` | `61 passed` | ✓ PASS |
| Phase test files | `uv run pytest tests/test_identifiers.py tests/test_dialect_builders.py tests/test_query.py tests/test_sql_snapshots.py tests/test_migrations.py tests/test_pool.py tests/test_bulk_upsert.py tests/test_aggregates.py tests/test_query_builder.py tests/test_engine.py tests/test_ci_harness.py -q` | `210 passed` | ✓ PASS |
| `ast` guards | `uv run pytest tests/test_dialect_builders.py -k guard -q` | `2 passed` | ✓ PASS |
| Coverage floor gate | `coverage run … && coverage json && python tools/ci/check_coverage_floors.py coverage.json` | `OK: 3 modulo(s) cumplen su piso.` exit 0 | ✓ PASS |
| Coverage gate fail-closed | drop a mapped module / force 0% | `FALLO: … AUSENTE del reporte` → exit 1 | ✓ PASS |
| Lint / format / types | `ruff check encino_orm tests tools` / `ruff format --check` / `mypy encino_orm` | `All checks passed!` / `114 files already formatted` / `Success: no issues found in 60 source files` | ✓ PASS |
| Docs strict build | `uv run mkdocs build --strict` | exit 0 | ✓ PASS |
| Single allowlist definition | `grep -rn '\^[A-Za-z_][A-Za-z0-9_]*\$' encino_orm/` | exactly `dialects/identifiers.py:21` | ✓ PASS |
| No leftover duplicates | `grep -rn "_IDENTIFIER_RE\|\.query\[0\]\|def rebind\|noqa" encino_orm/` | 0 hits | ✓ PASS |
| **CR-01 reproduction** | `QueryBuilder(T, None, alias='mm WHERE 1=0 UNION SELECT nombre FROM usuarios --')._build_base()[0]` | `'FROM t mm WHERE 1=0 UNION SELECT nombre FROM usuarios --'` | ✗ FAIL (injection) |
| **WR-04 reproduction** | `build_upsert('t', {...}, strategy_for('mariadb'), UPSERT_KIND['mariadb'], ...).sql` | `… ON CONFLICT (a) DO UPDATE SET b = excluded.b` (MariaDB rejects) | ✗ FAIL |
| **WR-05 reproduction** | `PostgresDb().insert('t', {'enabled': True, 'nombre': 'Ana'}, False, True).sql` | `… ON CONFLICT (enabled) DO UPDATE …` (non-PK) | ✗ FAIL |
| **WR-01/WR-02 reproduction** | `Query('SELECT 1',[1]).params` / `Query('a={00}',[7]).sql` + `_to_positional` | silent param drop / `KeyError: 'parameter_00000'` | ✗ FAIL |
| **WR-06 reproduction** | dynamically created model with field `'a; DROP TABLE x --'` → `_column_map()` / `to_ddl()` | unvalidated identifier flows into DDL | ✗ FAIL |
| **WR-03 inspection** | `grep -n 'LIMIT' encino_orm/model/query_builder.py` | `:236`, `:242`, `:287` inline `LIMIT` | ✗ FAIL |
| **WR-07 reproduction** | `Query('SELECT * FROM usuarios', []).with_params(['Grupo B', 0]).sql` | `'SELECT * FROM usuarios'` (doc claims an INSERT) | ✗ FAIL |

### Probe Execution

Step 7c: SKIPPED — the phase declares no probe scripts, and `find scripts -path '*/tests/probe-*.sh'` finds none. The phase's runnable verification is pytest + the coverage script, both executed above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DIAL-01 | 02-01 | `_IDENTIFIER_RE`/`_check_identifier` centralized in one module as a pure refactor | ✓ SATISFIED | One definition, 6 importers, source guard, 0 test edits. |
| DIAL-02 | 02-02 | Shared DML builders validating every table/column on six engines | ✓ SATISFIED (letter) | `builders.py` is the single construction point; 6 spy rejection tests. Note: `QueryBuilder` (a SELECT builder) and `insert_many` are outside the letter — see G1. |
| DIAL-03 | 02-04 | `count`/`paginate`/`list_tables` correct on PG/MSSQL/Oracle (`AS n`) | ✓ SATISFIED (unfiltered path) | 7 sites aliased; live parity tests. The `name=` filter of `list_tables` is broken on 4/6 — partial gap. |
| DIAL-04 | 02-02 | Introspection-derived identifiers validated before `ALTER TABLE` | ✓ SATISFIED | 4 `check_identifier` calls + spy test. |
| DIAL-05 | 02-03 | `Query` correct: no fragile sentinel, immutable/hashable, `with_params()` copy (replaces `rebind`) | ✓ SATISFIED | Verified, with two documented-contract edge cases (WR-01/WR-02). |
| DIAL-06 | 02-03 | Per-dialect `MAX_PARAMS`/`MAX_ROWS` constants | ✓ SATISFIED | `LIMITS` + 6 adapters + `PoolDb` + `insert_many` consumer. |
| DIAL-07 | 02-05 | Per-dialect SQL snapshots (syrupy) on the always-on SQLite job | ✓ SATISFIED | Committed `.ambr`, 9 snapshots in the DB-free selection. |
| DIAL-08 | 02-05 | CI matrix covers multiple engines (MariaDB + Redis services; MSSQL/Oracle separate job) | ✓ SATISFIED (structure) | Wiring verified; live CI run pending (human). |
| DIAL-09 | 02-04 | Per-engine integration tests for `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` | ✓ SATISFIED | 6 parity classes, 61 integration tests green live. |

**Orphaned requirements:** none. REQUIREMENTS.md maps exactly DIAL-01…DIAL-09 to Phase 2, and every ID appears in at least one PLAN's `requirements:` frontmatter (02-01: DIAL-01; 02-02: DIAL-02/04; 02-03: DIAL-05/06; 02-04: DIAL-03/09; 02-05: DIAL-07/08).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `encino_orm/model/query_builder.py` | 49, 101, 112, 178, 184, 192 | Unvalidated alias interpolated into `FROM`/`JOIN` | 🛑 Blocker | Working SQL-injection primitive through a public API parameter; falsifies the single-choke-point goal clause. |
| `encino_orm/model/model.py` | 231 | `col = name` — default column name unvalidated | ⚠️ Warning | `to_ddl` / `insert_many` interpolate unvalidated identifiers. |
| `encino_orm/model/query_builder.py` | 236, 242, 287 | Inline `LIMIT` | ⚠️ Warning | Invalid on MSSQL/Oracle; same bug class the phase fixed elsewhere. |
| `encino_orm/dialects/strategies.py` | 57 | `UPSERT_KIND['mariadb'] = 'on_conflict'` | ⚠️ Warning | Broken on a newly-required engine; not logged in `deferred-items.md`. |
| `encino_orm/query.py` | 56, 62 | Contract not enforced (`indices and` carve-out; raw `{00}` compilation) | ⚠️ Warning | Silent parameter drop; `KeyError` instead of `ValueError`. |
| `docs/design/0-design.md` | 95-104 | Wrong example in published docs | ℹ️ Info | Documents a non-existent result. |
| `pyproject.toml` | 131-137, 77 | Stale/contradictory `S608` comment; stale `optional_engine` marker description | ℹ️ Info | Documentation drift. |
| — | — | `TBD`/`FIXME`/`XXX` in phase-modified files | — | None found (debt-marker gate clean). |

### Human Verification Required

See the `human_verification` frontmatter block. In summary:

1. **`engine-heavy` live CI run** — the only way to prove the MSSQL/Oracle job actually installs the ODBC driver, starts both containers, selects tests by file (never zero), and reports 0 skips.
2. **Induced-failure check** — remove the MariaDB service on a scratch branch; the `test` job must go RED.
3. **Ad-hoc parameter-ceiling probe** for MSSQL (2100) and Oracle (65535) in `engine-heavy`, annotating the measured value in `dialects/strategies.py`.
4. **`engine-heavy` scheduling decision** (per-PR vs main-only).
5. **Adapter coverage floors** (including `oracle.py`) from the first green `engine-heavy` run.
6. **Decision on the pre-existing gaps** (CR-01 / WR-03 / WR-04 / WR-05): accept as overrides or open gap-closure plans.

### Deferred Items

| # | Item | Addressed In | Evidence |
| --- | ---- | ------------ | -------- |
| 1 | `CHANGELOG.md` entry for the breaking `rebind`/`format` removal (and the `0.3.0` version wording in the design doc) | Phase 8 (Release 0.3.0) | ROADMAP Phase 8 SC3 + plan 08-04 own `CHANGELOG.md` and `MIGRATION-0.3.md`; CONTEXT D-01 explicitly assigned it there. |

No other identified gap is covered by a later milestone phase: Phases 3–7 target migrations/cache, the pool, resilience, config/optional-layer hygiene, and performance. Phase 6 SC5 documents trust boundaries for `Filter.raw`/`Query`/`db.fn.*` but does not name `QueryBuilder` aliases, so CR-01 is not a clean deferral.

### Gaps Summary

Phase 2 delivers its five ROADMAP Success Criteria and all nine requirement IDs, and it does so for real: the full suite (710) passes including 61 integration tests against the live MySQL, MariaDB, PostgreSQL, MSSQL, Oracle and Redis engines; the identifier allowlist has exactly one definition; DML construction is single-sourced in `dialects/builders.py` with byte-identical SQL proven by untouched golden-string assertions; the seven aggregate readers are aliased; `Query` is an immutable value object with `with_params()`; snapshots are committed and DB-free; and the coverage-floor gate fails closed.

The gaps are against the phase goal's two broad clauses, not against the letter of the success criteria, and they are pre-existing defects the phase did not introduce:

- **Goal clause 1 — "identifier validation … in exactly one place".** The allowlist is single-sourced but not a choke point. `QueryBuilder`'s public `alias=`/`join(alias=)`/`join_subquery(alias=)` reach SQL interpolation with no validation (a reproduced UNION injection primitive), and the default pydantic field name bypasses validation in `_build_column_map`, leaking into `to_ddl` and `insert_many`. This is the largest surviving bypass of the seam the phase built.
- **Goal clause 2 — "correct results on all six engines".** `QueryBuilder.all()/first()/exists()` still emit inline `LIMIT` (invalid on MSSQL/Oracle — the exact bug the phase fixed in `Model.search`); MariaDB `upsert` emits `ON CONFLICT`, which MariaDB does not support, on an engine this phase promoted to *required*; and PostgreSQL `Model.insert(replace=True)` targets a non-PK column. None of these paths is exercised by the new per-engine parity tests, so CI stays green over them.

Two smaller partial gaps (the `Query` cardinality contract's two unenforced edge cases, and the factually wrong `with_params()` example in the published design doc) and one documented-but-unowned deferral (`list_tables(name=)` broken on 4/6 engines) complete the picture.

Because the goal's clauses are functional claims about the core and a reproduced injection primitive plus three engine-correctness holes falsify them, this phase is reported as `gaps_found`. Every failure is pre-existing and partially planned around; if the developer judges them out of scope for this phase, they can be accepted by adding `overrides:` entries (see `references/verification-overrides.md`) and re-running verification — the roadmap success criteria themselves all pass.

---

_Verified: 2026-09-18T05:09:52Z_
_Verifier: the agent (gsd-verifier)_
