"""Snapshots DB-free del SQL de los seis dialectos (DIAL-07).

Este modulo congela el SQL que producen los seis adaptadores SIN abrir una
conexion: los constructores solo asignan ``self._connection = None``, los
builders ``insert``/``update``/``delete`` son puros y ``_prepare()`` solo aplica
una regex. Es la red que detecta deriva de dialecto en segundos sobre el job
SQLite siempre activo, sin contenedores.

Cada operacion compara UN snapshot con los seis dialectos indexados por nombre,
de modo que el diff de un fallo dice EXACTAMENTE que dialecto derivo.

Flujo de actualizacion (tras un cambio DELIBERADO de SQL):

    uv run pytest --snapshot-update -m syrupy_snapshot

y REVISAR el diff de ``tests/__snapshots__/test_sql_snapshots.ambr`` antes de
commitearlo: un ``.ambr`` regenerado sin revisar "bendice" una regresion
(T-02-29). syrupy es *sound*: un snapshot ausente FALLA, no se omite, asi que
los ``.ambr`` van en el MISMO commit que este fichero.

Politica de snapshots huerfanos: se acepta el comportamiento estricto por
defecto de syrupy (un snapshot que ya no se ejecuta FALLA). Un snapshot sin test
es peso muerto; el flujo de limpieza es ``--snapshot-update`` tras renombrar o
borrar un test. NO se anade ``--snapshot-warn-unused``.

Los snapshots de ``count``/``paginate``/``list_tables`` se capturan con un *spy*:
el adaptador real, sin ``connect()``, con ``fetch_one``/``fetch_many``
sustituidos por funciones que registran el ``Query`` recibido y devuelven filas
canonicas. Se congela el ``sql_template`` capturado (el que conserva los
``{n}``), que es justo la clase de SQL que DIAL-03 arreglo.
"""

from encino_orm import MariadbDb, MssqlDb, MysqlDb, OracleDb, PostgresDb, Query, SqliteDb
from encino_orm.model import Model

ADAPTERS = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "mariadb": MariadbDb,
    "postgresql": PostgresDb,
    "mssql": MssqlDb,
    "oracle": OracleDb,
}

_DML_DATA = {"a": 1, "b": "x"}


def _snapshot_builder(build) -> dict:
    """Aplica ``build(db)`` a los seis dialectos y congela el SQL preparado.

    ``build`` recibe un adaptador SIN ``connect()`` y devuelve el ``Query`` del
    builder. El resultado se indexa por dialecto para que un fallo de snapshot
    senale el dialecto culpable, no "algo cambio".
    """
    out = {}
    for name, cls in ADAPTERS.items():
        db = cls()
        sql, values = db._prepare(build(db))
        out[name] = {"sql": sql, "values": values}
    return out


class _SnapshotModel(Model):
    """Modelo minimo para congelar el SQL de ``Model.count`` sin motor."""

    _table = "snap_tabla"
    nombre: str | None = None


def _spy(cls):
    """Adaptador real sin ``connect()`` cuyos ``fetch_*`` capturan el ``Query``."""
    db = cls()
    captured: list[Query] = []

    async def fetch_one(qry):
        captured.append(qry)
        return {"n": 1}

    async def fetch_many(qry, limit, page):
        captured.append(qry)
        return [{"name": "snap_tabla"}]

    db.fetch_one = fetch_one
    db.fetch_many = fetch_many
    return db, captured


def _aggregate_template(qry: Query) -> str:
    """Congela el ``sql_template`` capturado y afirma el contrato ``AS n``."""
    assert "AS n" in qry.sql_template
    return qry.sql_template


# --- DML: builders compartidos x 6 dialectos ---


def test_insert_plain_snapshot(snapshot):
    actual = _snapshot_builder(lambda db: db.insert("t", dict(_DML_DATA)))
    assert actual == snapshot


def test_insert_ignore_duplicated_snapshot(snapshot):
    actual = _snapshot_builder(lambda db: db.insert("t", {"a": 1}, ignore_duplicated=True))
    assert actual == snapshot


