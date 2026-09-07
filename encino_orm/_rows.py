"""Helper para convertir filas de un cursor (tuplas) a `dict` por descripción.

SQL Server (`aioodbc`/`pyodbc`) y Oracle (`oracledb` thin) devuelven tuplas y
exponen los nombres de columna en `cursor.description`. Este helper materializa
dicts con la clave en minúsculas, igual que el `DictCursor` de `aiomysql` y el
`Row` de `aiosqlite`.
"""


def _rows_to_dicts(description, rows) -> list[dict]:
    """Convierte `rows` (lista de tuplas) a lista de dicts usando `description`.

    `description` es la secuencia de tuplas que devuelven `cursor.description`
    en `pyodbc`/`oracledb`; el primer elemento de cada tupla es el nombre de la
    columna.
    """
    cols = [d[0].lower() for d in description]
    return [dict(zip(cols, row)) for row in rows]
