"""Introspección de tablas y columnas (delega en los métodos del motor)."""


async def list_tables(db, *, name: str = "", limit: int = 50, page: int = 1):
    """Lista las tablas del catálogo con filtro por nombre y paginación."""
    return await db.list_tables(name=name, limit=limit, page=page)


async def columns_of(db, table: str):
    """Devuelve la especificación de columnas de una tabla (por motor)."""
    return await db.columns_of(table)
