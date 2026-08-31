import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from encinorm import Query
from encinorm.cli import main
from encinorm.introspection.types import ColumnSpec
from encinorm.sqlite import SqliteDb
from encinorm.transfer import (
    _normalize_value,
    _serialize_for_target,
    build_ddl,
    copy_database,
    copy_table,
)


def _col(name, datatype, pk=False):
    return ColumnSpec(name=name, raw_type=datatype, datatype=datatype,
                      nullable=True, primary_key=pk)


class TestBuildDdl:
    def test_sqlite_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True), _col("nombre", "str")], "sqlite")
        assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
        assert "nombre TEXT" in ddl

    def test_mysql_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True), _col("nombre", "str")], "mysql")
        assert "id INT AUTO_INCREMENT PRIMARY KEY" in ddl
        assert "nombre VARCHAR(255)" in ddl

    def test_postgres_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True)], "postgresql")
        assert "id SERIAL PRIMARY KEY" in ddl

    def test_composite_pk(self):
        ddl = build_ddl(
            "m",
            [_col("tenant_id", "int", pk=True), _col("code", "str", pk=True)],
            "sqlite",
        )
        assert "PRIMARY KEY (tenant_id, code)" in ddl


class TestValueTranslation:
    def test_date_from_str(self):
        assert _normalize_value("2026-09-07", "date") == date(2026, 9, 7)

    def test_date_targets(self):
        d = date(2026, 9, 7)
        assert _serialize_for_target(d, "date", "sqlite") == "2026-09-07"
        assert _serialize_for_target(d, "date", "mysql") is d
        assert _serialize_for_target(d, "date", "postgresql") is d

    def test_datetime_from_str(self):
        assert _normalize_value("2026-01-01 14:00:00", "datetime") == datetime(2026, 1, 1, 14, 0, 0)

    def test_datetime_targets(self):
        dt = datetime(2026, 1, 1, 14, 0, 0)
        assert _serialize_for_target(dt, "datetime", "sqlite") == "2026-01-01 14:00:00"
        assert _serialize_for_target(dt, "datetime", "mysql") == dt
        assert _serialize_for_target(dt, "datetime", "postgresql") is dt

    def test_datetime_aware_normalized_to_naive(self):
        aware = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        assert _serialize_for_target(aware, "datetime", "sqlite") == "2026-01-01 09:00:00"
        assert _serialize_for_target(aware, "datetime", "mysql") == datetime(2026, 1, 1, 9, 0, 0)

    def test_bool_targets(self):
        assert _serialize_for_target(True, "bool", "sqlite") == 1
        assert _serialize_for_target(True, "bool", "mysql") == 1
        assert _serialize_for_target(True, "bool", "postgresql") is True

    def test_numeric_targets(self):
        assert _serialize_for_target(Decimal("10.50"), "numeric", "sqlite") == "10.50"
        assert _serialize_for_target(Decimal("10.50"), "numeric", "mysql") == Decimal("10.50")
        assert _serialize_for_target(Decimal("10.50"), "numeric", "postgresql") == Decimal("10.50")

    def test_str_from_jsonb_like_value(self):
        assert _normalize_value({"a": 1}, "str") == '{"a": 1}'

    def test_json_from_str(self):
        assert _normalize_value('{"a": 1}', "json") == {"a": 1}

    def test_json_passthrough(self):
        assert _normalize_value({"a": 1}, "json") == {"a": 1}

    def test_json_targets(self):
        assert _serialize_for_target({"a": 1}, "json", "sqlite") == '{"a": 1}'
        assert _serialize_for_target({"a": 1}, "json", "mysql") == '{"a": 1}'
        assert _serialize_for_target({"a": 1}, "json", "postgresql") == {"a": 1}

    def test_blob(self):
        assert _normalize_value(b"x", "blob") == b"x"
        assert _normalize_value(memoryview(b"x"), "blob") == b"x"


@pytest.fixture
async def src():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


@pytest.fixture
async def dst():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


