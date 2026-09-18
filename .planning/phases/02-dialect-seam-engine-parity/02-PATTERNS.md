# Phase 2: Dialect Seam & Engine Parity - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 27 (10 new / generated + 17 modified) plus 10 existing test files to extend
**Analogs found:** 24 / 27 (3 partial/role-match)

> Authoritative shape: `02-RESEARCH.md`. Where the RESEARCH "Recommended Project Structure"
> and the code disagree, the code excerpts below are the source of truth for **byte-identical SQL**.

---

## File Classification

| New/Modified File | Action | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `encino_orm/dialects/__init__.py` | new | barrel/config | transform | `encino_orm/model/__init__.py` | exact |
| `encino_orm/dialects/identifiers.py` | new | utility | transform (pure) | `encino_orm/base.py:13,60-65` | exact |
| `encino_orm/dialects/builders.py` | new | service | transform (pure DML) | `encino_orm/sqlite.py:133-172` + `postgresql.py:154-195` + `mssql.py:192-224` | exact |
| `encino_orm/dialects/strategies.py` | new | config/value-object | transform | `encino_orm/model/column.py:4-7` + `model/domain.py` | role-match |
| `encino_orm/query.py` | modify | model/value-object | transform | `encino_orm/model/filter.py:32-43` (immutable `__slots__`) | role-match |
| `encino_orm/base.py` | modify | controller (ABC) | request-response | itself (`_check_identifier`, builders, `list_tables`) | exact |
| `encino_orm/sqlite.py` | modify | adapter | CRUD | itself (`insert/delete/update`, `_prepare`) | exact |
| `encino_orm/mysql.py` | modify | adapter | CRUD | itself | exact |
| `encino_orm/mariadb.py` | modify | adapter (subclass) | CRUD | `encino_orm/mysql.py` | exact |
| `encino_orm/postgresql.py` | modify | adapter | CRUD | itself | exact |
| `encino_orm/mssql.py` | modify | adapter | CRUD/merge | itself | exact |
| `encino_orm/oracle.py` | modify | adapter | CRUD/merge | itself | exact |
| `encino_orm/model/model.py` | modify | model/ORM | CRUD + DDL | itself (`count`, `sync_schema`, `insert_many`) | exact |
| `encino_orm/model/query_builder.py` | modify | builder | aggregate | itself (`count/sum/avg/min/max`) | exact |
| `encino_orm/model/types.py` | modify | utility | transform (DDL) | itself (`indexes_ddl`) | exact |
| `encino_orm/transfer.py` | modify | service | batch/file-I/O | itself (`_check_identifier`, `build_ddl`) | exact |
| `encino_orm/pool.py` | modify | wrapper/decorator | CRUD | itself (`insert/delete/update` delegation) | exact |
| `tools/ci/check_coverage_floors.py` | new | utility/CI | file-I/O (batch) | `tools/ci/check_skips.py` | exact |
| `.github/workflows/ci.yml` | modify | config | — | itself (job `test`) | exact |
| `docs/design/0-design.md` | modify | docs | — | itself (`§2.1 Query`) | exact |
| `pyproject.toml` | modify | config | — | itself (markers, per-file-ignores, mypy overrides) | exact |
| `tests/test_identifiers.py` | new | test | unit | `tests/test_engine.py` (pure unit, no DB) | exact |
| `tests/test_dialect_builders.py` | new | test | unit + spy | `tests/test_pool.py` (monkeypatch) + `test_postgresql.py:32-57` | exact |
| `tests/test_query.py` | new | test | unit | `tests/test_engine.py` | exact |
| `tests/test_sql_snapshots.py` | new | test | snapshot (DB-free) | `tests/test_mssql.py:32-55` / `test_oracle.py:37-68` | exact |
| `tests/__snapshots__/*.ambr` | new (generated) | test data | — | none (syrupy artifact) | none |
| `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` | modify | test | integration | themselves | exact |
| `tests/test_aggregates.py`, `test_migrations.py`, `test_engine.py`, `test_redis_cache.py` | modify | test | unit/integration | themselves | exact |

---

## Pattern Assignments

### `encino_orm/dialects/identifiers.py` (utility, pure transform)

**Analog:** `encino_orm/base.py` (canonical definition) + `encino_orm/transfer.py` (the duplicate to delete).

**Imports pattern** (`base.py:1-9`) — stdlib only, no core deps:

```python
import re
```

**Core pattern — the definition to move verbatim** (`base.py:12-13, 60-65`):

```python
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    @staticmethod
    def _check_identifier(value: str, label: str) -> str:
        """Valida que `value` sea un identificador SQL seguro (evita inyección en SAVEPOINT)."""
        if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
            raise ValueError(f"{label} inválido: {value!r}")
        return value
```

**The duplicate to collapse** (`transfer.py:16-23`) — note it re-implements the same body; 02-01 deletes it:

```python
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_identifier(value: str, label: str) -> str:
    """Valida que `value` sea un identificador SQL seguro (evita inyección)."""
    if not isinstance(value, str) or not _IDENTIFIER_RE.match(value):
        raise ValueError(f"{label} inválido: {value!r}")
    return value
```

**Error handling pattern** (existing convention — `CONVENTIONS.md`): `ValueError` with the offending value via `!r`; message text in Spanish. Preserve the exact wording so 02-01 is a zero-behavior-change move.

**Public naming:** the research sketch exposes `IDENTIFIER_RE` (no underscore) and `check_identifier(value, label)`. The 02-01 commit must keep behavior identical, so the module-level function keeps the `(value, label)` signature.

**Call-site styles to update (6 regexes, 2 checker shapes)** — grep both names in 02-01:

