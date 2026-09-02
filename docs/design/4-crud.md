# Documento de Diseño — encinorm.http (CRUD REST por modelo)

Helper opcional para **FastAPI** que genera rutas CRUD **tipadas por modelo**
(create/read/update/delete) y expone un registro para introspección de modelos.
Reutiliza el ORM (`Model`, `Filter`, `Records`) y corrige la semántica HTTP
respecto al prompt original.

> Complementa `docs/design/1-model.md` (ORM), `docs/design/3-graphql.md` (GraphQL)
> y `docs/design/2-constraint.md`. No modifica `Db` ni `QueryBuilder`; añade un
> parámetro opcional `sort_by` a `Model.search`/`Model.paginate` (aditivo).

---

## 1. Contexto y Objetivos

El público objetivo son desarrolladores **FastAPI**. Se busca un helper que evite
escribir a mano los mismos endpoints CRUD para cada modelo.

| # | Objetivo |
|---|----------|
| 1 | Generar rutas **tipadas** por modelo (POST/GET/PUT/DELETE) con validación pydantic. |
| 2 | Listados paginados con filtro y orden (`sort_by`), devolviendo `Records` de instancias `Model`. |
| 3 | Registro de modelos para **introspección** (`/models`, `/models/{name}`). |
| 4 | Semántica HTTP correcta: 404 (no encontrado), 422 (validación), 400/500 (BD). |
| 5 | Validación de entrada por pydantic (auto-422); `Model.validate()` queda para uso programático. |
| 6 | Integrarse con `session(db)` para la conexión por request. |
| 7 | Ser **opcional** (fastapi como dependencia extra). |

---

## 2. Veredicto del análisis

El prompt original proponía un endpoint dinámico `/model/{modelo}` con `data: dict`.
**Se descarta** por:

- `data: dict` sin validación tipada (inseguro, anti-idiomático).
- `filter: list[Filter]` / `sort_by: list[str]` no serializables como query params.
- Mezcla de códigos HTTP (403 para "no encontrado").

En su lugar, se genera **una ruta tipada por modelo** (cuerpo/response = el propio
`Model`), con un registro solo para introspección.

---

## 3. Arquitectura y ubicación

```
encinorm/
├── encinorm/
│   ├── ...                     # Db, pool, model (ya existente)
│   └── http/                   # NUEVO (subpaquete opcional)
│       ├── __init__.py         # create_crud, register_crud, install_error_handlers
│       ├── registry.py         # Registry + register_introspection (nombre -> Model)
│       ├── routes.py           # register_crud (rutas tipadas)
│       ├── parsing.py          # filter/sort_by desde query params
│       └── errors.py           # install_error_handlers (mapeo a HTTPException)
└── docs/
    └── 4-crud.md          # este documento
```

- `encinorm.http` importa de `encinorm.model` y `encinorm.pool.session`; nunca al revés.
- `fastapi` es dependencia **opcional**.

---

## 4. Registro de modelos

```python
# encinorm/http/registry.py
class Registry:
    def __init__(self):
        self._models = {}

    def register(self, model_cls) -> None:
        self._models[model_cls._table] = model_cls

    def get(self, name: str):
        return self._models[name]          # KeyError -> 404

    def names(self) -> list[str]:
        return sorted(self._models)
```

El nombre del modelo es `_table`. El registro es explícito (no se auto-descubre),
por seguridad: solo se exponen los modelos registrados.

No hay registro global implícito: el desarrollador crea un `Registry` y lo pasa a
`create_crud`/`register_introspection`, evitando contaminación entre apps/tests.

---

## 5. Generador de rutas CRUD (`register_crud`)

Genera rutas tipadas bajo un `prefix` (p. ej. `/agentes`), con `response_model`
y `request body` iguales al `Model`.

