"""Traducción de tipos lógicos a DDL por motor de base de datos."""

import re
import types as _types
from datetime import date, datetime
from decimal import Decimal
from typing import Union, get_args, get_origin


def _base_type(annotation):
    if hasattr(annotation, "__metadata__"):  # Annotated[...]
        annotation = get_args(annotation)[0]
    origin = get_origin(annotation)
    if origin is None:
        return annotation
    args = get_args(annotation)
    if origin is Union or origin is _types.UnionType:
        non_none = [a for a in args if a is not type(None)]
        return non_none[0] if non_none else args[0]
    return args[0]


# tipo Python -> datatype lógico (inferencia por defecto)
PY_TYPE_TO_DATATYPE = {
    str: "str",
    int: "int",
    bool: "bool",
    float: "numeric",
    Decimal: "decimal",
    datetime: "datetime",
    date: "date",
    bytes: "blob",
    dict: "json",
    list: "json",
}


# datatype lógico -> DDL por motor
DDL_MAP = {
    "sqlite": {
        "pk": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "str": "TEXT",
        "int": "INTEGER",
        "bool": "INTEGER",
        "tinyint": "INTEGER",
        "datetime": "TEXT",
        "date": "TEXT",
        "numeric": "REAL",
        "decimal": "TEXT",
        "float": "REAL",
        "blob": "BLOB",
        "json": "TEXT",
    },
    "mysql": {
        "pk": "INT AUTO_INCREMENT PRIMARY KEY",
        "str": "VARCHAR(255)",
        "int": "INT",
        "bool": "TINYINT(1)",
        "tinyint": "TINYINT(1)",
        "datetime": "DATETIME",
        "date": "DATE",
        "numeric": "DECIMAL(10,2)",
        "decimal": "DECIMAL(10,2)",
        "float": "FLOAT",
        "blob": "BLOB",
        "json": "JSON",
    },
    "postgres": {
        "pk": "SERIAL PRIMARY KEY",
        "str": "TEXT",
        "int": "INTEGER",
        "bool": "BOOLEAN",
        "tinyint": "SMALLINT",
        "datetime": "TIMESTAMPTZ",
        "date": "DATE",
        "numeric": "NUMERIC",
        "decimal": "NUMERIC",
        "float": "DOUBLE PRECISION",
        "blob": "BYTEA",
        "json": "JSONB",
    },
}


def ddl_type(datatype: str, engine: str = "sqlite") -> str:
    """Traduce un datatype lógico a su DDL para el motor indicado."""
    table = DDL_MAP.get(engine)
    if table is None:
        raise ValueError(f"motor no soportado: {engine!r}")
    if datatype not in table:
        raise ValueError(f"datatype no soportado para {engine!r}: {datatype!r}")
    return table[datatype]


def _field_datatype(model_class, field: str, info) -> str:
    if field == "enabled":
        return "bool"
    if field in ("created_at", "updated_at"):
        return "datetime"
    for meta in getattr(info, "metadata", None) or []:
        datatype = getattr(meta, "datatype", None)
        if datatype:
            return datatype
    base = _base_type(info.annotation)
    return PY_TYPE_TO_DATATYPE.get(base, "str")


def to_ddl(model_class, engine: str = "sqlite") -> str:
    """Genera la sentencia ``CREATE TABLE`` a partir de un ``Model``.

    Recorre ``_column_map()`` (respetando ``_fields_disabled`` y ``Column.name``)
    y traduce cada campo a su DDL usando ``DDL_MAP``. Además, genera cláusulas
    ``FOREIGN KEY ... ON DELETE`` a partir de ``_references_def`` con ``on_delete``.
    """
    table = DDL_MAP.get(engine)
    if table is None:
        raise ValueError(f"motor no soportado: {engine!r}")

    _ON_DELETE = {"cascade": "CASCADE", "set_null": "SET NULL", "restrict": "RESTRICT"}

    pk_fields = model_class._pk_fields()
    auto = model_class._is_auto_pk()

    lines = []
    for field, col in model_class._column_map().items():
        if auto and field == "id":
            lines.append(f"  {col} {table['pk']}")
            continue
        dt = _field_datatype(model_class, field, model_class.model_fields[field])
        if dt not in table:
            raise ValueError(f"datatype no soportado para {engine!r}: {dt!r}")
        lines.append(f"  {col} {table[dt]}")

    if not auto:
        pk_cols = [model_class._col(f) for f in pk_fields]
        lines.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

    for spec in getattr(model_class, "_references_def", {}).values():
        on_delete = spec.get("on_delete")
        if not on_delete:
            continue
        action = _ON_DELETE.get(on_delete)
        if action is None:
            continue
        remote = spec["model"]
        local_cols = [model_class._col(local) for local in spec["match_keys"].values()]
        remote_cols = [remote._col(r) for r in spec["match_keys"].keys()]
        lines.append(
            f"  FOREIGN KEY ({', '.join(local_cols)}) "
            f"REFERENCES {remote._table} ({', '.join(remote_cols)}) ON DELETE {action}"
        )

    body = ",\n".join(lines)
    return f"CREATE TABLE {model_class._table} (\n{body}\n)"


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def indexes_ddl(model_class, engine: str = "sqlite") -> list[tuple[str, str]]:
    """Genera las sentencias ``CREATE [UNIQUE] INDEX`` de un modelo.

    Devuelve una lista de tuplas ``(nombre, sql)`` a partir de ``_indexes``.
    Cada columna puede ser un ``str`` (orden por defecto) o una tupla
    ``(nombre, "ASC" | "DESC")``. Los nombres se resuelven contra ``_column_map()``.
    """
    col_map = model_class._column_map()
    if_not_exists = "" if engine == "mysql" else "IF NOT EXISTS "
    result = []
    for idx in getattr(model_class, "_indexes", []):
        rendered = []
        for spec in idx.columns:
            if isinstance(spec, (tuple, list)):
                if len(spec) != 2:
                    raise ValueError(f"especificación de columna inválida: {spec!r}")
                col, direction = spec
                direction = str(direction).upper()
                if direction not in ("ASC", "DESC"):
                    raise ValueError(f"dirección de índice inválida: {direction!r}")
                rendered.append(f"{col_map.get(col, col)} {direction}")
            else:
                rendered.append(col_map.get(spec, spec))
        name = idx.name or f"idx_{model_class._table}_{'_'.join(rendered)}"
        name = name.replace(" ", "_")
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(f"nombre de índice inválido: {name!r}")
        unique = "UNIQUE " if idx.unique else ""
        sql = (
            f"CREATE {unique}INDEX {if_not_exists}{name} "
            f"ON {model_class._table} ({', '.join(rendered)})"
        )
        result.append((name, sql))
    return result
