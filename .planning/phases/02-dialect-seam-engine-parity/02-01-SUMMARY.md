---
phase: 02-dialect-seam-engine-parity
plan: 01
subsystem: database
tags: [orm, sql, security, refactor, identifier-allowlist, dialects]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "gates de ruff/mypy/pytest y el baseline de 553 tests que prueban el refactor puro"
provides:
  - "Allowlist estricto de identificadores en un único módulo: encino_orm/dialects/identifiers.py"
  - "Barrel encino_orm/dialects/__init__.py que re-exporta IDENTIFIER_RE y check_identifier"
  - "Guard de fuente que impide reintroducir una copia del allowlist (tests/test_identifiers.py)"
  - "Db._check_identifier delegado, preservando los 10 puntos de llamada self._check_identifier de los adaptadores"
affects: [02-02, 02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Allowlist de identificadores centralizada: un único check_identifier antes de interpolar SQL"
    - "Guard de definición única a nivel de fuente (rglob sobre encino_orm/*.py)"
    - "TDD de movimiento puro: test RED (tabla accept/reject) → implementación verbatim → suite intacta como oráculo"

key-files:
  created:
    - encino_orm/dialects/identifiers.py
    - encino_orm/dialects/__init__.py
    - tests/test_identifiers.py
  modified:
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/model/model.py
    - encino_orm/model/types.py
    - encino_orm/transfer.py
    - encino_orm/sql.py
    - encino_orm/model/query_builder.py

key-decisions:
  - "La allowlist NO se relaja para aceptar nombres cualificados: el caso schema.tabla se resolverá con un parámetro schema= validado por separado en 02-02 (Pitfall 10)"
  - "sql.py:_COLUMN_RE y model/query_builder.py:_COLUMN_RE se conservan sin unificar (aceptan puntos a propósito); se documenta el por qué con un comentario"
  - "El anclaje $ del allowlist acepta un salto final ('tabla\\n'); se conserva tal cual por ser refactor puro y se caracteriza en un test"

patterns-established:
  - "Un único cuello de botella de validación de identificadores antes de añadir validación nueva (bisecabilidad)"
  - "Guard de fuente como control anti-podredumbre de una definición única"

requirements-completed: [DIAL-01]

# Metrics
duration: 4min
completed: 2026-09-18
---

# Phase 2 Plan 01: Dialect Seam & Identifier Allowlist Centralization Summary

**Allowlist estricto de identificadores centralizado en `dialects/identifiers.py` e importado por los 6 módulos que lo duplicaban; refactor puro con 553 tests existentes intactos y un guard de fuente que hace imposible reintroducir una copia.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-18T04:11:44Z
- **Completed:** 2026-09-18T04:15:47Z
- **Tasks:** 3 (2 con cambios, 1 de verificación pura)
- **Files modified:** 11 (3 creados, 8 modificados)

## Accomplishments

- **DIAL-01 cumplido:** existe exactamente UNA definición del allowlist (`encino_orm/dialects/identifiers.py`), con `IDENTIFIER_RE` + `check_identifier` copiados verbatim de `Db._check_identifier`.
- Los **6 importadores** (`base.py`, `sqlite.py`, `mysql.py`, `model/model.py`, `model/types.py`, `transfer.py`) usan la definición compartida; la copia local de regex + checker de `transfer.py` se eliminó.
- `sql.py` y `model/query_builder.py` conservan su `_COLUMN_RE` (allowlist distinta que acepta puntos a propósito) con un comentario que explica por qué no se unifica.
- **Prueba de refactor puro:** la suite pasó de 553 a 571 tests (18 nuevos) sin editar un solo test preexistente y sin cambiar ninguna aserción de SQL.
- Guard de fuente: un test exige que exactamente un fichero bajo `encino_orm/` contenga el allowlist literal.
- Gates de Fase 1 intactos: `ruff check`, `ruff format --check` y `mypy encino_orm` salen 0; `noqa`/`nosec` siguen en 0.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): tabla accept/reject del allowlist** - `aa68fd1` (test)
2. **Task 1 (corrección de expectativa): caracterizar el anclaje `$`** - `9e99d4f` (test)
3. **Task 1 (GREEN): centralizar el allowlist en `dialects/identifiers.py`** - `a2a6dc4` (feat)
4. **Task 2: migrar los 6 importadores + guard de fuente** - `388ce18` (refactor)
5. **Task 3: verificación de refactor puro** - sin commit (tarea de verificación; su entregable es la evidencia de abajo)

**Plan metadata:** docs commit `docs(02-01): complete ... plan` (hash en `git log`)

_Note: Task 1 siguió el ciclo TDD RED → GREEN (más un commit intermedio que corrige una expectativa errónea del plan)._

## Files Created/Modified

