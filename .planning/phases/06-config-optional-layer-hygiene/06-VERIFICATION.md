---
phase: 06-config-optional-layer-hygiene
verified: 2026-09-19T07:30:41Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 6: Config & Optional-Layer Hygiene Verification Report

**Phase Goal:** No mutable module-level global decides which database or which secret is in play, and generated handlers stop being built with `exec()` — without changing the HTTP or GraphQL contract.
**Verified:** 2026-09-19T07:30:41Z
**Status:** passed
**Re-verification:** No — initial verification (no previous `*-VERIFICATION.md`)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Two `ConnectionRegistry` instances resolve to their own databases; deprecated global shim still works with a `DeprecationWarning` | ✓ VERIFIED | `encino_orm/context.py:32-76` (instance `_default_db`); `tests/test_registry.py` 9 tests green (`test_dos_registries_resuelven_a_su_propia_db`, `test_shim_deprecado_avisa`). Independent probe: two registries → `DB_A`/`DB_B`; `set_default_db`/`get_default_db` emit exactly 2 `DeprecationWarning`s. No `global _default_db` remains. |
| 2 | `SecurityConfig` is frozen and guards are built from injected config; mutating `SECRET`/`GET_DB` no longer changes behavior | ✓ VERIFIED | `encino_orm/security/config.py:25-49` (`@dataclass(frozen=True)` + fail-closed `__post_init__`); `guard.py:67-112` (`security_dependencies(config)`). `tests/test_security.py::TestSecurityConfig` (9 tests) green: `FrozenInstanceError`, 200/401/403 from config, globals inert. Probe: frozen mutation raises; empty secret / `None` get_db rejected. |
| 3 | Generated OpenAPI schema identical before/after `exec()`→closure rewrite; path params still validate | ✓ VERIFIED | No real `exec(` call in `routes.py`/`schema.py` (only docstring mentions). `.ambr` captured against `exec()` at `ca20a32` (ancestor of HEAD), never touched after (`git diff` empty); `tests/test_http_openapi.py` passes WITHOUT `--snapshot-update`. Path params: `abc`→422, `999`→404, `1`→200; composite `abc/2`→422, `7/admin`→404 then 200. |
| 4 | Two successive `build_schema` calls do not mutate module-level GraphQL namespace state | ✓ VERIFIED | `graphql/schema.py:190-220` (per-build `types.ModuleType` + `weakref.finalize`, no `setattr(module, ...)`). `tests/test_graphql_namespace.py` 6 tests green incl. `test_build_schema_no_muta_el_namespace_del_modulo` + `test_build_schema_no_fuga_modulos_sinteticos`. Independent probe: namespace unchanged after 2 builds; no `_build_*` entries in `sys.modules` after `gc.collect()`. |
| 5 | `Filter.raw`, `Query` and `db.fn.*` trust boundaries documented with safe/unsafe examples | ✓ VERIFIED | `docs/trust-boundaries.md` (4424 B) with `## Filter.raw`, `## Query`, `## db.fn.*` + `SEGURO`/`INSEGURO` examples; `Filter.raw` docstring in `model/filter.py`; `tests/test_trust_boundaries.py` 5 tests green (parsers cannot emit `raw`, page presence, verbatim re-emit). |

