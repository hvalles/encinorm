# Project Research Summary

**Project:** `encino_orm` — production-hardening milestone (0.2.6 → 0.3.0)
**Domain:** Async multi-engine Python ORM library (brownfield hardening)
**Researched:** 2026-09-17
**Confidence:** HIGH

## Executive Summary

`encino_orm` is not a prototype missing features — it is a broad, working library (6 engines, CRUD,
relations, migrations, cache, REST/GraphQL/RBAC) that is missing the **reliability, security, and
operability contract** production users assume an ORM already honors. All four research streams
converge on the same conclusion: **0.3.0 is a correctness release, not a feature release.** The
library is not behind competitors on API surface; it is behind on hardened failure semantics
(reset-on-return, disconnect classification, pre-ping, lifecycle verbs, dialect parity). Nearly every
P1 item is a *guarantee* to be established, not a capability to be added.

The recommended approach is a strictly ordered, 8-phase hardening campaign built on a hard
dependency chain: **CI safety net first (P1) → shared dialect seam (P2) → data correctness (P3,
parallel) → pool correctness (P4) → resilience (P5) → config/optional-layer hygiene (P6) →
performance (P7) → release (P8).** The single most important structural insight from architecture
research is that the pool bugs are **state in the wrong layer**: `_last_id`, transaction state, and
connection health are per-connection concerns currently stored on the *pool* or discarded.
Introducing a `PooledConnection` handle plus reserve-before-await admission fixes the `acquire()`
race, `last_id` cross-talk, and implicit-commit in one architectural move instead of three patches.

The dominant risk is not "the fix won't work" — it is **"the fix works, tests go green, and the
library is less trustworthy than before."** Three specific traps are decisive. First, **green CI that
verifies nothing**: four of six engines silently `pytest.skip` today, which is the root cause of the
`COUNT(*)` bug. Second, **the pool fix can deadlock or silently discard writes**: a lock around the
whole `acquire()` deadlocks, and flipping release-from-commit to release-from-rollback naively turns
every standalone `pool.execute(INSERT)` into a silent data-loss bug. Third, **0.3.0 breaks reach users
automatically**: `>=0.2.6` specifiers auto-upgrade, `release.yml` bypasses all new gates, and PyPI is
immutable. Mitigation is procedural as much as technical: required-engine CI switches, a
deprecation release (0.2.7) + release candidate (0.3.0rc1), and characterization tests written
*before* the pool is touched.

## Key Findings

### Recommended Stack

This milestone adds **no runtime dependencies**. It is entirely about the quality gate, CI, and
release toolchain. The single hardest constraint is **Python 3.10** (`requires-python = ">=3.10"`,
local venv CPython 3.10.18) — this rules out `asyncio.Barrier`, `asyncio.timeout`, `TaskGroup`, and
`except*` in library code *and tests*, which eliminates the most commonly recommended
concurrency-testing primitives.

**Core technologies:**
- **uv `0.12.15`** — package/lock management, plus new `uv audit` (OSV), `uv check`, `uv format`.
  Local 0.8.22 lacks these; **upgrade is a hard prerequisite** for the audit gate.
- **ruff `0.16.8`** — lint + format; replaces flake8/black/isort/pyupgrade/bandit. Its `ASYNC`
  (flake8-async) and `RUF006` (dangling-task) rules target exactly the pool bug class here; `S608`
  covers hardcoded SQL.
- **mypy `2.3.1`** — the only checker with an official pydantic v2 plugin, essential for a library
  whose public API *is* pydantic models. `py.typed` is currently **missing** (PEP 561 blocker).
- **pytest-cov `7.1.0` / coverage `7.16.1`** — needs `parallel = true` + `coverage combine` for the
  per-engine job topology. Do **not** chase a single global `--cov-fail-under`.
- **pytest-asyncio `1.4.0`** — already in use, but config is incomplete and emits a warning
  (`asyncio_default_fixture_loop_scope` must be set explicitly).
- **pytest-codspeed `5.0.3`** — the only benchmark plugin with a real CI regression service;
  backward-compatible with pytest-benchmark. `simulation` mode is far less flaky than wall-clock.
- **testcontainers `4.15.0`** — identical engine provisioning on Windows dev and Linux CI, driven
  from Python. `[oracle-free]` uses `oracledb` (driver-version bump risk — see Gaps).
- **syrupy `6.1.1`** — **highest-leverage idea in STACK.md**: snapshot generated SQL per dialect and
  assert against committed `.ambr` files. Catches dialect drift *without a live database*, on the
  always-on SQLite job.

