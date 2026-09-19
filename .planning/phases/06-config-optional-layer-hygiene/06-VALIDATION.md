---
phase: 6
slug: config-optional-layer-hygiene
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-19
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Generated from the 5 plans (`06-01`…`06-05`). Every task's `<verify><automated>` is reproduced here as the per-task contract; the manual-only items are the ones that cannot be asserted mechanically (snapshot ordering across commits, the prose quality of the trust-boundary page, and the dependency-audit outcome).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) + syrupy 6.1.1 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`filterwarnings=["error"]`, `--strict-markers`, `xfail_strict`, `timeout = 0`) |
| **Targeted run command** | 06-01 T1 → `uv run pytest tests/test_singleton.py -q` (verde SIN warning) · 06-01 T2 → `uv run pytest tests/test_registry.py tests/test_singleton.py -q` · 06-02 → `uv run pytest tests/test_security.py -q` · Wave 2 → `uv run pytest tests/test_http_openapi.py tests/test_graphql_namespace.py -q` · Wave 3 → `uv run pytest tests/test_trust_boundaries.py -q` |
| **Quick run command** | `uv run pytest tests/test_registry.py tests/test_http_openapi.py tests/test_graphql_namespace.py -q` |
| **Full suite command** | `uv run pytest -q -m "not integration and not optional_engine"` |
| **CI run command** | `uv run pytest -q -m "not optional_engine" --junitxml=junit.xml` |
| **Estimated runtime** | ~2 s targeted `-k`; ~5 s per new file; ~90 s full local suite |

**Snapshot tooling:** `syrupy==6.1.1` (dev, pinned). A missing snapshot FAILS (sound). The update flow is `uv run pytest <file> --snapshot-update` and it is **only** legal in the capture task, never after the rewrite.

**Floor constraint:** Python 3.10. No `asyncio.Barrier`/`asyncio.timeout`/`TaskGroup`/`except*` in library or tests. No `unittest.mock` (repo convention: hand-rolled doubles).

**Lazy-import constraint:** `context.py` must not import `pool` at module level; `security/config.py` must not import `fastapi`/`PyJWT` at module level; `http/routes.py` and `graphql/schema.py` keep their `fastapi`/`strawberry` imports function-local where they already are.

---

## Sampling Rate

