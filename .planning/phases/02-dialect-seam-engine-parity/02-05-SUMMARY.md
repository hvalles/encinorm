---
phase: 02-dialect-seam-engine-parity
plan: 05
subsystem: testing
tags: [ci, snapshots, syrupy, coverage, mariadb, redis, mssql, oracle, dialect-parity]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "Seam DML byte-identico (`dialects/builders.py` + `strategies.py`), `Query` inmutable y el alias `AS n` en los siete lectores (02-01…02-04)"
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "Interruptor `ENCINO_ORM_REQUIRE_ENGINES`, gate `check_skips.py`, ratchet global `fail_under = 82`, config pytest endurecida"
provides:
  - "9 snapshots DB-free del SQL de los 6 dialectos (`tests/test_sql_snapshots.py` + `.ambr` commiteado) como gate en el job SQLite siempre activo"
  - "MariaDB y Redis REQUERIDOS en el job `test` (servicios + `--extra cache` + marcadores `optional_engine` retirados)"
  - "Job `engine-heavy` no-advisory para MSSQL/Oracle con instalacion explicita de `msodbcsql18` y `FREEPDB1`"
  - "Gate de pisos de cobertura por modulo (`tools/ci/check_coverage_floors.py`) cableado al job `coverage`, fail-closed"
affects: [03, 04, 07]

# Tech tracking
tech-stack:
  added: [syrupy 6.1.1]
  patterns:
    - "Snapshot DB-free indexado por dialecto: UN snapshot con los 6 dialectos nombrados, de modo que el diff senala el dialecto culpable"
    - "Spy sin `connect()` para congelar el SQL de count/paginate/list_tables (fetch_* monkeypatcheados)"
    - "Seleccion de motores por FICHERO en el job pesado (nunca por marker) para que el job no pueda pasar en vacio"
    - "Gate de pisos por modulo sobre `coverage json`, fail-closed ante un modulo ausente (espejo de check_skips.py)"

key-files:
  created:
    - tests/test_sql_snapshots.py
    - tests/__snapshots__/test_sql_snapshots.ambr
    - tools/ci/check_coverage_floors.py
  modified:
    - pyproject.toml
    - uv.lock
    - tests/test_mariadb.py
    - tests/test_redis_cache.py
    - tests/test_ci_harness.py
    - .github/workflows/ci.yml
    - .gitignore

key-decisions:
  - "syrupy==6.1.1 con pin exacto: el formato de serializacion de los .ambr esta versionado, como la salida de ruff."
  - "Los snapshots son un gate, no advisory: el .ambr va en el mismo commit que el test y un snapshot ausente FALLA."
  - "MariaDB/Redis se promueven quitando sus marcadores optional_engine en el MISMO commit que anade servicio+env+extra (Pitfall H)."
  - "engine-heavy selecciona por fichero, no por marker; instala msodbcsql18+unixodbc-dev y sobreescribe ENCINO_ORM_ORACLE_SERVICE=FREEPDB1."
  - "Sin pisos de cobertura de adaptador todavia: oracle.py mide 16% en la corrida equivalente a CI; se fijan cuando engine-heavy este verde."
  - "coverage.json se anade a .gitignore (artefacto generado por el job coverage)."

patterns-established:
  - "Snapshot de dialecto con diff atribuible: dict indexado por nombre de dialecto, no lista posicional"
  - "Un solo fixture de snapshot por operacion cubre los 6 motores; la operacion, no el motor, define el test"

requirements-completed: [DIAL-07, DIAL-08]

# Metrics
duration: 7min
completed: 2026-09-18
---

# Phase 2 Plan 05: Snapshots por dialecto + matriz multi-motor + pisos de cobertura Summary