| File | Current | New call |
|------|---------|----------|
| `base.py:13,63` | `_IDENTIFIER_RE` + `_check_identifier` (canonical) | delegate `check_identifier` |
| `sqlite.py:13,115` | `_IDENTIFIER_RE.match(table)` in `columns_of` | `check_identifier` |
| `mysql.py:15,122` | `_IDENTIFIER_RE.match(table)` in `columns_of` | `check_identifier` |
| `transfer.py:16,19,106,109,112,144` | local regex + local checker | delete; import shared |
| `model/model.py:29,223,235,244,752,847` | `_IDENTIFIER_RE.match(...)` | `check_identifier` |
| `model/types.py:201,229` | `_IDENTIFIER_RE.match(name)` | `check_identifier` |
| `sql.py:8` `_COLUMN_RE` | **DO NOT TOUCH** — intentionally allows dots | leave + comment |

**Adapter delegate shape** (keeps the 5 `self._check_identifier(...)` call sites byte-identical):

```python
# encino_orm/base.py (after 02-01)
from .dialects.identifiers import check_identifier

class Db(ABC):
    @staticmethod
    def _check_identifier(value: str, label: str) -> str:
        return check_identifier(value, label)
```

**Source-level single-definition guard** (test recipe from RESEARCH Pitfall A) — assert exactly one `_IDENTIFIER_RE =` remains across `encino_orm/`.

---

### `encino_orm/dialects/builders.py` (service, pure DML transform)

**Analog:** the six adapters' `insert`/`update`/`delete` bodies. Simple canonical = `sqlite.py:133-172`; suffix canonical = `postgresql.py:154-195`; merge canonical = `mssql.py:192-224` / `oracle.py:191-226`.

**Imports pattern** — the builder module depends only on stdlib + `Query` + the sibling checker (no driver, no `Db`, avoids a cycle):

```python
# derived from RESEARCH §Pattern 2 + ARCHITECTURE anti-pattern "branches outside the adapter"
from ..query import Query
from .identifiers import check_identifier
```

**Core pattern — plain INSERT/UPDATE/DELETE to preserve byte-for-byte** (`sqlite.py:141-172`):

```python
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ",".join(f"{{{i}}}" for i in range(len(columns)))

        keyword = "INSERT"
        if replace:
            keyword = "INSERT OR REPLACE"
        elif ignore_duplicated:
            keyword = "INSERT OR IGNORE"

        sql = f"{keyword} INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
        return Query(sql, values)
```

```python
        where = " AND ".join(f"{col} = {{{i}}}" for i, col in enumerate(columns))
        sql = f"DELETE FROM {tabla} WHERE {where}"
```

```python
        set_clause = ",".join(f"{col} = {{{i}}}" for i, col in enumerate(set_cols))
        offset = len(set_cols)
        where = " AND ".join(f"{col} = {{{offset + i}}}" for i, col in enumerate(key_cols))
        sql = f"UPDATE {tabla} SET {set_clause} WHERE {where}"
        return Query(sql, set_vals + key_vals)
```

**Suffix variant — PostgreSQL ON CONFLICT** (`postgresql.py:166-175`):

```python
        sql = f"INSERT INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
        if replace:
            conflict_cols = ", ".join(conflict) if conflict else (columns[0] if columns else "id")
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)
            sql += f" ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}"
        elif ignore_duplicated:
            sql += " ON CONFLICT DO NOTHING"
```

**Merge variant — MSSQL (has `AS`)** (`mssql.py:203-216`):

```python
            conflict_cols = list(conflict) if conflict else ([columns[0]] if columns else ["id"])
            src = ", ".join(f"{{{i}}} AS {c}" for i, c in enumerate(columns))
            on = " AND ".join(f"dst.{c} = src.{c}" for c in conflict_cols)
            updates = ", ".join(f"dst.{c} = src.{c}" for c in columns)
            ins_cols = ",".join(columns)
            ins_vals = ",".join(f"src.{c}" for c in columns)
            sql = (
                f"MERGE INTO {tabla} AS dst "
                f"USING (SELECT {src}) AS src "
                f"ON ({on}) "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})"
            )
```

**Merge variant — Oracle (NO `AS`, plus `RETURNING`)** (`oracle.py:202-221`):

```python
            sql = (
                f"MERGE INTO {tabla} dst "
                f"USING (SELECT {src}) src "
                f"ON ({on}) "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})"
            )
        else:
            placeholders = ",".join(f"{{{i}}}" for i in range(len(columns)))
            sql = f"INSERT INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
            if "id" not in columns:
                sql += " RETURNING id INTO :ret_id"
```

**Validation pattern — `schema=` policy** (RESEARCH §`dialects/builders.py`; never widen the character class):

```python
def _qualified(table: str, schema: str | None) -> str:
    """Valida y compone `tabla` o `esquema.tabla`. Nunca relaja la allowlist."""
    table = check_identifier(table, "tabla")
    if schema is None:
        return table
    return f"{check_identifier(schema, 'esquema')}.{table}"
```

**Signature change (keyword-only so positional pool callers are unaffected):**

```python
def build_insert(table, data, *, strategy, conflict=None, replace=False,
                 ignore_duplicated=False, schema=None) -> Query: ...
def build_update(table, keys, values, *, schema=None) -> Query: ...
def build_delete(table, keys, *, schema=None) -> Query: ...
```

**Preservation invariants** (must hold exactly; see RESEARCH §Pattern 2):
1. Column order = `dict` insertion order; **no spaces** after commas (`a,b`, `$1,$2`).
2. Placeholder indices contiguous from 0; `update` numbers SET `0..n-1` then WHERE `n..`.
3. `replace` wins over `ignore_duplicated` (`elif`) — all six adapters already do this.
4. PostgreSQL `replace` with no `conflict` defaults target to `columns[0]`.
5. Oracle `RETURNING id INTO :ret_id` only when `"id" not in columns`; `:ret_id` is bound by `execute()`, not the builder.
6. `ignore_duplicated` carried as a `Query` constructor field for MSSQL/Oracle.

