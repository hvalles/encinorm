# Documento de Diseño — funcionalidades faltantes (encinorm)

Este documento consolida el **diseño de las funcionalidades omitidas** en el alcance
actual, identificadas y ponderadas en `prompts/analisys-06.md`. Cubre: migraciones
de esquema, operaciones masivas/upsert, tipos `Decimal` y `JSON`, relaciones
`has_many`, alcance por fila (multi-tenant), observabilidad, CLI de codegen,
agregados `avg`/`min`/`max` y borrado lógico automático. La capa **GraphQL** se
documenta por separado en `docs/design/3-graphql.md` (se referencia en §12).

> Complementa `docs/design/1-model.md`, `docs/design/2-constraint.md`,
> `docs/design/5-security.md`, `docs/design/4-crud.md` y `docs/design/6-from_db.md`.
> No modifica la interfaz pública de `Db` (solo extiende `Model`/`QueryBuilder`
> con métodos aditivos y añade módulos nuevos).

---

## 1. Contexto y Objetivos

| # | Objetivo | Origen (analisys-06) |
|---|----------|----------------------|
| 1 | Migraciones de esquema **versionadas** (`up`/`down`) y **diff** modelo↔BD. | #2 (Alto) |
| 2 | Operaciones **masivas** (`insert_many`) y **upsert** (`save`/`on_conflict`). | #3, #4 |
| 3 | Tipos de dato `Decimal` y `JSON` (de)serializados por motor. | #5, #6 |
| 4 | Relaciones **uno-a-muchos** (`has_many`). | #7 |
| 5 | Alcance por fila / **multi-tenancy** (`scope`). | #8 |
| 6 | **Observabilidad**: logging estructurado + métricas de consultas. | #9 |
| 7 | **CLI** de codegen (`encinorm generate models`). | #10 |
| 8 | Agregados `avg`/`min`/`max` en `QueryBuilder`. | #11 |
| 9 | **Soft-delete** automático en consultas. | #12 |
| 10 | Capa GraphQL (diseño existente). | #1 |

---

## 2. Arquitectura y ubicación

```
encinorm/
├── encinorm/
│   ├── migration.py            # NUEVO: Migration + runner + load_from_dir
│   ├── cli.py                  # NUEVO: CLI (argparse) — `generate models`
│   ├── observability.py        # NUEVO: QueryTracer + métricas (opcional)
│   ├── model/
│   │   ├── types.py            # + datatype "json" en DDL_MAP / PY_TYPE_TO_DATATYPE
│   │   ├── model.py            # + bulk/upsert/save, Decimal+JSON serialize, scope, soft-delete
│   │   ├── domain.py           # + DECIMAL, JSON
│   │   ├── query_builder.py    # + avg/min/max
│   │   └── references.py       # + has_many (colecciones inversas)
│   └── graphql/                # (ver docs/design/3-graphql.md, no se repite aquí)
└── docs/
    └── 7-missing.md       # este documento
```

- Todo lo nuevo es **aditivo** (no cambia firmas existentes) o **módulos nuevos**.
- Sin dependencias nuevas salvo `strawberry-graphql` (GraphQL) — ya documentada.

---

## 3. Migraciones de esquema

### 3.1. `Migration` + runner

Hoy `db.migrate(name, sql)` registra en `_encinorm_migrations` pero no hay
archivos versionados ni `down`. Se añade una abstracción mínima:

```python
# encinorm/migration.py (concepto)
from dataclasses import dataclass
from encinorm.query import Query

@dataclass(frozen=True)
class Migration:
    name: str
    up: Query | str
    down: Query | str | None = None     # opcional (rollback)

async def apply_migration(db, m: Migration) -> None:
    await db.migrate(m.name, _to_query(m.up))

async def rollback_migration(db, m: Migration) -> None:
    if m.down is None:
        raise MigrationError(f"{m.name} no tiene down")
    await db.migrate(f"{m.name}:down", _to_query(m.down))

def migrations_from_dir(path: str) -> list[Migration]:
    """Carga `NNN_descripcion.py` en orden; cada archivo define `MIGRATION`."""
```

