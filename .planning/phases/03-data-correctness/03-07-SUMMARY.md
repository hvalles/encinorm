---
phase: 03-data-correctness
plan: 07
status: complete
gap_closure: true
subsystem: database
tags: [migrations, ledger, concurrency, wr-01, in-01, compare-and-delete, data-correctness, rolling-back]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "Runner de migraciones de dos fases con `_apply`, ledger `status` y `reconcile_migrations`/`resolve_migration` (03-01/03-02)"
provides:
  - "`_apply` con propiedad de fila: la compensación pre-DDL solo borra si ESTA llamada insertó la fila (`inserted`) y el DDL no corrió"
  - "Compare-and-delete `{name, status: pending}` en la compensación: nunca borra una fila `applied` ni la de otro proceso (WR-01)"
  - "Reintento del rollback documentado y accionable en el docstring de `resolve_migration` y en el texto del `MigrationError` de `reconcile_migrations` (IN-01, D-08 fila 4)"
  - "Cuatro regresiones (RED→GREEN): INSERT duplicado, compare-and-delete de la compensación, texto del error y docstring"
affects: [03-data-correctness, 08-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Propiedad de fila en compensaciones: un borrado compensatorio exige probar que ESTA llamada insertó la fila"
    - "Compare-and-delete: el DELETE liga todas las claves (name + status) para no tocar una fila ajena ni una promoción concurrente"
    - "Instrucción de resolución explícita: el docstring y el error de reconciliación nombran el helper a re-emitir"

key-files:
  created: []
  modified:
    - encino_orm/migration.py
    - tests/test_migration_reconcile.py

key-decisions:
  - "IN-01 se DOCUMENTA en vez de automatizar: `resolve_migration(db, name, *, applied)` no recibe la `Migration` ni el SQL del `down` (el ledger solo guarda el `up`), así que automatizar el reintento exigiría cambiar la firma pública y el contrato de D-05/D-17. La acción correcta es hacer explícito que el operador re-emita `rollback_migration(db, migration)`."
  - "WR-01 se corrige con doble defensa: flag `inserted` (propiedad) + compare-and-delete sobre `status='pending'` (estado). El flag evita borrar la fila de otro proceso; el `status` evita borrar una fila `applied` por una promoción concurrente."

patterns-established:
  - "La compensación de un fallo nunca borra lo que no insertó: `inserted` gatea el DELETE y el DELETE exige el estado esperado"
  - "Los residuales de spec se cierran documentando la acción faltante en el punto de contacto (docstring + mensaje de error), sin ampliar la firma pública"

requirements-completed: [DATA-02]

# Metrics
duration: 2min
completed: 2026-09-18
---

# Phase 3 Plan 7: Propiedad de la fila en `_apply` + reintento documentado del rollback Summary

**La compensación pre-DDL de `_apply` ya no puede borrar la fila del ledger de otro proceso: solo borra si ESTA llamada insertó la fila (`inserted`) y con compare-and-delete `{name, status: pending}` (WR-01); y el docstring de `resolve_migration` más el error de `reconcile_migrations` indican re-emitir `rollback_migration` para reintentar el `down` (IN-01).**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-18T18:56:34Z
- **Completed:** 2026-09-18T18:58:05Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **WR-01 cerrado.** `_apply` distingue "yo inserté esta fila" de "otro proceso ya la publicó": el flag `inserted` arranca en `False` y solo pasa a `True` tras un INSERT exitoso. Si el INSERT duplicado falla, la compensación no corre y la fila del otro proceso queda intacta.
- **Defensa en profundidad.** El borrado compensatorio pasa de `DELETE ... WHERE name = {name}` a `DELETE ... WHERE name = {0} AND status = {1}` (ambas ligadas): nunca borra una fila `applied` ni una promoción concurrente.
- **IN-01 cerrado.** El docstring de `resolve_migration` (tabla D-08 + párrafo) y el texto del `MigrationError` de `reconcile_migrations` nombran `rollback_migration` como el reintento obligatorio para `rolling_back` + `applied=True`.
- **Garantía de reconciliación intacta.** El `pending` publicado por un fallo DESPUÉS del DDL sigue sobreviviendo a propósito (rama `elif ... ddl_done`) y `reconcile_migrations` lo detecta (D-02/Pitfall 8).
- **Las cuatro transiciones de D-08/D-17 no cambian.** Solo se amplía la documentación de la fila 4.

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresiones WR-01 e IN-01 (RED) con el fake extendido** - `b9ce450` (test)
2. **Task 2: Propiedad de la fila en `_apply` + reintento documentado del rollback (GREEN)** - `7d42565` (fix)

**Plan metadata:** `d7d11fc` (docs: complete plan)

_Note: TDD tasks may have multiple commits (test → feat → refactor)_

## Files Created/Modified

- `tests/test_migration_reconcile.py` — `LedgerDb` extendido: `fail_duplicate_insert`, registro `delete_calls` y DELETE condicional fiel al SQL real (todas las claves deben coincidir); cuatro tests nuevos (`test_insert_duplicado_no_borra_la_fila_ajena`, `test_compensacion_borra_solo_la_fila_pending_propia`, `test_reconcile_error_text_instruye_reintentar_rollback`, `test_resolve_migration_docstring_documenta_reintento`).
- `encino_orm/migration.py` — `_apply`: flag `inserted`, condición `inserted and not ddl_done` y compare-and-delete `{name, status: STATUS_PENDING}`; docstring y error de `reconcile_migrations` con la instrucción de re-emitir `rollback_migration`; docstring de `resolve_migration` actualizado (IN-01).

## RED Evidence

Captured before touching `encino_orm/migration.py` (Task 1 verify, exit code 1):

```
FFFF                                                                     [100%]
FAILED tests/test_migration_reconcile.py::TestApplyTwoPhase::test_insert_duplicado_no_borra_la_fila_ajena
FAILED tests/test_migration_reconcile.py::TestApplyTwoPhase::test_compensacion_borra_solo_la_fila_pending_propia
FAILED tests/test_migration_reconcile.py::TestResolveMigration::test_reconcile_error_text_instruye_reintentar_rollback
FAILED tests/test_migration_reconcile.py::TestResolveMigration::test_resolve_migration_docstring_documenta_reintento
4 failed, 11 deselected in 0.10s
```

Tras el fix (Task 2 verify): `4 passed, 11 deselected` y `34 passed` en `test_migration_reconcile.py + test_migrations.py`.

## Verification

| Gate | Command | Result |
| ---- | ------- | ------ |
| Plan (Task 2) | `uv run pytest tests/test_migration_reconcile.py tests/test_migrations.py -q` | `34 passed` (exit 0) |
| Nuevas regresiones | `uv run pytest tests/test_migration_reconcile.py -k "duplicado or compensacion or reintentar or docstring" -q` | `4 passed` (exit 0) |
| Suite completa | `uv run pytest -q` | `834 passed` (10 snapshots) (exit 0) |
| Lint | `uv run ruff check encino_orm tests` | exit 0 |
| Formato | `uv run ruff format --check encino_orm tests` | `115 files already formatted` (exit 0) |
| Tipos | `uv run mypy encino_orm` | `Success: no issues found in 60 source files` (exit 0) |
| `noqa` | `grep -rn "noqa" encino_orm/` | 0 |
| Sin commit directo | `grep -c "db.commit()" encino_orm/migration.py` | 0 |
| DATA-01 no reabierto | `grep -c '":down"' encino_orm/migration.py` | 0 |
| `filterwarnings` | `pyproject.toml` | `["error", ...]` intacto |

Acceptance greps de Task 2: `inserted = True`=1, `inserted and not ddl_done`=1, `{"name": name, "status": STATUS_PENDING}`=1, `rollback_migration`>=2 (4), `db.commit()`=0.

## Decisions Made

- **IN-01 se documenta, no se automatiza.** `resolve_migration(db, name, *, applied)` no recibe la `Migration` ni el SQL del `down`; el ledger solo guarda el `up`. Automatizar el reintento cambiaría la firma pública y el contrato D-05/D-17. Se hace explícito en el docstring y en el error de reconciliación (decisión ya fijada en el PLAN).
- **Doble defensa en WR-01.** Flag `inserted` (propiedad de la fila) + compare-and-delete sobre `status='pending'` (estado esperado). El primero cubre el INSERT duplicado; el segundo, una promoción concurrente.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. Los cambios solo condicionan un DELETE existente y amplían documentación; `name`/`status` siguen viajando como parámetros ligados (T-03-07-04 intacto).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DATA-02 queda cubierto sin el residual de concurrencia (WR-01) ni la desviación de spec (IN-01).
- El contrato de importación diferida se preserva: `encino_orm/migration.py` no gana dependencias de capas opcionales.
- No se tocó `encino_orm/model/cached.py` (propiedad del plan 03-06).

---

_Phase: 03-data-correctness_
_Completed: 2026-09-18_

## Self-Check: PASSED

- FOUND: encino_orm/migration.py
- FOUND: tests/test_migration_reconcile.py
- FOUND: .planning/phases/03-data-correctness/03-07-SUMMARY.md
- FOUND: b9ce450
- FOUND: 7d42565
