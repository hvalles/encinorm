---
phase: 08-release-0-3-0
plan: 01
subsystem: release
tags: [release, deprecations, pypi, semver, changelog, uv-lock, hatchling, fail-closed]

# Dependency graph
requires:
  - phase: "02 y 04 y 06"
    provides: "Los tres caminos deprecados que 0.2.7 avisa ya existen y estan congelados: reset_on_release='commit' (04-04), globales SECRET/GET_DB (06-02) y last_id() post-hoc (04-02)"
provides:
  - "0.2.7 publicada en PyPI (linea de mantenimiento v0.2.6) ANTES de cualquier artefacto 0.3.0"
  - "tests/test_deprecations_0_2_7.py: pines de los tres DeprecationWarning reales + guard de la allowlist tolerante a puntos (dotted) + guard fail-closed"
  - "pyproject.toml / uv.lock en 0.2.7 de forma consistente (uv lock --check verde)"
  - "CHANGELOG.md: seccion ## [0.2.7] - 2026-09-19 con deprecaciones y rupturas fail-closed sin warning posible"
  - "tag anotado v0.2.7 sobre main en el commit de congelacion e984e78, empujado a origin"
affects: [08-02, 08-03, 08-04, 08-06, 08-08]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SemVer deprecate-before-break: el minor 0.2.7 describe el comportamiento viejo con DeprecationWarning y nombra el reemplazo; las remociones se ejecutan en la linea 0.3.0 (08-06/08-08)"
    - "Ruptura fail-closed = no puede avisar: las validaciones que lanzan ValueError ANTES de aceptar (identificadores, indexes_ddl, QueryBuilder._table, cardinalidad de Query) se documentan, no se avisan; degradarlas para avisar reabriria la superficie de inyeccion"
    - "Allowlist tolerante a puntos (sql.py/query_builder.py) es diseno intencional y NO se unifica ni recibe warning; se blinda con un guard que corre bajo simplefilter('error')"
    - "Publicacion real como checkpoint humano (D-04): el ejecutor deja todo lo automatizable hecho (lock/build/suite/CHANGELOG) y no maneja credenciales"

key-files:
  created:
    - tests/test_deprecations_0_2_7.py
  modified:
    - pyproject.toml
    - uv.lock
    - CHANGELOG.md

key-decisions:
  - "No se anaden warnings nuevos: se pinean los tres reales (implicit commit on release, globales SECRET/GET_DB, last_id() post-hoc) con pytest.warns bajo filterwarnings=['error']."
  - "La ruptura de identificadores no validados es fail-closed y queda documentada como la que NO puede emitir warning previo; la allowlist tolerante a puntos se conserva intacta (intencional)."
  - "D-01 honrada: tag anotado v0.2.7 sobre main en el commit de congelacion e984e78, sin rama nueva (branching_strategy: none)."
  - "D-04 honrada: la publicacion real la ejecuto una persona; el tag disparo el workflow con PYPI_API_TOKEN (migracion a OIDC es 08-02)."

patterns-established:
  - "DeprecationWarning pinado con pytest.warns y match de substring, tolerante a filterwarnings=['error'] global"
  - "Guard de comportamiento intencional: el camino feliz (identificador cualificado) NO debe emitir warning"

requirements-completed: [REL-01]  # REL-01 se reparte entre 08-01 (0.2.7 publicada), 08-06 y 08-08 (retiradas); NO queda cerrada con este plan.

# Metrics
duration: 15min
completed: 2026-09-19
---

# Phase 8 Plan 1: Publicacion de 0.2.7 con DeprecationWarnings (REL-01)

**0.2.7 publicada en PyPI con los tres `DeprecationWarning` de runtime pinados (`reset_on_release='commit'`, globales `SECRET`/`GET_DB`, `last_id()` post-hoc), la ruptura fail-closed de identificadores documentada y la allowlist tolerante a puntos blindada; tag anotado `v0.2.7` sobre `main` en el commit de congelacion `e984e78`.**

## Performance

- **Duration:** ~15 min (ejecucion de tareas; `301c0f6` 15:04:47 -0600 → `e984e78` 15:06:01 -0600). El checkpoint humano de publicacion se resolvio el mismo dia.
- **Started:** 2026-09-19 (ejecucion de tareas)
- **Completed:** 2026-09-19
- **Tasks:** 3 de 3 (Task 3 = checkpoint humano, resuelto fuera de sesion)
- **Files modified:** 4 (1 creado, 3 modificados)

## Accomplishments

- **0.2.7 esta publicada en PyPI** (`info.version = 0.2.7`, `0.2.7` presente en `releases`) ANTES de que exista cualquier artefacto `0.3.0` — Criterio de Exito 1 de la Fase 8 satisfecho.
- Los tres `DeprecationWarning` reales de la linea 0.2.7 quedan pinados con `pytest.warns` bajo `filterwarnings=["error"]`: politica de liberacion (`reset_on_release="commit"`), globales mutables de seguridad (`SECRET`/`GET_DB`) y `last_id()` post-hoc.
- La ruptura de **identificadores no validados** queda documentada como **fail-closed**: valida y lanza `ValueError` antes de aceptar, por lo que no puede avisar sin degradar la seguridad. Misma justificacion escrita para `indexes_ddl` hostil, `QueryBuilder._table` no identificador y el contrato de cardinalidad de `Query`.
- La **allowlist tolerante a puntos** de `sql.py`/`query_builder.py` se conserva intacta y blindada por test: es diseno intencional y no se le anade un warning que lo contradiga.
- Version unica y consistente en `pyproject.toml` + `uv.lock` (`uv lock --check` verde); seccion `## [0.2.7] - 2026-09-19` en `CHANGELOG.md` en el orden descendente correcto (`[Unreleased]` con su contenido → `[0.2.7]` → `[0.2.6]`).
- Tag anotado **`v0.2.7`** sobre `main` apuntando a `e984e78` y empujado a `origin`.

