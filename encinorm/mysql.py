import contextlib
import re
import time
import warnings

import aiomysql

from .base import Db, logger
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
_MIGRATIONS_TABLE = "_encinorm_migrations"


def _log(method, sql, values, elapsed):
    logger.debug("mysql %s (%.4fs) trace_id=%r sql=%r params=%r",
                 method, elapsed, current_trace_id(), sql, values)


@contextlib.contextmanager
def _suppress_mysql_warnings():
    """Suprime los warnings/notes de MySQL (ej. 'already exists', 'duplicate entry')
    que produce el servidor ante operaciones idempotentes como IF NOT EXISTS o INSERT IGNORE."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", aiomysql.Warning)
        yield


def _to_mysql(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "%s"

    return _PLACEHOLDER_RE.sub(repl, sql), values


class MysqlDb(Db):
    dialect = "mysql"

    def __init__(self):
        self._connection = None
        self._database = None
        self._last_id = 0

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.closed

    def is_lock_error(self, exc: Exception) -> bool:
        # 1213 deadlock, 1205 lock wait timeout
        code = getattr(exc, "args", None)
        return bool(code) and code[0] in (1205, 1213)

    async def connect(self, **kwargs):
        self._connection = await aiomysql.connect(**kwargs)
        self._database = kwargs.get("db")

    async def close(self):
        if self._connection is not None:
            await self._connection.ensure_closed()
            self._connection = None

    async def is_alive(self) -> bool:
        if self._connection is None:
            return False
        try:
            await self._connection.ping(reconnect=False)
            return True
        except Exception:
            return False

    async def in_transaction(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.get_transaction_status()

    async def commit(self):
        if self._connection is not None:
            await self._connection.commit()

    async def rollback(self, save_point: str = None):
        if self._connection is None:
            return
        if save_point:
            await self._execute_raw(f"ROLLBACK TO SAVEPOINT {save_point}")
        else:
            await self._connection.rollback()

    async def save_point(self, name: str):
        if self._connection is not None:
            await self._execute_raw(f"SAVEPOINT {name}")

    def _ensure_connected(self):
        if self._connection is None or self._connection.closed:
            raise ConnectionError("No hay conexión activa a la base de datos.")

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_mysql(qry.query[0], qry.query[1])

    # --- introspección ---
    def _tables_sql(self) -> str:
        return (
            "SELECT table_name AS name FROM information_schema.tables "
            "WHERE table_schema = DATABASE()"
        )

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(f"SHOW COLUMNS FROM {table}", []))
        return [
            ColumnSpec(
                name=r["Field"],
                raw_type=r["Type"],
                datatype=_normalize(r["Type"])[0],
                nullable=(r["Null"] == "YES"),
                primary_key=(r["Key"] == "PRI"),
                max_length=_normalize(r["Type"])[1],
                unsigned=_normalize(r["Type"])[2],
            )
            for r in rows
        ]

    async def _execute_raw(self, sql: str):
        self._ensure_connected()
        cursor = await self._connection.cursor()
        try:
            with _suppress_mysql_warnings():
                await cursor.execute(sql)
        finally:
            await cursor.close()

    # --- Builders (construyen Query, no ejecutan) ---

    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False):
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ",".join("{%d}" % i for i in range(len(columns)))

        if replace:
            keyword = "REPLACE"
        elif ignore_duplicated:
            keyword = "INSERT IGNORE"
        else:
            keyword = "INSERT"

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
        cursor = await self._connection.cursor(aiomysql.DictCursor)
        try:
            with _suppress_mysql_warnings():
                await cursor.execute(sql, values)
            self._last_id = cursor.lastrowid
            _log("execute", sql, values, time.monotonic() - t0)
            return cursor.rowcount
        finally:
            await cursor.close()

    async def fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(sql, values)
            result = await cursor.fetchall()
            _log("fetch_all", sql, values, time.monotonic() - t0)
            return result
        finally:
            await cursor.close()

    async def fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(sql, values)
            result = await cursor.fetchone()
            _log("fetch_one", sql, values, time.monotonic() - t0)
            return result
        finally:
            await cursor.close()

    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        sql = sql.rstrip().rstrip(";")
        offset = (page - 1) * limit
        t0 = time.monotonic()
        cursor = await self._connection.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(f"{sql} LIMIT {limit} OFFSET {offset}", values)
            result = await cursor.fetchall()
            _log("fetch_many", sql, values, time.monotonic() - t0)
            return result
        finally:
            await cursor.close()

    async def exists(self, qry: Query) -> bool:
        return await self.fetch_one(qry) is not None

    async def last_id(self) -> int:
        return self._last_id

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
        await self._execute_raw(
            f"CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "name VARCHAR(255) NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "sql_text TEXT NOT NULL)"
        )
        await self._connection.commit()
