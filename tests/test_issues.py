from datetime import date

import pytest

from encinorm import Query
from encinorm.model import DATE, INT_POS, STR_100, Model


class Holiday(Model):
    _table = "holidays"
    start_date: DATE(required=True)


class Client(Model):
    _table = "clients"
    name: STR_100(required=True)


class Appointment(Model):
    _table = "appointments"
    client_id: INT_POS()
    _references_def = {"client": {"model": Client, "match_keys": {"id": "client_id"}}}


class Tenant(Model):
    _table = "tenants"
    _primary_key = ("tenant_id", "code")
    _fields_disabled = ["id"]
    tenant_id: INT_POS(required=True)
    code: STR_100(required=True)
    label: STR_100(required=True)


class Member(Model):
    _table = "members"
    _fields_disabled = ["id"]
    tenant_id: INT_POS()
    code: STR_100()
    _references_def = {
        "tenant": {
            "model": Tenant,
            "match_keys": {"tenant_id": "tenant_id", "code": "code"},
        }
    }


def _cursor(db, cls, **kwargs):
    obj = cls.model_construct(**kwargs)
    object.__setattr__(obj, "_db", db)
    return obj


@pytest.fixture
async def db(connected_db):
    for cls in (Holiday, Client, Appointment, Tenant, Member):
        await _cursor(connected_db, cls).create_table()
    return connected_db


class TestDateColumn:
    @pytest.mark.asyncio
    async def test_insert_date_object_roundtrip(self, db):
        await Holiday(db, start_date=date(2026, 9, 7)).insert()

        rows = await _cursor(db, Holiday).search()
        assert rows[0].start_date == date(2026, 9, 7)

    @pytest.mark.asyncio
    async def test_insert_date_string_roundtrip(self, db):
        await Holiday(db, start_date="2026-09-07").insert()

        row = await db.fetch_one(Query("SELECT start_date FROM holidays LIMIT 1", []))
        assert row["start_date"] == "2026-09-07"

        rows = await _cursor(db, Holiday).search()
        assert rows[0].start_date == date(2026, 9, 7)

    @pytest.mark.asyncio
    async def test_update_date(self, db):
        h = Holiday(db, start_date=date(2026, 9, 7))
        await h.insert()

        h.start_date = date(2026, 10, 1)
        await h.update()

        rows = await _cursor(db, Holiday).search()
        assert rows[0].start_date == date(2026, 10, 1)


class TestReferenceWithRequiredField:
    @pytest.mark.asyncio
    async def test_resolve_reference(self, db):
        await Client(db, name="Acme").insert()
        await Appointment(db, client_id=1).insert()

        loaded = (await _cursor(db, Appointment).search())[0]
        assert (await loaded["client"]).name == "Acme"

    @pytest.mark.asyncio
    async def test_batch_reference(self, db):
        await Client(db, name="Acme").insert()
        await Appointment(db, client_id=1).insert()

        loaded = (await _cursor(db, Appointment).search())[0]
        await Appointment.batch_reference([loaded], "client")
        assert loaded._references["client"]._cached.name == "Acme"

    @pytest.mark.asyncio
    async def test_resolve_reference_composite(self, db):
        await Tenant(db, tenant_id=7, code="admin", label="Propietario").insert()
        await Member(db, tenant_id=7, code="admin").insert()

        loaded = (await _cursor(db, Member).search())[0]
        assert (await loaded["tenant"]).label == "Propietario"

    @pytest.mark.asyncio
    async def test_batch_reference_composite(self, db):
        await Tenant(db, tenant_id=7, code="admin", label="Propietario").insert()
        await Tenant(db, tenant_id=8, code="user", label="Invitado").insert()
        await Member(db, tenant_id=7, code="admin").insert()
        await Member(db, tenant_id=8, code="user").insert()

        loaded = await _cursor(db, Member).search()
        await Member.batch_reference(loaded, "tenant")

        labels = {(await m["tenant"]).label for m in loaded}
        assert labels == {"Propietario", "Invitado"}


class TestCursor:
    @pytest.mark.asyncio
    async def test_cursor_load_search_count(self, db):
        await Client(db, name="Acme").insert()
        await Client(db, name="Beta").insert()

        loaded = await Client.cursor(db, id=1).load()
        assert loaded.name == "Acme"

        names = {r.name for r in await Client.cursor(db).search()}
        assert names == {"Acme", "Beta"}

        assert await Client.cursor(db).count() == 2

    @pytest.mark.asyncio
    async def test_cursor_create_table(self, connected_db):
        class Fresh(Model):
            _table = "fresh"
            label: STR_100(required=True)

        await Fresh.cursor(connected_db).create_table()
        await Fresh(connected_db, label="x").insert()

        rows = await Fresh.cursor(connected_db).search()
        assert rows[0].label == "x"

    @pytest.mark.asyncio
    async def test_normal_constructor_still_validates(self):
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):
            Client(db=None)
