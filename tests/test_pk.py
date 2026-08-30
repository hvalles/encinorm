import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from encinorm.graphql import build_schema
from encinorm.http import create_crud, install_error_handlers
from encinorm.introspection.codegen import generate_model
from encinorm.model import Model
from encinorm.model.types import to_ddl
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


class Product(Model):
    _table = "products"
    _primary_key = ("sku",)
    _fields_disabled = ["id"]
    sku: str | None = None
    name: str | None = None


class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "code")
    _fields_disabled = ["id"]
    tenant_id: int | None = None
    code: str | None = None
    role: str | None = None


class AuditLog(Model):
    _table = "audit_logs"
    _fields_disabled = ["id"]
    tenant_id: int | None = None
    code: str | None = None
    detail: str | None = None
    _references_def = {
        "membership": {
            "model": Membership,
            "match_keys": {"tenant_id": "tenant_id", "code": "code"},
            "on_delete": "cascade",
        },
    }


Membership._has_many_def = {
    "logs": {"model": AuditLog, "foreign_key": {"tenant_id": "tenant_id", "code": "code"}},
}


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


class TestNaturalPk:
    def test_ddl(self):
        ddl = to_ddl(Product, "sqlite")
        assert "PRIMARY KEY (sku)" in ddl
        assert "AUTOINCREMENT" not in ddl

    @pytest.mark.asyncio
    async def test_crud_by_natural_key(self, db):
        await Product(db).create_table()

        assert await Product(db, sku="A", name="x").insert() == 0
        got = await Product(db, sku="A").load()
        assert got._exists and got.name == "x"

        got.name = "y"
        await got.update()
        assert (await Product(db, sku="A").load()).name == "y"

        await Product(db, sku="A").delete()
        got = await Product(db, sku="A").load()
        assert got._exists and got.enabled is False


class TestCompositePk:
    def test_ddl(self):
        ddl = to_ddl(Membership, "sqlite")
        assert "PRIMARY KEY (tenant_id, code)" in ddl

    @pytest.mark.asyncio
    async def test_crud(self, db):
        await Membership(db).create_table()

        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        got = await Membership(db, tenant_id=7, code="admin").load()
        assert got._exists and got.role == "owner"

        got.role = "super"
        await got.update()

        assert (await Membership(db, tenant_id=7, code="admin").load()).role == "super"

        await Membership(db, tenant_id=7, code="admin", role="x").upsert()
        assert (await Membership(db, tenant_id=7, code="admin").load()).role == "x"

        await Membership(db, tenant_id=7, code="admin", role="final").save()
        assert await Membership(db).count() == 1
        assert (await Membership(db, tenant_id=7, code="admin").load()).role == "final"

        await Membership(db, tenant_id=7, code="admin").delete()
        assert await Membership(db).count() == 0

    @pytest.mark.asyncio
    async def test_load_by_string_keys(self, db):
        await Membership(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        got = await Membership(db, tenant_id=7, code="admin").load(keys="tenant_id,code")
        assert got._exists


class TestCompositeFk:
    @pytest.mark.asyncio
    async def test_reference_resolution(self, db):
        await Membership(db).create_table()
        await AuditLog(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        log = AuditLog(db, tenant_id=7, code="admin", detail="login")
        await log.insert()

        m = await log["membership"]
        assert m._exists and m.role == "owner"

    @pytest.mark.asyncio
    async def test_fk_ddl(self):
        ddl = to_ddl(AuditLog, "sqlite")
        assert (
            "FOREIGN KEY (tenant_id, code) REFERENCES memberships (tenant_id, code)"
            in ddl
        )

    @pytest.mark.asyncio
    async def test_has_many_composite(self, db):
        await Membership(db).create_table()
        await AuditLog(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        await AuditLog(db, tenant_id=7, code="admin", detail="login").insert()
        await AuditLog(db, tenant_id=7, code="admin", detail="logout").insert()

        m = await Membership(db, tenant_id=7, code="admin").load()
        logs = await m["logs"]
        assert {lg.detail for lg in logs} == {"login", "logout"}

    @pytest.mark.asyncio
    async def test_batch_reference_composite(self, db):
        await Membership(db).create_table()
        await AuditLog(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        await AuditLog(db, tenant_id=7, code="admin", detail="login").insert()

        logs = await AuditLog(db).search()
        await AuditLog.batch_reference(logs, "membership")
        m = await logs[0]["membership"]
        assert m.role == "owner"

    @pytest.mark.asyncio
    async def test_batch_has_many_composite(self, db):
        await Membership(db).create_table()
        await AuditLog(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()
        await AuditLog(db, tenant_id=7, code="admin", detail="login").insert()

        memberships = await Membership(db).search()
        await Membership.batch_has_many(memberships, "logs")
        logs = await memberships[0]["logs"]
        assert [lg.detail for lg in logs] == ["login"]


class TestRestComposite:
    @pytest.mark.asyncio
    async def test_crud(self, db):
        await Membership(db).create_table()
        app = FastAPI()
        install_error_handlers(app)
        app.include_router(create_crud(db, [Membership], prefix="/api"))

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/api/memberships/", json={"tenant_id": 7, "code": "admin", "role": "owner"}
            )
            assert r.status_code == 201

            r = await client.get("/api/memberships/7/admin")
            assert r.status_code == 200
            assert r.json()["role"] == "owner"

            r = await client.put("/api/memberships/7/admin", json={"role": "super"})
            assert r.status_code == 200
            assert r.json()["role"] == "super"


class TestGraphqlComposite:
    @pytest.mark.asyncio
    async def test_get_composite(self, db):
        await Membership(db).create_table()
        await Membership(db, tenant_id=7, code="admin", role="owner").insert()

        schema = build_schema([Membership, AuditLog])
        result = await schema.execute(
            '{ membership(tenant_id: 7, code: "admin") { role } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert result.data["membership"]["role"] == "owner"


class TestCodegen:
    @pytest.mark.asyncio
    async def test_generate_composite_pk(self, db, tmp_path):
        await db.execute(Query(
            "CREATE TABLE memberships (tenant_id INTEGER NOT NULL, code TEXT NOT NULL, "
            "role TEXT, PRIMARY KEY (tenant_id, code))", []
        ))
        path = await generate_model(db, "memberships", folder=str(tmp_path))
        text = path.read_text(encoding="utf-8")
        assert "_primary_key = ('tenant_id', 'code')" in text
        assert "'id'" in text  # _fields_disabled incluye id (ausente en la tabla)
