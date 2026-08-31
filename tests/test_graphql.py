import pytest

from encinorm.graphql import build_schema
from encinorm.model import Model
from encinorm.sqlite import SqliteDb


class Agente(Model):
    _table = "agentes"
    agente: str | None = None
    region_id: int | None = None


class Region(Model):
    _table = "regiones"
    region: str | None = None
    _has_many_def = {"agentes": {"model": Agente, "foreign_key": "region_id"}}


Agente._references_def = {"region": {"model": Region, "match_keys": {"id": "region_id"}}}


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Region(d).create_table()
    await Agente(d).create_table()
    yield d
    await d.close()


@pytest.fixture
async def schema():
    return build_schema([Region, Agente])


class TestQueries:
    @pytest.mark.asyncio
    async def test_list(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        await Agente(db, agente="Ana", region_id=2).insert()

        result = await schema.execute(
            "{ agentes { id agente region_id } }", context_value={"db": db}
        )
        assert result.errors is None
        data = result.data["agentes"]
        assert len(data) == 2
        assert {a["agente"] for a in data} == {"Héctor", "Ana"}

    @pytest.mark.asyncio
    async def test_list_filter_eq(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        await Agente(db, agente="Ana", region_id=1).insert()
        await Agente(db, agente="Luis", region_id=2).insert()

        result = await schema.execute(
            '{ agentes(filter: { region_id: { eq: 1 } }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert len(result.data["agentes"]) == 2

    @pytest.mark.asyncio
    async def test_list_filter_like(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        await Agente(db, agente="Ana", region_id=1).insert()

        result = await schema.execute(
            '{ agentes(filter: { agente: { like: "Héc" } }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert len(result.data["agentes"]) == 1
        assert result.data["agentes"][0]["agente"] == "Héctor"

    @pytest.mark.asyncio
    async def test_list_filter_in(self, db, schema):
        await Agente(db, agente="a", region_id=1).insert()
        await Agente(db, agente="b", region_id=2).insert()
        await Agente(db, agente="c", region_id=3).insert()

        result = await schema.execute(
            '{ agentes(filter: { region_id: { in: [1, 3] } }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert {a["agente"] for a in result.data["agentes"]} == {"a", "c"}

    @pytest.mark.asyncio
    async def test_list_filter_and(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        await Agente(db, agente="Ana", region_id=1).insert()
        await Agente(db, agente="Luis", region_id=2).insert()

        result = await schema.execute(
            '{ agentes(filter: { and: [ { region_id: { eq: 1 } }, '
            '{ agente: { like: "Héc" } } ] }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert [a["agente"] for a in result.data["agentes"]] == ["Héctor"]

    @pytest.mark.asyncio
    async def test_list_filter_or(self, db, schema):
        await Agente(db, agente="a", region_id=1).insert()
        await Agente(db, agente="b", region_id=2).insert()
        await Agente(db, agente="c", region_id=3).insert()

        result = await schema.execute(
            '{ agentes(filter: { or: [ { agente: { eq: "a" } }, '
            '{ agente: { eq: "c" } } ] }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert {a["agente"] for a in result.data["agentes"]} == {"a", "c"}

    @pytest.mark.asyncio
    async def test_list_filter_not(self, db, schema):
        await Agente(db, agente="a", region_id=1).insert()
        await Agente(db, agente="b", region_id=2).insert()

        result = await schema.execute(
            '{ agentes(filter: { not: { agente: { eq: "a" } } }) { agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert [a["agente"] for a in result.data["agentes"]] == ["b"]

    @pytest.mark.asyncio
    async def test_list_paginate(self, db, schema):
        for i in range(5):
            await Agente(db, agente=f"a{i}").insert()

        result = await schema.execute(
            "{ agentes(limit: 2, page: 1) { agente } }", context_value={"db": db}
        )
        assert result.errors is None
        assert len(result.data["agentes"]) == 2

    @pytest.mark.asyncio
    async def test_get(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        result = await schema.execute(
            "{ agente(id: 1) { agente region_id } }", context_value={"db": db}
        )
        assert result.errors is None
        assert result.data["agente"]["agente"] == "Héctor"

    @pytest.mark.asyncio
    async def test_get_not_found(self, db, schema):
        result = await schema.execute(
            "{ agente(id: 999) { agente } }", context_value={"db": db}
        )
        assert result.errors is None
        assert result.data["agente"] is None

    @pytest.mark.asyncio
    async def test_count(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        await Agente(db, agente="Ana", region_id=1).insert()
        result = await schema.execute(
            "{ agentes_count(filter: { region_id: { eq: 1 } }) }",
            context_value={"db": db},
        )
        assert result.errors is None
        assert result.data["agentes_count"] == 2


class TestMutations:
    @pytest.mark.asyncio
    async def test_create(self, db, schema):
        result = await schema.execute(
            'mutation { agente_create(data: { agente: "Héctor", region_id: 1 }) { id agente } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert result.data["agente_create"]["agente"] == "Héctor"
        assert len(await Agente(db).search()) == 1

    @pytest.mark.asyncio
    async def test_update_partial(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        result = await schema.execute(
            'mutation { agente_update(id: 1, data: { agente: "Héctor M." }) { id agente region_id } }',
            context_value={"db": db},
        )
        assert result.errors is None
        assert result.data["agente_update"]["agente"] == "Héctor M."
        assert result.data["agente_update"]["region_id"] == 1

    @pytest.mark.asyncio
    async def test_delete(self, db, schema):
        await Agente(db, agente="Héctor", region_id=1).insert()
        result = await schema.execute(
            "mutation { agente_delete(id: 1) }", context_value={"db": db}
        )
        assert result.errors is None
        assert result.data["agente_delete"] is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, db, schema):
        result = await schema.execute(
            "mutation { agente_delete(id: 999) }", context_value={"db": db}
        )
        assert result.errors is None
        assert result.data["agente_delete"] is False


class TestRelationships:
    @pytest.mark.asyncio
    async def test_has_many(self, db, schema):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="Héctor", region_id=rid).insert()
        await Agente(db, agente="Ana", region_id=rid).insert()

        result = await schema.execute(
            "{ regiones { region agentes { agente } } }", context_value={"db": db}
        )
        assert result.errors is None
        region = result.data["regiones"][0]
        assert region["region"] == "Norte"
        assert {a["agente"] for a in region["agentes"]} == {"Héctor", "Ana"}

    @pytest.mark.asyncio
    async def test_reference(self, db, schema):
        rid = await Region(db, region="Norte").insert()
        await Agente(db, agente="Héctor", region_id=rid).insert()

        result = await schema.execute(
            "{ agentes { agente region { region } } }", context_value={"db": db}
        )
        assert result.errors is None
        agente = result.data["agentes"][0]
        assert agente["agente"] == "Héctor"
        assert agente["region"]["region"] == "Norte"


class CountingDb(SqliteDb):
    def __init__(self):
        super().__init__()
        self.fetch_count = 0

    async def fetch_all(self, qry):
        self.fetch_count += 1
        return await super().fetch_all(qry)


class TestDataLoaderBatching:
    @pytest.mark.asyncio
    async def test_has_many_batched(self):
        db = CountingDb()
        await db.connect(database=":memory:")
        await Region(db).create_table()
        await Agente(db).create_table()
        for i in range(5):
            rid = await Region(db, region=f"r{i}").insert()
            await Agente(db, agente=f"a{i}", region_id=rid).insert()

        schema = build_schema([Region, Agente])
        db.fetch_count = 0
        result = await schema.execute(
            "{ regiones { region agentes { agente } } }", context_value={"db": db}
        )
        await db.close()

        assert result.errors is None
        assert len(result.data["regiones"]) == 5
        # 1 consulta de lista + 1 batch de has_many (sin N+1)
        assert db.fetch_count == 2

    @pytest.mark.asyncio
    async def test_reference_batched(self):
        db = CountingDb()
        await db.connect(database=":memory:")
        await Region(db).create_table()
        await Agente(db).create_table()
        for i in range(5):
            rid = await Region(db, region=f"r{i}").insert()
            await Agente(db, agente=f"a{i}", region_id=rid).insert()

        schema = build_schema([Region, Agente])
        db.fetch_count = 0
        result = await schema.execute(
            "{ agentes { agente region { region } } }", context_value={"db": db}
        )
        await db.close()

        assert result.errors is None
        assert len(result.data["agentes"]) == 5
        # 1 consulta de lista + 1 batch de referencia (sin N+1)
        assert db.fetch_count == 2
