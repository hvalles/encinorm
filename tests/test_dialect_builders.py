"""Tests del builder DML compartido (`dialects/builders.py`), sin base de datos.

Cubren, por dialecto y por modo, el SQL exacto que el seam debe producir (el
mismo que producían los seis adaptadores, byte a byte) y el rechazo de
identificadores maliciosos ANTES de que el driver sea alcanzado.
"""

import pytest

from encino_orm.dialects import (
    MSSQL_INSERT,
    MYSQL_INSERT,
    ORACLE_INSERT,
    POSTGRES_INSERT,
    SQLITE_INSERT,
    build_delete,
    build_insert,
    build_update,
)
from encino_orm.mariadb import MariadbDb
from encino_orm.mssql import MssqlDb
from encino_orm.mysql import MysqlDb
from encino_orm.oracle import OracleDb
from encino_orm.postgresql import PostgresDb
from encino_orm.sqlite import SqliteDb

# Nombres que el allowlist estricto debe rechazar (inyección, citado,
# cualificado, arranque no-alfabético, vacío, espacios, guiones).
MALICIOSOS = ["t; DROP TABLE x; --", "`x`", "a.b", "1abc", "", "a b", "a-b"]


def _spy_prepare(db, monkeypatch):
    """Sustituye `db._prepare` por un spy que registra y falla si se alcanza."""
    reached = []

    def fake_prepare(qry):
        reached.append(qry)
        raise AssertionError("_prepare no debe alcanzarse")

    monkeypatch.setattr(db, "_prepare", fake_prepare)
    return reached


def _assert_rechazo_antes_del_driver(db, monkeypatch):
    reached = _spy_prepare(db, monkeypatch)
    for nombre in MALICIOSOS:
        with pytest.raises(ValueError):
            db._prepare(build_insert(nombre, {"a": 1}, strategy=SQLITE_INSERT))
        with pytest.raises(ValueError):
            db._prepare(build_insert("t", {nombre: 1}, strategy=SQLITE_INSERT))
        with pytest.raises(ValueError):
            db._prepare(build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, schema=nombre))
        with pytest.raises(ValueError):
            db._prepare(
                build_insert(
                    "t", {"a": 1}, strategy=POSTGRES_INSERT, replace=True, conflict=[nombre]
                )
            )
        with pytest.raises(ValueError):
            db._prepare(build_update(nombre, {"id": 1}, {"a": 2}))
        with pytest.raises(ValueError):
            db._prepare(build_delete("t", {nombre: 1}))
    assert reached == []


class TestSqliteInsert:
    def test_plano(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=SQLITE_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.fields == [1, "x"]

    def test_replace(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=SQLITE_INSERT, replace=True)
        assert qry.sql_template == "INSERT OR REPLACE INTO t (a,b) VALUES ({0},{1})"

    def test_ignore_duplicated(self):
        qry = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, ignore_duplicated=True)
        assert qry.sql_template == "INSERT OR IGNORE INTO t (a) VALUES ({0})"

    def test_replace_gana_sobre_ignore(self):
        qry = build_insert(
            "t", {"a": 1}, strategy=SQLITE_INSERT, replace=True, ignore_duplicated=True
        )
        assert qry.sql_template == "INSERT OR REPLACE INTO t (a) VALUES ({0})"


class TestMysqlInsert:
    def test_plano(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=MYSQL_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.fields == [1, "x"]

    def test_replace(self):
        qry = build_insert("t", {"a": 1}, strategy=MYSQL_INSERT, replace=True)
        assert qry.sql_template == "REPLACE INTO t (a) VALUES ({0})"

    def test_ignore_duplicated(self):
        qry = build_insert("t", {"a": 1}, strategy=MYSQL_INSERT, ignore_duplicated=True)
        assert qry.sql_template == "INSERT IGNORE INTO t (a) VALUES ({0})"

    def test_mariadb_reutiliza_la_estrategia_mysql(self):
        db = MariadbDb()
        assert db.dialect == "mariadb"
        qry = build_insert("t", {"a": 1}, strategy=MYSQL_INSERT, replace=True)
        assert qry.sql_template == "REPLACE INTO t (a) VALUES ({0})"


class TestPostgresInsert:
    def test_plano(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=POSTGRES_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.fields == [1, "x"]

    def test_ignore_duplicated(self):
        qry = build_insert("t", {"a": 1}, strategy=POSTGRES_INSERT, ignore_duplicated=True)
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0}) ON CONFLICT DO NOTHING"

    def test_replace_sin_conflict_usa_la_primera_columna(self):
        qry = build_insert("t", {"a": 1}, strategy=POSTGRES_INSERT, replace=True)
        assert qry.sql_template == (
            "INSERT INTO t (a) VALUES ({0}) ON CONFLICT (a) DO UPDATE SET a = EXCLUDED.a"
        )

    def test_replace_con_conflict_compuesto_lleva_espacio(self):
        # Pin byte a byte: `build_insert` usa ", " (postgresql.py:170), a
        # diferencia de `build_upsert`, que usa "," sin espacio.
        qry = build_insert(
            "t", {"a": 1, "b": "x"}, strategy=POSTGRES_INSERT, replace=True, conflict=["a", "b"]
        )
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) "
            "ON CONFLICT (a, b) DO UPDATE SET a = EXCLUDED.a, b = EXCLUDED.b"
        )


