---
phase: 02-dialect-seam-engine-parity
reviewed: 2026-09-18T14:04:14Z
depth: deep
files_reviewed: 26
files_reviewed_list:
  - encino_orm/model/query_builder.py
  - encino_orm/model/model.py
  - encino_orm/model/types.py
  - encino_orm/query.py
  - encino_orm/dialects/strategies.py
  - encino_orm/dialects/builders.py
  - encino_orm/base.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - tests/test_query_builder.py
  - tests/test_identifiers.py
  - tests/test_index.py
  - tests/test_query.py
  - tests/test_sql_snapshots.py
  - tests/__snapshots__/test_sql_snapshots.ambr
  - tests/test_dialect_builders.py
  - tests/test_mariadb.py
  - tests/test_mssql.py
  - tests/test_oracle.py
  - tests/test_postgresql.py
  - tests/test_mysql.py
  - tests/test_sqlite.py
  - tests/test_d_recommendations.py
  - docs/design/0-design.md
  - CHANGELOG.md
  - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md
findings:
  critical: 3
  warning: 2
  info: 3
  total: 8
status: issues_found
---

# Phase 02 (GAP-CLOSURE Round): Code Review Report

**Reviewed:** 2026-09-18T14:04:14Z
**Depth:** deep
**Files Reviewed:** 26
**Status:** issues_found

## Summary

The gap-closure round (`6ef8c43`..`2e4cf4f`, plans 02-06…02-09) genuinely fixes the
three headline items it set out to fix, and I verified each one against the working
tree rather than the summaries:

- **CR-01 (public alias vector) is closed.** `QueryBuilder.__init__`, `join()` and
  `join_subquery()` all pass the alias through the strict `check_identifier`
  allowlist before storing it; the literal UNION payload raises `ValueError` and a
  driver spy proves no query is issued. `indexes_ddl` and `_build_column_map` are
  now fail-closed too.
- **WR-01/WR-02 are closed.** `Query("SELECT 1", [1])` raises; `Query("a={00}",[7])`
  compiles to `%(parameter_0000)s` with a matching params key. The `Query(sql, [])`
  compatibility path is pinned. I re-ran the DB-free suite: `683 passed`.
- **WR-03/WR-04/WR-05 are closed for the paths named.** `QueryBuilder` no longer
  emits inline `LIMIT`; MariaDB emits `ON DUPLICATE KEY UPDATE`; PostgreSQL
  `Model.insert(replace=True)` derives `ON CONFLICT` from the model PK only for
  `suffix`. The MSSQL `;` and Oracle `FROM dual` driver-boundary rewrites leave the
  builder output byte-identical (only the new filtered snapshot entry was added).
- **GAP 4 is closed.** `list_tables(name=)` filters a real derived-table column with
  a bound value and `LOWER()` on both sides; the unfiltered path is byte-identical.
  Live integration selection `-k "list_tables_filtrado or model_upsert or
  model_insert_replace or query_builder_limit"` → `14 passed`; `ruff`/`mypy` green.

However, the round's central claim — that identifier validation is now a real choke
point and that the six-engine parity goal holds — is **not** fully true, and the
round's own deferral log is inaccurate. Three defects are real and live-confirmed,
not theoretical:

1. **`QueryBuilder` still interpolates an unvalidated `_table` into `FROM`/`JOIN`.**
   The alias fix covered the public `alias=` parameter, but the model's `_table`
   reaches `_build_base()` with no validation because `QueryBuilder` never triggers
   `_build_column_map()` (the only place `_table` is validated). Reproduced:
   `QueryBuilder(Evil, None)._build_base()[0] == 'FROM t; DROP TABLE usuarios -- mm'`.
   See CR-01.
2. **`Model.upsert()` with the documented default conflict (`None` → PK) emits
   `ON (dst.id = src.id)` on MSSQL/Oracle, but the `src` derived table has no `id`
   column.** Live-confirmed: MSSQL error 207 *Invalid column name 'id'*; Oracle
   ORA-00904 `"SRC"."ID": invalid identifier`. The round explicitly recognised this
   hazard for `insert(replace=True)` and worked around it, but left `upsert` doing
   exactly the hazardous thing. See CR-02.
