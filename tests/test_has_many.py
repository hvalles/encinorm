from datetime import datetime

import pytest

from encino_orm.model import (
    DuplicateReferenceError,
    Filter,
    Model,
    RelationshipError,
)
from encino_orm.sqlite import SqliteDb


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Order(Model):
    _table = "orders"
    codigo: str | None = None
    region_id: int | None = None
    fecha: datetime | None = None


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


class TestHasManyFilter:
    @pytest.mark.asyncio
    async def test_filter_eq(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()
        await Agente(db, agente="b", region_id=rid).insert()

        r = Region(db, id=rid)
        result = await r.has_many("agentes", filter=Filter.eq("agente", "a"))
        assert len(result) == 1
        assert result[0].agente == "a"

    @pytest.mark.asyncio
    async def test_filter_startswith_and_endswith(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="alfa", region_id=rid).insert()
        await Agente(db, agente="algo", region_id=rid).insert()
        await Agente(db, agente="beta", region_id=rid).insert()
        await Agente(db, agente="batez", region_id=rid).insert()

        r = Region(db, id=rid)
        a = await r.has_many("agentes", filter=Filter.startswith("agente", "al"))
        assert {x.agente for x in a} == {"alfa", "algo"}

        z = await r.has_many("agentes", filter=Filter.endswith("agente", "ez"))
        assert {x.agente for x in z} == {"batez"}

    @pytest.mark.asyncio
    async def test_filter_and_or_composition(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="ana", region_id=rid).insert()
        await Agente(db, agente="alberto", region_id=rid).insert()
        await Agente(db, agente="berta", region_id=rid).insert()

        r = Region(db, id=rid)
        # AND: empieza por "a" y termina en "o"
        f = Filter.startswith("agente", "a") & Filter.endswith("agente", "o")
        res = await r.has_many("agentes", filter=f)
        assert {x.agente for x in res} == {"alberto"}

        # OR: empieza por "a" o por "b"
        f = Filter.startswith("agente", "a") | Filter.startswith("agente", "b")
        res = await r.has_many("agentes", filter=f)
        assert {x.agente for x in res} == {"ana", "alberto", "berta"}

    @pytest.mark.asyncio
    async def test_filter_combines_with_foreign_key(self, db):
        rid1 = await Region(db, region="Norte").insert()
        rid2 = await Region(db, region="Sur").insert()
        await Agente(db, agente="a1", region_id=rid1).insert()
        await Agente(db, agente="a2", region_id=rid1).insert()
        await Agente(db, agente="b1", region_id=rid2).insert()

        r = Region(db, id=rid1)
        result = await r.has_many("agentes", filter=Filter.startswith("agente", "a"))
        assert {x.agente for x in result} == {"a1", "a2"}

    @pytest.mark.asyncio
    async def test_filter_date_range(self, db):
        await Order(db).create_table()
        rid = await Region(db, region="Norte").insert()
        await Order(db, codigo="ago1", region_id=rid, fecha=datetime(2026, 8, 10)).insert()
        await Order(db, codigo="ago2", region_id=rid, fecha=datetime(2026, 8, 25)).insert()
        await Order(db, codigo="sep1", region_id=rid, fecha=datetime(2026, 9, 1)).insert()

        r = Region(db, id=rid)
        r.add_has_many("orders", Order, "region_id")
        agosto = await r.has_many(
            "orders",
            filter=Filter.between(
                "fecha", datetime(2026, 8, 1), datetime(2026, 8, 31, 23, 59, 59)
            ),
        )
        assert {o.codigo for o in agosto} == {"ago1", "ago2"}

    @pytest.mark.asyncio
    async def test_filter_limit_and_sort(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()
        await Agente(db, agente="b", region_id=rid).insert()
        await Agente(db, agente="c", region_id=rid).insert()

        r = Region(db, id=rid)
        page = await r.has_many("agentes", limit=2, page=1, sort_by=["agente"])
        assert [x.agente for x in page] == ["a", "b"]

        page2 = await r.has_many("agentes", limit=2, page=2, sort_by=["agente"])
        assert [x.agente for x in page2] == ["c"]

    @pytest.mark.asyncio
    async def test_filter_cache_isolated(self, db):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="a", region_id=rid).insert()
        await Agente(db, agente="b", region_id=rid).insert()

        r = Region(db, id=rid)
        solo_a = await r.has_many("agentes", filter=Filter.eq("agente", "a"))
        assert len(solo_a) == 1

        # una petición filtrada distinta no reutiliza el resultado anterior
        solo_b = await r.has_many("agentes", filter=Filter.eq("agente", "b"))
        assert len(solo_b) == 1
        assert solo_b[0].agente == "b"

        # y la carga completa sigue devolviendo todo (no contamina el caché)
        todos = await r["agentes"]
        assert len(todos) == 2

    @pytest.mark.asyncio
    async def test_unknown_relation(self, db):
        rid = await Region(db, region="Norte").insert()
        r = Region(db, id=rid)
        with pytest.raises(RelationshipError):
            await r.has_many("inexistente")

    @pytest.mark.asyncio
    async def test_batch_has_many_extra(self, db):
        rid1 = await Region(db, region="Norte").insert()
        rid2 = await Region(db, region="Sur").insert()
        await Agente(db, agente="a1", region_id=rid1).insert()
        await Agente(db, agente="a2", region_id=rid1).insert()
        await Agente(db, agente="b1", region_id=rid2).insert()
        await Agente(db, agente="b2", region_id=rid2).insert()

        regiones = await Region(db).search()
        await Region.batch_has_many(regiones, "agentes", extra=Filter.startswith("agente", "a"))

        by_id = {r.id: r for r in regiones}
        assert {x.agente for x in await by_id[rid1].has_many("agentes", filter=Filter.startswith("agente", "a"))} == {"a1", "a2"}
        # el filtro no cachea por padre, así que la carga completa sigue intacta
        assert len(await by_id[rid2]["agentes"]) == 2
