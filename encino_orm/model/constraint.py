"""Clase `Constraint` y fábrica `make_constraint` para declarar columnas reutilizables."""

from dataclasses import dataclass, field
from typing import Annotated

from pydantic import AfterValidator, Field

from .column import Column
from .types import PY_TYPE_TO_DATATYPE


@dataclass(frozen=True)
class Constraint:
    """Especificación inmutable: tipo de dato + restricciones de una columna."""

    datatype: str                    # int, bool, str, datetime, date, numeric, blob, float
    required: bool = False           # False -> campo opcional (None permitido)
    name: str | None = None          # nombre de columna en la BD
    field_kwargs: dict = field(default_factory=dict)  # kwargs para pydantic.Field
    validators: tuple = ()           # funciones extra (AfterValidator)

    @classmethod
    def str(cls, min_length=None, max_length=None, pattern=None,
            required=False, name=None) -> "Constraint":
        kw = {}
        if min_length is not None:
            kw["min_length"] = min_length
        if max_length is not None:
            kw["max_length"] = max_length
        if pattern is not None:
            kw["pattern"] = pattern
        return cls("str", required, name, kw)

    @classmethod
    def int(cls, ge=None, gt=None, le=None, lt=None,
            required=False, name=None) -> "Constraint":
        kw = {}
        if ge is not None:
            kw["ge"] = ge
        if gt is not None:
            kw["gt"] = gt
        if le is not None:
            kw["le"] = le
        if lt is not None:
            kw["lt"] = lt
        return cls("int", required, name, kw)

    @classmethod
    def numeric(cls, ge=None, gt=None, le=None, lt=None,
                required=False, name=None) -> "Constraint":
        kw = {}
        if ge is not None:
            kw["ge"] = ge
        if gt is not None:
            kw["gt"] = gt
        if le is not None:
            kw["le"] = le
        if lt is not None:
            kw["lt"] = lt
        return cls("numeric", required, name, kw)

    @classmethod
    def bool(cls, required=False, name=None) -> "Constraint":
        return cls("bool", required, name)

    @classmethod
    def datetime(cls, required=False, name=None) -> "Constraint":
        return cls("datetime", required, name)

    @classmethod
    def date(cls, required=False, name=None) -> "Constraint":
        return cls("date", required, name)

    @classmethod
    def blob(cls, required=False, name=None) -> "Constraint":
        return cls("blob", required, name)

    def to_field(self):
        if self.required:
            return Field(**self.field_kwargs)
        return Field(default=None, **self.field_kwargs)

    def to_column(self) -> Column:
        return Column(datatype=self.datatype, name=self.name)


def make_constraint(py_type, *, datatype=None, required=False, name=None,
                    validators=(), **base):
    """Fábrica de orden superior: devuelve una función ``build(...) -> Annotated``.

    ``STR_100 = make_constraint(str, max_length=100)`` es una **función**;
    se invoca ``STR_100(...)`` y devuelve el ``Annotated`` correspondiente.
    """
    if datatype is None:
        try:
            datatype = PY_TYPE_TO_DATATYPE[py_type]
        except KeyError:
            raise TypeError(
                f"Sin datatype inferido para {py_type!r}; indícalo con datatype=..."
            )

    def build(name=name, required=required, **overrides):
        field_kwargs = {**base, **overrides}
        t = py_type if required else (py_type | None)
        constraint = Constraint(
            datatype=datatype,
            required=required,
            name=name,
            field_kwargs=field_kwargs,
            validators=validators,
        )
        return Annotated[
            t,
            constraint,
            constraint.to_field(),
            *(AfterValidator(v) for v in validators),
        ]

    return build
