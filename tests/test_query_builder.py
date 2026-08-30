import pytest
from pydantic import Field

from encinorm.query import Query
from encinorm.model import Filter, Model, QueryBuilder, col


class Region(Model):
    _table = "regiones"
    region: str | None = Field(default=None)


class Agente(Model):
    _table = "agentes"
    agente: str | None = Field(default=None)
    region_id: int | None = None
    monto: float = 0.0


REGION_DDL = (
    "CREATE TABLE regiones (id INTEGER PRIMARY KEY AUTOINCREMENT, region TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)
AGENTE_DDL = (
    "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
    "region_id INTEGER, monto REAL, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(REGION_DDL, []))
    await connected_db.execute(Query(AGENTE_DDL, []))
    return connected_db


async def _seed(db):
    rid1 = await Region(db, region="Norte").insert()
    rid2 = await Region(db, region="Sur").insert()
    await Agente(db, agente="Ana", region_id=rid1, monto=10).insert()
    await Agente(db, agente="Luis", region_id=rid2, monto=50).insert()
    return rid1, rid2


class TestQueryBuilder:
    @pytest.mark.asyncio
    async def test_where_and_select(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).where(Filter.eq("enabled", 1)).select("agente").all()
        assert sorted(r["agente"] for r in rows) == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_join(self, db):
        await _seed(db)
        qb = QueryBuilder(Agente, db)
        qb.join(Region, "r", Filter.eq("mm.region_id", col("r.id")))
        rows = await qb.select("mm.agente", "r.region").where(Filter.eq("r.region", "Norte")).all()
        assert rows == [{"agente": "Ana", "region": "Norte"}]

    @pytest.mark.asyncio
    async def test_column_alias(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente AS nombre").order_by("agente").all()
        assert [r["nombre"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_order_and_limit_pagination(self, db):
        await _seed(db)
        p1 = await QueryBuilder(Agente, db).select("agente").order_by("agente").limit(1).all()
        p2 = await QueryBuilder(Agente, db).select("agente").order_by("agente").limit(1, page=2).all()
        assert [r["agente"] for r in p1] == ["Ana"]
        assert [r["agente"] for r in p2] == ["Luis"]

    @pytest.mark.asyncio
    async def test_count_sum_exists(self, db):
        await _seed(db)
        assert await QueryBuilder(Agente, db).count() == 2
        assert await QueryBuilder(Agente, db).sum("monto") == 60.0
        assert await QueryBuilder(Agente, db).where(Filter.eq("agente", "Ana")).exists() is True
        assert await QueryBuilder(Agente, db).where(Filter.eq("agente", "Zzz")).exists() is False

    @pytest.mark.asyncio
    async def test_join_subquery(self, db):
        await _seed(db)
        sub = QueryBuilder(Agente, db).where(Filter.gt("monto", 20))
        qb = QueryBuilder(Agente, db)
        qb.join_subquery(sub, None, Filter.eq("mm.id", col("sq1_mm.id")))
        rows = await qb.select("mm.agente").all()
        assert [r["agente"] for r in rows] == ["Luis"]


class TestSortBy:
    @pytest.mark.asyncio
    async def test_asc_default(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente").all()
        assert [r["agente"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_desc_string(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente desc").all()
        assert [r["agente"] for r in rows] == ["Luis", "Ana"]

    @pytest.mark.asyncio
    async def test_asc_string(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente asc").all()
        assert [r["agente"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_tuple_direction(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by(("agente", "desc")).all()
        assert [r["agente"] for r in rows] == ["Luis", "Ana"]

    @pytest.mark.asyncio
    async def test_multiple_fields(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("region_id", "agente").sort_by("region_id desc", "agente").all()
        assert [r["region_id"] for r in rows] == [2, 1]

    @pytest.mark.asyncio
    async def test_invalid_direction(self, db):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, db).sort_by("agente sideways")
