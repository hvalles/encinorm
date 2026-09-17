import asyncio
import os
import sys

import pytest

from encino_orm.sqlite import SqliteDb

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def db():
    return SqliteDb()


@pytest.fixture
async def connected_db():
    db = SqliteDb()
    await db.connect(database=":memory:")
    yield db
    await db.close()


def required_engines() -> set[str]:
    """Motores que DEBEN estar disponibles; se activa solo en CI (D-03)."""
    raw = os.getenv("ENCINO_ORM_REQUIRE_ENGINES", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def engine_unavailable(engine: str, exc: Exception) -> None:
    """Falla si el motor es requerido; si no, omite. Sustituye a `pytest.skip`.

    Los llamadores mantienen su `except Exception` sin estrechar (Pitfall 1 del
    research): un fallo de importacion o una variable mal escrita degradan a
    skip en local, que es justo el comportamiento que el interruptor invierte
    en CI. Estrechar ese `except` es seguimiento de Fase 2, fuera de CI-01.
    """
    if engine.lower() in required_engines():
        pytest.fail(
            f"{engine} es un motor requerido (ENCINO_ORM_REQUIRE_ENGINES) "
            f"pero no está disponible: {exc!r}"
        )
    pytest.skip(f"{engine} no disponible: {exc}")
