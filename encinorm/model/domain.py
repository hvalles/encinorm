"""Vocabulario de tipos de dato genéricos (presets de `make_constraint`).

Conjunto de uso común reutilizado por el codegen (`encinorm.introspection`).
Si el tipo de una columna no coincide con ninguno de estos presets, el generador
emite un `make_constraint(...)` directo al campo.
"""

from datetime import date, datetime
from decimal import Decimal

from .constraint import make_constraint


def _coerce_datetime(v):
    """Acepta `datetime` o string ISO; devuelve `datetime` (normaliza)."""
    if v is None or isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    raise ValueError("datetime inválido")


STR_10 = make_constraint(str, max_length=10)
STR_15 = make_constraint(str, max_length=15)
STR_20 = make_constraint(str, max_length=20)
STR_30 = make_constraint(str, max_length=30)
STR_50 = make_constraint(str, max_length=50)
STR_100 = make_constraint(str, max_length=100)
STR_255 = make_constraint(str, max_length=255)
STR_500 = make_constraint(str, max_length=500)
TEXT = make_constraint(str)                       # sin límite de longitud
INT = make_constraint(int)
INT_POS = make_constraint(int, ge=0)              # no negativo
CURRENCY = make_constraint(float, ge=0)           # datatype "numeric"
FLOAT = make_constraint(float, datatype="float")
FLOAT_POS = make_constraint(float, datatype="float", ge=0)
BOOL = make_constraint(bool)
DATE = make_constraint(date)
DATETIME = make_constraint(datetime, validators=(_coerce_datetime,))
BLOB = make_constraint(bytes)                     # datatype "blob"
DECIMAL = make_constraint(Decimal)                # datatype "numeric" (dinero exacto)
JSON = make_constraint(dict, datatype="json")     # dict | None -> columna JSON

__all__ = [
    "STR_10",
    "STR_15",
    "STR_20",
    "STR_30",
    "STR_50",
    "STR_100",
    "STR_255",
    "STR_500",
    "TEXT",
    "INT",
    "INT_POS",
    "CURRENCY",
    "FLOAT",
    "FLOAT_POS",
    "BOOL",
    "DATE",
    "DATETIME",
    "BLOB",
    "DECIMAL",
    "JSON",
]
