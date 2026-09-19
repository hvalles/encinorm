# Phase 5: Resilience - Pattern Map

**Mapped:** 2026-09-18
**Files analyzed:** 20 (7 de librería modificados, 1 verificado sin cambio, 1 barrel, 7 tests, 1 config/gate, 2 docs, 1 nuevo helper)
**Analogs found:** 20 / 20 (todos tienen analog exacto o role-match; ninguno sin analog)

> Autoridad: `05-RESEARCH.md`. Donde el sketch de RESEARCH y el código discrepen, **el código vivo de este documento es la fuente de verdad**. Las anclas `file:line` de abajo están verificadas contra el árbol actual. No existe `05-CONTEXT.md`; las decisiones bloqueadas son las de `ROADMAP.md:277-299` + los Constraints de `PROJECT.md` + el Assumptions Log de RESEARCH.

---

## File Classification

| New/Modified File | Action | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `encino_orm/exceptions.py` — taxonomía | modify | value-object (errores) | — | sí mismo (`exceptions.py:1-22`) + `model/exceptions.py:1-33` | exact |
| `encino_orm/__init__.py` — exportar taxonomía | modify | barrel | — | sí mismo (`__init__.py:13-20`, `:41-85`) | exact |
| `encino_orm/base.py` — `_with_reconnect`/`_reconnect`/`_is_reconnectable`/`_translate_exception`/`_resilience_opts` | modify | controller (ABC, template method) | request-response | sí mismo: `retry` (`base.py:95-109`) + `transaction` (`base.py:60-67`); `PoolDb._run` (`pool.py:456-487`) | exact |
| `encino_orm/base.py` — wrappers públicos `execute`/`execute_insert`/`fetch_*` + rename `_execute`/`_fetch_*` | modify | controller (ABC) | request-response | sí mismo (`base.py:111-155`) + `_last_id_value` concreto (`base.py:167-173`) | exact |
| `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `is_disconnect_error` | modify | adapter (hook de clasificación) | — | sus `is_lock_error` (`sqlite.py:54-55`, `mysql.py:66-69`, `postgresql.py:65-73`, `mssql.py:55-63`, `oracle.py:66-79`) | exact |
| `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `_translate_error` | modify | adapter (hook de mapeo) | — | `install_error_handlers` (`http/errors.py:7-22`) | role-match |
| `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `_connect_kwargs`/`_connected_at` en `connect()` | modify | adapter (estado de conexión) | — | `PoolDb._conn_kwargs` (`pool.py:128`) + firmas `connect(**kwargs)` (`sqlite.py:57`, `mysql.py:71`, `postgresql.py:75`, `mssql.py:74`, `oracle.py:82`) | exact |
| `encino_orm/sqlite.py` — `_reconnect` rechaza `:memory:` | modify | adapter | — | `sqlite.py:57-64` (`database = kwargs.get("database", ":memory:")`) | exact |
| `encino_orm/mariadb.py` | verify (sin cambio) | adapter (subclass) | — | `mariadb.py:7-30` (hereda de `MysqlDb`) | exact |
| `encino_orm/pool.py` | verify (sin cambio de comportamiento) | wrapper/pool | concurrency | sí mismo (`pool.py:456-487`, `:196-200`) | exact |
| `encino_orm/base.py` — `pre_ping`/`max_connection_lifetime` | modify | controller (política) | request-response | `PooledConnection.last_used`/`is_idle_for` (`pool.py:60,65-77`) + `_reap` (`pool.py:209-252`) | role-match |
| `tests/_resilience_helpers.py` — `FakeResilientDb` | new | test helper | unit (fake driver) | `tests/_pool_helpers.py:20-131` (`FakeDb`/`BlockingFakeDb`) | exact |
| `tests/test_resilience.py` | new | test | unit parametrizado | `tests/test_oracle.py:22-94` + `tests/test_base.py:30-33` | role-match |
| `tests/test_resilience_lifetime.py` (opcional, fusionable) | new | test | unit + reloj falso | `tests/test_pool.py` (monkeypatch de reloj) | role-match |
| `tests/test_base.py` | extend | test | unit | sí mismo (`test_base.py:30-33`) | exact |
| `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` | extend | test | integration/unit | `test_oracle.py:89-94` (clasificadores con `_FakeExc`) | exact |
| `tests/test_resilience_integration.py` (opcional) | new | test | integration | `tests/test_{mysql,postgresql,...}.py` + `conftest.engine_unavailable` | role-match |
| `pyproject.toml` — ratchet mypy | modify | config | — | sí mismo (`pyproject.toml:243-283`, en especial `:269-283`) | exact |
| `docs/engines.md` + `CHANGELOG.md` | modify | docs | prosa | `docs/engines.md:138-158`; `CHANGELOG.md:9-50` (`[Unreleased]`) | role-match |

---

## Pattern Assignments

### `encino_orm/exceptions.py` — taxonomía pública (RESL-04)

**Analog:** sí mismo (`exceptions.py:1-22`) para la forma plana, y `model/exceptions.py:1-33` para el precedente de un subárbol que importa `EncinoOrmError`.

**Jerarquía actual completa** (`exceptions.py:1-22`):
```python
class EncinoOrmError(Exception):
    pass


class ConnectionError(EncinoOrmError):
    pass


class QueryError(EncinoOrmError):
    pass


class UnsupportedEngineError(EncinoOrmError):
    pass


class MigrationError(EncinoOrmError):
    pass


class PoolExhaustedError(EncinoOrmError):
    pass
```

**Precedente de subárbol con base compartida** (`model/exceptions.py:1-8`):
```python
from encino_orm.exceptions import EncinoOrmError


class ModelError(EncinoOrmError):
    pass


class FailOnUpdate(ModelError):
    pass
