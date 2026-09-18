"""Máquina de estados del runner de migraciones (DATA-02). Fake `Db` a mano."""

import copy
from contextlib import asynccontextmanager

import pytest

from encino_orm.base import Db
from encino_orm.exceptions import MigrationError
from encino_orm.migration import (
    STATUS_APPLIED,
    STATUS_PENDING,
    STATUS_ROLLING_BACK,
    _apply,
    reconcile_migrations,
    resolve_migration,
)
from encino_orm.pool import PoolDb
from encino_orm.query import Query


class LedgerDb(Db):
    """Fake `Db` que modela el ledger y el commit implícito del DDL.

    `transaction()` restaura el snapshot de ENTRADA si `transactional_ddl` es
    True (rollback real) o el snapshot PUBLICADO por el último DDL si es False.
    Esto modela exactamente MySQL/MariaDB/Oracle: el commit implícito ocurre
    ANTES del DDL, así que lo escrito hasta ahí sobrevive al fallo.

    `insert`/`update`/`delete` devuelven marcadores (tuplas), no `Query`;
    `execute` los interpreta. Cuando recibe un `Query` (el DDL del usuario)
    publica el snapshot y luego ejecuta o falla según `fail_ddl`.
    """

    def __init__(
        self,
        *,
        transactional_ddl: bool,
        fail_ddl: bool = False,
        fail_promote: bool = False,
        fail_duplicate_insert: bool = False,
        fail_compensation: bool = False,
        last_id_available: bool = True,
    ):
        self.transactional_ddl = transactional_ddl
        self.fail_ddl = fail_ddl
        self.fail_promote = fail_promote
        self.fail_duplicate_insert = fail_duplicate_insert
        # IN-01: fuerza que el DELETE de compensación falle.
        self.fail_compensation = fail_compensation
        # False modela un motor sin `last_id()` útil (Oracle devuelve 0).
        self.last_id_available = last_id_available
        self.ledger: dict[str, dict] = {}
        # Registro de cada DELETE emitido, para verificar el borrado por
        # identidad y el compare-and-delete de la compensación (WR-01).
        self.delete_calls: list[dict] = []
        # Autoincremento del ledger y `lastrowid` de ESTA instancia (WR-01).
        self._next_id = 0
        self._last_id = 0
        self._entry: dict | None = None
        self._published: dict | None = None

    # --- ciclo de vida (stubs) ---
    async def connect(self, **kw): ...
    async def close(self): ...

    async def is_alive(self):
        return True

    async def in_transaction(self):
        return False

    async def commit(self): ...
    async def rollback(self, save_point=None): ...
    async def save_point(self, name): ...

    @asynccontextmanager
    async def transaction(self):
        self._entry = copy.deepcopy(self.ledger)
        try:
            yield self
        except Exception:
            self.ledger = copy.deepcopy(
                self._entry
                if self.transactional_ddl
                else (self._published if self._published is not None else self._entry)
            )
            raise

    # --- builders (marcadores) ---
    def insert(
        self,
        tabla,
        data,
        ignore_duplicated=False,
        replace=False,
        conflict=None,
        *,
        schema=None,
    ):
        return ("INSERT", dict(data))

    def delete(self, tabla, keys, *, schema=None):
        return ("DELETE", dict(keys))

    def update(self, tabla, keys, values, *, schema=None):
        return ("UPDATE", dict(keys), dict(values))

    async def execute(self, qry):
        if isinstance(qry, tuple):
            kind = qry[0]
            if kind == "INSERT":
                if self.fail_duplicate_insert and qry[1]["name"] in self.ledger:
                    raise RuntimeError("nombre duplicado en el ledger")
                # El ledger real asigna un `id` autoincremental; lo modelamos y
                # recordamos la identidad de la última fila insertada (WR-01).
                self._next_id += 1
                row = dict(qry[1])
                row["id"] = self._next_id
                self.ledger[qry[1]["name"]] = row
                self._last_id = self._next_id
            elif kind == "DELETE":
                # Fiel al SQL real (`DELETE ... WHERE col = {n} AND ...`): todas
                # las claves del dict deben coincidir con la fila. Soporta tanto
                # el borrado por identidad `{id}` como el compare-and-delete
                # `{name, status: pending}` (WR-01).
                keys = dict(qry[1])
                self.delete_calls.append(keys)
                if self.fail_compensation:
                    raise RuntimeError("compensación falló")
                for nombre, row in list(self.ledger.items()):
                    if all(row.get(k) == v for k, v in keys.items()):
                        self.ledger.pop(nombre, None)
                        break
            elif kind == "UPDATE":
                if self.fail_promote and qry[2].get("status") == STATUS_APPLIED:
                    raise RuntimeError("promote a applied falló")
                self.ledger[qry[1]["name"]].update(qry[2])
            return 1
        # `qry` es un `Query`: el DDL del usuario. El commit implícito publica lo
        # escrito hasta ahora ANTES de ejecutar el DDL.
        self._published = copy.deepcopy(self.ledger)
        if self.fail_ddl:
            raise RuntimeError("DDL falló")
        return 0

    async def fetch_all(self, qry):
        estados = set(qry.fields)
        return [
            dict(row) for row in self.ledger.values() if not estados or row["status"] in estados
        ]

    async def fetch_one(self, qry):
        row = self.ledger.get(qry.fields[0])
        return dict(row) if row else None

    async def fetch_many(self, qry, limit, page):
        return await self.fetch_all(qry)

    async def exists(self, qry):
        return await self.fetch_one(qry) is not None

    async def last_id(self):
        # Identidad de la última fila insertada por ESTA instancia (modela el
        # `lastrowid` de MySQL/MariaDB). 0 si no hubo INSERT o si el motor no
        # expone `last_id()` útil (Oracle).
        return self._last_id if self.last_id_available else 0

    async def migrate(self, name, qry): ...

    async def migrate_status(self):
        return list(self.ledger.values())


