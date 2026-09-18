---
phase: 03-data-correctness
plan: 09
status: complete
gap_closure: true
subsystem: database
tags: [migrations, ledger, transaction, oracle, mysql, wr-01, in-01, in-02]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "runner de dos fases (03-01/03-02) y compare-and-delete por propiedad+estado (03-07)"
provides:
  - "compensación pre-DDL por IDENTIDAD de fila ({id: ledger_id}) cuando el motor expone last_id() útil"
  - "fallback documentado {name, status: pending} para Oracle (last_id()==0), residual de Fase 4 / POOL-03"
  - "compensación que no enmascara la excepción raíz del DDL (IN-01)"
  - "test de IN-02 por comportamiento, sin aserción sobre __doc__"
affects: [03-10, phase-04-pool, POOL-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "borrado de compensación por identidad de fila (lastrowid) en vez de por compare-and-delete de estado"
    - "captura best-effort de last_id() que degrada a fallback sin romper el runner"

key-files:
  created: []
  modified:
    - encino_orm/migration.py
    - tests/test_migration_reconcile.py

key-decisions:
  - "La compensación borra por {id: ledger_id} cuando last_id() > 0; {name, status} no prueba propiedad y borraría la fila que otro runner re-publicó tras el rollback."
  - "Oracle (last_id()==0) mantiene el fallback {name, status: pending} como residual estrecho, asignado a Fase 4 / POOL-03."
  - "La compensación va en su propio try/except con logger.warning; el raise exterior re-lanza SIEMPRE la excepción raíz del DDL (IN-01)."

patterns-established:
  - "Identidad sobre estado: un compare-and-delete por columnas de negocio no prueba propiedad; la PK de la fila insertada sí."
  - "Best-effort degradable: last_id() se captura en try/except y 0 activa el camino seguro sin abortar el runner."

requirements-completed: [DATA-02]

# Metrics
duration: 8min
completed: 2026-09-18
---

# Phase 3 Plan 09: Compensación por identidad y error raíz Summary

**La compensación pre-DDL del runner borra por identidad de fila (`{id: ledger_id}`, capturada con `last_id()`) en vez de por `{name, status}`, y un fallo de compensación ya no enmascara la excepción raíz del DDL.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-18T20:40:00Z
- **Completed:** 2026-09-18T20:48:15Z
- **Tasks:** 3 (2 TDD: RED + GREEN; 1 test hardening)
- **Files modified:** 2

## Accomplishments

- **WR-01 residual cerrado** para motores con `last_id()` útil (MySQL/MariaDB): `_apply` captura best-effort `db.last_id()` justo tras el INSERT y compensa con `db.delete(MIGRATIONS_TABLE, {"id": ledger_id})`. El interleaving rollback+reinserción (A hace rollback de su fila, B re-publica `pending`) ya no borra la fila de B.
- **Fallback documentado** para Oracle (`last_id()` devuelve 0): se conserva el compare-and-delete `{name, status: pending}` y la limitación queda registrada como residual estrecho de la Fase 4 / POOL-03 (captura real de `last_id` dentro del INSERT). Sin ramas específicas de motor ni `RETURNING`.
- **IN-01 cerrado:** el cuerpo de la compensación va en su propio `try/except Exception` con `logger.warning`; el `raise` desnudo exterior re-lanza la excepción ORIGINAL del DDL. Un fallo de compensación ya no reemplaza el error raíz.
- **IN-02 fortalecido:** eliminada la aserción sobre `resolve_migration.__doc__`; la cobertura del efecto (`rolling_back` + `applied=True` → `applied`, y la fila deja de ser ambigua para `reconcile_migrations`) es ahora de comportamiento. Se conserva la comprobación del texto de error de `reconcile_migrations` (load-bearing para el operador).
- **D-08/D-17 preservados:** el DDL que corre y falla el promote deja la fila `pending` A PROPÓSITO (rama `ddl_done` sin cambios).

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresiones RED de WR-01 residual e IN-01** - `1f22ce1` (test)
2. **Task 2: Compensación por identidad + no enmascarar el error raíz (GREEN)** - `081a1b5` (fix)
3. **Task 3: Fortalecer el test de IN-02 (comportamiento, no substring)** - `491bcc5` (test)

## Files Created/Modified

- `encino_orm/migration.py` - `_apply`: captura best-effort de `last_id()`, compensación por `{id: ledger_id}` con fallback, try/except con warning que no enmascara el error raíz; docstring actualizado.
- `tests/test_migration_reconcile.py` - `LedgerDb` extendido (`id` autoincremental, `last_id()` con flag `last_id_available`, `delete` fiel por `{id}`/`{name,...}`, `fail_compensation`); `ReinsertionLedgerDb`; regresiones `test_wr01_*`/`test_in01_*` + test de fallback; retirada la aserción de docstring de IN-02.

## Decisions Made

- **Identidad sobre estado:** `{name, status}` no prueba PROPIEDAD de la fila; la PK capturada tras el INSERT sí. Se prefiere `{id: ledger_id}` cuando `last_id() > 0`.
- **Oracle = fallback:** `last_id()==0` activa el compare-and-delete documentado; el residual queda con dueño explícito (Fase 4 / POOL-03), sin introducir un `RETURNING` específico de motor.
- **IN-01:** la compensación nunca sustituye la excepción raíz; se registra warning y se re-lanza el original.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Actualización de la aserción del test existente de 03-07**
- **Found during:** Task 2 (GREEN)
- **Issue:** `test_compensacion_borra_solo_la_fila_pending_propia` (03-07) asertaba `delete_calls == [{"name": "v1", "status": STATUS_PENDING}]`. Con `LedgerDb.last_id()` devolviendo un id positivo, la compensación ahora emite `{"id": 1}`, así que la aserción quedaba obsoleta y el fichero no podía quedar verde.
- **Fix:** se actualizó la aserción a `[{"id": 1}]` y el docstring del test a "borra por identidad la fila que ESTA llamada insertó". No se borró ni renombró el test; la cobertura del fallback se añadió por separado (`test_compensacion_sin_last_id_usa_compare_and_delete`, con `last_id_available=False`).
- **Files modified:** `tests/test_migration_reconcile.py`
- **Verification:** `uv run pytest tests/test_migration_reconcile.py tests/test_migrations.py -q` → 37 passed.
- **Committed in:** `081a1b5` (Task 2 commit)

**2. [Rule 3 - Blocking] Ajuste de la firma del fake para mantener `def last_id` único**
- **Found during:** Task 1 (RED)
- **Issue:** la primera aproximación modelaba el motor sin `last_id` útil con una subclase `NoLastIdLedgerDb` que redefinía `last_id`, rompiendo el criterio de aceptación `grep -c "def last_id" == 1`.
- **Fix:** se sustituyó por un flag `last_id_available: bool = True` en `LedgerDb`, manteniendo una sola definición de `last_id`.
- **Files modified:** `tests/test_migration_reconcile.py`
- **Verification:** `grep -c "def last_id" tests/test_migration_reconcile.py` → 1.
- **Committed in:** `1f22ce1` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Ambos cambios son mecánicos y necesarios para que los criterios de aceptación y el fichero de tests queden verdes; no hay scope creep ni cambios de comportamiento no previstos.

## Issues Encountered

- El formateador de ruff colapsó el `db.delete(MIGRATIONS_TABLE, {"name": name, "status": STATUS_PENDING})` del fallback en una sola línea; se aplicó `ruff format` antes del commit de Task 2. Sin impacto funcional.

## Authentication Gates

None.

## Known Stubs

None. No se introdujeron valores vacíos, placeholders ni componentes sin fuente de datos.

## Threat Flags

None. Los cambios endurecen la frontera runner→ledger (T-03-09-01) y backend→runner (T-03-09-03); no añaden superficie nueva (T-03-09-02 mitigado). No se instalaron paquetes (T-03-09-SC).

## TDD Gate Compliance

- RED: `test(03-09): añade regresiones RED de WR-01 residual e IN-01` (`1f22ce1`) — capturado `2 failed, 16 deselected` (exit 1).
- GREEN: `fix(03-09): compensa por identidad de fila y no enmascara el error raíz` (`081a1b5`) — `2 passed`, fichero completo `37 passed`.
- Secuencia RED→GREEN verificada en `git log`.

## Verification

- `uv run pytest tests/test_migration_reconcile.py -k "wr01_ or in01_" -q`: RED `2 failed` → GREEN `2 passed`.
- `uv run pytest tests/test_migration_reconcile.py tests/test_migrations.py -q`: `37 passed`.
- `uv run pytest -q`: `841 passed` (10 snapshots).
- `uv run ruff check encino_orm tests`: exit 0.
- `uv run ruff format --check encino_orm tests`: `115 files already formatted`.
- `uv run mypy encino_orm`: `Success: no issues found in 60 source files`.
- `grep -c "db.commit()" encino_orm/migration.py` → 0.
- `grep -c "last_id"` → 6; `grep -c '{"id": ledger_id}'` → 1; `grep -c "STATUS_PENDING"` → 5; `grep -c "logger.warning"` → 3.
- `grep -c "__doc__" tests/test_migration_reconcile.py` → 0.

## Next Phase Readiness

- El residual WR-01 queda cerrado para MySQL/MariaDB; Oracle conserva un residual estrecho con dueño (Fase 4 / POOL-03). La Fase 4 debe capturar el `id` real del INSERT del ledger (p. ej. `OUTPUT INSERTED.id` en SQL Server / `RETURNING id INTO` en Oracle) para eliminar el fallback.
- `03-10` (docs/CHANGELOG) puede describir el borrado por identidad y su fallback Oracle.
- DATA-02 sigue cubierto por must-haves verificables; el runner usa exclusivamente `async with db.transaction()`.

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- FOUND: `encino_orm/migration.py`
- FOUND: `tests/test_migration_reconcile.py`
- FOUND: `.planning/phases/03-data-correctness/03-09-SUMMARY.md`
- FOUND commits: `1f22ce1`, `081a1b5`, `491bcc5`, `e156a51`
