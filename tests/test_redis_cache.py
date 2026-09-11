import os

import pytest

from encino_orm import Query
from encino_orm.model import CachedModel, RedisCacheBackend

REDIS_URL = os.getenv("ENCINO_ORM_REDIS_URL", "redis://127.0.0.1:6379")


class ClienteRedis(CachedModel):
    _table = "clientes_redis"
    rfc: str | None = None
    nombre: str | None = None


DDL = (
    "CREATE TABLE clientes_redis (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT, "
    "nombre TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def redis_cache():
    try:
        import redis.asyncio as redis
    except ImportError:
        pytest.skip("redis no instalado; usa el extra 'cache'")

    client = redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception as e:
        await client.aclose()
        pytest.skip(f"Redis no disponible: {e}")

    backend = RedisCacheBackend(url=REDIS_URL)
    backend._client = client
    yield backend
    await client.aclose()


class TestRedisCacheBackend:
    @pytest.mark.asyncio
    async def test_set_get_delete(self, redis_cache):
        await redis_cache.set("encino:test:k1", b"valor-1", 60)
        assert await redis_cache.get("encino:test:k1") == b"valor-1"
        await redis_cache.delete("encino:test:k1")
        assert await redis_cache.get("encino:test:k1") is None

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, redis_cache):
        assert await redis_cache.get("encino:test:noexiste") is None


class TestCachedModelRedis:
    @pytest.mark.asyncio
    async def test_load_populates_and_hits_redis(self, connected_db, redis_cache):
        await connected_db.execute(Query(DDL, []))
        await ClienteRedis(connected_db, rfc="XAXX010101000", nombre="Héctor").insert()

        c1 = ClienteRedis(connected_db, rfc="XAXX010101000", cache=redis_cache)
        obj = await c1.load(keys=["rfc"], duration=600)
        assert obj.nombre == "Héctor"
        key = c1._cache_key(["rfc"])
        try:
            assert await redis_cache.get(key) is not None

            # borrar de la BD -> la segunda carga debe servirse desde Redis
            await connected_db.execute(
                Query("DELETE FROM clientes_redis WHERE rfc = {0}", ["XAXX010101000"])
            )
            c2 = ClienteRedis(connected_db, rfc="XAXX010101000", cache=redis_cache)
            obj2 = await c2.load(keys=["rfc"], duration=600)
            assert obj2.nombre == "Héctor"
            assert getattr(obj2, "__exists") is True
        finally:
            await redis_cache.delete(key)
