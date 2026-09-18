---
phase: 02-dialect-seam-engine-parity
reviewed: 2026-09-18T14:51:06Z
depth: deep
files_reviewed: 21
files_reviewed_list:
  - encino_orm/model/query_builder.py
  - encino_orm/dialects/builders.py
  - encino_orm/model/model.py
  - encino_orm/dialects/identifiers.py
  - encino_orm/query.py
  - encino_orm/base.py
  - encino_orm/pool.py
  - encino_orm/mssql.py
  - encino_orm/oracle.py
  - encino_orm/model/filter.py
  - tests/test_query_builder.py
  - tests/test_dialect_builders.py
  - tests/test_mssql.py
  - tests/test_oracle.py
  - tests/test_d_recommendations.py
  - tests/test_sql_snapshots.py
  - tests/__snapshots__/test_sql_snapshots.ambr
  - CHANGELOG.md
  - .planning/phases/02-dialect-seam-engine-parity/deferred-items.md
  - .planning/ROADMAP.md
  - .planning/REQUIREMENTS.md
findings:
  critical: 0
  warning: 1
  info: 5
  total: 6
status: issues_found
---

# Phase 02 (GAP-CLOSURE ROUND 2): Code Review Report

**Reviewed:** 2026-09-18T14:51:06Z
**Depth:** deep
**Files Reviewed:** 21
**Status:** issues_found (advisory, non-blocking)

## Summary

This round (`d4df155`..`0455afb`, plans 02-10/02-11/02-12) closes the three BLOCKERs and two
WARNINGs raised by the previous re-verification. I re-derived every claim from the working tree
at `0455afb` rather than from the SUMMARYs:

- **CR-01 is closed at the public boundary.** `QueryBuilder.__init__` (`:55`) and `join()` (`:115`)
  now run `check_identifier` (strict allowlist) before any SQL is built. I could not find a
  remaining unvalidated interpolation point reachable through the builder: `select`/`group_by`/
  `order_by`/`sort_by`/aggregates go through `_safe_column`; `select("alias.*")` expands through
  `_column_map()` (validated in `_build_column_map`); `where`/`having` go through
  `Filter._safe_field`; subqueries are themselves `QueryBuilder`s validated at their own
  construction. Validation is **construction-time (fail-fast)**.
- **CR-02 is closed for conflict columns.** The `_merge_sql` guard (`builders.py:46-51`) is the
  single render point shared by `build_insert`/`build_upsert`; it rejects every absent conflict
  column, and I verified it does **not** fire spuriously (DB-free snapshots 10/10, full suite
  787 passed, `.ambr` untouched). It is, however, **incomplete** for two adjacent inputs
  (WR-01 below).
- **CR-03 is semantically sound.** `Model.insert` decides from the statement it built
  (`qry.sql_template`), returns `0` and leaves `self.id` intact on a MERGE. This prevents the
  data-integrity defect (a later `update()` targeting another row) — and a later `update()` now
  fails loudly with `FailOnUpdate("llave 'id' sin valor")` instead of hitting the wrong row. The
  detection is robust through `PoolDb` (its `insert()` returns the template's `Query`, and inside
  `_transactional` the `contextvar` makes `PoolDb.last_id()` delegate to the real connection).
  Oracle is covered by the same guard; on Oracle today the MERGE is still non-executable
  (ORA-38104), so it fails before any id assignment.
- **Regression risk: none found.** The two production fixes are Python guards/decisions; valid
  SQL is byte-identical, `git diff --stat tests/__snapshots__/` is empty and
  `encino_orm/mssql.py`/`oracle.py` are unchanged.
- **Documentation is accurate and traceable.** The ORA-38104 ownership is recorded in all three
  artifacts (`deferred-items.md:116`, `ROADMAP.md:231`, `REQUIREMENTS.md:45`), and the changelog
  describes old + new behaviour without claiming the `columns[0]` fallback was fixed.

Independently reproduced: full suite `787 passed`; DB-free suite `707 passed` (10 snapshots).