```python
def _cursor(model: type[Model], db, **fields) -> Model:
    """Instancia sin validación para invocar `load()`/`paginate()` sobre modelos
    con campos requeridos (que no se pueden construir vacíos)."""
    obj = model.model_construct(**fields)
    object.__setattr__(obj, "_db", db)
    return obj


def register_crud(router: APIRouter, model: type[Model], prefix: str,
                  *, get_db) -> None:
    """Genera POST/GET/PUT/DELETE tipados bajo `prefix`.

    `get_db` es la dependency de conexión; se inyecta explícitamente."""
    @router.post(prefix + "/", response_model=model, status_code=201)
    async def create(data: model, db=Depends(get_db)) -> model:
        obj = model(db, **data.model_dump(exclude_unset=True))
        await obj.insert()
        return await _cursor(model, db, id=obj.id).load()

    @router.get(prefix + "/", response_model=Records)
    async def list_(limit: int = 50, page: int = 1, sort_by: str = "",
                    filter: str = "", db=Depends(get_db)):
        return await _cursor(model, db).paginate(
            filter=filter_from_str(filter),
            limit=limit, page=page,
            sort_by=sort_from_str(sort_by),
        )

    @router.get(prefix + "/{id}", response_model=model)
    async def get(id: int, db=Depends(get_db)):
        obj = await _cursor(model, db, id=id).load()
        if not obj._exists:
            raise HTTPException(404, detail="no encontrado")
        return obj

    @router.put(prefix + "/{id}", response_model=model)
    async def update(id: int, data: model, db=Depends(get_db)):
        obj = await _cursor(model, db, id=id).load()
        if not obj._exists:
            raise HTTPException(404, detail="no encontrado")
        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(obj, k, v)
        await obj.update()
        return await _cursor(model, db, id=id).load()

    @router.delete(prefix + "/{id}")
    async def delete(id: int, physical: bool = False, db=Depends(get_db)):
        obj = await _cursor(model, db, id=id).load()
        if not obj._exists:
            raise HTTPException(404, detail="no encontrado")
        await obj.delete(physical=physical)
        return {"id": id, "deleted": True}
```

**Mapeo de operaciones:**

| Endpoint | ORM | Respuesta |
|----------|-----|-----------|
| `POST {prefix}/` | `insert()` + `load()` | registro creado (201) |
| `GET {prefix}/` | `paginate()` (con `sort_by`) | `Records` (listado paginado) |
| `GET {prefix}/{id}` | `load()` | registro o 404 |
| `PUT {prefix}/{id}` | `update()` | registro actualizado |
| `DELETE {prefix}/{id}` | `delete(physical=...)` | `{id, deleted}` |

- `list` y `get` devuelven **instancias `Model`** (misma serialización, aliases de
  columna resueltos). No hay filas crudas.
- `Model.paginate`/`Model.search` reciben un `sort_by` opcional (lista de
  `"campo"` / `"-campo"`); ver sección 6.
- Envelope de `list` (`Records`): `{"rows": [...], "total": N, "limit": L, "page": P}`.
- El borrado lógico es el default; `physical=true` fuerza el borrado físico.

### 5.1. `create_crud`: composición de alto nivel

```python
# encinorm/http/__init__.py (concepto)
from encinorm import session

def create_crud(pool, models, *, get_db=None, prefix="/api",
                registry=None, tags=("Model",)) -> APIRouter:
    """Monta CRUD + introspección para `models` en un solo router."""
    if get_db is None:
        async def get_db():
            async with session(pool) as conn:
                yield conn

    registry = registry or Registry()
    router = APIRouter(prefix=prefix, tags=list(tags))
    for model_cls in models:
        registry.register(model_cls)
        register_crud(router, model_cls, "/" + model_cls._table, get_db=get_db)
    register_introspection(router, registry)
    return router
```

Con `create_crud`, el desarrollador no monta a mano el router, el registro, la
`get_db` ni la introspección: solo pasa el `pool` y la lista de modelos.

---

## 6. Parsing de `filter` y `sort_by` desde query

### 6.1. `filter` (JSON)

`filter` se recibe como **JSON** (string) y se convierte a `Filter`. La gramática
es `{campo: {op: valor}}`, compuesta con `and` (lista), `or` (lista) y `not`
(objeto). Un `valor` escalar es atajo de `eq` (`{"region_id": 1}` equivale a
`{"region_id": {"eq": 1}}`):

```
?filter={"agente":{"like":"Héct"},"region_id":{"ge":1}}
?filter={"or":[{"region_id":1},{"agente":{"like":"Héct"}}]}
```

**Operadores** (clave → `Filter` y forma del valor):

