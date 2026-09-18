"""Mapa de DDL transaccional por dialecto (DATA-02, D-01). DB-free."""

from encino_orm.base import Db
from encino_orm.dialects import TRANSACTIONAL_DDL
from encino_orm.mariadb import MariadbDb
from encino_orm.mssql import MssqlDb
from encino_orm.mysql import MysqlDb
from encino_orm.oracle import OracleDb
from encino_orm.pool import PoolDb
from encino_orm.postgresql import PostgresDb
from encino_orm.sqlite import SqliteDb


class TestTransactionalDdlMap:
    def test_tiene_exactamente_los_seis_dialectos(self):
        assert set(TRANSACTIONAL_DDL) == {
            "sqlite",
            "mysql",
            "mariadb",
            "postgresql",
            "mssql",
            "oracle",
        }

    def test_motores_con_ddl_transaccional(self):
        # En estos tres el DDL comparte transacción con el ledger: un `pending`
        # nunca sobrevive a un fallo (el rollback lo elimina).
        for dialecto in ("sqlite", "postgresql", "mssql"):
            assert TRANSACTIONAL_DDL[dialecto] is True

    def test_motores_con_commit_implicito_del_ddl(self):
        # En estos tres el DDL commitea implícitamente ANTES de ejecutarse: un
        # `pending` puede sobrevivir y la reconciliación debe detectarlo.
        for dialecto in ("mysql", "mariadb", "oracle"):
            assert TRANSACTIONAL_DDL[dialecto] is False

    def test_db_default_es_conservador(self):
        assert Db.transactional_ddl is True


class TestAdapterTransactionalDdl:
    def test_adaptadores_con_ddl_transaccional(self):
        assert SqliteDb.transactional_ddl is True
        assert PostgresDb.transactional_ddl is True
        assert MssqlDb.transactional_ddl is True

    def test_adaptadores_con_commit_implicito_del_ddl(self):
        assert MysqlDb.transactional_ddl is False
        assert MariadbDb.transactional_ddl is False
        assert OracleDb.transactional_ddl is False

    def test_pool_delega_al_template(self):
        # Sin conectar: la property lee el template, no una conexión.
        assert PoolDb("sqlite").transactional_ddl is True
        assert PoolDb("postgresql").transactional_ddl is True
        assert PoolDb("mysql").transactional_ddl is False
        assert PoolDb("oracle").transactional_ddl is False
