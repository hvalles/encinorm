"""Helpers de resolución: conexión por request, cursor y relaciones."""

from contextlib import asynccontextmanager
from typing import Annotated, Any, Optional

import strawberry

from encinorm import session as _session


@asynccontextmanager
async def db_session(info):
    """Obtiene una conexión de `info.context["db"]` vía `session()`."""
    db = info.context.get("db")
    async with _session(db) as conn:
        yield conn


def cursor(model, conn, **fields):
    """Instancia sin validación para invocar `load()`/`search()`/`count()`."""
    obj = model.model_construct(**fields)
    object.__setattr__(obj, "_db", conn)
    return obj


def _ref_resolver(name, child, module_name):
    async def resolver(root: Any) -> Optional[
        Annotated[child.__name__, strawberry.lazy(module_name)]
    ]:
        return await root[name]
    return resolver


def _has_many_resolver(name, child, module_name):
    async def resolver(root: Any) -> Optional[
        list[Annotated[child.__name__, strawberry.lazy(module_name)]]
    ]:
        return await root[name]
    return resolver
