---
phase: 06-config-optional-layer-hygiene
plan: 04
subsystem: graphql
tags: [strawberry, graphql, syrupy, snapshot, inspect, signature, closures, namespace, weakref, ruff, mypy]

# Dependency graph
requires:
  - phase: 06-01
    provides: "ConnectionRegistry / resolve_db sin global mutable (Wave 1, firmas congeladas)"
  - phase: 06-02
    provides: "SecurityConfig + guards con Annotated (Wave 1, firmas congeladas)"
provides:
  - "_pk_resolver de graphql/schema.py construido con closures + inspect.Signature (sin exec())"
  - "build_schema con un modulo sintetico por build (no muta el namespace del modulo real)"
  - "tests/test_graphql_namespace.py + tests/__snapshots__/test_graphql_namespace.ambr: guardian SDL (CFG-03 GraphQL) + no-mutacion/no-fuga (CFG-04)"
affects: [06-05, verify-phase-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Firma generada via inspect.Parameter/Signature en __signature__ (Strawberry deriva los argumentos GraphQL)"
    - "Namespace por build via types.ModuleType + sys.modules; ciclo de vida ligado al schema con weakref.finalize"
    - "Snapshot syrupy SDL capturado ANTES del rewrite y verificado con diff cero (guardian de contrato)"

key-files:
  created:
    - tests/test_graphql_namespace.py
    - tests/__snapshots__/test_graphql_namespace.ambr
  modified:
    - encino_orm/graphql/schema.py

key-decisions:
  - "El snapshot SDL se captura y commitea CONTRA el exec() vigente (e1fbcd3) antes del rewrite (66671d0); Task 2/3 corren sin --snapshot-update y exigen diff cero (T-06-04-01)"
  - "El modulo sintetico por build NO se borra en un finally: Strawberry resuelve los LazyType de los filtros autorreferentes (and/or/not) en EJECUCION via LazyType.resolve_type(), que no cachea; se libera con weakref.finalize cuando el schema se recolecta"
  - "El test de no-mutacion usa un modelo sonda (Sonda) que ningun otro build registra: con [Region, Agente] la asercion pasaba en vacio porque tests previos ya habian mutado el modulo"
  - "gtype | None sustituye a Optional[gtype] por ruff UP045; la SDL del .ambr queda byte-identica"
  - "resolver.__name__/__qualname__ = 'resolver' preserva la forma de la firma observable; la coercion id=int(id) se hace en el cuerpo (_cast)"

patterns-established:
  - "Refactor preservador de contrato custodiado por snapshot SDL pre/post con diff cero"
  - "Namespace sintetico por build con ciclo de vida atado al objeto consumidor (weakref) para no filtrar sys.modules"

requirements-completed: [CFG-03, CFG-04]

# Metrics
duration: 7min
completed: 2026-09-19
---

# Phase 6 Plan 4: GraphQL sin `exec()` + namespace por build (CFG-03/CFG-04) Summary

**`_pk_resolver` sustituye `exec()` por closures con `inspect.Signature` en `__signature__` y `build_schema` registra un modulo sintetico por build en `sys.modules`, dejando la SDL byte-identica (snapshot `.ambr` con diff cero) y sin mutar el namespace de `encino_orm.graphql.schema`.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-19T06:57:50Z
- **Completed:** 2026-09-19T07:05:17Z
- **Tasks:** 3/3
- **Files modified:** 3 (2 creados, 1 modificado)

## Accomplishments

- `tests/test_graphql_namespace.py` con 6 tests: snapshot SDL, dos builds sucesivos funcionales (relacion, filtros autorreferentes `and`/`or`/`not`, mutation), build con modelos distintos, operaciones PK simple/compuesta y no-mutacion/no-fuga del namespace.
- `.ambr` capturado CONTRA el codigo `exec()` actual y commiteado antes del rewrite (`e1fbcd3`); tras el rewrite la SDL queda byte-identica.
- `_pk_resolver` reescrito con tres closures `get`/`update`/`delete` y `Signature` explicita; `resolver.__name__`/`__qualname__` fijados a `"resolver"`; sin `exec()` (probe `ruff --isolated --select S102` en verde).
- `build_schema` ya no hace `setattr(module, ...)` sobre `encino_orm.graphql.schema`: cada build usa `types.ModuleType` + `sys.modules[name]`, con ciclo de vida atado al schema.
- Dos builds sucesivos no acumulan tipos: `set(vars(schema_mod))` identico antes/despues; cero entradas huerfanas en `sys.modules` tras la recoleccion.

## Task Commits

Cada tarea se commiteo atomicamente:

1. **Task 1: `tests/test_graphql_namespace.py` + `.ambr` contra el `exec()` actual** — `e1fbcd3` (test)
2. **Task 2: `_pk_resolver` → closures + `__signature__`** — `66671d0` (feat)
3. **Task 3 (RED): tests de no-mutacion/no-fuga del namespace** — `484224e` (test)
4. **Task 3 (GREEN): `build_schema` con namespace por build** — `d98ca92` (feat)

## Snapshot Ordering Evidence (Pitfall 2 / T-06-04-01)

- Commit del `.ambr` (captura contra `exec()`): **`e1fbcd3`** — `test(06-04): congela la SDL de build_schema contra el exec() actual`
- Commit del rewrite: **`66671d0`** — `feat(06-04): reescribe _pk_resolver con closures y __signature__`
- Commit del namespace: **`d98ca92`** — `feat(06-04): aisla el namespace de build_schema por build`
- `git log --oneline -- tests/__snapshots__/test_graphql_namespace.ambr` → solo `e1fbcd3` (ancestro de ambos rewrites).
- `git diff --stat tests/__snapshots__/test_graphql_namespace.ambr` → vacio (diff cero desde la captura).
- `uv run pytest tests/test_graphql_namespace.py -q` (sin `--snapshot-update`) → 1 snapshot passed.

## Files Created/Modified

- `tests/test_graphql_namespace.py` — Snapshot SDL (syrupy) + funcionalidad de dos builds + operaciones PK + no-mutacion/no-fuga del namespace.
- `tests/__snapshots__/test_graphql_namespace.ambr` — SDL congelada contra el `exec()` vigente (99 lineas; guardian del Criterio de Exito 4, mitad SDL).
- `encino_orm/graphql/schema.py` — `_pk_resolver` con closures + `__signature__` (sin `exec`); `build_schema` con modulo sintetico por build y `weakref.finalize`.

## Decisions Made

- El snapshot se captura antes del rewrite y nunca se regenera: cualquier diff habria invalidado el guardian.
- `resolver.__name__ = resolver.__qualname__ = "resolver"` para conservar la firma observable que Strawberry convierte en argumentos GraphQL.
- La coercion `id=int(id)` se replica en el helper `_cast` del cuerpo (no en la firma), igual que el codigo generado.
- El modulo sintetico por build se libera via `weakref.finalize` cuando el schema se recolecta (no se borra en un `finally`): Strawberry resuelve los `LazyType` de los filtros en ejecucion y no los cachea.
- El test de no-mutacion usa un modelo sonda (`Sonda`) para no depender del orden de ejecucion de los tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] El `del sys.modules[name]` en `finally` rompe los filtros GraphQL**

