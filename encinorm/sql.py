"""Registro de funciones SQL portables (`db.fn.*`) y convención de días de la semana."""

from enum import IntEnum

from .engine import Engine, engine_of


class Weekday(IntEnum):
    """Día de la semana, convención ISO: 0=lunes … 6=domingo."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


_UNITS = ("second", "minute", "hour", "day", "week", "month", "year")


class SqlFunctions:
    """Funciones SQL traducidas al dialecto del motor (vía `db.fn.*`).

    Devuelven **fragmentos SQL** (texto de confianza) para incrustar en `Query`
    o `Filter.raw`, no valores a enlazar:

    ```python
    await db.fetch_all(Query(f"SELECT * FROM t WHERE creado > {db.fn.now()}", []))
    ```
    """

    def __init__(self, dialect):
        self._engine = engine_of(dialect)

    # --- temporales ---
    def now(self) -> str:
        if self._engine is Engine.SQLITE:
            return "datetime('now')"
        if self._engine is Engine.MYSQL:
            return "NOW()"
        return "now()"

    def date_add(self, column: str, amount, unit: str = "day") -> str:
        return self._date_arith(column, amount, unit, add=True)

    def date_sub(self, column: str, amount, unit: str = "day") -> str:
        return self._date_arith(column, amount, unit, add=False)

    def _date_arith(self, column, amount, unit, add):
        self._check_unit(unit)
        if self._engine is Engine.SQLITE:
            sign = "+" if add else "-"
            return f"datetime({column}, '{sign}{amount} {unit}')"
        if self._engine is Engine.MYSQL:
            fn = "DATE_ADD" if add else "DATE_SUB"
            return f"{fn}({column}, INTERVAL {amount} {unit.upper()})"
        op = "+" if add else "-"
        return f"{column} {op} INTERVAL '{amount} {unit}'"

    # --- partes de fecha ---
    def year(self, column) -> str:
        return self._date_part(column, "year")

    def month(self, column) -> str:
        return self._date_part(column, "month")

    def day(self, column) -> str:
        return self._date_part(column, "day")

    def hour(self, column) -> str:
        return self._date_part(column, "hour")

    def minute(self, column) -> str:
        return self._date_part(column, "minute")

    def second(self, column) -> str:
        return self._date_part(column, "second")

    def weekday(self, column) -> str:
        """Día de la semana normalizado a `Weekday` (0=lunes)."""
        if self._engine is Engine.SQLITE:
            return f"((CAST(strftime('%w', {column}) AS INTEGER) + 6) % 7)"
        if self._engine is Engine.MYSQL:
            return f"WEEKDAY({column})"
        return f"EXTRACT(ISODOW FROM {column}) - 1"

    def _date_part(self, column, part):
        fmt = {
            "year": "%Y", "month": "%m", "day": "%d",
            "hour": "%H", "minute": "%M", "second": "%S",
        }[part]
        if self._engine is Engine.SQLITE:
            return f"CAST(strftime('{fmt}', {column}) AS INTEGER)"
        if self._engine is Engine.MYSQL:
            return f"{part.upper()}({column})"
        return f"EXTRACT({part.upper()} FROM {column})"

    # --- string ---
    def length(self, column) -> str:
        if self._engine is Engine.MYSQL:
            return f"CHAR_LENGTH({column})"
        return f"length({column})"

    def substring(self, column, start: int, length: int | None = None) -> str:
        if self._engine is Engine.SQLITE:
            return f"substr({column}, {start})" if length is None else f"substr({column}, {start}, {length})"
        if self._engine is Engine.MYSQL:
            return f"SUBSTRING({column}, {start})" if length is None else f"SUBSTRING({column}, {start}, {length})"
        return f"substring({column} from {start})" if length is None else f"substring({column} from {start} for {length})"

    def concat(self, *parts) -> str:
        if self._engine is Engine.SQLITE:
            return " || ".join(str(p) for p in parts)
        return f"CONCAT({', '.join(str(p) for p in parts)})"

    # --- otros ---
    def random(self) -> str:
        if self._engine is Engine.MYSQL:
            return "RAND()"
        return "RANDOM()"

    def uuid(self) -> str:
        if self._engine is Engine.SQLITE:
            raise NotImplementedError("uuid() no está disponible en SQLite (requiere extensión)")
        if self._engine is Engine.MYSQL:
            return "UUID()"
        return "gen_random_uuid()"

    def date_format(self, column, pattern) -> str:
        """Formatea una fecha con el patrón nativo del motor (`%Y-%m-%d` o `YYYY-MM-DD`)."""
        if self._engine is Engine.SQLITE:
            return f"strftime('{pattern}', {column})"
        if self._engine is Engine.MYSQL:
            return f"DATE_FORMAT({column}, '{pattern}')"
        return f"to_char({column}, '{pattern}')"

    @staticmethod
    def _check_unit(unit):
        if unit not in _UNITS:
            raise ValueError(f"unidad de fecha inválida: {unit!r}")
