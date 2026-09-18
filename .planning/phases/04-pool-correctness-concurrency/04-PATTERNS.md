# Phase 4: Pool Correctness & Concurrency - Pattern Map

**Mapped:** 2026-09-18
**Files analyzed:** 24 (10 modificados de librería, 3 tests extendidos, 3 tests nuevos/extraídos, 1 snapshot, 4 config/gates, 3 docs)
**Analogs found:** 24 / 24 (todos tienen analog exacto o role-match; ninguno sin analog)

> Autoridad: `04-RESEARCH.md`. Donde el sketch de RESEARCH y el código discrepen, **el código vivo de este documento es la fuente de verdad**. Las anclas `file:line` de abajo están verificadas contra el árbol actual. No existe `04-CONTEXT.md`; las decisiones bloqueadas son las de `ROADMAP.md:249-274` + Research Corrections #1/#4/#5.

---

## File Classification

| New/Modified File | Action | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|--------|------|-----------|----------------|---------------|
| `encino_orm/pool.py` — `PooledConnection` | new | value-object/handle | concurrency (stateful) | `model/column.py:4-7` + `model/constraint.py:12-20` + `dialects/strategies.py:16-30`; estado = `PoolDb` (`pool.py:65-71`) | role-match |
| `encino_orm/pool.py` — `acquire`/`release`/`_reap`/`close` | modify | wrapper/pool | request-response + concurrency | sí mismo (`pool.py:113-196`) + `base.py:80-94` (`retry`) | exact |
| `encino_orm/base.py` — `execute_insert`, `insert(returning=)`, `last_id()` deprecado | modify | controller (ABC) | request-response | sí mismo (`base.py:96-136`) + `mysql.py:32-38` (`warnings`) | exact |
| `encino_orm/query.py` — `returns_id`/`id_column` | modify | model/value-object | transform | sí mismo (`query.py:51-138`, campo `ignore_duplicated`) | exact |
| `encino_orm/context.py` — `resolve_db()` desenvaina `.driver` | modify | utility | request-response | sí mismo (`context.py:47-59`) | exact |
| `encino_orm/dialects/builders.py` — `build_insert(returning=)` + `MERGE SET` excluye `conflict_cols` | modify | service | transform (pure DML) | sí mismo: `build_upsert` (`builders.py:242-254`) + `_merge_sql` (`:32-78`) | exact |
| `encino_orm/dialects/strategies.py` | modify (si aplica) | config/value-object | transform | sí mismo (`InsertStrategy`, `strategies.py:16-46`) | exact |
| `encino_orm/sqlite.py` — `execute_insert` | modify | adapter | CRUD | sí mismo (`sqlite.py:173-180`, `:217-222`) | exact |
| `encino_orm/mysql.py` — `execute_insert` | modify | adapter | CRUD | sí mismo (`mysql.py:188-200`, `:246-247`) | exact |
| `encino_orm/mariadb.py` — `execute_insert` | modify | adapter (subclass) | CRUD | `encino_orm/mysql.py` (hereda) | exact |
| `encino_orm/postgresql.py` — `execute_insert` | modify | adapter | CRUD | sí mismo (`postgresql.py:195-201`, `:232-234`) | exact |
| `encino_orm/mssql.py` — `execute_insert` | modify | adapter | CRUD | sí mismo (`mssql.py:233-261`, `:316-317`) | exact |
| `encino_orm/oracle.py` — `execute_insert` | modify | adapter | CRUD | sí mismo (`oracle.py:238-266`, `:316-317`) | exact |
| `encino_orm/model/model.py` — `insert` usa `execute_insert` | modify | model/ORM | CRUD + transacción | sí mismo (`model/model.py:492-552`) | exact |
| `encino_orm/migration.py` — `_apply` usa `execute_insert` | modify | service | state-machine | sí mismo (`migration.py:65-144`) | exact |
| `tests/test_pool.py` | extend | test | unit + integración SQLite | sí mismo (`test_pool.py:11-341`) | exact |
| `tests/test_pool_characterization.py` | extend/invertir | test | concurrency (barrera) | sí mismo (`:29-393`) | exact |
| `tests/conftest.py` (o `tests/_pool_helpers.py`) — `EventBarrier` | modify/new | test helper | concurrency | `test_pool_characterization.py:126-144` | exact |
| `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` | extend | test | integration | sí mismos (`test_last_id_characterization`) | exact |
| `tests/__snapshots__/test_sql_snapshots.ambr` | modify (generado) | test data | snapshot | sí mismo (`.ambr:85,128,160,174,206,220`) | exact |
| `pyproject.toml` | modify | config | — | sí mismo (`markers:75-80`, `dev:265-286`, `mypy:230-239`) | exact |
| `.github/workflows/ci.yml` | modify | config | — | sí mismo (job `test` `:102-136`, `engine-heavy` `:353-356`) | exact |
| `docs/engines.md`, `docs/guide.md`, `CHANGELOG.md` | modify | docs | prosa | `docs/engines.md:133-137`; entrada `[Unreleased]` | role-match |

---

## Pattern Assignments

### `encino_orm/pool.py` — `PooledConnection` (value-object/handle, concurrency)

