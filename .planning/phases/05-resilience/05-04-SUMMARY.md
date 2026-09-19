---
phase: 05-resilience
plan: 04
subsystem: database
tags: [error-taxonomy, exception-translation, reconnect, mypy-ratchet, docs]

# Dependency graph
requires:
  - phase: 05-resilience
    provides: "05-01 is_disconnect_error por motor; 05-02 _with_reconnect/_reconnect y wrappers públicos; 05-03 pre_ping/max_connection_lifetime"
provides:
  - "Taxonomía pública aditiva: ConnectionLostError(ConnectionError), OperationalError/IntegrityError/ProgrammingError(QueryError)"
  - "Punto único de traducción Db._translate_exception con cortocircuito de lock + hook por adaptador _translate_error"
  - "_with_reconnect relanza SIEMPRE traducido y preserva la causa del driver con raise ... from exc"
  - "SqliteDb._reconnect de :memory: lanza ConnectionLostError"
  - "docs/engines.md y CHANGELOG.md documentan el contrato nuevo y el cambio de comportamiento"
  - "Ratchet de mypy reducido: retiradas base/oracle/mysql/mssql (pool intacto)"
affects: [06-config, 07-performance, 08-milestone-docs]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Traducción centralizada driver → librería (un punto, hooks por adaptador)"
    - "Clasificación sobre la excepción ORIGINAL antes de traducir (lock intocable)"
    - "Chaining deliberado raise ... from exc para preservar __cause__ (ASVS V7)"

key-files:
  created: []
  modified:
    - encino_orm/exceptions.py
    - encino_orm/__init__.py
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - tests/_resilience_helpers.py
    - tests/test_resilience.py
    - tests/test_base.py
    - tests/test_index.py
    - pyproject.toml
    - docs/engines.md
    - CHANGELOG.md

key-decisions:
  - "El cortocircuito de lock va PRIMERO en _translate_exception: devuelve el original sin traducir para que retry() siga reconociéndolo"
  - "El chaining raise ... from exc se adopta como desviación deliberada de la convención del repo (ASVS V7) y se documenta"
  - "El residual de mypy de oracle (out Any|None) se corrige con guard `out is not None`, sin # type: ignore"
  - "La aserción de tests/test_index.py pasa a esperar IntegrityError de la librería (cambio de comportamiento RESL-04)"

patterns-established:
  - "Hook _translate_error por adaptador junto al bloque # --- errores ---, reutilizando is_unique_violation/_native_code/_ora_code"
  - "Traducción idempotente: un EncinoOrmError no se re-traduce"

requirements-completed: [RESL-04]

# Metrics
duration: 7min
completed: 2026-09-19
---

# Phase 5 Plan 4: Taxonomía pública de errores y traducción driver → librería

**Traducción centralizada de excepciones de driver a la taxonomía pública (ConnectionLostError/OperationalError/IntegrityError/ProgrammingError) con cortocircuito de lock, causa preservada por chaining, docs/CHANGELOG y ratchet de mypy reducido**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-19T05:19:37Z
- **Completed:** 2026-09-19T05:26:50Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments
- Taxonomía aditiva publicada en `exceptions.py` y exportada por el barrel (`ConnectionLostError` hereda de `ConnectionError`; los tres `QueryError`-derived).
- `Db._translate_exception` es el punto ÚNICO de traducción: lock → original sin traducir; `EncinoOrmError` → tal cual; disconnect → `ConnectionLostError`; resto → hook del adaptador.
- Los cinco adaptadores implementan `_translate_error` con los códigos reales de su driver (SQLite/MySQL/MariaDB/PostgreSQL/MSSQL/Oracle), reutilizando `is_unique_violation`/`_native_code`/`_ora_code`.
- `_with_reconnect` relanza traducido con `raise ... from exc`/`from exc2`/`from rexc` y traduce también el fallo de `_reconnect()`.
- `SqliteDb._reconnect` de `:memory:` lanza `ConnectionLostError` (subclase de `ConnectionError`).
- `docs/engines.md` + `CHANGELOG.md` documentan taxonomía, chaining, `pre_ping`/lifetime y `:memory:`; ratchet retira `base`/`oracle`/`mysql`/`mssql` (`pool` intacto).

