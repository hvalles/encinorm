# Phase 8: Release 0.3.0 - Pattern Map

**Mapped:** 2026-09-19
**Files analyzed:** 15 (8 modify, 3 new, plus CI/config/docs analog set)
**Analogs found:** 15 / 15 (all targets have a real in-repo analog or are direct self-edits)

## Scope Note

This is a **release / DevOps / docs** phase for a Spanish-language Python ORM
(`encino_orm`). It is **not** a frontend phase and introduces no new engines,
features or 1.0 declaration. Every pattern below is a *file-format / convention*
pattern (workflow YAML, TOML, Markdown, `warnings.warn`), not an application
architecture pattern. The planner must mirror the existing files exactly; do
**not** invent new CI structure or doc style.

Cross-cutting conventions observed and required everywhere:
- **Spanish** comments, docstrings, Markdown prose and changelog entries.
- `ruff` `line-length = 100` is the source of truth (`pyproject.toml:127`); no
  formatter config beyond that. Python edits must pass `ruff check` + `ruff format --check`.
- **uv is pinned** to `0.12.15` in every publish job (`ci.yml:93`, `release.yml:34`).
- Actions are pinned by **major tag** (`actions/checkout@v5`,
  `astral-sh/setup-uv@v5`, `actions/upload-artifact@v4`); SHA pinning is explicitly
  deferred.
- `pyproject.toml` uses the **hatchling** backend with
  `packages = ["encino_orm"]`; version is the single literal `version = "0.2.6"`.
  There is **no `__version__`** in `encino_orm/__init__.py` — the version literal
  lives only in `pyproject.toml` (verified: grep found no `__version__`).

## File Classification

| New/Modified File | Plan | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `.github/workflows/release.yml` | 08-01, 08-02, 08-03 | config (CI) | event-driven | self (existing) + `docs.yml` `environment:` | exact (self) |
| `.github/workflows/publish-testpypi.yml` | 08-02 | config (CI) | event-driven | self (existing) + `release.yml` | exact (self) |
| `.github/workflows/ci.yml` | 08-02 (read-only ref) | config (CI) | event-driven | self (existing) | exact (self) |
| `pyproject.toml` | 08-01, 08-03 | config (build) | batch/transform | self (existing) | exact (self) |
| `CHANGELOG.md` | 08-01, 08-03, 08-04 | docs | transform | self (existing) | exact (self) |
| `README.md` | 08-05 | docs | transform | self (existing) + `docs/getting-started.md` | exact (self) |
| `docs/MIGRATION-0.3.md` | 08-04 | docs | transform | `docs/trust-boundaries.md` | role-match (new file) |
| `.env.example` | 08-05 | config (env) | n/a | `docs/docker.md` §Variables + `docker-compose.yml` | role-match (new file) |
| `mkdocs.yml` | 08-04 | config (docs nav) | n/a | self (existing) | exact (self) |
| `encino_orm/base.py` | 08-01 | utility (warning emit) | event-driven | self (`_warn_last_id_deprecated`) | exact (self) |
| `encino_orm/context.py` | 08-01 | utility (warning emit) | event-driven | self (`set_default_db`/`get_default_db`) | exact (self) |
| `encino_orm/security/guard.py` | 08-01 | utility (warning emit) | event-driven | self (`_legacy_config`) | exact (self) |
| `encino_orm/pool.py` | 08-01 | utility (warning emit) | event-driven | self (`reset_on_release`) | exact (self) |
| `tests/test_*.py` (deprecation asserts) | 08-01 | test | request-response | existing `DeprecationWarning` tests | exact |
| `docs/docker.md`, `docs/credits.md`, `docs/design/*.md` | 08-05 (related) | docs | transform | self (remove `prompts/` links) | exact (self) |

## Pattern Assignments

### `.github/workflows/release.yml` (config, event-driven)

**Analog:** itself. Modify in place; mirror the existing structure.

**Header + permissions pattern** (lines 1-19) — the `id-token: write` is already
present; 08-02 keeps it and adds the `environment: pypi` block:
```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"
  workflow_dispatch:

permissions:
  contents: read
  id-token: write          # para trusted publishing (OIDC) si se usa
```

