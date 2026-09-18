"""Seam de dialectos: validación de identificadores y construcción DML compartida."""

from .identifiers import IDENTIFIER_RE, check_identifier
from .strategies import (
    MARIADB_INSERT,
    MSSQL_INSERT,
    MYSQL_INSERT,
    ORACLE_INSERT,
    POSTGRES_INSERT,
    SQLITE_INSERT,
    InsertStrategy,
)

__all__ = [
    "IDENTIFIER_RE",
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "InsertStrategy",
    "check_identifier",
]
