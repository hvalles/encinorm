"""Tests de resiliencia (Fase 5): clasificación de desconexión por motor.

Bloque RESL-01: cada adaptador clasifica una desconexión simulada como
`is_disconnect_error(exc) is True` y NO misclasifica un error de lock/deadlock
(`is_lock_error(exc) is True` ⇒ `is_disconnect_error(exc) is False`). Los
builders de excepciones viven en `tests/_resilience_helpers.py` con las firmas
reales verificadas contra desconexiones reales (`05-RESEARCH.md`).

Los tests unitarios NO necesitan servidores: construyen la excepción del driver
con su tipo/errno/SQLSTATE/códigos reales. La construcción con el tipo REAL de
`pyodbc`/`oracledb` vive en tests `optional_engine` que degradan a skip si el
extra no está instalado.

Selector estable del bloque: `-k disconnect`.

El bloque RESL-02 (`-k reconnect`) prueba el template method `_with_reconnect`
con `FakeResilientDb`: reconexión exactamente una vez fuera de transacción, guard
de transacción y la política A2 de escrituras (lecturas re-ejecutan; escrituras
pre-ejecución ejecutan; escrituras mid-statement reconectan y relanzan).
"""

import pymysql.err
import pytest

from encino_orm import MariadbDb, MssqlDb, MysqlDb, OracleDb, PostgresDb, SqliteDb
from encino_orm.base import Db
from encino_orm.exceptions import ConnectionError as OrmConnectionError
from encino_orm.exceptions import QueryError
from encino_orm.pool import PoolDb
from encino_orm.query import Query
from tests._pool_helpers import FakeDb as PoolFakeDb
from tests._resilience_helpers import (
    FakeResilientDb,
    mssql_disconnect_idle,
    mssql_disconnect_midquery,
    mssql_lock,
    mssql_lock_timeout,
    mysql_disconnect,
    mysql_gone_away,
    mysql_interface,
    mysql_lock,
    mysql_lock_timeout,
    oracle_disconnect_dpy,
    oracle_disconnect_ora,
    oracle_lock,
    oracle_lock_timeout,
    oracle_serialization,
    pg_cached_stmt,
    pg_disconnect,
    pg_interface,
    pg_lock,
    pg_lock_not_available,
    pg_serialization,
    real_mssql_disconnect,
    real_oracle_disconnect,
    sqlite_disconnect,
    sqlite_disk_io,
    sqlite_lock,
)
from tests.conftest import engine_unavailable

# (clase de adaptador, builder de desconexión) — deben clasificar como disconnect.
_DISCONNECT_CASES = [
    (SqliteDb, sqlite_disconnect),
    (SqliteDb, sqlite_disk_io),
    (MysqlDb, mysql_disconnect),
    (MysqlDb, mysql_gone_away),
    (MysqlDb, mysql_interface),
    (MariadbDb, mysql_disconnect),
    (PostgresDb, pg_disconnect),
    (PostgresDb, pg_interface),
    (MssqlDb, mssql_disconnect_midquery),
    (MssqlDb, mssql_disconnect_idle),
    (OracleDb, oracle_disconnect_dpy),
    (OracleDb, oracle_disconnect_ora),
]

# (clase de adaptador, builder de lock) — deben clasificar como lock y NO disconnect.
_LOCK_CASES = [
    (SqliteDb, sqlite_lock),
    (MysqlDb, mysql_lock),
    (MysqlDb, mysql_lock_timeout),
    (MariadbDb, mysql_lock),
    (PostgresDb, pg_lock),
    (PostgresDb, pg_serialization),
    (PostgresDb, pg_lock_not_available),
    (MssqlDb, mssql_lock),
    (MssqlDb, mssql_lock_timeout),
    (OracleDb, oracle_lock),
    (OracleDb, oracle_lock_timeout),
    (OracleDb, oracle_serialization),
]

# Par disconnect/lock por motor, para la exclusión mutua (Success Criterion 1).
_ENGINE_CASES = [
    (SqliteDb, sqlite_disconnect, sqlite_lock),
    (MysqlDb, mysql_disconnect, mysql_lock),
    (MariadbDb, mysql_disconnect, mysql_lock),
    (PostgresDb, pg_disconnect, pg_lock),
    (MssqlDb, mssql_disconnect_midquery, mssql_lock),
    (OracleDb, oracle_disconnect_dpy, oracle_lock),
]


def test_db_default_is_disconnect_error_false():
    """El hook por defecto de `Db` es `False` (mismo contrato que `is_lock_error`).

    Se invoca sin instancia (`Db` es ABC) porque el cuerpo del hook no usa
    `self`; así se prueba el default sin construir un doble.
    """
    assert Db.is_disconnect_error(None, Exception("x")) is False


