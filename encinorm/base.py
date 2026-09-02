import asyncio
import logging
import random
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

from .query import Query

logger = logging.getLogger("encinorm")


class Db(ABC):
    MAX_TRIES = 9
    WAITERS = [x * 0.02 for x in range(1, 11)]
    MAX_WAIT = len(WAITERS) - 1

    dialect: str = ""

    @property
    def fn(self):
        """Namespace de funciones SQL portables (`db.fn.now()`, `db.fn.date_add(...)`)."""
        from .sql import SqlFunctions

        return SqlFunctions(self.dialect)

    @abstractmethod
    async def connect(self, **kwargs): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    async def is_alive(self): ...

    @abstractmethod
    async def in_transaction(self): ...

    @asynccontextmanager
    async def transaction(self):
        try:
            yield
            await self.commit()
        except Exception:
            await self.rollback()
            raise

    @abstractmethod
    async def commit(self): ...

    @abstractmethod
    async def rollback(self, save_point: str = None): ...

    @abstractmethod
    async def save_point(self, name: str): ...

    @staticmethod
    async def wait(waiter: int = -1):
        """Mecanismo de espera en caso de bloqueo por deadlock en la base de datos."""
        if waiter < 0:
            waiter = random.randint(0, Db.MAX_WAIT)
        await asyncio.sleep(Db.WAITERS[waiter])
        return waiter

    def is_lock_error(self, exc: Exception) -> bool:
        """Indica si `exc` corresponde a un error de bloqueo/deadlock re-reintentable."""
        return False

    async def retry(self, coro, tries: int = None):
        """Reintenta una coroutine ante errores de bloqueo (deadlock)."""
        max_tries = tries if tries is not None else self.MAX_TRIES
        last_exc = None
        for attempt in range(max_tries):
            try:
                return await coro()
            except Exception as exc:
                if not self.is_lock_error(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_tries:
                    break
                await self.wait()
        raise last_exc

    @abstractmethod
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False): ...

    @abstractmethod
    def delete(self, tabla: str, keys: dict): ...

    @abstractmethod
    def update(self, tabla: str, keys: dict, values: dict): ...

    @abstractmethod
    async def execute(self, qry: Query): ...

    @abstractmethod
    async def fetch_all(self, qry: Query): ...

    @abstractmethod
    async def fetch_one(self, qry: Query): ...

    @abstractmethod
    async def fetch_many(self, qry: Query, limit: int, page: int): ...

    @abstractmethod
    async def exists(self, qry: Query): ...

    @abstractmethod
    async def last_id(self): ...

    @abstractmethod
    async def migrate(self, name: str, qry: Query): ...

    @abstractmethod
    async def migrate_status(self): ...

    def _tables_sql(self) -> str:
        """SQL base que lista las tablas del catálogo (por motor).

        Opcional: los motores que no lo implementen no soportan `list_tables`.
        """
        raise NotImplementedError("introspección no soportada para este motor")

    async def columns_of(self, table: str) -> list:
        """Devuelve la especificación de columnas de una tabla (por motor).

        Opcional: los motores que no lo implementen no soportan `columns_of`.
        """
        raise NotImplementedError("introspección no soportada para este motor")

    async def list_tables(self, *, name: str = "", limit: int = 50, page: int = 1):
        """Lista las tablas del catálogo con filtro por nombre y paginación."""
        from .model.records import Records

        sql = self._tables_sql()
        params = []
        if name:
            sql += " AND name LIKE {0}"
            params.append(f"%{name}%")
        total = (await self.fetch_one(Query(f"SELECT COUNT(*) FROM ({sql})", params)))["COUNT(*)"]
        rows = await self.fetch_many(Query(sql, params), limit, page)
        return Records(rows=rows, total=total, limit=limit, page=page)

    async def paginate(self, qry: Query, limit: int, page: int = 1):
        """Devuelve un `Records` con la página y el total de un `Query` raw.

        El total se calcula envolviendo el SQL en
        ``SELECT COUNT(*) AS n FROM (...)``, por lo que solo es fiable para
        SELECT simples (sin ``;`` final, sin su propio ``LIMIT``/``OFFSET`` y sin
        cláusulas no re-embebibles como ``FOR UPDATE``). Conviene incluir
        ``ORDER BY`` en el SQL para una paginación estable.
        """
        from .model.records import Records

        rows = await self.fetch_many(qry, limit, page)
        sql = qry.sql_template.strip().rstrip(";")
        count_qry = Query(
            f"SELECT COUNT(*) AS n FROM ({sql}) _encinorm_count", list(qry.fields)
        )
        row = await self.fetch_one(count_qry)
        total = row["n"] if row else 0
        return Records(rows=rows, total=total, limit=limit, page=page)
