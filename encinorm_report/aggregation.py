"""Agregación: enriquece renglones, construye el árbol de grupos y resuelve totales."""

from __future__ import annotations

from ._specs import GroupSpec
from .charts import build_chart
from .expressions import evaluate
from .models import (Chart, Detail, Format, Group, Image, Kpi, Link, Pivot,
                     ReportMeta, ReportResult, Total)
from .pivot import build_pivot
from .template import render as render_template


def _as_format(fmt):
    if fmt is None:
        return None
    if isinstance(fmt, Format):
        return fmt
    return Format(**fmt)


def _aggregate(operator, values):
    vals = [v for v in values if v is not None]
    if operator == "sum":
        return sum(vals)
    if operator == "avg":
        return (sum(vals) / len(vals)) if vals else None
    if operator == "count":
        return len(vals)
    if operator == "count_distinct":
        return len(set(vals))
    if operator == "max":
        return max(vals) if vals else None
    if operator == "min":
        return min(vals) if vals else None
    raise ValueError(f"operador desconocido: {operator!r}")


def _value_for(operator, column, expression, rows, functions, aggregates):
    if operator.startswith("custom:"):
        name = operator.split(":", 1)[1]
        return aggregates[name](rows, column)
    if expression is not None:
        vals = [evaluate(expression, r, functions) for r in rows]
        if operator == "count":
            return sum(1 for v in vals if v)
        if operator == "count_distinct":
            return len({v for v in vals if v is not None})
        return _aggregate(operator, vals)
    if operator == "count" and column is None:
        return len(rows)
    vals = [r.get(column) for r in rows]
    return _aggregate(operator, vals)


def _make_total(spec, value):
    return Total(
        operator=spec.operator, column=spec.column, expression=spec.expression,
        name=spec.name, label=spec.label, value=value,
        format=_as_format(spec.format), column_position=spec.column_position,
    )


def _make_value_fn(operator, column, expression, functions, aggregates):
    return lambda rows: _value_for(operator, column, expression, rows, functions, aggregates)


# --- enriquecimiento ---
def _build_link(spec, row):
    href = render_template(spec.href, row) if spec.href else ""
    label = render_template(spec.label, row) if spec.label else None
    return Link(target=spec.target, href=href, label=label)


def _build_image(spec, row):
    src = render_template(spec.src, row) if spec.src else ""
    alt = render_template(spec.alt, row) if spec.alt else None
    return Image(src=src, alt=alt, width=spec.width, height=spec.height)


def _enrich(report, source):
    rows = report._rows if source is None else report._datasets.get(source, [])
    out = []
    cum = {}
    for row in rows:
        enriched = dict(row)
        for f in report._fields:
            if f.source not in (None, source):
                continue
            if f.kind == "expr":
                if f.expression is None:
                    continue
                val = evaluate(f.expression, enriched, report._functions)
                if f.cumulative == "sum":
                    prev = cum.get(f.name, 0 if f.start is None else f.start)
                    val = prev + (val or 0)
                    cum[f.name] = val
                enriched[f.name] = val
            elif f.kind == "link":
                enriched[f.name] = _build_link(f, enriched)
            elif f.kind == "image":
                enriched[f.name] = _build_image(f, enriched)
        out.append(enriched)
    return out


# --- árbol de grupos ---
def _build_group_tree(report):
    specs = report._groups
    root = None
    for name in report._order:
        s = specs[name]
        if s.columns is None and s.path is None:
            root = s
            break
    if root is None:
        root = GroupSpec(name="global", columns=None)

    for name in report._order:
        s = specs[name]
        if s is root:
            continue
        parent = specs.get(s.parent) if s.parent else None
        if parent is not None:
            parent.children.append(s)
        else:
            root.children.append(s)
    return root


def _partition(spec, rows):
    if spec.columns is None:
        return [(None, list(rows))]
    index = {}
    order = []
    for r in rows:
        key = tuple(r.get(c) for c in spec.columns)
        if key not in index:
            index[key] = []
            order.append(key)
        index[key].append(r)
    return [
        ({c: v for c, v in zip(spec.columns, key)}, index[key]) for key in order
    ]


