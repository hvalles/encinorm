"""Derivación de `labels`/`series` de un gráfico desde los datos ya agregados."""

from __future__ import annotations

from .models import Chart, Series


def build_chart(spec, child_pairs, own_totals, value_fn) -> Chart:
    """Construye un `Chart`.

    - `child_pairs`: lista de `(Group, rows)` de los subgrupos hijos (caso "con hijos").
    - `own_totals`: lista de `Total` del corte (caso "sin hijos").
    - `value_fn(rows)`: agrega el operador sobre un conjunto de renglones.
    """
    labels = []
    values = []
    if child_pairs:
        for child_node, child_rows in child_pairs:
            labels.append(_label(spec, child_node, child_rows))
            values.append(value_fn(child_rows))
    else:
        labels = [t.label if t.label is not None else t.name for t in own_totals]
        values = [t.value for t in own_totals]

    series_label = spec.column or spec.expression or "value"
    return Chart(
        kind=spec.kind,
        title=spec.title,
        labels=labels,
        series=[Series(label=series_label, values=values)],
        options=spec.options or {},
    )


def _label(spec, child_node, child_rows):
    if spec.label_field:
        if child_rows and spec.label_field in child_rows[0]:
            return child_rows[0][spec.label_field]
        if child_node.key and spec.label_field in child_node.key:
            return child_node.key[spec.label_field]
        return None
    if child_node.key:
        return next(iter(child_node.key.values()), None)
    if child_rows:
        return next(iter(child_rows[0].values()), None)
    return None
