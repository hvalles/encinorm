class EncinormError(Exception):
    pass


class ConnectionError(EncinormError):
    pass


class QueryError(EncinormError):
    pass


class UnsupportedEngineError(EncinormError):
    pass


class MigrationError(EncinormError):
    pass


class PoolExhaustedError(EncinormError):
    pass
