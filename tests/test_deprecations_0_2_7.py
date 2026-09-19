"""Pines de los `DeprecationWarning` de la línea 0.2.7 (REL-01).

Cada ruptura 0.3.0 que PUEDE avisar emite aquí un `DeprecationWarning` de
runtime, pinado con `pytest.warns` bajo `filterwarnings=["error"]`. La ruptura
de identificadores no validados es **fail-closed** (rechaza ANTES de aceptar),
de modo que no puede emitir un warning previo; además, la allowlist tolerante a
puntos de `sql.py`/`query_builder.py` es diseño intencional y se blinda con un
guard para no reintroducir un warning inventado en el camino feliz.
"""

import warnings

import pytest
from pydantic import Field

from encino_orm import PoolDb
from encino_orm.model import Model, QueryBuilder
from encino_orm.model.query_builder import _safe_column
from encino_orm.security import guard
from encino_orm.security.guard import get_current_user
from encino_orm.sql import SqlFunctions
from encino_orm.sqlite import SqliteDb

# Material de firma de prueba: nunca debe aparecer en el mensaje de warning.
_SIGNING_MATERIAL = "material-de-firma-de-prueba-con-32-bytes-o-mas"


class _Agente(Model):
    _table = "agentes"
    agente: str | None = Field(default=None)


async def _noop_get_db():
    raise NotImplementedError  # nunca se invoca: el fallback solo resuelve la config


def test_implicit_commit_on_release_avisa():
    """`reset_on_release='commit'` es la política vieja deprecada (pool)."""
    with pytest.warns(DeprecationWarning, match="reset_on_release='commit'") as record:
        PoolDb("sqlite", reset_on_release="commit")
    assert len(record) == 1


def test_secret_get_db_globales_avisan():
    """El fallback legacy nombra los NOMBRES de los globales, nunca sus valores."""
    previous = (guard.SECRET, guard.GET_DB)
    guard.SECRET = _SIGNING_MATERIAL
    guard.GET_DB = _noop_get_db
    try:
        with pytest.warns(DeprecationWarning, match="deprecad") as record:
            get_current_user()
        assert len(record) == 1
        assert _SIGNING_MATERIAL not in str(record[0].message)
    finally:
        guard.SECRET, guard.GET_DB = previous


@pytest.mark.asyncio
async def test_last_id_post_hoc_avisa():
    """`last_id()` devolvía el id de otra fila bajo concurrencia; queda deprecado."""
    db = SqliteDb()
    await db.connect(database=":memory:")
    try:
        with pytest.warns(DeprecationWarning, match="deprecado") as record:
            await db.last_id()
        assert len(record) == 1
    finally:
        await db.close()


def test_identificador_cualificado_no_avisa():
    """Guard de la allowlist intencionalmente tolerante a puntos (NO se unifica)."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        QueryBuilder(_Agente, None).select("mm.agente")
        assert SqlFunctions("sqlite")._col("t.c") == "t.c"


def test_hostil_sigue_fallando_cerrado():
    """Un identificador hostil lanza `ValueError` fail-closed, sin warning previo."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(ValueError):
            _safe_column("x; DROP TABLE t --")
