# Documento de Diseño — Reporteador financiero (`encinorm-report`)

Este documento diseña un **reporteador de tipo financiero** a partir del análisis
de `prompts/analisys-10.md`: un motor de agregación y presentación que consume
`list[dict]` (la salida de `Db.fetch_all`/`fetch_many`/`db.paginate`) y produce
un **árbol canónico de datos** desacoplado del destino, con renderers opcionales
a HTML, Excel, CSV, PDF y texto.

> Complementa `docs/design_model.md` (sección `QueryBuilder`) y es **aditivo**:
> no modifica `Db`, `Query` ni `QueryBuilder`. Se diseña como **proyecto
> separado** (`encinorm-report`, módulo `encinorm_report`), con integración
> opcional con `encinorm` (véase §10).

---

## 1. Contexto y alcance

El ORM ya resuelve agregados planos en SQL (`QueryBuilder` con `group_by`/`having`
/`sum`/`avg`/`min`/`max`/`count`). El reporteador aporta lo que SQL no expresa
limpiamente entre motores: **jerarquías de cortes** (grupos anidados) con
**encabezado, pie y total por nivel**, y una **salida tipada** lista para un
frontend o para exportar.

**Objetivos**

- Agrupar filas en una jerarquía arbitraria (por columna), con totales por grupo.
- Columnas calculadas (`cantidad*precio`) mediante un evaluador **seguro**.
- Encabezados/pies con plantillas que interpolan campos del corte y parámetros.
- Celdas enriquecidas: **enlaces** (a secciones, reportes, páginas o URLs) e
  **imágenes**.
- Salida **renderer-agnóstica**: un único árbol alimenta JSON, HTML, Excel, CSV,
  PDF y texto.

**No-objetivos**

- No genera SQL ni consulta la BD (recibe filas ya materializadas).
- No es un motor de agregados *server-side* para grandes volúmenes (los
  agregados pesados deben delegarse a `GROUP BY ROLLUP`/`CUBE`; el reporteador
  solo ensambla el resultado).

---

## 2. Arquitectura

Tres capas desacopladas:

```
list[dict]  ──►  Builder (Report)  ──►  Árbol canónico (ReportResult)  ──►  Renderers
 (entrada)      enriquecer/agrupar        dato puro (JSON vía model_dump)     HTML/Excel/CSV/PDF/Texto
```

1. **Entrada**: filas `list[dict]` + parámetros de la consulta (`params`).
2. **`Report`**: builder fluido que define columnas calculadas, detalle, grupos,
   secciones (header/footer/total), enlaces, imágenes, gráficos, pivotes y KPIs;
   `run()` materializa el árbol.
3. **Renderers**: clases *visitor* que recorren el árbol y lo convierten al
   formato destino. Añadir un destino nuevo no toca `run()` ni el dato.

---

## 3. Modelo de datos canónico

Estructura tipada (pydantic, como `Records`) y serializable a JSON. Cada nodo
lleva un **discriminador de tipo**; las celdas pueden ser escalares o
descriptores `Link`/`Image`.

```python
# encinorm_report/models.py
from typing import Any, Literal, Union
from pydantic import BaseModel, Field

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
    decimals: int | None = None          # None → no redondea
    thousands: bool = False              # separador de miles
    symbol: str | None = None            # p. ej. "$", "€"
    symbol_position: Literal["prefix", "suffix"] = "prefix"
    negative: Literal["minus", "paren"] = "minus"   # -100.0 o (100.0)
    percent_scale: bool = False          # percent: multiplica por 100 al mostrar
    pattern: str | None = None           # kind="date": patrón strftime (p. ej. "%d/%m/%Y")

class Total(BaseModel):
    operator: str                    # sum | avg | count | count_distinct | max | min | custom:<name>
    column: str | None = None        # columna agregada (None en count global)
    expression: str | None = None    # expresión por renglón a agregar (p. ej. "es_par * total")
    name: str | None = None          # clave para referenciar vía {{total.NOMBRE}}
    label: str | None = None
    value: Any = None                # resultado (numérico, salvo custom)
    format: Format | None = None     # formato de presentación del total
    column_position: str | None = None   # pista de presentación (columna bajo la que se alinea)

class Detail(BaseModel):
    type: Literal["detail"] = "detail"
    row: dict[str, Any]              # valores escalares o Link/Image

class Series(BaseModel):
    label: str | None = None
    values: list[Any] = Field(default_factory=list)

class Chart(BaseModel):
    type: Literal["chart"] = "chart"
    kind: Literal["pie", "bar", "line"]
    title: str | None = None
    labels: list[Any] = Field(default_factory=list)   # misma longitud que series[i].values
    series: list[Series] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)   # pistas de estilo (colores, apilado, …)

class Pivot(BaseModel):
    """Matriz de doble entrada (cross-tab): filas × columnas."""
    type: Literal["pivot"] = "pivot"
    title: str | None = None
    rows: list[Any] = Field(default_factory=list)        # valores de la dimensión fila
    columns: list[Any] = Field(default_factory=list)     # valores de la dimensión columna
    cells: list[list[Any]] = Field(default_factory=list) # [fila][columna] = valor
    row_totals: list[Any] = Field(default_factory=list)
    column_totals: list[Any] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)

class ConditionalRule(BaseModel):
    """Regla de formato condicional por valor (la aplican los renderers)."""
    column: str | None = None            # None → aplica a cualquier columna numérica
    when: Literal["lt", "le", "gt", "ge", "eq", "ne"] = "lt"
    value: Any = 0
    style: dict[str, Any] = Field(default_factory=dict)   # {"color": "red", "bold": true}

class Kpi(BaseModel):
    """Tarjeta de indicador (métrica escalar de primera clase)."""
    type: Literal["kpi"] = "kpi"
    label: str | None = None
    value: Any = None
    format: Format | None = None
    options: dict[str, Any] = Field(default_factory=dict)

class Group(BaseModel):
    type: Literal["group"] = "group"
    name: str                        # identificador lógico del corte
    key: dict[str, Any] | None = None    # valores del corte (None en el grupo raíz)
    header: str | None = None
    footer: str | None = None
    show_collapsed: bool = False     # ¿el encabezado se muestra aunque el grupo esté colapsado?
    default_collapsed: bool = False  # presentación inicial (abierta/cerrada) para renderers interactivos
    page_break: bool = False         # pista: iniciar este corte en página nueva (PDF/impresión)
    totals: list[Total] = Field(default_factory=list)
    children: list[Union[Detail, Group, Chart, Pivot]] = Field(default_factory=list)

class ReportMeta(BaseModel):
    title: str | None = None
    params: list[Any] = Field(default_factory=list)

class ReportResult(BaseModel):
    meta: ReportMeta = Field(default_factory=ReportMeta)
    columns: list[str] = Field(default_factory=list)   # orden del detalle
    formats: dict[str, Format] = Field(default_factory=dict)   # columna -> formato
    styles: list[ConditionalRule] = Field(default_factory=list)   # formato condicional
    kpis: list[Kpi] = Field(default_factory=list)   # tarjetas de indicador (resumen)
    root: Group
```

