"""Migraciones de esquema versionadas (`Migration` + runner)."""

import logging
from dataclasses import dataclass

from .dialects.identifiers import check_identifier
from .exceptions import MigrationError
from .query import Query

logger = logging.getLogger("encino_orm")

# Fuente única del nombre del ledger. Los adaptadores lo importan desde aquí
# (adaptador -> migration, nunca al revés) para no crear ciclos de importación.
MIGRATIONS_TABLE = "_encino_orm_migrations"

# Máquina de estados de la columna `status` (D-01/D-07). El DEFAULT del ledger
# es `applied` porque una fila solo existe tras un DDL exitoso.
STATUS_PENDING = "pending"
STATUS_APPLIED = "applied"
STATUS_ROLLING_BACK = "rolling_back"


@dataclass(frozen=True)
class Migration:
    name: str
    up: Query | str
    down: Query | str | None = None  # opcional (rollback)


def _to_query(sql: Query | str) -> Query:
    return sql if isinstance(sql, Query) else Query(sql, [])


async def _ensure_ledger(db) -> None:
    """Garantiza que el ledger existe; tolera dobles que no lo implementan."""
    ensure = getattr(db, "_ensure_migrations_table", None)
    if ensure is not None:
        await ensure()


async def _row_status(db, name: str) -> str | None:
    """Devuelve el `status` de la fila `{name}`, o `None` si no existe.

    `name` viaja SIEMPRE como parámetro ligado (T-03-01-01).
    """
    check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
    row = await db.fetch_one(
        Query(f"SELECT status FROM {MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
    )
    return None if row is None else row["status"]


async def _set_status(db, name: str, status: str) -> None:
    """Actualiza el `status` de la fila `{name}` (valores ligados)."""
    check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
    await db.execute(db.update(MIGRATIONS_TABLE, {"name": name}, {"status": status}))


async def _delete_row(db, name: str) -> None:
    """Borra la fila `{name}` del ledger."""
    check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
    await db.execute(db.delete(MIGRATIONS_TABLE, {"name": name}))


async def apply_migration(db, m: Migration) -> None:
    """Aplica una migración (idempotente vía `db.migrate`)."""
    await db.migrate(m.name, _to_query(m.up))


async def rollback_migration(db, m: Migration) -> None:
    """Revierte una migración ejecutando su `down` y borrando su fila del ledger.

    La fila pasa a `rolling_back` antes del `down` (D-07) y se borra al
    terminar (D-06); NUNCA se registra una fila con sufijo de reversión. El
    runner usa solo `async with db.transaction()` — nunca el commit directo del
    adaptador — para funcionar también a través de un `PoolDb`.
    """
    if m.down is None:
        raise MigrationError(f"{m.name} no tiene down")

    await _ensure_ledger(db)

    status = await _row_status(db, m.name)
    if status != STATUS_APPLIED:
        raise MigrationError(
            f"{m.name} no está aplicada (status={status!r}); "
            "usa resolve_migration() si su estado es ambiguo"
        )

    down_done = False
    try:
        async with db.transaction():
            await _set_status(db, m.name, STATUS_ROLLING_BACK)
            await db.execute(_to_query(m.down))
            down_done = True
            await _delete_row(db, m.name)
    except Exception:
        if not down_done:
            # El `down` no llegó a correr: compensar a `applied`. En motores
            # transaccionales el rollback ya la dejó así (el UPDATE es no-op);
            # en MySQL/MariaDB/Oracle el commit implícito del DDL publicó
            # `rolling_back` y hay que restaurarla.
            try:
                async with db.transaction():
                    await _set_status(db, m.name, STATUS_APPLIED)
            except Exception as exc:
                # Fail-open: la fila queda `rolling_back` para reconciliación.
                logger.warning("no se pudo restaurar %s a applied: %r", m.name, exc)
        # Si `down_done` es True el `down` sí corrió: la fila debe quedar
        # `rolling_back` para que la reconciliación la detecte.
        raise


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
