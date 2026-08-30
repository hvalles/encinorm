import pytest

from encinorm.migration import (
    Migration,
    apply_migration,
    apply_migrations,
    migrations_from_dir,
    rollback_migration,
)
from encinorm.model import Model
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


class TestMigrationRunner:
    @pytest.mark.asyncio
    async def test_apply_migration_idempotent(self, db):
        m = Migration("v1", Query("CREATE TABLE t (id INTEGER PRIMARY KEY)", []))
        await apply_migration(db, m)
        await apply_migration(db, m)  # idempotente
        assert len(await db.migrate_status()) == 1

    @pytest.mark.asyncio
    async def test_apply_migration_accepts_str(self, db):
        m = Migration("v1", "CREATE TABLE t2 (id INTEGER PRIMARY KEY)")
        await apply_migration(db, m)
        row = await db.fetch_one(
            Query("SELECT name FROM sqlite_master WHERE type='table' AND name='t2'", [])
        )
        assert row is not None

    @pytest.mark.asyncio
    async def test_apply_migrations_in_order(self, db):
        ms = [
            Migration("001", "CREATE TABLE a (id INTEGER PRIMARY KEY)"),
            Migration("002", "CREATE TABLE b (id INTEGER PRIMARY KEY)"),
        ]
        await apply_migrations(db, ms)
        assert len(await db.migrate_status()) == 2

    @pytest.mark.asyncio
    async def test_rollback_migration(self, db):
        m = Migration(
            "v1",
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY)", []),
            Query("DROP TABLE t", []),
        )
        await apply_migration(db, m)
        await rollback_migration(db, m)
        row = await db.fetch_one(
            Query("SELECT name FROM sqlite_master WHERE type='table' AND name='t'", [])
        )
        assert row is None

    @pytest.mark.asyncio
    async def test_rollback_without_down_raises(self, db):
        m = Migration("v1", Query("CREATE TABLE t (id INTEGER PRIMARY KEY)", []))
        await apply_migration(db, m)
        with pytest.raises(Exception):
            await rollback_migration(db, m)


class TestMigrationsFromDir:
    def test_loads_in_order(self, tmp_path):
        (tmp_path / "001_a.py").write_text(
            "from encinorm.migration import Migration\n"
            "MIGRATION = Migration('001_a', 'SELECT 1')\n",
            encoding="utf-8",
        )
        (tmp_path / "002_b.py").write_text(
            "from encinorm.migration import Migration\n"
            "MIGRATION = Migration('002_b', 'SELECT 1')\n",
            encoding="utf-8",
        )
        ms = migrations_from_dir(str(tmp_path))
        assert [m.name for m in ms] == ["001_a", "002_b"]

    def test_missing_migration_raises(self, tmp_path):
        (tmp_path / "001_a.py").write_text("x = 1\n", encoding="utf-8")
        with pytest.raises(Exception):
            migrations_from_dir(str(tmp_path))


class T1(Model):
    _table = "t"
    a: str | None = None
    b: str | None = None


class T2(Model):
    _table = "t"
    a: str | None = None
    c: int | None = None


class T3(Model):
    _table = "t"
    a: int | None = None


class TestDiffSchema:
    @pytest.mark.asyncio
    async def test_added_and_dropped(self, db):
        await T1(db).create_table()
        diff = await T2(db).diff_schema()
        assert "c" in diff["added"]
        assert "b" in diff["dropped"]
        assert diff["changed"] == []

    @pytest.mark.asyncio
    async def test_changed(self, db):
        await T1(db).create_table()  # a: TEXT
        diff = await T3(db).diff_schema()
        assert "b" in diff["dropped"]
        changed = {c["column"]: c for c in diff["changed"]}
        assert changed["a"]["model"] == "int"
        assert changed["a"]["db"] == "str"

    @pytest.mark.asyncio
    async def test_no_diff(self, db):
        await T1(db).create_table()
        diff = await T1(db).diff_schema()
        assert diff == {"added": [], "dropped": [], "changed": []}


class TestSyncSchema:
    @pytest.mark.asyncio
    async def test_add_column(self, db):
        await T1(db).create_table()
        result = await T2(db).sync_schema()
        assert "c" in result["added"]
        assert result["dropped"] == []
        assert result["changed"] == []

    @pytest.mark.asyncio
    async def test_drop_column(self, db):
        await T1(db).create_table()
        result = await T2(db).sync_schema(drop_missing=True)
        assert "b" in result["dropped"]

    @pytest.mark.asyncio
    async def test_alter_types_sqlite_raises(self, db):
        await T1(db).create_table()
        with pytest.raises(NotImplementedError):
            await T3(db).sync_schema(alter_types=True)
