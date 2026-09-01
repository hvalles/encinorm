import pytest
from encinorm.query import Query


class TestSqliteLifecycle:
    @pytest.mark.asyncio
    async def test_connect_and_close(self, db):
        assert db.is_connected is False

        await db.connect(database=":memory:")
        assert db.is_connected is True

        await db.close()
        assert db.is_connected is False

    @pytest.mark.asyncio
    async def test_is_alive(self, db, connected_db):
        assert await db.is_alive() is False

        assert await connected_db.is_alive() is True
        await connected_db.close()
        assert await connected_db.is_alive() is False

    @pytest.mark.asyncio
    async def test_in_transaction(self, connected_db):
        assert await connected_db.in_transaction() is False

        await connected_db._connection.execute(
            "CREATE TABLE test_tx_state (id INTEGER PRIMARY KEY, valor TEXT)"
        )
        await connected_db.commit()

        await connected_db._connection.execute(
            "INSERT INTO test_tx_state (valor) VALUES (?)", ("tx",)
        )
        assert await connected_db.in_transaction() is True

        await connected_db.commit()
        assert await connected_db.in_transaction() is False

    @pytest.mark.asyncio
    async def test_connect_defaults_to_memory(self, db):
        await db.connect()
        assert db.is_connected is True
        assert db._database == ":memory:"
        await db.close()

    @pytest.mark.asyncio
    async def test_commit_and_rollback(self, connected_db):
        await connected_db._connection.execute(
            "CREATE TABLE test_lifecycle (id INTEGER PRIMARY KEY, valor TEXT)"
        )
        await connected_db.commit()

        await connected_db._connection.execute(
            "INSERT INTO test_lifecycle (valor) VALUES (?)", ("commit_test",)
        )
        await connected_db.commit()

        cursor = await connected_db._connection.execute(
            "SELECT valor FROM test_lifecycle"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "commit_test"

    @pytest.mark.asyncio
    async def test_rollback_discards_changes(self, connected_db):
        await connected_db._connection.execute(
            "CREATE TABLE test_tx (id INTEGER PRIMARY KEY, valor TEXT)"
        )
        await connected_db.commit()

        await connected_db._connection.execute(
            "INSERT INTO test_tx (valor) VALUES (?)", ("antes_rollback",)
        )

        await connected_db.rollback()

        cursor = await connected_db._connection.execute(
            "SELECT valor FROM test_tx"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_save_point_and_rollback_to_savepoint(self, connected_db):
        await connected_db._connection.execute(
            "CREATE TABLE test_sp (id INTEGER PRIMARY KEY, valor TEXT)"
        )
        await connected_db.commit()

        await connected_db._connection.execute(
            "INSERT INTO test_sp (valor) VALUES (?)", ("paso1",)
        )
        await connected_db.commit()

        await connected_db.save_point("antes_paso2")

        await connected_db._connection.execute(
            "INSERT INTO test_sp (valor) VALUES (?)", ("paso2",)
        )

        cursor = await connected_db._connection.execute(
            "SELECT valor FROM test_sp"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 2

        await connected_db.rollback(save_point="antes_paso2")

        cursor = await connected_db._connection.execute(
            "SELECT valor FROM test_sp"
        )
        rows = await cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "paso1"


class TestSqliteMigrations:
    @pytest.mark.asyncio
    async def test_migrate_applies_and_records(self, connected_db):
        await connected_db.migrate(
            "v1_crear_usuarios",
            Query("CREATE TABLE usuarios (id INTEGER PRIMARY KEY, nombre TEXT)", []),
        )

        status = await connected_db.migrate_status()
        assert len(status) == 1
        assert status[0]["name"] == "v1_crear_usuarios"
        assert "CREATE TABLE usuarios" in status[0]["sql_text"]
        assert status[0]["applied_at"] is not None

        tables = await connected_db.fetch_all(
            Query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='usuarios'",
                [],
            )
        )
        assert len(tables) == 1

    @pytest.mark.asyncio
    async def test_migrate_is_idempotent(self, connected_db):
        await connected_db.migrate(
            "v1", Query("CREATE TABLE t1 (id INTEGER PRIMARY KEY)", [])
        )
        await connected_db.migrate(
            "v1", Query("CREATE TABLE t1 (id INTEGER PRIMARY KEY)", [])
        )

        status = await connected_db.migrate_status()
        assert len(status) == 1

    @pytest.mark.asyncio
    async def test_migrate_status_returns_history_in_order(self, connected_db):
        await connected_db.migrate(
            "v1", Query("CREATE TABLE a (id INTEGER PRIMARY KEY)", [])
        )
        await connected_db.migrate(
            "v2", Query("CREATE TABLE b (id INTEGER PRIMARY KEY)", [])
        )

        status = await connected_db.migrate_status()
        assert [s["name"] for s in status] == ["v1", "v2"]


class TestSqliteBuildersAndQueries:
    @pytest.mark.asyncio
    async def test_insert_execute_and_last_id(self, connected_db):
        await connected_db.execute(
            Query(
                "CREATE TABLE usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)",
                [],
            )
        )

        q = connected_db.insert("usuarios", {"nombre": "Héctor"})
        assert await connected_db.execute(q) == 1
        assert await connected_db.last_id() == 1

        await connected_db.execute(connected_db.insert("usuarios", {"nombre": "Ana"}))
        assert await connected_db.last_id() == 2

        rows = await connected_db.fetch_all(Query("SELECT * FROM usuarios", []))
        assert len(rows) == 2
        assert rows[0]["nombre"] == "Héctor"

    @pytest.mark.asyncio
    async def test_insert_ignore_duplicated(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE g (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE)", [])
        )

        await connected_db.execute(connected_db.insert("g", {"id": 1, "nombre": "a"}))

        result = await connected_db.execute(
            connected_db.insert("g", {"id": 1, "nombre": "b"}, ignore_duplicated=True)
        )
        assert result == 0

        rows = await connected_db.fetch_all(Query("SELECT * FROM g", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "a"

    @pytest.mark.asyncio
    async def test_insert_replace(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE r (id INTEGER PRIMARY KEY, nombre TEXT)", [])
        )

        await connected_db.execute(connected_db.insert("r", {"id": 1, "nombre": "a"}))
        await connected_db.execute(connected_db.insert("r", {"id": 1, "nombre": "b"}, replace=True))

        rows = await connected_db.fetch_all(Query("SELECT * FROM r", []))
        assert len(rows) == 1
        assert rows[0]["nombre"] == "b"

    @pytest.mark.asyncio
    async def test_delete(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE d (id INTEGER PRIMARY KEY, nombre TEXT)", [])
        )
        await connected_db.execute(connected_db.insert("d", {"id": 1, "nombre": "a"}))
        await connected_db.execute(connected_db.insert("d", {"id": 2, "nombre": "b"}))

        result = await connected_db.execute(connected_db.delete("d", {"id": 1}))
        assert result == 1

        rows = await connected_db.fetch_all(Query("SELECT * FROM d", []))
        assert len(rows) == 1
        assert rows[0]["id"] == 2

    @pytest.mark.asyncio
    async def test_update(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE u (id INTEGER PRIMARY KEY, nombre TEXT, email TEXT)", [])
        )
        await connected_db.execute(connected_db.insert("u", {"id": 1, "nombre": "a", "email":"info@gmail.com"}))

        result = await connected_db.execute(
            connected_db.update("u", {"id": 1}, {"nombre": "modificado","email":"correo@gmail.com"})
        )
        assert result == 1

        row = await connected_db.fetch_one(Query("SELECT * FROM u WHERE id = 1", []))
        assert row["nombre"] == "modificado" and row['email']=="correo@gmail.com"

    @pytest.mark.asyncio
    async def test_fetch_one_and_exists(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE e (id INTEGER PRIMARY KEY, nombre TEXT)", [])
        )
        await connected_db.execute(connected_db.insert("e", {"id": 1, "nombre": "a"}))

        assert await connected_db.exists(Query("SELECT 1 FROM e WHERE id = 1", [])) is True
        assert await connected_db.exists(Query("SELECT 1 FROM e WHERE id = 99", [])) is False

        assert await connected_db.fetch_one(Query("SELECT 1 FROM e WHERE id = 99", [])) is None

    @pytest.mark.asyncio
    async def test_fetch_many_pagination(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE p (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", [])
        )
        for nombre in ["a", "b", "c", "d", "e"]:
            await connected_db.execute(connected_db.insert("p", {"nombre": nombre}))

        page1 = await connected_db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=1)
        page2 = await connected_db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=2)
        page3 = await connected_db.fetch_many(Query("SELECT * FROM p ORDER BY id", []), limit=2, page=3)

        assert [r["nombre"] for r in page1] == ["a", "b"]
        assert [r["nombre"] for r in page2] == ["c", "d"]
        assert [r["nombre"] for r in page3] == ["e"]

    @pytest.mark.asyncio
    async def test_paginate_raw(self, connected_db):
        await connected_db.execute(
            Query("CREATE TABLE pr (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", [])
        )
        for nombre in ["a", "b", "c", "d", "e"]:
            await connected_db.execute(connected_db.insert("pr", {"nombre": nombre}))

        rec = await connected_db.paginate(
            Query("SELECT * FROM pr WHERE nombre < {0} ORDER BY id", ["e"]),
            limit=2,
            page=2,
        )

        assert [r["nombre"] for r in rec.rows] == ["c", "d"]
        assert rec.total == 4
        assert rec.limit == 2
        assert rec.page == 2
        assert rec.total_pages == 2
        assert rec.has_next is False
        assert rec.has_prev is True
