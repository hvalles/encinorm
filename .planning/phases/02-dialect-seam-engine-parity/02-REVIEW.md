---
phase: 02-dialect-seam-engine-parity
reviewed: 2026-09-18T05:03:01Z
depth: deep
files_reviewed: 34
files_reviewed_list:
  - encino_orm/dialects/__init__.py
  - encino_orm/dialects/identifiers.py
  - encino_orm/dialects/builders.py
  - encino_orm/dialects/strategies.py
  - encino_orm/query.py
  - encino_orm/base.py
  - encino_orm/sqlite.py
  - encino_orm/mysql.py
  - encino_orm/mariadb.py
  - encino_orm/postgresql.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - encino_orm/_rows.py
  - encino_orm/model/model.py
  - encino_orm/model/query_builder.py
  - encino_orm/model/types.py
  - encino_orm/sql.py
  - encino_orm/transfer.py
  - encino_orm/pool.py
  - encino_orm/introspection/codegen.py
  - tests/conftest.py
  - tests/test_identifiers.py
  - tests/test_dialect_builders.py
  - tests/test_query.py
  - tests/test_sql_snapshots.py
  - tests/__snapshots__/test_sql_snapshots.ambr
  - tests/test_engine.py
  - tests/test_ci_harness.py
  - tests/test_mssql.py
  - tests/test_mariadb.py
  - tools/ci/check_coverage_floors.py
  - .github/workflows/ci.yml
  - pyproject.toml
  - docs/design/0-design.md
findings:
  critical: 1
  warning: 8
  info: 6
  total: 15
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-09-18T05:03:01Z
**Depth:** deep
**Files Reviewed:** 34
**Status:** issues_found

## Summary

Phase 2 delivers a real, verifiable improvement: the DML seam is genuinely single-sourced, the identifier allowlist is genuinely single-sourced, and the aggregate-alias fix is complete. I independently re-derived the phase's two headline claims instead of trusting the summaries:

- **Byte-identity of DML (verified, not taken on faith).** I extracted the pre-phase package (`git archive aa68fd1 encino_orm`) into a scratch tree and ran a differential harness against the new tree: 11 builder cases × 6 dialects for `insert`/`update`/`delete`, plus `Model.upsert` in 3 modes × 6 dialects. **Output is byte-identical in every case.** The 5 golden-string test files also show `0` deleted lines in the range (`--numstat` = `+N 0`).
- **Coverage floors (verified, not taken on faith).** Ran the DB-free suite with `--cov --cov-branch` and executed `tools/ci/check_coverage_floors.py`: `identifiers.py` 100.0%, `builders.py` 100.0%, `query.py` 100.0% → exit 0. The gate is not vacuous and has real headroom.
- **Gates:** `ruff check` (exit 0), `ruff format --check` (114 files), `mypy encino_orm` (60 files, exit 0), `uv lock --check` (exit 0), 9/9 snapshots pass.

The problems are in the *claims that surround* the seam, not in the seam itself:

1. **The "single choke point" is not single.** `QueryBuilder`'s `alias` parameter — both the constructor and `join()`/`join_subquery()` — is interpolated raw into the SQL. This is a working SQL-injection primitive (`FROM t mm WHERE 1=0 UNION SELECT … --`), and it is a *public* API parameter. See CR-01.
2. **The `Query` cardinality contract is documented but not enforced in two reachable cases.** An empty `{n}` set with a non-empty `values` list passes silently (WR-01), and a leading-zero index (`{00}`) compiles to a parameter key that does not exist and blows up as a `KeyError` inside the driver adapter (WR-02).
3. **The "six-engine parity" claim has holes.** `QueryBuilder.all()/first()/exists()` still emit `LIMIT`, which is invalid on MSSQL/Oracle — the exact bug class the phase fixed in `Model.search` (WR-03). MariaDB `upsert` still emits `ON CONFLICT` (WR-04). PostgreSQL `Model.insert(replace=True)` targets `ON CONFLICT (enabled)` rather than the PK (WR-05).
4. **Two known-broken behaviours were preserved byte-for-byte but not logged in `deferred-items.md`, and the CI promotion of MariaDB does not exercise either** (WR-03, WR-04).

