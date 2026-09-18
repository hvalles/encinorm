import re
import time

import aiosqlite

from .base import Db, logger
from .dialects.builders import build_delete, build_insert, build_update
from .dialects.identifiers import check_identifier
from .dialects.strategies import LIMITS, SQLITE_INSERT, TRANSACTIONAL_DDL, InsertStrategy
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .migration import MIGRATIONS_TABLE, _apply, reconcile_migrations
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")


def _log(method, sql, values, elapsed):
    logger.debug(
        "sqlite %s (%.4fs) trace_id=%r sql=%r params=%r",
        method,
        elapsed,
        current_trace_id(),
        sql,
        values,
    )


def _to_positional(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "?"

    return _PLACEHOLDER_RE.sub(repl, sql), values


class SqliteDb(Db):
    dialect = "sqlite"
    MAX_PARAMS = LIMITS["sqlite"].max_params
    MAX_ROWS = LIMITS["sqlite"].max_rows
    transactional_ddl = TRANSACTIONAL_DDL["sqlite"]

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

    async def rollback(self, save_point: str | None = None):
        if not self._connection:
            return
        if save_point:
            save_point = self._check_identifier(save_point, "savepoint")
            await self._connection.execute(f"ROLLBACK TO SAVEPOINT {save_point}")
        else:
            await self._connection.rollback()

    async def save_point(self, name: str):
        if self._connection:
            name = self._check_identifier(name, "savepoint")
            await self._connection.execute(f"SAVEPOINT {name}")

    def _ensure_connected(self):
        if not self._connection:
            raise ConnectionError("No hay conexión activa a la base de datos.")

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_positional(qry.sql, qry.params)

    # --- introspección ---
    def _tables_sql(self) -> str:
        return (
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            f"AND name <> '{MIGRATIONS_TABLE}'"
        )

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        check_identifier(table, "nombre de tabla")
        rows = await self.fetch_all(Query(f"PRAGMA table_info({table})", []))
        return [
            ColumnSpec(
                name=r["name"],
                raw_type=r["type"] or "",
                datatype=_normalize(r["type"])[0],
                nullable=not bool(r["notnull"]),
                primary_key=bool(r["pk"]),
                max_length=_normalize(r["type"])[1],
                unsigned=_normalize(r["type"])[2],
            )
            for r in rows
        ]

    # --- Builders (delegan en el seam; construyen Query, no ejecutan) ---

    def _insert_strategy(
        self, *, replace: bool, ignore_duplicated: bool, conflict: list[str] | None
    ) -> InsertStrategy:
        return SQLITE_INSERT

    def insert(
        self,
        tabla: str,
        data: dict,
        ignore_duplicated=False,
        replace=False,
        conflict: list[str] | None = None,
        *,
        schema: str | None = None,
    ):
        return build_insert(
            tabla,
            data,
            strategy=self._insert_strategy(
                replace=replace, ignore_duplicated=ignore_duplicated, conflict=conflict
            ),
            conflict=conflict,
            replace=replace,
            ignore_duplicated=ignore_duplicated,
            schema=schema,
        )

    def delete(self, tabla: str, keys: dict, *, schema: str | None = None):
        return build_delete(tabla, keys, schema=schema)

    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None):
        return build_update(tabla, keys, values, schema=schema)

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
        cursor = await self._connection.execute(f"{sql} LIMIT {limit} OFFSET {offset}", values)
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
        await reconcile_migrations(self)

        existing = await self.fetch_one(
            Query(f"SELECT id FROM {MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
        )
        if existing is not None:
            return

        await _apply(self, name, qry)

    async def migrate_status(self) -> list[dict]:
        self._ensure_connected()
        await self._ensure_migrations_table()
        return await self.fetch_all(Query(f"SELECT * FROM {MIGRATIONS_TABLE} ORDER BY id", []))

    async def _ensure_migrations_table(self):
        self._ensure_connected()
        await self._connection.execute(
            f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "status TEXT NOT NULL DEFAULT 'applied', "
            "sql_text TEXT NOT NULL)"
        )
        await self._connection.commit()
        await self._ensure_status_column()

    async def _ensure_status_column(self):
        """Añade `status` al ledger si falta (instalaciones legacy, D-04).

        `CREATE TABLE IF NOT EXISTS` no añade columnas a una tabla ya existente;
        el guard es "verify-then-swallow": si el `ALTER` falla por una carrera
        multi-proceso, se re-lee el catálogo y solo se re-lanza si `status`
        sigue ausente (Pitfall 6).
        """
        check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
        cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
        if "status" in cols:
            return
        try:
            await self._connection.execute(
                f"ALTER TABLE {MIGRATIONS_TABLE} ADD status TEXT NOT NULL DEFAULT 'applied'"
            )
            await self._connection.commit()
        except Exception:
            if await self.in_transaction():
                await self.rollback()
            cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
            if "status" not in cols:
                raise
