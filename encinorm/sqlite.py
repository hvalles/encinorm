import re
import time

import aiosqlite

from .base import Db, logger
from .exceptions import ConnectionError
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
_MIGRATIONS_TABLE = "_encinorm_migrations"


def _log(method, sql, values, elapsed):
    logger.debug("sqlite %s (%.4fs) trace_id=%r sql=%r params=%r",
                 method, elapsed, current_trace_id(), sql, values)


def _to_positional(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "?"

    return _PLACEHOLDER_RE.sub(repl, sql), values


class SqliteDb(Db):
    dialect = "sqlite"

    def __init__(self):
        self._connection = None
        self._database = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    def is_lock_error(self, exc: Exception) -> bool:
        return "locked" in str(exc) or "busy" in str(exc)

    async def connect(self, **kwargs):
        database = kwargs.get("database", ":memory:")
        self._database = database
        self._connection = await aiosqlite.connect(database)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.commit()

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def is_alive(self) -> bool:
        if not self._connection:
            return False
        try:
            cursor = await self._connection.execute("SELECT 1")
            await cursor.fetchone()
            await cursor.close()
            return True
        except Exception:
            return False

    async def in_transaction(self) -> bool:
        if not self._connection:
            return False
        return self._connection.in_transaction

    async def commit(self):
        if self._connection:
            await self._connection.commit()

    async def rollback(self, save_point: str = None):
        if not self._connection:
            return
        if save_point:
            await self._connection.execute(f"ROLLBACK TO SAVEPOINT {save_point}")
        else:
            await self._connection.rollback()

    async def save_point(self, name: str):
        if self._connection:
            await self._connection.execute(f"SAVEPOINT {name}")

    def _ensure_connected(self):
        if not self._connection:
            raise ConnectionError("No hay conexión activa a la base de datos.")

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_positional(qry.query[0], qry.query[1])

    # --- Builders (construyen Query, no ejecutan) ---

    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False):
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ",".join("{%d}" % i for i in range(len(columns)))

        keyword = "INSERT"
        if replace:
            keyword = "INSERT OR REPLACE"
        elif ignore_duplicated:
            keyword = "INSERT OR IGNORE"

        sql = f"{keyword} INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
        return Query(sql, values)

    def delete(self, tabla: str, keys: dict):
        columns = list(keys.keys())
        values = list(keys.values())
        where = " AND ".join(f"{col} = {{{i}}}" for i, col in enumerate(columns))
        sql = f"DELETE FROM {tabla} WHERE {where}"
        return Query(sql, values)

    def update(self, tabla: str, keys: dict, values: dict):
        set_cols = list(values.keys())
        set_vals = list(values.values())
        set_clause = ",".join(f"{col} = {{{i}}}" for i, col in enumerate(set_cols))

        key_cols = list(keys.keys())
        key_vals = list(keys.values())
        offset = len(set_cols)
        where = " AND ".join(
            f"{col} = {{{offset + i}}}" for i, col in enumerate(key_cols)
        )

        sql = f"UPDATE {tabla} SET {set_clause} WHERE {where}"
        return Query(sql, set_vals + key_vals)

    # --- Ejecución / Consulta ---

    async def execute(self, qry: Query) -> int:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        await cursor.close()
        _log("execute", sql, values, time.monotonic() - t0)
        return cursor.rowcount

    async def fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        rows = await cursor.fetchall()
        await cursor.close()
        _log("fetch_all", sql, values, time.monotonic() - t0)
        return [dict(row) for row in rows]

    async def fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        row = await cursor.fetchone()
        await cursor.close()
        _log("fetch_one", sql, values, time.monotonic() - t0)
        return dict(row) if row is not None else None

    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        sql = sql.rstrip().rstrip(";")
        offset = (page - 1) * limit
        t0 = time.monotonic()
        cursor = await self._connection.execute(
            f"{sql} LIMIT {limit} OFFSET {offset}", values
        )
        rows = await cursor.fetchall()
        await cursor.close()
        _log("fetch_many", sql, values, time.monotonic() - t0)
        return [dict(row) for row in rows]

    async def exists(self, qry: Query) -> bool:
        return await self.fetch_one(qry) is not None

    async def last_id(self) -> int:
        self._ensure_connected()
        cursor = await self._connection.execute("SELECT last_insert_rowid()")
        row = await cursor.fetchone()
        await cursor.close()
        return row[0]

    async def migrate(self, name: str, qry: Query):
        self._ensure_connected()
        await self._ensure_migrations_table()

        existing = await self.fetch_one(
            Query(f"SELECT id FROM {_MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
        )
        if existing is not None:
            return

        await self.execute(qry)
        await self.execute(
            self.insert(_MIGRATIONS_TABLE, {"name": name, "sql_text": qry.query[0]})
        )
        await self.commit()

    async def migrate_status(self) -> list[dict]:
        self._ensure_connected()
        await self._ensure_migrations_table()
        return await self.fetch_all(
            Query(f"SELECT * FROM {_MIGRATIONS_TABLE} ORDER BY id", [])
        )

    async def _ensure_migrations_table(self):
        self._ensure_connected()
        await self._connection.execute(
            f"CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "sql_text TEXT NOT NULL)"
        )
        await self._connection.commit()
