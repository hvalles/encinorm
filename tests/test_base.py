import pytest

from encinorm.base import Db
from encinorm.exceptions import (
    ConnectionError,
    EncinormError,
    MigrationError,
    PoolExhaustedError,
)
from encinorm.mysql import MysqlDb
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


@pytest.fixture(params=[SqliteDb, MysqlDb])
def unconnected_db(request):
    return request.param()


class TestDbWait:
    @pytest.mark.asyncio
    async def test_wait_returns_valid_index(self):
        waiter = await Db.wait()
        assert 0 <= waiter <= Db.MAX_WAIT

        waiter = await Db.wait(3)
        assert waiter == 3


class TestDbExceptions:
    def test_exceptions_subclass_encinorm(self):
        for exc in (ConnectionError, MigrationError, PoolExhaustedError):
            assert issubclass(exc, EncinormError)


class TestDbWithoutConnection:
    def test_ensure_connected_raises(self, unconnected_db):
        with pytest.raises(ConnectionError):
            unconnected_db._ensure_connected()

    @pytest.mark.asyncio
    async def test_close_when_not_connected_does_not_raise(self, unconnected_db):
        await unconnected_db.close()

    @pytest.mark.asyncio
    async def test_save_point_and_rollback_not_connected_no_op(self, unconnected_db):
        await unconnected_db.save_point("sp1")
        await unconnected_db.rollback(save_point="sp1")


class TestDbTransaction:
    @pytest.mark.asyncio
    async def test_transaction_commits_on_success(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE test_tx_ctx (id INTEGER PRIMARY KEY, valor TEXT)", [])
        )
        await connected_db.commit()

        async with connected_db.transaction():
            await connected_db.execute(
                connected_db.insert("test_tx_ctx", {"valor": "tx_success"})
            )

        rows = await connected_db.fetch_all(Query("SELECT valor FROM test_tx_ctx", []))
        assert len(rows) == 1
        assert rows[0]["valor"] == "tx_success"

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_exception(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE test_tx_err (id INTEGER PRIMARY KEY, valor TEXT)", [])
        )
        await connected_db.commit()

        try:
            async with connected_db.transaction():
                await connected_db.execute(
                    connected_db.insert("test_tx_err", {"valor": "before_error"})
                )
                raise RuntimeError("fallo simulado")
        except RuntimeError:
            pass

        rows = await connected_db.fetch_all(Query("SELECT valor FROM test_tx_err", []))
        assert len(rows) == 0
