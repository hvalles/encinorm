"""Construcción de matrices filas x columnas (cross-tab / `Pivot`)."""

from __future__ import annotations

from .models import Pivot


def build_pivot(spec, rows, value_fn) -> Pivot:
    """Construye un `Pivot` agrupando por `(row_column, column_column)`.

    - `rows`: renglones ya enriquecidos.
    - `value_fn(rows)`: agrega el operador sobre un conjunto de renglones.
    """
    row_values = _ordered_unique(r.get(spec.row_column) for r in rows)
    col_values = _ordered_unique(r.get(spec.column_column) for r in rows)
    row_index = {v: i for i, v in enumerate(row_values)}
    col_index = {v: i for i, v in enumerate(col_values)}

    buckets = {}
    for r in rows:
        key = (r.get(spec.row_column), r.get(spec.column_column))
        buckets.setdefault(key, []).append(r)

    cells = [[None] * len(col_values) for _ in row_values]
    for (rv, cv), group in buckets.items():
        cells[row_index[rv]][col_index[cv]] = value_fn(group)

    row_totals = [
        value_fn([r for r in rows if r.get(spec.row_column) == rv]) for rv in row_values
    ]
    col_totals = [
        value_fn([r for r in rows if r.get(spec.column_column) == cv]) for cv in col_values
    ]

    return Pivot(
        title=spec.title,
        rows=row_values,
        columns=col_values,
        cells=cells,
        row_totals=row_totals,
        column_totals=col_totals,
        options=spec.options or {},
    )


def _ordered_unique(values):
    seen = set()
    out = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out
