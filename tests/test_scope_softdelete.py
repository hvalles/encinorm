import pytest

from encinorm.model import Filter, Model
from encinorm.model.scope import scope
from encinorm.sqlite import SqliteDb


class Item(Model):
    _table = "items"
    nombre: str | None = None


class Doc(Model):
    _table = "docs"
    tenant_id: int | None = None
    titulo: str | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Item(d).create_table()
    await Doc(d).create_table()
    yield d
    await d.close()


class TestSoftDelete:
    @pytest.mark.asyncio
    async def test_search_hides_deleted(self, db):
        await Item(db, nombre="a").insert()
        await Item(db, nombre="b").insert()
        await (await Item(db, id=2).load()).delete()

        rows = await Item(db).search()
        assert [r.nombre for r in rows] == ["a"]

        rows = await Item(db).search(include_deleted=True)
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_count_include_deleted(self, db):
        await Item(db, nombre="a").insert()
        await Item(db, nombre="b").insert()
        await (await Item(db, id=1).load()).delete()

        assert await Item(db).count() == 1
        assert await Item(db).count(include_deleted=True) == 2

    @pytest.mark.asyncio
    async def test_load_returns_deleted(self, db):
        await Item(db, nombre="a").insert()
        await (await Item(db, id=1).load()).delete()
        loaded = await Item(db, id=1).load()
        assert loaded._exists is True
        assert loaded.enabled is False


class TestScope:
    @pytest.mark.asyncio
    async def test_scope_filters_search(self, db):
        await Doc(db, tenant_id=1, titulo="a").insert()
        await Doc(db, tenant_id=2, titulo="b").insert()

        with scope(Filter.eq("tenant_id", 1)):
            rows = await Doc(db).search()
            assert [r.titulo for r in rows] == ["a"]
            assert await Doc(db).count() == 1

        rows = await Doc(db).search()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_scope_and_softdelete_combine(self, db):
        await Doc(db, tenant_id=1, titulo="a").insert()
        await Doc(db, tenant_id=1, titulo="b").insert()
        await (await Doc(db, id=2).load()).delete()

        with scope(Filter.eq("tenant_id", 1)):
            rows = await Doc(db).search()
            assert [r.titulo for r in rows] == ["a"]

    @pytest.mark.asyncio
    async def test_scope_paginate(self, db):
        for i in range(3):
            await Doc(db, tenant_id=1, titulo=f"a{i}").insert()
        await Doc(db, tenant_id=2, titulo="otro").insert()

        with scope(Filter.eq("tenant_id", 1)):
            rec = await Doc(db).paginate(limit=10, page=1)
            assert rec.total == 3
            assert len(rec.rows) == 3