**9 snapshots syrupy DB-free congelan el SQL de los 6 dialectos en el job SQLite siempre activo; MariaDB y Redis pasan a motores requeridos en el job `test`; un job `engine-heavy` no-advisory instala el driver ODBC y exige MSSQL/Oracle; y un gate fail-closed aplica pisos de cobertura por módulo sobre `coverage json`.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-18T04:48:57Z
- **Completed:** 2026-09-18T04:55:05Z
- **Tasks:** 3 ejecutadas (Task 2, 3, 4) + 1 checkpoint humano aprobado (Task 1)
- **Files modified:** 10 (3 creados, 7 modificados)

## Accomplishments

- **DIAL-07 cumplido.** `tests/test_sql_snapshots.py` congela el SQL de los 6 dialectos sin base de datos: `insert` (plano / `ignore_duplicated` / `replace` / `replace`+`conflict`), `update`, `delete`, y el SQL de `count`/`paginate`/`list_tables` capturado con un spy sin `connect()`. Los `.ambr` están commiteados y son un gate (un snapshot ausente FALLA, verificado).
- **DIAL-08 cumplido.** El job `test` levanta MariaDB (3307:3306) y Redis, instala `--extra cache` y exige `mysql,postgresql,mariadb,redis`. Un job `engine-heavy` de una sola pata (3.12) instala `msodbcsql18` + `unixodbc-dev`, usa `FREEPDB1` y corre MSSQL/Oracle **por selección de fichero**, de modo que no puede quedar probando cero tests. `continue-on-error` es 0 en todo el workflow.
- **Gate de pisos por módulo (D-04/D-06 de Fase 1).** `tools/ci/check_coverage_floors.py` aplica 100/95/95 a `identifiers.py`/`builders.py`/`query.py` y **falla cerrado** si un módulo del mapa desaparece del reporte (Pitfall J). Cableado al job `coverage`.
- **Promoción real, no teatro (Pitfall H).** Los marcadores `optional_engine` de MariaDB (DOS decoradores) y Redis se retiraron en el mismo commit que añade los servicios; el comentario obsoleto de Redis se reescribió.
- Gates de Fase 1 intactos: `ruff check` / `ruff format --check` / `mypy encino_orm` salen 0; `noqa` sigue en 0; `filterwarnings = ["error"]` activo; ambos workflows parsean con `yaml.safe_load`.
- Suite completa: **710 passed** (baseline 694 + 16 nuevos), cobertura total **90.47%**.

## Task Commits

Each task was committed atomically:

1. **Task 1: Compuerta de legitimidad de `syrupy`** - checkpoint humano, sin commit (no instaló ni cambió ficheros)
2. **Task 2: Snapshots por dialecto + instalación de `syrupy`** - `5a3712b` (test)
3. **Task 3: Matriz multi-motor (MariaDB+Redis requeridos, job `engine-heavy`)** - `d6ad923` (feat)
4. **Task 4 (RED): tests del gate de pisos por módulo** - `78cd767` (test)
5. **Task 4 (GREEN): `check_coverage_floors.py` + cableado CI** - `f6a7be6` (feat)

**Plan metadata:** `docs(02-05): complete ... plan` (hash en `git log`)

_Note: la tarea 4 siguió el ciclo TDD RED → GREEN (gate RED y GREEN presentes)._

## Checkpoint Evidence (Task 1 — aprobado por el humano)

Compuerta `checkpoint:human-verify` `gate="blocking-human"` sobre `syrupy` (slopcheck `[SUS]`). Evidencia registrada verbatim:

- Independent PyPI verification: name `syrupy`, version `6.1.1`, license MIT, `requires_python >=3.10`, repository `https://github.com/syrupy-project/syrupy`, summary "Pytest Snapshot Test Utility".
- Release history 5.5.0 → 6.0.0 → 6.1.1 (2026-09-13) — active project, not a single-commit package.
- `slopcheck`'s `[SUS]` was a FALSE POSITIVE from name similarity vs `scrapy` (unrelated projects).
- Human approval granted to install `syrupy==6.1.1` as a dev dependency.

**Outcome:** APPROVED. `uv add --dev syrupy==6.1.1` executed as part of Task 2. No auth gate, no blocker.