- **Found during:** Task 3 (GREEN)
- **Issue:** Con `del sys.modules[name]` en un `finally` tras `strawberry.Schema(...)`, la query con filtro (`{ agentes(filter: { and: [...] }) }`) falla con `ModuleNotFoundError: No module named 'encino_orm.graphql._build_1'`. La premisa del plan/research de que Strawberry resuelve **todos** los `LazyType` durante la construccion es incorrecta para los filtros autorreferentes: `convert_argument` → `LazyType.resolve_type()` los resuelve en tiempo de **ejecucion** y `LazyType.resolve_type()` **no cachea** (importa el modulo en cada llamada).
- **Fix:** El modulo sintetico no se borra al terminar la construccion; su ciclo de vida se ata al schema con `weakref.finalize(schema, sys.modules.pop, name, None)`. El schema participa en un ciclo, de modo que el modulo se libera en el GC ciclico cuando el schema deja de estar referenciado (evita fugas permanentes). En caso de fallo durante la construccion, el modulo se retira inmediatamente (`except BaseException: sys.modules.pop(name, None); raise`).
- **Files modified:** `encino_orm/graphql/schema.py`, `tests/test_graphql_namespace.py`
- **Commit:** `d98ca92`
- **Impacto en acceptance_criteria:** `grep -c "del sys.modules\[name\]" encino_orm/graphql/schema.py` devuelve **0** (el plan esperaba 1). La propiedad del Criterio de Exito 4 (no mutar el namespace del modulo) y la ausencia de fugas (verificada con `gc.collect()`) se conservan. El fallback que el plan autoriza ("conservar el modulo registrado") se implementa de forma mas estricta: el modulo se libera con el schema en lugar de quedar para siempre.

**2. [Rule 1 - Bug] El test de no-mutacion pasaba en vacio (dependencia del orden de ejecucion)**

- **Found during:** Task 3 (RED)
- **Issue:** El cuerpo literal del plan (`before = set(vars(schema_mod))`; dos builds de `[Region, Agente]`; `assert set(vars(...)) == before`) **pasaba** contra el `build_schema` que muta el modulo, porque tests anteriores del mismo fichero (`test_sdl_snapshot`, `test_build_schema_con_modelo_distinto_funciona`, ...) ya habian registrado `Region`/`Agente` en el namespace, y los dos builds solo re-asignaban los mismos nombres.
- **Fix:** El test incluye un build con un modelo sonda (`Sonda`) que ningun otro test registra, de modo que la asercion es independiente del orden y falla contra el codigo mutante (RED confirmado: `Extra items: 'Sonda', 'SondaFilter'`).
- **Files modified:** `tests/test_graphql_namespace.py`
- **Commit:** `484224e` (RED) / `d98ca92` (GREEN)

