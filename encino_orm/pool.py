import asyncio
import contextvars
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from .base import Db, _warn_last_id_deprecated
from .context import bind
from .engine import Engine
from .exceptions import ConnectionError, PoolExhaustedError, UnsupportedEngineError
from .mariadb import MariadbDb
from .mssql import MssqlDb
from .mysql import MysqlDb
from .oracle import OracleDb
from .postgresql import PostgresDb
from .sqlite import SqliteDb

_ENGINES = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "mariadb": MariadbDb,
    "postgresql": PostgresDb,
    "mssql": MssqlDb,
    "oracle": OracleDb,
}

logger = logging.getLogger("encino_orm")

# Conexión activa de la transacción en curso (por tarea/contexto). Permite que
# `PoolDb.execute/fetch/...` resuelvan a la MISMA conexión dentro de
# `transaction()`, garantizando atomicidad y `last_id()` correcto.
_current_connection = contextvars.ContextVar("encino_orm_pool_connection", default=None)


def _get_engine_cls(engine):
    key = engine.value if isinstance(engine, Engine) else engine
    cls = _ENGINES.get(key)
    if cls is None:
        raise UnsupportedEngineError(engine)
    return cls


@dataclass(eq=False)
class PooledConnection:
    """Handle que concentra el estado por conexión del pool (POOL-01).

    Reúne el driver y el estado que antes vivía repartido entre `PoolDb` (el
    cache de id y el registro de último uso) y el propio adaptador: el id de la
    última inserción es **por conexión/tarea** (nunca un cache compartido entre
    tareas) y ``last_used`` permite decidir si la conexión está ociosa.
    ``eq=False`` conserva la identidad de objeto, de modo que el handle es
    hashable y puede vivir en los conjuntos ``_connections``/``_checked_out``
    del pool.
    """

    driver: Db
    last_id: int = 0
    last_used: float = field(default_factory=time.monotonic)
    generation: int = 0
    checked_out: bool = False
    owner_task: object | None = None

    def touch(self) -> None:
        """Marca la conexión como usada ahora mismo."""
        self.last_used = time.monotonic()

    def is_idle_for(self, timeout: float | None) -> bool:
        """Indica si la conexión lleva más de `timeout` segundos ociosa.

        `timeout=None` desactiva la detección de ociosidad: nunca se considera
        ociosa.
        """
        if timeout is None:
            return False
        return time.monotonic() - self.last_used > timeout


