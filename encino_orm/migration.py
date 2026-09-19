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


async def _apply(db, name: str, qry: Query) -> None:
    """Aplica una migración con la máquina de dos fases (D-01).

    Registra la intención (`pending`) ANTES de ejecutar el DDL y la promueve a
    `applied` DESPUÉS. El runner NUNCA llama al commit directo del adaptador: usa
    `async with db.transaction()`, que funciona igual en un adaptador directo y
    a través de un `PoolDb` (`PoolDb.commit()` lanza `ConnectionError`).

    En motores con commit implícito del DDL (MySQL/MariaDB/Oracle) la fila
    `pending` puede sobrevivir al fallo; ahí se compensa solo si ESTA llamada
    insertó la fila y el DDL NO llegó a correr. El borrado usa la IDENTIDAD de la
    fila (`{id: ledger_id}`, capturada DENTRO del INSERT con `execute_insert`)
    porque `{name, status}` no prueba propiedad: la fila `pending` que otro
    runner re-publica tras nuestro rollback sobreviviría al compare-and-delete.
    Si el motor no expone un id utilizable (un MERGE, o un doble de test que
    devuelve 0), se cae al compare-and-delete `{name, status='pending'}`. Si el
    DDL sí corrió y falló el promote, la fila queda `pending` A PROPÓSITO para
    que la reconciliación la detecte (Pitfall 8: nada de teatro de atomicidad).

    Un fallo de la propia compensación NO reemplaza la excepción original del
    DDL: se registra un warning y se re-lanza el error raíz (IN-01).
    """
    ddl_done = False
    # Propiedad de la fila: la compensación solo puede borrar lo que ESTA
    # llamada insertó. Un INSERT duplicado pertenece a OTRO proceso.
    inserted = False
    # Identidad de la fila insertada por ESTA llamada (0 = no utilizable).
    ledger_id = 0
    try:
        async with db.transaction():
            # El id del ledger se captura en la MISMA sentencia (execute_insert);
            # ya no hay un `last_id()` post-hoc best-effort.
            ledger_id = await db.execute_insert(
                db.insert(
                    MIGRATIONS_TABLE,
                    {"name": name, "status": STATUS_PENDING, "sql_text": qry.sql},
                    returning="id",
                )
            )
            inserted = True
            ledger_id = ledger_id or 0
            await db.execute(qry)
            ddl_done = True
            await db.execute(
                db.update(MIGRATIONS_TABLE, {"name": name}, {"status": STATUS_APPLIED})
            )
    except Exception:
        if not db.transactional_ddl and inserted and not ddl_done:
            # El commit implícito del DDL publicó el `pending` pero el DDL no
            # corrió: limpiar la fila en una transacción nueva. En motores con
            # DDL transaccional el rollback de `db.transaction()` ya la eliminó.
            # Se borra por IDENTIDAD (`{id: ledger_id}`): `{name, status}` no
            # prueba propiedad y borraría la fila `pending` que otro runner
            # re-publicó tras nuestro rollback (WR-01 residual). Solo si el
            # motor no expone un id utilizable se usa el compare-and-delete.
            try:
                async with db.transaction():
                    if ledger_id > 0:
                        await db.execute(db.delete(MIGRATIONS_TABLE, {"id": ledger_id}))
                    else:
                        await db.execute(
                            db.delete(MIGRATIONS_TABLE, {"name": name, "status": STATUS_PENDING})
                        )
            except Exception as exc:
                # IN-01: un fallo de la compensación NO debe enmascarar el error
                # raíz del DDL; se registra y se re-lanza el original abajo.
                logger.warning("no se pudo compensar la fila pending de %s: %r", name, exc)
        elif not db.transactional_ddl and ddl_done:
            # El DDL SÍ corrió y el promote falló: la fila queda `pending` para
            # que `reconcile_migrations` la detecte y el humano la resuelva.
            logger.warning(
                "migración %s quedó en 'pending'; resuélvela con resolve_migration()",
                name,
            )
        # transactional_ddl=True: el rollback ya eliminó la fila; nada que compensar.
        raise


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


async def reconcile_migrations(db) -> None:
    """Detecta migraciones en estado ambiguo (D-02/D-03).

    API pública para el arranque de la aplicación (y llamada por los seis
    `migrate()` antes de aplicar). Un `pending` o un `rolling_back` significa
    que no sabemos si el DDL corrió, así que se falla de forma ruidosa con el
    SQL de cada fila y la instrucción de resolución. NUNCA re-ejecuta el DDL ni
    asume `applied` (eso sería el ledger mintiendo).
    """
    await _ensure_ledger(db)
    check_identifier(MIGRATIONS_TABLE, "tabla del ledger")
    rows = await db.fetch_all(
        Query(
            f"SELECT name, status, sql_text FROM {MIGRATIONS_TABLE} "
            "WHERE status IN ({0}, {1}) ORDER BY id",
            [STATUS_PENDING, STATUS_ROLLING_BACK],
        )
    )
    if not rows:
        return
    detail = "\n".join(f"  - {r['name']} [{r['status']}] SQL: {r['sql_text']}" for r in rows)
    raise MigrationError(
        "Migraciones en estado ambiguo (no se re-ejecuta DDL automáticamente).\n"
        f"{detail}\n"
        "Resuelve cada una con resolve_migration(db, name, applied=<bool>) "
        "tras verificar el catálogo real.\n"
        "Para una fila `rolling_back` cuyo `down` no corrió, restaura con "
        "resolve_migration(db, name, applied=True) y RE-EMITE "
        "rollback_migration(db, migration) para reintentar la reversión."
    )


async def resolve_migration(db, name: str, *, applied: bool) -> None:
    """Resuelve una migración ambigua (D-05/D-08/D-17).

    `applied` significa "¿debe quedar la migración registrada como aplicada?",
    NO "¿corrió el SQL?". La acción se infiere del estado actual de la fila:

    | Estado         | `applied` | Acción                  |
    |----------------|-----------|-------------------------|
    | `pending`      | `True`    | marcar `applied`        |
    | `pending`      | `False`   | borrar la fila          |
    | `rolling_back` | `True`    | restaurar `applied` y re-emitir `rollback_migration` |
    | `rolling_back` | `False`   | borrar la fila          |

    Para `rolling_back` + `applied=True` el helper solo restaura `applied`: el
    SQL del `down` NO está en el ledger (solo guarda el `up`), así que el
    operador DEBE re-emitir `rollback_migration(db, migration)` para reintentar
    la reversión (IN-01).
    """
    await _ensure_ledger(db)
    status = await _row_status(db, name)
    if status is None or status == STATUS_APPLIED:
        raise MigrationError(
            f"{name} no está en un estado ambiguo (status={status!r}); no hay nada que resolver"
        )
    if status not in (STATUS_PENDING, STATUS_ROLLING_BACK):
        raise MigrationError(f"{name} tiene un estado desconocido: {status!r}")
    async with db.transaction():
        if applied:
            await _set_status(db, name, STATUS_APPLIED)
        else:
            await _delete_row(db, name)


def migrations_from_dir(path: str) -> list[Migration]:
    """Carga las migraciones de un directorio (archivos `NNN_descripcion.py`).

    Cada archivo debe definir una variable módulo `MIGRATION` (instancia de
    `Migration`). Se cargan en orden alfabético por nombre de archivo.

    Frontera de confianza (T-03-02-02): cada archivo se importa con
    `exec_module`, es decir, se EJECUTA código Python arbitrario. El directorio
    debe estar versionado por el usuario y no ser escribible por terceros; no
    se valida ni se aísla el contenido.
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
