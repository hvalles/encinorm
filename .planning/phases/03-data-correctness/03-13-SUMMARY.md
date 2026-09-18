---
phase: 03-data-correctness
plan: 13
subsystem: docs
tags: [changelog, security, multi-tenant, scope, cache, upsert, oracle, last_id]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: 03-11 DML acotado por scope (`_scoped_dml` en `Model.update`/`delete`)
  - phase: 03-data-correctness
    provides: 03-12 invalidación post-escritura fail-open (`_invalidate_after_write`, huella `repr`)
provides:
  - CHANGELOG veraz: SEC-01 y WR-R3-02 registrados; overclaim "escritura cruzada cerrada" corregido
  - Guía y diseño de seguridad con el contrato de escritura bajo `scope()` y los residuales
  - Corrección de la nota `last_id()` (IN-R3-01) y de la promesa de huella estable (IN-R3-03)
affects: [03-data-correctness, 08-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Documentación veraz: describe el comportamiento real entregado por el código, no la intención
    - Residuales explícitos (upsert global, scope del escritor, filtros deterministas)

key-files:
  created: []
  modified:
    - CHANGELOG.md
    - docs/guide.md
    - docs/design/5-security.md

key-decisions:
  - "El overclaim de la ronda 3 se reformula: la caché namespaced por scope deja de ser un HABILITADOR de escritura cruzada; el cierre real de la escritura cruzada con clave no-PK es SEC-01 (03-11)"
  - "El bullet de la ronda 2 'esa única entrada' se supersede: la invalidación cubre TODAS las filas afectadas"
  - "El residual de upsert (claves de conflicto globales) se documenta como límite conocido en guía y diseño de seguridad"
  - "La nota de last_id() deja de nombrar a Oracle: el fallback cubre un last_id() que falle, no que un motor devuelva 0"
  - "No se añade mención de last_id() a los docs (no existía): la corrección IN-R3-01 es solo del CHANGELOG"

patterns-established:
  - "Una afirmación de aislamiento que el código no cumple induce configuraciones inseguras: los overclaims se corrigen contra el código entregado"

requirements-completed: [SEC-01, DATA-03, DATA-02]

# Metrics
duration: 3min
completed: 2026-09-18
---

# Phase 3 Plan 13: CHANGELOG y docs veraces (DML acotado por scope, residuales) Summary

**CHANGELOG, guía y diseño de seguridad alineados con el DML acotado por `scope()` de 03-11 y la invalidación fail-open de 03-12: se elimina el overclaim "escritura cruzada cerrada", se documenta que el escritor debe correr bajo el mismo `scope()` que el lector, y se registran los residuales de `upsert` y de huella determinista.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-09-18T21:21:01Z
- **Completed:** 2026-09-18T21:23:41Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- **WR-R3-03 cerrado:** la entrada de `### Cambiado` ya no afirma que la ronda 3 cerró "la escritura cruzada de tenant"; ahora dice que el acierto de caché **no habilita** una escritura cruzada y que el DML acotado por `scope()` (SEC-01, 03-11) es el cierre real. Se eliminó el bullet contradictorio "esa única entrada" de la ronda 2.
- **SEC-01 registrado en `### Corregido`:** `Model.update`/`delete` aplican el `scope()` activo al `WHERE` del DML con parámetros ligados; una clave no-PK ya no modifica/borra filas de otro tenant; sin `scope()` el DML es idéntico.
- **WR-R3-02 registrado:** la invalidación post-escritura de `CachedModel` es fail-open incluso con PK no hashable (`_union` con huella `repr` + `_invalidate_after_write`).
- **IN-R3-01 corregido:** la nota de `last_id()` deja de nombrar a Oracle como el motor del fallback; el fallback cubre un `last_id()` que **falle**.
- **WR-R3-04 documentado (guía + diseño):** la invalidación se namespacea con el `scope()` del **escritor**; una ruta administrativa sin `scope()` deja las entradas con scope obsoletas hasta el TTL; recomendación de mismo `scope()` o deshabilitar `CachedModel`/invalidar fuera de banda.
- **IN-R3-03 documentado:** la huella de scope es estable solo con filtros deterministas (`Filter.in_` con `set` varía el orden entre procesos).
- **Residual de `upsert` documentado:** sus claves de conflicto son globales; en multi-tenant la unicidad debe ser `(tenant, clave)`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Corregir el CHANGELOG (overclaim + bullet contradictorio)** — `abcd500` (docs)
2. **Task 2: Guía y diseño de seguridad (escrituras bajo scope + residuales)** — `b5c5b24` (docs)

**Plan metadata:** commit de cierre `docs(03-13): complete plan` (ver abajo)

## Files Created/Modified

- `CHANGELOG.md` — reescrita la entrada de formato de clave de caché; añadidos SEC-01 y WR-R3-02 a `### Corregido`; superseded el bullet "única entrada"; corregida la nota `last_id()`.
- `docs/guide.md` — §10: huella determinista, escritor/lector bajo el mismo `scope()`, residual de `upsert`; §12: DML acotado por `scope()` en `update`/`delete` y residual de `upsert`.
- `docs/design/5-security.md` — §5.4: residuales de scope del escritor, filtros deterministas y `upsert`; nuevo §5.5: alcance por fila (`scope()`) en el DML.

## Decisions Made

- El overclaim se reformula como "el acierto de caché ya no habilita una escritura cruzada" y se remite a SEC-01 para el cierre real.
- Se documentan los residuales como límites conocidos en lugar de prometer aislamiento total.
- IN-R3-01 es una corrección exclusiva del CHANGELOG: `docs/guide.md` y `docs/design/5-security.md` no mencionaban `last_id()`, así que no se añadió una mención nueva.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Reflow del literal `ORA-00904` en el CHANGELOG**
- **Found during:** Task 1 (verificación de acceptance criteria)
- **Issue:** El criterio `sed ... | grep -ci "Oracle.*0\|devuelve 0"` devolvía 1 (no 0) por un falso positivo en la entrada del CR-02 (merge): la línea "(antes: MSSQL 207 `Invalid column name` / Oracle `ORA-00904`)" contiene "Oracle" y el `0` de `ORA-00904` en la misma línea.
- **Fix:** Reflow mínimo del texto a "(`Invalid column name` de MSSQL / `ORA-00904` de Oracle)"; el contenido no cambia.
- **Files modified:** CHANGELOG.md
- **Verification:** `sed ... | grep -ci "Oracle.*0\|devuelve 0"` → 0.
- **Committed in:** `abcd500` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Cambio cosmético y sin efecto semántico, necesario para satisfacer el criterio de aceptación literal. Sin scope creep.

## Issues Encountered

None. Los gates de fin de plan salieron verdes a la primera.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ronda 4 de gap-closure cerrada en docs: WR-R3-03, WR-R3-04, IN-R3-01 e IN-R3-03.
- Pendiente el commit de metadatos del plan (SUMMARY/STATE/ROADMAP) y el tick de `03-13` en `ROADMAP.md`.
- Sin blockers nuevos.

## Self-Check: PASSED

- FOUND: CHANGELOG.md
- FOUND: docs/guide.md
- FOUND: docs/design/5-security.md
- FOUND: `.planning/phases/03-data-correctness/03-13-SUMMARY.md`
- FOUND: abcd500 (Task 1)
- FOUND: b5c5b24 (Task 2)

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*
