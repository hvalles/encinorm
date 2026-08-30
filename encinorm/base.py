import asyncio
import logging
import random
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

logger = logging.getLogger("encinorm")


class Db(ABC):
    MAX_TRIES = 9
    WAITERS = [x * 0.02 for x in range(1, 11)]
    MAX_WAIT = len(WAITERS) - 1

    dialect: str = ""

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
    async def execute(self, qry): ...

    @abstractmethod
    async def fetch_all(self, qry): ...

    @abstractmethod
    async def fetch_one(self, qry): ...

    @abstractmethod
    async def fetch_many(self, qry, limit: int, page: int): ...

    @abstractmethod
    async def exists(self, qry): ...

    @abstractmethod
    async def last_id(self): ...

    @abstractmethod
    async def migrate(self, name: str, qry): ...

    @abstractmethod
    async def migrate_status(self): ...
