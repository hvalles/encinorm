"""Alcance por fila (multi-tenancy) vía `contextvars`.

El filtro de alcance se establece por request/corutina con el context manager
`scope(...)` y `Model.search`/`paginate`/`count` lo combinan automáticamente con
el filtro del usuario (intersección `&`).
"""

import contextvars
from contextlib import contextmanager

_scope_var = contextvars.ContextVar("encinorm_scope", default=None)


@contextmanager
def scope(filter):
    """Establece el filtro de visibilidad (tenant/usuario) para el bloque."""
    token = _scope_var.set(filter)
    try:
        yield
    finally:
        _scope_var.reset(token)


def current_scope():
    """Devuelve el `Filter` de alcance activo, o `None`."""
    return _scope_var.get()
