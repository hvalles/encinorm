from contextlib import asynccontextmanager

import pytest

from encino_orm import (
    Engine,
    MariadbDb,
    MssqlDb,
    MysqlDb,
    OracleDb,
    PostgresDb,
    SqliteDb,
    create_db,
    engine_of,
    is_mariadb,
    is_mssql,
    is_mysql,
    is_oracle,
    is_postgres,
    is_sqlite,
)
from encino_orm.dialects.strategies import LIMITS
from encino_orm.exceptions import UnsupportedEngineError
from encino_orm.model import Model
from encino_orm.pool import PoolDb


def test_engine_values():
    assert Engine.SQLITE.value == "sqlite"
    assert Engine.MYSQL.value == "mysql"
    assert Engine.MARIADB.value == "mariadb"
    assert Engine.POSTGRESQL.value == "postgresql"
    assert Engine.MSSQL.value == "mssql"
    assert Engine.ORACLE.value == "oracle"
    assert Engine.SQLITE == "sqlite"
    assert Engine.SQLITE == "sqlite"
    assert str(Engine.SQLITE) == "sqlite"
    assert [e.value for e in Engine] == [
        "sqlite",
        "mysql",
        "mariadb",
        "postgresql",
        "mssql",
        "oracle",
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


_ADAPTERS = [SqliteDb, MysqlDb, MariadbDb, PostgresDb, MssqlDb, OracleDb]


def test_max_params_and_max_rows_on_adapters():
    for cls in _ADAPTERS:
        db = cls()
        assert isinstance(db.MAX_PARAMS, int)
        assert db.MAX_PARAMS > 0
        assert isinstance(db.MAX_ROWS, int)
        assert db.MAX_ROWS > 0


def test_max_params_limits_cover_exactly_six_dialects():
    assert set(LIMITS) == {"sqlite", "mysql", "mariadb", "postgresql", "mssql", "oracle"}
    for limits in LIMITS.values():
        assert limits.provenance
        assert limits.max_params > 0
        assert limits.max_rows > 0


def test_max_params_pool_delegates_to_template():
    for engine in Engine:
        pool = PoolDb(engine)
        assert pool.MAX_PARAMS == pool._template.MAX_PARAMS
        assert pool.MAX_ROWS == pool._template.MAX_ROWS


class _Row(Model):
    _table = "row_limits"
    a: str | None = None
    b: int | None = None


# `_Row` aporta 5 columnas insertables (id/enabled/created_at/updated_at + a + b,
# sin el pk auto `id`), así que los techos del fake se eligen para que el chunk
# derivado sea observable.
_N_COLUMNS = 5


class _CapturingDb:
    """Fake de `Db` que captura los `Query` de `insert_many` y fija techos pequeños."""

    MAX_PARAMS = 15
    MAX_ROWS = 1000

    def __init__(self):
        self.queries = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, qry):
        self.queries.append(qry)


class _RowClampedDb(_CapturingDb):
    """`MAX_ROWS` es la restricción activa (más pequeña que `MAX_PARAMS // n`)."""

    MAX_PARAMS = 1000
    MAX_ROWS = 2


class _NoLimitsDb(_CapturingDb):
    """Fake sin constantes de dialecto: fuerza el último recurso `chunk=500`."""

    MAX_PARAMS = None
    MAX_ROWS = None


async def test_insert_many_derives_chunk_from_max_params():
    db = _CapturingDb()
    rows = [{"a": f"a{i}", "b": i} for i in range(7)]
    total = await _Row.insert_many(db, rows)
    assert total == 7
    # chunk = min(MAX_PARAMS // n_columnas, MAX_ROWS) = min(15 // 5, 1000) = 3
    assert [len(q.params) for q in db.queries] == [15, 15, 5]


async def test_insert_many_chunk_clamped_by_max_rows():
    db = _RowClampedDb()
    rows = [{"a": f"a{i}", "b": i} for i in range(5)]
    await _Row.insert_many(db, rows)
    # min(1000 // 5, 2) = 2
    assert [len(q.params) for q in db.queries] == [10, 10, 5]


async def test_insert_many_explicit_chunk_wins():
    db = _CapturingDb()
    rows = [{"a": f"a{i}", "b": i} for i in range(5)]
    await _Row.insert_many(db, rows, chunk=2)
    assert [len(q.params) for q in db.queries] == [10, 10, 5]


async def test_insert_many_falls_back_to_500_without_limits():
    db = _NoLimitsDb()
    rows = [{"a": f"a{i}", "b": i} for i in range(501)]
    await _Row.insert_many(db, rows)
    assert [len(q.params) for q in db.queries] == [500 * _N_COLUMNS, _N_COLUMNS]
