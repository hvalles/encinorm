import os

import pytest

from encinorm import MysqlDb, Query

MYSQL_CONFIG = {
    "host": os.getenv("ENCINORM_MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("ENCINORM_MYSQL_PORT", "3306")),
    "user": os.getenv("ENCINORM_MYSQL_USER", "root"),
    "password": os.getenv("ENCINORM_MYSQL_PASSWORD", "admin"),
    "db": os.getenv("ENCINORM_MYSQL_DB", "encinorm_test"),
}


@pytest.fixture
async def mysql_connected_db():
    cfg = dict(MYSQL_CONFIG)
    db_name = cfg.pop("db")

    admin = MysqlDb()
    try:
        await admin.connect(**cfg)
    except Exception as e:
        pytest.skip(f"MySQL no disponible: {e}")

    await admin.execute(Query(f"CREATE DATABASE IF NOT EXISTS `{db_name}`", []))
    await admin.close()

    db = MysqlDb()
    await db.connect(db=db_name, **cfg)
    yield db
    await db.close()


async def _reset(db, name, ddl):
    await db.execute(Query(f"DROP TABLE IF EXISTS {name}", []))
    await db.execute(Query(ddl, []))


class TestMysqlLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, mysql_connected_db):
        db = mysql_connected_db
        assert db.is_connected is True

        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, mysql_connected_db):
        db = mysql_connected_db
        assert await db.is_alive() is True

        await db.close()
        assert await db.is_alive() is False

    @pytest.mark.asyncio
    async def test_in_transaction(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "test_tx_state", "CREATE TABLE test_tx_state (id INT PRIMARY KEY, valor VARCHAR(50))")

        assert await db.in_transaction() is False

        await db.execute(db.insert("test_tx_state", {"id": 1, "valor": "tx"}))
        assert await db.in_transaction() is True

        await db.commit()
        assert await db.in_transaction() is False

    @pytest.mark.asyncio
    async def test_commit_and_rollback(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "test_tx", "CREATE TABLE test_tx (id INT PRIMARY KEY, valor VARCHAR(50))")

        await db.execute(db.insert("test_tx", {"id": 1, "valor": "commit_test"}))
        await db.commit()

        rows = await db.fetch_all(Query("SELECT valor FROM test_tx", []))
        assert len(rows) == 1
        assert rows[0]["valor"] == "commit_test"

        await db.execute(db.insert("test_tx", {"id": 2, "valor": "antes_rollback"}))
        await db.rollback()

        rows = await db.fetch_all(Query("SELECT valor FROM test_tx", []))
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_save_point_and_rollback_to_savepoint(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "test_sp", "CREATE TABLE test_sp (id INT AUTO_INCREMENT PRIMARY KEY, valor VARCHAR(50))")

        await db.execute(db.insert("test_sp", {"valor": "paso1"}))
        await db.save_point("antes_paso2")
        await db.execute(db.insert("test_sp", {"valor": "paso2"}))

        rows = await db.fetch_all(Query("SELECT valor FROM test_sp ORDER BY id", []))
        assert len(rows) == 2

        await db.rollback(save_point="antes_paso2")

        rows = await db.fetch_all(Query("SELECT valor FROM test_sp ORDER BY id", []))
        assert len(rows) == 1
        assert rows[0]["valor"] == "paso1"

        await db.commit()