**3. [Rule 1 - Bug] `Optional[gtype]` dispara ruff UP045**

- **Found during:** Task 2
- **Issue:** Al pasar `Optional[gtype]` de string (en el codigo generado) a objeto real, `ruff` (regla UP045) exige `X | None`.
- **Fix:** `return_annotation = gtype | None`. Se verifico que la SDL del `.ambr` permanece byte-identica (el snapshot pasa sin `--snapshot-update`).
- **Files modified:** `encino_orm/graphql/schema.py`
- **Commit:** `66671d0`

**4. [Rule 1 - Test robustness] El test de no-fuga requiere `gc.collect()`**

- **Found during:** Task 3
- **Issue:** El schema participa en un ciclo de referencias, por lo que el `weakref.finalize` no se dispara solo con el decremento de refcount; el test de no-fuga comprobaba `sys.modules` inmediatamente y veia los modulos vivos.
- **Fix:** El test fuerza `gc.collect()` antes de afirmar `not [k for k in sys.modules if "_build_" in k]`.
- **Files modified:** `tests/test_graphql_namespace.py`
- **Commit:** `d98ca92`

## TDD Gate Compliance

- RED gate (Task 3): `484224e` (`test(06-04): anade el test de no-mutacion del namespace (RED, CFG-04)`) — falla contra el `build_schema` mutante.
- GREEN gate (Task 3): `d98ca92` (`feat(06-04): aisla el namespace de build_schema por build (CFG-04)`).
- Task 2 es un refactor preservador de contrato: su RED es el snapshot SDL de Task 1 (capturado contra el `exec()` y verificado con diff cero tras el rewrite), no un test nuevo que falle; el plan limita `files` de Task 2 a `encino_orm/graphql/schema.py`.
- No hubo commit REFACTOR adicional.

## Known Stubs

None.

## Threat Flags

None. No se introduce superficie de red, autenticacion, acceso a ficheros ni cambios de esquema fuera del `<threat_model>` del plan.

## Issues Encountered

Ninguno mas alla de las desviaciones anteriores (todas resueltas en el mismo plan).

## Verification (end-of-plan gates)

- `uv run pytest tests/test_graphql_namespace.py -q` → 6 passed, 1 snapshot passed (sin `--snapshot-update`).
- `uv run pytest tests/test_graphql.py tests/test_pk.py -q` → 32 passed.
- `uv run pytest tests/test_graphql.py tests/test_pk.py tests/test_pagination_limits.py -q` → 43 passed.
- `uv run pytest -q -m "not integration and not optional_engine"` → 959 passed, 88 deselected, 12 snapshots passed.
- `uv run pytest -q` → 1047 passed (integration se auto-omite sin motores), 12 snapshots passed.
- `uv run ruff check encino_orm tests` → All checks passed.
- `uv run ruff format --check encino_orm tests` → 123 files already formatted.
- `uv run mypy encino_orm` → Success: no issues found in 61 source files.
- `uv run ruff check --isolated --select S102 encino_orm/graphql/schema.py` → All checks passed (probe W6; ignore retirable por 06-05).
- `grep -Ec "^\s*exec\(" encino_orm/graphql/schema.py` → 0; `__signature__` → 2; `Signature(` → 1; `resolver.__name__` → 1; `ModuleType` → 1; `setattr(module` → 0.
- `grep -c "del sys.modules\[name\]"` → 0 (desviacion documentada; ver Deviations #1).
- `git diff --stat tests/__snapshots__/test_graphql_namespace.ambr` → vacio; `set(vars(encino_orm.graphql.schema))` identico antes/despues de dos builds; `sys.modules` sin `_build_` tras `gc.collect()`.

## Next Phase Readiness

- CFG-03 (GraphQL) y CFG-04 cerrados: `06-05` puede retirar el `per-file-ignore` `S102` de `encino_orm/graphql/schema.py` y las entradas del ratchet mypy `encino_orm.graphql.*` (los 5 `name-defined` eran artefacto del `exec()`; `mypy encino_orm` ya sale limpio).
- `06-05` sigue siendo el unico dueno de `pyproject.toml`, `CHANGELOG.md`, `mkdocs.yml` y `ci.yml` (Pitfall 8): este plan no toco ninguno.
- Sin bloqueos.

---

*Phase: 06-config-optional-layer-hygiene*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `tests/test_graphql_namespace.py`
- FOUND: `tests/__snapshots__/test_graphql_namespace.ambr`
- FOUND: `.planning/phases/06-config-optional-layer-hygiene/06-04-SUMMARY.md`
- FOUND: commit `e1fbcd3` (captura del snapshot)
- FOUND: commit `66671d0` (rewrite `_pk_resolver`)
- FOUND: commit `484224e` (RED namespace)
- FOUND: commit `d98ca92` (GREEN namespace)
- `e1fbcd3` es ancestro de `66671d0` y `d98ca92` (orden de snapshots verificado)
