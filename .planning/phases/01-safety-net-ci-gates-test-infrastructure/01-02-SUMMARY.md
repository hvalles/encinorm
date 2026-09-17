---
phase: 01-safety-net-ci-gates-test-infrastructure
plan: 02
subsystem: infra
tags: [mypy, py.typed, pep561, typecheck, uv, uv-audit, pip-audit, supply-chain, ci, github-actions, ratchet]

# Dependency graph
requires:
  - phase: 01-safety-net-ci-gates-test-infrastructure
    provides: "01-01: ruff 0.16.8 pineado + job `lint` bloqueante + uv 0.12.15 fijado en CI (prerequisito de `uv audit`)"
provides:
  - "`encino_orm/py.typed` (marcador PEP 561) presente en la wheel construida"
  - "`[tool.mypy]` no estricto con ratchet documentado por `ignore_errors` y `warn_unused_ignores = true`"
  - "Job `typecheck` bloqueante en ci.yml, con los mismos extras que el job `test` (W3)"
  - "Job `deps` bloqueante: `uv lock --check` + `uv audit` (OSV) + `pip-audit` (PyPA) sobre `uv export`"
  - "Semántica de exit de `uv audit` verificada empíricamente (exit 1 con hallazgos)"
  - "Las 4 dependencias dev aprobadas por humano: mypy 2.3.1, pytest-cov 7.1.0, coverage 7.16.1, pip-audit 2.10.1"
affects: [01-03, 01-04, 01-05, "fases posteriores: todo módulo nuevo nace mypy-clean bajo el ratchet y ruff-clean"]

# Tech tracking
tech-stack:
  added:
    - "mypy 2.3.1 (+ mypy-extensions) con el plugin pydantic.mypy"
    - "pytest-cov 7.1.0 y coverage 7.16.1 (instalados aquí; los cablea 01-03)"
    - "pip-audit 2.10.1 (feed PyPA) como cross-check de `uv audit` (feed OSV)"
  patterns:
    - "Ratchet de tipos por `[[tool.mypy.overrides]]` con `ignore_errors = true`, nunca `# type: ignore`"
    - "Allowlist de vulnerabilidades explícita, comentada en español y con fase de levantamiento; jamás `continue-on-error`"
    - "Gate probado por fallo inducido, no por corrida verde"

key-files:
  created:
    - encino_orm/py.typed
  modified:
    - pyproject.toml
    - uv.lock
    - .github/workflows/ci.yml

key-decisions:
  - "Ratchet de mypy con `ignore_errors` por módulo (15 módulos, 64 errores / 17 ficheros) en lugar de `# type: ignore`: el conteo de supresiones inline en `encino_orm/` sigue siendo 0"
  - "El job `typecheck` sincroniza `--extra http --extra security --extra graphql` (W3), idéntico al job `test`: el ratchet se midió con esos extras importables"
  - "Los 5 avisos GHSA de PyJWT 2.12.1 se aceptan con `--ignore` explícito y comentado; `--ignore-until-fixed` no los suprime porque existe fix (2.13.0)"
  - "`pip-audit` se alimenta de un fichero temporal con la salida de `uv export`; no acepta `-r -` ni lee `uv.lock`"
  - "El baseline de mypy medido (64 errores / 17 ficheros) difiere del de la investigación (85 / 21); el ratchet se fija contra la medición real post-ruff"

patterns-established:
  - "Fallo inducido como prueba de gate: sonda temporal fuera del override (mypy) y cota sin re-lockear (`uv lock --check`)"
  - "Allowlist de CVEs con fase de levantamiento nombrada y comentario en español, en lugar de silenciar el escáner"

requirements-completed: [CI-04, CI-07]

# Metrics
duration: 9min
completed: 2026-09-17
---

# Phase 1 Plan 02: Tipos y cadena de suministro — `py.typed`, ratchet de mypy y jobs `typecheck`/`deps` bloqueantes

