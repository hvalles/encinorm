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


@dataclass(frozen=True)
class DialectLimits:
    """Techos de parámetros y filas de un dialecto, con procedencia escrita.

    `max_params` acota los placeholders ligados por sentencia; `max_rows` acota
    las filas de un multi-row `VALUES`. `provenance` dice de dónde sale el número
    y si está verificado empíricamente: sin procedencia el número sería una
    suposición sin dueño. La sonda manual del job `engine-heavy` (02-05) refina
    los valores marcados como no verificados.
    """

    max_params: int
    max_rows: int
    provenance: str


LIMITS: dict[str, DialectLimits] = {
    "sqlite": DialectLimits(
        max_params=32766,
        max_rows=1000,
        provenance=(
            "SQLITE_MAX_VARIABLE_NUMBER verificado empíricamente (SQLite 3.50.4): "
            "32766 acepta, 32768 lanza 'too many SQL variables'; un multi-VALUES de "
            "1000 filas (2000 parámetros) fue aceptado."
        ),
    ),
    "postgresql": DialectLimits(
        max_params=32767,
        max_rows=1000,
        provenance=(
            "asyncpg 0.31.0 rechaza más de 32767 argumentos "
            "(protocol/prepared_stmt.pyx:130-132); verificado en la fuente instalada "
            "del driver. max_rows=1000 es discreción del planner (no verificado)."
        ),
    ),
    "mysql": DialectLimits(
        max_params=65535,
        max_rows=1000,
        provenance=(
            "Límite de protocolo para el contador de placeholders (65535); NO "
            "verificado empíricamente (sonda pendiente en el job engine-heavy de 02-05)."
        ),
    ),
    "mariadb": DialectLimits(
        max_params=65535,
        max_rows=1000,
        provenance=(
            "Mismo protocolo que MySQL (65535 placeholders); NO verificado "
            "empíricamente (sonda pendiente en el job engine-heavy de 02-05)."
        ),
    ),
    "mssql": DialectLimits(
        max_params=2100,
        max_rows=1000,
        provenance=(
            "Especificación oficial de capacidad de SQL Server: 2100 parámetros para "
            "procedimientos y UDF; el techo ad-hoc NO está verificado empíricamente "
            "(sonda pendiente en el job engine-heavy de 02-05)."
        ),
    ),
    "oracle": DialectLimits(
        max_params=65535,
        max_rows=1000,
        provenance=(
            "Techo documentado de binds por sentencia (65535); NO verificado "
            "empíricamente (sonda pendiente en el job engine-heavy de 02-05)."
        ),
    ),
}

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
    "LIMITS",
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "UPSERT_KIND",
    "UPSERT_KINDS",
    "DialectLimits",
    "InsertStrategy",
    "strategy_for",
]