- `encino_orm/dialects/identifiers.py` (nuevo) - `IDENTIFIER_RE` + `check_identifier`, único punto de validación; solo stdlib (`re`).
- `encino_orm/dialects/__init__.py` (nuevo) - Barrel que re-exporta ambos símbolos en `__all__`.
- `tests/test_identifiers.py` (nuevo) - Tabla accept/reject, mensaje exacto, caracterización del salto final y guard de definición única.
- `encino_orm/base.py` - `Db._check_identifier` delega en `check_identifier`; se borra `_IDENTIFIER_RE` y el `import re` huérfano.
- `encino_orm/sqlite.py` - `columns_of` usa `check_identifier(table, "nombre de tabla")`; se borra `_IDENTIFIER_RE`.
- `encino_orm/mysql.py` - Igual que sqlite; MariaDB hereda sin cambios.
- `encino_orm/model/model.py` - Los 5 puntos de llamada pasan a `check_identifier` con labels idénticos (`nombre de tabla`, `nombre de columna`, `columna`, `columna de orden`).
- `encino_orm/model/types.py` - `indexes_ddl` usa `check_identifier(name, "nombre de índice")`; se borra `import re`.
- `encino_orm/transfer.py` - Se borran la regex y el checker locales; 4 puntos de llamada usan el compartido.
- `encino_orm/sql.py` - `_COLUMN_RE` intacta + comentario del por qué (allowlist distinta).
- `encino_orm/model/query_builder.py` - `_COLUMN_RE` intacta + comentario del por qué (allowlist distinta).

## Decisions Made

- **No relajar la allowlist** para aceptar `schema.tabla`; el caso cualificado se resolverá con un parámetro `schema=` validado por separado en 02-02 (Pitfall 10).
- **No unificar `_COLUMN_RE`**: es una allowlist deliberadamente distinta que acepta puntos; unificarla sería un cambio de comportamiento (prohibido aquí) y relajarla reabriría la superficie de inyección. Queda documentada como candidata de seguimiento.
- **Conservar el anclaje `$`** (que acepta un `\n` final) por ser refactor puro; se caracteriza en un test en lugar de endurecerla silenciosamente.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Conflicto plan/realidad] El plan listaba `"tabla\n"` como rechazo, pero el allowlist canónico lo acepta**
- **Found during:** Task 1 (GREEN — el test RED falló al implementar el módulo)
- **Issue:** El bloque `<behavior>` del plan lista `"tabla\n"` entre los 11 valores que deben lanzar `ValueError`. Sin embargo, `re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")` usa `$`, que en Python también casa justo antes de un salto de línea final, así que el `Db._check_identifier` actual **acepta** `"tabla\n"`. Rechazarlo habría exigido `\Z`/`fullmatch`, es decir, un cambio de comportamiento de validación — fuera de alcance para 02-01 y perteneciente al commit bisecable de 02-02.
- **Fix:** Se preservó el comportamiento canónico (invariante de refactor puro): `"tabla\n"` salió de la tabla de rechazo y se añadió `test_check_identifier_salto_final_sigue_aceptado` que documenta el comportamiento actual y lo deja señalado para un commit de validación aparte.
- **Files modified:** `tests/test_identifiers.py`
- **Verification:** `uv run pytest tests/test_identifiers.py -q` → 18 passed; la suite completa sigue en verde.
- **Committed in:** `aa68fd1` (RED) y `9e99d4f` (corrección de expectativa)

---

**Total deviations:** 1 auto-fixed (1 conflicto plan/realidad resuelto preservando el invariante de refactor puro)
**Impact on plan:** Ninguno sobre el alcance. La única diferencia es que la tabla de rechazo tiene 10 valores en lugar de 11; el allowlist, los mensajes y el SQL generado son byte a byte los de antes.

## Issues Encountered

None — aparte del conflicto plan/realidad documentado arriba. La migración de los 6 importadores no requirió iteración: `ruff`, `mypy` y la suite completa pasaron al primer intento.

## Pure-Refactor Evidence (Task 3)

- **Diff del plan completo sobre `tests/`:** solo `tests/test_identifiers.py` (83 inserciones); ningún test preexistente modificado.
- **Diff de los 5 ficheros de motor** (`test_postgresql.py`, `test_mssql.py`, `test_oracle.py`, `test_mysql.py`, `test_sqlite.py`) sobre `9dc2acf..HEAD`: vacío (aserción golden-string intacta).
- **`uv run pytest -q -m "not integration and not optional_engine"`:** 530 passed, 41 deselected.
- **`uv run pytest -q` (suite completa):** 571 passed (553 baseline + 18 nuevos).
- **Mensajes de commit:** ninguno contiene `validate`/`validación`/`validation`.
- **Gates:** `ruff check` exit 0; `ruff format --check` exit 0 (108 ficheros); `mypy encino_orm` exit 0 (58 ficheros); `noqa` = 0; `nosec` = 0.
- **Definición única:** el comando del plan imprime exactamente `[WindowsPath('encino_orm/dialects/identifiers.py')]`; `grep -rn "_IDENTIFIER_RE" encino_orm/` no devuelve coincidencias en fuentes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- El único cuello de botella de validación existe y está probado: 02-02 puede ahora *aplicar* `check_identifier` dentro de `dialects/builders.py` y en `sync_schema` en un commit separado y bisecable, sin tocar la allowlist ni los mensajes.
- `dialects/__init__.py` es el barrel donde 02-02 añadirá `build_*` y `strategies`.
- La caracterización del salto final queda como señal para decidir, en 02-02 o después, si se endurece el anclaje (cambio de validación, no de refactor).

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- `encino_orm/dialects/identifiers.py` — FOUND
- `encino_orm/dialects/__init__.py` — FOUND
- `tests/test_identifiers.py` — FOUND
- Commit `aa68fd1` — FOUND
- Commit `9e99d4f` — FOUND
- Commit `a2a6dc4` — FOUND
- Commit `388ce18` — FOUND