**Deliberately avoided:** standalone `bandit` (duplicates ruff `S`), `black`/`isort`/`flake8`,
`pyright` as primary gate (no pydantic plugin), `ty` as a gate (pre-1.0, `0.0.82`), `asv`,
`anyio`'s pytest plugin, `safety`, `python-semantic-release` in this milestone,
`pytest-xdist` for concurrency tests (separate processes cannot observe in-process races), and
`asyncio.Barrier`/`timeout`/`TaskGroup` (3.11+).

### Expected Features

This is brownfield: "MVP" means **what 0.3.0 must ship to be credibly production-usable**, not
"minimum to validate an idea." 39 table-stakes items (TS-1…TS-39) were identified, plus 9
differentiators and 15 explicit anti-features.

**Must have (table stakes, P1 — the 0.3.0 scope):**
- **Correctness (the reason for the milestone):** TS-10 dialect-correct `count`/`paginate`/`list_tables`
  (`AS n` alias); TS-11 atomic-or-reconciled migrations; TS-12 rollback bookkeeping so re-apply works;
  TS-13 `CachedModel` write-invalidation (store-then-invalidate); TS-30 regression test per fix +
  `CHANGELOG.md`.
- **Concurrency/pool:** TS-1 race-free checkout (never exceeds `max_size`); TS-2 release = rollback
  (**the milestone's key breaking change**); TS-8 per-connection/task `last_id`; TS-9 deterministic
  `close()`/dispose; TS-3+TS-4 health check + classified reconnect for direct connections; TS-29
  concurrency/stress tests (the proof for all of the above).
- **Security:** TS-18 identifier allow-list validation in all six dialect builders; TS-20 validate
  introspection-derived identifiers before `ALTER TABLE`; TS-21 explicit secret/config injection over
  mutable globals; TS-22 documented trust boundaries for `Filter.raw`/`Query`/`db.fn.*`; TS-23
  dev-only credentials marked + OIDC trusted publishing; TS-24 dependency/vulnerability scanning.
- **Quality gates & CI:** TS-25 ruff config + gate; TS-26 mypy (non-strict, ratcheting); TS-27
  pytest-cov + threshold; TS-28 multi-engine CI matrix (MariaDB + Redis minimum); TS-16 error taxonomy.
- **Performance:** TS-37 cached placeholder translation *(see correction below — defer)*; TS-38
  batched `copy_table`; TS-39 benchmark suite with numeric targets; TS-6 lazy idle reaping.

**Should have (competitive, 0.3.x — P2):** TS-31 automatic query instrumentation hook; TS-32 OTel
stable semantic conventions; TS-33 PII-safe logging; TS-34 bounded metric buffers; TS-35 pool metrics
with idle count; TS-36 slow-query logging; TS-5 connection recycling; TS-17 isolation-level config;
TS-15 bulk-write atomicity docs; D-9 published per-engine reliability contract.

**Defer (0.4+ — P3):** D-1 full six-engine conformance harness; D-2 cache-as-differentiator;
D-3 OTel as headline; D-4 self-healing pool as product promise; D-6 MySQL/Oracle migration
reconciliation; new engines (AF-1); Alembic-style autogenerate (AF-4).

**Critical anti-features to refuse:** AF-5 blind retry of arbitrary writes (duplicates data);
AF-6 double-pooling a driver-native pool; AF-7 mandatory background reaper daemon; AF-9 distributed
cache coherence; AF-11 catch-all `except Exception` resilience wrappers; AF-12 extending
`exec()`-generated REST/GraphQL codegen; AF-13 100% coverage as a stated goal; AF-15 default-on
read caching.

### Architecture Approach

Brownfield hardening, **not** a redesign. The layered architecture (`Db` ABC → 6 adapters →
Model/Filter/QueryBuilder → optional lazy layers) is sound and must be preserved; every
recommendation is scoped to *where a concern belongs* inside existing layers so fixes do not regress
the import-lazy contract, the `contextvars` state model, or adapter-localized dialect behavior.

**Major components:**
1. **`PooledConnection` (new handle in `pool.py`)** — the unit of per-connection state: driver
   handle, `last_id`, timestamps, generation, in-use flag. Fixes `acquire()` races, `last_id`
   cross-talk, and implicit-commit in one move.
2. **`PoolDb` facade (reworked)** — owns admission, reset, reaping, close semantics; reserves the
   capacity slot **under lock before** `await connect()`, and never holds the lock across the await.
3. **`dialects/builders.py` + `dialects/strategies.py` (new seam inside core)** — one shared
   `build_insert/update/delete` with `_check_identifier` on every table/column; adapters override
   only small hooks (`_prepare`, `_conflict_clause`, `is_lock_error`, `is_disconnect_error`). This is
   the single choke point that fixes identifier validation for all six engines at once.
4. **`Query` compiled-SQL cache** — memoize native-placeholder SQL per dialect on the instance.
5. **`ConnectionRegistry` + `SecurityConfig`** — injectable objects replacing module-level mutable
   `_default_db` / `SECRET` / `GET_DB`, with deprecated backward-compatible shims.
6. **Two distinct recovery paths** — `Db.retry` (lock/deadlock, safe to re-run) kept separate from
   `Db._with_reconnect` (connection loss, reconnect once, **only when `in_transaction()` is false**).

### Critical Pitfalls

1. **Green CI that verifies nothing** — four of six engines call `pytest.skip` on connection
   failure; a skipped suite is a passing suite. This is the direct root cause of the `COUNT(*)` bug.
   *Avoid:* an explicit `ENCINO_ORM_REQUIRE_ENGINES` switch that makes `pytest.fail` (not skip) in
   CI, catch only specific driver exception types, and add a JUnit-XML post-run gate failing on
   `skipped > 0`; add `--strict-markers` and `xfail_strict = true`.
2. **Pool race "fix" deadlocks / release-policy "fix" silently discards writes** — locking all of
   `acquire()` deadlocks against `release()`; naively flipping commit→rollback makes standalone
   `pool.execute(INSERT)` a silent no-op. *Avoid:* reserve-before-await (never lock the queue wait);
   sequence the reset change as (i) make `execute`/`_run` commit-or-rollback explicitly, (ii) then
   rollback leftovers with a `DeprecationWarning`, (iii) keep `TestPoolAutocommit` passing; add
   `reset_on_return` with the old behavior available.
3. **`last_id()` cannot be fixed by bookkeeping alone** — moving `_last_id` per-connection is
   necessary but **not sufficient**. *Avoid:* capture the id **inside the same operation as the
   insert** — PostgreSQL/Oracle `RETURNING`, MySQL/MariaDB immediate `cursor.lastrowid`, SQLite
   immediate `last_insert_rowid()`, MSSQL `SCOPE_IDENTITY()`/`OUTPUT INSERTED` — and deprecate
   post-hoc `last_id()`. Add a concurrent-insert test per engine.
4. **Identifier validation that breaks legitimate use or misses dialects** — the regex is duplicated
   in six modules; rejecting `schema.table`/quoted/non-ASCII names pushes users to hand-build SQL
   (less safe); validation without dialect-aware quoting addresses the wrong object (Oracle
   uppercases, PostgreSQL lowercases, MySQL fold is config-dependent). *Avoid:* centralize first as
   a **pure refactor with zero behavior change** (separate commit), then add validation as its own
   bisectable commit; test the *rejection* with a spy connection asserting `ValueError` before the
   driver is called.
5. **0.3.0 breaking changes reach users automatically with no deprecation path** — `>=0.2.6`
   auto-upgrades; `release.yml` does not depend on `ci.yml` so no gate actually blocks publish; PyPI
   is immutable. *Avoid:* ship a **0.2.7 deprecation release** with runtime warnings, publish
   **0.3.0rc1** before 0.3.0, make release `needs:` CI, add a protected `pypi` environment, and
   document `~=0.2.6` pinning.
6. **Benchmarks that measure noise or the wrong thing** — see the tooling correction below.
   *Avoid:* profile before optimizing; benchmark per engine; disable debug logging in fixtures;
   report median/p95/σ; make the benchmark a *gate* that a deliberate 2× regression fails.

### Corrections Surfaced by Cross-Research

Two cross-cutting corrections must be carried into the roadmap explicitly:

- **CORRECTION (ARCHITECTURE.md is wrong): PostgreSQL `lastval()` is _session-scoped_, not
  transaction-scoped.** `ARCHITECTURE.md` (External Services table) describes it as
  "transaction-scoped." It returns the last sequence value obtained by `nextval` **in the current
  session**, regardless of transaction boundaries. Consequences: outside a transaction a shared
  pooled connection can return another task's id with no error; inside a transaction it is still
  wrong if any trigger inserts into another table with its own sequence; if the INSERT touched no
  sequence it returns stale data or raises `ObjectNotInPrerequisiteState`. **The only correct answer
  on PostgreSQL is `INSERT ... RETURNING <pk>`**, which changes `Db.insert`'s return contract (an
  API change). The roadmapper must not build on the false premise.
