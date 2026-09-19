---
phase: 5
slug: resilience
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-18
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Generated from the 4 plans (`05-01`…`05-04`). Every task's `<verify><automated>` is reproduced here as the per-task contract; the manual-only items are the ones that cannot be asserted on the local Windows host or require a real engine kill.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) + pytest-timeout 2.4.0 + pytest-repeat 0.9.4 (instalados en Fase 4) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`filterwarnings=["error"]`, `--strict-markers`, `xfail_strict`, `timeout = 0`) |
| **Targeted run command** | `uv run pytest tests/test_resilience.py -q -k <bloque>` (`disconnect`/`reconnect`/`lifetime`/`translate`) |
| **Quick run command** | `uv run pytest tests/test_resilience.py -q` |
| **Full suite command** | `uv run pytest -q -m "not integration and not optional_engine"` (6 motores locales con `uv run pytest -q`) |
| **CI run command** | `uv run pytest -q -m "not optional_engine" --timeout-method=signal --junitxml=junit.xml` |
| **Estimated runtime** | ~2 s targeted `-k`; ~5 s `tests/test_resilience.py`; ~90 s full local suite (MSSQL/Oracle en el job `engine-heavy`) |

**Restricción de piso (Research Correction #4):** Python 3.10. Prohibido `asyncio.Barrier`, `asyncio.timeout`, `TaskGroup` y `except*` en librería y tests. Los tests de la fase son unitarios con dobles a mano; no usan temporizadores reales (`sleep`).

**Restricción de importación diferida:** el job `test` de CI sincroniza `--extra http --security --graphql --cache` y **no** instala `pyodbc`/`oracledb`. Por eso la clasificación de MSSQL/Oracle en los tests siempre-activos usa la **forma exacta** de `args` verificada en research, y la construcción con los tipos REALES (`pyodbc.Error`, `oracledb.exceptions.DatabaseError`) vive en tests `optional_engine` que corren en el job `engine-heavy`.

---

## Sampling Rate

- **After every task commit:** primero el comando targeted del bloque que toca el plan (`uv run pytest tests/test_resilience.py -q -k disconnect|reconnect|lifetime|translate`), luego el fichero completo del plan (`uv run pytest tests/test_resilience.py -q`).
- **After every plan wave:** `uv run pytest -q -m "not integration and not optional_engine"` (gate de wave; el targeted NO sustituye a este gate).
- **Before `/gsd-verify-work`:** suite completa verde + `uv run ruff check encino_orm tests` + `uv run ruff format --check encino_orm tests` + `uv run mypy encino_orm` + `uv lock --check`.
- **Max feedback latency:** ~2 s targeted `-k` / ~5 s `tests/test_resilience.py` (quick run); sin barreras ni timeouts en esta fase.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure / Correct Behavior | Test Type | Automated Command | Expected Result | File Exists | Status |
|---------|------|------|-------------|------------|---------------------------|-----------|-------------------|-----------------|-------------|--------|
| 05-01-01 | 05-01 | 1 | RESL-01 | T-05-01-04 | `tests/_resilience_helpers.py` con builders de excepciones (firmas reales SQLite/MySQL/PostgreSQL; forma exacta MSSQL/Oracle; variantes `real_*` para `optional_engine`) y `FakeResilientDb` | unit (helper) | `uv run python -c "import ast,pathlib; ast.parse(...); print('helper OK')" && uv run ruff check tests/_resilience_helpers.py` | green; `class FakeResilientDb` presente; `unittest.mock` == 0; drivers opcionales solo importados dentro de funciones | ❌ W0 | ⬜ pending |
| 05-01-02 | 05-01 | 1 | RESL-01 | T-05-01-01, T-05-01-02, T-05-01-03, T-05-01-05, T-05-01-06 | `is_disconnect_error` en `base.py` + cinco adaptadores, exclusión mutua con lock | unit (dobles de excepción) | `uv run pytest tests/test_resilience.py -q -k disconnect` | green; `def is_disconnect_error` >= 6; MSSQL `HY000` mid-query → True; Oracle `full_code` DPY-4011 → True; `InvalidCachedStatementError` → False | ❌ W0 | ⬜ pending |
| 05-01-03 | 05-01 | 1 | RESL-01 | T-05-01-01, T-05-01-04 | Par disconnect/lock por motor en `tests/test_{motor}.py` + herencia MariaDB | unit por motor | `uv run pytest tests/test_resilience.py tests/test_sqlite.py tests/test_mysql.py tests/test_mariadb.py tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py -q -k "disconnect or lock"` | green; `def test_is_disconnect_error` >= 6; sin imports de drivers opcionales a nivel de módulo | ❌ W0 | ⬜ pending |
| 05-02-01 | 05-02 | 2 | RESL-02 | T-05-02-01, T-05-02-02, T-05-02-06, T-05-02-07 | `_with_reconnect`/`_reconnect`/`_is_reconnectable` + wrappers públicos concretos + privados con `NotImplementedError` | unit (template) | `uv run python -c "from encino_orm.base import Db; ... print('base template OK')"` | green; 3 helpers + 5 privados; `execute` deja de ser abstracto; `NotImplementedError` >= 5 | ❌ W0 | ⬜ pending |
| 05-02-02 | 05-02 | 2 | RESL-02 | T-05-02-03, T-05-02-05, T-05-02-08 | Rename a `_execute`/`_execute_insert`/`_fetch_*` + estado `_connect_kwargs`/`_connected_at` + `:memory:` rechazado | unit + integration SQLite | `uv run python -c "... rename OK ..." && uv run pytest tests/test_sqlite.py -q` | green; 25 privados (5×5); 0 públicos en adaptadores; `pool.py` intacto | ❌ W0 | ⬜ pending |
| 05-02-03 | 05-02 | 2 | RESL-02 | T-05-02-01, T-05-02-02, T-05-02-04 | Bloque RESL-02: reconecta-una-vez, guard de tx, política A2 (lectura / escritura pre-ejecución / escritura mid-statement), sin bucle, lock intacto | unit (FakeResilientDb) | `uv run pytest tests/test_resilience.py -q -k reconnect && uv run pytest tests/test_d_recommendations.py -k retry -q && uv run pytest -q -m "not integration and not optional_engine"` | green; `TestD4AutoRetry` verde; `git diff --stat encino_orm/pool.py` vacío | ❌ W0 | ⬜ pending |
| 05-03-01 | 05-03 | 3 | RESL-03 | T-05-03-01, T-05-03-02, T-05-03-05, T-05-03-06 | `pre_ping`/`max_connection_lifetime` + `_resilience_opts` + `_should_recycle` + `_maybe_recycle` | unit (política) | `uv run python -c "from encino_orm.base import Db; ... print('lifetime opts OK')"` | green; 3 métodos; `time.monotonic` >= 1; `time.time()`/`create_task` == 0 | ❌ W0 | ⬜ pending |
| 05-03-02 | 05-03 | 3 | RESL-03 | T-05-03-03 | `_resilience_opts` cableado en los cinco `connect()` (pop antes de guardar/reenviar) | unit + integration SQLite | `uv run pytest tests/test_sqlite.py -q && uv run pytest tests/test_base.py -q` | green; `_resilience_opts` >= 1 por adaptador; `pre_ping`/`max_connection_lifetime` ausentes de `_connect_kwargs`; driver real conecta | ❌ W0 | ⬜ pending |
| 05-03-03 | 05-03 | 3 | RESL-03 | T-05-03-01, T-05-03-04 | Bloque RESL-03: pre_ping reconecta inmediatamente, lifetime recicla por edad, defaults off, validación, `:memory:` | unit (fake + SQLite fichero) | `uv run pytest tests/test_resilience.py -q -k lifetime && uv run pytest -q -m "not integration and not optional_engine"` | green; sin `sleep`; `is_alive_calls` caracterizado; `pool.py` intacto | ❌ W0 | ⬜ pending |
| 05-04-01 | 05-04 | 4 | RESL-04 | T-05-04-01, T-05-04-02, T-05-04-03, T-05-04-05 | Taxonomía + barrel + `_translate_exception` (cortocircuito de lock) + `_translate_error` por adaptador + chaining | unit (taxonomía) | `uv run python -c "from encino_orm import ConnectionLostError, OperationalError, IntegrityError, ProgrammingError, ConnectionError, QueryError; ... print('taxonomy OK')"` | green; 4 clases; `_translate_error` >= 1 por adaptador; `from exc` >= 3; `type: ignore` == 0; `TestD4AutoRetry` verde | ❌ W0 | ⬜ pending |
| 05-04-02 | 05-04 | 4 | RESL-04 | T-05-04-01, T-05-04-05 | Bloque RESL-04: traducción por motor, lock sin traducir, causa preservada, `:memory:` → `ConnectionLostError`; jerarquía en `test_base.py` | unit (parametrizado) | `uv run pytest tests/test_resilience.py -q -k translate && uv run pytest tests/test_base.py -q && uv run pytest tests/test_d_recommendations.py -k retry -q` | green; `_translate_exception(lock) is lock`; `__cause__` es el driver; `issubclass` de la jerarquía | ❌ W0 | ⬜ pending |
| 05-04-03 | 05-04 | 4 | RESL-04 | T-05-04-04, T-05-04-06, T-05-04-07 | Docs + CHANGELOG + retirada del ratchet `base`/`oracle`/`mysql`/`mssql` + gates de cierre | docs + gates | `uv run pytest tests/test_resilience.py tests/test_base.py -q && uv run pytest -q -m "not integration and not optional_engine" && uv run ruff check encino_orm tests && uv run ruff format --check encino_orm tests && uv run mypy encino_orm && uv lock --check` | green; targeted primero; `is_disconnect_error`/`ConnectionLostError`/`pre_ping` en `docs/engines.md`; `### Corregido` sin duplicar; ratchet retirado o residual documentado; `encino_orm.pool` intacto | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Ficheros/artefactos que NO existen hoy y que un plan de la fase debe crear antes de que sus aserciones puedan correr:

- [ ] `tests/_resilience_helpers.py` — builders de excepciones por motor (firmas reales / forma exacta) + `FakeResilientDb` (05-01 Task 1; extendido en 05-02/05-03)
- [ ] `tests/test_resilience.py` — bloques RESL-01 (05-01), RESL-02 (05-02), RESL-03 (05-03), RESL-04 (05-04)
- [ ] `encino_orm/base.py` — `is_disconnect_error` (05-01), `_with_reconnect` (05-02), `pre_ping`/lifetime (05-03), `_translate_exception` (05-04)
- [ ] Los seis adaptadores — `is_disconnect_error` (05-01), rename + estado (05-02), `_resilience_opts` (05-03), `_translate_error` (05-04)
- [ ] `encino_orm/exceptions.py` + `encino_orm/__init__.py` — taxonomía y barrel (05-04)
- [ ] `docs/engines.md`, `CHANGELOG.md` — contrato nuevo (05-04)
- [ ] `pyproject.toml` — ratchet de mypy reducido (05-04)
- [ ] No se requieren fixtures compartidas nuevas en `tests/conftest.py` (los dobles viven en el helper).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clasificación de desconexión con el driver REAL de MSSQL (`pyodbc.Error`) | RESL-01 | `pyodbc` no está en el job `test` de CI; el tipo real solo se puede construir donde el extra `mssql` está instalado | En local/`engine-heavy`: `uv run pytest tests/test_resilience.py -q -k "disconnect and optional_engine"`; confirmar que `pyodbc.Error('HY000', '...terminated by the server... (596)')` clasifica como disconnect. Registrarlo en el SUMMARY |
| Clasificación de desconexión con el driver REAL de Oracle (`oracledb.exceptions.DatabaseError` con `full_code='DPY-4011'`) | RESL-01 | `oracledb` no está en el job `test` de CI | En local/`engine-heavy`: `uv run pytest tests/test_resilience.py -q -k "disconnect and optional_engine"`; confirmar `DPY-4011` → True y `_OraExc(60)` → lock. Registrarlo en el SUMMARY |
| Reconexión real tras un `KILL`/`pg_terminate_backend` (caída en reposo) y NO-reintento de una escritura mid-statement | RESL-01/02 | Requiere matar una conexión real; no es determinista sin los contenedores. La lógica está cubierta por `FakeResilientDb` | Opcional: `uv run pytest tests/test_resilience_integration.py -q -m integration` (si se crea) o verificación manual contra MySQL/PostgreSQL locales: matar la sesión en reposo, comprobar que la siguiente LECTURA reconecta y triunfa, y que una ESCRITURA que muere mid-statement relanza sin duplicar la fila |
| `pre_ping` contra un motor real tras un periodo de inactividad | RESL-03 | El paso del tiempo se simula por asignación de `_connected_at`; la supervivencia real a un idle de red no es determinista | Opcional en `engine-heavy`: conectar directo a MySQL/PostgreSQL con `pre_ping=True`, matar la sesión, ejecutar una lectura y confirmar que reconecta. Registrar el run |
| `PoolDb` recibiendo `pre_ping`/`max_connection_lifetime` por conexión física (A6) | RESL-03 | El reciclado a nivel de pool es v2; solo se verifica el paso de opciones | `uv run pytest tests/test_resilience.py -q -k "pool and lifetime"`; confirmar que las opciones llegan al `connect()` del driver y que `pool.py` no cambia |

---

## Nyquist Dimension Checklist

| Dimension | Covered by | Evidence |
|-----------|-----------|----------|
| **Every task has automated verify** | 12/12 tasks | Todas las tareas tienen `<verify><automated>`; los tests `optional_engine` de MSSQL/Oracle degradan a skip sin driver, pero su cobertura siempre-activa usa la forma exacta de `args` |
| **No 3 consecutive tasks without automated verify** | sampling rate | Cada tarea tiene comando; sin checkpoints humanos en la fase (no hay paquetes nuevos) |
| **Requirement coverage** | RESL-01→05-01, RESL-02→05-02, RESL-03→05-03, RESL-04→05-04 | 4/4 requisitos con al menos un test automatizado |
| **Engine dimension** | SQLite siempre (rápido); MySQL/MariaDB/PostgreSQL con dependencias duras; MSSQL/Oracle con forma exacta + `optional_engine` real | Cada motor tiene par disconnect/lock y traducción cubiertos |
| **Ordering / regression dimension** | `TestD4AutoRetry` (lock), `test_pool_*` sin cambios, `git diff --stat encino_orm/pool.py` vacío | El camino de lock y el pool no se rompen; las waves están encadenadas por `depends_on` |
| **Negative / fail-closed dimension** | `:memory:` rechazado, `max_connection_lifetime <= 0` → `ValueError`, no-reconectable relanza, no-bucle, sin catch-all | Tests dedicados por escenario |
| **Backward-compat dimension** | `ConnectionLostError` hereda de `ConnectionError`; `OperationalError`/`IntegrityError`/`ProgrammingError` de `QueryError`; `last_id()` deprecado intacto | Asserts de jerarquía + nota de status HTTP 400 en CHANGELOG |
| **Write-safety dimension (Core Value)** | Política A2: lecturas reintentan; escrituras pre-ejecución ejecutan; escrituras mid-statement reconectan y relanzan; dentro de tx se relanza | `test_escritura_mid_statement_reconecta_pero_no_reejecuta`, `test_desconexion_dentro_de_tx_relanza_sin_reconectar` |
| **Lazy-import dimension** | `base.py` sin drivers; `pyodbc`/`oracledb` solo dentro de `connect()`/funciones `real_*` | greps de control por adaptador y en el helper |
| **Warning dimension** | `filterwarnings=["error"]`; sin warnings por operación | Suite verde bajo `-W error`; sin allowlist nueva |
| **Feedback latency** | targeted `-k` ~2 s; `tests/test_resilience.py` ~5 s; sin barreras ni sleeps | `Max feedback latency` arriba |
| **Wave 0 gaps** | sección Wave 0 | 8 artefactos listados; todos con dueño en un plan |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (draft — se aprueba al cerrar la fase)