Ejemplo de árbol (resumido):

```json
{
  "meta": {"title": "Ventas por agente", "params": ["2026-01-01 00:00", "2026-01-31 23:59", "cancel", "pending"]},
  "columns": ["sku", "descripcion", "cantidad", "precio", "total"],
  "root": {
    "type": "group", "name": "global",
    "header": "Reporte de Ventas por Agente del 2026-01-01 00:00 al 2026-01-31 23:59",
    "totals": [{"operator": "sum", "column": "total", "label": "Total general", "value": 12345.6}],
    "children": [
      {
        "type": "group", "name": "tot_agt", "key": {"id": 1},
        "header": "1 Agente: Ana", "footer": "Total agente Ana",
        "totals": [{"operator": "sum", "column": "total", "value": 6789.0}],
        "children": [
          {"type": "detail", "row": {"sku": "A1", "descripcion": "...", "cantidad": 2, "precio": 10.0, "total": 20.0}}
        ]
      },
      {
        "type": "chart", "kind": "pie", "title": "Ventas por agente",
        "labels": ["Ana", "Bob"],
        "series": [{"label": "total", "values": [6789.0, 4556.0]}]
      }
    ]
  }
}
```

> `key` conserva los **campos de agrupación** del corte (para anclas/acceso
> programático); puede ser una clave simple (`{"id": 1}`) o compuesta
> (`{"tenant_id": 7, "code": "admin"}`). El contexto de interpolación de
> `header`/`footer` es el **primer renglón del grupo**, por lo que cualquier campo
> de ese renglón (`id`, `agente`, `referencia`, …) está disponible, no solo las
> columnas de agrupación.

---

## 4. API del builder

API fluida corregida respecto al boceto de `prompts/24.md` (consistencia de
acceso, kwargs, y sintaxis de plantillas).

```python
# encinorm_report/report.py
class Report:
    def __init__(self, rows: list[dict], params: list | None = None, title: str | None = None):
        self._rows = list(rows)
        self._params = list(params or [])
        self._title = title                              # se copia a ReportMeta.title en run()
        self._functions: dict[str, callable] = {}   # funciones de expresión
        self._aggregates: dict[str, callable] = {}  # funciones de agregado (custom:)
        self._fields: list[FieldSpec] = []          # columnas calculadas (en orden)
        self._detail: list[str] = []                # columnas del detalle
        self._groups: dict[str, GroupSpec] = {}     # cortes declarados
        self._formats: dict[str, Format] = {}       # columna -> formato
        self._styles: list[ConditionalRule] = []    # formato condicional
        self._datasets: dict[str, list[dict]] = {}  # conjuntos adicionales (source -> filas)
        self._root: GroupSpec | None = None

    # --- funciones / campos ---
    def add_function(self, name: str, fn: callable) -> "Report":
        """Registra una función de **expresión** (por renglón): se invoca con
        argumentos explícitos desde una expresión, p. ej. `redondear(total)`."""
        self._functions[name] = fn
        return self

    def add_aggregate(self, name: str, fn: callable) -> "Report":
        """Registra una función de **agregado** para `custom:<name>`: `fn(rows, column)`."""
        self._aggregates[name] = fn
        return self

    def set_format(self, column: str, *, kind: str = "number",
                   decimals: int | None = None, thousands: bool = False,
                   symbol: str | None = None, symbol_position: str = "prefix",
                   negative: str = "minus", percent_scale: bool = False,
                   pattern: str | None = None) -> "Report":
        """Registra el formato de presentación de una columna (número, moneda,
        porcentaje o fecha). Lo aplican los renderers; no altera el valor crudo."""

    def add_style(self, column: str | None = None, *, when: str = "lt",
                  value: Any = 0, **style) -> "Report":
        """Regla de formato condicional por valor (p. ej. `add_style("total",
        when="lt", value=0, color="red")`). La aplican los renderers."""

    def add_dataset(self, name: str, rows: list[dict]) -> "Report":
        """Registra un conjunto de filas adicional (multi-query/sub-reporte)."""

    def kpi(self, label: str, *, operator: str = "sum", column: str | None = None,
            expression: str | None = None, value: Any = None,
            format: Format | dict | None = None, source: str | None = None) -> "Report":
        """Declara una **tarjeta de indicador** (KPI) en el resumen del reporte.
        Si `value` no se pasa, se calcula `operator(column|expression)` sobre las
        filas del `source`."""

    def add_field(self, name: str, expression: str | None = None, *,
                  after: str | None = None, format: Format | dict | None = None,
                  cumulative: str | None = None, start: Any = 0,
                  source: str | None = None) -> "Report":
        """Columna calculada. `expression` usa el evaluador seguro (§6).

        - `after=None` (por defecto): campo **oculto** — se calcula y queda
          disponible para expresiones/totales, pero no se imprime.
        - `after="col"`: campo **visible**, insertado tras `col`.

        Regla de visibilidad: un campo es visible si está listado en
        `detail()` **o** lleva `after`; `after` posiciona relativo a una columna
        visible (si `col` no es visible, se añade al final).

        Un campo comparativo se declara como expresión que devuelve 1|0
        (p. ej. `IF(pedido_id % 2 == 0)`); sirve de factor en totales condicionales.

        - `format`: formato de presentación (un `Format` o un `dict` equivalente).
        - `cumulative="sum"`: acumula el valor de la expresión a lo largo de los
          renglones previos (en el orden final), produciendo un **saldo corrido**
          (p. ej. `debe - haber`). `start` es el **saldo inicial (apertura)**;
          por defecto `0`. El valor en el renglón `i` es `start + Σ(expr_j, j ≤ i)`.
          Para un saldo de apertura distinto de cero, pásalo explícitamente
          (p. ej. desde `params`).
        """

    def link(self, name: str, target: str, href: str, label: str | None = None,
             *, after: str | None = None) -> "Report":
        """Columna de enlace (target: section|report|page|external)."""

    def image(self, name: str, src: str, *, alt: str | None = None,
              width: int | None = None, height: int | None = None,
              after: str | None = None) -> "Report":
        """Columna de imagen (src puede ser ruta, URL o data URI)."""

    # --- detalle / grupos ---
    def detail(self, *columns: str, source: str | None = None) -> "Report":
        """Columnas que se imprimen por renglón, en orden (opcionalmente por `source`)."""

    def group(self, name: str, columns: str | list[str] | tuple[str, ...] | None = None, *,
              parent: str | None = None,
              show_collapsed: bool = False,
              default_collapsed: bool = False,
              path: str | None = None, separator: str = ".",
              source: str | None = None) -> "Section":
        """Crea (o devuelve) un corte. `columns=None` es el grupo raíz/global.
        Acepta una columna (`"id"`) o varias (`["tenant_id", "code"]`) para
        agrupar por **clave compuesta**. `parent` anida el corte dentro de otro.
        `path` agrupa por una **jerarquía guiada por datos** (p. ej. `"1.2.3"`)
        con profundidad variable; `source` selecciona un conjunto de
        `add_dataset`."""

    def section(self, name: str) -> "Section":
        """Acceso a una sección existente para añadir header/footer/total."""

    def run(self) -> ReportResult: ...
```