Nothing in the security-critical *value binding* path regressed: values are still always bound, never interpolated; `schema=` cannot bypass the allowlist; `_qualified()` validates both halves separately. The phase's stated invariants hold where the phase actually looked.

## Critical Issues

### CR-01: `QueryBuilder` alias is interpolated into SQL without validation (SQL injection)

**File:** `encino_orm/model/query_builder.py:46-51`, `:94-102`, `:104-114`, `:178`, `:184`, `:192`
**Issue:** The phase's central claim is that "un único cuello de botella de validación de identificadores" exists. It does not. `QueryBuilder` interpolates its alias into `FROM`/`JOIN` with **no** `check_identifier` and **no** `_safe_column` call:

```python
def __init__(self, model_class, db=None, alias: str = "mm"):   # :46
    self._alias = alias                                        # :49  <- never validated
...
def join(self, other, alias: str, on: Filter):                 # :94
    ...
    self._joins.append({... "alias": alias ...})               # :101 <- never validated
...
sql = f"FROM {self._model_class._table} {self._alias}"         # :178
sql += f" JOIN {join['model_class']._table} {join['alias']} ON {on_frag}"  # :184
```

`_safe_column` is applied to column expressions (`:80-82`) but never to the table alias. Proven on the current tree:

```
$ python -c "QueryBuilder(T, None, alias='mm WHERE 1=0 UNION SELECT nombre FROM usuarios --')._build_base()[0]"
FROM t mm WHERE 1=0 UNION SELECT nombre FROM usuarios --
```

`QueryBuilder.all()` prepends `SELECT *`, so the executed statement is a valid single-statement `UNION` — the `sqlite3` "one statement at a time" restriction does **not** neutralise this. The same hole exists on `join()` and `join_subquery()` (`evil alias` → `JOIN otra evil alias ON …`). The constructor alias is a documented, public parameter; `join(..., alias, ...)` is the standard way to attach a joined table.

**Why this matters for the phase's own claim:** focus item 1 of this review ("is the identifier validation actually a single choke point?") is answered **no**. The allowlist is single-sourced (good), but it is not a choke point: `QueryBuilder` reaches the driver with an unvalidated identifier.

**Fix:**
```python
# encino_orm/model/query_builder.py
def __init__(self, model_class, db=None, alias: str = "mm"):
    self._alias = _safe_column(alias)      # validates + normalises
    self._aliases = {self._alias}
    ...

def join(self, other, alias: str, on: Filter) -> "QueryBuilder":
    alias = _safe_column(alias)
    ...

def join_subquery(self, subquery, alias, on):
    if alias is None:
        alias = self._next_subquery_alias()
    alias = _safe_column(alias)
    ...
```
Add a regression test in `tests/test_query_builder.py` asserting `ValueError` for `QueryBuilder(Model, db, alias="x; DROP TABLE t --")` and for `join(Other, "a b", on)`, mirroring the `TestAdaptadoresRechazanAntesDelDriver` pattern already used in `tests/test_dialect_builders.py:283-302`.

_Note: this is pre-existing, not introduced by Phase 2. I am reporting it because the phase's deliverable is a validation choke point and this is the largest surviving bypass of it._

## Warnings

### WR-01: `Query` silently accepts parameters that no placeholder uses (documented contract not enforced)

**File:** `encino_orm/query.py:55-59`
**Issue:** The docstring and `docs/design/0-design.md` both state that the set of detected indices must be exactly `range(len(values))` and that a violation raises `ValueError`. The guard does not enforce that when there are no placeholders at all:

```python
indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}
if indices and indices != set(range(len(values))):   # `if indices` short-circuits the empty case
    raise ValueError(...)
```

`set() != set(range(len(values)))` is already `False` for `values == []`, so the `indices and` clause is both redundant and wrong. Proven:

```
>>> Query("SELECT 1", [1]).params
{'parameter_0000': 1}          # no error; the value is never bound to anything
```

