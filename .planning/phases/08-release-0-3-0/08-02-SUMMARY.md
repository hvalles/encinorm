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
  - "Task 3 (configuracion de dashboard PyPI/GitHub + validacion OIDC en TestPyPI) es un checkpoint humano por D-04: la sesion no maneja credenciales ni la UI. El plan NO queda cerrado hasta que se resuelva."
  - "Se conserva el gate CI-08 existente (`uses: ./.github/workflows/ci.yml` + `publish: needs: [ci]`); el entorno `pypi` se monta SOBRE el, sin duplicarlo."
  - "El bloque comentado de TestPyPI en release.yml se reescribio como nota OIDC sin `UV_PUBLISH_TOKEN`, de modo que no queda ninguna aparicion de los secretos en los workflows."
  - "Las guardas enumeran los nombres de job de ci.yml (incluido `Motores pesados (MSSQL + Oracle)`) porque un job que pierde su `name:` deja el gate del entorno sin verificar nada."

patterns-established:
  - "Contrato de release congelado por test DB-free (texto + YAML), de modo que una regresion de CI no puede colarse silenciosamente"
  - "`assert` de fuente tolerante a CRLF/LF: se afirma el substring del comando, no el fichero byte a byte"

requirements-completed: []  # REL-03 PENDIENTE: requiere resolver Task 3 (checkpoint humano). NO marcar completo aqui.

# Metrics
duration: 2min
completed: 2026-09-20
---

# Phase 8 Plan 2: OIDC trusted publishing y entorno `pypi` (REL-03) — PARCIAL (checkpoint pendiente)

**Ambos workflows de publicacion migrados a OIDC trusted publishing sin tokens de larga vida y congelados por un test de fuente; el job `publish` de `release.yml` corre en el entorno `pypi`. Falta la Task 3 (checkpoint humano): proteger el entorno, eliminar `PYPI_API_TOKEN` y validar OIDC en TestPyPI.**

## Status: CHECKPOINT PENDIENTE (no es un plan cerrado)

Este SUMMARY documenta las tareas autonomas 1-2. **La Task 3 es `checkpoint:human-action`
(bloqueante) y NO se ha resuelto**, por lo que REL-03 no esta completo y el contador de
plan no se avanza.

## Performance

- **Duration:** ~2 min (edicion de workflows + test + suite completa)
- **Started:** 2026-09-20T03:28:21Z
- **Completed (tareas autonomas):** 2026-09-20T03:29:52Z
- **Tasks:** 2 de 3 (Task 3 = checkpoint humano, pendiente)
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

## Task Commits

1. **Task 1: Convertir los dos workflows de publicacion a OIDC** - `0ebe4f5` (ci)
2. **Task 2: Congelar la configuracion de publicacion con un test de fuente** - `83ef856` (test)
3. **Task 3: Proteger el entorno pypi, eliminar el token y validar OIDC en TestPyPI** - PENDIENTE (checkpoint humano)

## Files Created/Modified

- `.github/workflows/release.yml` - OIDC + `environment: { name: pypi }`; eliminados el paso con token y el bloque comentado de TestPyPI (reescrito como nota OIDC).
- `.github/workflows/publish-testpypi.yml` - `id-token: write` + publicacion OIDC; eliminado `TEST_PYPI_API_TOKEN`.
- `tests/test_release_config.py` (creado, 84 lineas) - Guardas de fuente del contrato REL-03.

## Verification

| Comando | Resultado |
|---------|-----------|
| `uv run pytest tests/test_release_config.py -q` | 9 passed |
| `uv run ruff check tests/test_release_config.py` | All checks passed (exit 0) |
| `uv run ruff format --check tests/test_release_config.py` | 1 file already formatted (exit 0) |
| `grep -R "PYPI_API_TOKEN\|UV_PUBLISH_TOKEN\|TEST_PYPI_API_TOKEN" .github/workflows/` | sin coincidencias |
| `uv run pytest -q -m "not optional_engine and not benchmark"` | 1080 passed, 38 deselected |
| `yaml.safe_load` de ambos workflows | valido |

## Deviations from Plan

None - plan ejecutado tal como se escribio en las tareas autonomas.

## Issues Encountered

None.

## User Setup Required

**Task 3 es un checkpoint humano bloqueante (D-04).** Requiere, en orden:

1. **PyPI > Settings > Publishing** — registrar el trusted publisher: repo `hvalles/encinorm`, workflow `release.yml`, environment `pypi`.
2. **TestPyPI > Settings > Publishing** — registrar el trusted publisher del workflow `publish-testpypi.yml`.
3. **GitHub > repo > Settings > Environments** — crear el entorno `pypi` con deployment branch `main`, required status checks = los jobs de `ci.yml` (incluido `Motores pesados (MSSQL + Oracle)`) y aprobacion de revisores. FALLBACK (D-02) si el plan de GitHub no soporta required reviewers: wait timer + required checks + disparo manual por `workflow_dispatch`; documentarlo.
4. **GitHub > Settings > Secrets and variables > Actions** — eliminar `PYPI_API_TOKEN` (objetivo de REL-03); `TEST_PYPI_API_TOKEN` tras validar OIDC.
5. **Validar OIDC en TestPyPI** — `gh workflow run "Publish to TestPyPI"` y confirmar publicacion SIN token. Si TestPyPI responde "already exists", no reintentar: la validacion se completa con `0.3.0rc1` en 08-03.
6. Confirmar que un intento de publicacion con CI rojo queda bloqueado por el entorno.

## Next Phase Readiness

- **Pendiente:** resolver el checkpoint de Task 3 para cerrar REL-03. Hasta entonces el plan no
  se marca completo y el contador no avanza.
- Tras resolverlo, `08-03` puede cortar `0.3.0rc1` y validar el camino OIDC end-to-end.

## Self-Check

- FOUND: `.github/workflows/release.yml` (contiene `trusted-publishing always`, `environment: name: pypi`)
- FOUND: `.github/workflows/publish-testpypi.yml` (contiene `id-token: write`, `--trusted-publishing always`)
- FOUND: `tests/test_release_config.py`
- FOUND: commit `0ebe4f5`
- FOUND: commit `83ef856`
- PENDIENTE: Task 3 (checkpoint humano) — entorno `pypi`, token eliminado, OIDC verificado en TestPyPI

## Self-Check: PENDING CHECKPOINT

Task 3 (human-action) sin resolver: el plan NO esta cerrado.

---

*Phase: 08-release-0-3-0*
*Completed (parcial): 2026-09-20*