## Files Created/Modified

- `tests/test_sql_snapshots.py` (nuevo) - 9 snapshots DB-free: DML de los builders compartidos + count/paginate/list_tables vía spy; docstring con el flujo de actualización y la política de snapshots huérfanos.
- `tests/__snapshots__/test_sql_snapshots.ambr` (nuevo, COMMITEADO) - el gate: 6 dialectos indexados por nombre en cada operación.
- `tools/ci/check_coverage_floors.py` (nuevo) - gate stdlib-only de pisos por módulo sobre `coverage json`; falla cerrado ante un módulo ausente.
- `pyproject.toml` - `syrupy==6.1.1` en `[dependency-groups].dev` con comentario justificativo del pin.
- `uv.lock` - resolución de `syrupy` + sus dependencias.
- `tests/test_mariadb.py` - retirados los DOS decoradores `optional_engine`; se conserva `integration`.
- `tests/test_redis_cache.py` - `pytestmark` sin `optional_engine`; comentario reescrito (Redis es requerido desde la Fase 2).
- `tests/test_ci_harness.py` - `TestCheckCoverageFloors` (7 tests) cubriendo todo el `<behavior>`.
- `.github/workflows/ci.yml` - job `test` extendido (servicios mariadb+redis, `--extra cache`, 4 motores requeridos); job `engine-heavy` nuevo; job `coverage` con `needs: [test, engine-heavy]`, `pattern: coverage-*` y el gate de pisos.
- `.gitignore` - `coverage.json` (artefacto generado por el job `coverage`).

## Decisions Made

