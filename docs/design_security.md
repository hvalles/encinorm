# Documento de Diseño — encinorm.security (RBAC + autenticación JWT)

Subpaquete opcional que centraliza la **seguridad** de las aplicaciones construidas
sobre encinorm: (A) **autorización RBAC** por roles sobre los modelos y (B)
**autenticación JWT** con refresh, expuestas como dependencies de FastAPI para
habilitar los CRUD (`http`) y las operaciones GraphQL sin esquemas repetitivos.

> Complementa `docs/design_model.md` (ORM), `docs/design_crud.md` (CRUD REST) y
> `docs/design_graphql.md` (GraphQL). No modifica `Db`, `Model`, `Query` ni
> `PoolDb`. Se apoya en el análisis `prompts/analisys-04.md`.

---

## 1. Contexto y Objetivos

Los desarrolladores no deberían escribir checks de permisos a mano en cada
endpoint. La seguridad se descompone en dos capas ortogonales:

| Capa | Responde | Responsabilidad |
|------|----------|-----------------|
| Autenticación | *"¿quién es?"* | JWT en header, verificación, refresh, identidad (`user_id`). |
| Autorización | *"¿qué puede hacer?"* | Roles → permisos por modelo/operación, negación por defecto. |

| # | Objetivo |
|---|----------|
| 1 | Definir roles, permisos por modelo y asignación usuario→rol con **orden** (`Rol`, `Roldet`, `RolUsuario`). |
| 2 | Resolver los permisos efectivos con **negación por defecto** y **"la primera asignación prevalece"**. |
| 3 | Autenticar por **JWT** en header `Authorization: Bearer`, con **refresh** ante sesión caducada (`401`). |
| 4 | Exponer `require(modelo, op)` y `get_current_user` como **dependencies** de FastAPI. |
| 5 | Mapear `delete` (lógico) / `remove` (físico) a `Model.delete(physical=...)`. |
| 6 | Ser **opcional** (`fastapi` y `pyjwt` como dependencias extra, imports perezosos). |

---

## 2. Veredicto del análisis

Ver `prompts/analisys-04.md`. Resumen:

- **RBAC**: viable y de alto valor; las tablas de seguridad son `Model` del ORM.
- **JWT**: se **envuelve** PyJWT; **no** se reimplementa el estándar ni el hashing
  de credenciales (lo gestiona la aplicación).
- **Permiso tri-estado** (`bool | None`): condición necesaria para que convivan
  "negación por defecto" y "la primera asignación prevalece".
- **Ubicación**: subpaquete `encinorm.security` dentro del proyecto (no aparte).

---

## 3. Arquitectura y ubicación

```
encinorm/
├── encinorm/
│   ├── ...                     # Db, pool, model (existente)
│   └── security/               # NUEVO (subpaquete opcional)
│       ├── __init__.py         # Rol, Roldet, RolUsuario, PermissionSet, require, get_current_user
│       ├── models.py           # Rol, Roldet, RolUsuario (Model)
│       ├── permissions.py      # PermissionSet + resolución tri-estado por orden
│       ├── guard.py            # require(modelo, op), get_current_user (lazy import fastapi)
│       ├── jwt.py              # emit_token / verify_token / refresh (envuelve PyJWT)
│       └── exceptions.py       # AuthenticationError, AuthorizationError
└── docs/
    └── design_security.md      # este documento
```

- `encinorm.security` importa de `encinorm.model`, `encinorm.pool.session` y (perezosamente) de `fastapi`/`jwt`; **nunca al revés**.
- `fastapi` y `PyJWT` son dependencias **opcionales**.

---

## 4. Modelo de datos de seguridad

Las tres tablas son `Model` de encinorm (persistentes, validables, con `enabled`,
`created_at`/`updated_at` heredados y borrado lógico).

### 4.1. `Rol`

```python
class Rol(Model):
    _table = "roles"
    rol: STR_100(required=True)      # 1:Administrador, 2:Usuario Interno, 3:Público
```

Semilla (vía `create_table`/`sync_schema` + inserción inicial en migración):

| id | rol |
|----|-----|
| 1 | Administrador |
| 2 | Usuario Interno |
| 3 | Público |

### 4.2. `Roldet` (permisos por rol y modelo)

