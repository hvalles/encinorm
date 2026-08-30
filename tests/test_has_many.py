import pytest

from encinorm.model import DuplicateReferenceError, Model
from encinorm.sqlite import SqliteDb


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Region(Model):
    _table = "regiones"
    region: str | None = None
    _has_many_def = {
        "agentes": {"model": Agente, "foreign_key": "region_id"},
    }


class RegionPlain(Model):
    _table = "regiones"
    region: str | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Region(d).create_table()
    await Agente(d).create_table()
    yield d
    await d.close()


class TestHasMany:
    @pytest.mark.asyncio
    async def test_has_many_def(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()
        await Agente(db, agente="b", region_id=rid).insert()

        r = Region(db, id=rid)
        agentes = await r["agentes"]
        assert len(agentes) == 2
        assert {a.agente for a in agentes} == {"a", "b"}

    @pytest.mark.asyncio
    async def test_add_has_many_explicit(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()

        r = RegionPlain(db, id=rid)
        r.add_has_many("agentes", Agente, "region_id")
        agentes = await r["agentes"]
        assert len(agentes) == 1
        assert agentes[0].agente == "a"

    @pytest.mark.asyncio
    async def test_has_many_on_loaded(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()

        r = await Region(db, id=rid).load()
        agentes = await r["agentes"]
        assert len(agentes) == 1
        assert agentes[0].agente == "a"

    @pytest.mark.asyncio
    async def test_has_many_on_search_results(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()

        regiones = await Region(db).search()
        assert len(regiones) == 1
        agentes = await regiones[0]["agentes"]
        assert len(agentes) == 1

    @pytest.mark.asyncio
    async def test_empty_has_many(self, db):
        rid = await Region(db, region="Norte").insert()
        r = Region(db, id=rid)
        assert await r["agentes"] == []

    @pytest.mark.asyncio
    async def test_batch_has_many(self, db):
        rid1 = await Region(db, region="Norte").insert()
        rid2 = await Region(db, region="Sur").insert()
        await Agente(db, agente="a", region_id=rid1).insert()
        await Agente(db, agente="b", region_id=rid1).insert()
        await Agente(db, agente="c", region_id=rid2).insert()

        regiones = await Region(db).search()
        await Region.batch_has_many(regiones, "agentes")

        by_id = {r.id: r for r in regiones}
        assert len(await by_id[rid1]["agentes"]) == 2
        assert len(await by_id[rid2]["agentes"]) == 1
        # caché por instancia -> sin consulta extra
        assert len(await by_id[rid1]["agentes"]) == 2


class TestHasManyErrors:
    @pytest.mark.asyncio
    async def test_duplicate_has_many(self, db):
        r = Region(db, region="x")
        with pytest.raises(DuplicateReferenceError):
            r.add_has_many("agentes", Agente, "region_id")

    @pytest.mark.asyncio
    async def test_field_collision(self, db):
        r = RegionPlain(db, region="x")
        with pytest.raises(DuplicateReferenceError):
            r.add_has_many("region", Agente, "region_id")

    @pytest.mark.asyncio
    async def test_reference_and_has_many_collision(self, db):
        r = RegionPlain(db, region="x")
        r.add_reference("agentes", Agente, {"id": "region_id"})
        with pytest.raises(DuplicateReferenceError):
            r.add_has_many("agentes", Agente, "region_id")
