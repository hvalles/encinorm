"""Tests del builder DML compartido (`dialects/builders.py`), sin base de datos.

Cubren, por dialecto y por modo, el SQL exacto que el seam debe producir (el
mismo que producían los seis adaptadores, byte a byte) y el rechazo de
identificadores maliciosos ANTES de que el driver sea alcanzado.
"""

import ast
import inspect
from contextlib import asynccontextmanager
from pathlib import Path
from typing import ClassVar

import pytest

from encino_orm.dialects import (
    MSSQL_INSERT,
    MYSQL_INSERT,
    ORACLE_INSERT,
    POSTGRES_INSERT,
    SQLITE_INSERT,
    UPSERT_KIND,
    UPSERT_KINDS,
    build_delete,
    build_insert,
    build_update,
    build_upsert,
    strategy_for,
)
from encino_orm.mariadb import MariadbDb
from encino_orm.model import Model
from encino_orm.mssql import MssqlDb
from encino_orm.mysql import MysqlDb
from encino_orm.oracle import OracleDb
from encino_orm.postgresql import PostgresDb
from encino_orm.query import Query
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
        # EDICIÓN DELIBERADA (04-02, ORA-38104): el `SET` EXCLUYE la columna del
        # `ON` (el fallback `columns[0]` = `a`); actualizarla es ORA-38104 en
        # Oracle. Mismo patrón que `build_upsert` con `update_cols`.
        assert qry.sql_template == (
            "MERGE INTO t AS dst USING (SELECT {0} AS a, {1} AS b) AS src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert qry.fields == [1, "x"]
        assert qry.returns_id is False

    def test_replace_merge_conflict_explicito(self):
        qry = build_insert(
            "t", {"a": 1, "b": "x"}, strategy=MSSQL_INSERT, replace=True, conflict=["b"]
        )
        assert "ON (dst.b = src.b)" in qry.sql_template
        assert "SET dst.a = src.a" in qry.sql_template
        assert "SET dst.a = src.a, dst.b" not in qry.sql_template

    def test_replace_merge_todas_conflicto_lanza(self):
        # Fix ORA-38104: si no queda ninguna columna actualizable, se falla
        # CERRADO en vez de emitir un `SET` inválido.
        with pytest.raises(ValueError, match="sin columnas actualizables"):
            build_insert("t", {"a": 1}, strategy=MSSQL_INSERT, replace=True)

    def test_insert_plano_con_returning_lleva_output_inserted(self):
        qry = build_insert("t", {"a": 1, "b": 2}, strategy=MSSQL_INSERT, returning="id")
        assert qry.sql_template == "INSERT INTO t (a,b) OUTPUT INSERTED.id VALUES ({0},{1})"
        assert qry.returns_id is True
        assert qry.id_column == "id"

    def test_insert_plano_sin_returning_no_lleva_output(self):
        qry = build_insert("t", {"a": 1, "b": 2}, strategy=MSSQL_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.returns_id is False
        assert qry.id_column is None


class TestOracleInsert:
    def test_plano_sin_returning_no_lo_emite(self):
        # EDICIÓN DELIBERADA (04-02): el `RETURNING id INTO :ret_id` deja de ser
        # incondicional y pasa a ser OPT-IN del llamador. Sin `returning`, el SQL
        # es byte-idéntico al INSERT plano.
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=ORACLE_INSERT)
        assert qry.sql_template == "INSERT INTO t (a,b) VALUES ({0},{1})"
        assert qry.fields == [1, "x"]
        assert qry.returns_id is False
        assert qry.id_column is None

    def test_plano_con_returning_lleva_returning_into(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=ORACLE_INSERT, returning="id")
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) RETURNING id INTO :ret_id"
        )
        assert qry.returns_id is True
        assert qry.id_column == "id"

    def test_plano_con_id_sin_returning_no_lleva_returning(self):
        qry = build_insert("t", {"id": 1}, strategy=ORACLE_INSERT)
        assert qry.sql_template == "INSERT INTO t (id) VALUES ({0})"

    def test_ignore_duplicated_lleva_el_flag(self):
        qry = build_insert("t", {"a": 1}, strategy=ORACLE_INSERT, ignore_duplicated=True)
        assert qry.ignore_duplicated is True
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0})"

    def test_replace_merge_sin_as(self):
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=ORACLE_INSERT, replace=True)
        # EDICIÓN DELIBERADA (04-02, ORA-38104): el `SET` excluye la columna del
        # `ON` (fallback `columns[0]` = `a`) para que el MERGE sea EJECUTABLE en
        # Oracle. Sigue sin capturar id: `MERGE … RETURNING` no existe (ORA-00933).
        assert qry.sql_template == (
            "MERGE INTO t dst USING (SELECT {0} AS a, {1} AS b) src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert qry.fields == [1, "x"]
        assert qry.returns_id is False


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


class TestQueryMetadata:
    """Metadata de captura de id en `Query` (patrón `ignore_duplicated`)."""

    def test_defaults(self):
        q = Query("INSERT INTO t (a) VALUES ({0})", [1])
        assert q.returns_id is False
        assert q.id_column is None

    def test_expone_metadata_y_la_propaga_en_with_params(self):
        q = Query("INSERT INTO t (a) VALUES ({0})", [1], returns_id=True, id_column="id")
        assert q.returns_id is True
        assert q.id_column == "id"
        q2 = q.with_params([2])
        assert q2.returns_id is True
        assert q2.id_column == "id"
        assert q2.fields == [2]

    def test_metadata_fuera_de_eq_y_hash(self):
        a = Query("INSERT INTO t (a) VALUES ({0})", [1])
        b = Query("INSERT INTO t (a) VALUES ({0})", [1], returns_id=True, id_column="id")
        assert a == b
        assert hash(a) == hash(b)


class TestInsertReturning:
    """`build_insert(returning=)` es OPT-IN y valida el nombre de columna."""

    def test_sqlite_returning_no_cambia_el_sql_pero_marca_metadata(self):
        qry = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, returning="id")
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0})"
        assert qry.returns_id is True
        assert qry.id_column == "id"

    def test_sqlite_sin_returning_byte_identico(self):
        con = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT, returning=None)
        sin = build_insert("t", {"a": 1}, strategy=SQLITE_INSERT)
        assert con.sql_template == sin.sql_template
        assert con.returns_id is False

    def test_postgres_returning_va_al_final(self):
        qry = build_insert("t", {"a": 1}, strategy=POSTGRES_INSERT, returning="id")
        assert qry.sql_template == "INSERT INTO t (a) VALUES ({0}) RETURNING id"
        assert qry.returns_id is True

    def test_postgres_returning_tras_on_conflict(self):
        qry = build_insert(
            "t", {"a": 1, "b": 2}, strategy=POSTGRES_INSERT, replace=True, returning="id"
        )
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) "
            "ON CONFLICT (a) DO UPDATE SET a = EXCLUDED.a, b = EXCLUDED.b RETURNING id"
        )
        assert qry.returns_id is True

    def test_returning_invalido_falla_cerrado(self):
        for strategy in (POSTGRES_INSERT, MSSQL_INSERT, ORACLE_INSERT, SQLITE_INSERT):
            with pytest.raises(ValueError):
                build_insert("t", {"a": 1}, strategy=strategy, returning="id; DROP TABLE x")


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


