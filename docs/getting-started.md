# Getting started

Guía rápida para instalar encinorm y crear tu primer modelo funcional.

## 1. Instalación

```bash
pip install -e .                 # núcleo
pip install -e ".[http,security,graphql]"   # con todas las capas opcionales
```

Requisitos: **Python 3.10+**. Dependencias del núcleo: `pydantic`, `aiosqlite`,
`aiomysql` y `asyncpg`.

## 2. Conectar a una base de datos

```python
from encinorm import create_db

# SQLite (archivo o :memory:)
db = await create_db("sqlite", database=":memory:")

# MySQL
db = await create_db("mysql", host="localhost", user="root", password="...", db="app")

# PostgreSQL
db = await create_db("postgresql", host="localhost", user="postgres", password="...", database="app")
```

Para aplicaciones concurrentes usa el pool:

```python
from encinorm import PoolDb

pool = PoolDb("sqlite", min_size=2, max_size=10, database="app.db")
await pool.connect()
```

## 3. Definir un modelo

```python
from encinorm.model import Model, STR_100, INT_POS, DATETIME

class User(Model):
    _table = "users"          # nombre de tabla (obligatorio)

    name: STR_100(required=True)
    age: INT_POS()            # >= 0, opcional
    born_at: DATETIME()
```

`Model` añade por defecto las columnas `id` (clave primaria auto-incremental),
`enabled` (soft-delete), `created_at` y `updated_at`.

## 4. Crear la tabla y operar

Como `name` es `required=True`, las operaciones que solo necesitan el esquema o
una clave (DDL, `load`, `search`, `delete`) se hacen sobre un cursor construido
sin validación con el classmethod `cursor()`:

```python
await User.cursor(db).create_table()              # DDL + aplicación (idempotente)

u = User(db, name="Ana", age=30)
await u.insert()                          # INSERT

got = await User.cursor(db, id=u.id).load()       # SELECT por id
print(got.name, got.age)

got.age = 31
await got.update()                        # UPDATE (solo campos modificados)

rows = await User.cursor(db).search()             # SELECT *
await User.cursor(db, id=u.id).delete()           # soft-delete (enabled=False)
```

## 5. Conexión implícita (opcional)

Para no pasar `db` en cada instancia, registra una conexión por defecto o usa el
ámbito de request:

```python
from encinorm import set_default_db, session, bind

set_default_db(db)                        # singleton de proceso
u = User(name="Bob")                      # sin `db`
await u.insert()

async def request_handler():
    async with session(pool):             # por request (FastAPI)
        u = User(name="Carol")            # resuelve a la conexión del request
        await u.insert()
```

Consulta la [Guía de uso](guide.md) para el detalle de cada operación.