- **After every task commit:** the targeted command of the plan that owns the task. **06-01 is split so no commit is red:** after **T1** run `uv run pytest tests/test_singleton.py -q` (green, no warning yet — `tests/test_registry.py` does not exist until T2); after **T2** run `uv run pytest tests/test_registry.py tests/test_singleton.py -q`. The shim `DeprecationWarning` and the `test_singleton.py` migration land in the **same** T2 commit (W1), so there is never an intermediate red suite under `filterwarnings=["error"]`. Wave 1 also runs `uv run pytest tests/test_security.py -q`; Wave 2 `uv run pytest tests/test_http_openapi.py tests/test_graphql_namespace.py -q`; Wave 3 `uv run pytest tests/test_trust_boundaries.py -q`.
- **After every plan wave:** `uv run pytest -q -m "not integration and not optional_engine"` (wave gate; the targeted run does NOT substitute it).
- **Before `/gsd-verify-work`:** full suite green + `uv run ruff check .` + `uv run mypy encino_orm` + `uv lock --check` + `uv run mkdocs build --strict`.
- **Max feedback latency:** ~2 s targeted `-k`; no barriers, no sleeps, no containers (SQLite `:memory:` only).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure / Correct Behavior | Test Type | Automated Command | Expected Result | File Exists | Status |
|---------|------|------|-------------|------------|---------------------------|-----------|-------------------|-----------------|-------------|--------|
| 06-01-01 | 06-01 | 1 | CFG-01 | T-06-01-02, T-06-01-04, T-06-01-05 | `ConnectionRegistry` con estado de instancia + `resolve_db(registry=None)` + shims retrocompatibles SIN warning; `pool` importado perezosamente | unit (stdlib) + suite existente | `uv run python -c "from encino_orm.context import ConnectionRegistry, resolve_db; ..."` && `uv run pytest tests/test_singleton.py -q` && `uv run ruff check encino_orm/context.py encino_orm/__init__.py` | green; `class ConnectionRegistry` == 1; `global _default_db` == 0; import de `pool` a nivel de módulo == 0; `DeprecationWarning` == 0 (llega en T2); `test_singleton.py` verde | ❌ W0 | ⬜ pending |
| 06-01-02 | 06-01 | 1 | CFG-01 | T-06-01-01, T-06-01-03 | Dos registries resuelven a su BD; shim deprecado avisa; `bind` gana; teardown sin warning. **El `warnings.warn` de los shims y la migración de `test_singleton.py` van en el MISMO commit (W1)** | unit (SQLite `:memory:`) | `uv run pytest tests/test_registry.py tests/test_singleton.py -q` | green; `def test_` >= 7 en `test_registry.py`; 4 `pytest.warns(DeprecationWarning)` en `test_singleton.py`; `set_default_db(None)` == 0; ningún commit intermedio rojo | ❌ W0 | ⬜ pending |
| 06-02-01 | 06-02 | 1 | CFG-02 | T-06-02-02, T-06-02-03, T-06-02-05 | `SecurityConfig` frozen sin imports opcionales; `security_dependencies(config)`; firmas legacy + fallback deprecado | unit (stdlib) | `uv run python -c "... FrozenInstanceError ..."` && `uv run ruff check encino_orm/security` | green; `frozen=True` == 1; `from fastapi`/`from jwt` en `config.py` == 0; `def security_dependencies` == 1; `Annotated` >= 2 | ❌ W0 | ⬜ pending |
| 06-02-02 | 06-02 | 1 | CFG-02 | T-06-02-01, T-06-02-04 | 200/401/403 desde config; mutar globales sin efecto; warning único sin filtrar el secreto | integration in-process (httpx `ASGITransport`) | `uv run pytest tests/test_security.py -q` && `uv run ruff check --isolated --select B008,S105 tests/test_security.py` | green; `class TestSecurityConfig` == 1; `FrozenInstanceError` >= 1; `guard.SECRET` >= 1; `B008`/`S105` == 0 | ❌ W0 | ⬜ pending |
| 06-03-01 | 06-03 | 2 | CFG-03 | T-06-03-01 | OpenAPI snapshot capturado CONTRA el `exec()` actual y commiteado antes del rewrite | snapshot (syrupy) | `uv run pytest tests/test_http_openapi.py -q` | green sin `--snapshot-update`; `.ambr` existe con `operationId`; `exec` sigue en `routes.py` | ❌ W0 | ⬜ pending |
| 06-03-02 | 06-03 | 2 | CFG-03 | T-06-03-02, T-06-03-03, T-06-03-04, T-06-03-05 | `_build_path_handler` con closures + `__signature__` (sin `exec`); `create`/`list_` con `Annotated`; OpenAPI byte-idéntica | snapshot + integration | `uv run pytest tests/test_http_openapi.py -q` && `uv run pytest tests/test_crud.py tests/test_pk.py tests/test_pagination_limits.py -q` | green; `^\s*exec\(` == 0; `__signature__` >= 1; `Annotated` >= 2; `.ambr` con diff cero | ❌ W0 | ⬜ pending |
| 06-03-03 | 06-03 | 2 | CFG-03 | T-06-03-06 | No-regresión completa y snapshots SQL intactos | regression | `uv run pytest -q -m "not integration and not optional_engine"` && `git diff --stat tests/__snapshots__/test_sql_snapshots.ambr` | green; diff SQL vacío; diff OpenAPI vacío desde el commit de captura | ❌ W0 | ⬜ pending |
| 06-04-01 | 06-04 | 2 | CFG-03 | T-06-04-01 | SDL snapshot capturada CONTRA el `exec()` actual y commiteada antes del rewrite | snapshot (syrupy) | `uv run pytest tests/test_graphql_namespace.py -q` | green sin `--snapshot-update`; `.ambr` con SDL; `exec` sigue en `schema.py` | ❌ W0 | ⬜ pending |
| 06-04-02 | 06-04 | 2 | CFG-03 | T-06-04-04 | `_pk_resolver` con closures + `__signature__` (sin `exec`); SDL byte-idéntica | snapshot + unit | `uv run pytest tests/test_graphql_namespace.py -q` && `uv run pytest tests/test_graphql.py tests/test_pk.py -q` | green; `^\s*exec\(` == 0; `__signature__` >= 1; `.ambr` con diff cero | ❌ W0 | ⬜ pending |
| 06-04-03 | 06-04 | 2 | CFG-04 | T-06-04-02, T-06-04-03, T-06-04-05, T-06-04-06 | Namespace por build; no muta el módulo real; sin fugas en `sys.modules`; dos schemas funcionales | unit | `uv run pytest tests/test_graphql_namespace.py -q` && `uv run pytest tests/test_graphql.py tests/test_pk.py tests/test_pagination_limits.py -q` | green; `ModuleType` >= 1; `del sys.modules[name]` == 1; `setattr(module` == 0; `set(vars(module))` idéntico | ❌ W0 | ⬜ pending |
| 06-05-01 | 06-05 | 3 | CFG-05 | T-06-05-01, T-06-05-02, T-06-05-03 | Fronteras documentadas con ejemplos seguros/inseguros; parsers no emiten `raw`; docs build estricto | docs + unit (regresión) | `uv run pytest tests/test_trust_boundaries.py -q` && `uv run mkdocs build --strict` | green; 3 encabezados; >= 1 bloque inseguro; `trust-boundaries.md` en nav; parsers sin `.raw(` | ❌ W0 | ⬜ pending |
| 06-05-02 | 06-05 | 3 | CFG-05 | T-06-05-06 | `CHANGELOG.md` documenta CFG-01…05 con viejo/nuevo y ownership a `08-04` | docs (presencia) | `uv run python -c "... Unreleased contiene ConnectionRegistry/SecurityConfig/__signature__/build_schema/trust-boundaries ..."` | green; 5 claves presentes en `[Unreleased]`; sin entradas duplicadas | ❌ W0 | ⬜ pending |
| 06-05-03 | 06-05 | 3 | CFG-05 | T-06-05-04, T-06-05-05 | Supresiones retiradas con el código arreglado; `PyJWT` bump con lock + auditorías; `ci.yml` sin ignores | gates + supply chain | `uv run ruff check .` && `uv run mypy encino_orm` && `uv lock --check` && `uv run pytest tests/test_security.py -q` && `uv run pytest -q -m "not integration and not optional_engine"` | green; `S102`/`B008` == 0 (o residual con causa); `PyJWT>=2.8,<2.15` == 1; `GHSA-` en `ci.yml` == 0 (o fail-closed) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Files/artifacts that do NOT exist today and that a phase plan must create before its assertions can run:

- [ ] `tests/test_registry.py` — CFG-01 (dos registries, shim deprecado con `pytest.warns`, precedencia `bind`, camino caliente limpio) — **06-01 Task 2**
- [ ] `encino_orm/context.py` — `ConnectionRegistry`, `_registry`, `resolve_db(registry=None)`, shims — **06-01 Task 1**
- [ ] `encino_orm/security/config.py` — `SecurityConfig` frozen — **06-02 Task 1**
- [ ] `encino_orm/security/guard.py` — `security_dependencies(config)` + firmas legacy — **06-02 Task 1**
- [ ] Extensión de `tests/test_security.py` — `TestSecurityConfig` + migración `Annotated`/`S105` — **06-02 Task 2**
- [ ] `tests/test_http_openapi.py` + `tests/__snapshots__/test_http_openapi.ambr` — CFG-03; el `.ambr` generado contra el `exec()` actual y commiteado **antes** del rewrite — **06-03 Task 1**
- [ ] `tests/test_graphql_namespace.py` + `tests/__snapshots__/test_graphql_namespace.ambr` — CFG-04 + SDL; mismo orden estricto — **06-04 Task 1**
- [ ] `docs/trust-boundaries.md` + `tests/test_trust_boundaries.py` — CFG-05 — **06-05 Task 1**
- [ ] `CHANGELOG.md` `[Unreleased]` — CFG-01…05 — **06-05 Task 2**
- [ ] `pyproject.toml` + `ci.yml` + `uv.lock` — retirada de supresiones y bump de `PyJWT` — **06-05 Task 3**
- [ ] No new shared fixtures in `tests/conftest.py` (`connected_db` already covers SQLite).
- [ ] Framework install: none (all present and pinned; no new package is introduced).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| **Snapshot ordering** (the `.ambr` is captured and committed BEFORE the rewrite and never regenerated after) | CFG-03 | Git history ordering cannot be asserted from inside a pytest run; a later `--snapshot-update` would silently overwrite the guardian | Inspect `git log --oneline -- tests/__snapshots__/test_http_openapi.ambr tests/__snapshots__/test_graphql_namespace.ambr`: the capture commit must be an ancestor of the rewrite commit. Then run `uv run pytest tests/test_http_openapi.py tests/test_graphql_namespace.py -q` **without** `--snapshot-update` and confirm the `.ambr` files have no diff. Record both commit hashes in the SUMMARY |
| **Trust-boundary prose quality** | CFG-05 | The test only asserts the page exists and has the three headings plus an unsafe block; whether the examples are actually safe/unsafe is a human judgement | Read `docs/trust-boundaries.md` end to end: each of `Filter.raw`, `Query`, `db.fn.*` must have one safe and one unsafe example, and the `Query` string-literal limitation must be stated. Confirm no real credentials appear |
| **`PyJWT` cap bump outcome** | CFG-02 | The bump is fail-closed and may legitimately be reverted; the decision depends on two independent audit feeds run in CI/local | Run `uv audit` (no `--ignore`) and `uv export --format requirements-txt --no-emit-project --no-hashes > tmp && uv run pip-audit -r tmp`. If both are clean and `tests/test_security.py` is green, confirm the 5 `--ignore GHSA-*` are gone from `ci.yml`. If either reports, confirm the cap is still `<2.13` and the cause is written in the SUMMARY and CHANGELOG |
| **`uv.lock` reflects the final `pyproject.toml`** | CFG-02 | Lock consistency is a CI job, but a stale lock on a dev host can mask the bump | `uv lock --check` returns 0 after the bump commit; `grep -c "PyJWT>=2.8,<2.15" pyproject.toml` == 1 |
| **No snapshot drift in the gate/dependency commit** | CFG-03/CFG-05 | A regenerated `.ambr` inside the bump commit would invalidate both guardians | `git diff --name-only <bump-commit>` must not list any file under `tests/__snapshots__/` |

