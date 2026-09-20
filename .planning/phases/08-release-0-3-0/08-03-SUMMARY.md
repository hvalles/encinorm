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
  - "0.3.0 construible y promovida en código: pyproject.toml + uv.lock a `0.3.0` y CHANGELOG a `## [0.3.0]`"
  - "wheel `dist/encino_orm-0.3.0-py3-none-any.whl` + sdist `.tar.gz` con `Version: 0.3.0` (no publicados)"
  - "promoción sin deriva de código: `git diff v0.3.0rc1 -- encino_orm` vacío"
affects: [08-03 (Task 4: publicación final), 08-release-0-3-0]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Promoción de versión pura: pyproject.toml + uv lock + heading de CHANGELOG, sin cambios de código entre rc y final"
    - "Detección temprana de build rojo: suite completa (mismo filtro que ci.yml) corrida ANTES del tag, porque `publish: needs: [ci]` + entorno `pypi` bloquean publicar con CI rojo"
    - "Trazabilidad rc→final: el tag anotado `v0.3.0rc1` sirve de punto de anclaje para demostrar `git diff -- encino_orm` vacío"

key-files:
  modified:
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "Task 1 (corte de 0.3.0rc1) ejecutada y commiteada en 3fec2da; Task 2 (publicación rc1) completada por la persona (D-04) y verificada por el orquestador (PyPI/TestPyPI con 0.3.0rc1, run 35491961779 SUCCESS)"
  - "Task 3 (promoción a 0.3.0) ejecutada y commiteada en 9eb3ea8: bump de pyproject/uv.lock, heading [0.3.0] y `Sin cambios de código respecto a 0.3.0rc1`"
  - "Task 4 (publicación de 0.3.0 final) queda PENDIENTE como checkpoint humano (D-04); NO se ha creado el tag v0.3.0, ni push, ni publicación"
  - "Heading final fechado 2026-09-19, coherente con [0.2.7] y [0.3.0rc1] (calendario de release del mantenedor -06:00)"

patterns-established:
  - "El guard file-wide de tests/test_release_docs.py sobrevive a la promoción: verde con `[Unreleased]` ya vacío y con el heading renombrado a [0.3.0]"
  - "La promoción se verifica como diff de código vacío contra el tag de rc1, no solo por el literal de versión"

requirements-completed: []  # REL-02 se cierra cuando 0.3.0rc1 y 0.3.0 estén AMBAS publicadas; 0.3.0 final sigue PENDIENTE

# Metrics
duration: "~9 min (autónomo acumulado: Task 3 sobre la pasada previa de Task 1)"
completed: 2026-09-19
---

# Phase 8 Plan 3: Release 0.3.0rc1 y promoción a 0.3.0 — PAUSADO EN CHECKPOINT DE PUBLICACIÓN FINAL

**`0.3.0rc1` publicada por OIDC (TestPyPI + PyPI, run `35491961779` SUCCESS) y `0.3.0` promovida en código con `git diff v0.3.0rc1 -- encino_orm` vacío, suite completa verde (1124 passed) y wheels `Version: 0.3.0` construidos; solo falta el checkpoint humano de publicación de la versión final.**

> **ESTADO: Plan PAUSADO en Task 4 (`checkpoint:human-action`).** Tasks 1–3 completas y commiteadas. NO se ha creado el tag `v0.3.0`, ni push, ni publicación. La Task 4 (tag anotado `v0.3.0` + aprobación del entorno `pypi`) la ejecuta la persona (D-04).

## Performance

- **Duration:** ~9 min autónomos (Task 3 sobre la pasada previa de Task 1)
- **Started:** 2026-09-19
- **Completed (parcial):** 2026-09-19 — pausado en el checkpoint de publicación final
- **Tasks:** 3 de 4 ejecutadas (Tasks 1 y 3 autónomas; Task 2 checkpoint humano COMPLETADO; Task 4 checkpoint humano PENDIENTE)
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
- `uv build` → `dist/encino_orm-0.3.0rc1-py3-none-any.whl` con `Version: 0.3.0rc1` (no publicado).

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
  `dist/encino_orm-0.3.0.tar.gz` (`Version: 0.3.0`). No publicado.

## Task Commits

1. **Task 1: Verificar el gate de CI y cortar 0.3.0rc1** - `3fec2da` (chore)
2. **Task 2: Publicar 0.3.0rc1 por OIDC** - sin commit (checkpoint humano; ejecutado por la persona)
3. **Task 3: Promover a 0.3.0 (versión + lock + heading + dry-run)** - `9eb3ea8` (chore)

**Plan metadata (props de checkpoint):** este SUMMARY y `STATE.md` (commit siguiente)

_Nota: Task 4 no se ha ejecutado (checkpoint humano pendiente)._

## Files Created/Modified

- `pyproject.toml` - `version = "0.3.0"` (único literal de versión, línea 10)
- `uv.lock` - entrada `encino-orm` (L792-793) actualizada a `version = "0.3.0"`
- `CHANGELOG.md` - heading `[0.3.0rc1]` → `[0.3.0] - 2026-09-19` + nota de "sin cambios de código"

## Decisions Made

- **Tasks 1–3 completas**: la Task 3 solo era alcanzable tras la publicación de rc1 (su verificación
  hace `git diff v0.3.0rc1`, tag que ya existe); el orquestador confirmó la publicación y esta pasada
  ejecutó la promoción. Task 4 se detiene en el checkpoint conforme a D-04.
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

## User Setup Required

La publicación de `0.3.0` final la dispara la persona (D-04). Ver el checkpoint en la respuesta.

## Next Phase Readiness

- `0.3.0` está construible y es idéntica en código a `0.3.0rc1`; la suite está verde en `9eb3ea8` y el
  gate de publicación (`needs: [ci]` + entorno `pypi`) está confirmado.
- Bloqueado hasta que la persona cree/empuje el tag anotado `v0.3.0` sobre `9eb3ea8` y apruebe el run
  de `Publish to PyPI` (entorno `pypi`). Tras la publicación, REL-02 queda satisfecho y el plan cierra.

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
- PENDING (por diseño): Task 4 es la publicación humana final (D-04); no se ha tageado `v0.3.0`.

## Self-Check: PASSED (Tasks 1–3; plan pausado en el checkpoint de publicación final)

---

*Phase: 08-release-0-3-0*
*Plan: 03 (PAUSADO en Task 4 — checkpoint humano de publicación final)*
