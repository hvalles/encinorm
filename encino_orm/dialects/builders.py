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
from .strategies import UPSERT_KINDS, InsertStrategy


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
    update_cols: list | None = None,
) -> str:
    """Render del `MERGE INTO` compartido por `build_insert` y `build_upsert`."""
    # El `src` derivado se construye SOLO con las columnas de `data`; en un modelo
    # de PK autoincremental la PK `id` está excluida, así que `ON (dst.id =
    # src.id)` referenciaría una columna inexistente (MSSQL 207 / ORA-00904). Se
    # falla CERRADO en este punto único (compartido por `build_insert` y
    # `build_upsert`) en vez de derivar un default silencioso: el llamador debe
    # pasar `conflict=` con una columna de datos.
    if not conflict_cols:
        raise ValueError(
            "el MERGE requiere un objetivo de conflicto NO vacío; pasa "
            "conflict=[...] con al menos una columna presente en los datos"
        )
    missing = [c for c in conflict_cols if c not in columns]
    if missing:
        raise ValueError(
            f"conflicto {missing} no está en el INSERT; en MERGE el objetivo "
            "debe ser una columna presente en los datos (pasa conflict=...)"
        )
    # `update_cols` solo se comprueba cuando el SET referencia `src.<col>`
    # (`update_values is None`); si el SET usa valores ligados no toca `src`.
    if update_cols is not None:
        missing_upd = [c for c in update_cols if c not in columns]
        if missing_upd:
            raise ValueError(
                f"columna(s) de actualización {missing_upd} no está(n) en el INSERT; "
                "en MERGE el SET `dst.<col> = src.<col>` requiere la columna en los datos"
            )
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
            # `conflict` explícito o, en su defecto, la PRIMERA COLUMNA DEL INSERT,
            # que NO es necesariamente la PK: el llamador (p. ej. `Model.insert`)
            # debe pasar `conflict`. Ese default solo lo alcanzan los llamadores
            # DIRECTOS del adaptador; `Model.insert` ya pasa `conflict` para
            # `suffix` + `replace`.
            target = ", ".join(conflict) if conflict else (columns[0] if columns else "id")
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns)
            sql += f" ON CONFLICT ({target}) DO UPDATE SET {updates}"
        elif ignore_duplicated:
            sql += " ON CONFLICT DO NOTHING"
    else:  # merge
        if replace:
            # El objetivo de conflicto debe ser una columna PRESENTE en el `src`
            # derivado (que solo contiene las columnas de `data`). `Model.insert`
            # deja `conflict=None` en `merge` (MSSQL/Oracle) deliberadamente: la PK
            # autoincremental `id` no está en `src`, así que pasar `["id"]` produciría
            # `ON (dst.id = src.id)` sobre una columna inexistente (MSSQL 4104 /
            # ORA-00904). El fallback a `columns[0]` es ejecutable en MSSQL pero
            # semánticamente incorrecto (actualiza la columna del `ON`); en Oracle ni
            # siquiera es ejecutable (ORA-38104), defecto preexistente documentado.
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


def build_upsert(
    table: str,
    data: dict,
    *,
    strategy: InsertStrategy,
    upsert_kind: str,
    conflict: list[str],
    update_cols: list[str],
    update_values: list | None = None,
    schema: str | None = None,
) -> Query:
    """Construye la cláusula de conflicto de un UPSERT (la que tenía `Model.upsert`).

    `upsert_kind` ∈ `UPSERT_KINDS`. El separador del objetivo de conflicto en
    `on_conflict` es `','.join(conflict)` **sin espacio** (idéntico al
    `Model.upsert` previo, `model.py:624`), deliberadamente distinto del `", "`
    que usa el `ON CONFLICT` de `build_insert` (postgresql.py:170). `excluded` va
    en minúsculas, también por byte-identidad. Nunca emite `RETURNING`.
    """
    if upsert_kind not in UPSERT_KINDS:
        raise ValueError(f"upsert_kind inválido: {upsert_kind!r}")

    qualified = _qualified(table, schema)
    cols = list(data.keys())
    insert_vals = list(data.values())
    for col in cols:
        check_identifier(col, "columna")
    for col in conflict:
        check_identifier(col, "columna de conflicto")
    for col in update_cols:
        check_identifier(col, "columna de actualización")

    placeholders = _placeholders(len(cols))
    offset = len(insert_vals)

    if upsert_kind == "on_conflict":
        if update_values is None:
            set_sql = ", ".join(f"{c} = excluded.{c}" for c in update_cols)
        else:
            set_sql = ", ".join(f"{c} = {{{offset + i}}}" for i, c in enumerate(update_cols))
        sql = (
            f"INSERT INTO {qualified} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({','.join(conflict)}) DO UPDATE SET {set_sql}"
        )
    elif upsert_kind == "on_duplicate":
        if update_values is None:
            set_sql = ", ".join(f"{c} = VALUES({c})" for c in update_cols)
        else:
            set_sql = ", ".join(f"{c} = {{{offset + i}}}" for i, c in enumerate(update_cols))
        sql = (
            f"INSERT INTO {qualified} ({','.join(cols)}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {set_sql}"
        )
    else:  # merge
        if update_values is None:
            set_sql = ", ".join(f"dst.{c} = src.{c}" for c in update_cols)
        else:
            set_sql = ", ".join(f"dst.{c} = {{{offset + i}}}" for i, c in enumerate(update_cols))
        sql = _merge_sql(
            qualified,
            strategy,
            cols,
            list(conflict),
            set_sql,
            update_cols=update_cols if update_values is None else None,
        )

    return Query(sql, insert_vals + list(update_values or []))


__all__ = ["build_delete", "build_insert", "build_update", "build_upsert"]
