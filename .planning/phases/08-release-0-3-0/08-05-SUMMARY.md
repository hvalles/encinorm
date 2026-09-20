---
phase: 08-release-0-3-0
plan: 05
subsystem: docs
tags: [readme, env-example, pinning, migration, release, rel-05]

# Dependency graph
requires:
  - phase: 08-04
    provides: "docs/MIGRATION-0.3.md y la enumeración viejo/nuevo del CHANGELOG (destino del enlace del README)"
provides:
  - "README con guía de pinning ~=0.2.6 y rationale ~= vs rango abierto"
  - "Aviso de credenciales SOLO para desarrollo local + .env.example committeable"
  - "Enlace del README a docs/MIGRATION-0.3.md y eliminación de la ruta muerta prompts/ en el README"
  - "tests/test_docs_hygiene.py que congela REL-05 para README + .env.example"
affects: [08-07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Guard de higiene docs por lectura pathlib (DB-free, sin red, sin subprocess)"
    - "Scope de guard explícito para no acoplarse a la limpieza docs/** de otro plan"

key-files:
  created:
    - .env.example
    - tests/test_docs_hygiene.py
  modified:
    - README.md

key-decisions:
  - "REL-05 se marca PARCIAL: 08-05 entrega README + credenciales dev; la parte docs/** la cierra 08-07 (ambos declaran REL-05)"
  - "El guard NO barre docs/** (esa prohibición vive en tests/test_docs_links.py de 08-07) para no dejar el test rojo entre planes"
  - "El README evita el literal >=0.2.6 en cualquier forma (incluso como contraejemplo) para no disparar el propio guard"

patterns-established:
  - "Hygiene guard: assertions de fuente con pathlib sobre artefactos rastreados; sin motores ni red"

requirements-completed: []  # REL-05 es parcial: 08-05 README/.env.example, 08-07 docs/**; se cierra en 08-07

# Metrics
duration: 2min
completed: 2026-09-20
---

# Phase 8 Plan 05: README release guide, dev-only .env.example, and hygiene guard Summary

**README con pinning `~=0.2.6` (rationale `~=` vs rango abierto), aviso de credenciales solo-dev, enlace a `docs/MIGRATION-0.3.md`, `.env.example` committeable para los seis motores y guard de higiene `tests/test_docs_hygiene.py`.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-20T04:12:27Z
- **Completed:** 2026-09-20T04:14:02Z
- **Tasks:** 3
- **Files modified:** 3 (README.md modificado; `.env.example` y `tests/test_docs_hygiene.py` creados)

## Accomplishments

- README con guía de pinning: token literal `encino-orm~=0.2.6` y explicación en español de por qué `~=` y no un rango abierto durante la ventana `0.x` (pip no trata las `0.x` como especiales para `>=`, así que un rango abierto auto-instala las rupturas de una nueva *minor*).
- README header/estado actualizados a `v0.3.0`; la referencia muerta a `prompts/analisys-07.md` (gitignored, 404 en PyPI/CI) se sustituye por punteros rastreados a `CHANGELOG.md` y `docs/MIGRATION-0.3.md`.
- Fila de `docs/MIGRATION-0.3.md` añadida a la tabla `## Documentación` (qué rupturas cubre).
- Aviso explícito en `## Pruebas`: las credenciales de `docker-compose.yml`/`.env.example` son SOLO para desarrollo local, nunca producción.
- `.env.example` nuevo: variables `ENCINO_ORM_*` de MySQL, MariaDB, PostgreSQL, MSSQL (incl. DRIVER/TRUST_CERT), Oracle (incl. SERVICE) y Redis, con cabecera dev-only y valores de juguete de `docs/docker.md`.
- `tests/test_docs_hygiene.py` con 7 tests que congelan pinning, ausencia de `prompts/` y de `>=0.2.6`, enlace a migración, aviso dev-only y contenido de `.env.example`.

## Task Commits

Each task was committed atomically:

1. **Task 1: README — pinning, aviso dev, versión, enlace de migración y enlace muerto** - `6046c01` (docs)
2. **Task 2: Crear .env.example con cabecera dev-only** - `acbac04` (chore)
3. **Task 3: Guard de higiene del README y de .env.example** - `81961ba` (test)

**Plan metadata:** final commit of this plan (`docs(08-05): complete README release guide plan`) — ver `git log`

## Files Created/Modified

- `README.md` - Pinning `~=0.2.6` con rationale, header `v0.3.0`, enlace a migración, aviso dev-only, eliminación de `prompts/`.
- `.env.example` - Variables `ENCINO_ORM_*` de los seis motores con cabecera "credenciales SOLO para desarrollo local".
- `tests/test_docs_hygiene.py` - Guard de fuente (7 tests) de REL-05 para README + `.env.example`.

## Decisions Made

- **REL-05 parcial, no cerrado aquí.** Tanto 08-05 como 08-07 declaran `REL-05`; 08-05 entrega la parte README + credenciales dev y 08-07 la parte `docs/**`. Marcar `REL-05` completo en este plan dejaría `REQUIREMENTS.md` en falso hasta 08-07, así que no se ejecuta `requirements.mark-complete` y `requirements-completed` queda vacío con nota. El verifier debe cerrar `REL-05` en 08-07.
- **El guard no barre `docs/**`.** Esa limpieza y su guard (`tests/test_docs_links.py`) son de 08-07; incluir el barrido aquí dejaría el test rojo hasta entonces (deadlock entre planes).
- **Contraejemplo sin literal.** El README explica el problema del rango abierto sin escribir la cadena exacta `>=0.2.6`, porque el guard prohíbe ese literal (incluso como contraejemplo) — solo aparece `>=` genérico.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- REL-05 parte README/credenciales entregada y congelada por test; `REL-05` permanece abierto y lo cierra 08-07 (barrido `docs/**`).
- Verificación de plan verde: `uv run pytest tests/test_docs_hygiene.py -q` (7 passed), `uv run mkdocs build --strict` (build OK), suite completa `uv run pytest -q -m "not optional_engine and not benchmark"` (1087 passed, 38 deselected).
- Sin bloqueos para 08-06/08-07.

---
*Phase: 08-release-0-3-0*
*Completed: 2026-09-20*

## Self-Check: PASSED

Files verified on disk:
- FOUND: README.md
- FOUND: .env.example
- FOUND: tests/test_docs_hygiene.py

Commits verified:
- FOUND: 6046c01
- FOUND: acbac04
- FOUND: 81961ba
