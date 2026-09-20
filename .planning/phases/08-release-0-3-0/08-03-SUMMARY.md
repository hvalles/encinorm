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
  - "0.3.0rc1 construible: pyproject.toml + uv.lock promovidos a `0.3.0rc1` y CHANGELOG promovido a `## [0.3.0rc1]`"
  - "wheel `dist/encino_orm-0.3.0rc1-py3-none-any.whl` con `Version: 0.3.0rc1` (no publicado)"
  - "suite completa verde sobre el árbol rc1 ANTES de tagear: 1124 passed, 38 deselected"
affects: [08-03 (continuación Task 3/4), 08-release-0-3-0]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Promoción de versión pura: pyproject.toml + uv lock + heading de CHANGELOG, sin cambios de código entre rc y final"
    - "Detección temprana de build rojo: suite completa (mismo filtro que ci.yml) corrida ANTES del tag, porque `publish: needs: [ci]` + entorno `pypi` bloquean publicar con CI rojo"

key-files:
  modified:
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "Task 1 (corte de 0.3.0rc1) ejecutada y commiteada; Tasks 2–4 (publicaciones reales a TestPyPI/PyPI) quedan tras checkpoints humanos (D-04, la sesión no maneja credenciales)"
  - "HEADING de rc1 fechado 2026-09-19 (fecha local del host, coherente con `## [0.2.7] - 2026-09-19`)"

patterns-established:
  - "El guard file-wide de tests/test_release_docs.py sobrevive a la promoción: se verificó en verde con `[Unreleased]` ya vacío"

requirements-completed: []  # REL-02 se cierra cuando 0.3.0rc1 y 0.3.0 estén publicadas; aquí queda PENDIENTE

# Metrics
duration: "~8 min (autónomo, solo Task 1)"
completed: 2026-09-19
---

# Phase 8 Plan 3: Release 0.3.0rc1 y promoción a 0.3.0 — PAUSADO EN CHECKPOINT

**Corte de `0.3.0rc1`: versión sincronizada en `pyproject.toml`/`uv.lock`, `[Unreleased]` promovido a `[0.3.0rc1]` con nuevo `[Unreleased]` vacío, wheel `0.3.0rc1` construida y suite completa verde (1124 passed) antes del tag; las publicaciones reales (Tasks 2 y 4) quedan como checkpoints humanos.**

> **ESTADO: Plan PAUSADO en Task 2 (`checkpoint:human-action`).** No se ha tageado ni publicado nada. Las Tasks 3 (promoción a `0.3.0`) y 4 (publicación final) NO se han ejecutado y dependen de que la persona publique `0.3.0rc1` (Task 2) primero.

## Performance

- **Duration:** ~8 min (autónomo; solo Task 1 y su verificación)
- **Started:** 2026-09-19
- **Completed (parcial):** 2026-09-19 — pausado en el checkpoint de publicación
- **Tasks:** 1 de 4 ejecutadas (Task 1 completa; Task 2 = checkpoint humano PENDIENTE; Tasks 3–4 pendientes)
- **Files modified:** 3 (`pyproject.toml`, `uv.lock`, `CHANGELOG.md`)

## Accomplishments (Task 1)

- Gate de CI verificado antes de cortar: `uv run pytest tests/test_release_config.py -q` → **9 passed**;
  `release.yml` confirma `uses: ./.github/workflows/ci.yml`, `needs: [ci]`, `id-token: write`,
  `uv publish --trusted-publishing always` y `environment: { name: pypi }`.
- Suite completa verde antes de cortar (build rojo imposible de publicar):
  `uv run pytest -q -m "not optional_engine and not benchmark"` → **1124 passed, 38 deselected**.
- `pyproject.toml` → `version = "0.3.0rc1"`; `uv lock` actualizó `encino-orm v0.2.7 -> v0.3.0rc1`;
  `uv lock --check` → exit 0.
