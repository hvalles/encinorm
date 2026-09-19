"""Helpers deterministas para los tests de resiliencia (Fase 5, RESL-01…04).

Dos grupos de utilidades:

1. **Builders de excepciones de driver** con las firmas REALES verificadas en
   `05-RESEARCH.md` §Code Examples (tipos de `aiosqlite`/`pymysql`/`asyncpg` y
   la forma exacta de `args` de `pyodbc`/`oracledb`). Los motores con driver
   OPCIONAL (MSSQL, Oracle) se construyen por forma de `args`, nunca importando
   el driver a nivel de módulo: el job `test` de CI no sincroniza los extras
   `mssql`/`oracle`. Las variantes `real_*` sí importan el driver, pero DENTRO
   de la función, para que el llamador degrade a skip si no está instalado.

2. **`FakeResilientDb`**, un doble a mano (sin dobles automáticos de la stdlib,
   convención del repo) que hereda de `Db` a propósito: el MRO debe resolver los métodos
   públicos del template method `_with_reconnect` (05-02) sobre las
   implementaciones privadas `_execute`/`_fetch_*` de este doble. Respeta
   `fail_first` para provocar una desconexión en la primera llamada y tiene
   `disconnect`/`lock` configurables para caracterizar la exclusión mutua.

Restricción dura: piso de Python 3.10. Nada de `asyncio.Barrier`,
`asyncio.timeout`, `TaskGroup` ni `except*`. Tampoco `sleep`: los dobles son
deterministas. El prefijo `_` del módulo evita que pytest lo colecte.
"""

import time

import aiosqlite
import asyncpg
import pymysql.err

from encino_orm.base import Db

__all__ = [
    "FakeReconnectFalla",
    "FakeResilientDb",
    "mssql_disconnect_idle",
    "mssql_disconnect_midquery",
    "mssql_integrity",
    "mssql_lock",
    "mssql_lock_timeout",
    "mssql_syntax",
    "mysql_disconnect",
    "mysql_gone_away",
    "mysql_integrity",
    "mysql_interface",
    "mysql_lock",
    "mysql_lock_timeout",
    "mysql_operational",
    "mysql_programming",
    "oracle_disconnect_dpy",
    "oracle_disconnect_ora",
    "oracle_integrity",
    "oracle_lock",
    "oracle_lock_timeout",
    "oracle_serialization",
    "oracle_syntax",
    "pg_cached_stmt",
    "pg_disconnect",
    "pg_integrity",
    "pg_interface",
    "pg_lock",
    "pg_lock_not_available",
    "pg_operational",
    "pg_programming",
    "pg_serialization",
    "real_mssql_disconnect",
    "real_oracle_disconnect",
    "sqlite_disconnect",
    "sqlite_disk_io",
    "sqlite_integrity",
    "sqlite_lock",
    "sqlite_operational",
    "sqlite_programming",
]

# ---------------------------------------------------------------------------
# Builders de excepciones por motor (firmas reales / forma exacta)
# ---------------------------------------------------------------------------


def sqlite_disconnect() -> Exception:
    """`sqlite3.ProgrammingError` de operar sobre una conexión cerrada.

    SQLite es embebido y no tiene socket: su "desconexión" es operar sobre una
    conexión ya cerrada.
    """
    return aiosqlite.ProgrammingError("Cannot operate on a closed database.")


def sqlite_disk_io() -> Exception:
    """`sqlite3.OperationalError` de E/S de disco (fichero perdido/inalcanzable)."""
    return aiosqlite.OperationalError("disk I/O error")


def sqlite_lock() -> Exception:
    """`sqlite3.OperationalError` de lock: NO debe clasificarse como disconnect."""
    return aiosqlite.OperationalError("database is locked")


def sqlite_integrity() -> Exception:
    """`sqlite3.IntegrityError` (UNIQUE/NOT NULL/CHECK) → `IntegrityError`."""
    return aiosqlite.IntegrityError("UNIQUE constraint failed: t.x")


def sqlite_programming() -> Exception:
    """`sqlite3.ProgrammingError` de programación (NO la de conexión cerrada)."""
    return aiosqlite.ProgrammingError("Incorrect number of bindings supplied")


def sqlite_operational() -> Exception:
    """`sqlite3.OperationalError` genérico (NO lock ni disconnect) → `OperationalError`."""
    return aiosqlite.OperationalError("no such table: t")