class ReinsertionLedgerDb(LedgerDb):
    """Simula el interleaving rollback+reinserción de WR-01 residual.

    La transacción fallida de ESTA llamada hace rollback de su fila `pending`
    (el fallo ocurre ANTES del commit implícito del DDL); acto seguido otro
    runner publica su propia fila `pending` con un `id` nuevo (autoincremento
    global). El `last_id()` de esta instancia sigue apuntando a la fila que
    ELLA insertó, así que la compensación no debe tocar la fila ajena.
    """

    @asynccontextmanager
    async def transaction(self):
        self._entry = copy.deepcopy(self.ledger)
        try:
            yield self
        except Exception:
            # Fallo ANTES del commit implícito: el rollback elimina la fila de A.
            self.ledger.clear()
            self.ledger.update(copy.deepcopy(self._entry))
            # El otro runner re-publica `pending` con un id distinto (id=2).
            self._next_id += 1
            self.ledger["v1"] = {
                "name": "v1",
                "status": STATUS_PENDING,
                "sql_text": "CREATE TABLE t",
                "id": self._next_id,
            }
            raise


DDL = Query("CREATE TABLE t (id INTEGER PRIMARY KEY)", [])


class TestApplyTwoPhase:
    @pytest.mark.asyncio
    async def test_commit_implicito_deja_pending_y_reconcile_lo_detecta(self):
        # Pitfall 8: se aserta la DETECCIÓN, no la imposibilidad.
        db = LedgerDb(transactional_ddl=False, fail_promote=True)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger["v1"]["status"] == STATUS_PENDING
        with pytest.raises(MigrationError) as exc:
            await reconcile_migrations(db)
        assert DDL.sql in str(exc.value)
        assert "v1" in str(exc.value)

    @pytest.mark.asyncio
    async def test_ddl_transaccional_no_deja_pending(self):
        db = LedgerDb(transactional_ddl=True, fail_promote=True)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger == {}
        await reconcile_migrations(db)  # no lanza

    @pytest.mark.asyncio
    async def test_fallo_del_ddl_limpia_el_pending_publicado(self):
        db = LedgerDb(transactional_ddl=False, fail_ddl=True)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger == {}
        await reconcile_migrations(db)  # no lanza

    @pytest.mark.asyncio
    async def test_aplicacion_exitosa_promueve_a_applied(self):
        db = LedgerDb(transactional_ddl=False)

        await _apply(db, "v1", DDL)

        assert db.ledger["v1"]["status"] == STATUS_APPLIED
        await reconcile_migrations(db)  # no lanza

    @pytest.mark.asyncio
    async def test_insert_duplicado_no_borra_la_fila_ajena(self):
        """WR-01: un INSERT duplicado pertenece a OTRO proceso; no se borra."""
        db = LedgerDb(transactional_ddl=False, fail_duplicate_insert=True)
        db.ledger["v1"] = {
            "name": "v1",
            "status": STATUS_APPLIED,
            "sql_text": "CREATE TABLE t",
        }

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger["v1"]["status"] == STATUS_APPLIED
        assert db.delete_calls == []

    @pytest.mark.asyncio
    async def test_compensacion_borra_solo_la_fila_pending_propia(self):
        """La compensación borra por identidad la fila que ESTA llamada insertó."""
        db = LedgerDb(transactional_ddl=False, fail_ddl=True)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger == {}
        assert db.delete_calls == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_wr01_compensacion_no_borra_la_fila_reinsertada(self):
        """WR-01 residual: el borrado por identidad no toca la fila de B.

        A inserta `pending` (id=1) y su DDL falla ANTES del commit (el rollback
        elimina su fila); B re-publica `pending` (id=2). La compensación de A
        debe borrar por `id=1` (inexistente) y dejar intacta la fila de B.
        """
        db = ReinsertionLedgerDb(transactional_ddl=False, fail_ddl=True)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        # La fila de B (id=2) sobrevive; la compensación apuntó a la de A (id=1).
        assert db.ledger["v1"]["id"] == 2
        assert db.ledger["v1"]["status"] == STATUS_PENDING
        assert db.delete_calls == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_in01_compensacion_fallida_no_enmascara_el_error_raiz(self):
        """IN-01: la excepción del DDL raíz sobrevive a un fallo de compensación."""
        db = LedgerDb(transactional_ddl=False, fail_ddl=True, fail_compensation=True)

        with pytest.raises(RuntimeError) as exc:
            await _apply(db, "v1", DDL)

        assert "DDL falló" in str(exc.value)

    @pytest.mark.asyncio
    async def test_compensacion_sin_last_id_usa_compare_and_delete(self):
        """Fallback (Oracle, `last_id()==0`): compare-and-delete `{name, pending}`."""
        db = LedgerDb(transactional_ddl=False, fail_ddl=True, last_id_available=False)

        with pytest.raises(RuntimeError):
            await _apply(db, "v1", DDL)

        assert db.ledger == {}
        assert db.delete_calls == [{"name": "v1", "status": STATUS_PENDING}]


