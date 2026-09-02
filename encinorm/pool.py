import asyncio
import contextvars
import time
from contextlib import asynccontextmanager

from .base import Db
from .context import bind
from .engine import Engine
from .exceptions import ConnectionError, PoolExhaustedError, UnsupportedEngineError
from .mysql import MysqlDb
from .postgresql import PostgresDb
from .sqlite import SqliteDb

_ENGINES = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "postgresql": PostgresDb,
}

# Conexión activa de la transacción en curso (por tarea/contexto). Permite que
# `PoolDb.execute/fetch/...` resuelvan a la MISMA conexión dentro de
# `transaction()`, garantizando atomicidad y `last_id()` correcto.
_current_connection = contextvars.ContextVar("encinorm_pool_connection", default=None)


def _get_engine_cls(engine):
    key = engine.value if isinstance(engine, Engine) else engine
    cls = _ENGINES.get(key)
    if cls is None:
        raise UnsupportedEngineError(engine)
    return cls


class PoolDb(Db):
    """Wrapper que administra un pool de conexiones para entornos concurrentes.

    Expone la misma interfaz `Db`; los métodos DML/DQL delegan en
    ``acquire() -> operación -> release()``. Dentro de ``transaction()``, las
    operaciones se ejecutan sobre la conexión mantenida (vía contextvar).
    """

    def __init__(self, engine: str | Engine, min_size: int = 2, max_size: int = 10,
                 idle_timeout: float | None = 60, **conn_kwargs):
        if isinstance(engine, Engine):
            engine = engine.value
        self._engine = engine
        self._engine_cls = _get_engine_cls(engine)
        self._min_size = min_size
        self._max_size = max_size
        self._idle_timeout = idle_timeout
        self._conn_kwargs = conn_kwargs
        self._template = self._engine_cls()
        self._pool = asyncio.Queue()
        self._connections = set()
        self._size = 0
        self._connected = False
        self._last_id = 0
        self._last_used = {}
        self._stats = {"acquires": 0, "waits": 0, "timeouts": 0, "creates": 0}

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def dialect(self) -> str:
        return self._engine

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
            db = await self._create_connection()
            self._connections.add(db)
            self._size += 1
            self._last_used[db] = time.monotonic()
            await self._pool.put(db)
        self._connected = True

    async def _create_connection(self) -> Db:
        db = self._engine_cls()
        await db.connect(**self._conn_kwargs)
        self._stats["creates"] += 1
        return db

    def _needs_check(self, db: Db) -> bool:
        if self._idle_timeout is None:
            return True
        last = self._last_used.get(db)
        if last is None:
            return True
        return time.monotonic() - last > self._idle_timeout

    async def acquire(self, timeout: float | None = None) -> Db:
        if not self._connected:
            raise ConnectionError("Pool no conectado")
        while True:
            try:
                db = self._pool.get_nowait()
            except asyncio.QueueEmpty:
                if self._size < self._max_size:
                    db = await self._create_connection()
                    self._connections.add(db)
                    self._size += 1
                    self._last_used[db] = time.monotonic()
                    self._stats["acquires"] += 1
                    return db
                self._stats["waits"] += 1
                if timeout is None:
                    db = await self._pool.get()
                    self._stats["acquires"] += 1
                    return db
                try:
                    db = await asyncio.wait_for(self._pool.get(), timeout=timeout)
                    self._stats["acquires"] += 1
                    return db
                except asyncio.TimeoutError:
                    self._stats["timeouts"] += 1
                    raise PoolExhaustedError(
                        f"Pool agotado tras {timeout}s de espera (max_size={self._max_size})"
                    )
            else:
                if not self._needs_check(db) or await db.is_alive():
                    self._stats["acquires"] += 1
                    return db
                self._connections.discard(db)
                self._size -= 1
                self._last_used.pop(db, None)
                await db.close()

    async def release(self, db: Db):
        self._last_used[db] = time.monotonic()
        await self._pool.put(db)

    async def close(self):
        self._connected = False
        while not self._pool.empty():
            self._pool.get_nowait()
        for db in list(self._connections):
            await db.close()
        self._connections.clear()
        self._size = 0
        self._last_used.clear()

    @asynccontextmanager
    async def transaction(self):
        db = await self.acquire()
        token = _current_connection.set(db)
        try:
            async with db.transaction():
                yield db
        finally:
            _current_connection.reset(token)
            await self.release(db)

    # --- Builders (no requieren conexión) ---
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False):
        return self._template.insert(tabla, data, ignore_duplicated, replace)

    def delete(self, tabla: str, keys: dict):
        return self._template.delete(tabla, keys)

    def update(self, tabla: str, keys: dict, values: dict):
        return self._template.update(tabla, keys, values)

    # --- introspección ---
    def _tables_sql(self) -> str:
        return self._template._tables_sql()

    async def columns_of(self, table: str):
        return await self._run("columns_of", table)

    # --- Delegación ---
    async def _run(self, method: str, *args):
        db = _current_connection.get()
        if db is not None:
            return await getattr(db, method)(*args)
        db = await self.acquire()
        try:
            return await getattr(db, method)(*args)
        finally:
            # dejar la conexión limpia antes de devolverla al pool: si la
            # operación dejó una transacción abierta (SQLite/MySQL no
            # autocommit), se confirma para que sea visible entre conexiones.
            if await db.in_transaction():
                await db.commit()
            await self.release(db)

    async def _run_scoped(self, method: str, *args):
        db = _current_connection.get()
        if db is None:
            raise ConnectionError(f"{method}() solo es válido dentro de pool.transaction()")
        return await getattr(db, method)(*args)

    async def is_alive(self):
        return await self._run("is_alive")

    async def in_transaction(self):
        return await self._run("in_transaction")

    async def commit(self):
        raise ConnectionError("commit() se gestiona con pool.transaction(); no lo llames directamente")

    async def rollback(self, save_point: str = None):
        if save_point is None:
            raise ConnectionError("rollback() se gestiona con pool.transaction(); no lo llames directamente")
        return await self._run_scoped("rollback", save_point)

    async def save_point(self, name: str):
        return await self._run_scoped("save_point", name)

    async def execute(self, qry):
        db = _current_connection.get()
        if db is not None:
            return await db.execute(qry)
        db = await self.acquire()
        try:
            result = await db.execute(qry)
            if qry.sql_template.lstrip().upper().startswith(("INSERT", "REPLACE")):
                self._last_id = await db.last_id()
            return result
        finally:
            if await db.in_transaction():
                await db.commit()
            await self.release(db)

    async def fetch_all(self, qry):
        return await self._run("fetch_all", qry)

    async def fetch_one(self, qry):
        return await self._run("fetch_one", qry)

    async def fetch_many(self, qry, limit: int, page: int):
        return await self._run("fetch_many", qry, limit, page)

    async def exists(self, qry):
        return await self._run("exists", qry)

    async def last_id(self):
        db = _current_connection.get()
        if db is not None:
            return await db.last_id()
        return self._last_id

    async def migrate(self, name: str, qry):
        return await self._run("migrate", name, qry)

    async def migrate_status(self):
        return await self._run("migrate_status")


async def create_db(engine: str | Engine, **kwargs) -> Db:
    """Factory asíncrona. ``engine`` ∈ {'sqlite', 'mysql', 'postgresql'} (o `Engine`)."""
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