@pytest.mark.parametrize(("db_cls", "exc_factory"), _DISCONNECT_CASES)
def test_is_disconnect_error(db_cls, exc_factory):
    db = db_cls()
    assert db.is_disconnect_error(exc_factory()) is True


@pytest.mark.parametrize(("db_cls", "exc_factory"), _LOCK_CASES)
def test_lock_no_es_disconnect(db_cls, exc_factory):
    db = db_cls()
    exc = exc_factory()
    assert db.is_lock_error(exc) is True
    assert db.is_disconnect_error(exc) is False


def test_invalid_cached_statement_no_es_disconnect_ni_lock():
    """`InvalidCachedStatementError` es invalidación de statement cache, no pérdida."""
    db = PostgresDb()
    exc = pg_cached_stmt()
    assert db.is_disconnect_error(exc) is False
    assert db.is_lock_error(exc) is False


@pytest.mark.parametrize(("db_cls", "disconnect_factory", "lock_factory"), _ENGINE_CASES)
def test_disconnect_y_lock_son_excluyentes(db_cls, disconnect_factory, lock_factory):
    """Exclusión mutua por motor: un lock NUNCA se clasifica como disconnect."""
    db = db_cls()
    assert db.is_disconnect_error(disconnect_factory()) is True

    lock_exc = lock_factory()
    assert db.is_lock_error(lock_exc) is True
    assert db.is_disconnect_error(lock_exc) is False
    assert not (db.is_disconnect_error(lock_exc) and db.is_lock_error(lock_exc))


@pytest.mark.optional_engine
def test_disconnect_con_driver_real_mssql():
    try:
        exc = real_mssql_disconnect()
    except ImportError as e:  # pragma: no cover - depende del entorno
        engine_unavailable("mssql", e)
    assert MssqlDb().is_disconnect_error(exc) is True


@pytest.mark.optional_engine
def test_disconnect_con_driver_real_oracle():
    try:
        exc = real_oracle_disconnect()
    except ImportError as e:  # pragma: no cover - depende del entorno
        engine_unavailable("oracle", e)
    assert OracleDb().is_disconnect_error(exc) is True


# ---------------------------------------------------------------------------
# RESL-02: `_with_reconnect` (reconecta-una-vez, guard de tx, política A2)
# Selector estable del bloque: `-k reconnect`.
# ---------------------------------------------------------------------------


async def _db_conectada(**kwargs) -> FakeResilientDb:
    """`FakeResilientDb` con una conexión VIVA y los contadores a cero.

    Los tests de reconexión miden SOLO la reconexión, así que la conexión
    inicial se descuenta: `connects`/`closes` reflejan lo que hace
    `_with_reconnect`.
    """
    db = FakeResilientDb(**kwargs)
    await db.connect()
    db.connects = 0
    db.closes = 0
    return db


class _DoblePublico(Db):
    """Doble que solo sobreescribe el PÚBLICO `execute` (Pitfall 10).

    No define `_execute`: si `Db._execute` fuese `@abstractmethod` esta clase no
    sería instanciable. Su `execute` no llama a `super()`, de modo que el MRO
    nunca entra al wrapper de `Db` (el contador de `connect` no cambia).
    """

    dialect = "fake"

    def __init__(self):
        self.connects = 0
        self.executes = 0

    async def connect(self, **kwargs):
        self.connects += 1

    async def close(self): ...
    async def is_alive(self):
        return True

    async def in_transaction(self):
        return False

    async def commit(self): ...
    async def rollback(self, save_point=None): ...
    async def save_point(self, name): ...

    def insert(
        self,
        tabla,
        data,
        ignore_duplicated=False,
        replace=False,
        conflict=None,
        *,
        schema=None,
        returning=None,
    ):
        return None

    def delete(self, tabla, keys, *, schema=None):
        return None

    def update(self, tabla, keys, values, *, schema=None):
        return None

    async def execute(self, qry):
        self.executes += 1
        return 1

    async def exists(self, qry):
        return False

    async def migrate(self, name, qry): ...
    async def migrate_status(self):
        return []