```

**Convenciones a copiar:**
- Clases planas, cuerpo `pass`, sin `__init__` ni `__str__` propios. La jerarquía se expresa **solo** por herencia (igual que `model/exceptions.py:1-33`).
- Aditivo: `ConnectionLostError(ConnectionError)` para que `except ConnectionError` siga capturando (RESEARCH Open Q5); `OperationalError`/`IntegrityError`/`ProgrammingError(QueryError)`.
- El mensaje se construye al **lanzar** (f-string en español, `CONVENTIONS.md` §Error Handling), no en la clase. Patrón: `raise ConnectionLostError(f"conexión perdida durante la operación: {exc}")`.
- Actualizar el barrel `encino_orm/__init__.py:13-20` y `__all__` (`:41-85`) con los cuatro nombres nuevos — es el contrato de importación pública del repo.

**Lo que NO se copiar:**
- **No renombrar ni re-parentar** las clases existentes (`ConnectionError`, `QueryError`, etc.): son API pública en `__init__.py:13-20` y romperían `except` de usuarios y tests.
- **No heredar de `Exception` directo**: todo cuelga de `EncinoOrmError` (`exceptions.py:1`), la convención del repo.
- **No añadir `__init__`/`args` estructurados**: `ValidationError` ya usa `args[0]` como dict (`http/errors.py:12-14`); la taxonomía nueva no necesita ese contrato.
- **No usar `raise ... from`** (convención del repo: `CONVENTIONS.md` §Error Handling, "`raise ... from` chaining is not used"). El sketch de RESEARCH usa `raise ... from exc`; si se adopta, es una desviación **consciente** que debe quedar escrita (ver Shared Patterns → "Chaining").
- **A3 (documentar):** al heredar de `QueryError`, el handler `_query_error` (`http/errors.py:20-22`) las mapeará a **400** en vez de 500. Es cambio de comportamiento → entrada en `CHANGELOG.md`.

---

### `encino_orm/base.py` — `_with_reconnect` como template method (RESL-02)

**Analog:** los dos template methods actuales de `Db`: `transaction()` (`base.py:60-67`) y `retry()` (`base.py:95-109`); y `PoolDb._run` (`pool.py:456-487`) como precedente de "wrapper único que centraliza un `try/except/else/finally`".

**`retry()` — clasificación sobre la excepción ORIGINAL** (`base.py:95-109`):
```python
async def retry(self, coro, tries: int | None = None):
    max_tries = tries if tries is not None else self.MAX_TRIES
    last_exc = None
    for attempt in range(max_tries):
        try:
            return await coro()
        except Exception as exc:
            if not self.is_lock_error(exc):   # clasificación sobre el tipo ORIGINAL
                raise
            last_exc = exc
            if attempt + 1 >= max_tries:
                break
            await self.wait()
    raise last_exc
```

**`transaction()` — try/except que preserva la excepción raíz** (`base.py:60-67`):
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

**`PoolDb._run` — delegación única con rama de error explícita** (`pool.py:456-487`):
```python
async def _run(self, method: str, *args):
    handle = self._owned_connection()
    if handle is not None:
        return await getattr(handle.driver, method)(*args)
    handle = await self.acquire()
    try:
        result = await getattr(handle.driver, method)(*args)
    except BaseException:
        ...
        raise
    else:
        ...
        return result
    finally:
        await self.release(handle)
```

**Convenciones a copiar:**
- La clasificación se hace sobre la excepción **original** del driver, nunca sobre una ya traducida (`base.py:103`); `_with_reconnect` debe clasificar con `is_disconnect_error(exc)`/`is_lock_error(exc)` **antes** de traducir.
- Estructura `try: return await fn()` / `except Exception as exc:` → decidir → reconectar → **un solo** segundo intento; el segundo fallo se traduce y se relanza.
- Exactamente-una-vez: **sin bucle y sin backoff** en `_with_reconnect`; el bucle/backoff es de `retry()` (`base.py:99-108`). Dos bucles se pisan (Pitfall 3).
- Guard de transacción con el `in_transaction()` existente por driver (`sqlite.py:82-85`, `mysql.py:89-92`, `postgresql.py:93-96`, `mssql.py:120-121`, `oracle.py:120-121`); no crear un flag nuevo (RESEARCH §Don't Hand-Roll).
- `_is_reconnectable(exc)` debe cubrir `is_disconnect_error(exc)` **o** (`isinstance(exc, ConnectionError)` de la librería **y** `self._connected_at is not None`) — Pitfall 1 / A1: el camino más común (caída en reposo) lanza `ConnectionError` desde `_ensure_connected()` (`mysql.py:112-114`, `postgresql.py:121-123`), no el error del driver.
- `_reconnect()` = `close()` + `connect(**self._connect_kwargs)`, con guard `_connected_at is not None`; envolver el `close()` en `try/except` (Pitfall 6, defensa barata).
- `_with_reconnect` se aplica **solo** a `execute`/`execute_insert`/`fetch_all`/`fetch_one`/`fetch_many`. **Nunca** a `is_alive`/`in_transaction`/`commit`/`rollback` (los usa el guard → recursión) ni a `migrate` (ya usa las ops envueltas internamente).

**Lo que NO se copiar:**
- **No `@abstractmethod` en `_execute`/`_fetch_*`/`_execute_insert`.** El precedente correcto es `_last_id_value()` (`base.py:167-173`): método **concreto** y sobreescribible. Si se hacen abstractos, `LockDb` (`test_d_recommendations.py:157`) y `LedgerDb` (`test_migration_reconcile.py:22`) dejan de instanciarse (`TypeError: Can't instantiate abstract class`, Pitfall 10).
- **No envolver `exists()`** (`sqlite.py:241-242`): ya llama a `self.fetch_one(qry)`; envolver ambos duplica la capa de reconexión.
- **No envolver `list_tables`/`paginate`** (`base.py:195-241`): ya llaman a `self.fetch_one`/`self.fetch_many`.
- **No reintentar errores de lock** en `_with_reconnect`: son de `retry()`.
- **No reintentar dentro de transacción**: guard obligatorio, "never silently duplicates a write".
- **No catch-all `except Exception` que trague**: está **explícitamente** fuera de alcance (`REQUIREMENTS.md:124`).
- **No añadir backoff/sleep**: un solo intento.
- **No reasignar el objeto driver en `PoolDb`**: reconectar **in-place** conserva el handle (Fase 4); el pool no se toca.
- **No emitir warnings por operación**: `filterwarnings = ["error"]` (`pyproject.toml:56-72`) tumba la suite (Pitfall 9). La auto-reconexión es cambio documentado en `CHANGELOG.md`, no warning de runtime.

---

### `encino_orm/base.py` — wrappers públicos + rename `execute`→`_execute` (RESL-02)

**Analog:** sí mismo. El contrato abstracto actual (`base.py:111-155`) y el patrón de "método público concreto que delega en un privado sobreescribible" (`last_id()`/`_last_id_value()`, `base.py:157-173`).