The round is a genuine closure of the prior findings. The one substantive residual is that the
new fail-closed guard is narrower than advertised (WR-01); the rest are low-risk quality notes.

## Narrative Findings (AI reviewer)

## Critical Issues

None. I probed the CR-01/CR-02/CR-03 attack surfaces and found no exploitable or data-corrupting
defect in the changed code.

## Warnings

### WR-01: The `_merge_sql` fail-closed guard is incomplete — absent `update_cols` and empty `conflict_cols` still emit invalid MERGE SQL

**File:** `encino_orm/dialects/builders.py:46-51` (guard), `:227-232` (merge `set_sql`), `encino_orm/model/model.py:610-611`, `:626` (upsert conflict default)
**Issue:** The round advertises the merge render as fail-closed, but the guard only checks
`conflict_cols` against the INSERT `columns`. Two other identifiers are interpolated into the same
MERGE body without that check:

1. **`update_cols` absent from the INSERT columns** (when `update_values is None`). `set_sql`
   becomes `dst.<c> = src.<c>` for a column the `src` derived table does not carry:
   ```
   $ build_upsert("t", {"a": 1}, strategy=MSSQL_INSERT, upsert_kind="merge",
   ...           conflict=["a"], update_cols=["b"])
   -> MERGE INTO t AS dst USING (SELECT {0} AS a) AS src ON (dst.a = src.a)
      WHEN MATCHED THEN UPDATE SET dst.b = src.b ...        # src.b does not exist
   ```
   This is the *same* "column referenced in the MERGE does not exist in `src`" defect class as
   CR-02. It is reachable by direct `build_upsert` callers (it is exported in `__all__`), and the
   existing test `tests/test_dialect_builders.py::test_no_emite_returning` already constructs such
   a statement (it only asserts `"RETURNING" not in ...`, so CI stays green over it). It is **not**
   reachable through `Model.upsert`, which derives `update_cols` from `data`.

2. **Empty `conflict_cols`** is not rejected, and `ON (" AND ".join([]))` renders `ON ()` with an
   empty `WHEN MATCHED THEN UPDATE SET`. This **is** reachable through the public `Model` API,
   because `Model.upsert` only substitutes the PK when `conflict is None` (`model.py:610`); an
   explicit `conflict=[]` passes straight through:
   ```
   $ await M(db_mssql, nombre="Ana", monto=1.0).upsert(conflict=[])
   -> EXECUTED: MERGE INTO t ... ON () WHEN MATCHED THEN UPDATE SET  ...
   ```
   The invalid statement reaches the driver (a loud syntax error on MSSQL/Oracle and an invalid
   `ON CONFLICT ()` on PostgreSQL), contradicting the round's "fail closed before the driver"
   guarantee for the merge render.

**Impact:** Loud driver errors rather than silent corruption, and only for inputs the documented
API does not produce by default — hence WARNING, not BLOCKER. But the guard is the round's stated
single choke point, so leaving the same defect class half-covered is worth fixing now.

**Fix:** Extend the guard in `_merge_sql` to validate every identifier it interpolates from the
`src` derived table, and reject an empty target:

```python
# builders.py::_merge_sql
missing = [c for c in conflict_cols if c not in columns]
if missing:
    raise ValueError(...)
# NEW: the SET clause also references src.<col> when update_values is None
if set_from_src and any(c not in columns for c in update_from_src_cols):
    raise ValueError(...)
# NEW: an empty conflict target cannot render a valid MERGE
if not conflict_cols:
    raise ValueError("conflicto vacío; en MERGE el objetivo no puede ser vacío")
```

Simpler alternative: pass the `update_cols` (when `update_values is None`) into `_merge_sql` and
run the same `not in columns` check, and add `if not conflict_cols: raise ValueError(...)`.
Add DB-free tests mirroring `TestMergeConflictGuard` for both cases.

## Info

### IN-01: CR-01 validation is construction-time; mutating `_table` afterwards bypasses it (TOCTOU)