**Analog:** los dataclasses de valor del repo (`Column`, `Constraint`, `Index`, `Migration`, `InsertStrategy`, `DialectLimits`) para la **forma**; el propio `PoolDb` (`pool.py:65-71`) para el **estado** que se concentra.

**Forma dataclass + defaults mutables** (`strategies.py:16-30` y `constraint.py:12-20`):
```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class InsertStrategy:
    kind: Literal["prefix", "suffix", "merge"]
    replace_prefix: str = "INSERT OR REPLACE"
    ...

@dataclass(frozen=True)
class Constraint:
    datatype: str
    field_kwargs: dict = field(default_factory=dict)  # default mutable SIEMPRE factory
```

**Estado por conexión que se mueve desde `PoolDb`** (`pool.py:65-71`, `:118`, `:147`, `:174`):
```python
self._last_id = 0          # cache COMPARTIDO entre tareas (POOL-03 lo elimina)
self._last_used = {}       # dict keyed por Db -> time.monotonic()
```

**Convenciones a copiar:**
- `@dataclass` **NO frozen**: `last_id`, `last_used`, `generation`, `checked_out` son mutables. El estado inmutable de config (p. ej. `dialect`) sí puede ser `frozen`.
- Defaults mutables con `field(default_factory=...)` (`constraint.py:19`), nunca `{}`/`set()` directos.
- Helper `touch()` = `self.last_used = time.monotonic()` (patrón `pool.py:118,147,174`); `is_idle_for(timeout)` = `time.monotonic() - self.last_used > timeout` (patrón `_needs_check`, `pool.py:128-134`).
- Tipo de `driver` anotado como `Db`; importar `from .base import Db` (ya presente, `pool.py:6`).

**Lo que NO se copia:**
- **No `frozen=True`** de `Column`/`Constraint`/`Index`: el handle se muta en cada operación.
- **No `__post_init__` + `object.__setattr__`** de `Index` (`index.py:23-27`): normaliza tuplas inmutables; aquí no aplica.
- **No `_set_private`** (`model/model.py:78-79`): es el escape hatch de pydantic, no de dataclasses.
- **No reintroducir `PoolDb._last_id`** (`pool.py:69,281,304`): es el cache compartido entre tareas que POOL-03 elimina.

---

### `encino_orm/base.py` — `execute_insert(qry) -> int | None` y `insert(..., returning=<col>)` (controller/ABC)

**Analog:** sí mismo. La firma abstracta actual fija el contrato keyword-only y los adaptadores delegan en el seam.

**Firma actual de `insert` (keyword-only `schema`)** (`base.py:96-106`):
```python
@abstractmethod
def insert(
    self,
    tabla: str,
    data: dict,
    ignore_duplicated=False,
    replace=False,
    conflict: list[str] | None = None,
    *,
    schema: str | None = None,
): ...
```

**Firma actual de `execute`/`last_id`** (`base.py:114-130`):
```python
@abstractmethod
async def execute(self, qry: Query): ...
...
@abstractmethod
async def last_id(self): ...
```

**Convenciones a copiar:**
- Añadir `execute_insert` como `@abstractmethod` junto a `execute` (`base.py:114-115`); `returning` va **keyword-only** (mismo criterio que `schema`, `base.py:105`) para no romper llamadores posicionales.
- Retorno `int | None` (`None` = "id no disponible", p. ej. MERGE).
- **Contrato de importación diferida**: `base.py` no importa drivers (imports actuales `base.py:1-9`); la captura del id vive en cada adaptador. El seam `builders.py` importa solo stdlib + `Query` + checker (`builders.py:15-17`) — no añadir imports de motor.
- Deprecación centralizada en `Db.last_id()` (base) con `warnings.warn(..., DeprecationWarning, stacklevel=2)`; los adaptadores exponen `_last_id_value()` (mapa de responsabilidades RESEARCH §Architectural Responsibility Map). Esto evita seis sitios de warning bajo `filterwarnings=["error"]`.
- `MAX_TRIES`/`WAITERS`/`MAX_WAIT` (`base.py:15-17`) son el precedente de constantes de clase tuneables.

**Lo que NO se copia:**
- **No cambiar el retorno de `Db.execute`** a `(rowcount, last_id)`: rompe `Model.upsert` (`model.py:678`), `insert_many` (`model.py:619`), `migration.py:56,62,97-114`, `transfer.py:118-157`, `http/`, `graphql/` (RESEARCH §Alternatives, blast radius enorme).
- **No emitir el `DeprecationWarning` de `last_id()` en `base.py` sin migrar antes** `model/model.py:542` y `migration.py:107` (Pitfall 2).

---

### `encino_orm/query.py` — `returns_id` / `id_column` (value-object, transform)

**Analog:** sí mismo, campo `ignore_duplicated` como precedente exacto de "campo de constructor con property de solo lectura, excluido de igualdad/hash".

**Slots + anotaciones + `object.__setattr__`** (`query.py:48-82`):
```python
__slots__ = ("_fields", "_ignore_duplicated", "_params", "_sql", "_sql_template")
_fields: list
_ignore_duplicated: bool
...
object.__setattr__(self, "_ignore_duplicated", bool(ignore_duplicated))
```

