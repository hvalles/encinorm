# Guía de uso

Referencia del ORM: modelos, restricciones, CRUD, filtros, consultas,
relaciones, claves primarias/foráneas, migraciones, hooks y caché.

## 1. Modelos

Un modelo es una subclase de `Model` con un atributo de clase `_table` y campos
declarados con anotaciones de tipo:

```python
from encinorm.model import Model, STR_100, INT_POS

class Product(Model):
    _table = "products"

    sku: STR_100(required=True)
    stock: INT_POS()
```

### Campos automáticos

`Model` aporta por defecto:

| Campo        | Tipo                    | Descripción                                  |
|--------------|-------------------------|----------------------------------------------|
| `id`         | `int \| None`           | Clave primaria auto-incremental.             |
| `enabled`    | `bool`                  | Soft-delete (`False` = borrado lógico).      |
| `created_at` | `datetime \| None`      | Fecha de creación (UTC).                     |
| `updated_at` | `datetime \| None`      | Fecha de última actualización (UTC).         |

Puedes excluir columnas con `_fields_disabled`:

```python
class Row(Model):
    _table = "rows"
    _fields_disabled = ["id", "enabled", "created_at", "updated_at"]
```

### Nombre de columna distinto

Usa `name=` en una restricción, o `Column` con `datatype` explícito:

```python
from encinorm.model import INT

class User(Model):
    _table = "users"
    order: INT(name="order_col") | None = None
```

```python
from typing import Annotated
from encinorm.model import Column

class User(Model):
    _table = "users"
    order: Annotated[int, Column(datatype="int", name="order_col")] | None = None
```

## 2. Restricciones y tipos

Las restricciones se crean con `make_constraint`; el vocabulario
(`encinorm.model.domain`) ya incluye presets:

| Preset     | Tipo      | Notas                          |
|------------|-----------|--------------------------------|
| `STR_n`    | `str`     | `STR_10` … `STR_500`, `TEXT`.  |
| `INT`      | `int`     | Entero.                        |
| `INT_POS`  | `int`     | `ge=0`.                        |
| `CURRENCY` | `float`   | `numeric`, `ge=0`.             |
| `FLOAT`    | `float`   | Punto flotante.                |
| `BOOL`     | `bool`    |                                |
| `DATE`     | `date`    |                                |
| `DATETIME` | `datetime`| UTC, acepta ISO 8601.          |
| `DECIMAL`  | `Decimal` | Dinero exacto (MySQL/PG).      |
| `JSON`     | `dict`    | Columna JSON.                  |
| `BLOB`     | `bytes`   | Binario.                       |

Crea restricciones propias:

```python
from encinorm.model import make_constraint

EMAIL = make_constraint(str, pattern=r"[^@]+@[^@]+\.[^@]+", max_length=120)

class User(Model):
    _table = "users"
    email: EMAIL(required=True)
```

## 3. CRUD

```python
u = User(db, name="Ana")
new_id = await u.insert()                       # INSERT -> id
u = await User(db, id=new_id).load()            # SELECT por clave primaria

u.name = "Ana M."
await u.update()                                 # UPDATE (campos modificados)
await u.update(data=["name"])                    # UPDATE solo de `name`

await u.delete()                                 # soft-delete
await u.delete(physical=True)                    # DELETE físico

# find-or-create / upsert
await User(db, name="Bob").save()                # inserta si no existe
await User(db, name="Bob").upsert()              # ON CONFLICT / ON DUPLICATE KEY
```

### Consultas

```python
rows = await User(db).search()                   # SELECT *
rows = await User(db).search(limit=10, page=2)   # paginación
rows = await User(db).search(sort_by=["-age"])   # ORDER BY age DESC
total = await User(db).count()                   # COUNT(*)
rec = await User(db).paginate(limit=10, page=1)  # {rows, total, limit, page}
```

### Bulk

```python
await User.insert_many(db, [{"name": "a"}, {"name": "b"}], chunk=500)
```

### SQL directo (raw)

Cuando el ORM no cubre el SQL que necesitas (CTEs, `UNION`, ventanas, sintaxis
específica del motor), ejecuta `Query` directamente sobre la conexión. Los
placeholders son `{0}...{n}` y los valores se pasan como lista, en el mismo orden:

```python
from encinorm import Query

rows = await db.fetch_all(Query("select * from agents where id={0}", [123]))
row  = await db.fetch_one(Query("select * from agents where id={0}", [123]))
await db.execute(Query("update agents set enabled={0} where id={1}", [False, 123]))
```

