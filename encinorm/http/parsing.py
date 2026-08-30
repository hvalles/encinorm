"""Parsing de `filter` (JSON) y `sort_by` (CSV) desde query params."""

import json
from functools import reduce

from encinorm.model import Filter

# Operadores simples `(campo, valor) -> Filter`.
_OP_MAP = {
    "eq": Filter.eq,
    "ne": Filter.ne,
    "gt": Filter.gt,
    "ge": Filter.ge,
    "lt": Filter.lt,
    "le": Filter.le,
    "in": Filter.in_,
    "like": Filter.like,
    "startswith": Filter.startswith,
    "endswith": Filter.endswith,
}


def _apply_op(op: str, campo: str, valor) -> Filter:
    # Operadores con aridad propia (no siguen el patrón `(campo, valor)`):
    if op == "between":
        lo, hi = valor
        return Filter.between(campo, lo, hi)
    if op == "is_null":
        return Filter.is_null(campo)
    if op == "not_null":
        return Filter.not_null(campo)
    return _OP_MAP[op](campo, valor)


def filter_from_str(raw: str) -> Filter | None:
    if not raw or not raw.strip():
        return None
    return _from_dict(json.loads(raw))


def _from_dict(d: dict) -> Filter | None:
    partes = []
    for campo, spec in d.items():
        if campo == "and":
            partes.extend(_from_dict(x) for x in spec)
        elif campo == "or":
            sub = [f for f in (_from_dict(x) for x in spec) if f is not None]
            if sub:
                partes.append(reduce(Filter.or_, sub))
        elif campo == "not":
            f = _from_dict(spec)
            if f is not None:
                partes.append(f.not_())
        elif isinstance(spec, dict):
            for op, valor in spec.items():
                partes.append(_apply_op(op, campo, valor))
        else:
            # valor escalar -> atajo de igualdad: `{"campo": valor}` == `eq`
            partes.append(Filter.eq(campo, spec))
    return reduce(Filter.and_, partes) if partes else None


def sort_from_str(raw: str) -> list[str]:
    """CSV de campos: `"campo"` (ASC), `"-campo"` (DESC), `"+campo"` (ASC)."""
    return [p.strip() for p in raw.split(",") if p.strip()]