**Igualdad/hash que excluye flags** (`query.py:121-138`):
```python
def __eq__(self, other) -> bool:
    return self.sql_template == other.sql_template and self.fields == other.fields

def __hash__(self) -> int:
    return hash((self.sql_template, tuple(self.fields)))
```

**Convenciones a copiar:**
- Añadir los slots **privados** `_returns_id`/`_id_column` a `__slots__` (orden RUF023), sus anotaciones de clase (necesarias para mypy con `object.__setattr__`, `query.py:48-56`), properties sin setter, y escribirlos con `object.__setattr__`.
- Excluirlos de `__eq__`/`__hash__` como `ignore_duplicated` (comentario `query.py:121-124`), **o** documentar explícitamente por qué entran; el planner debe elegir y escribirlo.
- `with_params` (`query.py:114-119`) debe propagar los nuevos campos por construcción.

**Lo que NO se copia:**
- No romper los lectores de `.sql_template`/`.query`/`.fields`/`.params`: los 6 adaptadores leen `qry.query[0]`/`[1]`, `pool.py:280` lee `qry.sql_template`, `base.py:195` lee `qry.fields` (ver `02-PATTERNS.md` §"Call sites that constrain the refactor").
- No mutar los campos post-construcción (D-04 de Fase 2 prohíbe asignaciones fuera del constructor).

---

### `encino_orm/context.py` — `resolve_db()` desenvaina el handle (utility)

**Analog:** sí mismo (`context.py:47-59`).

```python
def resolve_db():
    from .pool import _current_connection  # lazy: evita import circular
    conn = _current_connection.get()       # 1. transacción activa del pool
    if conn is not None:
        return conn
    ...
```

**Convención a copiar:** mantener el import diferido `from .pool import _current_connection` (rompe el ciclo, `context.py:49`) y devolver `conn.driver` cuando `conn` sea un `PooledConnection` (Pitfall 8). El orden de resolución 1→4 (`context.py:6-12`) no cambia.

**Lo que NO se copia:** no devolver el handle tal cual — `Model` llama `.insert/.execute/.last_id` sobre el resultado (`model/model.py:533-542`) y `engine_of` lee `.dialect` (`engine.py:35-43`).

---

### `encino_orm/dialects/builders.py` — `build_insert(returning=)` + fix ORA-38104 (service, transform)

**Analog:** sí mismo. `build_upsert` ya implementa **exactamente** el patrón de exclusión de columnas de conflicto que necesita el `MERGE` de `build_insert`.

**Patrón a copiar para ORA-38104 — exclusión de `update_cols`** (`builders.py:242-254`):
```python
else:  # merge
    if update_values is None:
        set_sql = ", ".join(f"dst.{c} = src.{c}" for c in update_cols)
    ...
    sql = _merge_sql(qualified, strategy, cols, list(conflict), set_sql, update_cols=update_cols ...)
```

**El defecto actual a corregir** (`builders.py:137-139`):
```python
conflict_cols = list(conflict) if conflict else ([columns[0]] if columns else ["id"])
set_sql = ", ".join(f"dst.{c} = src.{c}" for c in columns)   # incluye la columna del ON -> ORA-38104
```

**Fix (mismo shape que `build_upsert`):**
```python
update_cols = [c for c in columns if c not in conflict_cols]
if not update_cols:
    raise ValueError("MERGE sin columnas actualizables: todas las del INSERT son de conflicto")
set_sql = ", ".join(f"dst.{c} = src.{c}" for c in update_cols)
```

**Validación fail-closed + `check_identifier`** (`_merge_sql:47-66`, `build_insert:92-99`): validar `returning` con `check_identifier(returning, "columna de retorno")` **antes** de interpolar en `RETURNING`/`OUTPUT INSERTED` (Security V5, RESEARCH:671). Mantener el `raise ValueError` temprano, nunca un default silencioso.

**Convenciones a copiar:**
- El builder sigue importando solo stdlib + `Query` + checker (`builders.py:15-17`).
- La rama `returning` es **opt-in** y por `strategy.kind`/flags: `suffix` → `RETURNING <col>`; `merge`+MSSQL → `OUTPUT INSERTED.<col>`; Oracle `returning_id` + plain INSERT → `RETURNING <col> INTO :ret_id` (patrón ya en `builders.py:145-146`).
- `Query(sql, values, ..., returns_id=..., id_column=...)` en el único `return Query(...)` (`builders.py:148-154`).
- Docstring de módulo documentando la frontera de confianza (`builders.py:1-13`) y el porqué del fix (ORA-38104).

**Lo que NO se copia:**
- **No `RETURNING`/`OUTPUT` incondicional**: `UndefinedColumnError` (PG) / ORA-00904 (Oracle) en tablas sin `id`; rompe `transfer.py:157` (Pitfall 3, verificado).
- **No añadir `RETURNING` al MERGE de Oracle**: `ORA-00933` (verificado). El fix de ORA-38104 solo garantiza ejecutabilidad, no id.
- **No eliminar `update_cols=` de `_merge_sql`** (`builders.py:60-66`): su validación fail-closed es compartida.