**CI gate via reusable workflow** (lines 13-23) — already satisfies CI-08 and
Success Criterion #2's `needs:` half; the `environment` is the *other* half:
```yaml
jobs:
  # CI-08: `needs:` no puede cruzar ficheros de workflow, asi que se llama a
  # `ci.yml` como workflow reutilizable. Con `./` el workflow llamado es el del
  # MISMO commit que el caller, que es la semantica correcta sobre un tag.
  ci:
    name: CI (reusable)
    uses: ./.github/workflows/ci.yml

  publish:
    needs: [ci]
    name: Build and publish
    runs-on: ubuntu-latest
```

**The OIDC replacement** (lines 37-49) — 08-02 replaces the token step with
`--trusted-publishing always` and **deletes** `UV_PUBLISH_TOKEN`:
```yaml
      - name: Build
        run: uv build

      # Publica a PyPI usando un token (secret PYPI_API_TOKEN).
      # Alternativa sin token: Trusted Publishing (OIDC):
      #   1. En PyPI > Settings > Publishing, añade el repo hvalles/encinorm
      #      con el workflow "release.yml".
      #   2. Sustituye este paso por: run: uv publish --trusted-publishing always
      #      y elimina el env con el token.
      - name: Publish to PyPI
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
        run: uv publish
```
Target shape (the inline comment already spells the destination):
```yaml
      - name: Publish to PyPI
        run: uv publish --trusted-publishing always
```

**Environment / protected-gate pattern** — there is exactly one `environment:`
analog in the repo, in `docs.yml:41-47`:
```yaml
  deploy:
    name: Deploy to GitHub Pages
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
```
The `pypi` environment uses only `name:` (no `url:` expected unless the user adds
one). GitHub environment protection (branch = `main`, required status checks,
approval) is configured in the GitHub UI/API, **not** in YAML — the YAML change
is only `environment: { name: pypi }` on the `publish` job. Do not invent
`required_reviewers:` YAML (not a workflow-file feature).

**Keep the pinned-uv step** (lines 29-35) unchanged:
```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          # Pin de uv en la ruta de publicacion (T-01-04): el entorno que
          # publica un artefacto debe usar una version conocida.
          version: "0.12.15"
          enable-cache: true
```

---

### `.github/workflows/publish-testpypi.yml` (config, event-driven)

**Analog:** itself + the same OIDC shape as `release.yml`.

**Current permissions** (lines 6-7) — lacks `id-token: write`; 08-02 adds it:
```yaml
permissions:
  contents: read
```

**Publish step to convert** (lines 33-41) — the comment already states the exact
target invocation:
```yaml
      # Alternativa sin token: Trusted Publishing (OIDC) sobre TestPyPI:
      #   1. En TestPyPI > Settings > Publishing, añade el repo hvalles/encinorm
      #      con el workflow "publish-testpypi.yml".
      #   2. Añade `id-token: write` a `permissions` y sustituye este paso por:
      #      run: uv publish --publish-url https://test.pypi.org/legacy/ --trusted-publishing always
      - name: Publish to TestPyPI
        env:
          UV_PUBLISH_TOKEN: ${{ secrets.TEST_PYPI_API_TOKEN }}
        run: uv publish --publish-url https://test.pypi.org/legacy/
```
Target shape:
```yaml
permissions:
  contents: read
  id-token: write

      - name: Publish to TestPyPI
        run: uv publish --publish-url https://test.pypi.org/legacy/ --trusted-publishing always
```
Keep the existing TestPyPI caveat comment (lines 28-31: "already exists" → bump
version before republishing) — it is accurate and useful.

---

### `.github/workflows/ci.yml` (config, event-driven — analog/reference for 08-02 gate)

**Analog:** itself. Do **not** restructure this file; 08-02 only needs the exact
**job names** to register as required status checks on the `pypi` environment.

**Reusable-workflow entry** (lines 1-12) — this is what makes `release.yml`'s
`uses:` work:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
  # CI-08: `release.yml` no puede usar `needs:` sobre un job de otro fichero, asi
  # que CI se expone como workflow reutilizable y `publish` lo llama.
  workflow_call:
```

**The job names that are candidates for required status checks** (the `name:`
keys the planner should enumerate, not the workflow-internal job ids):
- `test` → displays as `CI / Python 3.10` … `Python 3.13` (matrix) — `ci.yml:19-20`
- `lint` → `Lint y formato` — `ci.yml:160-161`
- `typecheck` → `Tipos (mypy)` — `ci.yml:184-185`
- `deps` → `Dependencias y vulnerabilidades` — `ci.yml:209-210`
- `benchmarks` → `Benchmarks (gate 2×)` — `ci.yml:252-253`
- `engine-heavy` → `Motores pesados (MSSQL + Oracle)` — `ci.yml:283-284`
- `coverage` → `Cobertura combinada (ratchet)` — `ci.yml:403-404`

Note the CI file's own comment at lines 286-289: `engine-heavy` "NUNCA es
advisory: un job que no puede fallar es CI verde sin verificacion (T-02-26)" —
so if the planner selects a subset of required checks, it must include
`engine-heavy`.

---

### `pyproject.toml` (config/build, batch)

**Analog:** itself. Single-line version bump only; do not touch backend, extras,
scripts or tool sections.

**Version literal** (lines 1-10):
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["encino_orm"]

[project]
name = "encino-orm"
version = "0.2.6"
```
08-01: `"0.2.7"`. 08-03: `"0.3.0rc1"` then `"0.3.0"`. Because the version is a
single literal with no `__version__` mirror, there is no second site to keep in
sync (confirmed: grep for `__version__` in `encino_orm/` returns nothing; grep
for `0.2.6` in `encino_orm/*.py` returns nothing).

**Constraints the planner must not disturb:**
- `requires-python = ">=3.10"` (line 12)
- `readme = "README.md"` (line 14) — README edits must keep a valid PyPI readme.
- `[project.scripts] encino_orm = "encino_orm.cli:main"` (line 39).

The `[tool.ruff] line-length = 100` block (lines 121-127) is the formatting
contract for all Python touched by 08-01.

---

### `CHANGELOG.md` (docs, transform)

**Analog:** itself. Format is **Keep a Changelog 1.1.0 (Spanish)** + SemVer,
declared at the top (lines 1-11):
```markdown
# Changelog

Todos los cambios notables del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Mientras esté
en `0.x`, **no hay garantía de estabilidad** (ver `README.md`).

## [Unreleased]

### Añadido
```
Section headings are Spanish: `### Añadido`, `### Cambiado`, `### Corregido`,
`### Seguridad` (a `### Removed`/`### Eliminado` may be needed by 08-04 — the
closest existing precedent is `### Seguridad` at line 352; use `### Eliminado`
or `### Removido` consistently and document the choice).

**Released-version heading pattern** (line 341) — the exact shape to create for
`[0.2.7]`, `[0.3.0rc1]`, `[0.3.0]`:
```markdown
## [0.2.6] - 2026-09-11
```

**Existing per-change entry pattern** — every entry names the requirement/plan
and states **old → new behavior**, which is exactly what REL-04 requires. See
the CFG-01 entry (lines 42-58) as the canonical "viejo: … nuevo: …" example:
```markdown
- **CAMBIO DE COMPORTAMIENTO (CFG-01: default de conexión inyectable).** El
  default de conexión de proceso deja de ser el global mutable `_default_db` y
  pasa a vivir en un `ConnectionRegistry` inyectable …
  … Viejo: un único default de proceso; nuevo:
  default inyectable por registry. La **retirada** de los globales (no solo su
  deprecación) es `REL-01` (Fase 8). Nota de ownership: esta entrada es ADITIVA y
  no prejuzga la enumeración de cambios incompatibles del milestone, que posee la
  Fase 8 (`08-04`).
```
The `[Unreleased]` section (lines 9-339) already holds the additive entries whose
`Nota de ownership` explicitly hands the milestone enumeration to `08-04` — 08-04
is the plan that promotes/rewrites them into the released `[0.3.0]` section with
old/new behavior, and 08-01 promotes a subset to `[0.2.7]`.

**Do not use `python-semantic-release`** (explicitly Out of Scope,
`REQUIREMENTS.md:129`) — entries are hand-written prose, not generated from commits.

