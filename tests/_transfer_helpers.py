"""Helpers compartidos para los tests cross-engine de `copy_table` (plan 07-03).

La fuente común es una sqlite en memoria con una tabla tipada
(str/int/float/bool y datetime como TEXT, el mismo criterio de tipos que el
resto de los tests de transfer) y `assert_copy_equivale` reduce la verificación
de un motor cualquiera a la comparación canónica vía `_normalize_value`.
"""

from encino_orm import Query
from encino_orm.sqlite import SqliteDb
from encino_orm.transfer import _normalize_value, copy_table

SOURCE_DDL = (
    "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "nombre TEXT, edad INTEGER, monto REAL, activo BOOLEAN, creado TEXT)"
)

_CANON_COLS = (
    ("nombre", "str"),
    ("edad", "int"),
    ("monto", "float"),
    ("activo", "bool"),
    ("creado", "str"),
)


async def sqlite_source(n_rows: int = 500) -> SqliteDb:
    """Crea una fuente sqlite en memoria con `n_rows` filas tipadas."""
    src = SqliteDb()
    await src.connect(database=":memory:")
    await src.execute(Query(SOURCE_DDL, []))
    for i in range(n_rows):
        await src.execute(
            Query(
                "INSERT INTO t (nombre, edad, monto, activo, creado) VALUES ({0},{1},{2},{3},{4})",
                [
                    f"fila-{i}",
                    i % 90,
                    i / 2.0,
                    i % 2 == 0,
                    f"2026-09-{i % 28 + 1:02d} 10:00:00",
                ],
            )
        )
    return src


async def assert_copy_equivale(
    src, dst, *, n_rows: int, create: bool = True, preserve_ids: bool = True
) -> int:
    """Copia `t` y verifica conteo, ids e equivalencia canónica por columna."""
    copied = await copy_table(src, dst, "t", create=create, preserve_ids=preserve_ids)
    assert copied == n_rows
    src_rows = await src.fetch_all(Query("SELECT * FROM t ORDER BY id", []))
    dst_rows = await dst.fetch_all(Query("SELECT * FROM t ORDER BY id", []))
    assert len(dst_rows) == n_rows
    for i, (s, d) in enumerate(zip(src_rows, dst_rows, strict=True)):
        if preserve_ids:
            assert d["id"] == s["id"], "los ids se preservan"
        else:
            assert d["id"] == i + 1, "el motor genera ids secuenciales"
        for col, datatype in _CANON_COLS:
            assert _normalize_value(d[col], datatype) == _normalize_value(s[col], datatype), col
    return copied