def test_insert_replace_snapshot(snapshot):
    actual = _snapshot_builder(lambda db: db.insert("t", dict(_DML_DATA), replace=True))
    assert actual == snapshot


def test_insert_replace_with_conflict_snapshot(snapshot):
    actual = _snapshot_builder(
        lambda db: db.insert("t", dict(_DML_DATA), replace=True, conflict=["b"])
    )
    assert actual == snapshot


def test_update_snapshot(snapshot):
    actual = _snapshot_builder(lambda db: db.update("t", {"id": 1}, {"nombre": "mod"}))
    assert actual == snapshot


def test_delete_snapshot(snapshot):
    actual = _snapshot_builder(lambda db: db.delete("t", {"id": 1}))
    assert actual == snapshot


# --- count / paginate / list_tables: spy sobre el adaptador sin motor ---


async def test_list_tables_snapshot(snapshot):
    actual = {}
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.list_tables(limit=50, page=1)
        # `list_tables` llama primero a `fetch_one` (el conteo) y luego a
        # `fetch_many` (la lista de tablas); el orden es parte del contrato.
        actual[name] = {
            "count_wrapper": _aggregate_template(captured[0]),
            "tables": captured[1].sql_template,
        }
    assert actual == snapshot


async def test_list_tables_filtered_snapshot(snapshot):
    actual = {}
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.list_tables(name="snap", limit=50, page=1)
        # El camino FILTRADO anida dos tablas derivadas: la interior es el SQL
        # base y la exterior (alias `encino_orm_tables`) expone `name` como
        # columna REAL, porque en 5 de 6 dialectos `name` es un alias de SELECT
        # y no puede referenciarse en `WHERE`.
        actual[name] = {
            "count_wrapper": _aggregate_template(captured[0]),
            "tables": captured[1].sql_template,
            "params": captured[1].fields,
        }
    assert actual == snapshot


async def test_list_tables_filtrado_liga_el_valor_y_envuelve_en_tabla_derivada():
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.list_tables(name="snap", limit=50, page=1)
        page = captured[1]
        assert "encino_orm_tables" in page.sql_template, name
        assert "LOWER(name) LIKE LOWER({0})" in page.sql_template, name
        # El valor viaja LIGADO: el literal no aparece en el SQL.
        assert "snap" not in page.sql_template, name
        assert page.fields == ["%snap%"], name
        # El alias de la tabla derivada no puede empezar por `_` (Oracle
        # rechaza esos identificadores con ORA-00911).
        assert "_encino_orm_tables" not in page.sql_template, name


async def test_list_tables_sin_filtro_no_envuelve():
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.list_tables(limit=50, page=1)
        # Byte-identidad: sin `name` no hay tabla derivada ni parámetros.
        assert "encino_orm_tables" not in captured[1].sql_template, name
        assert captured[1].fields == [], name


async def test_list_tables_con_nombre_vacio_no_envuelve():
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.list_tables(name="", limit=50, page=1)
        # El parámetro por defecto es `""`, no `None`: debe comportarse como
        # "sin filtro".
        assert "encino_orm_tables" not in captured[1].sql_template, name
        assert captured[1].fields == [], name


async def test_paginate_snapshot(snapshot):
    actual = {}
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await db.paginate(Query("SELECT id FROM t WHERE a = {0}", [1]), limit=10, page=2)
        # `paginate` llama primero a `fetch_many` (la pagina) y luego a
        # `fetch_one` (el conteo).
        actual[name] = {
            "page": captured[0].sql_template,
            "count_wrapper": _aggregate_template(captured[1]),
        }
    assert actual == snapshot


async def test_count_snapshot(snapshot):
    actual = {}
    for name, cls in ADAPTERS.items():
        db, captured = _spy(cls)
        await _SnapshotModel(db).count()
        actual[name] = {"count": _aggregate_template(captured[0])}
    assert actual == snapshot