def _seed(name: str, status: str) -> LedgerDb:
    db = LedgerDb(transactional_ddl=True)
    db.ledger[name] = {"name": name, "status": status, "sql_text": "CREATE TABLE t"}
    return db


class TestResolveMigration:
    @pytest.mark.asyncio
    async def test_pending_true_marca_applied(self):
        db = _seed("v1", STATUS_PENDING)
        await resolve_migration(db, "v1", applied=True)
        assert db.ledger["v1"]["status"] == STATUS_APPLIED

    @pytest.mark.asyncio
    async def test_pending_false_borra_la_fila(self):
        db = _seed("v1", STATUS_PENDING)
        await resolve_migration(db, "v1", applied=False)
        assert "v1" not in db.ledger

    @pytest.mark.asyncio
    async def test_rolling_back_false_borra_la_fila(self):
        db = _seed("v1", STATUS_ROLLING_BACK)
        await resolve_migration(db, "v1", applied=False)
        assert "v1" not in db.ledger

    @pytest.mark.asyncio
    async def test_rolling_back_true_restaura_applied(self):
        db = _seed("v1", STATUS_ROLLING_BACK)
        await resolve_migration(db, "v1", applied=True)
        assert db.ledger["v1"]["status"] == STATUS_APPLIED
        # Comportamiento: la fila deja de ser ambigua para la reconciliación.
        await reconcile_migrations(db)  # no lanza

    @pytest.mark.asyncio
    async def test_fila_inexistente_lanza(self):
        db = _seed("v1", STATUS_PENDING)
        with pytest.raises(MigrationError):
            await resolve_migration(db, "otra", applied=True)

    @pytest.mark.asyncio
    async def test_fila_ya_applied_lanza(self):
        db = _seed("v1", STATUS_APPLIED)
        with pytest.raises(MigrationError):
            await resolve_migration(db, "v1", applied=False)

    @pytest.mark.asyncio
    async def test_reconcile_error_text_instruye_reintentar_rollback(self):
        """IN-01: el error de reconciliación nombra la re-emisión del rollback."""
        db = _seed("v1", STATUS_ROLLING_BACK)
        with pytest.raises(MigrationError) as exc:
            await reconcile_migrations(db)
        assert "rollback_migration" in str(exc.value)


@pytest.mark.asyncio
async def test_reconcile_migrations_on_pool_ensures_ledger(tmp_path):
    """WARNING 5: el pool crea el ledger antes de cualquier `migrate()`."""
    pool = PoolDb(
        "sqlite",
        min_size=1,
        max_size=2,
        database=str(tmp_path / "reconcile.db"),
    )
    await pool.connect()
    try:
        await reconcile_migrations(pool)  # no lanza: la delegación crea el ledger
        rows = await pool.fetch_all(
            Query("SELECT name FROM sqlite_master WHERE name = '_encino_orm_migrations'", [])
        )
        assert len(rows) == 1
    finally:
        await pool.close()
