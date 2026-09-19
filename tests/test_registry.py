"""CFG-01: `ConnectionRegistry` aísla el default de conexión por instancia."""

import warnings

import pytest

from encino_orm import (
    ConnectionError,
    ConnectionRegistry,
    bind,
    create_db,
    get_default_db,
    resolve_db,
    set_default_db,
)
from encino_orm.context import _registry


@pytest.fixture(autouse=True)
def _clean_registry():
    yield
    _registry.set_default(None)


@pytest.mark.asyncio
async def test_dos_registries_resuelven_a_su_propia_db():
    db_a = await create_db("sqlite", database=":memory:")
    db_b = await create_db("sqlite", database=":memory:")
    try:
        ra = ConnectionRegistry(db_a)
        rb = ConnectionRegistry(db_b)
        assert ra.resolve() is db_a
        assert rb.resolve() is db_b
    finally:
        await db_a.close()
        await db_b.close()


def test_registry_sin_default_lanza_connection_error():
    with pytest.raises(ConnectionError):
        ConnectionRegistry().resolve()


@pytest.mark.asyncio
async def test_resolve_db_sin_argumentos_usa_el_registry_de_modulo():
    db_a = await create_db("sqlite", database=":memory:")
    try:
        with pytest.warns(DeprecationWarning, match="set_default_db"):
            set_default_db(db_a)
        assert resolve_db() is db_a
    finally:
        _registry.set_default(None)
        await db_a.close()


@pytest.mark.asyncio
async def test_shim_deprecado_avisa():
    db_a = await create_db("sqlite", database=":memory:")
    try:
        with pytest.warns(DeprecationWarning, match="set_default_db"):
            set_default_db(db_a)
        with pytest.warns(DeprecationWarning, match="get_default_db"):
            assert get_default_db() is db_a
    finally:
        _registry.set_default(None)
        await db_a.close()


def test_teardown_no_deprecado_no_avisa():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        _registry.set_default(None)


@pytest.mark.asyncio
async def test_bind_gana_al_default_del_registry():
    db_a = await create_db("sqlite", database=":memory:")
    db_b = await create_db("sqlite", database=":memory:")
    try:
        ra = ConnectionRegistry(db_a)
        with bind(db_b):
            assert ra.resolve() is db_b
        assert ra.resolve() is db_a
    finally:
        await db_a.close()
        await db_b.close()


@pytest.mark.asyncio
async def test_camino_caliente_sin_warnings():
    db_a = await create_db("sqlite", database=":memory:")
    try:
        _registry.set_default(db_a)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert resolve_db() is db_a
    finally:
        _registry.set_default(None)
        await db_a.close()


@pytest.mark.asyncio
async def test_resolve_db_acepta_registry_explicito():
    db_a = await create_db("sqlite", database=":memory:")
    try:
        ra = ConnectionRegistry(db_a)
        assert resolve_db(registry=ra) is db_a
    finally:
        await db_a.close()


def test_resolve_db_no_ignora_un_registry_falsy():
    """WR-03: un registry que se evalúa como falsy NO debe caer al de módulo."""
    db_modulo = object()
    db_falsy = object()
    _registry.set_default(db_modulo)

    class _RegistryFalsy(ConnectionRegistry):
        def __bool__(self):
            return False

    ra = _RegistryFalsy(db_falsy)
    assert resolve_db(registry=ra) is db_falsy
