---
phase: 01-safety-net-ci-gates-test-infrastructure
plan: 04
subsystem: testing
tags: [pytest, junit-xml, ci-gate, github-actions, reusable-workflow, required-engines, skip-gate, release-gate, ruff, S314]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-01: job `lint` bloqueante (ruff 0.16.8) — los ficheros nuevos deben nacer lint/format-clean"
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-02: jobs `typecheck` y `deps`; extras de CI sincronizados"
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-03: markers `integration`/`optional_engine` aplicados y el step de test ya emite `--junitxml`/`--cov*`"
provides:
  - "`tests/conftest.py`: `required_engines()` y `engine_unavailable()` — el interruptor CI-01, activado solo por env var (D-03)"
  - "Los 8 sitios de skip de motor usan `engine_unavailable(...)`; `pytest.skip` desaparece de todos los `tests/test_*.py`"
  - "`tools/ci/check_skips.py`: gate JUnit-XML stdlib-only que falla cerrado ante `skipped > 0` o XML ausente/ilegible (CI-02)"
  - "`tests/test_ci_harness.py`: 13 tests unitarios del interruptor y del gate, sin tocar ningun motor"
  - "`ci.yml`: `on.workflow_call`, `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql`, `-m \"not optional_engine\"`, `--junitxml=junit.xml` y step de gate con `if: always()`"
  - "`release.yml`: job `ci` que llama `./.github/workflows/ci.yml` + `publish: needs: [ci]` (CI-08)"