3. **MSSQL `Model.insert(replace=True)` now silently returns a stale id.** The
   round's `;` fix made the MERGE executable, but `MssqlDb.execute` only refreshes
   `_last_id` for statements starting with `INSERT`, and `last_id()` returns the
   cached value. Live-confirmed: after inserting Ana (id=1), `insert(replace=True)`
   for Zoe returns `1` and sets `z.id = 1`. See CR-03.

## Critical Issues

### CR-01: `QueryBuilder` still interpolates an unvalidated `_table` into `FROM`/`JOIN` (choke point not complete)

**File:** `encino_orm/model/query_builder.py:189`, `:195`
**Issue:** The CR-01 fix validates the three alias parameters, but `_build_base()`
interpolates the model's table name directly:

```python
sql = f"FROM {self._model_class._table} {self._alias}"                    # :189
...
sql += f" JOIN {join['model_class']._table} {join['alias']} ON {on_frag}" # :195
```

`Model._table` is only validated inside `Model._build_column_map()`
(`encino_orm/model/model.py:224`), and `QueryBuilder` never calls `_column_map()` on
the model before building SQL. Reproduced on the current tree:

```
$ python -c "from encino_orm.model.query_builder import QueryBuilder; ... "
'FROM t; DROP TABLE usuarios -- mm'
```

This is the same class of defect the round set out to eliminate; the public `alias=`
vector is fixed, but the choke point is still bypassable whenever a model class is
created with a non-identifier `_table` (e.g. dynamic/code-generated models, the exact
scenario WR-06 cited for field names). Focus-area 1's answer is therefore **no**:
`check_identifier` is not applied at every construction point.

**Fix:** validate the table at the `QueryBuilder` boundary (constructor and joins), or
force `_column_map()` so the existing lazy check runs:

```python
def __init__(self, model_class, db=None, alias: str = "mm"):
    check_identifier(model_class._table, "nombre de tabla")
    ...
def join(self, other, alias: str, on: Filter) -> "QueryBuilder":
    check_identifier(other._table, "nombre de tabla")
    ...
```

Add a regression test mirroring `TestAliasInjection` with a dynamic model whose
`_table` is `"t; DROP TABLE usuarios --"`, asserting `ValueError` from `_build_base()`.

### CR-02: `Model.upsert()` default conflict emits `ON (dst.id = src.id)` on MSSQL/Oracle where `src.id` does not exist

**File:** `encino_orm/model/model.py:604`, `:616-624`; `encino_orm/dialects/builders.py:41-42`, `:220`
**Issue:** `Model.upsert()` documents `conflict=None` as "clave primaria" and builds
`conflict_cols = [self._col(c) for c in conflict]` (`model.py:604`). For an
auto-PK model `id` is omitted from `data` (`model.py:600-603`), so the MERGE `src`
derived table — built from `columns` only (`builders.py:41`) — has no `id` column,
yet the `ON` clause is `" AND ".join(f"dst.{c} = src.{c}" for c in conflict_cols)`
(`builders.py:42`). Live-confirmed on both merge engines:

```
MSSQL  -> ('42S22', "Invalid column name 'id'. (207) ... Statement(s) could not be prepared.")
ORACLE -> ORA-00904: "SRC"."ID": invalid identifier
```