**`encino_orm/py.typed` (PEP 561) embarcado en la wheel; `uv run mypy encino_orm` en verde bajo un ratchet no estricto de 15 módulos con `warn_unused_ignores` y cero `# type: ignore`; y un job `deps` bloqueante con `uv lock --check` + `uv audit` (OSV) + `pip-audit` (PyPA), ambos gates probados por fallo inducido.**

## Performance

- **Duration:** 9 min (continuación: Tasks 2–3; la Task 1 fue un checkpoint humano resuelto antes de esta sesión)
- **Started:** 2026-09-17T23:03:00Z (aprox., inicio de la continuación)
- **Completed:** 2026-09-17T23:12:00Z
- **Tasks:** 3 (Task 1 = checkpoint humano; Tasks 2 y 3 = auto)
- **Files modified:** 4 (1 creado, 3 modificados)

## Accomplishments

- `encino_orm/py.typed` creado (vacío) y **verificado dentro de la wheel** `encino_orm-0.2.6-py3-none-any.whl` — sin cambio de empaquetado: hatchling lo incluye bajo `packages = ["encino_orm"]`.
- `[tool.mypy]` no estricto (`python_version = "3.10"`, `files = ["encino_orm"]`, `ignore_missing_imports`, `plugins = ["pydantic.mypy"]`, `warn_unused_ignores = true`) con un ratchet de 15 módulos; `uv run mypy encino_orm` → **exit 0**, `Success: no issues found in 56 source files`.
- Job `typecheck` bloqueante en `ci.yml` (sin servicios, sin `continue-on-error`) que sincroniza los mismos extras que `test` (W3).
- Job `deps` bloqueante: `uv lock --check` → `uv audit` (allowlist explícita) → `pip-audit` sobre `uv export`.
- **Ambos gates probados por fallo inducido** (transcripciones abajo): mypy exit 1 ante un tipo erróneo fuera del override; `uv lock --check` exit 1 ante un `pyproject.toml` divergente.
- `uv run pytest -q` sigue reportando **510 passed**; `ruff check`/`ruff format --check` siguen en 0 (sin regresión del plan 01-01).

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: Verificar legitimidad de paquetes (checkpoint:human-verify)** — sin commit (no instala, no modifica ficheros); aprobado por el humano
2. **Task 2: `py.typed` + config de mypy + job `typecheck`** — `23009b4` (feat)
3. **Task 3: job `deps` (lock + auditoría de vulnerabilidades)** — `970cb6e` (feat)

**Plan metadata:** (este commit) (docs: complete plan)

## Files Created/Modified

- `encino_orm/py.typed` — **nuevo**; marcador PEP 561 vacío, presente en la wheel
- `pyproject.toml` — `[tool.mypy]` + `[[tool.mypy.overrides]]` (ratchet comentado) + las 4 deps dev
- `uv.lock` — re-resuelto con las 4 deps dev (95 paquetes)
- `.github/workflows/ci.yml` — jobs `typecheck` y `deps`, ambos bloqueantes, sin servicios y sin `continue-on-error`

## Task 1 — Checkpoint de legitimidad de paquetes (T-01-SC)

**Evidencia automática de resolución en PyPI (salida literal):**

```text
mypy 2.3.1
pytest-cov 7.1.0
coverage 7.16.1
pip-audit 2.10.1
```

**Upstreams canónicos verificados:**

| Paquete | Upstream canónico | Resultado |
|---------|-------------------|-----------|
| `mypy` | `github.com/python/mypy` | coincide |
| `pytest-cov` | `github.com/pytest-dev/pytest-cov` | coincide |
| `coverage` | `github.com/coveragepy/coveragepy` | **desviación aceptada** (el plan esperaba `github.com/nedbat/coveragepy`; el proyecto se trasladó a su propia organización — no es typosquat) |
| `pip-audit` | `github.com/pypa/pip-audit` | coincide |

**Aprobación humana:** concedida para añadir los cuatro a `[dependency-groups].dev`. Respuesta: «Aprobar (Recomendado)». El checkpoint es `blocking-human` y **no** era auto-aprobable; `workflow.auto_advance` fue ignorado, como exige T-01-SC.

