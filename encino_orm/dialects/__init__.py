"""Seam de dialectos: validación de identificadores y construcción DML compartida."""

from .builders import build_delete, build_insert, build_update, build_upsert
from .identifiers import IDENTIFIER_RE, check_identifier
from .strategies import (
    MARIADB_INSERT,
    MSSQL_INSERT,
    MYSQL_INSERT,
    ORACLE_INSERT,
    POSTGRES_INSERT,
    SQLITE_INSERT,
    UPSERT_KIND,
    UPSERT_KINDS,
    InsertStrategy,
    strategy_for,
)

__all__ = [
    "IDENTIFIER_RE",
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "UPSERT_KIND",
    "UPSERT_KINDS",
    "InsertStrategy",
    "build_delete",
    "build_insert",
    "build_update",
    "build_upsert",
    "check_identifier",
    "strategy_for",
]
