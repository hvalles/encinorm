# Documento de Diseño — encinorm.graphql

Capa opcional de **GraphQL** auto-generada sobre el ORM `encinorm.model`.
Permite exponer los modelos como tipos GraphQL con queries y mutations, sin
escribir resolvers manuales. Usa **Strawberry GraphQL** (integración nativa con
pydantic v2 + async).

> Complementa —no reemplaza— `docs/design/0-design.md` (capa `Db`), `docs/design/1-model.md`
> (ORM) y `docs/design/2-constraint.md`. No modifica la interfaz `Db` ni `Query`.

---

## 1. Contexto y Objetivos

El público objetivo de encinorm son desarrolladores **FastAPI**. GraphQL es un
complemento natural para exponer el modelo de datos como API. La sinergia clave
es que `Model` hereda de `pydantic.BaseModel`, y **Strawberry** genera tipos
GraphQL directamente desde pydantic v2.

| # | Objetivo |
|---|----------|
| 1 | Auto-generar **ObjectType** de GraphQL desde cada `Model`. |
| 2 | Exponer **queries** de lectura: lista paginada con filtro, `get` por llave y `count`. |
| 3 | Exponer **mutations** de escritura: `create`, `update`, `delete` reusando `validate()`. |
| 4 | Traducir la clase `Filter` a **input types** de GraphQL (operadores + and/or/not). |
| 5 | Resolver **relaciones** (`add_reference`/`_references_def`) sin N+1 (DataLoader). |
| 6 | Integrarse con `session(db)` para el acceso a BD por request. |
| 7 | Ser **opcional**: el núcleo no debe depender de GraphQL. |

---

## 2. Arquitectura y ubicación

```
encinorm/
├── encinorm/
│   ├── ...                     # Db, pool, model (ya existente)
│   └── graphql/                # NUEVO (subpaquete opcional)
│       ├── __init__.py         # build_schema, auto_register
│       ├── types.py            # generación de ObjectType/Input desde Model
│       ├── scalars.py          # mapeo datatype -> scalar GraphQL
│       ├── filters.py          # Filter -> FilterInput
│       ├── queries.py          # lista/get/count
│       ├── mutations.py        # create/update/delete
│       ├── resolvers.py        # resolvers de relaciones (DataLoader)
│       └── schema.py           # Strawberry Schema + registro de modelos
└── docs/
    └── 3-graphql.md       # este documento
```

- `encinorm.graphql` importa de `encinorm.model` y de `encinorm.pool.session`; **nunca al revés**.
- No se tocan `base.py`, `sqlite.py`, `mysql.py`, `postgresql.py`, `pool.py` ni `model.py`.

---

## 3. Mapeo de tipos (Model → GraphQL)

### 3.1. Scalars por `datatype`

| `datatype` (lógico) | Tipo GraphQL |
|---------------------|--------------|
| `str` | `String` |
| `int` | `Int` |
| `numeric` / `float` | `Float` |
| `bool` / `tinyint` | `Boolean` |
| `datetime` | `DateTime` |
| `date` | `Date` |
| `blob` | `String` (base64) — o `Bytes` |
| `id` (campo `id`) | `ID` |

El tipo se obtiene de `Column(datatype=...)` o se infiere con
`PY_TYPE_TO_DATATYPE` (misma lógica de `types.py`).

### 3.2. Reglas de generación

- Cada campo pydantic del `Model` → campo GraphQL.
- Se **excluyen** los atributos internos (`_`-prefijados y el estado `__exists`/`__dirties`, que no son campos pydantic).
- `Optional[T]` / `T | None` → campo **nullable**.
- `id` → `ID`.
- Campos que apuntan a otro `Model` (relaciones) → campo anidado con resolver (sección 6), no columna.

```python
# encinorm/graphql/types.py (concepto)
import strawberry
from encinorm.model import Model

def build_type(model: type[Model]) -> strawberry.ObjectType:
    # strawberry.experimental.pydantic.type(model, all_fields=True, ...)
    ...
```

---

## 4. `FilterInput` (traducción de `Filter`)

### 4.1. Operadores por tipo

