"""REL-05: guard de higiene del README y de `.env.example`.

Congela la parte de usuario del release sin tocar motores ni red: (a) el README
recomienda pinnear con `~=0.2.6` y no con un rango abierto; (b) el README ya no
enlaza la ruta gitignored `prompts/` y sí enlaza la guía de migración; (c) el
README marca las credenciales de desarrollo como solo-dev; y (d) `.env.example`
existe con las variables de los seis motores y el mismo aviso.

El barrido de `docs/**` es DELIBERADAMENTE ajeno a este guard: esa limpieza y su
propio test viven en el plan 08-07 (`tests/test_docs_links.py`). Incluir aquí un
barrido de `docs/` dejaría el test rojo hasta entonces.
"""

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_README = _ROOT / "README.md"
_ENV_EXAMPLE = _ROOT / ".env.example"

_PIN = "~=0.2.6"
_MIGRATION_LINK = "docs/MIGRATION-0.3.md"
_DEAD_PATH = "prompts/"
_OPEN_RANGE = ">=0.2.6"
_AVISO = "solo para desarrollo local"

# Variables cuyo namespace REL-05 exige ejemplificar por motor.
_ENV_VARS = (
    "ENCINO_ORM_MYSQL_HOST",
    "ENCINO_ORM_MARIADB_HOST",
    "ENCINO_ORM_POSTGRES_HOST",
    "ENCINO_ORM_MSSQL_HOST",
    "ENCINO_ORM_ORACLE_HOST",
    "ENCINO_ORM_REDIS_URL",
)


def _leer(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def test_readme_recomienda_pin_tilde():
    assert _PIN in _leer(_README)


def test_readme_no_recomienda_rango_abierto():
    # La recomendacion en el README debe ser ~=; un >=0.2.6 la reinstalaria.
    assert _OPEN_RANGE not in _leer(_README)


def test_readme_no_enlaza_la_ruta_gitignored_prompts():
    assert _DEAD_PATH not in _leer(_README)


def test_readme_enlaza_la_guia_de_migracion():
    assert _MIGRATION_LINK in _leer(_README)


def test_readme_avisa_credenciales_solo_dev():
    assert _AVISO in _leer(_README).lower()


def test_env_example_existe_con_aviso_dev_only():
    assert _ENV_EXAMPLE.is_file()
    assert _AVISO in _leer(_ENV_EXAMPLE).lower()


def test_env_example_declara_las_variables_de_los_seis_motores():
    texto = _leer(_ENV_EXAMPLE)
    faltantes = [var for var in _ENV_VARS if var not in texto]
    assert not faltantes, faltantes
