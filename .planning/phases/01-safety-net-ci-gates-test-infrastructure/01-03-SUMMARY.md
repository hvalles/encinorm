---
phase: 01-safety-net-ci-gates-test-infrastructure
plan: 03
subsystem: testing
tags: [pytest, pytest-asyncio, pytest-cov, coverage, markers, strict-markers, filterwarnings, ratchet, github-actions, ci, combine]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-01: ruff 0.16.8 pineado + job `lint` bloqueante (los ficheros nuevos deben nacer format/lint-clean)"
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-02: pytest-cov 7.1.0 y coverage 7.16.1 ya instalados; jobs `typecheck` y `deps` ya en ci.yml"
provides:
  - "`[tool.pytest.ini_options]` endurecido: `--strict-markers`, `xfail_strict = true`, `filterwarnings = [\"error\"]` con allowlist vacia comentada, ambos loop scopes `\"function\"` y los cuatro markers registrados"
  - "Markers `integration` (41) y `optional_engine` (13) aplicados por mapa; el comando de `README.md:130` (`-m \"not integration\"`) pasa de no-op a real"
  - "`[tool.coverage.run]` (`source_pkgs`, `branch`, `parallel`) y `[tool.coverage.report]` (`fail_under = 82`, ratchet no-baja) en pyproject.toml"
  - "Job `coverage` en ci.yml: descarga los artefactos de las cuatro patas, `coverage combine` y `coverage report` como gate bloqueante"
  - "`tests/test_pytest_config.py`: 11 guards que prueban presencia Y funcion de cada knob (sondas de subprocess)"
  - "`.gitignore` con el glob `.coverage*`"