- **CORRECTION (benchmarking capability): neither `pytest-benchmark` nor `pytest-codspeed` measures
  coroutines.** Verified by reading plugin source: pytest-benchmark 5.3.0 has zero occurrences of
  `async`/`asyncio`/`coroutine`/`await` in README or changelog; pytest-codspeed's
  `BenchmarkFixture.__call__` is literally `return target(*args, **kwargs)`, so passing a coroutine
  function returns an un-awaited coroutine and "benchmarks" only coroutine-object creation. **The
  stated performance goals are CPU/sync-bound, so this is largely self-inflicted** — `copy_table`
  batching, placeholder translation, and the idle-reaper policy are deterministic synchronous code
  paths. Benchmark the **sync units directly** (SQL build, placeholder translation, batch sizing).
  For end-to-end async latency, write a hand-rolled `time.perf_counter` harness inside an async test
  with a loose budget assertion. Do **not** build a gate on `@pytest.mark.benchmark` over an async
  test until empirically validated (MEDIUM confidence that the awaited body falls inside the
  measured region; it also includes loop setup/teardown).

## Implications for Roadmap

Based on combined research, the suggested phase structure is **8 phases** with a hard ordering
chain. Phase IDs below align with `ARCHITECTURE.md` Levels and the `PITFALLS.md` mapping table;
note that `PITFALLS.md` references P1–P4 and P6–P8 but skips P5, so **P5 (Resilience) is inferred
from `ARCHITECTURE.md` Level 3** and should be confirmed during roadmap creation.