## Task Commits

Each task was committed atomically:

1. **Task 1: Taxonomía + barrel + `_translate_exception`/`_translate_error` + chaining** - `500ca29` (feat)
2. **Task 2: Bloque RESL-04 en tests + jerarquía en test_base** - `f939c96` (test)
3. **Task 3: Docs + CHANGELOG + ratchet de mypy + gates** - `7bad4d4` (docs)

**Plan metadata:** (final commit below)

## Files Created/Modified
- `encino_orm/exceptions.py` - Cuatro clases nuevas con jerarquía aditiva.
- `encino_orm/__init__.py` - Barrel + `__all__` con los cuatro nombres.
- `encino_orm/base.py` - `_translate_exception`/`_translate_error`, chaining en `_with_reconnect`, tipado de `last_exc`.
- `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` - Hook `_translate_error` por driver; SQLite `:memory:` → `ConnectionLostError`.
- `encino_orm/mysql.py` - `is_lock_error` reescrito con guard de `args` (residual de tipado).
- `encino_orm/oracle.py` - Guard `out is not None` (residual de tipado) y `_translate_error`.
- `tests/_resilience_helpers.py` - Builders de integridad/programación/operacional por motor y `FakeReconnectFalla`.
- `tests/test_resilience.py` - Bloque `-k translate` (42 casos) y ajuste de 3 tests RESL-02 al tipo traducido.
- `tests/test_base.py` - Jerarquía nueva y compatibilidad de `except`.
- `tests/test_index.py` - El UNIQUE de SQLite ahora aflora como `IntegrityError` de la librería.
- `docs/engines.md` - `is_disconnect_error`, taxonomía, chaining, `pre_ping`/lifetime, `:memory:`.
- `CHANGELOG.md` - Entradas de cambio de comportamiento en `[Unreleased]` (sin duplicar encabezados).
- `pyproject.toml` - Ratchet de mypy reducido en 4 entradas.

## Decisions Made
- **Cortocircuito de lock primero:** garantiza que `retry()` siga viendo el tipo/args originales del driver (T-05-04-01).
- **Chaining deliberado:** `raise ... from exc` en los tres relanzados + el fallo de reconexión, documentado como excepción consciente a la convención (ASVS V7 / T-05-04-05).
- **Traducción idempotente:** una excepción ya `EncinoOrmError` se devuelve tal cual (evita dobles traducciones).
- **HTTP:** al heredar de `QueryError`, `OperationalError`/`IntegrityError`/`ProgrammingError` se mapean a 400 (antes 500); `ConnectionLostError` sigue 500. Registrado en CHANGELOG y docs (A3 / T-05-04-04).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] El import único de `.exceptions` en `base.py` no pasa el isort de ruff**
- **Found during:** Task 1 (`base.py`)
- **Issue:** El plan pedía extender una sola línea `from .exceptions import ...` con el alias; ruff/isort (`combine-as-imports=false`) exige separar el import aliaseado en su propia sentencia y el gate `ruff check` es de aceptación.
- **Fix:** Dos sentencias: `from .exceptions import ConnectionError as OrmConnectionError` + `from .exceptions import (ConnectionLostError, EncinoOrmError, OperationalError)`. Se conserva el alias (no se sombrea el builtin).
- **Files modified:** `encino_orm/base.py`
- **Verification:** `uv run ruff check encino_orm` → 0.
- **Committed in:** `500ca29`

**2. [Rule 1 - Bug] `tests/test_index.py::test_unique_index_enforced` afirmaba el tipo del driver**
- **Found during:** Task 2 (suite `-m "not integration and not optional_engine"`)
- **Issue:** El test esperaba `sqlite3.IntegrityError`; con la traducción (RESL-04) el UNIQUE aflora como `encino_orm.IntegrityError` (cambio de comportamiento intencional).
- **Fix:** Se actualiza la aserción a `encino_orm.exceptions.IntegrityError` y se retira el import `sqlite3` (quedaba sin uso).
- **Files modified:** `tests/test_index.py`
- **Verification:** Suite completa verde (1018 passed).
- **Committed in:** `f939c96`

