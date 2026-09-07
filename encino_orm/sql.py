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

_GEO_UNITS = ("m", "km", "mi", "nmi")
_METERS_PER_UNIT = {"m": 1, "km": 1000, "mi": 1609.344, "nmi": 1852.0}


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
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return "NOW()"
        if self._engine is Engine.MSSQL:
            return "GETDATE()"
        if self._engine is Engine.ORACLE:
            return "SYSDATE"
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
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            fn = "DATE_ADD" if add else "DATE_SUB"
            return f"{fn}({column}, INTERVAL {amount} {unit.upper()})"
        if self._engine is Engine.MSSQL:
            sign = "" if add else "-"
            return f"DATEADD({unit}, {sign}{amount}, {column})"
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
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"WEEKDAY({column})"
        if self._engine is Engine.MSSQL:
            # independiente de @@DATEFIRST: (dw + DATEFIRST - 2) % 7 => 0=lunes
            return f"((DATEPART(WEEKDAY, {column}) + @@DATEFIRST - 2) % 7)"
        return f"EXTRACT(ISODOW FROM {column}) - 1"

    def _date_part(self, column, part):
        fmt = {
            "year": "%Y", "month": "%m", "day": "%d",
            "hour": "%H", "minute": "%M", "second": "%S",
        }[part]
        if self._engine is Engine.SQLITE:
            return f"CAST(strftime('{fmt}', {column}) AS INTEGER)"
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"{part.upper()}({column})"
        if self._engine is Engine.MSSQL:
            return f"DATEPART({part}, {column})"
        return f"EXTRACT({part.upper()} FROM {column})"

    # --- string ---
    def length(self, column) -> str:
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"CHAR_LENGTH({column})"
        if self._engine is Engine.MSSQL:
            return f"LEN({column})"
        return f"length({column})"

    def substring(self, column, start: int, length: int | None = None) -> str:
        if self._engine is Engine.SQLITE:
            return f"substr({column}, {start})" if length is None else f"substr({column}, {start}, {length})"
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"SUBSTRING({column}, {start})" if length is None else f"SUBSTRING({column}, {start}, {length})"
        if self._engine is Engine.MSSQL:
            if length is None:
                raise ValueError("substring() en SQL Server requiere `length`")
            return f"SUBSTRING({column}, {start}, {length})"
        if self._engine is Engine.ORACLE:
            return f"SUBSTR({column}, {start})" if length is None else f"SUBSTR({column}, {start}, {length})"
        return f"substring({column} from {start})" if length is None else f"substring({column} from {start} for {length})"

    def concat(self, *parts) -> str:
        if self._engine in (Engine.SQLITE, Engine.ORACLE):
            return " || ".join(str(p) for p in parts)
        return f"CONCAT({', '.join(str(p) for p in parts)})"

    # --- otros ---
    def random(self) -> str:
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return "RAND()"
        if self._engine is Engine.MSSQL:
            return "NEWID()"
        if self._engine is Engine.ORACLE:
            return "DBMS_RANDOM.VALUE"
        return "RANDOM()"

    def uuid(self) -> str:
        if self._engine is Engine.SQLITE:
            raise NotImplementedError("uuid() no está disponible en SQLite (requiere extensión)")
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return "UUID()"
        if self._engine is Engine.MSSQL:
            return "NEWID()"
        if self._engine is Engine.ORACLE:
            return "SYS_GUID()"
        return "gen_random_uuid()"

    def date_format(self, column, pattern) -> str:
        """Formatea una fecha con el patrón nativo del motor (`%Y-%m-%d` o `YYYY-MM-DD`)."""
        if self._engine is Engine.SQLITE:
            return f"strftime('{pattern}', {column})"
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"DATE_FORMAT({column}, '{pattern}')"
        if self._engine is Engine.MSSQL:
            return f"FORMAT({column}, '{pattern}')"
        return f"to_char({column}, '{pattern}')"

    # --- diferencias de fecha ---
    def date_diff(self, a, b, unit: str = "day") -> str:
        """Diferencia `a - b` en la unidad indicada (portable entre motores)."""
        self._check_unit(unit)
        if unit in ("month", "year"):
            return self._date_diff_calendar(a, b, unit)
        factor = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800}[unit]
        secs = self._diff_seconds(a, b)
        return secs if factor == 1 else f"({secs} / {factor})"

    def _diff_seconds(self, a, b) -> str:
        if self._engine is Engine.SQLITE:
            return f"(strftime('%s', {a}) - strftime('%s', {b}))"
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"TIMESTAMPDIFF(SECOND, {b}, {a})"
        if self._engine is Engine.MSSQL:
            return f"DATEDIFF(SECOND, {b}, {a})"
        if self._engine is Engine.ORACLE:
            return f"((CAST({a} AS DATE) - CAST({b} AS DATE)) * 86400)"
        return f"EXTRACT(EPOCH FROM ({a} - {b}))"  # PostgreSQL

    def _date_diff_calendar(self, a, b, unit) -> str:
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"TIMESTAMPDIFF({unit.upper()}, {b}, {a})"
        if self._engine is Engine.MSSQL:
            return f"DATEDIFF({unit.upper()}, {b}, {a})"
        if self._engine is Engine.ORACLE:
            m = f"MONTHS_BETWEEN({a}, {b})"
            return m if unit == "month" else f"({m} / 12)"
        if self._engine is Engine.SQLITE:
            days = f"(julianday({a}) - julianday({b}))"
            return (
                f"CAST({days} / 30.44 AS INTEGER)" if unit == "month"
                else f"CAST({days} / 365.25 AS INTEGER)"
            )
        age = f"AGE({a}, {b})"
        return (
            f"EXTRACT(YEAR FROM {age})" if unit == "year"
            else f"(EXTRACT(YEAR FROM {age}) * 12 + EXTRACT(MONTH FROM {age}))"
        )

    # --- agregación de texto ---
    def group_concat(self, column, sep: str = ",") -> str:
        """Agrega valores de texto separados por `sep` (string_agg/LISTAGG/GROUP_CONCAT)."""
        s = str(sep).replace("'", "''")
        if self._engine is Engine.SQLITE:
            return f"group_concat({column}, '{s}')"
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            return f"GROUP_CONCAT({column} SEPARATOR '{s}')"
        if self._engine is Engine.MSSQL:
            return f"STRING_AGG(CAST({column} AS NVARCHAR(MAX)), '{s}')"
        if self._engine is Engine.ORACLE:
            return f"LISTAGG({column}, '{s}')"
        return f"string_agg({column}::text, '{s}')"

    # --- manejo de nulos ---
    def coalesce(self, *values) -> str:
        return f"COALESCE({', '.join(str(v) for v in values)})"

    def nullif(self, a, b) -> str:
        return f"NULLIF({a}, {b})"

    # --- string (case) ---
    def lower(self, column) -> str:
        return f"lower({column})"

    def upper(self, column) -> str:
        return f"upper({column})"

    def ilike(self, column, pattern) -> str:
        """Comparación `LIKE` case-insensitive (`ILIKE` en PostgreSQL)."""
        p = "'" + str(pattern).replace("'", "''") + "'"
        if self._engine is Engine.POSTGRESQL:
            return f"{column} ILIKE {p}"
        return f"LOWER({column}) LIKE LOWER({p})"

    # --- geo ---
    def geo_distance(self, lat1, lon1, lat2, lon2, unit: str = "m") -> str:
        """Distancia entre dos puntos (o columna↔punto) en `unit`.

        `lat1`/`lon1`/`lat2`/`lon2` son literales o nombres de columna. Usa la
        función espacial nativa (metros) en MySQL/MariaDB/SQL Server y haversine
        portable en SQLite/PostgreSQL/Oracle.
        """
        if unit not in _GEO_UNITS:
            raise ValueError(f"unidad de distancia inválida: {unit!r} (use: {', '.join(_GEO_UNITS)})")
        if self._engine in (Engine.MYSQL, Engine.MARIADB):
            m = f"ST_Distance_Sphere(POINT({lon1}, {lat1}), POINT({lon2}, {lat2}))"
        elif self._engine is Engine.MSSQL:
            m = (
                f"geography::Point({lat1}, {lon1}, 4326).STDistance("
                f"geography::Point({lat2}, {lon2}, 4326))"
            )
        else:
            m = self._haversine_m(lat1, lon1, lat2, lon2)
        factor = _METERS_PER_UNIT[unit]
        return m if factor == 1 else f"({m} / {factor})"

    def geo_distance_col(self, lat_col, lon_col, lat, lon, unit: str = "m") -> str:
        """Distancia desde una columna `(lat_col, lon_col)` a un punto `(lat, lon)`."""
        return self.geo_distance(lat_col, lon_col, lat, lon, unit)

    def _radians(self, expr) -> str:
        if self._engine is Engine.ORACLE:
            return f"({expr} * 3.14159265358979323846 / 180)"
        return f"radians({expr})"

    def _haversine_m(self, lat1, lon1, lat2, lon2) -> str:
        r = self._radians
        dlat = f"sin({r(f'({lat2} - {lat1}) / 2.0')})"
        dlon = f"sin({r(f'({lon2} - {lon1}) / 2.0')})"
        return (
            "2 * 6371000 * asin(sqrt("
            f"power({dlat}, 2) + "
            f"cos({r(lat1)}) * cos({r(lat2)}) * power({dlon}, 2)))"
        )

    @staticmethod
    def _check_unit(unit):
        if unit not in _UNITS:
            raise ValueError(f"unidad de fecha inválida: {unit!r}")