**Error handling:** raise `ValueError` from `check_identifier` **before** any SQL string exists. Add `"encino_orm/dialects/builders.py" = ["S608"]` to `pyproject.toml` per-file-ignores (trust boundary documented there).

---

### `encino_orm/dialects/strategies.py` (config/value-object, transform)

**Analog:** frozen value objects `encino_orm/model/column.py:4-7`; module-of-constants style `encino_orm/model/domain.py:23-40`.

**Core pattern** (`column.py:1-7`):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    datatype: str = "str"  # int, bool, str, datetime, date, numeric, blob, float
    name: str | None = None  # nombre de columna en la BD (si difiere del atributo)
```

**Target shape** (RESEARCH §Pattern 2) — three branches, not six:

```python
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

**Constants pattern:** module-level instances per dialect, mirroring `domain.py`'s exported presets. Adapters return one of these from `_insert_strategy(...)`. `MAX_PARAMS`/`MAX_ROWS` (DIAL-06) live here as module constants with provenance comments (see `pyproject.toml:96-103` ratchet-comment style for documenting measured values).

**No I/O, no statements:** coverage floor for this module is intentionally skipped (data only).

---

### `encino_orm/dialects/__init__.py` (barrel)

**Analog:** `encino_orm/model/__init__.py:1-52` (import block) + `:54-114` (`__all__`).

