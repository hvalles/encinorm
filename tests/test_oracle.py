import os
from typing import ClassVar

import pytest

from encino_orm import OracleDb, Query
from encino_orm.introspection.types import _normalize
from encino_orm.model import Filter, Model
from encino_orm.model.types import ddl_type
from encino_orm.oracle import _to_oracle
from tests._resilience_helpers import oracle_disconnect_dpy, oracle_disconnect_ora, oracle_lock
from tests._transfer_helpers import assert_copy_equivale, sqlite_source
from tests.conftest import engine_unavailable

ORACLE_CONFIG = {
    "host": os.getenv("ENCINO_ORM_ORACLE_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINO_ORM_ORACLE_PORT", "1521")),
    "service_name": os.getenv("ENCINO_ORM_ORACLE_SERVICE", "XEPDB1"),
    "user": os.getenv("ENCINO_ORM_ORACLE_USER", "system"),
    "password": os.getenv("ENCINO_ORM_ORACLE_PASSWORD", "admin"),
}


class _FakeError:
    def __init__(self, code):
        self.code = code


class _FakeExc(Exception):
    def __init__(self, code):
        self.args = (_FakeError(code),)


class TestOracleInternal:
    def test_to_oracle_named_binds(self):
        q = Query("SELECT * FROM t WHERE a = {0} AND b = {1}", [1, "x"])
        sql, values = _to_oracle(q.query[0], q.query[1])
        assert sql == "SELECT * FROM t WHERE a = :parameter_0000 AND b = :parameter_0001"
        assert values == {"parameter_0000": 1, "parameter_0001": "x"}

    def test_insert_builder_sin_returning_no_lo_emite(self):
        # EDICIÓN DELIBERADA (04-02): el `RETURNING id INTO :ret_id` es opt-in.
        db = OracleDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
        assert sql == "INSERT INTO t (a,b) VALUES (:parameter_0000,:parameter_0001)"
        assert values == {"parameter_0000": 1, "parameter_0001": "x"}

    def test_insert_builder_with_returning(self):
        db = OracleDb()
        q = db.insert("t", {"a": 1, "b": "x"}, returning="id")
        sql, values = db._prepare(q)
        assert sql == (
            "INSERT INTO t (a,b) VALUES (:parameter_0000,:parameter_0001) RETURNING id INTO :ret_id"
        )
        assert values == {"parameter_0000": 1, "parameter_0001": "x"}
        assert q.returns_id is True

    def test_insert_builder_ignore_duplicated_flag(self):
        db = OracleDb()
        q = db.insert("t", {"a": 1}, ignore_duplicated=True, returning="id")
        assert q.ignore_duplicated is True
        sql, _ = db._prepare(q)
        assert sql == "INSERT INTO t (a) VALUES (:parameter_0000) RETURNING id INTO :ret_id"

    def test_insert_builder_replace_merge_no_as(self):
        db = OracleDb()
        q = db.insert("t", {"a": 1, "b": "x"}, replace=True)
        sql, values = db._prepare(q)
        # EDICIÓN DELIBERADA (04-02, ORA-38104): el `SET` excluye la columna del
        # `ON` (fallback `columns[0]` = `a`) para que el MERGE sea EJECUTABLE.
        assert sql == (
            "MERGE INTO t dst USING (SELECT :parameter_0000 AS a, :parameter_0001 AS b) src "
            "ON (dst.a = src.a) "
            "WHEN MATCHED THEN UPDATE SET dst.b = src.b "
            "WHEN NOT MATCHED THEN INSERT (a,b) VALUES (src.a,src.b)"
        )
        assert values == {"parameter_0000": 1, "parameter_0001": "x"}
        assert q.returns_id is False

    def test_update_builder(self):
        db = OracleDb()
        sql, values = db._prepare(db.update("t", {"id": 1}, {"nombre": "mod"}))
        assert sql == "UPDATE t SET nombre = :parameter_0000 WHERE id = :parameter_0001"
        assert values == {"parameter_0000": "mod", "parameter_0001": 1}

    def test_is_unique_violation(self):
        db = OracleDb()
        assert db.is_unique_violation(_FakeExc(1)) is True  # ORA-00001
        assert db.is_unique_violation(_FakeExc(2291)) is False  # ORA-02291 FK

    def test_is_lock_error(self):
        db = OracleDb()
        assert db.is_lock_error(_FakeExc(60)) is True  # ORA-00060 deadlock
        assert db.is_lock_error(_FakeExc(54)) is True  # ORA-00054 lock timeout
        assert db.is_lock_error(_FakeExc(8177)) is True  # ORA-08177 serialization
        assert db.is_lock_error(_FakeExc(1)) is False

    def test_is_disconnect_error(self):
        """RESL-01: Oracle lee `full_code` (DPY-4011 trae `code == 0`)."""
        db = OracleDb()
        assert db.is_disconnect_error(oracle_disconnect_dpy()) is True
        assert db.is_disconnect_error(oracle_disconnect_ora()) is True

        lock = oracle_lock()
        assert db.is_lock_error(lock) is True
        assert db.is_disconnect_error(lock) is False
        assert not (db.is_disconnect_error(lock) and db.is_lock_error(lock))

    def test_normalize_new_types(self):
        assert _normalize("varchar2(255)") == ("str", 255, False)
        assert _normalize("nvarchar2(100)") == ("str", 100, False)
        assert _normalize("clob")[0] == "str"
        assert _normalize("blob")[0] == "blob"
        assert _normalize("raw(16)")[0] == "blob"
        assert _normalize("binary_double")[0] == "float"

    def test_ddl_map(self):
        assert (
            ddl_type("pk", "oracle")
            == "NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY"
        )
        assert ddl_type("str", "oracle") == "VARCHAR2(255)"
        assert ddl_type("bool", "oracle") == "NUMBER(1)"
        assert ddl_type("json", "oracle") == "CLOB"


