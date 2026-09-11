import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from encino_orm.graphql import build_schema
from encino_orm.http import create_crud, install_error_handlers
from encino_orm.model import DEFAULT_LIMIT, MAX_LIMIT, Model, normalize_limit_page
from encino_orm.sqlite import SqliteDb


class Item(Model):
    _table = "items"
    nombre: str | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Item(d).create_table()
    yield d
    await d.close()


def _make_app(d, models):
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(create_crud(d, models, prefix="/api"))
    return app


class TestNormalizeLimitPage:
    def test_caps_to_max(self):
        assert normalize_limit_page(10_000, 1) == (MAX_LIMIT, 1)

    def test_zero_or_negative_limit(self):
        assert normalize_limit_page(0, 1) == (DEFAULT_LIMIT, 1)
        assert normalize_limit_page(-5, 1) == (DEFAULT_LIMIT, 1)

    def test_page_clamped(self):
        assert normalize_limit_page(10, 0) == (10, 1)
        assert normalize_limit_page(10, -3) == (10, 1)

    def test_none_preserved(self):
        assert normalize_limit_page(None, 1) == (None, 1)


class TestSearchClamp:
    @pytest.mark.asyncio
    async def test_search_caps_at_max(self, db):
        await Item.insert_many(db, [{"nombre": f"n{i}"} for i in range(1001)])
        rows = await Item(db).search(limit=10_000)
        assert len(rows) == MAX_LIMIT

    @pytest.mark.asyncio
    async def test_zero_and_negative_limit(self, db):
        for i in range(3):
            await Item(db, nombre=f"n{i}").insert()
        assert len(await Item(db).search(limit=0)) == 3
        assert len(await Item(db).search(limit=-5)) == 3

    @pytest.mark.asyncio
    async def test_page_zero(self, db):
        for i in range(3):
            await Item(db, nombre=f"n{i}").insert()
        rows = await Item(db).search(limit=2, page=0)
        assert [r.nombre for r in rows] == ["n0", "n1"]


class TestRestLimits:
    @pytest.mark.asyncio
    async def test_out_of_range_returns_422(self, db):
        app = _make_app(db, [Item])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/api/items/", params={"limit": 0})).status_code == 422
            assert (await client.get("/api/items/", params={"limit": 2000})).status_code == 422
            assert (await client.get("/api/items/", params={"page": 0})).status_code == 422

    @pytest.mark.asyncio
    async def test_valid_limit_ok(self, db):
        app = _make_app(db, [Item])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/items/", params={"limit": 100})
            assert r.status_code == 200
            assert r.json()["limit"] == 100


class TestGraphqlLimits:
    @pytest.fixture
    async def schema(self):
        return build_schema([Item])

    @pytest.mark.asyncio
    async def test_list_without_limit_defaults(self, db, schema):
        for i in range(60):
            await Item(db, nombre=f"n{i}").insert()
        result = await schema.execute("{ items { id } }", context_value={"db": db})
        assert result.errors is None
        assert len(result.data["items"]) == DEFAULT_LIMIT

    @pytest.mark.asyncio
    async def test_list_limit_capped(self, db, schema):
        for i in range(3):
            await Item(db, nombre=f"n{i}").insert()
        result = await schema.execute(
            "{ items(limit: 10000) { id } }", context_value={"db": db}
        )
        assert result.errors is None
        assert len(result.data["items"]) == 3