## Task 2 — Medición de mypy y ratchet

**Entorno de medición (W3):** mypy 2.3.1, `--python-version 3.10`, con los extras opcionales instalados (`uv sync --extra http --extra security --extra graphql`; verificado que `fastapi`, `jwt` y `strawberry` importan). El job `typecheck` de CI sincroniza exactamente esos extras.

**Baseline medido (2026-09-17): 64 errores en 17 de 56 ficheros.**

> **Desviación respecto a la investigación:** 01-RESEARCH.md midió 85 errores / 21 ficheros con el plugin. La diferencia proviene de los refactors de lint/imports del plan 01-01 (posteriores a la medición de la investigación). El ratchet se fija contra la medición **real**, no contra la cifra histórica.

**Distribución por módulo:**

| Módulo | Errores |
|--------|---------|
| `encino_orm.model.model` | 20 |
| `encino_orm.model.query_builder` | 9 |
| `encino_orm.model.cached` | 6 |
| `encino_orm.pool` | 5 |
| `encino_orm.security.models` | 4 |
| `encino_orm.graphql.filters` | 3 |
| `encino_orm.migration` | 3 |
| `encino_orm.graphql.resolvers` | 2 |
| `encino_orm.oracle` | 2 |
| `encino_orm.http.routes` | 2 |
| `encino_orm.http.parsing` | 2 |
| `encino_orm.graphql.types` | 1 |
| `encino_orm.security.guard` | 1 |
| `encino_orm.mysql` | 1 |
| `encino_orm.mssql` | 1 |
| `encino_orm.model.references` | 1 |
| `encino_orm.base` | 1 |
| **Total** | **64 en 17 ficheros** |

**Entradas del ratchet (`[[tool.mypy.overrides]]`, todas con `ignore_errors = true`):**

| Bloque | Módulos | Errores | Fase que lo levanta |
|--------|---------|---------|---------------------|
| 1 | `encino_orm.model.model` | 20 | Fase 2 (DIAL) + Fase 4 (POOL-03) |
| 1 | `encino_orm.model.query_builder` | 9 | Fase 2 (DIAL-03: `count`/`paginate`/`list_tables`) |
| 1 | `encino_orm.model.cached` | 6 | Fase 3 (DATA-03: invalidación de escritura) |
| 1 | `encino_orm.pool` | 5 | Fase 4 (POOL-01…06) |
| 1 | `encino_orm.security.models` | 4 | Fase 6 (CFG-02: `SecurityConfig` inmutable) |
| 2 | `encino_orm.graphql.*` | 6 | Fase 6 (CFG-03: `exec()` → closures; CFG-04: namespace) |
| 3 | `encino_orm.migration` | 3 | Fase 3 (DATA-01/DATA-02) |
| 3 | `encino_orm.http.routes` | 2 | Fase 6 (CFG-03) |
| 3 | `encino_orm.http.parsing` | 2 | Fase 6 (CFG-03) |
| 3 | `encino_orm.oracle` | 2 | Fase 2 (DIAL-01/02) + Fase 5 (RESL-01) |
| 3 | `encino_orm.mysql` | 1 | Fase 2 (DIAL-01/02) + Fase 5 (RESL-01) |
| 3 | `encino_orm.mssql` | 1 | Fase 2 (DIAL-01/02) + Fase 5 (RESL-01) |
| 3 | `encino_orm.model.references` | 1 | Fase 2 (DIAL-02) |
| 3 | `encino_orm.security.guard` | 1 | Fase 6 (CFG-02) |
| 3 | `encino_orm.base` | 1 | Fase 5 (RESL-02: plantilla `_with_reconnect`) |

Cada módulo lleva su conteo medido y su fase en un comentario dentro de `pyproject.toml`. El bloque abre con un comentario que registra la fecha de medición, el total y la regla de que las entradas se **quitan**, nunca se añaden sin justificación.

