import importlib.util
from datetime import datetime

import pytest

from encinorm.introspection import (
    ColumnSpec,
    columns_of,
    generate_model,
    list_tables,
    resolve_field_type,
)
from encinorm.introspection.types import _normalize
from encinorm.model import Model
from encinorm.model.domain import CURRENCY, DATETIME, STR_50
from encinorm.model.types import to_ddl
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


class TestDomain:
    def test_str_50(self):
        assert STR_50().__metadata__[0].datatype == "str"
        assert STR_50().__metadata__[0].field_kwargs == {"max_length": 50}

    def test_currency_numeric(self):
        assert CURRENCY().__metadata__[0].datatype == "numeric"

    def test_datetime_coerces_iso(self):
        class T(Model):
            _table = "t"
            dt: DATETIME()

        assert isinstance(T(dt="2026-08-29T10:00:00").dt, datetime)

    def test_ddl_uses_preset(self):
        class T(Model):
            _table = "t"
            nombre: STR_50()

        assert "nombre TEXT" in to_ddl(T, "sqlite")


class TestNormalize:
    def test_varchar(self):
        assert _normalize("VARCHAR(50)") == ("str", 50, False)

    def test_text(self):
        assert _normalize("TEXT") == ("str", None, False)

    def test_integer(self):
        assert _normalize("INTEGER") == ("int", None, False)

    def test_tinyint1_is_bool(self):
        assert _normalize("tinyint(1)") == ("bool", None, False)

    def test_decimal_is_numeric(self):
        assert _normalize("DECIMAL(10,2)") == ("numeric", None, False)

    def test_unsigned_int(self):
        assert _normalize("int unsigned") == ("int", None, True)

    def test_datetime(self):
        assert _normalize("DATETIME") == ("datetime", None, False)

    def test_float_types(self):
        assert _normalize("FLOAT") == ("float", None, False)
        assert _normalize("REAL") == ("float", None, False)
        assert _normalize("double precision") == ("float", None, False)

    def test_unknown_falls_back_to_str(self):
        assert _normalize("geometry") == ("str", None, False)


class TestResolveFieldType:
    def _col(self, datatype, max_length=None, unsigned=False):
        return ColumnSpec("x", "", datatype, True, max_length=max_length, unsigned=unsigned)

    def test_preset_str50(self):
        assert resolve_field_type(self._col("str", 50)) == "STR_50"

    def test_preset_str100(self):
        assert resolve_field_type(self._col("str", 100)) == "STR_100"

    def test_preset_str_lengths(self):
        for n, name in [(10, "STR_10"), (15, "STR_15"), (20, "STR_20"),
                        (30, "STR_30"), (500, "STR_500")]:
            assert resolve_field_type(self._col("str", n)) == name

    def test_preset_text(self):
        assert resolve_field_type(self._col("str")) == "TEXT"

    def test_fallback_str_length(self):
        assert resolve_field_type(self._col("str", 13)) == "make_constraint(str, max_length=13)"

    def test_preset_int(self):
        assert resolve_field_type(self._col("int")) == "INT"

    def test_preset_int_pos(self):
        assert resolve_field_type(self._col("int", unsigned=True)) == "INT_POS"

    def test_preset_currency(self):
        assert resolve_field_type(self._col("numeric")) == "CURRENCY"

    def test_preset_float(self):
        assert resolve_field_type(self._col("float")) == "FLOAT"

    def test_preset_float_pos(self):
        assert resolve_field_type(self._col("float", unsigned=True)) == "FLOAT_POS"

    def test_preset_datetime(self):
        assert resolve_field_type(self._col("datetime")) == "DATETIME"

    def test_fallback_bool(self):
        assert resolve_field_type(self._col("bool")) == "BOOL"


class TestIntrospection:
    @pytest.mark.asyncio
    async def test_list_tables(self, db):
        await db.execute(Query("CREATE TABLE agentes (id INTEGER PRIMARY KEY, agente TEXT)", []))
        await db.execute(Query("CREATE TABLE regiones (id INTEGER PRIMARY KEY, region TEXT)", []))
        rec = await list_tables(db)
        assert rec.total == 2
        names = {r["name"] for r in rec.rows}
        assert names == {"agentes", "regiones"}

    @pytest.mark.asyncio
    async def test_list_tables_filter_and_paginate(self, db):
        for t in ("aaa", "aab", "aac", "bbb"):
            await db.execute(Query(f"CREATE TABLE {t} (id INTEGER PRIMARY KEY)", []))
        rec = await list_tables(db, name="aa", limit=2, page=1)
        assert rec.total == 3
        assert len(rec.rows) == 2

        rec2 = await list_tables(db, name="aa", limit=2, page=2)
        assert len(rec2.rows) == 1

    @pytest.mark.asyncio
    async def test_columns_of(self, db):
        await db.execute(Query(
            "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "agente VARCHAR(50) NOT NULL, rfc VARCHAR(13))", []
        ))
        cols = await columns_of(db, "agentes")
        by_name = {c.name: c for c in cols}
        assert by_name["agente"].datatype == "str"
        assert by_name["agente"].max_length == 50
        assert by_name["agente"].nullable is False
        assert by_name["id"].primary_key is True
        assert by_name["rfc"].max_length == 13


class TestGenerateModel:
    @pytest.mark.asyncio
    async def test_roundtrip(self, db, tmp_path):
        await db.execute(Query(
            "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "agente VARCHAR(50) NOT NULL, rfc VARCHAR(13), monto DECIMAL(10,2))", []
        ))
        path = await generate_model(db, "agentes", folder=str(tmp_path))

        assert path.name == "agentes.py"
        text = path.read_text(encoding="utf-8")
        assert "class Agentes(Model):" in text
        assert "STR_50" in text
        assert "make_constraint(str, max_length=13)" in text
        assert "CURRENCY" in text
        assert "_fields_disabled" in text

        spec = importlib.util.spec_from_file_location("gen_agentes", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        Agentes = mod.Agentes
        await Agentes(db, agente="Héctor", rfc="ABC123", monto=10.5).insert()

        rows = await Agentes(db, agente="x").search()
        assert len(rows) == 1
        assert rows[0].agente == "Héctor"
        assert rows[0].rfc == "ABC123"
        assert rows[0].monto == 10.5

    @pytest.mark.asyncio
    async def test_custom_class_name_and_reserved_column(self, db, tmp_path):
        await db.execute(Query(
            "CREATE TABLE detalle (id INTEGER PRIMARY KEY, \"order\" INTEGER, descripcion TEXT)", []
        ))
        path = await generate_model(db, "detalle", folder=str(tmp_path), class_name="LineaDetalle")

        assert path.name == "linea_detalle.py"
        text = path.read_text(encoding="utf-8")
        assert "class LineaDetalle(Model):" in text
        # "order" es palabra reservada -> atributo con sufijo y name= mapeado
        assert 'name="order"' in text
