---
phase: 04-pool-correctness-concurrency
plan: 05
subsystem: testing
tags: [pytest, pytest-timeout, pytest-repeat, asyncio, concurrency, pool, uv-lock, ci]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "CI-09 characterization tests; baseline de la barrera `EventBarrier` en `tests/test_pool_characterization.py`"
  - phase: 04-pool-correctness-concurrency
    provides: "04-01 (handle PooledConnection + acquire sin carrera) — contexto del helper extraído"
provides:
  - "Dev deps pinadas `pytest-timeout==2.4.0` y `pytest-repeat==0.9.4` + `uv.lock` regenerado"
  - "Marker `stress` registrado y `timeout = 0` global explícito en `[tool.pytest.ini_options]`"
  - "`--timeout-method=signal` en los jobs CI `test` y `engine-heavy`"
  - "`tests/_pool_helpers.py` con `EventBarrier` (3.10-safe), `FakeDb`, `BlockingFakeDb`, `_CONNECT_BARRIER` y `execute_insert`"
affects: [04-06, pool-concurrency-tests]

# Tech tracking
tech-stack:
  added: ["pytest-timeout==2.4.0", "pytest-repeat==0.9.4"]
  patterns:
    - "Barrera determinista 3.10 con asyncio.Event (liberación en la última llegada, nunca por temporizador)"
    - "Fakes a mano + monkeypatch (sin unittest.mock)"
    - "Timeout por marker (`@pytest.mark.timeout`), global desactivado (`timeout = 0`)"
    - "Pin exacto de plugins de test con racional en español (patrón ruff/syrupy)"

key-files:
  created:
    - tests/_pool_helpers.py
  modified:
    - pyproject.toml
    - uv.lock
    - .github/workflows/ci.yml

key-decisions:
  - "Instalar pytest-timeout/pytest-repeat tras aprobación humana explícita del checkpoint blocking-human (Task 1), con evidencia de resolución PyPI y upstream canónico `github.com/pytest-dev/...` pegada abajo."
  - "Timeout global DESACTIVADO (`timeout = 0`): el job engine-heavy (Oracle 60-120 s) no debe morir por un límite global; el límite va por marker SOLO en los tests de barrera."
  - "`--timeout-method=signal` en ambos jobs Linux: el método *thread* mata el proceso y pierde el JUnit XML (Pitfall 7)."
  - "No se migran `tests/test_pool.py` ni `tests/test_pool_characterization.py` al helper: esa migración pertenece a 04-06 y así se evita solapamiento de ficheros en la Wave 1."

patterns-established:
  - "EventBarrier: parties DEBE ser igual al nº de tareas o el test se cuelga; pytest-timeout con signal lo corta en CI"
  - "FakeDb.execute_insert devuelve self._last para no romperse cuando 04-02 lo añada al contrato de Db"

requirements-completed: [POOL-07]

# Metrics
duration: 25min
completed: 2026-09-19
---

# Phase 4 Plan 05: Infraestructura de tests de concurrencia/estrés Summary

**Dev deps `pytest-timeout==2.4.0`/`pytest-repeat==0.9.4` pinadas con lock regenerado, marker `stress` registrado, `--timeout-method=signal` en CI y `EventBarrier`/`FakeDb`/`BlockingFakeDb` extraídos a `tests/_pool_helpers.py`**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-09-18T23:55:00Z
- **Completed:** 2026-09-19T00:20:00Z
- **Tasks:** 3 (1 checkpoint aprobado + 2 de implementación)
- **Files modified:** 4 (1 creado, 3 modificados)

## Accomplishments

- `pytest-timeout==2.4.0` y `pytest-repeat==0.9.4` añadidos a `[dependency-groups].dev` con pin exacto y racional en español; `uv add` regeneró `uv.lock` (28 líneas) y `uv lock --check` pasa.
- Marker `stress` registrado y `timeout = 0` global explícito, de modo que `--strict-markers` no falla y el timeout se aplica solo por marker.
- `--timeout-method=signal` añadido a los comandos de pytest de los jobs `test` y `engine-heavy` (Linux).
- `tests/_pool_helpers.py` extrae la barrera determinista 3.10-safe y los dobles del pool, listos para que 04-06 los importe, sin tocar los ficheros de test existentes.

## Package Legitimacy Evidence (Task 1 — checkpoint aprobado)

Salida del chequeo automático de PyPI (Task 1 `<verify><automated>`), ejecutado antes de instalar:

```
$ uv run python -c "import json,urllib.request as u; [print(p, ...) for p in ['pytest-timeout','pytest-repeat']]"
pytest-timeout 2.4.0 https://github.com/pytest-dev/pytest-timeout
pytest-repeat 0.9.4 None
```

`pytest-repeat` no expone `project_urls['Source']` ni `home_page`; su upstream canónico aparece en `project_urls['Home']`, verificado aparte:

```
$ uv run python -c "import json,urllib.request as u; d=json.load(u.urlopen('https://pypi.org/pypi/pytest-repeat/json'))['info']; print('version:', d['version']); print('project_urls:', d.get('project_urls')); print('author:', d.get('author'))"
version: 0.9.4
project_urls: {'Home': 'https://github.com/pytest-dev/pytest-repeat'}
author: Bob Silverberg
```

