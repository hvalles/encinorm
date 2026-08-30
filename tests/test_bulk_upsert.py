import pytest

from encinorm.model import Model
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Usuario(Model):
    _table = "usuarios"
    email: str | None = None
    nombre: str | None = None


_USUARIOS_DDL = (
    "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "email TEXT UNIQUE, nombre TEXT, enabled INTEGER DEFAULT 1, "
    "created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


@pytest.fixture
async def agentes(db):
    await Agente(db).create_table()
    return db


@pytest.fixture
async def usuarios(db):
    await db.execute(Query(_USUARIOS_DDL, []))
    return db


class TestInsertMany:
    @pytest.mark.asyncio
    async def test_insert_many(self, agentes):
        total = await Agente.insert_many(agentes, [
            {"agente": "a", "region_id": 1},
            {"agente": "b", "region_id": 2},
            {"agente": "c", "region_id": 3},
        ])
        assert total == 3
        rows = await Agente(agentes).search()
        assert len(rows) == 3
        assert {r.agente for r in rows} == {"a", "b", "c"}

    @pytest.mark.asyncio
    async def test_insert_many_chunked(self, agentes):
        rows = [{"agente": f"a{i}"} for i in range(5)]
        total = await Agente.insert_many(agentes, rows, chunk=2)
        assert total == 5
        assert len(await Agente(agentes).search()) == 5

    @pytest.mark.asyncio
    async def test_insert_many_empty(self, agentes):
        assert await Agente.insert_many(agentes, []) == 0
        assert len(await Agente(agentes).search()) == 0


class TestSave:
    @pytest.mark.asyncio
    async def test_save_inserts_new(self, agentes):
        a = Agente(agentes, agente="Héctor")
        await a.save()
        assert a.id == 1
        assert len(await Agente(agentes).search()) == 1

    @pytest.mark.asyncio
    async def test_save_updates_existing(self, agentes):
        await Agente(agentes, agente="Héctor").insert()
        b = Agente(agentes, id=1, agente="Héctor M.")
        await b.save()
        rows = await Agente(agentes).search()
        assert len(rows) == 1
        assert rows[0].agente == "Héctor M."


class TestInsertFlags:
    @pytest.mark.asyncio
    async def test_ignore_duplicated(self, usuarios):
        await Usuario(usuarios, email="a@x.com", nombre="A").insert()
        await Usuario(usuarios, email="a@x.com", nombre="B").insert(ignore_duplicated=True)
        assert len(await Usuario(usuarios).search()) == 1

    @pytest.mark.asyncio
    async def test_replace(self, usuarios):
        await Usuario(usuarios, email="a@x.com", nombre="A").insert()
        await Usuario(usuarios, email="a@x.com", nombre="B").insert(replace=True)
        rows = await Usuario(usuarios).search()
        assert len(rows) == 1
        assert rows[0].nombre == "B"


class TestUpsert:
    @pytest.mark.asyncio
    async def test_upsert_insert_then_update(self, usuarios):
        await Usuario(usuarios, email="a@x.com", nombre="A").upsert(conflict=["email"])
        assert len(await Usuario(usuarios).search()) == 1

        await Usuario(usuarios, email="a@x.com", nombre="B").upsert(conflict=["email"])
        rows = await Usuario(usuarios).search()
        assert len(rows) == 1
        assert rows[0].nombre == "B"

    @pytest.mark.asyncio
    async def test_upsert_with_explicit_values(self, usuarios):
        await Usuario(usuarios, email="a@x.com", nombre="A").upsert(conflict=["email"])
        await Usuario(usuarios, email="a@x.com", nombre="ignored").upsert(
            conflict=["email"], values={"nombre": "C"}
        )
        rows = await Usuario(usuarios).search()
        assert len(rows) == 1
        assert rows[0].nombre == "C"
