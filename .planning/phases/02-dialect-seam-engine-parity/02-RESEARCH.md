# Phase 2: Dialect Seam & Engine Parity - Research

**Researched:** 2026-09-18
**Domain:** Multi-dialect DML seam + identifier-validation policy, `Query` value-object correctness, multi-engine CI topology, per-dialect coverage gating, database-free SQL snapshotting
**Confidence:** HIGH on code-level findings and on the parameter ceilings I could verify empirically; MEDIUM on the multi-engine CI topology and the Oracle ceilings; HIGH on the design recommendations (they are constrained by locked decisions D-01…D-06)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Refactor de `Query` (DIAL-05)**
- **D-01:** **Ruptura limpia.** `Query` pasa a ser inmutable y `rebind` se **elimina**. No se dejan shims deprecados. Justificación: `rebind` no se usa en ningún punto de `encino_orm/` ni de `tests/` — solo está documentado en `docs/design/0-design.md`. Se documenta la ruptura en `CHANGELOG.md` y en `MIGRATION-0.3.md` (Fase 8).
- **D-02:** **Interfaz con accesores tipados + compatibilidad de lectura.** El `Query` inmutable expone accesores tipados `sql` y `params`, y mantiene una property `query` de **solo lectura** que devuelve `[sql, params]`. Objetivo: que DIAL-05 **no toque los 6 adaptadores** (que hoy leen `qry.query[0]`/`qry.query[1]` en su `_prepare` y en las migraciones). Los adaptadores migran a los accesores tipados en DIAL-02, cuando ya se reescriben los builders.
- **D-03:** **Igualdad y hash estrictos.** `__eq__` compara plantilla SQL + params. `__hash__` se calcula sobre `(sql_template, tupla_de_params)` y lanza **`TypeError` explícito** si algún valor de los params no es hashable (list/dict), en lugar de devolver un hash engañoso. Esto habilita un cache-key real para DATA-07 (v2) y falla ruidosamente.
- **D-04:** **Se mantiene `{n}` como contrato de entrada.** La firma sigue siendo `Query(sql_con_{n}, [valores])`. Se arregla la compilación: detección por regex de los `{n}` **reales** (no `enumerate` sobre el dict de params), soporte de índices dispersos o duplicados, y **validación de cardinalidad** (el número de placeholders debe cuadrar con la lista de params) con error claro. No se añade el modo dict nombrado en esta fase.
- **D-05:** **Se actualiza `docs/design/0-design.md`** a la API nueva (inmutable, `with_params()` en lugar de `rebind`) con una nota de migración. El sitio de docs se publica, así que no debe documentar una API eliminada.

**Ajuste de requisito derivado de D-01**
- **D-06:** La redacción de **DIAL-05** en `REQUIREMENTS.md` dice literalmente *"sin sentinel frágil `{0}`, inmutable/hashable, y `rebind` funciona"*. Al eliminar `rebind`, la letra del requisito cambia: se reformula a **"`Query` inmutable con `with_params()` que devuelve una copia"**. El roadmapper/planner debe reflejar esta reformulación en la trazabilidad.

### the agent's Discretion
- Estructura interna del seam `dialects/` (nombres de módulos, forma de los hooks por dialecto).
- Forma exacta de `with_params()` y de la validación de cardinalidad.
- Valores concretos de `MAX_PARAMS`/`MAX_ROWS` por dialecto (la investigación los marca como **no verificados empíricamente**: MSSQL 2100, Oracle 1000-elemento `IN`, asyncpg ~32767).
- Selección de qué SQL exacto se congela en los snapshots.

### Deferred Ideas (OUT OF SCOPE)
- **Cache de placeholders compilados (TS-37)** — diferido a v2 como `DATA-07`; D-03 deja `Query` *listo* para ello (hashable) sin implementar el cache. Se reabre solo si el profiler de Fase 7 lo muestra en el top 5.
- **Modo de params nombrados (`%(nombre)s` con dict)** — considerado y descartado para esta fase (D-04); posible mejora futura de ergonomía.
- **Piso global de cobertura más alto** — el piso por dialecto (no discutido) es lo prometido para Fase 2; subir el global queda para más adelante.

### Areas NOT discussed by the user (in scope; research must resolve)
1. Identifier-validation policy (DIAL-01/02/04) — hard constraint: centralize as a PURE refactor in its own commit, then validate in a SEPARATE bisectable commit.
2. Multi-engine CI matrix (DIAL-08).
3. Per-dialect coverage floor (Phase 1 D-04/D-06, promised for this phase).
4. syrupy dialect snapshots (DIAL-07).
</user_constraints>

---

## ⚠️ Roadmap correction carried into this research (STALE criterion)

ROADMAP.md Phase 2 Success Criterion 4 reads:

> "`Query` is immutable and hashable, `rebind` works, per-dialect `MAX_PARAMS`/`MAX_ROWS` constants exist, and committed SQL snapshots assert dialect output on the always-on SQLite job"

