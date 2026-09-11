import re
import time

from ._rows import _rows_to_dicts
from .base import Db, logger
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
_MIGRATIONS_TABLE = "_encino_orm_migrations"


def _log(method, sql, values, elapsed):
    logger.debug("mssql %s (%.4fs) trace_id=%r sql=%r params=%r",
                 method, elapsed, current_trace_id(), sql, values)


def _to_mssql(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "?"

    return _PLACEHOLDER_RE.sub(repl, sql), values


class MssqlDb(Db):
    dialect = "mssql"

    def __init__(self):
        self._connection = None
        self._last_id = 0
        self._in_tx = False

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    # --- errores ---
    def _native_code(self, exc) -> int | None:
        try:
            return int(exc.args[1][0])
        except (IndexError, TypeError, ValueError):
            return None

    def is_lock_error(self, exc: Exception) -> bool:
        # 1205 deadlock victim, 1222 lock request timeout
        return self._native_code(exc) in (1205, 1222)

    def is_unique_violation(self, exc: Exception) -> bool:
        try:
            sqlstate = exc.args[0]
        except (IndexError, TypeError):
            return False
        code = self._native_code(exc)
        return sqlstate == "23000" and code in (2601, 2627)

    # --- ciclo de vida ---
    async def connect(self, **kwargs):
        try:
            import aioodbc
        except ImportError as e:
            raise ConnectionError(
                "MssqlDb requiere el extra 'mssql': pip install encino-orm[mssql]"
            ) from e

        driver = kwargs.get("driver", "ODBC Driver 18 for SQL Server")
        host = kwargs["host"]
        port = kwargs.get("port", 1433)
        user = kwargs["user"]
        password = kwargs["password"]
        database = kwargs.get("db") or kwargs.get("database") or "master"
        encrypt = kwargs.get("encrypt", True)
        trust_cert = kwargs.get("trust_server_certificate", False)
        conn_str = (
            f"DRIVER={{{driver}}};SERVER={host},{port};"
            f"UID={user};PWD={password};DATABASE={database};"
            f"Encrypt={'yes' if encrypt else 'no'};"
            f"TrustServerCertificate={'yes' if trust_cert else 'no'};"
        )
        self._connection = await aioodbc.connect(dsn=conn_str)
        self._connection.autocommit = False
        self._in_tx = False

    async def close(self):
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def is_alive(self) -> bool:
        if self._connection is None:
            return False
        try:
            cursor = await self._connection.cursor()
            try:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
            finally:
                await cursor.close()
            await self._connection.commit()
            return True
        except Exception:
            return False

    async def in_transaction(self) -> bool:
        return self._connection is not None and self._in_tx

    async def commit(self):
        if self._connection is not None:
            await self._connection.commit()
            self._in_tx = False

    async def rollback(self, save_point: str = None):
        if self._connection is None:
            return
        if save_point:
            save_point = self._check_identifier(save_point, "savepoint")
            await self._execute_raw(f"ROLLBACK TRANSACTION {save_point}")
        else:
            await self._connection.rollback()
            self._in_tx = False

    async def save_point(self, name: str):
        if self._connection is not None:
            name = self._check_identifier(name, "savepoint")
            await self._execute_raw(f"SAVE TRANSACTION {name}")

    def _ensure_connected(self):
        if self._connection is None:
            raise ConnectionError("No hay conexión activa a la base de datos.")

    async def _execute_raw(self, sql: str):
        self._ensure_connected()
        cursor = await self._connection.cursor()
        try:
            await cursor.execute(sql)
        finally:
            await cursor.close()

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_mssql(qry.query[0], qry.query[1])

    # --- introspección ---
    def _tables_sql(self) -> str:
        return (
            "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE'"
        )

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(
            "SELECT COLUMN_NAME AS name, DATA_TYPE AS data_type, "
            "CHARACTER_MAXIMUM_LENGTH AS max_len, IS_NULLABLE AS is_nullable, "
            "COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, "
            "'IsIdentity') AS is_identity "
            "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = {0}",
            [table],
        ))
        result = []
        for r in rows:
            dt = (r["data_type"] or "").lower()
            max_len = r["max_len"]
            raw_type = dt
            if max_len is not None and max_len > 0:
                raw_type = f"{dt}({max_len})"
            datatype, ml, unsigned = _normalize(raw_type)
            result.append(ColumnSpec(
                name=(r["name"] or "").lower(),
                raw_type=raw_type,
                datatype=datatype,
                nullable=(r["is_nullable"] == "YES"),
                primary_key=bool(r["is_identity"]),
                max_length=ml,
                unsigned=unsigned,
            ))
        return result

    # --- Builders (construyen Query, no ejecutan) ---
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False,
               conflict: list[str] | None = None):
        columns = list(data.keys())
        values = list(data.values())

        if replace:
            conflict_cols = list(conflict) if conflict else ([columns[0]] if columns else ["id"])
            src = ", ".join(f"{{{i}}} AS {c}" for i, c in enumerate(columns))
            on = " AND ".join(f"dst.{c} = src.{c}" for c in conflict_cols)
            updates = ", ".join(f"dst.{c} = src.{c}" for c in columns)
            ins_cols = ",".join(columns)
            ins_vals = ",".join(f"src.{c}" for c in columns)
            sql = (
                f"MERGE INTO {tabla} AS dst "
                f"USING (SELECT {src}) AS src "
                f"ON ({on}) "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})"
            )
        else:
            placeholders = ",".join("{%d}" % i for i in range(len(columns)))
            sql = f"INSERT INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"

        q = Query(sql, values)
        if ignore_duplicated and not replace:
            q.ignore_duplicated = True
        return q

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
        cursor = await self._connection.cursor()
        try:
            try:
                await cursor.execute(sql, values)
            except Exception as exc:
                if getattr(qry, "ignore_duplicated", False) and self.is_unique_violation(exc):
                    return 0
                raise
            self._in_tx = True
            rowcount = cursor.rowcount
            if sql.lstrip().upper().startswith("INSERT"):
                await cursor.execute("SELECT CAST(@@IDENTITY AS INT)")
                row = await cursor.fetchone()
                self._last_id = row[0] if row and row[0] is not None else 0
            _log("execute", sql, values, time.monotonic() - t0)
            return rowcount
        finally:
            await cursor.close()

    async def fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            rows = await cursor.fetchall()
            description = cursor.description
        finally:
            await cursor.close()
        self._in_tx = True
        _log("fetch_all", sql, values, time.monotonic() - t0)
        return _rows_to_dicts(description, rows)

    async def fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = await self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            row = await cursor.fetchone()
            description = cursor.description
        finally:
            await cursor.close()
        self._in_tx = True
        _log("fetch_one", sql, values, time.monotonic() - t0)
        return _rows_to_dicts(description, [row])[0] if row is not None else None

    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        sql = sql.rstrip().rstrip(";")
        offset = (page - 1) * limit
        if "ORDER BY" not in sql.upper():
            sql += " ORDER BY (SELECT NULL)"
        sql += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
        t0 = time.monotonic()
        cursor = await self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            rows = await cursor.fetchall()
            description = cursor.description
        finally:
            await cursor.close()
        self._in_tx = True
        _log("fetch_many", sql, values, time.monotonic() - t0)
        return _rows_to_dicts(description, rows)

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
            f"IF NOT EXISTS (SELECT * FROM sysobjects "
            f"WHERE name = '{_MIGRATIONS_TABLE}' AND xtype = 'U') "
            f"CREATE TABLE {_MIGRATIONS_TABLE} ("
            "id INT IDENTITY(1,1) PRIMARY KEY, "
            "name NVARCHAR(255) NOT NULL UNIQUE, "
            "applied_at DATETIME2 DEFAULT SYSUTCDATETIME(), "
            "sql_text NVARCHAR(MAX) NOT NULL)"
        )
        await self._connection.commit()
        self._in_tx = False
