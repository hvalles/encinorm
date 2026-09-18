"""Estrategias de construcción de INSERT por dialecto.

`InsertStrategy` describe la FORMA del INSERT, no el SQL completo: `kind`
discrimina los TRES renders de `dialects/builders.py` (prefijo, sufijo y
`MERGE INTO`), de modo que el builder ramifica tres veces y no seis. Las
constantes de módulo son DATOS, no ramas: cada adaptador elige una desde su hook
`_insert_strategy(...)`.
"""

from dataclasses import dataclass
from typing import Literal

from ..engine import Engine


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

# Tipo de UPSERT por dialecto. Reproduce LITERALMENTE el comportamiento actual de
# `Model.upsert`, que ramifica con `dialect is Engine.MYSQL` (identidad exacta):
# por eso `"mariadb"` NO entra en la rama MySQL y cae en `on_conflict`. Preservar
# ese comportamiento es el criterio de aceptación de este refactor; que MariaDB
# soporte o no `ON CONFLICT` queda como HALLAZGO a verificar en una fase
# posterior, nunca como arreglo silencioso aquí.
UPSERT_KIND: dict[str, str] = {
    "sqlite": "on_conflict",
    "mysql": "on_duplicate",
    "mariadb": "on_conflict",
    "postgresql": "on_conflict",
    "mssql": "merge",
    "oracle": "merge",
}

# Literales válidos de `upsert_kind`; validación del builder.
UPSERT_KINDS = ("on_conflict", "on_duplicate", "merge")

_STRATEGIES: dict[str, InsertStrategy] = {
    "sqlite": SQLITE_INSERT,
    "mysql": MYSQL_INSERT,
    "mariadb": MARIADB_INSERT,
    "postgresql": POSTGRES_INSERT,
    "mssql": MSSQL_INSERT,
    "oracle": ORACLE_INSERT,
}


def strategy_for(dialect: Engine | str) -> InsertStrategy:
    """Estrategia de INSERT del dialecto (normaliza `Engine` o su valor `str`)."""
    key = dialect.value if isinstance(dialect, Engine) else dialect
    try:
        return _STRATEGIES[key]
    except KeyError:
        raise ValueError(f"dialecto desconocido: {dialect!r}") from None


__all__ = [
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "UPSERT_KIND",
    "UPSERT_KINDS",
    "InsertStrategy",
    "strategy_for",
]
