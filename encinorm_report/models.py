"""Modelo de datos canónico del reporte (pydantic, serializable a JSON)."""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, PrivateAttr


class Link(BaseModel):
    """Enlace a otra sección, reporte, página o URL externa."""

    type: Literal["link"] = "link"
    target: Literal["section", "report", "page", "external"]
    href: str
    label: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class Image(BaseModel):
    """Imagen por ruta, URL o data URI."""

    type: Literal["image"] = "image"
    src: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None


class Format(BaseModel):
    """Formato de presentación de una columna o total (lo aplican los renderers)."""

    kind: Literal["number", "currency", "percent", "date"] = "number"
    decimals: int | None = None          # None -> no redondea
    thousands: bool = False              # separador de miles
    symbol: str | None = None            # p. ej. "$", "€"
    symbol_position: Literal["prefix", "suffix"] = "prefix"
    negative: Literal["minus", "paren"] = "minus"
    percent_scale: bool = False          # percent: multiplica por 100 al mostrar
    pattern: str | None = None           # kind="date": patrón strftime


class Total(BaseModel):
    """Total de un corte (resultado ya calculado)."""

    operator: str
    column: str | None = None
    expression: str | None = None
    name: str | None = None
    label: str | None = None
    value: Any = None
    format: Format | None = None
    column_position: str | None = None


class Detail(BaseModel):
    """Renglón del detalle."""

    type: Literal["detail"] = "detail"
    row: dict[str, Any]


class Series(BaseModel):
    label: str | None = None
    values: list[Any] = Field(default_factory=list)


class Chart(BaseModel):
    type: Literal["chart"] = "chart"
    kind: Literal["pie", "bar", "line"]
    title: str | None = None
    labels: list[Any] = Field(default_factory=list)
    series: list[Series] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class Pivot(BaseModel):
    """Matriz de doble entrada (cross-tab): filas x columnas."""

    type: Literal["pivot"] = "pivot"
    title: str | None = None
    rows: list[Any] = Field(default_factory=list)
    columns: list[Any] = Field(default_factory=list)
    cells: list[list[Any]] = Field(default_factory=list)
    row_totals: list[Any] = Field(default_factory=list)
    column_totals: list[Any] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class ConditionalRule(BaseModel):
    """Regla de formato condicional por valor (la aplican los renderers)."""

    column: str | None = None
    when: Literal["lt", "le", "gt", "ge", "eq", "ne"] = "lt"
    value: Any = 0
    style: dict[str, Any] = Field(default_factory=dict)


class Kpi(BaseModel):
    """Tarjeta de indicador (métrica escalar)."""

    type: Literal["kpi"] = "kpi"
    label: str | None = None
    value: Any = None
    format: Format | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class Group(BaseModel):
    type: Literal["group"] = "group"
    name: str
    key: dict[str, Any] | None = None
    header: str | None = None
    footer: str | None = None
    show_collapsed: bool = False
    default_collapsed: bool = False
    page_break: bool = False
    totals: list[Total] = Field(default_factory=list)
    children: list[Union[Detail, Group, Chart, Pivot]] = Field(default_factory=list)

    # Contexto interno (no serializado) para renderizar header/footer en la fase final.
    _first_row: dict = PrivateAttr(default_factory=dict)
    _header_tpl: str | None = PrivateAttr(default=None)
    _footer_tpl: str | None = PrivateAttr(default=None)


class ReportMeta(BaseModel):
    title: str | None = None
    params: list[Any] = Field(default_factory=list)


class ReportResult(BaseModel):
    meta: ReportMeta = Field(default_factory=ReportMeta)
    columns: list[str] = Field(default_factory=list)
    formats: dict[str, Format] = Field(default_factory=dict)
    styles: list[ConditionalRule] = Field(default_factory=list)
    kpis: list[Kpi] = Field(default_factory=list)
    root: Group

    def render_html(self, classes: dict | None = None, repeat_header: bool = False) -> str:
        from .renderers.html import HtmlRenderer

        return HtmlRenderer(classes=classes, repeat_header=repeat_header).render(self)

    def to_csv(self, delimiter: str = ",") -> str:
        from .renderers.csv import CsvRenderer

        return CsvRenderer(delimiter=delimiter).render(self)

    def to_text(self) -> str:
        from .renderers.text import TextRenderer

        return TextRenderer().render(self)

    def to_excel(self, ws=None, styles: dict | None = None, formulas: bool = False):
        from .renderers.excel import ExcelRenderer

        return ExcelRenderer(styles=styles, formulas=formulas).render(self, ws=ws)

    def to_pdf(self, *, repeat_header: bool = True, **opts) -> bytes:
        from .renderers.pdf import PdfRenderer

        return PdfRenderer().render(self, repeat_header=repeat_header, **opts)


Group.model_rebuild()
