---
phase: 08-release-0-3-0
plan: 03
subsystem: infra
tags: [release, pypi, testpypi, oidc, changelog, versioning, semver, release-candidate]

# Dependency graph
requires:
  - phase: "08-02"
    provides: "OIDC trusted publishing + entorno `pypi` protegido (REL-03); gates de `release.yml` congelados por tests/test_release_config.py"
  - phase: "08-04"
    provides: "CHANGELOG.md con la enumeración de rupturas y guard file-wide en tests/test_release_docs.py"
  - phase: "08-06"
    provides: "retiradas reales de 0.3.0 (set_default_db/get_default_db, globales SECRET/GET_DB)"
  - phase: "08-08"
    provides: "retirada de la API pública post-hoc last_id()"
provides:
  - "0.3.0rc1 publicada en TestPyPI y PyPI por OIDC (run 35491961779 SUCCESS; tag anotado v0.3.0rc1 → 3fec2da)"
  - "0.3.0 promovida en código: pyproject.toml + uv.lock a `0.3.0` y CHANGELOG a `## [0.3.0]` (commit 9eb3ea8)"
  - "0.3.0 publicada en PyPI por OIDC (run 35492821208 SUCCESS; tag anotado v0.3.0 → 9eb3ea8); PyPI JSON API reporta info.version = 0.3.0"
  - "cadena de publicación completa y ordenada en PyPI: 0.2.7 → 0.3.0rc1 → 0.3.0 (REL-02 satisfecho)"
affects: [08-release-0-3-0 (fase completa), milestone v0.3.0]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Promoción de versión pura: pyproject.toml + uv lock + heading de CHANGELOG, sin cambios de código entre rc y final"
    - "Detección temprana de build rojo: suite completa (mismo filtro que ci.yml) corrida ANTES del tag, porque `publish: needs: [ci]` + entorno `pypi` bloquean publicar con CI rojo"
    - "Trazabilidad rc→final: el tag anotado `v0.3.0rc1` sirve de punto de anclaje para demostrar `git diff -- encino_orm` vacío"
    - "Publicación OIDC sin token: tag anotado → workflow `Publish to PyPI` → CI reutilizable verde → aprobación del entorno `pypi`"

key-files:
  modified:
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "Task 1 (corte de 0.3.0rc1) ejecutada y commiteada en 3fec2da; Task 2 (publicación rc1) completada por la persona (D-04) y verificada por el orquestador (PyPI/TestPyPI con 0.3.0rc1, run 35491961779 SUCCESS)"
  - "Task 3 (promoción a 0.3.0) ejecutada y commiteada en 9eb3ea8: bump de pyproject/uv.lock, heading [0.3.0] y `Sin cambios de código respecto a 0.3.0rc1`"
  - "Task 4 (publicación de 0.3.0 final) COMPLETADA por la persona (D-04) y verificada por el orquestador: tag anotado v0.3.0 → 9eb3ea8, run 35492821208 SUCCESS (10/10 jobs CI verdes), PyPI info.version = 0.3.0"
  - "Heading final fechado 2026-09-19, coherente con [0.2.7] y [0.3.0rc1] (calendario de release del mantenedor -06:00)"

patterns-established:
  - "El guard file-wide de tests/test_release_docs.py sobrevive a la promoción: verde con `[Unreleased]` ya vacío y con el heading renombrado a [0.3.0]"
  - "La promoción se verifica como diff de código vacío contra el tag de rc1, no solo por el literal de versión"
  - "La publicación final se cierra con evidencia de tres capas: tag anotado → run de CI/publicación verde → introspección del registro PyPI"

requirements-completed: [REL-02]

# Metrics
duration: "~9 min autónomos (Tasks 1 y 3); Tasks 2 y 4 son checkpoints humanos (D-04)"
completed: 2026-09-19
---

# Phase 8 Plan 3: Release 0.3.0rc1 → 0.3.0 — COMPLETO (4/4)

**`0.3.0rc1` y `0.3.0` publicadas en PyPI por OIDC sin token (runs `35491961779` y `35492821208`, 10/10 jobs de CI verdes), con promoción rc→final sin deriva de código (`git diff v0.3.0rc1 -- encino_orm` vacío), suite completa verde (1124 passed) y wheels `Version: 0.3.0`; REL-02 satisfecho.**

> **ESTADO: Plan COMPLETO — 4/4 tasks.** Tags anotados `v0.3.0rc1` → `3fec2da` y `v0.3.0` → `9eb3ea8` empujados a origin; PyPI reporta `0.3.0rc1` y `0.3.0` (y `0.2.7` precede a ambos).

## Performance

