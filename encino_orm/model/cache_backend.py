import time
from typing import Protocol


class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    async def delete(self, key: str) -> None: ...


class MemoryCacheBackend:
    """Backend en memoria para desarrollo y pruebas."""

    def __init__(self):
        self._store = {}

    async def get(self, key: str) -> bytes | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (value, expires_at)

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
