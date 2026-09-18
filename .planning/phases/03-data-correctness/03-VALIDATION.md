---
phase: 3
slug: data-correctness
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-18
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (markers, `filterwarnings=["error"]`, `xfail_strict`) |
| **Quick run command** | `uv run pytest tests/test_migrations.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_migration_reconcile.py -q` |
| **Full suite command** | `uv run pytest -q` (usa los 6 contenedores locales; en CI, `ENCINO_ORM_REQUIRE_ENGINES`) |
| **Estimated runtime** | ~20 s (suite actual, con motores locales) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/test_migrations.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_migration_reconcile.py -q`
- **After every plan wave:** `uv run pytest -q`
- **Before `/gsd-verify-work`:** suite completa verde antes de la verificación
- **Max feedback latency:** ~25 s

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 03-01 | 1 | DATA-01 | SQLi por nombre de migración | `rollback_migration` ejecuta el `down`, borra `{name}` y **no** inserta `{name}:down` | unit/integration | `uv run pytest tests/test_migrations.py -k rollback_ledger -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 03-01 | 1 | DATA-01 | — | `apply → rollback → apply` re-aplica el DDL y el ledger tiene una sola fila `{name}` | integration (SQLite) | `uv run pytest tests/test_migrations.py::TestMigrationRunner::test_reapply_after_rollback -x` | ❌ W0 | ⬜ pending |
| 03-02-01 | 03-02 | 2 | DATA-02 | SQLi por identificador en `ALTER TABLE` | `TRANSACTIONAL_DDL` mapea los 6 dialectos (PG/SQLite/MSSQL True; MySQL/MariaDB/Oracle False) | unit DB-free | `uv run pytest tests/test_dialect_ddl.py -x` | ❌ W0 | ⬜ pending |
| 03-02-02 | 03-02 | 2 | DATA-02 | Teatro de seguridad (Pitfall 8) | Con `transactional_ddl=False`, un fallo tras el DDL deja `pending` y `reconcile_migrations` **lanza** `MigrationError` con el SQL | unit (fake `Db`) | `uv run pytest tests/test_migration_reconcile.py -x` | ❌ W0 | ⬜ pending |
| 03-02-03 | 03-02 | 2 | DATA-02 | — | `ALTER TABLE` añade `status` a una tabla legacy y es **idempotente** (segunda ejecución no falla) | integration (SQLite + MySQL si disponible) | `uv run pytest tests/test_migrations.py -k ensure_status -x` | ❌ W0 | ⬜ pending |
| 03-02-04 | 03-02 | 2 | DATA-02 | — | `migrate()` sigue siendo idempotente para una migración ya `applied` | unit (regresión) | `uv run pytest tests/test_sqlite.py -k migrate_is_idempotent -x` | ✅ (regresión) | ⬜ pending |
| 03-02-05 | 03-02 | 2 | DATA-02 | — | `resolve_migration` infiere la acción correcta para las 4 filas de D-08 (`applied` = "¿queda aplicada?") | unit (fake/ledger SQLite) | `uv run pytest tests/test_migration_reconcile.py -k resolve -x` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03-03 | 3 | DATA-03 | — | `update` invalida la clave cacheada (la lectura posterior va a BD) | unit | `uv run pytest tests/test_cached_model.py -k update_invalidates -x` | ❌ W0 | ⬜ pending |
| 03-03-02 | 03-03 | 3 | DATA-03 | — | `delete` invalida la clave cacheada | unit | `uv run pytest tests/test_cached_model.py -k delete_invalidates -x` | ❌ W0 | ⬜ pending |
| 03-03-03 | 03-03 | 3 | DATA-03 | — | `upsert` invalida (y no deja obsoleta la lectura) | unit | `uv run pytest tests/test_cached_model.py -k upsert_invalidates -x` | ❌ W0 | ⬜ pending |
| 03-03-04 | 03-03 | 3 | DATA-03 | — | `insert_many(cache=...)` invalida las claves afectadas cuando se pasa `cache=` | unit | `uv run pytest tests/test_cached_model.py -k insert_many_invalidates -x` | ❌ W0 | ⬜ pending |
| 03-03-05 | 03-03 | 3 | DATA-03 | — | Fallo de `cache.delete` = warning, **no** propaga (fail-open) | unit (cache fake que lanza) | `uv run pytest tests/test_cached_model.py -k invalidate_fail_open -x` | ❌ W0 | ⬜ pending |
| 03-04-01 | 03-04 | 4 | DATA-04 | — | LRU desaloja la clave menos usada al superar `max_size` | unit DB-free | `uv run pytest tests/test_cache_backend.py -k lru -x` | ❌ W0 | ⬜ pending |
| 03-04-02 | 03-04 | 4 | DATA-04 | — | El contrato dev/test está documentado en el docstring y en los docs | source | `grep -c "dev/test" encino_orm/model/cache_backend.py` ≥ 1 | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_migration_reconcile.py` — fake `Db` con `transactional_ddl=False`, ledger en memoria/SQLite, inyección de fallo del promote, `reconcile_migrations` y `resolve_migration` (DATA-02)
- [ ] `tests/test_cache_backend.py` — LRU, `max_size`, `len(_store)`, `delete` (DATA-04)
- [ ] Extender `tests/test_cached_model.py` — invalidación en `update`/`delete`/`upsert`/`insert_many(cache=)`, fail-open (DATA-03)
- [ ] Extender `tests/test_migrations.py` — regresión `apply→rollback→apply`, ledger sin `:down`, `ensure_status` idempotente (DATA-01/DATA-02)
- [ ] `tests/test_dialect_ddl.py` (o caso en `tests/test_dialect_builders.py`) — mapa `TRANSACTIONAL_DDL` DB-free
- [ ] (Discreción) Pisos en `tools/ci/check_coverage_floors.py` para `migration.py`, `model/cached.py`, `model/cache_backend.py`

*(Si el fake `Db` reutiliza el patrón de `tests/test_d_recommendations.py::LockDb`, recordar que **no** tiene `_ensure_migrations_table`: el helper `_ensure_ledger` debe tolerar su ausencia o el fake debe añadirlo.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| La ambigüedad de `pending` es real en motores no transaccionales | DATA-02 | Requiere matar el proceso entre el DDL y el promote | Test de inyección de fallo con un fake `Db`: asertar que `reconcile_migrations` **detecta** el `pending` (no que sea imposible). En MySQL real, verificar que el DDL commitea implícito antes del promote |
| `ALTER TABLE ADD COLUMN` idempotente en MySQL/MariaDB | DATA-02 | La receta portable no es verificable sin el motor | Ejecutar `ensure_status` dos veces contra MySQL/MariaDB reales (o en `engine-heavy`) y confirmar que la segunda no falla |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 25s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-18