@pytest.fixture
async def oracle_connected_db():
    db = OracleDb()
    try:
        await db.connect(**ORACLE_CONFIG)
    except Exception as e:
        engine_unavailable("oracle", e)
    yield db
    await db.close()


class _ParityModel(Model):
    """Modelo de paridad DIAL-03/DIAL-09 contra el motor real."""

    _table = "test_parity"
    nombre: str | None = None
    monto: float | None = None


class _MergeModel(Model):
    """Modelo para la regresión del MERGE: sin campos `datetime`.

    `Model._serialize` convierte `datetime`->`str` y Oracle no puede ligar ese
    string a una columna `TIMESTAMP` (ORA-01843) — limitación preexistente del
    camino de modelo, ajena a este plan. Se excluyen `created_at`/`updated_at`
    para que la sentencia MERGE sea realmente ejecutable.
    """

    _table = "test_parity"
    _fields_disabled: ClassVar[list] = ["created_at", "updated_at"]
    nombre: str | None = None
    monto: float | None = None


_PARITY_DDL = (
    "CREATE TABLE test_parity ("
    "id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, "
    "nombre VARCHAR2(50), monto NUMBER, enabled NUMBER(1) DEFAULT 1, "
    "created_at TIMESTAMP, updated_at TIMESTAMP)"
)
_PARITY_DDL_SIN_MONTO = (
    "CREATE TABLE test_parity ("
    "id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, "
    "nombre VARCHAR2(50), enabled NUMBER(1) DEFAULT 1, "
    "created_at TIMESTAMP, updated_at TIMESTAMP)"
)
_DROP_PARITY = (
    "BEGIN EXECUTE IMMEDIATE 'DROP TABLE test_parity'; "
    "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"
)


async def _reset_parity(db, ddl):
    await db._execute_raw(_DROP_PARITY)
    await db._execute_raw(ddl)


async def _seed_parity(db):
    for nombre, monto in [("Ana", 10.0), ("Luis", 20.0), ("Eva", 30.0)]:
        await db.execute(db.insert("test_parity", {"nombre": nombre, "monto": monto}))


@pytest.mark.integration
@pytest.mark.optional_engine
class TestOracleLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, oracle_connected_db):
        db = oracle_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, oracle_connected_db):
        assert await oracle_connected_db.is_alive() is True

    @pytest.mark.asyncio
    async def test_insert_execute_and_execute_insert(self, oracle_connected_db):
        db = oracle_connected_db
        await db._execute_raw(
            "BEGIN EXECUTE IMMEDIATE 'DROP TABLE usuarios'; "
            "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"
        )
        await db._execute_raw(
            "CREATE TABLE usuarios ("
            "id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, "
            "nombre VARCHAR2(50))"
        )

        q = db.insert("usuarios", {"nombre": "Héctor"}, returning="id")
        assert await db.execute_insert(q) == 1

        q2 = db.insert("usuarios", {"nombre": "Ana"}, returning="id")
        assert await db.execute_insert(q2) == 2

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Héctor", "Ana"]


