# Documento de Diseño — Conexión por defecto / ambiente (`db` implícito en el `Model`)

Este documento analiza las recomendaciones **B** de `prompts/analisys-07.md` y
diseña un mecanismo que **elimina la necesidad de pasar `db` a cada instancia**
del `Model`, resolviendo la barrera de adopción "`db` por constructor" (analisys-07
§2.3). El patrón se apoya en `contextvars` (mismo mecanismo que `scope()` y el
pool) y es la base que facilita B.3 (multi-tenant en `load`) y B.4 (DataLoader).

> Complementa `docs/design/1-model.md`, `docs/design/4-crud.md` y
> `docs/design/8-pk.md`. Es **aditivo**: `Model(db, ...)` sigue funcionando como hoy.

---

## 1. Análisis de las recomendaciones B (analisys-07)

| # | Recomendación | Análisis / decisión |
|---|---------------|---------------------|
| B.3 | **Multi-tenant en `load`**: extender `scope` a `load(id)` (o `load_scoped`). | Correctitud real (un tenant no debe leer filas ajenas por id). Usa el mismo patrón `contextvars` que este diseño; se implementa sobre `_effective_filter`/`current_scope`. |
| B.4 | **DataLoader en GraphQL** (o documentar N+1 y exponer `batch_*`). | Mejora de desempeño; independiente de la conexión. El `batch_*` ya existe. |
| B.5 | **CI**: matriz con 3 motores (testcontainers/servicios). | Infraestructura de equipo; fuera del código del ORM. |
| §2.3 | **`db` por constructor** (barrera de adopción). | Es el habilitador transversal: resolver la conexión de forma **implícita** simplifica B.3/B.4 y el uso diario. Se diseña aquí. |

**Conclusión:** B.3–B.5 son independientes entre sí, pero todas se benefician de
que el `Model` no exija `db` explícito. Este documento define el **mecanismo de
conexión por defecto / ambiente** (el "singleton" de conexión), que reduce el
ruido en B.3 y B.4 y habilita un quick-start de una línea.

---

## 2. Estado actual

- `Model.__init__(self, db=None, **kwargs)` guarda `self._db`; si es `None`, todo
  CRUD falla con `AttributeError`/`ConnectionError` al usar `self._db`.
- Los *classmethods* exigen `db`: `insert_many(cls, db, rows)`.
- `batch_reference`/`batch_has_many` toman la conexión de `models[0]._db`.
- `QueryBuilder` se construye con `QueryBuilder(Model, db)`.
- `session(db)` (context manager) ya **obtiene** la conexión por request, pero la
  entrega por parámetro: cada `Model` debe recibirla manualmente.
- `PoolDb` ya usa un `contextvars.ContextVar` (`_current_connection`) para enrutar
  operaciones a la conexión de la transacción en curso.

Es decir: **la conexión ya es contextual en el pool, pero no en el `Model`**.

---

## 3. Diseño propuesto

### 3.1. Módulo nuevo `encinorm/context.py`

Centraliza el estado de conexión por proceso y por contexto:

```python
# encinorm/context.py (nuevo)
import contextvars
from contextlib import contextmanager

from .exceptions import ConnectionError

# Conexión/pool por defecto de TODO el proceso (el "singleton").
_default_db = None

# Conexión ambiente por tarea/contexto (bind / session).
_ambient_db = contextvars.ContextVar("encinorm_ambient_db", default=None)


def set_default_db(db) -> None:
    """Registra la conexión o pool por defecto del proceso."""
    global _default_db
    _default_db = db


def get_default_db():
    return _default_db


@contextmanager
def bind(db):
    """Establece la conexión ambiente para el bloque (async-safe vía contextvar)."""
    token = _ambient_db.set(db)
    try:
        yield db
    finally:
        _ambient_db.reset(token)


def resolve_db():
    """Resuelve la conexión actual. Lanza `ConnectionError` si no hay ninguna."""
    from .pool import _current_connection   # lazy: evita import circular

    conn = _current_connection.get()        # 1. transacción activa del pool
    if conn is not None:
        return conn
    ambient = _ambient_db.get()             # 2. bind()/session()
    if ambient is not None:
        return ambient
    if _default_db is not None:             # 3. set_default_db()
        return _default_db
    raise ConnectionError(
        "Sin conexión: pasa `db`, usa `bind()`, `set_default_db()` o `session()`"
    )
```

### 3.2. Orden de resolución (prioridad)

1. **`db` explícito** en el constructor/método (mayor prioridad, sin cambios).
2. **Transacción activa del pool** (`_current_connection`) — garantiza atomicidad
   y `last_id()` correcto si el modelo se crea dentro de `pool.transaction()`.
3. **Conexión ambiente** (`bind()` / `session()`) — el caso típico por request.
4. **Conexión por defecto** (`set_default_db()`) — apps/scripts de un solo proceso.
5. **Error** `ConnectionError` si no hay ninguna.

### 3.3. Cambios en `Model` (`model/model.py`)

El `_db` sigue siendo `None` para **validación pura** (respuesta pydantic, parsing
de request); la resolución es **perezosa** y se **cachea** en la instancia:

```python
def _get_db(self) -> "Db":
    if self._db is None:
        _set_private(self, "_db", resolve_db())
    return self._db
```

- `__init__` no cambia de firma (`db=None` sigue permitido).
- Todos los métodos que hoy usan `self._db` pasan a `self._get_db()`:
  `insert`, `save`, `load`, `update`, `delete`, `upsert`, `search`, `count`,
  `paginate`, `create_table`, `sync_schema`, `diff_schema`, `query()`,
  `_resolve_reference`, `_resolve_has_many`, `_transactional`.
