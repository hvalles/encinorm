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
from encino_orm.exceptions import (
    ConnectionLostError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
    QueryError,
)
from encino_orm.pool import PoolDb
from encino_orm.query import Query
from tests._pool_helpers import FakeDb as PoolFakeDb
from tests._resilience_helpers import (
    FakeReconnectFalla,
    FakeResilientDb,
    mssql_disconnect_idle,
    mssql_disconnect_midquery,
    mssql_fk_violation,
    mssql_integrity,
    mssql_lock,
    mssql_lock_timeout,
    mssql_not_null,
    mssql_syntax,
    mysql_disconnect,
    mysql_gone_away,
    mysql_integrity,
    mysql_interface,
    mysql_lock,
    mysql_lock_timeout,
    mysql_operational,
    mysql_programming,
    oracle_disconnect_dpy,
    oracle_disconnect_ora,
    oracle_integrity,
    oracle_lock,
    oracle_lock_timeout,
    oracle_serialization,
    oracle_syntax,
    pg_cached_stmt,
    pg_disconnect,
    pg_integrity,
    pg_interface,
    pg_lock,
    pg_lock_not_available,
    pg_operational,
    pg_programming,
    pg_serialization,
    real_mssql_disconnect,
    real_oracle_disconnect,
    sqlite_disconnect,
    sqlite_disk_io,
    sqlite_integrity,
    sqlite_lock,
    sqlite_operational,
    sqlite_programming,
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

        with pytest.raises(ConnectionLostError):
            await db.execute(Query("UPDATE t SET x = {0}", [1]))
        assert db.connects == 1
        assert db.closes == 1
        assert db.executes == 1

    @pytest.mark.asyncio
    async def test_desconexion_dentro_de_tx_relanza_sin_reconectar(self):
        db = await _db_conectada(fail_first=1, tx=True)

        with pytest.raises(ConnectionLostError):
            await db.execute(Query("UPDATE t SET x = {0}", [1]))
        assert db.connects == 0
        assert db.closes == 0
        assert db.executes == 1

    @pytest.mark.asyncio
    async def test_fallo_persistente_no_hace_bucle(self):
        db = await _db_conectada(fail_first=99)

        with pytest.raises(ConnectionLostError):
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


# ---------------------------------------------------------------------------
# RESL-03: `pre_ping` / `max_connection_lifetime` (conexiones directas)
# Selector estable del bloque: `-k lifetime`.
# ---------------------------------------------------------------------------


class TestResilienceLifetime:
    """RESL-03: reciclado opt-in para conexiones DIRECTAS (no-pool).

    Patrón obligatorio (W4): en TODOS los tests de reciclado se llama PRIMERO
    `await fake.connect()` — es lo que fija `_connect_kwargs` y `_connected_at` —
    y DESPUÉS se muta `_connected_at`/`_connected` para simular edad o caída.
    Sin ese `connect()` previo, `_connected_at is None` y `_maybe_recycle` es
    no-op. Sin temporizadores reales ni pausas: el envejecimiento se hace por
    asignación directa sobre `_connected_at`.
    """

    def test_defaults_off(self):
        """Defaults conservadores: sin opt-in no hay sonda ni reciclado."""
        assert Db.pre_ping is False
        assert Db.max_connection_lifetime is None
        assert SqliteDb()._should_recycle() is False

    @pytest.mark.asyncio
    async def test_pre_ping_no_sondea_por_defecto(self):
        """Con `pre_ping=False` NO se llama `is_alive()` en el camino caliente."""
        db = FakeResilientDb(fail_first=0)
        await db.connect()

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.is_alive_calls == 0

    @pytest.mark.asyncio
    async def test_pre_ping_reconecta_cuando_is_alive_es_falso(self):
        """Pitfall 5: sonda muerta ⇒ reconectar INMEDIATAMENTE, no solo anotar."""
        db = FakeResilientDb(fail_first=0)
        await db.connect()  # fija _connect_kwargs/_connected_at (W4)
        db.pre_ping = True
        db._connected = False  # la sonda `is_alive()` devolverá False

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.is_alive_calls == 1
        assert db.connects == 2  # connect inicial + reconexión
        assert db.closes == 1

    @pytest.mark.asyncio
    async def test_max_lifetime_recicla_conexion_vieja(self):
        """Una conexión con edad >= lifetime se recicla antes de la operación."""
        db = FakeResilientDb(fail_first=0)
        await db.connect()  # fija _connect_kwargs/_connected_at (W4)
        db.max_connection_lifetime = 10.0
        db._connected_at -= 11  # envejece sin temporizador real

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.connects == 2
        assert db.closes == 1

    @pytest.mark.asyncio
    async def test_max_lifetime_no_recicla_conexion_joven(self):
        """Una conexión recién abierta NO se recicla."""
        db = FakeResilientDb(fail_first=0)
        await db.connect()
        db.max_connection_lifetime = 10.0

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.connects == 1
        assert db.closes == 0

    @pytest.mark.asyncio
    async def test_maybe_recycle_noop_si_nunca_conecto(self):
        """Nunca se recicla una conexión que no existió (`_connected_at is None`)."""
        db = FakeResilientDb(fail_first=0)
        db.pre_ping = True
        db.max_connection_lifetime = 1.0

        assert db._connected_at is None
        await db._maybe_recycle()
        assert db.connects == 0
        assert db.is_alive_calls == 0

    @pytest.mark.asyncio
    async def test_lifetime_no_recicla_dentro_de_transaccion(self):
        """CR-01: un reciclado proactivo NUNCA toca una transacción abierta.

        Cerrar la conexión revertiría el trabajo no confirmado en silencio; las
        sentencias posteriores correrían fuera de la transacción.
        """
        db = FakeResilientDb(fail_first=0, tx=True)
        await db.connect()
        db.max_connection_lifetime = 10.0
        db._connected_at -= 11

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.connects == 1
        assert db.closes == 0

    @pytest.mark.asyncio
    async def test_pre_ping_no_reconecta_dentro_de_transaccion(self):
        """CR-01: ni siquiera la sonda `pre_ping` corre dentro de una transacción."""
        db = FakeResilientDb(fail_first=0, tx=True)
        await db.connect()
        db.pre_ping = True
        db._connected = False

        assert await db.fetch_one(Query("SELECT 1", [])) == {"ok": 1}
        assert db.connects == 1
        assert db.closes == 0
        assert db.is_alive_calls == 0

    @pytest.mark.asyncio
    async def test_fallo_de_reconexion_proactiva_se_traduce(self):
        """WR-01: el fallo de `_maybe_recycle` no escapa crudo (RESL-04)."""
        db = FakeResilientDb(fail_first=0)
        await db.connect()
        db.pre_ping = True
        db._connected = False

        async def _connect_falla(**kwargs):
            raise mysql_disconnect()

        db.connect = _connect_falla

        with pytest.raises(ConnectionLostError) as raised:
            await db.fetch_one(Query("SELECT 1", []))
        assert isinstance(raised.value.__cause__, pymysql.err.OperationalError)

    def test_resilience_opts_extrae_y_valida(self):
        """`_resilience_opts` hace pop, normaliza y falla cerrado con `<= 0`."""
        db = SqliteDb()
        limpio = db._resilience_opts({"pre_ping": True, "max_connection_lifetime": 5, "db": "x"})
        assert limpio == {"db": "x"}
        assert db.pre_ping is True
        assert db.max_connection_lifetime == 5.0

        with pytest.raises(ValueError, match="max_connection_lifetime"):
            SqliteDb()._resilience_opts({"max_connection_lifetime": 0})

        db_none = SqliteDb()
        assert db_none._resilience_opts({"max_connection_lifetime": None}) == {}
        assert db_none.max_connection_lifetime is None

    @pytest.mark.asyncio
    async def test_sqlite_fichero_sobrevive_a_lifetime(self, tmp_path):
        """SQLite real: el reciclado por edad reconecta y NO pierde la fila."""
        db = SqliteDb()
        await db.connect(database=str(tmp_path / "lifetime.db"), max_connection_lifetime=10)
        try:
            assert db.max_connection_lifetime == 10.0
            assert "max_connection_lifetime" not in db._connect_kwargs
            await db.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)", []))
            await db.commit()
            await db.execute(db.insert("t", {"v": "hola"}))
            await db.commit()

            viejo = db._connected_at
            db._connected_at = viejo - 11  # envejece sin temporizador real
            assert await db.fetch_one(Query("SELECT v FROM t", [])) == {"v": "hola"}
            assert db._connected_at >= viejo  # se refrescó al reconectar
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_sqlite_memory_no_se_recicla_por_lifetime(self):
        """`:memory:` con lifetime vencido relanza en vez de crear una base vacía."""
        db = SqliteDb()
        await db.connect(database=":memory:", max_connection_lifetime=10)
        try:
            db._connected_at -= 11
            with pytest.raises(OrmConnectionError):
                await db.fetch_one(Query("SELECT 1", []))
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_pool_pasa_opciones_a_cada_conexion_fisica(self, monkeypatch):
        """A6: las opciones llegan al `connect()` de cada conexión FÍSICA.

        No se asserta reciclado a nivel de pool: eso es RELI-03 (v2); `pool.py`
        no se modifica.
        """
        import encino_orm.pool as pool_module

        capturado = []

        class _DriverEspia(PoolFakeDb):
            async def connect(self, **kwargs):
                capturado.append(kwargs)
                await super().connect(**kwargs)

        monkeypatch.setitem(pool_module._ENGINES, "fake", _DriverEspia)
        pool = PoolDb("fake", min_size=1, max_size=1, pre_ping=True, max_connection_lifetime=30)
        await pool.connect()
        try:
            assert capturado == [{"pre_ping": True, "max_connection_lifetime": 30}]
        finally:
            await pool.close()


