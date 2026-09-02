"""Fachada pública `Section`: muta la `GroupSpec` de un corte."""

from __future__ import annotations

from ._specs import ChartSpec, GroupSpec, PivotSpec, TotalSpec


class Section:
    """Acceso fluido a las piezas de presentación de un corte (header/footer/total/chart/pivot/...)."""

    def __init__(self, spec: GroupSpec):
        self._spec = spec

    def header(self, template: str) -> "Section":
        self._spec.header = template
        return self

    def footer(self, template: str, column_position: str | None = None) -> "Section":
        self._spec.footer = template
        self._spec.footer_column_position = column_position
        return self

    def total(self, operator: str, column: str | None = None, *,
              expression: str | None = None, name: str | None = None,
              label: str | None = None, column_position: str | None = None,
              format=None) -> "Section":
        self._spec.totals.append(
            TotalSpec(operator, column, expression, name, label, format, column_position)
        )
        return self

    def chart(self, kind: str, *, title: str | None = None,
              operator: str = "sum", column: str | None = None,
              expression: str | None = None, label_field: str | None = None,
              options: dict | None = None, source: str | None = None) -> "Section":
        self._spec.charts.append(
            ChartSpec(kind, title, operator, column, expression, label_field, options, source)
        )
        return self

    def pivot(self, row_column: str, column_column: str, *,
              operator: str = "sum", value_column: str | None = None,
              value_expression: str | None = None, title: str | None = None,
              show_totals: bool = True, options: dict | None = None,
              source: str | None = None) -> "Section":
        self._spec.pivots.append(
            PivotSpec(row_column, column_column, operator, value_column,
                      value_expression, title, show_totals, options, source)
        )
        return self

    def order_by(self, column: str | None = None, *, direction: str = "asc",
                 total: str | None = None, expression: str | None = None) -> "Section":
        if direction.lower() not in ("asc", "desc"):
            raise ValueError(f"dirección de orden inválida: {direction!r}")
        self._spec.order_by = {
            "column": column,
            "direction": direction.lower(),
            "total": total,
            "expression": expression,
        }
        return self

    def top(self, n: int) -> "Section":
        self._spec.top_n = n
        return self

    def suppress_zero(self, column: str | None = None, total: str | None = None) -> "Section":
        self._spec.suppress_zero = {"column": column, "total": total}
        return self

    def page_break(self, enabled: bool = True) -> "Section":
        self._spec.page_break = enabled
        return self
