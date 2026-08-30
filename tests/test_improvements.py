from typing import Annotated

import pytest
from pydantic import Field

from encinorm import Query, SqliteDb
from encinorm.model import Column, Model


class Agente(Model):
    _table = "agentes"
    agente: Annotated[str | None, Column(name="nombre")] = Field(default=None, min_length=3, max_length=50)
    monto: Annotated[float, Column(datatype="numeric")] = Field(ge=0, default=0.0)


class Region(Model):
    _table = "regiones"
    region: str | None = Field(default=None)


class AgenteRegion(Model):
    _table = "agentes_r"
    agente: str | None = Field(default=None)
    region_id: int | None = None


AGENTE_DDL = (
    "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, monto REAL, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def agentes(connected_db):
    await connected_db.execute(Query(AGENTE_DDL, []))
    return connected_db


class TestColumnMapCache:
    def test_cached(self):
        assert Agente._column_map() is Agente._column_map()


class TestValidateIncremental:
    @pytest.mark.asyncio
    async def test_fields_subset(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=10)
        object.__setattr__(a, "monto", -5.0)
        errs = await a.validate(fields=["monto"])
        assert errs is not None
        assert "monto" in errs
        assert "agente" not in errs


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_on_lock_error(self, monkeypatch):
        db = SqliteDb()

        async def no_sleep(*a, **k):
            return 0

        monkeypatch.setattr(db, "wait", no_sleep)

        calls = {"n": 0}

        async def op():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception("database is locked")
            return "ok"

        result = await db.retry(op, tries=5)
        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_retry_stops_on_non_lock_error(self, monkeypatch):
        db = SqliteDb()

        async def no_sleep(*a, **k):
            return 0

        monkeypatch.setattr(db, "wait", no_sleep)

        async def op():
            raise ValueError("no es bloqueo")

        with pytest.raises(ValueError):
            await db.retry(op, tries=3)

    def test_is_lock_error(self):
        db = SqliteDb()
        assert db.is_lock_error(Exception("database is locked")) is True
        assert db.is_lock_error(Exception("otro")) is False


class TestQueryAndCreateTable:
    @pytest.mark.asyncio
    async def test_create_table_and_query(self, connected_db):
        class P(Model):
            _table = "p"
            nombre: str | None = None

        p = P(connected_db)
        await p.create_table()

        rows = await connected_db.fetch_all(
            Query("SELECT name FROM sqlite_master WHERE type='table' AND name='p'", [])
        )
        assert len(rows) == 1

        qb = p.query()
        assert qb._model_class is P
        assert qb._db is connected_db


class TestExistsDirtiesProperties:
    @pytest.mark.asyncio
    async def test_properties(self, agentes):
        a = Agente(agentes, agente="Héctor")
        assert a._exists is False
        assert a._dirties == ["agente"]


class TestIdentifierValidation:
    def test_invalid_table_raises(self):
        class Bad(Model):
            _table = "bad; DROP TABLE x"
            nombre: str | None = None

        with pytest.raises(ValueError):
            Bad._column_map()

    def test_invalid_column_raises(self):
        class Bad2(Model):
            _table = "t"
            nombre: Annotated[str, Column(name="bad; col")] = None

        with pytest.raises(ValueError):
            Bad2._column_map()


class TestBatchReference:
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
                "CREATE TABLE agentes_r (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
                "region_id INTEGER, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)",
                [],
            )
        )
        return connected_db

    @pytest.mark.asyncio
    async def test_batch_reference(self, db):
        rid1 = await Region(db, region="Norte").insert()
        rid2 = await Region(db, region="Sur").insert()
        a1 = AgenteRegion(db, agente="a", region_id=rid1)
        await a1.insert()
        a2 = AgenteRegion(db, agente="b", region_id=rid2)
        await a2.insert()

        a1.add_reference("region", Region, {"id": "region_id"})
        a2.add_reference("region", Region, {"id": "region_id"})

        await AgenteRegion.batch_reference([a1, a2], "region")

        assert (await a1["region"]).region == "Norte"
        assert (await a2["region"]).region == "Sur"
