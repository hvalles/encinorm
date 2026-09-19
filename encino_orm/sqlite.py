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
        self._connect_kwargs = None
        self._connected_at = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    def is_lock_error(self, exc: Exception) -> bool:
        return "locked" in str(exc) or "busy" in str(exc)

    def is_disconnect_error(self, exc: Exception) -> bool:
        """SQLite es embebido y no tiene socket: su "desconexión" es operar
        sobre una conexión ya cerrada o perder el fichero de E/S.

        `locked`/`busy` pertenecen a `is_lock_error` y quedan FUERA.
        """
        if isinstance(exc, aiosqlite.ProgrammingError):
            return "closed database" in str(exc)
        if isinstance(exc, aiosqlite.OperationalError):
            text = str(exc)
            return "disk I/O error" in text or "unable to open database file" in text
        return False

    async def connect(self, **kwargs):
        # Las opciones de resiliencia (RESL-03) se consumen aquí y NO se reenvían
        # al driver; `_connect_kwargs` queda con los kwargs ya limpios.
        kwargs = self._resilience_opts(dict(kwargs))
        database = kwargs.get("database", ":memory:")
        self._database = database
        # Se guarda el default ya resuelto para que `_reconnect` use la MISMA BD.
        self._connect_kwargs = {"database": database}
        self._connection = await aiosqlite.connect(database)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.commit()
        self._connected_at = time.monotonic()

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None
        # Una conexión cerrada a propósito no se resucita: `_is_reconnectable`
        # exige `_connected_at is not None`.
        self._connected_at = None

    async def _reconnect(self):
        """Rechaza reconectar `:memory:` (crearía una base vacía, Pitfall 2).

        En SQLite en memoria, `close()` + `connect(":memory:")` devuelve una base
        nueva y vacía: todas las tablas desaparecerían sin error. Se lanza la
        `ConnectionError` de la librería (RESL-04 la refinará a
        `ConnectionLostError`, subclase, sin romper este contrato).
        """
        if self._database == ":memory:":
            raise ConnectionError(
                "no se puede reconectar una base SQLite en memoria: se perderían los datos"
            )
        await super()._reconnect()

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
        returning: str | None = None,
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
            returning=returning,
        )

    def delete(self, tabla: str, keys: dict, *, schema: str | None = None):
        return build_delete(tabla, keys, schema=schema)

    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None):
        return build_update(tabla, keys, values, schema=schema)

    # --- Ejecución / Consulta ---

    async def _execute(self, qry: Query) -> int:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        await cursor.close()
        _log("execute", sql, values, time.monotonic() - t0)
        return cursor.rowcount

    async def _execute_insert(self, qry: Query) -> int | None:
        """Ejecuta el INSERT y devuelve `cursor.lastrowid` si el `Query` lo pide.

        `lastrowid` se lee INMEDIATAMENTE tras el `execute` y antes de cerrar el
        cursor (el id pertenece a ESTA sentencia, no a la sesión). Con
        `qry.returns_id` falso devuelve `None`: el SQL es byte-idéntico y no hay
        captura que ofrecer.
        """
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        if not qry.returns_id:
            new_id = None
        elif cursor.rowcount == 0:
            # `INSERT OR IGNORE` no insertó (fila duplicada): `lastrowid` sigue
            # apuntando a la inserción ANTERIOR de esta conexión, así que
            # devolverlo asignaría a la instancia el id de OTRA fila (CR-02).
            new_id = None
        else:
            new_id = cursor.lastrowid
        await cursor.close()
        _log("execute_insert", sql, values, time.monotonic() - t0)
        return new_id

    async def _fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        rows = await cursor.fetchall()
        await cursor.close()
        _log("fetch_all", sql, values, time.monotonic() - t0)
        return [dict(row) for row in rows]

    async def _fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.execute(sql, values)
        row = await cursor.fetchone()
        await cursor.close()
        _log("fetch_one", sql, values, time.monotonic() - t0)
        return dict(row) if row is not None else None

    async def _fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
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

    async def _last_id_value(self) -> int:
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
