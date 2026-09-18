---
phase: 2
slug: dialect-seam-engine-parity
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-18
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode = "auto"`, ambos loop scopes `function`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (endurecido en Fase 1: `--strict-markers`, `xfail_strict`, `filterwarnings = ["error"]`, 4 markers) |
| **Quick run command** | `uv run pytest -q -m "not integration and not optional_engine"` (sin BD) |
| **Full suite command** | `uv run pytest -q` (con motores disponibles) |
| **CI-equivalent command** | `uv run pytest -q -m "not optional_engine" --junitxml=junit.xml --cov=encino_orm --cov-branch --cov-report=` |
| **Snapshot update** | `uv run pytest --snapshot-update -m syrupy_snapshot` |
| **Estimated runtime** | ~15 s (suite actual, sin motores pesados) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest -q -m "not integration and not optional_engine"` + `uv run ruff check encino_orm tests tools` + `uv run mypy encino_orm`
- **After every plan wave:** `uv run pytest -q -m "not optional_engine"` (añade MySQL/PostgreSQL/MariaDB/Redis donde estén disponibles) + `uv run coverage report`
- **Before `/gsd-verify-work`:** suite completa verde en todos los motores requeridos, snapshots commiteados, pisos de cobertura pasando
- **Max feedback latency:** ~30 s (quick run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 02-01 | 1 | DIAL-01 | Validación que se salta 5 de 6 dialectos | Un único `_IDENTIFIER_RE`/`check_identifier`; comportamiento sin cambios | unit + guard de fuente | `uv run pytest tests/test_identifiers.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 02-01 | 1 | DIAL-01 | — | Prueba de refactor puro: la suite existente pasa con cero ediciones de test | regression | `uv run pytest -q` | ✅ | ⬜ pending |
| 02-02-01 | 02-02 | 2 | DIAL-02 | Inyección vía nombre de tabla/columna | Los 6 adaptadores rechazan nombre malicioso con `ValueError` **antes** de `_prepare` | unit + spy | `uv run pytest tests/test_dialect_builders.py -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02-02 | 2 | DIAL-02 | Inyección vía `schema=` | SQL generado byte-idéntico al actual (6 dialectos × 3 verbos × 3 modos) | regression | `uv run pytest tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py tests/test_mysql.py tests/test_sqlite.py -x` | ✅ | ⬜ pending |
| 02-02-03 | 02-02 | 2 | DIAL-04 | Inyección vía columna derivada de catálogo | `sync_schema` rechaza nombre derivado de introspección antes de cualquier `ALTER TABLE` | unit + spy | `uv run pytest tests/test_migrations.py -k sync_schema -x` | ✅ (extender) | ⬜ pending |
| 02-02-04 | 02-02 | 2 | DIAL-02 | Inyección vía `schema=` | El DML de `upsert` se construye **solo** en el seam; `Model.upsert` delega y no conserva ramas de dialecto | unit + guard `ast` | `uv run pytest tests/test_bulk_upsert.py -x` + guard `ast` (excluyendo docstrings) | ✅ | ⬜ pending |
| 02-03-01 | 02-03 | 3 | DIAL-05 | — | Inmutabilidad: asignar atributo lanza; `with_params()` devuelve objeto nuevo; el original no cambia | unit | `uv run pytest tests/test_query.py -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 02-03 | 3 | DIAL-05 | — | Índices dispersos, duplicados, params sin usar, índice fuera de rango | unit | `uv run pytest tests/test_query.py -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 02-03 | 3 | DIAL-05 | — | `__hash__` lanza `TypeError` con param no hashable; Queries iguales hashean igual | unit | `uv run pytest tests/test_query.py -x` | ❌ W0 | ⬜ pending |
| 02-03-04 | 02-03 | 3 | DIAL-05 | — | `rebind` ya no existe (`not hasattr`) | unit | `uv run pytest tests/test_query.py -k rebind -x` | ❌ W0 | ⬜ pending |
| 02-03-05 | 02-03 | 3 | DIAL-06 | — | Los 6 dialectos exponen `MAX_PARAMS`/`MAX_ROWS`; el `chunk` de `insert_many` deriva de ellos | unit | `uv run pytest tests/test_engine.py -k max_params -x` | ✅ (extender) | ⬜ pending |
| 02-04-01 | 02-04 | 4 | DIAL-03 | — | `count`/`paginate`/`list_tables` + `sum/avg/min/max` correctos en PG/MSSQL/Oracle | integration | `uv run pytest tests/test_postgresql.py -k "count or paginate or list_tables or aggregate" -x` (por motor) | ❌ W0 (asserts) | ⬜ pending |
| 02-04-02 | 02-04 | 4 | DIAL-03 | — | Unit SQLite: el SQL de count contiene `AS n` | unit | `uv run pytest tests/test_aggregates.py -x` | ✅ (extender) | ⬜ pending |
| 02-04-03 | 02-04 | 4 | DIAL-09 | — | Cobertura de integración por motor para count/paginate/list_tables/sync_schema/last_id | integration | `uv run pytest tests/test_<engine>.py -x` | ❌ W0 (asserts) | ⬜ pending |
| 02-05-01 | 02-05 | 5 | DIAL-07 | — | 6 dialectos × DML + count/paginate/list_tables coinciden con snapshots `.ambr` commiteados, sin BD | unit (snapshot) | `uv run pytest tests/test_sql_snapshots.py -x` | ❌ W0 | ⬜ pending |
| 02-05-02 | 02-05 | 5 | DIAL-08 | Gate degradado a no-op | Quitar MariaDB/Redis/MSSQL/Oracle de un job requerido lo hace **fallar**, no omitir | CI induced failure | rama scratch → job rojo | ✅ (switch de Fase 1) | ⬜ pending |
| 02-05-03 | 02-05 | 5 | DIAL-08 | — | `skipped == 0` en cada job de motor requerido | CI gate | `uv run python tools/ci/check_skips.py junit.xml` | ✅ | ⬜ pending |
| 02-05-04 | 02-05 | 5 | (D-04/D-06 Fase 1) | — | Pisos de cobertura por módulo aplicados | CI gate | `uv run coverage json -o coverage.json && uv run python tools/ci/check_coverage_floors.py coverage.json` | ❌ W0 (script) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_identifiers.py` — tabla accept/reject del checker centralizado (DIAL-01)
- [ ] `tests/test_dialect_builders.py` — 6 adaptadores × nombres maliciosos, spy que afirma que `_prepare` nunca se llamó (DIAL-02)
- [ ] `tests/test_query.py` — inmutabilidad, `with_params`, `{n}` dispersos/duplicados/sin usar/fuera de rango, hash/eq (DIAL-05)
- [ ] `tests/test_sql_snapshots.py` + `tests/__snapshots__/*.ambr` — 6 dialectos × DML + count/paginate/list_tables (DIAL-07)
- [ ] `tools/ci/check_coverage_floors.py` — pisos por módulo sobre `coverage.json` (D-04/D-06 de Fase 1)
- [ ] Extender `tests/test_<engine>.py` × 6 con asserts de count/paginate/list_tables/sync_schema/last_id (DIAL-03, DIAL-09)
- [ ] Extender `tests/test_engine.py` (o nuevo `tests/test_dialect_constants.py`) con los asserts de `MAX_PARAMS`/`MAX_ROWS` (DIAL-06)
- [ ] Instalar `syrupy` (`uv add --dev syrupy`) — **detrás de un `checkpoint:human-verify`** (slopcheck `[SUS]`, falso positivo por similitud de nombre con `scrapy`)
- [ ] CI: extender el job `test` (servicios mariadb + redis, `--extra cache`, quitar los markers `optional_engine` de esos dos archivos); añadir el job `engine-heavy` (mssql + oracle, paso de instalación ODBC, `FREEPDB1`); añadir `coverage json` + el script de pisos al job `coverage`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| El gate de motores requeridos falla al quitar un servicio | DIAL-08 | Requiere un run real de GitHub Actions con un servicio eliminado | Rama scratch: quitar el servicio → PR → el job `test` debe quedar **rojo** (no skip). Precedente probado en Fase 1 (run #25) |
| Techo de parámetros **ad-hoc** de Oracle (A1) y MSSQL (A2) | DIAL-06 | Documentado pero no verificado empíricamente | Sondear en el job `engine-heavy`: construir un INSERT con N params creciente y registrar el primer N que falla; ajustar `MAX_PARAMS` con la procedencia anotada |
| `engine-heavy` en cada PR vs solo `main` | DIAL-08 | Decisión de coste/tiempo (Oracle tarda 1-3 min en arrancar) | Medir la duración del job una vez y decidir; **nunca** marcarlo advisory (`continue-on-error` prohibido) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-18
