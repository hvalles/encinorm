"""Construcción del `strawberry.Schema` con queries y mutations por modelo."""

import itertools
import sys
import types
import weakref
from inspect import Parameter, Signature

import strawberry
from strawberry.schema.config import StrawberryConfig
from strawberry.types import Info

from encino_orm.model.exceptions import NotFoundError
from encino_orm.model.records import DEFAULT_LIMIT, normalize_limit_page
from encino_orm.model.types import _field_datatype

from .filters import build_filter_input, filter_from_input
from .resolvers import cursor, db_session
from .scalars import DATATYPE_TO_TYPE
from .types import _snake, build_input, build_type


def _list_resolver(model, gtype, ftype):
    async def resolver(
        info: Info,
        filter: ftype | None = None,
        limit: int | None = None,
        page: int | None = 1,
    ) -> list[gtype]:
        async with db_session(info) as conn:
            f = filter_from_input(model, filter)
            limit, page = normalize_limit_page(limit or DEFAULT_LIMIT, page)
            return await cursor(model, conn).search(f, limit=limit, page=page)

    return resolver


def _count_resolver(model, ftype):
    async def resolver(info: Info, filter: ftype | None = None) -> int:
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
    """Construye un resolver `get`/`update`/`delete` derivado de `_primary_key`.

    La firma observable (nombres, anotaciones y tipo de retorno que Strawberry
    convierte en argumentos GraphQL) se declara con `inspect.Signature` en
    `__signature__`; no se genera ni ejecuta código con `exec()`.
    """
    pk = list(model._primary_key)
    arg_types = {f: _pk_arg_type(model, f) for f in pk}

    def _cast(values):
        # Replica la coercion `id=int(id)` del cuerpo generado original.
        return {f: (int(values[f]) if f == "id" else values[f]) for f in pk}

    if op == "get":

        async def resolver(info, **kwargs):
            async with db_session(info) as conn:
                obj = await cursor(model, conn, **_cast(kwargs)).load()
                return obj if obj._exists else None

        return_annotation = gtype | None
    elif op == "update":

        async def resolver(info, data, **kwargs):
            async with db_session(info) as conn:
                obj = await cursor(model, conn, **_cast(kwargs)).load()
                if not obj._exists:
                    raise NotFoundError(model._table)
                for k, v in strawberry.asdict(data).items():
                    if v is not None:
                        setattr(obj, k, v)
                await obj.update()
                return await cursor(model, conn, **_cast(kwargs)).load()

        return_annotation = gtype
    else:  # delete

        async def resolver(info, **kwargs):
            async with db_session(info) as conn:
                obj = await cursor(model, conn, **_cast(kwargs)).load()
                if not obj._exists:
                    return False
                await obj.delete()
                return True

        return_annotation = bool

    parameters = [Parameter("info", Parameter.POSITIONAL_OR_KEYWORD, annotation=Info)]
    parameters += [
        Parameter(f, Parameter.POSITIONAL_OR_KEYWORD, annotation=arg_types[f]) for f in pk
    ]
    if op == "update":
        parameters.append(Parameter("data", Parameter.POSITIONAL_OR_KEYWORD, annotation=itype))
    resolver.__signature__ = Signature(parameters, return_annotation=return_annotation)
    resolver.__name__ = "resolver"
    resolver.__qualname__ = "resolver"
    return resolver


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

        fields[table] = strawberry.field(resolver=_list_resolver(model, gtype, ftype))
        fields[f"{table}_count"] = strawberry.field(resolver=_count_resolver(model, ftype))
        fields[singular] = strawberry.field(resolver=_get_resolver(model, gtype))

    return strawberry.type(type("Query", (), fields))


def _build_mutation(models, type_map, input_map):
    fields = {}
    for model in models:
        singular = _snake(model.__name__)
        gtype = type_map[model]
        itype = input_map[model]

        fields[f"{singular}_create"] = strawberry.field(
            resolver=_create_resolver(model, gtype, itype)
        )
        fields[f"{singular}_update"] = strawberry.field(
            resolver=_update_resolver(model, gtype, itype)
        )
        fields[f"{singular}_delete"] = strawberry.field(resolver=_delete_resolver(model))

    return strawberry.type(type("Mutation", (), fields))


_build_counter = itertools.count(1)


def build_schema(models, *, auto_camel_case: bool = False) -> strawberry.Schema:
    """Construye un `strawberry.Schema` con queries y mutations para `models`.

    Los resolvers obtienen la conexión desde `context_value={"db": db}`.

    Los tipos generados usan `strawberry.lazy(...)`, que resuelve vía
    `importlib.import_module`. Para no mutar el namespace de este módulo, cada
    build registra un módulo sintético propio en `sys.modules`.

    Ese módulo NO se puede borrar al terminar la construcción: Strawberry
    resuelve los `LazyType` de los filtros autorreferentes (`and`/`or`/`not`)
    en tiempo de *ejecución* (`LazyType.resolve_type()` no cachea), así que
    debe sobrevivir mientras el schema pueda ejecutarse. Se libera cuando el
    schema se recolecta (participa en un ciclo, de modo que lo libera el GC
    cíclico), evitando fugas permanentes en `sys.modules`.
    """
    name = f"encino_orm.graphql._build_{next(_build_counter)}"
    mod = types.ModuleType(name)
    mod.__package__ = __package__
    sys.modules[name] = mod
    try:
        type_map = {}
        for model in models:
            typ = build_type(model, name)
            type_map[model] = typ
            setattr(mod, model.__name__, typ)

        input_map = {m: build_input(m) for m in models}
        filter_map = {}
        for model in models:
            ftype = build_filter_input(model, name)
            filter_map[model] = ftype
            setattr(mod, f"{model.__name__}Filter", ftype)

        query = _build_query(models, type_map, filter_map)
        mutation = _build_mutation(models, type_map, input_map)

        schema = strawberry.Schema(
            query=query,
            mutation=mutation,
            config=StrawberryConfig(auto_camel_case=auto_camel_case),
        )
    except BaseException:
        sys.modules.pop(name, None)
        raise
    weakref.finalize(schema, sys.modules.pop, name, None)
    return schema