This is a footgun for the `Query("SELECT … WHERE x = %s", [v])` / native-placeholder case: the parameter is accepted, stored, and then silently dropped by every `_prepare`. It is also what makes the design-doc example in WR-07 "work".

**Fix:** make the carve-out explicit instead of implicit, or enforce the contract:
```python
indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}
if indices != set(range(len(values))):
    raise ValueError(
        f"placeholders {sorted(indices)} no cuadran con {len(values)} parámetros"
    )
```
Removing `indices and` makes `Query("SELECT 1", [1])` raise as documented. If native-placeholder pass-through must stay supported, keep the carve-out but document it in the docstring and add a test (`test_no_placeholders_with_non_empty_fields_is_silently_ignored`) so the behaviour is intentional rather than accidental.

### WR-02: Leading-zero placeholder index compiles to a non-existent parameter key → `KeyError` from the adapter

**File:** `encino_orm/query.py:55`, `:62`
**Issue:** Validation normalises the index with `int(...)`, but compilation uses the **raw** captured text:

```python
indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}          # :55  -> int("00") == 0
compiled = _PLACEHOLDER_RE.sub(
    lambda m: f"%(parameter_000{m.group(1)})s", sql                # :62  -> uses "00" verbatim
)
```

For `{00}` the validator sees index `0` (so `{0}` and `{00}` are indistinguishable), the params dict is keyed `parameter_0000`, and the compiled SQL references `parameter_00000`. The mismatch is not caught at construction; it surfaces as a `KeyError` inside `_to_positional`/`_to_postgres`/`_to_mysql`:

```
>>> from encino_orm.sqlite import _to_positional
>>> q = Query("a={00}", [7])
>>> q.sql, q.params
('a=%(parameter_00000)s', {'parameter_0000': 7})
>>> _to_positional(q.sql, q.params)
KeyError: 'parameter_00000'
```

Same class of failure for mixed `{0}` / `{00}` in one template. The failure mode is a `KeyError` leaking out of the driver adapter — not the clean `ValueError` the constructor promises.

**Fix:** compile from the normalised index so validation and compilation cannot disagree:
```python
compiled = _PLACEHOLDER_RE.sub(lambda m: f"%(parameter_000{int(m.group(1))})s", sql)
```
Add a test asserting `Query("a={00}", [7]).sql == "a=%(parameter_0000)s"` (or that it raises), so the two paths stay locked together.

### WR-03: `QueryBuilder.all()/first()/exists()` still emit `LIMIT`, invalid on MSSQL/Oracle

**File:** `encino_orm/model/query_builder.py:234-236`, `:242`, `:287`
**Issue:** The phase fixed exactly this bug in `Model.search` (delegating pagination to `fetch_many`, `encino_orm/model/model.py:743-750`) but the same pattern survives in the main query builder:

```python
if self._limit_n is not None:
    offset = (self._limit_page - 1) * self._limit_n
    sql += f" LIMIT {self._limit_n} OFFSET {offset}"     # :236  -> invalid T-SQL / Oracle
...
sql = f"SELECT {self._render_select()} {sql} LIMIT 1"    # :242  -> invalid T-SQL / Oracle
...
sql = f"SELECT 1 {sql} LIMIT 1"                          # :287  -> invalid T-SQL / Oracle
```

`QueryBuilder.limit(n).all()`, `first()` and `exists()` therefore raise a syntax error on SQL Server and Oracle. The new parity tests (`tests/test_mssql.py:257-262`, `tests/test_oracle.py`) exercise only `count/sum/avg/min/max`, never `limit().all()` / `first()` / `exists()`, so the gap is invisible to CI. This is the same defect class the phase exists to eliminate ("resultados correctos en los seis motores"), and it is not listed in `deferred-items.md`.

**Fix:** route these three through the adapter, as `Model.search` now does:
```python
async def all(self):
    ...
    if self._limit_n is not None:
        return await self._db.fetch_many(Query(sql, params), self._limit_n, self._limit_page)
    return await self._db.fetch_all(Query(sql, params))

async def first(self):
    rows = await self._db.fetch_many(Query(sql, params), 1, 1)
    return rows[0] if rows else None

async def exists(self):
    return await self.first() is not None
```
(For `first()`/`exists()` you may also drop the `LIMIT 1` entirely and let `fetch_one` return the first row, which is portable on all six engines.) Add `QueryBuilder.limit(2).all()` to the per-engine parity classes, and log the item in `deferred-items.md` if it is deliberately deferred.

