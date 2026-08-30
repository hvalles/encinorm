from contextlib import asynccontextmanager

import pytest
from pydantic import Field

import encinorm.pool as pool_module
from encinorm import ConnectionError, PoolDb, PoolExhaustedError, Query, create_db
from encinorm.model import Model


class FakeDb:
    def __init__(self):
        self.connected = False
        self.closed = False
        self.calls = []
        self._last = 0
        self._in_tx = False

    @property
    def is_connected(self):
        return self.connected

    async def connect(self, **kwargs):
        self.connected = True

    async def close(self):
        self.closed = True
        self.connected = False

    async def is_alive(self):
        return self.connected

    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("begin",))
        try:
            yield self
            self.calls.append(("commit",))
            self._in_tx = False
        except Exception:
            self.calls.append(("rollback",))
            self._in_tx = False
            raise

    def insert(self, tabla, data, ignore_duplicated=False, replace=False):
        return f"INSERT {tabla} {data}"

    def delete(self, tabla, keys):
        return f"DELETE {tabla} {keys}"

    def update(self, tabla, keys, values):
        return f"UPDATE {tabla} {keys} {values}"

    async def fetch_all(self, qry):
        self.calls.append(("fetch_all", qry))
        return [{"q": qry}]

    async def execute(self, qry):
        self.calls.append(("execute", qry))
        self._last = 42
        self._in_tx = True
        return 1

    async def last_id(self):
        self.calls.append(("last_id",))
        return self._last

    async def in_transaction(self):
        return self._in_tx

    async def commit(self):
        self.calls.append(("commit",))
        self._in_tx = False

    async def save_point(self, name):
        self.calls.append(("save_point", name))

    async def rollback(self, save_point=None):
        self.calls.append(("rollback", save_point))
        if save_point is None:
            self._in_tx = False


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb


@pytest.fixture
async def pool(fake_engine):
    p = PoolDb("fake", min_size=2, max_size=5)
    await p.connect()
    yield p
    await p.close()


class TestPool:
    @pytest.mark.asyncio
    async def test_connect_creates_min_size(self, pool):
        assert pool.is_connected is True
        assert pool._size == 2
        assert len(pool._connections) == 2

    @pytest.mark.asyncio
    async def test_acquire_release(self, pool):
        db = await pool.acquire()
        assert db.is_connected is True
        await pool.release(db)

    @pytest.mark.asyncio
    async def test_max_size_creates_and_reuses(self, pool):
        conns = [await pool.acquire() for _ in range(5)]
        assert pool._size == 5
        assert len(pool._connections) == 5

        await pool.release(conns[0])
        reused = await pool.acquire()
        assert reused is conns[0]

    @pytest.mark.asyncio
    async def test_delegation(self, pool):
        rows = await pool.fetch_all("SELECT 1")
        assert rows == [{"q": "SELECT 1"}]

    @pytest.mark.asyncio
    async def test_builders(self, pool):
        assert pool.insert("t", {"a": 1}) == "INSERT t {'a': 1}"
        assert pool.delete("t", {"id": 1}) == "DELETE t {'id': 1}"
        assert pool.update("t", {"id": 1}, {"a": 2}) == "UPDATE t {'id': 1} {'a': 2}"

    @pytest.mark.asyncio
    async def test_transaction_context(self, pool):
        async with pool.transaction() as db:
            assert db.is_connected is True

    @pytest.mark.asyncio
    async def test_close(self, pool):
        db = await pool.acquire()
        await pool.release(db)

        await pool.close()
        assert pool.is_connected is False
        assert pool._size == 0
        assert len(pool._connections) == 0
        assert db.closed is True


class TestPoolTransactionScope:
    @pytest.mark.asyncio
    async def test_operations_use_held_connection(self, pool):
        async with pool.transaction() as db:
            await pool.execute("INSERT 1")
            await pool.fetch_all("SELECT 1")
            rid = await pool.last_id()
        assert ("execute", "INSERT 1") in db.calls
        assert ("fetch_all", "SELECT 1") in db.calls
        assert ("last_id",) in db.calls
        assert rid == 42

    @pytest.mark.asyncio
    async def test_commit_raises(self, pool):
        with pytest.raises(ConnectionError):
            await pool.commit()

    @pytest.mark.asyncio
    async def test_full_rollback_raises(self, pool):
        with pytest.raises(ConnectionError):
            await pool.rollback()

    @pytest.mark.asyncio
    async def test_save_point_inside_transaction(self, pool):
        async with pool.transaction() as db:
            await pool.save_point("sp")
            await pool.rollback(save_point="sp")
        assert ("save_point", "sp") in db.calls
        assert ("rollback", "sp") in db.calls

    @pytest.mark.asyncio
    async def test_save_point_outside_raises(self, pool):
        with pytest.raises(ConnectionError):
            await pool.save_point("sp")


