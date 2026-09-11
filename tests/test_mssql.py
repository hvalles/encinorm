import os

import pytest

from encino_orm import MssqlDb, Query
from encino_orm._rows import _rows_to_dicts
from encino_orm.introspection.types import _normalize
from encino_orm.mssql import _to_mssql
from encino_orm.model.types import ddl_type

MSSQL_CONFIG = {
    "host": os.getenv("ENCINO_ORM_MSSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINO_ORM_MSSQL_PORT", "1433")),
    "user": os.getenv("ENCINO_ORM_MSSQL_USER", "sa"),
    "password": os.getenv("ENCINO_ORM_MSSQL_PASSWORD", "Admin_123"),
    "db": os.getenv("ENCINO_ORM_MSSQL_DB", "encino_orm_test"),
    "driver": os.getenv("ENCINO_ORM_MSSQL_DRIVER", "ODBC Driver 18 for SQL Server"),
    # El contenedor local usa certificado autofirmado; se confía solo en pruebas.
    "trust_server_certificate": os.getenv("ENCINO_ORM_MSSQL_TRUST_CERT", "true").lower()
    in ("1", "true", "yes"),
}


class TestMssqlInternal:
    def test_to_mssql_translates_placeholders(self):
        q = Query("SELECT * FROM t WHERE a = {0} AND b = {1}", [1, "x"])
        sql, values = _to_mssql(q.query[0], q.query[1])
        assert sql == "SELECT * FROM t WHERE a = ? AND b = ?"
        assert values == [1, "x"]

    def test_insert_builder_default(self):
        db = MssqlDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
        assert sql == "INSERT INTO t (a,b) VALUES (?,?)"
        assert values == [1, "x"]

    def test_insert_builder_ignore_duplicated_flag(self):
        db = MssqlDb()
        q = db.insert("t", {"a": 1}, ignore_duplicated=True)
        assert q.ignore_duplicated is True
        sql, values = db._prepare(q)
        assert sql == "INSERT INTO t (a) VALUES (?)"

    def test_insert_builder_replace_merge(self):
        db = MssqlDb()
        q = db.insert("t", {"a": 1, "b": "x"}, replace=True)
        sql, values = db._prepare(q)
        assert sql == (
            "MERGE INTO t AS dst USING (SELECT ? AS a, ? AS b) AS src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.a = src.a, dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert values == [1, "x"]

    def test_insert_builder_replace_merge_conflict(self):
        db = MssqlDb()
        q = db.insert("t", {"a": 1, "b": "x"}, replace=True, conflict=["b"])
        sql, _ = db._prepare(q)
        assert "ON (dst.b = src.b)" in sql

    def test_update_builder(self):
        db = MssqlDb()
        sql, values = db._prepare(db.update("t", {"id": 1}, {"nombre": "mod"}))
        assert sql == "UPDATE t SET nombre = ? WHERE id = ?"
        assert values == ["mod", 1]

    def test_rows_to_dicts(self):
        description = [("ID",), ("Nombre",)]
        rows = [(1, "a"), (2, "b")]
        assert _rows_to_dicts(description, rows) == [
            {"id": 1, "nombre": "a"},
            {"id": 2, "nombre": "b"},
        ]

    def test_is_unique_violation(self):
        db = MssqlDb()
        e = Exception()
        e.args = ("23000", (2627, "duplicate key"))
        assert db.is_unique_violation(e) is True

        e2 = Exception()
        e2.args = ("23000", (2601, "unique index"))
        assert db.is_unique_violation(e2) is True

        e3 = Exception()
        e3.args = ("23000", (547, "fk violation"))
        assert db.is_unique_violation(e3) is False

    def test_is_lock_error(self):
        db = MssqlDb()
        e = Exception()
        e.args = ("40001", (1205, "deadlock"))
        assert db.is_lock_error(e) is True

        e2 = Exception()
        e2.args = ("HYT00", (1222, "lock timeout"))
        assert db.is_lock_error(e2) is True

    def test_normalize_new_types(self):
        assert _normalize("nvarchar(100)") == ("str", 100, False)
        assert _normalize("datetime2")[0] == "datetime"
        assert _normalize("bit")[0] == "bool"
        assert _normalize("varbinary(max)")[0] == "blob"
        assert _normalize("uniqueidentifier")[0] == "str"
        assert _normalize("money")[0] == "numeric"

    def test_ddl_map(self):
        assert ddl_type("pk", "mssql") == "INT IDENTITY(1,1) PRIMARY KEY"
        assert ddl_type("str", "mssql") == "NVARCHAR(255)"
        assert ddl_type("bool", "mssql") == "BIT"
        assert ddl_type("json", "mssql") == "NVARCHAR(MAX)"


@pytest.fixture
async def mssql_connected_db():
    cfg = dict(MSSQL_CONFIG)
    db_name = cfg.pop("db")

    admin = MssqlDb()
    try:
        await admin.connect(**cfg, db="master")
    except Exception as e:
        pytest.skip(f"SQL Server no disponible: {e}")

    admin._connection.autocommit = True
    await admin.execute(Query(f"IF DB_ID('{db_name}') IS NULL CREATE DATABASE {db_name}", []))
    admin._connection.autocommit = False
    await admin.close()

    db = MssqlDb()
    try:
        await db.connect(db=db_name, **cfg)
    except Exception as e:
        pytest.skip(f"SQL Server no disponible: {e}")
    yield db
    await db.close()


class TestMssqlLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, mssql_connected_db):
        db = mssql_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, mssql_connected_db):
        assert await mssql_connected_db.is_alive() is True

    @pytest.mark.asyncio
    async def test_insert_execute_and_last_id(self, mssql_connected_db):
        db = mssql_connected_db
        await db.execute(Query(
            "IF OBJECT_ID('usuarios', 'U') IS NOT NULL DROP TABLE usuarios", []
        ))
        await db.execute(Query(
            "CREATE TABLE usuarios (id INT IDENTITY(1,1) PRIMARY KEY, nombre NVARCHAR(50))", []
        ))

        assert await db.execute(db.insert("usuarios", {"nombre": "Héctor"})) == 1
        assert await db.last_id() == 1

        await db.execute(db.insert("usuarios", {"nombre": "Ana"}))
        assert await db.last_id() == 2

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Héctor", "Ana"]

    @pytest.mark.asyncio
    async def test_migrate_applies_and_records(self, mssql_connected_db):
        db = mssql_connected_db
        await db.execute(Query("IF OBJECT_ID('usuarios', 'U') IS NOT NULL DROP TABLE usuarios", []))
        await db.execute(Query("IF OBJECT_ID('_encino_orm_migrations', 'U') IS NOT NULL DROP TABLE _encino_orm_migrations", []))

        await db.migrate(
            "v1_crear_usuarios",
            Query("CREATE TABLE usuarios (id INT IDENTITY(1,1) PRIMARY KEY, nombre NVARCHAR(50))", []),
        )

        status = await db.migrate_status()
        matching = [s for s in status if s["name"] == "v1_crear_usuarios"]
        assert len(matching) == 1
        assert "CREATE TABLE usuarios" in matching[0]["sql_text"]
