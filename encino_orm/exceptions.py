class EncinoOrmError(Exception):
    pass


class ConnectionError(EncinoOrmError):
    pass


class ConnectionLostError(ConnectionError):
    pass


class QueryError(EncinoOrmError):
    pass


class OperationalError(EncinoOrmError):
    # NO deriva de `QueryError`: agrupa fallos de INFRAESTRUCTURA del driver
    # (servidor caído, timeout, error operativo), no errores de la consulta del
    # cliente. Así el mapeo HTTP no los etiqueta como 400 (WR-05); sin un
    # handler específico caen al 500 genérico.
    pass


class IntegrityError(QueryError):
    pass


class ProgrammingError(QueryError):
    pass


class UnsupportedEngineError(EncinoOrmError):
    pass


class MigrationError(EncinoOrmError):
    pass


class PoolExhaustedError(EncinoOrmError):
    pass
