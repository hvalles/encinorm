---
phase: 03-data-correctness
plan: 11
status: complete
gap_closure: true
subsystem: database
tags: [scope, multi-tenant, security, cr-r3-01, sec-01, dml, update, delete, sqlite]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "03-08: clave de caché namespaced por scope() + invalidación multi-fila"
  - phase: 03-data-correctness
    provides: "03-10: documentación de la invalidación multi-fila y el scope (base del overclaim corregido en 03-13)"
provides:
  - "helper _scoped_dml en encino_orm/model/model.py: compone el Query del builder con el fragmento del scope() ligado (params reindexados)"
  - "Model.update y Model.delete (físico y lógico) acotan el WHERE al scope() activo; sin scope el Query es byte-idéntico"
  - "regresión tests/test_scope_softdelete.py::TestScope::test_cr_r3_01_* con clave de escritura no-PK (grupo)"
affects: [phase-08-release, 03-12, 03-13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "el scope() es filtro de visibilidad también en ESCRITURA: el DML compone el predicado de alcance en la capa Model, no en los builders"
    - "composición de Query por concatenación de plantilla + reindexado de placeholders + params ligados (sin interpolar valores)"
    - "el scope se lee dentro del closure transaccional (ambient, sobrevive a los reintentos de _transactional)"

key-files:
  created: []
  modified:
    - encino_orm/model/model.py
    - tests/test_scope_softdelete.py

key-decisions:
  - "El acotado por scope se hace en la capa Model sobre el Query que devuelve el builder; NO se tocan encino_orm/dialects/builders.py ni los seis adaptadores (snapshots intactos)."
  - "Sin scope() no se envuelve el Query: el camino sin scope queda byte-idéntico (compatibilidad y sin churn de snapshots)."
  - "current_scope() se lee dentro de do_update/do_delete (no capturado fuera) porque _transactional puede reintentar y el scope es ambient."

patterns-established:
  - "Predicado de visibilidad aplicado a DML: WHERE <claves del builder> AND (<scope mapeado>), con placeholders reindexados vía _shift_placeholders y valores siempre ligados."

requirements-completed: [SEC-01]

# Metrics
duration: 4min
completed: 2026-09-18
---

# Phase 3 Plan 11: DML acotado por `scope()` en `Model.update`/`delete` Summary

**El WHERE del `UPDATE`/`DELETE` emitido por `Model.update`/`delete` incorpora el `scope()` activo (params ligados) en la capa `Model`, cerrando la escritura cruzada entre tenants con claves no-PK (CR-R3-01/SEC-01) sin alterar el camino sin scope ni los builders.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-18T21:09:00Z
- **Completed:** 2026-09-18T21:13:37Z
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 2

## Accomplishments

- **CR-R3-01 cerrado:** `Model.update`/`delete` ya no se limitan al pre-chequeo `load()`; el DML lleva el predicado de alcance. Con `update(keys=["grupo"])`/`delete(keys=["grupo"])` bajo `scope(tenant=1)`, el tenant 2 queda intacto (verificado sobre `SqliteDb` real).
- **Helper `_scoped_dml`:** mapea el `scope()` a columnas físicas (`map_fields(self._column_map())`), reindexa los placeholders con `_shift_placeholders(frag, len(qry.fields))` y compone una `Query` nueva con `sql_template + " AND (<frag>)"` y `fields + params` del scope; el contrato de cardinalidad de `Query` revalida la composición.
- **Sin scope, byte-idéntico:** cuando `current_scope() is None` el `Query` del builder no se envuelve; el control `test_cr_r3_01_sin_scope_sigue_sin_acotar` documenta que el acotado solo aplica con scope activo.
- **WR-R3-01 resuelto por construcción:** al acotar la escritura, la sonda `_resolve_pk_values` de `CachedModel` y la escritura ven el mismo conjunto de filas.
- **Sin tocar builders ni adaptadores:** la composición es de la capa `Model`; los 10 snapshots de dialecto permanecen intactos.

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresión RED de escritura cruzada con clave no-PK** - `a722648` (test)
2. **Task 2: DML acotado por scope en `Model.update`/`delete` (GREEN)** - `b893f76` (fix)

**Plan metadata:** commit de cierre `docs(03-11): complete plan` (ver abajo)

_Note: TDD con dos commits: `test(...)` (RED) → `fix(...)` (GREEN). No hubo fase REFACTOR._

## Files Created/Modified

- `tests/test_scope_softdelete.py` - `Doc` gana `grupo: str | None = None` (clave de escritura no-PK no única) y 3 regresiones `test_cr_r3_01_*`: update sin cruzar tenant, delete lógico sin cruzar tenant y control sin scope.
- `encino_orm/model/model.py` - helper módulo-level `_scoped_dml` (junto a `_shift_placeholders`); `do_update` y ambas ramas de `do_delete` (física y lógica) leen `current_scope()` dentro del closure y acotan el `Query` solo cuando hay scope.

## Decisions Made

- **Acotado en la capa `Model`, no en los builders:** evita tocar `encino_orm/dialects/builders.py` y los seis adaptadores, manteniendo los snapshots de dialecto sin cambios (T-03-11-03).
- **Sin scope = sin envolver:** el `Query` sin scope es exactamente el del builder (mismo `sql_template`, `fields` e `ignore_duplicated`), preservando compatibilidad.
- **`current_scope()` dentro del closure:** `_transactional` puede reintentar; capturar el scope fuera rompería la semántica ambient en un reintento.
- **Ambas ramas de `do_delete` aplican `_scoped_dml` de forma explícita:** el predicado de alcance acompaña tanto al `DELETE` físico como al `UPDATE enabled=False` lógico.

## Deviations from Plan

None - plan executed exactly as written.

_(Único ajuste de forma respecto al snippet del plan: el `return Query(...)` de `_scoped_dml` se envuelve en varias líneas para respetar `line-length = 100` de ruff. Sin cambio funcional.)_

## Issues Encountered

- `ruff check` marcó `E501` en el `return Query(...)` del helper (101 > 100). Resuelto envolviendo la llamada en varias líneas antes del commit GREEN; sin cambio de comportamiento.

## Authentication Gates

None.

## Known Stubs

None. No se introdujeron valores vacíos, placeholders ni componentes sin fuente de datos.

## Threat Flags

None. El cambio **reduce** superficie de amenaza (T-03-11-01 Elevation of Privilege, mitigado): el WHERE del DML incluye el fragmento de `current_scope()` ligado. No se añadieron endpoints, rutas de auth ni patrones de acceso a ficheros nuevos. No se instalaron paquetes (T-03-11-SC).

## TDD Gate Compliance

- RED: `a722648` `test(03-11): añade regresión RED de escritura cruzada con clave no-PK` — 2 fallos (`update` cruzó tenant, `delete` deshabilitó la fila del tenant 2) y 1 control verde, exit 1.
- GREEN: `b893f76` `fix(03-11): acota el DML de update/delete al scope activo (CR-R3-01)` — 34 passed (`test_scope_softdelete.py` + `test_cached_model.py`).
- REFACTOR: no aplicó.

## Verification

- **RED (Task 1):** `uv run pytest tests/test_scope_softdelete.py -k cr_r3_01 -q` → `2 failed, 1 passed, 11 deselected`, exit 1.
  - `test_cr_r3_01_update_no_cruza_tenant`: `assert 'PWNED' == 'B1'` → FALLA (el tenant 2 fue modificado).
  - `test_cr_r3_01_delete_no_cruza_tenant`: `assert False is True` → FALLA (el tenant 2 quedó `enabled=False`).
  - `test_cr_r3_01_sin_scope_sigue_sin_acotar`: PASA (control).
- **GREEN (Task 2):** `uv run pytest tests/test_scope_softdelete.py tests/test_cached_model.py -q` → `34 passed`, exit 0.
- **Acceptance:**
  - `grep -c "def test_cr_r3_01_" tests/test_scope_softdelete.py` → 3.
  - `grep -c "grupo" tests/test_scope_softdelete.py` → 10 (>= 1).
  - `grep -c "_scoped_dml" encino_orm/model/model.py` → 4 (definición + 3 usos).
  - `grep -c "current_scope()" encino_orm/model/model.py` → 6 (>= 3).
- **Gates de fin de plan:**
  - `uv run pytest -q` → `844 passed` (10 snapshots passed), exit 0 (baseline ronda 3: 841 passed → +3 tests).
  - `uv run ruff check encino_orm tests` → `All checks passed!`, exit 0.
  - `uv run ruff format --check encino_orm tests` → `115 files already formatted`, exit 0.
  - `uv run mypy encino_orm` → `Success: no issues found in 60 source files`, exit 0.
  - No se ejecutó `pytest -m integration`.

## Next Phase Readiness

- CR-R3-01/SEC-01 cerrado; WR-R3-01 queda resuelto por construcción (sonda y escritura comparten el mismo conjunto de filas).
- `03-12` (`_union` fail-open) puede proceder sobre `cached.py` sin solapar ficheros con este plan.
- `03-13` (docs/CHANGELOG) puede documentar el DML acotado entregado aquí; el overclaim "escritura cruzada cerrada" ya es cierto a nivel de DML.

---
*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- FOUND: `encino_orm/model/model.py`
- FOUND: `tests/test_scope_softdelete.py`
- FOUND: `.planning/phases/03-data-correctness/03-11-SUMMARY.md`
- FOUND commits: `a722648`, `b893f76`
