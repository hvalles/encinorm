import os

import pytest

from encinorm import PostgresDb, Query
from encinorm.postgresql import _rowcount, _to_postgres

POSTGRES_CONFIG = {
    "host": os.getenv("ENCINORM_POSTGRES_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINORM_POSTGRES_PORT", "5432")),
    "user": os.getenv("ENCINORM_POSTGRES_USER", "postgres"),
    "password": os.getenv("ENCINORM_POSTGRES_PASSWORD", "admin"),
    "database": os.getenv("ENCINORM_POSTGRES_DB", "encinorm_test"),
}


class TestPostgresInternal:
    def test_to_postgres_translates_placeholders(self):
        q = Query("SELECT * FROM t WHERE a = {0} AND b = {1}", [1, "x"])
        sql, values = _to_postgres(q.query[0], q.query[1])
        assert sql == "SELECT * FROM t WHERE a = $1 AND b = $2"
        assert values == [1, "x"]

    def test_rowcount_parses_status(self):
        assert _rowcount("INSERT 0 1") == 1
        assert _rowcount("UPDATE 5") == 5
        assert _rowcount("DELETE 3") == 3
        assert _rowcount("CREATE TABLE") == 0

    def test_insert_builder_default(self):
        db = PostgresDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}))
        assert sql == "INSERT INTO t (a,b) VALUES ($1,$2)"
        assert values == [1, "x"]

    def test_insert_builder_ignore_duplicated(self):
        db = PostgresDb()
        sql, values = db._prepare(db.insert("t", {"a": 1}, ignore_duplicated=True))
        assert sql == "INSERT INTO t (a) VALUES ($1) ON CONFLICT DO NOTHING"
        assert values == [1]

    def test_insert_builder_replace(self):
        db = PostgresDb()
        sql, values = db._prepare(db.insert("t", {"a": 1, "b": "x"}, replace=True))
        assert sql == (
            "INSERT INTO t (a,b) VALUES ($1,$2) "
            "ON CONFLICT (a) DO UPDATE SET a = EXCLUDED.a, b = EXCLUDED.b"
        )
        assert values == [1, "x"]

    def test_update_builder(self):
        db = PostgresDb()
        sql, values = db._prepare(db.update("t", {"id": 1}, {"nombre": "mod"}))
        assert sql == "UPDATE t SET nombre = $1 WHERE id = $2"
        assert values == ["mod", 1]


@pytest.fixture
async def pg_connected_db():
    cfg = dict(POSTGRES_CONFIG)
    db_name = cfg.pop("database")

    admin = PostgresDb()
    try:
        await admin.connect(**cfg, database="postgres")
    except Exception as e:
        pytest.skip(f"PostgreSQL no disponible: {e}")

    try:
        await admin.execute(Query(f"CREATE DATABASE {db_name}", []))
    except Exception:
        pass
    await admin.close()

    db = PostgresDb()
    await db.connect(**cfg, database=db_name)
    yield db
    await db.close()


async def _reset(db, name, ddl):
    await db.execute(Query(f"DROP TABLE IF EXISTS {name}", []))
    await db.execute(Query(ddl, []))


class TestPostgresLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, pg_connected_db):
        db = pg_connected_db
        assert db.is_connected is True
        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, pg_connected_db):
        db = pg_connected_db
        assert await db.is_alive() is True
        await db.close()
        assert await db.is_alive() is False

    @pytest.mark.asyncio
    async def test_transaction_context(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "test_tx", "CREATE TABLE test_tx (id SERIAL PRIMARY KEY, valor VARCHAR(50))")

        async with db.transaction():
            await db.execute(db.insert("test_tx", {"valor": "a"}))
            assert await db.in_transaction() is True

        rows = await db.fetch_all(Query("SELECT * FROM test_tx", []))
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_save_point_and_rollback(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "test_sp", "CREATE TABLE test_sp (id SERIAL PRIMARY KEY, valor VARCHAR(50))")

        async with db.transaction():
            await db.execute(db.insert("test_sp", {"valor": "paso1"}))
            await db.save_point("antes_paso2")
            await db.execute(db.insert("test_sp", {"valor": "paso2"}))

            rows = await db.fetch_all(Query("SELECT valor FROM test_sp ORDER BY id", []))
            assert len(rows) == 2

            await db.rollback(save_point="antes_paso2")
            rows = await db.fetch_all(Query("SELECT valor FROM test_sp ORDER BY id", []))
            assert len(rows) == 1
            assert rows[0]["valor"] == "paso1"


