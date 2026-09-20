---
phase: 08-release-0-3-0
plan: 02
subsystem: infra
tags: [oidc, trusted-publishing, pypi, testpypi, github-environments, release, ci, supply-chain]

# Dependency graph
requires:
  - phase: "08-01"
    provides: "0.2.7 publicada con el mecanismo vigente (token/dispatch); el gate CI-08 (`uses: ./.github/workflows/ci.yml` + `publish: needs: [ci]`) ya presente en release.yml"
  - phase: "01"
    provides: "ci.yml expuesto como workflow reutilizable (`on.workflow_call`) con los jobs que el entorno `pypi` exige como required status checks"
provides:
  - "release.yml: job `publish` dentro del entorno `pypi` y publicacion por OIDC (`uv publish --trusted-publishing always`), sin token"
  - "publish-testpypi.yml: `id-token: write` y publicacion por OIDC contra TestPyPI"
  - "tests/test_release_config.py: guardas de fuente que congelan OIDC activo, cero tokens, entorno `pypi` y el gate `needs: [ci]`"
  - "entorno `pypi` protegido (branch `main` + tag `v*` + required reviewer) y `PYPI_API_TOKEN`/`TEST_PYPI_API_TOKEN` eliminados de Actions"
affects: [08-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OIDC trusted publishing: `id-token: write` + `uv publish --trusted-publishing always`; ningun token de larga vida en el repo"
    - "Entorno GitHub como gate de publicacion: `environment: { name: pypi }` en el job `publish`; branch/checks/reviewers son ajustes de GitHub, no YAML"
    - "Guardas de fuente sobre workflows: assertions literales + `yaml.safe_load` para congelar contrato de release sin red ni motores"

key-files:
  created:
    - tests/test_release_config.py
  modified:
    - .github/workflows/release.yml
    - .github/workflows/publish-testpypi.yml

key-decisions:
  - "Task 3 (configuracion de dashboard PyPI/GitHub + validacion OIDC en TestPyPI) se resolvio por la persona duena (D-04) y el orquestador lo verifico por la API de GitHub: el entorno `pypi` existe, con deployment branch policy custom (`branch: main` + `tag: v*`) y required reviewer `hvalles`; `gh secret list` sale vacio."
  - "La regla `tag: v*` esta presente, de modo que la publicacion disparada por tag NO queda bloqueada por la politica de rama (el riesgo de que el gate impidiera el release se descarto)."
  - "Se conserva el gate CI-08 existente (`uses: ./.github/workflows/ci.yml` + `publish: needs: [ci]`); el entorno `pypi` se monta SOBRE el, sin duplicarlo."
  - "El bloque comentado de TestPyPI en release.yml se reescribio como nota OIDC sin `UV_PUBLISH_TOKEN`, de modo que no queda ninguna aparicion de los secretos en los workflows."
  - "Las guardas enumeran los nombres de job de ci.yml (incluido `Motores pesados (MSSQL + Oracle)`) porque un job que pierde su `name:` deja el gate del entorno sin verificar nada."
  - "La validacion end-to-end de OIDC en TestPyPI se DIFIERE a 08-03 con `0.3.0rc1` (el plan lo permite): relanzar el workflow sobre `main` publicaria un 0.2.7 mal etiquetado o fallaria con 'already exists'."

patterns-established:
  - "Contrato de release congelado por test DB-free (texto + YAML), de modo que una regresion de CI no puede colarse silenciosamente"
  - "`assert` de fuente tolerante a CRLF/LF: se afirma el substring del comando, no el fichero byte a byte"

requirements-completed: [REL-03]

# Metrics
duration: "2min (autonomo) + config. dashboard"
completed: 2026-09-20
---

# Phase 8 Plan 2: OIDC trusted publishing y entorno `pypi` (REL-03)

**Ambos workflows de publicacion migrados a OIDC trusted publishing sin tokens de larga vida y congelados por un test de fuente; el job `publish` de `release.yml` corre en el entorno `pypi` protegido (branch `main` + tag `v*` + required reviewer) y `PYPI_API_TOKEN`/`TEST_PYPI_API_TOKEN` ya no existen. REL-03 satisfecho.**

## Performance

- **Duration:** ~2 min de trabajo autonomo (edicion de workflows + test + suite completa) + la configuracion de dashboard realizada por la persona duena.
- **Started:** 2026-09-20T03:28:21Z
- **Completed (plan completo):** 2026-09-20T05:10:45Z (resuelto el checkpoint humano de Task 3)
- **Tasks:** 3 de 3
- **Files modified:** 3 (1 creado, 2 modificados)

## Accomplishments

- `release.yml` publica por **OIDC** (`uv publish --trusted-publishing always`) sin `env`
  de token, dentro del entorno **`pypi`** (`environment: { name: pypi }`), conservando el
  gate existente `uses: ./.github/workflows/ci.yml` + `publish: needs: [ci]` y el pin de uv
  `0.12.15`.
- `publish-testpypi.yml` declara `id-token: write` y publica por
  `uv publish --publish-url https://test.pypi.org/legacy/ --trusted-publishing always`; se
  conserva la nota sobre "already exists".
- **Cero tokens de publicacion** en `.github/workflows/` (ni `PYPI_API_TOKEN`, ni
  `TEST_PYPI_API_TOKEN`, ni `UV_PUBLISH_TOKEN`).
- `tests/test_release_config.py` congela el contrato (9 tests verdes) y falla si se
  reintroduce un token, se quita `id-token: write`, se saca `publish` del entorno `pypi` o
  se rompe `needs: [ci]`.
- Suite completa verde: `uv run pytest -q -m "not optional_engine and not benchmark"` →
  **1080 passed, 38 deselected**.
- **Task 3 resuelta (configuracion de dashboard + verificacion por API):** el entorno `pypi`
  esta protegido y los secretos de token se eliminaron de Actions (evidencia en la tabla de
  verificacion). Los trusted publishers de PyPI y TestPyPI quedaron registrados por la persona
  duena mediante el dashboard (no verificable por API).

## Task Commits

1. **Task 1: Convertir los dos workflows de publicacion a OIDC** - `0ebe4f5` (ci)
2. **Task 2: Congelar la configuracion de publicacion con un test de fuente** - `83ef856` (test)
3. **Task 3: Proteger el entorno pypi, eliminar el token y validar OIDC en TestPyPI** - sin commit de codigo: es un `checkpoint:human-action` resuelto en el dashboard de GitHub/PyPI y verificado por el orquestador via API (configuracion externa, no produce cambios de fichero)

## Files Created/Modified

- `.github/workflows/release.yml` - OIDC + `environment: { name: pypi }`; eliminados el paso con token y el bloque comentado de TestPyPI (reescrito como nota OIDC).
- `.github/workflows/publish-testpypi.yml` - `id-token: write` + publicacion OIDC; eliminado `TEST_PYPI_API_TOKEN`.
- `tests/test_release_config.py` (creado, 84 lineas) - Guardas de fuente del contrato REL-03.

## Verification

| Comando / Evidencia | Resultado |
|---------|-----------|
| `uv run pytest tests/test_release_config.py -q` | 9 passed |
| `uv run ruff check tests/test_release_config.py` | All checks passed (exit 0) |
| `uv run ruff format --check tests/test_release_config.py` | 1 file already formatted (exit 0) |
| `grep -R "PYPI_API_TOKEN\|UV_PUBLISH_TOKEN\|TEST_PYPI_API_TOKEN" .github/workflows/` | sin coincidencias (grep exit 1) |
| `uv run pytest -q -m "not optional_engine and not benchmark"` | 1080 passed, 38 deselected |
| `yaml.safe_load` de ambos workflows | valido |
| GitHub API — entorno `pypi` | Existe; `deployment_branch_policy` custom con reglas exactas `branch: main` **y** `tag: v*`; protection rule `required_reviewers` → `hvalles` |
| `gh secret list -R hvalles/encinorm` | **Vacio** → `PYPI_API_TOKEN` y `TEST_PYPI_API_TOKEN` eliminados de Actions |
| Trusted publishers PyPI/TestPyPI | Registrados por la persona duena en el dashboard (no verificable por API) |
| `origin/main` | `35d2ede` (pushed) |
| Validacion OIDC end-to-end en TestPyPI | **DIFERIDA a 08-03** con `0.3.0rc1` (permitido por el plan) |

## Deviations from Plan

None - plan ejecutado tal como se escribio. La Task 3 se resolvio por la via prevista
(checkpoint humano, D-04) sin trabajo fuera de plan.

## Issues Encountered

- **Required status checks del entorno no verificados por API.** La API de GitHub confirmo la
  deployment branch policy (`branch: main` + `tag: v*`) y el required reviewer, pero no se
  inspecciono la lista exacta de required status checks del entorno. El gate de CI verde se
  mantiene de todos modos **en-workflow** via `publish: needs: [ci]` (Task 1), que es la via
  unica de publicacion; los required status checks del entorno son una segunda linea de defensa.
- **Validacion OIDC end-to-end diferida.** Publicar ahora desde `main` produciria un 0.2.7 mal
  etiquetado o un fallo "already exists"; el plan autoriza explicitamente completar la validacion
  de OIDC en TestPyPI con `0.3.0rc1` en 08-03. No es un fallo de REL-03: el mecanismo OIDC ya esta
  activo y congelado por test.

## User Setup Required

None - la configuracion externa requerida por Task 3 (entorno `pypi`, eliminacion de secretos,
trusted publishers) quedo completada y verificada.

## Next Phase Readiness

- REL-03 satisfecho: OIDC activo en ambos workflows, `PYPI_API_TOKEN` eliminado y entorno `pypi`
  protegido como via unica de publicacion.
- `08-03` puede cortar `0.3.0rc1` y validar el camino OIDC end-to-end contra TestPyPI (incluida la
  validacion diferida) antes de promover a `0.3.0`.

## Self-Check

- FOUND: `.github/workflows/release.yml` (contiene `trusted-publishing always`, `environment: name: pypi`)
- FOUND: `.github/workflows/publish-testpypi.yml` (contiene `id-token: write`, `--trusted-publishing always`)
- FOUND: `tests/test_release_config.py` (9 tests verdes)
- FOUND: commit `0ebe4f5`
- FOUND: commit `83ef856`
- FOUND: entorno `pypi` protegido + secretos de token ausentes (evidencia API del orquestador)

## Self-Check: PASSED

3/3 tareas completas. REL-03 satisfecho.

---

*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*