---

### `README.md` (docs, transform — REL-05, 08-05)

**Analog:** itself + `docs/getting-started.md` for install/pinning wording.

**Current version + dead link** (lines 1-16) — the two things 08-05 fixes:
```markdown
# encino_orm · v0.2.6
...
> **Estado: experimental (v0.2.6).** ...
> depender de una API estable en producción. Documentación de usuario en `docs/`;
> estado de preparación en `prompts/analisys-07.md`.
```
The `prompts/` path is **gitignored** (`.gitignore:38`) and 404s on PyPI/CI
checkouts. `CONCERNS.md:31-34` prescribes the fix: *move the readiness/status
content into `docs/` (tracked) and remove the `prompts/` reference from
`README.md`*. That repo-side fix is the analog for what 08-05 must do here.

**Install block — the "not pinning" shape to correct** (lines 50-64) — uses
`pip install -e .`; there is **no `>=`/`~=` pin anywhere today**, so REL-05's
`~=0.2.6` guidance is net-new prose. Mirror the existing table style:
```markdown
## Instalación

```bash
# núcleo (SQLite + MySQL + MariaDB + PostgreSQL)
pip install -e .

# con extras opcionales
pip install -e ".[http,security,graphql]"
...

| Extra      | Incluye                                              |
|------------|------------------------------------------------------|
| `http`     | `fastapi` (REST CRUD)                                |
```
Add the pinning guidance next to this section, e.g. `pip install "encino-orm~=0.2.6"`
and explain `~=` vs `>=` in Spanish.

**Versioning section** (lines 148-153) already states the 0.x instability
contract; the dev-credentials warning must be added without contradicting it:
```markdown
## Versionado