def _build_group(report, spec, sources, registry, deferred, visible):
    rows = sources.get(spec.source, sources[None])
    if spec.path is not None:
        return _build_path_group(report, spec, rows, registry, deferred, visible)
    result = []
    for key, part_rows in _partition(spec, rows):
        result.append(_build_instance(report, spec, key, part_rows, sources, registry, deferred, visible))
    return result


def _compute_totals_into(report, spec, rows, node, registry, deferred):
    for ts in spec.totals:
        if ts.expression and "TOTAL(" in ts.expression:
            total = _make_total(ts, None)
            deferred.append((total, ts, rows))
            node.totals.append(total)
        else:
            val = _value_for(ts.operator, ts.column, ts.expression, rows,
                             report._functions, report._aggregates)
            total = _make_total(ts, val)
            node.totals.append(total)
            if ts.name:
                key = f"{spec.name}.{ts.name}"
                registry[key] = registry.get(key, 0) + val


def _build_path_group(report, spec, rows, registry, deferred, visible):
    return _make_path_node(report, spec, rows, 0, registry, deferred, visible)


def _segs(r, spec):
    return [s for s in str(r.get(spec.path, "")).split(spec.separator) if s != ""]


def _make_path_node(report, spec, rows, level, registry, deferred, visible):
    buckets = {}
    order = []
    for r in rows:
        segs = _segs(r, spec)
        seg = segs[level] if level < len(segs) else ""
        if seg not in buckets:
            buckets[seg] = []
            order.append(seg)
        buckets[seg].append(r)

    results = []
    for seg in order:
        sub_rows = buckets[seg]
        segs0 = _segs(sub_rows[0], spec)
        cur_path = spec.separator.join(segs0[: level + 1])
        node = Group(
            name=spec.name, key={spec.path: cur_path},
            show_collapsed=spec.show_collapsed,
            default_collapsed=spec.default_collapsed,
            page_break=spec.page_break,
        )
        node._first_row = dict(sub_rows[0])
        node._header_tpl = spec.header
        node._footer_tpl = spec.footer
        _compute_totals_into(report, spec, sub_rows, node, registry, deferred)

        leaf_rows = [r for r in sub_rows if len(_segs(r, spec)) == level + 1]
        branch_rows = [r for r in sub_rows if len(_segs(r, spec)) > level + 1]

        children = []
        if leaf_rows:
            children += [
                Detail(row={k: v for k, v in r.items() if k in visible}) for r in leaf_rows
            ]
        if branch_rows:
            children += [
                n for n, _ in _make_path_node(report, spec, branch_rows, level + 1, registry, deferred, visible)
            ]
        node.children = children
        results.append((node, sub_rows))
    return results


def _build_instance(report, spec, key, rows, sources, registry, deferred, visible):
    node = Group(
        name=spec.name, key=key,
        show_collapsed=spec.show_collapsed,
        default_collapsed=spec.default_collapsed,
        page_break=spec.page_break,
    )
    node._first_row = dict(rows[0]) if rows else {}
    node._header_tpl = spec.header
    node._footer_tpl = spec.footer

    # children: subgrupos o detalle
    child_pairs = []
    if spec.children:
        for child_spec in spec.children:
            child_pairs.extend(_build_group(report, child_spec, sources, registry, deferred, visible))
        node.children = [n for n, _ in child_pairs]
    else:
        node.children = [
            Detail(row={k: v for k, v in r.items() if k in visible}) for r in rows
        ]

    # totals base + registro + diferidos
    _compute_totals_into(report, spec, rows, node, registry, deferred)

    # fase C sobre los hijos (grupos/detalle), antes de añadir chart/pivot
    node.children = _apply_order(spec, node.children)

    # charts y pivots al final
    extras = []
    for cs in spec.charts:
        fn = _make_value_fn(cs.operator, cs.column, cs.expression,
                            report._functions, report._aggregates)
        extras.append(build_chart(cs, child_pairs, node.totals, fn))
    for ps in spec.pivots:
        fn = _make_value_fn(ps.operator, ps.value_column, ps.value_expression,
                            report._functions, report._aggregates)
        extras.append(build_pivot(ps, rows, fn))
    node.children = node.children + extras

    return node, rows


