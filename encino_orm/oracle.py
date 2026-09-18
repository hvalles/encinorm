import re
import time

from ._rows import _rows_to_dicts
from .base import Db, logger
from .dialects.builders import build_delete, build_insert, build_update
from .dialects.identifiers import check_identifier
from .dialects.strategies import LIMITS, ORACLE_INSERT, InsertStrategy
from .exceptions import ConnectionError
from .introspection.types import ColumnSpec, _normalize
from .migration import MIGRATIONS_TABLE
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")
# Oracle exige `FROM dual` en el subquery del `USING` de un `MERGE`; el render
# compartido (`builders._merge_sql`) lo omite para conservar el SQL del adaptador
# byte-idéntico (golden strings y snapshots). Se reescribe SOLO el SQL que va al
# driver, no la salida de `_prepare`. Sin esto, `Model.insert(replace=True)` y
# `Model.upsert()` fallan en Oracle con ORA-00923.
_MERGE_USING_RE = re.compile(r"USING \(SELECT (.+?)\) src")


def _log(method, sql, values, elapsed):
    logger.debug(
        "oracle %s (%.4fs) trace_id=%r sql=%r params=%r",
        method,
        elapsed,
        current_trace_id(),
        sql,
        values,
    )


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
    MAX_PARAMS = LIMITS["oracle"].max_params
    MAX_ROWS = LIMITS["oracle"].max_rows

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

    async def rollback(self, save_point: str | None = None):
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
        return _to_oracle(qry.sql, qry.params)

    # --- introspección ---
    def _tables_sql(self) -> str:
        return "SELECT table_name AS name FROM user_tables"

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(
            Query(
                "SELECT column_name AS name, data_type, data_length, data_precision, "
                "data_scale, nullable, identity_column "
                "FROM user_tab_columns WHERE table_name = UPPER({0})",
                [table],
            )
        )
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
                    "varchar2",
                    "nvarchar2",
                    "char",
                    "nchar",
                    "raw",
                ):
                    raw_type = f"{dt}({r['data_length']})"
                datatype, max_length, unsigned = _normalize(raw_type)
            result.append(
                ColumnSpec(
                    name=(r["name"] or "").lower(),
                    raw_type=dt,
                    datatype=datatype,
                    nullable=(r["nullable"] == "Y"),
                    primary_key=(r["identity_column"] == "YES"),
                    max_length=max_length,
                    unsigned=unsigned,
                )
            )
        return result

    # --- Builders (delegan en el seam; construyen Query, no ejecutan) ---

    def _insert_strategy(
        self, *, replace: bool, ignore_duplicated: bool, conflict: list[str] | None
    ) -> InsertStrategy:
        return ORACLE_INSERT

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
        # `FROM dual` solo al SQL que va al driver (ver `_MERGE_USING_RE`).
        if sql.lstrip().upper().startswith("MERGE"):
            sql = _MERGE_USING_RE.sub(r"USING (SELECT \1 FROM dual) src", sql, count=1)
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
            Query(f"SELECT id FROM {MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
        )
        if existing is not None:
            return

        await self.execute(qry)
        await self.execute(self.insert(MIGRATIONS_TABLE, {"name": name, "sql_text": qry.sql}))
        await self.commit()

    async def migrate_status(self) -> list[dict]:
        self._ensure_connected()
        await self._ensure_migrations_table()
        return await self.fetch_all(Query(f"SELECT * FROM {MIGRATIONS_TABLE} ORDER BY id", []))

    async def _ensure_migrations_table(self):
        self._ensure_connected()
        ddl = (
            f"CREATE TABLE {MIGRATIONS_TABLE} ("
            "id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY PRIMARY KEY, "
            "name VARCHAR2(255) NOT NULL UNIQUE, "
            "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
            "status VARCHAR2(20) DEFAULT 'applied' NOT NULL, "
            "sql_text CLOB NOT NULL)"
        )
        # El DDL viaja dentro de un literal PL/SQL: las comillas simples de
        # `'applied'` se duplican para que Oracle las lea como una comilla
        # literal dentro de la cadena de `EXECUTE IMMEDIATE`.
        block = (
            "BEGIN\n"
            f"  EXECUTE IMMEDIATE '{ddl.replace(chr(39), chr(39) * 2)}';\n"
            "EXCEPTION WHEN OTHERS THEN\n"
            "  IF SQLCODE != -955 THEN RAISE; END IF;\n"
            "END;"
        )
        await self._execute_raw(block)
        await self._connection.commit()
        self._in_tx = False
        await self._ensure_status_column()

    async def _ensure_status_column(self):
        """Añade `status` al ledger si falta (instalaciones legacy, D-04).

        El guard es "verify-then-swallow": si el `ALTER` falla por una carrera
        multi-proceso, se re-lee el catálogo y solo se re-lanza si `status`
        sigue ausente (Pitfall 6).
        """
        check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
        cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
        if "status" in cols:
            return
        try:
            await self._execute_raw(
                f"ALTER TABLE {MIGRATIONS_TABLE} ADD status VARCHAR2(20) DEFAULT 'applied' NOT NULL"
            )
            await self._connection.commit()
            self._in_tx = False
        except Exception:
            if await self.in_transaction():
                await self.rollback()
            cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
            if "status" not in cols:
                raise
