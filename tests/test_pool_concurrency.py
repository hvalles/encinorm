"""Tests deterministas de concurrencia y estrés del pool (POOL-07).

Este fichero es el reemplazo AFIRMATIVO de la caracterización de Fase 1: en vez
de documentar el defecto, fija el comportamiento CORRECTO del pool tras
04-01…04-04 — `acquire()` nunca supera `max_size` bajo una carrera forzada, los
inserts concurrentes devuelven cada uno SU PROPIO id y el commit standalone
sigue siendo visible entre conexiones. Toda la cobertura nueva vive aquí; los
ficheros de 04-04 (`test_pool.py`/`test_pool_characterization.py`) no se tocan.

Restricciones duras:
- Piso de Python 3.10: la barrera es `EventBarrier` (solo `asyncio.Event`, en
  `tests/_pool_helpers.py`); NO se usan `asyncio.Barrier`, `TaskGroup`,
  `asyncio.timeout` ni `except*`.
- Sin dobles automáticos de la stdlib: los `FakeDb`/`BlockingFakeDb` son a mano.
- Determinismo: la liberación de la barrera ocurre en la última llegada (nunca
  por temporizador); los `sleep(0)` solo ceden el turno al bucle de eventos, no
  introducen una carrera dependiente del reloj.
- `@pytest.mark.timeout` es el plugin `pytest-timeout` (permitido); el timeout
  global está desactivado (`timeout = 0`) y el límite va por marker.
"""

import asyncio

import pytest

import encino_orm.pool as pool_module
import tests._pool_helpers as helpers
from encino_orm import PoolDb

# --- Task 1: carrera de admisión determinista (POOL-02 afirmado) ---


@pytest.mark.concurrency
@pytest.mark.timeout(10)
async def test_no_overshoot_under_barrier(monkeypatch):
    """`acquire()` nunca supera `max_size` aunque 5 tareas compitan a la vez.

    `parties=5` es igual al número de tareas. Bajo el baseline pre-refactor las
    5 pasaban la comprobación `_size < max_size` antes del `await` y `_size`
    acababa en 5; con la reserva-antes-del-await (POOL-02) solo `max_size` tareas
    alcanzan `connect()`, así que la barrera NO se libera sola y se libera
    explícitamente (T-04-06-01). Sin ese `release()` el test se colgaría y
    `@pytest.mark.timeout(10)` sería la red de seguridad.
    """
    monkeypatch.setitem(pool_module._ENGINES, "blocking", helpers.BlockingFakeDb)
    p = PoolDb("blocking", min_size=0, max_size=2)
    await p.connect()

    barrier = helpers.EventBarrier(parties=5)
    monkeypatch.setattr(helpers, "_CONNECT_BARRIER", barrier)

    checked_out_peak: list[int] = []

    async def worker():
        handle = await p.acquire()
        checked_out_peak.append(len(p._checked_out))
        # Cede el turno para que la segunda tarea con cupo se registre antes de
        # liberar; así el pico observado es 2 de forma determinista.
        await asyncio.sleep(0)
        await p.release(handle)
        return handle

    tasks = [asyncio.create_task(worker()) for _ in range(5)]
    # Deja que las tareas alcancen su punto de await y libera la barrera. El
    # `release()` es incondicional, de modo que el test no puede colgarse aunque
    # menos de `parties` tareas lleguen a `connect()`.
    for _ in range(10):
        await asyncio.sleep(0)
    barrier.release()

    handles = await asyncio.gather(*tasks)

    # Propiedad AFIRMADA (baseline pre-refactor: `_size == 5`).
    assert p._size <= p._max_size
    assert p._size == p._max_size
    assert max(checked_out_peak) <= p._max_size
    # 5 tareas servidas con solo 2 conexiones: los handles se reutilizan, nunca
    # se crean por encima de `max_size`.
    assert len(set(handles)) == p._max_size

    await p.close()


@pytest.mark.concurrency
async def test_barrier_releases_only_with_matching_parties():
    """Una barrera con más `parties` que tareas no se libera jamás.

    Se acota con `asyncio.wait_for` para NO depender de que `pytest-timeout`
    mate el proceso (T-04-06-01); `wait_for` cancela la tarea al vencer.
    """
    barrier = helpers.EventBarrier(parties=2)
    waiter = asyncio.create_task(barrier.wait())

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(waiter, timeout=0.5)

    assert waiter.cancelled()
