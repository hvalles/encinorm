"""Snapshot OpenAPI del CRUD generado y validacion de path params (CFG-03).

Congela el contrato observable de las rutas ``get``/``put``/``delete`` que hoy se
construyen con ``exec()`` en ``encino_orm/http/routes.py``. El snapshot se
captura ANTES del rewrite a closures + ``__signature__``; tras el rewrite este
test debe pasar SIN ``--snapshot-update`` (diff cero). Un diff en el ``.ambr``
significa que el contrato observable cambio y el rewrite debe corregirse.

Se congela ``json.dumps(app.openapi(), indent=2, sort_keys=True)``: los paths,
los ``operationId``, los parametros (path/query) y los componentes que FastAPI
deriva de las firmas de los handlers. Es la red que prueba el Criterio de Exito
3 ("OpenAPI identica antes y despues, y los path params siguen validando").
"""

import json
from typing import ClassVar

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from encino_orm.http import create_crud, install_error_handlers
from encino_orm.model import Model
from encino_orm.sqlite import SqliteDb


class Region(Model):
    _table = "regiones"
    region: str | None = None


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "code")
    _fields_disabled: ClassVar[list] = ["id"]
    tenant_id: int | None = None
    code: str | None = None
    role: str | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Region(d).create_table()
    await Agente(d).create_table()
    await Membership(d).create_table()
    yield d
    await d.close()


def _make_app(d, models):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_crud(d, models, prefix="/api"))
    return app


@pytest.mark.asyncio
async def test_openapi_snapshot(db, snapshot):
    """El OpenAPI completo (PK simple y compuesta) queda congelado en el `.ambr`."""
    app = _make_app(db, [Region, Agente, Membership])
    assert snapshot == json.dumps(app.openapi(), indent=2, sort_keys=True)


@pytest.mark.asyncio
async def test_path_params_siguen_validando(db):
    """Los path params derivados de la PK siguen validando (int vs str)."""
    app = _make_app(db, [Agente, Membership])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # PK simple (`id` int): no numerico -> 422; valido inexistente -> 404.
        assert (await client.get("/api/agentes/abc")).status_code == 422
        assert (await client.get("/api/agentes/999")).status_code == 404

        await Agente(db, agente="Hector", region_id=1).insert()
        r = await client.get("/api/agentes/1")
        assert r.status_code == 200
        assert r.json()["agente"] == "Hector"

        # PK compuesta (`tenant_id` int + `code` str): primer segmento no
        # numerico -> 422; compuesta valida inexistente -> 404.
        assert (await client.get("/api/memberships/abc/2")).status_code == 422
        assert (await client.get("/api/memberships/7/admin")).status_code == 404

        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        r = await client.get("/api/memberships/7/admin")
        assert r.status_code == 200
        assert r.json()["role"] == "owner"


@pytest.mark.asyncio
async def test_contrato_operaciones(db):
    """Rutas, metodos y status codes no cambian (POST 201 / GET 200 / PUT / DELETE)."""
    app = _make_app(db, [Agente])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/agentes/", json={"agente": "Hector", "region_id": 1})
        assert r.status_code == 201
        pk = r.json()["id"]

        assert (await client.get("/api/agentes/")).status_code == 200

        r = await client.put(f"/api/agentes/{pk}", json={"agente": "Hector M."})
        assert r.status_code == 200
        assert r.json()["agente"] == "Hector M."

        r = await client.delete(f"/api/agentes/{pk}")
        assert r.status_code == 200
        assert r.json() == {"id": pk, "deleted": True}
