"""Copia de datos entre bases de datos, en el mismo motor o cross-engine.

Traduce los valores según el datatype lógico de cada columna (introspección) al
formato que espera el motor destino, y opcionalmente crea el esquema destino.
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from .engine import Engine, engine_of
from .query import Query


def _auto_pk_name(columns) -> str | None:
    """Devuelve el nombre de la PK auto-incremental (una única columna `int`), o `None`."""
    pk = [c for c in columns if c.primary_key]
    if len(pk) == 1 and pk[0].datatype == "int":
        return pk[0].name
    return None


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

    auto_pk = _auto_pk_name(columns)
    pk_names = [c.name for c in columns if c.primary_key]
    lines = []
    for col in columns:
        if col.name == auto_pk:
            lines.append(f"  {col.name} {DDL_MAP[dialect]['pk']}")
        else:
            lines.append(f"  {col.name} {ddl_type(col.datatype, dialect)}")
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
        try:
            await db.execute(Query(
                f"SET session_replication_role = {'origin' if enabled else 'replica'}", []
            ))
        except Exception:
            pass


async def copy_table(src, dst, table: str, *, create: bool = False,
                     truncate: bool = False, preserve_ids: bool = True) -> int:
    """Copia una tabla completa del origen al destino. Devuelve filas copiadas."""
    from .introspection import columns_of

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
    async with dst.transaction():
        if truncate:
            await dst.execute(Query(f"DELETE FROM {table}", []))
        for row in rows:
            data = {}
            for col in target_cols:
                canonical = _normalize_value(row[col.name], col.datatype)
                data[col.name] = _serialize_for_target(canonical, col.datatype, dialect)
            await dst.execute(dst.insert(table, data))
            total += 1
    return total


async def copy_database(src, dst, tables: list[str] | None = None, *,
                        create: bool = False, truncate: bool = False,
                        preserve_ids: bool = True, disable_fk: bool = True) -> dict[str, int]:
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
                src, dst, table,
                create=create, truncate=truncate, preserve_ids=preserve_ids,
            )
    finally:
        if disable_fk:
            await _set_fk(dst, True)
    return result
