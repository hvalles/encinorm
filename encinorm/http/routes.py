"""Generador de rutas CRUD tipadas por modelo (`register_crud`)."""

from encinorm.model import Model, Records
from encinorm.model.types import _base_type

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
    """Construye un handler `get`/`put`/`delete` con la firma derivada de la PK."""
    from fastapi import Depends, HTTPException

    pk = list(model._primary_key)
    sig = ", ".join(f"{f}: {_path_type(model, f).__name__}" for f in pk)
    kwargs = ", ".join(f"{f}={f}" for f in pk)
    pk_dict = "{" + ", ".join(f"{f!r}: {f}" for f in pk) + "}"

    if op == "get":
        decl = f"async def handler({sig}, db=Depends(get_db)):"
        body = (
            f"    obj = await _cursor(model, db, {kwargs}).load()\n"
            "    if not obj._exists:\n"
            "        raise HTTPException(404, detail='no encontrado')\n"
            "    return obj\n"
        )
    elif op == "put":
        decl = f"async def handler({sig}, data: model, db=Depends(get_db)):"
        body = (
            f"    obj = await _cursor(model, db, {kwargs}).load()\n"
            "    if not obj._exists:\n"
            "        raise HTTPException(404, detail='no encontrado')\n"
            "    for k, v in data.model_dump(exclude_unset=True).items():\n"
            "        setattr(obj, k, v)\n"
            "    await obj.update()\n"
            f"    return await _cursor(model, db, {kwargs}).load()\n"
        )
    else:  # delete
        decl = f"async def handler({sig}, physical: bool = False, db=Depends(get_db)):"
        body = (
            f"    obj = await _cursor(model, db, {kwargs}).load()\n"
            "    if not obj._exists:\n"
            "        raise HTTPException(404, detail='no encontrado')\n"
            "    await obj.delete(physical=physical)\n"
            f"    return {{**{pk_dict}, 'deleted': True}}\n"
        )

    src = f"{decl}\n{body}"
    ns = {
        "_cursor": _cursor,
        "model": model,
        "HTTPException": HTTPException,
        "Depends": Depends,
        "get_db": get_db,
    }
    exec(src, ns)
    return ns["handler"]


def register_crud(router, model: type[Model], prefix: str, *, get_db) -> None:
    """Genera POST/GET/PUT/DELETE tipados bajo `prefix`.

    `get_db` es la dependency de conexión; se inyecta explícitamente. Las rutas
    de `get`/`put`/`delete` derivan sus parámetros de `model._primary_key`
    (simple o compuesta).
    """
    from fastapi import Depends, HTTPException

    @router.post(prefix + "/", response_model=model, status_code=201)
    async def create(data: model, db=Depends(get_db)) -> model:
        obj = model(db, **data.model_dump(exclude_unset=True))
        await obj.insert()
        return await _cursor(
            model, db, **{f: getattr(obj, f) for f in model._primary_key}
        ).load()

    @router.get(prefix + "/", response_model=Records)
    async def list_(limit: int = 50, page: int = 1, sort_by: str = "",
                    filter: str = "", db=Depends(get_db)):
        return await _cursor(model, db).paginate(
            filter=filter_from_str(filter),
            limit=limit, page=page,
            sort_by=sort_from_str(sort_by),
        )

    get_handler = _build_path_handler(model, get_db, "get")
    router.get(prefix + _path_suffix(model), response_model=model)(get_handler)

    put_handler = _build_path_handler(model, get_db, "put")
    router.put(prefix + _path_suffix(model), response_model=model)(put_handler)

    delete_handler = _build_path_handler(model, get_db, "delete")
    router.delete(prefix + _path_suffix(model))(delete_handler)