**Contrato actual** (`base.py:130-152`):
```python
@abstractmethod
async def execute(self, qry: Query): ...

@abstractmethod
async def execute_insert(self, qry: Query) -> int | None:
    ...

@abstractmethod
async def fetch_all(self, qry: Query): ...

@abstractmethod
async def fetch_one(self, qry: Query): ...

@abstractmethod
async def fetch_many(self, qry: Query, limit: int, page: int): ...
```

**Precedente del wrapper público → privado** (`base.py:157-173`):
```python
async def last_id(self):
    """DEPRECADO: usa `execute_insert(qry)` o el retorno de `Model.insert()`."""
    _warn_last_id_deprecated()
    return await self._last_id_value()

async def _last_id_value(self) -> int:
    """Id de la última inserción de ESTA conexión (0 si no está disponible).

    Método concreto y sobreescribible por adaptador: los dobles de test no
    necesitan implementarlo.
    """
    return 0
```

**Forma objetivo del wrapper:**
```python
# base.py — nuevo. `_execute`/`_fetch_*` son las implementaciones ACTUALES renombradas.
async def execute(self, qry: Query):
    return await self._with_reconnect(lambda: self._execute(qry))

async def _execute(self, qry: Query):
    raise NotImplementedError("execute() no implementado para este motor")
```

**Convenciones a copiar:**
- Los métodos públicos pasan a **concretos** en `Db`; cada adaptador renombra su `execute`→`_execute`, `execute_insert`→`_execute_insert`, `fetch_all`→`_fetch_all`, `fetch_one`→`_fetch_one`, `fetch_many`→`_fetch_many`.
- Los privados nuevos nacen **concretos** y lanzan `NotImplementedError` con mensaje en español (mismo criterio que `_tables_sql`/`columns_of`, `base.py:181-193`) — **no** `@abstractmethod` (Pitfall 10).
- Los dobles de test que **sobreescriben el método público** (`LockDb.execute` en `test_d_recommendations.py:202`, `FakeDb.execute` en `_pool_helpers.py:82`) siguen funcionando sin cambios: el MRO resuelve su override y nunca entra al wrapper de `Db`. Esto es exactamente lo que exige la RESEARCH (RESEARCH §Anti-Patterns).
- Las llamadas internas de `Db` a sí mismo (`exists`→`fetch_one`, `list_tables`→`fetch_one`/`fetch_many`) pasan por el wrapper público y se benefician de la resiliencia sin tocar nada.
- `PoolDb` (`pool.py:516-541`) **no** cambia: `_run` hace `getattr(handle.driver, method)` (`pool.py:461,464`) y el driver es un adaptador concreto, así que hereda el wrapper automáticamente. Verificar, no reescribir.
- El rename **no toca SQL**: `Query` conserva `.sql`/`.params`/`.sql_template`/`.returns_id`/`.id_column`; los snapshots `.ambr` y los golden strings de `test_dialect_builders.py` **no** se regeneran (RESEARCH §Runtime State Inventory).

**Lo que NO se copiar:**
- **No cambiar la firma pública** de `execute`/`fetch_*` (los llaman `model/model.py`, `migration.py`, `transfer.py`, `http/`, `graphql/`, `pool.py`).
- **No usar `**kwargs` opacos** en los wrappers: la firma debe seguir siendo `(qry: Query)` / `(qry, limit, page)` para conservar mypy y el contrato de `PoolDb._run`.
- **No mover el rename a los llamadores**: el rename es interno a cada adaptador; ningún llamador externo debe cambiar.
- **No envolver `execute` dentro de `_run` de nuevo** (doble reconexión): `PoolDb._run` ya delega; no añadir `_with_reconnect` en `pool.py`.

---

### `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `is_disconnect_error` (RESL-01)

**Analog por adaptador:** su propio `is_lock_error` — mismo rol, mismo contrato booleano, mismo lugar en el fichero (bloque `# --- errores ---`). La regla dura: **exclusión mutua** con `is_lock_error` (Success Criterion 1).

**Las cinco implementaciones existentes (estado actual):**

| Motor | `is_lock_error` | Ancla | Mecanismo |
|-------|-----------------|-------|-----------|
| SQLite | `"locked" in str(exc) or "busy" in str(exc)` | `sqlite.py:54-55` | substring (embebido) |
| MySQL/MariaDB | `code[0] in (1205, 1213)` | `mysql.py:66-69` | `args[0]` errno |
| PostgreSQL | `isinstance(exc, (DeadlockDetectedError, SerializationError, LockNotAvailableError))` | `postgresql.py:65-73` | tipo de driver |
| MSSQL | `self._native_code(exc) in (1205, 1222)` | `mssql.py:55-63` | `args[1][0]` |
| Oracle | `self._ora_code(exc) in (60, 54, 8177)` | `oracle.py:66-79` | `args[0].code` |

**Patrón de clasificación por tipo/atributo, sin catch-all** (`postgresql.py:65-73`, `mssql.py:55-63`, `oracle.py:66-79`):
```python
# mssql.py:55-63 — helper de extracción defensivo + predicado final
def _native_code(self, exc) -> int | None:
    try:
        return int(exc.args[1][0])
    except (IndexError, TypeError, ValueError):
        return None

def is_lock_error(self, exc: Exception) -> bool:
    return self._native_code(exc) in (1205, 1222)

# oracle.py:66-79 — el helper actual SOLO lee `.code` (defecto a corregir en disconnect)
def _ora_code(self, exc) -> int | None:
    try:
        err = exc.args[0]
        return getattr(err, "code", None)
    except (IndexError, TypeError):
        return None
```

**Formas objetivo (verificadas con sondas reales, RESEARCH §Code Examples):**
```python
# MySQL/MariaDB — mysql.py (nuevo, junto a is_lock_error en :66-69)
_DISCONNECT_ERRNOS = (2006, 2013, 2055)   # gone away / lost during query / lost at handshake

def is_disconnect_error(self, exc: Exception) -> bool:
    if isinstance(exc, aiomysql.InterfaceError):
        return True
    if isinstance(exc, aiomysql.OperationalError):
        errno = exc.args[0] if exc.args else None
        return errno in _DISCONNECT_ERRNOS       # 1213/1205 quedan FUERA (lock)
    return False

# Oracle — leer TAMBIÉN full_code (DPY-4011 trae code == 0)
def is_disconnect_error(self, exc: Exception) -> bool:
    if isinstance(exc, self._oracledb.InterfaceError):   # `_oracledb` se fija en connect()
        return True
    err = exc.args[0] if getattr(exc, "args", None) else None
    if getattr(err, "code", None) in _ORA_DISCONNECT_CODES:
        return True
    return getattr(err, "full_code", None) in _ORA_DISCONNECT_DPY
```

