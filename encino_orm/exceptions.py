class EncinoOrmError(Exception):
    pass


class ConnectionError(EncinoOrmError):
    pass


class ConnectionLostError(ConnectionError):
    pass


class QueryError(EncinoOrmError):
    pass


class OperationalError(QueryError):
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
