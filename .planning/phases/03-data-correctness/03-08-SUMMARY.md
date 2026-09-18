---
phase: 03-data-correctness
plan: 08
status: complete
gap_closure: true
subsystem: database
tags: [cache, invalidation, multi-tenant, scope, cr-01, cr-02, wr-02, data-correctness, tdd]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "Dominio de caché canónico por PK: `load()` escribe solo bajo la PK y `update`/`delete`/`upsert` resuelven la PK real de la fila afectada antes de invalidar (03-06)"
  - phase: 03-data-correctness
    provides: "Backend de caché acotado (LRU) y contrato dev/test-only (03-05); fail-open D-12 e `insert_many(cache=)` D-16 (03-03)"
provides:
  - "`_resolve_pk_values` devuelve la LISTA de TODAS las PKs que casan las claves de escritura (SELECT multi-fila ligado, scope-aware, `include_deleted=True`): cierra CR-01 multi-fila"
  - "`_cache_key_for` namespaced por `current_scope().digest()`: una entrada de un tenant nunca se sirve a otro ni habilita una escritura cruzada (cierra CR-02)"
  - "Re-resolución de PKs tras la escritura + invalidación de la unión antes/después: acota el TOCTOU (WR-02)"
  - "Regresiones RED→GREEN: 4 fallan antes del fix (multi-fila, lectura cruzada, escritura cruzada, clave por scope) + 1 guarda intra-tenant"
