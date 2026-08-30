import pytest
from pydantic import Field

from encinorm import Query
from encinorm.model import Model
from encinorm.model.types import to_ddl


class Padre(Model):
    _table = "padres"
    nombre: str | None = None


class Agente(Model):
    _table = "agentes"
    agente: str | None = Field(default=None)


class Hija(Model):
    _table = "hijas"
    padre_id: int | None = None
    _references_def = {
        "padre": {"model": Padre, "match_keys": {"id": "padre_id"}, "on_delete": "cascade"},
    }


class TestE8EnabledBool:
    def test_enabled_default_is_bool(self):
        a = Agente()
        assert a.enabled is True
        assert isinstance(a.enabled, bool)


class TestE10ForeignKeyDdl:
    def test_to_ddl_generates_fk(self):
        ddl = to_ddl(Hija, "sqlite")
        assert "FOREIGN KEY (padre_id) REFERENCES padres (id) ON DELETE CASCADE" in ddl

    def test_to_ddl_no_fk_without_on_delete(self):
        class SinFK(Model):
            _table = "sinfk"
            padre_id: int | None = None
            _references_def = {
                "padre": {"model": Padre, "match_keys": {"id": "padre_id"}},
            }

        ddl = to_ddl(SinFK, "sqlite")
        assert "FOREIGN KEY" not in ddl


class TestE11SyncSchema:
    @pytest.mark.asyncio
    async def test_sync_schema_adds_missing_column(self, connected_db):
        class T1(Model):
            _table = "t"
            a: str | None = None

        t1 = T1(connected_db)
        await t1.create_table()

        class T2(Model):
            _table = "t"
            a: str | None = None
            b: str | None = None

        t2 = T2(connected_db)
        await t2.sync_schema()

        rows = await connected_db.fetch_all(Query("PRAGMA table_info(t)", []))
        cols = {r["name"] for r in rows}
        assert "a" in cols
        assert "b" in cols
