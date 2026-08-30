import asyncio

import pytest

from encinorm.cli import _build_parser, _conn_kwargs, main
from encinorm.query import Query
from encinorm.sqlite import SqliteDb


class TestConnKwargs:
    def test_sqlite(self):
        args = _build_parser().parse_args(
            ["generate", "models", "sqlite", "--database", "app.db"]
        )
        assert _conn_kwargs(args) == {"database": "app.db"}

    def test_sqlite_default_memory(self):
        args = _build_parser().parse_args(["generate", "models", "sqlite"])
        assert _conn_kwargs(args) == {"database": ":memory:"}

    def test_mysql(self):
        args = _build_parser().parse_args(
            ["generate", "models", "mysql", "--host", "h", "--user", "u",
             "--password", "p", "--database", "d"]
        )
        assert _conn_kwargs(args) == {"host": "h", "user": "u", "password": "p", "db": "d"}

    def test_postgres(self):
        args = _build_parser().parse_args(
            ["generate", "models", "postgresql", "--host", "h", "--database", "d"]
        )
        assert _conn_kwargs(args) == {"host": "h", "database": "d"}


class TestGenerateModels:
    def test_end_to_end(self, tmp_path):
        db_file = tmp_path / "app.db"

        async def _setup():
            d = SqliteDb()
            await d.connect(database=str(db_file))
            await d.execute(Query(
                "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "agente VARCHAR(50) NOT NULL, rfc VARCHAR(13))", []
            ))
            await d.close()

        asyncio.run(_setup())

        out = tmp_path / "out"
        code = main([
            "generate", "models", "sqlite",
            "--database", str(db_file), "--folder", str(out),
        ])
        assert code == 0
        text = (out / "agentes.py").read_text(encoding="utf-8")
        assert "class Agentes(Model):" in text
        assert "STR_50" in text

    def test_no_command_returns_nonzero(self):
        assert main([]) == 1
