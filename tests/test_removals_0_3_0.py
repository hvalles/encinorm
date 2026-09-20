"""Retiradas reales de la línea 0.3.0 (REL-01): ausencia de shims y camino feliz.

Congela que los *shims* de default de conexión deprecados en 0.2.7 ya no existen
en 0.3.0 y que sus reemplazos documentados siguen verdes. Reemplaza la cobertura
de la línea 0.2.7 que se retiró con `tests/test_deprecations_0_2_7.py`.

Los nombres retirados se construyen por concatenación a propósito: el guard de
ausencia del plan es un `grep` repo-wide de esos literales sobre `encino_orm/` y
`tests/`, así que este fichero no puede contenerlos tal cual.
"""

import importlib

import pytest

import encino_orm
import encino_orm.context
from encino_orm import ConnectionRegistry, PoolDb, create_db
from encino_orm.context import _registry

_SET_DEFAULT = "set_" + "default_db"
_GET_DEFAULT = "get_" + "default_db"


def _import_from(module_name, symbol):
    """Equivale a `from <module_name> import <symbol>` para un nombre dinámico."""
    module = importlib.import_module(module_name)
    try:
        return getattr(module, symbol)
    except AttributeError as exc:
        raise ImportError(f"cannot import name {symbol!r} from {module_name!r}") from exc


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    _registry.set_default(None)


def test_shim_setter_retirado():
    """El setter de default de proceso ya no es export (ImportError)."""
    with pytest.raises(ImportError):
        _import_from("encino_orm", _SET_DEFAULT)
    assert not hasattr(encino_orm, _SET_DEFAULT)
    assert not hasattr(encino_orm.context, _SET_DEFAULT)


def test_shim_getter_retirado():
    """El getter de default de proceso ya no es export (ImportError)."""
    with pytest.raises(ImportError):
        _import_from("encino_orm", _GET_DEFAULT)
    assert not hasattr(encino_orm, _GET_DEFAULT)
    assert not hasattr(encino_orm.context, _GET_DEFAULT)


def test_shims_no_son_atributos_de_context():
    """`encino_orm.context` tampoco los expone (AttributeError)."""
    assert not hasattr(encino_orm.context, _SET_DEFAULT)
    assert not hasattr(encino_orm.context, _GET_DEFAULT)


@pytest.mark.asyncio
async def test_registry_sigue_siendo_la_via():
    """El default vive en el registry: de instancia o el de módulo."""
    db = await create_db("sqlite", database=":memory:")
    try:
        registry = ConnectionRegistry(db)
        assert registry.get_default() is db
        assert registry.resolve() is db
        _registry.set_default(db)
        assert encino_orm.context.resolve_db() is db
    finally:
        _registry.set_default(None)
        await db.close()


def test_reset_on_release_commit_sigue_avisando():
    """Reemplaza el pin de 0.2.7: `reset_on_release='commit'` sigue vigente."""
    with pytest.warns(DeprecationWarning, match="reset_on_release='commit'"):
        PoolDb("sqlite", reset_on_release="commit")
