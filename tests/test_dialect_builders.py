"""Tests del builder DML compartido (`dialects/builders.py`), sin base de datos.

Cubren, por dialecto y por modo, el SQL exacto que el seam debe producir (el
mismo que producían los seis adaptadores, byte a byte) y el rechazo de
identificadores maliciosos ANTES de que el driver sea alcanzado.
"""

import ast
import inspect
from pathlib import Path

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
            qry = build_upsert(
                "t",
                {"a": 1},
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
        assert UPSERT_KIND["mariadb"] == "on_conflict"
        assert UPSERT_KIND["mysql"] == "on_duplicate"
        assert UPSERT_KIND["mssql"] == "merge"
        assert UPSERT_KIND["oracle"] == "merge"
        assert set(UPSERT_KINDS) == {"on_conflict", "on_duplicate", "merge"}

    def test_strategy_for_normaliza_engine_y_str(self):
        from encino_orm.engine import Engine

        assert strategy_for("mariadb") is strategy_for("mysql")
        assert strategy_for(Engine.ORACLE) is ORACLE_INSERT
        assert strategy_for("sqlite") is SQLITE_INSERT

    def test_strategy_for_dialecto_desconocido(self):
        with pytest.raises(ValueError):
            strategy_for("mongodb")


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
