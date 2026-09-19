---
phase: 06-config-optional-layer-hygiene
reviewed: 2026-09-19T07:26:55Z
depth: deep
files_reviewed: 13
files_reviewed_list:
  - encino_orm/security/config.py
  - encino_orm/security/guard.py
  - encino_orm/security/jwt.py
  - encino_orm/security/exceptions.py
  - encino_orm/security/__init__.py
  - encino_orm/context.py
  - encino_orm/model/model.py
  - tests/test_security.py
  - CHANGELOG.md
  - .github/workflows/ci.yml
  - pyproject.toml
  - docs/reference/context.md
  - docs/integrations.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 6 (R2): Re-review of fix commit `8a57bfb`

**Reviewed:** 2026-09-19T07:26:55Z
**Depth:** deep
**Files Reviewed:** 13
**Status:** issues_found
**Fix commit:** `8a57bfb` — "fix(06): cierra CR-01 (secret fail-closed), WR-01/02/03/04 de la revisión"

## Verdict

The Critical regression is **CLOSED** and the fix is sound for the recommended path. Three of the
four warnings are closed; **WR-01 and WR-02 are PARTIAL** (residuals in `asdict` and in the
`context.py` docstrings respectively). Two new residuals were found, neither introduced by this
commit: the low-level `verify_token` API still accepts an empty secret (the same root cause CR-01
addressed, mitigated only at the `SecurityConfig` layer), and two new validation branches plus the
WR-03 fix lack tests.

**Per-finding status:** CR-01 **CLOSED** · WR-01 **PARTIAL** · WR-02 **PARTIAL** · WR-03 **CLOSED** ·
WR-04 **CLOSED**. **New findings: 3** (1 WARNING, 2 INFO); the WR-01 `asdict` residual also
remains open (counted as a WARNING in the frontmatter).

## Closure verification

### CR-01 — CLOSED

**Evidence:** `SecurityConfig.__post_init__` (`encino_orm/security/config.py:39-48`) rejects a
non-`str`/empty `secret`, a `None` `get_db`, and an empty `algorithms`, raising
`AuthenticationError` with a message that never interpolates the secret. Probes:

```
SecurityConfig('', g)        -> AuthenticationError("SECRET no configurado ...")
SecurityConfig('SECRET', None)-> AuthenticationError("get_db no configurado ...")
SecurityConfig('SECRET', g, ())-> AuthenticationError("algorithms no puede estar vacío")
```

- Forged HS256 token with an empty secret can no longer reach `security_dependencies(config)`:
  the config cannot be constructed, so the documented path is fail-closed. The legacy paths remain
  fail-closed too — `_explicit_config`/`_legacy_config` call `_resolve()` first
  (`guard.py:33-41`), and `get_current_user(secret="", get_db=g)` raises `AuthenticationError`.
- `_legacy_config` validates **before** `warnings.warn`, so the unset-globals case raises with no
  warning (fail-closed preserved).
- `filterwarnings = ["error"]` is intact: full suite passes (`1054 passed`, `12 snapshots passed`)
  under the `pyproject.toml` `"error"` filter.
- New tests are genuine RED→GREEN. Against `8a57bfb^` the parent `config.py` had no
  `__post_init__` (so `SecurityConfig("", _noop_get_db)` did not raise) and `secret` had no
  `field(repr=False)` (so `repr` contained the secret); both new assertions fail on the parent and
  pass on the fix.

**Residual (see NEW-01):** the fix guards the config layer only; `verify_token(token, "")` still
authenticates an empty-secret forged token.

### WR-01 — PARTIAL

**Evidence:** `secret: str = field(repr=False)` (`config.py:35`). `repr(cfg)` and `str(cfg)` no
longer contain the secret (verified). However the original finding explicitly named
`dataclasses.asdict`, and it is **not** closed:

```
repr:   SecurityConfig(get_db=<function g ...>, algorithms=('HS256',))
str:    SecurityConfig(get_db=<function g ...>, algorithms=('HS256',))
asdict: {'secret': 'SUPER-SECRET-JWT-KEY', ...}   # still leaks
astuple:('SUPER-SECRET-JWT-KEY', ...)             # still leaks
```

`repr=False` suppresses the field from `__repr__` only; `asdict`/`astuple` walk `__dataclass_fields__`
and ignore `repr`. No production code calls `asdict(config)` (grep: only `strawberry.asdict` on
GraphQL payloads), so practical exposure is low, but the stated fix ("avoid `asdict` exposure") was
not implemented. To fully close, keep the key out of the dataclass fields (e.g. store a private
holder / custom `__deepcopy__`) or document the `asdict` residual explicitly.

### WR-02 — PARTIAL

