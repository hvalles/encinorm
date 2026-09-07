from dataclasses import replace

from .mysql import MysqlDb


class MariadbDb(MysqlDb):
    """Motor MariaDB: drop-in del protocolo MySQL (`aiomysql`).

    Reusa toda la lógica de `MysqlDb`; solo ajusta la introspección porque
    MariaDB reporta el tipo `JSON` como `LONGTEXT` (alias con `CHECK json_valid`).
    """

    dialect = "mariadb"

    async def columns_of(self, table):
        cols = await super().columns_of(table)
        result = []
        for c in cols:
            if c.datatype == "str" and (c.raw_type or "").lower() == "longtext":
                c = replace(c, datatype="json")
            result.append(c)
        return result
