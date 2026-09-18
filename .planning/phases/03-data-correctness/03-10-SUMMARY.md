---
phase: 03-data-correctness
plan: 10
status: complete
gap_closure: true
subsystem: database
tags: [docs, changelog, cache, cachedmodel, scope, multi-tenant, migration, wr-03, cr-01, cr-02]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "03-08: invalidación multi-fila + clave namespaced por scope() + re-sonda TOCTOU"
  - phase: 03-data-correctness
    provides: "03-09: compensación por identidad de fila (last_id) + IN-01/IN-02"
provides:
  - "docs/guide.md §10 alineado con la invalidación de TODAS las filas afectadas, el namespace de scope y el residual TOCTOU"
  - "docs/design/5-security.md §5.4 con el mecanismo real sha1(tabla:[pk=...]|scope=<huella>), resolución multi-fila scope-aware con include_deleted=True y fail-open"
  - "CHANGELOG.md [Unreleased]: cambio de comportamiento de la clave de caché (namespace de scope) + fixes CR-01 multi-fila y WR-01 residual/IN-01"
affects: [phase-08-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "documentación de seguridad que declara el aislamiento SOLO en los términos que el código cumple"
    - "residuales (TOCTOU, fallback Oracle) documentados explícitamente en vez de omitidos"

key-files:
  created: []
  modified:
    - docs/guide.md
    - docs/design/5-security.md
    - CHANGELOG.md

key-decisions:
  - "La guía y el diseño de seguridad describen la invalidación de TODAS las filas afectadas (no 'esa única entrada'), el namespace de scope en la clave y el residual TOCTOU."
  - "El aislamiento por tenant se afirma SOLO como namespace de scope en la clave; se advierte que sin scope() la entrada se comparte."
  - "El CHANGELOG registra el cambio de formato de clave bajo ### Cambiado y los fixes bajo ### Corregido, sin duplicar encabezados."

patterns-established:
  - "Cada cambio incompatible de 0.x queda registrado en CHANGELOG con nota de ownership aditiva (Fase 8 / 08-04)."

requirements-completed: [DATA-03, DATA-02]

# Metrics
duration: 6min
completed: 2026-09-18
---

# Phase 3 Plan 10: Alineación documental con la invalidación multi-fila y el scope Summary

**Guía, diseño de seguridad y CHANGELOG alineados con el comportamiento real entregado por 03-08/03-09: invalidación de TODAS las filas afectadas, clave namespaced por `scope()`, residual TOCTOU y compensación por identidad.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-18T20:46:00Z
- **Completed:** 2026-09-18T20:52:17Z
- **Tasks:** 2 (docs-only)
- **Files modified:** 3

## Accomplishments

- **WR-03 cerrado en `docs/guide.md` §10:** se eliminó la afirmación de "esa única entrada"/"la única entrada posible". La sección ahora describe que `update`/`delete`/`upsert` resuelven la PK de **TODAS las filas afectadas** (clave no-PK puede afectar a varias filas) y borran cada entrada; documenta el **aislamiento por `scope()`** (huella en la clave) y el **residual TOCTOU** sonda/escritura acotado por la re-resolución pero no eliminado. Se conservan la limitación multi-proceso y el contrato dev/test de `MemoryCacheBackend`.
- **WR-03 cerrado en `docs/design/5-security.md` §5.4:** se documenta el mecanismo REAL `sha1(tabla:[pk=...]|scope=<huella>)` (`<huella>` = `digest()` del filtro de scope), la resolución multi-fila con `SELECT` ligado, scope-aware e `include_deleted=True`, el borrado post-commit y el fail-open (warning, no propaga, obsolescencia acotada por TTL). Se mantiene que no se usa el hook post-commit de `_transactional`.
- **CHANGELOG.md:** nueva sección `### Cambiado` en `[Unreleased]` con el cambio de comportamiento del formato de clave (namespace de scope, CR-02) y nota de claves huérfanas hasta el TTL; dos entradas nuevas en `### Corregido` (invalidación multi-fila CR-01 y compensación por identidad de fila WR-01 residual/IN-01). Encabezados existentes reutilizados, sin duplicar `### Corregido`.
- **Solo documentación:** no se tocó código ni tests; los gates de la fase quedan verdes sin cambios de comportamiento.

## Task Commits

Each task was committed atomically:

1. **Task 1: Alinear guía y diseño de seguridad con la invalidación multi-fila y el namespace de scope** - `177df92` (docs)
2. **Task 2: Registrar en el CHANGELOG el cambio de comportamiento de la clave y los fixes** - `9f807f3` (docs)

**Plan metadata:** (commit de cierre, ver `docs(03-10): complete ...`)

## Files Created/Modified

- `docs/guide.md` - §10 "Caché (`CachedModel`)": sección de invalidación reescrita (TODAS las filas, aislamiento por `scope()`, TOCTOU residual, multi-proceso preservado); nota de la clave Redis actualizada con el sufijo `|scope=<huella>`.
- `docs/design/5-security.md` - §5.4 "Caché (opcional)": mecanismo real de la clave, resolución multi-fila scope-aware con `include_deleted=True`, fail-open y residual TOCTOU.
- `CHANGELOG.md` - `[Unreleased]`: `### Cambiado` (formato de clave) + 2 entradas en `### Corregido` (CR-01 multi-fila, WR-01 residual/IN-01).

## Decisions Made

- **Documentar el comportamiento REAL, no el deseado:** la guía y el diseño afirman el aislamiento por tenant solo como namespace de scope en la clave; se advierte que sin `scope()` la entrada se comparte entre tenants.
- **Residuales explícitos:** el TOCTOU sonda/escritura y el fallback Oracle (`last_id()==0`) quedan documentados como residuales con mitigación, no declarados imposibles.
- **CHANGELOG sin duplicar encabezados:** `### Cambiado` se inserta como sección nueva; los fixes se anexan a `### Corregido` existente.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Authentication Gates

None.

## Known Stubs

None. Cambios exclusivamente documentales; no se introdujeron valores vacíos, placeholders ni componentes sin fuente de datos.

## Threat Flags

None. El cambio alinea la documentación con el comportamiento real (mitiga T-03-10-01, Repudiation: sin afirmaciones de aislamiento no implementadas). No se instalaron paquetes (T-03-10-SC).

## Verification

- `uv run mkdocs build --strict` → exit 0, sin warnings de anclas (`Documentation built in 2.10 seconds`).
- `grep -c "scope" docs/guide.md` → 14; `grep -c "scope" docs/design/5-security.md` → 7.
- `grep -c "todas las filas\|TODAS las filas\|todas las entradas" docs/guide.md` → 1.
- `sed -n '/## \[Unreleased\]/,/## \[0.2.6\]/p' CHANGELOG.md | grep -ci "scope"` → 6; `... | grep -c "### Corregido"` → 1.
- `uv run pytest -q` → `841 passed` (10 snapshots).
- `uv run ruff check encino_orm tests` → exit 0.
- `uv run ruff format --check encino_orm tests` → `115 files already formatted`.
- `uv run mypy encino_orm` → `Success: no issues found in 60 source files`.

## Next Phase Readiness

- WR-03 cerrado: ninguna afirmación de "única entrada" ni de aislamiento de tenant sin soporte en el código.
- El cambio de formato de clave queda registrado en el CHANGELOG (requisito de PROJECT.md para 0.x).
- La Fase 8 (`08-04`) posee la enumeración completa de cambios incompatibles del milestone; estas entradas son aditivas.

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- FOUND: `docs/guide.md`
- FOUND: `docs/design/5-security.md`
- FOUND: `CHANGELOG.md`
- FOUND: `.planning/phases/03-data-correctness/03-10-SUMMARY.md`
- FOUND commits: `177df92`, `9f807f3`