class TestCopyTable:
    @pytest.mark.asyncio
    async def test_copy_creates_and_copies(self, src, dst):
        await src.execute(Query(
            "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "nombre TEXT, edad INTEGER, activo INTEGER, creado TEXT)", []
        ))
        await src.execute(Query(
            "INSERT INTO users (nombre, edad, activo, creado) VALUES ('Ana', 30, 1, '2026-09-07')", []
        ))
        await src.execute(Query(
            "INSERT INTO users (nombre, edad, activo, creado) VALUES ('Bob', 25, 0, '2026-09-08')", []
        ))

        assert await copy_table(src, dst, "users", create=True) == 2

        rows = await dst.fetch_all(Query("SELECT * FROM users ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Ana", "Bob"]
        assert [r["edad"] for r in rows] == [30, 25]
        assert [r["activo"] for r in rows] == [1, 0]
        assert [r["creado"] for r in rows] == ["2026-09-07", "2026-09-08"]

    @pytest.mark.asyncio
    async def test_truncate(self, src, dst):
        await src.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", []))
        await src.execute(Query("INSERT INTO t (v) VALUES ('x')", []))
        await dst.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", []))
        await dst.execute(Query("INSERT INTO t (v) VALUES ('old')", []))

        await copy_table(src, dst, "t", truncate=True)
        rows = await dst.fetch_all(Query("SELECT v FROM t", []))
        assert [r["v"] for r in rows] == ["x"]

    @pytest.mark.asyncio
    async def test_copy_json_column(self, src, dst):
        await src.execute(Query(
            "CREATE TABLE docs (id INTEGER PRIMARY KEY AUTOINCREMENT, payload JSON)", []
        ))
        await src.execute(Query("INSERT INTO docs (payload) VALUES ('{\"a\": 1}')", []))

        assert await copy_table(src, dst, "docs", create=True) == 1
        rows = await dst.fetch_all(Query("SELECT payload FROM docs", []))
        assert rows[0]["payload"] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_preserve_ids_false_drops_auto_pk(self, src, dst):
        await src.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", []))
        await src.execute(Query("INSERT INTO t (v) VALUES ('x')", []))
        await dst.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", []))

        await copy_table(src, dst, "t", preserve_ids=False)
        rows = await dst.fetch_all(Query("SELECT * FROM t", []))
        assert len(rows) == 1
        assert rows[0]["v"] == "x"


class TestCopyDatabase:
    @pytest.mark.asyncio
    async def test_copies_all_tables(self, src, dst):
        await src.execute(Query("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)", []))
        await src.execute(Query("CREATE TABLE b (id INTEGER PRIMARY KEY AUTOINCREMENT, y INTEGER)", []))
        await src.execute(Query("INSERT INTO a (x) VALUES ('uno')", []))
        await src.execute(Query("INSERT INTO b (y) VALUES (7)", []))

        result = await copy_database(src, dst, create=True)
        assert result == {"a": 1, "b": 1}

        assert (await dst.fetch_all(Query("SELECT x FROM a", [])))[0]["x"] == "uno"
        assert (await dst.fetch_all(Query("SELECT y FROM b", [])))[0]["y"] == 7

    @pytest.mark.asyncio
    async def test_subset_of_tables(self, src, dst):
        await src.execute(Query("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)", []))
        await src.execute(Query("CREATE TABLE b (id INTEGER PRIMARY KEY AUTOINCREMENT, y INTEGER)", []))
        await src.execute(Query("INSERT INTO a (x) VALUES ('uno')", []))
        await src.execute(Query("INSERT INTO b (y) VALUES (7)", []))

        result = await copy_database(src, dst, tables=["a"], create=True)
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_missing_table_raises(self, src, dst):
        with pytest.raises(ValueError):
            await copy_table(src, dst, "inexistente")


class TestCliCopy:
    def test_end_to_end(self, tmp_path):
        src_file = tmp_path / "src.db"
        dst_file = tmp_path / "dst.db"

        async def _setup():
            d = SqliteDb()
            await d.connect(database=str(src_file))
            await d.execute(Query(
                "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", []
            ))
            await d.execute(Query("INSERT INTO t (nombre) VALUES ('Héctor')", []))
            await d.commit()
            await d.close()

        asyncio.run(_setup())

        code = main([
            "copy", "sqlite", "sqlite",
            "--src-database", str(src_file),
            "--dst-database", str(dst_file),
            "--create",
        ])
        assert code == 0

        async def _check():
            d = SqliteDb()
            await d.connect(database=str(dst_file))
            rows = await d.fetch_all(Query("SELECT * FROM t", []))
            await d.close()
            return rows

        rows = asyncio.run(_check())
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Héctor"
