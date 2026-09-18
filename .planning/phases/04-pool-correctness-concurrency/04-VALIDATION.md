---
phase: 4
slug: pool-correctness-concurrency
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-18
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Generated from the 6 plans (`04-01`…`04-06`). Every task's `<verify><automated>` is reproduced here as the per-task contract; the manual-only items are the ones that cannot be asserted on the local Windows host.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) + **pytest-timeout 2.4.0** + **pytest-repeat 0.9.4** (instalados por `04-05`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (markers `concurrency`/`stress`, `timeout = 0` global, `filterwarnings=["error"]`, `xfail_strict`, `--strict-markers`) |
| **Quick run command** | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py tests/test_pool_concurrency.py -q` |
| **Full suite command** | `uv run pytest -q` (6 contenedores locales; en CI, `ENCINO_ORM_REQUIRE_ENGINES`) |
| **CI run command** | `uv run pytest -q -m "not optional_engine" --timeout-method=signal --junitxml=junit.xml` |
| **Estimated runtime** | ~30 s quick run; ~90 s full local suite (Oracle/MSSQL en el job `engine-heavy`) |

**Restricción de piso (Research Correction #4):** Python 3.10. Prohibido `asyncio.Barrier`, `asyncio.timeout`, `TaskGroup` y `except*` en librería y tests. La barrera de concurrencia es `EventBarrier` (solo `asyncio.Event`).

---

## Sampling Rate

- **After every task commit:** quick run del fichero que toca el plan (ver columna `Automated Command`).
- **After every plan wave:** `uv run pytest -q` (6 motores locales).
- **Before `/gsd-verify-work`:** suite completa verde + `uv run ruff check encino_orm tests` + `uv run ruff format --check encino_orm tests` + `uv run mypy encino_orm` + `uv lock --check` + `tools/ci/check_skips.py` (0 skips).
- **Max feedback latency:** ~30 s (quick run); los tests de barrera llevan `@pytest.mark.timeout(10–20)` para acotar el peor caso.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure / Correct Behavior | Test Type | Automated Command | Expected Result | File Exists | Status |
|---------|------|------|-------------|------------|---------------------------|-----------|-------------------|-----------------|-------------|--------|
| 04-01-01 | 04-01 | 1 | POOL-01 | T-04-01-04 | `PooledConnection` concentra el estado; `_last_id`/`_last_used` del pool desaparecen; `resolve_db()` desenvaina `.driver` | unit (fake `Db`) | `uv run pytest tests/test_pool.py -q` | green; `grep -c "_last_id" encino_orm/pool.py` == 0; `handle.driver.calls` en `test_standalone_operation_commits`; `_last_used` fuera de `test_pool_characterization.py` | ❌ W0 | ⬜ pending |
| 04-01-02 | 04-01 | 1 | POOL-02 | T-04-01-01, T-04-01-02 | `acquire()` no supera `max_size` bajo barrera; el cupo vuelve si la creación falla; doble `release()` no duplica | concurrency + unit | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` | green; `-k "overshoot or double_release"` green; evidencia RED (`_size == 5`) y GREEN (`_size <= 2`) en el SUMMARY | ✅ (invertir) | ⬜ pending |
| 04-01-03 | 04-01 | 1 | POOL-01/02 | T-04-01-03 | `last_id()` fuera de transacción → `0`; `session()` no fija `_current_connection` y ata `handle.driver` | unit + integration SQLite | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py tests/test_d_recommendations.py -q` | green; `grep -c "_last_id" tests/test_pool_characterization.py` == 0 | ✅ (invertir) | ⬜ pending |
| 04-05-01 | 04-05 | 1 | POOL-07 | T-04-05-SC | Legitimidad de `pytest-timeout`/`pytest-repeat` verificada antes de instalar | checkpoint:human-verify (`blocking-human`) | `uv run python -c "…pypi.org/pypi/{pytest-timeout,pytest-repeat}/json…"` | versiones `2.4.0`/`0.9.4` + upstream `github.com/pytest-dev/...`; aprobación humana explícita (nunca auto-aprobable) | ❌ W0 | ⬜ pending |
| 04-05-02 | 04-05 | 1 | POOL-07 | T-04-05-02, T-04-05-03 | Dev deps pinadas + `uv.lock` + marker `stress` + `--timeout-method=signal` en CI | config | `uv lock --check && uv run python -c "import pytest_timeout, pytest_repeat; print('plugins OK')" && uv run pytest --collect-only -q -m stress` | green; `uv lock --check` == 0; marker registrado (sin fallo de `--strict-markers`) | ❌ W0 | ⬜ pending |
| 04-05-03 | 04-05 | 1 | POOL-07 | T-04-05-01 | `EventBarrier`/`FakeDb`/`BlockingFakeDb` 3.10-safe, sin `unittest.mock` | unit (helper) | AST check (identificadores de código `Barrier`/`TaskGroup`/`timeout` ausentes) | green; clases presentes; helper importable | ❌ W0 | ⬜ pending |
| 04-02-01 | 04-02 | 2 | POOL-03 | T-04-02-01, T-04-02-05 | `execute_insert` + `returning` opt-in en los 6 motores; fix ORA-38104; snapshots/golden regenerados | unit DB-free + snapshot | `uv run pytest tests/test_dialect_builders.py tests/test_sql_snapshots.py -q` | green; `git diff --stat tests/__snapshots__/` NO vacío y revisado; `grep -c "DeprecationWarning" encino_orm/base.py` == 0 | ❌ W0 | ⬜ pending |
| 04-02-02 | 04-02 | 2 | POOL-03 | T-04-02-02, T-04-02-03 | `Model.insert`/`migration._apply` capturan el id con `execute_insert`; `PoolDb.insert` reenvía `returning` (B3); SIN warning todavía | integration SQLite REAL + unit | `uv run pytest tests/test_sqlite.py tests/test_crud.py tests/test_migrations.py tests/test_migration_reconcile.py tests/test_pool.py tests/test_dialect_builders.py -q` | green; `grep -rn "\.last_id()" encino_orm/` == 0; `grep -c "returning" encino_orm/pool.py` >= 2 | ❌ W0 | ⬜ pending |
| 04-02-03 | 04-02 | 2 | POOL-03 | T-04-02-04, T-04-02-06 | Warning habilitado SOLO tras migrar internos+tests; tests de deprecación sobre adaptadores REALES; docs/CHANGELOG | unit real + integration + docs | `uv run pytest tests/test_sqlite.py -k "deprecated" -q && uv run pytest tests/test_sqlite.py tests/test_crud.py tests/test_migrations.py -q` | green; `grep -c "_warn_last_id_deprecated" encino_orm/base.py encino_orm/pool.py` >= 2; suite sin warnings escapados | ❌ W0 | ⬜ pending |
| 04-03-01 | 04-03 | 3 | POOL-04 | T-04-03-01, T-04-03-04 | `execute`/`_run` commitean en éxito y revierten en error ANTES de liberar | unit + integration SQLite | `uv run pytest tests/test_pool.py -q` | green; `-k "autocommit or standalone"` green SIN editar esos tests; test de rollback en error verde | ✅ (preservar) | ⬜ pending |
| 04-03-02 | 04-03 | 3 | POOL-04 | T-04-03-02, T-04-03-03, T-04-03-05 | `reset_on_release` (rollback default, commit deprecado); warning enganchado a la política, no a `in_transaction()` | unit (fake `Db`) | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` | green; `-k "release"` con la aserción invertida (`("rollback", None)`); `pytest.warns` para `"commit"` | ✅ (invertir) | ⬜ pending |
| 04-03-03 | 04-03 | 3 | POOL-04 | T-04-03-02 | Guía + CHANGELOG describen la semántica de liberación | docs + gates | `uv run pytest -q -m "not integration and not optional_engine" && uv run ruff check encino_orm tests && uv run mypy encino_orm` | green; `grep -c "reset_on_release" docs/guide.md` >= 1; `### Corregido` sin duplicar | ❌ W0 | ⬜ pending |
| 04-04-01 | 04-04 | 4 | POOL-05 | T-04-04-02, T-04-04-04 | Reaper perezoso cierra ociosas > `min_size`; `idle_timeout=None` desactiva | unit (fake `Db`) | `uv run pytest tests/test_pool.py -k "reap" -q` | green (4 tests); `grep -c "await self._reap()" encino_orm/pool.py` >= 2 | ❌ W0 | ⬜ pending |
| 04-04-02 | 04-04 | 4 | POOL-05/06 | T-04-04-01, T-04-04-03 | `close()` idempotente que no cierra lo retenido; generación evita reencolar obsoletos | unit (fake `Db`) | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` | green; `-k "close"` con `held.driver.closed is False` (invertida); evidencia RED/GREEN en el SUMMARY | ✅ (invertir) | ⬜ pending |
| 04-04-03 | 04-04 | 4 | POOL-05/06 | T-04-04-05 | Ratchet de mypy de `pool.py` retirado (o residual documentado); CHANGELOG de `close()`/reaper | gates + docs | `uv run pytest -q -m "not integration and not optional_engine" && uv run ruff check encino_orm tests && uv run ruff format --check encino_orm tests && uv run mypy encino_orm && uv lock --check` | green; `grep -c '"encino_orm.pool"' pyproject.toml` == 0 (o residual documentado) | ❌ W0 | ⬜ pending |
| 04-06-01 | 04-06 | 5 | POOL-07 | T-04-06-01, T-04-06-05 | Carrera de admisión determinista bajo `EventBarrier` + `pytest.mark.timeout`; sin primitivas 3.11 | concurrency | `uv run pytest tests/test_pool_concurrency.py -q -m concurrency` | green y < 30 s; AST check sin `Barrier`/`TaskGroup`/`asyncio.timeout` | ❌ W0 | ⬜ pending |
| 04-06-02 | 04-06 | 5 | POOL-03/04 | T-04-06-02, T-04-06-03 | Inserts concurrentes devuelven cada uno su id; commit standalone visible entre conexiones | integration SQLite + unit | `uv run pytest tests/test_pool_concurrency.py -q -k "concurrent_insert_ids or standalone_commit or inside_transaction"` | green; 5 ids distintos con mapeo nombre→id; `git diff --numstat tests/test_pool.py tests/test_pool_characterization.py` VACÍO | ❌ W0 | ⬜ pending |
| 04-06-03 | 04-06 | 5 | POOL-07 | T-04-06-04 | Variante de estrés `pytest-repeat` tras el marker `stress` | stress | `uv run pytest tests/test_pool_concurrency.py -q -m stress` | green; `-m "not stress"` green; `repeat(5)` corre en la corrida normal sin colgar | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Ficheros/artefactos que NO existen hoy y que un plan de la fase debe crear antes de que sus aserciones puedan correr:

- [ ] `tests/_pool_helpers.py` — `EventBarrier` (asyncio.Event), `FakeDb`, `BlockingFakeDb`, `_CONNECT_BARRIER`, `execute_insert` (04-05 Task 3)
- [ ] `tests/test_pool_concurrency.py` — tests deterministas de concurrencia/estrés (04-06)
- [ ] `pyproject.toml` — dev deps `pytest-timeout==2.4.0`/`pytest-repeat==0.9.4`, marker `stress`, `timeout = 0` (04-05 Task 2)
- [ ] `uv.lock` — regenerado por `uv add --dev` (04-05 Task 2)
- [ ] `.github/workflows/ci.yml` — `--timeout-method=signal` en `test` y `engine-heavy` (04-05 Task 2)
- [ ] Casos nuevos en `tests/test_pool.py` — handle, reaper, generación, `close()` retenido, rollback en error, `reset_on_release`, ids concurrentes (04-01/03/04)
- [ ] Casos nuevos/migrados en `tests/test_pool_characterization.py` — inversiones POOL-02/04/06; lecturas de `_last_id` eliminadas (04-01/03/04)
- [ ] Migración de `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` — `execute_insert` + `test_last_id_deprecated` (04-02 Task 2/3)
- [ ] `tests/__snapshots__/test_sql_snapshots.ambr` — regenerado (MERGE `SET` + `RETURNING` opt-in) (04-02 Task 1)
- [ ] `docs/engines.md`, `docs/guide.md`, `CHANGELOG.md` — contrato nuevo (04-02/03/04)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Legitimidad de `pytest-timeout`/`pytest-repeat` | POOL-07 | `slopcheck` no está disponible; ambos son `[ASSUMED]` | Checkpoint `blocking-human` (04-05 Task 1): el ejecutor pega la salida del chequeo automático de PyPI; el humano abre `pypi.org/project/pytest-timeout` y `…/pytest-repeat`, confirma upstream `github.com/pytest-dev/...` y aprueba. Nunca auto-aprobable |
| `Model.insert(replace=True)` ejecutable en Oracle (sin ORA-38104) | POOL-03 | Oracle no está disponible en el host Windows; corre en `engine-heavy` | En el job `engine-heavy`: `uv run pytest tests/test_oracle.py -k "insert_replace" -q`; confirmar que NO lanza ORA-38104 y que `zoe.id is None`. Registrar el run en el SUMMARY |
| `OUTPUT INSERTED.id` en MSSQL (rowcount == -1) | POOL-03 | MSSQL no está disponible en el host Windows; corre en `engine-heavy` | En el job `engine-heavy`: `uv run pytest tests/test_mssql.py -k "execute_insert" -q`; confirmar que el id capturado es el correcto y que `rowcount` no se usa como retorno |
| Timing real de barrera en CI Linux con `--timeout-method=signal` | POOL-07 | El método *signal* no se pudo probar en Windows (A5; el *thread* mata el proceso y pierde el JUnit XML) | Primer run verde del job `test` en CI: confirmar que un test de barrera colgado sería interrumpido y que la corrida continúa con el JUnit XML intacto. Si falla, mitigación documentada: fijar `pytest-timeout==2.5.0` cuando se publique |
| Soak de estrés (`--count=100`) | POOL-07 | Es un comando local opcional, no un gate de CI | `uv run pytest -m stress --count=100` en local; registrar cualquier flake. NO añadir a `ci.yml` en esta fase |

---

## Nyquist Dimension Checklist

| Dimension | Covered by | Evidence |
|-----------|-----------|----------|
| **Every task has automated verify** | 18/18 tasks | Todas las tareas tienen `<verify><automated>` (la única excepción es `04-05-01`, un checkpoint humano con verificación automática de PyPI previa) |
| **No 3 consecutive tasks without automated verify** | sampling rate | Cada tarea tiene comando; los checkpoints no rompen la continuidad |
| **Requirement coverage** | POOL-01→04-01, POOL-02→04-01, POOL-03→04-02, POOL-04→04-03, POOL-05/06→04-04, POOL-07→04-05+04-06 | 7/7 requisitos con al menos un test automatizado |
| **Engine dimension** | SQLite siempre (rápido); MySQL/MariaDB/PostgreSQL con `-m integration`; MSSQL/Oracle en `engine-heavy` | Cada motor tiene `execute_insert`/deprecación/`insert(replace=True)` cubiertos |
| **Concurrency dimension** | `EventBarrier` determinista + `pytest.mark.timeout` + `pytest-repeat` | Carrera de admisión, doble release, ids concurrentes, soak |
| **Ordering / regression dimension** | `TestPoolAutocommit`, `TestPoolStandaloneCommit`, `test_dml_visible_across_connections` | Regresión de POOL-04 sin editar; inversiones con evidencia RED/GREEN en el SUMMARY |
| **Negative / fail-closed dimension** | `check_identifier(returning=)`, `reset_on_release` inválido, MERGE sin columnas actualizables, doble `release()` | Tests de `ValueError`/warning/ignorado |
| **Backward-compat dimension** | `returning=None` byte-idéntico; snapshots/golden revisados; `_last_id` eliminado | `git diff` de snapshots revisado; golden strings actualizados de forma visible |
| **Warning dimension** | `filterwarnings=["error"]`; B2 ordering | Task 1/2 sin warning; Task 3 lo habilita con tests `pytest.warns` sobre adaptadores reales |
| **Feedback latency** | quick run ~30 s; barreras con timeout 10–20 s | `Max feedback latency` arriba |
| **Wave 0 gaps** | sección Wave 0 | 10 artefactos listados; todos con dueño en un plan |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-18
