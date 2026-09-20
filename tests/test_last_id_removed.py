"""Ausencia de la API post-hoc `last_id()` y camino feliz de `execute_insert`.

REL-01 (retirada de 0.3.0): `Db.last_id()`/`PoolDb.last_id()` y el helper
centralizado de warning ya no existen. El id se obtiene con `execute_insert(qry)`
o con el retorno de `Model.insert()`. Los nombres retirados se escriben en este
fichero porque es el guard de su ausencia.
"""

import pytest

import encino_orm.base as base
from encino_orm import Query, SqliteDb
from encino_orm.pool import PoolDb


def test_db_last_id_retirado():
    """`Db.last_id()` y el helper de warning ya no son atributos de `base`."""
    assert not hasattr(base.Db, "last_id")
    with pytest.raises(AttributeError):
        _ = base.Db.last_id
    assert not hasattr(base, "_warn_last_id_deprecated")


def test_pool_db_last_id_retirado():
    """`PoolDb.last_id()` ya no existe en la línea 0.3.0."""
    assert not hasattr(PoolDb, "last_id")
    with pytest.raises(AttributeError):
        _ = PoolDb.last_id


@pytest.mark.asyncio
async def test_execute_insert_devuelve_id():
    """El camino nuevo sigue devolviendo el id capturado dentro de la sentencia."""
    db = SqliteDb()
    await db.connect(database=":memory:")
    try:
        await db.execute(
            Query(
                "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)",
                [],
            )
        )
        q1 = db.insert("t", {"nombre": "Ana"}, returning="id")
        assert await db.execute_insert(q1) == 1
        q2 = db.insert("t", {"nombre": "Luis"}, returning="id")
        assert await db.execute_insert(q2) == 2
    finally:
        await db.close()
