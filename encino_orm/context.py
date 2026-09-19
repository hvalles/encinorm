"""Conexión por defecto / ambiente para `Model` sin `db` explícito.

Proporciona un `ConnectionRegistry` inyectable (el "default" de la aplicación) y
un enlace ambiente por tarea/contexto (`contextvars`), de modo que los `Model`
puedan resolver su conexión de forma implícita. El orden de resolución es:

1. `db` explícito (constructor/método).
2. transacción activa del pool (`_current_connection`).
3. `bind()` / `session()` (ambiente).
4. default del `ConnectionRegistry` (explícito o el `_registry` de módulo).
5. error `ConnectionError`.

El default ya NO es un global mutable de proceso: vive en el estado de instancia
de un `ConnectionRegistry`, de modo que dos aplicaciones/tenants en el mismo
proceso pueden resolver a bases de datos distintas sin pisarse.
"""

import contextvars
import warnings
from contextlib import contextmanager

from .exceptions import ConnectionError

# Conexión ambiente por tarea/contexto (bind / session). Es estado ambiente, no
# un global mutable de configuración: se conserva como nivel de precedencia.
_ambient_db = contextvars.ContextVar("encino_orm_ambient_db", default=None)


class ConnectionRegistry:
    """Holder inyectable de la conexión por defecto de una aplicación.

    El estado es de instancia (`_default_db`), no de módulo: dos registries en
    el mismo proceso resuelven a sus propias bases de datos. La precedencia
    ambiente (`bind`/`session`/transacción del pool) sigue ganando al default.
    """

    __slots__ = ("_default_db",)

    def __init__(self, default_db=None):
        self._default_db = default_db

    def set_default(self, db) -> None:
        """Registra la conexión o pool por defecto de este registry."""
        self._default_db = db

    def get_default(self):
        """Devuelve la conexión/pool por defecto de este registry, o `None`."""
        return self._default_db

    def resolve(self):
        """Resuelve la conexión actual. Lanza `ConnectionError` si no hay ninguna."""
        # Import perezoso dentro del método: `pool` importa `context`, así que
        # un import a nivel de módulo crearía un ciclo. `from . import pool`
        # mantiene el mismo contrato diferido sin adquirir dependencia dura.
        from . import pool

        conn = pool._current_connection.get()  # 1. transacción activa del pool
        if isinstance(conn, pool.PooledConnection):
            # El contextvar guarda el handle del pool; `Model`/`engine_of` esperan
            # un `Db` (con `.dialect` y los métodos de CRUD), así que se desenvaina.
            return conn.driver
        if conn is not None:
            return conn
        ambient = _ambient_db.get()  # 2. bind()/session()
        if ambient is not None:
            return ambient
        if self._default_db is not None:  # 3. default del registry
            return self._default_db
        raise ConnectionError(
            "Sin conexión: pasa `db`, usa `bind()`, `session()` o el default del registry"
        )


# Registry por defecto del proceso: único punto que guarda el default implícito.
_registry = ConnectionRegistry()


def set_default_db(db) -> None:
    """Registra la conexión o pool por defecto del proceso.

    Deprecado: usa un `ConnectionRegistry` explícito y su método `set_default()`.
    """
    warnings.warn(
        "set_default_db() está deprecado; usa un ConnectionRegistry explícito",
        DeprecationWarning,
        stacklevel=2,
    )
    _registry.set_default(db)


def get_default_db():
    """Devuelve la conexión/pool por defecto del proceso, o `None`.

    Deprecado: usa `ConnectionRegistry.get_default()` sobre un registry explícito.
    """
    warnings.warn(
        "get_default_db() está deprecado; usa ConnectionRegistry.get_default()",
        DeprecationWarning,
        stacklevel=2,
    )
    return _registry.get_default()


@contextmanager
def bind(db):
    """Establece la conexión ambiente para el bloque (async-safe vía contextvar)."""
    token = _ambient_db.set(db)
    try:
        yield db
    finally:
        _ambient_db.reset(token)


def resolve_db(registry: ConnectionRegistry | None = None):
    """Resuelve la conexión actual. Lanza `ConnectionError` si no hay ninguna.

    Sin argumentos usa el `_registry` de módulo, conservando el comportamiento
    histórico. Pasa `registry` para resolver contra un `ConnectionRegistry`
    explícito (aislamiento por aplicación/tenant).
    """
    # `is None` (no `or`): un registry que se evalúe como falsy no debe ignorarse
    # en silencio y caer al de módulo (WR-03).
    return (_registry if registry is None else registry).resolve()