`FieldSpec` y `GroupSpec` son **especificaciones internas** del builder
(dataclasses), no forman parte del árbol canónico:

- `FieldSpec(name, expression, after, kind)` — describe una columna calculada;
  `kind ∈ {"expr", "link", "image"}`.
- `GroupSpec(name, columns, parent, show_collapsed, default_collapsed, section)`
  — describe un corte; `columns` es `str | list[str] | None` (clave simple,
  compuesta o raíz). `Section` es la **fachada pública** que muta esa
  `GroupSpec` (header/footer/totals).

La `Section` agrupa las piezas de presentación de un corte:

```python
# encinorm_report/section.py
class Section:
    def header(self, template: str) -> "Section": ...
    def footer(self, template: str, column_position: str | None = None) -> "Section": ...
    def total(self, operator: str, column: str | None = None, *,
              expression: str | None = None, name: str | None = None,
              label: str | None = None, column_position: str | None = None,
              format: Format | dict | None = None) -> "Section": ...
    def chart(self, kind: str, *, title: str | None = None,
              operator: str = "sum", column: str | None = None,
              expression: str | None = None, label_field: str | None = None,
              options: dict | None = None, source: str | None = None) -> "Section": ...
    def pivot(self, row_column: str, column_column: str, *,
              operator: str = "sum", value_column: str | None = None,
              value_expression: str | None = None, title: str | None = None,
              show_totals: bool = True, options: dict | None = None,
              source: str | None = None) -> "Section": ...
    def order_by(self, column: str | None = None, *, direction: str = "asc",
                 total: str | None = None, expression: str | None = None) -> "Section": ...
    def top(self, n: int) -> "Section": ...
    def suppress_zero(self, column: str | None = None, total: str | None = None) -> "Section": ...
    def page_break(self, enabled: bool = True) -> "Section": ...
```

- `operator` válidos: `sum`, `avg`, `count`, `count_distinct`, `max`, `min`,
  `custom:<nombre>` (usa una función registrada con `add_aggregate`).
- `total` agrega sobre `column`, **o** sobre `expression` (expresión por renglón
  evaluada con el evaluador seguro). `expression` habilita **totales
  condicionales**: `total("sum", expression="es_par * total")` suma `total` solo
  en los renglones donde `es_par == 1`.
- `name` identifica el total para referenciarlo desde plantillas como
  `{{total.NOMBRE}}`.
- `format` aplica presentación al total (moneda, porcentaje, decimales) sin alterar
  su valor crudo.
- `column_position` es una **pista de presentación** (bajo qué columna alinear el
  rótulo/valor); no afecta al dato y es independiente de `column` (p. ej. un
  `count` global sin `column` puede alinearse bajo `column_position="cantidad"`).
- **Porcentajes/razones**: un `total` con `expression` puede referenciar otro total
  con `TOTAL("seccion.nombre")`; se resuelve en la **segunda fase** de agregación
  (tras calcular los totales base). Ej. `total("sum", expression="total / TOTAL('global.total_gral') * 100")`.
- `chart(kind, ...)` declara un gráfico (pie/bar/line) **dentro del corte**. Sus
  `labels` y `series` se derivan de los datos ya agregados; admite los mismos
  `operator` que `total` (incluido `custom:<n>`):

  - **Con hijos**: grafica los subgrupos hijos. Etiqueta = `label_field` resuelto
    contra el **primer renglón** del hijo (o contra `key` si es columna de
    agrupación); si `label_field` es `None`, se usa la primera columna de
    agrupación del hijo. Valor = `operator` sobre `column`/`expression` de cada hijo.
  - **Sin hijos** (hoja o raíz sin subgrupos): grafica los `totals` del corte
    (etiquetas = `label`/`name`), ignorando `operator`/`column`/`expression`.

  El nodo `chart` se inserta al **final** de `children` del corte. `labels` y
  `series[i].values` deben tener la misma longitud. `options` son **pistas
  opcionales** de estilo que el renderer puede ignorar.
- `pivot(row_column, column_column, ...)` declara una **matriz de doble entrada**
  (cross-tab): filas = valores de `row_column`, columnas = valores de
  `column_column`, celdas = `operator` sobre `value_column`/`value_expression`.
  Produce un nodo `Pivot` (con totales de fila/columna si `show_totals=True`).
- **Jerarquía por datos**: `group(..., path="ruta", separator=".")` expande una
  jerarquía de profundidad variable (p. ej. un catálogo de cuentas "1", "1.1",
  "1.1.1"); `columns` y `path` son excluyentes.
- **Formato condicional**: `add_style(column, when, value, **style)` registra
  reglas (p. ej. resaltar negativos en rojo); se guardan en `ReportResult.styles`.
