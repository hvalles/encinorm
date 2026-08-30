"""Generación de ObjectType/Input desde un `Model`."""

import re
from typing import Annotated, Optional

import strawberry

from encinorm.model.types import _field_datatype

from .resolvers import _has_many_resolver, _ref_resolver
from .scalars import DATATYPE_TO_TYPE

# Campos heredados que no forman parte del input de escritura.
_AUTO = ("id", "enabled", "created_at", "updated_at")


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _graphql_annotation(model, field):
    info = model.model_fields[field]
    dt = _field_datatype(model, field, info)
    base = DATATYPE_TO_TYPE.get(dt, str)
    if field == "id":
        base = strawberry.ID
    if not info.is_required():
        base = Optional[base]
    return base


def build_type(model, module_name: str):
    """Devuelve un `strawberry.ObjectType` con campos escalares y relaciones."""
    annotations = {
        f: _graphql_annotation(model, f)
        for f in model.model_fields if not f.startswith("_")
    }
    namespace = {"__annotations__": annotations}

    for name, spec in model._references_def.items():
        child = spec["model"]
        annotations[name] = Optional[
            Annotated[child.__name__, strawberry.lazy(module_name)]
        ]
        namespace[name] = strawberry.field(
            resolver=_ref_resolver(name, child, module_name))

    for name, spec in model._has_many_def.items():
        child = spec["model"]
        annotations[name] = Optional[
            list[Annotated[child.__name__, strawberry.lazy(module_name)]]
        ]
        namespace[name] = strawberry.field(
            resolver=_has_many_resolver(name, child, module_name))

    cls = type(model.__name__ or model._table, (), namespace)
    return strawberry.type(cls)


def build_input(model):
    """Devuelve un `strawberry.input` para create/update (sin campos automáticos)."""
    annotations = {}
    defaults = {}
    for f, info in model.model_fields.items():
        if f.startswith("_") or f in _AUTO:
            continue
        annotations[f] = _graphql_annotation(model, f)
        if not info.is_required():
            defaults[f] = None
    namespace = {"__annotations__": annotations, **defaults}
    cls = type(f"{model.__name__}Input", (), namespace)
    return strawberry.input(cls)