Se generan input types por categoría de tipo, estilo Hasura/Prisma:

```graphql
input StringFilter {
  eq: String
  ne: String
  in: [String!]
  like: String
  startswith: String
  endswith: String
  is_null: Boolean
}

input IntFilter {
  eq: Int
  ne: Int
  gt: Int
  ge: Int
  lt: Int
  le: Int
  in: [Int!]
  between: [Int!]
  is_null: Boolean
}

input DateTimeFilter {
  gt: DateTime
  ge: DateTime
  lt: DateTime
  le: DateTime
  between: [DateTime!]
  is_null: Boolean
}
```

Mapeo directo desde la clase `Filter` (ya implementada):

| `Filter` | Campo GraphQL |
|----------|---------------|
| `eq` | `eq` |
| `ne` | `ne` |
| `gt`/`ge`/`lt`/`le` | `gt`/`ge`/`lt`/`le` |
| `in_` | `in` |
| `between` | `between` |
| `like` | `like` |
| `startswith`/`endswith` | `startswith`/`endswith` |
| `is_null`/`not_null` | `is_null` (`true`/`false`) |
| `raw` | **no expuesto** (escape hatch inseguro) |

### 4.2. Filtro por modelo (composición)

```graphql
input AgenteFilter {
  agente: StringFilter
  monto: FloatFilter
  region_id: IntFilter
  and: [AgenteFilter!]
  or: [AgenteFilter!]
  not: AgenteFilter
}
```

- `and`/`or`/`not` recursivos corresponden a `Filter.__and__`/`__or__`/`__invert__`.
- `filters.py` convierte un `FilterInput` GraphQL a un objeto `Filter` del ORM.

```python
# encinorm/graphql/filters.py (concepto)
def to_filter(input_data) -> Filter:
    condiciones = []
    for campo, valor in input_data.items():
        if campo in ("and", "or", "not"):
            ...  # recursivo
        elif valor is not None:
            condiciones.append(_op_filter(campo, valor))
    return _and(*condiciones)
```

---

## 5. Queries

```graphql
type Query {
  agentes(filter: AgenteFilter, limit: Int, page: Int): [Agente!]!
  agente(id: ID!): Agente
  agentes_count(filter: AgenteFilter): Int!
}
```

| Query | Implementación ORM |
|-------|--------------------|
| `agentes(...)` | `Agente(db).search(filter, limit=limit, page=page)` |
| `agente(id)` | `Agente(db, id=id).load()` |
| `agentes_count(...)` | `Agente(db).count(filter)` |

- Los resolvers obtienen el `db` vía `session()` (sección 8).
- `filter=None` → sin filtro; `limit`/`page` opcionales → paginación.

---

## 6. Mutations

```graphql
type Mutation {
  agente_create(data: AgenteInput!): Agente!
  agente_update(id: ID!, data: AgenteInput!): Agente!
  agente_delete(id: ID!): Boolean!
}
```

- `AgenteInput` = mismos campos que `Agente` (sin `id`, que lo gestiona la BD).
- `create`: `Agente(db, **data).insert()`; devuelve el registro recién creado.
- `update`: `agente.load()` → asignar `data` → `update()` (usa `__dirties`).
- `delete`: `Agente(db, id=id).delete()` (borrado lógico).
- **Validación**: `validate()` se reutiliza; si devuelve errores, se propagan como errores GraphQL por campo (no excepción genérica).

```python
# encinorm/graphql/mutations.py (concepto)
@strawberry.mutation
async def agente_update(info, id: strawberry.ID, data: AgenteInput) -> Agente:
    async with session(info.context["db"]) as db:
        a = Agente(db, id=id)
        a = await a.load()
        if not a._exists:
            raise NotFoundError("agente")
        for campo, valor in strawberry.asdict(data).items():
            setattr(a, campo, valor)
        await a.update()
        return await Agente(db, id=id).load()
```

---

## 7. Relaciones (sin N+1)

Las referencias (`_references_def` o `add_reference`) se exponen como campos
anidados y se resuelven con **DataLoader**, reutilizando `Model.batch_reference`.

