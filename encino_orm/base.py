import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import ClassVar

from .dialects.identifiers import check_identifier
from .exceptions import ConnectionError as OrmConnectionError
from .exceptions import (
    ConnectionLostError,
    EncinoOrmError,
    OperationalError,
)
from .query import Query

logger = logging.getLogger("encino_orm")


class Db(ABC):
    MAX_TRIES = 9
    WAITERS: ClassVar[list[float]] = [x * 0.02 for x in range(1, 11)]
    MAX_WAIT = len(WAITERS) - 1

    dialect: str = ""

    # Default conservador: se asume DDL rollbackable. Cada adaptador lo fija
    # desde `dialects.strategies.TRANSACTIONAL_DDL`; el runner de migraciones lo
    # lee en runtime para saber si el rollback ya eliminó la fila `pending`.
    transactional_ddl: bool = True

    # Política de reciclado para conexiones DIRECTAS (RESL-03), OPT-IN: el
    # default es conservador porque `pre_ping` añade un round-trip (`is_alive()`)
    # por operación. Se fijan por INSTANCIA desde `connect(**kwargs)` — nunca por
    # constructor, porque `PoolDb._create_connection` y `create_db` construyen
    # `cls()` sin argumentos y un `__init__` con parámetros los rompería.
    # `max_connection_lifetime` mide EDAD de conexión (semántica de
    # `pool_recycle`), no inactividad: esa la cubre el reaper del pool (Fase 4).
    pre_ping: bool = False
    max_connection_lifetime: float | None = None

    # Estado de conexión para la auto-reconexión (RESL-02). Cada adaptador los
    # fija por instancia en `__init__`/`connect()`. `_connect_kwargs` guarda los
    # kwargs ORIGINALES de `connect(**kwargs)` para poder reconectar in-place y
    # **puede contener `password`**: nunca debe loguearse. `_connected_at` usa
    # `time.monotonic()` (nunca el reloj de pared, inmune a saltos de hora) y
    # vale `None` mientras no haya una conexión viva; `close()` lo limpia para
    # no resucitar una conexión cerrada a propósito.
    _connect_kwargs: dict | None = None
    _connected_at: float | None = None

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
        last_exc: Exception | None = None
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
        if last_exc is None:
            raise RuntimeError("retry() no ejecutó ningún intento")
        raise last_exc

    # --- Resiliencia: traducción de excepciones de driver (RESL-04) ---

    def _translate_error(self, exc: Exception) -> Exception:
        """Hook por adaptador: mapea la excepción de su driver a la taxonomía.

        El default no conoce drivers (contrato de importación diferida) y degrada
        a `OperationalError`. Cada adaptador lo sobreescribe reutilizando sus
        helpers de clasificación (`is_unique_violation`, `_native_code`,
        `_ora_code`). NO construye SQL ni interpola valores; el mensaje incluye
        `str(exc)` del driver y **nunca** `_connect_kwargs` (contienen `password`).
        """
        return OperationalError(str(exc))

    def _translate_exception(self, exc: Exception) -> Exception:
        """Punto ÚNICO de traducción driver → taxonomía de la librería.

        Orden EXACTO (el cortocircuito de lock es lo PRIMERO):

        1. `is_lock_error(exc)` → devuelve `exc` SIN traducir: `retry()` clasifica
           sobre el ORIGINAL y traducirlo rompería el reintento por deadlock
           (Pitfall 3 / T-05-04-01).
        2. Ya es `EncinoOrmError` → devuelve `exc` tal cual (idempotente: no se
           re-traduce una excepción de la librería).
        3. `is_disconnect_error(exc)` → `ConnectionLostError`.
        4. En otro caso → `self._translate_error(exc)` (hook del adaptador).

        NO traga la excepción: devuelve la instancia a lanzar; `_with_reconnect`
        es quien relanza con `raise ... from exc` para preservar la causa del
        driver (desviación deliberada de la convención "sin chaining", ASVS V7).
        """
        if self.is_lock_error(exc):
            return exc
        if isinstance(exc, EncinoOrmError):
            return exc
        if self.is_disconnect_error(exc):
            return ConnectionLostError(str(exc))
        return self._translate_error(exc)

    # --- Resiliencia: auto-reconexión única fuera de transacción (RESL-02) ---

    def _is_reconnectable(self, exc: Exception) -> bool:
        """Indica si `exc` justifica un intento de reconexión (una sola vez).

        Cubre los DOS caminos reales de una desconexión:

        1. La excepción del driver (`is_disconnect_error`), típica de una caída
           mid-statement.
        2. La `ConnectionError` de la librería lanzada por `_ensure_connected()`
           cuando la conexión murió **en reposo** (Pitfall 1): el driver marca
           `closed`/`is_closed()` y la sentencia nunca llega a enviarse, así que
           la excepción es de la librería, no del driver. Exige
           `_connected_at is not None` para no "reconectar" una conexión que
           nunca existió.

        Nunca devuelve True para un lock: `is_disconnect_error` es mutuamente
        excluyente con `is_lock_error` (RESL-01) y `OrmConnectionError` no lo es.
        """
        if self.is_disconnect_error(exc):
            return True
        return isinstance(exc, OrmConnectionError) and self._connected_at is not None

    async def _reconnect(self) -> None:
        """Reconecta **in-place** reusando los kwargs originales de `connect()`.

        Es un no-op si nunca hubo una conexión viva (`_connected_at is None`) o
        si no se guardaron kwargs: no se resucita una conexión que no existió.
        El `close()` va envuelto en `try/except` (Pitfall 6: defensa barata ante
        drivers que fallan al cerrar una conexión rota). No reasigna el objeto
        driver: el handle del pool de Fase 4 debe seguir siendo válido.

        Nunca loguea `_connect_kwargs` (contienen `password`).
        """
        kwargs = self._connect_kwargs
        if self._connected_at is None or kwargs is None:
            return
        try:
            await self.close()
        except Exception:
            logger.warning("fallo al cerrar la conexión antes de reconectar", exc_info=True)
        await self.connect(**kwargs)

    # --- Resiliencia: política `pre_ping` / `max_connection_lifetime` (RESL-03) ---

    def _resilience_opts(self, kwargs: dict) -> dict:
        """Extrae las opciones de resiliencia ANTES de reenviar `kwargs` al driver.

        Hace `pop` de `pre_ping`/`max_connection_lifetime`, las normaliza y las
        fija por instancia. Devuelve el dict SIN esas dos claves, listo para
        guardarse en `_connect_kwargs` y reenviarse al driver: si llegasen al
        driver, `aiomysql.connect(**kwargs)`/`asyncpg.connect(**kwargs)` fallarían
        con un kwarg desconocido y la construcción de `conn_str`/`dsn` recibiría
        datos de más.

        Falla cerrado: un `max_connection_lifetime` no-`None` `<= 0` lanza
        `ValueError` (mismo criterio que `check_identifier` para argumentos
        inválidos). `None` desactiva el reciclado por edad sin error.
        """
        pre_ping = bool(kwargs.pop("pre_ping", self.pre_ping))
        lifetime = kwargs.pop("max_connection_lifetime", self.max_connection_lifetime)
        if lifetime is not None:
            lifetime = float(lifetime)
            if lifetime <= 0:
                raise ValueError(
                    f"max_connection_lifetime debe ser un número positivo: {lifetime!r}"
                )
        # Se asignan DESPUÉS de validar ambos (IN-03): un `lifetime` inválido no
        # debe dejar `pre_ping` cambiado en la instancia.
        self.pre_ping = pre_ping
        self.max_connection_lifetime = lifetime
        return kwargs

    def _should_recycle(self) -> bool:
        """Indica si la conexión superó su vida máxima (EDAD, no inactividad).

        `False` si nunca hubo conexión (`_connected_at is None`) o si el límite
        está desactivado (`None`). El reloj es `time.monotonic()` — el mismo del
        pool (`pool.py`) e inmune a saltos de hora —, nunca el reloj de pared.
        """
        if self._connected_at is None:
            return False
        if self.max_connection_lifetime is None:
            return False
        return time.monotonic() - self._connected_at >= self.max_connection_lifetime

    async def _maybe_recycle(self) -> None:
        """Recicla proactivamente la conexión directa antes de usarla (RESL-03).

        Chequeo PEREZOSO y por operación (sin daemon ni tarea de fondo),
        invocado al ENTRAR en `_with_reconnect`. Es un no-op si nunca hubo
        conexión (`_connected_at is None`): no se recicla lo que no existió.

        - Si se superó `max_connection_lifetime` → reconecta.
        - Si `pre_ping` está activo y `is_alive()` es `False` → reconecta
          INMEDIATAMENTE (Pitfall 5: `aiomysql.ping(reconnect=False)` sobre una
          conexión muerta la deja inutilizable; anotar el fallo sin reconectar no
          basta).

        No emite warnings (el proyecto corre con `filterwarnings = ["error"]`) ni
        loguea `_connect_kwargs` (contienen `password`).

        GUARDA DE TRANSACCIÓN (CR-01): si hay una transacción abierta NO se
        recicla. `close()` revertiría el trabajo no confirmado en silencio y las
        sentencias posteriores correrían FUERA de la transacción; el reciclado
        proactivo nunca puede tocar una transacción abierta.
        """
        if self._connected_at is None:
            return
        if await self.in_transaction():
            return
        if self._should_recycle():
            await self._reconnect()
            return
        if self.pre_ping and not await self.is_alive():
            await self._reconnect()

    def _raise_translated(self, exc: Exception):
        """Relanza `exc` traducida, encadenando SOLO si cambia de instancia (IN-04).

        `_translate_exception` devuelve la MISMA instancia para un lock o una
        excepción ya de la librería; en ese caso se relanza tal cual para no
        crear un `__cause__` auto-referencial.
        """
        translated = self._translate_exception(exc)
        if translated is exc:
            raise
        raise translated from exc

    async def _with_reconnect(self, fn, *, is_read: bool):
        """Ejecuta `fn()` y, ante una desconexión fuera de transacción, reconecta.

        Template method (RESL-02) que centraliza la clasificación y la
        recuperación. `fn` es un callable sin argumentos que devuelve una
        corrutina. Reglas EXACTAS:

        - Clasifica la excepción **original** con `_is_reconnectable`. Si no es
          reconectable (p. ej. un error de sintaxis o un lock), la relanza sin
          tocar la conexión.
        - Dentro de una transacción (`await self.in_transaction()` True) NUNCA
          reconecta ni reintenta: relanza. Un write pudo haber llegado al
          servidor antes de morir el socket; reintentarlo duplicaría datos.
        - Fuera de transacción reconecta **EXACTAMENTE UNA VEZ**, sin bucle ni
          backoff, y aplica la política A2:
          * **Lecturas** (`is_read=True`, `fetch_*`): idempotentes → re-ejecuta.
          * **Escrituras pre-ejecución** (`is_read=False` pero `fn` lanzó la
            `ConnectionError` de la librería): la sentencia nunca llegó al
            driver, así que re-ejecutar es su PRIMERA ejecución, no un
            reintento.
          * **Escrituras mid-statement** (`is_read=False` y excepción de driver):
            el servidor pudo haber aplicado el write → reconecta pero RELANZA
            el error original, sin re-ejecutar (nunca duplica en silencio).

        El camino de lock queda estrictamente separado: `_with_reconnect` nunca
        reintenta un lock (eso es de `retry()`, con backoff) y relanza la MISMA
        instancia (sin traducir) para que `retry()` siga reconociéndola.

        Todo relanzado pasa por `_translate_exception` (RESL-04) y usa
        `raise ... from exc` para preservar la causa del driver: es una
        DESVIACIÓN DELIBERADA de la convención "sin chaining" del repo,
        justificada por ASVS V7 (diagnóstico del error de driver) y registrada en
        `docs/engines.md`/`CHANGELOG.md`. El fallo de `_reconnect()` también se
        traduce para que no escape una excepción de driver cruda.

        Antes del `try` principal se ejecuta `_maybe_recycle()`: un chequeo
        PROACTIVO, PEREZOSO (sin daemon) y opt-in de `pre_ping`/
        `max_connection_lifetime` (RESL-03). Con los defaults (`False`/`None`) es
        un no-op sin coste en el camino caliente. Su fallo se traduce (WR-01)
        pero NO dispara otra reconexión: ya intentó reconectar y falló.
        """
        try:
            await self._maybe_recycle()
        except Exception as exc:
            self._raise_translated(exc)
        try:
            return await fn()
        except Exception as exc:
            if not self._is_reconnectable(exc):
                self._raise_translated(exc)
            if await self.in_transaction():
                self._raise_translated(exc)
            pre_execution = isinstance(exc, OrmConnectionError)
            try:
                await self._reconnect()
            except Exception as rexc:
                self._raise_translated(rexc)
            if is_read or pre_execution:
                try:
                    return await fn()
                except Exception as exc2:
                    self._raise_translated(exc2)
            self._raise_translated(exc)

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

    # --- Ejecución / Consulta (wrappers concretos → privados del adaptador) ---
    #
    # Los públicos son CONCRETOS y envuelven a los privados `_`-prefijados con
    # `_with_reconnect`. Los privados también son CONCRETOS y lanzan
    # `NotImplementedError` (NO `@abstractmethod`): los dobles de test que
    # heredan de `Db` y sobreescriben solo el público siguen instanciándose
    # (Pitfall 10). `PoolDb` sobreescribe los públicos y nunca entra aquí.

    async def execute(self, qry: Query):
        return await self._with_reconnect(lambda: self._execute(qry), is_read=False)

    async def _execute(self, qry: Query):
        raise NotImplementedError("execute() no implementado para este motor")

    async def execute_insert(self, qry: Query) -> int | None:
        """Ejecuta un INSERT y devuelve el id capturado en la MISMA sentencia.

        `None` significa "id no disponible" (p. ej. un `MERGE`, que no expone el
        id en la frontera del driver). Solo los adaptadores conocen el mecanismo
        nativo (`lastrowid`/`RETURNING`/`OUTPUT INSERTED`/`RETURNING INTO`); el
        `Query` transporta la metadata `returns_id`/`id_column` que fija
        `build_insert(returning=...)`.
        """
        return await self._with_reconnect(lambda: self._execute_insert(qry), is_read=False)

    async def _execute_insert(self, qry: Query) -> int | None:
        raise NotImplementedError("execute_insert() no implementado para este motor")

    async def fetch_all(self, qry: Query):
        return await self._with_reconnect(lambda: self._fetch_all(qry), is_read=True)

    async def _fetch_all(self, qry: Query):
        raise NotImplementedError("fetch_all() no implementado para este motor")

    async def fetch_one(self, qry: Query):
        return await self._with_reconnect(lambda: self._fetch_one(qry), is_read=True)

    async def _fetch_one(self, qry: Query):
        raise NotImplementedError("fetch_one() no implementado para este motor")

    async def fetch_many(self, qry: Query, limit: int, page: int):
        return await self._with_reconnect(lambda: self._fetch_many(qry, limit, page), is_read=True)

    async def _fetch_many(self, qry: Query, limit: int, page: int):
        raise NotImplementedError("fetch_many() no implementado para este motor")

    @abstractmethod
    async def exists(self, qry: Query): ...

    async def _last_id_value(self) -> int:
        """Id de la última inserción de ESTA conexión (0 si no está disponible).

        Hook interno concreto y sobreescribible por adaptador: los dobles de test
        no necesitan implementarlo. NO es API pública — la captura post-hoc del
        id se retiró en `0.3.0` (REL-01); el id se obtiene con
        `execute_insert(qry)` o el retorno de `Model.insert()`.
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
