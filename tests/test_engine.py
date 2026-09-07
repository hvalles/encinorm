import pytest

from encino_orm import (Engine, SqliteDb, create_db, engine_of, is_mariadb,
                      is_mssql, is_mysql, is_oracle, is_postgres, is_sqlite)
from encino_orm.exceptions import UnsupportedEngineError
from encino_orm.pool import PoolDb


def test_engine_values():
    assert Engine.SQLITE.value == "sqlite"
    assert Engine.MYSQL.value == "mysql"
    assert Engine.MARIADB.value == "mariadb"
    assert Engine.POSTGRESQL.value == "postgresql"
    assert Engine.MSSQL.value == "mssql"
    assert Engine.ORACLE.value == "oracle"
    assert Engine.SQLITE == "sqlite"
    assert "sqlite" == Engine.SQLITE
    assert str(Engine.SQLITE) == "sqlite"
    assert [e.value for e in Engine] == [
        "sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle",
    ]


def test_engine_of():
    assert engine_of(SqliteDb()) is Engine.SQLITE
    assert engine_of("mysql") is Engine.MYSQL
    assert engine_of(Engine.POSTGRESQL) is Engine.POSTGRESQL
    assert engine_of("mariadb") is Engine.MARIADB
    assert engine_of("mssql") is Engine.MSSQL
    assert engine_of("oracle") is Engine.ORACLE


def test_predicates():
    assert is_sqlite(SqliteDb()) is True
    assert is_mysql(SqliteDb()) is False
    assert is_postgres("postgresql") is True
    assert is_mariadb("mariadb") is True
    assert is_mssql("mssql") is True
    assert is_oracle("oracle") is True


def test_pool_engine_of():
    pool = PoolDb(Engine.MYSQL)
    assert engine_of(pool) is Engine.MYSQL
    assert pool.dialect == "mysql"


def test_engine_of_invalid():
    with pytest.raises(ValueError):
        engine_of("mongodb")


async def test_create_db_accepts_engine():
    db = await create_db(Engine.SQLITE, database=":memory:")
    assert engine_of(db) is Engine.SQLITE
    await db.close()

    db2 = await create_db("sqlite", database=":memory:")
    assert engine_of(db2) is Engine.SQLITE
    await db2.close()


async def test_create_db_invalid_engine():
    with pytest.raises(UnsupportedEngineError):
        await create_db("mongodb")
