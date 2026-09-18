import os

import pytest

from encino_orm import MariadbDb, Query
from encino_orm.model import Filter, Model
from encino_orm.model.types import ddl_type
from tests.conftest import engine_unavailable

MARIADB_CONFIG = {
    "host": os.getenv("ENCINO_ORM_MARIADB_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINO_ORM_MARIADB_PORT", "3307")),
    "user": os.getenv("ENCINO_ORM_MARIADB_USER", "root"),
    "password": os.getenv("ENCINO_ORM_MARIADB_PASSWORD", "admin"),
    "db": os.getenv("ENCINO_ORM_MARIADB_DB", "encino_orm_test"),
}


def test_mariadb_is_mysql_subclass():
    from encino_orm.mysql import MysqlDb

    assert issubclass(MariadbDb, MysqlDb)
    assert MariadbDb.dialect == "mariadb"


def test_mariadb_ddl_map_matches_mysql():
    assert ddl_type("pk", "mariadb") == "INT AUTO_INCREMENT PRIMARY KEY"
    assert ddl_type("str", "mariadb") == "VARCHAR(255)"
    assert ddl_type("json", "mariadb") == "JSON"


@pytest.fixture
async def mariadb_connected_db():
    cfg = dict(MARIADB_CONFIG)
    db_name = cfg.pop("db")

    admin = MariadbDb()
    try:
        await admin.connect(**cfg)
    except Exception as e:
        engine_unavailable("mariadb", e)

    await admin.execute(Query(f"CREATE DATABASE IF NOT EXISTS `{db_name}`", []))
    await admin.close()

    db = MariadbDb()
    await db.connect(db=db_name, **cfg)
    yield db
    await db.close()


class _ParityModel(Model):
    """Modelo de paridad DIAL-03/DIAL-09 contra el motor real."""

    _table = "test_parity"
    nombre: str | None = None
    monto: float | None = None


_PARITY_DDL = (
    "CREATE TABLE test_parity ("
    "id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50), monto DOUBLE, "
    "enabled TINYINT(1) DEFAULT 1, created_at DATETIME, updated_at DATETIME)"
)
_PARITY_DDL_SIN_MONTO = (
    "CREATE TABLE test_parity ("
    "id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50), "
    "enabled TINYINT(1) DEFAULT 1, created_at DATETIME, updated_at DATETIME)"
)


class _UpsertModel(Model):
    """Modelo dedicado de upsert: clave ÚNICA DE DATO (no la PK autoincremental).

    `Model.upsert` omite `id` del INSERT cuando la PK es autoincremental, así que
    `ON DUPLICATE KEY UPDATE` solo puede dispararse sobre una clave que SÍ viaja
    en el INSERT. Mismo motivo por el que `tests/test_bulk_upsert.py` usa
    `Usuario(email UNIQUE)` + `upsert(conflict=["email"])`.
    """

    _table = "test_upsert_parity"
    nombre: str | None = None
    monto: float | None = None


_UPSERT_DDL = (
    "CREATE TABLE test_upsert_parity ("
    "id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50) UNIQUE, monto DOUBLE, "
    "enabled TINYINT(1) DEFAULT 1, created_at DATETIME, updated_at DATETIME)"
)


async def _reset(db, ddl):
    await db.execute(Query("DROP TABLE IF EXISTS test_parity", []))
    await db.execute(Query(ddl, []))


async def _seed_parity(db):
    for nombre, monto in [("Ana", 10.0), ("Luis", 20.0), ("Eva", 30.0)]:
        await db.execute(db.insert("test_parity", {"nombre": nombre, "monto": monto}))


@pytest.mark.integration
class TestMariadbLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, mariadb_connected_db):
        db = mariadb_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, mariadb_connected_db):
        assert await mariadb_connected_db.is_alive() is True

    @pytest.mark.asyncio
    async def test_insert_and_last_id(self, mariadb_connected_db):
        db = mariadb_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS usuarios", []))
        await db.execute(
            Query(
                "CREATE TABLE usuarios (id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50))", []
            )
        )

        assert await db.execute(db.insert("usuarios", {"nombre": "Héctor"})) == 1
        assert await db.last_id() == 1

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Héctor"]


@pytest.mark.integration
class TestMariadbParity:
    """DIAL-03/DIAL-09: `count`/`paginate`/`list_tables`/`sync_schema`/`last_id`."""

    @pytest.mark.asyncio
    async def test_count_paginate_and_list_tables(self, mariadb_connected_db):
        db = mariadb_connected_db
        await _reset(db, _PARITY_DDL)
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
    async def test_query_builder_aggregates(self, mariadb_connected_db):
        db = mariadb_connected_db
        await _reset(db, _PARITY_DDL)
        await _seed_parity(db)

        qb = _ParityModel(db).query()
        assert await qb.count() == 3
        assert await qb.sum("monto") == 60.0
        assert await qb.avg("monto") == 20.0
        assert await qb.min("monto") == 10.0
        assert await qb.max("monto") == 30.0

    @pytest.mark.asyncio
    async def test_query_builder_limit_first_exists(self, mariadb_connected_db):
        # WR-03: `limit().all()`, `first()` y `exists()` deben ser válidos en el
        # motor real (la paginación la aplica el adaptador, sin `LIMIT` en línea).
        db = mariadb_connected_db
        await _reset(db, _PARITY_DDL)
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
    async def test_sync_schema_adds_missing_column(self, mariadb_connected_db):
        db = mariadb_connected_db
        await _reset(db, _PARITY_DDL_SIN_MONTO)

        result = await _ParityModel(db).sync_schema()
        assert "monto" in result["added"]

        cols = {c.name for c in await db.columns_of("test_parity")}
        assert "monto" in cols

    @pytest.mark.asyncio
    async def test_last_id_characterization(self, mariadb_connected_db):
        db = mariadb_connected_db
        await _reset(db, _PARITY_DDL)

        await db.execute(db.insert("test_parity", {"nombre": "Ana"}))
        assert await db.last_id() == 1

        await db.execute(db.insert("test_parity", {"nombre": "Luis"}))
        assert await db.last_id() == 2

    @pytest.mark.asyncio
    async def test_model_upsert_on_duplicate_key(self, mariadb_connected_db):
        # WR-04: `Model.upsert` debe emitir `ON DUPLICATE KEY UPDATE` (MariaDB no
        # implementa `ON CONFLICT`). El objetivo de conflicto es una clave ÚNICA
        # DE DATO presente en el INSERT, no la PK autoincremental (que se omite).
        db = mariadb_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS test_upsert_parity", []))
        await db.execute(Query(_UPSERT_DDL, []))

        obj = _UpsertModel(db, nombre="Ana", monto=10.0)
        await obj.insert()

        obj.monto = 99.0
        await obj.upsert(conflict=["nombre"])

        # `count() == 1` + `monto == 99.0` distinguen el UPDATE en sitio de un
        # INSERT plano (que dejaría dos filas); no es una tautología de "no lanza".
        assert await _UpsertModel(db).count() == 1
        filas = await _UpsertModel(db).search(Filter.eq("nombre", "Ana"))
        assert len(filas) == 1
        assert filas[0].monto == 99.0
