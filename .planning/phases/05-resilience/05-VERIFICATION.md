---
phase: 05-resilience
verified: 2026-09-19T06:15:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps: []
---

# Phase 5: Resilience Verification Report

**Phase Goal:** Connection loss is classified, handled once, and never silently duplicates a write. Direct (non-pooled) connections survive idle periods, and driver failures surface as library exceptions.
**Verified:** 2026-09-19T06:15:00Z
**Status:** passed
**Re-verification:** No — initial verification (no prior `05-VERIFICATION.md`)

**Method:** goal-backward verification at HEAD `3fee7bf` (one commit past the R2 review `4fb4ccb`). Read all four PLAN/SUMMARY files, both reviews (`05-REVIEW.md`, `05-REVIEW-R2.md`), and the actual source (`base.py`, `exceptions.py`, six adapters, `pool.py`, docs/CHANGELOG/pyproject). Ran the full suite with `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle` against live containers and independent behavioral spot-checks. SUMMARY claims were not treated as evidence.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each of the six adapters classifies a simulated disconnect as a disconnect error, and does not misclassify a lock/deadlock error (mutual exclusion). | ✓ VERIFIED | `Db.is_disconnect_error` hook + overrides in `sqlite.py:65`, `mysql.py:85` (MariaDB inherits), `postgresql.py:82`, `mssql.py:126`, `oracle.py:109`. `tests/test_resilience.py` 104 passed, incl. per-engine disconnect/lock pairs and mutual-exclusion asserts. Independent spot-check: all six → disconnect=True, lock=True, lock-as-disconnect=False. Real driver shapes (`pyodbc.Error("HY000", "...(596)")`, `oracledb DPY-4011`) pass `test_disconnect_con_driver_real_{mssql,oracle}`. |
| 2 | A disconnect **outside** a transaction reconnects once and the operation succeeds; the same disconnect **inside** a transaction raises instead of retrying (A2 policy: reads + pre-execution writes succeed; mid-statement write reconnects but re-raises). | ✓ VERIFIED | `Db._with_reconnect` (`base.py:319-381`) implements exact rules: single `_reconnect`, `in_transaction()` guard at :369, `pre_execution = isinstance(exc, OrmConnectionError)` at :371, re-execute only if `is_read or pre_execution`. Tests: `test_lectura_desconectada_fuera_de_tx_reconecta_una_vez` (connects=1, fetches=2), `test_escritura_pre_ejecucion_reconecta_y_ejecuta` (executes=2), `test_escritura_mid_statement_reconecta_pero_no_reejecuta` (raises, executes=1), `test_desconexion_dentro_de_tx_relanza_sin_reconectar` (connects=0). Independent real-SQLite check: dropped live handle → next read reconnected and returned the row; inside-tx fake raised `ConnectionLostError` with connects=0/closes=0. |
| 3 | Direct (non-pooled) connections survive an idle period via `pre_ping` and `max_connection_lifetime`. | ✓ VERIFIED | `Db.pre_ping`/`max_connection_lifetime` opt-in defaults (`base.py:55-56`), `_resilience_opts` (`:235`), `_should_recycle` via `time.monotonic()` (`:263`), `_maybe_recycle` hooked at `_with_reconnect` entry (`:361`); wired in all five drivers' `connect()` (`sqlite:94`, `mysql:120`, `postgresql:123`, `mssql:177`, `oracle:146`). 10 `TestResilienceLifetime` tests pass; independent real-SQLite file recycled on lifetime expiry and retained rows. Documented limitation on MSSQL/Oracle (see Residuals). |
| 4 | Driver exceptions are translated into a documented public library error taxonomy. | ✓ VERIFIED | `exceptions.py:9-30` (`ConnectionLostError(ConnectionError)`, `OperationalError(EncinoOrmError)`, `IntegrityError/ProgrammingError(QueryError)`), exported in `__init__.py` + `__all__`; single point `Db._translate_exception` (`base.py:165`) with lock short-circuit first, `_translate_error` hook per adapter; chaining `raise ... from exc` (`:307-317`). Documented in `docs/engines.md:159-233` and `CHANGELOG.md:234-262`. 42 `-k translate` tests pass. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `encino_orm/base.py` | `is_disconnect_error`, `_with_reconnect`, `_reconnect`, `_is_reconnectable`, `_maybe_recycle`, `_translate_exception`, `_translate_error` | ✓ VERIFIED | All present, substantive (docstrings + logic), wired by public wrappers. |
| `encino_orm/sqlite.py` | classifier + `_reconnect` rejecting `:memory:` + `_translate_error` | ✓ VERIFIED | `:memory:` raises `ConnectionLostError`; file DB reconnects. |
| `encino_orm/mysql.py` | classifier + state + `_translate_error` | ✓ VERIFIED | errnos 2006/2013/2055 + `InterfaceError` + raw socket errors; 1213/1205 excluded. |
| `encino_orm/mariadb.py` | inherits MySQL classification | ✓ VERIFIED | No override; `MariadbDb.is_disconnect_error is MysqlDb.is_disconnect_error` confirmed. |
| `encino_orm/postgresql.py` | asyncpg type classifier + `_translate_error` | ✓ VERIFIED | `InvalidCachedStatementError` excluded from both. |
| `encino_orm/mssql.py` | SQLSTATE classifier + real `pyodbc` shape + `_translate_error` | ✓ VERIFIED | `_native_code` extracts trailing `(NNNN)`; whole `23000` class → `IntegrityError`; N-01 `HYT00` fix present. |
| `encino_orm/oracle.py` | code/full_code classifier + `_translate_error` | ✓ VERIFIED | DPY-4011 via `full_code` (code==0); ORA list extended. |
| `encino_orm/exceptions.py` | four new taxonomy classes | ✓ VERIFIED | Hierarchy as documented; `OperationalError` intentionally not `QueryError` (WR-05). |
| `encino_orm/__init__.py` | barrel + `__all__` exports | ✓ VERIFIED | All four names exported. |
| `tests/_resilience_helpers.py` | real-shape builders + `FakeResilientDb` | ✓ VERIFIED | `_MssqlExc` uses real `(sqlstate, "msg (code)")`; deterministic hand doubles, no `sleep`/`unittest.mock`. |
| `tests/test_resilience.py` | RESL-01…04 blocks | ✓ VERIFIED | 104 tests, substantive assertions (connects/closes/executes counters). |
| `docs/engines.md`, `CHANGELOG.md`, `pyproject.toml` | documentation + ratchet | ✓ VERIFIED | Taxonomy, chaining, pre_ping/lifetime, `:memory:`, N-04/WR-06 caveats documented; ratchet shrank by base/oracle/mysql/mssql; `pool` residual documented. |

