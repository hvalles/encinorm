"""Construcción DML compartida por los seis dialectos.

Este es el ÚNICO punto donde se arma el INSERT/UPDATE/DELETE del camino público.
El módulo interpola identificadores A PROPÓSITO —frontera de confianza
documentada aquí—: la defensa es `check_identifier`, aplicado a la tabla, a cada
columna, a cada columna de conflicto y al `schema` ANTES de construir la cadena
SQL. No importa drivers ni `Db`: solo stdlib + `Query` + el checker, para no
crear ciclos ni romper el contrato de importación diferida.

El SQL es byte-idéntico al que producían los adaptadores: los separadores sin
espacio de la lista de columnas (`a,b`), el `", "` del `ON CONFLICT` de
PostgreSQL y el `AS`/sin-`AS` del `MERGE` están pinados por los tests.
"""

from ..query import Query
from .identifiers import check_identifier
from .strategies import InsertStrategy


def _qualified(table: str, schema: str | None) -> str:
    """Valida y compone `tabla` o `esquema.tabla`. Nunca relaja la allowlist."""
    table = check_identifier(table, "tabla")
    if schema is None:
        return table
    return f"{check_identifier(schema, 'esquema')}.{table}"


def _placeholders(count: int) -> str:
    return ",".join(f"{{{i}}}" for i in range(count))


def _merge_sql(
    qualified: str,
    strategy: InsertStrategy,
    columns: list,
    conflict_cols: list,
    set_sql: str,
) -> str:
    """Render del `MERGE INTO` compartido por `build_insert` y `build_upsert`."""
    alias = f"{strategy.merge_alias_keyword} " if strategy.merge_alias_keyword else ""
    src = ", ".join(f"{{{i}}} AS {c}" for i, c in enumerate(columns))
    on = " AND ".join(f"dst.{c} = src.{c}" for c in conflict_cols)
    ins_cols = ",".join(columns)
    ins_vals = ",".join(f"src.{c}" for c in columns)
    return (
        f"MERGE INTO {qualified} {alias}dst "
        f"USING (SELECT {src}) {alias}src "
        f"ON ({on}) "
        f"WHEN MATCHED THEN UPDATE SET {set_sql} "
        f"WHEN NOT MATCHED THEN INSERT ({ins_cols}) VALUES ({ins_vals})"
    )


def build_insert(
    table: str,
    data: dict,
    *,
    strategy: InsertStrategy,
    conflict: list[str] | None = None,
    replace: bool = False,
    ignore_duplicated: bool = False,
    schema: str | None = None,
) -> Query:
    """Construye el INSERT del dialecto descrito por `strategy`."""
    qualified = _qualified(table, schema)
    columns = list(data.keys())
    values = list(data.values())
    for col in columns:
        check_identifier(col, "columna")
    if conflict is not None:
        for col in conflict:
            check_identifier(col, "columna de conflicto")

    if strategy.kind == "prefix":
        keyword = "INSERT"
        if replace:
            keyword = strategy.replace_prefix
        elif ignore_duplicated:
            keyword = strategy.ignore_prefix
        sql = (
            f"{keyword} INTO {qualified} ({','.join(columns)}) "
            f"VALUES ({_placeholders(len(columns))})"
        )
    elif strategy.kind == "suffix":
        sql = (
            f"INSERT INTO {qualified} ({','.join(columns)}) VALUES ({_placeholders(len(columns))})"
        )
        if replace:
            # PostgreSQL exige un objetivo de conflicto para DO UPDATE; se usa el
            # `conflict` explícito, o la primera columna (PK) por defecto.
            target = ", ".join(conflict) if conflict else (columns[0] if columns else "id")
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)
            sql += f" ON CONFLICT ({target}) DO UPDATE SET {updates}"
        elif ignore_duplicated:
            sql += " ON CONFLICT DO NOTHING"
    else:  # merge
        if replace:
            conflict_cols = list(conflict) if conflict else ([columns[0]] if columns else ["id"])
            set_sql = ", ".join(f"dst.{c} = src.{c}" for c in columns)
            sql = _merge_sql(qualified, strategy, columns, conflict_cols, set_sql)
        else:
            sql = (
                f"INSERT INTO {qualified} ({','.join(columns)}) "
                f"VALUES ({_placeholders(len(columns))})"
            )
            if strategy.returning_id and "id" not in columns:
                sql += " RETURNING id INTO :ret_id"

    return Query(
        sql,
        values,
        ignore_duplicated=bool(
            strategy.carries_ignore_duplicated and ignore_duplicated and not replace
        ),
    )


def build_update(table: str, keys: dict, values: dict, *, schema: str | None = None) -> Query:
    """Construye `UPDATE tabla SET ... WHERE ...`."""
    qualified = _qualified(table, schema)
    set_cols = list(values.keys())
    set_vals = list(values.values())
    key_cols = list(keys.keys())
    key_vals = list(keys.values())
    for col in set_cols:
        check_identifier(col, "columna")
    for col in key_cols:
        check_identifier(col, "columna")

    set_clause = ",".join(f"{col} = {{{i}}}" for i, col in enumerate(set_cols))
    offset = len(set_cols)
    where = " AND ".join(f"{col} = {{{offset + i}}}" for i, col in enumerate(key_cols))
    sql = f"UPDATE {qualified} SET {set_clause} WHERE {where}"
    return Query(sql, set_vals + key_vals)


def build_delete(table: str, keys: dict, *, schema: str | None = None) -> Query:
    """Construye `DELETE FROM tabla WHERE ...`."""
    qualified = _qualified(table, schema)
    columns = list(keys.keys())
    values = list(keys.values())
    for col in columns:
        check_identifier(col, "columna")

    where = " AND ".join(f"{col} = {{{i}}}" for i, col in enumerate(columns))
    sql = f"DELETE FROM {qualified} WHERE {where}"
    return Query(sql, values)


__all__ = ["build_delete", "build_insert", "build_update"]
