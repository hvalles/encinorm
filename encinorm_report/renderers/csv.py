"""Renderer CSV (aplanado)."""

from __future__ import annotations

import csv
import io

from ..models import Chart, Detail, Group, Pivot
from ._format import format_value


class CsvRenderer:
    def __init__(self, delimiter: str = ","):
        self.delimiter = delimiter

    def render(self, result) -> str:
        out = io.StringIO()
        writer = csv.writer(out, delimiter=self.delimiter)
        for kpi in result.kpis:
            writer.writerow([kpi.label, format_value(kpi.value, kpi.format)])
        self._walk(result.root, result, writer)
        return out.getvalue().rstrip("\r\n")

    def _walk(self, node, result, writer):
        if isinstance(node, Group):
            if node.header:
                writer.writerow([node.header])
            for child in node.children:
                self._walk(child, result, writer)
            for t in node.totals:
                label = t.label or t.name or t.operator
                fmt = t.format or (result.formats.get(t.column) if t.column else None)
                writer.writerow([label, format_value(t.value, fmt)])
            if node.footer:
                writer.writerow([node.footer])
        elif isinstance(node, Detail):
            writer.writerow(
                [format_value(node.row.get(c), result.formats.get(c)) for c in result.columns]
            )
        elif isinstance(node, Chart):
            writer.writerow([f"chart:{node.kind}", node.title or ""])
            for s in node.series:
                writer.writerow([s.label or "", *s.values])
        elif isinstance(node, Pivot):
            writer.writerow(["", *[str(c) for c in node.columns]])
            for i, row in enumerate(node.rows):
                writer.writerow([row, *["" if c is None else c for c in node.cells[i]]])