**Pattern:** import the public seam symbols and list them in `__all__`, sorted alphabetically (the repo's barrel convention). Research §Recommended Project Structure: re-export `check_identifier`, `build_*` here.

**Import organization** (`CONVENTIONS.md`): sibling modules use relative imports; keep `dialects/` importing `..query` only.

---

### `encino_orm/query.py` (model/value-object, transform) — DIAL-05

**Analog:** current file (`query.py:1-34`, the code to replace) + immutable `__slots__` pattern from `encino_orm/model/filter.py:32-43` + `object.__setattr__` idiom from `encino_orm/model/model.py:78-79`.

**Current defects to fix** (`query.py:1-34`) — the whole file is the "before":

```python
class Query:
    def __init__(self, sql: str, fields: list):
        self.sql_template: str = sql
        self.fields: list = fields
        self._param_name: str = "parameter_000"

        if sql.find("{0}") != -1:          # ← sentinel: only detects a leading {0}
            self.query = self.format(sql, fields, self._param_name)
        else:
            self.query = [sql, {}]

    def format(self, sql, columns: list | None = None, name="parameter_000"):
        ...
        for i, key in enumerate(cols):     # ← enumerate over params, not real {n}
            formatted_sql = formatted_sql.replace(f"{{{i}}}", f"%({key})s")
        return [formatted_sql, cols]

    def rebind(self, fields: list):        # ← DELETE (D-01)
        self.fields = fields
        self.query = self.format(self.sql_template, fields, self._param_name)
        return self

    def __str__(self):
        return str(self.query[0]) + str(self.query[1])
```

**Immutability idiom** (`filter.py:32-43`) — `__slots__` + read-only construction, same house style:

```python
class Filter:
    __slots__ = ("_args", "_op")

    def __init__(self, op: str, *args):
        self._op = op
        self._args = args
```

**Private-state idiom** (`model/model.py:78-79`) — the codebase's sanctioned escape hatch for internal state:

```python
def _set_private(obj, name, value):
    object.__setattr__(obj, name, value)
```

**Target shape:** see RESEARCH §Code Examples "`Query` — the target shape (DIAL-05)" (lines 571-652). Invariants the planner must not relax:

- `__slots__ = ("_sql_template", "_fields", "_ignore_duplicated", "_sql", "_params")` — slots **privados** (excluyen `__dict__` → una errata de nombre lanza). La superficie legible `sql_template`/`fields`/`ignore_duplicated` se expone con **properties sin setter**: un slot plano es un descriptor ESCRIBIBLE (así que `q.fields = []` tendría éxito) y un slot llamado igual que una property lanza `ValueError: 'fields' in __slots__ conflicts with class variable` al crear la clase. Ver la corrección anotada en RESEARCH §Code Examples.
- Constructor `Query(sql, fields, *, ignore_duplicated=False)`; `ignore_duplicated` es un **campo**, no se fija post-construcción.
- `.sql` = compilado `%(parameter_0000)s` (el antiguo `query[0]`); `.params` = dict (el antiguo `query[1]`); `.fields` = property de solo lectura que devuelve la MISMA lista de entrada; `.query` = property de solo lectura que devuelve un `[sql, params]` **nuevo**.
- `.with_params(values)` returns a **new** `Query`; re-validates cardinality.
- Cardinality: `set(re.findall(r"\{(\d+)\}", sql)) == set(range(len(values)))`; duplicates legal; raise `ValueError` with indices + count.
- `__eq__` compares `(sql_template, fields, ignore_duplicated)`; `__hash__` over `(sql_template, tuple(fields), ignore_duplicated)` and raises an explicit `TypeError` on unhashable params.
- `.query` must stay readable by the **6 adapters** (`qry.query[0]`/`qry.query[1]`) and 3 white-box tests, and `.sql_template` must stay readable by `pool.py:246`.

**Call sites that constrain the refactor (do not break):**

| Site | Reads |
|------|-------|
| `sqlite.py:105`, `mysql.py:112`, `postgresql.py:120`, `mssql.py:150`, `oracle.py:144` | `qry.query[0]`, `qry.query[1]` |
| `sqlite.py:238`, `mysql.py:265`, `postgresql.py:253`, `mssql.py:337`, `oracle.py:338` | `qry.query[0]` (migration ledger) |
| `pool.py:246` | `qry.sql_template` |
| `base.py:175` | `list(qry.fields)` |
| `migration.py:17` | `Query(sql, [])` (no placeholders, empty fields) |
| `tests/test_postgresql.py:22`, `test_oracle.py:33`, `test_mssql.py:28` | `q.query[0]`, `q.query[1]` |

**`ignore_duplicated` conflict to resolve** (RESEARCH §Pattern 3 / Pitfall E):
- Writers: `mssql.py:221-224` and `oracle.py:223-226` do `q.ignore_duplicated = True`.
- Readers: `mssql.py:256`, `oracle.py:263` do `getattr(qry, "ignore_duplicated", False)`.
- Asserts: `tests/test_mssql.py:41`, `tests/test_oracle.py:48` assert `q.ignore_duplicated is True`.
- Resolution: promote to constructor field; builders pass it in; attribute stays readable → **no test edit required**.

---

### `encino_orm/base.py` (controller/ABC, request-response)

**Analog:** itself.

**Imports pattern** (`base.py:1-9`) — add the seam import; keep `Query`:

```python
from .query import Query
```

**`_check_identifier` delegate** (`base.py:60-65`) — see identifiers section above.

**Builder delegation** (`base.py:95-109`) — the abstract signatures that set the keyword-only contract:

```python
    @abstractmethod
    def insert(
        self,
        tabla: str,
        data: dict,
        ignore_duplicated=False,
        replace=False,
        conflict: list[str] | None = None,
    ): ...

    @abstractmethod
    def delete(self, tabla: str, keys: dict): ...

    @abstractmethod
    def update(self, tabla: str, keys: dict, values: dict): ...
```

**The `COUNT(*)` bug site** (`base.py:158`) — the misleading one (works on SQLite/MySQL, `KeyError` on PG/MSSQL/Oracle):

```python
        total = (await self.fetch_one(Query(f"SELECT COUNT(*) FROM ({sql})", params)))["COUNT(*)"]
```

**The correct pattern already in-file** (`base.py:174-177`) — copy this to all 7 sites:

```python
        sql = qry.sql_template.strip().rstrip(";")
        count_qry = Query(f"SELECT COUNT(*) AS n FROM ({sql}) _encino_orm_count", list(qry.fields))
        row = await self.fetch_one(count_qry)
        total = row["n"] if row else 0
```

**Error handling pattern** (`base.py:42-49`) — transaction rollback template (unchanged):

```python
    @asynccontextmanager
    async def transaction(self):
        try:
            yield
            await self.commit()
        except Exception:
            await self.rollback()
            raise
```

---

### Adapters — `sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`

**Analog:** each file itself. The seam **replaces the `insert/update/delete` bodies with a `_insert_strategy` hook** and leaves `_prepare`/`columns_of`/`last_id`/`migrate` unchanged.

**Imports pattern (all six)** — drop the local `_IDENTIFIER_RE`, import the shared checker; `_PLACEHOLDER_RE` + `_to_<engine>` stay module-level:

```python
# sqlite.py:1-10 / mysql.py:1-12 / postgresql.py:1-11 / mssql.py:1-9 / oracle.py:1-9
import re
import time

from .base import Db, logger
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
```

**`_prepare` contract — UNCHANGED (do not move to core)**:

```python
# sqlite.py:104-105
    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_positional(qry.query[0], qry.query[1])

# postgresql.py:119-120
        return _to_postgres(qry.query[0], qry.query[1])

# mssql.py:149-150
        return _to_mssql(qry.query[0], qry.query[1])

# oracle.py:143-144
        return _to_oracle(qry.query[0], qry.query[1])
```

**Placeholder translators to keep as-is** (`sqlite.py:28-35`, `postgresql.py:28-35`, `mysql.py:39-46`, `mssql.py:26-33`, `oracle.py:26-37`) — e.g. PostgreSQL:

```python
def _to_postgres(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "$" + str(len(values))

    return _PLACEHOLDER_RE.sub(repl, sql), values
```

**Guard pattern** (`sqlite.py:100-102`) — unchanged:

```python
    def _ensure_connected(self):
        if not self._connection:
            raise ConnectionError("No hay conexión activa a la base de datos.")
```

**`columns_of` validation to migrate** (`sqlite.py:114-116`, `mysql.py:121-123`) — replace the local `_IDENTIFIER_RE.match` with the shared `check_identifier`:

```python
    async def columns_of(self, table: str) -> list[ColumnSpec]:
        if not _IDENTIFIER_RE.match(table):
            raise ValueError(f"nombre de tabla inválido: {table!r}")
```

**`ignore_duplicated` read sites to keep working** (`mssql.py:255-258`, `oracle.py:262-265`):

```python
            except Exception as exc:
                if getattr(qry, "ignore_duplicated", False) and self.is_unique_violation(exc):
                    return 0
                raise
```

**Per-adapter strategy constants to introduce:**

| Adapter | `kind` | `replace_prefix` / `ignore_prefix` | `merge_alias` / `conflict_target` |
|---------|--------|------------------------------------|-----------------------------------|
| `sqlite.py` | prefix | `INSERT OR REPLACE` / `INSERT OR IGNORE` | — |
| `mysql.py` | prefix | `REPLACE` / `INSERT IGNORE` | — |
| `mariadb.py` | inherits MySQL | inherits | — |
| `postgresql.py` | suffix | — | `conflict_target=True` |
| `mssql.py` | merge | — | `merge_alias="dst"` (SQL: `AS dst`) |
| `oracle.py` | merge | — | `merge_alias="dst"` (SQL: no `AS`) |

**MSSQL Oracle execute() extras stay adapter-local:** `SELECT CAST(@@IDENTITY AS INT)` (`mssql.py:261-264`), `RETURNING` output bind (`oracle.py:253-258`). Do not lift these into the seam.

---

### `encino_orm/model/model.py` (model/ORM, CRUD + DDL)

**Analog:** itself.

**Imports + regex** (`model/model.py:1-31`) — delete local `_IDENTIFIER_RE:29`, import `check_identifier`:

```python
import re
...
from encino_orm.query import Query

_MISSING = object()
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")   # ← remove
```

**`COUNT(*)` bug site** (`model/model.py:793-795`) — `Model.count`:

```python
        sql = f"SELECT COUNT(*) FROM {self._table}{where}"
        row = await self._get_db().fetch_one(Query(sql, params))
        return row["COUNT(*)"] if row else 0
```
→ becomes `SELECT COUNT(*) AS n ...` / `row["n"]`.

**`insert_many` hardcoded chunk** (`model/model.py:512-516`, `:527-546`) — DIAL-06 derives `chunk` from `MAX_PARAMS // n_columns`:

```python
    async def insert_many(cls, db=None, rows: list[dict] | None = None, *, chunk: int = 500) -> int:
        """Inserta varios registros en una transacción (multi-filas `VALUES`).

        Devuelve el total de filas insertadas. Los registros se particionan en
        *chunks* de `chunk` para no exceder el límite de parámetros del motor.
        """
        ...
                sql = f"INSERT INTO {cls._table} ({','.join(columns)}) VALUES " + ",".join(row_sqls)
                await db.execute(Query(sql, params))
```

**`sync_schema` ALTER sites to validate** (`model/model.py:887-918`) — catalog-derived `col` interpolated unvalidated:

```python
            await self._get_db().execute(
                Query(f"ALTER TABLE {self._table} ADD COLUMN {col} {ddl}", [])
            )
            ...
                await self._get_db().execute(
                    Query(f"ALTER TABLE {self._table} DROP COLUMN {col}", [])
                )
            ...
                        Query(f"ALTER TABLE {self._table} ALTER COLUMN {col} TYPE {ddl}", [])
            ...
                        Query(f"ALTER TABLE {self._table} MODIFY COLUMN {col} {ddl}", [])
```

**Existing validation call sites to route through the shared checker** (`:223, :235, :244, :752, :847`) — e.g. `_col` (`:241-246`):

```python
    @classmethod
    def _col(cls, field: str) -> str:
        col = cls._column_map().get(field, field)
        if not _IDENTIFIER_RE.match(col):
            raise ValueError(f"nombre de columna inválido: {col!r}")
        return col
```

**Private-state idiom** (`model/model.py:78-79`) — the sanctioned `object.__setattr__` pattern (relevant if `Query` reuses it).

---

### `encino_orm/model/query_builder.py` (builder, aggregate)

**Analog:** itself.

**Validation pattern already in-file** (`query_builder.py:15-33`) — `_COLUMN_RE` allows dotted qualified names (keep; do NOT unify with the strict allowlist):

```python
_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _safe_column(expr: str) -> str:
    expr = expr.strip()
    if expr == "*":
        return expr
    if expr.endswith(".*"):
        if _COLUMN_RE.match(expr[:-2]):
            return expr
        raise ValueError(f"nombre de columna inválido: {expr!r}")
    if not _COLUMN_RE.match(expr):
        raise ValueError(f"nombre de columna inválido: {expr!r}")
    return expr
```

**The 5 aggregate bug sites** (`query_builder.py:241-279`) — all read by expression text:

```python
    async def count(self) -> int:
        ...
        sql = f"SELECT COUNT(*) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        return row["COUNT(*)"] if row else 0

    async def sum(self, column: str):
        ...
        sql = f"SELECT SUM({column}) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        key = f"SUM({column})"
        return row[key] if row and row[key] is not None else 0

    async def avg(self, column: str):
        ...
        return row[f"AVG({column})"] if row else None

    async def min(self, column: str):
        ...
        return row[f"MIN({column})"] if row else None

    async def max(self, column: str):
        ...
        return row[f"MAX({column})"] if row else None
```
→ all become `... AS n` + `row["n"]` (Pitfall C: 7 sites total, not 3).

---

### `encino_orm/model/types.py` (utility, DDL transform)

**Analog:** itself.

**Regex + validation site** (`types.py:201, 227-230`) — delete local regex, import shared:

```python
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

...
        name = name.replace(" ", "_")
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(f"nombre de índice inválido: {name!r}")
```

---

### `encino_orm/transfer.py` (service, batch/file-I/O)

**Analog:** itself.

**Duplicate checker to delete** (`transfer.py:16-23`) — see identifiers section. `build_ddl` call sites (`:106, :109, :112, :144`) then use the shared import.

**Batch loop pattern** (`transfer.py:156-168`) — context for `MAX_PARAMS`/`MAX_ROWS` consumers (DIAL-06), unchanged this phase:

```python
    rows = await src.fetch_all(Query(f"SELECT * FROM {table}", []))
    total = 0
    async with dst.transaction():
        ...
        for row in rows:
            ...
            await dst.execute(dst.insert(table, data))
```

---

### `encino_orm/pool.py` (wrapper, CRUD) — Pitfall L

**Analog:** itself.

**The divergent seventh DML signature to fix** (`pool.py:180-187`) — `conflict` (and new `schema=`) is silently dropped:

```python
    # --- Builders (no requieren conexión) ---
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False):
        return self._template.insert(tabla, data, ignore_duplicated, replace)

    def delete(self, tabla: str, keys: dict):
        return self._template.delete(tabla, keys)

    def update(self, tabla: str, keys: dict, values: dict):
        return self._template.update(tabla, keys, values)
```

**Fix:** mirror the full abstract signature from `base.py:95-103` including `conflict` and `schema=`, or delegate `**kwargs`. Abstract signature for reference:

```python
    def insert(
        self,
        tabla: str,
        data: dict,
        ignore_duplicated=False,
        replace=False,
        conflict: list[str] | None = None,
    ): ...
```

**`sql_template` read to preserve** (`pool.py:246`):

```python
            if qry.sql_template.lstrip().upper().startswith(("INSERT", "REPLACE")):
```

**Test analog for the fix** (`tests/test_pool.py:127-130`) — extend `test_builders` with a `conflict=` forward assertion using the `FakeDb` double (`test_pool.py:11-81`).

---

### `tools/ci/check_coverage_floors.py` (utility/CI, file-I/O)

**Analog:** `tools/ci/check_skips.py` — exact stdlib-only, fail-closed script shape.

**Imports + fail-closed read** (`check_skips.py:10, 22-32`):

```python
import sys
import xml.etree.ElementTree as ET


def main(argv: list[str] | None = None) -> int:
    """Devuelve 1 si hay algun test omitido o si el XML no se puede leer."""
    if argv is None:
        argv = sys.argv
    path = argv[1] if len(argv) > 1 else "junit.xml"
    try:
        skipped = total_skipped(path)
    except (OSError, ET.ParseError) as exc:
        # Falla cerrado: un XML ausente o ilegible no puede convertirse en un 0.
        print(f"FALLO: no se pudo leer el JUnit-XML {path!r}: {exc}", file=sys.stderr)
        return 1
    ...
```

**`__main__` idiom** (`check_skips.py:43-44`):

```python
if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

**Target shape:** RESEARCH §Code Examples "`tools/ci/check_coverage_floors.py` (02-05)" (lines 747-803). Key invariants: `FLOORS` map; `_norm()` normalizes `\`→`/`; **fail closed** when a floor module is missing from `coverage.json` (Pitfall J); exit 1 with `FALLO:` lines to stderr; OK message on success. Add `"tools/ci/check_coverage_floors.py" = ["S314"]`? — only if it parses XML; it parses JSON, so no `S` ignore is needed.

---

### `.github/workflows/ci.yml` (config) — DIAL-08

**Analog:** itself.

**Service pattern to copy for MariaDB/Redis** (`ci.yml:28-55`, MySQL):

```yaml
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: admin
          MYSQL_ROOT_HOST: "%"
          MYSQL_DATABASE: encino_orm_test
        ports:
          - 3306:3306
        options: >-
          --health-cmd="mysqladmin ping -h 127.0.0.1 --password=admin --silent"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=12
```

**Env + required-engine switch pattern** (`ci.yml:74-93`):

```yaml
      - name: Run tests
        env:
          COVERAGE_FILE: .coverage.py${{ matrix.python-version }}
          ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql
          ENCINO_ORM_MYSQL_HOST: 127.0.0.1
          ...
```

**Run + skip gate** (`ci.yml:99-107`):

```yaml
        run: >
          uv run pytest -q -m "not optional_engine" --junitxml=junit.xml
          --cov=encino_orm --cov-branch --cov-report=

      - name: Gate — ningún test omitido
        if: always()
        run: uv run python tools/ci/check_skips.py junit.xml
```

**Coverage job to extend** (`ci.yml:244-250`):

```yaml
      - name: Combinar cobertura de la matriz
        run: uv run coverage combine

      - name: Gate de cobertura (fail_under desde pyproject.toml)
        run: uv run coverage report
```
→ add `uv run coverage json -o coverage.json` + `uv run python tools/ci/check_coverage_floors.py coverage.json`.

**Required changes (RESEARCH §Pattern 6):**
- `test` job: add `mariadb` (port **`3307:3306`**) + `redis` services; `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql,mariadb,redis`; `--extra cache`; add `ENCINO_ORM_MARIADB_*` / `ENCINO_ORM_REDIS_URL`.
- New `engine-heavy` job: Python **3.12 only**, `mssql` + `oracle` services, `timeout-minutes: 30`, `--extra mssql --extra oracle`, **mandatory ODBC install step**, `ENCINO_ORM_ORACLE_SERVICE=FREEPDB1`. Never `continue-on-error`.
- Remove `optional_engine` markers from `test_mariadb.py:52` and `test_redis_cache.py:11` when promoting.

**ODBC install snippet** — RESEARCH §Pattern 6 (lines 418-428), copy verbatim into the job.

---

### `docs/design/0-design.md` (docs) — D-05

**Analog:** itself, `§2.1 Query` (`0-design.md:33-90`).

**Sections to rewrite** (document the removed `rebind`):

- `:22` — table row 8 mentions `rebind`.
- `:35` — prose says queries are reused via `rebind`.
- `:38-72` — the class sketch (`self.query` mutable, `format`, `rebind`).
- `:79-89` — examples using `q.query` and `q.rebind(...)`.
- `:295-296` — `qry.query[0]` / `list(qry.query[1].values())`.
- `:397` — `q_tpl.rebind([nombre, 1])`.

**Target:** document `.sql`/`.params`/`.fields`/`.query` (read-only) and `.with_params()`; add a migration note (`rebind` → `with_params`). Style: Spanish prose + fenced Python, per `CONVENTIONS.md` (no `Args:`/`Returns:` sections).

---

### `pyproject.toml` (config)

**Analog:** itself.

**Markers + addopts to respect** (`pyproject.toml:50-80`) — syrupy must not break `--strict-markers`/`filterwarnings=["error"]`:

```toml
addopts = "-ra --strict-markers"
xfail_strict = true
filterwarnings = [
    "error",
    ...
]
markers = [
    "integration: ...",
    "optional_engine: ...",
    "concurrency: ...",
    "benchmark: ...",
]
```

**Per-file-ignores to extend** (`pyproject.toml:127-177`) — add:

```toml
# S608: constructores de dialecto centralizados (frontera de confianza documentada en el módulo).
"encino_orm/dialects/builders.py" = ["S608"]
```

**Dev group to extend** (`pyproject.toml:254-270`) — pin syrupy exactly, mirroring the `ruff==` rationale comment:

```toml
    "ruff==0.16.8",
    ...
    "coverage>=7.16.1",
```
→ add `"syrupy==6.1.1"` **behind a `checkpoint:human-verify`** (slopcheck `[SUS]`).

**mypy overrides to ratchet** (`pyproject.toml:238-252`) — `oracle`, `mysql`, `mssql`, `model.references`, `base` are slated for Fase 2. New `dialects/*` modules are checked strictly (no override). `model.model`/`model.query_builder` remain ignored until their Phase-2 cleanup.

**Coverage config context** (`pyproject.toml:82-109`) — global `fail_under = 82`; per-module floors go in the new script, not here.

---

## Tests

### `tests/test_identifiers.py` (new, unit)

**Analog:** `tests/test_engine.py:19-80` — pure unit, no DB, plain `def test_*` + `pytest.raises`.

**Pattern:**

```python
def test_engine_of_invalid():
    with pytest.raises(ValueError):
        engine_of("mongodb")
```

**Coverage:** accept/reject table for `check_identifier` (`"t"`, `"_x"`, `"a1"` accepted; `"t; DROP TABLE x; --"`, `` "`x`" ``, `"a.b"`, `"1abc"`, `""`, `"a b"`, `"a-b"` rejected), plus the **source-level single-definition guard** (`grep`-style assert that only one `_IDENTIFIER_RE =` remains across `encino_orm/`). `tests/**` already ignores `PT011` (`pyproject.toml:131`), so broad `pytest.raises(ValueError)` is fine.

---

### `tests/test_dialect_builders.py` (new, unit + spy)

**Analog:** `tests/test_pool.py:11-89` (hand-written fake + `monkeypatch.setitem`) and `tests/test_postgresql.py:32-57` (unconnected adapter builder + `_prepare`).

**Hand-written fake / monkeypatch pattern** (`test_pool.py:84-87`):

```python
@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb
```

**Unconnected-adapter builder pattern** (`test_postgresql.py:32-42`):

```python
    def test_insert_builder_default(self):
        db = PostgresDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
        assert sql == "INSERT INTO t (a,b) VALUES ($1,$2)"
        assert values == [1, "x"]
```

**Spy-rejection recipe** (RESEARCH §Code Examples "Spy-rejection test", lines 715-741): monkeypatch `db._prepare` to record calls; assert `reached == []` after each `pytest.raises(ValueError)`. Recommendation from RESEARCH: prefer **explicit per-adapter tests in the existing per-engine files** over `@pytest.mark.parametrize` (repo has zero parametrize usage today).

**Byte-identical regression oracle:** the pre-existing golden-string assertions in `test_postgresql.py:20-57`, `test_mssql.py:26-67`, `test_oracle.py:31-68`, `test_mysql.py`, `test_sqlite.py` — 02-02 must land with **zero** edits to these (Pitfall M).

---

### `tests/test_query.py` (new, unit) — DIAL-05

**Analog:** `tests/test_engine.py` (pure unit) + the 3 white-box tests that read `.query` (`test_postgresql.py:22`, `test_oracle.py:33`, `test_mssql.py:28`).

**Coverage:** immutability (attribute assignment raises), `with_params()` returns a new object and leaves the original unchanged, sparse/duplicate/unused/out-of-range `{n}`, `__hash__` raises `TypeError` on an unhashable param, equal Queries hash equal, `not hasattr(Query, "rebind")`, and empty-fields/no-placeholder → `[sql, {}]` compatibility. Existing `.query` reads must keep passing unmodified.

---

### `tests/test_sql_snapshots.py` (new, snapshot, DB-free) — DIAL-07

**Analog:** `tests/test_mssql.py:32-55` / `tests/test_oracle.py:37-68` — construct adapter **without `connect()`**, call builder, run `_prepare()`.

**DB-free pattern** (`test_mssql.py:32-36`):

```python
    def test_insert_builder_default(self):
        db = MssqlDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
        assert sql == "INSERT INTO t (a,b) VALUES (?,?)"
        assert values == [1, "x"]
```

**Target shape:** RESEARCH §Code Examples "`tests/test_sql_snapshots.py`" (lines 805-839): `assert {"sql": sql, "values": values} == snapshot`. Scope: 6 dialects × `insert` (plain / `ignore_duplicated` / `replace`), `update`, `delete`, plus count/paginate/list_tables SQL. `.ambr` files land in `tests/__snapshots__/` and **must be committed**. Gate, not advisory.

**Environment interactions to verify first:** `--strict-markers` + syrupy's `syrupy_snapshot` marker (A4) and `filterwarnings=["error"]` (A4).

---

### Per-engine test extensions (modify)

**Analog:** themselves; skip-guard from `tests/conftest.py:32-44`.

**Skip-guard pattern** (`test_mariadb.py:36-40`):

```python
    admin = MariadbDb()
    try:
        await admin.connect(**cfg)
    except Exception as e:
        engine_unavailable("mariadb", e)
```

**Integration class pattern** (`test_mariadb.py:51-79`):

```python
@pytest.mark.integration
@pytest.mark.optional_engine
class TestMariadbLifecycle:
    @pytest.mark.asyncio
    async def test_insert_and_last_id(self, mariadb_connected_db):
        ...
```

**White-box helper import pattern** (`test_postgresql.py:7`):

```python
from encino_orm.postgresql import _rowcount, _to_postgres
```

**DIAL-03/DIAL-09 additions:** `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` assertions in `test_postgresql.py`, `test_mssql.py`, `test_oracle.py`, `test_mariadb.py`, `test_mysql.py`, `test_sqlite.py`. Add the spy-rejection tests here too (per RESEARCH recommendation).

**DIAL-03 unit extension** (`tests/test_aggregates.py:22-32`) — assert the generated SQL contains `AS n` and `sum/avg/min/max` still return correct values on SQLite.

**DIAL-04 unit extension** (`tests/test_migrations.py`, `-k sync_schema`) — catalog-derived malicious column name rejected before any `ALTER TABLE` reaches the driver (spy on `_get_db().execute`).

**DIAL-06 unit extension** (`tests/test_engine.py`) — each of the 6 dialects exposes `MAX_PARAMS`/`MAX_ROWS`; `insert_many`'s chunk derives from them.

**Marker removal** (`test_mariadb.py:52`, `test_redis_cache.py:11`) — delete `optional_engine` in the same commit that adds the service + env var (Pitfall H).

---

## Shared Patterns

### Identifier validation (the single seam)
**Source:** `encino_orm/dialects/identifiers.py` (new; moved from `base.py:13,60-65`).
**Apply to:** all 6 adapters' `columns_of`/`save_point`/`rollback`; `transfer.py`; `model/model.py`; `model/types.py`; `dialects/builders.py`.
**Rule:** validate **before** any SQL string is built. Never widen `^[A-Za-z_][A-Za-z0-9_]*$`; add `schema=` for qualified names. Leave `sql.py:8 _COLUMN_RE` and `model/query_builder.py:16 _COLUMN_RE` untouched (they intentionally allow dots) with a comment explaining why.

### Placeholder contract (`%(parameter_0000)s`)
**Source:** `query.py` (compiled SQL) + each adapter's `_prepare`.
**Apply to:** all execution paths. The seam returns `Query`; adapters translate natively. Do **not** move translation into core; do **not** change `_prepare`'s `(sql, params)` contract.

### Error handling
**Source:** `base.py:42-49` (transaction), `CONVENTIONS.md` (raise specific exceptions, Spanish f-strings, `ValueError` with `!r`).
**Apply to:** builders raise `ValueError` on bad identifiers; `Query` raises `ValueError` on cardinality mismatch and `TypeError` on unhashable params.

### Immutability (`__slots__` + read-only properties)
**Source:** `model/filter.py:32-43`; private-state escape hatch `model/model.py:78-79`.
**Apply to:** `Query` only in this phase.

### Barrel exports
**Source:** `encino_orm/model/__init__.py:1-114`, `encino_orm/__init__.py:1-80`.
**Apply to:** `dialects/__init__.py`. Add new public symbols to both the import block and `__all__`.

### Deferred/lazy imports
**Source:** `base.py:25-28` (`from .sql import SqlFunctions`), `base.py:151` (`from .model.records import Records`).
**Apply to:** `dialects/` must import only stdlib + `..query`; no driver, no optional layer. `Query` must not import dialects (no cycle).

### Deterministic test doubles (no `unittest.mock`)
**Source:** `tests/test_pool_characterization.py:29-104` (hand-written `FakeDb`), `:106-144` (`EventBarrier`), `:147-156` (`monkeypatch.setitem` fixtures).
**Apply to:** `test_dialect_builders.py` spy tests, `test_pool.py` conflict-forward test, `sync_schema` rejection tests.

### stdlib-only CI gates, fail-closed
**Source:** `tools/ci/check_skips.py:22-40`.
**Apply to:** `tools/ci/check_coverage_floors.py`.

### CI required-engine switch
**Source:** `tests/conftest.py:26-44` (`required_engines`/`engine_unavailable`) + `ci.yml:83` (`ENCINO_ORM_REQUIRE_ENGINES`) + `ci.yml:100` (`-m "not optional_engine"`).
**Apply to:** promoting MariaDB/Redis; adding the `engine-heavy` job. Promotion = delete marker + add env vars + add service + add extra, same commit.

---

## No Analog Found

| File | Role | Data Flow | Reason / Fallback |
|------|------|-----------|-------------------|
| `encino_orm/dialects/strategies.py` | config/value-object | transform | No per-dialect strategy-object precedent; closest is `model/column.py` frozen dataclass + `model/domain.py` constants. Use RESEARCH §Pattern 2 shape. |
| `tests/__snapshots__/*.ambr` | test data | — | No snapshot infrastructure exists. Generate with syrupy `--snapshot-update`, commit, gate. |
| `tests/test_sql_snapshots.py` | test | snapshot | No syrupy usage exists; use the unconnected-adapter pattern (`test_mssql.py:32-55`) + RESEARCH §Code Examples. |

---

## Metadata

**Analog search scope:** `encino_orm/` (all subpackages), `tests/`, `tools/ci/`, `.github/workflows/`, `pyproject.toml`, `docs/design/`.
**Files read for extraction:** 30 (query, base, 6 adapters, model/model, model/query_builder, model/types, model/column, model/filter, model/domain, model/__init__, transfer, pool, _rows, sql, engine, __init__, check_skips, ci.yml, conftest, pyproject, 0-design, 8 test files).
**Pattern extraction date:** 2026-09-17

**Critical downstream reminders for the planner:**
1. **02-01 must be a pure move** — zero diff in generated SQL and zero test edits; prove it with the existing golden-string tests. Do not touch `sql.py:_COLUMN_RE`.
2. **02-02's acceptance criterion is byte-identical generated SQL** — the existing builder assertions in `test_{postgresql,mssql,oracle,mysql,sqlite}.py` are the regression oracle; any edit to them is a finding, not a fix.
3. **DIAL-03 is 7 sites, not 3** — `base.py:158`, `model/model.py:795`, `model/query_builder.py:246,254,263,271,279`.
4. **`ignore_duplicated` must become a `Query` constructor field**, not an attribute assigned after construction (`mssql.py:223`, `oracle.py:225`).
5. **`Query.query` must stay readable** (fresh list) so DIAL-05 does not touch the 6 adapters or 3 white-box tests; `sql_template` must stay readable for `pool.py:246`.
6. **`syrupy` install is gated behind `checkpoint:human-verify`** (slopcheck `[SUS]`, false positive).
7. **ODBC Driver 18 is mandatory** in the `engine-heavy` job; `ENCINO_ORM_ORACLE_SERVICE=FREEPDB1` for the CI Oracle image.