def mysql_disconnect() -> Exception:
    """`OperationalError(2013)` de conexión perdida durante una query (KILL real)."""
    return pymysql.err.OperationalError(2013, "Lost connection to MySQL server during query")


def mysql_gone_away() -> Exception:
    """`OperationalError(2006)` del servidor que se fue (idle)."""
    return pymysql.err.OperationalError(2006, "MySQL server has gone away")


def mysql_interface() -> Exception:
    """`InterfaceError` de PyMySQL (interfaz/estado de conexión inválido)."""
    return pymysql.err.InterfaceError(0, "")


def mysql_lock() -> Exception:
    """`OperationalError(1213)` de deadlock: es lock, no disconnect."""
    return pymysql.err.OperationalError(1213, "Deadlock found when trying to get lock")


def mysql_lock_timeout() -> Exception:
    """`OperationalError(1205)` de lock wait timeout: es lock, no disconnect."""
    return pymysql.err.OperationalError(1205, "Lock wait timeout exceeded")


def mysql_integrity() -> Exception:
    """`IntegrityError(1062)` de clave duplicada → `IntegrityError`."""
    return pymysql.err.IntegrityError(1062, "Duplicate entry 'x' for key 'PRIMARY'")


def mysql_programming() -> Exception:
    """`ProgrammingError(1064)` de sintaxis → `ProgrammingError`."""
    return pymysql.err.ProgrammingError(1064, "You have an error in your SQL syntax")


def mysql_operational() -> Exception:
    """`OperationalError(2003)` que NO es desconexión (no está en los errnos)."""
    return pymysql.err.OperationalError(2003, "Can't connect to MySQL server")


def pg_disconnect() -> Exception:
    """`asyncpg.ConnectionDoesNotExistError` de conexión cerrada mid-operation."""
    return asyncpg.exceptions.ConnectionDoesNotExistError(
        "connection was closed in the middle of operation"
    )


def pg_interface() -> Exception:
    """`asyncpg.InterfaceError` (p. ej. operar sobre una conexión cerrada)."""
    return asyncpg.InterfaceError("connection is closed")


def pg_lock() -> Exception:
    """`DeadlockDetectedError`: es lock, no disconnect."""
    return asyncpg.exceptions.DeadlockDetectedError("deadlock detected")


def pg_serialization() -> Exception:
    """`SerializationError`: es lock (re-reintentable), no disconnect."""
    return asyncpg.exceptions.SerializationError("could not serialize access")


def pg_lock_not_available() -> Exception:
    """`LockNotAvailableError`: es lock, no disconnect."""
    return asyncpg.exceptions.LockNotAvailableError("lock not available")


def pg_cached_stmt() -> Exception:
    """`InvalidCachedStatementError`: NI disconnect NI lock (statement cache)."""
    return asyncpg.exceptions.InvalidCachedStatementError("cached statement plan is invalid")


def pg_integrity() -> Exception:
    """`UniqueViolationError` (subclase de `IntegrityConstraintViolationError`)."""
    return asyncpg.exceptions.UniqueViolationError("duplicate key value violates unique constraint")


def pg_programming() -> Exception:
    """`UndefinedTableError` (subclase de `SyntaxOrAccessError`) → `ProgrammingError`."""
    return asyncpg.exceptions.UndefinedTableError('relation "t" does not exist')


def pg_operational() -> Exception:
    """`PostgresError` genérico que no es integridad ni programación."""
    return asyncpg.exceptions.PostgresError("boom")


class _MssqlExc(Exception):
    """Excepción con la MISMA forma de `args` que `pyodbc.Error`.

    `mssql.py:_native_code` consume `exc.args[1][0]` y `is_unique_violation`
    consume `exc.args[0]`, así que el doble reproduce `(sqlstate, (code, msg))`.
    """

    def __init__(self, sqlstate: str, code: int, message: str):
        self.args = (sqlstate, (code, message))


def mssql_disconnect_midquery() -> Exception:
    """SQLSTATE `HY000` genérico en mitad de query (KILL real, Pitfall 7)."""
    return _MssqlExc("HY000", 596, "Connection may have been terminated by the server")


def mssql_disconnect_idle() -> Exception:
    """SQLSTATE `08S01` de caída en reposo (Communication link failure)."""
    return _MssqlExc("08S01", 10054, "Communication link failure")


