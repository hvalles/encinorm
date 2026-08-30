"""Subpaquete opcional `encinorm.http`: CRUD REST tipado por modelo (FastAPI).

`fastapi` es dependencia opcional; se importa de forma perezosa dentro de cada
función, por lo que `encinorm` y `encinorm.model` siguen funcionando sin ella.
"""

from .errors import install_error_handlers
from .registry import Registry, register_introspection
from .routes import register_crud
from .parsing import filter_from_str, sort_from_str


def create_crud(pool, models, *, get_db=None, prefix="/api",
                registry=None, tags=("Model",)):
    """Monta CRUD + introspección para `models` en un solo router.

    Si no se pasa `get_db`, se deriva de `session(pool)`. El `registry` se crea
    si no se inyecta (sin singleton global).
    """
    from fastapi import APIRouter
    from encinorm import session

    if get_db is None:
        async def get_db():
            async with session(pool) as conn:
                yield conn

    registry = registry or Registry()
    router = APIRouter(prefix=prefix, tags=list(tags))
    for model_cls in models:
        registry.register(model_cls)
        register_crud(router, model_cls, "/" + model_cls._table, get_db=get_db)
    register_introspection(router, registry)
    return router


__all__ = [
    "Registry",
    "register_crud",
    "register_introspection",
    "create_crud",
    "install_error_handlers",
    "filter_from_str",
    "sort_from_str",
]
