# Phase 1: Safety Net — CI Gates & Test Infrastructure - Context

**Gathered:** 2026-09-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Hacer que CI pueda **fallar de verdad** antes de tocar cualquier código de producción. Esta fase entrega la red de seguridad: lint/formato, tipos, cobertura por motor, un interruptor de motores requeridos que falla en vez de saltar, un gate de tests omitidos, y tests de caracterización del pool escritos contra la implementación actual.

Entrega: infraestructura de calidad verificable. **No** entrega correcciones de comportamiento del ORM (eso empieza en Fase 2) ni cambios en la superficie pública.

</domain>

<decisions>
## Implementation Decisions

### Motores requeridos
- **D-01:** El interruptor de motores requeridos exige **MySQL + PostgreSQL** en Fase 1 — exactamente los servicios que ya existen en `.github/workflows/ci.yml`. Queda **extensible** para que Fase 2 (DIAL-08) añada MariaDB, Redis, MSSQL y Oracle sin rediseño.
- **D-02:** Los motores no requeridos (MariaDB, Redis, MSSQL, Oracle) se omiten con un **marker explícito** (p. ej. `optional_engine`). El gate de tests omitidos falla **solo por skips NO marcados** — así un motor ausente legítimo no produce falsos positivos.
- **D-03:** El interruptor se activa **solo en CI mediante variable de entorno** (p. ej. `ENCINO_ORM_REQUIRE_ENGINES`). En local, un motor ausente sigue saltando. Se descarta la auto-detección porque un fallo de servicio degradaría silenciosamente a verde — el anti-patrón que motiva la fase.

### Política de cobertura
- **D-04:** Estructura de umbrales: **piso global bajo (ratchet) + piso alto por dialecto**. El piso alto aplica al seam `dialects/` y a los builders compartidos, para que SQLite no enmascare rutas dialectales.
- **D-05:** La cobertura arranca como **ratchet no-baja**: se fija el baseline del estado actual y el gate falla solo si la cobertura **baja**. No se exigen números absolutos en Fase 1.
- **D-06:** Fase 1 monta el **mecanismo** (`parallel = true`, `COVERAGE_FILE` por job, `coverage combine`, ratchet global). El **piso por dialecto se define en Fase 2**, cuando el seam `dialects/` exista al que aplicarlo.

### Endurecer pytest
- **D-07:** `filterwarnings = ["error", ...]` con una **allowlist acotada, explícita y comentada** para warnings conocidos y justificados. Cualquier warning nuevo falla.
- **D-08:** Registrar los markers `integration`, `optional_engine`, `concurrency` y `benchmark`. Aplicar `integration` a los tests de motor real para que el comando documentado en `README.md:130` (`uv run pytest -m "not integration"`) funcione de verdad.
- **D-09:** Alcance de Fase 1: **config endurecida + arreglos mínimos** de las incompatibilidades que aparezcan (markers no registrados, warnings, `xfail`), en commits **separados y bisectables**. No se reescriben asserts genéricos (`pytest.raises(Exception)`) ni asserts de estado privado en esta fase.

### the agent's Discretion
- La selección exacta de reglas de `ruff` a habilitar en el primer ruleset (la investigación recomienda empezar por `E/W/F/I/UP/B/C4/SIM/PERF/FURB/ASYNC/RUF/S/PT` y diferir `ANN`/`D`/`PL`).
- El valor numérico exacto del piso global inicial del ratchet (se fija contra el baseline medido).
- La versión exacta de `uv` a fijar (la investigación apunta a 0.12.15 como mínimo con `uv audit`).
- La forma concreta del gate post-run sobre JUnit-XML.

### Folded Todos
Ninguno — no había todos pendientes para esta fase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Contexto de proyecto y alcance
- `.planning/PROJECT.md` — Core value y límites del milestone (hardening sin congelar API)
- `.planning/REQUIREMENTS.md` — Los 47 requisitos v1; esta fase cubre **CI-01…CI-09**
- `.planning/ROADMAP.md` — Fase 1 con sus 5 planes (01-01…01-05) y las **Restricciones Duras de Ordenamiento**; incluye la sección "Research Corrections Carried Into This Roadmap"
- `.planning/STATE.md` — Posición actual y blockers conocidos

### Investigación (decisiones y trampas)
- `.planning/research/STACK.md` — Versiones verificadas y bocetos de configuración de ruff/mypy/pytest-cov/uv; es la referencia principal para los planes 01-01…01-03
- `.planning/research/PITFALLS.md` — Pitfall 1 ("CI verde que no verifica nada"), Pitfall 2 (cobertura que enmascara dialectos), Pitfall 12 (gates big-bang), Pitfall 15 (ambigüedad de loop scope), Pitfall 18 (límites de dependencias), Pitfall 24 (`pytest.raises` amplio)
- `.planning/research/SUMMARY.md` — Fase 1: criterio de salida ("quitar el servicio de un motor requerido hace fallar su job") y flags de investigación