## Task 3 — Auditoría de dependencias: semántica y hallazgos

**Semántica de exit de `uv audit` (assumption A2, ahora verificada empíricamente):**

| Comando | Resultado |
|---------|-----------|
| `uv audit --help` | exit **0** |
| `uv audit` (lock actual) | exit **1** — 9 entradas OSV, todas PyJWT 2.12.1 |
| `uv audit --ignore-until-fixed PYSEC-2026-175` | exit **1** — **no suprime** (sigue reportando el aviso) |
| `uv audit --ignore <5 GHSA>` | exit **0** — «Found no known vulnerabilities and no adverse project statuses in 94 packages» |

**Hallazgos preexistentes y disposición** (todos PyJWT 2.12.1, todos con fix en 2.13.0; el proyecto mantiene el cap `PyJWT>=2.8,<2.13`):

| Aviso | Alias | Resumen | Disposición |
|-------|-------|---------|-------------|
| `GHSA-993g-76c3-p5m4` | CVE-2026-48522 / PYSEC-2026-175 | `PyJWKClient` sin allowlist de esquemas → SSRF (`file://`, `ftp://`, `data:`) + forja de tokens | `--ignore` comentado |
| `GHSA-fhv5-28vv-h8m8` | CVE-2026-48524 / PYSEC-2026-177 | `PyJWKClient` peticiones JWKS ilimitadas vía `kid` atacante (DoS) | `--ignore` comentado |
| `GHSA-jq35-7prp-9v3f` | CVE-2026-48523 / PYSEC-2026-176 | Bypass de la allowlist de algoritmos al decodificar con claves `PyJWK`/`PyJWKClient` | `--ignore` comentado |
| `GHSA-w7vc-732c-9m39` | CVE-2026-48525 / PYSEC-2026-178 | DoS no autenticado por decodificación Base64URL sin límite en JWS detached `b64=false` | `--ignore` comentado |
| `GHSA-xgmm-8j9v-c9wx` | CVE-2026-48526 / PYSEC-2026-179 | JWK de clave pública aceptado como secreto HMAC → forja HS256 con familias mixtas (auth bypass) | `--ignore` comentado |

- Los 5 GHSA cubren las 9 entradas OSV (uv deduplica por alias): ignorar los GHSA basta para exit 0.
- `pip-audit` (feed **PyPA**, independiente del feed OSV) sobre `uv export`: **0 hallazgos**, exit 0 — confirma que las dos fuentes son realmente independientes (PyPI aún no tiene los avisos 2026 de PyJWT).
- Cada `--ignore` va acompañado de un comentario en español en `ci.yml` que explica por qué se acepta (cap deliberado, fuera de alcance) y la fase que lo levanta (Fase 6, CFG-02, al revalidar la capa `security` y ampliar el cap).

## Induced-failure proofs

**1. mypy (tipo erróneo fuera del override) — `encino_orm/query.py`, módulo limpio no incluido en ningún `ignore_errors`:**

```text
$ # sonda temporal anadida al final de encino_orm/query.py
_probe_mypy: int = "esto no es un int"
$ uv run mypy encino_orm
encino_orm\query.py:38: error: Incompatible types in assignment (expression has type "str", variable has type "int")  [assignment]
Found 1 error in 1 file (checked 56 source files)
EXIT=1
$ # sonda revertida
$ uv run mypy encino_orm
Success: no issues found in 56 source files   # EXIT=0
```

**2. `uv lock --check` (lockfile divergente):**

```text
$ # pyproject.toml: "aiosqlite" -> "aiosqlite>=0.22.1" (sin re-lockear)
$ uv lock --check
Resolved 95 packages in 40ms
LOCK_EXIT=1
error: The lockfile at `uv.lock` needs to be updated, but `--check` was provided.
hint: To update the lockfile, run `uv lock`.
$ # cota revertida
$ uv lock --check   # EXIT=0
```

## Verification (plan-level)

