class Query:
    """Sentencia SQL + parámetros, con placeholders `{n}` compilados a `%(name)s`.

    Los accesores `sql` y `params` son la superficie tipada que consumen los
    adaptadores; `query` se conserva como property de SOLO LECTURA que devuelve
    una lista nueva `[sql, params]` en cada acceso (compatibilidad de lectura,
    D-02). La inmutabilidad real y `with_params()` llegan en DIAL-05; aquí el
    cambio es puramente aditivo.
    """

    def __init__(self, sql: str, fields: list | None = None, *, ignore_duplicated: bool = False):
        self.sql_template: str = sql
        self.fields: list = fields if fields is not None else []
        self.ignore_duplicated: bool = ignore_duplicated
        self._param_name: str = "parameter_000"

        compiled = self.format(sql, self.fields, self._param_name)
        self._sql: str = compiled[0]
        self._params: dict = compiled[1]

    def format(self, sql, columns: list | None = None, name="parameter_000"):
        if columns is None:
            columns = []
        if not columns:
            return [sql, {}]

        cols = {}
        for i, val in enumerate(columns):
            cols[f"{name}{i}"] = val

        formatted_sql = sql
        for i, key in enumerate(cols):
            formatted_sql = formatted_sql.replace(f"{{{i}}}", f"%({key})s")

        return [formatted_sql, cols]

    @property
    def sql(self) -> str:
        """SQL compilado con placeholders intermedios `%(parameter_0000)s`."""
        return self._sql

    @property
    def params(self) -> dict:
        """Parámetros por nombre (`{"parameter_0000": valor}`)."""
        return self._params

    @property
    def query(self) -> list:
        """Compatibilidad de lectura: lista nueva `[sql, params]` en cada acceso."""
        return [self._sql, self._params]

    def rebind(self, fields: list):
        self.fields = fields
        compiled = self.format(self.sql_template, fields, self._param_name)
        self._sql = compiled[0]
        self._params = compiled[1]
        return self

    def __str__(self):
        return str(self._sql) + str(self._params)
