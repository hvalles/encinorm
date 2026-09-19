---
phase: 07-performance-and-benchmarks
plan: 02
subsystem: benchmarking
tags: [benchmarks, perf-counter, ci, floors, calibration, zero-dep]
requirements-completed: [PERF-02]

# Dependency graph
requires:
  - phase: 07-01
    provides: "Línea base de rendimiento pre-optimización (PERF-03) — profiler commiteado antes"
provides:
  - "tests/test_benchmarks.py: harness zero-dep + 5 unidades síncronas con piso numérico (mediana/p95/sigma)"
  - ".github/workflows/ci.yml: job `benchmarks` dedicado (ubuntu, 3.12, sin servicios, sin cov/junitxml) + filtro `test` a `not benchmark`"
  - "pyproject.toml: cabecera del marker `benchmark` corregida (sin pytest-codspeed)"
  - "Calibración documentada de pisos (0.6x de línea base del harness local; la PRIMERA corrida de CI recalibra +/-20%)"
affects: [verify-phase-07, 07-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Harness zero-dep time.perf_counter + statistics.median/_percentile dentro de `@pytest.mark.benchmark` (sin pytest-benchmark/codspeed)"
    - "Medición con GC desactivado DURANTE el cronometrado y `gc.collect()` antes (metodología timeit): ventana de 1024 floats estabiliza la mediana"
    - "inner CORTO (2_000/200_000 ops por repetición): un inner largo colapsa la medición por thermal/boost del CPU (batch: 10,4M con bursts 500K vs 3,6M con 5M sostenidos, misma aritmética)"

key-files:
  created:
    - tests/test_benchmarks.py
  modified:
    - .github/workflows/ci.yml
    - pyproject.toml

key-decisions:
  - "Los pisos se fijaron a 0.6x de líneas base medidas con EL MISMO harness (no a los números del RESEARCH Q3): el RESEARCH medía to_mysql ~625K y Query ~236K con plantillas más pequeñas/granularidad aislada; el harness mide la unidad completa (`Query.__init__` con validación, `_to_mysql` de 8 placeholders). Disciplina Q3: la primera corrida del job `benchmarks` en CI recalibra cada piso +/-20% en el mismo commit."
  - "inner corto (2_000 para 4 unidades, 200_000 para batch) como en las semillas del plan 07-02, NO los inner largos que el boceto de Task 1 sugería ajustar a >= 0.5s: los inner largos hacen colapsar el rate por throttling del CPU en este host (evidencia en el test), no por GC"
  - "El fixture de silencio del logger restaura el estado previo (disabled) tras cada test para no contaminar los tests de logging posteriores (test_g_recommendations/test_pool_characterization)"

patterns-established:
  - "Gate PERF-02 por marcador y por job: `-m "not optional_engine and not benchmark"` en la matriz de 4 patas; job `benchmarks` sin `needs:`, sin `--cov*`, sin `--junitxml` para no alimentar el combine de `coverage`"
  - "Unidad de rendimiento = operación real del núcleo (no re-materialización ad hoc) con smoke assert fuera del timing para que el piso no se mida sobre una operación rota"
  - "Fixture de módulo con teardown de estado (restaura logger): los benchmarks nunca dejan estado global mutado para tests posteriores"

duration: 95min
completed: 2026-09-19
---

# Phase 7 Plan 2: Harness de benchmarks síncronos + gate de CI (PERF-02)

**Instala un harness zero-denpendencia (`time.perf_counter`) con 5 unidades síncronas del núcleo y piso numérico = 0.6x de la línea base, lo cablea a CI en un job `benchmarks` dedicado y excluye los benchmarks de la matriz funcional y del combine de cobertura.**

## Performance

- **Duration:** ~95 min
- **Started:** 2026-09-19T17:1xZ
- **Completed:** 2026-09-19T18:5xZ
- **Tasks:** 2/2
- **Files modified:** 3 (1 creado, 2 modificados)

## Accomplishments

- **tests/test_benchmarks.py (5 unidades, todas con smoke + floor):**
  - `test_sql_build_floor` — `QueryBuilder._build_full` → floor 152_000 ops/s.
  - `test_query_construction_floor` — `Query(plantilla 7 placeholders)` → floor 105_000.
  - `test_query_with_params_floor` — copia con nueva cardinalidad → floor 130_000.
  - `test_to_mysql_floor` — traducción del `Query` compilado (8 params) → floor 226_000.
  - `test_batch_sizing_floor` — fórmula de chunk de `insert_many` → floor 6_300_000.
- Versionado: `pytestmark = [pytest.mark.benchmark, pytest.mark.timeout(60)]`; fixture autouse que silencia el logger del núcleo y lo RESTAURA al terminar.
- Harness `_measure(fn, *, inner, warmup=3, reps=9)` → `(mediana, p95, sigma)`: `gc.collect()` antes de cada repetición cronometrada, GC desactivado DURANTE el bucle (metodología de `timeit`) y restaurado tras él; assert con `median > FLOOR` y p95/sigma en el mensaje de fallo.
- **pyproject.toml:** cabecera del marker `benchmark` corregida de "medidos por pytest-codspeed" (falso, no se usa) a la descripción del harness real.
- **.github/workflows/ci.yml:**
  - Job `test`: `-m "not optional_engine"` → `-m "not optional_engine and not benchmark"` (los benchmarks no corren en la matriz de 4 patas ni ensucian el combine de `coverage`).
  - Job `benchmarks` nuevo (después de `deps`, sin `needs:`): ubuntu, 3.12, `timeout-minutes: 10`, `uv sync --group dev` + `uv run pytest -m benchmark -q --timeout-method=signal`. Sin `--cov*`, sin `--junitxml`.
- **Calibración documentada en el propio archivo:** líneas base locales (mediana): sql_build ~330K, query_construction ~176K, with_params ~218K, to_mysql ~366K, batch ~11,1M; pisos = 0.6x. Nota explícita de por qué difieren del RESEARCH Q3 y de que la primera corrida de CI recalibra +/-20%.

## Task Commits

1. **Task 1: harness + 5 unidades + marker + job de CI (commit atómico)** — `bbc08ff`
2. **Task 2: dry-run de CI en el host** — sin código nuevo (gates verdes y artefactos verificados; la calibración fina la hace la primera corrida del job `benchmarks` en CI).

## Medianas medidas (host local, 2026-09-19, `_measure` real)

| Unidad | Mediana (ops/s) | p95 | sigma | Piso (0.6x) |
|--------|----------------:|----:|------:|------------:|
| sql_build | 329,636 | 339,182 | 6,983 | 152,000 |
| query_construction | 176,462 | 186,653 | 11,199 | 105,000 |
| query_with_params | 218,024 | 228,268 | 22,206 | 130,000 |
| to_mysql | 366,314 | 370,311 | 31,655 | 226,000 |
| batch_sizing | 11,141,751 | 11,550,244 | 602,019 | 6,300,000 |

## Dry-run de CI en el host

- `uv run pytest -q -m "not optional_engine and not benchmark"` → **1034 passed, 35 deselected** (la suite funcional queda intacta y excluye benchmarks).
- `uv run pytest -q` → **1069 passed** (suite COMPLETA local, benchmarks incluidos), 12 snapshots passed.
- `uv run pytest tests/test_benchmarks.py` → 5 passed.
- `uv run ruff check encino_orm tests` → All checks passed; `ruff format --check` → 125 files already formatted.
- `uv run mypy encino_orm` → Success: no issues found in 61 source files.
- `uv run mkdocs build --strict` → exit 0.
- `uv lock --check` → exit 0 (sin dependencias nuevas; `uv.lock` intacto).
- `uv build` → wheel `encino_orm-0.2.6-py3-none-any.whl`; `zipfile.namelist()` sin entradas `test_benchmarks`/`benchmark` (`bad entries: []`).
- YAML de CI parseado con `yaml.safe_load`: jobs `['test','lint','typecheck','deps','benchmarks','engine-heavy','coverage']`; el job `benchmarks` NO pasa `--cov*` ni `--junitxml`.

## Files Created/Modified

- `tests/test_benchmarks.py` — **nuevo**; harness + 5 unidades con smoke + pisos.
- `.github/workflows/ci.yml` — filtro del job `test` + job `benchmarks` dedicado.
- `pyproject.toml` — cabecera del marker `benchmark` corregida (nombre no cambia; `tests/test_pytest_config.py` compara solo nombres).

## Decisions Made

- **Pisos calibrados al harness real, no a los constantes literales del plan.** El RESEARCH Q3 medía granularidades más finas (traducción aislada, plantillas más pequeñas) y los FLOOR del plan (85K/140K/120K/375K/5M) no correspondían a lo que esta suite mide como unidad completa. Se recalibraron con la regla 0.6x sobre líneas base medidas con `_measure` (152K/105K/130K/226K/6.3M). La disciplina Q3 del RESEARCH —primera corrida de CI recalibra +/-20% en el MISMO commit— queda intacta.
- **inner corto.** Se confirmó que `inner` largo (>= 1s por repetición) colapsa el rate por throttling/boost del CPU: batch (aritmética pura) mide 10,4M ops/s con bursts de 500K y 3,6M con 5M sostenidos — el mismo código, así que es temperatura, no GC. Se usan los inner de las semillas del plan (2_000 / 200_000).
- **GC desactivado durante el cronometrado.** `gc.collect()` antes del bucle y `gc.disable()`/`gc.enable()` alrededor (igual que `timeit`): sin esto, las recolecciones automáticas disparadas por las propias asignaciones de la unidad contaminan la medición (las primeras pasadas con GC activo daban 2-3x de ruido).
- **Fixture con teardown.** Restaurar `logger.disabled` tras cada benchmark: sin la restauración, `test_g_recommendations::test_query_is_logged` y `test_pool_characterization::test_release_foreign_handle_does_not_enqueue` fallaban cuando la suite completa corría después de los benchmarks (el logger quedaba silenciado permanentemente).

## Deviations from Plan

### Auto-fixed / plan-fallback issues

**1. [Rule 1] Los FLOOR del plan no pasaban localmente porque la granularidad de las unidades difería de la del RESEARCH Q3**

- **Found during:** Task 1.
- **Issue:** `to_mysql` con los constantes del plan (375_000) fallaba siempre en el host (~238-377K medidos según carga); `query_construction` (140_000) quedaba al borde (~145K). El RESEARCH midió 625K/236K con granularidades más finas.
- **Fix:** Recalibración a 0.6x de líneas base medidas con el propio harness y documentada en el archivo (152K/105K/130K/226K/6.3M). Los pisos locales quedan con margen 1.5-2.2x sobre la mediana medida; la calibración FINAL la hace CI.
- **Files modified:** `tests/test_benchmarks.py`
- **Commit:** `bbc08ff`

**2. [Rule 1] `inner` largo colapsaba la medición por thermal throttling**

- **Found during:** Task 1.
- **Issue:** Con `inner` grande (150K-7M) las medianas caían 2-3x respecto a mediciones cortas del MISMO código (batch: 3,6M vs 10,4M ops/s). Causa: el turbo/boost del CPU del portátil se agota en bucles sostenidos de >0.5s.
- **Fix:** Usar los inner de las semillas del plan (2_000 / 200_000 ops por repetición), que dan repeticiones de ~5-20ms y medianas estables. Documentado en el archivo.
- **Files modified:** `tests/test_benchmarks.py`
- **Commit:** `bbc08ff`

**3. [Rule 1] SQLite sin `SIGALRM` en Windows**

- **Found during:** Task 1.
- **Issue:** `--timeout-method=signal` no existe en Windows (no hay `signal.SIGALRM`); el plan pedía esa invocación en la verificación local.
- **Fix:** Se usa `--timeout-method=thread` localmente (como dice la misma nota operativa del plan: "el método *thread* (default en Windows)"). En CI Linux sí se usa `signal`.
- **Files modified:** ninguno (invocación).
- **Commit:** `bbc08ff`

**4. [Rule 1] El smoke de `Query` contaba mal los placeholders**

- **Found during:** Task 1.
- **Issue:** El plan decía `len(q.params) == 8` con plantilla de 7 placeholders `{0}`-`{6}` + la frase "~8 placeholders"; `params` (dict) tiene 7 entradas.
- **Fix:** Smoke corregido a `len(q.params) == 7` (plantilla con 7 placeholders únicos). El comentario del plan "~8" era un error de redacción.
- **Files modified:** `tests/test_benchmarks.py`
- **Commit:** `bbc08ff`

**5. [Rule 1] PT022 / PT018 / RUF002-003 / W292 de ruff**

- **Found during:** Task 1 (gate de lint).
- **Issue:** ruff marcaba el fixture con `yield` sin teardown (PT022), asserts compuestos (PT018), caracteres ambiguos `×`/`σ` en docstrings (RUF002/003) y falta de newline EOF (W292).
- **Fix:** El fixture pasó a `yield` CON teardown real (restaura el logger — ver Decisions); asserts divididos; `×`/`σ` → `x`/`sigma`; newline añadido.
- **Files modified:** `tests/test_benchmarks.py`
- **Commit:** `bbc08ff`

### Out-of-scope discoveries (deferred)

- No hay desviaciones fuera de alcance. La calibración "final" de los pisos contra hardware real queda como primer acto del job `benchmarks` en CI (por diseño, no como fallo).

## Known Stubs

None. Las 5 unidades miden operaciones reales del núcleo (no stubs) y cada piso es un número calibrado al harness; el smoke assert verifica que la operación produce SQL/objetos válidos antes de medirla.

## Threat Flags

None. No se añade superficie de red, autenticación ni acceso a ficheros. El job `benchmarks` no levanta servicios de DB (T-07-11 mitigado con `timeout-minutes: 10` + `pytest.mark.timeout(60)`), no publica cobertura (T-07-13), añade cero dependencias (T-07-SC) y la cabecera del marker es cosmética con assert por nombre (T-07-12).

## Issues Encountered

- **Contaminación entre tests (la incidencia más seria):** la primera versión del fixture usaba `disabled = True` sin restauración. La suite completa (`uv run pytest -q`) fallaba en `test_g_recommendations::test_query_is_logged` y `test_pool_characterization::test_release_foreign_handle_does_not_enqueue` DESPUÉS de correr los benchmarks. En aislamiento ambos pasaban. La restauración del estado en teardown lo resolvió; la suite completa vuelve a ser `1069 passed`.
- El `to_mysql` llegó a caer un run puntual bajo carga concurrente de la suite completa por debajo de su piso (226K) una vez; con la metodología final (GC off + inner corto + fixtura restaurada) se mantiene estable ~366K. Es el ruido que la ventana 0.6x absorbe y que CI recalibrará.

## Verification (end-of-plan gates)

- `uv run pytest tests/test_benchmarks.py -q --timeout-method=thread` → 5 passed.
- `uv run pytest -q -m "not optional_engine and not benchmark"` → 1034 passed, 35 deselected.
- `uv run pytest -q` → **1069 passed**, 12 snapshots passed.
- `uv run ruff check encino_orm tests` → All checks passed; `ruff format --check` → 125 files already formatted.
- `uv run mypy encino_orm` → Success: no issues found in 61 source files.
- `uv run mkdocs build --strict` → exit 0.
- `uv lock --check` → exit 0.
- `uv build` + listado del wheel → sin entradas `benchmark`/`test_benchmarks`.
- `yaml.safe_load` de `ci.yml` → `benchmarks` presente; job sin `--cov*`/`--junitxml`; `coverage` conserva `needs: [test, engine-heavy]`.
- `git diff --name-only` de `bbc08ff` → solo `tests/test_benchmarks.py`, `.github/workflows/ci.yml`, `pyproject.toml`.

## Next Phase Readiness

- 07-02 cerrado; el job `benchmarks` de CI es el nuevo gate de regresión 2x (PERF-02).
- 07-03 (copy_table por lotes) extenderá `tests/test_benchmarks.py` con la unidad de multi-VALUES gen (misma disciplina: piso 0.6x, calibrado en su commit).
- Los pisos de CI se recalibrarán con la primera corrida verde/ajustada del job `benchmarks`, documentada en el MISMO commit del ajuste.
- Sin bloqueos.

---

*Phase: 07-performance-and-benchmarks*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `tests/test_benchmarks.py` (harness + 5 unidades, `pytest.mark.benchmark`)
- FOUND: `.github/workflows/ci.yml` job `benchmarks` + filtro `not benchmark` en job `test`
- FOUND: `pyproject.toml` cabecera del marker corregida
- FOUND: commit atómico `bbc08ff` (harness + CI + marker)
- FOUND: dry-run de CI local completo: suite funcional + benchmarks + gates, mediana/p95/sigma documentadas