El proyecto sigue [Versionado Semántico](https://semver.org). Mientras esté en
`0.x`, **no hay garantía de estabilidad**: cada versión *minor* puede introducir
cambios incompatibles. La estabilidad de la API se declarará a partir de `1.0.0`.
```

**Doc-links table** (lines 116-126) — the place to link `docs/MIGRATION-0.3.md`
and the tracked replacement for `prompts/`:
```markdown
| Documento | Contenido |
|-----------|-----------|
| [Getting started](docs/getting-started.md) | Instalación y primer modelo en 5 minutos. |
...
```

---

### `docs/MIGRATION-0.3.md` (docs, transform — NEW, 08-04)

**Analog:** `docs/trust-boundaries.md` — the most recently authored standalone
doc page (Phase 6), and the closest structural match: Spanish intro → rule/table
→ per-topic sections with safe-vs-unsafe **fenced code examples** → summary table.

**Structure to mirror** (trust-boundaries.md lines 1-13 and 104-115):
```markdown
# Fronteras de confianza (SQL)

Esta página documenta los tres puntos de `encino_orm` donde el llamador puede
introducir **texto SQL** en una sentencia. La regla transversal es una sola:

> **Los valores SIEMPRE viajan ligados como parámetros; nunca se interpola
> entrada no confiable en la plantilla SQL.**
...
## Resumen

| Escape | Qué valida | Regla del llamador |
|--------|------------|--------------------|
| `Filter.raw` | Solo reindexa `{n}`; reemite verbatim | No interpolar entrada no confiable; usar `params` |
```
For `MIGRATION-0.3.md` the "before/after" pairs replace the safe/unsafe pairs.
Scope (per `08-CONTEXT.md` "the agent's Discretion"): enumerate **all breaking
changes accumulated since 0.2.6 (Phases 2–7)**, not only the deprecated shims —
the source material is the `[Unreleased]` `### Cambiado`/`### Corregido` entries
marked `CAMBIO DE COMPORTAMIENTO` in `CHANGELOG.md` (lines 42-339).

**Register the page in the MkDocs nav** — `mkdocs.yml:67-71` "Desarrolladores"
section is the natural home:
```yaml
  - Desarrolladores:
      - Fronteras de confianza (SQL): trust-boundaries.md
      - Agregar un motor: engines.md
      - Docker: docker.md
      - Créditos: credits.md
```
`docs.yml:34` runs `uv run mkdocs build --strict`, so a page not in nav is
allowed but a broken nav entry fails the docs build — add the nav entry and the
file together.

---

### `.env.example` (config/env — NEW, 08-05)

**Analog:** there is **no** `.env` or `.env.example` in the repo today (glob
`.env*` → no files; `.env` is gitignored exactly at `.gitignore:33`, so
`.env.example` is *not* ignored). The authoritative value source is the
env-var table in `docs/docker.md:220-227` (mirrored in the CI test env at
`ci.yml:111-127`):
```markdown
| Motor | Variables de entorno | Valores por defecto (local) |
|-------|----------------------|------------------------------|
| MySQL | `ENCINO_ORM_MYSQL_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| MariaDB | `ENCINO_ORM_MARIADB_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `3306` / `root` / `admin` / `encino_orm_test` |
| PostgreSQL | `ENCINO_ORM_POSTGRES_HOST/PORT/USER/PASSWORD/DB` | `127.0.0.1` / `5432` / `postgres` / `admin` / `encino_orm_test` |
| SQL Server | `ENCINO_ORM_MSSQL_HOST/PORT/USER/PASSWORD/DB/DRIVER/TRUST_CERT` | `127.0.0.1` / `1433` / `sa` / `Admin_123` / `encino_orm_test` / `ODBC Driver 18 for SQL Server` / `true` |
| Oracle | `ENCINO_ORM_ORACLE_HOST/PORT/SERVICE/USER/PASSWORD` | `127.0.0.1` / `1521` / `XEPDB1` / `system` / `admin` |
| Redis | `ENCINO_ORM_REDIS_URL` | `redis://127.0.0.1:6379` |
```
`docker-compose.yml:1-40` provides the same dev-only credentials. The file must
carry an explicit **"credenciales SOLO para desarrollo local"** header — this is
the REL-05 warning, and the values are all throwaway (`admin`, `Admin_123`),
never production secrets. Do not include a real secret. The planner should also
note: `.gitignore:37-38` ignores `prompts/` and `.env` (exact basename), so
`.env.example` is committable without a `.gitignore` change.

---

### Runtime `DeprecationWarning` sites (08-01, REL-01)

**Analog:** the four existing centralized/point warnings already in source. The
canonical shape is `warnings.warn("<mensaje en español>", DeprecationWarning, stacklevel=2)`.

**Centralized-helper pattern** (`encino_orm/base.py:22-33`) — one emission point
chosen because `filterwarnings = ["error"]` in `pyproject.toml:62-72` turns any
warning into a test failure, so warning count must stay manageable:
```python
def _warn_last_id_deprecated():
    """Emite el `DeprecationWarning` CENTRALIZADO de `last_id()`.

    Un único punto de emisión evita seis sitios de warning en los adaptadores y
    mantiene `filterwarnings = ["error"]` manejable. `stacklevel=2` señala al
    llamador real (o al `PoolDb.last_id` que delega en este helper).
    """
    warnings.warn(
        "last_id() está deprecado; usa execute_insert(qry) o el retorno de Model.insert()",
        DeprecationWarning,
        stacklevel=2,
    )
```

**Global-shim pattern** (`encino_orm/context.py:83-106`) — warns **before**
delegating; message names the replacement:
```python
def set_default_db(db) -> None:
    """Registra la conexión o pool por defecto del proceso.

    Deprecado: usa un `ConnectionRegistry` explícito y su método `set_default()`.
    """
    warnings.warn(
        "set_default_db() está deprecado; usa un ConnectionRegistry explícito",
        DeprecationWarning,
        stacklevel=2,
    )
    _registry.set_default(db)
```

**Security-global fallback pattern** (`encino_orm/security/guard.py:50-64`) — note
the hard rule: the message names the **global names**, never their values:
```python
def _legacy_config() -> SecurityConfig:
    """Fallback a los globales: emite EXACTAMENTE un `DeprecationWarning`.

    El mensaje nombra los NOMBRES de los globales y su reemplazo, nunca sus
    valores (Pitfall 12). Se valida primero para seguir fallando cerrado sin
    avisar cuando no hay configuración.
    """
    secret, db_dep = _resolve(None, None)
    warnings.warn(
        "los globales SECRET/GET_DB están deprecados; usa SecurityConfig y "
        "security_dependencies(config)",
        DeprecationWarning,
        stacklevel=2,
    )
```

**Policy-warning pattern** (`encino_orm/pool.py:118-127`) — attached to the
*policy flag*, not to a runtime state, precisely to avoid firing on every call:
```python
        if reset_on_release == "commit":
            # El warning se engancha a la POLÍTICA, no a `in_transaction()`:
            # en MSSQL/Oracle un SELECT deja `_in_tx=True` y avisar por cada
            # lectura rompería `filterwarnings=["error"]` (Pitfall 4 / A1).
            warnings.warn(
                "reset_on_release='commit' está deprecado: la liberación con "
                "transacción abierta revierte por defecto (usa 'rollback')",
                DeprecationWarning,
                stacklevel=2,
            )
```

Map of the four breaks named by `ROADMAP.md:392` to their current code site
(the planner must *verify presence*, add only what is missing, and **not remove
globals** — removal is out of 0.2.7's scope per `08-CONTEXT.md` D-01):
| Break | Current warning site |
|-------|----------------------|
| implicit commit on release | `pool.py:118-127` (`reset_on_release='commit'`) |
| mutable `SECRET`/`GET_DB` | `security/guard.py:50-64` (`_legacy_config`) |
| post-hoc `last_id()` | `base.py:22-33` (`_warn_last_id_deprecated`) |
| unvalidated identifiers | **no runtime warning found** — fail-closed `ValueError` from `dialects/identifiers.py`; see `CHANGELOG.md:188-196`. Planner must decide/confirm the 0.2.7 deprecation wording for this break. |

## Shared Patterns

### Warning emission
**Source:** `encino_orm/base.py:22-33`
**Apply to:** every 0.2.7 deprecation site. One `warnings.warn(..., DeprecationWarning, stacklevel=2)` call, Spanish message, `stacklevel=2` so the warning points at the caller (critical because `pyproject.toml` sets `filterwarnings = ["error"]`).

### Workflow step shape
**Source:** `ci.yml:83-95`, `release.yml:25-38`
**Apply to:** both publish workflows. Every job starts `Checkout` (`actions/checkout@v5`) → `Install uv` (`astral-sh/setup-uv@v5`, `version: "0.12.15"`, `enable-cache: true`) → domain steps. Keep `uv build` before any `uv publish`.

### GitHub `environment:` (protected gate)
**Source:** `docs.yml:45-47` (the only in-repo `environment:` usage)
**Apply to:** `release.yml` `publish` job for the `pypi` environment. Protection rules (branch, required reviewers/checks) are GitHub settings, not YAML; the fallback per D-02 (wait timer + required checks + `workflow_dispatch`) is also a settings change.

### Spanish documentation voice
**Source:** `docs/trust-boundaries.md:1-13`, `CHANGELOG.md:3-7`, `README.md`
**Apply to:** `docs/MIGRATION-0.3.md`, `.env.example` comments, `CHANGELOG.md` entries, `README.md` additions. Triple-quoted docstrings use Spanish prose with a one-line summary and no `Args:`/`Returns:` sections.

### dev-only credentials
**Source:** `docs/docker.md:215-227`, `docker-compose.yml:1-40`, `ci.yml:111-127`
**Apply to:** `.env.example` and the README dev-credentials header. All values are local test credentials; the header must say so explicitly.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `docs/MIGRATION-0.3.md` | docs | transform | No migration-guide page exists; pattern borrowed from `docs/trust-boundaries.md` structure. |
| `.env.example` | config | n/a | No `.env*` files are tracked; values sourced from `docs/docker.md` + `docker-compose.yml`. |

## Metadata

**Analog search scope:** `.github/workflows/`, repo root config (`pyproject.toml`,
`CHANGELOG.md`, `README.md`, `.gitignore`, `mkdocs.yml`, `docker-compose.yml`),
`docs/`, `encino_orm/` warning sites, `tools/ci/`.
**Files scanned:** ~20 (all targets read in full; source warning sites read
targeted).
**Pattern extraction date:** 2026-09-19
