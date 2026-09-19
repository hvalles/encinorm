import re
import time

from ._rows import _rows_to_dicts
from .base import Db, logger
from .dialects.builders import build_delete, build_insert, build_update
from .dialects.identifiers import check_identifier
from .dialects.strategies import LIMITS, MSSQL_INSERT, TRANSACTIONAL_DDL, InsertStrategy
from .exceptions import (
    ConnectionError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
)
from .introspection.types import ColumnSpec, _normalize
from .migration import MIGRATIONS_TABLE, _apply, reconcile_migrations
from .observability import current_trace_id
from .query import Query

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")

# Código nativo de SQL Server al final del mensaje de `pyodbc.Error` real:
# "... (1205)". Se usa el ÚLTIMO paréntesis numérico como código.
_NATIVE_CODE_RE = re.compile(r"\((\d+)\)")


def _log(method, sql, values, elapsed):
    logger.debug(
        "mssql %s (%.4fs) trace_id=%r sql=%r params=%r",
        method,
        elapsed,
        current_trace_id(),
        sql,
        values,
    )


def _to_mssql(sql: str, params: dict) -> tuple[str, list]:
    values = []

    def repl(match):
        values.append(params[match.group(1)])
        return "?"

    return _PLACEHOLDER_RE.sub(repl, sql), values