class TestBuildUpsert:
    def test_on_conflict_sqlite(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=SQLITE_INSERT,
            upsert_kind="on_conflict",
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) ON CONFLICT (a) DO UPDATE SET b = excluded.b"
        )
        assert qry.fields == [1, "x"]

    def test_on_conflict_objetivo_sin_espacio(self):
        # Pin byte a byte: `build_upsert` usa "," (model.py:624), mientras que
        # el `ON CONFLICT` de `build_insert` usa ", " (postgresql.py:170).
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=SQLITE_INSERT,
            upsert_kind="on_conflict",
            conflict=["a", "b"],
            update_cols=["b"],
        )
        assert "ON CONFLICT (a,b) DO UPDATE SET" in qry.sql_template

    def test_on_duplicate_mysql(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=MYSQL_INSERT,
            upsert_kind="on_duplicate",
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) ON DUPLICATE KEY UPDATE b = VALUES(b)"
        )

    def test_build_upsert_mariadb_emite_on_duplicate_key(self):
        # WR-04: MariaDB habla el protocolo MySQL y espera `ON DUPLICATE KEY
        # UPDATE`, no el `ON CONFLICT` de PostgreSQL/SQLite.
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=strategy_for("mariadb"),
            upsert_kind=UPSERT_KIND["mariadb"],
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template == (
            "INSERT INTO t (a,b) VALUES ({0},{1}) ON DUPLICATE KEY UPDATE b = VALUES(b)"
        )
        assert "ON CONFLICT" not in qry.sql_template
        assert strategy_for("mariadb") is strategy_for("mysql")

    def test_merge_mssql_con_as(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=MSSQL_INSERT,
            upsert_kind="merge",
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template == (
            "MERGE INTO t AS dst USING (SELECT {0} AS a, {1} AS b) AS src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )

    def test_merge_oracle_sin_as(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=ORACLE_INSERT,
            upsert_kind="merge",
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template.startswith(
            "MERGE INTO t dst USING (SELECT {0} AS a, {1} AS b) src ON (dst.a = src.a) "
        )

    def test_merge_update_col_ausente_falla(self):
        # WR-01: el SET `dst.b = src.b` exige que `b` esté en los datos del INSERT.
        with pytest.raises(ValueError, match="no está\\(n\\) en el INSERT"):
            build_upsert(
                "t",
                {"a": 1},
                strategy=MSSQL_INSERT,
                upsert_kind="merge",
                conflict=["a"],
                update_cols=["b"],
            )

    def test_merge_conflict_vacio_falla(self):
        # WR-01: `conflict=[]` produciría `ON ()` y llegaría al driver.
        with pytest.raises(ValueError, match="NO vacío"):
            build_upsert(
                "t",
                {"a": 1, "b": "x"},
                strategy=MSSQL_INSERT,
                upsert_kind="merge",
                conflict=[],
                update_cols=["b"],
            )

    def test_merge_update_values_no_exige_update_cols_en_src(self):
        # Con `update_values` el SET usa valores ligados, así que no toca `src`.
        qry = build_upsert(
            "t",
            {"a": 1},
            strategy=MSSQL_INSERT,
            upsert_kind="merge",
            conflict=["a"],
            update_cols=["b"],
            update_values=[2],
        )
        assert "src.b" not in qry.sql_template

    def test_update_values_on_conflict(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=SQLITE_INSERT,
            upsert_kind="on_conflict",
            conflict=["a"],
            update_cols=["b"],
            update_values=[9],
        )
        assert qry.sql_template.endswith("DO UPDATE SET b = {2}")
        assert qry.fields == [1, "x", 9]

    def test_update_values_on_duplicate(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=MYSQL_INSERT,
            upsert_kind="on_duplicate",
            conflict=["a"],
            update_cols=["b"],
            update_values=[9],
        )
        assert qry.sql_template.endswith("ON DUPLICATE KEY UPDATE b = {2}")
        assert qry.fields == [1, "x", 9]

    def test_update_values_merge(self):
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=MSSQL_INSERT,
            upsert_kind="merge",
            conflict=["a"],
            update_cols=["b"],
            update_values=[9],
        )
        assert "WHEN MATCHED THEN UPDATE SET dst.b = {2}" in qry.sql_template
        assert qry.fields == [1, "x", 9]

    def test_no_emite_returning(self):
        casos = (
            ("on_conflict", SQLITE_INSERT),
            ("on_duplicate", MYSQL_INSERT),
            ("merge", ORACLE_INSERT),
        )
        for kind, strategy in casos:
            # `b` va en los datos: el guard de MERGE (WR-01) exige que toda
            # columna del SET `dst.b = src.b` esté presente en el INSERT.
            qry = build_upsert(
                "t",
                {"a": 1, "b": 2},
                strategy=strategy,
                upsert_kind=kind,
                conflict=["a"],
                update_cols=["b"],
            )
            assert "RETURNING" not in qry.sql_template

    def test_rechaza_identificadores(self):
        for nombre in MALICIOSOS:
            with pytest.raises(ValueError):
                build_upsert(
                    nombre,
                    {"a": 1},
                    strategy=SQLITE_INSERT,
                    upsert_kind="on_conflict",
                    conflict=["a"],
                    update_cols=["b"],
                )
            with pytest.raises(ValueError):
                build_upsert(
                    "t",
                    {nombre: 1},
                    strategy=SQLITE_INSERT,
                    upsert_kind="on_conflict",
                    conflict=["a"],
                    update_cols=["b"],
                )
            with pytest.raises(ValueError):
                build_upsert(
                    "t",
                    {"a": 1},
                    strategy=SQLITE_INSERT,
                    upsert_kind="on_conflict",
                    conflict=[nombre],
                    update_cols=["b"],
                )
            with pytest.raises(ValueError):
                build_upsert(
                    "t",
                    {"a": 1},
                    strategy=SQLITE_INSERT,
                    upsert_kind="on_conflict",
                    conflict=["a"],
                    update_cols=[nombre],
                )
            with pytest.raises(ValueError):
                build_upsert(
                    "t",
                    {"a": 1},
                    strategy=SQLITE_INSERT,
                    upsert_kind="on_conflict",
                    conflict=["a"],
                    update_cols=["b"],
                    schema=nombre,
                )

    def test_upsert_kind_invalido(self):
        with pytest.raises(ValueError):
            build_upsert(
                "t",
                {"a": 1},
                strategy=SQLITE_INSERT,
                upsert_kind="nope",
                conflict=["a"],
                update_cols=["b"],
            )


class TestUpsertKindYStrategyFor:
    def test_mapa_por_dialecto(self):
        assert set(UPSERT_KIND) == {
            "sqlite",
            "mysql",
            "mariadb",
            "postgresql",
            "mssql",
            "oracle",
        }
        # EDICIÓN DELIBERADA (02-08): 02-02 preservó verbatim el valor previo
        # ("on_conflict") para mantener la byte-identidad del refactor, pero
        # MariaDB NO implementa `ON CONFLICT` (sintaxis de PostgreSQL/SQLite):
        # MariaDB 11 —imagen de CI promovida a motor REQUERIDO por 02-05— espera
        # `ON DUPLICATE KEY UPDATE`, la misma forma que MySQL.
        assert UPSERT_KIND["mariadb"] == "on_duplicate"
        assert UPSERT_KIND["mysql"] == "on_duplicate"
        assert UPSERT_KIND["mssql"] == "merge"
        assert UPSERT_KIND["oracle"] == "merge"
        assert set(UPSERT_KINDS) == {"on_conflict", "on_duplicate", "merge"}

    def test_upsert_kind_mariadb_es_on_duplicate(self):
        # Complementa `test_mapa_por_dialecto` (que pina el valor editado) y
        # verifica que el mapa conserva los seis dialectos.
        assert UPSERT_KIND["mariadb"] == "on_duplicate"
        assert set(UPSERT_KIND) == {
            "sqlite",
            "mysql",
            "mariadb",
            "postgresql",
            "mssql",
            "oracle",
        }

    def test_strategy_for_normaliza_engine_y_str(self):
        from encino_orm.engine import Engine

        assert strategy_for("mariadb") is strategy_for("mysql")
        assert strategy_for(Engine.ORACLE) is ORACLE_INSERT
        assert strategy_for("sqlite") is SQLITE_INSERT

    def test_strategy_for_dialecto_desconocido(self):
        with pytest.raises(ValueError):
            strategy_for("mongodb")


class _ModelDbRegistrador:
    """Doble a mano que registra lo que `Model.insert` pasa al adaptador.

    Implementa el contrato mínimo que usa `Model.insert`: `transaction()` como
    `asynccontextmanager`, `retry(fn)`, `insert(...)` (registrando los cinco
    argumentos) y `execute`/`last_id`. `dialect` lo lee `engine_of`.
    """

    def __init__(self, dialect):
        self.dialect = dialect
        self.insert_calls = []
        self._last = 1

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def retry(self, fn):
        return await fn()

    def insert(
        self, tabla, data, ignore_duplicated=False, replace=False, conflict=None, *, schema=None
    ):
        self.insert_calls.append((tabla, data, ignore_duplicated, replace, conflict))
        return Query("INSERT INTO t VALUES ({0})", [1])

    async def execute(self, qry):
        return 1

    async def last_id(self):
        return self._last


class _ModelPkAuto(Model):
    _table = "t"
    nombre: str | None = None
    monto: float | None = None


class _ModelPkNatural(Model):
    _table = "t"
    _primary_key = ("codigo",)
    _fields_disabled: ClassVar[list] = ["id"]
    codigo: str | None = None
    monto: float | None = None


class TestModelInsertConflictTarget:
    """WR-05: el objetivo de conflicto se deriva de la PK solo en `suffix`."""

    @pytest.mark.asyncio
    async def test_model_insert_replace_pasa_la_pk_como_conflicto(self):
        # suffix (PostgreSQL): la PK del modelo se pasa como objetivo de conflicto.
        pg = _ModelDbRegistrador("postgresql")
        await _ModelPkAuto(pg, nombre="Ana", monto=1.0).insert(replace=True)
        assert pg.insert_calls[-1][4] == ["id"]

        # merge (MSSQL/Oracle): `conflict=None` deliberado. El `src` derivado del
        # MERGE se construye solo con las columnas de `data` y la PK autoincremental
        # `id` está excluida; pasar ["id"] produciría `ON (dst.id = src.id)` sobre una
        # columna inexistente (MSSQL 4104 / Oracle ORA-00904). ESTE es el guard.
        for dialecto in ("mssql", "oracle"):
            db = _ModelDbRegistrador(dialecto)
            await _ModelPkAuto(db, nombre="Ana", monto=1.0).insert(replace=True)
            assert db.insert_calls[-1][4] is None

        # Sin `replace`: nunca se pasa objetivo de conflicto.
        pg_sin = _ModelDbRegistrador("postgresql")
        await _ModelPkAuto(pg_sin, nombre="Ana", monto=1.0).insert()
        assert pg_sin.insert_calls[-1][4] is None

        # PK natural: la clave SÍ viaja en el INSERT y el objetivo es la PK física.
        pg_nat = _ModelDbRegistrador("postgresql")
        await _ModelPkNatural(pg_nat, codigo="A", monto=1.0).insert(replace=True)
        assert pg_nat.insert_calls[-1][4] == ["codigo"]

        # El MERGE del fallback no referencia `src.id` (columna ausente en `src`);
        # su `ON` apunta a una columna presente en `data`.
        qry = build_insert(
            "t",
            {"nombre": "Ana", "monto": 1.0},
            strategy=strategy_for("mssql"),
            conflict=None,
            replace=True,
        )
        assert "src.id" not in qry.sql_template
        assert "ON (dst.nombre = src.nombre)" in qry.sql_template


class TestMergeConflictGuard:
    """CR-02: el render `merge` falla CERRADO cuando una columna de conflicto no
    está en las columnas del INSERT.

    El `src` derivado del MERGE se construye SOLO con las columnas de `data`; en
    un modelo de PK autoincremental la PK `id` está excluida, así que
    `ON (dst.id = src.id)` referencia una columna inexistente (MSSQL 207 /
    ORA-00904). El guard vive en el punto único `_merge_sql`, compartido por
    `build_insert` y `build_upsert`.
    """

    def test_build_upsert_merge_conflicto_ausente_lanza(self):
        for strategy in (MSSQL_INSERT, ORACLE_INSERT):
            with pytest.raises(ValueError) as exc:
                build_upsert(
                    "t",
                    {"nombre": "Zoe"},
                    strategy=strategy,
                    upsert_kind="merge",
                    conflict=["id"],
                    update_cols=["nombre"],
                )
            assert "no está en el INSERT" in str(exc.value)
            assert "'id'" in str(exc.value)

    def test_build_insert_merge_conflicto_ausente_lanza(self):
        # Defensa en profundidad: el mismo `_merge_sql` sirve a `build_insert`.
        with pytest.raises(ValueError):
            build_insert(
                "t", {"nombre": "Zoe"}, strategy=MSSQL_INSERT, replace=True, conflict=["id"]
            )

    def test_merge_con_conflicto_presente_sigue_byte_identico(self):
        # El guard solo AÑADE rechazo: un conflicto presente produce el MISMO SQL.
        qry = build_upsert(
            "t",
            {"a": 1, "b": "x"},
            strategy=MSSQL_INSERT,
            upsert_kind="merge",
            conflict=["a"],
            update_cols=["b"],
        )
        assert qry.sql_template == (
            "MERGE INTO t AS dst USING (SELECT {0} AS a, {1} AS b) AS src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )

    def test_fallback_columns0_sigue_siendo_valido(self):
        # El fallback `columns[0]` de `build_insert` está en `columns` por
        # construcción, así que el guard no lo alcanza.
        qry = build_insert("t", {"a": 1, "b": "x"}, strategy=MSSQL_INSERT, replace=True)
        assert "ON (dst.a = src.a)" in qry.sql_template

    @pytest.mark.asyncio
    async def test_model_upsert_default_pk_autoincremental_falla_cerrado(self):
        # El default documentado de `Model.upsert` es la PK; en un modelo
        # autoincremental la PK no viaja en `data`, así que el render `merge`
        # debe lanzar ANTES de alcanzar al driver (no un 207 / ORA-00904).
        for dialecto in ("mssql", "oracle"):
            db = _ModelDbRegistrador(dialecto)
            with pytest.raises(ValueError) as exc:
                await _ModelPkAuto(db, nombre="Ana", monto=1.0).upsert()
            assert "no está en el INSERT" in str(exc.value)


class _ModelDbMerge:
    """Doble cuyo `insert()` devuelve un `Query` de MERGE y un `last_id()` OBSOLETO.

    Reproduce CR-03: `MssqlDb.execute` refresca `_last_id` solo para sentencias
    `INSERT` y `OracleDb.execute` solo cuando la sentencia lleva `RETURNING`; un
    MERGE nunca refresca el cache. El doble declara `_last = 1` a propósito (el id
    de OTRA fila) para probar que `Model.insert` no lo consume ni lo asigna.
    """

    def __init__(self, dialect):
        self.dialect = dialect
        self.queries = []
        self._last = 1

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def retry(self, fn):
        return await fn()

    def insert(
        self, tabla, data, ignore_duplicated=False, replace=False, conflict=None, *, schema=None
    ):
        sql = (
            "MERGE INTO t AS dst USING (SELECT {0} AS nombre) AS src "
            "ON (dst.nombre = src.nombre) "
            "WHEN MATCHED THEN UPDATE SET dst.nombre = src.nombre "
            "WHEN NOT MATCHED THEN INSERT (nombre) VALUES (src.nombre)"
        )
        return Query(sql, ["Zoe"])

    async def execute(self, qry):
        self.queries.append(qry)
        return 1

    async def last_id(self):
        return self._last


class TestModelInsertMergeNoConsumeIdObsoleto:
    """CR-03: `Model.insert` no consume ni asigna un `last_id()` obsoleto en MERGE."""

    @pytest.mark.asyncio
    async def test_merge_no_devuelve_ni_asigna_id_obsoleto(self):
        for dialecto in ("mssql", "oracle"):
            db = _ModelDbMerge(dialecto)
            obj = _ModelPkAuto(db, nombre="Zoe", monto=5.0)
            assert await obj.insert(replace=True) == 0
            assert obj.id is None
            # La sentencia SÍ se ejecutó: no se trata de saltarse la escritura.
            assert len(db.queries) == 1

    @pytest.mark.asyncio
    async def test_insert_plano_sigue_consumiendo_last_id(self):
        db = _ModelDbRegistrador("mssql")
        obj = _ModelPkAuto(db, nombre="Zoe", monto=5.0)
        assert await obj.insert() == 1
        assert obj.id == 1

    @pytest.mark.asyncio
    async def test_suffix_replace_sigue_consumiendo_last_id(self):
        db = _ModelDbRegistrador("postgresql")
        obj = _ModelPkAuto(db, nombre="Zoe", monto=5.0)
        assert await obj.insert(replace=True) == 1
        assert obj.id == 1


# Ruta normalizada (`\` -> `/`) para que los guards se comporten igual en
# Windows y Linux.
MODEL_PATH = (Path(__file__).resolve().parents[1] / "encino_orm" / "model" / "model.py").as_posix()

_LITERALES_DML = ("ON DUPLICATE KEY", "MERGE INTO", "ON CONFLICT")


def _nodos_docstring(tree):
    """Ids de los `ast.Constant` que son docstring (primer statement de un bloque)."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return docstrings


def test_guard_model_no_construye_dml_de_upsert():
    """Guard 1: ningún literal DML de upsert fuera de un docstring en `model.py`."""
    tree = ast.parse(Path(MODEL_PATH).read_text(encoding="utf-8"))
    docstrings = _nodos_docstring(tree)
    ofensores = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and any(literal in node.value for literal in _LITERALES_DML)
    ]
    assert ofensores == []


def test_guard_upsert_no_ramifica_por_engine():
    """Guard 2: `Model.upsert` no referencia `Engine.*` (anti-patrón eliminado)."""
    from encino_orm.model.model import Model

    src = inspect.getsource(Model.upsert)
    assert "Engine.MYSQL" not in src
    assert "Engine.MSSQL" not in src
    assert "Engine.ORACLE" not in src