**Evidence:** `CHANGELOG.md:13-29` was rewritten and is now **accurate**: it states that
`resolve_db(registry=...)` resolves against the passed registry, that `Model` without explicit `db`
resolves through the ambient chain and ultimately the module registry, that per-tenant isolation
requires `db=`/`bind`/`session`, and it explicitly labels the residual ("un `Model` no acepta un
registry directamente — residual documentado"). Good.

But the original finding also cited the **module docstring**, which is unchanged by `8a57bfb`:

- `encino_orm/context.py:13-15`: "…de modo que dos aplicaciones/tenants en el mismo proceso pueden
  resolver a bases de datos distintas sin pisarse." Still overclaims for the primary `Model` API.
- `encino_orm/context.py:32-34` (`ConnectionRegistry` docstring): "dos registries en el mismo
  proceso resuelven a sus propias bases de datos." True only for direct `resolve_db(registry=...)`
  calls, not for `Model` CRUD.
- `encino_orm/model/model.py:214` still documents the last precedence level as `set_default_db()`
  (deprecated; the real last level is the module `ConnectionRegistry`) — pre-existing IN-01, not
  addressed here.

Align the two `context.py` docstrings with the corrected CHANGELOG wording (or add the Model caveat).

### WR-03 — CLOSED

**Evidence:** `encino_orm/context.py:121-123` now uses identity:
`return (_registry if registry is None else registry).resolve()`. Probe with a falsy subclass:

```
class Falsy(ConnectionRegistry): __bool__ = lambda self: False
_registry.set_default('GLOBAL')
resolve_db(registry=Falsy('SENTINEL'))  -> 'SENTINEL'   # was 'GLOBAL'
resolve_db()                            -> 'GLOBAL'
```

Correct. No regression test was added (see NEW-03).

### WR-04 — CLOSED

**Evidence:** `.github/workflows/ci.yml:247` adds `--all-extras`. With the same uv version CI pins
(`0.12.15`), the command exits 0 and the export now contains the optional-extra deps that were
previously omitted:

```
aioodbc==0.5.0  fastapi==0.141.1  oracledb==4.0.2  pyjwt==2.14.0
pyodbc==5.3.0   redis==8.1.0      strawberry-graphql==0.324.4
```

`uv run pip-audit -r <export>` → `No known vulnerabilities found` (exit 0). The step comment's
coverage claim is now truthful.

## New Findings

### WR-01-R: `verify_token`/`verify_refresh` still authenticate an empty-secret forged token

**File:** `encino_orm/security/jwt.py:74-85, 103-114` (documented usage `docs/integrations.md:69-70`)

**Severity:** WARNING (pre-existing residual of the CR-01 root cause; not introduced by `8a57bfb`)

**Issue:** CR-01's root cause was that PyJWT only *warns* on an empty HMAC key. The fix validates
at the `SecurityConfig` layer, but the low-level public API remains fail-open:

```python
tok = jwt.encode({"sub":"attacker","type":"access","exp":...}, "", algorithm="HS256")
verify_token(tok, "")   # -> {'sub': 'attacker', ...}  (accepted; only InsecureKeyLengthWarning)
```

`docs/integrations.md` documents the direct pattern `verify_token(token, SECRET)` with `SECRET`
sourced from env, so an app that follows that page (rather than `SecurityConfig`) with a missing
env var still accepts forged tokens. The guardrails now protect the recommended path only.

**Fix:** add an explicit fail-closed check in `verify_token`/`verify_refresh` (and optionally
`emit_token`/`emit_refresh`), e.g. `if not secret: raise AuthenticationError("secret vacío")`,
so the same class of misconfiguration is rejected at every public entry point.

### IN-04: New `__post_init__` validation branches are untested

**File:** `encino_orm/security/config.py:43,47`, `tests/test_security.py:263-270`

**Issue:** `test_config_rechaza_secret_vacio_fail_closed` covers empty `secret` and `None` `get_db`
only. The added `if not isinstance(self.secret, str)` and `if not self.algorithms` branches are
never exercised, and `security/config.py` has no per-module coverage floor in
`tools/ci/check_coverage_floors.py`, so CI cannot catch the gap.

**Fix:** extend the test with `SecurityConfig("SECRET", _noop_get_db, ())` and a non-`str` secret.

### IN-05: WR-03 fix has no regression test

**File:** `encino_orm/context.py:121-123`

**Issue:** The `is None` semantics are correct, but nothing asserts that a falsy
`ConnectionRegistry` is honored. A future refactor back to `registry or _registry` would regress
silently.

**Fix:** add a test using a `ConnectionRegistry` subclass with `__bool__` returning `False` and
assert `resolve_db(registry=...)` returns the passed registry's connection.

---

_Reviewed: 2026-09-19T07:26:55Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
