import pytest

from encinorm.query import Query
from encinorm.model import (
    Model,
    after_commit,
    after_transaction_fail,
    before_commit,
    before_delete,
    before_insert,
    before_update,
)


DDL = (
    "CREATE TABLE pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, total REAL, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(DDL, []))
    return connected_db


class TestHooks:
    @pytest.mark.asyncio
    async def test_hooks_run_in_order(self, db):
        calls = []

        class Pedido(Model):
            _table = "pedidos"
            total: float = 0.0

            @before_insert
            async def _bi(self):
                calls.append("before_insert")

            @before_commit
            async def _bc(self, action):
                calls.append(f"before_commit:{action}")

            @after_commit
            async def _ac(self):
                calls.append("after_commit")

        p = Pedido(db, total=10)
        await p.insert()
        assert calls == ["before_insert", "before_commit:insert", "after_commit"]

    @pytest.mark.asyncio
    async def test_before_commit_raise_rolls_back(self, db):
        class P(Model):
            _table = "pedidos"
            total: float = 0.0

            @before_commit
            async def _bc(self, action):
                raise RuntimeError("boom")

        p = P(db, total=10)
        with pytest.raises(RuntimeError):
            await p.insert()

        rows = await db.fetch_all(Query("SELECT * FROM pedidos", []))
        assert rows == []

    @pytest.mark.asyncio
    async def test_after_transaction_fail(self, db):
        calls = []

        class P(Model):
            _table = "pedidos"
            total: float = 0.0

            @before_commit
            async def _bc(self, action):
                raise RuntimeError("boom")

            @after_transaction_fail
            async def _atf(self, action):
                calls.append(f"fail:{action}")

        p = P(db, total=10)
        with pytest.raises(RuntimeError):
            await p.insert()
        assert calls == ["fail:insert"]

    @pytest.mark.asyncio
    async def test_update_and_delete_hooks(self, db):
        calls = []

        class P(Model):
            _table = "pedidos"
            total: float = 0.0

            @before_update
            async def _bu(self):
                calls.append("before_update")

            @before_delete
            async def _bd(self):
                calls.append("before_delete")

            @before_commit
            async def _bc(self, action):
                calls.append(f"bc:{action}")

        p = P(db, total=10)
        await p.insert()
        calls.clear()

        q = P(db, id=1)
        q = await q.load()
        q.total = 20
        await q.update()
        assert calls == ["before_update", "bc:update"]

        calls.clear()
        await q.delete()
        assert calls == ["before_delete", "bc:delete"]
