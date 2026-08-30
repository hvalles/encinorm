import logging

import pytest
from pydantic import Field

from encinorm import PoolDb, PoolExhaustedError, Query
from encinorm.model import Model


class TestG7SyncSchema:
    @pytest.mark.asyncio
    async def test_drop_missing_column(self, connected_db):
        class T1(Model):
            _table = "t"
            a: str | None = None
            b: str | None = None

        class T2(Model):
            _table = "t"
            a: str | None = None

        await T1(connected_db).create_table()
        result = await T2(connected_db).sync_schema(drop_missing=True)
        assert "b" in result["dropped"]

        rows = await connected_db.fetch_all(Query("PRAGMA table_info(t)", []))
        cols = {r["name"] for r in rows}
        assert "b" not in cols

    @pytest.mark.asyncio
    async def test_add_missing_column_report(self, connected_db):
        class T1(Model):
            _table = "t2"
            a: str | None = None

        class T2(Model):
            _table = "t2"
            a: str | None = None
            b: str | None = None

        await T1(connected_db).create_table()
        result = await T2(connected_db).sync_schema()
        assert result["added"] == ["b"]
        assert result["dropped"] == []


class TestG8Logging:
    @pytest.mark.asyncio
    async def test_query_is_logged(self, connected_db, caplog):
        caplog.set_level(logging.DEBUG, logger="encinorm")
        await connected_db.execute(Query("SELECT 1", []))
        assert any("sqlite" in r.getMessage() for r in caplog.records)


class TestG9PoolMetrics:
    @pytest.fixture
    async def pool(self, tmp_path):
        p = PoolDb("sqlite", min_size=1, max_size=1, database=str(tmp_path / "m.db"))
        await p.connect()
        yield p
        await p.close()

    @pytest.mark.asyncio
    async def test_stats(self, pool):
        assert pool.stats["creates"] == 1
        conn = await pool.acquire()
        assert pool.stats["acquires"] == 1
        await pool.release(conn)

    @pytest.mark.asyncio
    async def test_stats_timeout(self, pool):
        conn = await pool.acquire()
        with pytest.raises(PoolExhaustedError):
            await pool.acquire(timeout=0.1)
        assert pool.stats["timeouts"] == 1
        assert pool.stats["waits"] >= 1
        await pool.release(conn)