**Convenciones a copiar:**
- Predicado booleano puro, sin efectos: recibe `Exception`, devuelve `bool`, termina en `return False`. Nunca captura ni relanza.
- Extracción defensiva de atributos con `getattr(..., None)` + `try/except (IndexError, TypeError)` como `_native_code` (`mssql.py:55-59`) y `_ora_code` (`oracle.py:66-71`).
- Clasificación por **tipo de driver** o **SQLSTATE/errno/código estructurado** primero; el substring es **refuerzo** solo donde el código es genérico (MSSQL `HY000`, Pitfall 7).
- **Importación diferida**: `aiomysql`/`asyncpg`/`pyodbc`/`oracledb` se importan dentro del adaptador (ya es así; `oracle.py:84` lo hace dentro de `connect()`); `base.py` **no** importa drivers.
- **Exclusión mutua** verificable con tests: para cada motor, un caso disconnect → `True`/`False` y un caso lock → `False`/`True`.
- Mantener el estilo de comentario con los códigos citados (`mysql.py:67` `# 1213 deadlock, 1205 lock wait timeout`).

**Lo que NO se copiar:**
- **No reutilizar `_ora_code` tal cual** para disconnect: solo lee `.code` y `DPY-4011` tiene `code == 0` (Pitfall 8). Hay que leer `.full_code`.
- **No clasificar MSSQL solo por `args[0].startswith("08")`**: el caso mid-query llega como `HY000` (`pyodbc.Error('HY000', '...Connection may have been terminated by the server... (596)')`, Pitfall 7). Aceptar `08xxx` **o** (`HY000`/`40001` no-lock + substring `"Communication link failure"`/`"terminated by the server"`/`"session is in the kill state"`).
- **No clasificar por substring en todos los motores**: los mensajes ODBC vienen **localizados** (en español en este host: "Se ha forzado la interrupción..."); el tipo/SQLSTATE es la fuente primaria.
- **No marcar PostgreSQL `InvalidCachedStatementError`** como disconnect: es invalidación de statement cache, no pérdida de conexión.
- **No marcar SQLite `OperationalError('database is locked')`** como disconnect: es lock (`sqlite.py:55`).
- **No marcar MySQL `OperationalError(1213/1205)`** como disconnect.
- **No tocar `is_lock_error`**: el camino `retry()` (`base.py:103`) depende de que siga viendo el original.

---

### `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `_translate_error` (RESL-04)

**Analog:** `install_error_handlers` (`http/errors.py:7-22`) — el precedente de **mapeo centralizado por tipo**, un único punto, sin `try/except` disperso.

**Mapeo centralizado existente** (`http/errors.py:7-22`):
```python
def install_error_handlers(app) -> None:
    """Registra los handlers globales (a nivel de app) una sola vez."""
    from fastapi.responses import JSONResponse

    @app.exception_handler(ValidationError)
    async def _validation(exc, request):
        return JSONResponse(status_code=422, content={"detail": exc.args[0]})

    @app.exception_handler(QueryError)
    async def _query_error(exc, request):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
```

**Convenciones a copiar:**
- Un único punto de traducción: `Db._translate_exception(exc)` en `base.py` (invocado desde `_with_reconnect`), que delega en el hook por adaptador `_translate_error(exc)` (default: `OperationalError(str(exc))`). Seis `except` divergentes en adaptadores es exactamente lo que el repo ya centralizó en `http/errors.py` y con `_warn_last_id_deprecated` (`base.py:15-26`).
- El hook por adaptador se coloca junto a los clasificadores (bloque `# --- errores ---`) y usa los helpers ya existentes: `is_unique_violation` (`mssql.py:65-71`, `oracle.py:77-79`), `_native_code` (`mssql.py:55-59`), `_ora_code` (`oracle.py:66-71`).
- **Cortocircuito de lock**: `_translate_exception` debe devolver `exc` sin traducir cuando `is_lock_error(exc)` es `True` (Pitfall 3; `retry()` en `base.py:103` necesita el original). Mismo criterio para no traducir el disconnect original antes de clasificarlo.
- Los mensajes nuevos son f-strings en español que **incluyen el mensaje del driver** pero **nunca** `_connect_kwargs` (Security V7 / ASVS V7: no filtrar `password`).

**Lo que NO se copiar:**
- **No un `try/except` por método en los seis adaptadores**: seis copias divergen.
- **No traducir errores de lock**: rompe `TestD4AutoRetry` (`tests/test_d_recommendations.py:154-245`).
- **No tragarse la excepción** (`except Exception: pass`): la traducción mapea y **relanza**; el catch-all está fuera de alcance.
- **No importar drivers en `base.py`**: el hook default no conoce drivers; el mapeo específico vive en el adaptador.
- **No loguear `_connect_kwargs`** ni el dict crudo en la ruta de traducción/reconexión.

---

### `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — `_connect_kwargs` / `_connected_at` (RESL-02/03)

**Analog:** `PoolDb._conn_kwargs` (`pool.py:128`) + las firmas `connect(**kwargs)` de los adaptadores.

**Almacenamiento de kwargs en el pool** (`pool.py:128`, uso en `:198`):
```python
self._conn_kwargs = conn_kwargs          # pool.py:128 (constructor)

async def _create_connection(self) -> PooledConnection:
    db = self._engine_cls()
    await db.connect(**self._conn_kwargs)     # pool.py:197-198
    ...
```

**Firmas `connect(**kwargs)` actuales (punto de paso obligado):**
```python
# sqlite.py:57-64
async def connect(self, **kwargs):
    database = kwargs.get("database", ":memory:")
    self._database = database
    self._connection = await aiosqlite.connect(database)
    ...

# mysql.py:71-73
async def connect(self, **kwargs):
    self._connection = await aiomysql.connect(**kwargs)
    self._database = kwargs.get("db")

# postgresql.py:75-77
async def connect(self, **kwargs):
    self._connection = await asyncpg.connect(**kwargs)
    self._database = kwargs.get("database")

# mssql.py:74-98 — construye conn_str desde kwargs individuales
# oracle.py:82-99 — construye dsn desde kwargs individuales
```

