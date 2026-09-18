import time
from collections import OrderedDict
from typing import Protocol


class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    async def delete(self, key: str) -> None: ...


class MemoryCacheBackend:
    """Backend en memoria acotado, pensado solo para dev/test (NO para producción).

    El almacén está limitado por una política LRU: al superar ``max_size`` se desaloja la
    entrada menos recientemente usada (``get`` y ``set`` actualizan el orden de uso). Cada
    proceso mantiene su propia instancia, así que la invalidación es local y no distribuida;
    para producción usa ``RedisCacheBackend``, que acota y expira del lado del servidor.
    """

    def __init__(self, max_size: int = 1024):
        self._max_size = max_size
        self._store: OrderedDict[str, tuple[bytes, float | None]] = OrderedDict()

    async def get(self, key: str) -> bytes | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        # la entrada sigue viva: marcarla como la más recientemente usada
        self._store.move_to_end(key)
        return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (value, expires_at)
        self._store.move_to_end(key)
        # desaloja la menos recientemente usada hasta respetar la cota
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


class RedisCacheBackend:
    """Backend Redis (asíncrono). Requiere la dependencia opcional ``redis``."""

    def __init__(self, url: str = "redis://localhost", client=None):
        self._url = url
        self._client = client

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as redis

            self._client = redis.from_url(self._url)
        return self._client

    async def get(self, key: str) -> bytes | None:
        client = await self._get_client()
        return await client.get(key)

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        client = await self._get_client()
        await client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        client = await self._get_client()
        await client.delete(key)
