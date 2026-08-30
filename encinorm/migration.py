"""Migraciones de esquema versionadas (`Migration` + runner)."""

from dataclasses import dataclass

from .exceptions import MigrationError
from .query import Query


@dataclass(frozen=True)
class Migration:
    name: str
    up: Query | str
    down: Query | str | None = None     # opcional (rollback)


def _to_query(sql: Query | str) -> Query:
    return sql if isinstance(sql, Query) else Query(sql, [])


async def apply_migration(db, m: Migration) -> None:
    """Aplica una migración (idempotente vía `db.migrate`)."""
    await db.migrate(m.name, _to_query(m.up))


async def rollback_migration(db, m: Migration) -> None:
    """Revierte una migración aplicando su `down` (si existe)."""
    if m.down is None:
        raise MigrationError(f"{m.name} no tiene down")
    await db.migrate(f"{m.name}:down", _to_query(m.down))


async def apply_migrations(db, migrations: list[Migration]) -> None:
    """Aplica una lista de migraciones en orden."""
    for m in migrations:
        await apply_migration(db, m)


def migrations_from_dir(path: str) -> list[Migration]:
    """Carga las migraciones de un directorio (archivos `NNN_descripcion.py`).

    Cada archivo debe definir una variable módulo `MIGRATION` (instancia de
    `Migration`). Se cargan en orden alfabético por nombre de archivo.
    """
    import importlib.util
    from pathlib import Path

    migrations = []
    for f in sorted(Path(path).glob("*.py")):
        spec = importlib.util.spec_from_file_location(f.stem, f)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        m = getattr(module, "MIGRATION", None)
        if m is None:
            raise MigrationError(f"{f.name} no define MIGRATION")
        migrations.append(m)
    return migrations