# ---------------------------------------------------------------------------
# RESL-04: taxonomía pública y traducción driver → librería
# Selector estable del bloque: `-k translate`.
# ---------------------------------------------------------------------------

# (adaptador, builder de excepción de driver, excepción de la librería esperada)
_TRANSLATE_CASES = [
    (SqliteDb, sqlite_integrity, IntegrityError),
    (SqliteDb, sqlite_programming, ProgrammingError),
    (SqliteDb, sqlite_operational, OperationalError),
    (MysqlDb, mysql_integrity, IntegrityError),
    (MysqlDb, mysql_programming, ProgrammingError),
    (MysqlDb, mysql_operational, OperationalError),
    (MariadbDb, mysql_integrity, IntegrityError),
    (PostgresDb, pg_integrity, IntegrityError),
    (PostgresDb, pg_programming, ProgrammingError),
    (PostgresDb, pg_operational, OperationalError),
    (MssqlDb, mssql_integrity, IntegrityError),
    (MssqlDb, mssql_fk_violation, IntegrityError),
    (MssqlDb, mssql_not_null, IntegrityError),
    (MssqlDb, mssql_syntax, ProgrammingError),
    (OracleDb, oracle_integrity, IntegrityError),
    (OracleDb, oracle_syntax, ProgrammingError),
]