class TestWithReconnect:
    """RESL-02: reconexión única fuera de tx y política A2 de escrituras."""

    @pytest.mark.asyncio
    async def test_lectura_desconectada_fuera_de_tx_reconecta_una_vez(self):
        db = await _db_conectada(fail_first=1)

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.connects == 1
        assert db.closes == 1
        assert db.fetches == 2

    @pytest.mark.asyncio
    async def test_escritura_pre_ejecucion_reconecta_y_ejecuta(self):
        """A2: la `ConnectionError` de la librería implica que la sentencia NUNCA
        llegó al driver, así que re-ejecutar es la PRIMERA ejecución (Pitfall 1)."""
        exc = OrmConnectionError("No hay conexión activa a la base de datos.")
        db = await _db_conectada(disconnect=False, fail_first=1, exc_factory=lambda: exc)

        assert await db.execute(Query("UPDATE t SET x = {0}", [1])) == "ok"
        assert db.connects == 1
        assert db.closes == 1
        assert db.executes == 2

    @pytest.mark.asyncio
    async def test_escritura_mid_statement_reconecta_pero_no_reejecuta(self):
        """A2: un disconnect de driver pudo aplicarse en el servidor → reconecta
        para el futuro, pero relanza sin re-ejecutar (nunca duplica en silencio)."""
        db = await _db_conectada(fail_first=1, exc_factory=mysql_disconnect)

        with pytest.raises(pymysql.err.OperationalError):
            await db.execute(Query("UPDATE t SET x = {0}", [1]))
        assert db.connects == 1
        assert db.closes == 1
        assert db.executes == 1

    @pytest.mark.asyncio
    async def test_desconexion_dentro_de_tx_relanza_sin_reconectar(self):
        db = await _db_conectada(fail_first=1, tx=True)

        with pytest.raises(pymysql.err.OperationalError):
            await db.execute(Query("UPDATE t SET x = {0}", [1]))
        assert db.connects == 0
        assert db.closes == 0
        assert db.executes == 1

    @pytest.mark.asyncio
    async def test_fallo_persistente_no_hace_bucle(self):
        db = await _db_conectada(fail_first=99)

        with pytest.raises(pymysql.err.OperationalError):
            await db.fetch_one(Query("SELECT 1", []))
        assert db.fetches == 2  # EXACTAMENTE un segundo intento, sin bucle
        assert db.connects == 1

    @pytest.mark.asyncio
    async def test_error_no_reconectable_relanza(self):
        db = await _db_conectada(disconnect=False, exc_factory=lambda: QueryError("boom"))

        with pytest.raises(QueryError):
            await db.fetch_one(Query("SELECT 1", []))
        assert db.connects == 0

    @pytest.mark.asyncio
    async def test_lock_no_se_reconecta_y_conserva_la_excepcion(self):
        """Un lock se relanza como la MISMA instancia para que `retry()` lo vea."""
        exc = mysql_lock()
        db = await _db_conectada(disconnect=False, lock=True, exc_factory=lambda: exc)

        with pytest.raises(pymysql.err.OperationalError) as raised:
            await db.fetch_one(Query("SELECT 1", []))
        assert raised.value is exc
        assert db.connects == 0

    @pytest.mark.asyncio
    async def test_reconnect_noop_si_nunca_conecto(self):
        db = FakeResilientDb()

        assert db._connected_at is None
        await db._reconnect()
        assert db.connects == 0

    @pytest.mark.asyncio
    async def test_sqlite_memory_rechaza_reconectar(self):
        db = SqliteDb()
        await db.connect(database=":memory:")
        try:
            with pytest.raises(OrmConnectionError):
                await db._reconnect()
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_sqlite_fichero_reconecta_sin_perder_filas(self, tmp_path):
        db = SqliteDb()
        await db.connect(database=str(tmp_path / "resiliencia.db"))
        try:
            await db.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)", []))
            await db.commit()
            await db.execute(db.insert("t", {"v": "hola"}))
            await db.commit()

            await db._reconnect()

            assert await db.fetch_one(Query("SELECT v FROM t", [])) == {"v": "hola"}
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_dobles_que_heredan_de_db_siguen_instanciandose(self):
        db = _DoblePublico()

        assert db._connected_at is None
        assert await db.execute(Query("UPDATE t SET x = {0}", [1])) == 1
        assert db.executes == 1
        assert db.connects == 0  # el MRO resolvió el override; no entró al wrapper

    @pytest.mark.asyncio
    async def test_pool_no_reconecta_dos_veces(self, monkeypatch):
        import encino_orm.pool as pool_module

        ejecuciones = []

        class _DriverEspia(PoolFakeDb):
            async def execute(self, qry):
                ejecuciones.append(qry)
                return await super().execute(qry)

        class _PoolEspia(PoolDb):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.reconnect_calls = 0

            async def _with_reconnect(self, fn, *, retry):
                self.reconnect_calls += 1
                return await super()._with_reconnect(fn, retry=retry)

        monkeypatch.setitem(pool_module._ENGINES, "fake", _DriverEspia)
        pool = _PoolEspia("fake", min_size=1, max_size=2)
        await pool.connect()
        try:
            qry = Query("SELECT 1", [])
            assert await pool.execute(qry) == 1
            assert ejecuciones == [qry]  # el driver ejecutó EXACTAMENTE una vez
            assert pool.reconnect_calls == 0  # PoolDb no se envuelve a sí mismo
        finally:
            await pool.close()