**File:** `encino_orm/model/query_builder.py:55`, `:115`, `:208`, `:214`
**Issue:** `check_identifier` runs in `__init__`/`join()`, but `_build_base()` re-reads
`self._model_class._table` at build time. Mutating the class attribute after construction
re-opens the original vector:
```
$ M._table = "ok_tabla"; qb = QueryBuilder(M, None); M._table = "t; DROP TABLE usuarios --"
$ qb._build_base()[0]
'FROM t; DROP TABLE usuarios -- mm'
```
No code path in this repo mutates `_table` after building a `QueryBuilder`, and models are
normally declared statically, so the real-world risk is low. This is defense-in-depth only.
**Fix (optional):** validate (or snapshot) the table name in `_build_base()` as well, e.g. capture
`self._table = check_identifier(model_class._table, "nombre de tabla")` in `__init__` and use the
captured value in `_build_base`/`join` instead of re-reading the class attribute.

### IN-02: `check_identifier` still accepts a trailing newline (residual IN-01 from the prior review)

**File:** `encino_orm/dialects/identifiers.py:21`, `:26`
**Issue:** `IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` — Python's `$` matches before
a final newline, so `check_identifier("agentes\n", "nombre de tabla")` returns `"agentes\n"`.
Confirmed on the current tree; mid-string newlines are still rejected, so it is not exploitable.
It now also gates `_table` (the CR-01 fix), which is why it is worth closing here.
**Fix:** use `\Z` instead of `$` (or `re.fullmatch`), plus a characterisation test.

### IN-03: `Db.insert`'s abstract contract still does not declare that it returns a `Query`

**File:** `encino_orm/base.py:91-101`; consumer `encino_orm/model/model.py:514`, `:521`
**Issue:** `Model.insert` now binds the result of `db.insert(...)` and reads `.sql_template`
(`model.py:521`). The abstract `Db.insert` signature has no return annotation or docstring, so the
"returns a `Query`" contract is implicit. A custom `Db`/test double returning a non-`Query`
breaks with `AttributeError` — exactly the failure the round hit in `LockDb` and patched in
`tests/test_d_recommendations.py`. Production adapters and `PoolDb` all return `Query`, so this is
a documentation/typing gap, not a live bug.
**Fix:** annotate `Db.insert(...) -> Query` (and document the return) in `base.py`.

### IN-04: New source-guard tests use a CWD-relative path, unlike the rest of the suite

**File:** `tests/test_query_builder.py:431`, `:441`
**Issue:** `pathlib.Path("encino_orm/model/query_builder.py").read_text(...)` resolves against the
process CWD. It works under `uv run pytest` from the repo root (CI and the local run pass), but
fails with `FileNotFoundError` if pytest is invoked from another directory. The sibling guard in
`tests/test_dialect_builders.py` correctly uses `Path(__file__).resolve().parents[1]`.
**Fix:** mirror the existing convention:
`(Path(__file__).resolve().parents[1] / "encino_orm/model/query_builder.py")`.

### IN-05: CR-03 verdict — `0` is an acceptable sentinel, but the original gap truth is only re-scoped, not satisfied

**File:** `encino_orm/model/model.py:473-481`, `:521-533`; `.planning/ROADMAP.md:412`
**Issue:** The fix is semantically sound: it eliminates the wrong-row exposure and leaves `self.id`
`None`, so a later `update()` raises `FailOnUpdate` rather than corrupting another row. `0` is a
reasonable "id no disponible" sentinel for auto-PK engines (identity seeds start at 1), and it is
consistent with the pre-existing non-auto return of `0`. Two caveats, both documented:
(a) `0` is ambiguous with a legitimate id `0` and with the non-auto path, so a caller that assigns
`obj.id = await obj.insert(replace=True)` would set `0`; (b) the re-verification's gap truth
("`Model.insert(replace=True)` on MSSQL returns the id of the row it just inserted") remains
literally false — the id is still unavailable and the capture is deferred to Phase 4 / `04-02` /
POOL-03. The changelog, `deferred-items.md` and `ROADMAP.md` all state this honestly, but
`ROADMAP.md:412` marks Phase 2 "Complete" while that clause is unmet. No code change required;
recorded so the status does not read as "id capture done".

