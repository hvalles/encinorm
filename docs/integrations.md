# Integraciones

Capas opcionales de producto: REST, GraphQL, seguridad, codegen/CLI y
observabilidad. Todas son **aditivas** y no afectan al núcleo.

## 1. REST (FastAPI)

Genera un CRUD tipado por modelo en un solo router:

```python
from fastapi import FastAPI
from encino_orm.http import create_crud, install_error_handlers

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
- El `PUT` ignora los campos de solo lectura `id`, `enabled`, `created_at` y
  `updated_at` (no se pueden modificar por esta vía; el soft-delete se gestiona
  con `DELETE`).

## 2. GraphQL (Strawberry)

```python
from encino_orm.graphql import build_schema

schema = build_schema([User, Product])

result = await schema.execute(
    '{ users { id name } user(id: 1) { name } users_count }',
    context_value={"db": pool},
)
```

- **Queries**: `{tabla}` (lista), `{tabla}_count`, `{singular}` (por clave
  primaria) con filtro `filter`, `limit` y `page`.
- **Mutations**: `{singular}_create`, `{singular}_update`, `{singular}_delete`.
- Las relaciones se resuelven con **DataLoader** (carga por lotes), evitando el
  N+1 al resolver `region { name }` sobre listas de padres.

## 3. Seguridad (RBAC + JWT)

```python
from encino_orm.security import (
    emit_token, verify_token, get_current_user, require, create_tables, seed_roles,
)

token = emit_token("user-1", SECRET)
payload = verify_token(token, SECRET)      # {"sub": "user-1", "type": "access", ...}
```

### Access vs refresh tokens

`emit_token`/`verify_token` gestionan tokens de **acceso** y
`emit_refresh`/`verify_refresh` tokens de **refresco**. Ambos se distinguen por el
claim `type` (`"access"`/`"refresh"`): `verify_token` **rechaza** un token de
refresco y `verify_refresh` **exige** que lo sea, de modo que un access token
robado no sirve para emitir nuevos tokens:

```python
from encino_orm.security import emit_refresh, verify_refresh

refresh = emit_refresh("user-1", SECRET, expires_seconds=604800)
payload = verify_refresh(refresh, SECRET)   # solo acepta type == "refresh"
```

Los algoritmos se validan contra una lista permitida (`HS256`, `RS256`, `ES256`,
…) y se rechaza `"none"` tanto al emitir como al verificar. Por compatibilidad,
`verify_token` sigue aceptando tokens legados **sin** `type` (pero no podrán
usarse como refresh).

### Roles y permisos

Las tablas de seguridad se crean con `create_tables(db)` y se siembran con
`seed_roles(db)`. El modelo de permisos es **tri-estado** (`True`/`False`/`None`)
con **negación por defecto** y resolución por orden de rol:

```python
from encino_orm.security import PermissionSet

perms = await PermissionSet.for_user(db, "user-1")
perms.can("users", "read")
perms.require("users", "create")           # lanza AuthorizationError si no puede
```

### Guard en FastAPI

```python
import encino_orm.security.guard as guard

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
from encino_orm.introspection import generate_model, list_tables

tables = await list_tables(db)
path = await generate_model(db, "users", folder="models")
```

Por CLI:

```bash
encino_orm generate models sqlite --database app.db --folder models
encino_orm generate models mysql --host localhost --user root --password s3cret --database app
```

Las claves primarias compuestas y los nombres de columna reservados se detectan
y se emiten automáticamente (`_primary_key`, `name='...'`). El `_table` y el
`name=` se generan con `repr`, por lo que los nombres con caracteres especiales
quedan correctamente escapados en el código generado.

## 5. Observabilidad

```python
from encino_orm import trace_id, QueryTracer, OtelQueryTracer

with trace_id("req-abc"):
    await User(db).search()      # los logs SQL incluyen trace_id=...

tracer = QueryTracer(collect_metrics=True)
tracer.record("sqlite", "fetch_all", "SELECT ...", [], 0.012, rows=10)
print(tracer.stats)              # {"queries": 1, "errors": 0, "rows": 10}
print(tracer.latency_stats)      # {"count": 1, "min": ..., "p50": ..., "p99": ...}
```

- `QueryTracer` además de contadores expone `latency_stats` (histograma con
  percentiles p50/p90/p99).
- `OtelQueryTracer` crea un **span de OpenTelemetry** por consulta (opt-in;
  requiere `opentelemetry-api`, que no es dependencia de encino_orm). El
  `TracerProvider`/exportador lo configura la aplicación.

El logging estructurado de los motores usa `logging.getLogger("encino_orm")` a
nivel `DEBUG`.
