import pytest

from encinorm import (Engine, SqliteDb, create_db, engine_of, is_mysql,
                      is_postgres, is_sqlite)
from encinorm.exceptions import UnsupportedEngineError
from encinorm.pool import PoolDb


def test_engine_values():
    assert Engine.SQLITE.value == "sqlite"
    assert Engine.MYSQL.value == "mysql"
    assert Engine.POSTGRESQL.value == "postgresql"
    assert Engine.SQLITE == "sqlite"
    assert "sqlite" == Engine.SQLITE
    assert str(Engine.SQLITE) == "sqlite"
    assert [e.value for e in Engine] == ["sqlite", "mysql", "postgresql"]


def test_engine_of():
    assert engine_of(SqliteDb()) is Engine.SQLITE
    assert engine_of("mysql") is Engine.MYSQL
    assert engine_of(Engine.POSTGRESQL) is Engine.POSTGRESQL


def test_predicates():
    assert is_sqlite(SqliteDb()) is True
    assert is_mysql(SqliteDb()) is False
    assert is_postgres("postgresql") is True


def test_pool_engine_of():
    pool = PoolDb(Engine.MYSQL)
    assert engine_of(pool) is Engine.MYSQL
    assert pool.dialect == "mysql"


def test_engine_of_invalid():
    with pytest.raises(ValueError):
        engine_of("oracle")


async def test_create_db_accepts_engine():
    db = await create_db(Engine.SQLITE, database=":memory:")
    assert engine_of(db) is Engine.SQLITE
    await db.close()

    db2 = await create_db("sqlite", database=":memory:")
    assert engine_of(db2) is Engine.SQLITE
    await db2.close()


async def test_create_db_invalid_engine():
    with pytest.raises(UnsupportedEngineError):
        await create_db("oracle")
