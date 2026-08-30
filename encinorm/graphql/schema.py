"""Construcción del `strawberry.Schema` con queries y mutations por modelo."""

from typing import Optional

import strawberry
from strawberry.schema.config import StrawberryConfig
from strawberry.types import Info

from encinorm.model.exceptions import NotFoundError
from encinorm.model.types import _field_datatype

from .filters import build_filter_input, filter_from_input
from .resolvers import cursor, db_session
from .scalars import DATATYPE_TO_TYPE
from .types import _snake, build_input, build_type


def _list_resolver(model, gtype, ftype):
    async def resolver(info: Info, filter: Optional[ftype] = None,
                       limit: Optional[int] = None,
                       page: Optional[int] = 1) -> list[gtype]:
        async with db_session(info) as conn:
            f = filter_from_input(model, filter)
            return await cursor(model, conn).search(f, limit=limit, page=page)
    return resolver


def _count_resolver(model, ftype):
    async def resolver(info: Info, filter: Optional[ftype] = None) -> int:
        async with db_session(info) as conn:
            return await cursor(model, conn).count(filter_from_input(model, filter))
    return resolver


def _pk_arg_type(model, field):
    """Tipo GraphQL del argumento de una llave primaria (`ID` solo para `id`)."""
    if field == "id":
        return strawberry.ID
    dt = _field_datatype(model, field, model.model_fields[field])
    return DATATYPE_TO_TYPE.get(dt, str)


def _pk_resolver(model, gtype, op, itype=None):
    """Construye un resolver `get`/`update`/`delete` derivado de `_primary_key`."""
    pk = list(model._primary_key)
    type_names = [f"_pk_t{i}" for i in range(len(pk))]
    sig = ", ".join(f"{f}: {tn}" for f, tn in zip(pk, type_names))
    kwargs = ", ".join(
        (f"{f}=int({f})" if f == "id" else f"{f}={f}") for f in pk
    )

    if op == "get":
        decl = f"async def resolver(info: Info, {sig}) -> Optional[gtype]:"
        body = (
            "    async with db_session(info) as conn:\n"
            f"        obj = await cursor(model, conn, {kwargs}).load()\n"
            "        return obj if obj._exists else None\n"
        )
    elif op == "update":
        decl = f"async def resolver(info: Info, {sig}, data: itype) -> gtype:"
        body = (
            "    async with db_session(info) as conn:\n"
            f"        obj = await cursor(model, conn, {kwargs}).load()\n"
            "        if not obj._exists:\n"
            "            raise NotFoundError(model._table)\n"
            "        for k, v in strawberry.asdict(data).items():\n"
            "            if v is not None:\n"
            "                setattr(obj, k, v)\n"
            "        await obj.update()\n"
            f"        return await cursor(model, conn, {kwargs}).load()\n"
        )
    else:  # delete
        decl = f"async def resolver(info: Info, {sig}) -> bool:"
        body = (
            "    async with db_session(info) as conn:\n"
            f"        obj = await cursor(model, conn, {kwargs}).load()\n"
            "        if not obj._exists:\n"
            "            return False\n"
            "        await obj.delete()\n"
            "        return True\n"
        )

    src = f"{decl}\n{body}"
    ns = {
        "__name__": __name__,
        "Info": Info,
        "Optional": Optional,
        "strawberry": strawberry,
        "db_session": db_session,
        "cursor": cursor,
        "model": model,
        "gtype": gtype,
        "itype": itype,
        "NotFoundError": NotFoundError,
    }
    for i, f in enumerate(pk):
        ns[f"_pk_t{i}"] = _pk_arg_type(model, f)
    exec(src, ns)
    return ns["resolver"]


def _get_resolver(model, gtype):
    return _pk_resolver(model, gtype, "get")


def _create_resolver(model, gtype, itype):
    async def resolver(info: Info, data: itype) -> gtype:
        async with db_session(info) as conn:
            obj = model(conn, **strawberry.asdict(data))
            await obj.insert()
            return await cursor(
                model, conn, **{f: getattr(obj, f) for f in model._primary_key}
            ).load()
    return resolver


def _update_resolver(model, gtype, itype):
    return _pk_resolver(model, gtype, "update", itype)


def _delete_resolver(model):
    return _pk_resolver(model, None, "delete")


def _build_query(models, type_map, filter_map):
    fields = {}
    for model in models:
        table = model._table
        singular = _snake(model.__name__)
        gtype = type_map[model]
        ftype = filter_map[model]

        fields[table] = strawberry.field(
            resolver=_list_resolver(model, gtype, ftype))
        fields[f"{table}_count"] = strawberry.field(
            resolver=_count_resolver(model, ftype))
        fields[singular] = strawberry.field(
            resolver=_get_resolver(model, gtype))

    return strawberry.type(type("Query", (), fields))


def _build_mutation(models, type_map, input_map):
    fields = {}
    for model in models:
        singular = _snake(model.__name__)
        gtype = type_map[model]
        itype = input_map[model]

        fields[f"{singular}_create"] = strawberry.field(
            resolver=_create_resolver(model, gtype, itype))
        fields[f"{singular}_update"] = strawberry.field(
            resolver=_update_resolver(model, gtype, itype))
        fields[f"{singular}_delete"] = strawberry.field(
            resolver=_delete_resolver(model))

    return strawberry.type(type("Mutation", (), fields))


def build_schema(models, *, auto_camel_case: bool = False) -> strawberry.Schema:
    """Construye un `strawberry.Schema` con queries y mutations para `models`.

    Los resolvers obtienen la conexión desde `context_value={"db": db}`.
    """
    import sys

    module_name = __name__
    module = sys.modules[module_name]

    type_map = {}
    for model in models:
        typ = build_type(model, module_name)
        type_map[model] = typ
        setattr(module, model.__name__, typ)

    input_map = {m: build_input(m) for m in models}
    filter_map = {}
    for model in models:
        ftype = build_filter_input(model, module_name)
        filter_map[model] = ftype
        setattr(module, f"{model.__name__}Filter", ftype)

    query = _build_query(models, type_map, filter_map)
    mutation = _build_mutation(models, type_map, input_map)

    return strawberry.Schema(
        query=query,
        mutation=mutation,
        config=StrawberryConfig(auto_camel_case=auto_camel_case),
    )
