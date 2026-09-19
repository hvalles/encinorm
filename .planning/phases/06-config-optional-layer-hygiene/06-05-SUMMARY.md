---
phase: 06-config-optional-layer-hygiene
plan: 05
subsystem: docs-and-gates
tags: [docs, mkdocs, trust-boundaries, changelog, ruff, mypy, pyjwt, uv-lock, supply-chain, ci]

# Dependency graph
requires:
  - phase: 06-01
    provides: "ConnectionRegistry / resolve_db sin global mutable (Wave 1)"
  - phase: 06-02
    provides: "SecurityConfig + security_dependencies (Wave 1)"
  - phase: 06-03
    provides: "Handlers REST con closures + __signature__, sin exec() (Wave 2)"
  - phase: 06-04
    provides: "Resolvers GraphQL sin exec() + namespace por build (Wave 2)"
provides:
  - "docs/trust-boundaries.md: fronteras de confianza de Filter.raw/Query/db.fn.* con ejemplos seguros e inseguros (CFG-05)"
  - "tests/test_trust_boundaries.py: los parsers HTTP/GraphQL no pueden emitir Filter.raw (regresion)"
  - "CHANGELOG.md [Unreleased]: CFG-01..CFG-05 con viejo/nuevo y ownership a 08-04"
  - "per-file-ignores S102/B008 retirados; ratchet mypy con causas reescritas (residuales conservados)"
  - "PyJWT>=2.8,<2.15 (2.14.0) con uv.lock regenerado y auditorias limpias; ci.yml sin ignores GHSA"
