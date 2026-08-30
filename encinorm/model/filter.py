import re

_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")

_COMPARISON = ("=", "!=", ">", "<", ">=", "<=")


class ColumnRef:
    """Referencia a una columna (no parametrizada), para condiciones de join."""

    __slots__ = ("name",)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"col({self.name!r})"


def col(name: str) -> ColumnRef:
    return ColumnRef(name)


def _safe_field(field) -> str:
    if not isinstance(field, str) or not _FIELD_RE.match(field):
        raise ValueError(f"Nombre de campo inválido: {field!r}")
    return field


class Filter:
    """Condición de filtrado componible y validable.

    Cada operación produce un nodo inmutable. `to_sql` devuelve un fragmento SQL
    con placeholders ``{0}..{n}`` y la lista de parámetros correspondiente.
    """

    __slots__ = ("_op", "_args")

    def __init__(self, op: str, *args):
        self._op = op
        self._args = args

    # --- comparación ---
    @staticmethod
    def eq(field, value) -> "Filter":
        return Filter("=", field, value)

    @staticmethod
    def ne(field, value) -> "Filter":
        return Filter("!=", field, value)

    @staticmethod
    def gt(field, value) -> "Filter":
        return Filter(">", field, value)

    @staticmethod
    def lt(field, value) -> "Filter":
        return Filter("<", field, value)

    @staticmethod
    def ge(field, value) -> "Filter":
        return Filter(">=", field, value)

    @staticmethod
    def le(field, value) -> "Filter":
        return Filter("<=", field, value)

    @staticmethod
    def in_(field, values) -> "Filter":
        return Filter("IN", field, tuple(values))

    @staticmethod
    def between(field, lo, hi) -> "Filter":
        return Filter("BETWEEN", field, lo, hi)

    @staticmethod
    def like(field, value) -> "Filter":
        return Filter("LIKE", field, f"%{value}%")

    @staticmethod
    def startswith(field, value) -> "Filter":
        return Filter("LIKE", field, f"{value}%")

    @staticmethod
    def endswith(field, value) -> "Filter":
        return Filter("LIKE", field, f"%{value}")

    @staticmethod
    def is_null(field) -> "Filter":
        return Filter("IS NULL", field)

    @staticmethod
    def not_null(field) -> "Filter":
        return Filter("IS NOT NULL", field)

    @staticmethod
    def raw(sql: str, params: list) -> "Filter":
        return Filter("RAW", sql, list(params))

    # --- agrupadores ---
    def and_(self, other) -> "Filter":
        return Filter("AND", self, other)

    def or_(self, other) -> "Filter":
        return Filter("OR", self, other)

    def not_(self) -> "Filter":
        return Filter("NOT", self)

    def __and__(self, other) -> "Filter":
        return self.and_(other)

    def __or__(self, other) -> "Filter":
        return self.or_(other)

    def __invert__(self) -> "Filter":
        return self.not_()

    # --- utilidades ---
    def map_fields(self, mapping: dict) -> "Filter":
        """Devuelve una copia con los nombres de campo reemplazados por `mapping`."""
        op = self._op
        if op in _COMPARISON or op in ("IN", "BETWEEN", "LIKE"):
            args = list(self._args)
            args[0] = mapping.get(args[0], args[0])
            return Filter(op, *args)
        if op in ("IS NULL", "IS NOT NULL"):
            (field,) = self._args
            return Filter(op, mapping.get(field, field))
        if op in ("AND", "OR"):
            return Filter(op, *(sub.map_fields(mapping) for sub in self._args))
        if op == "NOT":
            return Filter(op, self._args[0].map_fields(mapping))
        return self

    def to_sql(self, alias: str | None = None) -> tuple[str, list]:
        idx = [0]
        sql, params = self._build(alias, idx)
        return sql, params

    def _build(self, alias, idx) -> tuple[str, list]:
        op = self._op
        if op in _COMPARISON:
            field, value = self._args
            if isinstance(value, ColumnRef):
                return f"{self._qual(field, alias)} {op} {_safe_field(value.name)}", []
            sql = f"{self._qual(field, alias)} {op} {{{idx[0]}}}"
            idx[0] += 1
            return sql, [value]
        if op == "IN":
            field, values = self._args
            placeholders = ", ".join(f"{{{idx[0] + i}}}" for i in range(len(values)))
            idx[0] += len(values)
            return f"{self._qual(field, alias)} IN ({placeholders})", list(values)
        if op == "BETWEEN":
            field, lo, hi = self._args
            sql = f"{self._qual(field, alias)} BETWEEN {{{idx[0]}}} AND {{{idx[0] + 1}}}"
            idx[0] += 2
            return sql, [lo, hi]
        if op == "LIKE":
            field, value = self._args
            sql = f"{self._qual(field, alias)} LIKE {{{idx[0]}}}"
            idx[0] += 1
            return sql, [value]
        if op in ("IS NULL", "IS NOT NULL"):
            (field,) = self._args
            return f"{self._qual(field, alias)} {op}", []
        if op == "RAW":
            sql, params = self._args
            return self._rebind_raw(sql, params, idx)
        if op in ("AND", "OR"):
            parts = []
            params = []
            for sub in self._args:
                s, p = sub._build(alias, idx)
                parts.append(s)
                params.extend(p)
            return f"({f' {op} '.join(parts)})", params
        if op == "NOT":
            (sub,) = self._args
            s, p = sub._build(alias, idx)
            return f"(NOT {s})", p
        raise ValueError(f"Operador desconocido en Filter: {op!r}")

    def _qual(self, field, alias) -> str:
        field = _safe_field(field)
        if alias and "." not in field:
            return f"{alias}.{field}"
        return field

    def _rebind_raw(self, sql, params, idx) -> tuple[str, list]:
        def repl(match):
            return "{" + str(int(match.group(1)) + idx[0]) + "}"

        new_sql = re.sub(r"\{(\d+)\}", repl, sql)
        idx[0] += len(params)
        return new_sql, list(params)

    def __repr__(self) -> str:
        return f"Filter({self._op!r}, {self._args!r})"