- `pytest-timeout 2.4.0` → `github.com/pytest-dev/pytest-timeout` (canónico).
- `pytest-repeat 0.9.4` → `github.com/pytest-dev/pytest-repeat` (canónico).
- Ambos son plugins de la organización `pytest-dev`; aprobación humana explícita ("approved"). La compuerta `blocking-human` **no** fue auto-aprobada.

## Task Commits

Each task was committed atomically:

1. **Task 1: Verificar legitimidad de paquetes (checkpoint)** — sin commit (no modifica ficheros; gate aprobado)
2. **Task 2: Instalar dev deps, marker `stress`, `--timeout-method=signal`** — `70b10ac` (chore)
3. **Task 3: Extraer `EventBarrier` y dobles a `tests/_pool_helpers.py`** — `e7b25f2` (test)

**Plan metadata:** (docs: complete plan) — ver commit final

## Files Created/Modified

- `pyproject.toml` — pins exactos `pytest-timeout==2.4.0`/`pytest-repeat==0.9.4` con comentario-racional, marker `stress`, `timeout = 0` (con `filterwarnings = ["error"]` intacto).
- `uv.lock` — regenerado por `uv add` (+28 líneas); sin edición manual.
- `.github/workflows/ci.yml` — `--timeout-method=signal` en el job `test` (matriz) y en el job `engine-heavy`.
- `tests/_pool_helpers.py` — `EventBarrier`, `FakeDb` (con `execute_insert`), `BlockingFakeDb`, `_CONNECT_BARRIER`; docstrings en español; sin `unittest.mock` ni primitivas 3.11.

## Decisions Made

- **Timeout global desactivado (`timeout = 0`)**: un límite global mataría el job `engine-heavy` (Oracle 60-120 s); el corte va por marker solo en los tests de barrera.
- **`--timeout-method=signal` en ambos jobs Linux**: el método *thread* mata el proceso y pierde el JUnit XML.
- **No migrar los ficheros de test al helper en este plan**: la migración es de 04-06; así se evita solapamiento en la Wave 1.
- **`execute_insert` en el doble**: declarado ya (devuelve `self._last`) para no romperse cuando 04-02 lo introduzca en el contrato de `Db`; en este plan no se usa.

## Verification (gates de fin de plan)

| Gate | Resultado |
|------|-----------|
| `uv lock --check` | OK (0) |
| `uv run python -c "import pytest_timeout, pytest_repeat"` | `pytest-timeout 2.4.0`, `pytest-repeat 0.9.4` |
| `uv run pytest --collect-only -q -m stress` | `no tests collected (857 deselected)` — sin fallo de `--strict-markers` |
| `uv run pytest -q` | **857 passed** in 21.07s |
| `uv run ruff check encino_orm tests` | All checks passed |
| `uv run ruff format --check encino_orm tests` | 116 files already formatted |
| `uv run mypy encino_orm` | Success: no issues found in 60 source files |
| AST check helper (`Barrier`/`TaskGroup`/`timeout` en código) | `helper OK: sin primitivas 3.11 en codigo` |
| `grep -c "unittest.mock" tests/_pool_helpers.py` | 0 |
| `grep -c -- "--timeout-method=signal" .github/workflows/ci.yml` | 3 (comentario + 2 comandos) |
| `grep -c '"stress: ' pyproject.toml` | 1 |

## Deviations from Plan

**1. [Rule 1 - Ajuste de docstring para cumplir el acceptance literal] `grep -c "unittest.mock"` debía dar 0**
- **Found during:** Task 3 (extracción del helper)
- **Issue:** El docstring del módulo nombraba `unittest.mock` en negativo ("Tampoco se usa `unittest.mock`"), lo que hacía que el `grep -c` del acceptance devolviera 1 en vez de 0.
- **Fix:** Se reformuló el docstring a "no se usan los dobles automáticos de la stdlib" sin cambiar el significado. (El chequeo AST sí era docstring-safe; solo el grep literal se veía afectado.)
- **Files modified:** `tests/_pool_helpers.py`
- **Verification:** `grep -c "unittest.mock" tests/_pool_helpers.py` → 0; AST check sigue verde.
- **Committed in:** `e7b25f2` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Cosmético/literal; sin cambio de comportamiento ni de alcance.

## Issues Encountered

- La comprobación PyPI del plan leía `project_urls['Source']`/`home_page`; `pytest-repeat` los devuelve `None`. Se resolvió consultando `project_urls['Home']`, que apunta al upstream canónico `github.com/pytest-dev/pytest-repeat`. La legitimidad queda confirmada y registrada arriba.

## Known Stubs

None. `FakeDb.execute_insert` existe deliberadamente como preparación para 04-02, pero no es un stub de UI ni afecta al objetivo del plan; no se usa todavía.

## Threat Flags

None — no se introduce superficie de red/auth/acceso a ficheros nueva. Los únicos cambios son deps de test (dev), config de pytest y un helper de tests.

## Next Phase Readiness

- 04-06 puede importar `EventBarrier`, `FakeDb`, `BlockingFakeDb` y `_CONNECT_BARRIER` desde `tests/_pool_helpers.py`, y usar `@pytest.mark.timeout`/`@pytest.mark.repeat` tras el marker `stress`.
- `uv lock --check` verde; el job `deps` de CI aceptará el lock regenerado.
- Sin blockers.

---
*Phase: 04-pool-correctness-concurrency*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `tests/_pool_helpers.py`
- FOUND: `.planning/phases/04-pool-correctness-concurrency/04-05-SUMMARY.md`
- FOUND commit: `70b10ac`
- FOUND commit: `e7b25f2`