- `query()` devuelve `QueryBuilder(type(self), self._get_db())`.

*Classmethods* con `db` explícito lo hacen opcional:

```python
@classmethod
async def insert_many(cls, db=None, rows=None, *, chunk=500) -> int:
    db = db or resolve_db()
    ...
```

`batch_reference`/`batch_has_many` usan `models[0]._get_db()` en lugar de
`models[0]._db`.

### 3.4. Integración con `session()` y `pool.transaction()`

- **`session(db)`** envuelve su cuerpo con `bind(conn)` para que cualquier
  `Model()` creado dentro resuelva automáticamente a esa conexión:

```python
@asynccontextmanager
async def session(db):
    if isinstance(db, PoolDb):
        conn = await db.acquire()
        try:
            with bind(conn):
                yield conn
        except Exception:
            if await conn.in_transaction():
                await conn.rollback()
            raise
        else:
            if await conn.in_transaction():
                await conn.commit()
        finally:
            await db.release(conn)
    else:
        with bind(db):
            yield db
```

- **`PoolDb.transaction()`** ya fija `_current_connection`; `resolve_db()` lo
  respeta (prioridad 2), por lo que un `Model()` creado dentro de una transacción
  usa la conexión mantenida y no adquiere una nueva.

> Con esto, `create_crud()`/GraphQL (que inyectan `session(pool)`) propagan la
> conexión al `Model` sin pasarla por parámetro.

### 3.5. Concurrencia y ciclo de vida

- `contextvars` es **por tarea/contexto**: en asyncio no hay colisión entre
  requests concurrentes (cada corutina ve su `bind`). El default de proceso
  (`set_default_db`) es compartido y solo debe apuntar a un `PoolDb` o a una
  conexión de uso exclusivo (scripts).
- No se cierra la conexión automáticamente: el dueño (pool/default) gestiona el
  ciclo de vida; `resolve_db` solo la **referencia**.
- `set_default_db(None)` permite limpiar el singleton (útil en tests).

---

## 4. Ejemplos de uso

```python
from encinorm import set_default_db, bind, session, create_db, PoolDb
from encinorm.model import Model

class User(Model):
    _table = "users"
    name: str | None = None

# --- (a) singleton de proceso ---
db = await create_db("sqlite", database=":memory:")
set_default_db(db)
u = User(name="ana")          # sin `db`
await u.insert()
users = await User().search() # sin `db`

# --- (b) por request (FastAPI / asyncio) ---
pool = PoolDb("sqlite", database=":memory:")
await pool.connect()
async def handler():
    async with session(pool):
        u = User(name="bob")  # resuelve a la conexión del request
        await u.insert()

# --- (c) explícito sigue funcionando ---
await User(db, name="carl").insert()
```

---

## 5. Resumen de cambios por archivo

| Archivo | Cambio |
|---------|--------|
| `encinorm/context.py` | **NUEVO**: `set_default_db`, `get_default_db`, `bind`, `resolve_db`. |
| `encinorm/__init__.py` | Exportar `set_default_db`, `bind`, `resolve_db` (y `get_default_db`). |
| `encinorm/pool.py` | `session()` envuelve con `bind(conn)`; exponer `_current_connection` para `resolve_db` (o moverlo a `context.py`). |
| `encinorm/model/model.py` | `_get_db()` + resolución perezosa cacheada; métodos CRUD/DDL/query usan `_get_db()`; `insert_many`/`batch_*` con `db` opcional. |

---

## 6. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Resolución perezosa vs eager | **Perezosa** (`_get_db()`): permite `Model()` para validación sin conexión; solo resuelve al tocar la BD. |
| 2 | Prioridad | `db` explícito → `_current_connection` → `bind`/`session` → `set_default_db` → error. |
| 3 | `session` + `bind` | `session` establece la conexión ambiente; `PoolDb.transaction()` la re-usa (no adquiere otra). |
| 4 | Singleton de proceso | Pensado para `PoolDb` (concurrente); para conexión cruda, solo scripts de un hilo/tarea. |
| 5 | Limpieza | `set_default_db(None)` para resetear; `bind`/`session` usan `contextvar.reset` (sin fugas). |
| 6 | `_current_connection` | Se importa perezoso en `resolve_db` para evitar import circular. |
| 7 | Relación con B.3 | `scope()`/`current_scope` (ya contextvar) se combina con `_get_db()` para `load_scoped`; no interfiere. |

---

## 7. Dependencias

- Ninguna nueva. Solo `contextvars` + `contextlib` (stdlib).

---

## 8. Estrategia de testing

- **Resolución**: `set_default_db` + `Model().insert()` sin `db`; `bind` por
  contexto; prioridad correcta (explícito > transacción > bind > default).
- **Error**: CRUD sin ninguna conexión lanza `ConnectionError` con mensaje claro.
- **`session`**: `Model()` creado dentro de `session(pool)` usa la conexión del
  request (misma transacción); confirmación/rollback intactos.
- **`PoolDb.transaction()`**: `Model()` dentro usa la conexión mantenida
  (atomicidad + `last_id`).
- **Concurrencia**: dos corutinas con `bind` distintos no se cruzan (contextvar).
- **Compatibilidad**: `Model(db, ...)` explícito y `insert_many(db=...)` siguen
  funcionando; regresión de la suite (333 tests).

---

## 9. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `encinorm/context.py` + exports en `__init__.py`. |
| 2 | `Model._get_db()` + reemplazo de `self._db` en métodos CRUD/DDL/query. |
| 3 | `insert_many`/`batch_*` con `db` opcional; `session` con `bind`. |
| 4 | Documentar quick-start + tests de resolución/concurrencia. |