@pytest.mark.integration
@pytest.mark.optional_engine
class TestOracleParity:
    """DIAL-03/DIAL-09: `count`/`paginate`/`list_tables`/`sync_schema`/`last_id`."""

    @pytest.mark.asyncio
    async def test_count_paginate_and_list_tables(self, oracle_connected_db):
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)
        await _seed_parity(db)

        assert await _ParityModel(db).count() == 3
        assert await _ParityModel(db).count(Filter.eq("nombre", "Ana")) == 1

        rec = await _ParityModel(db).paginate(limit=2, page=1)
        assert rec.total == 3
        assert len(rec.rows) == 2
        assert rec.limit == 2
        assert rec.page == 1

        tablas = await db.list_tables(limit=1000)
        assert tablas.total >= 1
        assert "test_parity" in {r["name"].lower() for r in tablas.rows}

    @pytest.mark.asyncio
    async def test_list_tables_filtrado_por_nombre(self, oracle_connected_db):
        # GAP 4: el filtro `name=` debe funcionar en los seis motores. Se usa el
        # nombre en MINÚSCULAS a propósito: Oracle devuelve los nombres en
        # MAYÚSCULAS y PostgreSQL es sensible por defecto, así que solo la
        # normalización `LOWER()` hace que el MISMO filtro funcione en los seis.
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)
        await _seed_parity(db)

        filtrado = await db.list_tables(name="test_parity", limit=1000)
        assert filtrado.total >= 1
        assert "test_parity" in {r["name"].lower() for r in filtrado.rows}

        ausente = await db.list_tables(name="zzz_no_existe_zzz", limit=1000)
        assert ausente.total == 0
        assert ausente.rows == []

    @pytest.mark.asyncio
    async def test_query_builder_aggregates(self, oracle_connected_db):
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)
        await _seed_parity(db)

        qb = _ParityModel(db).query()
        assert await qb.count() == 3
        assert await qb.sum("monto") == 60.0
        assert await qb.avg("monto") == 20.0
        assert await qb.min("monto") == 10.0
        assert await qb.max("monto") == 30.0

    @pytest.mark.asyncio
    async def test_query_builder_limit_first_exists(self, oracle_connected_db):
        # WR-03: `limit().all()`, `first()` y `exists()` deben ser válidos en el
        # motor real (la paginación la aplica el adaptador, sin `LIMIT` en línea).
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)
        await _seed_parity(db)

        # `order_by` EXPLÍCITO: `fetch_many` de MSSQL inyecta `ORDER BY (SELECT NULL)`
        # cuando falta, y sin orden la paginación no es determinista.
        p1 = await _ParityModel(db).query().order_by("nombre").limit(2).all()
        assert [r["nombre"] for r in p1] == ["Ana", "Eva"]

        p2 = await _ParityModel(db).query().order_by("nombre").limit(2, page=2).all()
        assert [r["nombre"] for r in p2] == ["Luis"]

        first = await _ParityModel(db).query().order_by("nombre").first()
        assert first["nombre"] == "Ana"

        assert (await _ParityModel(db).query().where(Filter.eq("nombre", "Ana")).exists()) is True
        assert (await _ParityModel(db).query().where(Filter.eq("nombre", "Zzz")).exists()) is False

    @pytest.mark.asyncio
    async def test_sync_schema_adds_missing_column(self, oracle_connected_db):
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL_SIN_MONTO)

        result = await _ParityModel(db).sync_schema()
        assert "monto" in result["added"]

        cols = {c.name.lower() for c in await db.columns_of("test_parity")}
        assert "monto" in cols

    @pytest.mark.asyncio
    async def test_execute_insert_characterization(self, oracle_connected_db):
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)

        q1 = db.insert("test_parity", {"nombre": "Ana"}, returning="id")
        assert await db.execute_insert(q1) == 1

        q2 = db.insert("test_parity", {"nombre": "Luis"}, returning="id")
        assert await db.execute_insert(q2) == 2

    @pytest.mark.asyncio
    async def test_last_id_retirado(self, oracle_connected_db):
        # REL-01 (0.3.0): la API post-hoc `last_id()` se retiró.
        assert not hasattr(oracle_connected_db, "last_id")
        with pytest.raises(AttributeError):
            _ = oracle_connected_db.last_id

    @pytest.mark.asyncio
    async def test_model_insert_replace_no_rompe_el_merge(self, oracle_connected_db):
        # ORA-38104 CERRADO (04-02, POOL-03): el `WHEN MATCHED THEN UPDATE SET`
        # del MERGE excluye la columna del `ON`, así que `Model.insert(
        # replace=True)` es EJECUTABLE en Oracle. Sigue sin devolver id: `MERGE …
        # RETURNING` no está soportado (ORA-00933), así que `insert` devuelve 0 y
        # `zoe.id` queda intacto. Antes este test caracterizaba el ORA-38104.
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)

        await _MergeModel(db, nombre="Ana", monto=10.0).insert()

        devuelto = await _MergeModel(db, nombre="Zoe", monto=5.0).insert(replace=True)
        assert devuelto == 0

        # El MERGE casa con la fila existente por el fallback `columns[0]`
        # (`enabled`): semántica PREEXISTENTE, incorrecta y ya documentada.
        filas = await db.fetch_all(Query("SELECT nombre, monto FROM test_parity", []))
        assert len(filas) == 1
        assert filas[0]["nombre"] == "Zoe"
        assert filas[0]["monto"] == 5.0

    @pytest.mark.asyncio
    async def test_model_upsert_merge_con_conflicto_explicito(self, oracle_connected_db):
        # CR-02: `Model.upsert` con una columna de DATOS como objetivo de conflicto
        # es ejecutable e idempotente en Oracle (antes no había NINGUNA cobertura de
        # `upsert` en este fichero). El `FROM dual` que Oracle exige en el `USING` lo
        # inyecta `OracleDb.execute`; no se toca el adaptador. NO se asserta el valor
        # de retorno (el `rowcount` de un MERGE no es fiable).
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)

        await _MergeModel(db, nombre="Ana", monto=10.0).upsert(conflict=["nombre"])
        filas = await db.fetch_all(Query("SELECT nombre, monto FROM test_parity", []))
        assert len(filas) == 1
        assert filas[0]["monto"] == 10.0

        await _MergeModel(db, nombre="Ana", monto=99.0).upsert(conflict=["nombre"])
        filas = await db.fetch_all(Query("SELECT nombre, monto FROM test_parity", []))
        assert len(filas) == 1
        assert filas[0]["monto"] == 99.0

    @pytest.mark.asyncio
    async def test_model_upsert_conflicto_por_defecto_falla_cerrado(self, oracle_connected_db):
        # CR-02: el default documentado (PK) no puede funcionar en `merge`; falla
        # CERRADO con `ValueError` accionable antes del driver, no con ORA-00904.
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)

        with pytest.raises(ValueError) as exc:
            await _MergeModel(db, nombre="Ana", monto=10.0).upsert()
        assert "no está en el INSERT" in str(exc.value)

    @pytest.mark.asyncio
    async def test_model_insert_replace_no_asigna_id_ajeno(self, oracle_connected_db):
        # CR-03: `Model.insert(replace=True)` en Oracle NO asigna un id ajeno.
        # Desde el fix de ORA-38104 (04-02) el MERGE es EJECUTABLE, pero sigue
        # sin capturar id (`MERGE … RETURNING` → ORA-00933), así que devuelve 0 y
        # `zoe.id` queda intacto.
        db = oracle_connected_db
        await _reset_parity(db, _PARITY_DDL)

        ana = _MergeModel(db, nombre="Ana", monto=10.0)
        await ana.insert()

        zoe = _MergeModel(db, nombre="Zoe", monto=5.0)
        devuelto = await zoe.insert(replace=True)
        assert devuelto == 0
        assert zoe.id is None
        assert zoe.id != ana.id


_DROP_T = (
    "BEGIN EXECUTE IMMEDIATE 'DROP TABLE t'; "
    "EXCEPTION WHEN OTHERS THEN IF SQLCODE != -942 THEN RAISE; END IF; END;"
)


@pytest.mark.integration
@pytest.mark.optional_engine
class TestTransferCopy:
    """Copia cross-engine sqlite -> Oracle vía `INSERT ALL` (PERF-01).

    Oracle es el único motor con `multi_values=False` (ORA-00938): este test es
    la sonda real de que `copy_table` pasa por el camino `INSERT ALL`.
    """

    @pytest.mark.asyncio
    async def test_copy_table_100_filas_insert_all(self, oracle_connected_db):
        db = oracle_connected_db
        src = await sqlite_source(n_rows=100)
        try:
            await db._execute_raw(_DROP_T)
            await assert_copy_equivale(src, db, n_rows=100)
        finally:
            await db._execute_raw(_DROP_T)
            await src.close()