- `CHANGELOG.md`: `## [Unreleased]` renombrado a `## [0.3.0rc1] - 2026-09-19` e insertado un
  `## [Unreleased]` nuevo y vacío arriba. Orden descendente confirmado:
  `[Unreleased]` (L9) → `[0.3.0rc1]` (L11) → `[0.2.7]` (L367) → `[0.2.6]` (L410).
- Guards file-wide de `tests/test_release_docs.py` **siguen verdes** con `[Unreleased]` vacío
  (`test_release_docs.py` + `test_release_config.py` → 17 passed).
- `uv build` → `dist/encino_orm-0.3.0rc1-py3-none-any.whl` con `Version: 0.3.0rc1` (NO publicado).
- Re-corrida de la suite completa sobre el árbol ya promovido: **1124 passed, 38 deselected**.

## Task Commits

1. **Task 1: Verificar el gate de CI y cortar 0.3.0rc1** - `3fec2da` (chore)

**Plan metadata (props de checkpoint):** este SUMMARY y `STATE.md` (commit siguiente)

## Files Created/Modified

- `pyproject.toml` - `version = "0.3.0rc1"` (único literal de versión, línea 10)
- `uv.lock` - entrada `encino-orm` actualizada a `version = "0.3.0rc1"`
- `CHANGELOG.md` - `[Unreleased]` → `[0.3.0rc1] - 2026-09-19` + nuevo `[Unreleased]` vacío

## Decisions Made

- **Task 1 solo**: Tasks 3–4 son estrictamente posteriores a la publicación de rc1 (la verificación de
  Task 3 hace `git diff v0.3.0rc1`, tag que solo existe tras la Task 2 humana), por lo que no son
  alcanzables en esta pasada. Se detiene en el checkpoint conforme a D-04.
- **Fecha del heading**: `2026-09-19`, coherente con `[0.2.7]` y la fecha local del host (UTC ya es
  2026-09-20; el calendario de release del mantenedor es -06:00).

## Deviations from Plan

None - plan ejecutado tal como se escribió en la parte autónoma (Task 1). Las Tasks 2–4 no se han
ejecutado por ser checkpoints/dependencias humanas (previsto, no desviación).

## Issues Encountered

- El comando de verificación literal del plan imprime `METADATA` `splitlines()[1]`, que en este
  backend devuelve `Name: encino-orm` (el orden del header es `Metadata-Version`, `Name`, `Version`).
  Se verificó el valor real con un filtro explícito de las líneas `Name:`/`Version:` →
  `Version: 0.3.0rc1`. Sin impacto (aceptación satisfecha).

## User Setup Required

La publicación real la dispara la persona (D-04). Ver el checkpoint en la respuesta.

## Next Phase Readiness

- `0.3.0rc1` está construible y la suite está verde en `3fec2da`; el gate de publicación
  (`needs: [ci]` + entorno `pypi`) está confirmado.
- Bloqueado hasta que la persona publique `v0.3.0rc1` (Task 2). Después, la Task 3 promueve a
  `0.3.0` (verificación `git diff v0.3.0rc1 -- encino_orm` vacío) y la Task 4 publica la final.

---

## Self-Check

- FOUND: `pyproject.toml` (contiene `version = "0.3.0rc1"`)
- FOUND: `uv.lock` (entrada `encino-orm` → `version = "0.3.0rc1"`)
- FOUND: `CHANGELOG.md` (contiene `## [0.3.0rc1]` en L11 y `## [Unreleased]` vacío en L9)
- FOUND: `dist/encino_orm-0.3.0rc1-py3-none-any.whl` (`Version: 0.3.0rc1`)
- FOUND: commit `3fec2da` (corte de rc1)
- FOUND: commit `2387bec` (metadatos del checkpoint)
- PENDING (por diseño): Tasks 2 y 4 son publicaciones humanas (D-04); Task 3 depende del tag `v0.3.0rc1`.

## Self-Check: PASSED (Task 1; plan pausado en el checkpoint de publicación)

---

*Phase: 08-release-0-3-0*
*Plan: 03 (PAUSADO en Task 2 — checkpoint humano de publicación)*