### Phase 1: Safety Net — CI Gates & Test Infrastructure (Level 0)
**Rationale:** The cheapest, highest-leverage interventions in the entire milestone, and the
prerequisite for every later "fix verified" claim. Without lint/type/coverage and a real
multi-engine signal, a refactor of this size has no safety net.
**Delivers:** `ruff` config + blocking CI job (land in 3 isolated mechanical commits: format-only in
`.git-blame-ignore-revs`, then narrow `ruff check` rule set, then mypy); mypy non-strict with
`--warn-unused-ignores` + `py.typed` marker; pytest-cov with `parallel = true` and a **low ratchet
floor** (not a high global number); per-engine `COVERAGE_FILE` + `coverage combine`; required-engine
switch (`ENCINO_ORM_REQUIRE_ENGINES`) with JUnit-XML `skipped > 0` gate; pytest config hardening
(`--strict-markers`, `xfail_strict`, both loop scopes, `filterwarnings = ["error"]`, markers);
characterization tests for pool invariants **before** any pool refactor; dependency scanning
(`uv lock --check`, `uv audit`, `pip-audit`); `uv self update` to 0.12.15; `__version__` in
`encino_orm/__init__.py`; release-gate wiring (`release.yml` `needs:` CI).
**Addresses:** TS-25, TS-26, TS-27, TS-28 (partial), TS-24, TS-30 (partial)
**Avoids:** Pitfall 1 (green CI verifying nothing), Pitfall 2 (coverage masking dialect paths),
Pitfall 4 (refactoring against fakes), Pitfall 12 (big-bang gates), Pitfall 15 (loop-scope
ambiguity), Pitfall 18 (dependency bounds), Pitfall 20–21, Pitfall 24 (broad `pytest.raises`).
**Exit criterion:** removing a required engine's service makes its CI job **fail**, and deleting
`tests/test_postgresql.py` makes the per-dialect coverage job fail.

### Phase 2: Dialect Seam & Engine Parity (Level 1)
**Rationale:** A new seam *inside* the core, not a new layer. It is the single choke point that
unblocks identifier validation for all six engines, the `sync_schema` fix, and `copy_table`
batching. Must precede the pool and transfer work or the same logic gets duplicated again.
**Delivers:** `dialects/builders.py` + `strategies.py`; centralized `_IDENTIFIER_RE` /
`_check_identifier` (**pure refactor, zero behavior change, its own commit**) followed by validation
as a separate bisectable commit; `Query` correctness (replace the `{0}` sentinel, make `Query`
immutable/hashable, fix `rebind`); dialect SQL snapshots via **syrupy** on the always-on SQLite job;
per-dialect `MAX_PARAMS`/`MAX_ROWS` constants; full multi-engine CI matrix (MariaDB + Redis cheap;
MSSQL/Oracle in a separate single-Python-version job); per-engine integration tests for
`count`/`paginate`/`list_tables`/`sync_schema`/`last_id`.
**Addresses:** TS-18, TS-20, TS-28, TS-10 (proof), TS-19 (regression guard)
**Avoids:** Pitfall 10 (validation that breaks use or misses dialects), Pitfall 19 (`Query` sentinel),
Pitfall 7 (batch constants land here), Pitfall 2 (per-engine tests make coverage meaningful).
**Research flag:** Needs research — `syrupy` dialect snapshot adoption and the `testcontainers`
Oracle/MSSQL topology are design recommendations, not documented consensus.

### Phase 3: Data Correctness (parallel to Phase 2 — different modules)
**Rationale:** Touches `migration.py`, `model/cached.py`, `model/cache_backend.py` — no file overlap
with Phase 2, so it can run in parallel. Must land before release so ledger semantics are settled.
**Delivers:** per-dialect `transactional_ddl: bool` (True for PostgreSQL/SQLite/SQL Server; False
for MySQL/MariaDB/Oracle) with record-intent-first + reconcile-on-startup for the False branch;
`rollback_migration` ledger fix (delete `{name}`, not just insert `{name}:down`); `CachedModel`
write-invalidation (store-then-invalidate, override both `update` **and** `delete`); bounded
`MemoryCacheBackend` (or document as dev/test-only).
**Addresses:** TS-11, TS-12, TS-13, TS-34 (cache portion)
**Avoids:** Pitfall 8 (security-theater atomic migrations), Pitfall 17 (unbounded caches).
**Research flag:** Standard patterns once `transactional_ddl` branching is understood; no deeper
research needed.

