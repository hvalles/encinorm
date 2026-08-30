import pytest
from pydantic import Field

from encinorm.query import Query
from encinorm.model import CachedModel, MemoryCacheBackend


class Cliente(CachedModel):
    _table = "clientes"
    rfc: str | None = Field(default=None)
    nombre: str | None = Field(default=None)


DDL = (
    "CREATE TABLE clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT, nombre TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


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
