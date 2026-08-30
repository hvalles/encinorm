"""Mapeo inverso de tipos (DB -> datatype lógico -> preset/fallback)."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    raw_type: str
    datatype: str
    nullable: bool
    primary_key: bool = False
    max_length: int | None = None
    unsigned: bool = False


_STR_TYPES = {
    "varchar", "char", "character varying", "text", "clob", "string",
    "nvarchar", "nchar", "tinytext", "mediumtext", "longtext",
}
_BOOL_TYPES = {"bool", "boolean"}
_INT_TYPES = {
    "int", "integer", "bigint", "smallint", "tinyint", "mediumint",
    "serial", "bigserial", "smallserial",
}
_NUMERIC_TYPES = {"numeric", "decimal", "money"}
_FLOAT_TYPES = {"real", "float", "double", "double precision"}
_DATETIME_TYPES = {"datetime", "timestamp", "timestamptz", "timestamp with time zone"}
_DATE_TYPES = {"date"}
_BLOB_TYPES = {"blob", "bytea", "binary", "varbinary"}


def _normalize(raw_type: str) -> tuple[str, int | None, bool]:
    """Normaliza el tipo crudo del motor a `(datatype, max_length, unsigned)`."""
    t = (raw_type or "").strip().lower()
    m = re.search(r"\((\d+)", t)
    max_length = int(m.group(1)) if m else None
    unsigned = "unsigned" in t
    base = t.split("(")[0].replace(" unsigned", "").replace(" zerofill", "").strip()
    if base in _STR_TYPES:
        return "str", max_length, unsigned
    if base in _BOOL_TYPES:
        return "bool", None, unsigned
    if base in _INT_TYPES:
        if base == "tinyint" and max_length == 1:
            return "bool", None, unsigned       # TINYINT(1) -> bool (ambiguo)
        return "int", None, unsigned
    if base in _FLOAT_TYPES:
        return "float", None, unsigned
    if base in _NUMERIC_TYPES:
        return "numeric", None, unsigned
    if base in _DATETIME_TYPES:
        return "datetime", None, unsigned
    if base in _DATE_TYPES:
        return "date", None, unsigned
    if base in _BLOB_TYPES:
        return "blob", None, unsigned
    return "str", max_length, unsigned          # fallback conservador


# Clave (datatype, discriminador) -> preset del vocabulario.
_PRESET = {
    ("str", 10): "STR_10",
    ("str", 15): "STR_15",
    ("str", 20): "STR_20",
    ("str", 30): "STR_30",
    ("str", 50): "STR_50",
    ("str", 100): "STR_100",
    ("str", 255): "STR_255",
    ("str", 500): "STR_500",
    ("str", None): "TEXT",
    ("int", "pos"): "INT_POS",
    ("int", None): "INT",
    ("float", "pos"): "FLOAT_POS",
    ("float", None): "FLOAT",
    ("bool", None): "BOOL",
    ("numeric", None): "CURRENCY",
    ("datetime", None): "DATETIME",
    ("date", None): "DATE",
    ("blob", None): "BLOB",
}


def _preset_key(col: ColumnSpec):
    if col.datatype == "str":
        return ("str", col.max_length)
    if col.datatype in ("int", "float"):
        return (col.datatype, "pos" if col.unsigned else None)
    return (col.datatype, None)


def _make_constraint_expr(col: ColumnSpec) -> str:
    dt = col.datatype
    if dt == "str":
        if col.max_length:
            return f"make_constraint(str, max_length={col.max_length})"
        return "make_constraint(str)"
    if dt == "int":
        return "make_constraint(int, ge=0)" if col.unsigned else "make_constraint(int)"
    if dt == "float":
        return (
            'make_constraint(float, datatype="float", ge=0)'
            if col.unsigned
            else 'make_constraint(float, datatype="float")'
        )
    if dt == "numeric":
        return "make_constraint(float)"
    if dt == "bool":
        return "make_constraint(bool)"
    if dt == "datetime":
        return "make_constraint(datetime)"
    if dt == "date":
        return "make_constraint(date)"
    if dt == "blob":
        return "make_constraint(bytes)"
    return "make_constraint(str)"


def resolve_field_type(col: ColumnSpec) -> str:
    """Devuelve la expresión Python que tipa el campo.

    Si el tipo coincide con un preset del vocabulario, devuelve el nombre del
    preset; si **no**, devuelve un `make_constraint(...)` explícito.
    """
    key = _preset_key(col)
    if key in _PRESET:
        return _PRESET[key]
    return _make_constraint_expr(col)
