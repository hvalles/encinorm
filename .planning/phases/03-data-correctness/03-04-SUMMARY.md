---
phase: 03-data-correctness
plan: 04
subsystem: docs
tags: [docs, changelog, cache, lru, dev-test-contract, migrations, reconciliation, breaking-changes]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "rollback ledger rewrite (03-01), two-phase pending/applied runner + reconcile/resolve (03-02), CachedModel write invalidation (03-03), MemoryCacheBackend LRU + dev/test docstring (03-05)"
provides:
  - "docs/guide.md §10: contrato dev/test-only de MemoryCacheBackend (LRU max_size=1024) y Redis para producción"
  - "docs/guide.md §10: limitación de invalidación local al proceso (sin pub/sub) + fail-open post-commit"
  - "CHANGELOG.md [Unreleased] ### Corregido: los cuatro cambios incompatibles de la fase"
affects: [03-verify, 08-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "docs-only plan: sin gates de lint/type por tarea, gates en la verificación de plan"
    - "CHANGELOG scoped-grep: el conteo de ### Corregido se acota a [Unreleased] (el global tiene 4 históricos)"

key-files:
  created: []
  modified:
    - docs/guide.md
    - CHANGELOG.md

key-decisions:
  - "La nota dev/test y la limitación multi-proceso viven en §10 junto a la sección de caché, con remisión a docs/design/5-security.md §5.4 para el mecanismo"
  - "Las entradas de CHANGELOG son aditivas y no prejuzgan la enumeración completa de cambios incompatibles del milestone, que posee la Fase 8 (08-04)"

patterns-established:
  - "El contrato de un backend opcional se documenta donde el usuario lo elige (guía) y la promesa de compatibilidad en CHANGELOG, con ownership explícito de la enumeración del milestone"

requirements-completed: [DATA-04]

# Metrics
duration: 1min
completed: 2026-09-18
---

# Phase 3 Plan 4: Cache Contract & Phase CHANGELOG Summary

**`docs/guide.md` documenta que `MemoryCacheBackend` es dev/test-only (LRU `max_size=1024`) y que la invalidación de `CachedModel` es local al proceso, post-commit y fail-open; `CHANGELOG.md` extiende `[Unreleased] ### Corregido` con los cuatro cambios de la fase sin duplicar encabezado.**

## Performance

- **Duration:** 1 min
- **Started:** 2026-09-18T17:53:57Z
- **Completed:** 2026-09-18T17:54:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `docs/guide.md` §10 gana un bloque de contrato: `MemoryCacheBackend` es para dev/test, **no** producción; LRU con `max_size=1024` por defecto (configurable); `RedisCacheBackend` para producción (D-14).
- Se añade la sección "Invalidación y limitación multi-proceso": invalidación tras el commit, fail-open (warning, nunca revierte la escritura), solo la clave afectada, con remisión a `docs/design/5-security.md` §5.4 para el mecanismo (sobrescrituras de `update`/`delete`/`upsert`).
- Se explicita la limitación conocida: la invalidación es **local al proceso**; sin pub/sub distribuido, en despliegues multi-proceso las entradas obsoletas quedan acotadas por el TTL.
- `CHANGELOG.md` `[Unreleased] ### Corregido` se extiende (sin encabezado nuevo) con cuatro entradas: ledger de rollback (D-06/D-07), `migrate()` de dos fases + `reconcile_migrations`/`resolve_migration` (D-01/D-02/D-05/D-17), invalidación de `CachedModel` (D-09…D-12), y cota LRU + contrato dev/test de `MemoryCacheBackend` (D-13/D-14).
- La entrada del ledger de rollback marca explícitamente el CAMBIO INCOMPATIBLE (las filas `:down` dejan de existir) y todas las entradas llevan nota de ownership: aditivas, la enumeración del milestone es de la Fase 8 (`08-04`).

## Task Commits

Each task was committed atomically:

1. **Task 1: contrato dev/test + limitación multi-proceso en `docs/guide.md` §10** - `11f1e26` (docs)
2. **Task 2: `CHANGELOG.md` con los cambios incompatibles de la fase** - `bc18d2c` (docs)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `docs/guide.md` - §10: contrato dev/test-only + LRU `max_size=1024`, sección de invalidación y limitación multi-proceso, remisión a `5-security.md` §5.4
- `CHANGELOG.md` - `[Unreleased] ### Corregido`: cuatro entradas nuevas (ledger de rollback, dos fases/reconciliación, invalidación de caché, cota LRU)

## Decisions Made
- El contrato y la limitación se colocan en `docs/guide.md` §10 (donde el usuario elige backend), no en el docstring de diseño: el docstring de la clase ya lo declara (03-05) y la guía es la superficie de usuario.
- Las entradas de `CHANGELOG.md` son aditivas y conservan la nota de ownership hacia la Fase 8 (`08-04`), igual que hicieron 02-12 y las entradas previas de `[Unreleased]`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- El enlace interno de la guía usa el ancla generada por MkDocs para `### 5.4. Caché (opcional)` (`design/5-security.md#54-caché-opcional`); el build de docs (`mkdocs build --strict`) no forma parte de los gates locales de este plan, pero el ancla sigue la convención de slugify de MkDocs.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DATA-04 queda cubierto en su parte de documentación; la parte de código (LRU + docstring) la entregó 03-05.
- Con este plan, los cinco planes de la Fase 3 están ejecutados; la fase queda lista para `03-verify`.
- La enumeración completa de cambios incompatibles del milestone sigue con dueño explícito en la Fase 8 (`08-04`).

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- `docs/guide.md` y `CHANGELOG.md` existen en disco.
- Ambos commits de tarea existen en el historial (`11f1e26`, `bc18d2c`).
- `uv run pytest tests/test_cache_backend.py tests/test_cached_model.py -q` → 15 passed.
- `uv run pytest tests/test_cache_backend.py tests/test_cached_model.py tests/test_migrations.py -q` → 34 passed.
- `uv run pytest -q` → 824 passed (10 snapshots passed), 0 failed.
- `sed -n '/## \[Unreleased\]/,/## \[0.2.6\]/p' CHANGELOG.md | grep -c "### Corregido"` = 1 (global = 4 históricos).
- Greps de aceptación: `dev/test`=1, `1024`=1, `proceso`=4 en `docs/guide.md`; `rollback_migration`=1, `reconcile_migrations`=1, `MemoryCacheBackend`=1 en `CHANGELOG.md`.
- `uv run ruff check encino_orm tests` / `ruff format --check encino_orm tests` / `uv run mypy encino_orm` → exit 0; `noqa` en `encino_orm/` = 0.
- `grep -n "OrderedDict" encino_orm/model/cache_backend.py` → presente (2 coincidencias).
