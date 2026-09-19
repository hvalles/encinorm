---
phase: 06-config-optional-layer-hygiene
plan: 03
subsystem: api
tags: [fastapi, openapi, syrupy, snapshot, inspect, signature, closures, ruff, mypy]

# Dependency graph
requires:
  - phase: 06-01
    provides: "ConnectionRegistry / resolve_db sin global mutable (Wave 1, firmas congeladas)"
  - phase: 06-02
    provides: "SecurityConfig + guards con Annotated (Wave 1, firmas congeladas)"
provides:
  - "Handlers get/put/delete de http/routes.py construidos con closures + inspect.Signature (sin exec())"
  - "tests/test_http_openapi.py + tests/__snapshots__/test_http_openapi.ambr: guardian del Criterio de Exito 3 (OpenAPI byte-identica)"
  - "create/list_ migrados a Annotated[object, Depends(get_db)] (B008 retirable por 06-05)"
affects: [06-04, 06-05, verify-phase-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Firma generada via inspect.Parameter/Signature asignada a __signature__ (FastAPI la lee tal cual)"
    - "Closures con **kwargs + kwargs.pop('db'); nombres por cierre, sin __globals__"
    - "Snapshot syrupy capturado ANTES del rewrite y verificado con diff cero (guardián de contrato)"

key-files:
  created:
    - tests/test_http_openapi.py
    - tests/__snapshots__/test_http_openapi.ambr
  modified:
    - encino_orm/http/routes.py

key-decisions:
  - "El snapshot OpenAPI se captura y commitea CONTRA el exec() vigente (ca20a32) antes del rewrite (fa76bcf); Task 2 corre sin --snapshot-update y exige diff cero (T-06-03-01)"
  - "handler.__name__ = handler.__qualname__ = 'handler' preserva el operationId de OpenAPI (Pitfall 3)"
  - "Parameter('db', ..., default=Depends(get_db)) SIN annotation mantiene la inyeccion de dependencia (Pitfall 5)"
  - "list_ declara db: Annotated[object, Depends(get_db)] = None porque sigue a parametros con default (orden de firma inalterado)"
  - "No se toca graphql/schema.py: ese exec() y el namespace por build pertenecen a 06-04 (Pitfall 9 / Open Q3)"

patterns-established:
  - "Refactor preservador de contrato custodiado por snapshot pre/post con diff cero"

requirements-completed: [CFG-03]

# Metrics
duration: 2min
completed: 2026-09-19
---

# Phase 6 Plan 3: HTTP codegen sin `exec()` (CFG-03) Summary

**`_build_path_handler` de `http/routes.py` sustituye `exec()` por closures con `inspect.Signature` en `__signature__`, dejando el OpenAPI byte-identico (snapshot `.ambr` con diff cero) y los path params de PK simple y compuesta validando.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-09-19T06:54:16Z
- **Completed:** 2026-09-19T06:56:32Z
- **Tasks:** 3/3
- **Files modified:** 3 (2 creados, 1 modificado)

## Accomplishments
- `tests/test_http_openapi.py` con 3 tests: snapshot OpenAPI completo, validacion de path params (PK `int` simple y PK compuesta `int`+`str`) y contrato de operaciones (201/200/PUT/DELETE).
- `.ambr` capturado CONTRA el codigo `exec()` actual y commiteado antes del rewrite (`ca20a32`), con los `operationId` (`handler_*`, `list_*`, `create_*`) y los parametros de path congelados.
- `_build_path_handler` reescrito con closures `get`/`put`/`delete` y `Signature` explicita; `handler.__name__`/`__qualname__` fijados a `"handler"`; `db` como `default=Depends(get_db)` sin anotacion.
- `create`/`list_` migrados a `Annotated[object, Depends(get_db)]` (elimina los 2 `B008` de `routes.py`).
- Contrato HTTP preservado byte a byte: el test de snapshot pasa SIN `--snapshot-update` y `git diff` no toca el `.ambr` tras el rewrite.

## Task Commits

Cada tarea se commiteo atomicamente:

1. **Task 1: `tests/test_http_openapi.py` + `.ambr` contra el `exec()` actual** - `ca20a32` (test)
2. **Task 2: `_build_path_handler` -> closures + `__signature__` + `Annotated`** - `fa76bcf` (feat)
3. **Task 3: No-regresion y cierre de CFG-03** - verificacion unicamente (sin cambios de codigo; ver commits de cierre del plan)

_Nota: Task 3 es una tarea de no-regresion (solo ejecuta la suite y confirma diffs); su evidencia es el run verde y el commit de metadatos del plan._

## Snapshot Ordering Evidence (Pitfall 2 / T-06-03-01)

- Commit del `.ambr` (captura contra `exec()`): **`ca20a32`** — `test(06-03): congela el OpenAPI del CRUD actual con exec()`
- Commit del rewrite: **`fa76bcf`** — `feat(06-03): reescribe _build_path_handler con closures y __signature__`
- `git log --oneline -- tests/__snapshots__/test_http_openapi.ambr` -> `ca20a32` (ancestro de `fa76bcf`); el rewrite **no** incluye el `.ambr`.
- `git diff --stat tests/__snapshots__/test_http_openapi.ambr` -> vacio desde la captura.
- El rewrite se verifico con `uv run pytest tests/test_http_openapi.py -q` (sin `--snapshot-update`): 1 snapshot passed, diff cero.

## Files Created/Modified
- `tests/test_http_openapi.py` - Snapshot OpenAPI (syrupy) + validacion de path params simple/compuesta + contrato de operaciones.
- `tests/__snapshots__/test_http_openapi.ambr` - OpenAPI congelado contra el `exec()` vigente (1153 lineas; guardian del Criterio 3).
- `encino_orm/http/routes.py` - `_build_path_handler` con closures + `__signature__` (sin `exec`); `create`/`list_` con `Annotated`.

## Decisions Made
- El snapshot se captura antes del rewrite y nunca se regenera: cualquier diff habria invalidado el guardian.
- `handler.__name__ = handler.__qualname__ = "handler"` para preservar el `operationId` derivado de `endpoint.__name__`.
- `db` en la `Signature` usa `default=Depends(get_db)` sin `annotation` (FastAPI detecta la dependencia por el default).
- `list_` mantiene el orden de la firma original: `db: Annotated[object, Depends(get_db)] = None` (un parametro sin default no puede seguir a otros con default).
- No se toco `graphql/schema.py` (su `exec()` y el namespace por build son de `06-04`).

## Deviations from Plan

None - plan executed exactly as written.

(Unica intervencion mecanica: `uv run ruff format encino_orm/http/routes.py` colapso la comprehension de `params` a una linea dentro del limite de 100; sin cambio de comportamiento.)

## TDD Gate Compliance

- RED gate: `ca20a32` (`test(06-03): ...`) — el test de snapshot nace fallando (snapshot ausente, syrupy sound) contra el `exec()` actual.
- GREEN gate: `fa76bcf` (`feat(06-03): ...`) — el rewrite deja el test verde con diff cero en el `.ambr`.
- No hubo commit REFACTOR (no hizo falta limpieza adicional).

## Issues Encountered
None.

## Verification (end-of-plan gates)

- `uv run pytest tests/test_http_openapi.py -q` -> 3 passed, 1 snapshot passed (sin `--snapshot-update`).
- `uv run pytest tests/test_crud.py tests/test_pk.py tests/test_pagination_limits.py -q` -> 42 passed.
- `uv run pytest -q -m "not integration and not optional_engine"` -> 953 passed, 88 deselected.
- `uv run pytest -q` -> 1041 passed (integration se auto-omite sin motores).
- `uv run ruff check encino_orm tests` -> All checks passed.
- `uv run ruff format --check encino_orm tests` -> 122 files already formatted.
- `uv run mypy encino_orm` -> Success: no issues found in 61 source files.
- `uv run ruff check --isolated --select S102,B008 encino_orm/http/routes.py` -> All checks passed (probe W6).
- `grep -Ec "^\s*exec\(" encino_orm/http/routes.py` -> 0; `__signature__` -> 3; `Signature(` -> 1; `__name__ = "handler"` -> 1; `Annotated` -> 3.
- `git diff --stat tests/__snapshots__/test_sql_snapshots.ambr` -> vacio; `git diff --stat encino_orm/http/__init__.py` -> vacio.

## Next Phase Readiness
- CFG-03 (HTTP) cerrado: `06-05` puede retirar el `per-file-ignore` `S102`/`B008` de `encino_orm/http/routes.py` y la entrada del ratchet mypy `encino_orm.http.routes` (mypy ya sale limpio en el modulo).
- `06-04` (GraphQL) sigue siendo disjunto en ficheros; su guardian SDL es independiente de este `.ambr`.
- Sin bloqueos.

---
*Phase: 06-config-optional-layer-hygiene*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `tests/test_http_openapi.py`
- FOUND: `tests/__snapshots__/test_http_openapi.ambr`
- FOUND: `.planning/phases/06-config-optional-layer-hygiene/06-03-SUMMARY.md`
- FOUND: commit `ca20a32` (captura del snapshot)
- FOUND: commit `fa76bcf` (rewrite)
- `ca20a32` es ancestro de `fa76bcf` (orden de snapshots verificado)