`Db` expone `fetch_all`, `fetch_one`, `fetch_many`, `execute` y `exists`; todos
reciben un `Query`.

Para paginar un SQL directo (página + total en un `Records`), usa
`db.paginate(Query(...), limit, page)`. El total se calcula envolviendo el SQL en
`SELECT COUNT(*) AS n FROM (...)`, por lo que solo es fiable para SELECT simples:

```python
rec = await db.paginate(
    Query("select * from agents where enabled={0} order by id", [True]),
    limit=10, page=2,
)
rec.rows           # lista de dicts de la página
rec.total          # total de filas del filtro
rec.total_pages    # páginas calculadas
```

- La numeración es **contigua desde 0** (`{0}`, `{1}`, …).
- Los valores se pasan **sin serializar**: fechas, `Decimal` y `bool` debes
  convertirlos tú (aquí el ORM no aplica `_serialize`).
- Para fragmentos crudos dentro de un filtro tipado, usa `Filter.raw(...)`:

```python
from encinorm.model import Filter

await Agent(db).search(Filter.raw("LOWER(name) = {0}", ["ana"]))
```

## 4. Filtros (`Filter`)

```python
from encinorm.model import Filter

Filter.eq("age", 30)          # age = 30
Filter.ne("age", 30)          # age != 30
Filter.gt("age", 18)          # age > 18
Filter.ge("age", 18)          # age >= 18
Filter.lt("age", 65)          # age < 65
Filter.le("age", 65)          # age <= 65
Filter.in_("id", [1, 2, 3])   # id IN (...)
Filter.between("age", 18, 65) # age BETWEEN 18 AND 65
Filter.like("name", "an")     # name LIKE '%an%'
Filter.startswith("name", "A")# name LIKE 'A%'
Filter.is_null("email")       # email IS NULL
Filter.raw("LOWER(name) = {0}", ["ana"])  # SQL crudo

# composición
f = Filter.ge("age", 18) & Filter.lt("age", 65)   # AND
f = Filter.eq("role", "admin") | Filter.eq("role", "owner")  # OR
f = ~Filter.eq("deleted", True)                   # NOT

await User(db).search(f)
```

## 5. `QueryBuilder`

Consultas con `join`, alias y agregados:

```python
qb = User(db).query()
rows = await (
    qb
    .select("mm.id", "mm.name")
    .join(Order, "o", on=Filter.eq("o.user_id", col("mm.id")))
    .where(Filter.ge("mm.age", 18))
    .order_by("mm.name")
    .all()
)

total = await User(db).query().where(Filter.eq("role", "admin")).count()
s = await User(db).query().sum("age")
```

Agregados disponibles: `count`, `sum`, `avg`, `min`, `max`, `exists`, `first`,
`all`, `paginate`.

## 6. Relaciones

### Referencia 1:1

```python
class Region(Model):
    _table = "regions"
    name: str | None = None

class Agent(Model):
    _table = "agents"
    region_id: int | None = None
    _references_def = {
        "region": {"model": Region, "match_keys": {"id": "region_id"}},
    }

agent = await Agent(db, id=1).load()
region = await agent["region"]            # carga perezosa de la referencia
```

`match_keys` es un mapeo `{campo_remoto: campo_local}`.

### Colección 1:N (`has_many`)

```python
class Region(Model):
    _table = "regions"
    name: str | None = None
    _has_many_def = {"agents": {"model": Agent, "foreign_key": "region_id"}}

region = await Region(db, id=1).load()
agents = await region["agents"]           # list[Agent] por clave foránea
```

### Carga por lotes (evita N+1)

```python
regions = await Region(db).search()
await Region.batch_has_many(regions, "agents")   # 1 consulta IN(...)

agents = await Agent(db).search()
await Agent.batch_reference(agents, "region")     # 1 consulta IN(...)
```

## 7. Claves primarias y foráneas

### Clave primaria

Por defecto la clave es `("id",)` (auto-incremental). Declara `_primary_key`
para una clave natural simple o una **compuesta**:

```python
# clave natural simple
class Product(Model):
    _table = "products"
    _primary_key = ("sku",)
    _fields_disabled = ["id"]            # quita el surrogate id
    sku: str | None = None
    name: str | None = None

# clave compuesta
class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "code")
    _fields_disabled = ["id"]
    tenant_id: int | None = None
    code: str | None = None
```