| Comando | Resultado |
|---------|-----------|
| `uv run mypy encino_orm` | `Success: no issues found in 56 source files` (exit 0) |
| `uv run pytest -q` | `510 passed` |
| `uv lock --check` | exit 0 |
| `uv build --wheel` + namelist | `py.typed OK in dist\encino_orm-0.2.6-py3-none-any.whl` |
| `uv export --format requirements-txt --no-emit-project --no-hashes` | 222 líneas, exit 0 |
| `grep -v '^#' -r encino_orm \| grep -c 'type: ignore'` | `0` |
| `grep -c 'continue-on-error' .github/workflows/ci.yml` | `0` |
| `yaml.safe_load(ci.yml)` | parsea; jobs = `test, lint, typecheck, deps` |
| `uv run ruff check encino_orm tests` | `All checks passed!` |
| `uv run ruff format --check encino_orm tests` | `101 files already formatted` |
| `git status --porcelain` tras `uv build` | limpio (`dist/` gitignorado) |

## Decisions Made

- **Ratchet puro, sin arreglos mecánicos de tipos.** Se siguió la opción por defecto del plan (research A6): los 64 errores se cubren con `ignore_errors` por módulo, no con arreglos de `var-annotated`/`assignment`. Mantiene el commit puramente de configuración + empaquetado + CI, bisectable y sin cambio de comportamiento.
- **El job `typecheck` sincroniza los extras, no `--group dev`.** Decisión forzada por W3: el ratchet se midió con `fastapi`/`PyJWT`/`strawberry-graphql` importables; sin ellos `ignore_missing_imports` los vuelve `Any` y el gate mediría otro conjunto de errores.
- **Allowlist con `--ignore`, no `--ignore-until-fixed`.** El flag que sugiere el plan no suprime avisos que ya tienen fix (verificado empíricamente); con fix=2.13.0 disponible, era un no-op.
- **`pip-audit` vía fichero temporal.** `pip-audit -r -` no acepta stdin y `--locked .` no reconoce `uv.lock` (verificado: «no lockfiles found»); el puente es `uv export ... > "$RUNNER_TEMP/uv-export.txt"`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `--ignore-until-fixed` no suprime avisos con fix disponible**
- **Found during:** Task 3 (job `deps`)
- **Issue:** el plan propone `uv audit --ignore-until-fixed <ID>` para la allowlist. Verificado empíricamente: `uv audit --ignore-until-fixed PYSEC-2026-175` sigue reportando el aviso (exit 1), porque uv solo ignora «until fixed» cuando **no** hay fix. Los 5 avisos tienen fix (2.13.0), así que el flag era un no-op y el gate habría quedado rojo.
- **Fix:** se usa `uv audit --ignore <ID>` para cada uno de los 5 GHSA, con el comentario en español exigido por el plan (motivo + fase de levantamiento).
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** `uv audit --ignore <5 GHSA>` → exit 0; `uv audit` sin ignores → exit 1.
- **Committed in:** `970cb6e` (Task 3)

**2. [Rule 3 - Blocking] `pip-audit -r -` no acepta stdin**
- **Found during:** Task 3 (cross-check `pip-audit`)
- **Issue:** el plan propone `uv export ... | pip-audit -r -`. pip-audit responde `invalid requirements input: -` (exit 1). Tampoco `--locked .` sirve: `no lockfiles found in .` (no lee `uv.lock`).
- **Fix:** puente por fichero temporal: `uv export ... > "$RUNNER_TEMP/uv-export.txt"` y `uv run pip-audit -r "$RUNNER_TEMP/uv-export.txt"`.
- **Files modified:** `.github/workflows/ci.yml`
- **Verification:** el puente por fichero temporal → «No known vulnerabilities found» (exit 0); la forma con pipe → exit 1.
- **Committed in:** `970cb6e` (Task 3)

