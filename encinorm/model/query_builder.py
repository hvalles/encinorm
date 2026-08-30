import re

from encinorm.query import Query

from .exceptions import DuplicateAliasError, DuplicateColumnAliasError
from .filter import Filter

_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _shift(sql: str, offset: int) -> str:
    return _PLACEHOLDER.sub(
        lambda m: "{" + str(int(m.group(1)) + offset) + "}", sql
    )


def _safe_column(expr: str) -> str:
    expr = expr.strip()
    if expr == "*":
        return expr
    if expr.endswith(".*"):
        if _COLUMN_RE.match(expr[:-2]):
            return expr
        raise ValueError(f"nombre de columna inválido: {expr!r}")
    if not _COLUMN_RE.match(expr):
        raise ValueError(f"nombre de columna inválido: {expr!r}")
    return expr


class QueryBuilder:
    """Constructor de consultas sobre modelos, con `join`, agregados y alias.

    Trabaja con **nombres de columna** calificados por alias (``mm.agente``).
    """

    def __init__(self, model_class, db=None, alias: str = "mm"):
        self._model_class = model_class
        self._db = db
        self._alias = alias
        self._aliases = {alias}
        self._alias_to_model = {alias: model_class}
        self._column_aliases = {}
        self._select = []
        self._joins = []
        self._where = None
        self._group_by = []
        self._having = None
        self._order_by = []
        self._limit_n = None
        self._limit_page = 1
        self._subquery_idx = 0

    # --- constructores (fluidos) ---
    def select(self, *columns) -> "QueryBuilder":
        for c in columns:
            self._add_select(c)
        return self

    def _add_select(self, expr: str):
        alias = None
        if " AS " in expr:
            expr, alias = expr.split(" AS ", 1)
            expr, alias = expr.strip(), alias.strip()
        if expr.endswith(".*"):
            base = expr[:-2]
            _safe_column(expr)
            for expanded in self._expand_star(base):
                self._select.append((expanded, None))
            return
        expr = _safe_column(expr)
        if alias is not None:
            alias = _safe_column(alias)
            if alias in self._column_aliases:
                raise DuplicateColumnAliasError(f"alias de columna '{alias}' duplicado")
            self._column_aliases[alias] = expr
        self._select.append((expr, alias))

    def _expand_star(self, alias: str) -> list:
        model_cls = self._alias_to_model.get(alias)
        if model_cls is None:
            raise ValueError(f"alias desconocido: {alias!r}")
        return [f"{alias}.{c}" for c in model_cls._column_map().values()]

    def join(self, other, alias: str, on: Filter) -> "QueryBuilder":
        if other is self._model_class:
            raise DuplicateAliasError(
                "self-join no permitido en join(); usa join_subquery()"
            )
        if alias in self._aliases:
            raise DuplicateAliasError(f"alias '{alias}' duplicado")
        self._aliases.add(alias)
        self._alias_to_model[alias] = other
        self._joins.append({"type": "table", "model_class": other, "alias": alias, "on": on})
        return self

    def join_subquery(self, subquery: "QueryBuilder", alias: str | None, on: Filter) -> "QueryBuilder":
        if alias is None:
            alias = self._next_subquery_alias()
        if alias in self._aliases:
            raise DuplicateAliasError(f"alias '{alias}' duplicado")
        self._aliases.add(alias)
        self._alias_to_model[alias] = subquery._model_class
        self._joins.append({"type": "subquery", "subquery": subquery, "alias": alias, "on": on})
        return self

    def _next_subquery_alias(self) -> str:
        while True:
            self._subquery_idx += 1
            candidate = f"sq{self._subquery_idx}_{self._alias}"
            if candidate not in self._aliases:
                return candidate

    def where(self, filter: Filter) -> "QueryBuilder":
        self._where = filter
        return self

    def group_by(self, *columns) -> "QueryBuilder":
        self._group_by = [_safe_column(c) for c in columns]
        return self

    def having(self, filter: Filter) -> "QueryBuilder":
        self._having = filter
        return self

    def order_by(self, *columns) -> "QueryBuilder":
        self._order_by = [_safe_column(c) for c in columns]
        return self

    def sort_by(self, *fields) -> "QueryBuilder":
        """Ordena el resultado por una lista de campos con dirección opcional.

        Cada campo puede ser:
          - ``"nombre"`` -> ASC (por defecto).
          - ``"nombre asc"`` / ``"nombre desc"`` -> dirección explícita.
          - ``("nombre", "asc" | "desc")`` -> tupla (nombre, dirección).
        """
        self._order_by = [self._parse_sort(f) for f in fields]
        return self

    @staticmethod
    def _parse_sort(field) -> str:
        if isinstance(field, (tuple, list)):
            if len(field) != 2:
                raise ValueError(f"especificación de orden inválida: {field!r}")
            name, direction = field
            direction = str(direction).lower()
        else:
            parts = str(field).strip().split()
            if len(parts) == 1:
                return _safe_column(parts[0])
            if len(parts) == 2:
                name, direction = parts[0], parts[1].lower()
            else:
                raise ValueError(f"especificación de orden inválida: {field!r}")
        if direction not in ("asc", "desc"):
            raise ValueError(f"dirección de orden inválida: {direction!r}")
        return f"{_safe_column(name)} {direction.upper()}"

    def limit(self, n: int, page: int = 1) -> "QueryBuilder":
        self._limit_n = n
        self._limit_page = page
        return self

    # --- generación de SQL ---
    def _build_base(self) -> tuple[str, list]:
        params = []
        sql = f"FROM {self._model_class._table} {self._alias}"
        for join in self._joins:
            if join["type"] == "table":
                on_frag, on_params = join["on"].to_sql()
                on_frag = _shift(on_frag, len(params))
                params.extend(on_params)
                sql += f" JOIN {join['model_class']._table} {join['alias']} ON {on_frag}"
            else:
                sub_sql, sub_params = join["subquery"]._build_subquery()
                sub_sql = _shift(sub_sql, len(params))
                params.extend(sub_params)
                on_frag, on_params = join["on"].to_sql()
                on_frag = _shift(on_frag, len(params))
                params.extend(on_params)
                sql += f" JOIN ({sub_sql}) {join['alias']} ON {on_frag}"
        if self._where is not None:
            wfrag, wparams = self._where.to_sql()
            wfrag = _shift(wfrag, len(params))
            params.extend(wparams)
            sql += f" WHERE {wfrag}"
        return sql, params

    def _build_full(self) -> tuple[str, list]:
        sql, params = self._build_base()
        if self._group_by:
            sql += " GROUP BY " + ", ".join(self._group_by)
        if self._having is not None:
            hfrag, hparams = self._having.to_sql()
            hfrag = _shift(hfrag, len(params))
            params.extend(hparams)
            sql += f" HAVING {hfrag}"
        if self._order_by:
            sql += " ORDER BY " + ", ".join(self._order_by)
        return sql, params

    def _build_subquery(self) -> tuple[str, list]:
        sql, params = self._build_full()
        return f"SELECT {self._render_select()} {sql}", params

    def _render_select(self) -> str:
        if not self._select:
            return "*"
        parts = []
        for expr, alias in self._select:
            parts.append(f"{expr} AS {alias}" if alias else expr)
        return ", ".join(parts)

    def _ensure_db(self):
        if self._db is None:
            raise ValueError("QueryBuilder sin conexión Db; pásalo como QueryBuilder(Model, db)")

    # --- ejecución ---
    async def all(self) -> list[dict]:
        self._ensure_db()
        sql, params = self._build_full()
        sql = f"SELECT {self._render_select()} {sql}"
        if self._limit_n is not None:
            offset = (self._limit_page - 1) * self._limit_n
            sql += f" LIMIT {self._limit_n} OFFSET {offset}"
        return await self._db.fetch_all(Query(sql, params))

    async def first(self) -> dict | None:
        self._ensure_db()
        sql, params = self._build_full()
        sql = f"SELECT {self._render_select()} {sql} LIMIT 1"
        return await self._db.fetch_one(Query(sql, params))

    async def count(self) -> int:
        self._ensure_db()
        sql, params = self._build_base()
        sql = f"SELECT COUNT(*) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        return row["COUNT(*)"] if row else 0

    async def sum(self, column: str):
        self._ensure_db()
        sql, params = self._build_base()
        sql = f"SELECT SUM({column}) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        key = f"SUM({column})"
        return row[key] if row and row[key] is not None else 0

    async def avg(self, column: str):
        self._ensure_db()
        column = _safe_column(column)
        sql, params = self._build_base()
        sql = f"SELECT AVG({column}) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        return row[f"AVG({column})"] if row else None

    async def min(self, column: str):
        self._ensure_db()
        column = _safe_column(column)
        sql, params = self._build_base()
        sql = f"SELECT MIN({column}) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        return row[f"MIN({column})"] if row else None

    async def max(self, column: str):
        self._ensure_db()
        column = _safe_column(column)
        sql, params = self._build_base()
        sql = f"SELECT MAX({column}) {sql}"
        row = await self._db.fetch_one(Query(sql, params))
        return row[f"MAX({column})"] if row else None

    async def exists(self) -> bool:
        self._ensure_db()
        sql, params = self._build_base()
        sql = f"SELECT 1 {sql} LIMIT 1"
        return await self._db.fetch_one(Query(sql, params)) is not None

    async def paginate(self, limit: int, page: int = 1) -> "Records":
        """Devuelve un `Records` con la página actual y el total de registros."""
        from .records import Records

        total = await self.count()
        rows = await self.limit(limit, page).all()
        return Records(rows=rows, total=total, limit=limit, page=page)
