import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from encinorm.http import (
    Registry,
    create_crud,
    filter_from_str,
    install_error_handlers,
    register_crud,
    register_introspection,
    sort_from_str,
)
from encinorm.model import Filter, Model, make_constraint
from encinorm.sqlite import SqliteDb

STR_50 = make_constraint(str, max_length=50)


class Region(Model):
    _table = "regiones"
    region: str | None = None


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Ciudad(Model):
    _table = "ciudades"
    nombre: STR_50(required=True)


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Region(d).create_table()
    await Agente(d).create_table()
    await Ciudad(d, nombre="tmp").create_table()
    yield d
    await d.close()


def _make_app(d, models):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_crud(d, models, prefix="/api"))
    return app


class TestParsing:
    def test_sort_from_str(self):
        assert sort_from_str("-region_id,agente") == ["-region_id", "agente"]
        assert sort_from_str("") == []
        assert sort_from_str(" agente , -region_id ") == ["agente", "-region_id"]

    def test_filter_from_str_empty(self):
        assert filter_from_str("") is None
        assert filter_from_str("   ") is None

    def test_filter_from_str_ops(self):
        f = filter_from_str('{"agente":{"like":"Héc"},"region_id":{"ge":1}}')
        assert isinstance(f, Filter)
        sql, params = f.to_sql()
        assert "LIKE" in sql and ">=" in sql
        assert params == ["%Héc%", 1]

    def test_filter_from_str_and_or_not(self):
        f = filter_from_str('{"or":[{"region_id":1},{"agente":{"like":"Héc"}}]}')
        sql, _ = f.to_sql()
        assert "OR" in sql

        f = filter_from_str('{"and":[{"region_id":{"ge":1}},{"region_id":{"le":5}}]}')
        sql, _ = f.to_sql()
        assert "AND" in sql

        f = filter_from_str('{"not":{"region_id":1}}')
        sql, _ = f.to_sql()
        assert "NOT" in sql

    def test_filter_from_str_between_is_null(self):
        f = filter_from_str('{"region_id":{"between":[1,3]}}')
        sql, params = f.to_sql()
        assert "BETWEEN" in sql and params == [1, 3]

        f = filter_from_str('{"region_id":{"is_null":true}}')
        sql, _ = f.to_sql()
        assert "IS NULL" in sql


class TestRegistry:
    def test_register_get_names(self):
        r = Registry()
        r.register(Region)
        r.register(Agente)
        assert r.names() == ["agentes", "regiones"]
        assert r.get("agentes") is Agente
        with pytest.raises(KeyError):
            r.get("inexistente")


class TestModelSort:
    @pytest.mark.asyncio
    async def test_search_sort_by(self, db):
        for nombre, rid in [("a", 2), ("b", 3), ("c", 1)]:
            await Agente(db, agente=nombre, region_id=rid).insert()

        rows = await Agente(db).search(sort_by=["-region_id"])
        assert [r.region_id for r in rows] == [3, 2, 1]

        rows = await Agente(db).search(sort_by=["region_id"])
        assert [r.region_id for r in rows] == [1, 2, 3]


class TestCrudIntegration:
    @pytest.mark.asyncio
    async def test_create_and_get(self, db):
        app = _make_app(db, [Region, Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/api/agentes/", json={"agente": "Héctor", "region_id": 1})
            assert r.status_code == 201
            assert r.json()["agente"] == "Héctor"
            assert r.json()["id"] == 1

            r = await client.get("/api/agentes/1")
            assert r.status_code == 200
            assert r.json()["agente"] == "Héctor"

    @pytest.mark.asyncio
    async def test_get_404(self, db):
        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/agentes/999")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list_filter_sort_paginate(self, db):
        for nombre, rid in [("Héctor", 2), ("Ana", 3), ("Héctor", 1)]:
            await Agente(db, agente=nombre, region_id=rid).insert()

        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(
                "/api/agentes/",
                params={"filter": '{"agente":{"like":"Héc"}}', "sort_by": "-region_id"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["total"] == 2
            assert data["limit"] == 50
            assert data["page"] == 1
            nombres = [row["agente"] for row in data["rows"]]
            assert nombres == ["Héctor", "Héctor"]
            regiones = [row["region_id"] for row in data["rows"]]
            assert regiones == [2, 1]

    @pytest.mark.asyncio
    async def test_update(self, db):
        await Agente(db, agente="Héctor", region_id=1).insert()

        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.put("/api/agentes/1", json={"agente": "Héctor M."})
            assert r.status_code == 200
            assert r.json()["agente"] == "Héctor M."
            # region_id no se envió -> se conserva
            assert r.json()["region_id"] == 1

    @pytest.mark.asyncio
    async def test_update_404(self, db):
        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.put("/api/agentes/999", json={"agente": "x"})
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_logical(self, db):
        await Agente(db, agente="Héctor", region_id=1).insert()

        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.delete("/api/agentes/1")
            assert r.status_code == 200
            assert r.json() == {"id": 1, "deleted": True}

            r = await client.get("/api/agentes/1")
            assert r.status_code == 200
            assert r.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_delete_physical(self, db):
        await Agente(db, agente="Héctor", region_id=1).insert()

        app = _make_app(db, [Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.delete("/api/agentes/1", params={"physical": "true"})
            assert r.status_code == 200

            r = await client.get("/api/agentes/1")
            assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_create_validation_422(self, db):
        app = _make_app(db, [Ciudad])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/api/ciudades/", json={})
            assert r.status_code == 422

            r = await client.post("/api/ciudades/", json={"nombre": "Querétaro"})
            assert r.status_code == 201
            assert r.json()["nombre"] == "Querétaro"

    @pytest.mark.asyncio
    async def test_introspection(self, db):
        app = _make_app(db, [Region, Agente])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/models")
            assert r.status_code == 200
            assert r.json() == ["agentes", "regiones"]

            r = await client.get("/api/models/agentes")
            assert r.status_code == 200
            assert "agente" in r.json()["properties"]

            r = await client.get("/api/models/inexistente")
            assert r.status_code == 404
