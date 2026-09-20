"""REL-04: guard de fuente de la enumeración de rupturas y de la guía de migración.

Congela cuatro propiedades sin tocar motores ni red: (a) `docs/MIGRATION-0.3.md`
existe y tiene secciones con pares Antes/Después; (b) la página está registrada
en la nav de `mkdocs.yml`; (c) `CHANGELOG.md` enumera cada cambio incompatible con
un par viejo/nuevo; y (d) ese guard es *file-wide*.

El escaneo del CHANGELOG es DELIBERADAMENTE file-wide (no scopeado a
`[Unreleased]`): la promoción de 08-03 renombra `[Unreleased]` a `[0.3.0rc1]` y
deja un `[Unreleased]` vacío, así que un guard limitado a ese bloque fallaría en
CI y, con `publish: needs: [ci]`, bloquearía el release. La unicidad de
`### Eliminado` se asserta aquí (file-wide) y es el guard que impide que dos
planes dupliquen ese heading: su único owner es 08-06.
"""

import pathlib
import re

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CHANGELOG = _ROOT / "CHANGELOG.md"
_MKDOCS = _ROOT / "mkdocs.yml"
_MIGRATION = _ROOT / "docs" / "MIGRATION-0.3.md"

_MARCA = "CAMBIO DE COMPORTAMIENTO"
_MARCA_ELIMINADO = "### Eliminado"
# Marcadores (case-insensitive) de comportamiento viejo y nuevo por entrada.
_VIEJO = re.compile(r"viejo:|antes[,\s]|antes\b", re.IGNORECASE)
_NUEVO = re.compile(r"nuevo:|ahora|despu[eé]s", re.IGNORECASE)


def _leer(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _marcas_changelog(texto: str) -> list[int]:
    """Posiciones de cada marca `CAMBIO DE COMPORTAMIENTO` en TODO el fichero."""
    return [m.start() for m in re.finditer(re.escape(_MARCA), texto)]


def _entrada_de(texto: str, posicion: int) -> str:
    """Extrae la entrada (bullet `- ` de nivel superior) que contiene la marca."""
    inicio = texto.rfind("\n- ", 0, posicion)
    inicio = 0 if inicio == -1 else inicio + 1
    resto = texto[posicion:]
    fin = re.search(r"\n(?=- |## |### )", resto)
    return texto[inicio:] if fin is None else texto[inicio : posicion + fin.start() + 1]


def _secciones_guia(texto: str) -> list[str]:
    """Divide la guía por encabezados `## ` de nivel 2 (excluye el preámbulo)."""
    partes = re.split(r"^## ", texto, flags=re.MULTILINE)
    return [parte for parte in partes[1:] if parte.strip()]


def test_migration_guide_existe_y_tiene_secciones():
    assert _MIGRATION.is_file()
    texto = _leer(_MIGRATION)
    assert len(_secciones_guia(texto)) >= 8


def test_migration_guide_cada_seccion_tiene_par_antes_despues():
    texto = _leer(_MIGRATION)
    secciones = _secciones_guia(texto)
    assert secciones
    for seccion in secciones:
        assert "Antes" in seccion, seccion.splitlines()[0]
        assert "Después" in seccion, seccion.splitlines()[0]


def test_mkdocs_nav_incluye_guia_migracion():
    assert "MIGRATION-0.3.md" in _leer(_MKDOCS)


def test_changelog_marcas_file_wide():
    # File-wide a propósito: sobrevive a la promoción de `[Unreleased]`.
    assert len(_marcas_changelog(_leer(_CHANGELOG))) >= 10


def test_changelog_cada_marca_declara_viejo_y_nuevo():
    texto = _leer(_CHANGELOG)
    marcas = _marcas_changelog(texto)
    assert marcas
    for posicion in marcas:
        entrada = _entrada_de(texto, posicion)
        assert _VIEJO.search(entrada), entrada.splitlines()[0]
        assert _NUEVO.search(entrada), entrada.splitlines()[0]


def test_changelog_guard_es_file_wide_no_depende_de_unreleased():
    # Un CHANGELOG ya promovido (sin `[Unreleased]`) debe seguir pasando el guard.
    sintetico = "## [0.3.0] - 2026-10-01\n\n### Cambiado\n\n" + "\n".join(
        f"- **{_MARCA} (X{i}).** Viejo: viejo {i}; nuevo: nuevo {i}." for i in range(10)
    )
    marcas = _marcas_changelog(sintetico)
    assert len(marcas) == 10
    assert "[Unreleased]" not in sintetico
    for posicion in marcas:
        entrada = _entrada_de(sintetico, posicion)
        assert _VIEJO.search(entrada)
        assert _NUEVO.search(entrada)


def test_eliminado_heading_unico():
    """08-06 es el único owner: EXACTAMENTE un `### Eliminado` en TODO el fichero.

    File-wide por la misma razón que el guard de `CAMBIO DE COMPORTAMIENTO`: en
    el commit tagueado el heading vive en `[0.3.0rc1]`/`[0.3.0]`, no en
    `[Unreleased]`; un conteo scopeado daría 0 y bloquearía el release.
    """
    texto = _leer(_CHANGELOG)
    assert len(re.findall(r"^### Eliminado\s*$", texto, re.MULTILINE)) == 1


def test_changelog_eliminado_nombra_retiradas_reales():
    """La sección de retiradas nombra los símbolos retirados de la línea 0.3.0."""
    texto = _leer(_CHANGELOG)
    for simbolo in ("set_default_db", "get_default_db", "SECRET", "GET_DB", "last_id"):
        assert simbolo in texto, simbolo