`gsd-sdk query verify.artifacts` → 05-01: 8/8, 05-02: 8/8, 05-03: 8/8, 05-04: 7/9. The two 05-04 "failures" are tool artifacts, not code gaps: the brace path `encino_orm/{sqlite,...}.py` is not a real path (all five files contain `_translate_error`), and `pyproject.toml` "missing pattern `encino_orm.base`" is the intended ratchet shrink.

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `Db.execute`/`execute_insert`/`fetch_*` | `Db._with_reconnect` | public wrappers with `is_read` flag | ✓ WIRED | `base.py:410-446`. |
| `Db._with_reconnect` | `Db._maybe_recycle` | proactive check before `try` | ✓ WIRED | `base.py:360-363`. |
| `Db._with_reconnect` | `Db._is_reconnectable` / `in_transaction` / `_reconnect` | classify → guard → reconnect once | ✓ WIRED | `base.py:367-375`. |
| `Db._with_reconnect` | `Db._translate_exception` | every re-raise translated + chained | ✓ WIRED | `base.py:307-317, 362-381`. |
| `Db._translate_exception` | `Db.is_lock_error` | lock short-circuit (identity) | ✓ WIRED | `base.py:182-183`. |
| adapter `connect()` | `Db._resilience_opts` | pop opts before driver kwargs | ✓ WIRED | all five adapters. |
| adapter `is_disconnect_error` | `is_lock_error` / disjoint signals | mutual exclusion | ✓ WIRED | MSSQL explicit call; others disjoint by errno/code/type. |
| `PoolDb._run` | adapter public wrapper | `getattr(handle.driver, method)` | ✓ WIRED | `pool.py:461,464,493`; `pool.py` untouched; `test_pool_no_reconecta_dos_veces` passes. |
| `__init__` | `exceptions.py` | barrel + `__all__` | ✓ WIRED | Confirmed. |