class PoolDb(Db):
    """Wrapper que administra un pool de conexiones para entornos concurrentes.

    Expone la misma interfaz `Db`; los métodos DML/DQL delegan en
    ``acquire() -> operación -> release()``. Dentro de ``transaction()``, las
    operaciones se ejecutan sobre la conexión mantenida (vía contextvar).
    """

    def __init__(
        self,
        engine: str | Engine,
        min_size: int = 2,
        max_size: int = 10,
        idle_timeout: float | None = 60,
        **conn_kwargs,
    ):
        if isinstance(engine, Engine):
            engine = engine.value
        self._engine = engine
        self._engine_cls = _get_engine_cls(engine)
        self._min_size = min_size
        self._max_size = max_size
        self._idle_timeout = idle_timeout
        self._conn_kwargs = conn_kwargs
        self._template = self._engine_cls()
        self._idle = asyncio.Queue()
        self._connections = set()
        self._checked_out = set()
        self._size = 0
        self._generation = 0
        self._connected = False
        self._stats = {"acquires": 0, "waits": 0, "timeouts": 0, "creates": 0}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def dialect(self) -> str:
        return self._engine

    @property
    def MAX_PARAMS(self) -> int:
        """Techo de parámetros por sentencia del motor subyacente (no del pool)."""
        return self._template.MAX_PARAMS

    @property
    def MAX_ROWS(self) -> int:
        """Techo de filas por lote del motor subyacente (no del pool)."""
        return self._template.MAX_ROWS

    @property
    def transactional_ddl(self) -> bool:
        """Indica si el DDL del motor subyacente es rollbackable (no del pool).

        Delega en el template, que lo fija desde `TRANSACTIONAL_DDL`; el runner
        de migraciones lo lee para decidir la rama de compensación.
        """
        return self._template.transactional_ddl

    @property
    def stats(self) -> dict:
        """Métricas básicas del pool (adquisiciones, esperas, timeouts, tamaño)."""
        return {
            "size": self._size,
            "min_size": self._min_size,
            "max_size": self._max_size,
            "acquires": self._stats["acquires"],
            "waits": self._stats["waits"],
            "timeouts": self._stats["timeouts"],
            "creates": self._stats["creates"],
        }

    async def connect(self):
        for _ in range(self._min_size):
            handle = await self._create_connection()
            self._connections.add(handle)
            self._size += 1
            await self._idle.put(handle)
        self._connected = True

    async def _create_connection(self) -> PooledConnection:
        db = self._engine_cls()
        await db.connect(**self._conn_kwargs)
        self._stats["creates"] += 1
        return PooledConnection(driver=db, generation=self._generation)

    def _checkout(self, handle: PooledConnection) -> None:
        """Marca el handle como en uso por la tarea actual."""
        handle.checked_out = True
        handle.owner_task = asyncio.current_task()
        self._checked_out.add(handle)
        self._stats["acquires"] += 1

    async def acquire(self, timeout: float | None = None) -> PooledConnection:
        if not self._connected:
            raise ConnectionError("Pool no conectado")
        while True:
            try:
                handle = self._idle.get_nowait()
            except asyncio.QueueEmpty:
                if self._size < self._max_size:
                    # Reserva el cupo ANTES del `await`: así ninguna otra tarea
                    # puede pasar la comprobación mientras se crea la conexión
                    # (POOL-02). Si la creación falla, el cupo vuelve.
                    self._size += 1
                    try:
                        handle = await self._create_connection()
                    except BaseException:
                        self._size -= 1
                        raise
                    self._connections.add(handle)
                    self._checkout(handle)
                    return handle
                self._stats["waits"] += 1
                if timeout is None:
                    handle = await self._idle.get()
                    self._checkout(handle)
                    return handle
                try:
                    handle = await asyncio.wait_for(self._idle.get(), timeout=timeout)
                    self._checkout(handle)
                    return handle
                except asyncio.TimeoutError:
                    self._stats["timeouts"] += 1
                    raise PoolExhaustedError(
                        f"Pool agotado tras {timeout}s de espera (max_size={self._max_size})"
                    ) from None
            else:
                # Una conexión reciente se devuelve aunque esté caída; una ociosa
                # (o cualquier conexión si `idle_timeout=None`) se comprueba con
                # `is_alive()` y se descarta si no responde.
                needs_check = self._idle_timeout is None or handle.is_idle_for(self._idle_timeout)
                if not needs_check or await handle.driver.is_alive():
                    self._checkout(handle)
                    return handle
                self._connections.discard(handle)
                self._size -= 1
                await handle.driver.close()

    async def release(self, conn):
        handle = self._as_handle(conn)
        if handle not in self._checked_out:
            # Liberación ajena o duplicada: no se reencola (POOL-02).
            logger.warning("release() de una conexión que no está en uso: %r", handle)
            return
        self._checked_out.discard(handle)
        handle.checked_out = False
        handle.owner_task = None
        handle.touch()
        await self._idle.put(handle)

    def _as_handle(self, conn) -> PooledConnection:
        """Normaliza un `PooledConnection` o un `Db` crudo al handle del pool."""
        if isinstance(conn, PooledConnection):
            return conn
        for handle in self._connections:
            if handle.driver is conn:
                return handle
        return conn

    async def close(self):
        self._connected = False
        while not self._idle.empty():
            self._idle.get_nowait()
        for handle in list(self._connections):
            await handle.driver.close()
        self._connections.clear()
        self._checked_out.clear()
        self._size = 0

    @asynccontextmanager
    async def transaction(self):
        handle = await self.acquire()
        token = _current_connection.set(handle)
        try:
            async with handle.driver.transaction():
                yield handle.driver
        finally:
            _current_connection.reset(token)
            await self.release(handle)

    # --- Builders (no requieren conexión) ---
    def insert(
        self,
        tabla: str,
        data: dict,
        ignore_duplicated=False,
        replace=False,
        conflict: list[str] | None = None,
        *,
        schema: str | None = None,
        returning: str | None = None,
    ):
        # B3: reenvía `returning` al template; sin esto, un `Model.insert` con
        # `_get_db()` siendo un `PoolDb` no capturaría el id (lo necesita 04-06).
        return self._template.insert(
            tabla,
            data,
            ignore_duplicated,
            replace,
            conflict,
            schema=schema,
            returning=returning,
        )

    def delete(self, tabla: str, keys: dict, *, schema: str | None = None):
        return self._template.delete(tabla, keys, schema=schema)

    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None):
        return self._template.update(tabla, keys, values, schema=schema)

    # --- introspección ---
    def _tables_sql(self) -> str:
        return self._template._tables_sql()

    async def columns_of(self, table: str):
        return await self._run("columns_of", table)

    async def _ensure_migrations_table(self):
        """Delega en el template: permite reconciliar antes del primer `migrate()`."""
        return await self._run("_ensure_migrations_table")

    # --- Delegación ---
    async def _run(self, method: str, *args):
        handle = _current_connection.get()
        if handle is not None:
            return await getattr(handle.driver, method)(*args)
        handle = await self.acquire()
        try:
            return await getattr(handle.driver, method)(*args)
        finally:
            # dejar la conexión limpia antes de devolverla al pool: si la
            # operación dejó una transacción abierta (SQLite/MySQL no
            # autocommit), se confirma para que sea visible entre conexiones.
            if await handle.driver.in_transaction():
                await handle.driver.commit()
            await self.release(handle)

    async def _run_scoped(self, method: str, *args):
        handle = _current_connection.get()
        if handle is None:
            raise ConnectionError(f"{method}() solo es válido dentro de pool.transaction()")
        return await getattr(handle.driver, method)(*args)

    async def is_alive(self):
        return await self._run("is_alive")

    async def in_transaction(self):
        return await self._run("in_transaction")

    async def commit(self):
        raise ConnectionError(
            "commit() se gestiona con pool.transaction(); no lo llames directamente"
        )

    async def rollback(self, save_point: str | None = None):
        if save_point is None:
            raise ConnectionError(
                "rollback() se gestiona con pool.transaction(); no lo llames directamente"
            )
        return await self._run_scoped("rollback", save_point)

    async def save_point(self, name: str):
        return await self._run_scoped("save_point", name)

    async def execute(self, qry):
        handle = _current_connection.get()
        if handle is not None:
            return await handle.driver.execute(qry)
        handle = await self.acquire()
        try:
            return await handle.driver.execute(qry)
        finally:
            if await handle.driver.in_transaction():
                await handle.driver.commit()
            await self.release(handle)

    async def execute_insert(self, qry):
        """Ejecuta un INSERT capturando el id por conexión/tarea (POOL-03).

        Dentro de `transaction()` opera sobre la conexión retenida; fuera,
        `_run` adquiere, ejecuta, confirma y libera. El id sale del driver
        (`lastrowid`/`RETURNING`/`OUTPUT`/`RETURNING INTO`), nunca de un cache
        compartido entre tareas.
        """
        return await self._run("execute_insert", qry)

    async def fetch_all(self, qry):
        return await self._run("fetch_all", qry)

    async def fetch_one(self, qry):
        return await self._run("fetch_one", qry)

    async def fetch_many(self, qry, limit: int, page: int):
        return await self._run("fetch_many", qry, limit, page)

    async def exists(self, qry):
        return await self._run("exists", qry)

    async def last_id(self):
        """DEPRECADO: usa `PoolDb.execute_insert(qry)`.

        Emite el MISMO `DeprecationWarning` centralizado que el `last_id()` de
        `Db` (helper de `.base`) y, dentro de una transacción, delega en el id por
        conexión/tarea del handle retenido; fuera devuelve 0.
        """
        _warn_last_id_deprecated()
        handle = _current_connection.get()
        if handle is not None:
            return await handle.driver._last_id_value()
        # Sin cache a nivel de pool: fuera de una transacción no hay una
        # conexión/tarea a la que asociar el id, así que se devuelve 0.
        return 0

    async def migrate(self, name: str, qry):
        return await self._run("migrate", name, qry)

    async def migrate_status(self):
        return await self._run("migrate_status")


