class Query:
    def __init__(self, sql: str, fields: list):
        self.sql_template: str = sql
        self.fields: list = fields
        self._param_name: str = "parameter_000"

        if sql.find("{0}") != -1:
            self.query = self.format(sql, fields, self._param_name)
        else:
            self.query = [sql, {}]

    def format(self, sql, columns: list = None, name="parameter_000"):
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

    def rebind(self, fields: list):
        self.fields = fields
        self.query = self.format(self.sql_template, fields, self._param_name)
        return self

    def __str__(self):
        return str(self.query[0]) + str(self.query[1])