class TestPoolTimeout:
    @pytest.mark.asyncio
    async def test_acquire_timeout_raises(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()

        conn = await p.acquire()  # mantiene la única conexión
        with pytest.raises(PoolExhaustedError):
            await p.acquire(timeout=0.1)

        await p.release(conn)
        conn2 = await p.acquire(timeout=0.1)
        assert conn2 is conn
        await p.release(conn2)
        await p.close()


class TestPoolStandaloneCommit:
    @pytest.mark.asyncio
    async def test_standalone_operation_commits(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()

        await p.execute(Query("INSERT 1", []))

        conn = next(iter(p._connections))
        assert any(c == "execute" for c, _ in conn.calls)
        assert ("commit",) in conn.calls
        await p.close()

    @pytest.mark.asyncio
    async def test_acquire_replaces_dead_connection(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1, idle_timeout=None)
        await p.connect()

        dead = next(iter(p._connections))
        dead.connected = False  # simula conexión caída

        db = await p.acquire()
        assert db is not dead
        assert db.connected is True
        await p.release(db)
        await p.close()

    @pytest.mark.asyncio
    async def test_recently_used_skips_check(self, fake_engine):
        import time

        p = PoolDb("fake", min_size=1, max_size=1, idle_timeout=60)
        await p.connect()

        dead = next(iter(p._connections))
        dead.connected = False  # caída pero "reciente"
        db = await p.acquire()
        assert db is dead  # no se reemplaza por ser reciente
        await p.release(db)
        await p.close()

    @pytest.mark.asyncio
    async def test_idle_connection_is_replaced(self, fake_engine):
        import time

        p = PoolDb("fake", min_size=1, max_size=1, idle_timeout=60)
        await p.connect()

        dead = next(iter(p._connections))
        dead.connected = False
        p._last_used[dead] = time.monotonic() - 100  # 100s inactiva

        db = await p.acquire()
        assert db is not dead
        await p.release(db)
        await p.close()


class TestModelWithPool:
    @pytest.fixture
    async def sqlite_pool(self, tmp_path):
        db_file = tmp_path / "model.db"
        p = PoolDb("sqlite", min_size=1, max_size=3, database=str(db_file))
        await p.connect()
        yield p
        await p.close()

    @pytest.mark.asyncio
    async def test_insert_and_load(self, sqlite_pool):
        class Agente(Model):
            _table = "agentes"
            agente: str | None = Field(default=None)

        await sqlite_pool.migrate(
            "agentes",
            Query(
                "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "agente TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)",
                [],
            ),
        )

        a = Agente(sqlite_pool, agente="Héctor")
        new_id = await a.insert()
        assert new_id == 1

        b = Agente(sqlite_pool, id=1)
        b = await b.load()
        assert b.agente == "Héctor"


class TestPoolAutocommit:
    @pytest.fixture
    async def sqlite_pool(self, tmp_path):
        db_file = tmp_path / "autocommit.db"
        p = PoolDb("sqlite", min_size=2, max_size=5, database=str(db_file))
        await p.connect()
        yield p
        await p.close()

    @pytest.mark.asyncio
    async def test_dml_visible_across_connections(self, sqlite_pool):
        await sqlite_pool.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", [])
        )
        await sqlite_pool.execute(sqlite_pool.insert("t", {"nombre": "a"}))

        rows = await sqlite_pool.fetch_all(Query("SELECT * FROM t", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "a"


class TestCreateDbFactory:
    @pytest.mark.asyncio
    async def test_create_sqlite(self):
        db = await create_db("sqlite", database=":memory:")
        assert db.is_connected is True
        await db.close()

    def test_unsupported_engine(self):
        with pytest.raises(Exception):
            PoolDb("oracle")