**Score:** 5/5 roadmap truths verified. All plan-level must-haves (06-01…06-05) also resolve to VERIFIED.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/context.py` | `ConnectionRegistry`, module `_registry`, `resolve_db(registry=None)`, deprecated shims | ✓ VERIFIED | 128 lines; no module-level `pool` import; `is None` identity (WR-03). |
| `encino_orm/security/config.py` | Frozen `SecurityConfig`, no optional imports at module level | ✓ VERIFIED | 49 lines; stdlib + `.exceptions` only; fail-closed `__post_init__`; `secret` `field(repr=False)`. |
| `encino_orm/security/guard.py` | `security_dependencies(config)`, legacy signatures, deprecated globals | ✓ VERIFIED | 141 lines; `Annotated[...]` injection; legacy fallback warns once without leaking secret. |
| `encino_orm/security/jwt.py` | `verify_token`/`verify_refresh` fail-closed on empty secret | ✓ VERIFIED | `_check_secret` at `:74-79` called by both verifiers (`:83`, `:113`) — WR-01-R closed. |
| `encino_orm/http/routes.py` | closures + `__signature__`, no `exec()` | ✓ VERIFIED | `_build_path_handler:28-90`; `__signature__`, `__name__/__qualname__="handler"`; no real `exec(`. |
| `encino_orm/graphql/schema.py` | closures + `__signature__`, per-build namespace, no `exec()` | ✓ VERIFIED | `_pk_resolver:54-111`; `build_schema:174-220`; no real `exec(`. |
| `tests/__snapshots__/test_http_openapi.ambr` | Frozen OpenAPI (guard) | ✓ VERIFIED | 31006 B; single commit `ca20a32`; diff clean. |
| `tests/__snapshots__/test_graphql_namespace.ambr` | Frozen SDL (guard) | ✓ VERIFIED | 2256 B; single commit `e1fbcd3`; diff clean. |
| `docs/trust-boundaries.md` | 3 sections + safe/unsafe | ✓ VERIFIED | Present; guarded by test. |
| `CHANGELOG.md` | CFG-01…05 entries | ✓ VERIFIED | 5 `CFG-0*` entries; no `PENDIENTE_BUMP`. |
| `pyproject.toml` | `PyJWT>=2.8,<2.15`; S102/B008 retired | ✓ VERIFIED | cap present; `"S102"|"B008"` count 0. |
| `.github/workflows/ci.yml` | no GHSA ignores; `--all-extras` | ✓ VERIFIED | `GHSA-` count 0; `--all-extras` at `:247` (WR-04 closed). |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `Model._get_db` | `context.resolve_db` | zero-arg call (back-compat) | ✓ WIRED | `resolve_db()` zero-arg path unchanged (tests + probe). |
| `context.set_default_db` | `context._registry` | shim writes module registry | ✓ WIRED | `_registry.set_default(db)` at `:93`. |
| `security_dependencies` | `jwt.verify_token` | `config.secret` + `list(config.algorithms)` | ✓ WIRED | `guard.py:87-91`. |
| `_build_path_handler` | `fastapi` | `__signature__` read by FastAPI | ✓ WIRED | Snapshot + path-param test. |
| `_pk_resolver` | `strawberry` | `__signature__` → GraphQL args | ✓ WIRED | SDL snapshot byte-identical. |
| `build_schema` | `LazyType.resolve_type` | synthetic module in `sys.modules` | ✓ WIRED | Per-build module; self-ref filters execute; finalize on GC. |
| `test_trust_boundaries` | `http/parsing._OP_MAP` | no parser emits `raw` | ✓ WIRED | 5 tests green. |

### Data-Flow Trace (Level 4)

Not applicable — Phase 6 changes configuration/wiring and code-generation internals; the generated HTTP/GraphQL handlers were verified end-to-end by the snapshot + behavioral tests (real SQLite DBs, real ASGI/GraphQL execution), which is stronger than a static data-flow trace.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Phase test suites | `uv run pytest tests/test_registry.py tests/test_singleton.py tests/test_security.py tests/test_http_openapi.py tests/test_graphql_namespace.py tests/test_trust_boundaries.py -q` | 61 passed, 2 snapshots passed | ✓ PASS |
| Full suite (non-integration) | `uv run pytest -q -m "not integration and not optional_engine"` | 969 passed, 88 deselected, 12 snapshots | ✓ PASS |
| Full suite | `uv run pytest -q` | 1057 passed, 12 snapshots | ✓ PASS |
| Two registries + shim warning | independent probe (`/tmp/probe_all.py`) | `True` / 2 `DeprecationWarning` | ✓ PASS |
| Frozen config + fail-closed + empty-secret token | independent probe | frozen True; rejects; forged token REJECTED | ✓ PASS |
| Namespace non-mutation + no leak | independent probe (`/tmp/probe_c4.py` semantics) | unchanged; no `_build_*` after gc | ✓ PASS |
| Trust-boundary page/headings | independent probe | headings + `INSEGURO` + docstring True | ✓ PASS |
| Lint / format / types | `uv run ruff check encino_orm tests` / `ruff format --check` / `mypy encino_orm` | All checks passed / 124 formatted / Success (61 files) | ✓ PASS |
| Docs strict build | `uv run mkdocs build --strict` | exit 0 | ✓ PASS |
| Lock integrity | `uv lock --check` | exit 0 (`pyjwt 2.14.0`) | ✓ PASS |

### Probe Execution

No project probe scripts (`scripts/*/tests/probe-*.sh`) exist for this phase; verification used the test suites and independent Python probes above. Step 7c: SKIPPED (no conventional probes).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| CFG-01 | 06-01 | `ConnectionRegistry` replaces `_default_db` global with deprecated shims | ✓ SATISFIED | `context.py`; `test_registry.py` |
| CFG-02 | 06-02 | Immutable `SecurityConfig` + guard factories replace mutable `SECRET`/`GET_DB` | ✓ SATISFIED | `security/config.py`, `guard.py`; `test_security.py` |
| CFG-03 | 06-03, 06-04 | `exec()`-generated handlers replaced by closures/`__signature__`, guarded by pre/post snapshots | ✓ SATISFIED | `routes.py`, `schema.py`; `.ambr` guards; 0 real `exec(` |
| CFG-04 | 06-04 | `build_schema` uses a per-build namespace, no module mutation | ✓ SATISFIED | `schema.py:174-220`; `test_graphql_namespace.py` |
| CFG-05 | 06-05 | Trust boundaries of `Filter.raw`/`Query`/`db.fn.*` documented | ✓ SATISFIED | `docs/trust-boundaries.md`; `test_trust_boundaries.py` |

**Orphaned requirements:** none — `REQUIREMENTS.md` maps exactly CFG-01…05 to Phase 6 and all five are claimed by plans.
**Tracking note (INFO):** `REQUIREMENTS.md` lines 66-67 / 173-174 still mark CFG-03 and CFG-04 as `[ ]` / "Pending" even though the code and ROADMAP mark them complete. This is stale tracking text, not a code gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX` debt markers in any phase-modified file | — | Debt-marker gate: clean (grep exit 1). |

No stubs, no empty implementations, no hardcoded-empty data, no `exec()` calls, no orphaned artifacts.

### Human Verification Required

None. All five success criteria are programmatically verified (snapshots, behavioral tests over real SQLite/ASGI/GraphQL execution, and independent probes).

### Gaps Summary

No gaps. The phase goal is achieved in the codebase at HEAD (`01aeb9a`):

- **CR-01 (security fix) confirmed present:** `SecurityConfig.__post_init__` rejects empty/`None` secret and empty `algorithms` at construction; additionally `_check_secret` in `verify_token`/`verify_refresh` rejects an empty secret at the low-level public API (WR-01-R). Independent probe forged an HS256 empty-key token: `verify_token(tok, "")` now raises `AuthenticationError`.
- **GraphQL namespace deviation confirmed correct:** `weakref.finalize` (not `del sys.modules[name]`) is used because self-referential `LazyType` filters resolve at execution time. Criterion-4 property holds: no mutation of `encino_orm.graphql.schema` namespace, and no permanent `sys.modules` leak (finalize fires on cyclic GC; `gc.collect()` → no `_build_*` entries).

**Known residuals (documented, non-blocking — no truth depends on them):**

1. A `Model` without explicit `db` resolves through the module registry, not an injected one. Documented in `context.py` module + class docstrings, `CHANGELOG.md`, and `docs/getting-started.md`; per-tenant isolation requires `db=`/`bind`/`session`. (WR-02 residual — wording corrected; no code gap.)
2. `dataclasses.asdict()`/`astuple()` still include `secret`; `repr`/`str` do not (`field(repr=False)`). Documented in the `SecurityConfig` docstring ("no serialices la config"). No production code serializes the config. (WR-01 residual.)
3. mypy-ratchet entries for `http.routes`, `http.parsing`, `security.guard`, `graphql.*`, `security.models` were kept with rewritten causes because `mypy encino_orm` is only clean with them; the plan/criterion explicitly permits "residual with cause written". (Not a gap.)
4. MSSQL `HY000` KILL detection uses English message markers — outside Phase 6 scope.
5. `pip-audit` cross-check now uses `--all-extras` (WR-04 closed), though the deferred-items note remains as historical context.

---

_Verified: 2026-09-19T07:30:41Z_
_Verifier: the agent (gsd-verifier)_