This is the *same* hazard the round's new comment in `builders.py:102-109` describes
for `insert(replace=True)` ("pasar `['id']` produciría `ON (dst.id = src.id)` sobre
una columna inexistente") — but `Model.upsert()` does exactly that and is untested on
both engines (`grep upsert tests/test_mssql.py tests/test_oracle.py` → 0). The phase
claims engine parity; `Model.upsert()` with its documented default is broken on 2 of
6 engines. It is also absent from `deferred-items.md`.

**Fix (fail-closed + explicit requirement):** in `build_upsert`, when
`upsert_kind == "merge"`, validate that every conflict column is present in the
insert columns, and raise a clear `ValueError` otherwise:

```python
else:  # merge
    missing = [c for c in conflict if c not in cols]
    if missing:
        raise ValueError(
            f"conflicto {missing} no está en el INSERT; en MERGE el objetivo "
            "debe ser una columna presente en los datos (pasa conflict=...)"
        )
```

Then `Model.upsert()` on MSSQL/Oracle with an auto-PK model raises a clean,
actionable error instead of invalid SQL. If the intended semantics is "upsert by a
data column", derive the default from a UNIQUE data column or require the caller to
pass `conflict=`. Log the item in `deferred-items.md` with an owner either way.

### CR-03: MSSQL `Model.insert(replace=True)` returns a stale id and corrupts `obj.id`

**File:** `encino_orm/mssql.py:239-240`, `:252`, `:314-315`; `encino_orm/model/model.py:505-518`
**Issue:** The round made the MSSQL MERGE executable by appending `;`. But
`MssqlDb.execute` only refreshes `_last_id` for statements whose text starts with
`INSERT` (`mssql.py:252`), and `last_id()` returns the cached `_last_id`
(`mssql.py:314-315`). A `MERGE` therefore never updates it, yet
`Model.insert()` unconditionally consumes `last_id()` and assigns it to `self.id`
(`model.py:508`, `:512-515`). Live-confirmed:

```
Ana insert() returned id: 1
Zoe insert(replace=True) returned id: 1   obj.id: 1
```

`insert(replace=True)` on MSSQL now silently returns another row's primary key and
mutates the object to point at it. A subsequent `obj.update()` would target Ana's
row — a data-integrity risk that did not exist before this round (the call used to
fail loudly with error 10713). The new test
`test_model_insert_replace_no_rompe_el_merge` does not assert the returned id, so CI
stays green over it.

**Fix:** capture the inserted id for MERGE. On SQL Server the MERGE supports
`OUTPUT INSERTED.id`; alternatively run `SELECT CAST(SCOPE_IDENTITY() AS INT)` after
the MERGE, or have `MssqlDb.execute` recognise `MERGE` and refresh `_last_id`.
Until fixed, document that `Model.insert(replace=True)` returns an unreliable id on
MSSQL and add an assertion to the existing test pinning the current (wrong) value so
the day it is corrected the test fails.

## Warnings

### WR-01: Oracle `Model.insert(replace=True)` remains non-executable (ORA-38104) and the deferral is unowned

**File:** `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md:10-11`, `:114-135`
**Issue:** The ORA-38104 entry is marked **PENDIENTE** with no owning phase, and its
own "sugerencia para una fase futura" names no phase. This directly contradicts the
`## Cerrados en la ronda de gap closure` header ("**Ya NO queda ningún item de la
Fase 02 sin dueño** — este era el último diferido huérfano"). The round's focus item 7
is therefore **not** satisfied: at least this item (and the CR-02 `upsert` defect,
which is not logged at all) remain unowned. The Oracle path is not merely deferred
but *characterised as failing* by
`tests/test_oracle.py::TestOracleParity::test_model_insert_replace_no_rompe_el_merge`.
**Fix:** either assign an owner (a future phase/plan ID) to ORA-38104 and to the
`Model.upsert` merge defect, or reword the header so it does not claim all items are
owned. The suggested fix already written in the entry (exclude `conflict_cols` from
`set_sql`) is correct and should be tracked.

### WR-02: The 02-07 behaviour change is not recorded in `CHANGELOG.md`

**File:** `CHANGELOG.md:9-45` (Unreleased), `encino_orm/query.py:64-73`
**Issue:** The project has a hard constraint (`AGENTS.md`/`PROJECT.md`): while on
`0.x`, incompatible changes **must** be documented in `CHANGELOG.md`. `02-06` and
`02-08` added `### Corregido` entries, but `02-07` — which changed observable
behaviour — added none (`git log 6ef8c43~1..2e4cf4f -- CHANGELOG.md` shows only the
02-06 and 02-08 commits). `Query("SELECT 1", [1])` was previously accepted (value
silently dropped) and now raises `ValueError`; `{00}` now compiles to a different
placeholder key. Whether this is framed as "Corregido" or "Cambiado", it belongs in
`CHANGELOG.md`, and the previous review's WR-08 (the `Query.rebind`/`format`
breaking removal) is still absent as well.
**Fix:** add a `[Unreleased]` bullet, e.g. "`Query` aplica el contrato de cardinalidad
sin carve-outs: pasar valores a una plantilla sin `{n}` ahora lanza `ValueError`
(antes se descartaban en silencio) y `{00}` se normaliza a `parameter_0000`", plus
the `rebind`/`format` removal entry recommended in `02-REVIEW.md` WR-08.

## Info

### IN-01: `check_identifier` accepts a trailing newline (`$` anchor)

**File:** `encino_orm/dialects/identifiers.py:21`
**Issue:** `IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` — Python's `$`
matches before a final newline, so `check_identifier("mm\n", "alias")` returns
`"mm\n"` and `QueryBuilder(Agente, None, alias="mm\n")` is accepted. It is not
exploitable (a mid-string newline is still rejected) and the verification already
documented it as a deliberate preservation, but it is a genuine allowlist looseness.
**Fix:** use `\Z` instead of `$` (or `re.fullmatch`), or add a characterisation test
so the behaviour is intentional.

### IN-02: `docs/design/0-design.md` redefines `q` with the same template twice

**File:** `docs/design/0-design.md:87`, `:101`
**Issue:** The `with_params()` example now re-creates `q` with a template already
defined 14 lines above; harmless but confusing.
**Fix:** drop the second `q = Query(...)` line and keep the reuse example on the
existing `q`.

### IN-03: PostgreSQL `insert(replace=True)` on an auto-PK model is a silent no-op replacement

**File:** `encino_orm/model/model.py:499-503`
**Issue:** For an auto-PK model, `id` is excluded from `data`, so the derived
`ON CONFLICT (id)` can never fire and `replace=True` behaves as a plain INSERT. The
`CHANGELOG.md` entry already discloses this explicitly ("la sentencia es válida pero
no reemplaza"), so this is acknowledged, not hidden — noted only so the semantic is
tracked. No code change required for this review.

---

## Focus-area verdicts

| Focus area | Verdict |
|---|---|
| 1. CR-01 injection actually closed / other `QueryBuilder` paths | **Partially.** The public `alias=`/`join`/`join_subquery` vectors are closed and regression-tested. But `_build_base()` still interpolates `model_class._table` / `join['model_class']._table` unvalidated (CR-01); `select`/`group_by`/`order_by` go through `_safe_column` (dot-tolerant, not the strict allowlist), which is acceptable for those expression positions. |
| 2. Cardinality rule safe for all callers | **Clean.** I enumerated every `Query(...)` site in `encino_orm/`; all non-empty `fields` sites supply matching `{n}` placeholders (`builders.py`, `insert_many`, `base.paginate` count wrapper, `list_tables` filtered). Placeholders used twice are handled (`indices` is a set). The only newly-rejected inputs are values-with-no-placeholder, which is the documented contract. DB-free suite `683 passed`. |
| 3. MariaDB `ON DUPLICATE KEY UPDATE` | **Clean.** `on_duplicate` renders `VALUES(c)` (valid on MariaDB/MySQL), works with and without `update_values`, and `replace` does not touch `upsert`. `UPSERT_KIND["mysql"]` is unchanged, so no MySQL regression. Live MariaDB integration test (`count()==1`, `monto==99.0`) passes. |
| 4. `insert(replace=True)` conflict target / merge keeps `conflict=None` | **`insert` is correct; `upsert` is not.** Confirmed `conflict` is set only for `strategy.kind == "suffix"`, so `merge` keeps `None` (CR-01/WR-05 for `insert` closed). But `Model.upsert()` passes the PK regardless and produces `ON (dst.id = src.id)` on merge engines (CR-02). |
| 5. MERGE fixes side effects / snapshots | **Clean for the builder output.** Both rewrites happen after `_prepare` and only for statements starting with `MERGE`; the `;` append is idempotent via `rstrip(";")`; the Oracle regex matches the single `USING (SELECT …) src` and inserts `FROM dual`. `.ambr` diff is additive only; golden strings untouched. Side effect found: the MSSQL fix exposes the stale `last_id` (CR-03). |
| 6. `list_tables(name=)` binding / `LOWER()` / alias legality | **Clean.** Value bound as `{0}` (`params.append(f"%{name}%")`), never interpolated; `LOWER()` on both sides; derived alias `encino_orm_tables` legal on all six dialects; unfiltered path byte-identical and pinned. |
| 7. Deferred items ownership | **Not satisfied.** `deferred-items.md` claims no Phase-2 item remains unowned, but ORA-38104 is PENDIENTE with no owner and the CR-02 `upsert` defect is not logged at all (WR-01). |

---

_Reviewed: 2026-09-18T14:04:14Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
