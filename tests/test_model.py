from typing import Annotated

import pytest
from pydantic import Field

from encinorm.query import Query
from encinorm.model import Column, FailOnUpdate, Filter, Model, ValidationError


class Agente(Model):
    _table = "agentes"
    agente: Annotated[str | None, Column(name="nombre")] = Field(default=None, min_length=3, max_length=50)
    monto: Annotated[float, Column(datatype="numeric")] = Field(ge=0, default=0.0)


DDL = (
    "CREATE TABLE agentes ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "nombre TEXT, monto REAL, "
    "enabled INTEGER DEFAULT 1, "
    "created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def agentes(connected_db):
    await connected_db.execute(Query(DDL, []))
    return connected_db


class TestInsertAndLoad:
    @pytest.mark.asyncio
    async def test_insert_returns_id_and_marks_exists(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=100)
        new_id = await a.insert()
        assert new_id == 1
        assert a.id == 1
        assert getattr(a, "__exists") is True
        assert getattr(a, "__dirties") == []

    @pytest.mark.asyncio
    async def test_load_hydrates_fields(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=100)
        await a.insert()

        b = Agente(agentes, id=1)
        b = await b.load()
        assert getattr(b, "__exists") is True
        assert b.agente == "Héctor"
        assert b.monto == 100.0

    @pytest.mark.asyncio
    async def test_load_not_found(self, agentes):
        b = Agente(agentes, id=999)
        b = await b.load()
        assert getattr(b, "__exists") is False
        assert getattr(b, "__dirties") == []

    @pytest.mark.asyncio
    async def test_load_uses_column_alias(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=1)
        await a.insert()
        row = await agentes.fetch_one(Query("SELECT nombre FROM agentes WHERE id = 1", []))
        assert row["nombre"] == "Héctor"


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_dirty_fields(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=100)
        await a.insert()

        b = Agente(agentes, id=1)
        b = await b.load()
        b.agente = "Héctor M."
        await b.update()

        c = Agente(agentes, id=1)
        c = await c.load()
        assert c.agente == "Héctor M."
        assert c.monto == 100.0

    @pytest.mark.asyncio
    async def test_update_empty_data_updates_all_except_id_and_created(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=100)
        await a.insert()

        b = Agente(agentes, id=1)
        b = await b.load()
        b.agente = "Nuevo"
        b.monto = 7.5
        await b.update(data=[])

        c = Agente(agentes, id=1)
        c = await c.load()
        assert c.agente == "Nuevo"
        assert c.monto == 7.5

    @pytest.mark.asyncio
    async def test_update_without_key_raises(self, agentes):
        b = Agente(agentes, agente="Sin id")
        b.agente = "Otro"
        with pytest.raises(FailOnUpdate):
            await b.update()


class TestDelete:
    @pytest.mark.asyncio
    async def test_delete_logical(self, agentes):
        a = Agente(agentes, agente="Héctor")
        await a.insert()

        b = Agente(agentes, id=1)
        b = await b.load()
        await b.delete()
        assert getattr(b, "__exists") is False

        rows = await agentes.fetch_all(Query("SELECT enabled FROM agentes WHERE id = 1", []))
        assert rows[0]["enabled"] == 0

    @pytest.mark.asyncio
    async def test_delete_physical(self, agentes):
        a = Agente(agentes, agente="Héctor")
        await a.insert()

        b = Agente(agentes, id=1)
        b = await b.load()
        await b.delete(physical=True)

        rows = await agentes.fetch_all(Query("SELECT * FROM agentes WHERE id = 1", []))
        assert rows == []


class TestSearch:
    @pytest.mark.asyncio
    async def _seed(self, agentes):
        for nombre, monto in [("Ana", 10), ("Luis", 50), ("María", 100)]:
            a = Agente(agentes, agente=nombre, monto=monto)
            await a.insert()

    @pytest.mark.asyncio
    async def test_search_ge(self, agentes):
        await self._seed(agentes)
        res = await Agente(agentes).search(Filter.ge("monto", 50))
        assert sorted(r.agente for r in res) == ["Luis", "María"]

    @pytest.mark.asyncio
    async def test_search_like_maps_column_name(self, agentes):
        await self._seed(agentes)
        res = await Agente(agentes).search(Filter.like("agente", "Lu"))
        assert [r.agente for r in res] == ["Luis"]

    @pytest.mark.asyncio
    async def test_search_and_or(self, agentes):
        await self._seed(agentes)
        f = Filter.gt("monto", 10) & Filter.lt("monto", 100)
        res = await Agente(agentes).search(f)
        assert sorted(r.agente for r in res) == ["Luis"]

    @pytest.mark.asyncio
    async def test_search_is_null(self, agentes):
        await agentes.execute(
            Query(
                "CREATE TABLE cosas (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "nota TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)",
                [],
            )
        )

        class Cosa(Model):
            _table = "cosas"
            nota: str | None = None

        await Cosa(agentes).insert()
        await Cosa(agentes, nota="x").insert()

        res = await Cosa(agentes).search(Filter.is_null("nota"))
        assert len(res) == 1
        assert res[0].nota is None


class TestValidate:
    @pytest.mark.asyncio
    async def test_validate_ok_returns_none(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=10)
        assert await a.validate() is None

    @pytest.mark.asyncio
    async def test_validate_reports_errors(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=10)
        object.__setattr__(a, "agente", "ab")   # viola min_length=3
        object.__setattr__(a, "monto", -5.0)    # viola ge=0
        errs = await a.validate()
        assert errs is not None
        assert "agente" in errs
        assert "monto" in errs

    @pytest.mark.asyncio
    async def test_insert_rejects_invalid(self, agentes):
        a = Agente(agentes, agente="Héctor", monto=10)
        object.__setattr__(a, "agente", "ab")   # viola min_length=3 (soft)
        object.__setattr__(a, "monto", -5.0)    # viola ge=0 (soft)
        with pytest.raises(ValidationError):
            await a.insert()