## Focus-area verdicts

| Focus area | Verdict |
|---|---|
| 1. Is CR-01 truly closed? Any identifier still unvalidated? | **Closed for reachable paths.** `_table` (ctor + join), aliases (ctor/join/join_subquery) use the strict allowlist; expressions use `_safe_column`; `alias.*` expands through the validated `_column_map`; `where`/`having` use `Filter._safe_field`. Validation is construction-time. Residuals: TOCTOU on post-construction `_table` mutation (IN-01) and the trailing-newline allowlist looseness (IN-02) — neither exploitable. |
| 2. Is the CR-02 guard correct and complete? | **Correct for conflict columns, incomplete overall.** Fails closed for every absent conflict column in both `build_insert` and `build_upsert`; does not fire for valid inputs (snapshots/golden strings untouched). But absent `update_cols` (direct builder) and empty `conflict_cols` (reachable via `Model.upsert(conflict=[])`) still emit invalid MERGE SQL — WR-01. |
| 3. Is CR-03's fix semantically sound? | **Yes.** Decides by the executed statement text, not stale driver state; returns `0` and leaves `obj.id` untouched, so `update()` fails loudly instead of targeting another row. Robust through `PoolDb`. Oracle covered (same guard; ORA-38104 fails before assignment). `0` sentinel acceptable and documented; the original "returns its own id" clause is re-scoped to Phase 4 (IN-05). |
| 4. Regression risk / byte-identity | **None found.** Guards add rejection only. Full suite `787 passed`; DB-free `707 passed`, 10 snapshots; `git diff --stat tests/__snapshots__/` empty; `mssql.py`/`oracle.py` unchanged. |
| 5. CHANGELOG / deferred-items accuracy | **Accurate and traceable.** Old + new behaviour described; no false "fixed" claim for the `columns[0]` fallback; ORA-38104 owner recorded in `deferred-items.md`, `ROADMAP.md` and `REQUIREMENTS.md`; the false "no unowned items" claim is gone. |

## Independent reproduction (this review)

| Check | Command | Result |
|---|---|---|
| Full suite (live engines) | `uv run pytest -q` | `787 passed` ✓ |
| DB-free + snapshots | `uv run pytest -q -m "not integration and not optional_engine"` | `707 passed`, 10 snapshots ✓ |
| Changed-file tests | `uv run pytest tests/test_query_builder.py tests/test_dialect_builders.py tests/test_sql_snapshots.py -q -m "not integration and not optional_engine"` | `121 passed` ✓ |
| CR-01 hostile `_table` | `QueryBuilder(Evil, None)` with `_table='t; DROP TABLE usuarios --'` | `ValueError: nombre de tabla inválido` ✓ |
| CR-02 absent conflict | `build_upsert(..., conflict=["id"])` / `build_insert(..., conflict=["id"])` | `ValueError: conflicto ['id'] no está en el INSERT` ✓ |
| WR-01a absent `update_cols` | `build_upsert(..., conflict=["a"], update_cols=["b"])` | emits `dst.b = src.b` (no raise) ✗ |
| WR-01b empty conflict | `Model.upsert(conflict=[])` on merge double | emits `ON ()`, reaches driver ✗ |
| IN-01 TOCTOU | mutate `M._table` after `QueryBuilder(M, None)` | `FROM t; DROP TABLE usuarios -- mm` ✗ |
| IN-02 trailing newline | `check_identifier("agentes\n", ...)` | returns `"agentes\n"` ✗ |
| Snapshots / adapters untouched | `git diff --stat d4df155~1..0455afb -- tests/__snapshots__/ encino_orm/mssql.py encino_orm/oracle.py` | empty ✓ |

---

_Reviewed: 2026-09-18T14:51:06Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
