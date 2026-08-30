import pytest
from pydantic import Field

from encinorm import Query
from encinorm.model import Filter, Model, QueryBuilder, Records


class Item(Model):
    _table = "items"
    nombre: str | None = Field(default=None)


@pytest.fixture
async def db(connected_db):
    await Item(connected_db).create_table()
    for nombre in ["aaa", "bbb", "ccc", "ddd", "eee"]:
        await Item(connected_db, nombre=nombre).insert()
    return connected_db


class TestRecordsProperties:
    def test_total_pages(self):
        assert Records(total=10, limit=2, page=1).total_pages == 5
        assert Records(total=9, limit=2, page=1).total_pages == 5
        assert Records(total=0, limit=0, page=1).total_pages == 1

    def test_has_next_prev(self):
        assert Records(total=10, limit=2, page=1).has_next is True
        assert Records(total=10, limit=2, page=5).has_next is False
        assert Records(total=10, limit=2, page=2).has_prev is True
        assert Records(total=10, limit=2, page=1).has_prev is False


class TestQueryBuilderPaginate:
    @pytest.mark.asyncio
    async def test_paginate(self, db):
        rec = await QueryBuilder(Item, db).select("nombre").order_by("nombre").paginate(limit=2, page=2)
        assert rec.total == 5
        assert rec.limit == 2
        assert rec.page == 2
        assert [r["nombre"] for r in rec.rows] == ["ccc", "ddd"]
        assert rec.total_pages == 3
        assert rec.has_next is True


class TestModelPaginate:
    @pytest.mark.asyncio
    async def test_paginate(self, db):
        rec = await Item(db).paginate(limit=2, page=1)
        assert rec.total == 5
        assert len(rec.rows) == 2
        assert rec.total_pages == 3
        assert rec.has_prev is False

    @pytest.mark.asyncio
    async def test_paginate_with_filter(self, db):
        rec = await Item(db).paginate(Filter.like("nombre", "b"), limit=2, page=1)
        assert rec.total == 1
        assert len(rec.rows) == 1
        assert rec.rows[0].nombre == "bbb"
