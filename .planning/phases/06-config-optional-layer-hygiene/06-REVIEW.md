---
phase: 06-config-optional-layer-hygiene
reviewed: 2026-09-19T07:21:34Z
depth: deep
files_reviewed: 31
files_reviewed_list:
  - encino_orm/context.py
  - encino_orm/__init__.py
  - encino_orm/security/config.py
  - encino_orm/security/guard.py
  - encino_orm/security/__init__.py
  - encino_orm/security/jwt.py
  - encino_orm/http/routes.py
  - encino_orm/graphql/schema.py
  - encino_orm/graphql/types.py
  - encino_orm/graphql/filters.py
  - encino_orm/model/filter.py
  - encino_orm/model/model.py
  - encino_orm/query.py
  - tests/test_registry.py
  - tests/test_singleton.py
  - tests/test_security.py
  - tests/test_http_openapi.py
  - tests/__snapshots__/test_http_openapi.ambr
  - tests/test_graphql_namespace.py
  - tests/__snapshots__/test_graphql_namespace.ambr
  - tests/test_trust_boundaries.py
  - docs/trust-boundaries.md
  - docs/integrations.md
  - docs/getting-started.md
  - docs/reference/context.md
  - README.md
  - CHANGELOG.md
  - pyproject.toml
  - .github/workflows/ci.yml
  - uv.lock
  - .planning/phases/06-config-optional-layer-hygiene/deferred-items.md
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-09-19T07:21:34Z
**Depth:** deep
**Files Reviewed:** 31
**Status:** issues_found

## Summary

Phase 6 is substantially well executed. I verified the core CFG-01…CFG-05 mechanics by
reading the code and running targeted probes (`uv run pytest` 964 passed / 12 snapshots,
`uv audit` clean, `pip-audit` clean, `ruff check`/`format --check` clean, `mypy` clean,
`uv lock --check` clean). Snapshot ancestry is genuine: `ca20a32` (HTTP) is an ancestor of
`fa76bcf`, `e1fbcd3` (SDL) is an ancestor of `66671d0`/`d98ca92`, and neither `.ambr` was
touched after capture (diff empty). The GraphQL `weakref.finalize` deviation is correct:
I confirmed two successive builds don't mutate `encino_orm.graphql.schema`, the synthetic
modules are popped when their schema is collected, a live schema keeps working after the
sibling module is popped, and the SDL is byte-identical.

The one **Critical** finding is a security regression introduced by the new recommended
security path: `SecurityConfig` + `security_dependencies(config)` bypasses the fail-closed
secret validation that the legacy `_resolve()` enforced, so an empty JWT secret is silently
accepted and forged tokens authenticate. The remaining warnings are a secret-in-`repr`
disclosure, an over-claimed tenant-isolation benefit (`ConnectionRegistry` is not wired into
`Model`), a truthiness bug in `resolve_db`, and a CI audit-coverage gap.

### Requirement verification

- **CFG-01 — VERIFIED TRUE (mechanics):** `ConnectionRegistry` has instance state;
  `resolve_db()` zero-arg behavior unchanged; both shims warn exactly once; two registries
  resolve independently; no `global _default_db` remains. **INCOMPLETE** end-to-end: see WR-02.
- **CFG-02 — VERIFIED TRUE:** frozen dataclass; guards close over config; mutating
  `guard.SECRET`/`GET_DB` is inert; explicit legacy args warning-free; exactly one warning on
  fallback; warning message does not contain the secret. **INCOMPLETE:** fail-closed validation
  is lost on the config path (CR-01) and the secret leaks via `repr` (WR-01).
- **CFG-03 — VERIFIED TRUE:** no `exec()` remains; OpenAPI and SDL byte-identical; path params
  still validate (int 422 / str 200/404); `__signature__`/`__name__` preserve `operationId`.
- **CFG-04 — VERIFIED TRUE:** per-build namespace; no module-namespace mutation; no permanent
  `sys.modules` leak; finalize fires; no cross-schema interference; SDL unchanged.
- **CFG-05 — VERIFIED TRUE:** `docs/trust-boundaries.md` present with the three headings and
  an `INSEGURO` example; HTTP/GraphQL parsers cannot emit `Filter.raw`; `Filter.raw` re-emits
  verbatim and binds values.
