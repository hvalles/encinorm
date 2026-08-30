# Integraciones

Capas opcionales de producto: REST, GraphQL, seguridad, codegen/CLI y
observabilidad. Todas son **aditivas** y no afectan al núcleo.

## 1. REST (FastAPI)

Genera un CRUD tipado por modelo en un solo router:

```python
from fastapi import FastAPI
from encinorm.http import create_crud, install_error_handlers

app = FastAPI()
install_error_handlers(app)
app.include_router(create_crud(pool, [User, Product], prefix="/api"))
```

Endpoints generados por modelo (tabla `users`):

| Método | Ruta                | Acción                                   |
|--------|---------------------|------------------------------------------|
| POST   | `/api/users/`       | Crear (valida con el modelo pydantic).   |
| GET    | `/api/users/`       | Listar (`limit`, `page`, `sort_by`, `filter`). |
| GET    | `/api/users/{id}`   | Obtener por clave primaria.              |
| PUT    | `/api/users/{id}`   | Actualizar parcial.                      |
| DELETE | `/api/users/{id}`   | Borrar (lógico; `?physical=true`).       |
| GET    | `/api/models`       | Introspección de modelos registrados.    |

- `filter` usa JSON: `?filter={"age":{"ge":18}}&sort_by=-age`.
- Con clave primaria compuesta, la ruta se genera con un segmento por campo
  (`/api/memberships/{tenant_id}/{code}`).
- `create_crud` acepta `get_db` para inyectar una dependency propia; por defecto
  usa `session(pool)`.

## 2. GraphQL (Strawberry)

```python
from encinorm.graphql import build_schema

schema = build_schema([User, Product])

result = await schema.execute(
    '{ users { id name } user(id: 1) { name } users_count }',
    context_value={"db": pool},
)
```

- **Queries**: `{tabla}` (lista), `{tabla}_count`, `{singular}` (por clave
  primaria) con filtro `filter`, `limit` y `page`.
- **Mutations**: `{singular}_create`, `{singular}_update`, `{singular}_delete`.
- Las relaciones se resuelven de forma perezosa (`region { name }`).

## 3. Seguridad (RBAC + JWT)

```python
from encinorm.security import (
    emit_token, verify_token, get_current_user, require, create_tables, seed_roles,
)

token = emit_token("user-1", SECRET)
payload = verify_token(token, SECRET)      # {"sub": "user-1", ...}
```

### Roles y permisos

Las tablas de seguridad se crean con `create_tables(db)` y se siembran con
`seed_roles(db)`. El modelo de permisos es **tri-estado** (`True`/`False`/`None`)
con **negación por defecto** y resolución por orden de rol:

```python
from encinorm.security import PermissionSet

perms = await PermissionSet.for_user(db, "user-1")
perms.can("users", "read")
perms.require("users", "create")           # lanza AuthorizationError si no puede
```

### Guard en FastAPI

```python
import encinorm.security.guard as guard

guard.SECRET = "clave-super-secreta"
guard.GET_DB = get_db                     # dependency de conexión

@app.get("/users")
async def list_users(user=Depends(get_current_user())):
    return await User(db).search()

@app.post("/users")
async def create_user(user=Depends(require("users", "create"))):
    ...
```

## 4. Codegen y CLI

Genera modelos desde una base de datos existente (database-first):

```python
from encinorm.introspection import generate_model, list_tables

tables = await list_tables(db)
path = await generate_model(db, "users", folder="models")
```

Por CLI:

```bash
encinorm generate models sqlite --database app.db --folder models
encinorm generate models mysql --host localhost --user root --password s3cret --database app
```

Las claves primarias compuestas y los nombres de columna reservados se detectan
y se emiten automáticamente (`_primary_key`, `name="..."`).

## 5. Observabilidad

```python
from encinorm import trace_id, QueryTracer

with trace_id("req-abc"):
    await User(db).search()      # los logs SQL incluyen trace_id=...

tracer = QueryTracer(collect_metrics=True)
tracer.record("sqlite", "fetch_all", "SELECT ...", [], 0.012, rows=10)
print(tracer.stats)              # {"queries": 1, "errors": 0, "rows": 10}
```

El logging estructurado de los motores usa `logging.getLogger("encinorm")` a
nivel `DEBUG`.