### 3.2. Diff de esquema (evolución)

`sync_schema()` hoy es **aditivo** (solo `ADD COLUMN`). Se extiende con un plan de
diff que detecta columnas **eliminadas** y **cambios de tipo**:

```python
# encinorm/model/model.py (concepto)
async def diff_schema(self, engine=None) -> dict:
    """Compara modelo vs BD -> {"added": [...], "dropped": [...], "changed": [...]}"""
    ...

async def sync_schema(self, engine=None, drop_missing=False, alter_types=False) -> dict:
    # añade columnas; si drop_missing -> DROP; si alter_types -> ALTER COLUMN TYPE
    ...
```

| Cambio | Acción |
|--------|--------|
| columna nueva | `ALTER TABLE ... ADD COLUMN` |
| columna eliminada | `ALTER TABLE ... DROP COLUMN` (`drop_missing=True`) |
| tipo cambiado | `ALTER COLUMN ... TYPE` (PG) / `MODIFY COLUMN` (MySQL) / SQLite: recrear tabla |

> **Ambigüedad (SQLite):** cambiar tipo exige recrear la tabla. Decisión §13-1.

---

## 4. Operaciones masivas y upsert

### 4.1. `insert_many` (bulk)

```python
# encinorm/model/model.py (concepto)
@classmethod
async def insert_many(cls, db, rows: list[dict], *, chunk: int = 500) -> int:
    """Inserta varios registros en una transacción. Devuelve el total."""
    # INSERT INTO t (c1, c2, ...) VALUES (...), (...), ...  (por chunks)
```

- Multi-filas `VALUES` en un solo statement, en *chunks* de `chunk` filas.
- Envuelto en `db.transaction()` (atomicidad). Alternativa futura: `COPY` en PG.

### 4.2. `save()` y `upsert()`

```python
class Model:
    async def insert(self, *, ignore_duplicated=False, replace=False) -> int:
        # expone los flags ya existentes en Db.insert(...)
        ...

    async def save(self, keys=None) -> int:
        """Insert si no existe; update si sí (find-or-create idempotente)."""
        obj = await self.load(keys or ["id"])
        if obj._exists:
            return await self.update(keys=keys)
        return await self.insert()

    async def upsert(self, conflict: list[str], values: dict | None = None) -> int:
        """INSERT ... ON CONFLICT (col) DO UPDATE (SQLite/PG) / ON DUPLICATE KEY (MySQL)."""
```

- `Db.insert` ya soporta `ignore_duplicated`/`replace`; `Model.insert` solo los
  **expone** (firma aditiva con defaults).
- `upsert` requiere un builder nuevo por motor (§13-2).

---

## 5. Tipos `Decimal` y `JSON`

### 5.1. `Decimal` (dinero exacto)

```python
# encinorm/model/domain.py (concepto)
from decimal import Decimal
DECIMAL = make_constraint(Decimal)             # datatype "numeric"
```

- `_serialize(Decimal)` → `str(value)`; `_from_db` → `Decimal(value)` cuando el
  campo base es `Decimal`.
- SQLite: `NUMERIC`/`REAL` pierde precisión; documentar que `Decimal` es exacto en
  MySQL `DECIMAL` y PG `NUMERIC` (§13-3).

### 5.2. `JSON`

```python
# encinorm/model/types.py (concepto)
PY_TYPE_TO_DATATYPE[dict] = "json"     # y list -> "json"
DDL_MAP["sqlite"]["json"] = "TEXT"
DDL_MAP["mysql"]["json"] = "JSON"
DDL_MAP["postgres"]["json"] = "JSONB"

# encinorm/model/domain.py (concepto)
JSON = make_constraint(dict, datatype="json")
```

- `_serialize(dict|list)` → `json.dumps(default=str)`; `_from_db` → `json.loads`
  cuando el campo base es `dict`/`list`.