affects: [01-05, "Fase 2 (DIAL-08: extiende el conjunto de motores requeridos; estrecha los `except Exception` de los fixtures)", "Fase 8 (REL-03: OIDC)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Skip-vs-fail en el limite del fixture: un helper decide omitir o fallar segun una env var inyectada SOLO en CI"
    - "Gate post-run sobre el artefacto JUnit-XML con `if: always()` y comportamiento fail-closed (XML ausente o ilegible -> 1)"
    - "Reconciliacion marker/XML en la INVOCACION: `-m \"not optional_engine\"` deselecciona antes del run, asi que `skipped > 0` es un skip NO marcado por construccion (D-02)"
    - "CI como workflow reutilizable (`on.workflow_call`) para que `release.yml` pueda gatear `publish` con `needs:` (CI-08)"
    - "Gate probado por fallo inducido, nunca por corrida verde"

key-files:
  created:
    - tools/ci/check_skips.py
    - tests/test_ci_harness.py
  modified:
    - tests/conftest.py
    - tests/test_mysql.py
    - tests/test_postgresql.py
    - tests/test_mariadb.py
    - tests/test_mssql.py
    - tests/test_oracle.py
    - tests/test_redis_cache.py
    - .github/workflows/ci.yml
    - .github/workflows/release.yml
    - pyproject.toml

key-decisions:
  - "El gate de skips se reconcilia en la INVOCACION, no en el XML: los markers no viajan al JUnit-XML, asi que el job de motores requeridos corre con `-m \"not optional_engine\"` y los 13 tests deseleccionados no aparecen en el XML. `skipped > 0` significa entonces, por construccion, un skip NO marcado (D-02)."
  - "El interruptor es SOLO env var (`ENCINO_ORM_REQUIRE_ENGINES`), nunca auto-deteccion: la auto-deteccion es precisamente el fallo silencioso que la fase elimina (D-03). En local, sin la var, un motor ausente sigue omitiendo."
  - "`release.yml` no puede usar `needs:` sobre un job de otro fichero: CI se expone con `on.workflow_call` y `publish` llama `./.github/workflows/ci.yml`. Con `./` el workflow llamado es el del MISMO commit que el caller, la semantica correcta sobre un tag (se descarto `workflow_run`, que correria contra la rama por defecto)."
  - "El gate JUnit es un script versionado y con tests propios, no YAML inline: asi el comportamiento del gate es unit-testeable y un XML ausente/ilegible falla cerrado en vez de reventar con traceback."
  - "El `except Exception` de los 8 fixtures NO se estrecha en esta fase (Pitfall 1 del research): un typo de env var o un `ImportError` degradan a skip en local, y el interruptor lo hace irrelevante en CI porque cualquier fallo que alcance `engine_unavailable()` para un motor requerido es un fallo duro. Estrecharlo queda para Fase 2."
  - "`S314` (`xml.etree.ElementTree`) se ignora por fichero en `tools/ci/check_skips.py`, con justificacion escrita: el XML es un artefacto de build del propio job y CPython no resuelve entidades externas por defecto (T-01-11); `defusedxml` violaria la regla 'solo stdlib' del gate."

patterns-established:
  - "Helper de politica en `conftest.py` en vez de un plugin de pytest: la politica es por-fixture, no por-sesion"
  - "Nombres de test que incluyen el nombre del modulo bajo prueba (`test_check_skips_*`, `test_require_engines_*`) para que `-k` seleccione de verdad en vez de pasar en vacio"

requirements-completed: [CI-01, CI-02, CI-08]

# Metrics
duration: 12min
completed: 2026-09-17
---

# Phase 1 Plan 04: Interruptor de motores requeridos, gate JUnit y release gateado por CI

**Un motor requerido ausente pasa de omitir a FALLAR (env var inyectada solo en CI), un unico test omitido en el job requerido hace fallar un gate JUnit-XML stdlib-only con tests propios, y `release.yml` no puede publicar hasta que CI este verde — todo probado por fallo inducido (puerto 1), no por corrida verde.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-09-17T17:23:23-06:00 (tras el cierre de 01-03)
- **Completed:** 2026-09-17T17:34:00-06:00
- **Tasks:** 3 (Task 3 con ciclo TDD RED -> GREEN)
- **Files modified:** 12 (2 creados, 10 modificados)

## Accomplishments

- **CI-01 — el interruptor invierte el skip en el limite del fixture.** `tests/conftest.py` gana `required_engines()` (lee `ENCINO_ORM_REQUIRE_ENGINES`, separa por comas, `strip` + `lower`) y `engine_unavailable(engine, exc)` (falla si el motor es requerido, omite si no). Los **8 sitios de skip** de los 6 ficheros de motor se migran a `engine_unavailable(...)`; `pytest.skip` ya no aparece en ningun `tests/test_*.py` fuera de `test_ci_harness.py`.
- **CI-02 — el gate de skips existe, esta versionado y tiene tests propios.** `tools/ci/check_skips.py` (solo `sys` + `xml.etree.ElementTree`) suma el atributo `skipped` de **todos** los `<testsuite>` y devuelve 1 tanto con `skipped > 0` como con un XML ausente o ilegible (fail-closed, sin traceback).
- **La ambiguedad marker/XML se resuelve en la invocacion.** El job de motores requeridos corre con `-m "not optional_engine"`: los 13 tests opcionales se deseleccionan y **no aparecen en el XML**, asi que `skipped > 0` es un skip NO marcado por construccion (D-02).
- **CI-08 — la ruta de publicacion no puede arrancar con CI rojo.** `ci.yml` gana `on.workflow_call` y `release.yml` gana un job `ci` que llama `./.github/workflows/ci.yml` mas `publish: needs: [ci]`. `./` resuelve al mismo commit que el caller (verificado en la documentacion de GitHub), la semantica correcta sobre un tag.
- **Cero cambios de comportamiento en local.** Sin `ENCINO_ORM_REQUIRE_ENGINES`, los mismos tests que antes se omitian siguen omitiendose: la suite local no cambia (D-03).
- **Todo gate probado por fallo inducido**, nunca por corrida verde: el interruptor (fail y skip), su extensibilidad a un motor hoy opcional (mariadb) y los tres modos de salida del gate (limpio / con skips / ausente).

## Task Commits

Cada tarea se commiteó atómicamente (Task 3 siguio el ciclo TDD):

1. **Task 1: interruptor + sitios MySQL/PostgreSQL** — `ef2a8b0` (feat)
2. **Task 2: sitios de motores opcionales** — `0f864c4` (feat)
3. **Task 3 RED: tests que fallan del arnes** — `3a015d1` (test)
4. **Task 3 RED (fix de seleccion): nombres que `-k` selecciona** — `87b4725` (test)
5. **Task 3 GREEN: gate JUnit + CI requerida + release gateado** — `a59564e` (feat)

**Plan metadata:** (este commit) (docs: complete plan)

_Nota: Task 3 produjo 3 commits (2 de la fase RED y 1 de la GREEN) porque el primer RED dejo pasar en vacio los filtros `-k` del plan; ver Desviacion 2._

## Files Created/Modified

- `tests/conftest.py` — `required_engines()` y `engine_unavailable()`; `import os`; guard win32 y ambos fixtures intactos
- `tests/test_mysql.py`, `tests/test_postgresql.py`, `tests/test_mariadb.py`, `tests/test_mssql.py` (x2), `tests/test_oracle.py`, `tests/test_redis_cache.py` (x2) — los 8 `pytest.skip` sustituidos por `engine_unavailable(...)`; import `from tests.conftest import engine_unavailable`
- `tools/ci/check_skips.py` — **nuevo**; `total_skipped(path)`, `main(argv) -> int`, bloque `if __name__ == "__main__"` (que `cli.py` no necesita por ser console-script)
- `tests/test_ci_harness.py` — **nuevo**; 13 tests en 3 clases (`TestCheckSkips`, `TestRequireEngines`, `TestEngineUnavailable`) con 3 documentos XML fixture
- `.github/workflows/ci.yml` — `workflow_call`, `ENCINO_ORM_REQUIRE_ENGINES: mysql,postgresql`, `-m "not optional_engine"`, `--junitxml=junit.xml`, step `Gate — ningún test omitido` con `if: always()`
- `.github/workflows/release.yml` — job `ci` (`uses: ./.github/workflows/ci.yml`), `publish: needs: [ci]`, `version: "0.12.15"` en `setup-uv`
- `pyproject.toml` — `[tool.ruff.lint.per-file-ignores]` gana `"tools/ci/check_skips.py" = ["S314"]` con justificacion

## El interruptor y el gate (diseno)

```python
def required_engines() -> set[str]:
    raw = os.getenv("ENCINO_ORM_REQUIRE_ENGINES", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}

def engine_unavailable(engine: str, exc: Exception) -> None:
    if engine.lower() in required_engines():
        pytest.fail(f"{engine} es un motor requerido (ENCINO_ORM_REQUIRE_ENGINES) "
                    f"pero no está disponible: {exc!r}")
    pytest.skip(f"{engine} no disponible: {exc}")
```

```python
def total_skipped(path: str) -> int:
    root = ET.parse(path).getroot()
    return sum(int(ts.get("skipped", 0)) for ts in root.iter("testsuite"))
```

`main(argv)` toma `argv[1]` (default `junit.xml`), y devuelve 1 con mensaje en `sys.stderr` si hay skips o si el XML no se puede leer; 0 con linea OK en caso contrario.

## Induced-failure proofs

**1. Ruta de FALLO — motor requerido inalcanzable (CI-01):**

```text
$ ENCINO_ORM_REQUIRE_ENGINES=postgresql ENCINO_ORM_POSTGRES_PORT=1 \
    uv run pytest tests/test_postgresql.py -q
E   Failed: postgresql es un motor requerido (ENCINO_ORM_REQUIRE_ENGINES) pero no está disponible:
    ConnectionRefusedError(10061, "Connect call failed ('127.0.0.1', 1)")
ERROR tests/test_postgresql.py::TestPostgresLifecycle::test_connect_and_close - Failed...
... (13 ERROR en total)
6 passed, 13 errors in 30.33s
FAIL_PATH_EXIT=1
```

**2. Ruta de SKIP — comportamiento local preservado (D-03):**

```text
$ ENCINO_ORM_POSTGRES_PORT=1 uv run pytest tests/test_postgresql.py -q
SKIPPED [1] tests\test_postgresql.py:219: postgresql no disponible: [Errno 10061] Connect call failed ('127.0.0.1', 1)
... (13 SKIPPED en total)
6 passed, 13 skipped in 26.70s
SKIP_PATH_EXIT=0
```

**3. Extensibilidad a un motor hoy opcional (D-01, requisito de Fase 2/DIAL-08):**

```text
$ ENCINO_ORM_REQUIRE_ENGINES=mariadb ENCINO_ORM_MARIADB_PORT=1 \
    uv run pytest tests/test_mariadb.py -q
E   Failed: mariadb es un motor requerido (ENCINO_ORM_REQUIRE_ENGINES) pero no está disponible:
    OperationalError(2003, "Can't connect to MySQL server on '127.0.0.1'")
ERROR tests/test_mariadb.py::TestMariadbLifecycle::test_connect_and_close - Failed...
2 passed, 3 errors in 6.86s
MARIADB_FAIL_EXIT=1
```

**4. Gate JUnit-XML — los tres modos de salida:**

```text
$ uv run python tools/ci/check_skips.py <clean.xml>     # skipped="0"
OK: 0 tests omitidos.
CLEAN_EXIT=0

$ uv run python tools/ci/check_skips.py <skipped.xml>   # skipped="2" + skipped="1"
FALLO: 3 test(s) omitidos. Un skip en CI es un gate roto.
SKIPS_EXIT=1

$ uv run python tools/ci/check_skips.py <missing.xml>
FALLO: no se pudo leer el JUnit-XML '...gsd-missing.xml': [Errno 2] No such file or directory
MISSING_EXIT=1
```

**5. Extremo a extremo con la invocacion exacta de CI (sin `--cov`, que no altera el XML):**

```text
$ uv run pytest -q -m "not optional_engine" --junitxml=junit.xml
521 passed, 13 deselected in 14.40s
$ uv run python tools/ci/check_skips.py junit.xml
OK: 0 tests omitidos.
GATE_EXIT=0
# XML: suites=['0']  total_tests=521   (el XML no contiene los 13 deseleccionados)
```

`junit.xml` se elimino tras la prueba; el arbol queda limpio.

**6. Equivalente local de "quitar el servicio de un motor requerido" (criterio de salida de la fase):** la prueba 1 ES ese escenario — un PostgreSQL inalcanzable hace que la corrida falle en vez de pasar con skips, que es exactamente lo que hara el job de CI cuando falte el servicio.

## CI-08: lo que SI se pudo probar localmente y lo que NO

**Probado localmente (estructural y sintactico):**

- `release.yml` contiene `ci: uses: ./.github/workflows/ci.yml` y `publish: needs: [ci]`; `PYPI_API_TOKEN` y los comentarios OIDC quedan intactos.
- Ambos workflows parsean con `yaml.safe_load` (W6: un YAML invalido desactivaria el gate de publicacion en silencio).
- `continue-on-error` aparece **0** veces en ambos ficheros.
- Documentacion de GitHub verificada: `./.github/workflows/{filename}` resuelve al **mismo commit que el caller** (correcto sobre un tag) y `workflow_call` es el mecanismo nativo; se descarto `workflow_run` porque correria contra la rama por defecto.

**NO probado (requiere push a GitHub; ver "Manual-Only Verifications Not Performed"):** la corrida real contra un gate rojo que demuestre que `publish` no arranca, y la corrida de CI con un servicio de motor requerido eliminado. No se ejecutaron: no hay `gh` instalado en esta maquina y no se hace push sin peticion explicita.

## Resolucion del riesgo `concurrency` en workflow reutilizable

El plan lo marcaba como "riesgo conocido a verificar, no asumir". **Resuelto: no hace falta ningun ajuste.** La documentacion de GitHub ("Reusing workflow configurations") restringe las **keywords de los jobs que llaman** a un workflow reutilizable (lista que incluye `jobs.<job_id>.concurrency`); no prohibe que el workflow **llamado** declare `concurrency` a nivel de workflow, que es una clave de primer nivel normal de cualquier workflow. Ademas, `release.yml` no declara `concurrency`, asi que no existe el conflicto que la documentacion advierte (mismo `group` con `cancel-in-progress: true` en caller y called). El `group: ci-${{ github.ref }}` de `ci.yml` se evalua con el contexto `github` del caller (el tag en la ruta de release), por lo que no colisiona con la corrida de push a `main`.

**`setup-uv` `version:` — input confirmado.** Se leyo el `action.yml` de `astral-sh/setup-uv@v5`: el input se llama `version` (descripcion "The version of uv to install e.g., `0.5.0`"), y tambien existe `python-version`. `ci.yml` ya lo usaba; `release.yml` no lo tenia y se anadio (`0.12.15`) para cumplir T-01-04.

## Verification (plan-level)

| Comando | Resultado |
|---------|-----------|
| `uv run pytest -q` | `534 passed` (521 preexistentes + 13 del arnes) |
| `uv run pytest tests/test_ci_harness.py -q` | `13 passed` |
| `uv run pytest tests/test_ci_harness.py -q -k check_skips` | `6 passed, 7 deselected` |
| `uv run pytest tests/test_ci_harness.py -q -k require_engines` | `4 passed, 9 deselected` |
| `uv run pytest -q -m "not optional_engine" --junitxml=junit.xml` | `521 passed, 13 deselected` |
| `uv run ruff check encino_orm tests tools` | `All checks passed!` (exit 0) |
| `uv run ruff format --check encino_orm tests tools` | `104 files already formatted` (exit 0) |
| `uv run mypy encino_orm` | `Success: no issues found in 56 source files` (exit 0) |
| `pytest.skip` en `tests/test_*.py` (fuera de `test_ci_harness.py`) | **0 ficheros** |
| `from conftest import` en los 7 ficheros migrados | **0** |
| `continue-on-error` en `ci.yml` / `release.yml` | `0` / `0` |
| `yaml.safe_load` de ambos workflows | parsean |
| `check_skips.py` sobre limpio / con skips / ausente | `0` / `1` / `1` |
| `git status --porcelain` tras las pruebas | limpio (`junit.xml` eliminado) |

## Decisions Made

- **El gate se reconcilia en la invocacion, no en el XML (D-02).** El JUnit-XML no lleva informacion de markers; deseleccionar los tests opcionales con `-m "not optional_engine"` elimina la ambiguedad en la fuente, verificado empiricamente (los deseleccionados no aparecen en el XML: `tests=521`, `skipped=0`).
- **Fail-closed en el gate.** Un XML ausente o ilegible devuelve 1 en vez de reventar o devolver 0: un gate que sale 0 con entrada mala es peor que no tener gate (frontera del threat model).
- **`release.yml` recibe el pin de `uv`** ademas de `needs: [ci]`: la ruta de publicacion es la frontera de mayor consecuencia del repo y T-01-04 exige el pin en ambos workflows.
- **El `except Exception` de los fixtures se deja intacto.** Documentado en el docstring del helper y en esta SUMMARY como seguimiento de Fase 2 (Pitfall 1), no como deuda oculta.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `ruff` S314 bloquea el gate recien creado**
- **Found during:** Task 3 (primera corrida de `uv run ruff check tools tests` con el script nuevo)
- **Issue:** `S314 Using xml to parse untrusted data is known to be vulnerable to XML attacks; use defusedxml equivalents` sobre `ET.parse(path)`. El job `lint` es bloqueante (01-01) y el plan exige `ruff check tools tests` en 0. La alternativa que sugiere la regla (`defusedxml`) violaria la regla explicita del plan "solo stdlib (sin dependencia nueva)" y ademas exigiria un checkpoint de legitimidad de paquete.
- **Fix:** entrada acotada `"tools/ci/check_skips.py" = ["S314"]` en `[tool.ruff.lint.per-file-ignores]` con comentario en español que cita T-01-11: el XML es un artefacto de build producido por el propio job (sin entrada no confiable) y `xml.etree.ElementTree` de CPython no resuelve entidades externas por defecto; se levantara solo si el XML pasara a venir de fuera del job. Se prefirio `per-file-ignores` a `# noqa` para preservar el invariante `# noqa = 0` de 01-01.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run ruff check encino_orm tests tools` -> exit 0.
- **Committed in:** `a59564e` (Task 3 GREEN)

**2. [Rule 1 - Bug] `-k check_skips` y `-k require_engines` seleccionaban CERO tests y pasaban en vacio**
- **Found during:** Task 3, al ejecutar el `<automated>` del plan
- **Issue:** el primer RED nombro las clases `TestCheckSkipsMain` y `TestRequiredEngines`. El filtro `-k` hace match de subcadena sobre el node id, y `TestCheckSkipsMain` **no** contiene el literal `check_skips` (falta el guion bajo). Resultado: `-k check_skips` -> `13 deselected`, exit 0. El criterio de aceptacion del plan ("`-k check_skips` passes") se cumpliria sin ejecutar ni un solo test del gate: una prueba decorativa, justo el anti-patron que la fase combate.
- **Fix:** se renombraron los metodos con el prefijo literal del modulo bajo prueba: `test_check_skips_*` (6 tests) y `test_require_engines_*` (4 tests); se documento el motivo en el docstring del fichero. Se hizo en un commit `test(...)` separado para que el commit GREEN quedase como implementacion pura.
- **Files modified:** `tests/test_ci_harness.py`
- **Verification:** `-k check_skips` -> `6 passed, 7 deselected`; `-k require_engines` -> `4 passed, 9 deselected`.
- **Committed in:** `87b4725` (Task 3 RED, segundo commit)

**3. [Rule 2 - Missing Critical] `release.yml` no fijaba la version de `uv`**
- **Found during:** Task 3, al revisar T-01-04
- **Issue:** el registro de amenazas exige el pin de `uv` "en ambos workflows" para que el entorno que publica use una version conocida, pero el step de `setup-uv` de `release.yml` solo tenia `enable-cache: true`. La ruta de publicacion es la frontera de mayor consecuencia del repo.
- **Fix:** se anadio `version: "0.12.15"` al `setup-uv` de `release.yml` con comentario que cita T-01-04. Se confirmo el nombre del input leyendo el `action.yml` de `astral-sh/setup-uv@v5`.
- **Files modified:** `.github/workflows/release.yml`
- **Verification:** `yaml.safe_load` parsea; el input `version` existe en el `action.yml` de la action.
- **Committed in:** `a59564e` (Task 3 GREEN)

**4. [Rule 3 - Medicion] El baseline del plan (510) no contempla los 11 guards de 01-03**
- **Found during:** Task 3, al comprobar el total de la suite
- **Issue:** el plan afirma repetidamente `510 passed` como baseline. El estado real tras 01-03 es **521 passed** (510 originales + 11 guards de `tests/test_pytest_config.py`, tal y como registro el SUMMARY de 01-03). Los 13 tests nuevos del arnes llevan el total a **534**.
- **Fix:** ninguno sobre el codigo; se documenta la reconciliacion (521 + 13 = 534) y se usa el numero medido, no el del plan. La unica asercion sensible al total (`--junitxml` -> `skipped=0`) se expresa sobre el XML, no sobre un conteo fijo.
- **Files modified:** ninguno
- **Verification:** `uv run pytest -q` -> `534 passed`; `uv run pytest -q -m "not optional_engine"` -> `521 passed, 13 deselected` (534 - 13 = 521).
- **Committed in:** n/a (documentado en este SUMMARY)

---

**Total deviations:** 4 (2 bloqueantes, 1 de funcionalidad critica, 1 de medicion).
**Impact on plan:** Ninguna desviacion cambia el alcance ni el comportamiento del ORM. La 2 es la mas relevante: sin ella, los criterios `-k` del plan habrian pasado en vacio y el gate no habria quedado cubierto por sus propios tests. La 1 es una supresion acotada a un fichero, comentada y con condicion de levantamiento. Sin scope creep.

## Issues Encountered

- **El coste de un motor requerido ausente es real y alto:** la ruta de fallo tardo **30.3 s** y la de skip **26.7 s** para un solo fichero (vs 1.5 s con el motor vivo), por los timeouts de conexion. Por eso `timeout-minutes: 15` se preservo sin tocarlo (el plan lo exige y el research lo midio).
- **`uv run ruff check` reconstruyo el paquete** tras editar `pyproject.toml` (uv detecta el cambio y reinstala `encino-orm`). Inofensivo, pero explica el ruido "Building encino-orm / Uninstalled 1 package" en una de las verificaciones.
- **`tools/` es un paquete de namespace implicito** (sin `__init__.py`): `from tools.ci.check_skips import ...` resuelve porque `pythonpath = ["."]` pone la raiz del repo en `sys.path`. Se verifico que el import resuelve antes de commitear.

## Manual-Only Verifications Not Performed

Estas dos verificaciones del plan requieren una corrida real de GitHub Actions. **No se ejecutaron** en esta sesion: no hay `gh` instalado en la maquina y no se hace push sin peticion explicita del usuario. Quedan para el verificador de fase o para el primer push.

| Verificacion | Por que es manual | Pasos exactos |
|--------------|-------------------|---------------|
| CI-08: `publish` no arranca con CI rojo | Requiere una corrida real contra un ref deliberadamente rojo | 1) Crear una rama scratch con un gate roto (p. ej. romper un assert). 2) `git push origin <rama> --tags` con un tag `v0.0.0-test`. 3) En la corrida de `Publish to PyPI`, confirmar que `ci` (reusable) falla y que `publish` aparece como **skipped**. 4) Registrar la URL de la corrida. 5) Borrar el tag y la rama. |
| Quitar un servicio de motor requerido hace FALLAR el job `test` | Requiere editar `ci.yml` y correr en GitHub | 1) En una rama scratch, eliminar el servicio `postgres` (o `mysql`) de `ci.yml`. 2) Push y observar que el job `test` **falla** en vez de pasar con skips (por `ENCINO_ORM_REQUIRE_ENGINES`). 3) Registrar la URL. 4) Revertir. |

**Lo que SI queda probado localmente para ambos:** la prueba 1 de fallo inducido (motor requerido inalcanzable -> exit 1 en vez de skip) es el equivalente local exacto del segundo caso, y la estructura de CI-08 (`needs: [ci]` + `uses: ./.github/workflows/ci.yml`) se verifico por parseo YAML y aserciones de subcadena.

## Threat Flags

Ninguno nuevo. Las mitigaciones del registro de amenazas del plan estan implementadas:

| Threat ID | Estado |
|-----------|--------|
| T-01-03 (un fallo de servicio degrada a verde) | Mitigado: interruptor invertido por env var solo-CI, gate con `if: always()` que sale 1 con `skipped > 0` y 1 (fail-closed) con XML ausente/ilegible, `continue-on-error` ausente y asertado; cada comportamiento probado por fallo inducido |
| T-01-02 (tampering en la ruta de publicacion) | Mitigado: `publish: needs: [ci]` + `ci` llama `./.github/workflows/ci.yml` (mismo commit que el caller). Prueba de corrida real pendiente (ver seccion anterior) |
| T-01-04 (supply chain de `setup-uv`) | Mitigado: `version: "0.12.15"` en **ambos** workflows; nombre del input confirmado contra el `action.yml` de la action. El pin por SHA completo sigue diferido |
| T-01-11 (`xml.etree` del gate) | Mitigado: entrada de build propia (sin entrada no confiable), ET de CPython no resuelve entidades externas por defecto, el parser solo lee enteros y nunca interpola contenido en shell/rutas; `S314` ignorado por fichero con esta justificacion |
| T-01-09 (alguien edita `ci.yml` y desactiva el switch) | Aceptado: protegido por branch protection y revision; el gate JUnit es la segunda capa independiente |
| T-01-10 (`PYPI_API_TOKEN`) | Aceptado: sin cambios en Fase 1; REL-03 (Fase 8) lo sustituye por OIDC |

**No hubo instalaciones de paquetes en este plan** — `tools/ci/check_skips.py` es solo-stdlib por diseno.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Listo para 01-05:** la suite de caracterizacion del pool correra bajo el harness endurecido de 01-03 y, si emitiera algun skip, el gate de `check_skips.py` lo detectaria (el plan 01-05 ya incluye correr el gate contra su XML).
- **Para Fase 2 (DIAL-08):** el interruptor es extensible sin rediseno — probado con `mariadb`. Anadir MariaDB/Redis/MSSQL/Oracle al conjunto requerido es cambiar el valor de `ENCINO_ORM_REQUIRE_ENGINES` en `ci.yml` y anadir sus servicios. Pendiente de Fase 2: estrechar los `except Exception` de los 8 fixtures (Pitfall 1).
- **Para el verificador de fase:** las dos verificaciones manuales de la tabla anterior necesitan un push a GitHub; el resto de los criterios de exito de la fase quedan probados localmente por fallo inducido.
- **Nota para todo fichero nuevo:** debe nacer `ruff check`/`ruff format`-clean, mypy-clean bajo el ratchet y libre de warnings; ahora ademas, si anade un skip no marcado en el job requerido, el gate de CI lo hara fallar.

---

*Phase: 01-safety-net-ci-gates-test-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `tools/ci/check_skips.py` y `tests/test_ci_harness.py` existen en disco.
- Los commits `ef2a8b0`, `0f864c4`, `3a015d1`, `87b4725` y `a59564e` existen en el historial.
- Puertas TDD: commit `test(01-04)` (`3a015d1`, RED con `ModuleNotFoundError`) precede al commit `feat(01-04)` (`a59564e`, GREEN).
- `uv run pytest -q` -> `534 passed`; `uv run pytest tests/test_ci_harness.py -q` -> `13 passed`.
- `uv run ruff check encino_orm tests tools` -> exit 0; `uv run ruff format --check encino_orm tests tools` -> exit 0; `uv run mypy encino_orm` -> exit 0.
- `yaml.safe_load` de ambos workflows parsea; `continue-on-error` = 0 en ambos.
- `check_skips.py` -> 0 (limpio) / 1 (con skips) / 1 (ausente).
- `pytest.skip` = 0 en `tests/test_*.py` fuera de `test_ci_harness.py`; `from conftest import` = 0.
- `git status --porcelain` limpio de artefactos (`junit.xml` eliminado).