class TestMysqlBuildersAndQueries:
    @pytest.mark.asyncio
    async def test_insert_execute_and_last_id(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "usuarios", "CREATE TABLE usuarios (id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50))")

        q = db.insert("usuarios", {"nombre": "Héctor"})
        assert await db.execute(q) == 1
        assert await db.last_id() == 1

        await db.execute(db.insert("usuarios", {"nombre": "Ana"}))
        assert await db.last_id() == 2

        rows = await db.fetch_all(Query("SELECT * FROM usuarios ORDER BY id", []))
        assert len(rows) == 2
        assert rows[0]["nombre"] == "Héctor"

    @pytest.mark.asyncio
    async def test_insert_ignore_duplicated(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "g", "CREATE TABLE g (id INT PRIMARY KEY, nombre VARCHAR(50) UNIQUE)")

        await db.execute(db.insert("g", {"id": 1, "nombre": "a"}))

        result = await db.execute(
            db.insert("g", {"id": 1, "nombre": "b"}, ignore_duplicated=True)
        )
        assert result == 0

        rows = await db.fetch_all(Query("SELECT * FROM g", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "a"

    @pytest.mark.asyncio
    async def test_insert_replace(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "r", "CREATE TABLE r (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("r", {"id": 1, "nombre": "a"}))
        await db.execute(db.insert("r", {"id": 1, "nombre": "b"}, replace=True))

        rows = await db.fetch_all(Query("SELECT * FROM r", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "b"

    @pytest.mark.asyncio
    async def test_delete(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "d", "CREATE TABLE d (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("d", {"id": 1, "nombre": "a"}))
        await db.execute(db.insert("d", {"id": 2, "nombre": "b"}))

        result = await db.execute(db.delete("d", {"id": 1}))
        assert result == 1

        rows = await db.fetch_all(Query("SELECT * FROM d", []))
        assert len(rows) == 1
        assert rows[0]["id"] == 2

    @pytest.mark.asyncio
    async def test_update(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "u", "CREATE TABLE u (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("u", {"id": 1, "nombre": "a"}))

        result = await db.execute(db.update("u", {"id": 1}, {"nombre": "modificado"}))
        assert result == 1

        row = await db.fetch_one(Query("SELECT * FROM u WHERE id = 1", []))
        assert row["nombre"] == "modificado"

    @pytest.mark.asyncio
    async def test_fetch_one_and_exists(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "e", "CREATE TABLE e (id INT PRIMARY KEY, nombre VARCHAR(50))")

        await db.execute(db.insert("e", {"id": 1, "nombre": "a"}))

        assert await db.exists(Query("SELECT 1 FROM e WHERE id = 1", [])) is True
        assert await db.exists(Query("SELECT 1 FROM e WHERE id = 99", [])) is False
        assert await db.fetch_one(Query("SELECT 1 FROM e WHERE id = 99", [])) is None

    @pytest.mark.asyncio
    async def test_fetch_many_pagination(self, mysql_connected_db):
        db = mysql_connected_db
        await _reset(db, "p", "CREATE TABLE p (id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(50))")

        for nombre in ["a", "b", "c", "d", "e"]:
            await db.execute(db.insert("p", {"nombre": nombre}))

        page1 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=1)
        page2 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=2)
        page3 = await db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=3)

        assert [r["nombre"] for r in page1] == ["a", "b"]
        assert [r["nombre"] for r in page2] == ["c", "d"]
        assert [r["nombre"] for r in page3] == ["e"]


class TestMysqlMigrations:
    @pytest.mark.asyncio
    async def test_migrate_applies_and_records(self, mysql_connected_db):
        db = mysql_connected_db
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
    async def test_migrate_is_idempotent(self, mysql_connected_db):
        db = mysql_connected_db
        await db.execute(Query("DROP TABLE IF EXISTS t1", []))
        await db.execute(Query("DROP TABLE IF EXISTS _encinorm_migrations", []))

        await db.migrate("v1", Query("CREATE TABLE t1 (id INT PRIMARY KEY)", []))
        await db.migrate("v1", Query("CREATE TABLE t1 (id INT PRIMARY KEY)", []))

        status = await db.migrate_status()
        assert len([s for s in status if s["name"] == "v1"]) == 1

    @pytest.mark.asyncio
    async def test_migrate_status_returns_history_in_order(self, mysql_connected_db):
        db = mysql_connected_db

        await db.execute(Query("DROP TABLE IF EXISTS a", []))
        await db.execute(Query("DROP TABLE IF EXISTS b", []))
        await db.execute(Query("DROP TABLE IF EXISTS _encinorm_migrations", []))
        await db.migrate("v1", Query("CREATE TABLE a (id INT PRIMARY KEY)", []))
        await db.migrate("v2", Query("CREATE TABLE b (id INT PRIMARY KEY)", []))

        status = await db.migrate_status()
        names = [s["name"] for s in status if s["name"] in ("v1", "v2")]
        assert names == ["v1", "v2"]