### WR-04: `Model.upsert` on MariaDB emits `ON CONFLICT` (unsupported syntax), and MariaDB is now a required CI engine that never tests it

**File:** `encino_orm/dialects/strategies.py:54-61`, `encino_orm/model/model.py:586`, `:601`
**Issue:** `UPSERT_KIND["mariadb"] = "on_conflict"` was preserved verbatim to keep the refactor byte-identical, and `build_upsert` therefore produces, for MariaDB:

```
INSERT INTO t (...) VALUES (...) ON CONFLICT (id) DO UPDATE SET enabled = excluded.enabled, ...
```

MariaDB does not implement `ON CONFLICT` (that is PostgreSQL/SQLite); MariaDB 11 (the CI image, `ci.yml:59-70`) expects `ON DUPLICATE KEY UPDATE`. So `Model.upsert()` is broken on one of the six engines. The code comment in `strategies.py:48-53` documents this as a HALLAZGO for a later phase — but:

- it is **not** in `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md` (which only logs the `list_tables(name=)` filter), so the phase's own deferral log is incomplete;
- the phase promoted MariaDB to a required engine (`ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql,mariadb,redis`) precisely to catch dialect drift, yet `tests/test_mariadb.py::TestMariadbParity` covers `count/paginate/list_tables/sync_schema/last_id` and the five aggregates — **never `upsert`**. `tests/test_bulk_upsert.py` is SQLite-only. CI will stay green over a broken code path.