- **Multi-query**: `add_dataset(name, rows)` + `source=name` en `group`/`chart`/
  `pivot`/`add_field`/`detail` permiten componer sub-reportes de varias consultas.
- **Orden / Top-N / ceros**: `order_by(...)` ordena los hijos (por columna,
  `total` nombrado o `expression`); `top(n)` conserva los primeros `n`;
  `suppress_zero(...)` descarta hijos con valor cero/None. Se aplican **después**
  de calcular los totales (fase C).
- **Saltos de página**: `page_break()` marca el corte para empezar en página
  nueva (lo respetan PDF/impresión HTML).
- **KPI**: `Report.kpi(...)` declara tarjetas de indicador en `ReportResult.kpis`.

### Ejemplo completo (equivalente a `prompts/24.md`)

```python
from encinorm import Query
from encinorm_report import Report

res = await db.fetch_all(Query(
    "select a.id, a.nombre as agente, p.id as pedido_id, p.referencia, p.fecha, "
    "p.estatus, pd.sku, pd.descripcion, pd.cantidad, pd.precio "
    "from agentes a inner join pedidos p on p.seller_id=a.id "
    "inner join pedidosdet pd on pd.pedido_id=p.id "
    "where p.fecha between {0} and {1} and p.estatus not in ({2},{3}) "
    "order by a.id, p.id",
    ["2026-01-01 00:00", "2026-01-31 23:59", "cancel", "pending"],
))

rep = Report(res, params=["2026-01-01 00:00", "2026-01-31 23:59", "cancel", "pending"],
             title="Reporte de Ventas por Agente")

rep.add_field("total", "cantidad * precio", after="precio")
rep.add_field("es_par", "IF(pedido_id % 2 == 0)")       # oculto (after=None): 1|0
rep.add_field("descripcion_may", "upper(descripcion)", after="descripcion")  # visible, tras "descripcion"
rep.detail("sku", "descripcion", "cantidad", "precio", "total")
# orden visible: sku, descripcion, descripcion_may, cantidad, precio, total

rep.group("tot_agt", columns="id", show_collapsed=False, default_collapsed=False)
rep.section("tot_agt").header("{{id}} Agente: {{agente}}")
rep.section("tot_agt").footer("Total agente {{agente}}", column_position="agente")
rep.section("tot_agt").total("sum", "total")
rep.section("tot_agt").total("sum", expression="es_par * total", label="Total (pares)")  # condicional
rep.section("tot_agt").total("avg", "precio", label="Precio Promedio")
rep.section("tot_agt").total("count", "pedido_id")

rep.group("tot_ped", columns="pedido_id", parent="tot_agt")
rep.section("tot_ped").header("{{pedido_id}} Referencia: {{referencia}}  fecha:{{fecha}} estatus:{{estatus}}")
rep.section("tot_ped").footer("Total pedido {{pedido_id}}", column_position="agente")
rep.section("tot_ped").total("sum", "total")

rep.group("global")
rep.section("global").header(
    "Reporte de Ventas por Agente del {{param.0}} al {{param.1}}")
rep.section("global").footer(
    "Total general {{total.total_gral}}", column_position="agente")  # {{total.NOMBRE}}
rep.section("global").total("sum", "total", name="total_gral", column_position="total")
rep.section("global").total("count", column_position="cantidad")
rep.section("global").chart("pie", title="Ventas por agente",
                            operator="sum", column="total", label_field="agente")

result = rep.run()

json_out = result.model_dump()            # (a) JSON canónico
html = result.render_html(classes={...})  # (b) tabla HTML opcional
```

Un `footer` puede interpolar `{{total.total_gral}}` aunque el total se calcule al
final del corte: el objeto `Total` se **crea al declararlo** (con su `name`) y su
`value` se rellena durante la agregación; las plantillas `header`/`footer` se
**renderizan después** de calcular los totales del grupo (dos pasadas por grupo),
por lo que `{{total.NOMBRE}}` resuelve en ambos. Véase §6.

La agrupación acepta **clave compuesta** (varias columnas); el `key` del grupo
lleva todos los valores:

```python
rep.group("tot_memb", columns=["tenant_id", "code"])
rep.section("tot_memb").header("Tenant {{tenant_id}} · Código {{code}}")
rep.section("tot_memb").total("sum", "total")
# → Group.key == {"tenant_id": 7, "code": "admin"}
```

Formato numérico, porcentajes y saldos corridos:

```python
rep.set_format("total", kind="currency", symbol="$", decimals=2,
               thousands=True, negative="paren")       # $1,234.56 / (100.00)

rep.section("global").total("sum", "total", name="total_gral")
rep.section("tot_agt").total(
    "sum", expression="total / TOTAL('global.total_gral') * 100",
    label="% del total", format={"kind": "percent", "decimals": 2})   # fase B

rep.add_field("saldo", "debe - haber", cumulative="sum", start=0, after="haber")  # saldo corrido
```

Pivote, formato condicional, jerarquía por datos, fechas y multi-query:

```python
rep.section("global").pivot("agente", "mes", operator="sum", value_column="total",
                            title="Ventas por agente/mes")       # matriz filas×columnas
rep.add_style("total", when="lt", value=0, color="red", bold=True)   # negativos en rojo
rep.set_format("fecha", kind="date", pattern="%d/%m/%Y")

rep.group("cuentas", path="cuenta_path", separator=".")   # jerarquía variable (1 → 1.1 → 1.1.1)

rep.add_dataset("presupuesto", presupuesto_rows)
rep.section("global").chart("bar", title="Real vs presupuesto",
                            operator="sum", column="monto", source="presupuesto")
```

Orden, Top-N, supresión de ceros, saltos de página y KPIs:

```python
rep.section("tot_agt").total("sum", "total", name="total_agt")
rep.section("tot_agt").order_by(total="total_agt", direction="desc").top(10)  # top 10 agentes por monto
rep.section("tot_agt").suppress_zero(total="total_agt")                        # descarta ceros

rep.section("tot_agt").page_break()                                           # página nueva por agente

rep.kpi("Ingresos totales", operator="sum", column="total",
        format={"kind": "currency", "symbol": "$", "decimals": 2})
rep.kpi("Ticket promedio", operator="avg", column="total")
```

---

