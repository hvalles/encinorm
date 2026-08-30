"""Introspección de tablas y columnas (SQL por motor)."""

from encinorm.model import Records
from encinorm.query import Query

from .types import ColumnSpec, _normalize

_SQLITE_TABLES = (
    "SELECT name FROM sqlite_master "
    "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name <> '_encinorm_migrations'"
)
_MYSQL_TABLES = (
    "SELECT table_name AS name FROM information_schema.tables "
    "WHERE table_schema = DATABASE()"
)
_POSTGRES_TABLES = (
    "SELECT tablename AS name FROM pg_catalog.pg_tables "
    "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
)


def _tables_query(dialect: str) -> str:
    if dialect == "sqlite":
        return _SQLITE_TABLES
    if dialect == "mysql":
        return _MYSQL_TABLES
    if dialect == "postgresql":
        return _POSTGRES_TABLES
    raise NotImplementedError(f"list_tables no soporta el motor {dialect!r}")


async def list_tables(db, *, name: str = "", limit: int = 50, page: int = 1) -> Records:
    """Lista las tablas del catálogo con filtro por nombre y paginación."""
    sql = _tables_query(getattr(db, "dialect", "sqlite"))
    params = []
    if name:
        sql += " AND name LIKE {0}"
        params.append(f"%{name}%")

    total = (await db.fetch_one(Query(f"SELECT COUNT(*) FROM ({sql})", params)))["COUNT(*)"]
    rows = await db.fetch_many(Query(sql, params), limit, page)
    return Records(rows=rows, total=total, limit=limit, page=page)


async def columns_of(db, table: str) -> list[ColumnSpec]:
    """Devuelve la especificación de columnas de una tabla (nombre, tipo, PK, nullable)."""
    dialect = getattr(db, "dialect", "sqlite")

    if dialect == "sqlite":
        rows = await db.fetch_all(Query(f"PRAGMA table_info({table})", []))
        return [
            ColumnSpec(
                name=r["name"],
                raw_type=r["type"] or "",
                datatype=_normalize(r["type"])[0],
                nullable=not bool(r["notnull"]),
                primary_key=bool(r["pk"]),
                max_length=_normalize(r["type"])[1],
                unsigned=_normalize(r["type"])[2],
            )
            for r in rows
        ]

    if dialect == "mysql":
        rows = await db.fetch_all(Query(f"SHOW COLUMNS FROM {table}", []))
        return [
            ColumnSpec(
                name=r["Field"],
                raw_type=r["Type"],
                datatype=_normalize(r["Type"])[0],
                nullable=(r["Null"] == "YES"),
                primary_key=(r["Key"] == "PRI"),
                max_length=_normalize(r["Type"])[1],
                unsigned=_normalize(r["Type"])[2],
            )
            for r in rows
        ]

    if dialect == "postgresql":
        rows = await db.fetch_all(Query(
            "SELECT column_name, data_type, is_nullable, "
            "CASE WHEN column_default LIKE 'nextval%' THEN TRUE ELSE FALSE END AS is_pk "
            "FROM information_schema.columns WHERE table_name = {0} "
            "ORDER BY ordinal_position",
            [table],
        ))
        return [
            ColumnSpec(
                name=r["column_name"],
                raw_type=r["data_type"],
                datatype=_normalize(r["data_type"])[0],
                nullable=(r["is_nullable"] == "YES"),
                primary_key=bool(r["is_pk"]),
                max_length=_normalize(r["data_type"])[1],
                unsigned=_normalize(r["data_type"])[2],
            )
            for r in rows
        ]

    raise NotImplementedError(f"columns_of no soporta el motor {dialect!r}")
