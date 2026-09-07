class EncinoOrmError(Exception):
    pass


class ConnectionError(EncinoOrmError):
    pass


class QueryError(EncinoOrmError):
    pass


class UnsupportedEngineError(EncinoOrmError):
    pass


class MigrationError(EncinoOrmError):
    pass


class PoolExhaustedError(EncinoOrmError):
    pass