affects: [verify-phase-06, 08-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pagina de fronteras de confianza con ejemplos SEGURO/INSEGURO custodiada por un test de presencia + un test de regresion de los parsers"
    - "Retirada de supresiones de gate SOLO tras probe `ruff --isolated`/`mypy`; residual ajeno se conserva con causa escrita (precedente 04-04)"
    - "Bump de dependencia fail-closed: commit aislado + uv lock --upgrade-package + doble feed (OSV/PyPA) sin ignores"

key-files:
  created:
    - docs/trust-boundaries.md
    - tests/test_trust_boundaries.py
    - .planning/phases/06-config-optional-layer-hygiene/deferred-items.md
  modified:
    - docs/reference/filter.md
    - docs/reference/sql.md
    - docs/reference/db.md
    - docs/reference/context.md
    - docs/integrations.md
    - docs/design/9-singleton.md
    - docs/getting-started.md
    - README.md
    - mkdocs.yml
    - encino_orm/model/filter.py
    - CHANGELOG.md
    - pyproject.toml
    - .github/workflows/ci.yml
    - uv.lock

key-decisions:
  - "Las entradas del ratchet mypy asignadas a Fase 6 (http.routes, http.parsing, security.guard, graphql.*, security.models) SE CONSERVAN con la causa reescrita: retirarlas deja `mypy encino_orm` rojo; el plan autoriza el residual con causa escrita"
  - "Los per-file-ignores S102/B008 (routes/schema/guard/test_security) SI se retiran: probe `ruff --isolated --select S102,B008` limpio y `ruff check .` verde"
  - "El cap de PyJWT sube a >=2.8,<2.15 (2.14.0); `uv lock` solo no actualiza la version fijada, hay que usar `uv lock --upgrade-package PyJWT`"
  - "Ambos feeds (uv audit OSV + pip-audit PyPA) limpios sin ignores y tests/test_security.py verde -> se retiran los 5 ignores GHSA de ci.yml"

patterns-established:
  - "Documentacion de frontera de confianza con token explicito INSEGURO y test de presencia que impide que la pagina desaparezca o se vacie"
  - "Fail-closed de dependencias: evidencia de dos feeds independientes antes de tocar el gate de CI"

requirements-completed: [CFG-05]

# Metrics
duration: 20min
completed: 2026-09-19
---

# Phase 6 Plan 5: Fronteras de confianza, CHANGELOG y gates (CFG-05) Summary

**Documenta `Filter.raw`/`Query`/`db.fn.*` con ejemplos seguros e inseguros (pagina nueva + docstring + test de regresion), cierra el `CHANGELOG` de CFG-01..CFG-05, retira los `per-file-ignores` S102/B008 y sube el cap de `PyJWT` a `<2.15` (2.14.0) con `uv.lock` regenerado y auditorias OSV/PyPA limpias, dejando `ci.yml` sin ignores GHSA.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-19T06:5xZ
- **Completed:** 2026-09-19T07:14Z
- **Tasks:** 3/3
- **Files modified:** 17 (3 creados, 14 modificados)

## Accomplishments

- **CFG-05 (Success Criterion 5):** `docs/trust-boundaries.md` con tres secciones exactas (`## Filter.raw`, `## Query`, `## db.fn.*`), cada una con anchor de codigo, un ejemplo `SEGURO` y uno `INSEGURO`, la limitacion declarada de `Query` (un `{n}` dentro de un literal) y la regla "los valores SIEMPRE viajan ligados". Solo placeholders, sin credenciales reales.
- Docstring de `Filter.raw` (`encino_orm/model/filter.py`) declarando la frontera: el fragmento se reemite VERBATIM, solo se reindexan los `{n}`, el llamador no debe interpolar entrada no confiable y los valores van en `params`.
- `tests/test_trust_boundaries.py` (5 tests): los parsers HTTP/GraphQL no construyen `Filter.raw` (chequeo de fuente + conjunto cerrado de operadores), la pagina conserva los tres encabezados y un bloque `INSEGURO`, y `Filter.raw` reemite verbatim ligando los valores.
- Referencias cruzadas en `reference/{filter,sql,db,context}.md`; `mkdocs.yml` con la entrada de nav; `docs/integrations.md` al patron `SecurityConfig`/`security_dependencies` con los globales marcados como deprecados; `docs/design/9-singleton.md` apuntando a `ConnectionRegistry`; banners de deprecacion en `README.md` y `docs/getting-started.md`.
- **CHANGELOG `[Unreleased]`:** cinco entradas nuevas (CFG-01..CFG-05) con comportamiento viejo/nuevo y nota de ownership hacia la Fase 8 (`08-04`); la retirada de los globales (no solo su deprecacion) queda asignada a `REL-01`.
- **Gates:** retirados los `per-file-ignores` `"S102"`/`"B008"` de `encino_orm/http/routes.py`, `encino_orm/graphql/schema.py`, `encino_orm/security/guard.py` y `tests/test_security.py`. El ratchet mypy conserva sus entradas con la causa reescrita (ver Deviations).
- **PyJWT (CFG-02):** cap `>=2.8,<2.13` → `>=2.8,<2.15`; `uv.lock` regenerado a `pyjwt 2.14.0`; `uv audit` (OSV) y `pip-audit` (PyPA) limpios sin ignores; `ci.yml` sin las 5 excepciones GHSA; `CHANGELOG` con el estado final (marcador `PENDIENTE_BUMP` eliminado).

## Task Commits

Cada tarea se commiteo atomicamente (Task 3 en dos commits aislados, como pide el plan):

1. **Task 1: docs de fronteras de confianza + docstring + test** — `d3c8cef` (docs)
2. **Task 2: CHANGELOG [Unreleased] CFG-01..CFG-05** — `2a39ef2` (docs)
3. **Task 3A: retirada de per-file-ignores + ratchet mypy con causas** — `cdebbe3` (chore)
4. **Task 3B: bump de PyJWT + ci.yml sin ignores + uv.lock + CHANGELOG final** — `5087bd2` (chore)

## PyJWT Outcome (bump)

**Resultado: BUMP aplicado (no revertido).** Evidencia:

| Feed | Comando | Resultado |
|------|---------|-----------|
| OSV | `uv audit` (sin `--ignore`) | "Found no known vulnerabilities and no adverse project statuses in 97 packages" (exit 0) |
| PyPA | `uv export … \| pip-audit -r` | "No known vulnerabilities found" |
| PyPA (directo) | `pip-audit -r <pyjwt==2.14.0>` | "No known vulnerabilities found" |
| Tests | `uv run pytest tests/test_security.py -q` | 26 passed |
| Lock | `uv lock --check` | exit 0 (`pyjwt 2.12.1 → 2.14.0`) |

- `pyproject.toml`: `PyJWT>=2.8,<2.15` (`grep -c` == 1); `PyJWT>=2.8,<2.13` == 0.
- `.github/workflows/ci.yml`: `grep -c "GHSA-"` == 0; el job `deps` ejecuta `uv audit` desnudo.
- `CHANGELOG.md`: `grep -c "PENDIENTE_BUMP"` == 0.

## Files Created/Modified

- `docs/trust-boundaries.md` — **nuevo**; las tres fronteras con ejemplos seguros/inseguros y resumen.
- `tests/test_trust_boundaries.py` — **nuevo**; regresion de los parsers + presencia de la pagina + contrato verbatim de `Filter.raw`.
- `.planning/phases/06-config-optional-layer-hygiene/deferred-items.md` — **nuevo**; el cross-check `pip-audit` de CI no cubre los extras opcionales (fuera de alcance).
- `encino_orm/model/filter.py` — docstring de `Filter.raw` (sin cambio de comportamiento).
- `docs/reference/{filter,sql,db,context}.md` — referencia cruzada + `ConnectionRegistry` en `context.md`.
- `docs/integrations.md`, `docs/design/9-singleton.md`, `docs/getting-started.md`, `README.md`, `mkdocs.yml` — alineacion con `SecurityConfig`/`ConnectionRegistry` y nav.
- `CHANGELOG.md` — entradas CFG-01..CFG-05 y estado final del cap de PyJWT.
- `pyproject.toml` — per-file-ignores retirados, causas del ratchet mypy reescritas, cap de PyJWT subido.
- `.github/workflows/ci.yml` — job `deps` sin ignores.
- `uv.lock` — `pyjwt 2.14.0`.

## Decisions Made

- **Ratchet mypy conservado con causa.** Se intentó retirar `encino_orm.http.routes`, `encino_orm.security.guard`, `encino_orm.http.parsing`, `encino_orm.graphql.*` y `encino_orm.security.models`; los cinco conservan errores residuales de tipado, asi que se mantienen con la causa reescrita (nunca se anadio un `# type: ignore` inline).
- **Per-file-ignores retirados.** Probe `ruff check --isolated --select S102,B008` sobre los cuatro ficheros → "All checks passed!"; `ruff check .` verde tras retirarlos.
- **Bump con `uv lock --upgrade-package PyJWT`.** `uv lock` a secas mantuvo la version fijada (2.12.1) pese a ampliar el rango; el upgrade explicito la subio a 2.14.0.
- **Snapshot ordering:** no aplica (este plan no toca snapshots); `git diff --name-only` de ambos commits no incluye `tests/__snapshots__/`.

## Deviations from Plan

### Auto-fixed / plan-fallback issues

**1. [Rule 3 — plan fallback] Las entradas del ratchet mypy NO se pudieron retirar; se conservan con causa escrita**

- **Found during:** Task 3A.
- **Issue:** El plan esperaba que tras el codigo de Wave 2 las entradas `encino_orm.http.routes`, `encino_orm.security.guard`, `encino_orm.http.parsing` (y, como intento, `encino_orm.graphql.*` y `encino_orm.security.models`) fueran retirables. **No lo son.** Probes con `mypy --config-file` (quitando solo cada entrada y conservando el resto):
  - `http.routes` → **5** errores (2 `misc` de variantes de la closure `handler`, 1 `valid-type`, 1 `arg-type`, 1 `attr-defined`). Baseline previo: 2.
  - `security.guard` → **2** errores (`"object" has no attribute "credentials"`, `union-attr` sobre `PermissionSet | None`). Baseline: 1.
  - `http.parsing` → **2** errores (`var-annotated`, `misc`). Sin cambio.
  - `graphql.*` → **7** errores en 4 ficheros (`filters` 3, `resolvers` 2, `types` 1 — `Name "child.__name__" is not defined` en anotaciones `strawberry.lazy` construidas con el nombre dinamico del hijo, y `schema` 1 `misc`). El SUMMARY de 06-04 afirmaba que los `name-defined` eran artefacto del `exec()`; es **incorrecto**: sobreviven en `resolvers.py`/`types.py`, ajenos a `schema.py`.
  - `security.models` → **4** errores (`valid-type` x3 por `STR_100(required=True)` como anotacion + `call-arg` x1).
- **Fix:** Se aplica la REGLA del propio plan: retirar SOLO si `mypy encino_orm` sigue 0; como no lo esta, cada entrada se **conserva** y su comentario se reescribe con el residual y su causa (precedente `04-04`). No se anadio ningun `# type: ignore`.
- **Impacto en acceptance_criteria:** `grep -c "encino_orm.http.routes" pyproject.toml` == 1 (el plan pedia 0) y `encino_orm.security.guard` == 1 (pedia 0); `encino_orm.http.parsing` == 1, permitido explicitamente por el criterio ("o la entrada sigue con la causa escrita; W3"). Los `per-file-ignores` S102/B008 SI se retiraron (los greps correspondientes dan 0). El `success_criteria` de la fase cubre este caso: "las entradas del ratchet mypy ... se retiran, **o el residual queda con causa escrita**".
- **Nota de deuda:** los errores de `http.routes` suben de 2 a 5 y `security.guard` de 1 a 2 por el patron de closures; el gate queda verde (entradas conservadas) pero es un residual de tipado a limpiar en una fase de calidad posterior.
- **Files modified:** `pyproject.toml`
- **Commit:** `cdebbe3`

**2. [Rule 3 — desviacion de comando] `uv lock` no actualiza la version fijada**

- **Found during:** Task 3B.
- **Issue:** `uv lock` tras ampliar el cap dejo `pyjwt 2.12.1` en `uv.lock` (uv conserva la version bloqueada si sigue siendo valida), por lo que `uv audit` seguia reportando los avisos.
- **Fix:** `uv lock --upgrade-package PyJWT` → `Updated pyjwt v2.12.1 -> v2.14.0`. Desviacion del literal "ejecuta `uv lock`", pero necesaria para que el bump sea efectivo (el plan exige auditorias limpias).
- **Files modified:** `uv.lock`
- **Commit:** `5087bd2`

### Out-of-scope discoveries (deferred)

- El `pip-audit` del job `deps` no audita los extras opcionales (`uv export` sin `--all-extras`), por lo que no cubre `PyJWT`. Registrado en `deferred-items.md`; no se corrige aqui (fuera de alcance).

## Known Stubs

None. La pagina de fronteras tiene contenido real y el test la custodia; no hay valores placeholder ni datos sin cablear.

## Threat Flags

None. No se introduce superficie de red, autenticacion, acceso a ficheros ni cambios de esquema fuera del `<threat_model>` del plan. El unico cambio de dependencia es de VERSION sobre `PyJWT` (ya declarado), con doble feed verificado.

## Issues Encountered

- El primer `pytest` de `test_trust_boundaries.py` fallo porque la pagina usaba `### Inseguro` y el test exigia el token `INSEGURO`; se alinearon los encabezados a `### Ejemplo SEGURO`/`### Ejemplo INSEGURO` (Rule 1, en el mismo Task 1).
- El `pip-audit` local choco con el `2>&1` que mezclaba el progreso de `uv export` en el fichero de requisitos; se replico el comando de CI sin `2>&1`.

## Verification (end-of-plan gates)

- `uv run pytest tests/test_trust_boundaries.py -q` → 5 passed.
- `uv run pytest tests/test_security.py -q` → 26 passed.
- `uv run pytest -q -m "not integration and not optional_engine"` → 964 passed, 88 deselected, 12 snapshots passed.
- `uv run pytest -q` → 1052 passed, 12 snapshots passed.
- `uv run ruff check .` / `uv run ruff check encino_orm tests` → All checks passed.
- `uv run ruff format --check encino_orm tests` → 124 files already formatted.
- `uv run mypy encino_orm` → Success: no issues found in 61 source files.
- `uv run mkdocs build --strict` → exit 0.
- `uv lock --check` → exit 0.
- `grep -cE '"S102"' pyproject.toml` → 0; `grep -cE '"B008"' pyproject.toml` → 0.
- `grep -c "GHSA-" .github/workflows/ci.yml` → 0; `grep -c "PENDIENTE_BUMP" CHANGELOG.md` → 0; `grep -c "PyJWT>=2.8,<2.15" pyproject.toml` → 1.
- `git diff --name-only` de ambos commits de Task 3 → sin `tests/__snapshots__/` ni codigo de Wave 2.

## Next Phase Readiness

- CFG-05 cerrado: los criterios de exito de la fase 1-5 quedan cubiertos por los planes 06-01..06-05.
- Residual de tipado (ratchet mypy) y el gap de `pip-audit` sobre extras quedan documentados para una fase de calidad / CI posterior.
- `06-05` fue el unico dueno de `pyproject.toml`, `CHANGELOG.md`, `mkdocs.yml` y `ci.yml` (Pitfall 8): sin conflictos de concurrencia.
- Sin bloqueos.

---

*Phase: 06-config-optional-layer-hygiene*
*Completed: 2026-09-19*

## Self-Check: PASSED

- FOUND: `docs/trust-boundaries.md`
- FOUND: `tests/test_trust_boundaries.py`
- FOUND: `.planning/phases/06-config-optional-layer-hygiene/deferred-items.md`
- FOUND: commit `d3c8cef` (docs de fronteras + test)
- FOUND: commit `2a39ef2` (CHANGELOG)
- FOUND: commit `cdebbe3` (gates / per-file-ignores)
- FOUND: commit `5087bd2` (bump PyJWT + ci.yml + uv.lock)
