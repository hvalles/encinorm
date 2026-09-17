---
phase: 01-safety-net-ci-gates-test-infrastructure
plan: 01
subsystem: infra
tags: [ruff, lint, format, ci, github-actions, uv, quality-gates, git-blame]

# Dependency graph
requires: []
provides:
  - "ruff 0.16.8 pineado exactamente y configurado ([tool.ruff], [tool.ruff.lint], per-file-ignores comentados)"
  - "Commit de formato aislado y registrado en .git-blame-ignore-revs"
  - "Job `lint` bloqueante en ci.yml (ruff check + ruff format --check), sin continue-on-error"
  - "uv 0.12.15 fijado en CI (prerequisito de `uv audit` en el plan 01-02)"
affects: [01-02, 01-03, 01-04, 01-05, "todas las fases posteriores (todo fichero nuevo debe nacer format-clean)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Commit mecánico de formato aislado + .git-blame-ignore-revs (formato primero, reglas después)"
    - "per-file-ignores acotados por fichero y comentados, cada uno nombrando la fase que lo levanta"
    - "Gate probado por fallo inducido, no por corrida verde"

key-files:
  created:
    - .git-blame-ignore-revs
  modified:
    - pyproject.toml
    - uv.lock
    - .github/workflows/ci.yml
    - "61 ficheros .py reformateados (encino_orm/ y tests/)"
    - "30 ficheros bajo encino_orm/ con correcciones de lint"
    - "27 ficheros bajo tests/ con correcciones de lint"

key-decisions:
  - "line-length = 100 es la fuente de verdad para ruff (desviación consciente de AGENTS.md §Code Style; baseline medido: 195 hallazgos a 88 vs 128 a 100)"
  - "PERF203 se ignora por fichero en encino_orm/base.py y encino_orm/pool.py: el try/except debe permanecer dentro de bucles acotados (reintentos/adquisición) y sacarlo cambia la semántica"
  - "El F821 de encino_orm/model/query_builder.py se corrige con un import TYPE_CHECKING, nunca se suprime"
  - "uv se actualizó vía pip (uv self update no está disponible en esta instalación)"

patterns-established:
  - "Aislamiento bisectable: formato (style) / reglas de fuente (refactor) / reglas de tests + CI (refactor) en commits separados"
  - "Cero `# noqa` y cero supresiones sin comentario en español que nombre la fase de levantamiento"

requirements-completed: [CI-03]

# Metrics
duration: 6 min
completed: 2026-09-17
---

# Phase 1 Plan 01: Ruff como gate real — formato aislado, ruleset de 14 familias y job `lint` bloqueante

**ruff 0.16.8 pineado y configurado a `line-length=100`; commit de formato aislado y excluido de `git blame`; `ruff check`/`format --check` limpios sobre `encino_orm/` y `tests/` (132 hallazgos post-formato resueltos) y job `lint` bloqueante en CI probado por fallo inducido.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-17T22:55:20Z
- **Completed:** 2026-09-17T23:01:34Z
- **Tasks:** 4
- **Files modified:** 84 (únicos, Tasks 1–4)

## Accomplishments

- `ruff` pasó de estar instalado pero sin configurar a ser un gate real: `[tool.ruff]`, `[tool.ruff.lint]` (14 familias) y `per-file-ignores` acotados.
- El commit mecánico de formato (61 de 101 ficheros) se aisló y se registró en `.git-blame-ignore-revs` (SHA `fd00e59894d43a62e13627458eea81602229e205`), con `git config blame.ignoreRevsFile` activado localmente.
- `ruff check encino_orm tests` y `ruff format --check encino_orm tests` salen 0; `uv run pytest -q` sigue reportando `510 passed` (cero cambio de comportamiento).
- Job `lint` bloqueante añadido a `ci.yml` con `ruff check` + `ruff format --check`, sin `continue-on-error`, y uv fijado a `0.12.15` en los jobs `test` y `lint`.
- Gate probado por **fallo inducido**: un `import os` sin usar en un módulo sonda hizo que `uv run ruff check` saliera con código 1 (transcripción abajo).

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Housekeeping previo (pre-plan)** - `fd5b052` (chore): adopta cambios preexistentes del árbol (`.gitignore`, STATE.md, config.json)
2. **Task 1: pin de ruff + config base** - `dcb3341` (chore)
3. **Task 2a: `ruff format` mecánico** - `fd00e59` (style)
4. **Task 2b: registrar el commit de formato en `.git-blame-ignore-revs`** - `6a1c2e1` (chore)
5. **Task 3: ruleset + correcciones en `encino_orm/`** - `83bbe92` (refactor)
6. **Task 4: correcciones en `tests/` + job `lint`** - `350c334` (refactor)

**Plan metadata:** (este commit) (docs: complete plan)

## Files Created/Modified

- `pyproject.toml` — `ruff==0.16.8`, `[tool.ruff]` (target py310, line-length 100), `[tool.ruff.lint]` (select de 14 familias), `[tool.ruff.lint.per-file-ignores]`, `[tool.ruff.lint.isort]`
- `uv.lock` — re-resuelto con el pin exacto de ruff
- `.git-blame-ignore-revs` — **nuevo**; exclusión de blame del commit de formato
- `.github/workflows/ci.yml` — job `lint` bloqueante; `version: "0.12.15"` en `setup-uv` de `test` y `lint`
- 61 ficheros `.py` reformateados por `ruff format`
- 30 ficheros de `encino_orm/` y 27 de `tests/` con correcciones de lint

## uv — versión y vía de actualización

- **Versión final:** `uv 0.12.15` (d35f1f270, 2026-09-15, x86_64-pc-windows-msvc).
- **Vía usada:** `uv self update 0.12.15` **no** está disponible en esta instalación (`error: Self-update is only available for uv binaries installed via the standalone installation scripts`). Se usó el fallback documentado: `pip install -U uv` a través del intérprete que posee el binario (`Python313/Scripts/uv`), es decir `python313 -m pip install -U "uv==0.12.15"`.
- **Motivo:** es prerequisito de `uv audit` (CI-07) en el plan 01-02.

## Baseline medido y resolución

| Ámbito | Pre-formato | Post-formato | Auto-fix | A mano | Ignorado | Final |
|--------|-------------|--------------|----------|--------|----------|-------|
| `encino_orm/` | 128 (a 100) / 195 (a 88) | **69** | 24 | 44 | 2 (`PERF203`) | **0** |
| `tests/` | 102 (ruleset estrecho, ignorando S101) | **63** | 19 | 45 | 0 | **0** |
| `ruff format --check` | 61 de 101 ficheros | — | — | 61 reformateados | — | **0** |

> **Desviación respecto al plan:** el plan anticipaba 23 auto-corregidos y 46 a mano en `encino_orm/`, y 18 auto-corregidos y 45 a mano en `tests/`. Se midió **24 auto / 46 restantes** en fuente (una corrección automática expuso un hallazgo nuevo) y **19 auto / 45 restantes** en tests. De los 46 restantes en fuente, **44 se corrigieron a mano** y **2 `PERF203`** se ignoraron por fichero (ver más abajo). El recuento alternativo del ruleset estrecho para tests (21 post-formato) coincide con el plan.

## Configuración final de ruff

### `[tool.ruff]`

```toml
target-version = "py310"   # coincide con requires-python; dirige las reescrituras UP
line-length = 100          # a 88 el baseline era 195 hallazgos vs 128 a 100
```

### `[tool.ruff.lint].select` (lista final)

```text
E, W, F, I, UP, B, C4, SIM, PERF, FURB, ASYNC, RUF, S, PT
```

**Deliberadamente NO habilitados en este milestone:** `ANN`, `D`, `PL` (101 ficheros / 507 tests; habilitarlos en bloque entierra los hallazgos reales).

### `[tool.ruff.lint.per-file-ignores]` — cada entrada con su justificación y fase de levantamiento

| Clave | Reglas | Justificación | Se levanta en |
|-------|--------|---------------|---------------|
| `tests/**` | `S101`, `PT011`, `B017`, `ARG001`, `ARG002` | D-09: no se reescriben asserts genéricos ni de estado privado en Fase 1. `PT012/PT018/PT006` siguen activos | Fase 4 (`PT011`/`B017`) |
| `encino_orm/{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` | `S608` | Los constructores de dialecto interpolan SQL intencionadamente; el resto de `S` sigue activo | Fase 2 (DIAL-02) |
| `encino_orm/transfer.py` | `S608` | Igual que los adaptadores | Fase 2 (DIAL-02) |
| `encino_orm/model/model.py` | `S608` | Igual que los adaptadores | Fase 2 (DIAL-02) |
| `encino_orm/http/routes.py` | `S102`, `B008` | `exec()` genera handlers; `Depends(...)` en defaults de FastAPI | Fase 6 (CFG-03 / CFG-02) |
| `encino_orm/graphql/schema.py` | `S102` | Handlers generados con `exec()` | Fase 6 (CFG-03) |
| `encino_orm/security/guard.py` | `B008` | `Depends(...)`/`require(...)` en defaults de FastAPI (5 hallazgos); idiom del framework | Fase 6 (CFG-02) |
| `encino_orm/base.py` | `S608`, `S311`, `PERF203` | `S608` adaptadores; `S311` (`random` solo alimenta el backoff con jitter, no es sensible a seguridad); `PERF203` (try/except dentro del bucle de reintentos, máx. 9) | Fase 2 (`S608`); `PERF203` es estructural |
| `encino_orm/pool.py` | `PERF203` | `get_nowait()` + `except QueueEmpty` es la condición del bucle de adquisición; no se puede sacar sin cambiar la semántica | Estructural |
| `encino_orm/model/cached.py`, `encino_orm/model/filter.py` | `S324` | `sha1` construye claves de caché, no una frontera de seguridad | No aplica |
| `tests/test_security.py` | `B008`, `S105` | `Depends/require` en defaults (2) y la constante `SECRET` solo de test (1) | Fase 6 (CFG-02) |
| `tests/test_sql_functions.py` | `S608` | Interpola SQL a propósito para ejercitar los fragmentos portables | No aplica |

**Ninguna entrada suprime `F821`.**

## F821 — corregido de verdad, nunca suprimido

`encino_orm/model/query_builder.py:281` anota `paginate(...) -> "Records"` con un nombre que el módulo importaba de forma diferida dentro del cuerpo. Se corrigió con:

```python
import re
from typing import TYPE_CHECKING

...
if TYPE_CHECKING:
    # Solo para la anotación `-> "Records"` de `paginate`; la importación real
    # sigue siendo diferida dentro del método (contrato de import diferido).
    from .records import Records
```

El import bajo `TYPE_CHECKING` se borra en runtime, por lo que se preserva el contrato de importación diferida de `AGENTS.md` §Import Organization. La importación local dentro de `paginate` se mantiene para el uso en runtime.

## Correcciones notables de comportamiento-preservación

- **B905 (`zip` sin `strict`)**: se añadió `strict=False` (5 sitios), preservando exactamente el truncado implícito previo.
- **B904 (`raise` dentro de `except`)**: se añadió `from None` en 3 sitios (`http/registry.py`, `model/constraint.py`, `pool.py`), que suprime el contexto interno sin introducir encadenamiento (coherente con `AGENTS.md` §Error Handling, que documenta que no se usa chaining).
- **RUF013/UP045**: anotaciones `X = None` → `X | None` y `Optional[X]` → `X | None` (PEP 604, el proyecto ya lo usa).
- **UP031**: `"{%d}" % i` → f-string `f"{{{i}}}"` (5 sitios), mismo resultado `{0}`, `{1}`, …
- **RUF012**: 25 atributos de clase mutables en tests anotados con `typing.ClassVar` (sobreescrituras de atributos `ClassVar` de `Model`).
- **PT018**: 12 asserts compuestos divididos en asserts simples (comportamiento-preservador; no cubierto por D-09).
- **SIM105/S110**: `try/except/pass` → `contextlib.suppress(Exception)` en `transfer.py` y `tests/test_postgresql.py`.
- **PERF203 en `model/model.py`**: se extrajo `Model._validate_field()` (helper sin bucle) en lugar de suprimir; los otros dos `PERF203` sí se ignoraron por fichero (ver tabla).

## Induced-failure proof (gate de lint)

Transcripción literal del fallo inducido (fichero sonda creado y eliminado a continuación; el árbol quedó limpio):

```text
$ printf 'import os\n\n\ndef probe():\n    return 1\n' > encino_orm/_lint_probe.py
$ uv run ruff check
F401 [*] `os` imported but unused
 --> encino_orm\_lint_probe.py:1:8
  |
1 | import os
  |        ^^
help: Remove unused import: `os`
  |
  - import os
1 |
  |

Found 1 error.
[*] 1 fixable with the `--fix` option.
EXIT_CODE=1
$ rm encino_orm/_lint_probe.py
```

`git status --porcelain` no mostró ningún fichero no rastreado tras eliminar la sonda.

## Verification (plan-level)

| Comando | Resultado |
|---------|-----------|
| `uv --version` | `uv 0.12.15` (≥ 0.12.15) |
| `uv run ruff --version` | `ruff 0.16.8` |
| `uv run ruff check encino_orm tests` | `All checks passed!` (exit 0) |
| `uv run ruff format --check encino_orm tests` | `101 files already formatted` (exit 0) |
| `uv run pytest -q` | `510 passed` |
| `uv lock --check` | exit 0 |
| `yaml.safe_load(ci.yml)` | parsea |
| `git config blame.ignoreRevsFile` | `.git-blame-ignore-revs` |
| `git log --oneline -5` | formato, blame, fuente y tests como cuatro commits separados |
| `mkdocs build --strict` | exit 0 (docstrings intactos tras el reformateo) |
| `grep -rn "# noqa" encino_orm tests \| wc -l` | `0` |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Árbol de trabajo con cambios preexistentes sin commitear**
- **Found during:** Antes de Task 1
- **Issue:** `.gitignore` (`*.db-*`), `pyproject.toml` y `uv.lock` (declaración de `ruff>=0.16.8`) tenían cambios sin commitear, además de `.planning/STATE.md` y `.planning/config.json` (sincronizados por el orquestador). Esto impedía satisfacer el criterio de Task 2 "`git status --porcelain` limpio".
- **Fix:** se aislaron en un commit `chore(01)` previo (`fd5b052`); la declaración de ruff pasó a formar parte natural de Task 1.
- **Files modified:** `.gitignore`, `.planning/STATE.md`, `.planning/config.json`
- **Verification:** `git status --porcelain` limpio antes de Task 1 y tras Task 2.
- **Committed in:** `fd5b052`

**2. [Rule 3 - Blocking] `uv self update` no disponible**
- **Found during:** Task 1
- **Issue:** `uv self update 0.12.15` falla: uv se instaló vía pip (Python 3.13), no mediante el instalador standalone.
- **Fix:** fallback documentado `pip install -U "uv==0.12.15"` con el intérprete dueño del binario. Registrado arriba.
- **Files modified:** ninguno del repo (instalación global).
- **Verification:** `uv --version` → `uv 0.12.15`.
- **Committed in:** `dcb3341` (Task 1)

**3. [Rule 3 - Blocking] PERF203 no es corregible sin cambiar semántica en 2 de 3 sitios**
- **Found during:** Task 3
- **Issue:** el plan esperaba corregir `PERF203 ×3` a mano. En `model/model.py` sí se pudo (helper `_validate_field`), pero en `encino_orm/base.py` (bucle de reintentos con `try/except` como control de flujo) y `encino_orm/pool.py` (`get_nowait()` + `except QueueEmpty` como condición del bucle) el `try/except` **debe** permanecer dentro del bucle; sacarlo cambia la semántica.
- **Fix:** `per-file-ignores` acotado a esos dos ficheros, con comentario en español justificando que es estructural (no hay fase de levantamiento). Es la única ampliación de la superficie de supresión respecto al plan.
- **Files modified:** `pyproject.toml`
- **Verification:** `ruff check encino_orm` → 0; `pytest -q` → 510 passed.
- **Committed in:** `83bbe92` (Task 3)

**4. [Rule 1 - Bug] E501 auto-inducido por la anotación ClassVar**
- **Found during:** Task 4
- **Issue:** al anotar `_references_def` en `tests/test_issues.py:23` la línea pasó de 100 a 102 caracteres, generando un `E501` nuevo.
- **Fix:** se partió el dict en varias líneas.
- **Files modified:** `tests/test_issues.py`
- **Verification:** `ruff check tests` → 0.
- **Committed in:** `350c334` (Task 4)

**5. [Rule 2 - Missing Critical] Comentario de diferimiento del pin por SHA de actions**
- **Found during:** Task 4 (threat T-01-04)
- **Issue:** el registro de amenazas exige dejar constancia explícita de que el pin por SHA completo de las actions queda diferido, en lugar de omitirlo silenciosamente.
- **Fix:** comentario en `ci.yml` junto a los `setup-uv` que documenta el pin por versión de uv y el diferimiento del pin por SHA.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** `yaml.safe_load` parsea; job `lint` presente.
- **Committed in:** `350c334` (Task 4)

---

**Total deviations:** 5 auto-corregidas (3 bloqueantes, 1 bug, 1 funcionalidad crítica faltante).
**Impact on plan:** Ninguna desviación cambia el alcance. La única ampliación real de la superficie de supresión son 2 entradas `PERF203` estructurales, documentadas y comentadas. El resto son arreglos de entorno/estado previo.

## Issues Encountered

- `uv self update` no disponible (resuelto vía pip, ver deviation 2).
- `PERF203` no corregible en 2 de 3 sitios (resuelto con ignore acotado, ver deviation 3).
- El recuento de auto-correcciones difirió en +1 en ambos ámbitos respecto al plan (una corrección automática expuso un hallazgo nuevo); documentado en la tabla de baseline.

## Threat Flags

Ninguno. Este plan no introduce superficie de red, autenticación, acceso a ficheros ni cambios de esquema. Las superficies de seguridad tratadas (T-01-03 job `lint` bloqueante, T-01-04 pin de uv/ruff, T-01-05 `# noqa` cero, T-01-06 `per-file-ignores` acotados, T-01-15 YAML válido) están mitigadas y verificadas según el registro de amenazas del plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Listo para 01-02:** uv 0.12.15 ya está instalado y fijado en CI, así que `uv audit` (CI-07) es utilizable. El ruleset y el formato están limpios, de modo que todo fichero nuevo del plan 01-02 debe nacer `ruff format`-clean y `ruff check`-clean bajo esta configuración.
- **Nota para fases posteriores:** el commit de formato queda excluido de `git blame` vía `.git-blame-ignore-revs`; GitHub lo aplica automáticamente y en local ya está activado.
- **Pendiente de `AGENTS.md`:** la desviación de `line-length = 100` debe quedar reflejada en `AGENTS.md` §Code Style como fuente de verdad (el plan la documenta como W7; el texto de `AGENTS.md` aún describe el límite histórico de 88).

---
*Phase: 01-safety-net-ci-gates-test-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `.git-blame-ignore-revs` y `01-01-SUMMARY.md` existen en disco.
- Los commits `dcb3341`, `fd00e59`, `6a1c2e1`, `83bbe92`, `350c334` existen en el historial.
- El commit de formato `fd00e59` toca únicamente ficheros `.py`.
