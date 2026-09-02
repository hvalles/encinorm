"""Renderer de texto plano (inspección)."""

from __future__ import annotations

from ..models import Chart, Detail, Group, Pivot
from ._format import format_value


class TextRenderer:
    def render(self, result) -> str:
        lines = []
        for kpi in result.kpis:
            lines.append(f"{kpi.label}: {format_value(kpi.value, kpi.format)}")
        self._walk(result.root, 0, result, lines)
        return "\n".join(lines)

    def _walk(self, node, depth, result, lines):
        indent = "  " * depth
        if isinstance(node, Group):
            if node.header:
                lines.append(f"{indent}{node.header}")
            for child in node.children:
                self._walk(child, depth + 1, result, lines)
            for t in node.totals:
                label = t.label or t.name or t.operator
                fmt = t.format or (result.formats.get(t.column) if t.column else None)
                lines.append(f"{indent}{label}: {format_value(t.value, fmt)}")
            if node.footer:
                lines.append(f"{indent}{node.footer}")
        elif isinstance(node, Detail):
            cells = "  ".join(
                f"{c}={format_value(node.row.get(c), result.formats.get(c))}"
                for c in result.columns
            )
            lines.append(f"{indent}{cells}")
        elif isinstance(node, Chart):
            lines.append(f"{indent}[chart:{node.kind}] {node.title or ''}")
            for s in node.series:
                lines.append(f"{indent}  {s.label or ''}: {', '.join(map(str, s.values))}")
        elif isinstance(node, Pivot):
            lines.append(f"{indent}[pivot] {node.title or ''}")
            lines.append(f"{indent}  (cols) {' '.join(map(str, node.columns))}")
            for i, row in enumerate(node.rows):
                cells = " ".join("" if c is None else str(c) for c in node.cells[i])
                lines.append(f"{indent}  {row}: {cells}")