**Convenciones a copiar:**
- Guardar `self._connect_kwargs = dict(kwargs)` **antes** de transformar (MSSQL/Oracle construyen `conn_str`/`dsn`; `_reconnect` debe re-llamar `connect(**self._connect_kwargs)` con los kwargs originales, no con la cadena).
- `self._connected_at = time.monotonic()` **tras** el `connect()` exitoso (mismo reloj que el pool, `pool.py:60,67,77`).
- Extraer `pre_ping`/`max_connection_lifetime` con un helper común `_resilience_opts(kwargs)` en `base.py` que haga `pop` **antes** de reenviar al driver (RESEARCH §Code Examples).
- `__init__` de cada adaptador ya inicializa estado (`sqlite.py:46-48`, `mysql.py:57-60`, `oracle.py:55-59`, `mssql.py:45-48`); añadir `_connect_kwargs = None`/`_connected_at = None` ahí.
- `SqliteDb` ya guarda `self._database` (`sqlite.py:59`): usarlo en `_reconnect` para rechazar `:memory:`.

**Lo que NO se copiar:**
- **No añadir parámetros al `__init__` de `Db`/adaptadores**: `PoolDb._create_connection` (`pool.py:197`) y `create_db` (`pool.py:568`) construyen `cls()` **sin argumentos**; un `__init__` con parámetros rompería ambos (RESEARCH §Alternatives).
- **No loguear `_connect_kwargs`**: contienen `password`.
- **No usar `datetime.now()`/`time.time()`**: solo `time.monotonic()`.
- **No reconectar SQLite `:memory:`**: `close()` + `connect(database=":memory:")` crea una base **vacía** → pérdida silenciosa de datos (Pitfall 2). `SqliteDb._reconnect` debe lanzar `ConnectionLostError` (o `ValueError`).
- **No reasignar `_connection` sin limpiar `_in_tx`/`_last_id`**: `mssql.py:98`, `oracle.py:98` fijan `_in_tx=False`; replicar en `_reconnect` (o dejar que `connect()` lo haga).

---

### `encino_orm/base.py` — `pre_ping` / `max_connection_lifetime` (RESL-03)

**Analog:** `PooledConnection.last_used`/`is_idle_for` (`pool.py:60,65-77`) y el reaper perezoso `_reap` (`pool.py:209-252`).

**Reloj + predicado de ociosidad del pool** (`pool.py:60,65-77`):
```python
last_used: float = field(default_factory=time.monotonic)

def touch(self) -> None:
    self.last_used = time.monotonic()

def is_idle_for(self, timeout: float | None) -> bool:
    if timeout is None:
        return False
    return time.monotonic() - self.last_used > timeout
```

**Reaper perezoso, sin daemon** (`pool.py:209-252`): invocado al entrar en `acquire()` (`:259`) y al salir de `release()` (`:336`); `idle_timeout=None` desactiva (`:223-224`).

**Guard de conexión (`_ensure_connected`)** (`sqlite.py:105-107`, `mysql.py:112-114`, `postgresql.py:121-123`, `mssql.py:143-145`, `oracle.py:143-145`):
```python
def _ensure_connected(self):
    if not self._connection:
        raise ConnectionError("No hay conexión activa a la base de datos.")
```

**Sonda de salud ya existente** (`mysql.py:80-87`, `postgresql.py:84-91`, `sqlite.py:71-80`, `mssql.py:105-118`, `oracle.py:106-118`) — el pool ya la usa en `acquire()` (`pool.py:296`).

**Convenciones a copiar:**
- `pre_ping: bool = False` y `max_connection_lifetime: float | None = None` como atributos de **clase** en `Db` (defaults conservadores), fijados por instancia en `connect()` (opt-in). Mismo shape que `dialect`/`transactional_ddl` (`base.py:34-39`).
- `_should_recycle()` con `_connected_at is None` → `False` (nunca conectado, nada que reciclar) y `time.monotonic() - self._connected_at >= lifetime`; `None` desactiva (paralelo a `is_idle_for`, `pool.py:75-77`).
- `pre_ping` debe **reconectar inmediatamente** cuando `is_alive()` es `False`, no solo anotar el fallo: `aiomysql.ping(reconnect=False)` sobre una conexión muerta deja `closed=True` (`mysql.py:84`) y la siguiente operación lanzaría `ConnectionError` (Pitfall 5).
- `max_connection_lifetime` mide **edad de conexión**, no inactividad (A5; semántica de `pool_recycle`).
- El coste (un round-trip por operación) se documenta; `pre_ping=False` por defecto.

**Lo que NO se copiar:**
- **No usar `time.time()`/`datetime.now()`**: el pool ya usa `time.monotonic()` (`pool.py:60`), inmune a saltos de reloj.
- **No añadir un daemon/reaper de fondo**: el precedente del repo es reaper **perezoso** (`pool.py:209-222`); el daemon está Out of Scope (`REQUIREMENTS.md:122`).
- **No implementar reciclado a nivel de pool**: `RELI-03` es v2; RESL-03 es **solo conexiones directas**. `max_connection_lifetime` aplica por conexión física vía `connect()` (A6), documentarlo.
- **No reemplazar `is_alive()`** por un `SELECT 1` ad-hoc: ya existe en los seis y el pool lo usa (`pool.py:296`).
- **No olvidar el guard `_connected_at is not None`**: si `pre_ping` corre antes de conectar, reconectaría una conexión que nunca existió.

---

### `tests/_resilience_helpers.py` — `FakeResilientDb` (Wave 0)

**Analog:** `tests/_pool_helpers.py` (`FakeDb` `:20-111`, `BlockingFakeDb` `:119-131`, `EventBarrier` `:134-164`) y `tests/test_pool_characterization.py:37-150`.

**Doble a mano con registro de llamadas y `transaction()` como `@asynccontextmanager`** (`_pool_helpers.py:20-56`):
```python
class FakeDb:
    """Doble de `Db` que registra cada llamada en `self.calls`."""

    def __init__(self):
        self.connected = False
        self.closed = False
        self.calls = []
        self._last = 0
        self._in_tx = False

    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("begin",))
        try:
            yield self
            self.calls.append(("commit",))
            self._in_tx = False
        except Exception:
            self.calls.append(("rollback",))
            self._in_tx = False
            raise
```

**Subclase que añade comportamiento determinista** (`_pool_helpers.py:119-131`):
```python
class BlockingFakeDb(FakeDb):
    async def connect(self, **kwargs):
        barrier = _CONNECT_BARRIER
        if barrier is not None:
            await barrier.wait()
        await super().connect(**kwargs)
```