`gsd-sdk query verify.key-links` returned false negatives ("Source file not found") because it cannot parse the `file::symbol` + brace syntax; manual verification above confirms every link.

### Data-Flow Trace (Level 4)

Not a UI/data-rendering phase. The relevant dynamic flows were traced to their sources:

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `is_disconnect_error` (all adapters) | driver exception type/errno/SQLSTATE/code | real driver exception objects (tests use real-shape `args`) | Yes | ✓ FLOWING |
| `_translate_exception` | translated library exception | classification + adapter `_translate_error` | Yes | ✓ FLOWING |
| `_should_recycle` | connection age | `time.monotonic() - _connected_at` (set in real `connect()`) | Yes | ✓ FLOWING |
| `_reconnect` | new live connection | `connect(**self._connect_kwargs)` (original kwargs) | Yes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite incl. live MSSQL+Oracle | `ENCINO_ORM_REQUIRE_ENGINES=mssql,oracle uv run pytest -q` | 1024 passed (10 snapshots) | ✓ PASS |
| Resilience block | `uv run pytest tests/test_resilience.py -q` | 104 passed | ✓ PASS |
| Real-driver classification | `uv run pytest tests/test_resilience.py -k real -v` | 2 passed (not skipped) | ✓ PASS |
| Six-adapter disconnect vs lock | `uv run python -c ...` spot-check | all 6 OK; MariaDB inherits MySQL | ✓ PASS |
| HYT00 generic → OperationalError | `_translate_exception(mssql_timeout_generic())` | `OperationalError` | ✓ PASS |
| Outside-tx real SQLite reconnect | destroy live handle, then `fetch_one` | returned row, `_connected_at` set | ✓ PASS |
| Inside-tx disconnect | `FakeResilientDb(tx=True, fail_first=1)` | raised `ConnectionLostError`, connects=0/closes=0 | ✓ PASS |
| Real SQLite lifetime recycle | age `_connected_at`, `fetch_one` | reconnected, rows preserved | ✓ PASS |
| Quality gates | `uv run mypy encino_orm`; `uv run ruff check encino_orm tests` | mypy clean (60 files); ruff clean | ✓ PASS |

### Probe Execution

SKIPPED — no phase-declared or conventional `scripts/*/tests/probe-*.sh` probes exist for this library phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| RESL-01 | 05-01 | Each adapter classifies disconnect errors via `is_disconnect_error` | ✓ SATISFIED | Hook + five overrides (MariaDB inherits); mutual-exclusion tests pass; real driver shapes pass. |
| RESL-02 | 05-02 | `_with_reconnect` reconnects once and only outside a transaction | ✓ SATISFIED | Template method + tx guard + A2 policy; deterministic tests; real SQLite reconnect. |
| RESL-03 | 05-03 | Direct connections support `pre_ping` and `max_connection_lifetime` | ✓ SATISFIED | Class attrs, opt-in pop, monotonic age, lazy hook; 10 tests + real SQLite. |
| RESL-04 | 05-04 | Public error taxonomy translating driver exceptions | ✓ SATISFIED | Four classes, barrel exports, single translation point, per-adapter hooks, docs/CHANGELOG. |