## 5. Evaluador seguro de expresiones

Prohibido `eval`. Se usa `ast.parse(mode="eval")` con un *whitelist* estricto:

```python
# encinorm_report/expressions.py
import ast, operator

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}

# funciones integradas del lenguaje de expresiones (además de las de add_function)
_FUNCTIONS = {
    "IF": lambda cond: 1 if cond else 0,          # comparativo → 1|0
    "lower": str.lower,
    "upper": str.upper,
    "concat": lambda *args: "".join(str(a) for a in args),
    "round": round,                                # round(x[, ndigits])
    "abs": abs,
    "AND": lambda *args: 1 if all(args) else 0,    # lógica → 1|0
    "OR": lambda *args: 1 if any(args) else 0,
    "NOT": lambda x: 1 if not x else 0,
    "IN": lambda x, *args: 1 if x in args else 0,
    "BETWEEN": lambda x, lo, hi: 1 if lo <= x <= hi else 0,
}

def evaluate(expr: str, row: dict, functions: dict) -> Any:
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body, row, {**_FUNCTIONS, **functions})

def _eval_node(node, row, functions):
    match node:
        case ast.Constant(value):
            return value
        case ast.Name(id):
            if id in row:
                return row[id]
            if id in functions:
                return functions[id]
            raise ValueError(f"nombre desconocido: {id!r}")
        case ast.BinOp(op, left, right):
            return _BINOPS[type(op)](_eval_node(left, ...), _eval_node(right, ...))
        case ast.UnaryOp(op, operand):
            return _UNARY[type(op)](_eval_node(operand, ...))
        case ast.Compare(left, ops, comparators):
            ...
        case ast.Call(func, args):
            # func es ast.Name con id en `functions` (integradas + add_function)
            ...
    raise ValueError(f"expresión no permitida: {ast.dump(node)}")
```

Reglas:

- Solo literales, operadores aritméticos/comparación, nombres de campo y
  funciones (integradas + `add_function`). Sin subíndices, atributos arbitrarios,
  comprehensions, imports, `lambda` ni acceso a `__`.
- **Funciones integradas**:
  - `IF(cond)` → `1` si `cond` es verdadero, `0` si no (campo comparativo).
  - `lower(x)`, `upper(x)`, `concat(a, b, ...)` para texto.
  - `round(x[, n])`, `abs(x)` para números.
  - Lógica/comparación → `1|0`: `AND(a, b, ...)`, `OR(a, b, ...)`, `NOT(x)`,
    `IN(x, a, b, ...)`, `BETWEEN(x, lo, hi)`.
  - Concatenación directa de cadenas con `+` (`"a" + "b"`).
- **`TOTAL("seccion.nombre")`**: referencia a un total nombrado de otra sección.
  Solo disponible en `total(..., expression=...)`; se resuelve en la **segunda
  fase** (porcentajes/razones). No está disponible en `add_field` (se evalúa antes
  de conocer los totales).
- **Funciones registradas**: `add_function` (expresión, por renglón) y
  `add_aggregate` (para `custom:<n>`, `fn(rows, column) -> value`).
- Errores de tipo (p. ej. `str * int`) se propagan como `ValueError` con el
  contexto del renglón.

---

## 6. Plantillas

Sintaxis `{{token}}` (sin colisión con el placeholder `{0}` de `Query`/`Filter` ni
con `str.format`):

- `{{campo}}` → campo del renglón (o del `key` del grupo, en header/footer).
- `{{param.N}}` → `params[N]` de la consulta.
- `{{total.NOMBRE}}` → valor del total identificado con `name=NOMBRE` en el
  mismo corte.
- `{{total.SECCION.NOMBRE}}` → valor de un total de **otra sección** (referencia
  cruzada, p. ej. `{{total.global.total_gral}}`).

Resolución en dos fases: los objetos `Total` se crean al declararlos (con su
`name`); durante `run()` se agregan (rellenando `value`) y **luego** se renderizan
las plantillas `header`/`footer` con acceso a los totales del grupo. Por eso
`{{total.NOMBRE}}` funciona tanto en `header` como en `footer`.

Implementación trivial:

```python
# encinorm_report/template.py
import re
_TOKEN = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_.]*)\}\}")

def render(template: str, ctx: dict, params: list) -> str:
    def repl(m):
        token = m.group(1)
        if token.startswith("param."):
            i = int(token.split(".", 1)[1])
            return str(params[i])
        return str(ctx.get(token, ""))
    return _TOKEN.sub(repl, template)
```

`{{total.NOMBRE}}`/`{{total.SECCION.NOMBRE}}` se resuelven en la fase de totales
(dos fases) y se **inyectan en `ctx`** antes de llamar a `render()`; este último
solo interpola `param.*` y los campos ya presentes en `ctx`.

> Si en el futuro se requiere formato (`{{fecha|%Y-%m-%d}}`) o condiciones, se
> delega a un motor real (Jinja2) como dependencia opcional; el árbol canónico no
> cambia.

---

## 7. Agrupación y agregados

Algoritmo de `run()`:

0. **Sin cortes declarados**: si no se llamó a `group()`, `run()` envuelve todas
   las filas como `detail` de un grupo implícito `name="global"` (sin header/
   footer/totals), produciendo una lista plana.
1. **Enriquecer** cada renglón: evaluar `add_field`/`link`/`image` y añadir las
   columnas en el orden indicado. Un campo con `after=None` es **oculto**: se
   calcula igualmente (queda disponible para expresiones y totales), pero no se
   incluye en `columns`/`detail`. Un campo `cumulative="sum"` acumula el valor de
   su expresión a lo largo de los renglones previos (saldo corrido).
2. **Ordenar** las filas por las columnas de los cortes, de raíz a hoja
   (agrupación por cortes adyacentes, sin depender de `ORDER BY` del SQL). Cada
   corte puede tener una o varias columnas (clave simple o compuesta).
3. **Recorrer** la jerarquía de `GroupSpec` (los grupos declarados sin `parent`
   cuelgan del grupo raíz `global`):
   - En cada grupo, partir las filas por el valor de sus `columns` (una clave
     compuesta se compara como tupla `(col1, col2, …)`; `None` → una sola
     partición global). El `key` resultante guarda `{col: valor, …}`.
   - Crear los objetos `Total` (con su `name`) y acumular `totals` base; recursar
     los hijos (detalle y subgrupos).