### Mapa del código
- `.planning/codebase/TESTING.md` — Framework, estructura, patrón skip-on-connection-failure, ausencia de markers registrados y de cobertura
- `.planning/codebase/CONCERNS.md` — Deuda técnica de tooling ("No linting, formatting, or type-checking tooling", "No coverage measurement or gate")

### Configuración viva
- `.github/workflows/ci.yml` — Matriz actual (Python 3.10–3.13), servicios MySQL 8.0 + PostgreSQL 16, `timeout-minutes: 15`, `uv run pytest -q` sin gates
- `.github/workflows/release.yml` — Debe pasar a depender de CI (CI-08)
- `pyproject.toml` — `[tool.pytest.ini_options]` mínimo; `ruff>=0.16.8` ya en `[dependency-groups].dev` pero sin configurar; `py.typed` ausente
- `docker-compose.yml` / `docs/docker.md` — Topología local de servicios para los motores opcionales

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`ruff>=0.16.8`** ya declarado en `[dependency-groups].dev` de `pyproject.toml` — solo falta configuración y un job de CI; no requiere añadir dependencia.
- **`pytest-asyncio>=1.4.0`** ya en uso con `asyncio_mode = "auto"`; solo falta fijar los loop scopes explícitos.
- **`httpx` ASGI transport** ya se usa para los tests in-process de las capas REST/GraphQL — no hace falta infraestructura E2E nueva.
- **Fakes escritos a mano** (`tests/test_pool.py`: `FakeDb`, `fake_engine` con `monkeypatch.setitem(pool_module._ENGINES, ...)`) son el patrón aceptado; preferirlos a `unittest.mock`.

### Established Patterns
- **Skip-on-connection-failure**: los tests de motor hacen `try/except Exception: pytest.skip(...)` (`tests/test_postgresql.py:58-78`, `tests/test_mysql.py:25`, `tests/test_mariadb.py:38`, `tests/test_mssql.py:124-135`, `tests/test_oracle.py:103`, `tests/test_redis_cache.py:28-35`). Este es el patrón que el interruptor CI-01 debe invertir en CI.
- **Config por env var**: los motores leen `ENCINO_ORM_<ENGINE>_HOST/PORT/USER/PASSWORD/DB` con defaults; CI los inyecta en el step de test.
- **Fixtures con `yield`** para teardown y `@pytest.mark.asyncio` explícito pese a `asyncio_mode = "auto"` (mayoría del código).
- **Commits mecánicos aislados** con `.git-blame-ignore-revs` para el commit de formato (según `research/STACK.md`).
- **Tests white-box** que importan helpers privados (`_rowcount`, `_to_postgres`, `_build_parser`) son un patrón aceptado en este repo.

### Integration Points
- `[tool.pytest.ini_options]` en `pyproject.toml` — donde viven `filterwarnings`, `markers`, `xfail_strict` y los loop scopes.
- `.github/workflows/ci.yml` — se añaden jobs (lint, tipos, cobertura, matriz) y el env del interruptor.
- `.github/workflows/release.yml` — se le añade `needs:` apuntando a CI (CI-08).
- `tests/conftest.py` — punto natural para la lógica del interruptor y los markers.
- `py.typed` (nuevo archivo en `encino_orm/`) — requisito de PEP 561 para que mypy sea significativo.

</code_context>

<specifics>
## Specific Ideas

- El criterio de salida de la fase (de `research/SUMMARY.md`): **quitar el servicio de un motor requerido debe hacer FALLAR su job de CI**, y borrar `tests/test_postgresql.py` debe hacer fallar el job de cobertura por dialecto.
- Los planes del roadmap ya fijan la secuencia de aterrizaje: 01-01 (uv + ruff formato + ruleset), 01-02 (mypy + py.typed + escaneo de dependencias), 01-03 (pytest config + pytest-cov), 01-04 (switch + gate JUnit + `release.yml needs: CI`), 01-05 (caracterización del pool).
- El comando del README `uv run pytest -m "not integration"` hoy no hace nada; esta fase lo convierte en real (D-08).

</specifics>

<deferred>
## Deferred Ideas

- **Matriz multi-motor completa (MariaDB/Redis/MSSQL/Oracle)** — es DIAL-08, Fase 2. Fase 1 solo deja el interruptor extensible.
- **Piso de cobertura por dialecto** — se define en Fase 2 sobre el seam `dialects/`.
- **Reescritura de asserts genéricos y de estado privado** — no entra en Fase 1; los tests de caracterización del pool (plan 01-05) capturan el comportamiento actual tal cual.
- **`uv check` / `ty` como gate** — pre-1.0 y experimental; la investigación recomienda mantenerlo local hasta comparar su ruido contra mypy.

### Reviewed Todos (not folded)
Ninguno — no había todos pendientes para esta fase.

</deferred>

---

*Phase: 1-Safety Net — CI Gates & Test Infrastructure*
*Context gathered: 2026-09-17*
