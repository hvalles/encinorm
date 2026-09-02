"""Identificación tipada de motores de base de datos."""

from enum import Enum


class Engine(str, Enum):
    """Motores soportados (miembro `str`, comparable con su valor).

    ``Engine.SQLITE == "sqlite"`` es `True`; para claves de dict/parámetros que
    exigen `str` usa ``engine.value``.
    """

    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"

    def __str__(self) -> str:
        return self.value


def engine_of(db) -> Engine:
    """Devuelve el motor activo como `Engine`.

    Acepta un `Db`/`PoolDb` (lee `dialect`), un `Engine` (se devuelve tal cual) o
    una cadena (`"sqlite"`/`"mysql"`/`"postgresql"`). Un valor desconocido lanza
    `ValueError`.
    """
    if isinstance(db, Engine):
        return db
    dialect = getattr(db, "dialect", db)
    if isinstance(dialect, Engine):
        return dialect
    return Engine(dialect)


def is_sqlite(db) -> bool:
    return engine_of(db) is Engine.SQLITE


def is_mysql(db) -> bool:
    return engine_of(db) is Engine.MYSQL


def is_postgres(db) -> bool:
    return engine_of(db) is Engine.POSTGRESQL