4. **Totales dependientes (fase B)**: tras calcular todos los totales base,
   resolver los `total(expression=...)` que usan `TOTAL("seccion.nombre")`
   (porcentajes/razones contra un total de referencia).
5. **Orden/Top-N/ceros (fase C)**: aplicar `order_by` (por columna, `total`
   nombrado o `expression`), `top(n)` y `suppress_zero` sobre los hijos de cada
   corte, ya con los totales calculados.
6. **Renderizar plantillas**: con todos los totales resueltos, interpolar
   `header`/`footer`, con contexto = primer renglón del grupo + `{{total.NOMBRE}}`
   / `{{total.SECCION.NOMBRE}}`.
7. **Total global** (grupo raíz, `columns=None`): agrega sobre todas las filas; un
   `count` cuyo `column` (del total) es `None` cuenta renglones.

Agregados (por grupo, sobre las filas del grupo):

| operator | semántica |
|----------|-----------|
| `sum` | suma de `column` (no numéricos → 0/None según política). |
| `avg` | promedio de `column`. |
| `count` | nº de filas con `column` no-nulo (o renglones si `column` es None). |
| `count_distinct` | valores distintos de `column`. |
| `max` / `min` | extremo de `column`. |
| `custom:<n>` | `aggregates[n](filas_del_grupo, column)` (registrada con `add_aggregate`). |

Con `expression` (en lugar de `column`), la expresión se evalúa por renglón y el
operador agrega los valores evaluados: `sum`/`avg`/`max`/`min` agregan esos
valores; `count` cuenta los renglones cuya evaluación es *truthy* (≠ 0/None);
`count_distinct` cuenta valores evaluados distintos.

`column` puede ser una columna calculada (`total`), por lo que los totales operan
sobre el resultado del evaluador. Alternativamente, un total con `expression`
habilita **totales condicionales**: con un campo comparativo
`es_par = IF(pedido_id % 2 == 0)` (1|0), `total("sum", expression="es_par * total")`
suma `total` solo en los renglones pares (en los impares `es_par * total == 0`).

> Colisión de nombres: si una columna calculada (`add_field`) repite el nombre de
> una columna fuente, el valor calculado **sobrescribe** al de origen (el
> evaluador lo ve primero). Para evitar ambigüedad, se recomienda usar nombres
> distintos.

- **Saldo corrido** (`add_field(..., cumulative="sum")`): el valor de la expresión
  se acumula sobre los renglones en el orden final; el campo resultante guarda el
  acumulado hasta ese renglón inclusive. El acumulador arranca en `start` (saldo
  inicial/apertura, por defecto `0`): `saldo_i = start + Σ(expr_j, j ≤ i)`.
- **Formato**: `ReportResult.formats` mapea columna → `Format` (moneda, porcentaje,
  decimales, miles, signo); los renderers lo aplican en la fase 2 sin alterar los
  valores crudos del árbol.
- **Jerarquía por datos** (`group(..., path="ruta", separator=".")`): cada renglón
  aporta una ruta (`"1.2.3"`) que se expande en grupos anidados de profundidad
  variable; los renglones hoja cuelgan del nivel más profundo. Es excluyente con
  `columns`.
- **Pivote** (`Section.pivot(...)`): agrupa por `(row_column, column_column)` y
  rellena la matriz `cells[fila][col]`; `show_totals=True` añade totales de fila y
  columna. Las filas/columnas se ordenan por su valor.

---

## 8. Renderers (patrón *visitor*)

El `ReportResult` es el contrato; cada renderer lo recorre. `render_html` y
`to_*` son métodos de conveniencia sobre `ReportResult` que delegan en clases.

```python
# encinorm_report/renderers.py
class HtmlRenderer:
    def __init__(self, classes: dict | None = None): ...
    def render(self, result: ReportResult) -> str: ...

class ExcelRenderer:
    def render(self, result: ReportResult, ws=None, styles: dict | None = None): ...

class CsvRenderer:
    def render(self, result: ReportResult, delimiter=",") -> str: ...

class TextRenderer:
    def render(self, result: ReportResult) -> str: ...

class PdfRenderer:
    def render(self, result: ReportResult, **opts): ...
```

`ReportResult` expone métodos de conveniencia que delegan en estos renderers con
imports perezosos (para no cargar dependencias opcionales):

```python
# encinorm_report/models.py (métodos sobre ReportResult)
class ReportResult(BaseModel):
    ...
    def render_html(self, classes: dict | None = None, repeat_header: bool = False) -> str: ...   # HtmlRenderer
    def to_excel(self, ws=None, styles: dict | None = None, formulas: bool = False): ...      # ExcelRenderer (extra openpyxl/xlsxwriter)
    def to_csv(self, delimiter: str = ",") -> str: ...                # CsvRenderer
    def to_text(self) -> str: ...                                     # TextRenderer
    def to_pdf(self, *, repeat_header: bool = True, **opts): ...      # PdfRenderer (extra reportlab/weasyprint)
```

> El JSON canónico es `model_dump()`; los métodos `render_*`/`to_*` son la fase 2
> (presentación) y nunca modifican el árbol.

Mapeo de nodos y celdas por destino:

| Nodo/Celda | HTML | Excel | CSV | PDF |
|------------|------|-------|-----|-----|
| `group` header/footer | `<tr class="group">` | fila con negrita | línea | párrafo/encabezado |
| `total` | `<tr class="total">` | fila con formato numérico | línea | fila de total |
| `detail` | `<tr>` | fila | fila | fila |
| `chart` | `<canvas>`/SVG (Chart.js) | gráfico nativo | tabla resumen (labels/values) | imagen (matplotlib/weasyprint) |
| `pivot` | `<table>` de dos dimensiones | hoja con matriz | matriz aplanada (fila, col, valor) | tabla de dos dimensiones |
| `kpi` | tarjeta/`<div>` | celda(s) de resumen | línea `label=value` | tarjeta de resumen |
| `Link` | `<a href target>` | hipervínculo (`cell.hyperlink`) | solo `label`/`href` | anotación de enlace |
| `Image` | `<img>` | imagen incrustada | — (URL) | imagen |

- `classes` de HTML: `{"group": "...", "total": "...", "columns": {"total": "text-end"}}`.
- **KPI**: los `kpi` se renderizan desde `ReportResult.kpis` (resumen del reporte),
  no desde `children` de un grupo.
