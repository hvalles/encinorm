"""Tests de resiliencia (Fase 5): clasificación de desconexión por motor.

Bloque RESL-01: cada adaptador clasifica una desconexión simulada como
`is_disconnect_error(exc) is True` y NO misclasifica un error de lock/deadlock
(`is_lock_error(exc) is True` ⇒ `is_disconnect_error(exc) is False`). Los
builders de excepciones viven en `tests/_resilience_helpers.py` con las firmas
reales verificadas contra desconexiones reales (`05-RESEARCH.md`).

Los tests unitarios NO necesitan servidores: construyen la excepción del driver
con su tipo/errno/SQLSTATE/códigos reales. La construcción con el tipo REAL de
`pyodbc`/`oracledb` vive en tests `optional_engine` que degradan a skip si el
extra no está instalado.

Selector estable del bloque: `-k disconnect`.
"""

import pytest

from encino_orm import MariadbDb, MssqlDb, MysqlDb, OracleDb, PostgresDb, SqliteDb
from encino_orm.base import Db
from tests._resilience_helpers import (
    mssql_disconnect_idle,
    mssql_disconnect_midquery,
    mssql_lock,
    mssql_lock_timeout,
    mysql_disconnect,
    mysql_gone_away,
    mysql_interface,
    mysql_lock,
    mysql_lock_timeout,
    oracle_disconnect_dpy,
    oracle_disconnect_ora,
    oracle_lock,
    oracle_lock_timeout,
    oracle_serialization,
    pg_cached_stmt,
    pg_disconnect,
    pg_interface,
    pg_lock,
    pg_lock_not_available,
    pg_serialization,
    real_mssql_disconnect,
    real_oracle_disconnect,
    sqlite_disconnect,
    sqlite_disk_io,
    sqlite_lock,
)
from tests.conftest import engine_unavailable

# (clase de adaptador, builder de desconexión) — deben clasificar como disconnect.
_DISCONNECT_CASES = [
    (SqliteDb, sqlite_disconnect),
    (SqliteDb, sqlite_disk_io),
    (MysqlDb, mysql_disconnect),
    (MysqlDb, mysql_gone_away),
    (MysqlDb, mysql_interface),
    (MariadbDb, mysql_disconnect),
    (PostgresDb, pg_disconnect),
    (PostgresDb, pg_interface),
    (MssqlDb, mssql_disconnect_midquery),
    (MssqlDb, mssql_disconnect_idle),
    (OracleDb, oracle_disconnect_dpy),
    (OracleDb, oracle_disconnect_ora),
]

# (clase de adaptador, builder de lock) — deben clasificar como lock y NO disconnect.
_LOCK_CASES = [
    (SqliteDb, sqlite_lock),
    (MysqlDb, mysql_lock),
    (MysqlDb, mysql_lock_timeout),
    (MariadbDb, mysql_lock),
    (PostgresDb, pg_lock),
    (PostgresDb, pg_serialization),
    (PostgresDb, pg_lock_not_available),
    (MssqlDb, mssql_lock),
    (MssqlDb, mssql_lock_timeout),
    (OracleDb, oracle_lock),
    (OracleDb, oracle_lock_timeout),
    (OracleDb, oracle_serialization),
]

# Par disconnect/lock por motor, para la exclusión mutua (Success Criterion 1).
_ENGINE_CASES = [
    (SqliteDb, sqlite_disconnect, sqlite_lock),
    (MysqlDb, mysql_disconnect, mysql_lock),
    (MariadbDb, mysql_disconnect, mysql_lock),
    (PostgresDb, pg_disconnect, pg_lock),
    (MssqlDb, mssql_disconnect_midquery, mssql_lock),
    (OracleDb, oracle_disconnect_dpy, oracle_lock),
]


def test_db_default_is_disconnect_error_false():
    """El hook por defecto de `Db` es `False` (mismo contrato que `is_lock_error`).

    Se invoca sin instancia (`Db` es ABC) porque el cuerpo del hook no usa
    `self`; así se prueba el default sin construir un doble.
    """
    assert Db.is_disconnect_error(None, Exception("x")) is False


@pytest.mark.parametrize(("db_cls", "exc_factory"), _DISCONNECT_CASES)
def test_is_disconnect_error(db_cls, exc_factory):
    db = db_cls()
    assert db.is_disconnect_error(exc_factory()) is True


@pytest.mark.parametrize(("db_cls", "exc_factory"), _LOCK_CASES)
def test_lock_no_es_disconnect(db_cls, exc_factory):
    db = db_cls()
    exc = exc_factory()
    assert db.is_lock_error(exc) is True
    assert db.is_disconnect_error(exc) is False


def test_invalid_cached_statement_no_es_disconnect_ni_lock():
    """`InvalidCachedStatementError` es invalidación de statement cache, no pérdida."""
    db = PostgresDb()
    exc = pg_cached_stmt()
    assert db.is_disconnect_error(exc) is False
    assert db.is_lock_error(exc) is False


@pytest.mark.parametrize(("db_cls", "disconnect_factory", "lock_factory"), _ENGINE_CASES)
def test_disconnect_y_lock_son_excluyentes(db_cls, disconnect_factory, lock_factory):
    """Exclusión mutua por motor: un lock NUNCA se clasifica como disconnect."""
    db = db_cls()
    assert db.is_disconnect_error(disconnect_factory()) is True

    lock_exc = lock_factory()
    assert db.is_lock_error(lock_exc) is True
    assert db.is_disconnect_error(lock_exc) is False
    assert not (db.is_disconnect_error(lock_exc) and db.is_lock_error(lock_exc))


@pytest.mark.optional_engine
def test_disconnect_con_driver_real_mssql():
    try:
        exc = real_mssql_disconnect()
    except ImportError as e:  # pragma: no cover - depende del entorno
        engine_unavailable("mssql", e)
    assert MssqlDb().is_disconnect_error(exc) is True


@pytest.mark.optional_engine
def test_disconnect_con_driver_real_oracle():
    try:
        exc = real_oracle_disconnect()
    except ImportError as e:  # pragma: no cover - depende del entorno
        engine_unavailable("oracle", e)
    assert OracleDb().is_disconnect_error(exc) is True