- PG `JSONB` permite indexar; MySQL `JSON` es texto validado; SQLite `TEXT`.

---

## 6. Relaciones uno-a-muchos (`has_many`)

Se añade la colección **inversa** (padre → hijos), complementaria a las
referencias 1:1 actuales (`_references_def`):

```python
# encinorm/model/references.py (concepto)
class Region(Model):
    _table = "regiones"
    region: str | None = None
    _has_many_def = {
        "agentes": {"model": Agente, "foreign_key": "region_id"},
    }

agentes = await region["agentes"]          # list[Agente] (search por FK)
```

- `_has_many_def` se procesa en `__init__` (igual que `_references_def`).
- Acceso perezoso por índice (`region["agentes"]`), con caché por instancia.
- `batch_reference` se extiende a colecciones (una consulta `IN (...)` por página),
  evitando N+1 (§13-4).

---

## 7. Alcance por fila / multi-tenancy (`scope`)

```python
# encinorm/model/model.py (concepto)
class ScopedModel(Model):
    _scope: Filter | None = None      # filtro por fila (tenant/usuario)

    @classmethod
    async def scope(cls, **ctx) -> Filter:
        """Devuelve el Filter que restringe las filas visibles (p. ej. tenant_id)."""

    async def search(self, filter=None, **kw):
        return await super().search((filter or EMPTY) & await self.scope(), **kw)
```

- `search`/`paginate`/`count` combinan el filtro del usuario con el `scope`
  (intersección `&`), **sin** exponer filas ajenas al tenant.
- Se integra con `security` (el `scope` puede derivarse del `user_id` del JWT),
  reutilizando `PermissionSet` para permisos y `scope` para visibilidad por fila.
- Alternativa sin herencia: `with_scope(db, filtro)` / contextvar (§13-5).

---

## 8. Observabilidad

```python
# encinorm/observability.py (concepto)
class QueryTracer:
    """Registra consultas con timing, params y contexto (trace_id)."""
    def __init__(self, logger, *, level=logging.DEBUG):
        ...
    async def wrap(self, engine, method, sql, params, elapsed): ...

# Uso: los motores ya llaman a logger.debug; se sustituye por el tracer
# (timing estructurado + trace_id por contextvar).
```

- Añade: `trace_id` por request (contextvar), `elapsed`, y un contador/métricas
  (`queries`, `rows`, `errors`) opcional, además de `PoolDb.stats` (ya existente).
- No cambia el rendimiento en producción (nivel `DEBUG`/opt-in).

---

## 9. CLI de codegen

```python
# encinorm/cli.py (concepto)
import argparse

def main(argv=None) -> int:
    # subcomandos:
    #   encinorm generate models <engine> --db ... [tablas] --folder out/
    #       -> usa encinorm.introspection.generate_model
    ...

# pyproject.toml
# [project.scripts]
# encinorm = "encinorm.cli:main"
```

- Solo stdlib (`argparse`); envuelve `encinorm.introspection`.
- Flujo: conectar → `list_tables` → seleccionar (o todas) → `generate_model` por tabla.

---

## 10. Agregados `avg`/`min`/`max`

```python
# encinorm/model/query_builder.py (concepto)
class QueryBuilder:
    async def avg(self, column): ...   # SELECT AVG(col)
    async def min(self, column): ...   # SELECT MIN(col)
    async def max(self, column): ...   # SELECT MAX(col)
```

- Mismo patrón que `sum`/`count` (usan `_build_base`). Esfuerzo mínimo.

---

## 11. Soft-delete automático

```python
# encinorm/model/model.py (concepto)
class Model:
    async def search(self, filter=None, ..., include_deleted: bool = False):
        if not include_deleted:
            filtro = Filter.eq("enabled", True) & (filter or ...)
        ...
```

- `search`/`paginate`/`count` aceptan `include_deleted=False` (por defecto ocultan
  `enabled=0`). `load` por id **sí** devuelve borrados (auditoría).
- **Ambigüedad (§13-6):** cambiar el default de `search` puede romper código que
  hoy lee borrados; se propone `include_deleted=False` explícito y documentar el
  cambio.