**3. [Rule 1 - Bug] Residual de tipado de `oracle.py` al retirar el ratchet**
- **Found during:** Task 3 (medición de `uv run mypy encino_orm` sin las entradas)
- **Issue:** `oracle.py` (2 errores `union-attr`: `out.getvalue()` con `out: Any | None`). `base`/`mysql`/`mssql` quedaron limpios tras los arreglos de Task 1.
- **Fix:** `if returning and out is not None:` en `_execute` y `_execute_insert` (sin `# type: ignore`, sin `assert`).
- **Files modified:** `encino_orm/oracle.py`
- **Verification:** `uv run mypy encino_orm` → 0 issues en 60 ficheros.
- **Committed in:** `7bad4d4`

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 3)
**Impact on plan:** Todas necesarias para los gates de aceptación (ruff/mypy/suite). Sin scope creep funcional. `tests/test_index.py` no estaba en `files_modified` pero el fallo lo causaba directamente el cambio de RESL-04.

## TDD Gate Compliance

Task 1 lleva `tdd="true"`, pero su `<files>` NO incluye tests (el bloque de tests es Task 2). No hubo commit RED separado: la evidencia RED es que los 3 tests RESL-02 existentes (`test_escritura_mid_statement_*`, `test_desconexion_dentro_de_tx_*`, `test_fallo_persistente_*`) fallaron contra el `feat` de Task 1 por el tipo traducido, y se pusieron verdes en Task 2. Gates: `feat(...)` presente (`500ca29`), `test(...)` presente (`f939c96`); no se requirió `refactor`.

## Issues Encountered
- Ninguno bloqueante. La suite completa (1018 tests) tarda ~37 s en local con los seis motores arriba.

## Gates (cierre de fase)

| Gate | Resultado |
|------|-----------|
| `uv run pytest -q` | 1018 passed |
| `uv run pytest -q -m "not integration and not optional_engine"` | 930 passed, 88 deselected |
| `uv run pytest tests/test_resilience.py -q -k translate` | 42 passed |
| `uv run ruff check encino_orm tests` | 0 |
| `uv run ruff format --check encino_orm tests` | 119 files already formatted |
| `uv run mypy encino_orm` | Success: no issues found in 60 source files |
| `uv lock --check` | Resolved 98 packages (sin cambios de lock) |
| `uv run mkdocs build --strict` | Documentación construida |
| `grep -c "type: ignore" encino_orm/` | 0 |
| `git diff --stat encino_orm/pool.py` (Fase 5) | vacío (intacto) |

**Diff del ratchet (`pyproject.toml`):** se retiraron `encino_orm.base` (1 error), `encino_orm.oracle` (2), `encino_orm.mysql` (1) y `encino_orm.mssql` (1); `encino_orm.pool` (5 errores, residual de Fase 4) NO se tocó. La cola medida pasa de 14 a 9 errores en 5 módulos.

## Known Stubs
None — no se introdujeron valores vacíos/placeholder ni componentes sin fuente de datos.

## Threat Flags
None — la superficie introducida (traducción de excepciones) está cubierta por el `<threat_model>` del plan (T-05-04-01…07).

## Next Phase Readiness
- RESL-04 cerrado: el usuario recibe excepciones de la librería, no del driver, sin romper `retry()` ni el pool.
- Fase 5 completa (4/4 planes); lista para `/gsd-verify-work`.
- Residuales fuera de alcance: `encino_orm.pool` sigue en el ratchet (5 errores de tipado, Fase 4); enumeración completa de breaking changes es de Fase 8 (`08-04`).

---
*Phase: 05-resilience*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `.planning/phases/05-resilience/05-04-SUMMARY.md`
- FOUND: `encino_orm/exceptions.py`, `encino_orm/base.py`, `encino_orm/oracle.py`, `tests/test_resilience.py`, `docs/engines.md`, `CHANGELOG.md`, `pyproject.toml`
- FOUND commits: `500ca29`, `f939c96`, `7bad4d4`