| Clave | `Filter` | Valor |
|-------|----------|-------|
| `eq` | `Filter.eq` | escalar |
| `ne` | `Filter.ne` | escalar |
| `gt` / `ge` / `lt` / `le` | `Filter.gt`/`ge`/`lt`/`le` | escalar |
| `in` | `Filter.in_` | lista |
| `like` | `Filter.like` | string (subcadena) |
| `startswith` / `endswith` | `Filter.startswith`/`endswith` | string |
| `between` | `Filter.between` | `[lo, hi]` |
| `is_null` / `not_null` | `Filter.is_null`/`not_null` | (el valor se ignora) |

```python
# encinorm/http/parsing.py (concepto)
import json
from functools import reduce
from encinorm.model import Filter

# Operadores simples `(campo, valor) -> Filter`.
_OP_MAP = {
    "eq": Filter.eq, "ne": Filter.ne, "gt": Filter.gt, "ge": Filter.ge,
    "lt": Filter.lt, "le": Filter.le, "in": Filter.in_,
    "like": Filter.like, "startswith": Filter.startswith,
    "endswith": Filter.endswith,
}

def _apply_op(op: str, campo: str, valor) -> Filter:
    # Operadores con aridad propia (no siguen el patrón `(campo, valor)`):
    if op == "between":
        lo, hi = valor
        return Filter.between(campo, lo, hi)
    if op == "is_null":
        return Filter.is_null(campo)
    if op == "not_null":
        return Filter.not_null(campo)
    return _OP_MAP[op](campo, valor)

def filter_from_str(raw: str) -> Filter | None:
    if not raw:
        return None
    return _from_dict(json.loads(raw))

def _from_dict(d: dict) -> Filter | None:
    partes = []
    for campo, spec in d.items():
        if campo == "and":
            partes.extend(_from_dict(x) for x in spec)
        elif campo == "or":
            sub = [f for f in (_from_dict(x) for x in spec) if f is not None]
            if sub:
                partes.append(reduce(Filter.or_, sub))
        elif campo == "not":
            f = _from_dict(spec)
            if f is not None:
                partes.append(f.not_())
        else:
            for op, valor in spec.items():
                partes.append(_apply_op(op, campo, valor))
    return reduce(Filter.and_, partes) if partes else None
```

> `Filter.and_`/`Filter.or_` son métodos de instancia (`and_(self, other)`); se
> combinan con `reduce`. Los ejemplos se muestran **sin** URL-encoding; en una
> petición real el JSON va codificado.

### 6.2. `sort_by` (CSV con prefijo `-`)

`sort_by` es una lista separada por comas; `-campo` = descendente, `campo` (o
`+campo`) = ascendente. Sin espacios:

```
?sort_by=-region_id,agente
```

```python
def sort_from_str(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]
```

Cada elemento (`"agente"`, `"-region_id"`) lo traduce `Model.paginate` a su
`ORDER BY` (el `sort_by` opcional de `Model.search`/`paginate`).

---

## 7. Introspección de modelos

```python
# encinorm/http/registry.py
def register_introspection(router: APIRouter, registry: Registry) -> None:
    @router.get("/models")
    async def models():
        return registry.names()

    @router.get("/models/{name}")
    async def model_schema(name: str):
        try:
            cls = registry.get(name)
        except KeyError:
            raise HTTPException(404, detail="modelo no encontrado")
        return cls.model_json_schema()   # definición pydantic + restricciones
```

> El `registry` se recibe por parámetro (no hay dependencia global).
> `model_json_schema()` incluye las columnas heredadas (`id`, `enabled`,
> `created_at`, `updated_at`); si se quieren ocultar, se filtra `properties`.

---

## 8. Semántica HTTP y errores

| Situación | Código | Detalle |
|-----------|--------|---------|
| Registro no encontrado (`get`/`update`/`delete`) | 404 | `"no encontrado"` |
| Body inválido (pydantic, `RequestValidationError`) | 422 | estructura estándar de FastAPI |
| `FailOnUpdate` / `QueryError` de BD | 400 | mensaje de la BD |
| `Model.ValidationError` persistente (defensivo) | 422 | `exc.args[0]` (dict campo→mensaje) |
| Excepción no controlada | 500 | mensaje genérico |

```python
# encinorm/http/errors.py (concepto)
from fastapi.responses import JSONResponse
from encinorm.exceptions import QueryError
from encinorm.model.exceptions import FailOnUpdate, ValidationError

def install_error_handlers(app) -> None:
    """Registra los handlers globales (a nivel de app) una sola vez."""

    @app.exception_handler(ValidationError)
    async def _validation(exc, request):
        # encinorm.ValidationError lleva el dict en `args[0]`
        return JSONResponse(status_code=422, content={"detail": exc.args[0]})

    @app.exception_handler(FailOnUpdate)
    async def _fail_update(exc, request):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(QueryError)
    async def _query_error(exc, request):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
```

