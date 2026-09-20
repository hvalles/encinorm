"""REL-05: guard de enlaces muertos a `prompts/` en la documentación rastreada.

`prompts/` está gitignored (`.gitignore`), así que cualquier `.md` de `docs/` que
lo cite da 404 en PyPI/CI. Este guard barre SOLO `docs/**/*.md`: la limpieza del
`README.md` y su propio guard viven en el plan 08-05
(`tests/test_docs_hygiene.py`). Incluir el README aquí acoplaría ambos planes de
la misma wave y dejaría un test rojo esperando al otro.

El test es DB-free, sin red y sin subprocess: solo lee ficheros con `pathlib`.
"""

import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DOCS = _ROOT / "docs"
_RUTA_MUERTA = "prompts/"
_README = _ROOT / "README.md"

# Barrido congelado en import: la lista de páginas es parte del contrato del test.
_PAGINAS = sorted(_DOCS.rglob("*.md"))


def _id(pagina: pathlib.Path) -> str:
    return pagina.relative_to(_ROOT).as_posix()


def test_el_barrido_cubre_paginas_de_docs():
    assert _PAGINAS, "no se encontro ningun .md bajo docs/"


def test_el_barrido_no_incluye_el_readme():
    # El README lo guarda 08-05; barrerlo aqui crearia un deadlock de ola.
    assert _README not in _PAGINAS


@pytest.mark.parametrize("pagina", _PAGINAS, ids=_id)
def test_docs_no_citan_la_ruta_gitignored_prompts(pagina):
    contenido = pagina.read_text(encoding="utf-8")
    assert _RUTA_MUERTA not in contenido, (
        f"{_id(pagina)} referencia la ruta gitignored {_RUTA_MUERTA!r}; "
        "sustituyela por contenido rastreado (REL-05)"
    )