```python
class Roldet(Model):
    _table = "roles_det"
    rol_id: int | None = None
    modelo: STR_100(required=True)          # nombre de tabla (`_table`) o "*"
    perm_read: bool | None = None
    perm_create: bool | None = None
    perm_update: bool | None = None
    perm_delete: bool | None = None         # borrado lógico
    perm_remove: bool | None = None         # borrado físico
```

- Los permisos son **tri-estado**: `None` (sin opinión, hereda), `True` (permite),
  `False` (niega explícitamente).
- Los campos usan el prefijo `perm_` para no colisionar con los métodos de
  `Model` (`update`/`delete`) ni con palabras reservadas de SQL (`create`).
- `modelo` se valida contra el registro de modelos (`_table`); `"*"` es un comodín
  que aplica a todos los modelos.

### 4.3. `RolUsuario`

```python
class RolUsuario(Model):
    _table = "roles_usuario"
    rol_id: int | None = None
    user_id: STR_50(required=True)          # identidad externa (claim `sub` del JWT)
    orden: int | None = None                # prioridad; menor = primero
```

- `user_id` es un `str` **opaco** (hasta 50 caracteres, `STR_50`) ligado al claim
  `sub` del JWT; la tabla de usuarios pertenece a la aplicación, no a encinorm.
- `STR_50` = `make_constraint(str, max_length=50)`; la identidad externa puede no
  ser numérica (UUID, email, id de otro sistema), por eso se guarda como texto y
  no como `int`.
- `orden` determina la precedencia entre roles; el menor valor se evalúa primero.

---

## 5. Resolución de permisos (`PermissionSet`)

### 5.1. Algoritmo (negación por defecto + primero prevalece)

Dado `(user_id, modelo, operación)`:

1. Roles del usuario: `RolUsuario` filtrado por `user_id`, ordenado por `orden` asc.
2. Por cada rol, en orden, su `Roldet` para `modelo` (o `"*"`):
   - `True` → **permitir**; `False` → **denegar**; `None` → continuar.
3. Ningún rol definió la operación → **denegar**.

### 5.2. Clase `PermissionSet`

```python
class PermissionSet:
    """Permisos efectivos de un usuario, resueltos una vez por request."""

    def __init__(self, user_id: str | None, rules: dict[str, dict[str, bool]]):
        self.user_id = user_id
        self._rules = rules          # {modelo: {op: True|False}}

    def can(self, modelo: str, op: str) -> bool:
        rule = self._rules.get(modelo) or self._rules.get("*")
        if rule is None:
            return False
        return bool(rule.get(op, False))     # negación por defecto

    def require(self, modelo: str, op: str) -> None:
        if not self.can(modelo, op):
            raise AuthorizationError(modelo, op)

    @classmethod
    async def for_user(cls, db, user_id: str | None) -> "PermissionSet":
        if user_id is None:
            user_id = PUBLIC_USER_ID        # rol Público para anónimos (str)
        # 1) roles ordenados
        roles = await RolUsuario(db).search(
            Filter.eq("user_id", user_id) & Filter.eq("enabled", True),
            columns=["rol_id"], sort_by=["orden"],
        )
        rol_ids = [r.rol_id for r in roles]
        if not rol_ids:
            return cls(user_id, {})
        # 2) permisos por modelo, en orden de rol
        dets = await Roldet(db).search(Filter.in_("rol_id", rol_ids))
        ordered = sorted(dets, key=lambda d: rol_ids.index(d.rol_id))
        rules: dict[str, dict[str, bool]] = {}
        for d in ordered:
            m = d.modelo
            slot = rules.setdefault(m, {})
            for op in OPS:                       # read/create/update/delete/remove
                if op not in slot and getattr(d, f"perm_{op}") is not None:
                    slot[op] = bool(getattr(d, f"perm_{op}"))     # primer valor explícito
        return cls(user_id, rules)
```

`PUBLIC_USER_ID` es una constante de tipo `str` (p. ej. `"public"`), acorde con
`RolUsuario.user_id` (texto, no `int`).

### 5.3. Operaciones

| Op | Endpoint REST | ORM |
|----|---------------|-----|
| `read` | `GET .../` y `GET .../{id}` | `search`/`load`/`paginate` |
| `create` | `POST .../` | `insert()` |
| `update` | `PUT .../{id}` | `update()` |
| `delete` | `DELETE .../{id}` | `delete(physical=False)` |
| `remove` | `DELETE .../{id}?physical=true` | `delete(physical=True)` |

