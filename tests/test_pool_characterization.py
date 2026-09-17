"""Caracterización del comportamiento actual de `PoolDb` (CI-09).

Estos tests documentan lo que `PoolDb` HACE HOY — incluidos sus defectos
conocidos — contra la implementación sin modificar. Deben pasar tal cual sobre
`encino_orm/pool.py` y son la red de seguridad de la Fase 4: el refactor del
pool (POOL-01…POOL-07) debe ACTUALIZAR (no borrar) cada aserción que invierta.
Cada aserción que se espera invertir nombra el requisito POOL que la cambia.

Restricciones (D-09 + Research Correction 4): no se "arregla" ningún resultado
sorprendente, no se suaviza ninguna aserción de estado privado y no se
reescriben los `pytest.raises` amplios. El piso de Python es 3.10, así que no
se usan las primitivas de concurrencia añadidas en 3.11 (`Barrier`, `timeout`,
`TaskGroup`); la carrera se reproduce con una barrera determinista hecha con
`asyncio.Event`.
"""

import asyncio
import sys
from contextlib import asynccontextmanager

import pytest

import encino_orm.pool as pool_module
from encino_orm import PoolDb, PoolExhaustedError

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

    async def last_id(self):
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
    async def test_concurrent_acquire_overshoots_max_size(self, blocking_engine, monkeypatch):
        p = PoolDb("blocking", min_size=0, max_size=2)
        await p.connect()

        # El número de tareas DEBE ser igual a `parties`; un desajuste dejaría
        # la barrera sin liberar y el test se colgaría.
        barrier = EventBarrier(parties=5)
        monkeypatch.setattr(_THIS_MODULE, "_CONNECT_BARRIER", barrier)

        tasks = [asyncio.create_task(p.acquire()) for _ in range(5)]
        await asyncio.gather(*tasks)

        # POOL-02: baseline pre-refactor. Cada tarea pasó `_size < _max_size`
        # antes de que ninguna incrementase `_size`, porque `_create_connection()`
        # es un punto de await. Esta aserción se espera INVERTIR en Fase 4
        # (pasará a `_size <= _max_size`).
        assert p._size > p._max_size
        assert p._size == 5

        await p.close()