affects: [01-04, 01-05, "Fase 2 (sube el piso de cobertura y anade pisos por dialecto sobre el seam `dialects/`)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Knob de config probado dos veces: como valor leido de pyproject.toml y como comportamiento real de un pytest hijo (sonda en tmp_path)"
    - "Ratchet no-baja anclado a la medicion equivalente a CI, nunca a la local"
    - "Guard de regresion de seleccion por fichero: cada fichero de motor debe aportar >=1 test `integration`"
    - "Gate probado por fallo inducido, no por corrida verde"

key-files:
  created:
    - tests/test_pytest_config.py
  modified:
    - pyproject.toml
    - .github/workflows/ci.yml
    - .gitignore
    - tests/test_mysql.py
    - tests/test_postgresql.py
    - tests/test_mariadb.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_redis_cache.py

key-decisions:
  - "El piso de cobertura se fija en 82 contra el 83% equivalente a CI (medido hoy: 84.42% con `-m \"not optional_engine\"`), NO contra el 88% local con los seis motores: en CI solo corren MySQL y PostgreSQL y `oracle.py` cae del 59% al 16% (Pitfall 2b). Fase 2 lo sube (D-04/D-06)"
  - "El guard de seleccion de markers se refuerza con una comprobacion por fichero de motor: la asercion `> 0` del plan no detectaba la retirada del `pytestmark` de un solo fichero (quedaban 26 tests `integration`), de modo que el fallo inducido exigido por el plan habria pasado en verde"
  - "El fichero de guards usa `subprocess` con `-c pyproject.toml`, la unica forma de probar que un knob es funcional y no solo presente; se paga con una entrada `S603` en `per-file-ignores` (el comando lleva rutas de `tmp_path` y no puede ser literal)"
  - "`filterwarnings` arranca con la allowlist vacia: la suite se verifico sin warnings bajo `-W error`; cualquier warning nuevo debe fallar (D-07)"
  - "`--strict-markers` NO valida las expresiones `-m`: por eso el marker se aplica a los tests (Task 2) y no basta con registrarlo"
  - "El `-m \"not optional_engine\"`, `ENCINO_ORM_REQUIRE_ENGINES` y el gate JUnit NO se anaden aqui: son del plan 01-04 y anadirlos haria inatribuible su prueba de fallo inducido"

patterns-established:
  - "Guard de config con sonda de subprocess cacheada (`functools.cache`) para no repetir la recoleccion entre dos aserciones"
  - "Comentario en español en la config que registra fecha de medicion, cifra usada, cifra descartada y fase que levanta el ratchet"

requirements-completed: [CI-05, CI-06]

# Metrics
duration: 8min
completed: 2026-09-17
---

# Phase 1 Plan 03: Harness de pytest endurecido y cobertura por pata con ratchet

**`--strict-markers` + `xfail_strict` + `filterwarnings = ["error"]` con allowlist vacía, ambos loop scopes fijados a `"function"` y los cuatro markers registrados y aplicados (41 `integration` / 13 `optional_engine`), de modo que el comando de `README.md:130` deja de ser un no-op; y `pytest-cov` cableado con `parallel = true`, `COVERAGE_FILE` por pata de la matriz, un job `coverage` que combina y un ratchet no-baja en 82 anclado al 83% equivalente a CI — todo probado por `tests/test_pytest_config.py` y por dos fallos inducidos.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-09-17T23:14:02Z
- **Completed:** 2026-09-17T23:22:15Z
- **Tasks:** 3
- **Files modified:** 10 (1 creado, 9 modificados)

## Accomplishments

- `[tool.pytest.ini_options]` pasó de cuatro claves a un harness endurecido: `addopts = "-ra --strict-markers"`, `xfail_strict = true`, `filterwarnings = ["error"]` con allowlist vacía y comentario de política, `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope` a `"function"`, y los cuatro markers registrados con descripción.
- **Cero arreglos mínimos hicieron falta** para activar los knobs: la suite ya era warning-free bajo `-W error`, no tenía xfails ni skips no marcados y el único marker en uso era `pytest.mark.asyncio`. El commit de Task 1 es puramente de configuración (D-09 respetado: 4 `pytest.raises(Exception)` y 8 `pytest.skip` antes y después).
- Los markers se aplican por mapa: `pytestmark` a nivel de módulo en `test_mysql.py` y `test_redis_cache.py`, decoradores por clase viva en los cuatro ficheros mixtos, dejando sin marcar las clases unit-only (`TestPostgresInternal`, `TestMssqlInternal`, `TestOracleInternal` y los dos tests unit de `test_mariadb.py`) para conservar su cobertura sin motor.
- **El comando documentado en `README.md:130` (`uv run pytest -m "not integration"`) pasa de no-op a real**: antes seleccionaba los 510 tests; ahora selecciona 480 y deselecciona los 41 `integration`.
- `pytest-cov` cableado: `COVERAGE_FILE: .coverage.py${{ matrix.python-version }}` por pata, `--cov-report=` para diferir el reporte, `upload-artifact@v4` con `include-hidden-files: true` (obligatorio: `.coverage.*` es un fichero oculto), y un job `coverage` nuevo (`needs: [test]`) que descarga con `merge-multiple: true`, ejecuta `coverage combine` y aplica el gate con `coverage report`.
- `tests/test_pytest_config.py` (11 guards) prueba **presencia y función** de cada knob: dos sondas de subprocess (marker no registrado → colección fallida; `warnings.warn` → test fallido) y la selección de markers con cobertura por fichero de motor.
- **Ambos gates probados por fallo inducido** (transcripciones abajo): `fail_under = 99` → `coverage report` sale 2; quitar el `pytestmark` de `tests/test_mysql.py` → `tests/test_pytest_config.py` sale 1.
- `ruff check` / `ruff format --check` / `uv run mypy encino_orm` siguen en 0 (sin regresión de 01-01/01-02); `# noqa` sigue en 0.

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: endurecer `[tool.pytest.ini_options]`** — `481fcf4` (feat) — sin arreglos mínimos
2. **Task 2: aplicar `integration` / `optional_engine` por mapa** — `b77ec14` (feat)
3. **Task 3: cablear pytest-cov, ratchet 82 y guards de config** — `b39746d` (feat)

**Plan metadata:** (este commit) (docs: complete plan)

## Files Created/Modified

- `pyproject.toml` — `[tool.pytest.ini_options]` endurecido, `[tool.coverage.run]`, `[tool.coverage.report]` y `per-file-ignores` `S603` para el fichero de guards
- `tests/test_pytest_config.py` — **nuevo**; 11 guards en cuatro clases (`TestPyprojectHardening`, `TestStrictMarkersBehaviour`, `TestWarningsAsErrors`, `TestMarkerSelectionRegression`)
- `.github/workflows/ci.yml` — `COVERAGE_FILE` + `--junitxml` + `--cov*` en el step de test; step de `upload-artifact` con `if: always()`; job `coverage` nuevo
- `.gitignore` — `.coverage` (exacto) → `.coverage*` (glob) con comentario
- `tests/test_mysql.py`, `tests/test_redis_cache.py` — `pytestmark` a nivel de módulo
- `tests/test_postgresql.py`, `tests/test_mariadb.py`, `tests/test_mssql.py`, `tests/test_oracle.py` — decoradores `@pytest.mark.integration` (+ `optional_engine` en los tres opcionales) sobre las clases vivas

## Configuración final de pytest

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
asyncio_default_test_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"
xfail_strict = true
filterwarnings = ["error"]          # allowlist vacia; solo con justificacion escrita
markers = [integration, optional_engine, concurrency, benchmark]
```

**Estado verificado antes de activar (research §Code Examples):** 0 xfails, 0 `@pytest.mark.skip`, 0 `skipif`, 0 `importorskip`, 0 warnings bajo `-W error`. Activarlos costó **cero arreglos**.

## Selecciones de markers (medidas)

| Comando | Antes (baseline) | Después de Task 2 | Después de Task 3 |
|---------|------------------|-------------------|-------------------|
| `uv run pytest -q` | `510 passed` | `510 passed` | `521 passed` (510 + 11 guards) |
| `-m "integration"` | 510 (no-op: **todos** seleccionados) | **41** | **41** |
| `-m "optional_engine"` | 510 (no-op) | **13** | **13** |
| `-m "not integration"` | 510 (no-op) | **469** | **480** |
| `-m "not optional_engine"` | 510 (no-op) | **497** | **508** |

Los conteos de Task 2 son exactamente los del plan (41 / 13 / 469 / 497). Los de Task 3 incorporan los 11 tests nuevos de `tests/test_pytest_config.py`, que son `not integration` y `not optional_engine`; el total pasa de 510 a 521.

## Cobertura: medición, piso y justificación

| Escenario | Comando | Total | Nota |
|-----------|---------|-------|------|
| Equivalente a CI (local, solo requeridos) | `COVERAGE_FILE=.coverage.local uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=` | **84.42%** (508 passed, 13 deselected) | Es la cifra contra la que se ancla el piso |
| Todos los motores (local, seis en Docker) | `COVERAGE_FILE=.coverage.full uv run pytest -q --cov=encino_orm --cov-branch --cov-report=` | **87.69%** (521 passed) | Reproduce el ~88% de la investigación; **no** se usa para el piso |
| Investigación (referencia) | equivalente a CI, 475 tests | 83% | Cifra histórica de `01-RESEARCH.md`; mismo orden, comando ligeramente distinto |
| **Piso elegido** | `[tool.coverage.report].fail_under` | **82** | Un punto por debajo del equivalente a CI |

**Por qué 82 y no 88:** en CI solo existen los servicios MySQL y PostgreSQL, así que los tests de los motores opcionales se excluyen y `oracle.py` cae del 59% al 16% de cobertura. Un piso anclado al 88% local fallaría en la primera corrida de CI (Pitfall 2b). La medición, la cifra descartada y la fase que sube el piso (Fase 2, D-04/D-06) quedan registradas como comentario en español junto a `fail_under`.

**Hallazgo empírico sobre el nombrado de artefactos:** con `pytest-cov` 7.1.0, tras la corrida el fichero en disco se llama exactamente `$COVERAGE_FILE` (`.coverage.local`), no `.coverage.local.<host>.<pid>.<rand>`: pytest-cov combina en proceso al terminar. `parallel = true` sigue siendo obligatorio (y el glob `.coverage.py<version>*` del `upload-artifact` cubre ambos nombrados), pero el `.gitignore` se ajustó para describir las dos formas reales. La conclusión de W4 no cambia: la entrada exacta `.coverage` **no** captura `.coverage.local` ni `.coverage.py3.10`, así que el glob `.coverage*` es el que hace el trabajo.

## Induced-failure proofs

**1. Ratchet de cobertura — `fail_under = 99` (temporal) → `uv run coverage report`:**

```text
$ uv run coverage report
----------------------------------------------------------------------------------
TOTAL                                   4321    588   1194    159  84.4%
Coverage failure: total of 84.4 is less than fail-under=99.0
REPORT_EXIT_WITH_99=2
$ # fail_under restaurado a 82
$ uv run coverage report
TOTAL                                   4321    588   1194    159  84.4%
REPORT_EXIT_WITH_82=0
```

**2. Guard de selección de markers — `pytestmark` retirado de `tests/test_mysql.py`:**

```text
$ uv run pytest tests/test_pytest_config.py -q
E           AssertionError: tests/test_mysql.py no aporta ningun test marcado como integration;
E           el comando documentado en README.md:130 volveria a ser un no-op
FAILED tests/test_pytest_config.py::TestMarkerSelectionRegression::test_cada_fichero_de_motor_aporta_tests_de_integracion
1 failed, 10 passed in 4.47s
GUARD_EXIT=1
$ # pytestmark restaurado
$ uv run pytest tests/test_pytest_config.py -q
11 passed in 4.44s
GUARD_EXIT=0
```

**3 y 4. Sondas de `--strict-markers` y de `filterwarnings = ["error"]`:** no son demostraciones manuales, son los tests `TestStrictMarkersBehaviour::test_marker_no_registrado_falla_la_coleccion` y `TestWarningsAsErrors::test_warning_emitido_falla_el_test`, que escriben la sonda en `tmp_path`, la ejecutan con `-c pyproject.toml` y **afirman `returncode != 0`**. Ambos pasan, de modo que la prueba es permanente y no una transcripción puntual.

## Coste de wall time de los guards

`tests/test_pytest_config.py` tarda **~4.1–5.4 s** en solitario (4 subprocess de pytest: dos sondas y dos recolecciones, una de ellas cacheada con `functools.cache`). La suite completa pasa de ~6 s a **~12–16 s** (con `--cov` activo, ~20–22 s). Esto **supera el presupuesto de ~8 s** de `01-VALIDATION.md` §Sampling Rate; el coste queda declarado en un comentario en español dentro del propio fichero, como pide el plan, y en esta tabla. Se mantiene el número de subprocess en cuatro (el mínimo para probar funcionalmente `--strict-markers`, `filterwarnings` y la selección de markers).

## Verification (plan-level)

| Comando | Resultado |
|---------|-----------|
| `uv run pytest -q` | `521 passed` (510 preexistentes + 11 guards) |
| `uv run pytest tests/test_pytest_config.py -q` | `11 passed` |
| `uv run pytest --collect-only -q -m "integration"` | `41/521 tests collected` |
| `uv run pytest --collect-only -q -m "optional_engine"` | `13/521 tests collected` |
| `uv run pytest --collect-only -q -m "not integration"` | `480/521 tests collected` |
| `uv run pytest --collect-only -q -m "not optional_engine"` | `508/521 tests collected` |
| `COVERAGE_FILE=.coverage.local uv run pytest -q -m "not optional_engine" --cov=encino_orm --cov-branch --cov-report=` | exit 0, `Total coverage: 84.42%` |
| `uv run coverage combine` | exit 0 (`Combined 1 file`) |
| `uv run coverage report` | exit 0, `TOTAL 84.4%` |
| `grep -c 'continue-on-error' .github/workflows/ci.yml` | `0` |
| `yaml.safe_load(ci.yml)` | parsea; jobs = `test, lint, typecheck, deps, coverage` |
| `.gitignore` contiene el literal `.coverage*` | sí |
| `uv run ruff check encino_orm tests` | `All checks passed!` (exit 0) |
| `uv run ruff format --check encino_orm tests` | `102 files already formatted` (exit 0) |
| `uv run mypy encino_orm` | `Success: no issues found in 56 source files` (exit 0) |
| `grep -rn "# noqa" encino_orm tests \| wc -l` | `0` |
| `git status --porcelain` tras la corrida de cobertura | solo los ficheros de la tarea (`.coverage*` ignorados) |

## Decisions Made

- **El piso se ancla al escenario equivalente a CI, medido hoy, no a la cifra histórica.** El equivalente a CI mide 84.42% (la investigación decía 83% con un comando algo distinto); el piso se deja en 82 igualmente, un punto por debajo, para absorber el ruido entre plataformas y versiones de Python (la investigación no detectó condicionales de plataforma en `encino_orm/`, pero la matriz cubre 3.10–3.13).
- **Refuerzo del guard de selección (desviación consciente).** La aserción `> 0` del plan no detectaba retirar el `pytestmark` de un solo fichero (quedaban 26 tests `integration`), así que el fallo inducido exigido por el propio plan habría pasado en verde. Se añadió una comprobación de que cada uno de los seis ficheros de motor aporta al menos un test `integration` — es lo que convierte T-01-07 en una mitigación real.
- **`subprocess` con `-c pyproject.toml` como única vía de prueba funcional.** No hay forma de probar que `--strict-markers` o `filterwarnings` *funcionan* sin lanzar un pytest hijo con la config del repositorio. El coste (wall time y una entrada `S603`) está acotado y declarado.
- **`.gitignore`: se reemplaza `.coverage` por `.coverage*` en lugar de añadir una línea redundante.** El glob cubre la entrada exacta y los artefactos por pata; el literal `.coverage*` se verificó presente (W4).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `ruff` S603 bloquea el fichero de guards recién creado**
- **Found during:** Task 3 (tras crear `tests/test_pytest_config.py`)
- **Issue:** el job `lint` de 01-01 (bloqueante) falla con `S603 subprocess call: check for execution of untrusted input` en `_run_pytest`. Se verificó empíricamente que la regla se dispara ante **cualquier** elemento no literal de la lista de comando (una ruta de `tmp_path`), y que ni `shell=False` ni construir el comando en una variable la satisfacen. `sys.executable` sí está permitido, pero la ruta de la sonda es dinámica por necesidad.
- **Fix:** entrada acotada `"tests/test_pytest_config.py" = ["S603"]` en `[tool.ruff.lint.per-file-ignores]` con comentario en español que explica por qué no hay entrada no confiable y en qué se levantaría (el fixture `pytester`). Se prefirió `per-file-ignores` a `# noqa` para no romper el invariante `# noqa = 0` establecido en 01-01.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run ruff check encino_orm tests` → exit 0; `grep -rn "# noqa" encino_orm tests | wc -l` → `0`.
- **Committed in:** `b39746d` (Task 3)

**2. [Rule 2 - Missing Critical] El guard de selección de markers no detectaba la retirada de un solo `pytestmark`**
- **Found during:** Task 3, al preparar el fallo inducido que el plan exige
- **Issue:** el plan pide «temporarily remove the module-level `pytestmark` from `tests/test_mysql.py`, confirm `uv run pytest tests/test_pytest_config.py -q` fails». Con la aserción especificada (`-m "integration"` selecciona `> 0`), retirar ese `pytestmark` deja 26 tests seleccionados: el guard **no** falla y el criterio de aceptación sería inalcanzable. La amenaza T-01-07 (borrar un `pytestmark` revierte el comando del README a un no-op) quedaba sin cubrir.
- **Fix:** se añadió `test_cada_fichero_de_motor_aporta_tests_de_integracion`, que recoge los node IDs de `-m "integration"` y exige que cada uno de los seis ficheros de motor aporte al menos uno. La recolección se cachea con `functools.cache` para no duplicar subprocess.
- **Files modified:** `tests/test_pytest_config.py`
- **Verification:** fallo inducido reproducido (exit 1 con el mensaje esperado) y restaurado (exit 0); ver la sección de fallos inducidos.
- **Committed in:** `b39746d` (Task 3)

**3. [Rule 1 - Bug] La descripción de los artefactos de cobertura en `.gitignore`/`pyproject.toml` era inexacta**
- **Found during:** Task 3 (verificación de la nomenclatura real)
- **Issue:** el plan y la investigación afirman que el artefacto por pata se llama `.coverage.py3.10.<host>.<pid>.<rand>`. Medido con pytest-cov 7.1.0: tras la corrida el fichero en disco es exactamente `$COVERAGE_FILE` (pytest-cov combina en proceso al terminar), sin sufijo. Un comentario que afirmase lo contrario sería documentación falsa.
- **Fix:** los comentarios de `.gitignore` y de `[tool.coverage.run]` describen ambas formas reales (`.coverage.py3.10` y, cuando aplica el sufijo paralelo, `.coverage.py3.10.<host>.<pid>.<rand>`). `parallel = true` se mantiene (requisito del plan y de `coverage combine`) y el glob del `upload-artifact` ya cubre las dos.
- **Files modified:** `.gitignore`, `pyproject.toml`
- **Verification:** `ls -la .coverage.probe*` tras una corrida con `COVERAGE_FILE=.coverage.probe` muestra exactamente `.coverage.probe`.
- **Committed in:** `b39746d` (Task 3)

**4. [Rule 3 - Medición] Los conteos absolutos de `-m` y del total de la suite del plan no contemplan el fichero de guards que el propio plan manda crear**
- **Found during:** Task 3
- **Issue:** el plan exige, en el mismo task, crear `tests/test_pytest_config.py` (11 tests) y que `uv run pytest -q` reporte `510 passed`; además Task 2 fija 469/497 para `not integration`/`not optional_engine`. Los 11 tests nuevos son `not integration` y `not optional_engine`, así que los conteos pasan a 521 / 480 / 508. Los conteos **exactos de Task 2** (41 / 13 / 469 / 497) sí se reprodujeron tal cual, antes de crear el fichero.
- **Fix:** ninguno sobre el código; se documenta la reconciliación (510 preexistentes + 11 guards = 521) y el guard de selección se expresa en términos **relativos** (`> 0`, `< total`), no absolutos, para no ser frágil ante tests nuevos.
- **Files modified:** ninguno
- **Verification:** `uv run pytest -q` → `521 passed`; `-m` → 41 / 13 / 480 / 508; 521 − 11 = 510.
- **Committed in:** n/a (documentado en este SUMMARY)

---

**Total deviations:** 4 (3 bloqueantes/correcciones, 1 de medición).
**Impact on plan:** Ninguna desviación cambia el alcance ni el comportamiento del ORM. La desviación 2 es la única que amplía lo planificado, y lo hace para que el fallo inducido exigido por el propio plan sea alcanzable. La 1 es una supresión acotada a un fichero, comentada y con fase de levantamiento. Sin scope creep.

## Issues Encountered

- **El presupuesto de ~8 s de feedback se supera.** Los guards añaden ~4–5 s por sus cuatro subprocess. Se acepta porque la alternativa (no probar la función de los knobs) dejaría el gate como decoración; el coste queda declarado en el fichero y en este SUMMARY.
- **`--strict-markers` no valida las expresiones `-m`** (confirmado de nuevo: registrar un marker no lo hace útil). Por eso la aplicación a los tests (Task 2) y el guard de selección (Task 3) son ambos necesarios.
- **La cifra equivalente a CI medida hoy (84.42%) es superior al 83% de la investigación.** Probablemente porque el conjunto de tests excluidos por `-m "not optional_engine"` no es idéntico al de la medición histórica (los tests unit de motores opcionales siguen corriendo). El piso de 82 absorbe la diferencia en ambos sentidos y el comentario de config cita las dos cifras.

## Threat Flags

Ninguno nuevo. Las mitigaciones del registro de amenazas están implementadas y probadas:

| Threat ID | Estado |
|-----------|--------|
| T-01-03 (knobs de pytest inertes) | Mitigado: cada knob se comprueba como config **y** como comportamiento; `filterwarnings = ["error"]` con allowlist vacía, `xfail_strict = true` y `--strict-markers` efectivos |
| T-01-06 (`fail_under` mal anclado) | Mitigado: 82 contra el equivalente a CI medido, con el razonamiento comentado; fallo inducido (99 → exit 2) registrado |
| T-01-07 (marker aplicado y luego borrado en silencio) | Mitigado y **reforzado**: guard por fichero de motor; fallo inducido (exit 1) registrado |
| T-01-08 (artefactos de cobertura en el artifact store) | Aceptado: solo rutas y números de línea, sin secretos; `permissions: contents: read` intacto |
| T-01-04 (supply chain de `setup-uv` en el job nuevo) | Mitigado: el job `coverage` reutiliza `version: "0.12.15"` |

**No hay instalaciones de paquetes en este plan** — `pytest-cov` y `coverage` ya entraron en `[dependency-groups].dev` en 01-02, tras su checkpoint de legitimidad.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Listo para 01-04:** `integration` / `optional_engine` ya están aplicados, así que el interruptor `ENCINO_ORM_REQUIRE_ENGINES` puede sustituir los 8 `pytest.skip` por `engine_unavailable(...)` sin tocar markers; y el step de test ya emite `--junitxml=junit.xml` y `--cov*`, de modo que 01-04 solo añade `-m "not optional_engine"`, el env del interruptor y el gate de skips. **Deliberadamente ausentes aquí** para que su prueba de fallo inducido sea atribuible.
- **Listo para 01-05:** la suite de caracterización del pool correrá bajo `--strict-markers` y `filterwarnings = ["error"]`; cualquier warning que introduzca fallará (y debe fallar).
- **Para Fase 2:** el piso global sube y se añaden pisos por dialecto sobre el seam `dialects/` (D-04/D-06). El mecanismo (`parallel`, `COVERAGE_FILE` por pata, `coverage combine`) ya está montado y probado.
- **Nota para todo fichero nuevo:** debe nacer `ruff check`/`ruff format`-clean, mypy-clean bajo el ratchet, y ahora además libre de warnings (o la suite falla).
- **Primera corrida real de CI:** si `coverage combine` reportase «No data to combine», la mitigación prevista es añadir `[tool.coverage.paths]` (asumption A3); no se añadió especulativamente.

---

*Phase: 01-safety-net-ci-gates-test-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `tests/test_pytest_config.py` y `01-03-SUMMARY.md` existen en disco.
- Los commits `481fcf4`, `b77ec14` y `b39746d` existen en el historial.
- `uv run pytest -q` → `521 passed`; `uv run pytest tests/test_pytest_config.py -q` → `11 passed`.
- `uv run ruff check encino_orm tests` → exit 0; `uv run ruff format --check encino_orm tests` → exit 0; `uv run mypy encino_orm` → exit 0.
- `uv run coverage report` → exit 0 con `fail_under = 82`; `yaml.safe_load(ci.yml)` parsea con los cinco jobs; `.gitignore` contiene `.coverage*`.
- `git status --porcelain` limpio de artefactos de cobertura.
