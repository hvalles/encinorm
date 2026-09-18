import pytest

import encino_orm.model.cache_backend as cache_backend
from encino_orm.model import MemoryCacheBackend


class TestMemoryCacheBackend:
    @pytest.mark.asyncio
    async def test_lru_evicts_least_recently_used(self):
        cache = MemoryCacheBackend(max_size=2)
        await cache.set("a", b"A", 0)
        await cache.set("b", b"B", 0)

        # leer "a" la vuelve la más recientemente usada
        assert await cache.get("a") == b"A"

        # insertar "c" desaloja "b" (la menos usada), no "a"
        await cache.set("c", b"C", 0)

        assert await cache.get("b") is None
        assert await cache.get("a") == b"A"
        assert await cache.get("c") == b"C"

    @pytest.mark.asyncio
    async def test_max_size_is_respected(self):
        cache = MemoryCacheBackend(max_size=3)
        for i in range(5):
            await cache.set(f"k{i}", b"v", 0)

        assert len(cache._store) == 3

    @pytest.mark.asyncio
    async def test_default_max_size_is_1024(self):
        assert MemoryCacheBackend()._max_size == 1024

    @pytest.mark.asyncio
    async def test_store_len_is_preserved(self):
        cache = MemoryCacheBackend()
        await cache.set("k", b"v", 60)

        assert len(cache._store) == 1

    @pytest.mark.asyncio
    async def test_delete_removes_key(self):
        cache = MemoryCacheBackend()
        await cache.set("k", b"v", 0)
        await cache.delete("k")

        assert await cache.get("k") is None
        assert len(cache._store) == 0

    @pytest.mark.asyncio
    async def test_expiration_still_works(self, monkeypatch):
        clock = {"now": 1000.0}
        monkeypatch.setattr(cache_backend.time, "monotonic", lambda: clock["now"])

        cache = MemoryCacheBackend()
        await cache.set("k", b"v", ttl=10)

        clock["now"] = 1005.0
        assert await cache.get("k") == b"v"

        clock["now"] = 1011.0
        assert await cache.get("k") is None
        assert len(cache._store) == 0
