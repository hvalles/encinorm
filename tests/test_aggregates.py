import pytest

from encinorm.model import Filter, Model
from encinorm.sqlite import SqliteDb


class Venta(Model):
    _table = "ventas"
    monto: float | None = None
    region_id: int | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Venta(d).create_table()
    yield d
    await d.close()


class TestAggregates:
    @pytest.mark.asyncio
    async def test_avg_min_max(self, db):
        for monto, rid in [(10.0, 1), (20.0, 1), (30.0, 2)]:
            await Venta(db, monto=monto, region_id=rid).insert()

        q = Venta(db).query().where(Filter.eq("region_id", 1))
        assert await q.sum("monto") == 30.0
        assert await q.avg("monto") == 15.0
        assert await q.min("monto") == 10.0
        assert await q.max("monto") == 20.0

    @pytest.mark.asyncio
    async def test_aggregates_empty_return_none(self, db):
        q = Venta(db).query().where(Filter.eq("region_id", 999))
        assert await q.avg("monto") is None
        assert await q.min("monto") is None
        assert await q.max("monto") is None

    @pytest.mark.asyncio
    async def test_invalid_column_raises(self, db):
        q = Venta(db).query()
        with pytest.raises(ValueError):
            await q.max("monto; DROP TABLE ventas")
