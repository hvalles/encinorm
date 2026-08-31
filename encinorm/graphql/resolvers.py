"""Helpers de resolución: conexión por request, cursor y relaciones."""

from contextlib import asynccontextmanager
from typing import Annotated, Any, Optional

import strawberry
from strawberry.dataloader import DataLoader
from strawberry.types import Info

from encinorm import session as _session


@asynccontextmanager
async def db_session(info):
    """Obtiene una conexión de `info.context["db"]` vía `session()`."""
    db = info.context.get("db")
    async with _session(db) as conn:
        yield conn


def cursor(model, conn, **fields):
    """Instancia sin validación para invocar `load()`/`search()`/`count()`."""
    return model.cursor(conn, **fields)


def _dataloader(info, key: str, load_fn):
    """Devuelve (y cachea por request) un `DataLoader` para `key` en `info.context`.

    Permite agrupar en una sola consulta las relaciones de una lista de padres
    (evita el N+1). El loader se comparte entre todos los resolvers del request.
    """
    ctx = info.context
    if not isinstance(ctx, dict):
        return DataLoader(load_fn=load_fn, cache_key_fn=id)
    loader = ctx.get(key)
    if loader is None:
        loader = DataLoader(load_fn=load_fn, cache_key_fn=id)
        ctx[key] = loader
    return loader


def _ref_resolver(model, name, child, module_name):
    async def load_fn(parents):
        await model.batch_reference(parents, name)
        return [await p[name] for p in parents]

    async def resolver(root: Any, info: Info) -> Optional[
        Annotated[child.__name__, strawberry.lazy(module_name)]
    ]:
        loader = _dataloader(info, f"_encinorm_ref:{model.__name__}:{name}", load_fn)
        return await loader.load(root)
    return resolver


def _has_many_resolver(model, name, child, module_name):
    async def load_fn(parents):
        await model.batch_has_many(parents, name)
        return [await p[name] for p in parents]

    async def resolver(root: Any, info: Info) -> Optional[
        list[Annotated[child.__name__, strawberry.lazy(module_name)]]
    ]:
        loader = _dataloader(info, f"_encinorm_hm:{model.__name__}:{name}", load_fn)
        return await loader.load(root)
    return resolver
