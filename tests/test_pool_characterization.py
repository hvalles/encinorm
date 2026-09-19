"""Caracterización del comportamiento de `PoolDb` (CI-09).

Estos tests documentan lo que `PoolDb` hace — incluidos los defectos aún
pendientes — y son la red de seguridad de la Fase 4: el refactor del pool
(POOL-01…POOL-07) ACTUALIZA (nunca borra) cada aserción que invierte. Cada
aserción que se espera invertir nombra el requisito POOL que la cambia.

Estado en 04-03: POOL-01 (handle `PooledConnection`), POOL-02 (admisión sin
carrera y `release()` con ownership), POOL-03 (id por conexión/tarea con
`execute_insert`) y POOL-04 (cierre explícito en `execute`/`_run` y política
`reset_on_release` con rollback por defecto) ya están implementados e
invertidos. POOL-05/06 (reaper y `close()`) siguen pendientes y conservan su
baseline.

Restricciones (D-09 + Research Correction 4): no se "arregla" ningún resultado
sorprendente, no se suaviza ninguna aserción de estado privado y no se
reescriben los `pytest.raises` amplios. El piso de Python es 3.10, así que no
se usan las primitivas de concurrencia añadidas en 3.11 (`Barrier`, `timeout`,
`TaskGroup`); la carrera se reproduce con una barrera determinista hecha con
`asyncio.Event`.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import pytest

import encino_orm.pool as pool_module
from encino_orm import PoolDb, PoolExhaustedError, Query
from encino_orm.pool import PooledConnection

_THIS_MODULE = sys.modules[__name__]


class FakeDb:
    """Doble de `Db` que registra cada llamada; modelado sobre `tests/test_pool.py`."""

    def __init__(self):
        self.connected = False
        self.closed = False
        self.calls = []
        self._last = 0
        self._in_tx = False

    @property
    def is_connected(self):
        return self.connected

    async def connect(self, **kwargs):
        self.connected = True

    async def close(self):
        self.closed = True
        self.connected = False

    async def is_alive(self):
        # Se registra para poder caracterizar que `release()` NO comprueba liveness.
        self.calls.append(("is_alive",))
        return self.connected

    @asynccontextmanager
    async def transaction(self):
        self.calls.append(("begin",))
        try:
            yield self
            self.calls.append(("commit",))
            self._in_tx = False
        except Exception:
            self.calls.append(("rollback",))
            self._in_tx = False
            raise

    def insert(self, tabla, data, ignore_duplicated=False, replace=False):
        return f"INSERT {tabla} {data}"

    def delete(self, tabla, keys):
        return f"DELETE {tabla} {keys}"

    def update(self, tabla, keys, values):
        return f"UPDATE {tabla} {keys} {values}"

    async def fetch_all(self, qry):
        self.calls.append(("fetch_all", qry))
        return [{"q": qry}]

    async def execute(self, qry):
        self.calls.append(("execute", qry))
        self._last = 42
        self._in_tx = True
        return 1

    async def execute_insert(self, qry):
        self.calls.append(("execute_insert", qry))
        self._last = 42
        self._in_tx = True
        return self._last

    async def _last_id_value(self):
        # `PoolDb.last_id()` delega aquí; se registra la llamada para que la
        # caracterización del scoping siga observándola.
        self.calls.append(("last_id",))
        return self._last

    async def in_transaction(self):
        return self._in_tx

    async def commit(self):
        self.calls.append(("commit",))
        self._in_tx = False

    async def save_point(self, name):
        self.calls.append(("save_point", name))

    async def rollback(self, save_point=None):
        self.calls.append(("rollback", save_point))
        if save_point is None:
            self._in_tx = False


# Barrera de conexión instalable por test. `monkeypatch.setattr` sobre este
# módulo la restaura automáticamente al terminar.
_CONNECT_BARRIER = None


class BlockingFakeDb(FakeDb):
    """`FakeDb` cuyo `connect()` espera a la barrera instalada, si la hay.

    Reproduce de forma determinista la carrera de `acquire()`: todas las tareas
    pasan la comprobación `_size < _max_size` antes de que ninguna incremente
    `_size`, porque quedan suspendidas en este `connect()`.
    """

    async def connect(self, **kwargs):
        barrier = _CONNECT_BARRIER
        if barrier is not None:
            await barrier.wait()
        await super().connect(**kwargs)


class EventBarrier:
    """Barrera determinista construida con `asyncio.Event`.

    El proyecto tiene un piso de Python 3.10, donde la clase `Barrier` de
    `asyncio` no existe (llega en 3.11). La liberación ocurre en la última
    llegada, nunca por un temporizador, así que el test no depende de `sleep`
    y no puede volverse flaky.
    """

    def __init__(self, parties: int):
        self._parties = parties
        self._arrived = 0
        self._event = asyncio.Event()

    async def wait(self):
        self._arrived += 1
        if self._arrived >= self._parties:
            self._event.set()
        await self._event.wait()

    def release(self):
        """Libera la barrera aunque no hayan llegado todas las `parties`.

        Necesario para tests donde, tras un fix, menos tareas de las previstas
        alcanzan el punto de espera (p. ej. la carrera de admisión de POOL-02).
        """
        self._event.set()


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "fake", FakeDb)
    return FakeDb


@pytest.fixture
def blocking_engine(monkeypatch):
    monkeypatch.setitem(pool_module._ENGINES, "blocking", BlockingFakeDb)
    return BlockingFakeDb


@pytest.fixture
async def pool(fake_engine):
    p = PoolDb("fake", min_size=2, max_size=5)
    await p.connect()
    yield p
    await p.close()


@pytest.fixture
async def single_pool(fake_engine):
    p = PoolDb("fake", min_size=1, max_size=1)
    await p.connect()
    yield p
    await p.close()


class TestPoolCheckoutCap:
    async def test_connect_creates_min_size_connections(self, pool):
        assert pool.is_connected is True
        assert pool._size == pool._min_size
        assert len(pool._connections) == pool._min_size

    async def test_sequential_acquisition_respects_max_size(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=3)
        await p.connect()

        conns = [await p.acquire() for _ in range(p._max_size)]

        assert p._size == p._max_size
        assert len(p._connections) == p._max_size

        for conn in conns:
            await p.release(conn)
        await p.close()

    async def test_holding_only_connection_raises_pool_exhausted(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()

        conn = await p.acquire()  # mantiene la única conexión
        with pytest.raises(PoolExhaustedError):
            await p.acquire(timeout=0.1)

        await p.release(conn)
        conn2 = await p.acquire(timeout=0.1)
        assert conn2 is conn
        await p.release(conn2)
        await p.close()


@pytest.mark.concurrency
class TestPoolAcquireOvershootRace:
    async def test_concurrent_acquire_does_not_overshoot_max_size(
        self, blocking_engine, monkeypatch
    ):
        p = PoolDb("blocking", min_size=0, max_size=2)
        await p.connect()

        # POOL-02: con la reserva de cupo ANTES del `await`, solo `max_size`
        # tareas alcanzan `connect()`, así que la barrera (parties=5, igual al
        # número de tareas) se libera explícitamente: bajo el baseline
        # pre-refactor las 5 llegaban y `_size` acababa en 5; con el fix solo
        # llegan 2. Las 3 restantes esperan en la cola y agotan su `timeout`.
        barrier = EventBarrier(parties=5)
        monkeypatch.setattr(_THIS_MODULE, "_CONNECT_BARRIER", barrier)

        tasks = [asyncio.create_task(p.acquire(timeout=0.5)) for _ in range(5)]
        # Deja que las tareas alcancen su punto de await y libera la barrera.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        barrier.release()

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # POOL-02: aserción invertida (baseline pre-refactor: `_size == 5`).
        assert p._size <= p._max_size
        assert sum(isinstance(r, PoolExhaustedError) for r in results) == 3

        await p.close()


class TestPoolLastIdScoping:
    async def test_inside_transaction_reads_held_connection(self, pool):
        qry = Query("INSERT 1", [])
        async with pool.transaction() as db:
            await pool.execute(qry)
            # POOL-03/Task 3: `last_id()` está DEPRECADO y emite warning; sigue
            # leyendo la conexión retenida para la caracterización del scoping.
            with pytest.warns(DeprecationWarning, match="deprecado"):
                rid = await pool.last_id()

        assert rid == 42
        assert ("execute", qry) in db.calls
        assert ("last_id",) in db.calls

    async def test_outside_transaction_has_no_pool_cache(self, single_pool):
        # POOL-03: se eliminó el cache de id a nivel de pool; fuera de una
        # transacción no hay conexión/tarea a la que asociar el id (devuelve 0).
        # El reemplazo es `execute_insert`.
        conn = next(iter(single_pool._connections))
        await single_pool.execute(Query("INSERT 1", []))

        with pytest.warns(DeprecationWarning, match="deprecado"):
            assert await single_pool.last_id() == 0

        calls_before = list(conn.driver.calls)
        with pytest.warns(DeprecationWarning, match="deprecado"):
            rid = await single_pool.last_id()

        assert rid == 0
        # `last_id()` fuera de transacción NO consulta la conexión.
        assert conn.driver.calls == calls_before

    async def test_no_cross_task_staleness(self, single_pool):
        # POOL-03: sin cache compartido, otra tarea no observa el id ajeno.
        await single_pool.execute(Query("INSERT 1", []))

        async def other_task():
            with pytest.warns(DeprecationWarning, match="deprecado"):
                return await single_pool.last_id()

        stale = await asyncio.create_task(other_task())
        assert stale == 0

    async def test_insert_inside_transaction_captures_handle_id(self, single_pool):
        # POOL-03: el id se captura por conexión/tarea DENTRO de una transacción.
        async with single_pool.transaction() as db:
            await single_pool.execute(Query("INSERT 1", []))
            with pytest.warns(DeprecationWarning, match="deprecado"):
                assert await single_pool.last_id() == 42
        assert ("last_id",) in db.calls

    async def test_lowercase_insert_inside_transaction_captures_handle_id(self, single_pool):
        async with single_pool.transaction() as db:
            await single_pool.execute(Query("insert into t values (1)", []))
            with pytest.warns(DeprecationWarning, match="deprecado"):
                assert await single_pool.last_id() == 42
        assert ("last_id",) in db.calls

    async def test_non_insert_outside_transaction_has_no_id(self, single_pool):
        # POOL-03: sin cache de pool, ninguna sentencia deja un id observable
        # fuera de una transacción.
        await single_pool.execute(Query("SELECT 1", []))
        with pytest.warns(DeprecationWarning, match="deprecado"):
            assert await single_pool.last_id() == 0


class TestPoolReleaseSemantics:
    async def test_release_records_last_used_and_requeues(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=2)
        await p.connect()
        conn = await p.acquire()

        conn.last_used = 0.0  # aísla el efecto de `release()`
        await p.release(conn)
        assert conn.last_used > 0.0

        reused = await p.acquire()
        assert reused is conn
        await p.close()

    async def test_release_rolls_back_leftover_transaction(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=2)
        await p.connect()
        conn = await p.acquire()
        conn.driver._in_tx = True

        await p.release(conn)

        # POOL-04: aserción INVERTIDA (antes: `release()` no tocaba la
        # transacción en absoluto). Con la política default `"rollback"`, el
        # sobrante de transacción se revierte al liberar.
        assert ("rollback", None) in conn.driver.calls
        await p.close()

    async def test_release_does_not_check_liveness(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=2)
        await p.connect()
        conn = await p.acquire()
        conn.driver.connected = False

        calls_before = list(conn.driver.calls)
        await p.release(conn)

        assert conn.driver.calls == calls_before
        assert all(call[0] != "is_alive" for call in conn.driver.calls)
        await p.close()

    async def test_double_release_does_not_alias_same_connection(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=2)
        await p.connect()
        conn = await p.acquire()

        await p.release(conn)
        await p.release(conn)  # segunda liberación: ignorada (ownership, POOL-02)

        # La cola NO duplica la referencia.
        assert p._idle.qsize() == 1

        conn_a = await p.acquire()
        conn_b = await p.acquire()

        # POOL-02: dos adquirentes distintos no comparten el mismo handle; el
        # segundo crea una conexión nueva (invierte `assert conn_a is conn_b`).
        assert conn_a is not conn_b
        await p.release(conn_a)
        await p.release(conn_b)
        await p.close()

    async def test_create_failure_returns_capacity(self, fake_engine, monkeypatch):
        # POOL-02: si `_create_connection()` falla, el cupo reservado vuelve.
        calls = {"n": 0}

        class FailingOnceDb(FakeDb):
            async def connect(self, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise RuntimeError("boom")
                await super().connect(**kwargs)

        monkeypatch.setitem(pool_module._ENGINES, "failing", FailingOnceDb)
        p = PoolDb("failing", min_size=0, max_size=1)
        await p.connect()

        with pytest.raises(RuntimeError):
            await p.acquire()

        assert p._size == 0  # el cupo no se filtró

        handle = await p.acquire()
        assert handle.driver.connected is True
        assert p._size == 1
        await p.release(handle)
        await p.close()

    async def test_release_foreign_handle_does_not_enqueue(self, fake_engine, caplog):
        p = PoolDb("fake", min_size=0, max_size=2)
        await p.connect()

        foreign = PooledConnection(driver=FakeDb())
        with caplog.at_level(logging.WARNING, logger="encino_orm"):
            await p.release(foreign)

        assert p._idle.empty()
        assert any("release()" in record.getMessage() for record in caplog.records)
        await p.close()


class TestPoolClose:
    async def test_close_normal_path(self, pool):
        conn = await pool.acquire()
        await pool.release(conn)

        await pool.close()

        assert pool.is_connected is False
        assert pool._size == 0
        assert len(pool._connections) == 0
        assert pool._idle.empty()
        assert conn.driver.closed is True

    async def test_close_is_idempotent(self, pool):
        conn = await pool.acquire()
        await pool.release(conn)

        await pool.close()
        await pool.close()  # segunda llamada: no debe lanzar

        assert pool.is_connected is False
        assert pool._size == 0
        assert len(pool._connections) == 0
        # POOL-06: baseline de idempotencia.

    async def test_close_closes_held_connection(self, pool):
        held = await pool.acquire()  # NO se libera

        await pool.close()

        # POOL-06: defecto caracterizado. `close()` cierra una conexión que un
        # llamador aún mantiene. Fase 4 exige que nunca cierre una conexión en
        # uso, así que esta aserción se espera INVERTIR (`held.driver.closed is False`).
        assert held.driver.closed is True

    async def test_close_never_connected_pool_does_not_raise(self, fake_engine):
        p = PoolDb("fake", min_size=0, max_size=1)

        await p.close()

        assert p.is_connected is False

    async def test_close_does_not_reset_stats(self, fake_engine):
        p = PoolDb("fake", min_size=1, max_size=1)
        await p.connect()
        creates_before = p.stats["creates"]
        assert creates_before == 1

        await p.close()

        assert p.stats["creates"] == creates_before