- **Formato numérico**: los renderers aplican `ReportResult.formats` (moneda,
  miles, decimales, negativos en paréntesis, `%`, fechas) usando `locale`/stdlib,
  sin modificar el valor crudo del árbol.
- **Formato condicional**: los renderers aplican `ReportResult.styles` (p. ej.
  negativos en rojo) en HTML (clase/estilo) y Excel (formato de celda).
- **Saltos de página / encabezados**: `Group.page_break` inicia el corte en página
  nueva (PDF/HTML de impresión); `repeat_header=True` repite el encabezado de
  columnas en cada página.
- **Excel con fórmulas vivas**: `to_excel(..., formulas=True)` emite `=SUM(...)`
  para totales `sum` (referenciando rangos) en lugar de valores; el resto queda
  como valor.
- Excel usa `openpyxl`/`xlsxwriter`; PDF usa `reportlab`/`weasyprint`. Ambas son
  **dependencias opcionales** (extras del paquete).
- **Gráficos**: los renderers que no dibujan gráficos nativamente (CSV/Texto)
  degradan el nodo `chart` a una **tabla resumen** (`labels`/`values`); un renderer
  puede, alternativamente, delegar en un `Image` (Opción A) o un `Link` a una
  gráfica generada por separado. Los backends de gráficos (`Chart.js` en el
  front, `matplotlib`/`plotly` en el back) son dependencias opcionales.

---

## 9. Nombres y estructura del paquete

```
encinorm-report/
  pyproject.toml
  encinorm_report/
    __init__.py        # Report, ReportResult, renderers
    models.py          # Link, Image, Format, Total, Series, Chart, Pivot, ConditionalRule, Kpi, Detail, Group, ReportMeta, ReportResult
    report.py          # Report (builder)
    section.py         # Section
    expressions.py     # evaluador seguro
    template.py        # plantillas {{...}}
    aggregation.py     # agrupación + agregados
    charts.py          # derivación de labels/series desde totals/keys (datos para Chart)
    pivot.py           # construcción de matrices filas×columnas (Pivot)
    renderers/
      __init__.py
      html.py
      excel.py
      csv.py
      text.py
      pdf.py
  tests/ ...
```

`[project.optional-dependencies]`: `excel = ["openpyxl"]` (o `xlsxwriter`),
`pdf = ["reportlab"]` (o `weasyprint`) y `charts = ["matplotlib"]` (back
server-side; en el front se usa Chart.js sin dependencia de Python). El núcleo no
tiene dependencias (solo `pydantic`).

---

## 10. Integración con encinorm

Opcional y en una sola dirección (`encinorm-report` → `encinorm`):

```python
from encinorm import Query
from encinorm_report import Report

rows = await db.fetch_all(Query(sql, params))
result = Report(rows, params=params).group("global").run()
```

- No se modifica `encinorm`: se consume la salida pública (`fetch_all`,
  `fetch_many`, `db.paginate(Query(...))` → `Records.rows`).
- Si se prefiere "todo en uno", la alternativa es un **subpaquete opcional**
  `encinorm.report` con imports perezosos y **cero** dependencias nuevas en el
  núcleo (decisión en §11).

---

## 11. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Ubicación | **Proyecto separado** `encinorm-report`. Alternativa aceptable: subpaquete `encinorm.report` opcional. |
| 2 | Retorno | **JSON canónico** (`ReportResult`) como dato; HTML/Excel/PDF como renderers opcionales. |
| 3 | Evaluador | Parser `ast` con whitelist; **nunca** `eval`. |
| 4 | Plantillas | Sintaxis `{{campo}}` / `{{param.N}}` propia; sin colisión con `{0}`. |
| 5 | Acceso a sección | `group()` devuelve `Section`; `section(name)` para re-abrir. Sin `rep("x")` por `__call__`. |
| 6 | `count` | `count` (no-nulos) y `count_distinct` (únicos) como operadores separados. |
| 7 | `column_position` | Pista de presentación; vive en `Total`/`footer`, la aplica el renderer. |
| 8 | Parámetros | `Report(rows, params=[...])`; `{{param.N}}` interpola desde ahí. |
| 9 | Escalabilidad | Motor in-memory; agregados grandes se delegan a SQL (`ROLLUP`/`CUBE`). |
| 10 | Imágenes | `src` puede ser ruta, URL o *data URI* (incrusta sin archivos externos). |
| 11 | Funciones | `add_function` (expresión, por renglón) y `add_aggregate` (para `custom:<n>`, `fn(rows, column)`). |
| 12 | `{{total.NOMBRE}}` | El `Total` se crea al declararlo (con `name`); las plantillas se renderizan **después** de calcular los totales del grupo (dos pasadas), por lo que resuelve en `header` y `footer`. |
| 13 | `after` vs `detail()` | `detail()` es la base; un campo es visible si está en `detail()` **o** lleva `after`. `after` posiciona relativo a una columna visible (si no existe, al final). |
| 14 | Sin cortes | `run()` sin `group()` envuelve todo en un grupo implícito `global` (lista plana). |
| 15 | Colapso | `show_collapsed`/`default_collapsed` se guardan en `Group` para que los renderers interactivos los apliquen. |
| 16 | Colisión de nombres | Un campo calculado que repite una columna fuente **sobrescribe** a la fuente. |
| 17 | Agrupación multi-columna | `group(..., columns=...)` acepta `str` (simple) o `list/tuple` (compuesta); el `key` guarda `{col: valor, …}`. |
| 18 | Gráficos | Nodo declarativo `Chart` (`kind=pie|bar|line`) derivado de `totals`/`key` ya agregados; los renderers lo dibujan o degradan a tabla/imagen. |
| 19 | Formato numérico | `Format` por columna en `ReportResult.formats` (moneda, miles, decimales, paréntesis, `%`); lo aplican los renderers sin alterar el valor crudo. |
| 20 | Referencias cruzadas | `TOTAL("seccion.nombre")` en `total(expression=...)` y `{{total.SECCION.NOMBRE}}` en plantillas; resueltas en la **fase B** (tras los totales base). |
| 21 | Saldo corrido | `add_field(..., cumulative="sum", start=0)` acumula la expresión por renglón en el orden final; `start` es el saldo inicial (apertura). |
| 22 | Pivote (cross-tab) | Nodo `Pivot` (`rows` × `columns` → `cells`) con totales opcionales; los renderers lo aplanan o muestran como matriz. |
| 23 | Formato condicional | `add_style(...)` → `ReportResult.styles` (reglas `lt/le/gt/ge/eq/ne`); lo aplican HTML/Excel. |
| 24 | Jerarquía por datos | `group(..., path=, separator=)` expande rutas (`"1.2.3"`) en grupos anidados de profundidad variable; excluyente con `columns`. |
| 25 | Multi-query | `add_dataset(name, rows)` + `source=` en `group`/`chart`/`pivot`/`add_field`/`detail` para sub-reportes. |
| 26 | Lógica en expresiones | `AND`/`OR`/`NOT`/`IN`/`BETWEEN` como funciones que devuelven `1|0` (no operadores Python). |
| 27 | Fechas | `Format(kind="date", pattern="%d/%m/%Y")` aplicado por los renderers. |
| 28 | Orden/Top-N/ceros | `order_by` (columna/total/expresión) + `top(n)` + `suppress_zero`, aplicados en **fase C** (tras los totales). |
| 29 | Saltos de página | `Group.page_break` + opción `repeat_header` en HTML/PDF para encabezados repetidos. |
| 30 | Excel fórmulas | `to_excel(formulas=True)` emite `=SUM(...)` para totales `sum`; el resto como valor. |
| 31 | KPI | Nodo `Kpi` en `ReportResult.kpis` (tarjeta de indicador de primera clase). |

