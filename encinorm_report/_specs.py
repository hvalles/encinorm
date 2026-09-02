"""Especificaciones internas del builder (dataclasses; no forman parte del árbol)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldSpec:
    name: str
    expression: str | None = None
    after: str | None = None
    kind: str = "expr"          # expr | link | image
    format: Any = None
    cumulative: str | None = None
    start: Any = 0
    source: str | None = None
    # link
    target: str | None = None
    href: str | None = None
    label: str | None = None
    # image
    src: str | None = None
    alt: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class TotalSpec:
    operator: str
    column: str | None = None
    expression: str | None = None
    name: str | None = None
    label: str | None = None
    format: Any = None
    column_position: str | None = None


@dataclass
class ChartSpec:
    kind: str
    title: str | None = None
    operator: str = "sum"
    column: str | None = None
    expression: str | None = None
    label_field: str | None = None
    options: dict | None = None
    source: str | None = None


@dataclass
class PivotSpec:
    row_column: str
    column_column: str
    operator: str = "sum"
    value_column: str | None = None
    value_expression: str | None = None
    title: str | None = None
    show_totals: bool = True
    options: dict | None = None
    source: str | None = None


@dataclass
class KpiSpec:
    label: str | None = None
    operator: str = "sum"
    column: str | None = None
    expression: str | None = None
    value: Any = None
    format: Any = None
    source: str | None = None


@dataclass
class GroupSpec:
    name: str
    columns: list[str] | None = None      # None -> raíz (una sola partición)
    parent: str | None = None
    path: str | None = None
    separator: str = "."
    show_collapsed: bool = False
    default_collapsed: bool = False
    page_break: bool = False
    source: str | None = None
    header: str | None = None
    footer: str | None = None
    footer_column_position: str | None = None
    totals: list[TotalSpec] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    pivots: list[PivotSpec] = field(default_factory=list)
    order_by: dict | None = None
    top_n: int | None = None
    suppress_zero: dict | None = None
    children: list["GroupSpec"] = field(default_factory=list)
