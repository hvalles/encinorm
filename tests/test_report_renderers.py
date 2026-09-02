import pytest

from encinorm_report import Report
from encinorm_report.models import Format
from encinorm_report.renderers._format import format_value


def test_format_value_currency():
    fmt = Format(kind="currency", symbol="$", decimals=2, thousands=True, negative="paren")
    assert format_value(1234.5, fmt) == "$1,234.50"
    assert format_value(-1234.5, fmt) == "($1,234.50)"


def test_format_value_percent():
    fmt = Format(kind="percent", decimals=1, percent_scale=True)
    assert format_value(0.256, fmt) == "25.6%"


def test_format_value_number():
    assert format_value(1.234, Format(decimals=2)) == "1.23"
    assert format_value(None, Format()) == ""
    assert format_value(5, None) == "5"


def test_text_renderer():
    rows = [{"agente": "Ana", "monto": 100}, {"agente": "Bob", "monto": 200}]
    rep = Report(rows)
    rep.group("por_agente", columns="agente")
    rep.section("por_agente").header("Agente {{agente}}")
    rep.section("por_agente").total("sum", "monto")
    rep.group("global")
    rep.section("global").total("sum", "monto")
    rep.detail("agente", "monto")
    result = rep.run()

    text = result.to_text()
    assert "Agente Ana" in text
    assert "Agente Bob" in text
    assert "sum: 100" in text
    assert "sum: 300" in text


def test_csv_renderer():
    rows = [{"sku": "A", "cantidad": 2}, {"sku": "B", "cantidad": 1}]
    rep = Report(rows)
    rep.detail("sku", "cantidad")
    result = rep.run()
    csv_out = result.to_csv()
    assert "A,2" in csv_out
    assert "B,1" in csv_out


def test_html_renderer_and_styles():
    rows = [{"total": -5}, {"total": 10}]
    rep = Report(rows)
    rep.detail("total")
    rep.add_style("total", when="lt", value=0, color="red")
    result = rep.run()

    html_out = result.render_html()
    assert "<table>" in html_out
    assert "<th>total</th>" in html_out
    assert "color:red" in html_out


def test_excel_renderer():
    pytest.importorskip("openpyxl")
    rows = [{"sku": "A", "cantidad": 2}, {"sku": "B", "cantidad": 1}]
    rep = Report(rows)
    rep.detail("sku", "cantidad")
    rep.group("global")
    rep.section("global").total("sum", "cantidad")
    result = rep.run()

    ws = result.to_excel()
    assert ws["A1"].value == "sku"
    assert ws["B1"].value == "cantidad"
    assert ws["A2"].value == "A"
    assert ws["B2"].value == 2
    assert ws["A4"].value == "sum"


def test_excel_formulas():
    pytest.importorskip("openpyxl")
    rows = [{"sku": "A", "cantidad": 2}, {"sku": "B", "cantidad": 1}]
    rep = Report(rows)
    rep.detail("sku", "cantidad")
    rep.group("global")
    rep.section("global").total("sum", "cantidad")
    result = rep.run()

    ws = result.to_excel(formulas=True)
    formula_cells = [
        c.value for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=")
    ]
    assert any("SUM" in f for f in formula_cells)


def test_excel_number_format():
    pytest.importorskip("openpyxl")
    rows = [{"total": 1234.5}]
    rep = Report(rows)
    rep.detail("total")
    rep.set_format("total", kind="currency", symbol="$", decimals=2, thousands=True)
    result = rep.run()
    ws = result.to_excel()
    assert ws["A2"].value == 1234.5
    assert "$" in ws["A2"].number_format


def test_pdf_renderer():
    pytest.importorskip("reportlab")
    rows = [{"sku": "A", "cantidad": 2}]
    rep = Report(rows)
    rep.detail("sku", "cantidad")
    result = rep.run()
    pdf = result.to_pdf()
    assert pdf[:5] == b"%PDF-"

