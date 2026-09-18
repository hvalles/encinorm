---
phase: 03-data-correctness
plan: 06
status: complete
gap_closure: true
subsystem: database
tags: [cache, cachedmodel, cache-invalidation, canonical-pk-domain, cr-01, data-correctness, fail-open]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "CachedModel con overrides post-commit de update/delete/upsert y fail-open (03-03); contrato de caché documentado (03-04)"
provides:
  - "Dominio de caché canónico: load() escribe SIEMPRE bajo la PK de la fila; una lectura no-PK consulta la BD, aprende la PK y recachea bajo ella"
  - "_resolve_pk_values aprende la PK real de la fila afectada (instancia si las claves de escritura son la PK; SELECT ligado y con scope si no)"
  - "_invalidate_pk borra exactamente la única entrada de la PK; fail-open (D-12) preservado en resolución y borrado"
  - "Cinco regresiones CR-01 (RED→GREEN) sobre escrituras sin la PK en la instancia (id=None) y el residual inverso"
affects: [03-data-correctness, 08-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dominio de caché canónico: una sola clave posible por fila (la PK), de modo que toda escritura puede invalidarla"
    - "Resolución de la PK reutilizando Model.load (parámetros ligados + current_scope) en vez de SQL nuevo"
    - "Fail-open en la derivación de la clave: la resolución de la PK y el cache.delete van dentro de try/except con logger.warning"

key-files:
  created: []
  modified:
    - encino_orm/model/cached.py
    - tests/test_cached_model.py
    - tests/test_redis_cache.py
    - docs/guide.md
    - docs/design/5-security.md
    - CHANGELOG.md

key-decisions:
  - "Opción (b) del encargo: dominio canónico por PK en vez de resolver la PK manteniendo el cacheo por clave de lectura. Elimina el residual inverso por construcción, reduce la invalidación a un único dominio y convierte la premisa de D-11 en invariante."
  - "La lectura no-PK deja de acierta en caché (consulta la BD y recachea bajo la PK): cambio de comportamiento real, documentado en docs/guide.md §10 y CHANGELOG."
  - "La PK se resuelve ANTES de delete (un borrado físico elimina la fila y el SELECT posterior ya no la encontraría); en update/upsert se resuelve antes y se invalida después de super() (post-commit)."

patterns-established:
  - "Cache-aside con dominio canónico: la clave de caché es la PK de la fila y la invalidación resuelve la PK real de la fila afectada"
  - "Resolución de identidad fail-open: si no se puede derivar la PK, no se invalida pero la escritura nunca se bloquea ni se revierte"

requirements-completed: [DATA-03]

# Metrics
duration: 8min
completed: 2026-09-18
---

# Phase 3 Plan 6: Dominio de caché canónico por PK (cierre de CR-01) Summary

**La caché de `CachedModel` pasa a tener un dominio canónico por PK: `load()` escribe solo bajo la PK de la fila y `update`/`delete`/`upsert` resuelven la PK real de la fila afectada antes de borrar esa única entrada, cerrando el residual CR-01 (A2/B2/C2) en el que una instancia de escritura con `id=None` dejaba viva la entrada `[id=1]`.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-18T18:46:00Z (aprox.)
- **Completed:** 2026-09-18T18:54:23Z
- **Tasks:** 3 (2 TDD + 1 docs)
- **Files modified:** 6

## Accomplishments
- `load()` cachea SIEMPRE bajo la PK: en miss o lectura no-PK llama a `super().load`, aprende la PK de la fila devuelta y escribe bajo `_cache_key_for(pk_keys, pk_values)`; nunca bajo la clave de lectura. Una lectura no-PK se comporta como consulta directa (no acierta en caché).
- `_resolve_pk_values(keys)` devuelve la PK real de la fila afectada: de la instancia si las claves de escritura son la PK, o con un `super().load(keys=write_keys)` ligado y con `scope` si no. Devuelve `None` si no hay caché, si alguna clave es `None` o si el backend falla (fail-open).
- `_invalidate_pk(pk_values)` borra exactamente la entrada de la PK (la derivación de la clave va dentro del `try`); `_invalidate` (dos dominios) se elimina.
- `update`/`delete`/`upsert` resuelven la PK antes y invalidan tras `super()` (post-commit); `delete` resuelve antes porque un borrado físico elimina la fila.
- Cinco regresiones `test_cr01_*` (RED capturado con 5 failed / 1 passed, luego GREEN con 6 passed) cubren la lectura no-PK, `update`/`upsert`/`delete` sin la PK en la instancia y el residual inverso.
- El test de integración de Redis queda alineado al contrato canónico (clave derivada de la PK con `obj.id`; segunda carga por `id=`).
- Documentación y CHANGELOG actualizados; `insert_many(cache=...)`, `_cache_key_for`, `_cache_key` y `_delete_cached` intactos (D-16).

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresiones CR-01 (RED)** - `25230fb` (test)
2. **Task 2: Dominio canónico por PK en `cached.py` (GREEN)** - `884439d` (fix)
3. **Task 3: Documentar el dominio canónico** - `e340c52` (docs)
4. **Formato ruff** - `182e20b` (style)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified
- `encino_orm/model/cached.py` - `load` canónico por PK; `_resolve_pk_values` + `_invalidate_pk` sustituyen a `_invalidate`; overrides reordenados (resolver antes, invalidar después).
- `tests/test_cached_model.py` - `DDL_PK.rfc` pasa a `TEXT UNIQUE`; helpers `_pk_key`/`_rfc_key`; cinco tests `test_cr01_*`; el test CR-01 previo intacto.
- `tests/test_redis_cache.py` - clave derivada de la PK (`_cache_key_for(("id",), {"id": obj.id})`) y segunda carga por `id=obj.id`.
- `docs/guide.md` - §10 documenta el dominio canónico y que la lectura no-PK no acierta en caché.
- `docs/design/5-security.md` - §5.4 describe el mecanismo real (resolver la PK de la fila, borrar esa única entrada; fail-open).
- `CHANGELOG.md` - entrada aditiva en `[Unreleased] ### Corregido` con el cambio de comportamiento.

## Decisions Made
- **Opción (b) — dominio canónico por PK** (supersede la premisa de D-11): elimina el residual inverso por construcción, deja un único dominio verificable y restaura la intención de D-11 como invariante. Coste aceptado: una lectura no-PK nunca acierta en caché y cada escritura no-PK paga un SELECT extra de resolución (el que la opción (a) también pagaba).
- La PK se resuelve **antes** del borrado físico (la fila desaparece tras él) y la invalidación ocurre **después** de `super()` (post-commit), preservando D-10/D-15.
- D-12 (fail-open) y D-16 (`insert_many(cache=)`) se preservan sin cambios.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `ruff format --check` fallaba en `cached.py`**
- **Found during:** Gate final (`uv run ruff format --check encino_orm tests`)
- **Issue:** La llamada `await cache.set(...)` multilínea escrita en Task 2 no coincidía con el formato de ruff (cabe en 100 columnas en una sola línea), así que el gate de formato salía 1.
- **Fix:** `uv run ruff format encino_orm/model/cached.py` (cambio puramente de formato).
- **Files modified:** `encino_orm/model/cached.py`
- **Verification:** `uv run ruff format --check encino_orm tests` → exit 0; suite completa 830 passed.
- **Committed in:** `182e20b` (style, commit separado)

---

**Total deviations:** 1 auto-fixed (1 blocking/formato)
**Impact on plan:** Ninguno funcional; solo se aplicó el formateador del proyecto para mantener el gate verde.

## Issues Encountered
- Ninguno. La suite completa pasó de 825 a 830 tests (los 5 nuevos CR-01) con 0 fallos.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CR-01 (BLOCKER) cerrado: DATA-03 vuelve a estar cubierto por un must-have verificable (dominio canónico por PK, fail-open e `insert_many(cache=)` preservados).
- Queda pendiente `03-07` (WR-01/IN-01, migraciones) para la ronda 2 de gap-closure de la Fase 3.
- Sin blockers para este plan. La suite completa, `ruff check`, `ruff format --check` y `mypy` salen 0.

---

*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- Ficheros creados/modificados en disco: `encino_orm/model/cached.py`, `tests/test_cached_model.py`, `tests/test_redis_cache.py`, `docs/guide.md`, `docs/design/5-security.md`, `CHANGELOG.md`.
- Commits de tarea en el historial: `25230fb`, `884439d`, `e340c52`, `182e20b`.
- Evidencia RED (Task 1): `uv run pytest tests/test_cached_model.py -k cr01 -q` → **5 failed, 1 passed, 9 deselected** (exit 1).
- Evidencia GREEN (Task 2): `uv run pytest tests/test_cached_model.py -k cr01 -q` → **6 passed, 9 deselected** (exit 0).
- Task 2 verify: `uv run pytest tests/test_cached_model.py tests/test_cache_backend.py -q` → **21 passed**.
- Suite completa: `uv run pytest -q` → **830 passed, 10 snapshots passed**.
- Gates: `ruff check encino_orm tests` → 0; `ruff format --check encino_orm tests` → 0; `mypy encino_orm` → 0; `noqa` en `encino_orm/` = 0; `import redis` en `cached.py` = 0.
- Greps de aceptación: `def _invalidate\b` en `cached.py` = 0; `_resolve_pk_values` = 4; `_invalidate_pk` = 4; `super().load` = 3; `_delete_cached` = 2.