**Extracción de excepciones de driver a mano (Oracle)** (`tests/test_oracle.py:22-29`):
```python
class _FakeError:
    def __init__(self, code):
        self.code = code


class _FakeExc(Exception):
    def __init__(self, code):
        self.args = (_FakeError(code),)
```

**Fakes que heredan de `Db`** (`test_d_recommendations.py:157-204` `LockDb`; `test_migration_reconcile.py:22-70` `LedgerDb`): implementan solo el subconjunto que usan y sobreescriben `execute`/`fetch_*` **públicos**.

**Convenciones a copiar:**
- Dobles **a mano**, sin `unittest.mock` (convención explícita en `_pool_helpers.py:9-11` y `test_pool_characterization.py:15-20`).
- `FakeResilientDb(Db)` con: `_execute` que lanza un disconnect en la 1ª llamada y devuelve `"ok"` en la 2ª; `is_disconnect_error=True`; `in_transaction()` configurable; contadores de `connect()`/`close()`/`_execute`.
- Registro en `self.calls` de cada operación (patrón `_pool_helpers.py:26,43,48`).
- Docstring de módulo con prefijo `_` para que pytest **no** lo colecte (`_pool_helpers.py:1-12`), y `__all__` (`:17`).
- Construir las excepciones con las **firmas reales verificadas** (RESEARCH §Validation Architecture): `pymysql.err.OperationalError(2013, ...)`, `asyncpg.exceptions.ConnectionDoesNotExistError(...)`, `pyodbc.Error('HY000', ...)`, `oracledb.exceptions.DatabaseError` con `args[0].full_code='DPY-4011'`, `sqlite3.ProgrammingError('Cannot operate on a closed database.')`.

**Lo que NO se copiar:**
- **No `unittest.mock`/`MagicMock`**: la convención del repo es dobles a mano.
- **No `asyncio.Barrier`/`TaskGroup`/`asyncio.timeout`**: piso Python 3.10 (`_pool_helpers.py:7-11`; `pyproject.toml` `python_version = "3.10"`).
- **No temporizadores/`sleep` reales**: para RESL-03, `monkeypatch.setattr(time, "monotonic", ...)`; para la carrera, `EventBarrier` (`_pool_helpers.py:134-164`).
- **No tests que dependan de red real** en `test_resilience.py` (los kills reales van a `test_resilience_integration.py`, marcados y auto-skip).
- **No heredar de `Db` y sobreescribir solo `_execute` sin implementar el resto**: los dobles deben seguir siendo instanciables (es el contrato que el rename debe preservar).

---

### `tests/test_resilience.py` / `test_resilience_lifetime.py` (Wave 0)

**Analog:** `tests/test_oracle.py:84-94` (clasificadores con `_FakeExc`), `tests/test_base.py:30-39` (jerarquía y `_ensure_connected`), `tests/test_pool.py` (monkeypatch de reloj/engine).

**Test de clasificador por motor** (`test_oracle.py:89-94`):
```python
def test_is_lock_error(self):
    db = OracleDb()
    assert db.is_lock_error(_FakeExc(60)) is True   # ORA-00060 deadlock
    assert db.is_lock_error(_FakeExc(54)) is True   # ORA-00054 lock timeout
    assert db.is_lock_error(_FakeExc(8177)) is True # ORA-08177 serialization
    assert db.is_lock_error(_FakeExc(1)) is False
```

**Test de jerarquía** (`test_base.py:30-33`):
```python
def test_exceptions_subclass_encino_orm(self):
    for exc in (ConnectionError, MigrationError, PoolExhaustedError):
        assert issubclass(exc, EncinoOrmError)
```

**Convenciones a copiar:**
- Parametrizar por motor cuando la firma de la excepción lo permita; un bloque `-k disconnect`, `-k reconnect`, `-k lifetime`, `-k translate` (RESEARCH §Phase Requirements → Test Map).
- Criterio 2 con doble: disconnect fuera de tx → resultado `"ok"`, `connect` 1 vez, `close` 1 vez, `_execute` 2 veces; `in_transaction=True` → `pytest.raises` y `connect` **0** veces; "siempre falla" → `pytest.raises` y `_execute` exactamente 2 veces (no bucle).
- Criterio 3: `monkeypatch.setattr(time, "monotonic", ...)`; `pre_ping=True` con `is_alive()` False → reconecta; `SqliteDb(database=":memory:")` → `_reconnect` lanza.
- Criterio 4: `pytest.raises(ConnectionLostError)`/`OperationalError`/`IntegrityError`/`ProgrammingError` + asserts de compatibilidad (`issubclass(ConnectionLostError, ConnectionError)`, `issubclass(OperationalError, QueryError)`) y que `is_lock_error` sigue viendo el original.
- Tests unitarios **sin servidores**; la integración opcional reutiliza `conftest.engine_unavailable` (`tests/conftest.py:32-45`) y los markers `integration`/`optional_engine`.

**Lo que NO se copiar:**
- **No usar los contenedores para los unitarios**: la clasificación se prueba con excepciones construidas con las firmas reales.
- **No `pytest.raises(Exception)`** sin `match` (el repo ignora `PT011` en `tests/**`, `pyproject.toml:127-131`, pero no es excusa para añadir ruido nuevo).
- **No `sleep`/timeouts reales** para simular inactividad.

---

### `tests/test_base.py` y `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` (extend)

**Analog:** sí mismos. `test_base.py:30-33` es el precedente exacto de "assert de jerarquía"; `test_oracle.py:84-94` el de "clasificador con excepción sintética".

**Convenciones a copiar:**
- Añadir a `test_base.py` los asserts de la taxonomía nueva y la compatibilidad de herencia (los cuatro nombres).
- Añadir a cada `test_{motor}.py` el par disconnect/lock de su motor, reutilizando `_FakeExc`/helpers locales cuando existan (`test_oracle.py:22-29`).
- MariaDB: reutilizar el patrón `from encino_orm.mysql import MysqlDb` (`test_mariadb.py:20`) y verificar que hereda `is_disconnect_error` de `MysqlDb` (no duplicar la implementación, `mariadb.py:7-30`).

**Lo que NO se copiar:**
- **No duplicar el clasificador en MariaDB**: hereda de `MysqlDb`; solo verificar la herencia.
- **No romper `unconnected_db`** (`test_base.py:15-17`, parametriza `SqliteDb`/`MysqlDb`): los adaptadores deben seguir instanciándose sin argumentos.

---

### `pyproject.toml` — ratchet de mypy