def mssql_lock() -> Exception:
    """Deadlock victim 1205: es lock, no disconnect."""
    return _MssqlExc("40001", 1205, "deadlock")


def mssql_lock_timeout() -> Exception:
    """Lock request timeout 1222: es lock, no disconnect."""
    return _MssqlExc("HYT00", 1222, "lock request time out")


def mssql_integrity() -> Exception:
    """SQLSTATE 23000 + 2627 (unique) → `IntegrityError`."""
    return _MssqlExc("23000", 2627, "Violation of UNIQUE KEY constraint")


def mssql_syntax() -> Exception:
    """SQLSTATE 42000 + 102 (syntax) → `ProgrammingError`."""
    return _MssqlExc("42000", 102, "Incorrect syntax near 'x'")


class _OraError:
    """Objeto de error con `code`/`full_code` como el de `oracledb`."""

    def __init__(self, code: int, full_code: str | None = None):
        self.code = code
        self.full_code = full_code


class _OraExc(Exception):
    """Excepción con `args[0]` = objeto de error de Oracle."""

    def __init__(self, code: int, full_code: str | None = None):
        self.args = (_OraError(code, full_code),)


def oracle_disconnect_dpy() -> Exception:
    """DPY-4011 con `code == 0`: exige leer `full_code` (Pitfall 8)."""
    return _OraExc(0, "DPY-4011")


def oracle_disconnect_ora() -> Exception:
    """ORA-03113 (end-of-file on communication channel)."""
    return _OraExc(3113, None)


def oracle_lock() -> Exception:
    """ORA-00060 deadlock: es lock, no disconnect."""
    return _OraExc(60, None)


def oracle_lock_timeout() -> Exception:
    """ORA-00054 lock timeout: es lock, no disconnect."""
    return _OraExc(54, None)


def oracle_serialization() -> Exception:
    """ORA-08177 serialization: es lock (re-reintentable), no disconnect."""
    return _OraExc(8177, None)


def oracle_integrity() -> Exception:
    """ORA-00001 unique constraint → `IntegrityError`."""
    return _OraExc(1, None)


def oracle_syntax() -> Exception:
    """ORA-00904 invalid identifier → `ProgrammingError`."""
    return _OraExc(904, None)


# ---------------------------------------------------------------------------
# Builders con el driver REAL (tests `optional_engine`; importan dentro)
# ---------------------------------------------------------------------------


def real_mssql_disconnect() -> Exception:
    """`pyodbc.Error('HY000', '...terminated by the server... (596)')` real.

    Deja propagar `ImportError` si el extra `mssql` no está instalado; el
    llamador lo convierte en skip con `engine_unavailable`.
    """
    import pyodbc

    return pyodbc.Error("HY000", "Connection may have been terminated by the server (596)")


def real_oracle_disconnect() -> Exception:
    """`oracledb.exceptions.DatabaseError` real con `full_code='DPY-4011'`.

    Deja propagar `ImportError` si el extra `oracle` no está instalado.
    `oracledb.exceptions` requiere import explícito (no se expone como atributo
    del paquete tras `import oracledb`).
    """
    from oracledb import exceptions

    exc = exceptions.DatabaseError("the database or network closed the connection")
    exc.args = (_OraError(0, "DPY-4011"),)
    return exc


# ---------------------------------------------------------------------------
# Doble determinista de `Db`
# ---------------------------------------------------------------------------

# `_with_reconnect` llega en 05-02. Mientras `Db.execute`/`fetch_*` sigan siendo
# abstractos (05-01), el doble debe implementar los públicos para poder
# instanciarse; cuando el template method exista, los públicos reenvían a la
# superclase para NO saltarse la clasificación/reconexión. Se evalúa una vez al
# importar el módulo.
_DB_CON_TEMPLATE = hasattr(Db, "_with_reconnect")