- **06-05 — VERIFIED TRUE:** `S102`/`B008` per-file-ignores genuinely retired (ruff clean, no
  `# noqa`/`# type: ignore` added); mypy ratchet entries kept with rewritten causes and no new
  entries; PyJWT cap `<2.15` resolved to 2.14.0 in `uv.lock`; GHSA ignores removed; `uv audit`
  clean without ignores; `ci.yml` valid. **Gap:** `pip-audit` cross-check does not cover extras
  (WR-04).

## Critical Issues

### CR-01: `SecurityConfig` path skips fail-closed secret validation → empty JWT secret authenticates forged tokens

**File:** `encino_orm/security/config.py:17-28` and `encino_orm/security/guard.py:67-112`

**Issue:** The legacy path validates configuration in `_resolve()` and fails closed
(`if not secret: raise AuthenticationError` / `if db_dep is None: raise`). The new
recommended path (`SecurityConfig` → `security_dependencies(config)`, documented in
`docs/integrations.md`) never calls `_resolve()` and performs **no** validation. A
`SecurityConfig` built with an empty secret is accepted, and `verify_token(token, "")`
authenticates any HS256 token signed with the empty key — PyJWT only emits an
`InsecureKeyLengthWarning`, it does not reject. An app following the new docs with
`os.environ.get("SECRET_KEY", "")` (missing env var) silently accepts forged tokens. This
directly contradicts the project's core value ("seguro frente a … configuraciones erróneas")
and regresses the guard that existed before Phase 6.