---

## 12. Capa GraphQL

Diseño completo en `docs/design/3-graphql.md` (Strawberry + `build_schema`,
`FilterInput`, queries `list/get/count`, mutations, DataLoader para relaciones).
Se incluye en el alcance de este plan como la pieza de mayor valor (§ analisys-06
#1), sin repetir su diseño aquí.

---

## 13. Decisiones / ambigüedades

| # | Punto | Decisión / nota |
|---|-------|-----------------|
| 1 | Cambio de tipo en SQLite (`ALTER COLUMN TYPE`) | Recrear tabla (o documentar como no soportado). |
| 2 | `upsert` por motor | SQLite/PG `ON CONFLICT (col) DO UPDATE`; MySQL `ON DUPLICATE KEY UPDATE`. |
| 3 | `Decimal` en SQLite | Guardar como `str`/`NUMERIC`; precisión exacta solo en MySQL `DECIMAL` y PG `NUMERIC`. |
| 4 | `has_many` + `batch` | `_has_many_def` procesado en `__init__`; `batch_reference` extendido a colecciones (`IN`). |
| 5 | `scope` por herencia vs contextvar | Preferir `ScopedModel` (explícito); contextvar como alternativa. |
| 6 | `include_deleted` default | `False` en `search` (oculta borrados); `load` por id no filtra. |
| 7 | `JSON` py_type | `dict`/`list` como base; `datatype="json"` explícito en `make_constraint`. |
| 8 | Bulk por `VALUES` vs `COPY` | Multi-filas `VALUES` con chunks; `COPY` (PG) como evolución. |

---

## 14. Dependencias

- Sin dependencias nuevas en el núcleo (stdlib para `cli`/`migration`/`json`).
- `graphql = ["strawberry-graphql>=0.200"]` (ya prevista en `3-graphql.md`).

---

## 15. Estrategia de testing

- `pytest` + `pytest-asyncio`, SQLite `:memory:` (y contenedores para MySQL/PG).
- Casos por funcionalidad:
  - **Migraciones**: `apply`/`rollback`, idempotencia, `diff_schema` (add/drop/type).
  - **Bulk/upsert**: `insert_many` atómico, `save()` idempotente, `upsert` por motor.
  - **`Decimal`/`JSON`**: round-trip (serializa/deserializa) y DDL (`DECIMAL`, `JSONB`).
  - **`has_many`**: colección inversa + `batch_reference` sin N+1.
  - **`scope`**: `search` restringido por tenant; no filtra en `load`.
  - **Observabilidad**: tracer registra timing/params/trace_id.
  - **CLI**: `generate models` produce archivos importables.
  - **`avg`/`min`/`max`** y **soft-delete** (`include_deleted`).

---

## 16. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `Decimal` + `JSON` (serialización + datatype + presets `DECIMAL`/`JSON`). |
| 2 | Bulk (`insert_many`) + upsert (`save`/`upsert`) + `insert(ignore_duplicated/replace)`. |
| 3 | Migraciones versionadas (`Migration` + `migrations_from_dir`) + `diff_schema`. |
| 4 | `has_many` (colecciones inversas + `batch`). |
| 5 | `scope`/multi-tenant + soft-delete. |
| 6 | Observabilidad (tracer) + agregados `avg`/`min`/`max`. |
| 7 | CLI de codegen. |
| 8 | GraphQL (implementar `docs/design/3-graphql.md`). |

---

## 17. Orden por valor

Prioridad sugerida según `analisys-06.md` (valor vs esfuerzo):

| Prioridad | Funcionalidades |
|-----------|-----------------|
| **Alta** | GraphQL (fase 8), Migraciones+diff (fase 3), Bulk/upsert (fase 2) |
| **Media-Alta** | `Decimal`+`JSON` (fase 1) |
| **Media** | `has_many`, `scope`, observabilidad, CLI |
| **Baja** | `avg`/`min`/`max`, soft-delete |
