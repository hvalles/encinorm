"""Pruebas unitarias del arnes de CI: interruptor de motores y gate de skips.

Cubre CI-01 (interruptor de motores requeridos) y CI-02 (gate JUnit-XML) sin
tocar ningun motor real: los documentos XML son fixtures escritos en `tmp_path`.
Los helpers se importan como `tests.conftest` porque `tests/__init__.py` existe
y pytest importa los modulos con el nombre cualificado del paquete.

Los nombres de metodo incluyen `check_skips` / `require_engines` a proposito:
`-k check_skips` y `-k require_engines` deben SELECCIONAR estos tests, no
deseleccionarlos en silencio (la investigacion de la fase los cita por nombre).
"""

import json

import pytest

from tests.conftest import engine_unavailable, required_engines
from tools.ci.check_coverage_floors import FLOORS
from tools.ci.check_coverage_floors import main as coverage_floors_main
from tools.ci.check_skips import main, total_skipped

CLEAN_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="3" time="0.100">
    <testcase classname="tests.test_x" name="test_a" time="0.010" />
  </testsuite>
</testsuites>
"""

SKIPS_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="0" skipped="2" tests="5" time="1.000">
    <testcase classname="tests.test_a" name="test_1" time="0.100" />
  </testsuite>
  <testsuite name="pytest" errors="0" failures="0" skipped="1" tests="3" time="0.500">
    <testcase classname="tests.test_b" name="test_2" time="0.100" />
  </testsuite>
</testsuites>
"""

FAILURES_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="0" failures="2" skipped="0" tests="2" time="0.200">
    <testcase classname="tests.test_c" name="test_3" time="0.100">
      <failure message="boom">traceback</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestCheckSkips:
    def test_check_skips_total_clean_xml_is_zero(self, tmp_path):
        assert total_skipped(_write(tmp_path, "clean.xml", CLEAN_XML)) == 0

    def test_check_skips_total_sums_across_testsuites(self, tmp_path):
        assert total_skipped(_write(tmp_path, "skips.xml", SKIPS_XML)) == 3

    def test_check_skips_total_ignores_failures(self, tmp_path):
        assert total_skipped(_write(tmp_path, "failures.xml", FAILURES_XML)) == 0

    def test_check_skips_main_clean_xml_returns_zero(self, tmp_path, capsys):
        code = main(["check_skips.py", _write(tmp_path, "clean.xml", CLEAN_XML)])
        assert code == 0
        assert capsys.readouterr().out.strip()

    def test_check_skips_main_skipped_xml_returns_one(self, tmp_path, capsys):
        code = main(["check_skips.py", _write(tmp_path, "skips.xml", SKIPS_XML)])
        assert code == 1
        assert "3" in capsys.readouterr().err

    def test_check_skips_main_missing_file_returns_one(self, tmp_path, capsys):
        code = main(["check_skips.py", str(tmp_path / "no-existe.xml")])
        assert code == 1
        assert capsys.readouterr().err.strip()


class TestRequireEngines:
    def test_require_engines_unset_is_empty(self, monkeypatch):
        monkeypatch.delenv("ENCINO_ORM_REQUIRE_ENGINES", raising=False)
        assert required_engines() == set()

    def test_require_engines_empty_is_empty(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "")
        assert required_engines() == set()

    def test_require_engines_comma_separated_is_parsed(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "mysql,postgresql")
        assert required_engines() == {"mysql", "postgresql"}

    def test_require_engines_values_are_stripped_and_lowercased(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", " MySQL , PostgreSQL ")
        assert required_engines() == {"mysql", "postgresql"}


class TestEngineUnavailable:
    def test_engine_unavailable_required_engine_fails(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "postgresql")
        with pytest.raises(pytest.fail.Exception):
            engine_unavailable("postgresql", RuntimeError("sin conexion"))

    def test_engine_unavailable_optional_engine_skips(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "mysql,postgresql")
        with pytest.raises(pytest.skip.Exception):
            engine_unavailable("mariadb", RuntimeError("sin conexion"))

    def test_engine_unavailable_unset_skips_any_engine(self, monkeypatch):
        monkeypatch.delenv("ENCINO_ORM_REQUIRE_ENGINES", raising=False)
        with pytest.raises(pytest.skip.Exception):
            engine_unavailable("postgresql", RuntimeError("sin conexion"))


def _coverage_json(tmp_path, files: dict) -> str:
    """Escribe un `coverage.json` minimo con el esquema real de coverage.py."""
    data = {
        "meta": {"format": 3},
        "files": {
            name: {"summary": {"percent_covered": pct, "num_statements": 10}}
            for name, pct in files.items()
        },
        "totals": {"percent_covered": 100.0},
    }
    path = tmp_path / "coverage.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _all_above(floor_offset: float = 0.0) -> dict:
    return {module: floor + floor_offset for module, floor in FLOORS.items()}


class TestCheckCoverageFloors:
    """Gate de pisos por modulo sobre `coverage json` (D-04/D-06 de Fase 1)."""

    def test_check_coverage_floors_map_has_required_modules(self):
        assert FLOORS["encino_orm/dialects/identifiers.py"] == 100.0
        assert FLOORS["encino_orm/dialects/builders.py"] == 95.0
        assert FLOORS["encino_orm/query.py"] == 95.0

    def test_check_coverage_floors_all_above_returns_zero(self, tmp_path, capsys):
        code = coverage_floors_main(
            ["check_coverage_floors.py", _coverage_json(tmp_path, _all_above())]
        )
        assert code == 0
        assert capsys.readouterr().out.strip()

    def test_check_coverage_floors_below_floor_returns_one(self, tmp_path, capsys):
        files = _all_above()
        files["encino_orm/query.py"] = FLOORS["encino_orm/query.py"] - 1.0
        code = coverage_floors_main(["check_coverage_floors.py", _coverage_json(tmp_path, files)])
        assert code == 1
        err = capsys.readouterr().err
        assert "FALLO:" in err
        assert "encino_orm/query.py" in err
        assert str(FLOORS["encino_orm/query.py"]) in err

    def test_check_coverage_floors_missing_module_returns_one(self, tmp_path, capsys):
        files = _all_above()
        del files["encino_orm/dialects/builders.py"]
        code = coverage_floors_main(["check_coverage_floors.py", _coverage_json(tmp_path, files)])
        assert code == 1
        err = capsys.readouterr().err
        assert "FALLO:" in err
        assert "encino_orm/dialects/builders.py" in err

    def test_check_coverage_floors_missing_file_returns_one(self, tmp_path, capsys):
        code = coverage_floors_main(["check_coverage_floors.py", str(tmp_path / "no-existe.json")])
        assert code == 1
        assert "FALLO:" in capsys.readouterr().err

    def test_check_coverage_floors_invalid_json_returns_one(self, tmp_path, capsys):
        path = tmp_path / "coverage.json"
        path.write_text("{no es json", encoding="utf-8")
        code = coverage_floors_main(["check_coverage_floors.py", str(path)])
        assert code == 1
        assert "FALLO:" in capsys.readouterr().err

    def test_check_coverage_floors_windows_paths_are_normalized(self, tmp_path, capsys):
        files = {module.replace("/", "\\"): pct for module, pct in _all_above().items()}
        code = coverage_floors_main(["check_coverage_floors.py", _coverage_json(tmp_path, files)])
        assert code == 0