**Snapshots/golden strings que este cambio mueve:** `tests/__snapshots__/test_sql_snapshots.ambr:160,174,206,220` (renders `MERGE ... SET dst.a = src.a, ...`) y `tests/test_dialect_builders.py:159-166,193-201` (golden strings). Regenerar con `--snapshot-update` y **revisar el diff visiblemente** (mismo criterio que 02-08).

---

### `encino_orm/{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` — `execute_insert` (adapters)

**Analog por adaptador:** su propio `execute`/`last_id`; la forma de delegación de `insert` es idéntica en los seis.

**Captura actual por motor (estado a sustituir):**

| Motor | Ejecución | Captura actual | Ancla | Objetivo |
|-------|-----------|----------------|-------|----------|
| SQLite | `sqlite.py:173-180` | `SELECT last_insert_rowid()` en `last_id` | `sqlite.py:217-222` | `cursor.lastrowid` inmediato tras el INSERT |
| MySQL/MariaDB | `mysql.py:188-200` | `self._last_id = cursor.lastrowid` | `mysql.py:196` | `cursor.lastrowid` (ya correcto) |
| PostgreSQL | `postgresql.py:195-201` | `SELECT lastval()` | `postgresql.py:232-234` | `INSERT ... RETURNING <pk>` + `fetchrow` |
| MSSQL | `mssql.py:233-261` | `SELECT CAST(@@IDENTITY AS INT)` en statement aparte | `mssql.py:255-257` | `OUTPUT INSERTED.<pk>` en el mismo statement (`rowcount == -1`) |
| Oracle | `oracle.py:238-266` | `:ret_id` out-var (ya existe) | `oracle.py:245-262` | mismo mecanismo, **opt-in** |

**Patrón Oracle ya implementado a preservar** (`oracle.py:245-262`):
```python
returning = ":ret_id" in sql
cursor = self._connection.cursor()
out = cursor.var(self._oracledb.NUMBER) if returning else None
params = dict(values)
if returning:
    params["ret_id"] = out
...
if returning:
    v = out.getvalue()
    self._last_id = v[0] if isinstance(v, (list, tuple)) and v else 0
```

**Convenciones a copiar (los seis):**
- `self._ensure_connected()` → `self._prepare(qry)` → `t0 = time.monotonic()` → driver → `_log(...)` (p. ej. `sqlite.py:173-180`).
- Cada adaptador mantiene su propio `_log` con `%`-style lazy (`mysql.py:21-29`).
- MSSQL/Oracle ponen `self._in_tx = True` tras ejecutar (`mssql.py:252,274`; `oracle.py:258`).
- `execute_insert` **no** cambia el SQL por defecto: con `returning=None` el SQL debe ser byte-idéntico al actual.
- Delegación del builder intacta: `insert()` → `build_insert(...)` (`sqlite.py:143-163`); solo se reenvía `returning`.
- MariaDB hereda de `MysqlDb`: no duplicar `execute_insert` salvo que el motor lo requiera.