- **Duration:** ~9 min autónomos (Tasks 1 y 3); Tasks 2 y 4 son checkpoints humanos (D-04)
- **Started:** 2026-09-19
- **Completed:** 2026-09-19 — publicación final de 0.3.0 verificada
- **Tasks:** 4 de 4 (Tasks 1 y 3 autónomas; Tasks 2 y 4 checkpoints humanos COMPLETADOS por la persona)
- **Files modified:** 3 (`pyproject.toml`, `uv.lock`, `CHANGELOG.md`)

## Accomplishments

### Task 1 — Corte de 0.3.0rc1 (`3fec2da`)

- Gate de CI verificado antes de cortar: `uv run pytest tests/test_release_config.py -q` → **9 passed**;
  `release.yml` confirma `uses: ./.github/workflows/ci.yml`, `needs: [ci]`, `id-token: write`,
  `uv publish --trusted-publishing always` y `environment: { name: pypi }`.
- Suite completa verde antes de cortar: `uv run pytest -q -m "not optional_engine and not benchmark"`
  → **1124 passed, 38 deselected**.
- `pyproject.toml` → `version = "0.3.0rc1"`; `uv lock`; `uv lock --check` → exit 0.
- `CHANGELOG.md`: `[Unreleased]` renombrado a `## [0.3.0rc1] - 2026-09-19` con nuevo `[Unreleased]` vacío.
- `uv build` → `dist/encino_orm-0.3.0rc1-py3-none-any.whl` con `Version: 0.3.0rc1` (no publicado en local).

### Task 2 — Publicación de 0.3.0rc1 (checkpoint humano, COMPLETADO por la persona)

Evidencia verificada por el orquestador:

- Workflow run `35491961779` ("Publish to PyPI", tag `v0.3.0rc1`) re-ejecutado **SUCCESS** tras el
  fix del trusted publisher; `Build and publish=success` y los **10 jobs reutilizables de CI verdes**.
- TestPyPI: `0.3.0rc1` presente (run `35491781848` SUCCESS) — validación OIDC en TestPyPI cerrada.
- PyPI: `0.3.0rc1` presente.
- Tag anotado `v0.3.0rc1` → `3fec2da` (`git rev-parse v0.3.0rc1^{commit}` = `3fec2da8e146431bb12f2437f0d07962e0017e27`),
  empujado a origin. `0.3.0` final NO presente en PyPI en este punto.

### Task 3 — Promoción a 0.3.0 (`9eb3ea8`)

- `pyproject.toml:10` → `version = "0.3.0"`; `uv lock` actualizó `encino-orm v0.3.0rc1 -> v0.3.0`;
  `uv.lock:793` → `version = "0.3.0"`; `uv lock --check` → exit 0.
- `CHANGELOG.md`: `## [0.3.0rc1] - 2026-09-19` renombrado a `## [0.3.0] - 2026-09-19` con la línea
  `Sin cambios de código respecto a \`0.3.0rc1\``. Orden descendente confirmado:
  `[Unreleased]` (L9) → `[0.3.0]` (L11) → `[0.2.7]` (L369) → `[0.2.6]` (L412).
- **Sin deriva de código**: `git diff v0.3.0rc1 -- encino_orm` **vacío** (solo versión/lock/changelog).
- Suite completa verde en el commit de promoción: `uv run pytest -q -m "not optional_engine and not benchmark"`
  → **1124 passed, 38 deselected**.
- Guards file-wide verdes con `[Unreleased]` vacío y heading renombrado:
  `tests/test_release_docs.py` + `tests/test_release_config.py` → **17 passed**.
- `uv build` → `dist/encino_orm-0.3.0-py3-none-any.whl` (`Version: 0.3.0`) y
  `dist/encino_orm-0.3.0.tar.gz` (`Version: 0.3.0`). No publicado en local.

### Task 4 — Publicación de 0.3.0 final (checkpoint humano, COMPLETADO por la persona)

Evidencia verificada por el orquestador:

- Tag anotado `v0.3.0` → `9eb3ea8` (`git rev-parse v0.3.0^{commit}` =
  `9eb3ea87d4349d665ccdeef61e16e8cb24b453b5`, el commit de promoción), empujado a origin.
- Workflow run **`35492821208`** ("Publish to PyPI", tag `v0.3.0`) = **SUCCESS**: los **10 jobs
  reutilizables de CI verdes**, `Build and publish=success`; el log muestra
  `Uploading encino_orm-0.3.0-py3-none-any.whl` y `Uploaded encino_orm-0.3.0.tar.gz`.
