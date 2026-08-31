"""Traducción de filtros GraphQL a `Filter` del ORM."""

from datetime import date, datetime
from typing import Annotated, Optional

import strawberry

from encinorm.model import Filter
from encinorm.model.types import _field_datatype

# Campos heredados que no se exponen como filtros.
_AUTO = ("enabled", "created_at", "updated_at")


@strawberry.input
class StringFilter:
    eq: str | None = None
    ne: str | None = None
    in_: list[str] | None = strawberry.field(default=None, name="in")
    like: str | None = None
    startswith: str | None = None
    endswith: str | None = None
    is_null: bool | None = None


@strawberry.input
class IntFilter:
    eq: int | None = None
    ne: int | None = None
    gt: int | None = None
    ge: int | None = None
    lt: int | None = None
    le: int | None = None
    in_: list[int] | None = strawberry.field(default=None, name="in")
    between: list[int] | None = None
    is_null: bool | None = None


@strawberry.input
class FloatFilter:
    eq: float | None = None
    ne: float | None = None
    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None
    is_null: bool | None = None


@strawberry.input
class BoolFilter:
    eq: bool | None = None
    is_null: bool | None = None


@strawberry.input
class DateTimeFilter:
    gt: datetime | None = None
    ge: datetime | None = None
    lt: datetime | None = None
    le: datetime | None = None
    is_null: bool | None = None


@strawberry.input
class DateFilter:
    gt: date | None = None
    ge: date | None = None
    lt: date | None = None
    le: date | None = None
    is_null: bool | None = None


@strawberry.input
class IdFilter:
    eq: strawberry.ID | None = None
    ne: strawberry.ID | None = None
    in_: list[strawberry.ID] | None = strawberry.field(default=None, name="in")
    is_null: bool | None = None


def _filter_type_for(dt: str, field: str):
    if field == "id":
        return IdFilter
    if dt == "int":
        return IntFilter
    if dt in ("numeric", "decimal", "float"):
        return FloatFilter
    if dt in ("bool", "tinyint"):
        return BoolFilter
    if dt == "datetime":
        return DateTimeFilter
    if dt == "date":
        return DateFilter
    return StringFilter          # str, blob, json


def build_filter_input(model, module_name: str):
    """Devuelve un input de filtro por modelo (campos + `and`/`or`/`not`)."""
    annotations = {}
    for f, info in model.model_fields.items():
        if f.startswith("_") or f in _AUTO:
            continue
        dt = _field_datatype(model, f, info)
        annotations[f] = Optional[_filter_type_for(dt, f)]

    name = f"{model.__name__}Filter"
    lazy_self = Annotated[name, strawberry.lazy(module_name)]
    annotations["and_"] = Optional[list[lazy_self]]
    annotations["or_"] = Optional[list[lazy_self]]
    annotations["not_"] = Optional[lazy_self]

    namespace = {"__annotations__": annotations}
    for f in annotations:
        if f in ("and_", "or_", "not_"):
            namespace[f] = strawberry.field(default=None, name=f[:-1])
        else:
            namespace[f] = None

    cls = type(name, (), namespace)
    return strawberry.input(cls)


def _apply_op(field: str, op: str, val) -> Filter:
    if op == "eq":
        return Filter.eq(field, val)
    if op == "ne":
        return Filter.ne(field, val)
    if op == "gt":
        return Filter.gt(field, val)
    if op == "ge":
        return Filter.ge(field, val)
    if op == "lt":
        return Filter.lt(field, val)
    if op == "le":
        return Filter.le(field, val)
    if op == "in_":
        return Filter.in_(field, val)
    if op == "like":
        return Filter.like(field, val)
    if op == "startswith":
        return Filter.startswith(field, val)
    if op == "endswith":
        return Filter.endswith(field, val)
    if op == "between":
        return Filter.between(field, val[0], val[1])
    if op == "is_null":
        return Filter.is_null(field) if val else Filter.not_null(field)
    raise ValueError(f"operador desconocido: {op}")


def _and(parts) -> Filter | None:
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    result = parts[0]
    for p in parts[1:]:
        result = result & p
    return result


def _or(parts) -> Filter | None:
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    result = parts[0]
    for p in parts[1:]:
        result = result | p
    return result


def _op_filter(field: str, scalar_filter) -> Filter | None:
    parts = []
    for op, val in vars(scalar_filter).items():
        if val is None:
            continue
        parts.append(_apply_op(field, op, val))
    return _and(parts)


def filter_from_input(model, filter_input) -> Filter | None:
    """Convierte un input de filtro GraphQL a un `Filter` del ORM."""
    if filter_input is None:
        return None
    parts = []
    and_parts = None
    or_parts = None
    not_part = None
    for field, value in vars(filter_input).items():
        if value is None:
            continue
        if field == "and_":
            and_parts = value
        elif field == "or_":
            or_parts = value
        elif field == "not_":
            not_part = value
        else:
            parts.append(_op_filter(field, value))

    result = _and(parts)
    if and_parts is not None:
        sub = _and([filter_from_input(model, x) for x in and_parts])
        result = sub if result is None else (result & sub)
    if or_parts is not None:
        sub = _or([filter_from_input(model, x) for x in or_parts])
        result = sub if result is None else (result & sub)
    if not_part is not None:
        sub = filter_from_input(model, not_part)
        result = (~sub) if result is None else (result & ~sub)
    return result
