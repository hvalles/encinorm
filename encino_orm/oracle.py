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
    logger.debug("oracle %s (%.4fs) trace_id=%r sql=%r params=%r",
                 method, elapsed, current_trace_id(), sql, values)


def _to_oracle(sql: str, params: dict) -> tuple[str, dict]:
    """Traduce placeholders intermedios `%(name)s` a binds **nombrados** `:name`.

    Oracle no permite mezclar binds posicionales (`:1`) con nombrados (`:name`),
    y el `RETURNING ... INTO :ret_id` (bind de salida) es nombrado; por eso todo
    el motor usa binds nombrados.
    """

    def repl(match):
        return ":" + match.group(1)

    return _PLACEHOLDER_RE.sub(repl, sql), dict(params)


class OracleDb(Db):
    dialect = "oracle"

    def __init__(self):
        self._connection = None
        self._last_id = 0
        self._in_tx = False
        self._oracledb = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    # --- errores ---
    def _ora_code(self, exc) -> int | None:
        try:
            err = exc.args[0]
            return getattr(err, "code", None)
        except (IndexError, TypeError):
            return None

    def is_lock_error(self, exc: Exception) -> bool:
        # ORA-00060 deadlock, ORA-00054 lock timeout, ORA-08177 serialization
        return self._ora_code(exc) in (60, 54, 8177)

    def is_unique_violation(self, exc: Exception) -> bool:
        # ORA-00001 unique constraint violated
        return self._ora_code(exc) == 1

    # --- ciclo de vida ---
    async def connect(self, **kwargs):
        try:
            import oracledb
        except ImportError as e:
            raise ConnectionError(
                "OracleDb requiere el extra 'oracle': pip install encino-orm[oracle]"
            ) from e

        host = kwargs["host"]
        port = kwargs.get("port", 1521)
        service = kwargs.get("service_name") or kwargs.get("db") or "XEPDB1"
        user = kwargs["user"]
        password = kwargs["password"]
        dsn = oracledb.makedsn(host, port, service_name=service)
        self._connection = await oracledb.connect_async(user=user, password=password, dsn=dsn)
        self._connection.autocommit = False
        self._in_tx = False
        self._oracledb = oracledb

    async def close(self):
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def is_alive(self) -> bool:
        if self._connection is None:
            return False
        try:
            cursor = self._connection.cursor()
            try:
                await cursor.execute("SELECT 1 FROM dual")
                await cursor.fetchone()
            finally:
                cursor.close()
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
            await self._execute_raw(f"ROLLBACK TO {save_point}")
        else:
            await self._connection.rollback()
            self._in_tx = False

    async def save_point(self, name: str):
        if self._connection is not None:
            name = self._check_identifier(name, "savepoint")
            await self._execute_raw(f"SAVEPOINT {name}")

    def _ensure_connected(self):
        if self._connection is None:
            raise ConnectionError("No hay conexión activa a la base de datos.")

    async def _execute_raw(self, sql: str):
        self._ensure_connected()
        cursor = self._connection.cursor()
        try:
            await cursor.execute(sql)
        finally:
            cursor.close()

    def _prepare(self, qry: Query) -> tuple[str, dict]:
        return _to_oracle(qry.query[0], qry.query[1])

    # --- introspección ---
    def _tables_sql(self) -> str:
        return "SELECT table_name AS name FROM user_tables"

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(
            "SELECT column_name AS name, data_type, data_length, data_precision, "
            "data_scale, nullable, identity_column "
            "FROM user_tab_columns WHERE table_name = UPPER({0})",
            [table],
        ))
        result = []
        for r in rows:
            dt = (r["data_type"] or "").lower()
            if dt == "number":
                datatype = "int" if (r["data_scale"] is None or r["data_scale"] == 0) else "numeric"
                max_length = None
                unsigned = False
            else:
                raw_type = dt
                if r["data_length"] is not None and dt in (
                    "varchar2", "nvarchar2", "char", "nchar", "raw",
                ):
                    raw_type = f"{dt}({r['data_length']})"
                datatype, max_length, unsigned = _normalize(raw_type)
            result.append(ColumnSpec(
                name=(r["name"] or "").lower(),
                raw_type=dt,
                datatype=datatype,
                nullable=(r["nullable"] == "Y"),
                primary_key=(r["identity_column"] == "YES"),
                max_length=max_length,
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
            # Oracle MERGE no admite `AS` para alias de tabla
            sql = (
                f"MERGE INTO {tabla} dst "
                f"USING (SELECT {src}) src "
                f"ON ({on}) "
                f"WHEN MATCHED THEN UPDATE SET {updates} "
                f"WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})"
            )
        else:
            placeholders = ",".join("{%d}" % i for i in range(len(columns)))
            sql = f"INSERT INTO {tabla} ({','.join(columns)}) VALUES ({placeholders})"
            if "id" not in columns:
                sql += " RETURNING id INTO :ret_id"

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
        returning = ":ret_id" in sql
        cursor = self._connection.cursor()
        out = cursor.var(self._oracledb.NUMBER) if returning else None
        params = dict(values)
        if returning:
            params["ret_id"] = out
        try:
            try:
                await cursor.execute(sql, params)
            except Exception as exc:
                if getattr(qry, "ignore_duplicated", False) and self.is_unique_violation(exc):
                    return 0
                raise
            self._in_tx = True
            rowcount = cursor.rowcount
            if returning:
                v = out.getvalue()
                self._last_id = v[0] if isinstance(v, (list, tuple)) and v else 0
            _log("execute", sql, values, time.monotonic() - t0)
            return rowcount
        finally:
            cursor.close()

    async def fetch_all(self, qry: Query) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            rows = await cursor.fetchall()
            description = cursor.description
        finally:
            cursor.close()
        _log("fetch_all", sql, values, time.monotonic() - t0)
        return _rows_to_dicts(description, rows)

    async def fetch_one(self, qry: Query):
        self._ensure_connected()
        sql, values = self._prepare(qry)
        t0 = time.monotonic()
        cursor = self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            row = await cursor.fetchone()
            description = cursor.description
        finally:
            cursor.close()
        _log("fetch_one", sql, values, time.monotonic() - t0)
        return _rows_to_dicts(description, [row])[0] if row is not None else None

    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
        self._ensure_connected()
        sql, values = self._prepare(qry)
        sql = sql.rstrip().rstrip(";")
        offset = (page - 1) * limit
        sql += f" OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
        t0 = time.monotonic()
        cursor = self._connection.cursor()
        try:
            await cursor.execute(sql, values)
            rows = await cursor.fetchall()
            description = cursor.description
        finally:
            cursor.close()
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
        ddl = (
            f"CREATE TABLE {_MIGRATIONS_TABLE} ("
            "id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, "
            "name VARCHAR2(255) NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "sql_text CLOB NOT NULL)"
        )
        block = (
            "BEGIN\n"
            f"  EXECUTE IMMEDIATE '{ddl}';\n"
            "EXCEPTION WHEN OTHERS THEN\n"
            "  IF SQLCODE != -955 THEN RAISE; END IF;\n"
            "END;"
        )
        await self._execute_raw(block)
        await self._connection.commit()
        self._in_tx = False