---

## 9. Integración con `session(db)`

`get_db` entrega **una conexión por request** (no un `PoolDb`). Se inyecta a
`register_crud` (o se deriva del `pool` en `create_crud`); no es una dependencia
global:

```python
from encinorm import PoolDb, session

pool = PoolDb("postgresql", min_size=2, max_size=10, ...)

async def get_db():
    async with session(pool) as conn:
        yield conn
```

Cada ruta declara `db=Depends(get_db)` y opera sobre esa conexión; `session(pool)`
confirma/revierte y devuelve la conexión al pool al terminar el request.

---

## 10. Ejemplo de uso

```python
from fastapi import FastAPI
from encinorm import PoolDb
from encinorm.http import create_crud, install_error_handlers
from encinorm.model import Model

class Region(Model):
    _table = "regiones"
    region: str | None = None

class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None

pool = PoolDb("postgresql", min_size=2, max_size=10, ...)

app = FastAPI()
install_error_handlers(app)
app.include_router(create_crud(pool, [Region, Agente], prefix="/api"))
```

Ejemplos:

```
POST /api/agentes/            {"agente": "Héctor", "region_id": 1}
GET  /api/agentes/?filter={"agente":{"like":"Héct"}}&sort_by=-region_id&page=1&limit=10
GET  /api/agentes/1
PUT  /api/agentes/1           {"agente": "Héctor M."}
DELETE /api/agentes/1?physical=true
GET  /api/models              -> ["agentes", "regiones"]
GET  /api/models/agentes      -> JSON Schema (definición + restricciones)
```

---

## 11. Dependencias

```toml
[project.optional-dependencies]
http = ["fastapi>=0.110"]
```

`encinorm` y `encinorm.model` siguen funcionando sin FastAPI (imports perezosos en `encinorm/http`).

---

## 12. Estrategia de testing

- `pytest` + `pytest-asyncio` + `fastapi.testclient.TestClient` (o `httpx` ASGI).
- SQLite `:memory:` para las pruebas.
- Casos: create (validación 422), get (404), list (filtro/sort/paginación → `Records`
  con instancias `Model`), update (422/404), delete lógico/físico, introspección
  `/models` y `/models/{name}`, y mapeo de errores (validación → 422, no encontrado → 404).

---

## 13. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `registry.py` + `parsing.py` (filter/sort desde query). |
| 2 | `routes.py`: `register_crud` (POST/GET/PUT/DELETE). |
| 3 | `errors.py`: mapeo a HTTPException + handlers. |
| 4 | Endpoints `/models` y `/models/{name}`. |
| 5 | Tests end-to-end con `TestClient` + SQLite. |

---

## 14. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Endpoint dinámico vs. rutas tipadas | **Rutas tipadas por modelo** (validación + OpenAPI). |
| 2 | Registro | Explícito; `Registry` se crea y se inyecta (sin singleton global). |
| 3 | Cuerpo/response | El propio `Model` (pydantic), sin `dict` genérico. |
| 4 | `filter`/`sort_by` | `filter` = JSON (gramática en §6.1); `sort_by` = CSV con prefijo `-`. |
| 5 | Códigos HTTP | 404 / 422 / 400 / 500 (no 403 para "no encontrado"). |
| 6 | Borrado | Lógico por defecto; `physical=true` para físico. |
| 7 | Validación de entrada | pydantic en el body (auto-422); `validate()` solo programático. |
| 8 | Listado | `Model.paginate(sort_by=...)`; `rows` son instancias `Model` (igual que `get`). |
| 9 | Modelos con campos requeridos | `_cursor()` (`model_construct`) para `load()`/`paginate()`. |
| 10 | `PUT` parcial | `exclude_unset=True`; los campos requeridos siguen siendo obligatorios. |
| 11 | Introspección | `model_json_schema()`; columnas heredadas filtrables. |
| 12 | Composición | `create_crud()` (rutas+introspección+`get_db`) y `install_error_handlers()` (errores). |
| 13 | Dependencia | `fastapi` opcional, imports perezosos. |
