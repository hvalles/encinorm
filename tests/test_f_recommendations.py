from datetime import datetime, timezone

import pytest
from pydantic import Field

from encinorm import Query
from encinorm.model import Filter, Model


class Evento(Model):
    _table = "eventos"
    cuando: datetime | None = None


class Item(Model):
    _table = "items"
    nombre: str | None = Field(default=None)


class TestF4Timezone:
    @pytest.mark.asyncio
    async def test_datetime_roundtrip_aware(self, connected_db):
        await Evento(connected_db).create_table()

        dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        e = Evento(connected_db, cuando=dt)
        await e.insert()

        loaded = await Evento(connected_db, id=e.id).load()
        assert loaded.cuando.tzinfo is not None
        assert loaded.cuando == dt

    @pytest.mark.asyncio
    async def test_serialize_normalizes_to_utc(self, connected_db):
        await Evento(connected_db).create_table()

        # aware en otra zona -> se guarda normalizado a UTC
        dt = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone(offset=__import__("datetime").timedelta(hours=-5)))
        e = Evento(connected_db, cuando=dt)
        await e.insert()

        row = await connected_db.fetch_one(Query("SELECT cuando FROM eventos WHERE id = {0}", [e.id]))
        assert row["cuando"] == "2026-01-01 14:00:00"  # -05:00 -> UTC

        loaded = await Evento(connected_db, id=e.id).load()
        assert loaded.cuando == datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)


class TestF5Count:
    @pytest.mark.asyncio
    async def test_count(self, connected_db):
        await Item(connected_db).create_table()
        await Item(connected_db, nombre="a").insert()
        await Item(connected_db, nombre="b").insert()

        assert await Item(connected_db).count() == 2
        assert await Item(connected_db).count(Filter.eq("nombre", "a")) == 1
        assert await Item(connected_db).count(Filter.eq("nombre", "z")) == 0
