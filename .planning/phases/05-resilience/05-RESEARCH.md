# Phase 5: Resilience - Research

**Researched:** 2026-09-18
**Domain:** Clasificación de errores de desconexión y reconexión segura sobre seis drivers asíncronos (aiosqlite, aiomysql/PyMySQL, asyncpg, aioodbc/pyodbc, oracledb), política `pre_ping`/`max_connection_lifetime` para conexiones directas, y taxonomía pública de errores.
**Confidence:** HIGH en la clasificación real de errores por motor (los seis contenedores están arriba y se **provocaron desconexiones reales** con `KILL`/`pg_terminate_backend`/`ALTER SYSTEM KILL SESSION`, capturando el tipo y los args exactos de cada excepción); HIGH en el mapa del estado actual (código vivo leído con anchors); MEDIUM en la forma final de `_with_reconnect` y de la taxonomía (decisiones de diseño, no hechos); HIGH en que la fase **no necesita dependencias nuevas**.

> **No existe `05-CONTEXT.md`.** La fase no ha pasado por `/gsd-discuss-phase` (el directorio `.planning/phases/05-resilience/` está vacío). Por eso no hay sección `## User Constraints (from CONTEXT.md)`; en su lugar se citan como restricciones vinculantes las decisiones ya bloqueadas en `ROADMAP.md` (Phase 5: goal, 4 criterios de éxito, planes `05-01`…`05-04`) y los Constraints de `PROJECT.md`.

<user_constraints>
## User Constraints (from ROADMAP.md — no CONTEXT.md exists)

### Locked Decisions (ROADMAP Phase 5, líneas 277-299)

- **Goal de la fase:** "Connection loss is classified, handled once, and never silently duplicates a write. Direct (non-pooled) connections survive idle periods, and driver failures surface as library exceptions."
- **Plan `05-01`:** `is_disconnect_error` por adaptador en los seis motores — **RESL-01**.
- **Plan `05-02`:** `Db._with_reconnect` (template method) que reconecta **exactamente una vez** y **solo** cuando `in_transaction()` es falso, estrictamente separado del camino de reintento por lock/deadlock — **RESL-02**.
- **Plan `05-03`:** política `pre_ping` + `max_connection_lifetime` para conexiones directas (no-pool) — **RESL-03**.
- **Plan `05-04`:** taxonomía pública de errores que traduce excepciones de driver a excepciones de la librería — **RESL-04**.
- **Success Criterion 1:** cada uno de los seis adaptadores clasifica una desconexión simulada como disconnect y **no** misclasifica un error de lock/deadlock.
- **Success Criterion 2:** una desconexión **fuera** de transacción reconecta una vez y la operación tiene éxito; la misma desconexión **dentro** de una transacción lanza en vez de reintentar.
- **Success Criterion 3:** las conexiones directas (no-pool) sobreviven a un periodo de inactividad vía `pre_ping` y `max_connection_lifetime`.
- **Success Criterion 4:** las excepciones de driver se traducen a una taxonomía pública documentada.
- **Dependencia dura:** "Depends on: Phase 4 (needs `PooledConnection` + generation counter)". Fase 4 ya está completa (`pool.py:45-77` handle, `:134` generación).
- **Modo:** standard. **Research:** needed (taxonomy boundary + per-driver classification).

### Constraints de PROJECT.md (vinculantes)

- **Contrato de importación diferida:** el núcleo (`base.py`, `exceptions.py`) **no puede** adquirir dependencias duras de las capas opcionales ni de los drivers opcionales. Las clases de excepción de driver (`pyodbc`, `oracledb`, `asyncpg`, `pymysql`, `aiosqlite`) solo pueden importarse **dentro del adaptador** (ya es así hoy).
- **0.x:** los cambios incompatibles se permiten pero **deben** documentarse en `CHANGELOG.md`.
- **Sin regresiones de corrección:** "las optimizaciones no pueden regresar la corrección".
- **Alcance:** sin nuevos motores; sin declarar 1.0.

### the agent's Discretion (deducido; no hay CONTEXT.md)

