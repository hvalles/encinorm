"""Guardas de fuente del contrato de publicacion de 0.3.0 (REL-03).

Estos tests NO tocan red ni motores: leen los workflows de `.github/workflows/`
como texto y como YAML y congelan el contrato de la migracion a OIDC trusted
publishing. Si alguien reintroduce un token de publicacion, quita
`id-token: write`, saca el job `publish` del entorno `pypi` o rompe el gate
`needs: [ci]`, la suite falla antes de que el error llegue a un release real.

El entorno `pypi` registra los jobs de `ci.yml` como required status checks:
por eso se afirma que los nombres de job siguen presentes. Si un job pierde su
`name:`, el gate deja de ser real sin que el YAML deje de ser valido.
"""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _text(name: str) -> str:
    """Devuelve el workflow como texto crudo (assertions de fuente literales)."""
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _yaml(name: str) -> dict:
    """Devuelve el workflow parseado (assertions sobre la estructura real)."""
    return yaml.safe_load(_text(name))


class TestReleaseWorkflow:
    def test_release_uses_oidc_trusted_publishing(self):
        text = _text("release.yml")
        assert "id-token: write" in text
        assert "uv publish --trusted-publishing always" in text

    def test_release_has_no_long_lived_publish_tokens(self):
        text = _text("release.yml")
        assert "PYPI_API_TOKEN" not in text
        assert "UV_PUBLISH_TOKEN" not in text

    def test_release_publish_job_runs_in_pypi_environment(self):
        data = _yaml("release.yml")
        assert data["jobs"]["publish"]["environment"]["name"] == "pypi"

    def test_release_publish_job_needs_ci(self):
        data = _yaml("release.yml")
        assert data["jobs"]["publish"]["needs"] == ["ci"]

    def test_release_reuses_ci_workflow_from_the_same_commit(self):
        data = _yaml("release.yml")
        assert data["jobs"]["ci"]["uses"] == "./.github/workflows/ci.yml"


class TestTestPypiWorkflow:
    def test_testpypi_uses_oidc_trusted_publishing(self):
        text = _text("publish-testpypi.yml")
        assert "id-token: write" in text
        assert "uv publish --publish-url https://test.pypi.org/legacy/" in text
        assert "--trusted-publishing always" in text

    def test_testpypi_has_no_long_lived_publish_tokens(self):
        text = _text("publish-testpypi.yml")
        assert "TEST_PYPI_API_TOKEN" not in text
        assert "UV_PUBLISH_TOKEN" not in text


class TestReusableCiWorkflow:
    def test_ci_exposes_workflow_call(self):
        data = _yaml("ci.yml")
        # PyYAML interpreta la clave YAML `on` como el booleano True.
        triggers = data.get("on") or data.get(True)
        assert "workflow_call" in triggers

    def test_ci_job_names_cover_the_required_checks(self):
        # El entorno `pypi` exige estos jobs como required status checks.
        # Incluir SIEMPRE `Motores pesados (MSSQL + Oracle)`: un job que no
        # puede fallar es CI verde sin verificacion.
        data = _yaml("ci.yml")
        names = {job.get("name") for job in data["jobs"].values()}
        assert "Motores pesados (MSSQL + Oracle)" in names
        assert "Lint y formato" in names
        assert "Tipos (mypy)" in names
        assert "Cobertura combinada (ratchet)" in names