### Phase 4: Pool Correctness & Concurrency (Level 2) — HIGHEST RISK
**Rationale:** The highest-severity bug class in the library and the milestone's core reliability
phase. TS-1, TS-2, TS-8, TS-9 are **one unit of work** — they all mutate the same pool bookkeeping
and the same release path; splitting them invites conflicting fixes. **Must not be split across
releases.**
**Delivers:** `PooledConnection` handle; reserve-before-await `acquire()`; per-connection +
task-scoped `last_id` with ids captured **inside the insert** (`RETURNING`/`SCOPE_IDENTITY`/
immediate `lastrowid`); `reset_on_release="rollback"` default with configurable commit, warning, and
CHANGELOG entry; generation counter + lazy idle reaper (no background daemon); safe idempotent
`close()` that never closes a checked-out connection under the caller; task-ownership binding on the
`_current_connection` contextvar; deterministic 3.10-compatible concurrency tests (hand-rolled
`asyncio.Event` barrier, never `asyncio.Barrier`/`TaskGroup`) + `pytest-timeout` with the **signal**
method; `pytest-repeat` stress variant behind a marker.
**Addresses:** TS-1, TS-2, TS-8, TS-9, TS-29, TS-14 (regression guard), D-8
**Avoids:** Pitfall 3 (deadlock / silent autocommit removal), Pitfall 4 (private-state tests),
Pitfall 5 (contextvars leaking into child tasks), Pitfall 6 (session-scoped `lastval()`),
Pitfall 14 (nondeterministic concurrency tests).
**Research flag:** Needs research — the `PooledConnection` refactor shape and the `last_id`
API-contract change are design decisions with breaking-change implications.

### Phase 5: Resilience — Disconnect Handling (Level 3) *(inferred — not labeled in PITFALLS.md)*
**Rationale:** A distinct failure domain (network loss vs. concurrency) and it **depends on Phase 4**
— reconnect/health needs the `PooledConnection` handle and the generation counter to exist. Cannot
start earlier.
**Delivers:** `is_disconnect_error` per adapter; `Db._with_reconnect` template method that reconnects
**once** and only when `in_transaction()` is false; `pre_ping` + `max_connection_lifetime` policy;
`TS-16` public error taxonomy (driver exceptions → library exceptions) — which is also the
prerequisite for Phase 6's observability work.
**Addresses:** TS-3, TS-4, TS-16, TS-5
**Avoids:** Anti-Pattern 4 / AF-5 (retrying a disconnect inside an open transaction → duplicate
writes).
**Research flag:** Needs research — the `TS-16` taxonomy boundary and per-driver disconnect
classification need API-level research per adapter.

### Phase 6: Config & Optional-Layer Hygiene (Levels 4 + 5)
**Rationale:** Both levels are about removing indirection (`exec`, globals) rather than runtime
correctness, and Level 4 must precede Level 5 so `create_crud`/`build_schema` accept config at the
same time their handler generation is rewritten — signatures change once.
**Delivers:** `ConnectionRegistry` replacing `_default_db` with deprecated shims; `SecurityConfig`
frozen dataclass + guard factories with deprecated globals; `exec()` → closures/`__signature__`
conversion as a **behavior-preserving refactor** with an OpenAPI snapshot test before/after; GraphQL
per-build namespace (stop mutating the module namespace); trust-boundary docs for
`Filter.raw`/`Query`/`db.fn.*`.
**Addresses:** TS-21, TS-22, AF-12 remediation
**Avoids:** Pitfall 13 (`exec()` removal changing the HTTP/GraphQL contract), Pitfall 16 (freezing
instead of removing secret globals).
**Research flag:** Needs research — the `__signature__` technique for FastAPI path params is a
community pattern (MEDIUM confidence), and GraphQL namespace isolation is explicitly untested.

