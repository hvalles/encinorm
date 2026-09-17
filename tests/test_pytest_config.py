"""Guards de regresion de la configuracion endurecida de pytest (CI-05, CI-06).

Cada knob se comprueba dos veces: una como valor de configuracion leido de
`pyproject.toml` y otra como comportamiento real de un proceso pytest hijo, de
modo que un knob presente pero inerte no pueda pasar por gate.
"""

import functools
import re
import subprocess
import sys
from pathlib import Path

try:  # Python >= 3.11
    import tomllib
except ModuleNotFoundError:  # Python 3.10: `tomli` llega transitivamente via pytest
    import tomli as tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Ficheros que DEBEN aportar tests marcados `integration`. Si cualquiera deja de
# aportarlos, el comando de `README.md:130` vuelve a ser un no-op silencioso.
_ARCHIVOS_CON_INTEGRATION = (
    "tests/test_mysql.py",
    "tests/test_postgresql.py",
    "tests/test_mariadb.py",
    "tests/test_mssql.py",
    "tests/test_oracle.py",
    "tests/test_redis_cache.py",
)

# Presupuesto de feedback de 01-VALIDATION.md: ~8 s. Este fichero lanza cuatro
# subprocess de pytest (dos sondas + la seleccion de markers), que añaden
# ~4-5 s al total; el coste esta medido en 01-03-SUMMARY.md.
_PYTEST_ARGS = ["-q", "--no-header", "-p", "no:cacheprovider"]

# `41/510 tests collected (469 deselected)` o `510 tests collected`.
_COLLECTED_RE = re.compile(r"(\d+)(?:/(\d+))? tests collected")


def _ini_options() -> dict:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["pytest"]["ini_options"]


def _run_pytest(*args: str) -> subprocess.CompletedProcess:
    """Ejecuta pytest en un proceso hijo con la configuracion del repositorio."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write_probe(folder: Path, name: str, body: str) -> Path:
    probe = folder / name
    probe.write_text(body, encoding="utf-8")
    return probe


def _collection_counts(*marker_args: str) -> tuple[int, int]:
    """Devuelve `(seleccionados, total)` del resumen de `--collect-only -q`."""
    result = _run_pytest("--collect-only", *_PYTEST_ARGS, *marker_args)
    assert result.returncode == 0, result.stdout + result.stderr
    match = _COLLECTED_RE.search(result.stdout)
    assert match, result.stdout
    selected = int(match.group(1))
    total = int(match.group(2)) if match.group(2) else selected
    return selected, total


@functools.cache
def _integration_node_ids() -> tuple[str, ...]:
    """Node IDs seleccionados por `-m "integration"`.

    Se cachea: la sonda es de solo lectura sobre una configuracion estatica y
    evita repetir el subprocess entre las dos comprobaciones que la usan.
    """
    result = _run_pytest("--collect-only", *_PYTEST_ARGS, "-m", "integration")
    assert result.returncode == 0, result.stdout + result.stderr
    return tuple(line.strip() for line in result.stdout.splitlines() if "::" in line)


class TestPyprojectHardening:
    """Cada knob de la Task 1 esta presente con su valor exacto."""

    def test_addopts_incluye_strict_markers(self):
        assert "--strict-markers" in _ini_options()["addopts"]

    def test_xfail_strict_activo(self):
        assert _ini_options()["xfail_strict"] is True

    def test_filterwarnings_empieza_por_error(self):
        assert _ini_options()["filterwarnings"][0] == "error"

    def test_loop_scopes_explicitos(self):
        opts = _ini_options()
        assert opts["asyncio_default_fixture_loop_scope"] == "function"
        assert opts["asyncio_default_test_loop_scope"] == "function"

    def test_los_cuatro_markers_estan_registrados(self):
        names = {entry.split(":")[0].strip() for entry in _ini_options()["markers"]}
        assert {"integration", "optional_engine", "concurrency", "benchmark"} <= names

    def test_se_conservan_las_claves_originales(self):
        opts = _ini_options()
        assert opts["asyncio_mode"] == "auto"
        assert opts["testpaths"] == ["tests"]
        assert opts["pythonpath"] == ["."]


class TestStrictMarkersBehaviour:
    """`--strict-markers` es funcional, no solo esta presente."""

    def test_marker_no_registrado_falla_la_coleccion(self, tmp_path):
        probe = _write_probe(
            tmp_path,
            "test_sonda_marker.py",
            "import pytest\n\n\n"
            "@pytest.mark.marker_que_no_existe\n"
            "def test_sonda():\n"
            "    assert True\n",
        )
        # `-c pyproject.toml` es lo que hace que la sonda herede el `addopts`
        # del repositorio (y por tanto `--strict-markers`).
        result = _run_pytest("-c", str(PYPROJECT), str(probe), *_PYTEST_ARGS)
        assert result.returncode != 0, result.stdout + result.stderr


class TestWarningsAsErrors:
    """`filterwarnings = ["error"]` es funcional, no solo esta presente."""

    def test_warning_emitido_falla_el_test(self, tmp_path):
        probe = _write_probe(
            tmp_path,
            "test_sonda_warning.py",
            "import warnings\n\n\n"
            "def test_sonda():\n"
            '    warnings.warn("sonda", UserWarning, stacklevel=1)\n'
            "    assert True\n",
        )
        result = _run_pytest("-c", str(PYPROJECT), str(probe), *_PYTEST_ARGS)
        assert result.returncode != 0, result.stdout + result.stderr


class TestMarkerSelectionRegression:
    """El comando documentado en `README.md:130` debe seleccionar de verdad.

    Sin este guard, borrar un `pytestmark` revertiria el comando del README a un
    no-op silencioso (T-01-07).
    """

    def test_integration_selecciona_un_conjunto_no_vacio(self):
        assert len(_integration_node_ids()) > 0

    def test_cada_fichero_de_motor_aporta_tests_de_integracion(self):
        ids = _integration_node_ids()
        for archivo in _ARCHIVOS_CON_INTEGRATION:
            assert any(node.startswith(archivo) for node in ids), (
                f"{archivo} no aporta ningun test marcado como integration; "
                "el comando documentado en README.md:130 volveria a ser un no-op"
            )

    def test_not_integration_deselecciona_algo(self):
        selected, total = _collection_counts("-m", "not integration")
        assert selected < total
