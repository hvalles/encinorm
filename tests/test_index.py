import sqlite3
from typing import Annotated

import pytest

from encinorm import Query
from encinorm.model import Column, Index, Model
from encinorm.model.types import indexes_ddl


class TestIndexClass:
    def test_str_to_tuple(self):
        idx = Index("rfc", unique=True)
        assert idx.columns == ("rfc",)
        assert idx.unique is True

    def test_list_to_tuple(self):
        idx = Index(["a", "b"])
        assert idx.columns == ("a", "b")

    def test_name_default(self):
        idx = Index("a")
        assert idx.name is None


class TestIndexesDdl:
    def test_regular_and_unique(self):
        class C(Model):
            _table = "clientes"
            rfc: str | None = None
            nombre: str | None = None
            _indexes = [Index("rfc", unique=True), Index("nombre")]

        result = indexes_ddl(C, "sqlite")
        assert ("idx_clientes_rfc", "CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_rfc ON clientes (rfc)") in result
        assert ("idx_clientes_nombre", "CREATE INDEX IF NOT EXISTS idx_clientes_nombre ON clientes (nombre)") in result

    def test_custom_name(self):
        class C(Model):
            _table = "c"
            a: str | None = None
            _indexes = [Index("a", name="idx_custom")]

        result = indexes_ddl(C, "sqlite")
        assert ("idx_custom", "CREATE INDEX IF NOT EXISTS idx_custom ON c (a)") in result

    def test_column_mapping(self):
        class A(Model):
            _table = "a"
            agente: Annotated[str | None, Column(name="nombre")] = None
            _indexes = [Index("agente")]

        result = indexes_ddl(A, "sqlite")
        assert "ON a (nombre)" in result[0][1]

    def test_mysql_no_if_not_exists(self):
        class C(Model):
            _table = "c"
            a: str | None = None
            _indexes = [Index("a")]

        result = indexes_ddl(C, "mysql")
        assert "IF NOT EXISTS" not in result[0][1]

    def test_desc_direction(self):
        class C(Model):
            _table = "c"
            created_at: str | None = None
            _indexes = [Index([("created_at", "DESC")])]

        result = indexes_ddl(C, "sqlite")
        assert "ON c (created_at DESC)" in result[0][1]

    def test_asc_direction(self):
        class C(Model):
            _table = "c"
            created_at: str | None = None
            _indexes = [Index([("created_at", "ASC")])]

        result = indexes_ddl(C, "sqlite")
        assert "ON c (created_at ASC)" in result[0][1]

    def test_mixed_directions(self):
        class C(Model):
            _table = "c"
            rfc: str | None = None
            created_at: str | None = None
            _indexes = [Index(["rfc", ("created_at", "DESC")])]

        result = indexes_ddl(C, "sqlite")
        assert "ON c (rfc, created_at DESC)" in result[0][1]

    def test_invalid_direction(self):
        class C(Model):
            _table = "c"
            a: str | None = None
            _indexes = [Index([("a", "SIDEWAYS")])]

        with pytest.raises(ValueError):
            indexes_ddl(C, "sqlite")


class TestAddIndex:
    def test_add_index_registers(self):
        class P(Model):
            _table = "p"
            a: str | None = None

        P.add_index(Index("a", unique=True))
        assert len(P._indexes) == 1
        assert P._indexes[0].unique is True


class TestCreateTableIndexes:
    @pytest.mark.asyncio
    async def test_create_table_applies_indexes(self, connected_db):
        class C(Model):
            _table = "c"
            rfc: str | None = None
            nombre: str | None = None
            _indexes = [Index("rfc", unique=True), Index("nombre")]

        await C(connected_db).create_table()

        rows = await connected_db.fetch_all(Query("PRAGMA index_list(c)", []))
        names = {r["name"] for r in rows}
        assert "idx_c_rfc" in names
        assert "idx_c_nombre" in names

    @pytest.mark.asyncio
    async def test_unique_index_enforced(self, connected_db):
        class C(Model):
            _table = "c"
            rfc: str | None = None
            _indexes = [Index("rfc", unique=True)]

        await C(connected_db).create_table()
        await C(connected_db, rfc="AAA").insert()

        with pytest.raises(sqlite3.IntegrityError):
            await C(connected_db, rfc="AAA").insert()