### Phase 7: Performance & Benchmarks (Level 6)
**Rationale:** Depends on Level 1 (dialect constants) + Level 2 (pool). Correctness comes first;
these are throughput concerns. `TS-39` gates every performance claim.
**Delivers:** profiler output (`py-spy`/`cProfile`) **committed before any optimization**; benchmark
harness (warmup, ≥5 reps, median + p95 + σ, logging explicitly disabled); `copy_table` batching with
`batch_rows = min(MAX_PARAMS // n_columns, MAX_ROWS)` and array binding / `executemany` preferred
for Oracle/PostgreSQL; benchmarks as a **gate** that a deliberate 2× regression fails; bounded
`QueryTracer._latencies` via `deque(maxlen=N)`; `WeakKeyDictionary` for `_FIELD_ADAPTERS`.
**Addresses:** TS-38, TS-39, TS-34 (tracer), TS-37 (**deferred — see below**)
**Avoids:** Pitfall 7 (batch size exceeding dialect limits), Pitfall 11 (benchmark methodology),
Pitfall 17 (unbounded growth).
**Research flag:** Needs research — per-dialect parameter ceilings (MSSQL 2100, Oracle 1000-element
`IN`, asyncpg ~32767) are documented but not empirically verified; measure before sizing batches.

### Phase 8: Release 0.3.0
**Rationale:** All breaking-change semantics must be settled before this phase; the deprecation path
must be *shipped*, not planned.
**Delivers:** **0.2.7 deprecation release** with runtime `DeprecationWarning`s for each 0.3.0 break
(implicit commit on release, unvalidated identifiers, mutable `SECRET`/`GET_DB`, post-hoc
`last_id()`); **0.3.0rc1** published before 0.3.0; release workflow gated on CI with a protected
`pypi` environment; OIDC trusted publishing (`uv publish` + `id-token: write`, no token — delete
`PYPI_API_TOKEN`); complete `CHANGELOG.md` enumerating every `### Changed`/`### Removed` with
old + new behavior; `MIGRATION-0.3.md` with before/after snippets; README pinning guidance
(`~=0.2.6`, not `>=`); dev-credentials header + `.env.example`; dead-link fix (`prompts/` is
gitignored); docs review.
**Addresses:** TS-23, TS-30, and every P1 item's user-facing contract.
**Avoids:** Pitfall 9 (breaks reaching users automatically), Pitfall 21–23, Pitfall 25.
**Research flag:** Standard patterns (SemVer + trusted publishing are well documented); skip
`--research-phase`.

### Phase Ordering Rationale

- **CI gates (P1) before everything** — without lint/type/coverage and a required-engine signal, a
  hardening refactor of this size has no safety net, and every later "fix verified" claim is
  unverifiable. This is the single most consequential ordering constraint.
- **Centralize-then-validate (P2)** — the `_IDENTIFIER_RE` centralization must be a separate
  zero-behavior-change commit *before* validation lands, or the security change is unbisectable and
  silently misses five of six dialects.
- **Pool work is one unit (P4)** — TS-1/TS-2/TS-8/TS-9 share the same release path; splitting them
  across phases invites conflicting fixes. Characterization tests (P1) must exist first.
- **Resilience (P5) after pool (P4)** — reconnect needs the `PooledConnection` handle and generation
  counter. The `TS-16` taxonomy gates observability (P2 in FEATURES terms).
- **Config (P6) is independent of P4/P5** — it can run in parallel, but Level 4 must precede Level 5
  so public signatures change once.
- **Performance (P7) last** — it depends on P2 (constants) and P4 (pool), and PROJECT.md forbids
  perceived improvements; benchmarks are the mechanism that makes P7 verifiable.
- **Release (P8) is procedural, not technical** — its entire value is sequencing (deprecation → rc →
  final) and gate wiring, which must precede the first breaking change, not follow it.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Dialect Seam):** syrupy snapshot adoption, testcontainers Oracle/MSSQL topology, and
  the `Query` immutability refactor shape are design recommendations without documented consensus.
- **Phase 4 (Pool Correctness):** the `PooledConnection` refactor and the `last_id` API-contract
  change are breaking-change design decisions. Also validate the `@pytest.mark.benchmark`-on-async
  question empirically if any async timing is attempted.
- **Phase 5 (Resilience):** per-driver disconnect classification requires adapter-level API research.
- **Phase 6 (Config Hygiene):** `__signature__` for FastAPI path params is a community pattern;
  GraphQL namespace isolation is explicitly untested.
- **Phase 7 (Performance):** empirical verification of per-dialect parameter ceilings before batch
  sizing.

Phases with standard patterns (skip `--research-phase`):
- **Phase 1 (Safety Net):** ruff/mypy/pytest-cov/uv configuration is exhaustively documented in
  STACK.md with version-verified config sketches.
- **Phase 3 (Data Correctness):** `transactional_ddl` branching and cache-aside invalidation follow
  Alembic and Microsoft's documented patterns.
- **Phase 8 (Release):** SemVer deprecation guidance and PyPI trusted publishing are official,
  stable, and fully sourced.

### Explicit Deferral: TS-37 (Placeholder Caching)