**Fix (do not silently change the SQL — the byte-identity criterion is legitimate):** add the item to `deferred-items.md` with the same evidence you gave for `list_tables`, and add a MariaDB integration test that pins the *current* (broken) SQL shape or is `xfail(strict=True)` with the reason, so the day MariaDB is fixed the test tells you. Concretely, the follow-up fix is `UPSERT_KIND["mariadb"] = "on_duplicate"` plus a `MARIADB_INSERT` whose `kind` stays `prefix` (it already shares MySQL's strategy), then regenerate the `.ambr` snapshot.

### WR-05: PostgreSQL `Model.insert(replace=True)` targets `ON CONFLICT (enabled)`, not the primary key

**File:** `encino_orm/dialects/builders.py:89-91`, `:98`
**Issue:** When no explicit `conflict` is supplied, the target is `columns[0]`, and the new comment asserts that this is "(PK)":

```python
# PostgreSQL exige un objetivo de conflicto para DO UPDATE; se usa el
# `conflict` explícito, o la primera columna (PK) por defecto.
target = ", ".join(conflict) if conflict else (columns[0] if columns else "id")
```

For an auto-PK model, `Model.insert` skips `id` (`model.py:481-484`), so `columns[0]` is the first *declared* column — `enabled` for the base `Model` shape. Proven against the current tree:

```
>>> PostgresDb().insert("t", {"enabled": True, "created_at": ..., "updated_at": ..., "nombre": "Ana"}, False, True).sql
'INSERT INTO t (enabled,created_at,updated_at,nombre) VALUES (...) ON CONFLICT (enabled) DO UPDATE SET enabled = EXCLUDED.enabled, ...'
```

PostgreSQL rejects this with *"there is no unique or exclusion constraint matching the ON CONFLICT specification"*. `Model.insert(replace=True)` is therefore broken on PostgreSQL for any auto-PK model. `PoolDb.insert` now forwards `conflict` correctly (`pool.py:190-201`, and `tests/test_pool.py:139-141` asserts it), but `Model.insert` never passes `conflict`, so the pool fix does not help this path. `tests/test_postgresql.py:201` passes `{"id": 1, ...}` explicitly, which masks the bug.

**Fix:** derive the default conflict target from the model's primary key rather than from positional order. `Model.insert` already knows `type(self)._pk_fields()` / `_primary_key`; pass it down:
```python
# encino_orm/model/model.py, Model.insert
qry = self._get_db().insert(
    self._table, data, ignore_duplicated, replace,
    conflict=[self._col(k) for k in type(self)._pk_fields()] if replace else None,
)
```
and correct the comment in `builders.py` to say "primera columna del INSERT (no necesariamente la PK) — el llamador debe pasar `conflict`". Add a PostgreSQL integration assertion for `Model.insert(replace=True)` without an explicit `id`, and log the item if the fix is deferred.

### WR-06: `_build_column_map` does not validate the default column name, so `to_ddl` and `insert_many` interpolate unvalidated identifiers

**File:** `encino_orm/model/model.py:222-238` (changed in this phase), `encino_orm/model/types.py:169-176`, `encino_orm/model/model.py:556`
**Issue:** The phase correctly added `check_identifier(cls._table, ...)` and `check_identifier(col_name, ...)` for explicit `Column(name=...)` metadata. But the *default* column name — the pydantic field name — is assigned without validation:

```python
col = name                                            # :231
for meta in ...:
    if col_name:
        check_identifier(col_name, "nombre de columna")   # :235  only the explicit override
        col = col_name
mapping[name] = col
```

`Model.model_fields` keys are not required to be SQL identifiers when the class is built dynamically. Proven:

```python
M = create_model("M", __base__=Model, **{"a; DROP TABLE x --": (str, None)})
M._table = "t"
M._column_map()   # -> {..., 'a; DROP TABLE x --': 'a; DROP TABLE x --'}
to_ddl(M, "sqlite")[:120]
# 'CREATE TABLE t (\n  id INTEGER PRIMARY KEY AUTOINCREMENT,\n  enabled INTEGER,\n  ... a; D'
```

`to_ddl` (DDL), `indexes_ddl` column list (`types.py:221-230` validates only the index *name*), and `Model.insert_many` (`model.py:556`, inline DML outside the seam) all interpolate these values. `Model.upsert` is protected because `build_upsert` validates every key of `data`; `Model.insert` is protected because `build_insert` validates every key of `data`. `insert_many` and `to_ddl` are not.

**Fix:** validate once, at the single place the map is built, so every consumer inherits it:
```python
col = check_identifier(name, "nombre de columna")     # instead of `col = name`
for meta in ...:
    if col_name:
        col = check_identifier(col_name, "nombre de columna")
```
Add a test in `tests/test_identifiers.py` (or `test_migrations.py`) that a dynamically-created model with a non-identifier field name raises `ValueError` from `_column_map()`.

### WR-07: `docs/design/0-design.md` §2.1 example is wrong and demonstrates the silent parameter drop

**File:** `docs/design/0-design.md:95-104`
**Issue:** The `with_params()` example reuses `q` from the *previous* block, which is a raw query with no placeholders:

```python
# Raw SQL (sin placeholders, fields vacío)
q = Query("SELECT * FROM usuarios", [])
...
q2 = q.with_params(["Grupo B", 0])
# q2.sql -> "insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)"
# q2.params -> {"parameter_0000": "Grupo B", "parameter_0001": 0}
```

Both comments are false. Actual behaviour on this tree:

```
>>> Query("SELECT * FROM usuarios", []).with_params(["Grupo B", 0]).sql
'SELECT * FROM usuarios'
```

So the published design doc (a) documents a non-existent SQL result and (b) teaches a reuse pattern whose parameters are silently discarded (WR-01). `mkdocs build --strict` cannot catch this — the code fence is syntactically valid.

**Fix:** use a template that actually has placeholders, e.g.
```python
q = Query("insert into grupos (grupo, enabled) values ({0},{1})", ["Grupo A", 1])
q2 = q.with_params(["Grupo B", 0])
# q2.sql    -> "insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)"
# q2.params -> {"parameter_0000": "Grupo B", "parameter_0001": 0}
# q sigue intacta
```

### WR-08: Breaking removal of `Query.rebind` is not recorded in `CHANGELOG.md`, and the migration note names a version that does not exist

**File:** `docs/design/0-design.md:107`, `CHANGELOG.md:9`
**Issue:** `AGENTS.md`/`PROJECT.md` state a hard project constraint: while on `0.x`, incompatible changes are allowed but **must** be documented in `CHANGELOG.md`. This phase deletes `Query.rebind` and `Query.format` with no shim (D-01) and updates the design doc, but `CHANGELOG.md` `[Unreleased]` is empty. The design doc's migration note instead says *"`rebind` se eliminó en **0.3.0**"*, while `pyproject.toml` still declares `version = "0.2.6"` and no `0.3.0` section exists. The break is therefore documented only in a design doc for an unreleased, unversioned release.

**Fix:** add a `[Unreleased]` entry now (the Phase-8 plan to write `CHANGELOG.md`/`MIGRATION-0.3.md` does not remove the obligation to not ship the break silently):
```markdown
## [Unreleased]

### Cambiado (ruptura)
- `Query` es ahora un value object inmutable y hashable. Se eliminan `Query.rebind`
  y `Query.format` sin shims; el sustituto es `Query.with_params(fields)`, que
  devuelve una copia. `Query.query` se conserva como property de solo lectura.
```
Either align the design doc to `0.3.0` after the version bump, or reword it to "se elimina en la próxima versión incompatible (0.3.0)".

## Info

### IN-01: `Query`'s private slots are writable, so "immutable" only holds for the public surface

**File:** `encino_orm/query.py:46-51`, `:73-96`
**Issue:** The docstring explains the public surface correctly, but there is no `__setattr__` guard, so `q._sql = "MUTATED"` succeeds and silently changes the SQL sent to the driver while `__hash__` (computed from `_sql_template`/`_fields`) is unchanged. Documented limitations cover `q.fields.append(...)` and `q.params[...]`, not this.
**Fix:** if you want the invariant to hold for a hashable key type, add
```python
def __setattr__(self, name, value):
    raise AttributeError("Query es inmutable")
```
(all writes in `__init__` already go through `object.__setattr__`, so this is safe). Otherwise, extend the docstring's limitations list to name private-slot reassignment.

### IN-02: `params` and `query` expose the internal dict by reference

**File:** `encino_orm/query.py:79-81`, `:98-101`
**Issue:** `q.params["parameter_0000"] = v` and `q.query[1]["parameter_0000"] = v` mutate the stored state (and, for `query`, the "fresh list" claim is only true of the list, not its second element). This is documented for `params` but the `query` docstring ("Lista nueva") can read as if the payload were copied too.
**Fix:** clarify the `query` docstring ("lista nueva; el dict de parámetros es el interno, por referencia"), or return `dict(self._params)`.

### IN-03: Duplicated and stale `S608` justification in `pyproject.toml`

**File:** `pyproject.toml:131-137`
**Issue:** The new `S608` block was appended under the old comment, leaving a contradictory pair: the first says *"La validación centralizada llega en Fase 2 (DIAL-02)"* and the second says it already exists. The stale line should have been replaced, not superseded.
**Fix:** delete the first two lines of the old comment ("S608: los constructores de dialecto interpolan SQL intencionadamente. La validación centralizada llega en Fase 2 (DIAL-02); …") and keep only the accurate one.

### IN-04: `optional_engine` marker description still lists MariaDB and Redis

**File:** `pyproject.toml:77`
**Issue:** `"optional_engine: motor no requerido en Fase 1 (MariaDB/Redis/MSSQL/Oracle); ver D-02"` — MariaDB and Redis were promoted to required in this phase (`tests/test_mariadb.py`, `tests/test_redis_cache.py` have their markers removed), so the description now contradicts the code.
**Fix:** `"optional_engine: motor no requerido en el job `test` (MSSQL/Oracle; su job es `engine-heavy`); ver D-02 y DIAL-08"`.

### IN-05: Placeholder regex `\{(\d+)\}` is still duplicated in three modules plus one inline copy

**File:** `encino_orm/query.py:5`, `encino_orm/model/model.py:107`, `encino_orm/model/query_builder.py:15`, `encino_orm/model/filter.py:222`
**Issue:** DIAL-01's whole premise is that duplicated validation drifts; the identifier allowlist was centralised, but the placeholder grammar — the other security-relevant regex, and the one that just produced WR-01/WR-02 — remains in four places. A fix to one (e.g. `int()` normalisation) will not reach the others.
**Fix:** export a single `PLACEHOLDER_RE` (and the `{n}` → `%(parameter_000N)s` compiler) from one module and import it in all four, mirroring `dialects/identifiers.py`.

### IN-06: The CI wiring added by this phase is not covered by any test

**File:** `.github/workflows/ci.yml:252-408`
**Issue:** `engine-heavy`'s file-based selection, `ENCINO_ORM_REQUIRE_ENGINES: mssql,oracle`, and the "no `continue-on-error`" invariant are verified only by hand (the 02-05 summary explicitly records them as manual-only). A future edit that switches the heavy job to `-m optional_engine` or adds `continue-on-error: true` would pass review silently. The `tools/ci/check_coverage_floors.py` gate *is* well covered (`tests/test_ci_harness.py:117-187`).
**Fix:** add a `tests/test_ci_harness.py` case that `yaml.safe_load`s `.github/workflows/ci.yml` and asserts (a) the `engine-heavy` step names `tests/test_mssql.py` and `tests/test_oracle.py`, (b) no job has `continue-on-error`, and (c) `coverage` `needs` includes `engine-heavy`. `yaml` is already imported by the phase's own validation steps.

---

## Focus-area verdicts

| Focus area | Verdict |
|---|---|
| 1. Single validation choke point / `schema=` bypass / values bound | **Partially false.** Values are always bound and `schema=` cannot bypass the allowlist (`_qualified` validates both halves, `builders.py:20-25`). But the choke point is bypassed by `QueryBuilder` aliases (CR-01) and by unvalidated default column names in `to_ddl`/`insert_many` (WR-06). |
| 2. Byte-identity regression risk | **Clean.** Independently verified by differential execution against `aa68fd1`: 11 DML cases × 6 dialects and 3 `upsert` modes × 6 dialects are byte-identical; the 5 golden-string test files have `0` deletions. Spacing, quoting, `RETURNING`, MERGE `AS`/no-`AS`, and the `,` vs `, ` conflict separators are all preserved. |
| 3. `Query` immutability | **Public surface airtight; not deep, and the documented limitations are honest.** `q.sql = …`/`q.fields = …`/`q.ignore_duplicated = …` raise; typos raise; `with_params` copies. Private slots remain writable (IN-01) and `params`/`query` alias the internal dict (IN-02). No `object.__setattr__` leak from outside `__init__`. |
| 4. The 7 aggregate alias fixes | **All fixed and collision-safe.** 8 reader sites (2 in `base.py`, 1 in `Model.count`, 5 in `QueryBuilder`) alias `AS n` and read `row["n"]`; grep finds no surviving expression-keyed read. Collision is impossible because each of these statements has exactly one output column. `sum`→0 / `avg|min|max`→None on empty is preserved. |
| 5. CI gates | **Not vacuous, fail-closed.** `engine-heavy` selects by file and requires both engines via `ENCINO_ORM_REQUIRE_ENGINES` → `engine_unavailable` calls `pytest.fail` (not skip) when required (`conftest.py:32-45`); `check_skips.py` fails on any `skipped > 0`; no `continue-on-error` anywhere; `check_coverage_floors.py` fails closed on a missing module (and I verified it returns 1 when a module is deleted). Floors measured at 100/100/100. Caveat: the wiring itself is untested (IN-06). |
| 6. Deferrals | **Under-scoped.** The `list_tables(name=)` deferral is well documented and the root cause is accurate. But the phase deferred two more broken-on-engines paths it discovered or preserved (`QueryBuilder.limit/first/exists` on MSSQL/Oracle, MariaDB `upsert`) and logged **neither** in `deferred-items.md`; WR-04 additionally left a known-broken path outside the new required-engine CI coverage. |

---

_Reviewed: 2026-09-18T05:03:01Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
