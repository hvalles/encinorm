"""Generador de rutas CRUD tipadas por modelo (`register_crud`)."""

from inspect import Parameter, Signature
from typing import Annotated

from encino_orm.model import DEFAULT_LIMIT, MAX_LIMIT, Model, Records
from encino_orm.model.types import _base_type

from .parsing import filter_from_str, sort_from_str


def _cursor(model: type[Model], db, **fields) -> Model:
    """Instancia sin validación para invocar `load()`/`paginate()` sobre modelos
    con campos requeridos (que no se pueden construir vacíos)."""
    return model.cursor(db, **fields)


def _path_type(model, field):
    """Tipo de path param (int o str) para un campo de la clave primaria."""
    base = _base_type(model.model_fields[field].annotation)
    return int if base is int else str


def _path_suffix(model) -> str:
    return "/" + "/".join("{" + f + "}" for f in model._primary_key)


def _build_path_handler(model, get_db, op):
    """Construye un handler `get`/`put`/`delete` con la firma derivada de la PK.

    Sustituye la generación con `exec()` por closures con una `inspect.Signature`
    explícita en `__signature__`: FastAPI la lee tal cual (`inspect.signature`
    devuelve `__signature__`) y deriva de ella los path params, la validación y
    el `operationId`. Los nombres (`model`, `HTTPException`, `Depends`,
    `get_db`) se resuelven por cierre, sin `__globals__` frágil ni `S102`.
    """
    from fastapi import Depends, HTTPException

    pk = list(model._primary_key)

    if op == "get":

        async def handler(**kwargs):
            db = kwargs.pop("db")
            obj = await _cursor(model, db, **kwargs).load()
            if not obj._exists:
                raise HTTPException(404, detail="no encontrado")
            return obj

    elif op == "put":

        async def handler(data, **kwargs):
            db = kwargs.pop("db")
            obj = await _cursor(model, db, **kwargs).load()
            if not obj._exists:
                raise HTTPException(404, detail="no encontrado")
            for k, v in data.model_dump(exclude_unset=True).items():
                if k in ("id", "enabled", "created_at", "updated_at"):
                    continue
                setattr(obj, k, v)
            await obj.update()
            return await _cursor(model, db, **kwargs).load()

    else:  # delete

        async def handler(physical: bool = False, **kwargs):
            db = kwargs.pop("db")
            obj = await _cursor(model, db, **kwargs).load()
            if not obj._exists:
                raise HTTPException(404, detail="no encontrado")
            await obj.delete(physical=physical)
            return {**kwargs, "deleted": True}

    params = [
        Parameter(f, Parameter.POSITIONAL_OR_KEYWORD, annotation=_path_type(model, f)) for f in pk
    ]
    if op == "put":
        params.append(Parameter("data", Parameter.POSITIONAL_OR_KEYWORD, annotation=model))
    elif op == "delete":
        params.append(
            Parameter("physical", Parameter.POSITIONAL_OR_KEYWORD, default=False, annotation=bool)
        )
    # `db` como DEPENDENCIA: `default=Depends(...)` y SIN `annotation` (Pitfall 5).
    params.append(Parameter("db", Parameter.POSITIONAL_OR_KEYWORD, default=Depends(get_db)))
    handler.__signature__ = Signature(params)
    # El nombre preserva el `operationId` de OpenAPI (`generate_unique_id` usa
    # `endpoint.__name__`); ver Pitfall 3.
    handler.__name__ = "handler"
    handler.__qualname__ = "handler"
    return handler


def register_crud(router, model: type[Model], prefix: str, *, get_db) -> None:
    """Genera POST/GET/PUT/DELETE tipados bajo `prefix`.

    `get_db` es la dependency de conexión; se inyecta explícitamente. Las rutas
    de `get`/`put`/`delete` derivan sus parámetros de `model._primary_key`
    (simple o compuesta).
    """
    from fastapi import Depends, Query

    @router.post(prefix + "/", response_model=model, status_code=201)
    async def create(data: model, db: Annotated[object, Depends(get_db)]) -> model:
        obj = model(db, **data.model_dump(exclude_unset=True))
        await obj.insert()
        return await _cursor(model, db, **{f: getattr(obj, f) for f in model._primary_key}).load()

    @router.get(prefix + "/", response_model=Records)
    async def list_(
        limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
        page: int = Query(1, ge=1),
        sort_by: str = "",
        filter: str = "",
        db: Annotated[object, Depends(get_db)] = None,
    ):
        return await _cursor(model, db).paginate(
            filter=filter_from_str(filter),
            limit=limit,
            page=page,
            sort_by=sort_from_str(sort_by),
        )

    get_handler = _build_path_handler(model, get_db, "get")
    router.get(prefix + _path_suffix(model), response_model=model)(get_handler)

    put_handler = _build_path_handler(model, get_db, "put")
    router.put(prefix + _path_suffix(model), response_model=model)(put_handler)

    delete_handler = _build_path_handler(model, get_db, "delete")
    router.delete(prefix + _path_suffix(model))(delete_handler)
