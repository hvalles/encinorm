from typing import Annotated

import pytest
from pydantic import Field

from encinorm.query import Query
from encinorm.model import Column, DuplicateReferenceError, Model


class Region(Model):
    _table = "regiones"
    region: Annotated[str | None, Column(name="region")] = Field(default=None)


class Agente(Model):
    _table = "agentes"
    agente: str | None = Field(default=None)
    region_id: int | None = None


REGION_DDL = (
    "CREATE TABLE regiones (id INTEGER PRIMARY KEY AUTOINCREMENT, region TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)
AGENTE_DDL = (
    "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
    "region_id INTEGER, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(REGION_DDL, []))
    await connected_db.execute(Query(AGENTE_DDL, []))
    return connected_db


class TestReferences:
    @pytest.mark.asyncio
    async def test_lazy_load(self, db):
        r = Region(db, region="Norte")
        rid = await r.insert()
        a = Agente(db, agente="x", region_id=rid)
        await a.insert()

        a.add_reference("region", Region, {"id": "region_id"})
        reg = await a["region"]
        assert reg.region == "Norte"

    @pytest.mark.asyncio
    async def test_reinit_on_key_change(self, db):
        rid1 = await Region(db, region="Norte").insert()
        rid2 = await Region(db, region="Sur").insert()
        a = Agente(db, agente="x", region_id=rid1)
        await a.insert()

        a.add_reference("region", Region, {"id": "region_id"})
        reg1 = await a["region"]
        assert reg1.region == "Norte"

        a.region_id = rid2
        reg2 = await a["region"]
        assert reg2.region == "Sur"

    @pytest.mark.asyncio
    async def test_duplicate_reference_name(self, db):
        a = Agente(db, agente="x")
        a.add_reference("region", Region, {"id": "region_id"})
        with pytest.raises(DuplicateReferenceError):
            a.add_reference("region", Region, {"id": "region_id"})

    @pytest.mark.asyncio
    async def test_reference_field_collision(self, db):
        a = Agente(db, agente="x")
        with pytest.raises(DuplicateReferenceError):
            a.add_reference("agente", Region, {"id": "region_id"})


class TestOnDeleteForeignKey:
    """El borrado en cascada se delega en la FK del DDL (semántica SQL)."""

    @pytest.fixture
    async def db(self, connected_db):
        return connected_db

    @pytest.mark.asyncio
    async def test_cascade_physical_delete(self, db):
        class Padre(Model):
            _table = "padres"
            nombre: str | None = Field(default=None)

        class Hija(Model):
            _table = "hijas"
            padre_id: int | None = None
            _references_def = {
                "padre": {"model": Padre, "match_keys": {"id": "padre_id"}, "on_delete": "cascade"},
            }

        await Padre(db).create_table()
        await Hija(db).create_table()

        pid = await Padre(db, nombre="p").insert()
        await Hija(db, padre_id=pid).insert()

        p = Padre(db, id=pid)
        p = await p.load()
        await p.delete(physical=True)

        rows = await db.fetch_all(Query("SELECT * FROM hijas", []))
        assert rows == []
