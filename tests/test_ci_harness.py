"""Pruebas unitarias del arnes de CI: interruptor de motores y gate de skips.

Cubre CI-01 (interruptor de motores requeridos) y CI-02 (gate JUnit-XML) sin
tocar ningun motor real: los documentos XML son fixtures escritos en `tmp_path`.
Los helpers se importan como `tests.conftest` porque `tests/__init__.py` existe
y pytest importa los modulos con el nombre cualificado del paquete.
"""

import pytest

from tests.conftest import engine_unavailable, required_engines
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


class TestTotalSkipped:
    def test_clean_xml_returns_zero(self, tmp_path):
        assert total_skipped(_write(tmp_path, "clean.xml", CLEAN_XML)) == 0

    def test_sums_skipped_across_all_testsuites(self, tmp_path):
        assert total_skipped(_write(tmp_path, "skips.xml", SKIPS_XML)) == 3

    def test_failures_are_not_counted_as_skips(self, tmp_path):
        assert total_skipped(_write(tmp_path, "failures.xml", FAILURES_XML)) == 0


class TestCheckSkipsMain:
    def test_clean_xml_returns_zero(self, tmp_path, capsys):
        code = main(["check_skips.py", _write(tmp_path, "clean.xml", CLEAN_XML)])
        assert code == 0
        assert capsys.readouterr().out.strip()

    def test_skipped_xml_returns_one_with_count(self, tmp_path, capsys):
        code = main(["check_skips.py", _write(tmp_path, "skips.xml", SKIPS_XML)])
        assert code == 1
        assert "3" in capsys.readouterr().err

    def test_missing_file_returns_one_without_traceback(self, tmp_path, capsys):
        code = main(["check_skips.py", str(tmp_path / "no-existe.xml")])
        assert code == 1
        assert capsys.readouterr().err.strip()


class TestRequiredEngines:
    def test_unset_is_empty(self, monkeypatch):
        monkeypatch.delenv("ENCINO_ORM_REQUIRE_ENGINES", raising=False)
        assert required_engines() == set()

    def test_empty_is_empty(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "")
        assert required_engines() == set()

    def test_comma_separated_is_parsed(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "mysql,postgresql")
        assert required_engines() == {"mysql", "postgresql"}

    def test_values_are_stripped_and_lowercased(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", " MySQL , PostgreSQL ")
        assert required_engines() == {"mysql", "postgresql"}


class TestEngineUnavailable:
    def test_required_engine_fails(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "postgresql")
        with pytest.raises(pytest.fail.Exception):
            engine_unavailable("postgresql", RuntimeError("sin conexion"))

    def test_optional_engine_skips(self, monkeypatch):
        monkeypatch.setenv("ENCINO_ORM_REQUIRE_ENGINES", "mysql,postgresql")
        with pytest.raises(pytest.skip.Exception):
            engine_unavailable("mariadb", RuntimeError("sin conexion"))

    def test_unset_skips_any_engine(self, monkeypatch):
        monkeypatch.delenv("ENCINO_ORM_REQUIRE_ENGINES", raising=False)
        with pytest.raises(pytest.skip.Exception):
            engine_unavailable("postgresql", RuntimeError("sin conexion"))
