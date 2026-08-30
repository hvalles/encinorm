from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    datatype: str = "str"          # int, bool, str, datetime, date, numeric, blob, float
    name: str | None = None        # nombre de columna en la BD (si difiere del atributo)