**Analog:** sí mismo (`pyproject.toml:243-283`), en especial el bloque de cola `:269-283`.

**Entradas asignadas a Fase 5** (`pyproject.toml:276-281`):
```toml
[[tool.mypy.overrides]]
module = [
    ...
    "encino_orm.oracle",               # 2 errores — Fase 2 (DIAL-01/DIAL-02) y Fase 5 (RESL-01)
    "encino_orm.mysql",                # 1 error  — Fase 2 (DIAL-01/DIAL-02) y Fase 5 (RESL-01)
    "encino_orm.mssql",                # 1 error  — Fase 2 (DIAL-01/DIAL-02) y Fase 5 (RESL-01)
    ...
    "encino_orm.base",                 # 1 error  — Fase 5 (RESL-02: plantilla `_with_reconnect`)
]
ignore_errors = true
```

**Precedente de "entrada conservada con causa escrita" (04-04)** (`pyproject.toml:249-256`):
```toml
    # 04-04 (POOL-01…06) intentó retirar esta entrada y NO pudo: quedan 5
    # errores residuales de TIPADO, ajenos a la corrección del pool — 3
    # `var-annotated` … y 2 `override` …
    # `base.py` (fuera del alcance de 04-04) y la convención del repo prohíbe
    # `# type: ignore` inline, así que la entrada sigue con su causa escrita.
    "encino_orm.pool",                 #  5 errores — residual de tipado (no de POOL-01…06)
```

**Convenciones a copiar:**
- Retirar `encino_orm.base`/`oracle`/`mysql`/`mssql` **solo si** `uv run mypy encino_orm` sale limpio; si no, dejar la entrada con la **causa escrita** en el comentario (precedente 04-04, `:249-256`), nunca borrarla en silencio.
- El ratchet solo encoge: no añadir entradas nuevas sin justificación escrita (`pyproject.toml:233-235`).
- Verificación: `uv run mypy encino_orm` + `uv run ruff check .` + `uv run ruff format --check`.

**Lo que NO se copiar:**
- **No `# type: ignore` inline**: el conteo de supresiones en `encino_orm/` es **0** y debe seguir siéndolo; `warn_unused_ignores = true` (`pyproject.toml:222`) lo hace fallar si sobra.
- **No retirar entradas sin medir**: dejar el ratchet mintiendo es peor que conservarlo documentado.
- **No tocar `uv.lock`/dependencias**: la fase **no** añade paquetes (RESEARCH §Standard Stack).

---

### `docs/engines.md` + `CHANGELOG.md` (docs)

**Analog:** `docs/engines.md:138-158` (sección "Implementa la captura del id y el manejo de errores", donde vive `is_lock_error`) y `CHANGELOG.md:9-50` (`[Unreleased]`, con `### Cambiado`/`### Corregido`).

**Estado actual a ampliar** (`docs/engines.md:157-158`):
```markdown
- `is_lock_error(exc)`: opcional; devuelve `True` ante deadlocks/bloqueos
  re-reintentables para que `retry()` funcione.
```

**Convenciones a copiar:**
- Añadir `is_disconnect_error(exc)` junto a `is_lock_error` (`docs/engines.md:157`), con la regla de exclusión mutua y la nota de que el substring solo es refuerzo (MSSQL).
- Documentar la taxonomía pública (`ConnectionLostError`/`OperationalError`/`IntegrityError`/`ProgrammingError`) y que `retry()` sigue viendo el error de lock original.
- Documentar `pre_ping`/`max_connection_lifetime` como kwargs de `connect()` (no del constructor), y el rechazo de `:memory:` en SQLite.
- `CHANGELOG.md`: entrada en `[Unreleased]` con **CAMBIO DE COMPORTAMIENTO** (auto-reconexión + traducción de excepciones + status HTTP 400 por herencia de `QueryError`), siguiendo el estilo de `CHANGELOG.md:29-50` (prosa española, negritas, nota de ownership hacia la Fase 8).
- Prosa española + fenced Python; sin `Args:`/`Returns:` (`CONVENTIONS.md` §Docstrings).

**Lo que NO se copiar:**
- **No olvidar `CHANGELOG.md`**: el Constraint de `PROJECT.md` exige documentar los cambios incompatibles en 0.x.
- **No añadir una allowlist a `filterwarnings`** (`pyproject.toml:56-72`) para callar nada: la auto-reconexión no emite warnings.

---

## Shared Patterns

### Importación diferida / sin dependencias duras
**Fuente:** `oracle.py:84` (`import oracledb` dentro de `connect()`), `context.py:49` (`from .pool import _current_connection` dentro de la función), `base.py:44` (`from .sql import SqlFunctions` dentro de `fn`).
**Aplicar a:** `base.py` (la taxonomía y `_with_reconnect` **no** importan drivers), `_translate_error` por adaptador (usa el módulo del driver ya importado en el adaptador), `is_disconnect_error` (Oracle necesita `self._oracledb`, fijado en `connect()`).
- `exceptions.py` no importa nada; `base.py` importa solo stdlib + `.dialects.identifiers` + `.query` (`base.py:1-10`).

### Clasificación sobre la excepción original + exclusión mutua
**Fuente:** `retry()` (`base.py:103`) clasifica antes de cualquier traducción; `is_lock_error` de los seis.
**Aplicar a:** `_with_reconnect` (`is_disconnect_error`/`is_lock_error` **antes** de traducir), `_translate_exception` (devuelve el original si `is_lock_error`).
- Criterio de éxito 1: cada adaptador clasifica disconnect y **no** misclasifica lock.

### `time.monotonic()` como único reloj
**Fuente:** `pool.py:60,67,77,134,147,174`.
**Aplicar a:** `_connected_at`, `max_connection_lifetime`, tests (monkeypatch).
- Nunca `time.time()`/`datetime.now()`.

### Logging perezoso `%`-style
**Fuente:** `logger = logging.getLogger("encino_orm")` (`base.py:12`, `pool.py:29`) + `_log` por adaptador (`mysql.py:21-29`, `sqlite.py:19-27`).
**Aplicar a:** reconexión, fallo de reconexión, `close()` de `_reconnect`.
- `%`-style, nunca f-strings; **no** loguear `_connect_kwargs` (password).

### Errores: mensajes en español, sin catch-all
**Fuente:** `exceptions.py` + `model/exceptions.py` + `CONVENTIONS.md` §Error Handling.
**Aplicar a:** taxonomía nueva, `_translate_error`, rechazo de `:memory:`.
- `ValueError` con `!r` para argumentos inválidos (`sqlite.py:110`); `NotImplementedError` con mensaje para capacidades opcionales (`base.py:186`).

