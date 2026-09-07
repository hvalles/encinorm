import os

import pytest

from encino_orm import MariadbDb, Query
from encino_orm.model.types import ddl_type

MARIADB_CONFIG = {
    "host": os.getenv("ENCINO_ORM_MARIADB_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINO_ORM_MARIADB_PORT", "3307")),
    "user": os.getenv("ENCINO_ORM_MARIADB_USER", "root"),
    "password": os.getenv("ENCINO_ORM_MARIADB_PASSWORD", "admin"),
    "db": os.getenv("ENCINO_ORM_MARIADB_DB", "encino_orm_test"),
}


def test_mariadb_is_mysql_subclass():
    from encino_orm.mysql import MysqlDb
    assert issubclass(MariadbDb, MysqlDb)
    assert MariadbDb.dialect == "mariadb"


def test_mariadb_ddl_map_matches_mysql():
    assert ddl_type("pk", "mariadb") == "INT AUTO_INCREMENT PRIMARY KEY"
    assert ddl_type("str", "mariadb") == "VARCHAR(255)"
    assert ddl_type("json", "mariadb") == "JSON"


@pytest.fixture
async def mariadb_connected_db():
    cfg = dict(MARIADB_CONFIG)
    db_name = cfg.pop("db")

    admin = MariadbDb()
    try:
        await admin.connect(**cfg)
    except Exception as e:
        pytest.skip(f"MariaDB no disponible: {e}")

    await admin.execute(Query(f"CREATE DATABASE IF NOT EXISTS `{db_name}`", []))
    await admin.close()

    db = MariadbDb()
    await db.connect(db=db_name, **cfg)
    yield db
    await db.close()


class TestMariadbLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, mariadb_connected_db):
        db = mariadb_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, mariadb_connected_db):
        assert await mariadb_connected_db.is_alive() is True

    @pytest.mark.asyncio
    async def test_insert_and_last_id(self, mariadb_connected_db):
        db = mariadb_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS usuarios", []))
        await db.execute(Query(
            "CREATE TABLE usuarios (id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50))", []
        ))

        assert await db.execute(db.insert("usuarios", {"nombre": "Héctor"})) == 1
        assert await db.last_id() == 1

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Héctor"]
