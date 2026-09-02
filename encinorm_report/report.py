"""Builder fluido `Report`."""

from __future__ import annotations

from typing import Any

from ._specs import FieldSpec, GroupSpec, KpiSpec
from .models import ConditionalRule, Format, ReportResult
from .section import Section


class Report:
    """Constructor de reportes a partir de filas `list[dict]`."""

    def __init__(self, rows: list[dict], params: list | None = None, title: str | None = None):
        self._rows = list(rows)
        self._params = list(params or [])
        self._title = title
        self._functions: dict[str, Any] = {}
        self._aggregates: dict[str, Any] = {}
        self._fields: list[FieldSpec] = []
        self._detail: list[str] = []
        self._groups: dict[str, GroupSpec] = {}
        self._order: list[str] = []          # orden de declaración de los cortes
        self._formats: dict[str, Format] = {}
        self._styles: list[ConditionalRule] = []
        self._datasets: dict[str, list[dict]] = {}
        self._kpis: list[KpiSpec] = []

    # --- funciones / campos ---
    def add_function(self, name: str, fn) -> "Report":
        self._functions[name] = fn
        return self

    def add_aggregate(self, name: str, fn) -> "Report":
        self._aggregates[name] = fn
        return self

    def set_format(self, column: str, *, kind: str = "number",
                   decimals: int | None = None, thousands: bool = False,
                   symbol: str | None = None, symbol_position: str = "prefix",
                   negative: str = "minus", percent_scale: bool = False,
                   pattern: str | None = None) -> "Report":
        self._formats[column] = Format(
            kind=kind, decimals=decimals, thousands=thousands, symbol=symbol,
            symbol_position=symbol_position, negative=negative,
            percent_scale=percent_scale, pattern=pattern,
        )
        return self

    def add_style(self, column: str | None = None, *, when: str = "lt",
                  value: Any = 0, **style) -> "Report":
        self._styles.append(ConditionalRule(column=column, when=when, value=value, style=style))
        return self

    def add_dataset(self, name: str, rows: list[dict]) -> "Report":
        self._datasets[name] = list(rows)
        return self

    def kpi(self, label: str, *, operator: str = "sum", column: str | None = None,
            expression: str | None = None, value: Any = None,
            format=None, source: str | None = None) -> "Report":
        self._kpis.append(KpiSpec(label, operator, column, expression, value, format, source))
        return self

    def add_field(self, name: str, expression: str | None = None, *,
                  after: str | None = None, format=None,
                  cumulative: str | None = None, start: Any = 0,
                  source: str | None = None) -> "Report":
        self._fields.append(
            FieldSpec(name=name, expression=expression, after=after, kind="expr",
                      format=format, cumulative=cumulative, start=start, source=source)
        )
        return self

    def link(self, name: str, target: str, href: str, label: str | None = None,
             *, after: str | None = None) -> "Report":
        self._fields.append(
            FieldSpec(name=name, after=after, kind="link", target=target, href=href, label=label)
        )
        return self

    def image(self, name: str, src: str, *, alt: str | None = None,
              width: int | None = None, height: int | None = None,
              after: str | None = None) -> "Report":
        self._fields.append(
            FieldSpec(name=name, after=after, kind="image", src=src, alt=alt,
                      width=width, height=height)
        )
        return self

    # --- detalle / grupos ---
    def detail(self, *columns: str, source: str | None = None) -> "Report":
        self._detail = list(columns)
        return self

    def group(self, name: str,
              columns: str | list[str] | tuple[str, ...] | None = None, *,
              parent: str | None = None,
              show_collapsed: bool = False,
              default_collapsed: bool = False,
              path: str | None = None, separator: str = ".",
              source: str | None = None) -> Section:
        if columns is not None and path is not None:
            raise ValueError("`columns` y `path` son excluyentes")
        cols = None
        if columns is not None:
            cols = [columns] if isinstance(columns, str) else list(columns)
        spec = GroupSpec(
            name=name, columns=cols, parent=parent, path=path, separator=separator,
            show_collapsed=show_collapsed, default_collapsed=default_collapsed,
            source=source,
        )
        self._groups[name] = spec
        self._order.append(name)
        return Section(spec)

    def section(self, name: str) -> Section:
        spec = self._groups.get(name)
        if spec is None:
            raise KeyError(f"corte no declarado: {name!r}")
        return Section(spec)

    def run(self) -> ReportResult:
        from .aggregation import build

        return build(self)
