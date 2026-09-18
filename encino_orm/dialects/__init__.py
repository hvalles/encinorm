"""Seam de dialectos: validación de identificadores y construcción DML compartida."""

from .builders import build_delete, build_insert, build_update, build_upsert
from .identifiers import IDENTIFIER_RE, check_identifier
from .strategies import (
    LIMITS,
    MARIADB_INSERT,
    MSSQL_INSERT,
    MYSQL_INSERT,
    ORACLE_INSERT,
    POSTGRES_INSERT,
    SQLITE_INSERT,
    TRANSACTIONAL_DDL,
    UPSERT_KIND,
    UPSERT_KINDS,
    DialectLimits,
    InsertStrategy,
    strategy_for,
)

__all__ = [
    "IDENTIFIER_RE",
    "LIMITS",
    "MARIADB_INSERT",
    "MSSQL_INSERT",
    "MYSQL_INSERT",
    "ORACLE_INSERT",
    "POSTGRES_INSERT",
    "SQLITE_INSERT",
    "TRANSACTIONAL_DDL",
    "UPSERT_KIND",
    "UPSERT_KINDS",
    "DialectLimits",
    "InsertStrategy",
    "build_delete",
    "build_insert",
    "build_update",
    "build_upsert",
    "check_identifier",
    "strategy_for",
]
