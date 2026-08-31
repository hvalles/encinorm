"""Generación de archivos `.py` con modelos a partir de una tabla."""

import keyword
import re
from pathlib import Path

from .tables import columns_of
from .types import resolve_field_type

_INHERITED = ("id", "enabled", "created_at", "updated_at")

# Nombres que colisionarían con métodos de `Model`/pydantic o palabras reservadas
# SQL: al detectarlos se les añade `_` y se mapea con `name="columna"`.
_RESERVED = {
    # campos heredados de Model
    "id", "enabled", "created_at", "updated_at",
    # métodos ORM
    "insert", "update", "delete", "load", "search", "count", "paginate",
    "query", "validate", "add_reference", "create_table", "sync_schema",
    "batch_reference",
    # pydantic / Model internos
    "dict", "json", "copy", "model_construct", "model_dump", "model_fields",
    "model_config", "_table", "_db",
    # palabras reservadas SQL comunes
    "create", "select", "insert", "drop", "alter", "table", "index", "order",
    "group", "where", "join", "on", "primary", "key", "references", "default",
    "limit", "offset", "desc", "asc", "between", "like", "is", "in",
}

_DOMAIN_IMPORT = (
    "from encinorm.model.domain import (\n"
    "    STR_10, STR_15, STR_20, STR_30, STR_50, STR_100, STR_255, STR_500,\n"
    "    TEXT, INT, INT_POS, CURRENCY, FLOAT, FLOAT_POS, BOOL, DATE, DATETIME,\n"
    "    BLOB, JSON,\n"
    ")"
)


def _class_name(table: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", table)
    name = "".join(p.capitalize() for p in parts if p)
    if not name or name[0].isdigit() or keyword.iskeyword(name):
        name = "Model" + name
    return name


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _field_name(col_name: str) -> str:
    name = re.sub(r"[^0-9a-zA-Z_]", "_", col_name).strip("_").lower()
    if not name or name[0].isdigit() or keyword.iskeyword(name):
        name = "col_" + name
    if name in _RESERVED:
        name += "_"
    return name


async def generate_model(db, table: str, *, folder: str,
                         class_name: str | None = None) -> Path:
    """Genera `folder/<archivo>.py` con el `Model` de la tabla.

    Devuelve la ruta del archivo generado. Los tipos que coinciden con el
    vocabulario (`domain.py`) usan el preset; el resto usa `make_constraint(...)`.
    """
    cols = await columns_of(db, table)
    cls = class_name or _class_name(table)
    present = {c.name for c in cols}
    missing = [f for f in ("id", "enabled", "created_at", "updated_at") if f not in present]

    lines = [
        "from datetime import date, datetime",
        "",
        "from encinorm.model import Model, make_constraint",
        _DOMAIN_IMPORT,
        "",
        f"class {cls}(Model):",
        f'    _table = "{table}"',
    ]
    if missing:
        lines.append(f"    _fields_disabled = {missing!r}")

    pk_cols = [c for c in cols if c.primary_key]
    pk_fields = [_field_name(c.name) for c in pk_cols]
    if pk_fields and pk_fields != ["id"]:
        lines.append(f"    _primary_key = {tuple(pk_fields)!r}")

    for c in cols:
        if c.name in _INHERITED:
            continue
        fname = _field_name(c.name)
        type_expr = resolve_field_type(c)
        args = []
        if not c.nullable:
            args.append("required=True")
        if fname != c.name:
            args.append(f'name="{c.name}"')
        suffix = f"({', '.join(args)})" if args else "()"
        lines.append(f"    {fname}: {type_expr}{suffix}")
    lines.append("")

    path = Path(folder) / f"{_snake(cls)}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
