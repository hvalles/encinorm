from typing import Annotated

import pytest
from pydantic import Field

from encinorm import PoolDb, Query, SqliteDb, session
from encinorm.base import Db
from encinorm.model import Column, Model


class Agente(Model):
    _table = "agentes"
    agente: Annotated[str | None, Column(name="nombre")] = Field(default=None, min_length=3, max_length=50)
    monto: Annotated[float, Column(datatype="numeric")] = Field(ge=0, default=0.0)


class Region(Model):
    _table = "regiones"
    region: str | None = Field(default=None)


class AgenteDecl(Model):
    _table = "agentes_decl"
    agente: str | None = Field(default=None)
    region_id: int | None = None
    _references_def = {
        "region": {"model": Region, "match_keys": {"id": "region_id"}},
    }


AGENTE_DDL = (
    "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, monto REAL, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def agentes(connected_db):
    await connected_db.execute(Query(AGENTE_DDL, []))
    return connected_db


class TestD1TimestampsUtc:
    @pytest.mark.asyncio
    async def test_created_at_is_aware(self, agentes):
        a = Agente(agentes, agente="Héctor")
        await a.insert()
        assert a.created_at is not None
        assert a.created_at.tzinfo is not None
        assert a.updated_at.tzinfo is not None


class TestD2SanitizeQueryBuilder:
    def test_order_by_invalid_raises(self):
        with pytest.raises(ValueError):
            Agente(agentes).query().order_by("id; DROP TABLE x")

    def test_select_invalid_raises(self):
        with pytest.raises(ValueError):
            Agente(agentes).query().select("nombre; DROP TABLE x")


class TestD3LastIdStandalone:
    @pytest.fixture
    async def pool(self, tmp_path):
        p = PoolDb("sqlite", min_size=1, max_size=2, database=str(tmp_path / "d3.db"))
        await p.connect()
        yield p
        await p.close()

    @pytest.mark.asyncio
    async def test_last_id_after_standalone_insert(self, pool):
        await pool.execute(Query("CREATE TABLE u (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", []))
        await pool.execute(pool.insert("u", {"nombre": "x"}))
        assert await pool.last_id() == 1
        await pool.execute(pool.insert("u", {"nombre": "y"}))
        assert await pool.last_id() == 2


class TestD5SearchPagination:
    @pytest.mark.asyncio
    async def test_search_limit_page(self, agentes):
        for nombre in ["aaa", "bbb", "ccc", "ddd", "eee"]:
            a = Agente(agentes, agente=nombre)
            await a.insert()

        p1 = await Agente(agentes).search(limit=2, page=1)
        p2 = await Agente(agentes).search(limit=2, page=2)
        p3 = await Agente(agentes).search(limit=2, page=3)
        assert [a.agente for a in p1] == ["aaa", "bbb"]
        assert [a.agente for a in p2] == ["ccc", "ddd"]
        assert [a.agente for a in p3] == ["eee"]


class TestD6DeclarativeReferences:
    @pytest.fixture
    async def db(self, connected_db):
        await connected_db.execute(
            Query(
                "CREATE TABLE regiones (id INTEGER PRIMARY KEY AUTOINCREMENT, region TEXT, "
                "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)",
                [],
            )
        )
        await connected_db.execute(
            Query(
                "CREATE TABLE agentes_decl (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
                "region_id INTEGER, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)",
                [],
            )
        )
        return connected_db

    @pytest.mark.asyncio
    async def test_declarative_reference(self, db):
        rid = await Region(db, region="Norte").insert()
        a = AgenteDecl(db, agente="x", region_id=rid)
        await a.insert()

        region = await a["region"]
        assert region.region == "Norte"


class TestD7Session:
    @pytest.mark.asyncio
    async def test_session_with_pool(self, tmp_path):
        p = PoolDb("sqlite", min_size=1, max_size=2, database=str(tmp_path / "s.db"))
        await p.connect()
        async with session(p) as conn:
            await conn.execute(Query("CREATE TABLE s (id INTEGER PRIMARY KEY, x TEXT)", []))
        async with session(p) as conn:
            await conn.execute(conn.insert("s", {"x": "a"}))
            rows = await conn.fetch_all(Query("SELECT * FROM s", []))
            assert len(rows) == 1
        await p.close()

    @pytest.mark.asyncio
    async def test_session_with_single_db(self):
        db = SqliteDb()
        await db.connect(database=":memory:")
        async with session(db) as conn:
            assert conn is db
        await db.close()


class TestD4AutoRetry:
    @pytest.mark.asyncio
    async def test_retry_auto_applied_on_lock(self):
        class LockDb(Db):
            dialect = "fake"

            def __init__(self):
                self.executes = 0
                self.last = 0

            def is_lock_error(self, exc):
                return "locked" in str(exc)

            async def wait(self, waiter=-1):
                return 0

            async def connect(self, **kw): ...
            async def close(self): ...
            async def is_alive(self): return True
            async def in_transaction(self): return False
            async def commit(self): ...
            async def rollback(self, save_point=None): ...
            async def save_point(self, name): ...
            def insert(self, tabla, data, ignore_duplicated=False, replace=False):
                return ("INSERT", tabla, data)
            def delete(self, tabla, keys):
                return ("DELETE", tabla)
            def update(self, tabla, keys, values):
                return ("UPDATE", tabla)
            async def execute(self, qry):
                self.executes += 1
                if self.executes == 1:
                    raise Exception("database is locked")
                self.last = 7
                return 1
            async def fetch_all(self, qry): return []
            async def fetch_one(self, qry): return None
            async def fetch_many(self, qry, limit, page): return []
            async def exists(self, qry): return False
            async def last_id(self): return self.last
            async def migrate(self, name, qry): ...
            async def migrate_status(self): return []

        db = LockDb()

        class P(Model):
            _table = "p"
            nombre: str | None = None

        p = P(db, nombre="x")
        new_id = await p.insert()
        assert db.executes == 2
        assert new_id == 7