### Chaining (`raise ... from`)
**Fuente:** `CONVENTIONS.md` §Error Handling: "`raise ... from` chaining is not used; original exceptions are re-raised or skipped".
**Tensión a resolver por el planner:** el sketch de RESEARCH (`05-RESEARCH.md:236-243`) usa `raise self._translate_exception(exc) from exc`. El precedente del repo **no** usa chaining. Decisión: o se mantiene la convención (re-lanzar sin `from`, perdiendo el traceback original) o se adopta `from exc` con una excepción documentada. **Escribirlo explícitamente en el plan.**

### Validación de identificadores y binding
**Fuente:** `check_identifier` (`dialects/identifiers.py`; uso en `base.py:81`, `sqlite.py:121`, `mysql.py:127`); valores siempre ligados vía `Query`.
**Aplicar a:** cualquier SQL nuevo (no hay SQL nuevo en esta fase; la traducción de errores **no** construye SQL ni interpola).

### Fakes deterministas + `monkeypatch`
**Fuente:** `_pool_helpers.py:20-164`, `test_pool_characterization.py:37-150`, `test_d_recommendations.py:157`, `test_migration_reconcile.py:22`.
**Aplicar a:** `test_resilience.py`, `test_resilience_lifetime.py`, extensiones de `test_base.py`/`test_{motor}.py`.
- Dobles a mano; `monkeypatch.setitem(encino_orm.pool._ENGINES, ...)` para engines fake; `monkeypatch.setattr(time, "monotonic", ...)` para el reloj.

### Barrel + `__all__`
**Fuente:** `encino_orm/__init__.py:13-20,41-85`.
**Aplicar a:** exportar `ConnectionLostError`, `OperationalError`, `IntegrityError`, `ProgrammingError` desde el paquete raíz (import block + `__all__`).

---

## No Analog Found

Todos los **ficheros** tienen analog de rol. Dos **comportamientos** son nuevos y quedan gobernados por `05-RESEARCH.md` (no por código existente):

| Behavior | Role | Data Flow | Reason |
|----------|------|-----------|--------|
| Reconexión exactamente-una-vez con guard de transacción (`_with_reconnect`) | controller | request-response | No existe ningún template de reconexión hoy; `retry()` es el análogo más cercano pero reintenta **N** veces y solo lock. Semántica exacta (una sola vez, nunca en tx) fijada por RESEARCH §Pattern 2. |
| Traducción de excepciones de driver → taxonomía de librería | service | transform | No hay precedente de traducción de errores de driver; `install_error_handlers` (`http/errors.py`) es el análogo de **mapeo centralizado**, pero mapea a HTTP, no a excepciones. El mapa por driver está en RESEARCH §Code Examples. |

**Restricciones de la investigación que el planner DEBE respetar:**
1. **`_is_reconnectable` cubre la `ConnectionError` de la librería** cuando `_connected_at is not None` (Pitfall 1 / A1): el camino más común (caída en reposo) **no** lanza error de driver.
2. **`_execute`/`_fetch_*`/`_execute_insert` concretos** (lanzan `NotImplementedError`), **no** `@abstractmethod`: `LockDb`/`LedgerDb` deben seguir instanciándose (Pitfall 10).
3. **SQLite `:memory:` rechaza reconectar** (Pitfall 2).
4. **Lock nunca se traduce ni se reintenta en `_with_reconnect`** (Pitfall 3): `TestD4AutoRetry` debe seguir verde.
5. **`pre_ping` reconecta inmediatamente** si `is_alive()` es False (Pitfall 5).
6. **Oracle: leer `.full_code`**, no solo `.code` (Pitfall 8).
7. **MSSQL: `HY000` mid-query es disconnect** (Pitfall 7).
8. **Sin warnings por operación** (`filterwarnings=["error"]`, Pitfall 9).
9. **Piso Python 3.10**: prohibido `asyncio.Barrier`/`TaskGroup`/`asyncio.timeout` (también en tests).
10. **A2/Open Q1 pendiente de decisión**: si `_with_reconnect` reintenta **escrituras** fuera de transacción. Recomendación de RESEARCH: lecturas reintentan; escrituras reconectan pero **relanzan**. Debe decidirse explícitamente en el plan.
11. **No tocar `pyproject.toml` de dependencias ni `uv.lock`**: la fase no instala paquetes.

---

## Metadata

**Analog search scope:** `encino_orm/` (raíz, `model/`, `http/`), `tests/`, `pyproject.toml`, `docs/engines.md`, `CHANGELOG.md`.
**Files read for extraction:** 20 (`base.py`, `exceptions.py`, `model/exceptions.py`, `sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`, `pool.py`, `http/errors.py`, `__init__.py`, `tests/_pool_helpers.py`, `tests/test_pool_characterization.py`, `tests/test_d_recommendations.py`, `tests/test_migration_reconcile.py`, `tests/test_oracle.py`, `tests/test_base.py`, `tests/conftest.py`, `pyproject.toml`, `docs/engines.md`, `CHANGELOG.md`).
**Pattern extraction date:** 2026-09-18

**Critical downstream reminders for the planner:**
1. **Orden safety-critical:** primero `is_disconnect_error` (RESL-01) y `_connect_kwargs`/`_connected_at`; después `_with_reconnect` (RESL-02); `pre_ping`/lifetime (RESL-03) y taxonomía (RESL-04) al final.
2. **El rename `execute`→`_execute` es el punto de mayor blast radius**: verificar que `LockDb`/`LedgerDb`/`FakeDb` siguen instanciándose y que `PoolDb._run` (`pool.py:456-487`) no necesita cambios.
3. **Clasificar antes de traducir**, y devolver el original cuando `is_lock_error` (no romper `retry()`).
4. **`_is_reconnectable` incluye la `ConnectionError` de librería** (Pitfall 1).
5. **No envolver `exists`/`list_tables`/`paginate`/`migrate`**: ya pasan por wrappers.
6. **`_reconnect` in-place, nunca reasignar el handle del pool** (Fase 4).
7. **Documentar en `CHANGELOG.md`** el cambio de status HTTP 400 por herencia de `QueryError` (A3).
8. **Ratchet mypy**: retirar `base`/`oracle`/`mysql`/`mssql` solo si `uv run mypy encino_orm` sale limpio; si no, causa escrita (precedente 04-04).
