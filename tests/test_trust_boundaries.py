"""CFG-05: fronteras de confianza de `Filter.raw`/`Query`/`db.fn.*`.

Congela dos propiedades: (a) los parsers HTTP/GraphQL no pueden emitir
`Filter.raw` (sus conjuntos de operadores son cerrados), y (b) la página de
fronteras existe con los tres encabezados y al menos un ejemplo marcado como
inseguro. No cambia el contrato de `Filter.raw`: solo lo documenta.
"""

import inspect
import pathlib

import pytest

from encino_orm.model import Filter

_DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs" / "trust-boundaries.md"


def _assert_no_raw_construction(module) -> None:
    """Ningún parser construye `Filter.raw` (ni por nombre ni por `.raw(`)."""
    src = inspect.getsource(module)
    assert "Filter.raw" not in src
    assert ".raw(" not in src


def test_parsers_http_no_emiten_raw():
    from encino_orm.http import parsing

    _assert_no_raw_construction(parsing)
    # Conjunto CERRADO de operadores: `raw` no existe en el parser.
    assert "raw" not in parsing._OP_MAP
    with pytest.raises(KeyError):
        parsing._apply_op("raw", "campo", "x")


def test_parsers_graphql_no_emiten_raw():
    from encino_orm.graphql import filters

    _assert_no_raw_construction(filters)
    with pytest.raises(ValueError):
        filters._apply_op("campo", "raw", "x")


def test_docs_trust_boundaries_presentes():
    text = _DOCS.read_text(encoding="utf-8")
    for heading in ("## Filter.raw", "## Query", "## db.fn.*"):
        assert heading in text
    assert "INSEGURO" in text


def test_filter_raw_reemite_verbatim():
    sql, params = Filter.raw("x = {0}", [1]).to_sql()
    assert sql == "x = {0}"
    assert params == [1]


def test_filter_raw_liga_los_valores():
    valor = "'; DROP TABLE t --"
    sql, params = Filter.raw("nombre = {0}", [valor]).to_sql()
    # El valor nunca aparece en el fragmento: viaja ligado.
    assert valor not in sql
    assert params == [valor]