**The PITFALLS researcher recommends treating TS-37 as premature pending profiling.** Rationale:
a `re.sub` over a ~200-byte SQL string is on the order of a microsecond while a DB round-trip is on
the order of a millisecond — Amdahl's law puts the win at **<1%**. The real bottleneck is round-trips
(`copy_table`, TS-38), already identified. Additionally, `Query` is currently **mutable**
(`rebind()` rewrites `self.query`) and its placeholder detection is a fragile `{0}` sentinel, so a
cache keyed on identity breaks after `rebind` and a cache keyed on `sql_template` alone breaks with
different parameter sets. **Recommendation:** remove TS-37 from the 0.3.0 P1 scope; run `py-spy` on
a representative PostgreSQL workload in Phase 7 and re-open TS-37 **only if placeholder translation
appears in the top 5 hot paths.** Fix the `Query` correctness issues in Phase 2 regardless, since
they are independent bugs.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI JSON API / GitHub Releases API / installed tooling on 2026-09-17. The async-benchmarking limitation is HIGH (verified by reading plugin source). MEDIUM on concurrency-testing technique (no single standard tool exists) and MEDIUM on multi-engine CI topology (design recommendation, not documented consensus). |
| Features | HIGH | Grounded in official docs from SQLAlchemy 2.0, Django 5.2, asyncpg, Alembic, OTel semconv, OWASP, Microsoft cache-aside, plus direct repo inspection. Competitor analysis read from peer docs. |
| Architecture | HIGH on pool/transaction/lifecycle patterns (verified against SQLAlchemy 2.0 and asyncpg authoritative docs); MEDIUM on DI refactor shape and `exec()` replacement (design recommendations for this specific codebase). |
| Pitfalls | HIGH | All code-level claims verified by reading the repo; async/CI/coverage/SemVer/DDL claims verified against official docs. Flagged MEDIUM items (SQL Server 2100-param limit, asyncpg ~32767 ceiling, GitHub runner memory for 6 containers, container readiness times) need empirical validation. |

**Overall confidence:** HIGH

### Gaps to Address

- **`lastval()` correction must propagate:** ARCHITECTURE.md states PostgreSQL `lastval()` is
  transaction-scoped. It is **session-scoped**. Correct ARCHITECTURE.md before the roadmap builds on
  it, and design `last_id` around `RETURNING`, not `lastval()` bookkeeping.
- **Benchmark tooling gap:** neither pytest-benchmark nor pytest-codspeed measures coroutines.
  Benchmark sync units directly; for async end-to-end timing write a `time.perf_counter` harness.
  Do not build a gate on `@pytest.mark.benchmark` over an async test until empirically validated.
- **TS-37 deferral:** treat placeholder caching as premature pending profiling (<1% expected win).
- **CodSpeed licensing unverified:** confirm `hvalles/encinorm` is public (then free) or budget for
  it. Fallback: committed `pytest-benchmark --benchmark-json` baseline with
  `--benchmark-compare-fail=15%`.
- **`uv check` / `ty` stability unproven:** `0.0.82`, pre-1.0, experimental. Run once and compare its
  error set against mypy's; keep local-only if noisy.
- **`oracledb` major-version bump risk:** project pins `>=2.0`; `testcontainers[oracle-free]`
  requires `>=3` and PyPI shows `26.0.0`. Verify the Oracle adapter against the resolved version.
- **`testcontainers[mssql]` driver mismatch:** the extra pulls `pymssql` + `sqlalchemy` and
  `get_connection_url()` returns an `mssql+pymssql` URL — read host/port/password instead.
- **`pytest-randomly` interaction unknown:** `tests/conftest.py` installs a Windows event-loop policy
  at import time and ~507 tests likely have order dependencies. Triage before enabling as a gate.
- **No off-the-shelf asyncio race detector exists:** the plan prescribes *techniques*, not a library.
  If the hand-rolled barrier proves awkward on 3.10, `hypothesis`'s `RuleBasedStateMachine` is the
  strongest fallback.
- **Per-dialect parameter ceilings unverified:** MSSQL 2100, Oracle 1000-element `IN`, asyncpg
  ~32767. Measure empirically before sizing `copy_table` batches.
- **GitHub runner capacity:** confirm current runner memory/disk limits can host the designed
  container topology before committing to it.
- **`pydantic` lower-bound tightness:** `>=2.13.4` combined with `Annotated`-subclassing workarounds
  means a pydantic minor bump may break constraint construction. Add a minimum-supported-pydantic
  CI matrix entry.

## Sources

### Primary (HIGH confidence)
- SQLAlchemy 2.0 Connection Pooling — `reset_on_return` (default `"rollback"`), `pool_pre_ping`,
  `pool_recycle`, `pool_timeout`, disconnect invalidation, `Pool.recreate()`, mid-transaction drop
  caveat: https://docs.sqlalchemy.org/en/20/core/pooling.html
