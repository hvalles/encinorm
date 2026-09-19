import asyncio
import logging
import random
import warnings
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import ClassVar

from .dialects.identifiers import check_identifier
from .query import Query

logger = logging.getLogger("encino_orm")


def _warn_last_id_deprecated():
    """Emite el `DeprecationWarning` CENTRALIZADO de `last_id()`.

    Un único punto de emisión evita seis sitios de warning en los adaptadores y
    mantiene `filterwarnings = ["error"]` manejable. `stacklevel=2` señala al
    llamador real (o al `PoolDb.last_id` que delega en este helper).
    """
    warnings.warn(
        "last_id() está deprecado; usa execute_insert(qry) o el retorno de Model.insert()",
        DeprecationWarning,
        stacklevel=2,
    )


class Db(ABC):
    MAX_TRIES = 9
    WAITERS: ClassVar[list[float]] = [x * 0.02 for x in range(1, 11)]
    MAX_WAIT = len(WAITERS) - 1

    dialect: str = ""

    # Default conservador: se asume DDL rollbackable. Cada adaptador lo fija
    # desde `dialects.strategies.TRANSACTIONAL_DDL`; el runner de migraciones lo
    # lee en runtime para saber si el rollback ya eliminó la fila `pending`.
    transactional_ddl: bool = True

    @property
    def fn(self):
        """Namespace de funciones SQL portables (`db.fn.now()`, `db.fn.date_add(...)`)."""
        from .sql import SqlFunctions

        return SqlFunctions(self.dialect)

    @abstractmethod
    async def connect(self, **kwargs): ...

    @abstractmethod
    async def close(self): ...

    @abstractmethod
    async def is_alive(self): ...

    @abstractmethod
    async def in_transaction(self): ...

    @asynccontextmanager
    async def transaction(self):
        try:
            yield
            await self.commit()
        except Exception:
            await self.rollback()
            raise

    @abstractmethod
    async def commit(self): ...

    @abstractmethod
    async def rollback(self, save_point: str | None = None): ...

    @abstractmethod
    async def save_point(self, name: str): ...

    @staticmethod
    def _check_identifier(value: str, label: str) -> str:
        """Delega en `dialects.identifiers.check_identifier`, el único punto de validación."""
        return check_identifier(value, label)

    @staticmethod
    async def wait(waiter: int = -1):
        """Mecanismo de espera en caso de bloqueo por deadlock en la base de datos."""
        if waiter < 0:
            waiter = random.randint(0, Db.MAX_WAIT)
        await asyncio.sleep(Db.WAITERS[waiter])
        return waiter

    def is_lock_error(self, exc: Exception) -> bool:
        """Indica si `exc` corresponde a un error de bloqueo/deadlock re-reintentable."""
        return False

    def is_disconnect_error(self, exc: Exception) -> bool:
        """Indica si `exc` corresponde a una pérdida de conexión (RESL-01).

        Hook por defecto: `False`; cada adaptador lo sobreescribe con los
        códigos/tipos de su driver. **Nunca** puede solaparse con
        `is_lock_error`: un lock se reintenta con `retry()` (con backoff),
        mientras que una desconexión no se reintenta ciegamente (evita duplicar
        una escritura en silencio). Un error de lock clasificado aquí rompería
        el reintento por deadlock.
        """
        return False

    async def retry(self, coro, tries: int | None = None):
        """Reintenta una coroutine ante errores de bloqueo (deadlock)."""
        max_tries = tries if tries is not None else self.MAX_TRIES
        last_exc = None
        for attempt in range(max_tries):
            try:
                return await coro()
            except Exception as exc:
                if not self.is_lock_error(exc):
                    raise
                last_exc = exc
                if attempt + 1 >= max_tries:
                    break
                await self.wait()
        raise last_exc

    @abstractmethod
    def insert(
        self,
        tabla: str,
        data: dict,
        ignore_duplicated=False,
        replace=False,
        conflict: list[str] | None = None,
        *,
        schema: str | None = None,
        returning: str | None = None,
    ): ...

    @abstractmethod
    def delete(self, tabla: str, keys: dict, *, schema: str | None = None): ...

    @abstractmethod
    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None): ...

    @abstractmethod
    async def execute(self, qry: Query): ...

    @abstractmethod
    async def execute_insert(self, qry: Query) -> int | None:
        """Ejecuta un INSERT y devuelve el id capturado en la MISMA sentencia.

        `None` significa "id no disponible" (p. ej. un `MERGE`, que no expone el
        id en la frontera del driver). Solo los adaptadores conocen el mecanismo
        nativo (`lastrowid`/`RETURNING`/`OUTPUT INSERTED`/`RETURNING INTO`); el
        `Query` transporta la metadata `returns_id`/`id_column` que fija
        `build_insert(returning=...)`.
        """
        ...

    @abstractmethod
    async def fetch_all(self, qry: Query): ...

    @abstractmethod
    async def fetch_one(self, qry: Query): ...

    @abstractmethod
    async def fetch_many(self, qry: Query, limit: int, page: int): ...

    @abstractmethod
    async def exists(self, qry: Query): ...

    async def last_id(self):
        """DEPRECADO: usa `execute_insert(qry)` o el retorno de `Model.insert()`.

        El id post-hoc es incorrecto bajo concurrencia (session-scoped en
        PostgreSQL/MSSQL) y devuelve el id de OTRA fila sin error. Emite un
        `DeprecationWarning` centralizado y delega en `_last_id_value()`.
        """
        _warn_last_id_deprecated()
        return await self._last_id_value()

    async def _last_id_value(self) -> int:
        """Id de la última inserción de ESTA conexión (0 si no está disponible).

        Método concreto y sobreescribible por adaptador: los dobles de test no
        necesitan implementarlo. No emite warning; `last_id()` es quien lo hará.
        """
        return 0

    @abstractmethod
    async def migrate(self, name: str, qry: Query): ...

    @abstractmethod
    async def migrate_status(self): ...

    def _tables_sql(self) -> str:
        """SQL base que lista las tablas del catálogo (por motor).

        Opcional: los motores que no lo implementen no soportan `list_tables`.
        """
        raise NotImplementedError("introspección no soportada para este motor")

    async def columns_of(self, table: str) -> list:
        """Devuelve la especificación de columnas de una tabla (por motor).

        Opcional: los motores que no lo implementen no soportan `columns_of`.
        """
        raise NotImplementedError("introspección no soportada para este motor")

    async def list_tables(self, *, name: str = "", limit: int = 50, page: int = 1):
        """Lista las tablas del catálogo con filtro por nombre y paginación."""
        from .model.records import Records

        base = self._tables_sql()
        params = []
        sql = base
        if name:
            # `name` es un ALIAS de SELECT en 5 de los 6 dialectos
            # (`tablename AS name`, `table_name AS name`, `TABLE_NAME AS name`):
            # PostgreSQL, MySQL, SQL Server y Oracle NO permiten referenciar un
            # alias de columna en `WHERE` (solo SQLite tiene una columna real
            # `name`). Envolver el SQL base en una tabla derivada expone `name`
            # como columna REAL, válido en los seis motores.
            #
            # `LOWER()` en AMBOS lados: Oracle devuelve los nombres de tabla en
            # MAYÚSCULAS y PostgreSQL es sensible a mayúsculas por defecto, así
            # que sin normalizar el MISMO `name=` no funcionaría en los seis.
            # No relaja la seguridad: el valor sigue ligado como `{0}`.
            sql = "SELECT * FROM (" + base + ") encino_orm_tables WHERE LOWER(name) LIKE LOWER({0})"
            params.append(f"%{name}%")
        # El alias no puede empezar por `_`: Oracle lo rechaza (ORA-00911) salvo
        # que se cite. `encino_orm_count` y `encino_orm_tables` son válidos en
        # los seis motores.
        count_qry = Query(f"SELECT COUNT(*) AS n FROM ({sql}) encino_orm_count", params)
        row = await self.fetch_one(count_qry)
        total = row["n"] if row else 0
        rows = await self.fetch_many(Query(sql, params), limit, page)
        return Records(rows=rows, total=total, limit=limit, page=page)

    async def paginate(self, qry: Query, limit: int, page: int = 1):
        """Devuelve un `Records` con la página y el total de un `Query` raw.

        El total se calcula envolviendo el SQL en
        ``SELECT COUNT(*) AS n FROM (...)``, por lo que solo es fiable para
        SELECT simples (sin ``;`` final, sin su propio ``LIMIT``/``OFFSET`` y sin
        cláusulas no re-embebibles como ``FOR UPDATE``). Conviene incluir
        ``ORDER BY`` en el SQL para una paginación estable.
        """
        from .model.records import Records

        rows = await self.fetch_many(qry, limit, page)
        sql = qry.sql_template.strip().rstrip(";")
        count_qry = Query(f"SELECT COUNT(*) AS n FROM ({sql}) encino_orm_count", list(qry.fields))
        row = await self.fetch_one(count_qry)
        total = row["n"] if row else 0
        return Records(rows=rows, total=total, limit=limit, page=page)