```graphql
type Agente {
  id: ID!
  agente: String
  region_id: Int
  region: Region        # resolver anidado
}
```

```python
# encinorm/graphql/resolvers.py (concepto)
async def load_regions(keys):
    modelos = [Agente(db, id=k) for k in keys]
    await Agente.batch_reference(modelos, "region")
    return [await m["region"] for m in modelos]
```

- Evita el N+1: una sola consulta para resolver la referencia de toda una página.
- El `db` proviene del contexto del request.

---

## 8. Integración con `session` (DI por request)

El esquema recibe el `db` (o el pool) por request vía el contexto de Strawberry:

```python
async def get_context():
    return {"db": pool}          # PoolDb o Db

schema = strawberry.Schema(query=Query, mutation=Mutation)
```

Cada resolver usa `session(context["db"])` para obtener/liberar una conexión:

```python
async with session(info.context["db"]) as db:
    ...
```

En FastAPI se integra con `GraphQLRouter` + la dependency que provee el pool.

---

## 9. Errores

| Situación | Comportamiento |
|-----------|----------------|
| Registro no encontrado (`get`/`update`) | Error GraphQL `NOT_FOUND` (no excepción 500). |
| `validate()` con errores | Errores por campo (`data.agente: ...`). |
| Error de BD (restricción, FK) | Error GraphQL genérico con mensaje del motor. |

Se reutilizan las excepciones del ORM (`ValidationError`, `FailOnUpdate`,
`NotFoundError`) y se mapean a errores GraphQL tipados.

---

## 10. Dependencias

```toml
[project.optional-dependencies]
graphql = ["strawberry-graphql>=0.200"]
```

Strawberry se agrega **solo** como dependencia opcional; `encinorm` y
`encinorm.model` siguen funcionando sin él (imports perezosos en `graphql/`).

---

## 11. Ejemplo de uso

```python
import strawberry
from strawberry.fastapi import GraphQLRouter
from encinorm import PoolDb
from encinorm.graphql import build_schema
from encinorm.model import Model

class Region(Model):
    _table = "regiones"
    region: str | None = None

class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None
    _references_def = {"region": {"model": Region, "match_keys": {"id": "region_id"}}}

schema = build_schema([Region, Agente])

pool = PoolDb("sqlite", min_size=2, max_size=10, database="app.db")
app.include_router(GraphQLRouter(schema, context_getter=lambda: {"db": pool}))
```

Consulta:

```graphql
query {
  agentes(filter: { agente: { like: "Héct" } }, limit: 10, page: 1) {
    id
    agente
    region { region }
  }
  agentes_count(filter: { agente: { like: "Héct" } })
}

mutation {
  agente_create(data: { agente: "Nuevo", region_id: 3 }) { id agente }
}
```

---

## 12. Estrategia de testing

- `pytest` + `pytest-asyncio`, ejecutando el **schema en memoria** (sin servidor),
  contra SQLite `:memory:`.
- Casos: generación de tipos, filtros (`like`/`gt`/`in`/`and`/`or`), paginación,
  `get`/`count`, mutations (create/update/delete), validación (`validate()` →
  errores por campo), relaciones con `batch_reference`, y `session()` por request.

---

## 13. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `scalars.py` + `types.py`: generar `ObjectType`/`Input` desde `Model`. |
| 2 | `filters.py`: `Filter` ↔ `FilterInput` + queries `list`/`get`/`count`. |
| 3 | `mutations.py`: create/update/delete con `validate()`. |
| 4 | `resolvers.py`: relaciones con DataLoader (`batch_reference`). |
| 5 | `schema.py`: `build_schema` + integración FastAPI + tests end-to-end. |

---

## 14. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Framework | **Strawberry** (pydantic v2 + async). |
| 2 | `Filter.raw` | No expuesto (escape hatch inseguro). |
| 3 | Relaciones | DataLoader sobre `batch_reference` (una sola consulta). |
| 4 | `db` por request | Contexto de Strawberry + `session()`. |
| 5 | Dependencia | Opcional (`strawberry-graphql`), imports perezosos. |
| 6 | Nombres | Plural para listas (`agentes`), singular para `get` (`agente`), `_count` para conteo. |
