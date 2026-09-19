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
from encino_orm import PoolDb, Query

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


# --- Task 2: ids concurrentes sin cruce y commit standalone (POOL-03/04) ---


@pytest.fixture
async def sqlite_pool(tmp_path):
    """Pool SQLite real sobre fichero, patrón de `tests/test_pool.py`."""
    p = PoolDb(
        "sqlite",
        min_size=1,
        max_size=3,
        database=str(tmp_path / "concurrency.db"),
    )
    await p.connect()
    yield p
    await p.close()


async def _create_names_table(pool: PoolDb) -> None:
    await pool.execute(
        Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", [])
    )


@pytest.mark.concurrency
@pytest.mark.timeout(20)
async def test_concurrent_insert_ids_no_crosstalk(sqlite_pool):
    """Cada tarea recibe SU PROPIO id, sin cruce entre tareas.

    SQLite serializa las escrituras con su `busy_timeout`; el objetivo del test
    es la captura del id DENTRO de la sentencia (04-02), no el paralelismo del
    motor.
    """
    await _create_names_table(sqlite_pool)

    async def insert_one(nombre):
        qry = sqlite_pool.insert("t", {"nombre": nombre}, returning="id")
        return nombre, await sqlite_pool.execute_insert(qry)

    results = await asyncio.gather(*(insert_one(f"n{i}") for i in range(5)))
    mapping = dict(results)

    assert len(set(mapping.values())) == 5
    assert sorted(mapping.values()) == [1, 2, 3, 4, 5]

    rows = await sqlite_pool.fetch_all(Query("SELECT nombre, id FROM t", []))
    by_name = {r["nombre"]: r["id"] for r in rows}
    assert by_name == mapping


async def test_standalone_commit_visible_across_connections(sqlite_pool):
    """Un `pool.execute(INSERT)` standalone es visible desde otra conexión.

    Sin marker `concurrency`: no hay barrera; el commit explícito de 04-03 lo
    hace determinista.
    """
    await _create_names_table(sqlite_pool)

    await sqlite_pool.execute(sqlite_pool.insert("t", {"nombre": "a"}))

    rows = await sqlite_pool.fetch_all(Query("SELECT * FROM t", []))
    assert len(rows) == 1
    assert rows[0]["nombre"] == "a"


async def test_execute_insert_inside_transaction_uses_held_connection(sqlite_pool):
    """Dentro de `transaction()`, `execute_insert` usa la conexión retenida."""
    await _create_names_table(sqlite_pool)

    async with sqlite_pool.transaction():
        first = await sqlite_pool.execute_insert(
            sqlite_pool.insert("t", {"nombre": "a"}, returning="id")
        )
        second = await sqlite_pool.execute_insert(
            sqlite_pool.insert("t", {"nombre": "b"}, returning="id")
        )

    assert second == first + 1

    rows = await sqlite_pool.fetch_all(Query("SELECT nombre, id FROM t ORDER BY id", []))
    assert [r["nombre"] for r in rows] == ["a", "b"]