- **Pin exacto de `syrupy`.** El formato de serialización de los `.ambr` está versionado, igual que la salida de `ruff format`; sin pin, CI podría resolver una versión más nueva que reformatee los snapshots y romper un PR no relacionado. Actualizar el pin es un cambio deliberado + `--snapshot-update`.
- **Snapshots como gate, no advisory.** syrupy es *sound*: un snapshot ausente FALLA (verificado borrando el `.ambr`). Se acepta el default estricto de snapshots huérfanos; **no** se añade `--snapshot-warn-unused`.
- **Promoción en el mismo commit (Pitfall H).** Retirar el marcador sin añadir el servicio (o al revés) deja los tests deseleccionados y CI verde sin verificar nada. Se hizo en un único commit.
- **Selección por fichero en `engine-heavy`.** `test_mssql.py`/`test_oracle.py` conservan `optional_engine` para que el job `test` los deseleccione; filtrar por marker en el job pesado lo dejaría probando cero tests.
- **`FREEPDB1` explícito.** La imagen ligera de CI (`gvenzl/oracle-free`) usa un service name distinto del `XEPDB1` de `docker-compose.yml` (`gvenzl/oracle-xe`).
- **Sin pisos de adaptador todavía.** En la corrida equivalente a CI `oracle.py` mide 16% porque Oracle está deseleccionado; un piso fijado antes de que existan los jobs de motor es una ficción. Se fijan cuando `engine-heavy` esté verde (su cobertura ya fluye al job `coverage` vía `coverage-*`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Las referencias de línea del plan para la Task 3 estaban obsoletas**
- **Found during:** Task 3 (promoción de MariaDB/Redis).
- **Issue:** El plan decía que `tests/test_mariadb.py` tenía UN decorador `optional_engine` en la línea 52. En realidad hay **DOS** decoradores (líneas 83 y 114, clases `TestMariadbLifecycle` y `TestMariadbParity`). Además el comentario de `tests/test_redis_cache.py` (líneas 9-10) contenía el literal `optional_engine`, lo que hacía imposible el criterio `grep -c "optional_engine" == 0`.
- **Fix:** Se retiraron ambos decoradores de MariaDB y se reescribió el comentario de Redis para reflejar la nueva realidad (sin el literal).
- **Files modified:** `tests/test_mariadb.py`, `tests/test_redis_cache.py`
- **Verification:** `grep -c "optional_engine" tests/test_mariadb.py tests/test_redis_cache.py` → 0 en ambos; `tests/test_pytest_config.py` (11 passed) confirma que ambos ficheros siguen aportando tests `integration`.
- **Committed in:** `d6ad923` (Task 3)

**2. [Rule 2 - Missing Critical] `coverage.json` quedaba sin rastrear**
- **Found during:** Task 4 (validación local del gate).
- **Issue:** El nuevo step de CI genera `coverage.json` en la raíz; ejecutar el gate en local dejaba un fichero sin rastrear. `.gitignore` solo tenía `.coverage*` (que no cubre `coverage.json`, sin punto inicial).
- **Fix:** Se añadió `coverage.json` a `.gitignore` con comentario; el fichero generado se borró.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short` limpio tras `rm coverage.json`.
- **Committed in:** `f6a7be6` (Task 4 GREEN)

**3. [Rule 1 - Bug] RUF003 por un carácter `×` ambiguo en un comentario**
- **Found during:** Task 2 (`ruff check`).
- **Issue:** Un comentario de `tests/test_sql_snapshots.py` usaba `×` (MULTIPLICATION SIGN), que ruff marca como RUF003.
- **Fix:** Sustituido por `x`.
- **Files modified:** `tests/test_sql_snapshots.py`
- **Verification:** `uv run ruff check encino_orm tests tools` exit 0.
- **Committed in:** `5a3712b` (Task 2)

---

**Total deviations:** 3 auto-fixed (1 blocking por drift del plan, 1 missing-critical de higiene, 1 bug de lint).
**Impact on plan:** Sin scope creep. La desviación 1 era necesaria para satisfacer el criterio de aceptación (marcadores a 0); la 2 evita dejar un artefacto generado sin rastrear; la 3 es cosmética.

## Issues Encountered

- El marker `syrupy_snapshot` que registra el plugin **no** rompe `--strict-markers`: `uv run pytest --collect-only -q -m syrupy_snapshot` sale 0. No fue necesario declararlo en `markers` de `pyproject.toml` (riesgo A4 de la investigación, resuelto empíricamente).
- `filterwarnings = ["error"]` no convirtió ningún warning de syrupy en fallo en el camino feliz; no se añadió ninguna entrada a la allowlist (D-07 intacta).
- Los techos ad-hoc de parámetros de MSSQL (2100) y Oracle (65535) siguen **NO verificados**; la sonda manual queda pendiente en el job `engine-heavy` (documentada en el YAML y en `02-VALIDATION.md`).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- La Fase 2 queda completa: DIAL-01…DIAL-09 entregados y el gate que los sostiene (snapshots + matriz + pisos) montado.
- **Registrado para una fase futura:** el filtro `name=` de `list_tables` está roto en 4 de 6 motores (ver `deferred-items.md`).
- **Registrado para la fase siguiente:** fijar los pisos de cobertura de adaptador (incluido `oracle.py`) a partir del primer run verde de `engine-heavy`.
- **Verificación manual pendiente (no automatizable desde el host):** rama scratch quitando el servicio MariaDB del job `test` → el job debe quedar ROJO; sonda del techo ad-hoc de parámetros en `engine-heavy`.

## TDD Gate Compliance

- RED: `78cd767` (`test(02-05): add failing tests for the per-module coverage floors gate`) — falla con `ModuleNotFoundError: No module named 'tools.ci.check_coverage_floors'`.
- GREEN: `f6a7be6` (`feat(02-05): per-module coverage floors gate over coverage json`) — 7 passed.
- REFACTOR: no aplica.

## Self-Check: PASSED

- `tests/test_sql_snapshots.py` — FOUND
- `tests/__snapshots__/test_sql_snapshots.ambr` — FOUND
- `tools/ci/check_coverage_floors.py` — FOUND
- Commit `5a3712b` — FOUND
- Commit `d6ad923` — FOUND
- Commit `78cd767` — FOUND
- Commit `f6a7be6` — FOUND

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*