class MssqlDb(Db):
    dialect = "mssql"
    MAX_PARAMS = LIMITS["mssql"].max_params
    MAX_ROWS = LIMITS["mssql"].max_rows
    transactional_ddl = TRANSACTIONAL_DDL["mssql"]

    def __init__(self):
        self._connection = None
        self._last_id = 0
        self._in_tx = False
        self._connect_kwargs = None
        self._connected_at = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None

    # --- errores ---
    def _sqlstate(self, exc) -> str | None:
        """SQLSTATE de `pyodbc.Error.args[0]` (str), o `None`."""
        args: tuple = getattr(exc, "args", None) or ()
        if not args:
            return None
        state = args[0]
        return state if isinstance(state, str) else None

    def _message(self, exc) -> str:
        """Mensaje del driver.

        `pyodbc.Error` REAL tiene `args == (sqlstate, str)`. Algunos dobles usan
        la forma `(sqlstate, (code, msg))`; se soportan ambas.
        """
        args: tuple = getattr(exc, "args", None) or ()
        if len(args) > 1:
            second = args[1]
            if isinstance(second, (tuple, list)):
                second = second[1] if len(second) > 1 else second[0]
            return str(second)
        return str(exc)

    def _native_code(self, exc) -> int | None:
        """Código nativo de SQL Server.

        El driver real NO expone el código como campo: viaja al final del
        mensaje (`... (1205)`), así que se extrae de ahí; la forma sintética
        `(sqlstate, (code, msg))` se sigue soportando. `None` si no se puede.
        """
        args: tuple = getattr(exc, "args", None) or ()
        if len(args) > 1 and isinstance(args[1], (tuple, list)):
            try:
                return int(args[1][0])
            except (IndexError, TypeError, ValueError):
                return None
        codes = _NATIVE_CODE_RE.findall(self._message(exc))
        return int(codes[-1]) if codes else None

    def is_lock_error(self, exc: Exception) -> bool:
        # 1205 deadlock victim, 1222 lock request timeout: por código nativo o
        # por SQLSTATE de serialización (`40001`). `HYT00` (timeout genérico) SOLO
        # es lock si el mensaje lo confirma (N-01): tratarlo como lock siempre
        # dejaría escapar crudo un timeout que no es de bloqueo.
        code = self._native_code(exc)
        if code in (1205, 1222):
            return True
        if code is not None:
            return False
        sqlstate = self._sqlstate(exc)
        if sqlstate == "40001":
            return True
        if sqlstate == "HYT00":
            message = self._message(exc).lower()
            return "lock" in message or "1222" in message
        return False

    def is_unique_violation(self, exc: Exception) -> bool:
        code = self._native_code(exc)
        return self._sqlstate(exc) == "23000" and code in (2601, 2627)

    def is_disconnect_error(self, exc: Exception) -> bool:
        """Clasifica la pérdida de conexión por SQLSTATE de ODBC.

        - `08xxx` (clase de error de conexión) → disconnect.
        - `HY000` NO-lock → disconnect solo si el mensaje trae una firma
          verificada. Pitfall 7: un KILL en mitad de query llega como `HY000`
          genérico, NO como `08xxx`.
        - Un lock/deadlock (`1205`/`1222`/`40001`/`HYT00`) queda FUERA: es de
          `is_lock_error` (RESL-01, exclusión mutua).

        NO importa `pyodbc`: clasifica por la forma de `args` del driver
        (drivers opcionales fuera del job `test` de CI).
        """
        if self.is_lock_error(exc):
            return False
        sqlstate = self._sqlstate(exc)
        if sqlstate is None:
            return False
        if sqlstate.startswith("08"):
            return True
        if sqlstate == "HY000":
            message = self._message(exc)
            return any(
                marker in message
                for marker in (
                    "Communication link failure",
                    "terminated by the server",
                    "session is in the kill state",
                )
            )
        return False

    def _translate_error(self, exc: Exception) -> Exception:
        """Traduce ODBC/`pyodbc` a la taxonomía (RESL-04).

        Toda la clase `23000` es integridad (UNIQUE 2601/2627, FK 547, NOT NULL
        515, CHECK): distinguirlas por código dejaba FK/NOT NULL como
        `ProgrammingError` (WR-02). Las desconexiones ya las intercepta
        `is_disconnect_error` antes de llegar aquí.
        """
        sqlstate = self._sqlstate(exc)
        if sqlstate == "23000" or self.is_unique_violation(exc):
            return IntegrityError(str(exc))
        if sqlstate in ("42000", "42S02", "42S22"):
            return ProgrammingError(str(exc))
        return OperationalError(str(exc))

    # --- ciclo de vida ---
    async def connect(self, **kwargs):
        # Las opciones de resiliencia (RESL-03) se consumen aquí y NO se reenvían
        # a la construcción de `conn_str`; los kwargs quedan limpios.
        kwargs = self._resilience_opts(dict(kwargs))
        # Kwargs ORIGINALES (no el `conn_str`) para `_reconnect`; contienen
        # `password`: no loguear.
        self._connect_kwargs = dict(kwargs)
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
        self._connected_at = time.monotonic()

    async def close(self):
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
        self._connected_at = None

    async def is_alive(self) -> bool:
        """Sonda de vida: `SELECT 1` SIN commit (WR-07).

        Un `commit()` aquí mutaría el estado transaccional del llamador; con
        `pre_ping` la sonda corre en el camino caliente y puede caer dentro de
        una transacción. El reset del sobrante es responsabilidad de
        `release()`/`_run`, no de una sonda de vida.
        """
        if self._connection is None:
            return False
        try:
            cursor = await self._connection.cursor()
            try:
                await cursor.execute("SELECT 1")
                await cursor.fetchone()
            finally:
                await cursor.close()
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
        return _to_mssql(qry.sql, qry.params)

    # --- introspección ---
    def _tables_sql(self) -> str:
        return (
            "SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_TYPE = 'BASE TABLE'"
        )

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(
            Query(
                "SELECT COLUMN_NAME AS name, DATA_TYPE AS data_type, "
                "CHARACTER_MAXIMUM_LENGTH AS max_len, IS_NULLABLE AS is_nullable, "
                "COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, "
                "'IsIdentity') AS is_identity "
                "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = {0}",
                [table],
            )
        )
        result = []
        for r in rows:
            dt = (r["data_type"] or "").lower()
            max_len = r["max_len"]
            raw_type = dt
            if max_len is not None and max_len > 0:
                raw_type = f"{dt}({max_len})"
            datatype, ml, unsigned = _normalize(raw_type)
            result.append(
                ColumnSpec(
                    name=(r["name"] or "").lower(),
                    raw_type=raw_type,
                    datatype=datatype,
                    nullable=(r["is_nullable"] == "YES"),
                    primary_key=bool(r["is_identity"]),
                    max_length=ml,
                    unsigned=unsigned,
                )
            )
        return result

    # --- Builders (delegan en el seam; construyen Query, no ejecutan) ---

    def _insert_strategy(
        self, *, replace: bool, ignore_duplicated: bool, conflict: list[str] | None
    ) -> InsertStrategy:
        return MSSQL_INSERT

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
        # SQL Server exige que `MERGE` termine en `;`. Se añade SOLO al SQL que va
        # al driver (no a `_prepare`), de modo que los golden strings y los
        # snapshots conservan el SQL byte-idéntico. Sin esto, `Model.insert(
        # replace=True)` y `Model.upsert()` fallan en MSSQL con el error 10713
        # ("A MERGE statement must be terminated by a semi-colon").
        if sql.lstrip().upper().startswith("MERGE"):
            sql = sql.rstrip().rstrip(";") + ";"
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

    async def _execute_insert(self, qry: Query) -> int | None:
        """Ejecuta el INSERT y lee `OUTPUT INSERTED.<col>` si el `Query` lo pide.

        `@@IDENTITY`/`SCOPE_IDENTITY()` en un `execute` separado son
        session-scoped (el segundo devuelve NULL, verificado); el id se captura
        en la MISMA sentencia con `OUTPUT INSERTED`, donde `cursor.rowcount` vale
        -1 y NO debe usarse como retorno. El `;` que exige un `MERGE` se añade
        solo al SQL del driver, igual que en `execute`.
        """
        self._ensure_connected()
        sql, values = self._prepare(qry)
        if sql.lstrip().upper().startswith("MERGE"):
            sql = sql.rstrip().rstrip(";") + ";"
        t0 = time.monotonic()
        cursor = await self._connection.cursor()
        try:
            try:
                await cursor.execute(sql, values)
            except Exception as exc:
                if getattr(qry, "ignore_duplicated", False) and self.is_unique_violation(exc):
                    return None
                raise
            self._in_tx = True
            new_id = None
            if qry.returns_id:
                row = await cursor.fetchone()
                new_id = row[0] if row and row[0] is not None else None
                self._last_id = new_id or 0
            _log("execute_insert", sql, values, time.monotonic() - t0)
            return new_id
        finally:
            await cursor.close()

    async def _fetch_all(self, qry: Query) -> list[dict]:
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

    async def _fetch_one(self, qry: Query):
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

    async def _fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
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

    async def _last_id_value(self) -> int:
        return self._last_id

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
        await self._execute_raw(
            f"IF NOT EXISTS (SELECT * FROM sysobjects "
            f"WHERE name = '{MIGRATIONS_TABLE}' AND xtype = 'U') "
            f"CREATE TABLE {MIGRATIONS_TABLE} ("
            "id INT IDENTITY(1,1) PRIMARY KEY, "
            "name NVARCHAR(255) NOT NULL UNIQUE, "
            "applied_at DATETIME2 DEFAULT SYSUTCDATETIME(), "
            "status NVARCHAR(20) NOT NULL DEFAULT 'applied', "
            "sql_text NVARCHAR(MAX) NOT NULL)"
        )
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
                f"ALTER TABLE {MIGRATIONS_TABLE} ADD status NVARCHAR(20) NOT NULL DEFAULT 'applied'"
            )
            await self._connection.commit()
            self._in_tx = False
        except Exception:
            if await self.in_transaction():
                await self.rollback()
            cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
            if "status" not in cols:
                raise
