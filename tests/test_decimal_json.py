from decimal import Decimal

import pytest

from encinorm.model import Model, make_constraint
from encinorm.model.domain import DECIMAL, JSON
from encinorm.model.types import PY_TYPE_TO_DATATYPE, to_ddl
from encinorm.sqlite import SqliteDb


class Doc(Model):
    _table = "docs"
    total: DECIMAL()
    payload: JSON()                  # dict | None -> columna JSON
    items: make_constraint(list)()   # list | None -> columna JSON


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Doc(d).create_table()
    yield d
    await d.close()


class TestPresets:
    def test_decimal_datatype(self):
        assert DECIMAL().__metadata__[0].datatype == "decimal"

    def test_json_datatype(self):
        assert JSON().__metadata__[0].datatype == "json"

    def test_py_type_to_datatype_json(self):
        assert PY_TYPE_TO_DATATYPE[dict] == "json"
        assert PY_TYPE_TO_DATATYPE[list] == "json"


class TestDdl:
    def test_sqlite(self):
        ddl = to_ddl(Doc, "sqlite")
        assert "total TEXT" in ddl
        assert "payload TEXT" in ddl
        assert "items TEXT" in ddl

    def test_mysql(self):
        ddl = to_ddl(Doc, "mysql")
        assert "total DECIMAL(10,2)" in ddl
        assert "payload JSON" in ddl
        assert "items JSON" in ddl

    def test_postgres(self):
        ddl = to_ddl(Doc, "postgresql")
        assert "total NUMERIC" in ddl
        assert "payload JSONB" in ddl
        assert "items JSONB" in ddl


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_decimal_and_json_roundtrip(self, db):
        doc = Doc(db, total=Decimal("123.45"), payload={"k": "v", "n": 1}, items=[1, 2, 3])
        await doc.insert()

        loaded = await Doc(db, id=1).load()
        assert loaded.total == Decimal("123.45")
        assert isinstance(loaded.total, Decimal)
        assert loaded.payload == {"k": "v", "n": 1}
        assert loaded.items == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_search_hydrates(self, db):
        await Doc(db, total=Decimal("0.10"), payload={"a": [1, 2]}, items=[9]).insert()

        rows = await Doc(db).search()
        assert len(rows) == 1
        assert rows[0].total == Decimal("0.10")
        assert rows[0].payload == {"a": [1, 2]}
        assert rows[0].items == [9]

    @pytest.mark.asyncio
    async def test_nullable_none(self, db):
        await Doc(db, total=Decimal("1.00")).insert()  # payload/items None
        loaded = await Doc(db, id=1).load()
        assert loaded.total == Decimal("1.00")
        assert loaded.payload is None
        assert loaded.items is None

    @pytest.mark.asyncio
    async def test_high_precision_roundtrip(self, db):
        value = Decimal("0.123456789012345678901234567890")
        await Doc(db, total=value).insert()

        loaded = await Doc(db, id=1).load()
        assert loaded.total == value
        assert isinstance(loaded.total, Decimal)

        rows = await Doc(db).search()
        assert rows[0].total == value


class TestSchema:
    @pytest.mark.asyncio
    async def test_diff_schema_decimal_not_flagged(self, db):
        diff = await Doc(db).diff_schema()
        changed_fields = {c["field"] for c in diff["changed"]}
        assert "total" not in changed_fields