def _apply_order(spec, children):
    if spec.order_by:
        ob = spec.order_by
        reverse = ob.get("direction") == "desc"
        children = sorted(children, key=lambda c: _sort_key(c, ob), reverse=reverse)
    if spec.suppress_zero:
        sz = spec.suppress_zero
        children = [c for c in children if not _is_zero(c, sz)]
    if spec.top_n is not None:
        children = children[: spec.top_n]
    return children


def _sort_key(child, ob):
    total = ob.get("total")
    expression = ob.get("expression")
    column = ob.get("column")
    if total:
        for t in getattr(child, "totals", []):
            if t.name == total:
                return t.value
        return None
    if expression:
        return evaluate(expression, getattr(child, "_first_row", {}), {})
    if column:
        if isinstance(child, Group):
            return child.key.get(column) if child.key else None
        if isinstance(child, Detail):
            return child.row.get(column)
        return None
    return 0


def _is_zero(child, sz):
    total = sz.get("total")
    column = sz.get("column")
    if total:
        for t in getattr(child, "totals", []):
            if t.name == total:
                return t.value is None or t.value == 0
        return False
    if column:
        if isinstance(child, Group):
            v = child.key.get(column) if child.key else None
        elif isinstance(child, Detail):
            v = child.row.get(column)
        else:
            v = None
        return v is None or v == 0
    return False


# --- fase B ---
def _resolve_deferred(deferred, functions, aggregates, registry):
    fns = dict(functions)
    fns["TOTAL"] = lambda name: registry.get(name)
    for total, spec, rows in deferred:
        total.value = _value_for(spec.operator, spec.column, spec.expression, rows, fns, aggregates)


# --- plantillas (fase final) ---
def _render_templates(node, registry, params):
    if not isinstance(node, Group):
        return
    ctx = dict(node._first_row)
    if node.key:
        ctx.update(node.key)
    for t in node.totals:
        if t.name:
            ctx[f"total.{t.name}"] = t.value
    for key, val in registry.items():
        ctx[f"total.{key}"] = val
    if node._header_tpl:
        node.header = render_template(node._header_tpl, ctx, params)
    if node._footer_tpl:
        node.footer = render_template(node._footer_tpl, ctx, params)
    for child in node.children:
        _render_templates(child, registry, params)


def _build_kpis(report, sources):
    kpis = []
    for spec in report._kpis:
        if spec.value is not None:
            value = spec.value
        else:
            rows = sources.get(spec.source, sources[None])
            value = _value_for(spec.operator, spec.column, spec.expression, rows,
                               report._functions, report._aggregates)
        kpis.append(Kpi(label=spec.label, value=value, format=_as_format(spec.format)))
    return kpis


def _visible_columns(report):
    cols = list(report._detail)
    for f in report._fields:
        if f.after is not None and f.name not in cols:
            if f.after in cols:
                cols.insert(cols.index(f.after) + 1, f.name)
            else:
                cols.append(f.name)
    return cols


def build(report) -> ReportResult:
    visible = _visible_columns(report)
    visible_set = set(visible)

    sources = {None: _enrich(report, None)}
    for name in report._datasets:
        sources[name] = _enrich(report, name)

    root_spec = _build_group_tree(report)
    registry = {}
    deferred = []
    root_nodes = _build_group(report, root_spec, sources, registry, deferred, visible_set)

    root = root_nodes[0][0] if root_nodes else Group(name="global", key=None)

    _resolve_deferred(deferred, report._functions, report._aggregates, registry)
    _render_templates(root, registry, report._params)

    return ReportResult(
        meta=ReportMeta(title=report._title, params=list(report._params)),
        columns=visible,
        formats=dict(report._formats),
        styles=list(report._styles),
        kpis=_build_kpis(report, sources),
        root=root,
    )