@pytest.mark.parametrize(("db_cls", "exc_factory", "expected"), _TRANSLATE_CASES)
def test_translate_por_motor(db_cls, exc_factory, expected):
    """Cada adaptador mapea su driver a la taxonomía (RESL-04)."""
    translated = db_cls()._translate_exception(exc_factory())
    assert type(translated) is expected


@pytest.mark.parametrize(("db_cls", "lock_factory"), _LOCK_CASES)
def test_translate_lock_no_se_traduce(db_cls, lock_factory):
    """Pitfall 3: un lock se devuelve SIN traducir (identidad) para `retry()`."""
    db = db_cls()
    lock_exc = lock_factory()
    assert db._translate_exception(lock_exc) is lock_exc


@pytest.mark.parametrize(("db_cls", "disconnect_factory"), _DISCONNECT_CASES)
def test_translate_disconnect_a_connection_lost(db_cls, disconnect_factory):
    """Una desconexión se traduce a `ConnectionLostError` (subclase de ConnectionError)."""
    translated = db_cls()._translate_exception(disconnect_factory())
    assert type(translated) is ConnectionLostError
    assert isinstance(translated, OrmConnectionError)


def test_translate_encinoorm_error_tal_cual():
    """Idempotencia: una excepción de la librería no se re-traduce."""
    db = SqliteDb()
    exc = QueryError("boom")
    assert db._translate_exception(exc) is exc


@pytest.mark.asyncio
async def test_translate_with_reconnect_preserva_la_causa():
    """T-05-04-05: el relanzado usa `from exc` y conserva la causa del driver."""
    driver_exc = mysql_disconnect()
    db = await _db_conectada(fail_first=1, tx=True, exc_factory=lambda: driver_exc)

    with pytest.raises(ConnectionLostError) as raised:
        await db.fetch_one(Query("SELECT 1", []))
    assert raised.value.__cause__ is driver_exc


@pytest.mark.asyncio
async def test_translate_reconnect_fallido_se_traduce():
    """Un fallo de `_reconnect()` no escapa crudo: se traduce y encadena la causa."""
    db = FakeReconnectFalla(fail_first=1)
    await db.connect()
    db.falla_connect = True

    with pytest.raises(ConnectionLostError) as raised:
        await db.fetch_one(Query("SELECT 1", []))
    assert isinstance(raised.value.__cause__, pymysql.err.OperationalError)


@pytest.mark.asyncio
async def test_translate_sqlite_memory_lanza_connection_lost():
    """`:memory:` rechaza reconectar con `ConnectionLostError` (subclase compatible)."""
    db = SqliteDb()
    await db.connect(database=":memory:")
    try:
        with pytest.raises(ConnectionLostError) as raised:
            await db._reconnect()
        assert isinstance(raised.value, OrmConnectionError)
    finally:
        await db.close()