No orphaned requirements: REQUIREMENTS.md maps only RESL-01…04 to Phase 5 and each is claimed by exactly one plan (`requirements:` frontmatter).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX` debt markers in any phase-modified file | — | None |
| — | — | No empty/stub returns in production paths; `NotImplementedError` in `Db._execute`/`_fetch_*` is the documented abstract-adapter seam | ℹ️ Info | None |
| — | — | `_translate_error` default → `OperationalError` is a deliberate driver-agnostic fallback, not a stub | ℹ️ Info | None |

### Intentional Deviations from PLAN Frontmatter (documented, intent preserved)

| Plan must-have | Implementation | Why / Evidence |
| -------------- | -------------- | -------------- |
| `_with_reconnect(fn, *, retry)` | renamed to `is_read` | IN-02 fix (name shadowed `retry()` method); `base.py:319`; all call sites use `is_read=`. |
| `OperationalError(QueryError)` | `OperationalError(EncinoOrmError)` | WR-05 fix so infrastructure failures map to HTTP 500, not 400; documented `docs/engines.md:197-199`, `CHANGELOG.md`, `tests/test_base.py:48-60`. |

These do not reduce roadmap scope; the RESL-04 requirement ("public taxonomy that translates driver exceptions") is fully met.

### Known Limitations / Residuals (WARNING — documented, fail-safe, not blockers)

| # | Residual | Evidence | Assessment |
|---|----------|----------|------------|
| R1 | MSSQL `HY000` mid-query (KILL) detection relies on English message markers; localized servers may not match. | `mssql.py:146-155`; documented `docs/engines.md:230-233`; acknowledged `05-REVIEW-R2` WR-06. | WARNING. `08xxx` disconnect class is SQLSTATE-based and language-independent; only the generic `HY000` KILL path is affected. |
| R2 | MSSQL (and Oracle after a write) `in_transaction()` is conservative, so `pre_ping`/`max_connection_lifetime` may be deferred (N-04). On MSSQL `_fetch_*` set `_in_tx=True`, so a direct connection after any statement reports in-transaction until `commit()`. | `mssql.py:368,401,423,438,458`; `oracle.py:329,365` (reads do not set it); guard `base.py:299-300`; documented `docs/engines.md:223-229`. | WARNING. Fails safe (raises, never silently duplicates). Criterion 3 is met on SQLite/MySQL/PostgreSQL and by the adapter-agnostic mechanism; this is a documented real-world limitation on 2 of 6 engines. |
| R3 | A failed `_reconnect()` leaves `_connected_at=None`, so no further auto-recovery is attempted; subsequent ops raise a library `ConnectionError`. | `_reconnect` (`base.py:224-231`) → `close()` clears `_connected_at`, then failing `connect()`; `_is_reconnectable` requires `_connected_at is not None`. | WARNING (low). Edge case after a failed reconnect; fails safe. Not explicitly documented in docs/CHANGELOG. |
| R4 | `pool.py` excluded from the mypy ratchet (5 residual typing errors). | `pyproject.toml:249-256`; explicitly a Phase 4 residual, out of Phase 5 scope. | WARNING. Pre-existing, documented. |
| R5 | No per-module coverage floor (global `fail_under = 82`). | `pyproject.toml:114`; Phase 1 mechanism, per-dialect floors deferred. | WARNING. Pre-existing, out of Phase 5 scope. |

### Human Verification Required

None required by the four success criteria: criterion 1 is explicitly scoped to *simulated* disconnects, and criteria 2–4 are verified programmatically (deterministic doubles + real SQLite) with live-engine integration tests green. Optional UAT (not blocking): end-to-end disconnect/idle survival against live MSSQL/Oracle via destructive session kill, which would exercise R1/R2 in production conditions.

### Gaps Summary

No gaps. All four roadmap success criteria are observably true in the codebase at HEAD `3fee7bf`, backed by real source (not stubs), wired end-to-end, and covered by 104 phase tests plus a 1024-test full run with required MSSQL and Oracle engines. The five residuals above are documented, fail-safe limitations (R1/R2 explicitly acknowledged by the phase's own docs and the pre-supplied residual list); none causes a must-have truth to fail, and none can silently duplicate a write — the phase's core safety property.

---

_Verified: 2026-09-19T06:15:00Z_
_Verifier: the agent (gsd-verifier)_