---

## Nyquist Dimension Checklist

| Dimension | Covered by | Evidence |
|-----------|-----------|----------|
| **Every task has automated verify** | 13/13 tasks | Todas las tareas tienen `<verify><automated>`; ninguna dependencia nueva que exija un checkpoint humano |
| **No 3 consecutive tasks without automated verify** | sampling rate | Cada tarea tiene comando; sin checkpoints humanos en la fase |
| **Requirement coverage** | CFG-01→06-01, CFG-02→06-02, CFG-03→06-03+06-04, CFG-04→06-04, CFG-05→06-05 | 5/5 requisitos con al menos un test automatizado |
| **Contract-preservation dimension (criterio 3)** | OpenAPI snapshot (06-03) + SDL snapshot (06-04) + `test_crud`/`test_pk`/`test_graphql` | Byte-identity verified before/after; `operationId` preserved by `__name__="handler"` |
| **Isolation dimension (criterios 1/2/4)** | Dos registries (06-01), mutar globales sin efecto (06-02), `set(vars(module))` idéntico (06-04) | Tests dedicados por criterio |
| **Warning dimension** | `filterwarnings=["error"]`; migración de `test_singleton.py` **en el mismo commit** que el warning del shim (W1); warning solo en shims/fallback | Suite verde bajo `-W error`; sin allowlist nueva; ningún commit intermedio rojo |
| **Lazy-import dimension** | `context.py` sin `pool` a nivel de módulo; `security/config.py` sin `fastapi`/`PyJWT` | Greps de control por fichero |
| **Snapshot-ordering dimension** | Captura en Task 1 de 06-03/06-04; rewrite en Task 2; diff cero | Commits separados + `git diff --stat` vacío del `.ambr` |
| **Gate-integrity dimension** | Supresiones retiradas solo tras `ruff`/`mypy` verdes; residual con causa escrita | `uv run ruff check .` + `uv run mypy encino_orm` == 0 |
| **Supply-chain dimension** | `PyJWT` bump con `uv lock` + `uv audit` + `pip-audit`, commit aislado, fail-closed | Dos feeds independientes limpios antes de retirar los ignores |
| **Feedback latency** | targeted ~2 s; sin barreras, sleeps ni contenedores | SQLite `:memory:` únicamente |
| **Wave 0 gaps** | sección Wave 0 | 10 artefactos listados; todos con dueño en un plan |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s (quick run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (draft — se aprueba al cerrar la fase)