**Lo que NO se copia:**
- **PostgreSQL `lastval()`** (`postgresql.py:232-234`): SESSION-scoped, devuelve el último `nextval` de la sesión (Correction #1).
- **MSSQL `@@IDENTITY`** (`mssql.py:255`): session-scoped y contaminable por triggers; y **`SCOPE_IDENTITY()` en un `execute` separado devuelve NULL** (Pitfall 5, verificado).
- **Oracle `RETURNING` incondicional**: hoy se añade solo cuando `"id" not in columns` (`builders.py:145`); con `returning=<col>` debe ser opt-in del llamador.
- **No `raise ... from`** (convención del repo, `CONVENTIONS.md` §Error Handling).

---

### `encino_orm/base.py` — `last_id()` deprecado con `DeprecationWarning`

**Analog:** el único uso de `warnings` en la librería es `mysql.py:4,32-38`:
```python
import warnings

@contextlib.contextmanager
def _suppress_mysql_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", aiomysql.Warning)
        yield
```

**Convenciones a copiar:**
- `import warnings` a nivel de módulo; `warnings.warn("last_id() está deprecado; usa execute_insert(qry) o el retorno de Model.insert()", DeprecationWarning, stacklevel=2)`.
- Mensaje en español nombrando el reemplazo (convención de mensajes).
- Warning centralizado en `Db.last_id()`; los adaptadores solo implementan `_last_id_value()`.

**`filterwarnings=["error"]` — implicaciones (`pyproject.toml:56-72`):**
```toml
filterwarnings = [
    "error",
    "ignore:The default datetime adapter is deprecated:DeprecationWarning",
]
```
- Cualquier `warnings.warn` **nuevo** falla la suite. El orden es safety-critical (Pitfall 2): (1) migrar `model/model.py:542` y `migration.py:107` a `execute_insert`; (2) añadir el warning; (3) envolver las aserciones legadas de tests en `pytest.warns(DeprecationWarning)` o migrarlas.
- La allowlist solo admite entradas con justificación escrita que nombre módulo y motivo (`pyproject.toml:56-61`); **no añadir una entrada nueva** para el warning de `last_id()`.
- El precedente de sonda que prueba que un warning rompe la suite está en `tests/test_pytest_config.py:140-142`.

**Lo que NO se copia:**
- **No enganchar el warning a la mera presencia de `in_transaction()`** al liberar: MSSQL/Oracle ponen `_in_tx=True` también en `fetch_all/fetch_one/fetch_many` (`mssql.py:274,289,309`; `oracle.py:258`) y cada SELECT rompería la suite (Pitfall 4, A1). Engancharlo a `reset_on_release="commit"`.

---

### `encino_orm/pool.py` — `reset_on_release` + commit/rollback explícito en `execute`/`_run`

**Analog:** `Db.transaction()` (template) + el commit best-effort actual del pool + `Model._transactional`.

**Template de transacción** (`base.py:45-52`):
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

**`PoolDb.transaction()`** (`pool.py:187-196`): fija `_current_connection`, delega en `db.transaction()` y libera en `finally`.

**El commit implícito actual (a hacer explícito con rama de error)** (`pool.py:231-244`):
```python
async def _run(self, method: str, *args):
    db = _current_connection.get()
    if db is not None:
        return await getattr(db, method)(*args)
    db = await self.acquire()
    try:
        return await getattr(db, method)(*args)
    finally:
        if await db.in_transaction():
            await db.commit()
        await self.release(db)
```
Idéntico en `execute` (`pool.py:273-286`).

**`Model._transactional` — precedente del patrón `try/except` con hooks** (`model/model.py:438-453`).

**Convenciones a copiar (Correction #5, orden obligatorio):**
1. En `_run`/`execute`: `try: result = await ...` / `except BaseException: if in_transaction(): rollback(); raise` / `else: if in_transaction(): commit(); return result` / `finally: release(handle)`.
2. **Después** `release()` aplica `reset_on_release` al sobrante (`"rollback"` default, `"commit"` configurable).
3. `reset_on_release` es kwarg de constructor, junto a `min_size`/`max_size`/`idle_timeout` (`pool.py:48-55`).
4. `release()` comprueba pertenencia a `_checked_out` antes de reencolar (doble release → warning + ignorar, patrón de log `logger.warning("...%r", handle)`).
5. `TestPoolAutocommit` (`test_pool.py:311-329`) y `TestPoolStandaloneCommit` (`test_pool.py:221-232`) son la regresión.

**Lo que NO se copia:**
- **No dejar el commit como única responsabilidad de `release()`**: invertir el orden convierte cada `pool.execute(INSERT)` standalone en pérdida silenciosa (Pitfall 1).
- **No aplicar `reset_on_release` a cualquier `in_transaction()` sin distinguir lectura de escritura** (Pitfall 4).
- **No exponer `reset_on_release="none"`**: es el comportamiento accidental que la fase elimina (A2).

---

### `encino_orm/pool.py` — contador de generación + reaper perezoso

**Analog:** la contabilidad `_last_used` y el guard de liveness actuales + las constantes tuneables de `base.py`.

**Bookkeeping actual** (`pool.py:70,118,128-134,147,174`):
```python
self._last_used = {}
...
def _needs_check(self, db: Db) -> bool:
    if self._idle_timeout is None:
        return True
    last = self._last_used.get(db)
    if last is None:
        return True
    return time.monotonic() - last > self._idle_timeout
```

**Constantes tuneables** (`base.py:15-17`):
```python
MAX_TRIES = 9
WAITERS: ClassVar[list[float]] = [x * 0.02 for x in range(1, 11)]
MAX_WAIT = len(WAITERS) - 1
```

**Convenciones a copiar:**
- Reaper perezoso invocado al **entrar** en `acquire()` y al **salir** de `release()`; `idle_timeout=None` desactiva (`pool.py:129-130`).
- `time.monotonic()` para ociosidad (`pool.py:118,134,147,174`), nunca `time.time`.
- Drain con `get_nowait()` + `except asyncio.QueueEmpty` (el `PERF203` está justificado en `pyproject.toml:163-165`); **cerrar los drivers FUERA del bucle** (recoger en una lista, luego `await close()`).
- `_size` se decrementa al reapear y nunca baja de `min_size`.
- Generación: contador del pool asignado por conexión; `release()` cierra (no reencola) handles de generación obsoleta.

**Lo que NO se copia:**
- **No `asyncio.Task` daemon con `sleep`**: sin daemon que cancelar en `close()` (RESEARCH §Don't Hand-Roll).
- **No cerrar dentro del bucle de drenado** con un `await` que pueda intercalar otra tarea (recoger primero, cerrar después).

---

### `encino_orm/pool.py` — `close()` idempotente

**Analog:** `close()` de los adaptadores (p. ej. `sqlite.py`, `mysql.py`) + el `close()` actual del pool.

**Defecto actual** (`pool.py:177-185`):
```python
async def close(self):
    self._connected = False
    while not self._pool.empty():
        self._pool.get_nowait()
    for db in list(self._connections):   # incluye las RETENIDAS -> defecto POOL-06
        await db.close()
    self._connections.clear()
    self._size = 0
    self._last_used.clear()
```

**Caracterización existente** (`test_pool_characterization.py:343-393`): `test_close_is_idempotent` (`:356-366`) ya pasa; `test_close_closes_held_connection` (`:368-376`) **se invierte** (`held.closed is False`).

**Convenciones a copiar:**
- Guard de idempotencia (`_closed = True`; segunda llamada no-op) sin lanzar (`:361`).
- Drenar `_idle` y cerrar **solo** las ociosas; las de `_checked_out` no se tocan y se cierran al liberarse (rama `_closed` de `release`).
- `is_connected` pasa a `False`; `_size` a 0; `_connections` limpio de ociosas; **los stats no se resetean** (`test_close_does_not_reset_stats`, `:385-393`).

**Lo que NO se copia:** no iterar `self._connections` (incluye retenidas) — es exactamente el defecto caracterizado.

---

### `encino_orm/model/model.py` — `insert` usa `execute_insert`

**Analog:** sí mismo (`model/model.py:492-552`).

**Punto exacto a migrar** (`model/model.py:532-542`):
```python
async def do_insert():
    qry = self._get_db().insert(self._table, data, ignore_duplicated, replace, conflict)
    await self._get_db().execute(qry)
    if qry.sql_template.lstrip().upper().startswith("MERGE"):
        return None
    return await self._get_db().last_id()
```

**Convenciones a copiar:**
- Pasar `returning="id"` solo si `_is_auto_pk()` (`model/model.py:510`, `:287-289`); en caso contrario, sin `returning`.
- Usar `execute_insert(qry)` y devolver su resultado directamente; **mantener el contrato "MERGE devuelve 0 / no asigna `id`"** también en Oracle (`model.py:540-541`; Pitfall 6).
- `_transactional("insert", do_insert)` (`:544`) no cambia.

**Lo que NO se copia:** no pedir `returning` incondicional (tablas con PK natural y `transfer.py`).

---

### `encino_orm/migration.py` — `_apply` usa `execute_insert`

**Analog:** sí mismo (`migration.py:65-144`).

**Punto exacto a migrar** (`migration.py:97-109`):
```python
await db.execute(db.insert(MIGRATIONS_TABLE, {"name": name, "status": STATUS_PENDING, "sql_text": qry.sql}))
inserted = True
try:
    ledger_id = await db.last_id()   # best-effort; Oracle devuelve 0
except Exception:
    ledger_id = 0
```

**Convenciones a copiar:**
- Capturar el id con `execute_insert(...)` del INSERT del ledger (ya no hace falta el `try/except` best-effort); conservar `ledger_id = 0` como "no utilizable" y el fallback compare-and-delete `{name, status}` (`migration.py:126-131`).
- Mantener `async with db.transaction()` (nunca `db.commit()`, `pool.py:258-261`) y la compensación fail-open con `logger.warning` (`:132-142`).

**Lo que NO se copia:** no depender de `last_id()` post-hoc (se auto-deprecaría con `filterwarnings=["error"]`, Pitfall 2).

---

### Tests

**Analog principal:** `tests/test_pool.py` y `tests/test_pool_characterization.py` (la red de seguridad CI-09).

**Fake `Db` a mano + `monkeypatch`** (`test_pool.py:11-92`, `test_pool_characterization.py:29-156`):
```python
class FakeDb:
    ...
    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("begin",))
        try:
            yield self
            self.calls.append(("commit",)); self._in_tx = False
        except Exception:
            self.calls.append(("rollback",)); self._in_tx = False
            raise

@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb
```
- Fakes a mano + `monkeypatch`; **evitar `unittest.mock`** (convención del repo).

**Barrera determinista 3.10** (`test_pool_characterization.py:106-123,126-144`):
```python
_CONNECT_BARRIER = None

class BlockingFakeDb(FakeDb):
    async def connect(self, **kwargs):
        barrier = _CONNECT_BARRIER
        if barrier is not None:
            await barrier.wait()
        await super().connect(**kwargs)

class EventBarrier:
    def __init__(self, parties: int):
        self._parties, self._arrived = parties, 0
        self._event = asyncio.Event()
    async def wait(self):
        self._arrived += 1
        if self._arrived >= self._parties:
            self._event.set()
        await self._event.wait()
```
- `parties` **debe** ser igual al número de tareas (`:215-217`), si no la barrera cuelga. Extraer a `tests/conftest.py` o `tests/_pool_helpers.py` si se reutiliza (Wave 0).
- Prohibido `asyncio.Barrier`/`TaskGroup`/`asyncio.timeout` (piso 3.10, Correction #4).

**Inversiones obligatorias** (no borrar aserciones; `04-RESEARCH.md:630-643`):
| Test actual | Acción | Nuevo assert |
|-------------|--------|--------------|
| `test_concurrent_acquire_overshoots_max_size` (`:227-228`) | invertir | `_size <= _max_size` |
| `test_double_release_aliases_same_connection` (`:339`) | invertir | la cola no duplica |
| `test_release_does_not_commit_or_rollback` (`:309-310`) | invertir | rollback por defecto |
| `test_close_closes_held_connection` (`:376`) | invertir | `held.closed is False` |
| `TestPoolLastIdScoping` (`:248,260,272,275,280,282`) | eliminar lecturas de `_last_id` | migrar a `execute_insert` |
| `test_standalone_operation_commits` (`test_pool.py:221-232`), `test_dml_visible_across_connections` (`:311-329`) | preservar | commit explícito intacto |

**Markers y timeout** (`pyproject.toml:73-80`; `ci.yml:102-136`):
```python
@pytest.mark.concurrency
@pytest.mark.timeout(10)          # pytest-timeout; --strict-markers no falla
async def test_no_overshoot_under_barrier(...): ...

@pytest.mark.stress
@pytest.mark.repeat(5)            # pytest-repeat
async def test_no_overshoot_repeated(...): ...
```
- Registrar el marker `stress` en `pyproject.toml` (hoy hay 4: `:75-80`) para no romper `--strict-markers` (`addopts`, `:52`).
- CI Linux: `--timeout-method=signal` en el job `test` (`ci.yml:134-136`) y, si aplica, `engine-heavy` (`ci.yml:353-356`). El método *thread* en Windows mata el proceso y pierde el JUnit XML (Pitfall 7).
- `PT011`/`B017` siguen ignorados en `tests/**` (`pyproject.toml:127-131`); levantarlos es decisión de alcance (A8/Open Q4).

**Lo que NO se copia:** no usar temporizadores/`sleep` en la barrera; no ajustar `parties` a ojo; no `asyncio.Barrier`.

---

### `pyproject.toml` (config)

**Analog:** sí mismo.

- Añadir marker `stress` a `markers` (`:75-80`), con descripción en español.
- Dev deps con pin exacto, copiando el comentario-racional de `syrupy==6.1.1` (`:281-285`):
```toml
# Pin exacto: la salida/efecto está versionada; sin fijar, CI podría resolver una
# versión más nueva y romper un PR no relacionado.
"pytest-timeout==2.4.0",
"pytest-repeat==0.9.4",
```
- `uv add --dev` regenera `uv.lock`; CI `deps` corre `uv lock --check` (`ci.yml:222-225`, Pitfall 10).
- Ratchet mypy: quitar `"encino_orm.pool"` de `[[tool.mypy.overrides]]` (`:236`) **solo si** `uv run mypy encino_orm` sale limpio (Pitfall 9).
- `filterwarnings` se mantiene `["error"]` (`:62`); no añadir allowlist.
- `check_coverage_floors.py`: RESEARCH Open Q5 recomienda **no** añadir piso para `pool.py` en esta fase (un piso mal calibrado bloquea CI).

---

### `.github/workflows/ci.yml` (config)

**Analog:** sí mismo. Job `test` (`:102-136`) y `engine-heavy` (`:353-356`).
- Añadir `--timeout-method=signal` al comando de pytest del job `test` (Linux) y, si aplica, al de `engine-heavy`.
- La corrida de estrés `-m stress --count=N` es opcional/soak local; si entra en CI, hacerlo tras el marker y con N pequeño.

---

### `docs/engines.md`, `docs/guide.md`, `CHANGELOG.md` (docs)

**Analog:** `docs/engines.md:133-137` documenta el contrato viejo (`lastval()`, `last_id()`); `docs/guide.md:190` menciona `PoolDb`; `CHANGELOG.md` entrada `[Unreleased]` (constraint de `PROJECT.md`: los cambios incompatibles 0.x DEBEN documentarse).
- Actualizar a `execute_insert` + `reset_on_release` + deprecación de `last_id` + "MERGE en Oracle no devuelve id".
- Estilo: prosa española + fenced Python, sin `Args:`/`Returns:` (`CONVENTIONS.md` §Docstrings).

---

## Shared Patterns

### Captura del id DENTRO de la sentencia (opt-in)
**Fuente:** `builders.py:81-154` (builder) + `execute_insert` por adaptador + `Query.returns_id`/`id_column`.
**Aplicar a:** los 6 adaptadores, `Model.insert`, `migration._apply`.
- `returning=None` por defecto → SQL byte-idéntico al actual. El id se captura en la MISMA sentencia (`lastrowid`/`RETURNING`/`OUTPUT`/`RETURNING INTO`).
- Sin cache global de id (`PoolDb._last_id` eliminado).

### Validación de identificadores
**Fuente:** `dialects/identifiers.py::check_identifier` (usado en `builders.py:22,96-99`, `model/model.py:266`).
**Aplicar a:** `returning=<col>` en `builders.py` **antes** de interpolar (`check_identifier(returning, "columna de retorno")`, Security V5). Nunca relajar `^[A-Za-z_][A-Za-z0-9_]*$`.

### Binding de parámetros
**Fuente:** `Query` con `{n}` (`query.py:58-82`); valores siempre ligados.
**Aplicar a:** todo SQL nuevo (reaper, `execute_insert`, MERGE). Los valores del id nunca se interpolan.

### Logging
**Fuente:** `logger = logging.getLogger("encino_orm")` (`base.py:11`) + `_log` por adaptador (`mysql.py:21-29`).
**Aplicar a:** reaper, release con doble liberación, warning de `last_id`.
- Formato `%` perezoso, nunca f-strings.

### Excepciones
**Fuente:** `exceptions.py` (`ConnectionError`, `PoolExhaustedError`) y `model/exceptions.py` (`ValidationError`).
**Aplicar a:** `acquire()` cerrado / no conectado (`pool.py:137-138`), `commit()`/`rollback()` directos (`pool.py:258-267`), `MERGE sin columnas actualizables` (`ValueError`). Mensajes en español; sin `raise ... from`.

### Transacción explícita
**Fuente:** `base.py:45-52` + `pool.py:187-196` + `migration.py:65-144`.
**Aplicar a:** `execute`/`_run`/`release`. Commit en éxito, rollback en error, **antes** de liberar; `release()` solo aplica la política al sobrante.

### Fakes deterministas + `monkeypatch`
**Fuente:** `test_pool.py:11-92`, `test_pool_characterization.py:29-156`, `tests/test_d_recommendations.py::LockDb`.
**Aplicar a:** tests nuevos de handle/reaper/generación/`reset_on_release`/doble release.
- Fakes a mano; `transaction()` como `@asynccontextmanager` que registra `begin`/`commit`/`rollback`.

### Importación diferida / sin dependencias duras
**Fuente:** `context.py:49` (`from .pool import ...` dentro de la función), `base.py:27-31`, `builders.py:15-17`.
**Aplicar a:** `context.resolve_db`; `builders.py` sigue sin importar drivers; `base.py` sin drivers.

---

## No Analog Found

Ningún fichero carece de analog de rol. Dos **comportamientos** son nuevos y quedan gobernados por `04-RESEARCH.md` (no por código existente):

| Behavior | Role | Data Flow | Reason |
|----------|------|-----------|--------|
| Reaper perezoso con contador de generación (semántica exacta) | pool | concurrency | No existe reaper hoy; solo `_needs_check` de liveness al adquirir (`pool.py:128-134`). Semántica de generación inventada (A6); cualquier equivalente testeable vale. |
| `reset_on_release` como política de constructor | pool | request-response | No hay precedente de política configurable de liberación; el commit accidental vive en `_run`/`execute` (`pool.py:242-243,284-285`). Sketch autoritativo: `04-RESEARCH.md:261-302`. |

**Restricciones de la investigación que el planner DEBE respetar:**
1. Orden de POOL-04 (Correction #5): commit/rollback explícito en `execute`/`_run` **antes** de `release()`; `TestPoolAutocommit` verde.
2. `returning` es opt-in; `RETURNING`/`OUTPUT` incondicional rompe inserts legítimos.
3. Oracle MERGE no puede devolver id (`ORA-00933`); el fix ORA-38104 solo da ejecutabilidad.
4. Piso 3.10: prohibido `asyncio.Barrier`/`TaskGroup`/`asyncio.timeout` (también en tests).
5. `resolve_db()` debe desenvainar `.driver` (Pitfall 8).
6. `pytest-timeout`/`pytest-repeat` son `[ASSUMED]` por ausencia de `slopcheck`: cada instalación va tras `checkpoint:human-verify`.

---

## Metadata

**Analog search scope:** `encino_orm/` (raíz, `model/`, `dialects/`), `tests/`, `tests/__snapshots__/`, `tools/ci/`, `.github/workflows/`, `pyproject.toml`, `docs/`.
**Files read for extraction:** 20 (`pool.py`, `base.py`, `context.py`, `query.py`, `dialects/builders.py`, `dialects/strategies.py`, `model/model.py`, `model/column.py`, `model/constraint.py`, `model/index.py`, `model/cached.py`, `migration.py`, `sqlite.py`, `mysql.py`, `postgresql.py`, `mssql.py`, `oracle.py`, `tests/test_pool.py`, `tests/test_pool_characterization.py`, `tests/conftest.py`, `tests/test_dialect_builders.py`, `pyproject.toml`, `ci.yml`, `tools/ci/check_coverage_floors.py`, `docs/engines.md`, snapshots `.ambr`).
**Pattern extraction date:** 2026-09-18

**Critical downstream reminders for the planner:**
1. **POOL-04 es safety-critical y secuencial**: hacer explícito el commit/rollback en `execute`/`_run` **antes** de tocar `release()`. Invertir el orden pierde escrituras en silencio.
2. **`returning` opt-in**; `Model.insert` lo pide solo si `_is_auto_pk()` (`model.py:510,287-289`).
3. **Migrar los llamadores internos de `last_id()`** (`model/model.py:542`, `migration.py:107`) **antes** de añadir el `DeprecationWarning` (`filterwarnings=["error"]`).
4. **Oracle MERGE: solo ejecutabilidad, nunca id** (`ORA-00933`).
5. **`resolve_db()` desenvaina `.driver`**; actualizar los tests que inspeccionan `_current_connection.get()`.
6. **Regenerar `.ambr` y revisar el diff** por el cambio del `SET` del MERGE y el `RETURNING` opt-in.
7. **No añadir piso de cobertura para `pool.py`** en esta fase (Open Q5).
8. **`pytest-timeout`/`pytest-repeat` tras `checkpoint:human-verify`** (slopcheck no disponible).
