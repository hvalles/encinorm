import pytest
from pydantic import Field

from encino_orm.model import CachedModel, MemoryCacheBackend
from encino_orm.query import Query


class Cliente(CachedModel):
    _table = "clientes"
    rfc: str | None = Field(default=None)
    nombre: str | None = Field(default=None)


DDL = (
    "CREATE TABLE clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT UNIQUE, nombre TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


class _FailingDeleteCache:
    """Backend cuyo `delete` siempre falla; prueba el fail-open de D-12."""

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        raise RuntimeError("backend caído")


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(DDL, []))
    return connected_db


class TestCachedModel:
    @pytest.mark.asyncio
    async def test_load_populates_cache(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await c.load(keys=["rfc"], duration=600)
        assert obj.nombre == "Héctor"
        assert getattr(obj, "__exists") is True
        assert len(cache._store) == 1

    @pytest.mark.asyncio
    async def test_load_hits_cache(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c1 = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c1.load(keys=["rfc"])

        # borrar de la BD para demostrar que se sirve desde caché
        await db.execute(Query("DELETE FROM clientes WHERE rfc = {0}", ["XAXX010101000"]))

        c2 = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await c2.load(keys=["rfc"])
        assert obj.nombre == "Héctor"
        assert getattr(obj, "__exists") is True

    @pytest.mark.asyncio
    async def test_cache_key_sha1(self, db):
        c = Cliente(db, rfc="XAXX010101000")
        key = c._cache_key(["rfc"])
        assert isinstance(key, str)
        assert len(key) == 40  # sha1 hexdigest

    @pytest.mark.asyncio
    async def test_update_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        c.nombre = "Nuevo"
        await c.update(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

        fresh = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await fresh.load(keys=["rfc"])
        assert obj.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_delete_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        await c.delete(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

    @pytest.mark.asyncio
    async def test_upsert_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", nombre="Otro", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        await c.upsert(conflict=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

        fresh = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await fresh.load(keys=["rfc"])
        assert obj.nombre == "Otro"

    @pytest.mark.asyncio
    async def test_invalidate_fail_open(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        c = Cliente(db, rfc="XAXX010101000", cache=_FailingDeleteCache())
        c.nombre = "Nuevo"
        count = await c.update(keys=["rfc"])
        assert count == 1

        row = await db.fetch_one(
            Query("SELECT nombre FROM clientes WHERE rfc = {0}", ["XAXX010101000"])
        )
        assert row["nombre"] == "Nuevo"