**Reproduction (verified):**
```python
import jwt, time
from encino_orm.security.jwt import verify_token
tok = jwt.encode({"sub": "attacker", "type": "access",
                  "exp": int(time.time()) + 1000}, "", algorithm="HS256")
verify_token(tok, "")          # -> {'sub': 'attacker', ...}  (accepted, only a warning)
```
And end-to-end through the documented API: `SecurityConfig(secret="", get_db=...)` +
`security_dependencies(cfg)` accepts a forged empty-secret bearer token past
`verify_token` (probe reached `PermissionSet.for_user` with the attacker's `sub`).
There is also no test asserting that `SecurityConfig` rejects empty/`None` secret —
`test_fallback_sin_globales_falla_cerrado` only covers the legacy fallback.

**Fix:** validate at construction and/or in the factory, e.g.:
```python
@dataclass(frozen=True)
class SecurityConfig:
    secret: str
    get_db: Callable
    algorithms: tuple[str, ...] = ("HS256",)

    def __post_init__(self):
        if not self.secret:
            raise AuthenticationError("SECRET no configurado para la dependency de seguridad")
        if self.get_db is None:
            raise AuthenticationError("get_db no configurado para la dependency de seguridad")
```
and add a test `test_config_sin_secret_falla_cerrado`.

## Warnings

### WR-01: `SecurityConfig` leaks the JWT secret through its generated `repr`/`str`/`asdict`

**File:** `encino_orm/security/config.py:26`

**Issue:** `@dataclass(frozen=True)` generates a `__repr__` (and `str` delegates to it) that
includes every field. `repr(config)` / `str(config)` / `dataclasses.asdict(config)` expose the
raw signing key, so a single `logger.info("security config: %s", config)`, an unhandled
exception dump, or a pytest failure rendering can write the JWT secret to logs. Phase 6
carefully avoided leaking the secret in the deprecation message (Pitfall 12) but reintroduced
the exposure via the value object itself.

**Reproduction (verified):**
```python
repr(SecurityConfig("SUPER-SECRET-JWT-KEY", get_db))  # -> "SecurityConfig(secret='SUPER-SECRET-JWT-KEY', ...)"
```

**Fix:** mark the field as non-repr and avoid `asdict` exposure:
```python
from dataclasses import dataclass, field
...
    secret: str = field(repr=False)
```

### WR-02: `ConnectionRegistry` is not wired into `Model`; tenant-isolation claim is incomplete

**File:** `encino_orm/context.py:114-121`, `encino_orm/model/model.py:218,591`

**Issue:** `Model._get_db()` and `Model.insert_many()` call `resolve_db()` with no registry,
so the implicit resolution path always uses the module-level `_registry`. Passing an explicit
`ConnectionRegistry` only affects direct `resolve_db(registry=...)` calls; it cannot isolate
`Model`-based CRUD. The module docstring and `CHANGELOG.md` claim two applications/tenants in
one process "resuelven a sus propias bases de datos sin pisarse" — that is not true for the
primary API. `docs/getting-started.md` is more careful ("la resolución implícita del `Model`
no cambia"), but that contradicts the stronger CHANGELOG/module claim.

**Reproduction (verified):**
```python
_registry.set_default(db_a)
reg = ConnectionRegistry(db_b)
resolve_db(registry=reg)      # -> db_b (explicit)
U(name="x")._get_db()         # -> db_a  (Model ignores reg)
```

**Fix:** thread an optional registry into the resolution chain used by `Model`
(e.g. `Model._registry` / a `registry` parameter forwarded to `resolve_db`), or downgrade the
CHANGELOG/module-docstring wording to state that isolation requires calling
`resolve_db(registry=...)` explicitly and that `Model` still uses the process registry.

### WR-03: `resolve_db(registry or _registry)` silently ignores a falsy registry

**File:** `encino_orm/context.py:121`

**Issue:** `registry or _registry` uses truthiness, not identity. A caller that passes a
`ConnectionRegistry` subclass (or any registry implementing `__bool__`/`__len__`) that is
falsy gets the module default instead — silently resolving to a different database than the
one explicitly passed. In a multi-tenant context that is a cross-tenant routing hazard.

**Reproduction (verified):**
```python
class Falsy(ConnectionRegistry):
    def __bool__(self): return False
_registry.set_default("GLOBAL")
resolve_db(registry=Falsy("SENTINEL"))   # -> "GLOBAL"  (SENTINEL ignored)
```

**Fix:**
```python
return (registry if registry is not None else _registry).resolve()
```

### WR-04: `pip-audit` cross-check never audits the optional extras (including PyJWT)

**File:** `.github/workflows/ci.yml:239-245`

**Issue:** `uv export --format requirements-txt --no-emit-project --no-hashes` without
`--all-extras`/`--extra` exports only default dependencies + the `dev` group. The `security`
extra (`PyJWT`), `http`, `graphql`, etc. are excluded, so the "second independent feed"
never audits the very dependency whose cap was bumped in this phase. The step comment claims
two-source coverage that does not exist. (Acknowledged in `deferred-items.md`, but the CI
comment still overstates coverage and the gap is not tracked as a phase deliverable.)

**Fix:** add `--all-extras` to the export (or the relevant `--extra security --extra http
--extra graphql`) and revalidate the job, or correct the comment to state the cross-check
covers only base+dev dependencies.

## Info

### IN-01: Stale references to the removed `_default_db`/`set_default_db` precedence

**File:** `encino_orm/model/model.py:214`, `docs/design/9-singleton.md:71-110`

**Issue:** `Model._get_db` docstring still lists `set_default_db()` as the last precedence
level; `docs/design/9-singleton.md` still contains the old implementation snippets
(`global _default_db = None`, `return _default_db`) under a note. The note explains the
change, but the stale code samples are misleading.

**Fix:** update the docstring to "default del `ConnectionRegistry`" and either remove or
clearly mark the old snippets as historical.

### IN-02: Dead/misleading `= None` default on the `list_` handler's `db` dependency

**File:** `encino_orm/http/routes.py:114`

**Issue:** `db: Annotated[object, Depends(get_db)] = None` — FastAPI ignores the `None` for a
`Depends` annotation, so the default is dead. It is only present because preceding query
params already have defaults. Harmless, but inconsistent with the `create` handler
(`routes.py:103`) and reads as if `db` were optional.

**Fix:** keep the explicit default (required by parameter ordering) but add a short comment
noting FastAPI ignores it, or reorder so no sentinel is needed.

### IN-03: `_build_counter` + `sys.modules` name collision on module reload

**File:** `encino_orm/graphql/schema.py:171,190,219`

**Issue:** Module names are `encino_orm.graphql._build_{N}` with a module-global counter. If
`encino_orm.graphql.schema` is reloaded (`importlib.reload`), the counter resets to 1 and a
new build can register `_build_1` while an old live schema still references the previous
`_build_1`; the old schema's `weakref.finalize` would then pop the *new* module. Extremely
unlikely in normal use, but the finalize callback should be name-unique.

**Fix:** incorporate a `uuid4().hex` or `id(schema)` fragment into the module name.

---

_Reviewed: 2026-09-19T07:21:34Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