**3. [Rule 3 - Blocking/Medición] El baseline de mypy difiere del de la investigación**
- **Found during:** Task 2 (medición)
- **Issue:** 01-RESEARCH.md midió 85 errores / 21 ficheros con el plugin; la medición real es 64 / 17. Los refactors de lint/imports del plan 01-01 (posteriores a la investigación) eliminaron errores.
- **Fix:** el ratchet se fija contra la medición real (64 / 17) y el SUMMARY registra el entorno exacto. No se «infló» el override para igualar la cifra histórica.
- **Files modified:** `pyproject.toml`
- **Verification:** `uv run mypy encino_orm` → exit 0 con 15 entradas de override; sin overrides → 64 errores.
- **Committed in:** `23009b4` (Task 2)

---

**Total deviations:** 3 auto-corregidas (3 bloqueantes; la 3.ª además de medición).
**Impact on plan:** Ninguna cambia el alcance ni el comportamiento del ORM. Las dos primeras son correcciones de comandos del plan que no funcionaban tal cual (flags/sintaxis); la tercera es una medición honesta que sustituye una cifra histórica. Sin scope creep.

## Issues Encountered

- **9 avisos reales de PyJWT quedan allowlisteados.** El cap `PyJWT>=2.8,<2.13` bloquea las correcciones (2.13.0) e incluye un auth-bypass y un SSRF. El plan ordena explícitamente allowlistear hallazgos preexistentes en lugar de resolverlos, y ampliar el cap es un cambio de dependencia con riesgo de ruptura en la capa `security`, fuera del alcance de una fase de «cero cambio de comportamiento». **Requiere decisión de seguimiento:** ampliar el cap al revalidar la capa `security` (Fase 6, CFG-02) y retirar los 5 `--ignore`. Registrado como concern en STATE.md.
- `uv audit` es **experimental** y emite un `warning` en cada corrida (`Pass --preview-features audit-command to disable`). No afecta al exit code.
- `uv audit` necesita red (feed OSV) y `pip-audit` también (feed PyPI); en CI ambos son alcanzables.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: supply-chain-residual | `.github/workflows/ci.yml` | 5 avisos GHSA de PyJWT 2.12.1 (auth bypass, SSRF, DoS) quedan `--ignore`-ados de forma temporal hasta ampliar el cap `<2.13` (Fase 6, CFG-02). Riesgo residual documentado; el escáner sigue bloqueante para cualquier aviso nuevo. |

Las mitigaciones del plan (T-01-01 dos fuentes de aviso independientes + `uv lock --check`; T-01-03 jobs bloqueantes sin `continue-on-error`, probados por fallo inducido; T-01-04 uv pineado y deps resueltas por lock auditado; T-01-05 cero `# type: ignore`; T-01-SC checkpoint humano bloqueante) están implementadas y verificadas.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **Listo para 01-03:** `pytest-cov 7.1.0` y `coverage 7.16.1` ya están instalados; el plan 01-03 solo tiene que cablearlos. `pyproject.toml` ya contiene `[tool.mypy]`, así que 01-03 debe añadir `[tool.pytest.ini_options]` endurecido y `[tool.coverage]` sin tocar el ratchet de mypy.
- **Listo para 01-04/01-05:** los jobs `typecheck` y `deps` ya están en `ci.yml`; 01-04 añade el interruptor de motores y `release.yml needs: CI` sobre esta base.
- **Bloqueante de seguimiento (no de esta fase):** retirar los 5 `--ignore` de PyJWT al ampliar el cap `<2.13`; sin dueño de fase explícito más allá de la revalidación de la capa `security` en Fase 6.
- Todo fichero nuevo debe nacer `ruff check`/`ruff format`-clean **y** mypy-clean bajo el ratchet vigente.

---
*Phase: 01-safety-net-ci-gates-test-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `encino_orm/py.typed` y `01-02-SUMMARY.md` existen en disco.
- Los commits `23009b4` y `970cb6e` existen en el historial.
- `uv run mypy encino_orm` → exit 0; `uv run pytest -q` → 510 passed; `uv lock --check` → exit 0; `py.typed` presente en la wheel; `git status --porcelain` limpio.