async def create_db(engine: str | Engine, **kwargs) -> Db:
    """Factory asíncrona. ``engine`` ∈ {'sqlite', 'mysql', 'mariadb',
    'postgresql', 'mssql', 'oracle'} (o `Engine`)."""
    db = _get_engine_cls(engine)()
    await db.connect(**kwargs)
    return db


@asynccontextmanager
async def session(db):
    """Obtiene una conexión de un pool (o devuelve `db` tal cual si no es pool).

    Facilita el patrón de *dependency injection* por request en FastAPI. Al
    salir, confirma (o revierte ante excepción) para devolver la conexión limpia.
    Mientras dura el bloque, la conexión queda **vinculada como ambiente**
    (`bind`), de modo que un `Model` construido sin `db` resuelve a ella:

    ```python
    async with session(pool) as conn:
        await conn.execute(...)
        m = Model(...)     # resuelve `db` implícitamente a `conn`
    ```
    """
    if isinstance(db, PoolDb):
        handle = await db.acquire()
        try:
            with bind(handle.driver):
                yield handle.driver
        except Exception:
            if await handle.driver.in_transaction():
                await handle.driver.rollback()
            raise
        else:
            if await handle.driver.in_transaction():
                await handle.driver.commit()
        finally:
            await db.release(handle)
    else:
        with bind(db):
            yield db
