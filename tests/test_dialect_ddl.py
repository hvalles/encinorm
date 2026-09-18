"""Mapa de DDL transaccional por dialecto (DATA-02, D-01). DB-free."""

from encino_orm.base import Db
from encino_orm.dialects import TRANSACTIONAL_DDL


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