class FakeResilientDb(Db):
    """Doble de `Db` que hereda del ABC a propósito (el MRO resuelve el template).

    No usa dobles automáticos: la convención del repo son dobles a mano. Configura:

    - `disconnect`: valor de `is_disconnect_error` (True por defecto).
    - `lock`: valor de `is_lock_error` (False por defecto).
    - `tx`: valor de `in_transaction()` (False por defecto).
    - `fail_first`: cuántas de las primeras operaciones lanzan `_exc_factory`.
    - `exc_factory`: callable sin argumentos que produce la excepción a lanzar
      (por defecto `mysql_disconnect`).
    """

    def __init__(
        self,
        *,
        disconnect: bool = True,
        lock: bool = False,
        tx: bool = False,
        fail_first: int = 1,
        exc_factory=None,
    ):
        self.disconnect = disconnect
        self.lock = lock
        self.tx = tx
        self.fail_first = fail_first
        self._exc_factory = exc_factory if exc_factory is not None else mysql_disconnect

        self.connects = 0
        self.closes = 0
        self.executes = 0
        self.fetches = 0
        self.is_alive_calls = 0
        self._connected = False
        self._connect_kwargs = None
        self._connected_at = None

    # --- ciclo de vida ---

    async def connect(self, **kwargs):
        self.connects += 1
        self._connect_kwargs = dict(kwargs)
        self._connected_at = time.monotonic()
        self._connected = True

    async def close(self):
        self.closes += 1
        self._connected = False
        self._connected_at = None

    async def is_alive(self) -> bool:
        self.is_alive_calls += 1
        return self._connected

    async def in_transaction(self) -> bool:
        return self.tx

    # --- clasificación ---

    def is_disconnect_error(self, exc) -> bool:
        return self.disconnect

    def is_lock_error(self, exc) -> bool:
        return self.lock

    # --- operaciones privadas (el template method las envuelve en 05-02) ---

    def _falla(self, contador: int) -> bool:
        return contador <= self.fail_first

    async def _execute(self, qry):
        self.executes += 1
        if self._falla(self.executes):
            raise self._exc_factory()
        return "ok"

    async def _execute_insert(self, qry) -> int | None:
        self.executes += 1
        if self._falla(self.executes):
            raise self._exc_factory()
        return 7

    async def _fetch_one(self, qry):
        self.fetches += 1
        if self._falla(self.fetches):
            raise self._exc_factory()
        return {"ok": 1}

    async def _fetch_all(self, qry) -> list:
        self.fetches += 1
        if self._falla(self.fetches):
            raise self._exc_factory()
        return [{"ok": 1}]

    async def _fetch_many(self, qry, limit, page) -> list:
        self.fetches += 1
        if self._falla(self.fetches):
            raise self._exc_factory()
        return [{"ok": 1}]

    # --- métodos públicos (compatibilidad 05-01; delegan al template en 05-02) ---

    async def execute(self, qry):
        if _DB_CON_TEMPLATE:
            return await super().execute(qry)
        return await self._execute(qry)

    async def execute_insert(self, qry):
        if _DB_CON_TEMPLATE:
            return await super().execute_insert(qry)
        return await self._execute_insert(qry)

    async def fetch_all(self, qry):
        if _DB_CON_TEMPLATE:
            return await super().fetch_all(qry)
        return await self._fetch_all(qry)

    async def fetch_one(self, qry):
        if _DB_CON_TEMPLATE:
            return await super().fetch_one(qry)
        return await self._fetch_one(qry)

    async def fetch_many(self, qry, limit, page):
        if _DB_CON_TEMPLATE:
            return await super().fetch_many(qry, limit, page)
        return await self._fetch_many(qry, limit, page)

    async def exists(self, qry) -> bool:
        return await self._fetch_one(qry) is not None

    # --- stubs mínimos del resto de abstractos ---

    async def commit(self):
        pass

    async def rollback(self, save_point: str | None = None):
        pass

    async def save_point(self, name: str):
        pass

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
        return None

    def delete(self, tabla: str, keys: dict, *, schema: str | None = None):
        return None

    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None):
        return None

    async def migrate(self, name: str, qry):
        pass

    async def migrate_status(self):
        return []


class FakeReconnectFalla(FakeResilientDb):
    """Doble cuyo `connect()` puede fallar para probar el fallo de `_reconnect`.

    La conexión inicial debe tener éxito (fija `_connected_at`/`_connect_kwargs`);
    después se activa `falla_connect` para que la reconexión lance la excepción de
    driver de `connect_exc_factory` y `_with_reconnect` tenga que traducirla.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.falla_connect = False
        self.connect_exc_factory = mysql_disconnect

    async def connect(self, **kwargs):
        if self.falla_connect:
            raise self.connect_exc_factory()
        await super().connect(**kwargs)