## Task Commits

Cada tarea se commiteo atomicamente:

1. **Task 1: Pinear los tres DeprecationWarning y blindar la allowlist** - `301c0f6` (test)
2. **Task 2: Bump a 0.2.7, sincronizar lock, documentar [0.2.7] y dry-run de build** - `e984e78` (chore)
3. **Task 3: Congelar y publicar 0.2.7 (tag v0.2.7 → PyPI)** - checkpoint humano, sin commit de codigo (evidencia en Tag/PyPI abajo)

**Plan metadata:** (este SUMMARY, commit `docs(08-01)`)

## Human Publish Action (Task 3) — Evidencia

Task 3 es `checkpoint:human-action` (D-04: la sesion no maneja credenciales de publicacion). La accion humana fue **completada y verificada por el orquestador**:

| Evidencia | Verificacion |
|-----------|--------------|
| Commit de congelacion | `e984e78b2562e701ccae74da86d49fef7046b46a` (`chore(08-01): cut 0.2.7 source line with CHANGELOG and lock sync`) |
| Tag anotado | `v0.2.7` → `git rev-parse v0.2.7^{commit}` = `e984e78`; tagger `hvalles`, mensaje `0.2.7` |
| Tag empujado | `git ls-remote --tags origin v0.2.7` → `refs/tags/v0.2.7` (objeto `7951e8de…`) |
| Workflow de release | GitHub Actions run **`35470090057`** ("Publish to PyPI", trigger tag `v0.2.7`) → `Build and publish=success`; los 10 jobs del CI reutilizable verdes |
| PyPI | `https://pypi.org/pypi/encino-orm/json` → `info.version = 0.2.7` y `0.2.7` presente en `releases` |

El commit tagueado declara `version = "0.2.7"` en `pyproject.toml` y contiene `## [0.2.7] - 2026-09-19` en `CHANGELOG.md` (verificado con `git show e984e78:<path>`).

## Files Created/Modified

- `tests/test_deprecations_0_2_7.py` (creado, 84 lineas) - Pines de los tres `DeprecationWarning` + guard de la allowlist tolerante a puntos + guard fail-closed.
- `pyproject.toml` - `version = "0.2.7"` (unico literal de version).
- `uv.lock` - entrada `encino-orm` sincronizada a `0.2.7`; `uv lock --check` verde.
- `CHANGELOG.md` - seccion `## [0.2.7] - 2026-09-19` (deprecaciones + rupturas fail-closed sin warning posible) insertada al final de `[Unreleased]`, inmediatamente encima de `## [0.2.6]`.

## Decisions Made

- **No anadir warnings nuevos**: se pinean los tres existentes. La ruptura fail-closed se documenta en lugar de avisarse.
- **Allowlist tolerante a puntos**: intencional (expresiones calificadas `mm.agente`); no se unifica con la estricta ni recibe warning.
- **D-01**: tag anotado sobre `main` en el commit de congelacion, sin rama nueva.
- **D-04**: la publicacion real es un checkpoint humano; la migracion a OIDC es 08-02.

## Deviations from Plan

None - plan ejecutado tal como se escribio. (El checkpoint humano se resolvio con exito fuera de sesion; no hubo auto-fixes.)

## Issues Encountered

None.

## User Setup Required

La publicacion requirio `PYPI_API_TOKEN` (mecanismo vigente, retirado en 08-02) y la aprobacion del workflow `Publish to PyPI`. **Ya completado** por la persona; no queda accion pendiente para este plan. No se genero `08-01-USER-SETUP.md` porque la accion ya se ejecuto.

## Next Phase Readiness

**Wave 1 completa.** `main` puede continuar hacia 0.3.0. Siguientes planes (Wave 2, independientes entre si):

- **`08-02-PLAN.md`** — OIDC trusted publishing (`id-token: write`, `uv publish --trusted-publishing always`) en ambos workflows, entorno `pypi` protegido, retirada de `PYPI_API_TOKEN` y validacion en TestPyPI — REL-03.
- **`08-04-PLAN.md`** — `CHANGELOG.md` con cada ruptura en viejo/nuevo y `docs/MIGRATION-0.3.md` con pares Antes/Despues, registrada en la nav de MkDocs, con guard de fuente — REL-04. Comparte `CHANGELOG.md` con 08-01 (ya en Wave 1).

Despues: Wave 3 (`08-05`, `08-06`, `08-07`) → Wave 4 (`08-08`) → Wave 5 (`08-03`, 0.3.0rc1 + 0.3.0).

**Nota de requisitos:** REL-01 NO queda cerrado con este plan. 08-01 publica 0.2.7; las **retiradas** de las APIs deprecadas viven en 08-06 (`set_default_db`/`get_default_db`, globales `SECRET`/`GET_DB`) y 08-08 (`last_id()` post-hoc). No marcar REL-01 completo todavia.

---

*Phase: 08-release-0-3-0*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `.planning/phases/08-release-0-3-0/08-01-SUMMARY.md`
- FOUND: `tests/test_deprecations_0_2_7.py`
- FOUND: `pyproject.toml` (`version = "0.2.7"`)
- FOUND: `uv.lock` (`version = "0.2.7"` en la entrada `encino-orm`)
- FOUND: `CHANGELOG.md` (`## [0.2.7]`)
- FOUND: commit `301c0f6`
- FOUND: commit `e984e78`
- FOUND: tag anotado `v0.2.7` → `e984e78`
- FOUND: PyPI `info.version = 0.2.7`