`load`, `save`, `update`, `delete` y `upsert` usan la clave primaria por defecto:

```python
m = Membership(db, tenant_id=7, code="admin")
await m.insert()
await Membership(db, tenant_id=7, code="admin").load()
await Membership(db, tenant_id=7, code="admin").load(keys="tenant_id,code")
```

### Clave foránea compuesta

Las relaciones que apuntan a una PK compuesta usan `match_keys` (1:1) o
`foreign_key` como dict `{campo_padre: campo_hijo}` (1:N):

```python
class AuditLog(Model):
    _table = "audit_logs"
    _fields_disabled = ["id"]
    tenant_id: int | None = None
    code: str | None = None
    _references_def = {
        "membership": {
            "model": Membership,
            "match_keys": {"tenant_id": "tenant_id", "code": "code"},
            "on_delete": "cascade",
        },
    }

Membership._has_many_def = {
    "logs": {"model": AuditLog, "foreign_key": {"tenant_id": "tenant_id", "code": "code"}},
}
```

`on_delete` acepta `"cascade"`, `"set_null"` o `"restrict"`.

## 8. Índices

```python
from encinorm.model import Index

class User(Model):
    _table = "users"
    email: str | None = None

User.add_index(Index("email", unique=True))
User.add_index(Index([("created_at", "DESC")], name="idx_created"))
```

Los índices se crean con `create_table()`.

## 9. Hooks

```python
from encinorm.model import Model, before_insert, after_commit

class User(Model):
    _table = "users"
    name: str | None = None

    @before_insert
    async def _lower(self):
        self.name = (self.name or "").lower()

    @after_commit
    async def _notify(self):
        await notify(self)
```

Hooks disponibles: `before_insert`, `before_update`, `before_delete`,
`before_commit`, `after_commit`, `after_transaction_fail`.

## 10. Caché (`CachedModel`)

```python
from encinorm.model import CachedModel, MemoryCacheBackend

class User(CachedModel):
    _table = "users"
    name: str | None = None

cache = MemoryCacheBackend()
u = User(db, cache=cache, id=1)
await u.load(duration=300)              # cachea 300 s; invalida al actualizar/borrar
```

Backends: `MemoryCacheBackend`, `RedisCacheBackend(url=...)`, o cualquiera que
implemente el `Protocol` `CacheBackend`.

## 11. Esquema y migraciones

```python
await User(db).create_table()                          # CREATE TABLE + índices
diff = await User(db).diff_schema()                    # compara modelo vs BD
await User(db).sync_schema(drop_missing=True)          # aplica cambios (aditivos)

from encinorm import Migration, apply_migration, migrations_from_dir

m = Migration(
    name="001_add_email",
    up="ALTER TABLE users ADD COLUMN email TEXT",
    down="ALTER TABLE users DROP COLUMN email",
)
await apply_migration(db, m)
migs = migrations_from_dir("./migrations")
```

## 12. Soft-delete y multi-tenant

- `search`, `count` y `paginate` ocultan `enabled=False` por defecto; usa
  `include_deleted=True` para verlos. `load` no filtra el soft-delete
  (auditoría), pero **sí respeta el `scope`** activo.
- El filtro de alcance por fila (`scope`) se aplica a `search`, `count`,
  `paginate`, **`load`, `update` y `delete`**, de modo que un tenant no puede
  leer, modificar ni borrar filas ajenas por clave primaria:

```python
from encinorm.model import scope, Filter

with scope(Filter.eq("tenant_id", 7)):
    rows = await Membership(db).search()      # solo tenant 7
    doc = await Membership(db, id=123).load() # _exists=False si es de otro tenant
    await doc.update()                        # lanza FailOnUpdate si está fuera de scope
    await Membership(db, id=123).delete()     # no-op (False) si está fuera de scope
```

> Nota: `load` devuelve también filas soft-deleteadas **dentro** del tenant
> (auditoría); `update`/`delete` verifican el `scope` antes de escribir para
> evitar fugas entre tenants.

## 13. Observabilidad

```python
from encinorm import trace_id, QueryTracer

with trace_id("req-123"):
    await User(db).search()                 # los logs incluyen trace_id

tracer = QueryTracer(collect_metrics=True)
tracer.record("sqlite", "fetch_all", "...", [], 0.012)
print(tracer.stats)                         # {"queries": 1, "errors": 0, "rows": 0}
```