### 5.4. Caché (opcional)

El `PermissionSet` puede cachearse por `user_id` reutilizando `CacheBackend`
(sección de caché de `design_model.md`) e invalidarse con un hook `after_commit`
en `RolUsuario`/`Roldet`. En apps pequeñas se omite.

---

## 6. Autenticación JWT

`encinorm/security/jwt.py` envuelve **PyJWT**. No gestiona credenciales ni hashing
(lo hace la aplicación al emitir el token en el login).

### 6.1. Funciones

```python
import jwt

def emit_token(user_id: str, secret: str, expires_seconds: int = 900,
               algorithm: str = "HS256", **claims) -> str:
    payload = {"sub": user_id, "iat": now(), "exp": now() + expires_seconds, **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)

def verify_token(token: str, secret: str, algorithms: list[str] = ["HS256"]) -> dict:
    return jwt.decode(token, secret, algorithms=algorithms, options={"require": ["exp"]})

def emit_refresh(user_id: str, secret: str, expires_seconds: int = 604800) -> str: ...
def verify_refresh(token: str, secret: str) -> dict: ...
```

- Access token: vida corta (~15 min); refresh token: vida larga (~7 días).
- `secret` proviene de configuración/env (`SECRET_KEY`); `RS256` si se requiere
  verificación externa.
- Errores de `jwt` (`ExpiredSignatureError`, `InvalidTokenError`) se traducen a
  `AuthenticationError`.

### 6.2. Refresh automático (flujo 401)

1. Cliente envía access token en `Authorization: Bearer <token>`.
2. Ante `401` (exp/revocado), el cliente llama a `POST /auth/refresh` con el refresh
   token y recibe un par nuevo.
3. Si el refresh también caducó → `401` definitivo y el cliente re-autentica.

`/auth/refresh` es responsabilidad de la aplicación (encinorm solo expone
`emit_refresh`/`verify_refresh`); se documenta el patrón.

---

## 7. Guard y dependencies de FastAPI

`guard.py` expone las dependencies con **imports perezosos** de `fastapi`, para que
el núcleo no dependa de FastAPI.

```python
# encinorm/security/guard.py (concepto)

def get_current_user(secret: str):
    """Dependency: resuelve la identidad desde el header Authorization."""
    async def _dep(authorization: str = Depends(HTTPBearer(auto_error=False)),
                   db=Depends(get_db)) -> CurrentUser:
        if authorization is None:
            return CurrentUser(None, PermissionSet.for_user(db, None))  # anónimo -> Público
        try:
            payload = verify_token(authorization.credentials, secret)
        except ExpiredSignatureError:
            raise HTTPException(401, "sesión caducada")
        except InvalidTokenError:
            raise HTTPException(401, "token inválido")
        user_id = payload["sub"]
        return CurrentUser(user_id, await PermissionSet.for_user(db, user_id))
    return _dep

def require(modelo: str, op: str):
    """Dependency de orden superior: autentica + autoriza una operación."""
    async def _dep(user: CurrentUser = Depends(get_current_user(SECRET))) -> None:
        user.permissions.require(modelo, op)      # AuthorizationError -> 403
    return _dep
```

```python
class CurrentUser:
    user_id: str | None
    permissions: PermissionSet
```

- **401**: token ausente/inválido/caducado.
- **403**: identidad válida pero sin permiso (`AuthorizationError`).
- `get_db` es la dependency de conexión (`session(pool)`) de `design_crud.md`.

### 7.1. `HTTPBearer` y OpenAPI

Se usa `HTTPBearer` para declarar el esquema `bearerAuth` en OpenAPI; los endpoints
protegidos quedan documentados automáticamente.

---

## 8. Integración con las capas existentes

### 8.1. `http` (`design_crud.md`)

`register_crud` acepta un parámetro `guard` que inyecta la dependency por operación:

```python
register_crud(
    router, Agente, "/agentes",
    guards={"create": require("agentes", "create"),
            "read": require("agentes", "read"),
            "update": require("agentes", "update"),
            "delete": require("agentes", "delete")},
)
```

### 8.2. `graphql` (`design_graphql.md`)

