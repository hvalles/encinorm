"""Copia de datos entre bases de datos, en el mismo motor o cross-engine.

Traduce los valores según el datatype lógico de cada columna (introspección) al
formato que espera el motor destino, y opcionalmente crea el esquema destino.
"""

import contextlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from .dialects import build_insert, build_multi_insert, strategy_for
from .dialects.identifiers import check_identifier
from .engine import Engine, engine_of
from .query import Query


def _auto_pk_name(columns) -> str | None:
    """Devuelve el nombre de la PK auto-incremental (una única columna `int`), o `None`."""
    pk = [c for c in columns if c.primary_key]
    if len(pk) == 1 and pk[0].datatype == "int":
        return pk[0].name
    return None


def batch_size(n_columns: int, max_params: int, max_rows: int) -> int:
    """Filas por lote del camino multi-VALUES de `copy_table`.

    `max_params // n_columns` es la capacidad de una fila en parámetros, techada
    por `max_rows`. Puede devolver 0 cuando el destino no admite NI UNA fila con
    ese número de columnas (más columnas que `max_params`): el llamador debe
    degradar al insert de fila única (LR-01). Vive en producción para que el
    canario de `tests/test_benchmarks.py` mida ESTE código y no una copia literal
    (LR-02).
    """
    return min(max_params // max(n_columns, 1), max_rows)


def _default_row_sql(table: str, auto_pk: str, dialect: str) -> str:
    """SQL de inserción de una fila con TODOS los valores por defecto.

    Solo se usa cuando la copia NO tiene columnas de datos (`target_cols == []`:
    una tabla con únicamente la PK autoincremental y `preserve_ids=False`). El
    `INSERT INTO t () VALUES ()` no es válido en SQLite/MSSQL/Oracle y el
    multi-VALUES sin columnas no existe en ningún dialecto (MR-01); Oracle no
    tiene `DEFAULT VALUES`, así que inserta el `DEFAULT` explícito en la columna
    de identidad (única columna garantizada en esta rama).
    """
    table = check_identifier(table, "tabla")
    if dialect in (Engine.SQLITE, Engine.POSTGRESQL, Engine.MSSQL):
        return f"INSERT INTO {table} DEFAULT VALUES"
    if dialect in (Engine.MYSQL, Engine.MARIADB):
        return f"INSERT INTO {table} () VALUES ()"
    if dialect == Engine.ORACLE:
        return f"INSERT INTO {table} ({check_identifier(auto_pk, 'columna')}) VALUES (DEFAULT)"
    raise ValueError(f"motor sin forma de fila de solo defaults: {dialect!r}")


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _normalize_value(value, datatype: str):
    """Lleva un valor crudo del origen a un tipo Python canónico por `datatype`."""
    if value is None:
        return None
    if datatype == "str":
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        return str(value)
    if datatype == "int":
        return int(value)
    if datatype == "float":
        return float(value)
    if datatype == "bool":
        return bool(value)
    if datatype in ("numeric", "decimal"):
        return value if isinstance(value, Decimal) else Decimal(str(value))
    if datatype == "date":
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    if datatype == "datetime":
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if datatype == "blob":
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        return bytes(value)
    if datatype == "json":
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value
    return value


def _serialize_for_target(value, datatype: str, dialect: str):
    """Serializa un valor canónico al formato que acepta el driver del destino."""
    if value is None:
        return None
    if datatype == "bool":
        return int(value) if dialect in (Engine.SQLITE, Engine.MYSQL) else bool(value)
    if datatype in ("numeric", "decimal"):
        return str(value) if dialect == Engine.SQLITE else value
    if datatype == "date":
        return value.isoformat() if dialect == Engine.SQLITE else value
    if datatype == "datetime":
        if dialect == Engine.SQLITE:
            return _as_naive_utc(value).isoformat(sep=" ")
        if dialect == Engine.MYSQL:
            return _as_naive_utc(value)
        return value
    if datatype == "json":
        if dialect == Engine.POSTGRESQL:
            return value
        return json.dumps(value, default=str) if isinstance(value, (dict, list)) else value
    return value


def build_ddl(table: str, columns, dialect: str) -> str:
    """Genera el ``CREATE TABLE`` destino a partir de las columnas introspeccionadas."""
    from .model.types import DDL_MAP, ddl_type

    if dialect not in DDL_MAP:
        raise ValueError(f"motor no soportado: {dialect!r}")

    table = check_identifier(table, "tabla")

    auto_pk = _auto_pk_name(columns)
    pk_names = [check_identifier(c.name, "columna") for c in columns if c.primary_key]
    lines = []
    for col in columns:
        name = check_identifier(col.name, "columna")
        if col.name == auto_pk:
            lines.append(f"  {name} {DDL_MAP[dialect]['pk']}")
        else:
            lines.append(f"  {name} {ddl_type(col.datatype, dialect)}")
    if pk_names and auto_pk is None:
        lines.append(f"  PRIMARY KEY ({', '.join(pk_names)})")
    body = ",\n".join(lines)
    return f"CREATE TABLE {table} (\n{body}\n)"


async def _set_fk(db, enabled: bool):
    """Desactiva/restaura la verificación de FK en el destino (best-effort)."""
    engine = engine_of(db)
    if engine is Engine.SQLITE:
        await db.execute(Query(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}", []))
    elif engine is Engine.MYSQL:
        await db.execute(Query(f"SET FOREIGN_KEY_CHECKS={'1' if enabled else '0'}", []))
    elif engine is Engine.POSTGRESQL:
        # best-effort: cambiar el rol de replicación puede requerir superusuario
        with contextlib.suppress(Exception):
            await db.execute(
                Query(f"SET session_replication_role = {'origin' if enabled else 'replica'}", [])
            )


async def copy_table(
    src, dst, table: str, *, create: bool = False, truncate: bool = False, preserve_ids: bool = True
) -> int:
    """Copia una tabla completa del origen al destino. Devuelve filas copiadas."""
    from .introspection import columns_of

    table = check_identifier(table, "tabla")
    columns = await columns_of(src, table)
    if not columns:
        raise ValueError(f"tabla {table!r} inexistente o sin columnas")

    dialect = getattr(dst, "dialect", "sqlite")
    if create:
        await dst.execute(Query(build_ddl(table, columns, dialect), []))

    auto_pk = _auto_pk_name(columns) if not preserve_ids else None
    target_cols = [c for c in columns if c.name != auto_pk]

    rows = await src.fetch_all(Query(f"SELECT * FROM {table}", []))
    total = 0

    def _serialize(row) -> dict:
        data = {}
        for col in target_cols:
            canonical = _normalize_value(row[col.name], col.datatype)
            data[col.name] = _serialize_for_target(canonical, col.datatype, dialect)
        return data

    async with dst.transaction():
        if truncate:
            await dst.execute(Query(f"DELETE FROM {table}", []))
        if not target_cols:
            # Sin columnas de datos (solo PK autoincremental y preserve_ids=False):
            # no hay valores que ligar; se inserta una fila de DEFAULTs por fila
            # origen con SQL específico de dialecto (MR-01). La rama solo es
            # alcanzable con PK autoincremental presente, pero se resuelve el caso
            # imposible explícito (guarda runtime que a la vez estrecha el tipo).
            if auto_pk is None:
                raise RuntimeError(
                    "camino de fila default alcanzado sin PK autoincremental (invariante roto)"
                )
            default_qry = Query(_default_row_sql(table, auto_pk, dialect), [])
            for _row in rows:
                await dst.execute(default_qry)
                total += 1
        else:
            max_params = getattr(dst, "MAX_PARAMS", 500)
            max_rows = getattr(dst, "MAX_ROWS", 1000)
            chunk = batch_size(len(target_cols), max_params, max_rows)
            if chunk == 0:
                # Más columnas de datos que el techo de parámetros del destino
                # (LR-01): ni una fila cabe en lote. Degrada al insert de fila
                # única, válido en los seis dialectos; es el límite respetándose
                # a sí mismo (una fila por sentencia).
                for row in rows:
                    await dst.execute(
                        build_insert(table, _serialize(row), strategy=strategy_for(dialect))
                    )
                    total += 1
            else:
                batch = []
                for row in rows:
                    batch.append(_serialize(row))
                    if len(batch) >= chunk:
                        # La lista de columnas se toma de la PRIMERA fila del lote y es
                        # estable dentro del lote: todas las filas serializan el mismo
                        # `target_cols`, así que `batch` comparte `keys()`.
                        qry = build_multi_insert(
                            table,
                            list(batch[0].keys()),
                            [list(d.values()) for d in batch],
                            strategy=strategy_for(dialect),
                        )
                        await dst.execute(qry)
                        total += len(batch)
                        batch = []
                if batch:
                    qry = build_multi_insert(
                        table,
                        list(batch[0].keys()),
                        [list(d.values()) for d in batch],
                        strategy=strategy_for(dialect),
                    )
                    await dst.execute(qry)
                    total += len(batch)
    return total


async def copy_database(
    src,
    dst,
    tables: list[str] | None = None,
    *,
    create: bool = False,
    truncate: bool = False,
    preserve_ids: bool = True,
    disable_fk: bool = True,
) -> dict[str, int]:
    """Copia todas (o una selección de) las tablas. Devuelve ``{tabla: filas}``."""
    from .introspection import list_tables

    if tables is None:
        tables = [r["name"] for r in (await list_tables(src)).rows]

    result = {}
    if disable_fk:
        await _set_fk(dst, False)
    try:
        for table in tables:
            result[table] = await copy_table(
                src,
                dst,
                table,
                create=create,
                truncate=truncate,
                preserve_ids=preserve_ids,
            )
    finally:
        if disable_fk:
            await _set_fk(dst, True)
    return result