- asyncpg API + `Pool.release()` source — `max_inactive_connection_lifetime` (default 300 s),
  `max_queries`, `expire_connections()`, reset-on-release, `executemany` atomic since 0.22:
  https://magicstack.github.io/asyncpg/current/api/index.html
- Django 5.2 Databases — `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS`, `close_old_connections()`:
  https://docs.djangoproject.com/en/5.2/ref/databases/
- Alembic — per-dialect `transactional_ddl`, `begin_transaction()`, `batch_alter_table`:
  https://alembic.sqlalchemy.org/en/latest/api/runtime.html
- OpenTelemetry database client span semconv (stable) — `db.system.name`, `db.query.text`
  sanitization, `db.query.parameter.<key>` opt-in, `db.response.returned_rows`:
  https://opentelemetry.io/docs/specs/semconv/database/database-spans/
- OWASP SQL Injection Prevention — prepared statements (Option 1), allow-list validation for
  table/column names (Option 3): https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Microsoft Azure Architecture Center — Cache-Aside: update the store **before** invalidating:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside
- Semantic Versioning 2.0.0 — clause 4 (`0.y.z` MAY change) + deprecation FAQ: https://semver.org/
- MariaDB KB — SQL statements causing an implicit commit:
  https://mariadb.com/kb/en/sql-statements-that-cause-an-implicit-commit/
- coverage.py config — `[paths]`, `dynamic_context = test_function`, config-only `fail_under`:
  https://coverage.readthedocs.io/en/stable/config.html
- pytest-asyncio reference — `asyncio_default_fixture_loop_scope` warns when unset; `event_loop`
  fixture removed in 1.0: https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html
- Python asyncio sync primitives — `asyncio.Barrier` "Added in version 3.11":
  https://docs.python.org/3/library/asyncio-sync.html
- SQLite implementation limits — `SQLITE_MAX_VARIABLE_NUMBER` 999/32766,
  `SQLITE_MAX_COMPOUND_SELECT` 500: https://www.sqlite.org/limits.html
- uv CLI reference + package guide — `uv lock --check`, `uv audit` (OSV), `uv check` (ty),
  `uv build --no-sources`, trusted publishing: https://docs.astral.sh/uv/reference/cli/
- pypa/gh-action-pypi-publish `release/v1` — `master` sunset, `id-token: write`, attestations on by
  default, Linux-only: https://github.com/pypa/gh-action-pypi-publish
- PyPI Trusted Publishers — OIDC exchange, 15-minute project-scoped token:
  https://docs.pypi.org/trusted-publishers/
- mypy 2.0–2.3 release notes — `--local-partial-types` and `--strict-bytes` on by default,
  `--python-version 3.9` dropped, `--num-workers` parallel checking
- pytest-cov changelog — 7.0 dropped subprocess measurement, requires coverage ≥ 7.10.6
- testcontainers-python — `SqlServerContainer` defaults, `OracleFreeContainer` uses `oracledb>=3`:
  https://testcontainers-python.readthedocs.io/
- pytest-benchmark README + full CHANGELOG and pytest-codspeed plugin source — **zero async handling
  in either** (verified)
- ruff rules index via installed `ruff 0.16.8` — `ASYNC100`, `RUF006`, `S608`, `PT011`

### Repository Inspection (HIGH confidence)
- `encino_orm/pool.py`, `base.py`, `query.py`, `postgresql.py`, `sqlite.py`, `security/guard.py`,
  `migration.py`, `model/cached.py`, `model/cache_backend.py`, `observability.py`, `transfer.py`,
  `http/routes.py`, `graphql/schema.py`
- `tests/test_pool.py` (private-state assertions, `FakeDb`, `pytest.raises(Exception)`),
  `tests/test_postgresql.py`, `tests/test_oracle.py`, `tests/conftest.py`
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `pyproject.toml`, `CHANGELOG.md`,
  `docker-compose.yml`, `README.md`, `.gitignore`
- `.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md`
- `py.typed` confirmed **absent**; `uv` 0.8.22 confirmed; CPython 3.10.18 confirmed

### Secondary / Tertiary (MEDIUM — flagged for validation)
- SQL Server 2,100-parameter limit and Oracle 1,000-element `IN` cap — widely documented, not
  re-fetched; verify before finalizing batch sizes
- asyncpg ~32767 parameter ceiling — protocol `int16` limit, not confirmed in fetched docs
- `asyncio.create_task` context-copy → shared-connection failure mode — inference from code + asyncpg
  single-operation contract; confirm with the P4 test
- GitHub-hosted runner memory/disk limits for six simultaneous containers — confirm against current
  specs
- Oracle/MSSQL container readiness times — measure once and pin the timeout
- `__signature__` for FastAPI path params — community pattern; validate in Phase 6
- Piccolo ORM — identified as a peer, not researched in depth

---
*Research completed: 2026-09-17*
*Ready for roadmap: yes*