El contexto del request (`info.context`) lleva `db` y `permissions`; los resolvers
de mutations llaman `permissions.require(modelo, op)` antes de ejecutar.

---

## 9. Ejemplos de uso

### 9.1. Configuración inicial

```python
from encinorm import PoolDb, session
from encinorm.security import Rol, Roldet, RolUsuario, require

pool = PoolDb("postgresql", min_size=2, max_size=10, ...)

async def get_db():
    async with session(pool) as conn:
        yield conn

# seed (migración/creación de tablas + roles por defecto)
await Rol(pool).create_table()
await Roldet(pool).create_table()
await RolUsuario(pool).create_table()
```

### 9.2. Declarar permisos

```python
# Administrador: todo
await Roldet(db, rol_id=1, modelo="*", perm_read=True, perm_create=True,
             perm_update=True, perm_delete=True, perm_remove=True).insert()

# Usuario interno: lectura de agentes, sin borrado físico
await Roldet(db, rol_id=2, modelo="agentes", perm_read=True).insert()

# Usuario 42: primero rol 2 (lee), luego rol 3 (Público, niega) -> prevalece rol 2
await RolUsuario(db, rol_id=2, user_id="42", orden=1).insert()
await RolUsuario(db, rol_id=3, user_id="42", orden=2).insert()
```

### 9.3. Proteger un endpoint

```python
router = APIRouter(prefix="/api", tags=["Model"])

@router.get("/agentes/", dependencies=[Depends(require("agentes", "read"))])
async def listar(db=Depends(get_db)):
    return await Agente(db).search()

@router.delete("/agentes/{id}", dependencies=[Depends(require("agentes", "remove"))])
async def borrar_fisico(id: int, db=Depends(get_db)):
    a = await Agente(db, id=id).load()
    await a.delete(physical=True)     # require "remove"
    return {"id": id, "deleted": True}
```

---

## 10. Dependencias

```toml
[project.optional-dependencies]
security = ["fastapi>=0.110", "PyJWT>=2.8"]
```

`encinorm` y `encinorm.model` siguen funcionando sin `fastapi`/`jwt` (imports
perezosos en `encinorm/security`).

---

## 11. Estrategia de testing

- `pytest` + `pytest-asyncio` + `fastapi.testclient.TestClient` contra SQLite `:memory:`.
- Casos:
  - Resolución tri-estado: permite / niega / `None`, y **"la primera asignación prevalece"**.
  - Negación por defecto (sin regla → denegar).
  - Rol **Público** para requests anónimos.
  - `remove` vs `delete` (físico vs lógico).
  - JWT: emitir/verificar, `exp` → 401, header ausente → 401, refresh.
  - `require(...)` en un CRUD: 200 con permiso, 403 sin permiso.
  - Caché del `PermissionSet` (opcional).

---

## 12. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `models.py`: `Rol`, `Roldet`, `RolUsuario` + `create_table`/seed. |
| 2 | `permissions.py`: `PermissionSet` + resolución tri-estado por orden. |
| 3 | `jwt.py`: `emit/verify/refresh` sobre PyJWT. |
| 4 | `guard.py`: `get_current_user` + `require` (dependencies, imports perezosos). |
| 5 | Integración con `register_crud`/GraphQL + tests end-to-end. |

---

## 13. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Permisos `bool` vs tri-estado | **`bool | None`** (`None` = sin opinión) para que "primero prevalece" y "negación por defecto" convivan. |
| 2 | `modelo:str` sin FK | Validar contra el registro de modelos (`_table`); `"*"` como comodín. |
| 3 | `user_id` | `str` opaco (`STR_50`, máx. 50) ligado al claim `sub`; la app posee la tabla de usuarios. |
| 4 | Orden de roles | `RolUsuario.orden` ascendente; el primer `Roldet` con valor explícito decide. |
| 5 | Rol Público | Se aplica a requests anónimos (sin token). |
| 6 | `delete` vs `remove` | `delete` = lógico, `remove` = físico (`delete(physical=...)`). |
| 7 | JWT | Envolver PyJWT; no reimplementar; access/refresh token. |
| 8 | Hashing de credenciales | Fuera de encinorm; la app gestiona el login. |
| 9 | Alcance por fila (row-level) | Fuera del MVP; hook `scope(user_id)` evolutivo. |
