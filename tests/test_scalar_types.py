from decimal import Decimal

import pytest

from encinorm import Query
from encinorm.model import BLOB, BOOL, CURRENCY, FLOAT, INT, INT_POS, Model
from encinorm.sqlite import SqliteDb


class Metrics(Model):
    _table = "metrics"
    counter: INT()
    total: INT_POS()
    score: FLOAT()
    amount: CURRENCY()
    active: BOOL()
    payload: BLOB()


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Metrics(d).create_table()
    yield d
    await d.close()


class TestScalarRoundTrip:
    @pytest.mark.asyncio
    async def test_int(self, db):
        await Metrics(db, counter=5, total=10).insert()
        loaded = (await Metrics(db).search())[0]
        assert loaded.counter == 5
        assert loaded.total == 10
        assert isinstance(loaded.counter, int)
        assert isinstance(loaded.total, int)

    @pytest.mark.asyncio
    async def test_float(self, db):
        await Metrics(db, score=3.5).insert()
        loaded = (await Metrics(db).search())[0]
        assert loaded.score == 3.5
        assert isinstance(loaded.score, float)

    @pytest.mark.asyncio
    async def test_currency(self, db):
        await Metrics(db, amount=10.5).insert()
        loaded = (await Metrics(db).search())[0]
        assert loaded.amount == 10.5
        assert isinstance(loaded.amount, float)

    @pytest.mark.asyncio
    async def test_bool(self, db):
        await Metrics(db, active=True).insert()
        loaded = (await Metrics(db).search())[0]
        assert loaded.active is True
        assert isinstance(loaded.active, bool)

        row = await db.fetch_one(Query("SELECT active FROM metrics LIMIT 1", []))
        assert row["active"] == 1  # bool se almacena como entero

    @pytest.mark.asyncio
    async def test_blob(self, db):
        await Metrics(db, payload=b"hello").insert()
        loaded = (await Metrics(db).search())[0]
        assert loaded.payload == b"hello"
        assert isinstance(loaded.payload, bytes)


class TestCurrencyFromDb:
    def test_decimal_is_coerced_to_float(self):
        m = Metrics.model_construct()
        value = m._from_db("amount", Decimal("10.50"))
        assert value == 10.5
        assert isinstance(value, float)

    def test_float_passes_through(self):
        m = Metrics.model_construct()
        value = m._from_db("amount", 10.5)
        assert value == 10.5
        assert isinstance(value, float)

    def test_none_stays_none(self):
        m = Metrics.model_construct()
        assert m._from_db("amount", None) is None