**`rebind` works` is STALE and contradicts locked decisions D-01/D-06.** `rebind` is eliminated, not fixed. The planner MUST rewrite criterion 4 as:

> "`Query` is immutable and hashable; **`with_params()` returns a copy**; per-dialect `MAX_PARAMS`/`MAX_ROWS` constants exist; and committed SQL snapshots assert dialect output on the always-on SQLite job"

Likewise ROADMAP plan **02-03** says *"fix `rebind`"* — it must read *"replace `rebind` with `with_params()`"*. This is the same correction already carried in the phase description; it is restated here because the roadmap text still contains the old premise.

---

## Summary

Phase 2 is a **seam-and-parity** phase: collapse six copy-pasted DML builders and six copies of an identifier regex into one core module, make `Query` a correct immutable value object, and then *prove* the library returns correct results on engines it has never been tested against. Three findings dominate the research:

1. **The `COUNT(*)` bug is 7 sites, not 3.** Every aggregate reader in the library assumes the driver returns the literal column label `COUNT(*)`/`SUM(x)`/`AVG(x)`/`MIN(x)`/`MAX(x)`. That works only on SQLite and MySQL. PostgreSQL/asyncpg lowercases the label to `count`; MSSQL and Oracle return tuple rows that `encino_orm/_rows.py:14` **explicitly lowercases** (`cols = [d[0].lower() ...]`). `base.py:175-177` already contains the correct pattern (`SELECT COUNT(*) AS n …` → `row["n"]`). The phase must apply it to **all 7 sites**, not only the 3 named in DIAL-03 — `QueryBuilder.sum/avg/min/max` fail with the identical `KeyError` on the same three engines and would leave the phase goal ("correct results on all six engines") unmet.

2. **The identifier allowlist must not be loosened, but the builders must not be a dead end either.** The strict regex `^[A-Za-z_][A-Za-z0-9_]*$` is the injection defense; widening it re-opens the surface (Pitfall 10). But applying it to the public `Db.insert/update/delete` breaks `schema.table`, which the codebase *already accepts elsewhere* (`sql.py:_COLUMN_RE = ^[A-Za-z_][A-Za-z0-9_.]*$` allows dots for `db.fn.*` columns). Recommendation: **keep the regex strict and add a keyword-only `schema=` parameter validated separately** — this covers the one legitimate case without touching the character class, and leaves raw `Query` as the documented trusted-input escape hatch for quoted/non-ASCII names.

3. **Three concrete, previously-unflagged execution blockers.** (a) The GitHub `ubuntu-latest` (24.04) runner image ships **no ODBC driver at all** — the MSSQL job needs an explicit `msodbcsql18` + `unixodbc` install step or every MSSQL test import-fails. (b) The Oracle container in `docker-compose.yml` is `gvenzl/oracle-xe:21-slim` (service `XEPDB1`) while the lighter CI image is `gvenzl/oracle-free` (service `FREEPDB1`) — the CI job **must** override `ENCINO_ORM_ORACLE_SERVICE=FREEPDB1`. (c) `Query` is currently mutated by two adapters (`q.ignore_duplicated = True` in `mssql.py:223` and `oracle.py:225`) and that attribute is asserted by existing tests (`test_mssql.py:41`, `test_oracle.py:48`) — the immutability refactor must promote it to a constructor field, not delete it.

**Primary recommendation:** Land the phase as five bisectable commits in this order — (1) pure-centralize identifiers, (2) shared strategy-driven builders + validation + `sync_schema` validation, (3) immutable `Query` + dialect constants, (4) the 7-site alias fix + per-engine integration tests, (5) DB-free syrupy snapshots + the expanded CI matrix + the per-module coverage-floor script. Keep the generated SQL **byte-identical** to today's output so the existing unit tests act as the refactor's regression oracle.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Identifier validation policy (`check_identifier`) | Core (`encino_orm/dialects/identifiers.py`) | Adapters (import only) | One definition, six importers. Pitfall 10: "fixing one and missing five is the expected outcome." |
| DML SQL construction (`build_insert/update/delete`) | Core (`encino_orm/dialects/builders.py`) | — | Pure functions, no I/O, no driver knowledge. Adapters stop owning DML text (ARCHITECTURE.md Anti-Pattern 6). |
| Dialect DML variance (upsert/merge shape) | Adapter hook (`_insert_strategy`) | Core (`dialects/strategies.py` data) | Strategy *objects* are data; the choice of strategy is adapter-local, preserving "no engine branches outside the adapter". |
| `Query` compilation (`{n}` → `%(name)s`) | Core (`encino_orm/query.py`) | — | Value object; no dialect knowledge (native translation stays in `_prepare`). |
| Native placeholder translation (`%(name)s` → `$1`/`?`/`:name`) | Adapter (`_prepare`) | — | Unchanged contract; the phase must not move it. |
| Count/aggregate result-key aliasing | Core (`base.py`, `model/model.py`, `model/query_builder.py`) | — | The label must be dialect-independent (`AS n`) because the result-shape contract differs per driver. |
| `sync_schema` DDL construction | ORM layer (`model/model.py`) | Core (`dialects/identifiers.py`) | Catalog-derived names are an untrusted input; validation is the core checker applied at the ORM boundary. |
| Per-dialect SQL regression proof | Test layer (`tests/test_sql_snapshots.py`) | Core (builders) | Snapshotting is DB-free and belongs on the always-on job. |
| Per-dialect coverage enforcement | CI (`tools/ci/check_coverage_floors.py` + `coverage` job) | — | `coverage.py` cannot express per-file floors; the mechanism must live outside the tool. |
| Engine provisioning (MariaDB/Redis/MSSQL/Oracle) | CI (GHA `services:`) | Local (docker-compose) | Dialect behavior is a function of the server, not the Python version — do not multiply heavy containers across the 4-leg matrix. |

---

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research Support |
|----|-------------------------------|------------------|
| DIAL-01 | `_IDENTIFIER_RE`/`_check_identifier` centralizados en un único módulo como refactor puro, sin cambio de comportamiento | Six duplicated regexes located (see Pitfall A); target module chosen (`dialects/identifiers.py`); pure-refactor checklist + the two call-site styles (`self._check_identifier` vs `_IDENTIFIER_RE.match`) documented |
| DIAL-02 | Builders DML compartidos en `dialects/` que validan cada tabla/columna en los seis motores | Strategy-object design (`strategies.py`) + byte-identical SQL preservation list; `schema=` policy; spy-rejection test recipe; the `ignore_duplicated` mutation conflict resolved |
| DIAL-03 | `count`/`paginate`/`list_tables` correctos en PostgreSQL, SQL Server y Oracle (alias `AS n`) | **7 sites** identified (not 3); correct pattern already exists at `base.py:175-177`; root cause is `_rows.py` lowercasing + asyncpg label normalization |
| DIAL-04 | Identificadores derivados de introspección validados antes de `ALTER TABLE` (`sync_schema`) | Three interpolation sites located (`model/model.py:894, 902, 913/917`); catalog-derived vs model-derived distinguished; fail-closed policy recommended |
| DIAL-05 | `Query` sin sentinel frágil `{0}`, inmutable/hashable, con `with_params()` (reemplaza a `rebind`) | Exact current defects enumerated (`query.py:7,12-26,28-31`); immutability mechanics chosen (`__slots__` + read-only properties + custom `__eq__`/`__hash__`); the `query` read-only property keeps the 6 adapters and 3 white-box tests untouched; `ignore_duplicated` conflict resolved |
| DIAL-06 | Constantes `MAX_PARAMS`/`MAX_ROWS` por dialecto | asyncpg 32767 **verified in installed driver source**; SQLite 32766 **verified empirically**; MSSQL 2100 **verified in Microsoft capacity specs**; Oracle ceilings flagged MEDIUM; `insert_many`'s hardcoded `chunk=500` located as the first consumer |
| DIAL-07 | Snapshots de SQL por dialecto (syrupy) en el job SQLite siempre activo | syrupy 6.1.1 verified compatible (Python ≥3.10, pytest ≥8); `snapshot` fixture + `__snapshots__/*.ambr` + `--snapshot-update` documented; "fails on missing snapshot" soundness caveat flagged; `.gitignore` verified not to exclude snapshots |
| DIAL-08 | Matriz CI multi-motor (MariaDB + Redis como servicios; MSSQL/Oracle en job separado) | Concrete job topology proposed; **ODBC-driver install step is a hard prerequisite** (verified absent from the runner image); Oracle service-name mismatch found; port-conflict (MySQL 3306 vs MariaDB) found; Phase 1 switch verified extensible with zero code change |
| DIAL-09 | Tests de integración por motor para `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` | Existing skip-guard pattern (`engine_unavailable`) and per-engine file layout confirmed; gap analysis: zero current calls to those five APIs in any non-SQLite test file |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `syrupy` | `6.1.1` | Database-free per-dialect SQL snapshots (DIAL-07) | Zero-dependency pytest plugin; 6.x requires Python ≥3.10 and pytest ≥8 (both satisfied). Snapshots are committed `.ambr` files, so dialect drift is caught in seconds on the always-on job with no containers. `[VERIFIED: PyPI JSON API + github.com/syrupy-project/syrupy README]` |
| `coverage` | `7.16.1` (already present) | Per-module coverage floor via `coverage json` | `[report] fail_under` is a single total — no per-file variant exists — so the floor must be enforced by a script over the JSON report. Schema verified empirically. `[VERIFIED: coverage.readthedocs.io config reference + local run]` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `testcontainers` | `4.15.0` | Optional **local-only** engine provisioning (identical DSNs on Windows dev and Linux) | Only if local MariaDB/MSSQL/Oracle/Redis provisioning via Python is wanted. **Not needed for CI** — GHA `services:` is simpler and avoids the `[mssql]` extra pulling `pymssql`+`sqlalchemy` and the `get_connection_url()` mismatch. `[VERIFIED: PyPI JSON API; slopcheck OK]` |
| `pytest` (present) | `9.1.1` | Host for the snapshot + rejection tests | Already the runner. `[VERIFIED: pyproject.toml]` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `syrupy` | Hand-written golden-string assertions | The repo already has these (`test_postgresql.py:32-57`). They cover 1 dialect × 3 verbs and do not catch drift systematically. Golden strings are the *floor*; syrupy generalizes them. Keep both. |
| `syrupy` | `inline-snapshot` | Syrupy's README explicitly points to `inline-snapshot` for inline snapshots, but syrupy's file-based `.ambr` is the better fit for a matrix of 6 dialects × N operations (one readable file per dialect). `[CITED: github.com/syrupy-project/syrupy]` |
| `testcontainers` for CI | GHA `services:` | `services:` needs no dev dependency, no Docker socket handling, and avoids the `mssql` extra's `pymssql`/`sqlalchemy` bloat. Use `services:` in CI, testcontainers only locally. |
| Per-file `fail_under` | `pytest-cov --cov-fail-under` per job | A per-*job* number still cannot express "95% for `dialects/`, 70% for `oracle.py`" in one run. Only a script over `coverage json` can. |
| Widening `_IDENTIFIER_RE` to allow dots | `schema=` keyword parameter | Widening re-opens the injection surface and is explicitly forbidden by Pitfall 10 ("Never widen the character class"). |

**Installation:**
```bash
# Runtime deps: NONE. This phase adds no runtime dependency (import-lazy contract preserved).
# Dev-only:
uv add --dev syrupy
# Optional, local-only:
uv add --dev "testcontainers[mssql,oracle-free,redis,mysql]"
```

**Version verification (run before writing the Standard Stack table into a plan):**
```bash
uv pip index versions syrupy        # or: curl -s https://pypi.org/pypi/syrupy/json | grep version
uv pip index versions testcontainers
```

---

## Package Legitimacy Audit

> slopcheck was installed and executed during this research. `testcontainers` → `[OK]`. `syrupy` → `[SUS]` by a **name-similarity heuristic** ("close to 'scrapy'"), which is a false positive: syrupy is the MIT-licensed pytest snapshot plugin maintained at `github.com/syrupy-project/syrupy` (884 stars), version 6.1.1 on PyPI, README read directly this session. Per protocol the `[SUS]` verdict is retained and the planner must gate the install behind a `checkpoint:human-verify`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `syrupy` | PyPI | multi-year (6.x major line; 7.x unreleased) | widely used pytest plugin | `github.com/syrupy-project/syrupy` | **[SUS]** | **Flagged** — false-positive name similarity vs `scrapy`; keep, but planner MUST add `checkpoint:human-verify` before install |
| `testcontainers` | PyPI | multi-year (4.15.0) | very widely used | `github.com/testcontainers/testcontainers-python` | [OK] | Approved (optional, local-only) |

**Packages removed due to slopcheck `[SLOP]` verdict:** none.
**Packages flagged as suspicious `[SUS]`:** `syrupy` — planner inserts a `checkpoint:human-verify` before `uv add --dev syrupy`.

**Note on side effect:** running the slopcheck gate installed `testcontainers` into the *user-level* Python 3.14 site-packages (`%APPDATA%\Python\Python314`), not the project venv. No project file was modified. Clean up with `pip uninstall testcontainers` if desired.

---

## Architecture Patterns

### System Architecture Diagram

Data flow for a write on any of the six engines, before and after the seam:

```text
  CALLER (user code / Model / PoolDb)
        │
        │  Model.insert() → Db.insert(tabla, data, ignore_duplicated, replace, conflict[, schema])
        ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ CORE SEAM  encino_orm/dialects/            [NEW — single choke point]│
  │                                                                     │
  │  identifiers.py ── check_identifier(table, schema, *columns)         │
  │        │              │  strict allowlist ^[A-Za-z_][A-Za-z0-9_]*$   │
  │        │              └── raises ValueError BEFORE any SQL exists    │
  │        ▼                                                            │
  │  builders.py ── build_insert / build_update / build_delete           │
  │        │            │                                                │
  │        │            └── renders {0},{1},… placeholders (D-04)        │
  │        ▼                                                            │
  │  strategies.py ── InsertStrategy(kind=prefix|suffix|merge)           │
  └────────┬────────────────────────────────────────────────────────────┘
           │  returns Query(sql_template, values)     ← immutable (DIAL-05)
           ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ Query  encino_orm/query.py                                          │
  │   .sql_template (with {n})  .fields (input list)                    │
  │   .sql  → compiled "%(parameter_0000)s" SQL                          │
  │   .params → {parameter_0000: value, …}                               │
  │   .query → [sql, params]  (read-only compat property, D-02)          │
  │   .with_params(values) → new Query   (replaces rebind, D-01/D-06)    │
  └────────┬────────────────────────────────────────────────────────────┘
           │  adapter.execute(qry) / fetch_*
           ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ ADAPTER  (sqlite | mysql | mariadb | postgresql | mssql | oracle)     │
  │   _prepare(qry) → native placeholders   (UNCHANGED contract)          │
  │      sqlite/mssql → ?     postgresql → $1     oracle → :name          │
  │   _insert_strategy(...) → InsertStrategy  [NEW hook, replaces insert] │
  │   is_lock_error / columns_of / last_id / migrate  (UNCHANGED)         │
  └────────┬────────────────────────────────────────────────────────────┘
           ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │ DRIVER  aiosqlite · aiomysql · asyncpg · aioodbc/pyodbc · oracledb    │
  │   returns rows whose COLUMN LABELS differ per engine                 │
  │   ⇒ every aggregate reader must alias (AS n) and read row["n"]        │
  └─────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

```text
encino_orm/
├── dialects/                 # [NEW] core seam — depends on stdlib + Query only
│   ├── __init__.py           # re-exports check_identifier, build_* (added in 02-02)
│   ├── identifiers.py        # 02-01: IDENTIFIER_RE + check_identifier (pure move)
│   ├── builders.py           # 02-02: build_insert/update/delete (+ validation)
│   └── strategies.py         # 02-02: InsertStrategy + per-dialect instances
├── query.py                  # 02-03: immutable Query, with_params(), __eq__/__hash__
├── base.py                   # 02-01: imports the shared regex/checker
│                             # 02-02: Db.insert/update/delete delegate to builders
│                             # 02-04: list_tables COUNT alias
├── sqlite.py mysql.py mariadb.py postgresql.py mssql.py oracle.py
│                             # 02-01: import the shared regex
│                             # 02-02: insert/update/delete replaced by _insert_strategy hook
│                             # 02-04: nothing (result-key fix is core-side)
├── model/model.py            # 02-01: import the shared regex
│                             # 02-02: sync_schema validates catalog-derived names
│                             # 02-04: Model.count alias
├── model/query_builder.py    # 02-04: count/sum/avg/min/max aliases
├── model/types.py            # 02-01: import the shared regex
└── transfer.py               # 02-01: delete local copy, import shared

tools/ci/
├── check_skips.py            # existing JUnit skip gate (unchanged)
└── check_coverage_floors.py  # [NEW] per-module floor over coverage.json

tests/
├── test_identifiers.py       # [NEW] allowlist accept/reject + spy (no driver reached)
├── test_dialect_builders.py  # [NEW] byte-identical SQL across the 6 strategies
├── test_query.py             # [NEW] immutability, with_params, sparse/duplicate {n}, hash
├── test_sql_snapshots.py     # [NEW] syrupy: 6 dialects × DML + count/paginate/list_tables
├── __snapshots__/            # [NEW, COMMITTED] *.ambr per test
├── test_postgresql.py …      # extend with count/paginate/list_tables/sync_schema/last_id
└── conftest.py               # unchanged (engine_unavailable switch already exists)
```

### Pattern 1: Centralize-then-validate as two separate, bisectable commits

**What:** 02-01 moves the regex and the checker into `dialects/identifiers.py` and rewrites every importer to use it — **with identical behavior and identical error messages**. 02-02 then *applies* validation inside the new builders and inside `sync_schema`.

**When to use:** Always for this phase. ROADMAP "Hard Ordering Constraints" #2: *"Merging them makes the security change unbisectable and lets it silently miss five of six dialects."*

**Why the split is real, not ceremony:** today there are **six** regex definitions and **two** `_check_identifier` implementations, and the call sites come in two shapes:

| File | Duplication | Call-site style |
|------|-------------|-----------------|
| `base.py:13` | `_IDENTIFIER_RE` + `_check_identifier:61` (canonical) | `self._check_identifier(...)` in 5 adapters |
| `sqlite.py:13` | `_IDENTIFIER_RE` | `_IDENTIFIER_RE.match(table)` in `columns_of:115` |
| `mysql.py:15` | `_IDENTIFIER_RE` | `_IDENTIFIER_RE.match(table)` in `columns_of:122` |
| `transfer.py:16,19` | regex **and** a re-implemented checker | `_check_identifier(...)` in `build_ddl` |
| `model/model.py:29` | `_IDENTIFIER_RE` | 5 call sites (`223, 235, 244, 752, 847`) |
| `model/types.py:201` | `_IDENTIFIER_RE` | `indexes_ddl:229` |
| `sql.py:8` | **`_COLUMN_RE`** — a *different* regex that allows dots | `SqlFunctions._col` |

`[VERIFIED: repo grep — 32 matches across 7 files]`

**Decision:** do **not** touch `sql.py:_COLUMN_RE` in 02-01. Unifying it would be a behavior change (it intentionally allows `a.b`), violating the zero-behavior-change requirement. Record it as a follow-up candidate.

**Adapter migration shape:** keep `Db._check_identifier` as a thin staticmethod that delegates to the shared function. The five adapters call `self._check_identifier(...)`, so a delegate preserves their code exactly — the *pure-refactor proof* is "the existing suite passes unchanged".

### Pattern 2: Strategy-object DML seam that preserves byte-identical SQL

**What:** one `build_insert/update/delete` in `dialects/builders.py`; adapters override only `_insert_strategy(...)`.

**The hard constraint:** the generated SQL must be **byte-identical** to today's output, or the existing unit tests break *and* the new syrupy snapshots would freeze a behavior change. The exact strings currently asserted:

| Adapter | Asserted SQL (from existing tests) |
|---------|-----------------------------------|
| PostgreSQL | `INSERT INTO t (a,b) VALUES ($1,$2)` · `… ON CONFLICT DO NOTHING` · `… ON CONFLICT (a) DO UPDATE SET a = EXCLUDED.a, b = EXCLUDED.b` · `UPDATE t SET nombre = $1 WHERE id = $2` |
| MSSQL | `INSERT INTO t (a,b) VALUES (?,?)` · `MERGE INTO t AS dst USING (SELECT ? AS a, ? AS b) AS src ON (…) WHEN MATCHED THEN UPDATE SET … WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)` |
| Oracle | `INSERT INTO t (a,b) VALUES (:parameter_0000,:parameter_0001) RETURNING id INTO :ret_id` · `MERGE INTO t dst USING (…) src ON (…) …` (**no `AS` before the table alias**) |
| SQLite | `INSERT …` / `INSERT OR REPLACE …` / `INSERT OR IGNORE …` (prefix variants) |
| MySQL/MariaDB | `INSERT …` / `REPLACE …` / `INSERT IGNORE …` (prefix variants) |

`[VERIFIED: tests/test_postgresql.py:20-57, tests/test_mssql.py:23-50, tests/test_oracle.py:31-68]`

Preservation invariants the builder must honour exactly:
1. Column order = `dict` insertion order; no spaces after commas in the column list (`a,b`) or in the placeholder list (`$1,$2`).
2. Placeholder indices are contiguous from 0: `insert`/`delete` start at 0; `update` numbers SET columns `0..n-1` then WHERE keys `n..`.
3. `replace`/`ignore_duplicated` precedence: `replace` wins (`elif ignore_duplicated`) — already the case in all six.
4. PostgreSQL `replace` with no explicit `conflict` defaults the target to `columns[0]`.
5. Oracle emits `RETURNING id INTO :ret_id` **only when `"id" not in columns`**; the `:ret_id` bind is added by `execute()`, not by the builder.
6. `ignore_duplicated` is carried as a Query attribute for MSSQL/Oracle (they suppress unique-violation errors in `execute`) — see Pattern 3.

**Strategy shape (recommended):**
```python
# encino_orm/dialects/strategies.py
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class InsertStrategy:
    """Forma del INSERT por dialecto. `kind` discrimina los tres renders."""

    kind: Literal["prefix", "suffix", "merge"]
    replace_prefix: str = "INSERT OR REPLACE"   # kind="prefix" + replace=True
    ignore_prefix: str = "INSERT OR IGNORE"     # kind="prefix" + ignore_duplicated=True
    merge_alias: str = "dst"                    # kind="merge": "AS dst" (MSSQL) vs "dst" (Oracle)
    conflict_target: bool = False               # kind="suffix": requires an ON CONFLICT (target)
```

Adapters expose `_insert_strategy(*, replace, ignore_duplicated, conflict) -> InsertStrategy` returning one of six module-level constants. The builder branches on `kind` only — three branches, not six.

### Pattern 3: Immutable `Query` with a read-only compat property

**Recommended mechanics:** plain class with `__slots__`, read-only properties, custom `__eq__`/`__hash__` (not `@dataclass(frozen=True)`). Rationale: `Query` is on the per-execution hot path; the codebase already uses the `object.__setattr__` idiom for private state (`model/model.py:83-105`); and a frozen dataclass fights the custom `__hash__` + the `ignore_duplicated` field.

**Critical conflict discovered:** two adapters mutate `Query` after construction —
```python
# encino_orm/mssql.py:222-223 and encino_orm/oracle.py:224-225
q = Query(sql, values)
if ignore_duplicated and not replace:
    q.ignore_duplicated = True
```
and two existing tests assert the attribute:
```python
# tests/test_mssql.py:38-41 and tests/test_oracle.py:45-48
q = db.insert("t", {"a": 1}, ignore_duplicated=True)
assert q.ignore_duplicated is True
```
`[VERIFIED: repo]`

**Resolution:** promote `ignore_duplicated` to a **constructor parameter** (`Query(sql, values, *, ignore_duplicated=False)`) and keep it a readable attribute. The builders pass it in; `mssql.py:256` / `oracle.py:263` keep reading `getattr(qry, "ignore_duplicated", False)`. **No test change is required** for these two assertions if the attribute stays readable — the test constructs via the builder.

**Include `ignore_duplicated` in `__eq__`/`__hash__`?** Yes. For MSSQL the SQL text is identical with and without the flag (`INSERT INTO t (a) VALUES (?)`), so excluding it would make two behaviorally different Queries compare equal and collide as cache keys (DATA-07). Flag this as an explicit decision for the planner.

**Accessor semantics (resolve the D-02 ambiguity explicitly):**
- `.sql` → the **compiled** SQL (`%(parameter_0000)s`), i.e. today's `query[0]`.
- `.params` → the `%(name)s → value` **dict**, i.e. today's `query[1]` (this is what `_to_postgres(sql, params)` needs).
- `.fields` → the raw input **list** (kept; `base.paginate:175` does `list(qry.fields)`).
- `.query` → read-only property returning a **fresh** `[sql, params]` list. Fresh, not cached, so a caller cannot mutate the internal state through it. The 6 adapters and 3 white-box tests (`test_postgresql.py:22`, `test_oracle.py:33`, `test_mssql.py:28`) keep working unchanged.
- `.with_params(values)` → returns a **new** `Query` with the same `sql_template`, re-validated cardinality, new values.

### Pattern 4: Database-free per-dialect snapshots

**What:** instantiate each adapter class (no `connect()`), call the builders, run `_prepare()` (pure regex translation), and assert the resulting SQL against a committed `.ambr` snapshot.

**Why it works with no database:** `MssqlDb()`, `OracleDb()`, `PostgresDb()` constructors only set `self._connection = None`; `insert()`/`update()`/`delete()` are pure; `_prepare()` only runs a regex. The repo already relies on this (`test_mssql.py:32-50`, `test_oracle.py:37-68` call builders and `_prepare` on unconnected adapters). `[VERIFIED: repo]`

**Recommended scope (the user's discretion, resolved):** snapshot **the shared builders' output for all six dialects**, covering `insert` (plain / `ignore_duplicated` / `replace`), `update`, `delete`, plus the count/paginate/list_tables SQL. Do **not** snapshot "all generated SQL" (brittle, unbounded) and do **not** limit it to `insert/update/delete` (that omits the exact bug class DIAL-03 fixes).

**Gate, not advisory.** Two operational caveats that must be in the plan:
1. syrupy **fails when a snapshot is missing** — the `.ambr` files must be committed in the same plan. Document the update workflow: `uv run pytest --snapshot-update -m syrupy_snapshot`.
2. syrupy detects **unused** snapshots and (by default) fails on them. Renaming or deleting a snapshot test orphans its entry and turns CI red. Decide explicitly: accept the strict default (forces cleanup) or add `--snapshot-warn-unused`. `[CITED: github.com/syrupy-project/syrupy]`

**Interaction risks to verify empirically during the plan** (both are cheap to test):
- `--strict-markers` is in `addopts`. syrupy registers its `syrupy_snapshot` marker via the plugin, so it should be fine — but confirm, because an unregistered marker under `--strict-markers` fails **collection**.
- `filterwarnings = ["error"]` is global. Confirm syrupy emits no warnings on the happy path.

### Pattern 5: Per-module coverage floor enforced by a stdlib script

`coverage.py` has **no per-file `fail_under`** — `[report] fail_under` is a single total percentage, verified in the official config reference. `[CITED: coverage.readthedocs.io/en/7.16.1/config.html]`

**Mechanism:** the `coverage` job already runs `coverage combine` + `coverage report`. Add `coverage json -o coverage.json` and run `python tools/ci/check_coverage_floors.py coverage.json`.

**Verified JSON schema** (ran `coverage json` locally):
```json
{
  "meta": {...},
  "files": { "m.py": { "summary": { "percent_covered": 75.0, "num_statements": 4, ... },
                        "executed_lines": [...], "missing_lines": [...], ... } },
  "totals": { "percent_covered": 85.71, ... }
}
```
`[VERIFIED: local coverage 7.16.1 run]`

**Proposed floors (start here, ratchet up):**

| Module | Floor | Justification |
|--------|-------|---------------|
| `encino_orm/dialects/identifiers.py` | 100 | Tiny, pure, security-critical. Accept/reject table is exhaustive. |
| `encino_orm/dialects/builders.py` | 95 | Pure; 6 strategies × 3 verbs + rejection paths. |
| `encino_orm/query.py` | 95 | Pure value object; sparse/duplicate/malformed `{n}` cases. |
| `encino_orm/dialects/strategies.py` | — | Data only (no statements); skip to avoid a vacuous floor. |
| Adapters (`sqlite/mysql/mariadb/postgresql/mssql/oracle`) | **measure after DIAL-08 lands**, then set at the measured value | A floor set before the engine jobs exist is a fiction: `oracle.py` measures 16% in the CI-equivalent run today because Oracle is deselected. |

**Fail-closed on a missing module.** If a module in the floor map is absent from `coverage.json`, the script must **fail**, not skip — otherwise deleting the file silently passes the gate. This is the anti-rot control that mirrors `warn_unused_ignores`.

**Path normalization.** Normalize `\` → `/` so the script behaves the same on the Windows dev host and on Linux CI.

### Pattern 6: Tiered multi-engine CI topology

**Recommendation (resolves the user's discretion):**

| Job | Python legs | Services | `ENCINO_ORM_REQUIRE_ENGINES` | Extras |
|-----|-------------|----------|------------------------------|--------|
| `test` (existing, extended) | 3.10–3.13 | mysql, postgres, **mariadb**, **redis** | `mysql,postgresql,mariadb,redis` | `--extra http --extra security --extra graphql --extra cache` |
| `engine-heavy` (NEW) | 3.12 only | **mssql**, **oracle** | `mssql,oracle` | `--extra mssql --extra oracle` |

Rationale:
- MariaDB and Redis are cheap (MariaDB ~10-20 s, Redis ~2 s) and belong on the same job so every Python leg exercises them. **Port conflict:** MySQL already maps `3306:3306`; MariaDB must map **`3307:3306`**, which matches the test default `ENCINO_ORM_MARIADB_PORT=3307`. `[VERIFIED: tests/test_mariadb.py:11, .github/workflows/ci.yml:36]`
- MSSQL (~1 GB RAM, 30-60 s) and Oracle (60-120 s cold start) must **not** be multiplied across four Python legs — dialect behavior does not vary by interpreter version. One leg, `timeout-minutes: 30`.
- The required-engine switch is **already extensible with zero code change**: `tests/conftest.py:26-29` splits `ENCINO_ORM_REQUIRE_ENGINES` on commas. `[VERIFIED: repo]` Phase 1 D-01 is satisfied.
- **Promoting an engine to required requires removing its `optional_engine` marker.** Today `tests/test_mariadb.py:52`, `tests/test_mssql.py:142`, `tests/test_oracle.py:112` and `tests/test_redis_cache.py:11` carry it, and the required job deselects those tests with `-m "not optional_engine"`. If MariaDB/Redis are promoted but the marker stays, the tests are silently deselected and the promotion is theater. `[VERIFIED: repo grep]`

**Hard prerequisite discovered — the MSSQL ODBC driver is NOT on the runner.**
The `ubuntu-24.04` runner image (Image Version 20260907.300.1) lists **no `unixodbc`, no `msodbcsql18`** in its installed apt packages, and its Databases section contains only sqlite3/PostgreSQL/MySQL. `pyodbc`/`aioodbc` cannot open a connection without them. The `engine-heavy` job therefore needs an explicit install step before the tests:
```yaml
- name: Instalar ODBC Driver 18 (SQL Server)
  run: |
    sudo apt-get update
    sudo apt-get install -y unixodbc-dev
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
      | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc >/dev/null
    curl -fsSL https://packages.microsoft.com/config/ubuntu/24.04/prod.list \
      | sudo tee /etc/apt/sources.list.d/mssql-release.list >/dev/null
    sudo apt-get update
    sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```
`[VERIFIED: raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md]`

**Second blocker discovered — the Oracle service name differs by image.**
`docker-compose.yml:33` uses `gvenzl/oracle-xe:21-slim` (service `XEPDB1`) and `tests/test_oracle.py:14` defaults to `XEPDB1`. The lighter, self-healthchecking CI image is `gvenzl/oracle-free` (service `FREEPDB1`). The `engine-heavy` job must set `ENCINO_ORM_ORACLE_SERVICE=FREEPDB1` (or use `oracle-xe` and accept the heavier image). `[VERIFIED: repo + STACK.md §Version Compatibility]`

**MSSQL service health check:** `mcr.microsoft.com/mssql/server:2022-latest` needs `ACCEPT_EULA=Y`, a complexity-compliant `MSSQL_SA_PASSWORD` (the repo default `Admin_123` qualifies), and a `sqlcmd`-based health check. `sqlcmd` lives at `/opt/mssql-tools18/bin/sqlcmd` in the 2022 image (the `-C` trust flag is needed for the self-signed cert). Budget `--health-retries: 20 --health-interval: 10s`.

**Do not use `continue-on-error: true`** for the heavy job — DIAL-08 requires the matrix to *cover* those engines; an advisory job is the Pitfall-1 failure mode (green CI verifying nothing). If runtime becomes a problem, gate the job on `push` to `main` + `workflow_dispatch` rather than making it advisory.

### Anti-Patterns to Avoid

- **Loosening `_IDENTIFIER_RE` to accept `schema.table`.** Re-opens the injection surface; explicitly forbidden by Pitfall 10. Use an explicit `schema=` parameter.
- **Applying validation in `Db.insert` only.** Pitfall 10's "Looks Done But Isn't" checklist: verify `update`, `delete`, all six dialects, **and** `sync_schema`.
- **Letting the shared builder drift from today's SQL.** Any whitespace/comma difference breaks the existing unit tests *and* freezes a change into the snapshots. Diff the generated strings before/after the refactor.
- **Mutating `Query` after construction.** `q.ignore_duplicated = True` is the pattern that must die with the immutability refactor; make it a constructor field.
- **Putting the identifier regex in `base.py` and calling it "centralized".** `base.py` is already an importer; the definition must live in `dialects/` so the builders can import it without a cycle.
- **Multiplying MSSQL/Oracle containers across the 4-leg matrix.** 4× the cold-start for zero extra dialect coverage.
- **Setting a per-dialect coverage floor before the engine jobs exist.** `oracle.py` measures 16% in today's CI-equivalent run; a floor set now is either vacuous or permanently red.
- **Treating syrupy as advisory.** A snapshot suite that does not fail on drift is decoration.
- **Using `testcontainers` in CI when `services:` suffices.** It adds `pymssql`+`sqlalchemy` for MSSQL and a Docker-socket dependency, for no coverage gain.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Snapshot/diff of generated SQL | A bespoke `golden/*.sql` comparison harness | `syrupy` 6.1.1 | Handles file layout, diff rendering, `--snapshot-update`, unused-snapshot detection, xdist locking. The repo's existing golden-string asserts stay as the *fast* unit layer. |
| Per-file coverage thresholds | A `pytest-cov` invocation per module, or `# pragma` gymnastics | `tools/ci/check_coverage_floors.py` over `coverage json` | The only mechanism that expresses "95% here, 70% there" in one run. Mirrors the already-proven `check_skips.py` (stdlib-only, fail-closed). |
| Engine readiness waits in CI | `sleep 60` before tests | GHA `services: options: --health-cmd/--health-retries` | Health checks poll the actual readiness signal; sleeps are either too short (flaky) or too long (slow). Oracle Free ships its own `HEALTHCHECK`. |
| Driver-level parameter-limit discovery | Guesswork in comments | Empirical probe tests in the engine jobs | asyncpg's 32767 is enforced in `prepared_stmt.pyx`; SQLite's 32766 was confirmed locally; MSSQL/Oracle must be measured where the engine actually runs. |
| A SQL parser to respect `{0}` inside string literals | A hand-rolled tokenizer | Regex + a documented limitation | D-04 locks the regex approach. Parsing is out of scope; document that `{n}` in a literal is unsupported and cover it with a test that records the behavior. |

**Key insight:** every "don't hand-roll" item here is a place where a bespoke implementation would *look* correct on SQLite and silently fail on the other five engines — which is precisely the bug class this phase exists to eliminate.

---

## Common Pitfalls

### Pitfall A: The identifier regex is duplicated six times and the call sites have two shapes
**What goes wrong:** 02-01 rewrites `base.py` and declares victory; `sqlite.py`, `mysql.py`, `transfer.py`, `model/model.py`, `model/types.py` keep their own copies; `sql.py:_COLUMN_RE` is either silently unified (behavior change) or forgotten. 02-02 then validates only in `base.py`'s builders and five dialects stay unvalidated.
**Why it happens:** the duplication is invisible in a diff review and the copies are byte-identical, so grep for the regex *value* returns everything and nothing looks wrong.
**How to avoid:** in 02-01, grep for **both** `_IDENTIFIER_RE` and `_check_identifier` and update all 7 files; add a test that asserts `len(re.findall(r"_IDENTIFIER_RE\s*=", <all sources>)) == 1` (a source-level single-definition guard, cheap and decisive). Leave `_COLUMN_RE` untouched and add a comment saying why.
**Warning signs:** `grep -rn "_IDENTIFIER_RE =" encino_orm/` returns more than one line after 02-01.

### Pitfall B: The validation commit is not actually separate, or not actually bisectable
**What goes wrong:** 02-01 and 02-02 land as one commit, or 02-02 also changes the regex/error message, so `git bisect` cannot isolate the security behavior change.
**How to avoid:** 02-01's commit must produce **zero** diff in any test outcome and **zero** diff in generated SQL; prove it by running the full suite before/after and diffing the snapshot files (which do not exist yet at 02-01 — so prove it with the existing golden-string tests). 02-02's commit adds only validation + the strategy seam.
**Warning signs:** 02-01 touches `dialects/builders.py`; 02-01's commit message contains "validate".

### Pitfall C: The `COUNT(*)` fix is applied to 3 sites and 4 remain broken
**What goes wrong:** DIAL-03 names `count`/`paginate`/`list_tables`, so `QueryBuilder.sum/avg/min/max` are left reading `row["SUM(col)"]` etc. They raise `KeyError` on PostgreSQL, MSSQL and Oracle — the *same* bug, the *same* three engines. The phase's own goal statement ("correct results on all six engines") is then false.
**Why it happens:** the requirement text enumerates three APIs; the code has seven readers.
**How to avoid:** fix all seven sites in 02-04:
`base.py:158` (list_tables), `model/model.py:795` (Model.count), `model/query_builder.py:246, 254, 263, 271, 279` (count/sum/avg/min/max). Copy the proven pattern from `base.py:175-177`: alias the expression `AS n`, read `row["n"]`. Add per-engine integration assertions for all five aggregate methods.
**Warning signs:** `grep -rn 'COUNT(\*)"\]' encino_orm/` is non-empty; any `row[f"SUM(`/`AVG(`/`MIN(`/`MAX(` remains.

### Pitfall D: The result-key fix is "solved" by normalizing keys in one adapter
**What goes wrong:** someone adds a dialect-aware key normalizer in `PostgresDb.fetch_one`. That is a band-aid: the labels differ *by expression*, not just by engine (`count` vs `count(*)` vs `COUNT(*)`), and `_rows_to_dicts` already lowercases MSSQL/Oracle. Normalizing in one adapter leaves the other five and every future aggregate exposed.
**How to avoid:** always alias at the SQL site (`AS n`). Do not add per-adapter key rewriting. The root cause is that the SQL asked for an unaliased expression and then indexed by the expression text.
**Warning signs:** a new `_normalize_keys` helper; `if engine == Engine.POSTGRESQL` inside a fetch path.

### Pitfall E: `Query` immutability breaks `ignore_duplicated` and the MERGE path
**What goes wrong:** `__slots__` (or a frozen dataclass) makes `q.ignore_duplicated = True` raise `AttributeError`. MSSQL/Oracle `execute()` then never suppresses unique violations on `ignore_duplicated=True` (because it reads `getattr(qry, "ignore_duplicated", False)` → always `False`), and two existing tests fail.
**Why it happens:** the attribute is set *after* construction in two adapters and is invisible in `Query.__init__`.
**How to avoid:** promote `ignore_duplicated` to a keyword-only constructor parameter; have the builders pass it; keep the attribute readable; include it in `__eq__`/`__hash__`.
**Warning signs:** `mssql.py`/`oracle.py` still assign `q.ignore_duplicated`; `test_mssql.py:41` / `test_oracle.py:48` fail.

### Pitfall F: Cardinality validation rejects the Oracle `RETURNING` bind or the paginate wrapper
**What goes wrong:** a naive "every `%(name)s` in the SQL must be in params" check (or a count of `:` in Oracle SQL) treats Oracle's output bind `:ret_id` as a missing parameter, or counts it as a placeholder. Also, `base.paginate:175` re-wraps `qry.sql_template` (which still contains `{n}`) with `list(qry.fields)` — a strict `set(indices) == set(range(len(params)))` check must accept that.
**Why it happens:** `:ret_id` is not a `{n}` placeholder and is added later by `execute()`; `%(...)s` is not the input contract.
**How to avoid:** validate **only** `re.findall(r"\{(\d+)\}", sql_template)` against `len(values)`. Never inspect `%(...)s` or `:name` at construction. Add an explicit test: Oracle's `insert` on a table without `id` passes validation despite the `RETURNING … INTO :ret_id` suffix.
**Warning signs:** `ValueError` on `OracleDb().insert("t", {"a": 1})`; `paginate` raising after the refactor.

### Pitfall G: Sparse/duplicate `{n}` semantics are guessed wrong
**What goes wrong:** "cardinality cuadra" is implemented as `max(index)+1 == len(values)`, which silently accepts unused params (the exact bug Pitfall 19 flags: "silently ignores parameters present in the dict but absent from the SQL") and rejects legitimate sparse use.
**Recommended semantics (explicit decision for the planner):** require `set(indices) == set(range(len(values)))` — every index is in range **and** every parameter is used at least once. Duplicate indices (`{0}` twice) are legal and bind the same value twice. Raise `ValueError` with the offending indices and the param count.
**Warning signs:** a test named "sparse indices accepted" that also passes with `Query("{0}", [1, 2])`.

### Pitfall H: The CI matrix is expanded but the optional markers are not removed
**What goes wrong:** MariaDB/Redis services are added and `ENCINO_ORM_REQUIRE_ENGINES` includes them, but `tests/test_mariadb.py:52` and `tests/test_redis_cache.py:11` still carry `optional_engine`, so `-m "not optional_engine"` deselects them. CI is green; the engines are still never tested. This is Pitfall 1 wearing a new hat.
**How to avoid:** promote = delete the marker **and** add the env vars **and** add the service **and** add the extra, in the same commit. Verify by the induced-failure test Phase 1 already established: remove the service → the job must fail, not skip.
**Warning signs:** the CI runtime does not grow after adding two engines; `13 deselected` still appears in the log.

### Pitfall I: syrupy's "fails on missing snapshot" turns a green suite red on first push
**What goes wrong:** the snapshot test is added but the `.ambr` files are generated on the dev's machine and not committed (or generated with a different syrupy version / line endings). CI fails with "snapshot does not exist".
**Why it happens:** syrupy is *sound* by design — a missing snapshot is a failure, not a skip. `[CITED: github.com/syrupy-project/syrupy]`
**How to avoid:** generate and commit the `.ambr` files in the same commit as the test; verify `.gitignore` does not exclude them (verified: it does not — only `.coverage*`, `htmlcov/`, `site/`, `.env`, `prompts/`, `*.db-*`); pin syrupy in `[dependency-groups].dev` (matching the `ruff==` pin rationale: formatting/serialization output is versioned); document `--snapshot-update -m syrupy_snapshot`.
**Warning signs:** `tests/__snapshots__/` missing from `git ls-files`.

### Pitfall J: The per-module coverage gate passes because the module vanished
**What goes wrong:** the script iterates the floor map and calls `.get(module)` → `None` → skips. Deleting `dialects/builders.py` (or renaming it) makes the gate pass vacuously.
**How to avoid:** fail closed on a missing module (mirror `check_skips.py:29-32`, which fails on an unreadable XML rather than treating it as zero).
**Warning signs:** the script has no `continue`-free branch for `entry is None`.

### Pitfall K: MSSQL/Oracle job fails at import, not at assertion
**What goes wrong:** `uv sync` without `--extra mssql --extra oracle` leaves `aioodbc`/`oracledb` unimportable; the fixtures' `except Exception` converts that to `engine_unavailable(...)` → hard fail (because required) but with a confusing import error, or worse a collection error if the module imports the driver at top level.
**Why it happens:** the fixtures intentionally keep a broad `except` (Phase 1 decision). The switch makes the failure hard, which is correct, but the message must be actionable.
**How to avoid:** the `engine-heavy` job must sync `--extra mssql --extra oracle` **and** install `msodbcsql18`/`unixodbc` before pytest. Consider narrowing the engine fixtures' `except` to the driver's connection error type (flagged in Phase 1 as Phase 2 follow-up) so an `ImportError` fails loudly with its real message.
**Warning signs:** `MssqlDb requiere el extra 'mssql'` in a job that claims to require MSSQL.

### Pitfall L: The refactor changes generated SQL subtly and the snapshots bless the change
**What goes wrong:** the shared builder emits `a, b` instead of `a,b`, or numbers `update` params differently, or drops Oracle's `RETURNING`. The existing golden-string tests catch most of this — **unless** they are updated in the same commit to match the new output, at which point the regression is laundered.
**How to avoid:** land 02-02 with **zero** changes to `test_postgresql.py`/`test_mssql.py`/`test_oracle.py`/`test_mysql.py`/`test_sqlite.py` builder assertions. If a test must change, that is a finding, not a fix. Generate the snapshots **after** 02-02 is green.
**Warning signs:** the 02-02 diff touches an existing SQL assertion.

---

## Code Examples

### `Query` — the target shape (DIAL-05)

```python
# Source: design derived from D-01…D-06 + the current encino_orm/query.py defects
import re

# Detección de placeholders REALES `{n}` (D-04). No es el sentinel `sql.find("{0}")`.
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


class Query:
    """Sentencia SQL + valores, inmutable y hashable.

    Contrato de entrada: `Query("… {0} … {1}", [v0, v1])`. Los índices pueden ser
    dispersos o repetidos, pero el conjunto de índices debe ser exactamente
    `range(len(values))`: ningún parámetro sin usar y ningún índice fuera de rango.

    Limitación conocida: un `{n}` dentro de un literal de cadena se interpreta
    como placeholder (no se parsean literales en esta versión).
    """

    __slots__ = ("sql_template", "fields", "ignore_duplicated", "_sql", "_params")

    def __init__(self, sql: str, fields: list, *, ignore_duplicated: bool = False):
        values = list(fields or [])
        indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}
        if indices and indices != set(range(len(values))):
            raise ValueError(
                f"placeholders {sorted(indices)} no cuadran con {len(values)} parámetros"
            )
        if indices and len(values) != max(indices) + 1:
            raise ValueError(
                f"faltan parámetros: índice máximo {max(indices)}, {len(values)} valores"
            )
        name = "parameter_000"
        params = {f"{name}{i}": v for i, v in enumerate(values)}
        compiled = _PLACEHOLDER_RE.sub(lambda m: f"%({name}{m.group(1)})s", sql)

        object.__setattr__(self, "sql_template", sql)
        object.__setattr__(self, "fields", values)
        object.__setattr__(self, "ignore_duplicated", ignore_duplicated)
        object.__setattr__(self, "_sql", compiled)
        object.__setattr__(self, "_params", params)

    @property
    def sql(self) -> str:
        """SQL compilado con placeholders intermedios `%(parameter_0000)s`."""
        return self._sql

    @property
    def params(self) -> dict:
        """Dict `%(name)s -> valor` que consume `_prepare` de cada adaptador."""
        return self._params

    @property
    def query(self) -> list:
        """Compatibilidad de lectura (D-02): `[sql_compilado, params]`. Lista nueva."""
        return [self._sql, self._params]

    def with_params(self, fields: list) -> "Query":
        """Devuelve una COPIA con nuevos valores (reemplaza al mutante `rebind`)."""
        return Query(self.sql_template, fields, ignore_duplicated=self.ignore_duplicated)

    def __eq__(self, other) -> bool:
        if not isinstance(other, Query):
            return NotImplemented
        return (
            self.sql_template == other.sql_template
            and self.fields == other.fields
            and self.ignore_duplicated == other.ignore_duplicated
        )

    def __hash__(self) -> int:
        try:
            return hash((self.sql_template, tuple(self.fields), self.ignore_duplicated))
        except TypeError as exc:
            raise TypeError(
                f"Query no hashable: hay un parámetro no hashable ({exc}). "
                "Usa una lista/tupla de valores inmutables o no uses Query como clave."
            ) from exc

    def __str__(self) -> str:
        return f"{self._sql}{self._params}"
```

**Notes on the sketch (the planner may adjust, but not the invariants):**
- The two cardinality checks together implement `set(indices) == set(range(len(values)))`; the second is redundant but gives a better message for the "index out of range" case. Simplify to one check if preferred.
- `_PLACEHOLDER_RE.sub` with a callable replaces **all** occurrences, including duplicates — `{0}` twice becomes the same `%(parameter_0000)s` twice, which is correct.
- Empty `fields` and no placeholders → `compiled == sql`, `params == {}` — matching today's `[sql, {}]` for the no-placeholder path.
- `__slots__` deliberately excludes `__dict__`, so a typo'd attribute assignment raises — this is the immutability guarantee.

### `dialects/identifiers.py` (02-01, pure move)

```python
# Source: consolidated verbatim from encino_orm/base.py:13,61-65 and transfer.py:16-23
import re

# Allowlist estricta: identificador simple, sin esquema, sin comillas, ASCII.
# NO se relaja para aceptar `schema.tabla` (Pitfall 10): el esquema se valida
# aparte con el parámetro `schema=` de los builders.
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_identifier(value: str, label: str) -> str:
    """Valida que `value` sea un identificador SQL seguro antes de interpolarlo."""
    if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
        raise ValueError(f"{label} inválido: {value!r}")
    return value
```

`Db._check_identifier` becomes a one-line delegate so the five adapters that call `self._check_identifier(...)` are untouched:

```python
# encino_orm/base.py (after 02-01)
from .dialects.identifiers import check_identifier

class Db(ABC):
    @staticmethod
    def _check_identifier(value: str, label: str) -> str:
        return check_identifier(value, label)
```

### `dialects/builders.py` — the `schema=` policy (02-02)

```python
# Source: policy derived from Pitfall 10 + sql.py:_COLUMN_RE precedent
def _qualified(table: str, schema: str | None) -> str:
    """Valida y compone `tabla` o `esquema.tabla`. Nunca relaja la allowlist."""
    table = check_identifier(table, "tabla")
    if schema is None:
        return table
    return f"{check_identifier(schema, 'esquema')}.{table}"
```

Signature change (keyword-only, so positional callers such as
`pool.insert(tabla, data, ignore_duplicated, replace)` are unaffected):

```python
def build_insert(table, data, *, strategy, conflict=None, replace=False,
                 ignore_duplicated=False, schema=None) -> Query: ...
def build_update(table, keys, values, *, schema=None) -> Query: ...
def build_delete(table, keys, *, schema=None) -> Query: ...
```

### Spy-rejection test (the difference between validation and theater)

```python
# Source: repo convention — hand-written fakes + monkeypatch, never unittest.mock
import pytest
from encino_orm import SqliteDb, MysqlDb, MariadbDb, PostgresDb, MssqlDb, OracleDb

ADAPTERS = [SqliteDb, MysqlDb, MariadbDb, PostgresDb, MssqlDb, OracleDb]
MALICIOUS = ["t; DROP TABLE x; --", "`x`", "a.b", "1abc", "", "a b", "a-b"]


@pytest.mark.parametrize("cls", ADAPTERS)
@pytest.mark.parametrize("bad", MALICIOUS)
def test_builders_reject_before_driver(cls, bad, monkeypatch):
    db = cls()  # sin connect(): los builders son puros
    reached = []
    monkeypatch.setattr(db, "_prepare", lambda qry: reached.append(qry) or ("", []))

    with pytest.raises(ValueError):
        db.insert(bad, {"a": 1})
    with pytest.raises(ValueError):
        db.update("t", {bad: 1}, {"a": 1})
    with pytest.raises(ValueError):
        db.delete("t", {bad: 1})
    with pytest.raises(ValueError):
        db.insert("t", {bad: 1})

    assert reached == [], "el driver fue alcanzado pese al ValueError"
```

> Note: the repo's `tests/**` ruff ignores already include `PT011` (broad `pytest.raises`), so `pytest.raises(ValueError)` is fine. `@pytest.mark.parametrize` is **not** used anywhere in this repo today (TESTING.md: "There is no `@pytest.mark.parametrize` usage"). The planner may either introduce it (it is not forbidden) or write six explicit per-adapter test classes to match the established per-engine-file convention. **Recommendation: use explicit per-adapter tests in the existing per-engine files**, plus one shared `tests/test_identifiers.py` for the pure function. This keeps the established "engine coverage via separate files" pattern and keeps the rejection evidence next to each engine.

### `tools/ci/check_coverage_floors.py` (02-05)

```python
"""Gate de pisos de cobertura POR MODULO sobre `coverage json` (D-04/D-06 de Fase 1).

`coverage.py` no soporta `fail_under` por fichero: `[report] fail_under` es un
unico total (verificado en la doc oficial). Este script lee el JSON y aplica un
piso por modulo. Falla cerrado si un modulo del mapa no aparece en el reporte:
borrar el fichero no puede convertir el gate en verde.
"""

import json
import sys

FLOORS = {
    "encino_orm/dialects/identifiers.py": 100.0,
    "encino_orm/dialects/builders.py": 95.0,
    "encino_orm/query.py": 95.0,
    # Los pisos de adaptador se fijan DESPUES de DIAL-08 (la matriz debe existir
    # antes que el numero): en la corrida equivalente a CI oracle.py mide 16%.
}


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    path = argv[1] if len(argv) > 1 else "coverage.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FALLO: no se pudo leer {path!r}: {exc}", file=sys.stderr)
        return 1

    files = {_norm(k): v for k, v in data.get("files", {}).items()}
    failures = []
    for module, floor in FLOORS.items():
        entry = files.get(module)
        if entry is None:
            failures.append(f"{module}: AUSENTE del reporte (piso {floor}%)")
            continue
        actual = entry["summary"]["percent_covered"]
        if actual < floor:
            failures.append(f"{module}: {actual:.1f}% < piso {floor}%")

    if failures:
        for line in failures:
            print(f"FALLO: {line}", file=sys.stderr)
        return 1
    print(f"OK: {len(FLOORS)} modulo(s) cumplen su piso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

### `tests/test_sql_snapshots.py` — DB-free, 6 dialects (02-05)

```python
# Source: syrupy 6.x README (assert actual == snapshot) + repo's unconnected-adapter tests
import pytest

from encino_orm import MariadbDb, MssqlDb, MysqlDb, OracleDb, PostgresDb, SqliteDb

ADAPTERS = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "mariadb": MariadbDb,
    "postgresql": PostgresDb,
    "mssql": MssqlDb,
    "oracle": OracleDb,
}


@pytest.mark.parametrize(("dialect", "cls"), ADAPTERS.items())
def test_insert_sql_snapshot(dialect, cls, snapshot):
    db = cls()  # sin connect()
    sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
    assert {"sql": sql, "values": values} == snapshot


@pytest.mark.parametrize(("dialect", "cls"), ADAPTERS.items())
def test_insert_ignore_duplicated_snapshot(dialect, cls, snapshot):
    db = cls()
    sql, values = db._prepare(db.insert("t", {"a": 1}, ignore_duplicated=True))
    assert {"sql": sql, "values": values} == snapshot
```

Plus `update`, `delete`, `replace`, and the count/paginate/list_tables SQL strings. Snapshots land in `tests/__snapshots__/test_sql_snapshots.ambr` and are committed.

> If the repo's "no `parametrize`" convention is treated as binding, expand this into six functions per operation instead. The planner should pick one and be consistent with the rest of the phase.

### Empirical parameter-limit probe (for the engine jobs)

```python
# Source: probe recipe validated locally on SQLite 3.50.4 / asyncpg 0.31.0
import sqlite3

# SQLite: SQLITE_MAX_VARIABLE_NUMBER. Medido localmente (3.50.4): 32766 OK,
# 32768 -> "too many SQL variables".
con = sqlite3.connect(":memory:")
con.execute("CREATE TABLE t (" + ",".join(f"c{i} INTEGER" for i in range(8)) + ")")
rows = 32766 // 8
sql = ("INSERT INTO t (" + ",".join(f"c{i}" for i in range(8)) + ") VALUES "
       + ",".join(["(" + ",".join(["?"] * 8) + ")"] * rows))
con.execute(sql, list(range(rows * 8)))  # OK
```

For MSSQL/Oracle, the equivalent probe belongs in the `engine-heavy` job and should assert the **measured** ceiling before the constants are frozen.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Six copy-pasted `insert/update/delete` per adapter | One shared builder + strategy object | This phase | A validation or correctness fix lands once and reaches six engines. |
| `Query` mutable with `rebind()` | `Query` immutable with `with_params()` | This phase (D-01) | Enables a real cache key (DATA-07) and removes a whole class of aliasing bugs. |
| `sql.find("{0}")` sentinel | Regex over real `{n}` occurrences + cardinality validation | This phase (D-04) | Sparse/duplicate indices work; unused params raise instead of being silently dropped. |
| Aggregate reads by expression text (`row["COUNT(*)"]`) | Aliased reads (`AS n` → `row["n"]`) | This phase (DIAL-03) | Correct on all six engines; the failure mode is engine-independent. |
| No dialect SQL regression coverage | Committed syrupy `.ambr` snapshots, DB-free | This phase (DIAL-07) | Dialect drift is caught in seconds on the always-on job. |
| One global coverage number | Global ratchet + per-module floors over `coverage json` | This phase (Phase 1 D-04/D-06) | Dialect modules can no longer hide behind SQLite's coverage. |
| Two required engines (MySQL, PostgreSQL) | Four required on the main job + a dedicated MSSQL/Oracle job | This phase (DIAL-08) | Parity is proven, not asserted. |

**Deprecated/outdated in this phase:**
- `Query.rebind()` — removed outright (D-01). Only `docs/design/0-design.md` documents it; `docs/design/0-design.md:22,35,66,87,397` must be updated (D-05).
- The duplicated `_IDENTIFIER_RE` / `_check_identifier` definitions in 7 files — collapsed to one (DIAL-01).
- The per-adapter `insert/update/delete` bodies — replaced by `_insert_strategy` hooks (DIAL-02).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Oracle's bind-variable ceiling per statement is 65535 and its `IN`-list ceiling is 1000 (ORA-01795) | Standard Stack / Pitfall (constants) | `MAX_PARAMS` for Oracle would be too high → runtime errors on wide `copy_table` batches (Phase 7). **Mitigation: probe in the `engine-heavy` job before freezing the constant.** |
| A2 | SQL Server's 2100-parameter cap applies to ad-hoc parameterized statements (not only stored procedures/UDFs) | Pitfall (constants) | `MAX_PARAMS=2100` for MSSQL would be too conservative (harmless) or, if the real ad-hoc cap is lower, batches would fail. The Microsoft capacity page documents 2100 for stored procedures and UDFs; the ad-hoc cap is the TDS RPC limit and is driver-enforced. **Mitigation: probe in the `engine-heavy` job.** |
| A3 | `MAX_ROWS` values (1000 default) | Pitfall (constants) | Too high → statement-size/compound-select errors on some engines. Empirically, SQLite 3.50.4 accepted a 1000-row multi-row `VALUES` (2000 params), **refuting** the PITFALLS.md claim that `SQLITE_MAX_COMPOUND_SELECT=500` limits multi-row `VALUES`. Keep `MAX_ROWS` conservative and derive batch size from `MAX_PARAMS // n_columns` first. |
| A4 | syrupy's `syrupy_snapshot` marker does not collide with `--strict-markers`, and syrupy emits no warnings under `filterwarnings = ["error"]` | Pattern 4 | Collection error or a red suite on the first snapshot run. **Mitigation: verify in the first plan task that adds syrupy.** |
| A5 | `mcr.microsoft.com/mssql/server:2022-latest` + `sqlcmd` at `/opt/mssql-tools18/bin/sqlcmd` for the health check | Pattern 6 | Health check never turns healthy → job times out. **Mitigation: use `sqlcmd -C` and 20 retries; fall back to a TCP port check if the path differs.** |
| A6 | `gvenzl/oracle-free` uses service `FREEPDB1` | Pattern 6 | Oracle tests fail to connect. **Mitigation: set `ENCINO_ORM_ORACLE_SERVICE=FREEPDB1` explicitly, or keep `oracle-xe` + `XEPDB1`.** |
| A7 | The identifier policy (strict allowlist + `schema=`) is acceptable to users | Pattern 2 | A user with quoted/non-ASCII identifiers is pushed to raw `Query`. **Mitigation: document the policy and the escape hatch in `MIGRATION-0.3.md`; consider dialect-aware quoting in a later phase.** |
| A8 | The `set(indices) == set(range(len(values)))` cardinality rule is the intended reading of "cardinalidad cuadra" | Pitfall G | Legitimate `Query` call sites that pass extra unused params would start raising. **Mitigation: grep the repo for such call sites before landing (the search found none), and cover the rule with a test.** |

**If this table is empty:** it is not — the six items above need either an empirical probe (A1, A2, A3) or a cheap verification (A4) before the corresponding constants/snapshots are frozen.

---

## Open Questions

1. **What exactly are Oracle's and MSSQL's ad-hoc parameter ceilings?**
   - What we know: asyncpg 32767 (verified in source), SQLite 32766 (verified empirically), MSSQL 2100 (official, stored-proc/UDF context).
   - What's unclear: the ad-hoc-statement caps that `MAX_PARAMS` actually governs.
   - Recommendation: land the constants with documented provenance, then have the `engine-heavy` job run a probe test that measures the real ceiling and asserts it; adjust the constants from the measured value. This is a Phase 2 deliverable (DIAL-06), not a Phase 7 one — Phase 7 only *consumes* them.

2. **Should the `engine-heavy` job run on every PR or only on `main`?**
   - What we know: Oracle cold start is 60-120 s; the job will add ~3-5 min to every PR.
   - What's unclear: the project's tolerance for CI latency on PRs.
   - Recommendation: run on PR + push with `timeout-minutes: 30`. If it becomes painful, move to `main`-only + `workflow_dispatch` — but never make it advisory.

3. **Does `Query.__hash__` include `ignore_duplicated`?**
   - What we know: for MSSQL the SQL text is identical with and without the flag; behavior differs.
   - Recommendation: include it (correctness over minimalism). If the planner disagrees, the reasoning must be recorded, because DATA-07 will use this hash as a cache key.

4. **Should `QueryBuilder.sum/avg/min/max` be fixed in this phase?**
   - What we know: DIAL-03 names only `count`/`paginate`/`list_tables`; the four aggregate methods have the identical defect.
   - Recommendation: yes, fix all seven in 02-04 and add per-engine assertions. Record the scope addition in the plan and the traceability table.

5. **Do the six adapter `S608` per-file-ignores shrink after the seam?**
   - What we know: the adapters still interpolate in `columns_of` (`PRAGMA table_info({table})`, `SHOW COLUMNS FROM {table}`) and `migrate`.
   - Recommendation: keep them in this phase; add `"encino_orm/dialects/builders.py" = ["S608"]`. Note the ratchet opportunity (e.g. `mariadb.py`'s `S608` is arguably removable) but do not force it.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| CPython | Everything | ✓ | 3.10.18 (`.venv`) | — |
| `uv` | Dependency management, `uv sync --extra …` | ✓ | 0.12.15 | — |
| `pytest` / `pytest-asyncio` / `pytest-cov` / `coverage` | Test + coverage gates | ✓ | 9.1.1 / 1.4.0 / 7.1.0 / 7.16.1 | — |
| `ruff` | Lint gate (new modules must pass) | ✓ | 0.16.8 | — |
| `mypy` | Type gate (new modules checked strictly) | ✓ | 2.3.1 | — |
| `syrupy` | DIAL-07 snapshots | ✗ | — | **None — must be added to `[dependency-groups].dev`** (gate behind a package-legitimacy checkpoint) |
| `docker` | Local multi-engine integration | ✓ | 29.7.2 | CI uses GHA `services:` |
| `oracledb` | Oracle adapter + `testcontainers[oracle-free]` | ✓ | 4.0.2 (`uv.lock`) | Satisfies the extra's `>=3` — the STACK.md "major-version bump risk" is **already resolved** in the lockfile |
| `asyncpg` | PostgreSQL adapter | ✓ | 0.31.0 | — |
| `aiomysql` | MySQL/MariaDB adapters | ✓ | (core dep) | — |
| `aioodbc` + `pyodbc` | MSSQL adapter | ✓ in venv (extra) | 0.5.0 / 5.3.0 | — |
| **ODBC Driver 18 for SQL Server** | MSSQL **on the CI runner** | ✗ on `ubuntu-latest` | — | **None — an explicit apt install step is mandatory** (see Pattern 6) |
| ODBC Driver 18 (Windows dev host) | Local MSSQL tests | not verified this session | — | Local MSSQL tests skip without it |
| `testcontainers` | Optional local provisioning | ✗ (installed only at user level by the slopcheck gate) | 4.15.0 | Not required — CI uses `services:` |
| `slopcheck` | Package-legitimacy gate | ✓ (`python -m slopcheck`) | installed this session | — |

**Missing dependencies with no fallback:**
- `syrupy` — blocks DIAL-07. Must be added (checkpoint-gated).
- **ODBC Driver 18 on the CI runner** — blocks DIAL-08's MSSQL leg. Must be installed in the job.

**Missing dependencies with fallback:**
- `testcontainers` — optional; GHA `services:` is the recommended CI path.
- Local MSSQL ODBC driver — local MSSQL tests skip; CI is the authoritative run.

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` in `.planning/config.json` — section included.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest `9.1.1` + pytest-asyncio `1.4.0` (`asyncio_mode = "auto"`, both loop scopes `function`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (hardened in Phase 1: `--strict-markers`, `xfail_strict`, `filterwarnings = ["error"]`, 4 markers) |
| Quick run command | `uv run pytest -q -m "not integration and not optional_engine"` |
| Full suite command | `uv run pytest -q` (with engines available) / CI-equivalent: `uv run pytest -q -m "not optional_engine" --junitxml=junit.xml --cov=encino_orm --cov-branch --cov-report=` |
| Snapshot update | `uv run pytest --snapshot-update -m syrupy_snapshot` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DIAL-01 | `_IDENTIFIER_RE`/`check_identifier` defined once; all 6 adapters import it; behavior unchanged | unit + source-level guard | `uv run pytest tests/test_identifiers.py -x` | ❌ Wave 0 |
| DIAL-01 | Pure-refactor proof: existing suite passes with zero test edits | regression | `uv run pytest -q` | ✅ (existing) |
| DIAL-02 | Each of the 6 adapters rejects a malicious table/column with `ValueError` **before** `_prepare` is called | unit + spy | `uv run pytest tests/test_dialect_builders.py -x` | ❌ Wave 0 |
| DIAL-02 | Generated SQL is byte-identical to today's for all 6 dialects × 3 verbs × 3 modes | regression | `uv run pytest tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py tests/test_mysql.py tests/test_sqlite.py -x` | ✅ (existing) |
| DIAL-03 | `count`/`paginate`/`list_tables` + `sum/avg/min/max` return correct values on PG/MSSQL/Oracle | integration | `uv run pytest tests/test_postgresql.py -k "count or paginate or list_tables or aggregate" -x` (per engine file) | ❌ Wave 0 (assertions) |
| DIAL-03 | SQLite unit: the generated count SQL contains `AS n` | unit | `uv run pytest tests/test_aggregates.py -x` | ✅ (extend) |
| DIAL-04 | `sync_schema` rejects a catalog-derived malicious column name before any `ALTER TABLE` reaches the driver | unit + spy | `uv run pytest tests/test_migrations.py -k sync_schema -x` | ✅ (extend) |
| DIAL-05 | Immutability: attribute assignment raises; `with_params()` returns a new object; original unchanged | unit | `uv run pytest tests/test_query.py -x` | ❌ Wave 0 |
| DIAL-05 | Sparse indices, duplicate indices, unused params, out-of-range index | unit | `uv run pytest tests/test_query.py -x` | ❌ Wave 0 |
| DIAL-05 | `__hash__` raises `TypeError` on an unhashable param; equal Queries hash equal | unit | `uv run pytest tests/test_query.py -x` | ❌ Wave 0 |
| DIAL-05 | `rebind` no longer exists | unit | `uv run pytest tests/test_query.py -k rebind -x` (asserts `not hasattr`) | ❌ Wave 0 |
| DIAL-06 | Each of the 6 dialects exposes `MAX_PARAMS`/`MAX_ROWS`; `insert_many`'s chunk derives from them | unit | `uv run pytest tests/test_engine.py -k max_params -x` | ✅ (extend) |
| DIAL-07 | 6 dialects × DML + count/paginate/list_tables SQL match committed `.ambr` snapshots, no DB | unit (snapshot) | `uv run pytest tests/test_sql_snapshots.py -x` | ❌ Wave 0 |
| DIAL-08 | Removing MariaDB/Redis/MSSQL/Oracle from a required job makes it **fail**, not skip | CI induced failure | remove the service in a throwaway branch → job red | ✅ (Phase 1 switch) |
| DIAL-08 | `skipped == 0` in every required-engine job | CI gate | `uv run python tools/ci/check_skips.py junit.xml` | ✅ (existing) |
| DIAL-09 | Per-engine integration coverage for count/paginate/list_tables/sync_schema/last_id | integration | `uv run pytest tests/test_<engine>.py -x` | ❌ Wave 0 (assertions) |
| (Phase 1 D-04/D-06) | Per-module coverage floors enforced | CI gate | `uv run coverage json -o coverage.json && uv run python tools/ci/check_coverage_floors.py coverage.json` | ❌ Wave 0 (script) |

### Sampling Rate
- **Per task commit:** `uv run pytest -q -m "not integration and not optional_engine"` (fast, DB-free) + `uv run ruff check encino_orm tests` + `uv run mypy encino_orm`
- **Per wave merge:** `uv run pytest -q -m "not optional_engine"` (adds MySQL/PostgreSQL/MariaDB/Redis where available) + `uv run coverage report`
- **Phase gate:** full suite green on all required engines, snapshots committed, coverage floors passing, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_identifiers.py` — accept/reject table for the pure checker (DIAL-01)
- [ ] `tests/test_dialect_builders.py` — 6 adapters × malicious names, spy asserts `_prepare` never called (DIAL-02)
- [ ] `tests/test_query.py` — immutability, `with_params`, sparse/duplicate/unused/out-of-range `{n}`, hash/eq (DIAL-05)
- [ ] `tests/test_sql_snapshots.py` + `tests/__snapshots__/*.ambr` — 6 dialects × DML + count/paginate/list_tables (DIAL-07)
- [ ] `tools/ci/check_coverage_floors.py` — per-module floor over `coverage.json` (Phase 1 D-04/D-06)
- [ ] Extend `tests/test_<engine>.py` × 6 with count/paginate/list_tables/sync_schema/last_id assertions (DIAL-03, DIAL-09)
- [ ] Extend `tests/test_engine.py` (or a new `tests/test_dialect_constants.py`) with the `MAX_PARAMS`/`MAX_ROWS` assertions (DIAL-06)
- [ ] Framework install: `uv add --dev syrupy` — **gated behind a `checkpoint:human-verify`** (slopcheck `[SUS]`)
- [ ] CI: extend the `test` job (mariadb + redis services, `--extra cache`, remove `optional_engine` markers from those two files); add the `engine-heavy` job (mssql + oracle, ODBC install step, `FREEPDB1`); add `coverage json` + the floors script to the `coverage` job

*(If no gaps: "None — existing test infrastructure covers all phase requirements")* — **not the case; eight Wave 0 items.**

---

## Security Domain

> `security_enforcement` is enabled (absent from config ⇒ enabled). Section included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Out of scope (Phase 6 / `security/`) |
| V3 Session Management | no | Out of scope (Phase 6) |
| V4 Access Control | no | Out of scope (Phase 6) |
| V5 Input Validation | **yes** | Strict allowlist `^[A-Za-z_][A-Za-z0-9_]*$` for every interpolated identifier; bound parameters for every value (never string-formatted); explicit `schema=` parameter validated separately; catalog-derived names validated before `ALTER TABLE` |
| V6 Cryptography | no | No crypto in this phase (the only hash is `Query.__hash__`, a cache key, not a security primitive) |
| V7 Error Handling & Logging | yes (light) | `ValueError` messages include the offending value via `!r` (existing convention); no SQL/params are added to error text beyond what already exists |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via a table/column name interpolated into DML | Tampering | Strict allowlist at the single seam (`dialects/identifiers.py`); validation **before** any SQL string is built; spy test asserts the driver is never reached |
| SQL injection via a catalog-derived column name interpolated into `ALTER TABLE` | Tampering | Validate `sync_schema`'s catalog-derived names with the same checker; the database is an untrusted input source |
| SQL injection via the `schema` qualifier | Tampering | Validate `schema` with the same allowlist — never concatenate an unvalidated schema |
| Injection via "loosening the regex to support `schema.table`" | Tampering | Forbidden by policy; an explicit `schema=` parameter instead. Widening the character class re-opens the surface |
| Injection via `Filter.raw`, raw `Query`, `db.fn.*` | Tampering | Documented trusted-input-only boundaries (CFG-05, Phase 6). This phase must **not** route untrusted data through them; the `schema=` policy exists precisely so users do not fall back to raw SQL |
| Validation that silently misses five of six dialects | Tampering / Repudiation | Centralize first (02-01) then validate (02-02) as separate commits; a source-level guard test asserts a single regex definition; per-adapter rejection tests |
| Injection linting becoming decoration (`# nosec` rot) | — | ruff `S` rules stay enabled; the only new `S608` ignore is on the centralized builder module (the trust boundary is documented there); the existing `noqa` count invariant (`noqa=0`) from Phase 1 is preserved |
| Secrets/credentials leaking through the new CI job | Information Disclosure | The `engine-heavy` job uses GHA service-container env values (dev-only passwords already in `docker-compose.yml`); no new repository secret is introduced; the OIDC/publish work is Phase 8 |

**Trust boundary statement to record (feeds CFG-05 in Phase 6):** after this phase, `Db.insert/update/delete` are **safe for untrusted table/column names** (allowlist + explicit schema) but their **values** are always bound, never interpolated. `Query`, `Filter.raw` and `db.fn.*` remain **trusted-input-only**. That distinction is the phase's security deliverable.

---

## Sources

### Primary (HIGH confidence)
- **Repository read directly (2026-09-18):** `encino_orm/query.py` (sentinel at :7, `format` at :12-26, `rebind` at :28-31); `encino_orm/base.py` (`_IDENTIFIER_RE:13`, `_check_identifier:61`, `list_tables` COUNT at :158, correct `AS n` at :175-177); `encino_orm/sqlite.py` (`_IDENTIFIER_RE:13`, builders :133-172, `_prepare:105`); `encino_orm/mysql.py` (`_IDENTIFIER_RE:15`, builders :149-189); `encino_orm/mariadb.py` (subclass); `encino_orm/postgresql.py` (builders :154-195, `_prepare:120`); `encino_orm/mssql.py` (`ignore_duplicated` set at :223, read at :256, MERGE at :210-216); `encino_orm/oracle.py` (`ignore_duplicated` set at :225, `RETURNING` at :221, MERGE at :210-216, `_to_oracle` named binds); `encino_orm/model/model.py` (`_IDENTIFIER_RE:29`, `_build_column_map:223-238`, `count:793-795`, `insert_many` `chunk=500` at :512, `sync_schema` ALTER sites :894, :902, :913, :917); `encino_orm/model/query_builder.py` (aggregate readers :244-279); `encino_orm/model/types.py` (`_IDENTIFIER_RE:201`); `encino_orm/transfer.py` (`_IDENTIFIER_RE:16`, `_check_identifier:19`); `encino_orm/sql.py` (`_COLUMN_RE:8` allows dots); `encino_orm/_rows.py` (lowercases column names at :14); `encino_orm/pool.py` (`sql_template` at :246, builders at :180-187); `encino_orm/model/records.py` (`MAX_LIMIT=1000`); `encino_orm/__init__.py` (`__all__`); `pyproject.toml` (ruff/mypy/coverage/pytest config, per-file-ignores, mypy ratchet); `.github/workflows/ci.yml` (5 jobs, MySQL 3306 + PostgreSQL 5432 services, `timeout-minutes: 15`, `-m "not optional_engine"`, `check_skips.py` gate); `tests/conftest.py` (`required_engines`/`engine_unavailable`); `tools/ci/check_skips.py` (fail-closed stdlib gate); `tests/test_postgresql.py:20-57`, `tests/test_mssql.py:23-50`, `tests/test_oracle.py:31-68`, `tests/test_mariadb.py:10-52`, `tests/test_redis_cache.py:10-11`; `.gitignore`; `uv.lock` (`oracledb 4.0.2`, `asyncpg 0.31.0`); `.planning/**` (CONTEXT, ROADMAP, REQUIREMENTS, STATE, research/, codebase/, Phase 1 CONTEXT + VERIFICATION).
- **Empirical local probes (2026-09-18):** SQLite 3.50.4 via `.venv` Python — `SQLITE_MAX_VARIABLE_NUMBER`: 32766 OK / 32768 → `too many SQL variables`; a 1000-row multi-row `VALUES` (2000 params) **succeeded** (refutes the `SQLITE_MAX_COMPOUND_SELECT=500` multi-row claim); `coverage json` schema confirmed (`files[path].summary.percent_covered`).
- **Installed driver source:** `asyncpg 0.31.0` — `protocol/prepared_stmt.pyx:130-132`: `if len(args) > 32767: raise … 'the number of query arguments cannot exceed 32767'`.
- **Microsoft Learn — Maximum Capacity Specifications for SQL Server** (updated 2026-07-20): "Parameters per stored procedure 2,100", "Parameters per user-defined function 2,100": https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server
- **SQLite — Implementation Limits For SQLite** (updated 2026-07-10): `SQLITE_MAX_VARIABLE_NUMBER` 999 pre-3.32 / 32766 after; `SQLITE_MAX_COMPOUND_SELECT` 500; `SQLITE_MAX_COLUMN` 2000: https://www.sqlite.org/limits.html
- **coverage.py 7.16.1 — Configuration reference:** `[report] fail_under` is a single total; `[json] output`; `[paths]`; `[run] parallel`: https://coverage.readthedocs.io/en/7.16.1/config.html
- **syrupy README (syrupy-project/syrupy, main):** 6.x requires Python ≥3.10 / pytest ≥8; `snapshot` fixture; `assert actual == snapshot`; `--snapshot-update`; `__snapshots__/*.ambr`; "will fail a test suite if a snapshot does not exist"; unused-snapshot detection; `--snapshot-warn-unused`; `syrupy_snapshot` marker: https://github.com/syrupy-project/syrupy
- **actions/runner-images — Ubuntu 24.04 README** (Image Version 20260907.300.1): no `unixodbc`/`msodbcsql18` in the installed apt packages or Databases section: https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md
- **PyPI JSON API (2026-09-18):** `syrupy 6.1.1` (`requires_dist: pytest>=8.0.0`); `testcontainers 4.15.0` (`pymssql>=2` + `sqlalchemy` for `[mssql]`; `oracledb>=3` for `[oracle]`/`[oracle-free]`).
- **slopcheck gate (run this session):** `testcontainers` `[OK]`; `syrupy` `[SUS]` — name-similarity false positive vs `scrapy`.

### Secondary (MEDIUM confidence)
- Oracle's 1000-expression `IN`-list cap (ORA-01795) and 65535 bind-variable ceiling — widely documented but **not re-fetched from official Oracle docs in this session**; flagged A1 and to be probed in the `engine-heavy` job.
- SQL Server's 2100-parameter cap for **ad-hoc** parameterized statements (as opposed to stored procedures/UDFs, which the Microsoft page documents directly) — flagged A2.
- GHA `services:` vs `testcontainers` for heavy engines — reasoned recommendation, not a documented consensus (matches STACK.md's own MEDIUM rating).
- Oracle/MSSQL container readiness times and the `sqlcmd` path — to be measured once and pinned.

### Tertiary (LOW confidence)
- None relied upon for a decision. Every LOW/uncertain item is listed in the Assumptions Log with a mitigation.

---

## Metadata

**Confidence breakdown:**
- **Standard stack:** HIGH — syrupy 6.1.1 and testcontainers 4.15.0 verified on PyPI + official repo; slopcheck executed; the coverage-json mechanism verified by running it.
- **Architecture:** HIGH on the seam shape and the `Query` design (derived from locked decisions + direct code reading, with the byte-identical-SQL constraint enumerated from the existing assertions); MEDIUM on the CI topology (a reasoned recommendation, not a documented consensus).
- **Pitfalls:** HIGH on the code-level findings (all verified by reading the repo) and on the SQLite/asyncpg ceilings (empirically verified); MEDIUM on the Oracle/MSSQL ad-hoc ceilings.

**Research date:** 2026-09-18
**Valid until:** 2026-10-18 (30 days) for the design; **the engine/CI topology should be re-checked after the first `engine-heavy` run**, and the `MAX_PARAMS`/`MAX_ROWS` constants must be re-derived from that run's probe results rather than trusted from this document.

**Handoff note for the planner:** the single highest-value action is to land 02-01 (pure centralization) with **zero** other changes and prove it by the existing suite passing unedited. The single highest-risk action is 02-02 (the builder seam) — its acceptance criterion is *byte-identical generated SQL*, enforced by the pre-existing golden-string tests plus the new snapshots. Do not reorder these.
