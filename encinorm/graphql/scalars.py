"""Mapeo de datatype lógico → tipo GraphQL/Strawberry."""

from datetime import date, datetime

import strawberry

DATATYPE_TO_TYPE = {
    "str": str,
    "int": int,
    "bool": bool,
    "tinyint": bool,
    "numeric": float,
    "decimal": float,
    "float": float,
    "datetime": datetime,
    "date": date,
    "blob": str,                      # binario como string (base64/texto)
    "json": strawberry.scalars.JSON,
}