class TestMssqlInsert:
    def test_plano(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=MSSQL_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.fields == [1, "x"]

    def test_ignore_duplicated_lleva_el_flag(self):
        qry = build_insert("t", {"a": 1}, strategy=MSSQL_INSERT, ignore_duplicated=True)
        assert qry.ignore_duplicated is True
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0})"

    def test_replace_merge_con_as(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=MSSQL_INSERT, replace=True)
        assert qry.sql_template == (
            "MERGE INTO t AS dst USING (SELECT {0} AS a, {1} AS b) AS src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.a = src.a, dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert qry.fields == [1, "x"]

    def test_replace_merge_conflict_explicito(self):
        qry = build_insert(
            "t", {"a": 1, "b": "x"}, strategy=MSSQL_INSERT, replace=True, conflict=["b"]
        )
        assert "ON (dst.b = src.b)" in qry.sql_template


class TestOracleInsert:
    def test_plano_sin_id_lleva_returning(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=ORACLE_INSERT)
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) RETURNING id INTO :ret_id"
        )
        assert qry.fields == [1, "x"]

    def test_plano_con_id_no_lleva_returning(self):
        qry = build_insert("t", {"id": 1}, strategy=ORACLE_INSERT)
        assert qry.sql_template == "INSERT INTO t (id) VALUES ({0})"

    def test_ignore_duplicated_lleva_el_flag(self):
        qry = build_insert("t", {"a": 1}, strategy=ORACLE_INSERT, ignore_duplicated=True)
        assert qry.ignore_duplicated is True
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0}) RETURNING id INTO :ret_id"

    def test_replace_merge_sin_as(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=ORACLE_INSERT, replace=True)
        assert qry.sql_template == (
            "MERGE INTO t dst USING (SELECT {0} AS a, {1} AS b) src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.a = src.a, dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert qry.fields == [1, "x"]


class TestUpdateYDelete:
    def test_update_numera_set_luego_where(self):
        qry = build_update("t", {"id": 1}, {"a": 2})
        assert qry.sql_template == "UPDATE t SET a = {0} WHERE id = {1}"
        assert qry.fields == [2, 1]

    def test_update_multiples_columnas(self):
        qry = build_update("t", {"id": 1}, {"a": 2, "b": 3})
        assert qry.sql_template == "UPDATE t SET a = {0},b = {1} WHERE id = {2}"
        assert qry.fields == [2, 3, 1]

    def test_delete(self):
        qry = build_delete("t", {"id": 1})
        assert qry.sql_template == "DELETE FROM t WHERE id = {0}"
        assert qry.fields == [1]

    def test_delete_multiples_llaves(self):
        qry = build_delete("t", {"a": 1, "b": 2})
        assert qry.sql_template == "DELETE FROM t WHERE a = {0} AND b = {1}"
        assert qry.fields == [1, 2]


class TestSchemaCualificado:
    def test_insert_con_schema(self):
        qry = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, schema="s")
        assert qry.sql_template == "INSERT INTO s.t (a) VALUES ({0})"

    def test_update_con_schema(self):
        qry = build_update("t", {"id": 1}, {"a": 2}, schema="s")
        assert qry.sql_template == "UPDATE s.t SET a = {0} WHERE id = {1}"

    def test_delete_con_schema(self):
        qry = build_delete("t", {"id": 1}, schema="s")
        assert qry.sql_template == "DELETE FROM s.t WHERE id = {0}"

    def test_schema_invalido_lanza(self):
        with pytest.raises(ValueError):
            build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, schema="s; DROP")

    def test_schema_none_no_cambia_nada(self):
        con = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT)
        sin = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, schema=None)
        assert con.sql_template == sin.sql_template


class TestRechazoPorAdaptador:
    """El driver nunca se alcanza: el builder lanza antes de `_prepare`."""

    def test_sqlite(self, monkeypatch):
        _assert_rechazo_antes_del_driver(SqliteDb(), monkeypatch)

    def test_mysql(self, monkeypatch):
        _assert_rechazo_antes_del_driver(MysqlDb(), monkeypatch)

    def test_mariadb(self, monkeypatch):
        _assert_rechazo_antes_del_driver(MariadbDb(), monkeypatch)

    def test_postgresql(self, monkeypatch):
        _assert_rechazo_antes_del_driver(PostgresDb(), monkeypatch)

    def test_mssql(self, monkeypatch):
        _assert_rechazo_antes_del_driver(MssqlDb(), monkeypatch)

    def test_oracle(self, monkeypatch):
        _assert_rechazo_antes_del_driver(OracleDb(), monkeypatch)


def _assert_adaptador_rechaza(db, monkeypatch):
    reached = _spy_prepare(db, monkeypatch)
    for nombre in MALICIOSOS:
        with pytest.raises(ValueError):
            db.insert(nombre, {"a": 1})
        with pytest.raises(ValueError):
            db.insert("t", {nombre: 1})
        with pytest.raises(ValueError):
            db.insert("t", {"a": 1}, schema=nombre)
        with pytest.raises(ValueError):
            db.update("t", {"id": 1}, {nombre: 1})
        with pytest.raises(ValueError):
            db.delete("t", {nombre: 1})
    assert reached == []


class TestAdaptadoresRechazanAntesDelDriver:
    """Camino público: el adaptador delega en el seam y valida antes del driver."""

    def test_sqlite(self, monkeypatch):
        _assert_adaptador_rechaza(SqliteDb(), monkeypatch)

    def test_mysql(self, monkeypatch):
        _assert_adaptador_rechaza(MysqlDb(), monkeypatch)

    def test_mariadb(self, monkeypatch):
        _assert_adaptador_rechaza(MariadbDb(), monkeypatch)

    def test_postgresql(self, monkeypatch):
        _assert_adaptador_rechaza(PostgresDb(), monkeypatch)

    def test_mssql(self, monkeypatch):
        _assert_adaptador_rechaza(MssqlDb(), monkeypatch)

    def test_oracle(self, monkeypatch):
        _assert_adaptador_rechaza(OracleDb(), monkeypatch)
