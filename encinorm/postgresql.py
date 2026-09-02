import re
import time
from contextlib import asynccontextmanager

import asyncpg

from .base import Db, logger
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
_MIGRATIONS_TABLE = "_encinorm_migrations"


def _log(method, sql, values, elapsed):
    logger.debug("postgresql %s (%.4fs) trace_id=%r sql=%r params=%r",
                 method, elapsed, current_trace_id(), sql, values)


def _to_postgres(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "$" + str(len(values))

    return _PLACEHOLDER_RE.sub(repl, sql), values


def _rowcount(status) -> int:
    parts = (status or "").split()
    if not parts:
        return 0
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


class PostgresDb(Db):
    dialect = "postgresql"

    def __init__(self):
        self._connection = None
        self._database = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed()

    def is_lock_error(self, exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                asyncpg.DeadlockDetectedError,
                asyncpg.SerializationError,
                asyncpg.LockNotAvailableError,
            ),
        )

    async def connect(self, **kwargs):
        self._connection = await asyncpg.connect(**kwargs)
        self._database = kwargs.get("database")

    async def close(self):
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def is_alive(self) -> bool:
        if self._connection is None:
            return False
        try:
            await self._connection.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def in_transaction(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.is_in_transaction()

    @asynccontextmanager
    async def transaction(self):
        async with self._connection.transaction():
            yield

    async def commit(self):
        if self._connection is not None:
            await self._connection.execute("COMMIT")

    async def rollback(self, save_point: str = None):
        if self._connection is None:
            return
        if save_point:
            await self._connection.execute(f"ROLLBACK TO SAVEPOINT {save_point}")
        else:
            await self._connection.execute("ROLLBACK")

    async def save_point(self, name: str):
        if self._connection is not None:
            await self._connection.execute(f"SAVEPOINT {name}")

    def _ensure_connected(self):
        if self._connection is None or self._connection.is_closed():
            raise ConnectionError("No hay conexión activa a la base de datos.")

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_postgres(qry.query[0], qry.query[1])

    # --- introspección ---
    def _tables_sql(self) -> str:
        return (
            "SELECT tablename AS name FROM pg_catalog.pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
        )

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(
            "SELECT column_name, data_type, is_nullable, "
            "CASE WHEN column_default LIKE 'nextval%' THEN TRUE ELSE FALSE END AS is_pk "
            "FROM information_schema.columns WHERE table_name = {0} "
            "ORDER BY ordinal_position",
            [table],
        ))
        return [
            ColumnSpec(
                name=r["column_name"],
                raw_type=r["data_type"],
                datatype=_normalize(r["data_type"])[0],
                nullable=(r["is_nullable"] == "YES"),
                primary_key=bool(r["is_pk"]),
                max_length=_normalize(r["data_type"])[1],
                unsigned=_normalize(r["data_type"])[2],
            )
            for r in rows
        ]

    # --- Builders (construyen Query, no ejecutan) ---

    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False):
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ",".join("{%d}" % i for i in range(len(columns)))

        sql = f"INSERT INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
        if replace:
            # PostgreSQL exige un objetivo de conflicto para DO UPDATE; se
            # asume la primera columna como clave (PK) del registro.
            conflict = columns[0] if columns else "id"
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)
            sql += f" ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        elif ignore_duplicated:
            sql += " ON CONFLICT DO NOTHING"
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
        status = await self._connection.execute(sql, *values)
        _log("execute", sql, values, time.monotonic() - t0)
        return _rowcount(status)

    async def fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        rows = await self._connection.fetch(sql, *values)
        _log("fetch_all", sql, values, time.monotonic() - t0)
        return [dict(row) for row in rows]

    async def fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        row = await self._connection.fetchrow(sql, *values)
        _log("fetch_one", sql, values, time.monotonic() - t0)
        return dict(row) if row is not None else None

    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        sql = sql.rstrip().rstrip(";")
        offset = (page - 1) * limit
        t0 = time.monotonic()
        rows = await self._connection.fetch(
            f"{sql} LIMIT {limit} OFFSET {offset}", *values
        )
        _log("fetch_many", sql, values, time.monotonic() - t0)
        return [dict(row) for row in rows]

    async def exists(self, qry: Query) -> bool:
        return await self.fetch_one(qry) is not None

    async def last_id(self) -> int:
        self._ensure_connected()
        return await self._connection.fetchval("SELECT lastval()")

    async def migrate(self, name: str, qry: Query):
        self._ensure_connected()
        await self._ensure_migrations_table()

        existing = await self.fetch_one(
            Query(f"SELECT id FROM {_MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
        )
        if existing is not None:
            return

        async with self.transaction():
            await self.execute(qry)
            await self.execute(
                self.insert(_MIGRATIONS_TABLE, {"name": name, "sql_text": qry.query[0]})
            )

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
            "id SERIAL PRIMARY KEY, "
            "name TEXT NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "sql_text TEXT NOT NULL)"
        )