class TestPostgresBuildersAndQueries:
    @pytest.mark.asyncio
    async def test_insert_execute_and_last_id(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "usuarios", "CREATE TABLE usuarios (id SERIAL PRIMARY KEY, nombre VARCHAR(50))")

        assert await db.execute(db.insert("usuarios", {"nombre": "Héctor"})) == 1
        assert await db.last_id() == 1

        await db.execute(db.insert("usuarios", {"nombre": "Ana"}))
        assert await db.last_id() == 2

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert len(rows) == 2
        assert rows[0]["nombre"] == "Héctor"

    @pytest.mark.asyncio
    async def test_insert_ignore_duplicated(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "g", "CREATE TABLE g (id INT PRIMARY KEY, nombre VARCHAR(50) UNIQUE)")

        await db.execute(db.insert("g", {"id": 1, "nombre": "a"}))
        result = await db.execute(db.insert("g", {"id": 1, "nombre": "b"}, ignore_duplicated=True))
        assert result == 0

        rows = await db.fetch_all(Query("SELECT * FROM g", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "a"

    @pytest.mark.asyncio
    async def test_insert_replace(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "r", "CREATE TABLE r (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("r", {"id": 1, "nombre": "a"}))
        await db.execute(db.insert("r", {"id": 1, "nombre": "b"}, replace=True))

        rows = await db.fetch_all(Query("SELECT * FROM r", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "b"

    @pytest.mark.asyncio
    async def test_delete(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "d", "CREATE TABLE d (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("d", {"id": 1, "nombre": "a"}))
        await db.execute(db.insert("d", {"id": 2, "nombre": "b"}))

        result = await db.execute(db.delete("d", {"id": 1}))
        assert result == 1

        rows = await db.fetch_all(Query("SELECT * FROM d", []))
        assert len(rows) == 1
        assert rows[0]["id"] == 2

    @pytest.mark.asyncio
    async def test_update(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "u", "CREATE TABLE u (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("u", {"id": 1, "nombre": "a"}))
        result = await db.execute(db.update("u", {"id": 1}, {"nombre": "modificado"}))
        assert result == 1

        row = await db.fetch_one(Query("SELECT * FROM u WHERE id = 1", []))
        assert row["nombre"] == "modificado"

    @pytest.mark.asyncio
    async def test_fetch_one_and_exists(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "e", "CREATE TABLE e (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("e", {"id": 1, "nombre": "a"}))

        assert await db.exists(Query("SELECT 1 FROM e WHERE id = 1", [])) is True
        assert await db.exists(Query("SELECT 1 FROM e WHERE id = 99", [])) is False
        assert await db.fetch_one(Query("SELECT 1 FROM e WHERE id = 99", [])) is None

    @pytest.mark.asyncio
    async def test_fetch_many_pagination(self, pg_connected_db):
        db = pg_connected_db
        await _reset(db, "p", "CREATE TABLE p (id SERIAL PRIMARY KEY, nombre VARCHAR(50))")

        for nombre in ["a", "b", "c", "d", "e"]:
            await db.execute(db.insert("p", {"nombre": nombre}))

        page1 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=1)
        page2 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=2)
        page3 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=3)

        assert [r["nombre"] for r in page1] == ["a", "b"]
        assert [r["nombre"] for r in page2] == ["c", "d"]
        assert [r["nombre"] for r in page3] == ["e"]


class TestPostgresMigrations:
    @pytest.mark.asyncio
    async def test_migrate_applies_and_records(self, pg_connected_db):
        db = pg_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS usuarios", []))
        await db.execute(Query("DROP TABLE IF EXISTS _encinorm_migrations", []))

        await db.migrate(
            "v1_crear_usuarios",
            Query("CREATE TABLE usuarios (id INT PRIMARY KEY, nombre VARCHAR(50))", []),
        )

        status = await db.migrate_status()
        matching = [s for s in status if s["name"] == "v1_crear_usuarios"]
        assert len(matching) == 1
        assert "CREATE TABLE usuarios" in matching[0]["sql_text"]
        assert matching[0]["applied_at"] is not None

    @pytest.mark.asyncio
    async def test_migrate_is_idempotent(self, pg_connected_db):
        db = pg_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS t1", []))
        await db.execute(Query("DROP TABLE IF EXISTS _encinorm_migrations", []))

        await db.migrate("v1", Query("CREATE TABLE t1 (id INT PRIMARY KEY)", []))
        await db.migrate("v1", Query("CREATE TABLE t1 (id INT PRIMARY KEY)", []))

        status = await db.migrate_status()
        assert len([s for s in status if s["name"] == "v1"]) == 1
