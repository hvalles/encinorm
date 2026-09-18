from dataclasses import replace

from .dialects.strategies import LIMITS
from .mysql import MysqlDb


class MariadbDb(MysqlDb):
    """Motor MariaDB: drop-in del protocolo MySQL (`aiomysql`).

    Reusa toda la lógica de `MysqlDb`; solo ajusta la introspección porque
    MariaDB reporta el tipo `JSON` como `LONGTEXT` (alias con `CHECK json_valid`).
    """

    dialect = "mariadb"
    # Sobrescribe los techos heredados de `MysqlDb` para que el valor sea el del
    # dialecto correcto aunque hoy coincidan.
    MAX_PARAMS = LIMITS["mariadb"].max_params
    MAX_ROWS = LIMITS["mariadb"].max_rows

    async def columns_of(self, table):
        cols = await super().columns_of(table)
        result = []
        for c in cols:
            if c.datatype == "str" and (c.raw_type or "").lower() == "longtext":
                c = replace(c, datatype="json")
            result.append(c)
        return result