- PyPI JSON API reporta `info.version = 0.3.0` y `0.3.0` presente; `0.3.0rc1` y `0.2.7` también
  presentes → cadena ordenada `0.2.7` → `0.3.0rc1` → `0.3.0` confirmada, sin republicar `0.2.7`.
- Publicación vía OIDC trusted publishing (sin `PYPI_API_TOKEN`) tras la aprobación del entorno `pypi`.

## Task Commits

1. **Task 1: Verificar el gate de CI y cortar 0.3.0rc1** - `3fec2da` (chore)
2. **Task 2: Publicar 0.3.0rc1 por OIDC** - sin commit (checkpoint humano; ejecutado por la persona)
3. **Task 3: Promover a 0.3.0 (versión + lock + heading + dry-run)** - `9eb3ea8` (chore)
4. **Task 4: Publicar 0.3.0 final por OIDC** - sin commit (checkpoint humano; ejecutado por la persona)

**Plan metadata (cierre):** este SUMMARY + `STATE.md` + `ROADMAP.md` + `REQUIREMENTS.md` (commits siguientes)

_Nota: los checkpoints humanos (Tasks 2 y 4) no producen commits de código; su evidencia son los runs de GitHub Actions y la introspección de PyPI._

## Files Created/Modified

- `pyproject.toml` - `version = "0.3.0"` (único literal de versión, línea 10)
- `uv.lock` - entrada `encino-orm` (L792-793) actualizada a `version = "0.3.0"`
- `CHANGELOG.md` - heading `[0.3.0rc1]` → `[0.3.0] - 2026-09-19` + nota de "sin cambios de código"

## Decisions Made

- **4/4 tasks completas**: la cadena de publicación humana (D-04) se cerró con los runs `35491961779`
  (rc1) y `35492821208` (0.3.0), ambos OIDC y gateados por CI verde; REL-02 queda satisfecho.
- **Fecha del heading**: `2026-09-19`, coherente con `[0.2.7]` y `[0.3.0rc1]` (calendario de release
  del mantenedor a -06:00; UTC ya marca 2026-09-20).
- **Nota "Sin cambios de código respecto a 0.3.0rc1"**: la promoción rc→final es un cambio de versión
  puro; la nota lo deja explícito y enlaza con la verificación de diff vacío.

## Deviations from Plan

None - plan ejecutado tal como se escribió en las partes autónomas (Tasks 1 y 3). Las Tasks 2 y 4 son
checkpoints humanos por diseño (no desviaciones).

## Issues Encountered

- El comando de verificación literal del plan imprime `METADATA` `splitlines()[1]`, que en este backend
  devuelve `Name: encino-orm` (orden del header: `Metadata-Version`, `Name`, `Version`). Se verificó el
  valor real filtrando las líneas `Name:`/`Version:` → `Version: 0.3.0` (wheel y sdist). Sin impacto
  (aceptación satisfecha).
- La primera publicación de rc1 falló por configuración del trusted publisher en GitHub/PyPI y se
  resolvió re-ejecutando el workflow (`35491961779` SUCCESS). Documentado como flujo normal de checkpoint.

## User Setup Required

Ninguno pendiente. La aprobación del entorno `pypi` se completó para ambos cortes (rc1 y final).

## Next Phase Readiness

- **Fase 8 COMPLETA (8/8 planes)**: 0.2.7 → 0.3.0rc1 → 0.3.0 publicados por OIDC; REL-02 satisfecho.
- Sin bloqueos. El milestone `0.2.6 → 0.3.0` está listo para su verificación/cierre de milestone.

---

## Self-Check

- FOUND: `pyproject.toml` (`version = "0.3.0"`)
- FOUND: `uv.lock` (entrada `encino-orm` → `version = "0.3.0"`)
- FOUND: `CHANGELOG.md` (contiene `## [0.3.0] - 2026-09-19` en L11 y `## [Unreleased]` vacío en L9)
- FOUND: `dist/encino_orm-0.3.0-py3-none-any.whl` (`Version: 0.3.0`)
- FOUND: `dist/encino_orm-0.3.0.tar.gz` (`Version: 0.3.0`)
- FOUND: commit `3fec2da` (corte de rc1)
- FOUND: commit `9eb3ea8` (promoción a 0.3.0)
- VERIFIED: `git diff v0.3.0rc1 -- encino_orm` vacío
- VERIFIED: tag anotado `v0.3.0` → `9eb3ea87d4349d665ccdeef61e16e8cb24b453b5`
- VERIFIED: run `35492821208` SUCCESS; PyPI `info.version = 0.3.0` con `0.3.0rc1` y `0.2.7` presentes

## Self-Check: PASSED (4/4 tasks)

---

*Phase: 08-release-0-3-0*
*Plan: 03 (COMPLETO — 4/4)*
