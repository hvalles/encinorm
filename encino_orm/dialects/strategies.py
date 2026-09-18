"""Estrategias de construcción de INSERT por dialecto.

`InsertStrategy` describe la FORMA del INSERT, no el SQL completo: `kind`
discrimina los TRES renders de `dialects/builders.py` (prefijo, sufijo y
`MERGE INTO`), de modo que el builder ramifica tres veces y no seis. Las
constantes de módulo son DATOS, no ramas: cada adaptador elige una desde su hook
`_insert_strategy(...)`.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class InsertStrategy:
    """Forma del INSERT de un dialecto. `kind` discrimina los tres renders."""

    kind: Literal["prefix", "suffix", "merge"]
    # kind="prefix": palabra clave base cuando replace/ignore_duplicated están activos.
    replace_prefix: str = "INSERT OR REPLACE"
    ignore_prefix: str = "INSERT OR IGNORE"
    # kind="merge": `AS` antes de los alias (MSSQL) o cadena vacía (Oracle, que
    # no admite `AS` para el alias de tabla).
    merge_alias_keyword: str = "AS"
    # MSSQL/Oracle suprimen la violación de unicidad en `execute()`, no en el SQL.
    carries_ignore_duplicated: bool = False
    # Oracle añade `RETURNING id INTO :ret_id` en el INSERT plano sin `id`.
    returning_id: bool = False


SQLITE_INSERT = InsertStrategy(kind="prefix")
MYSQL_INSERT = InsertStrategy(
    kind="prefix", replace_prefix="REPLACE", ignore_prefix="INSERT IGNORE"
)
# MariaDB habla el protocolo MySQL: hereda literalmente su estrategia.
MARIADB_INSERT = MYSQL_INSERT
POSTGRES_INSERT = InsertStrategy(kind="suffix")
MSSQL_INSERT = InsertStrategy(kind="merge", carries_ignore_duplicated=True)
ORACLE_INSERT = InsertStrategy(
    kind="merge",
    merge_alias_keyword="",
    carries_ignore_duplicated=True,
    returning_id=True,
)

__all__ = [
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "InsertStrategy",
]
