import asyncio

import pytest

from encinorm import (
    ConnectionError,
    PoolDb,
    bind,
    create_db,
    resolve_db,
    session,
    set_default_db,
)
from encinorm.model import Model


@pytest.fixture(autouse=True)
def _clean_default():
    yield
    set_default_db(None)


class User(Model):
    _table = "users"
    name: str | None = None


class TestDefaultDb:
    @pytest.mark.asyncio
    async def test_model_resolves_default_db(self, connected_db):
        set_default_db(connected_db)
        await User(connected_db).create_table()

        u = User(name="ana")
        await u.insert()
        assert u.id is not None

        rows = await User().search()
        assert len(rows) == 1
        assert rows[0].name == "ana"

    @pytest.mark.asyncio
    async def test_insert_many_without_db(self, connected_db):
        set_default_db(connected_db)
        await User(connected_db).create_table()
        await User.insert_many(rows=[{"name": "a"}, {"name": "b"}])
        assert await User().count() == 2

    @pytest.mark.asyncio
    async def test_explicit_db_wins(self, connected_db):
        set_default_db(connected_db)
        assert User(connected_db)._get_db() is connected_db

    @pytest.mark.asyncio
    async def test_error_without_connection(self):
        u = User(name="x")
        with pytest.raises(ConnectionError):
            await u.insert()


class TestBind:
    @pytest.mark.asyncio
    async def test_bind_sets_ambient(self, connected_db):
        with bind(connected_db):
            assert resolve_db() is connected_db
        with pytest.raises(ConnectionError):
            resolve_db()

    @pytest.mark.asyncio
    async def test_bind_wins_over_default(self, connected_db):
        set_default_db(connected_db)
        other = await create_db("sqlite", database=":memory:")
        try:
            with bind(other):
                assert resolve_db() is other
            assert resolve_db() is connected_db
        finally:
            await other.close()


class TestSession:
    @pytest.fixture
    async def pool(self, tmp_path):
        p = PoolDb("sqlite", min_size=1, max_size=1, database=str(tmp_path / "m.db"))
        await p.connect()
        yield p
        await p.close()

    @pytest.mark.asyncio
    async def test_session_binds_connection(self, pool):
        await User(pool).create_table()
        async with session(pool) as conn:
            u = User(name="bob")
            assert u._get_db() is conn
            await u.insert()
            assert await User().count() == 1

    @pytest.mark.asyncio
    async def test_concurrent_binds_do_not_cross(self, tmp_path):
        db_a = await create_db("sqlite", database=str(tmp_path / "a.db"))
        db_b = await create_db("sqlite", database=str(tmp_path / "b.db"))
        await User(db_a).create_table()
        await User(db_b).create_table()
        try:
            async def work(db, name):
                with bind(db):
                    u = User(name=name)
                    await u.insert()
                    rows = await User().search()
                    assert [r.name for r in rows] == [name]

            await asyncio.gather(work(db_a, "a"), work(db_b, "b"))
        finally:
            await db_a.close()
            await db_b.close()
