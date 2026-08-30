"""Conexión por defecto / ambiente para `Model` sin `db` explícito.

Proporciona un "singleton" de conexión (por proceso) y un enlace ambiente por
tarea/contexto (`contextvars`), de modo que los `Model` puedan resolver su
conexión de forma implícita. El orden de resolución es:

1. `db` explícito (constructor/método).
2. transacción activa del pool (`_current_connection`).
3. `bind()` / `session()` (ambiente).
4. `set_default_db()` (proceso).
5. error `ConnectionError`.
"""

import contextvars
from contextlib import contextmanager

from .exceptions import ConnectionError

# Conexión/pool por defecto de TODO el proceso (el "singleton").
_default_db = None

# Conexión ambiente por tarea/contexto (bind / session).
_ambient_db = contextvars.ContextVar("encinorm_ambient_db", default=None)


def set_default_db(db) -> None:
    """Registra la conexión o pool por defecto del proceso."""
    global _default_db
    _default_db = db


def get_default_db():
    """Devuelve la conexión/pool por defecto del proceso, o `None`."""
    return _default_db


@contextmanager
def bind(db):
    """Establece la conexión ambiente para el bloque (async-safe vía contextvar)."""
    token = _ambient_db.set(db)
    try:
        yield db
    finally:
        _ambient_db.reset(token)


def resolve_db():
    """Resuelve la conexión actual. Lanza `ConnectionError` si no hay ninguna."""
    from .pool import _current_connection  # lazy: evita import circular

    conn = _current_connection.get()        # 1. transacción activa del pool
    if conn is not None:
        return conn
    ambient = _ambient_db.get()             # 2. bind()/session()
    if ambient is not None:
        return ambient
    if _default_db is not None:             # 3. set_default_db()
        return _default_db
    raise ConnectionError(
        "Sin conexión: pasa `db`, usa `bind()`, `set_default_db()` o `session()`"
    )
