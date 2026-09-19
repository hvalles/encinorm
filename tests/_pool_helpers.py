"""Helpers compartidos para los tests deterministas de concurrencia del pool.

Extraído de `tests/test_pool_characterization.py` para que `04-06` lo reutilice
sin duplicar la barrera ni los dobles de `Db`. El prefijo `_` evita que pytest
lo colecte como módulo de tests.

Restricción dura (Research Correction #4): el piso de Python es 3.10. La clase
`Barrier` de `asyncio`, `asyncio.timeout` y `TaskGroup` llegan en 3.11 y están
prohibidas aquí; `EventBarrier` se construye SOLO con `asyncio.Event`. Tampoco
se usan los dobles automáticos de la stdlib: la convención del repo son dobles
a mano.
"""

import asyncio
from contextlib import asynccontextmanager

__all__ = ["BlockingFakeDb", "EventBarrier", "FakeDb"]


class FakeDb:
    """Doble de `Db` que registra cada llamada en `self.calls`."""

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
        # 04-02 introduce `execute_insert` en el contrato de `Db`; el doble debe
        # responderlo para que los tests de 04-06 no se rompan. En 04-05 no se usa.
        self.calls.append(("execute_insert", qry))
        return self._last

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

    `parties` DEBE ser igual al número de tareas que alcanzan `wait()`: si es
    mayor, la barrera nunca se libera y el test se cuelga (lo corta
    `pytest-timeout` con el método *signal* en CI).
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