---

## 12. Dependencias

- **Núcleo**: `pydantic>=2` (misma familia que `Records`); el formateo numérico
  usa stdlib (`locale`), sin dependencias adicionales.
- **Extras**: `openpyxl`/`xlsxwriter` (Excel), `reportlab`/`weasyprint` (PDF),
  `matplotlib` (gráficos server-side). En el front, Chart.js (sin dependencia Python).
- Sin dependencias de `encinorm` (consume `list[dict]` plano).

---

## 13. Estrategia de testing

- **Expresiones**: aritmética (`cantidad*precio`), precedencia, `%`, `**`,
  comparaciones, funciones integradas (`IF/lower/upper/concat`) y `add_function`;
  **rechazo** de `eval`-style (acceso a atributos, subíndices, `import`, `lambda`).
- **Campos ocultos / comparativos**: `after=None` no aparece en `columns` pero sí
  en totales; `IF(cond)` devuelve `1|0`.
- **Totales condicionales**: `total("sum", expression="es_par * total")`; `count`
  sobre `expression` (conteo de renglones *truthy*).
- **Agregados**: `sum/avg/count/count_distinct/max/min` por grupo y global;
  `custom:<n>` vía `add_aggregate`.
- **Formato numérico**: `Format` (moneda, miles, decimales, paréntesis, `%`),
  `round`/`abs` en expresiones; el valor crudo no cambia.
- **Porcentajes/razones**: `total(expression="total / TOTAL('global.total_gral') * 100")`
  y `{{total.SECCION.NOMBRE}}` (fase B).
- **Saldo corrido**: `add_field("saldo", "debe - haber", cumulative="sum", start=0)`
  (incluye saldo de apertura distinto de cero).
- **Pivote**: matriz `rows`×`columns` correcta, totales de fila/columna, celdas
  ausentes en `None`/`0` según política.
- **Formato condicional**: reglas `lt/gt/eq/...` aplicadas en HTML/Excel.
- **Jerarquía por datos**: `path` anidado de profundidad variable (`"1"`, `"1.1"`,
  `"1.1.1"`), excluyente con `columns`.
- **Multi-query**: `add_dataset` + `source=` resuelve al conjunto correcto.
- **Lógica**: `AND`/`OR`/`NOT`/`IN`/`BETWEEN` → `1|0`; fechas con `Format.pattern`.
- **Orden/Top-N/ceros**: `order_by` por total desc, `top(n)`, `suppress_zero`.
- **Saltos de página**: `page_break` + `repeat_header` en PDF/HTML.
- **Excel fórmulas**: `to_excel(formulas=True)` produce `=SUM(...)`.
- **KPI**: `Report.kpi(...)` calcula `sum/avg/...` y se guarda en `ReportResult.kpis`.
- **Jerarquía**: grupos anidados (`parent`), `key` correcto, header/footer con
  plantillas, `{{total.NOMBRE}}` en header y footer (dos pasadas), `show_collapsed`/
  `default_collapsed` en `Group`, orden de `detail`.
- **Sin cortes**: `run()` sin `group()` produce un grupo implícito `global`.
- **Celdas enriquecidas**: `link` (los 4 `target`) e `image` (ruta/URL/data URI).
- **Gráficos**: `Chart` con `labels`/`series` derivados de `totals`/`key`;
  `pie`/`bar`/`line`; degradación a tabla resumen en CSV/Texto; round-trip JSON.
- **Renderers**: HTML (clases por columna/grupo/total), CSV (aplanado), Excel
  (hipervínculo/imagen/gráfico nativo), round-trip JSON (`model_dump`/`model_validate`).
- **Integración**: `Report(db.fetch_all(Query(...)))` contra SQLite (sin servidor).
- **Regresión**: la suite de `encinorm` no cambia (el paquete es independiente).

---

## 14. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `models.py` (`ReportResult` y nodos: `Chart`, `Pivot`, `ConditionalRule`, `Kpi`, `Format`) + `expressions.py` + `template.py`. |
| 2 | `report.py`/`section.py` (builder: `chart`, `pivot`, `kpi`, `set_format`, `add_style`, `add_dataset`, `cumulative`, `path`, `order_by`/`top`/`suppress_zero`/`page_break`) + `aggregation.py` (`run()`, tres fases) + `charts.py` + `pivot.py`. |
| 3 | Renderers `text`/`csv` + `html` (clases configurables; `chart` → Canvas/SVG; `pivot` → tabla; formato condicional; `page_break`/`repeat_header`). |
| 4 | Renderers `excel` y `pdf` (extras opcionales; `chart` → gráfico nativo / imagen; `pivot` → matriz; formato condicional; `formulas=True` en Excel). |
| 5 | Integración con `encinorm` (ejemplo `fetch_all`) + tests + docs de usuario. |