- Nombres y jerarquía exactos de la taxonomía pública (`ConnectionLostError`/`OperationalError`/`IntegrityError`/`ProgrammingError`) y de quién hereda de quién.
- Firma exacta de `_with_reconnect` (helper con callable vs. wrapper de métodos públicos concretos) y su ubicación.
- Si `pre_ping`/`max_connection_lifetime` se configuran por constructor del adaptador o por `connect(**kwargs)`.
- Semántica exacta de `max_connection_lifetime` (edad de conexión vs. inactividad) y si aplica a `PoolDb`.
- Si se retiran las entradas `encino_orm.base`, `encino_orm.oracle`, `encino_orm.mysql`, `encino_orm.mssql` del ratchet de mypy (`pyproject.toml:261-276`), que están asignadas explícitamente a Fase 5.
- Si el reintento tras reconexión aplica a escrituras o solo a lecturas (ver **Riesgo #2** y Open Questions).

### Deferred Ideas (OUT OF SCOPE)

- **Reciclado de conexiones del pool** (`max_connection_lifetime` para `PoolDb`) → v2 `RELI-03` (`REQUIREMENTS.md:107`). RESL-03 es **solo conexiones directas** (ROADMAP:298).
- Pool auto-reparable como promesa de producto → v2 `RELI-04`.
- Reintento ciego de escrituras arbitrarias → **Out of Scope explícito** (`REQUIREMENTS.md:120`): "Duplica datos; el reintento solo es seguro para errores de lock, no de desconexión".
- Daemon reaper en background → Out of Scope (`REQUIREMENTS.md:122`).
- Wrappers `except Exception` catch-all → Out of Scope (`REQUIREMENTS.md:124`): contradice la taxonomía de errores.
- Sustituir `Filter.raw`/`Query`/`db.fn.*` trust boundaries → Fase 6 (`CFG-05`).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RESL-01 | Cada adaptador clasifica errores de desconexión mediante `is_disconnect_error` | §2: tabla de clasificación por motor **verificada con desconexiones reales** contra los seis contenedores. Hoy `is_lock_error` existe en los seis (`base.py:91-93`, `sqlite.py:54-55`, `mysql.py:66-69`, `postgresql.py:65-73`, `mssql.py:61-63`, `oracle.py:73-75`) pero **no hay `is_disconnect_error`**. |
| RESL-02 | `_with_reconnect` reconecta una sola vez y **solo** cuando no hay transacción abierta | §3: forma recomendada del template method, guard `in_transaction()` verificado contra conexiones muertas reales, interacción con `retry()` (`base.py:95-109`) y con `Model._transactional` (`model.py:438-453`). |
| RESL-03 | Las conexiones directas soportan `pre_ping` y `max_connection_lifetime` | §4: hoy `connect()` no guarda kwargs ni timestamp; los adaptadores pasan `**kwargs` crudos al driver (`mysql.py:72`, `postgresql.py:76`, `mssql.py:96`, `oracle.py:96`). `is_alive()` ya existe en los seis y `PoolDb.acquire` ya lo usa (`pool.py:296`). |
| RESL-04 | Existe una taxonomía pública que traduce excepciones de driver a excepciones de la librería | §5: jerarquía actual mínima (`exceptions.py:1-22`), propuesta compatible, y el punto único de traducción dentro de `_with_reconnect` sin romper `retry()`. |
</phase_requirements>

## Summary

Hoy **ninguna** desconexión se clasifica ni se maneja: el error del driver sale crudo del adaptador. Se verificó provocando desconexiones reales en los seis contenedores:

- **MySQL / MariaDB:** `KILL <id>` → la siguiente sentencia lanza `pymysql.err.OperationalError(2013, 'Lost connection to MySQL server during query')`. Si antes se llama `is_alive()` (`ping(reconnect=False)`, `mysql.py:84`), el ping falla y deja `Connection.closed=True`, con lo que la siguiente sentencia lanza la `ConnectionError` **de la librería** desde `_ensure_connected()` (`mysql.py:112-114`) y el error del driver **nunca se ve**.
- **PostgreSQL:** `pg_terminate_backend` → `asyncpg` marca `is_closed()=True`, así que la siguiente sentencia lanza la `ConnectionError` de la librería (`postgresql.py:121-123`). El error de driver `asyncpg.exceptions.ConnectionDoesNotExistError('connection was closed in the middle of operation')` solo aparece si la conexión muere **en mitad** de una operación. Dentro de una transacción, `is_in_transaction()` sigue devolviendo `True` tras la muerte y `Transaction.rollback()` lanza `InterfaceError`.
- **SQL Server:** `KILL` en mitad de una query → `pyodbc.Error('HY000', '...Connection may have been terminated by the server... (596)')`. `KILL` en reposo con `ConnectRetryCount=0` → `pyodbc.OperationalError('08S01', '...Communication link failure...')`; con el default (`ConnectRetryCount=1`) el driver puede reconectar en silencio (el `@@SPID` cambia). **Ojo:** un clasificador que solo mire SQLSTATE `08xxx` **falla** el caso mid-query (`HY000`).
- **Oracle:** `ALTER SYSTEM KILL SESSION ... IMMEDIATE` → `oracledb.exceptions.DatabaseError` con `args[0].code == 0` y `args[0].full_code == 'DPY-4011'` ("the database or network closed the connection"). El helper actual `_ora_code` (`oracle.py:66-71`) solo lee `.code` → devuelve `0` y **no detectaría** este caso; hay que leer `.full_code`.
- **SQLite:** es embebido; la "desconexión" real es `sqlite3.ProgrammingError('Cannot operate on a closed database.')`. `database is locked`/`busy` es el error de lock que **no** debe clasificarse como desconexión.

Además, `connect()` **no guarda los kwargs** en ningún adaptador (grep de `_connect_kwargs`/`_connected_at` → 0 resultados), así que `_with_reconnect` no puede reconectar hoy: cada adaptador debe persistir `self._connect_kwargs = dict(kwargs)` y `self._connected_at = time.monotonic()`.

**Primary recommendation:** (a) añadir `is_disconnect_error` por adaptador con la tabla de §2, con la regla de exclusión mutua respecto a `is_lock_error`; (b) convertir `execute`/`execute_insert`/`fetch_all`/`fetch_one`/`fetch_many` de `Db` en métodos **concretos** que envuelven implementaciones `_`-prefijadas de cada adaptador con `_with_reconnect` (punto único de clasificación + reconexión + traducción); (c) `_reconnect()` = `close()` + `connect(**self._connect_kwargs)` con guard `_connected_at is not None`, y **rechazo explícito en SQLite `:memory:`** (reconectar crearía una BD vacía); (d) `pre_ping`/`max_connection_lifetime` como kwargs de `connect()` (popped antes de reenviar al driver) con defaults `False`/`None`; (e) taxonomía `ConnectionLostError(ConnectionError)` + `OperationalError`/`IntegrityError`/`ProgrammingError(QueryError)`, y la traducción **no** se aplica a errores de lock para no romper `retry()`.

**Hallazgo que cambia el alcance de RESL-02:** en los seis motores el camino **más común** de desconexión (caída en reposo) no produce una excepción de driver, sino la `ConnectionError` de la librería que lanza `_ensure_connected()` antes de tocar el driver (verificado en MySQL y PostgreSQL). Por tanto `_with_reconnect` debe considerar "reconectable" **también** esa `ConnectionError` cuando el adaptador ya había conectado (`_connected_at is not None`), no solo `is_disconnect_error(exc)`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Clasificación de desconexión (`is_disconnect_error`) | Adaptador (dueño del driver) | — | Solo el adaptador importa su driver y conoce sus excepciones (contrato de importación diferida). |
| Reconexión exactamente-una-vez y guard de transacción (`_with_reconnect`) | `Db` (base, template method) | Adaptador (`_reconnect`, `_connect_kwargs`) | La política es común; el "cómo reconectar" es del adaptador. |
| Traducción de excepciones de driver → librería | `Db` (base, punto único) + `exceptions.py` | Adaptador (`_translate_exception` por driver) | Una sola frontera evita seis `except` divergentes y cumple "no catch-all". |
| `pre_ping` / `max_connection_lifetime` | `Db` (base: estado `_connected_at`, decisión) | Adaptador (`connect` pop de kwargs) | El timestamp y la política son comunes; los kwargs los consume el adaptador. |
| Reintento por lock/deadlock | `Db.retry` (existente, intacto) | Adaptador (`is_lock_error`) | Camino separado y ya probado; `_with_reconnect` **no** debe tocarlo. |
| Salud de conexión (`is_alive`) | Adaptador (ya existe en los seis) | `_with_reconnect` (lo consume) | `is_alive()` es driver-specific; el pool ya lo usa (`pool.py:296`). |

## Standard Stack

### Core
| Library | Version (instalada) | Purpose | Why Standard |
|---------|---------------------|---------|--------------|
| stdlib `time.monotonic` | Python ≥3.10 | `_connected_at`, `max_connection_lifetime` | Ya es el reloj del pool (`pool.py:60,67,77`); inmune a saltos de reloj. |
| stdlib `asyncio` | Python ≥3.10 | Reconexión async | Ya en uso. |
| Drivers existentes: `aiosqlite` 0.22.1, `aiomysql` 0.3.1 + `PyMySQL` 1.2.0, `asyncpg` 0.31.0, `aioodbc` 0.5.0 + `pyodbc` 5.3.0, `oracledb` 4.0.2 | — | Clasificación por tipo/atributos | Ya declarados en `pyproject.toml`; **no se añade ninguno**. `[VERIFIED: importlib.metadata en .venv]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| — | — | — | **Esta fase no requiere dependencias nuevas.** Las pruebas son stdlib + pytest existente. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Clasificación por clase/atributos del driver | `is_disconnect_error` por substring de mensaje en todos los motores | Frágil ante traducciones del driver (los mensajes de ODBC vienen **en español** en este host: "Se ha forzado la interrupción...", verificado). Solo usar substring como **refuerzo** del SQLSTATE en MSSQL. |
| Guardar kwargs en `connect()` | Añadir un `__init__` base con política | `PoolDb._create_connection` construye `self._engine_cls()` sin args (`pool.py:197`) y `create_db` también (`pool.py:568`): un `__init__` con parámetros rompería ambos. `connect(**kwargs)` ya es el punto de paso de ambos. |
| Wrapper concreto en `Db` (recomendado) | Llamadas explícitas a `_with_reconnect` en cada uno de los ~30 puntos de invocación del driver | Más ediciones y fácil olvidar un sitio; el wrapper centraliza clasificación+reconexión+traducción una vez. Ver §3. |
| `Db._reconnect` = `close()` + `connect()` | Reasignar el objeto driver en `PoolDb` | El pool ya tiene generación/reaper (Fase 4); reemplazar el driver invalidaría el handle. Reconectar **in-place** conserva el handle. |

**Installation:**
```bash
# NINGUNA. RESL-01…04 se implementan con stdlib + drivers ya declarados.
# No hay que tocar pyproject.toml ni uv.lock (evita el gate `uv lock --check`).
```

**Version verification:** las seis versiones anteriores se leyeron con `importlib.metadata.version(...)` en `.venv` el 2026-09-18: `PyMySQL 1.2.0`, `aiomysql 0.3.1`, `asyncpg 0.31.0`, `aiosqlite 0.22.1`, `aioodbc 0.5.0`, `pyodbc 5.3.0`, `oracledb 4.0.2` — `[VERIFIED: .venv importlib.metadata]`. Nota: `pymysql.__version__` reporta `2.2.8` (atributo obsoleto/incorrecto de la distribución); la versión real según metadatos es `1.2.0`. No se añaden paquetes.

## Package Legitimacy Audit

> **No aplica gate de legitimidad:** esta fase **no instala ningún paquete nuevo**. Solo usa stdlib y drivers ya presentes en `pyproject.toml`/`uv.lock` desde antes del milestone.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (ninguno nuevo) | — | — | — | — | — | — |

**Packages removed due to slopcheck [SLOP] verdict:** none (no hay paquetes nuevos)
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
        Llamada pública (Model / usuario / PoolDb._run)
                        │
                        ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ Db (base.py) — métodos PÚBLICOS concretos (nuevos)            │
   │   execute / execute_insert / fetch_all / fetch_one / fetch_many
   │        │                                                      │
   │        └─► _with_reconnect(lambda: self._<op>(...))           │
   │              │                                                │
   │              ├─ pre_ping / max_connection_lifetime ───────────┼──► _reconnect()  (RESL-03)
   │              │                                                │
   │              ├─ await fn()  ──────────────────────────────►   │
   │              │        │                                       │
   │              │        └─ _<op>() del adaptador                │
   │              │              └─ _ensure_connected()  ──► ConnectionError (sin conexión)
   │              │              └─ driver.<método>()   ──► excepción de driver
   │              │                                                │
   │              └─ except exc:                                   │
   │                    ├─ is_disconnect_error(exc)? ──NO──► _translate_exception(exc) ► raise
   │                    ├─ in_transaction()?  ──SÍ──► _translate_exception(exc) ► raise  (nunca reintenta)
   │                    ├─ _reconnect()                            │
   │                    └─ await fn()   ◄── EXACTAMENTE UNA VEZ    │
   │                           └─ falla otra vez ──► _translate_exception ► raise
   └──────────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┴────────────────────────────────────────┐
        ▼                                                        ▼
   is_disconnect_error (adaptador)                        is_lock_error (adaptador, intacto)
   ConnectionLostError / OperationalError /               retry() (base.py:95-109)
   IntegrityError / ProgrammingError                     (Model._transactional, model.py:448)
```

### Recommended Project Structure
```text
encino_orm/
├── exceptions.py           # + ConnectionLostError, OperationalError, IntegrityError, ProgrammingError
├── __init__.py             # + exportar la taxonomía nueva (barrel + __all__)
├── base.py                 # + is_disconnect_error default, _with_reconnect, _reconnect,
│                           #   _is_reconnectable, _translate_exception, pre_ping/lifetime,
│                           #   wrappers públicos concretos execute/execute_insert/fetch_*
├── sqlite.py / mysql.py / mariadb.py / postgresql.py / mssql.py / oracle.py
│                           # + is_disconnect_error, _translate_exception, _connect_kwargs,
│                           #   _connected_at, pop de pre_ping/max_connection_lifetime,
│                           #   rename execute→_execute, fetch_*→_fetch_*, execute_insert→_execute_insert
├── mariadb.py              # hereda todo de MysqlDb (no requiere cambios propios)
└── pool.py                 # SIN cambios de comportamiento (RESL-03 no aplica al pool); solo
                            #   verificar que _run sigue funcionando con los wrappers concretos
tests/
├── test_resilience.py              # RESL-01/02/04 unitarios con dobles de driver (sin servidores)
├── test_resilience_lifetime.py     # RESL-03 con monkeypatch de time.monotonic (opcional: fusionar)
├── _resilience_helpers.py          # FakeResilientDb / FakeDriverQueFalla
└── test_base.py                    # + taxonomía y compatibilidad de herencia
```

### Pattern 1: `is_disconnect_error` por adaptador (RESL-01)
**What:** hook booleano análogo a `is_lock_error`, que clasifica el error del driver como pérdida de conexión.
**When to use:** siempre; lo consume `_with_reconnect`. **Nunca** puede solaparse con `is_lock_error`.
**Example (MySQL, verificado):**
```python
# Source: mysql.py:66-69 (is_lock_error) + sonda real: KILL -> OperationalError(2013, ...)
_DISCONNECT_ERRNOS = (2006, 2013, 2055)  # gone away / lost during query / lost at handshake

def is_disconnect_error(self, exc: Exception) -> bool:
    if isinstance(exc, aiomysql.InterfaceError):
        return True
    if isinstance(exc, aiomysql.OperationalError):
        errno = exc.args[0] if exc.args else None
        return errno in _DISCONNECT_ERRNOS     # 1213/1205 quedan FUERA (lock)
    return False
```
```python
# Source: oracle.py:66-79 + sonda real: kill session -> DatabaseError full_code='DPY-4011', code=0
_ORA_DISCONNECT_CODES = (28, 1012, 1080, 2396, 3113, 3114, 3135, 12537, 12541, 12547)
_ORA_DISCONNECT_DPY = ("DPY-4011", "DPY-6005", "DPY-6001", "DPY-6003")

def is_disconnect_error(self, exc: Exception) -> bool:
    if isinstance(exc, self._oracledb.InterfaceError):     # `_oracledb` se fija en connect()
        return True
    err = exc.args[0] if getattr(exc, "args", None) else None
    if getattr(err, "code", None) in _ORA_DISCONNECT_CODES:
        return True
    return getattr(err, "full_code", None) in _ORA_DISCONNECT_DPY
```

### Pattern 2: `_with_reconnect` como template method (RESL-02)
**What:** `Db` define métodos públicos **concretos** que envuelven implementaciones privadas del adaptador; el wrapper clasifica, aplica el guard de transacción, reconecta **una vez** y traduce.
**When to use:** en `execute`/`execute_insert`/`fetch_all`/`fetch_one`/`fetch_many`. **No** en `is_alive`/`in_transaction`/`commit`/`rollback` (usados por el guard) ni en `migrate` (que ya usa las ops envueltas internamente).
**Example:**
```python
# base.py — nuevo. `_execute`/`_fetch_*` son las implementaciones actuales renombradas.
async def execute(self, qry: Query):
    return await self._with_reconnect(lambda: self._execute(qry))

async def _with_reconnect(self, fn):
    if self._should_recycle():
        await self._reconnect()
    try:
        return await fn()
    except Exception as exc:
        if not self._is_reconnectable(exc):
            raise self._translate_exception(exc) from exc
        if await self._in_transaction_guarded():
            raise self._translate_exception(exc) from exc   # dentro de tx: NUNCA reintenta
        await self._reconnect()
        try:
            return await fn()                                # EXACTAMENTE UNA VEZ
        except Exception as exc2:
            raise self._translate_exception(exc2) from exc2
```

### Pattern 3: `pre_ping` + `max_connection_lifetime` (RESL-03)
**What:** antes de cada operación, si `pre_ping` está activo y `is_alive()` es falso, o si la conexión supera su vida máxima, se reconecta proactivamente.
**When to use:** conexiones directas. Opt-in (`pre_ping=False`, `max_connection_lifetime=None` por defecto).
**Example:**
```python
# base.py — el reloj es time.monotonic (mismo criterio que pool.py:60)
def _should_recycle(self) -> bool:
    if self._connected_at is None:          # nunca conectado: no hay nada que reciclar
        return False
    if self.max_connection_lifetime is not None:
        if time.monotonic() - self._connected_at >= self.max_connection_lifetime:
            return True
    return False

async def _pre_ping_ok(self) -> bool:
    return (not self.pre_ping) or await self.is_alive()
```

### Anti-Patterns to Avoid
- **Reconectar dentro de una transacción:** un write pudo llegar al servidor antes de morir el socket; reintentar duplica. Guard obligatorio `in_transaction()`.
- **Clasificar por substring genérico en todos los motores:** los mensajes de ODBC vienen localizados (verificado en español en este host). El tipo/SQLSTATE es la fuente primaria.
- **Hacer `RETURNING`/`execute` abstractos y renombrar a `_execute` sin más:** rompería los dobles de test que **heredan** de `Db`. Mantener `_execute` como método **concreto** que lanza `NotImplementedError` (no `@abstractmethod`) para que las subclases de test que sobreescriben `execute` sigan funcionando sin cambios.
- **Reconectar SQLite `:memory:`:** crea una base vacía → pérdida silenciosa de datos. Debe rechazarse explícitamente.
- **Traducir los errores de lock:** si `_translate_exception` convierte un `OperationalError(1213)` en `OperationalError` de la librería, `retry()` (`base.py:103`) deja de reconocerlo. La traducción debe **devolver el original** cuando `is_lock_error(exc)` es True.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Clasificación de desconexión | Un `except Exception` genérico que reintente todo | `is_disconnect_error` por driver + `is_lock_error` separados | Un catch-all oculta fallos reales y está **explícitamente** fuera de alcance (`REQUIREMENTS.md:124`). |
| Traducción de errores | `try/except` por método en los seis adaptadores | Un único `_translate_exception` en `Db` invocado desde `_with_reconnect` | Seis copias divergen; el proyecto ya centralizó el warning de `last_id` por el mismo motivo (`base.py:15-26`). |
| Reloj de vida de conexión | `datetime.now()`/`time.time()` | `time.monotonic()` | Ya es el criterio del pool (`pool.py:60`); inmune a cambios de reloj. |
| Detección de transacción abierta | Un flag nuevo por adaptador | `await self.in_transaction()` existente (por driver) | Cada driver ya lo implementa correctamente (`sqlite.py:82-85`, `mysql.py:89-92`, `postgresql.py:93-96`, `mssql.py:120-121`, `oracle.py:120-121`). |
| Sonda de salud | Un `SELECT 1` ad-hoc en `_with_reconnect` | `await self.is_alive()` | Ya existe en los seis y ya lo usa el pool (`pool.py:296`). |
| Reintento con backoff | Un bucle nuevo en `_with_reconnect` | `retry()` existente para lock; `_with_reconnect` NO hace backoff (un solo intento) | Dos bucles se pisan (ver Pitfall 3). |

**Key insight:** el trabajo hecho a mano a evitar es **la detección de "conexión muerta" por mensaje de texto**. Los seis drivers ya exponen tipos/atributos estructurados (`args[0]` errno, SQLSTATE, `.code`/`.full_code`, clase de excepción); el mensaje solo se usa como **refuerzo** donde el SQLSTATE es genérico (`HY000` de MSSQL).

## Runtime State Inventory

> Fase de **cambio de comportamiento con cambio de contrato de errores** (nuevas excepciones públicas + auto-reconexión). No es un rename, pero cambia el estado observable de procesos vivos y artefactos versionados.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Ninguno — la resiliencia es estado en memoria del proceso (`_connected_at`, `_connect_kwargs`). | Ninguna migración. |
| Live service config | Ninguno — no hay configuración externa que embeba nombres. Las sesiones de BD se reciclan por reconnect. | Ninguna. |
| OS-registered state | Ninguno — sin tareas programadas ni servicios. | Ninguna. |
| Secrets/env vars | Ninguno — las `ENCINO_ORM_*` son de tests y no cambian. Los kwargs de conexión se guardan **en memoria** (`_connect_kwargs`), no en disco. | Ninguna. Nota de seguridad: no loguear `_connect_kwargs` (contienen password); usar `%r` del adaptador, no del dict. |
| Build artifacts | Ninguno — no se tocan `pyproject.toml`/`uv.lock`. | Ninguna. |
| Configuración de gates | `pyproject.toml:261-276` (ratchet mypy) asigna a Fase 5: `encino_orm.base` (1 error), `encino_orm.oracle` (2), `encino_orm.mysql` (1), `encino_orm.mssql` (1). | Retirar esas entradas si `uv run mypy encino_orm` sale limpio; si no, dejar la causa escrita. |
| Documentación | `docs/engines.md:157-158` describe `is_lock_error`; falta `is_disconnect_error`. No hay página de errores en `mkdocs.yml:51-83`. | Actualizar `docs/engines.md` y añadir la taxonomía a `docs/engines.md` o `docs/reference/db.md`; entrada en `CHANGELOG.md [Unreleased]`. |
| Snapshots/golden | `tests/__snapshots__/test_sql_snapshots.ambr` y golden strings de `test_dialect_builders.py` pinean SQL; **el rename `execute`→`_execute` no toca SQL**. | Ninguna regeneración esperada; verificar que no cambian. |

**Canonical question:** *después de cambiar el código, ¿qué sistemas en runtime siguen con el estado viejo?* → Ninguno en runtime (la resiliencia es efímera). Lo que sobrevive son los **artefactos versionados**: el ratchet de mypy, la documentación de `docs/engines.md` y el `CHANGELOG.md`.

## Common Pitfalls

### Pitfall 1: El camino más común de desconexión NO lanza excepción de driver
**What goes wrong:** se implementa `_with_reconnect` clasificando solo `is_disconnect_error(exc)`, pero una caída en reposo en MySQL/PostgreSQL/MariaDB hace que `_ensure_connected()` lance la `ConnectionError` de la librería **antes** de tocar el driver, así que nunca se reconecta.
**Why it happens:** `is_connected`/`_ensure_connected` consultan el estado del driver (`mysql.py:64,113`, `postgresql.py:63,122`); asyncpg marca `is_closed()` y aiomysql marca `closed` cuando el socket muere.
**How to avoid:** `_is_reconnectable(exc)` debe devolver True para `is_disconnect_error(exc)` **o** `isinstance(exc, ConnectionError) and self._connected_at is not None`.
**Warning signs:** un test con `ConnectionError("No hay conexión activa...")` no reconecta; solo el test con `OperationalError(2013)` pasa.

### Pitfall 2: SQLite `:memory:` + reconnect = pérdida silenciosa de datos
**What goes wrong:** `_reconnect()` sobre una BD en memoria ejecuta `close()` + `connect(database=":memory:")` → base **nueva y vacía**; todas las tablas desaparecen sin error.
**Why it happens:** `SqliteDb.connect` usa `kwargs.get("database", ":memory:")` (`sqlite.py:58`).
**How to avoid:** `SqliteDb._reconnect()` debe lanzar `ConnectionLostError` (o `ValueError`) cuando `self._database == ":memory:"`; documentarlo.
**Warning signs:** un test de reconnect SQLite que pasa de 1 fila a 0.

### Pitfall 3: Doble reintento / enmascaramiento entre `retry()` y `_with_reconnect`
**What goes wrong:** un error de lock se traduce a `OperationalError` de la librería y `retry()` deja de reconocerlo (`is_lock_error` mira el tipo/args del driver), con lo que se pierde el reintento por deadlock. O al revés: `_with_reconnect` reintenta un lock.
**Why it happens:** `retry()` clasifica la excepción que recibe (`base.py:103`); si la traducción la sustituye, el original se pierde.
**How to avoid:** (i) `is_disconnect_error` e `is_lock_error` **mutuamente excluyentes** (criterio de éxito 1); (ii) `_translate_exception` devuelve `exc` sin traducir cuando `is_lock_error(exc)` es True; (iii) `_with_reconnect` nunca reintenta lock.
**Warning signs:** `TestD4AutoRetry` (`tests/test_d_recommendations.py:154-245`) rojo; un deadlock deja de reintentar.

### Pitfall 4: `in_transaction()` en MSSQL/Oracle es conservador tras un SELECT
**What goes wrong:** se espera que `_with_reconnect` reconecte tras una lectura, pero en MSSQL `_in_tx=True` desde cualquier `fetch_*` (`mssql.py:309,324,344`) y en Oracle desde `execute` (`oracle.py:260,296`). El guard ve "transacción abierta" y no reconecta.
**Why it happens:** el flag modela "hay una transacción abierta" (correcto en SQL Server: un SELECT abre transacción implícita), no "hay una escritura sin confirmar".
**How to avoid:** aceptarlo como comportamiento **conservador** (nunca duplica escrituras) y documentarlo; el criterio de éxito 2 se prueba con un doble cuyo `in_transaction()` devuelve False/True explícitamente.
**Warning signs:** un test de reconnect MSSQL tras un `fetch_all` no reconecta.

### Pitfall 5: `is_alive()` (ping) puede cerrar la conexión antes de reconectar
**What goes wrong:** con `pre_ping=True`, `aiomysql.ping(reconnect=False)` sobre una conexión muerta devuelve False **y deja `closed=True`** (verificado); la siguiente operación lanza `ConnectionError` de la librería. Si `pre_ping` no va seguido de `_reconnect()`, la conexión queda inutilizable.
**Why it happens:** `MysqlDb.is_alive` (`mysql.py:80-87`) no reabre (`reconnect=False`).
**How to avoid:** el chequeo de `pre_ping` en `_with_reconnect` debe **reconectar inmediatamente** cuando `is_alive()` es False (no solo anotar el fallo).
**Warning signs:** `is_alive()` False y la operación siguiente falla con `ConnectionError` pese a `pre_ping=True`.

### Pitfall 6: `close()` sobre una conexión muerta
**What goes wrong:** se asume que `_reconnect()` = `close()`+`connect()` puede fallar en el `close()`.
**Why it happens:** drivers suelen lanzar al cerrar conexiones rotas.
**How to avoid:** **verificado**: `close()` sobre conexiones muertas de PostgreSQL, MySQL y Oracle **no lanza** (devuelve OK y deja `_connection=None`). Aun así, envolver `close()` en `try/except` dentro de `_reconnect` es defensa barata.
**Warning signs:** `_reconnect` lanza en el `close()` y deja `_connection` a medio limpiar.

### Pitfall 7: `HY000` en MSSQL no es SQLSTATE `08xxx`
**What goes wrong:** el clasificador MSSQL solo mira `args[0].startswith("08")` y **falla** el caso mid-query (verificado: `pyodbc.Error('HY000', '...Connection may have been terminated by the server... (596)')`).
**Why it happens:** el driver ODBC 18 reporta la sesión matada en mitad de query como `HY000` genérico.
**How to avoid:** aceptar `08xxx` **o** (`HY000`/`40001` no-lock y mensaje con `"Communication link failure"`, `"terminated by the server"`, `"session is in the kill state"`).
**Warning signs:** el test de disconnect MSSQL con `HY000` da False.

### Pitfall 8: `_ora_code` no ve `full_code` (DPY-4011 tiene `code == 0`)
**What goes wrong:** `is_disconnect_error` de Oracle usa `self._ora_code(exc)` (que lee `.code`) y **nunca** detecta `DPY-4011`, la firma real de una sesión matada.
**Why it happens:** `_ora_code` (`oracle.py:66-71`) solo lee `err.code`; verificado que el error real trae `code=0`, `full_code='DPY-4011'`.
**How to avoid:** leer también `getattr(err, "full_code", None)`.
**Warning signs:** test Oracle con `_FakeError(code=0)` + `full_code='DPY-4011'` da False.

### Pitfall 9: `filterwarnings = ["error"]` y `DeprecationWarning`s de comportamiento
**What goes wrong:** si la auto-reconexión se acompaña de un `DeprecationWarning` (p. ej. "reconnect implícito deprecado"), cada operación bajo `filterwarnings=["error"]` (`pyproject.toml:62-63`) tumba la suite.
**Why it happens:** el proyecto convierte cualquier warning en error.
**How to avoid:** **no** emitir warnings por operación; la auto-reconexión es un cambio de comportamiento documentado en `CHANGELOG.md`, no un warning de runtime. Si se quisiera avisar, solo en el constructor/`connect`, nunca en el camino caliente.
**Warning signs:** fallos masivos con `DeprecationWarning` en tests de reconnect.

### Pitfall 10: El rename `execute`→`_execute` rompe dobles que heredan de `Db`
**What goes wrong:** al hacer `_execute` `@abstractmethod`, `LockDb` (`test_d_recommendations.py:157`) y `LedgerDb` (`test_migration_reconcile.py:22`) dejan de ser instanciables.
**Why it happens:** el ABC exige implementar todo abstractmethod.
**How to avoid:** `_execute`/`_fetch_*`/`_execute_insert` deben ser métodos **concretos** que lanzan `NotImplementedError`, no abstractos; las subclases de test que sobreescriben el método público siguen funcionando sin cambios.
**Warning signs:** `TypeError: Can't instantiate abstract class LockDb`.

## Code Examples

### Estado actual, anclado (para el planner)
```python
# base.py:91-109 — los dos caminos actuales (solo lock; NO hay disconnect)
def is_lock_error(self, exc: Exception) -> bool:
    return False

async def retry(self, coro, tries: int | None = None):
    max_tries = tries if tries is not None else self.MAX_TRIES
    for attempt in range(max_tries):
        try:
            return await coro()
        except Exception as exc:
            if not self.is_lock_error(exc):   # <-- clasificación sobre el tipo ORIGINAL
                raise
            ...
            await self.wait()
    raise last_exc

# base.py:60-67 — transacción base (PostgreSQL la sobreescribe, postgresql.py:98-101)
@asynccontextmanager
async def transaction(self):
    try:
        yield
        await self.commit()
    except Exception:
        await self.rollback()
        raise

# model/model.py:441-448 — las escrituras del Model van SIEMPRE dentro de transaction()
async def attempt():
    async with self._get_db().transaction():
        result = await fn()
        ...
result = await self._get_db().retry(attempt)   # <-- retry() envuelve a la transacción
```

### Dónde muere hoy una desconexión (sin clasificar)
```python
# mysql.py:190-202 — sin `except`: el error del driver sube tal cual
async def execute(self, qry: Query) -> int:
    self._ensure_connected()                    # puede lanzar ConnectionError (mysql.py:112-114)
    cursor = await self._connection.cursor(aiomysql.DictCursor)
    try:
        await cursor.execute(sql, values)       # puede lanzar OperationalError(2013) si el socket murió
        ...
# postgresql.py:197-203 / mssql.py:235-263 / oracle.py:240-268: mismo patrón.
# mssql.py:250-253 y oracle.py:256-259 solo capturan para `ignore_duplicated`, no traducen.
```

### Clasificación por motor — valores verificados con sondas reales
```text
# Sonda 2026-09-18 contra los seis contenedores de docker-compose.yml (todos "Up").
#
# MySQL 3306 / MariaDB 3307  (KILL <connection_id>):
#   pymysql.err.OperationalError(2013, 'Lost connection to MySQL server during query')
#   -> is_disconnect_error: errno in (2006, 2013, 2055) | InterfaceError
#   -> NO lock: 1213 (deadlock) / 1205 (lock wait timeout)
#   -> is_alive() (ping) sobre muerta: False y deja Connection.closed=True
#
# PostgreSQL 5432  (pg_terminate_backend):
#   idle  -> asyncpg.ConnectionDoesNotExistError('connection was closed in the middle of operation')
#            (pero `is_closed()` ya True -> el siguiente op lanza la ConnectionError de la librería)
#   in-tx -> asyncpg.exceptions._base.InterfaceError('connection is closed');
#            is_in_transaction() sigue True; Transaction.rollback() lanza InterfaceError
#   -> is_disconnect_error: ConnectionDoesNotExistError | ConnectionFailureError | InterfaceError
#   -> NO lock: DeadlockDetectedError / SerializationError / LockNotAvailableError
#   -> NO disconnect: InvalidCachedStatementError (invalidación de statement cache, NO pérdida de conexión)
#
# MSSQL 1433  (KILL <spid>):
#   mid-query -> pyodbc.Error('HY000', '...Connection may have been terminated by the server... (596)')
#   idle      -> pyodbc.OperationalError('08S01', '...Communication link failure...')
#   -> is_disconnect_error: args[0].startswith('08') OR (HY000 + substring de arriba)
#   -> NO lock: 1205/1222 (is_lock_error ya los detecta por _native_code, mssql.py:55-63)
#
# Oracle 1521  (ALTER SYSTEM KILL SESSION 'sid,serial#' IMMEDIATE):
#   oracledb.exceptions.DatabaseError(args=(<oracledb.errors._Error>,))
#     args[0].code == 0, args[0].full_code == 'DPY-4011', message 'the database or network closed the connection'
#   -> is_disconnect_error: code in (28,1012,1080,2396,3113,3114,3135,12537,12541,12547)
#                           | full_code in ('DPY-4011','DPY-6005',...) | InterfaceError
#   -> NO lock: ORA-00060/00054/08177 (oracle.py:73-75)
#
# SQLite (embebido; sonda con sqlite3 en su hilo):
#   sqlite3.ProgrammingError('Cannot operate on a closed database.')
#   -> is_disconnect_error: ProgrammingError con ese mensaje | OperationalError 'disk I/O error'
#                           | 'unable to open database file'
#   -> NO lock: OperationalError 'database is locked' / 'database table is locked' / 'busy'
```

### Taxonomía propuesta (RESL-04)
```python
# encino_orm/exceptions.py — aditivo; las existentes NO cambian de nombre ni de herencia base
class EncinoOrmError(Exception): ...
class ConnectionError(EncinoOrmError): ...            # existente
class ConnectionLostError(ConnectionError): ...       # NUEVA (RESL-01/02)
class QueryError(EncinoOrmError): ...                 # existente
class OperationalError(QueryError): ...               # NUEVA
class IntegrityError(QueryError): ...                 # NUEVA
class ProgrammingError(QueryError): ...               # NUEVA
class UnsupportedEngineError(EncinoOrmError): ...     # existente
class MigrationError(EncinoOrmError): ...             # existente
class PoolExhaustedError(EncinoOrmError): ...         # existente

# Punto único de traducción (base.py). NO traduce lock (retry() necesita el original):
def _translate_exception(self, exc: Exception) -> Exception:
    if self.is_lock_error(exc):
        return exc
    return self._translate_error(exc)     # hook por adaptador; default: OperationalError(str(exc))
```

```text
# Mapeo por driver -> taxonomía (recomendado)
# SQLite     : IntegrityError -> IntegrityError; ProgrammingError -> ProgrammingError;
#              OperationalError (no-lock) -> OperationalError; DatabaseError -> OperationalError
# MySQL/Maria : IntegrityError -> IntegrityError; OperationalError(1213/1205) -> OperationalError (lock, sin traducir);
#              OperationalError(otros) -> OperationalError; ProgrammingError -> ProgrammingError;
#              InterfaceError -> ConnectionLostError
# PostgreSQL : IntegrityConstraintViolationError (+) -> IntegrityError; PostgresConnectionError/InterfaceError
#              -> ConnectionLostError; SyntaxError/UndefinedTable/... -> ProgrammingError;
#              PostgresError (resto) -> OperationalError
# MSSQL      : is_unique_violation (mssql.py:65-71) -> IntegrityError; 08xxx/HY000-disconnect
#              -> ConnectionLostError; ProgrammingError -> ProgrammingError; resto -> OperationalError
# Oracle     : ORA-00001/02290/02291/02292/01400 -> IntegrityError; disconnect (ver §2)
#              -> ConnectionLostError; ORA-00904/00942/01722/... -> ProgrammingError; resto -> OperationalError
```

### Configuración de `pre_ping`/`max_connection_lifetime` (RESL-03)
```python
# base.py — atributos de clase con default; se fijan por instancia en connect()
class Db(ABC):
    pre_ping: bool = False
    max_connection_lifetime: float | None = None

    def _resilience_opts(self, kwargs: dict) -> dict:
        """Extrae las opciones de resiliencia ANTES de reenviar kwargs al driver."""
        self.pre_ping = bool(kwargs.pop("pre_ping", self.pre_ping))
        self.max_connection_lifetime = kwargs.pop(
            "max_connection_lifetime", self.max_connection_lifetime
        )
        return kwargs

# En cada adaptador, al principio de connect():
#   kwargs = self._resilience_opts(dict(kwargs))
#   self._connect_kwargs = dict(kwargs)          # para _reconnect()
#   self._connected_at = time.monotonic()        # tras conectar con éxito
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Una desconexión sale cruda del driver | Se clasifica (`is_disconnect_error`), se maneja una vez (`_with_reconnect`) y se traduce (taxonomía) | Fase 5 | Los fallos de red dejan de ser errores de driver opacos para el usuario. |
| Solo `is_lock_error` + `retry()` | Dos caminos separados: `retry()` (lock, con backoff) y `_with_reconnect()` (disconnect, un intento) | Fase 5 | No se reintenta una escritura ambigua. |
| Conexión directa: si el socket muere, hay que reconectar a mano (`CONCERNS.md:178-181`) | `pre_ping`/`max_connection_lifetime` opcionales | Fase 5 | Supervivencia a periodos de inactividad. |
| Errores del driver sin taxonomía pública | `ConnectionLostError`/`OperationalError`/`IntegrityError`/`ProgrammingError` | Fase 5 | El llamador puede distinguir sin importar el driver. |
| SQLAlchemy: `pool_pre_ping` no recupera caídas a mitad de transacción | Mismo principio: reconectar solo fuera de transacción | Fase 5 (adoptado) | Seguridad frente a duplicados. |

**Deprecated/outdated:**
- `.planning/codebase/CONCERNS.md:178-181` ("No reconnect for direct (non-pool) connections... callers must reconnect manually"): obsoleto tras RESL-02/03.
- `docs/engines.md:157-158` (solo documenta `is_lock_error`): debe documentar `is_disconnect_error` y la taxonomía.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `_with_reconnect` debe considerar reconectable también la `ConnectionError` de la librería que lanza `_ensure_connected()` (no solo `is_disconnect_error`), cuando `_connected_at is not None`. | §2, Pitfall 1 | **Alto:** sin esto, el camino más común (caída en reposo) no reconecta y el criterio 2 podría parecer cumplirse solo con dobles artificiales. Confirmar. |
| A2 | El reintento tras reconexión se aplica a **todas** las ops envueltas (lecturas y escrituras) fuera de transacción, aceptando que un write ambiguo podría duplicarse. Alternativa conservadora: no reintentar escrituras. | §3, Riesgo #2 | **Alto:** el goal dice "never silently duplicates a write" y `REQUIREMENTS.md:120` prohíbe el "reintento ciego de escrituras arbitrarias". Hay que decidir explícitamente. Recomendación: lecturas reintentan; escrituras reconectan pero **relanzan** (sin segundo intento). Confirmar. |
| A3 | La taxonomía nueva hereda de `QueryError` (`OperationalError`/`IntegrityError`/`ProgrammingError`), lo que hace que el handler HTTP (`http/errors.py:20-22`) las mapee a **400** en vez de 500. | §5 | Medio: cambia el status HTTP de errores que hoy escapan como 500. Es una mejora, pero es un cambio de comportamiento que debe ir al CHANGELOG. |
| A4 | `pre_ping`/`max_connection_lifetime` se pasan por `connect(**kwargs)` (pop antes del driver), no por constructor. | §4 | Medio: `SqliteDb(pre_ping=True)` no funcionaría; el usuario tendría que usar `db.connect(database=..., pre_ping=True)` o `create_db("sqlite", pre_ping=True)`. Confirmar la ergonomía deseada. |
| A5 | `max_connection_lifetime` mide **edad de conexión** (`time.monotonic() - _connected_at`), no inactividad. | §4 | Bajo: es la semántica de `pool_recycle` de SQLAlchemy; la inactividad ya la cubre el reaper del pool (Fase 4). |
| A6 | `PoolDb` **no** implementa `max_connection_lifetime` (es RELI-03, v2); si un usuario pasa la opción a un pool, se aplica por conexión física vía `connect()`. | §4, Open Q3 | Bajo-medio: podría sorprender; documentar. |
| A7 | La traducción de excepciones es un **cambio de comportamiento** para quien captura excepciones de driver; se documenta en `CHANGELOG.md` y se acepta por ser 0.x. | §5 | Bajo: el contrato de importación diferida hace que el usuario nunca deba importar el driver. |

## Open Questions (RESOLVED)

> Todas resueltas por los planes `05-01`…`05-04`. Se conserva el texto original y se añade `RESUELTO:` con el plan/tarea que lo cierra.

1. **¿`_with_reconnect` reintenta escrituras fuera de transacción?**
   - What we know: el goal dice "never silently duplicates a write"; `REQUIREMENTS.md:120` prohíbe el reintento ciego de escrituras. `Model.insert/update/delete/upsert` van **siempre** dentro de `transaction()` (`model.py:441-448,682-686`), así que no se ven afectados.
   - What's unclear: una escritura cruda `await db.execute(INSERT)` fuera de transacción (PostgreSQL autocommit) que muere mid-statement es ambigua.
   - Recommendation: `_with_reconnect` reintenta **solo lecturas** (`fetch_*`); para escrituras (`execute`/`execute_insert`) reconecta pero **relanza** la excepción traducida. Se implementa con un flag `retry=True/False` por método. Confirmar en discuss.
   - **RESUELTO — `05-02` (Tasks 1 y 3):** política A2 de tres vías. `retry=True` para lecturas; `retry=False` para escrituras, con la excepción `OrmConnectionError` (pre-ejecución: la sentencia nunca llegó al driver → se ejecuta) frente a la desconexión de driver mid-statement (reconecta y **relanza**, no re-ejecuta). Documentado en el docstring de `_with_reconnect` y en el CHANGELOG (`05-04`).

2. **¿`pre_ping` corre en cada operación o solo tras inactividad?**
   - What we know: en conexiones directas no hay "checkout"; SQLAlchemy corre pre-ping en checkout.
   - What's unclear: el coste (un round-trip extra por query).
   - Recommendation: por operación, opt-in (`pre_ping=False` default), documentando el coste. Alternativa: `pre_ping_idle` que solo sondea si `now - last_used > umbral`.
   - **RESUELTO — `05-03` (Tasks 1 y 3):** por operación, opt-in con default `False`; `_maybe_recycle()` en `_with_reconnect`; el test caracteriza que sin opt-in NO se llama `is_alive()` (contador `is_alive_calls`). La variante `pre_ping_idle` queda fuera de alcance.

3. **¿`PoolDb` debe exponer/rechazar `pre_ping`/`max_connection_lifetime`?**
   - What we know: RELI-03 (reciclado del pool) es v2; RESL-03 es solo directas.
   - Recommendation: permitir `pre_ping` (beneficio inmediato, ya usa `is_alive()` en `acquire`) y documentar `max_connection_lifetime` como "por conexión física"; el reciclado a nivel de pool queda para v2.
   - **RESUELTO — `05-03` (Task 2) + A6:** las opciones llegan a cada conexión FÍSICA vía `PoolDb(..., **conn_kwargs)` → `db.connect(**self._conn_kwargs)`; `pool.py` NO se toca (`git diff --stat encino_orm/pool.py` vacío). El reciclado a nivel de pool es `RELI-03` (v2).

4. **¿Retirar las entradas del ratchet de mypy asignadas a Fase 5?**
   - What we know: `pyproject.toml:261-276` asigna `base`/`oracle`/`mysql`/`mssql` a Fase 5.
   - Recommendation: intentar retirarlas; si quedan errores de tipado ajenos, dejar la causa escrita (como hizo 04-04 con `encino_orm.pool`).
   - **RESUELTO — `05-04` (Task 3):** se miden retirando el bloque de overrides; los residuales en alcance (`base:109`, `oracle:263/299`, `mysql:69`) se arreglan sin `# type: ignore`; `mssql` se mide (no se asume 0, W7); si queda un residual fuera de alcance se restaura la entrada con la causa escrita (precedente 04-04). `encino_orm.pool` no se toca.

5. **¿`ConnectionLostError` o `DisconnectError`?**
   - Recommendation: `ConnectionLostError` (hereda de `ConnectionError`, así `except ConnectionError` sigue funcionando).
   - **RESUELTO — `05-04` (Task 1):** `ConnectionLostError(ConnectionError)`; test de jerarquía y de compatibilidad de `except` en `test_base.py` (`05-04` Task 2).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (local) | Todo | ✓ | **3.13.7** (`.venv`) | Piso real de librería: 3.10 (`requires-python`, ruff `target-version`, mypy `python_version`). Ver nota. |
| `uv` | Build/test | ✓ | 0.12.15 (`.venv/pyvenv.cfg`) | — |
| `aiosqlite` | SQLite | ✓ | 0.22.1 | — |
| `aiomysql` + `PyMySQL` | MySQL/MariaDB | ✓ | 0.3.1 / 1.2.0 | — |
| `asyncpg` | PostgreSQL | ✓ | 0.31.0 | — |
| `aioodbc` + `pyodbc` | MSSQL | ✓ | 0.5.0 / 5.3.0 | ODBC Driver 18 presente (sondas exitosas) |
| `oracledb` | Oracle | ✓ | 4.0.2 | — |
| Docker + 6 contenedores | Sondas de integración | ✓ | MySQL 8.0, MariaDB 11, PostgreSQL 16, MSSQL 2022, Oracle XE 21, Redis | Los tests unitarios de la fase **no** los necesitan. |
| `pytest` / `pytest-asyncio` / `pytest-timeout` / `pytest-repeat` | Tests | ✓ | 9.1.1 / 1.4.0 / 2.4.0 / 0.9.4 | — |

**Missing dependencies with no fallback:** ninguna.

**Missing dependencies with fallback:** ninguna.

**Nota de entorno (corrección factual):** `AGENTS.md`/`STACK.md` afirman que el venv local es CPython **3.10.18**; el `.venv` real es **3.13.7** (`pyvenv.cfg`). Las sondas se corrieron en 3.13.7. El piso 3.10 se mantiene como restricción de código (CI matriz 3.10–3.13; `ruff target-version = "py310"`; `mypy python_version = "3.10"`), así que **no** usar `asyncio.timeout`/`TaskGroup`/`except*` (Research Correction #4). Los tests nuevos deben pasar en 3.10.

## Validation Architecture

> `workflow.nyquist_validation = true` en `.planning/config.json:19` → sección incluida.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.1.1 + `pytest-asyncio` 1.4.0 (`asyncio_mode="auto"`, ambos loop scopes `function`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (líneas 41-90) |
| Quick run command | `uv run pytest tests/test_resilience.py -q` |
| Full suite command | `uv run pytest -q -m "not optional_engine"` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESL-01 | Los 6 adaptadores clasifican un disconnect y **no** un lock | unit (dobles de excepción construidos con firmas reales) | `uv run pytest tests/test_resilience.py -q -k disconnect` | ❌ Wave 0 |
| RESL-02 | Disconnect fuera de tx reconecta 1 vez y la op triunfa; dentro de tx lanza; siempre-1-vez no hace bucle | unit (FakeResilientDb) | `uv run pytest tests/test_resilience.py -q -k reconnect` | ❌ Wave 0 |
| RESL-03 | `pre_ping` y `max_connection_lifetime` reciclan la conexión directa; `:memory:` rechaza | unit (monkeypatch de `time.monotonic` + fake) | `uv run pytest tests/test_resilience.py -q -k lifetime` | ❌ Wave 0 |
| RESL-04 | Cada driver → excepción de la librería; lock NO se traduce; herencia compatible | unit (parametrizado por motor) | `uv run pytest tests/test_resilience.py -q -k translate` | ❌ Wave 0 |
| RESL-01/02 (integración opcional) | Kill real + reconnect real contra contenedores | integration (marker `integration`, auto-skip si no hay motor) | `uv run pytest tests/test_resilience_integration.py -q -m integration` | ❌ Wave 0 (opcional) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_resilience.py -q`
- **Per wave merge:** `uv run pytest -q -m "not optional_engine"`
- **Phase gate:** suite completa verde + `uv run mypy encino_orm` + `uv run ruff check .` antes de `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/_resilience_helpers.py` — `FakeResilientDb` (subclase de `Db` con `_execute` que falla N veces y luego triunfa, contador de `connect()`/`close()`), `FakeDriverQueFalla`.
- [ ] `tests/test_resilience.py` — los cuatro bloques RESL-01…04.
- [ ] (Opcional) `tests/test_resilience_integration.py` — kills reales por motor, marcados `integration`/`optional_engine` y auto-skip vía `tests/conftest.py::engine_unavailable`.
- [ ] No se requieren fixtures compartidas nuevas en `tests/conftest.py` (los dobles viven en el helper).

### Cómo probar cada criterio de éxito SIN fallos de red reales (deliverable #7)
1. **Criterio 1 (clasificación):** construir las excepciones con las **firmas reales verificadas** y pasarlas a `is_disconnect_error`/`is_lock_error`:
   - `pymysql.err.OperationalError(2013, 'Lost connection...')` → disconnect True; `OperationalError(1213, 'Deadlock...')` → lock True y disconnect False.
   - `asyncpg.exceptions.ConnectionDoesNotExistError('...')`, `asyncpg.InterfaceError('connection is closed')` → True; `asyncpg.exceptions.DeadlockDetectedError(...)` → lock True, disconnect False; `InvalidCachedStatementError(...)` → ambos False.
   - `pyodbc.Error('HY000', '...Connection may have been terminated by the server... (596)')` y `pyodbc.OperationalError('08S01', '...Communication link failure...')` → True; code 1205/1222 → lock.
   - `oracledb.exceptions.DatabaseError` con `args[0]` falso que exponga `code=0, full_code='DPY-4011'` → True; `_FakeExc(60)` → lock. (Reusar el patrón `_FakeError`/`_FakeExc` de `tests/test_oracle.py:22-29`.)
   - `sqlite3.ProgrammingError('Cannot operate on a closed database.')` → True; `sqlite3.OperationalError('database is locked')` → False.
2. **Criterio 2 (reconexión):** `FakeResilientDb` que hereda de `Db`, con `_execute` que lanza un disconnect en la 1ª llamada y devuelve `"ok"` en la 2ª, `is_disconnect_error=True`, `in_transaction=False`, contadores de `connect()`/`close()`. Asserts: resultado `"ok"`, `connect` 1 vez, `close` 1 vez, `_execute` 2 veces. Variante `in_transaction=True`: `pytest.raises` y `connect` **0** veces. Variante "siempre falla": `pytest.raises` y `_execute` exactamente 2 veces (no bucle).
3. **Criterio 3 (idle):** `monkeypatch.setattr(time, "monotonic", ...)` (o inyectar un reloj) para simular el paso del tiempo; `pre_ping=True` con `is_alive()` False → reconecta y la op triunfa; `max_connection_lifetime=N` con reloj avanzado → reconecta; `SqliteDb(database=":memory:")` → `_reconnect` lanza. **Sin** temporizadores reales ni `sleep`.
4. **Criterio 4 (taxonomía):** parametrizar por motor con las excepciones construidas y `pytest.raises(ConnectionLostError)`/`OperationalError`/`IntegrityError`/`ProgrammingError`; assert de compatibilidad (`issubclass(ConnectionLostError, ConnectionError)`, `issubclass(OperationalError, QueryError)`) y que `is_lock_error` sigue viendo el original.
5. **Manual-only:** verificar contra un motor real que `Model.insert` dentro de `transaction()` **no** reconecta y lanza (requiere kill mid-tx); se puede automatizar con los contenedores como test `integration` opcional, pero no es determinista en CI sin los servicios. La lógica está cubierta por el doble.

## Security Domain

> `security_enforcement` ausente en `.planning/config.json` → habilitado. La fase es de resiliencia, no de autenticación; los controles son de integridad de datos y de no fuga de secretos.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | parcial | La traducción de errores no debe construir SQL ni interpolar valores; los identificadores ya pasan por `check_identifier`. |
| V6 Cryptography | no | — |
| V7 Error Handling & Logging | **sí** | Traducir sin filtrar secretos: `_connect_kwargs` contiene `password`; **no** loguear el dict crudo. Los mensajes de la taxonomía deben incluir el mensaje del driver (útil) pero **nunca** los kwargs de conexión. |

### Known Threat Patterns for esta fase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Duplicación silenciosa de escrituras por reintento tras desconexión ambigua | Tampering / Repudiation | Guard `in_transaction()` + no reintentar escrituras fuera de transacción (Open Q1). |
| Fuga de credenciales en logs de reconexión | Information Disclosure | No loguear `_connect_kwargs`; loguear solo el dialecto/motivo. |
| Catch-all `except Exception` que oculte fallos | Repudiation | Taxonomía explícita; `_translate_exception` mapea, no traga. |
| Reconexión que salta controles de aislamiento/scope | Tampering | Reconectar **fuera** de transacción; dentro, relanzar. El `scope()` multi-tenant vive en `Query`, no se ve afectado. |
| `:memory:` reconectado → pérdida de datos (integridad) | Tampering | Rechazo explícito en `SqliteDb._reconnect`. |

## Sources

### Primary (HIGH confidence)
- **Sondas de desconexión reales** contra los seis contenedores de `docker-compose.yml` (2026-09-18, todos "Up"): MySQL/MariaDB `KILL`, PostgreSQL `pg_terminate_backend`, MSSQL `KILL` (mid-query e idle, con y sin `ConnectRetryCount`), Oracle `ALTER SYSTEM KILL SESSION`, SQLite `sqlite3` closed-db. Tipos y `args` exactos capturados.
- **Introspección de los drivers instalados** (`.venv`): jerarquías de `pymysql.err`, `asyncpg.exceptions`, `pyodbc`, `oracledb.exceptions`, `sqlite3` — `[VERIFIED: .venv]`.
- Código vivo del repositorio, con anchors citados en cada sección: `base.py`, `exceptions.py`, `sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`, `pool.py`, `context.py`, `model/model.py`, `http/errors.py`, `pyproject.toml`, `tests/*`.
- `docs/engines.md:138-158` (contrato de hooks de adaptador).
- `.planning/research/ARCHITECTURE.md` (Pattern 5, líneas 342-380; Anti-Pattern 4, líneas 608-614; integración por motor, líneas 653-662) — SQLAlchemy `pool_pre_ping`/`pool_recycle` como referencia de comportamiento.

### Secondary (MEDIUM confidence)
- SQLAlchemy 2.0 Connection Pooling (`reset_on_return`, `pool_pre_ping`, `pool_recycle`, optimistic disconnect handling, `PoolEvents.reset`) — citado en `.planning/research/ARCHITECTURE.md:729`; informa la semántica de `max_connection_lifetime` (edad) y pre-ping (no recupera mid-transaction).

### Tertiary (LOW confidence)
- Ninguna. Toda la clasificación por motor está respaldada por sondas directas; las decisiones de diseño restantes están en **Assumptions Log** / **Open Questions**.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no hay dependencias nuevas; versiones verificadas por metadatos.
- Clasificación por motor: HIGH — desconexiones reales provocadas en los seis motores (cinco contenedores + SQLite local).
- `_with_reconnect` shape: MEDIUM — decisión de diseño; la mecánica (guard, exactamente-una-vez) está anclada al código y a las sondas.
- Taxonomía: MEDIUM — propuesta compatible, pero el punto de herencia (QueryError) es una decisión.
- Pitfalls: HIGH — siete de los diez están respaldados por reproducción empírica; tres (warnings, rename de dobles, doble reintento) son riesgos de refactor deducidos del código.

**Research date:** 2026-09-18
**Valid until:** 2026-10-18 (30 días) para las decisiones de diseño; la clasificación por motor es válida mientras no cambien las versiones de driver fijadas en `uv.lock`.