affects: [03-data-correctness, 08-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Invalidación multi-fila: resolver con `Model.search(columns=pk_cols, include_deleted=True)` todas las PKs que casan, no una sonda `fetch_one`"
    - "Namespace de caché por alcance: la huella `Filter.digest()` del `scope()` activo forma parte de la clave (sin scope, clave idéntica a la anterior)"
    - "Re-sonda post-escritura: resolver la PK antes y después e invalidar la unión acota (no elimina) el TOCTOU entre la sonda y la escritura"
    - "Fail-open en toda resolución/invalidación: `try/except` con `logger.warning`, la escritura commiteada nunca se revierte (D-12)"

key-files:
  created: []
  modified:
    - encino_orm/model/cached.py
    - tests/test_cached_model.py

key-decisions:
  - "CR-01 multi-fila se resuelve con `Model.search` (parámetros ligados, `current_scope()`, `include_deleted=True`), no con una consulta dedicada: se hereda el filtrado multi-fila y el scope sin escribir SQL nuevo ni interpolar."
  - "CR-02 se resuelve namespaceando la CLAVE con `current_scope().digest()` en vez de re-chequear el scope en el hit path: la entrada de un tenant jamás casa la clave de otro, cubre lectura y escritura, y sin scope la clave es idéntica (compatible)."
  - "WR-02 se acota (no se elimina) re-resolviendo las PKs DESPUÉS de la escritura e invalidando la unión; el residual se documenta en los docstrings de los overrides."

patterns-established:
  - "Toda escritura de `CachedModel` invalida las entradas de TODAS las filas que casan sus claves, resueltas con `search` ligado y scope-aware"
  - "La clave de caché incorpora el alcance activo: el aislamiento multi-tenant es una propiedad de la clave, no del camino de lectura"

requirements-completed: [DATA-03]

# Metrics
duration: 8min
completed: 2026-09-18
---

# Phase 3 Plan 8: Invalidación multi-fila + caché namespaced por scope Summary

**`CachedModel` invalida las entradas de TODAS las filas que casa una escritura (CR-01 multi-fila) y namespaces la clave por `scope()` para que ningún acierto cruce tenants (CR-02), acotando el TOCTOU con una re-sonda post-escritura (WR-02).**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-18T19:14:00Z
- **Completed:** 2026-09-18T19:22:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- **CR-01 multi-fila cerrado.** `_resolve_pk_values` devuelve una LISTA de PKs: cuando la clave de escritura no es la PK, `Model.update`/`delete` afectan a TODAS las filas que casan, así que se resuelven con `self.search(filter=<AND de Filter.eq>, columns=_pk_cols(), include_deleted=True)` — SELECT ligado, scope-aware y multi-fila. `_invalidate_pks` borra cada entrada; ya no queda una fila afectada obsoleta.
- **CR-02 cerrado.** `_cache_key_for` concatena `|scope={current_scope().digest()}` antes del sha1. Un acierto del tenant B ya no sirve la fila de A, y `Model.update` cae en su pre-chequeo con scope y lanza `FailOnUpdate` (la escritura cruzada queda bloqueada). Sin scope, la clave es idéntica a la anterior (compatibilidad y `insert_many` D-16 intactos).
- **WR-02 acotado.** `update`/`delete`/`upsert` resuelven las PKs ANTES y DESPUÉS de la escritura e invalidan `_union(pks, pks_after)`: si otra transacción mueve la clave a otra fila entre ambas sondas, la re-sonda también captura esa fila. El residual (no eliminado por completo) queda documentado.
- **Fail-open (D-12) preservado.** Toda la resolución y la derivación de clave + `cache.delete` viven dentro de `try/except` con `logger.warning`; una escritura ya commiteada nunca se revierte. `insert_many(cache=)` sigue invalidando bajo el namespace del scope activo.
- **Sin regresiones.** Suite completa `839 passed` (10 snapshots); lint/formato/mypy en 0.

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresiones RED de CR-01 multi-fila y CR-02 (aislamiento por scope)** - `5bfa5e6` (test)
2. **Task 2: Invalidación multi-fila + clave namespaced por scope (GREEN)** - `f039343` (fix)

**Plan metadata:** `PENDING` (docs: complete plan)

_Note: TDD tasks may have multiple commits (test → fix)_

## RED Evidence

Capturado antes de tocar `encino_orm/model/cached.py` (verify de Task 1, exit code 1):

```
FFF.F                                                                    [100%]
FAILED tests/test_cached_model.py::TestCachedModel::test_cr01_multifila_invalida_todas_las_pks
FAILED tests/test_cached_model.py::TestCachedModel::test_cr02_scope_no_aislado_no_sirve_otro_tenant
FAILED tests/test_cached_model.py::TestCachedModel::test_cr02_scope_bloquea_escritura_cruzada
FAILED tests/test_cached_model.py::TestCachedModel::test_cr02_clave_depende_del_scope
4 failed, 1 passed, 15 deselected in 0.22s
```

Diagnóstico RED por caso:
- **multi-fila**: solo desaparece la entrada `id=1`; la `id=2` sobrevive (`assert ... is None` falla) → confirmado CR-01 multi-fila.
- **lectura cruzada**: bajo `scope(B)`, `load(id=1)` acierta la entrada de A (`__exists` es `True` en vez de `False`) → confirmado CR-02 lectura.
- **escritura cruzada**: bajo `scope(B)`, `update()` NO lanza `FailOnUpdate` (el hit de caché salta el scope) → confirmado CR-02 escritura.
- **clave por scope**: `k_a == k_out` (`a94b8aa1…` idénticas) → confirmado que el scope no formaba parte de la clave.
- **guarda intra-tenant** (`test_cr02_mismo_scope_si_acierta`): pasa ya antes del fix (el aislamiento no debe romper el cacheo del mismo tenant); es guarda, no regresión.

Tras el fix (verify de Task 2): `5 passed, 15 deselected` y `26 passed` en `test_cached_model.py + test_cache_backend.py`.

## Verification

| Gate | Command | Result |
| ---- | ------- | ------ |
| Nuevas regresiones (GREEN) | `uv run pytest tests/test_cached_model.py -k "cr01_multifila or cr02_" -q` | `5 passed` (exit 0) |
| Plan (Task 2) | `uv run pytest tests/test_cached_model.py tests/test_cache_backend.py -q` | `26 passed` (exit 0) |
| Suite completa | `uv run pytest -q` | `839 passed` (10 snapshots) (exit 0) |
| Lint | `uv run ruff check encino_orm tests` | `All checks passed!` (exit 0) |
| Formato | `uv run ruff format --check encino_orm tests` | `115 files already formatted` (exit 0) |
| Tipos | `uv run mypy encino_orm` | `Success: no issues found in 60 source files` (exit 0) |
| `noqa` | `grep -rn "noqa" encino_orm/` | 0 |
| Import diferido | `grep -c "import redis" encino_orm/model/cached.py` | 0 |

Acceptance greps de Task 2: `_invalidate_pks`=4 (>=4), `def _invalidate_pk\b`=0, `current_scope`=3 (>=2), `self.search`=1 (>=1), `include_deleted=True`=2 (>=1), `_union`=4 (>=4).

Acceptance greps de Task 1: `def test_cr01_multifila`=1, `def test_cr02_`=4, `class ClienteScope`=1.

## Files Created/Modified

- `tests/test_cached_model.py` — Nuevo modelo `ClienteScope` (tabla `clientes_scope`, PK `id`, `grupo` NO único, `tenant`) con `DDL_SCOPE` y fixture `db_scope`; helper `_scope_pk_key`; 5 tests nuevos (`test_cr01_multifila_invalida_todas_las_pks`, `test_cr02_scope_no_aislado_no_sirve_otro_tenant`, `test_cr02_scope_bloquea_escritura_cruzada`, `test_cr02_mismo_scope_si_acierta`, `test_cr02_clave_depende_del_scope`). Los 5 `test_cr01_*` existentes se conservan.
- `encino_orm/model/cached.py` — `_cache_key_for` namespaced por `current_scope().digest()`; `_resolve_pk_values` devuelve `list[dict] | None` vía `self.search`; nuevo `_union` (dedup por tupla ordenada) y `_invalidate_pks` (itera la lista, fail-open); overrides `update`/`delete`/`upsert` re-resuelven tras la escritura e invalidan la unión; imports `Filter` y `current_scope`.

## Decisions Made

- **CR-01 con `search` multi-fila, no con consulta dedicada.** Reutilizar `Model.search(columns=_pk_cols(), include_deleted=True)` hereda los parámetros ligados, el `current_scope()` y el filtrado multi-fila sin escribir SQL nuevo (no se interpola) — respeta la convención de seguridad del proyecto.
- **CR-02 en la clave, no en el hit path.** Namespacear la clave cubre simultáneamente lectura y escritura, y sin scope deja la clave idéntica a la anterior (compatibilidad e `insert_many` D-16 intactos). Re-chequear el scope en el hit path solo habría cubierto la lectura.
- **WR-02 se acota, no se elimina.** La re-sonda post-escritura + unión captura la fila a la que otra transacción pudo mover la clave; el residual (una escritura posterior a la re-sonda) queda documentado, no se declara imposible.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- El primer borrador del test de escritura cruzada usaba dos `with` anidados; `ruff check` (SIM117) lo rechazó. Se combinó en `with scope(...), pytest.raises(...):` y se aplicó `ruff format`. Sin impacto en el comportamiento del test.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries. Los cambios refuerzan los mitigations del `<threat_model>`: T-03-08-01/02/03/05 (clave namespaced, invalidación multi-fila, escritura cruzada bloqueada, re-sonda) y T-03-08-04 (fail-open preservado). No se instalaron paquetes ni se añadió `continue-on-error` (T-03-08-SC).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- DATA-03 (sin lecturas obsoletas) queda cubierto por must-haves verificables: CR-01 multi-fila y CR-02 de scope cerrados; WR-02 acotado.
- El contrato de importación diferida se preserva: `encino_orm/model/cached.py` no gana dependencias de capas opcionales (`import redis`=0).
- Cambio de formato de clave por scope: las entradas viejas (sin sufijo de scope) quedan huérfanas hasta el TTL; su registro en `CHANGELOG.md`/docs pertenece a otro plan (03-09/03-10), no a este.
- No se tocó `encino_orm/migration.py` (propiedad de 03-07/03-09) ni docs.

---

_Phase: 03-data-correctness_
_Completed: 2026-09-18_

## Self-Check: PASSED

- FOUND: encino_orm/model/cached.py
- FOUND: tests/test_cached_model.py
- FOUND: .planning/phases/03-data-correctness/03-08-SUMMARY.md
- FOUND: 5bfa5e6
- FOUND: f039343
