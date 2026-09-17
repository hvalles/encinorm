# Feature Research

**Domain:** Production hardening of a multi-engine async Python ORM (`encino_orm` 0.2.6 → 0.3.0)
**Researched:** 2026-09-17
**Confidence:** HIGH

> **Framing:** This is a brownfield hardening milestone, not a greenfield launch. "MVP" below means **what 0.3.0 must ship to be credibly production-usable**, not "minimum to validate an idea." The project already has a broad feature surface (6 engines, CRUD, relations, migrations, cache, REST/GraphQL/RBAC layers). What is missing is the *reliability, security and operability contract* that production users assume an ORM already honors.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features production users assume exist. Missing these = the library is a prototype, regardless of feature breadth.

#### A. Connection Lifecycle & Pool Health

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-1 | **Race-free pool checkout** — never exceeds `max_size` under concurrency | Silent over-subscription exhausts the DB's own connection limit and takes down other services. A pool that can leak connections is worse than no pool. | LOW–MED | `pool.py:111-146` is check-then-act across an `await`: two acquirers can both pass `self._size < self._max_size`. Fix by reserving the slot (increment `_size` before awaiting create) or guarding bookkeeping with `asyncio.Lock`. |
| TS-2 | **Deterministic reset-on-release: ROLLBACK, not commit** | Releasing a connection must leave it in a well-defined state; committing leftover work makes partial writes durable and leaks locks. This is the SQLAlchemy default (`reset_on_return="rollback"`) and asyncpg runs a reset query on release (`pg_advisory_unlock_all; CLOSE ALL; UNLISTEN *; RESET ALL`). | LOW–MED | `pool.py:199-204,239-242` currently **commits** if a transaction is open. Inverts the industry default and silently commits partial work. **Breaking change → CHANGELOG.** |
| TS-3 | **Health check + automatic reconnect for direct (non-pool) connections** | A dropped TCP connection should surface once, then self-heal. Callers should not have to build a reconnect loop. Django ships `CONN_HEALTH_CHECKS`; SQLAlchemy ships `pool_pre_ping`; Tortoise retries connections. | MED | `is_alive()` already exists on all six engines (`SELECT 1` / `aiomysql.ping`). The gap is *wiring*: nothing calls it except `PoolDb.acquire()` on idle-timeout. Reuse `Db.retry` (`base.py:78`) — today it only retries `is_lock_error`, never disconnects. |
| TS-4 | **Disconnect classification (`is_disconnect`)** | Auto-reconnect is only safe if you can distinguish "connection died" from "query was wrong." Needed as the foundation for TS-3 and TS-16. | MED | SQLAlchemy centralizes this in per-dialect `is_disconnect()`. Mirror `is_lock_error` (`base.py:74`, overridden in all six engines) with `is_disconnect`. |
| TS-5 | **Connection recycling by age / query count** | MySQL/Oracle silently kill idle connections (and MySQL's `wait_timeout` defaults are aggressive); server-side statement caches grow unbounded. | LOW–MED | SQLAlchemy `pool_recycle`; asyncpg `max_queries`. Cheap insurance against a class of "works in dev, fails after lunch" bugs. |
| TS-6 | **Idle reaping above `min_size`** | Bursts pin `max_size` connections for the process lifetime, permanently consuming DB capacity. | MED | asyncpg `max_inactive_connection_lifetime=300s`. Currently only lazily closed during `acquire()` (`pool.py:103-109,140-146`). Prefer lazy close in `release()` over a background daemon (see AF-7). |
| TS-7 | **Checkout timeout surfaces an explicit error, never hangs** | A saturated pool must fail fast with a typed error the app can catch and map to a 503. | LOW | `PoolExhaustedError` + `timeout` param already exist (`pool.py:131-138`). Make a sane default timeout non-optional/documented; count `waits`/`timeouts` (already tracked). |
| TS-8 | **`last_id()` correct per connection/task** | Returning another task's insert id corrupts audit trails and parent/child writes. | LOW–MED | `pool.py:63` is a single shared `_last_id`; `pool.py:236-237` overwrites it after every INSERT. Store per-connection; resolve via `_current_connection` when in a transaction. |
| TS-9 | **Deterministic `close()` / dispose** | Shutdown must drain checked-out connections, be idempotent, and not lose in-flight work silently. | LOW–MED | `pool.py:152-160` clears the queue without accounting for checked-out connections. SQLAlchemy exposes `dispose()` / `recreate()` as first-class lifecycle verbs. |

#### B. Transaction & Data Correctness

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-10 | **Count/paginate/list_tables correct on every engine** | A count that raises `KeyError` on PostgreSQL is a hard stop for anyone not on SQLite. Cross-engine behavioral parity is the entire value proposition of a unified ORM. | LOW | `model.py:790-792`, `query_builder.py:240-242`, `base.py:151` read `row["COUNT(*)"]`; asyncpg lowercases to `count`. `Db.paginate` (`base.py:168-172`) already uses `AS n` — apply that pattern everywhere. |
| TS-11 | **Atomic migration apply, or documented reconciliation** | A migration that half-applies leaves schema and ledger inconsistent — the worst failure mode for a data library. | MED–HIGH | Alembic gates this on per-dialect `transactional_ddl` (True for PostgreSQL; False for MySQL/Oracle). Wrap DDL+record in a transaction where supported; for MySQL/Oracle record intent first (status column) and reconcile on startup. |
| TS-12 | **Rollback bookkeeping so re-apply works** | A rollback you cannot undo is a one-way door; users discover it in an incident. | MED | `migration.py:25-29` records `"{name}:down"` and never deletes `{name}`, so re-apply is a no-op. Delete/annotate the original row on rollback. |
| TS-13 | **Cache invalidation on write (write-invalidate / cache-aside)** | A cache that never invalidates is a stale-data generator; the default TTL (300s) makes it invisible in tests and obvious in production. | LOW–MED | `cached.py` only writes on load; no `cache.delete` call exists anywhere. Microsoft's cache-aside guidance is explicit: **write the data store first, then invalidate the key** (reversing the order re-populates stale data). Override `update`/`delete` in `CachedModel`. |
| TS-14 | **Transaction API rolls back on exception** | Non-negotiable; already correct. | LOW | `base.py:41-48` + `PoolDb.transaction` (`pool.py:162-171`). Keep as regression-guarded behavior. |
| TS-15 | **Bulk writes are atomic and batched** | `insert_many` that partially applies on error corrupts data; per-row round-trips make bulk loads unusable. | MED | asyncpg made `executemany` atomic in 0.22 (all-or-nothing). Verify `insert_many` semantics per driver and document them. |
| TS-16 | **Error taxonomy: driver exceptions → library exceptions** | Users must be able to `except encino_orm.ConnectionError / QueryError / ...` portably instead of importing six drivers. Also the input to retry policy and observability. | MED | `exceptions.py` is thin (6 types, no mapping). Add disconnect/timeout/constraint/deadlock mapping per dialect. Prerequisite for TS-3 and TS-32. |
| TS-17 | **Isolation-level configuration** | Production apps need `READ COMMITTED` vs `SERIALIZABLE` control, and must know when to handle serialization failures. | LOW–MED | Django and SQLAlchemy both expose per-connection isolation level. `connect(**kwargs)` passthrough likely already works for some drivers — document and test it, or make it explicit. |

#### C. Security

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-18 | **Identifier allow-list validation on all public builders, all six dialects** | OWASP's primary defense for non-bindable SQL fragments (table/column names) is allow-list validation; string-built identifiers from user input are a direct injection vector. | LOW–MED | `Db._check_identifier` exists (`base.py:59-64`) but `insert`/`update`/`delete` in all six dialect modules interpolate `tabla` and dict keys unvalidated. `_IDENTIFIER_RE` is already the right allow-list — apply it uniformly. Also protects users who legitimately derive names dynamically. |
| TS-19 | **Parameter binding for all values** | OWASP Option 1. Already systemic (`Query` + params). | LOW | Existing validated strength. Guard with tests; do not regress while optimizing placeholder translation (TS-37). |
| TS-20 | **Introspection-derived identifiers validated before DDL** | Column names read from the catalog are interpolated into `ALTER TABLE`; exotic names break or inject. | LOW | `model.py:877,885,896,900`. Apply `_IDENTIFIER_RE` (or per-dialect quoting) before building DDL. |
| TS-21 | **Secret/config injection without mutable module globals** | Process-wide mutable `SECRET`/`GET_DB` means one misconfiguration or late overwrite affects every request. | LOW–MED | `security/guard.py:13-15`. The dependency factories already accept `secret=`/`get_db=` params — make the explicit path the documented one and freeze/deprecate the globals. |
| TS-22 | **Documented trust boundaries for raw-SQL escape hatches** | `Filter.raw`, `Query(sql, ...)` and `db.fn.*` fragments are legitimate power features but must be unambiguously "trusted input only." | LOW | Document + add a lint/CI guard that HTTP/GraphQL parsers never emit `raw` (they currently don't — keep it that way). |
| TS-23 | **Dev-only credentials marked; release via OIDC trusted publishing** | Hardcoded `admin` passwords invite copy-paste into real environments; long-lived PyPI tokens are a supply-chain risk. | LOW | `docker-compose.yml`, `.github/workflows/release.yml:35-38`. Migrate to `uv publish --trusted-publishing always` + `id-token: write`. |
| TS-24 | **Dependency / vulnerability scanning in CI** | A "production-grade" claim with unmonitored dependencies is not defensible. | LOW | No `pip-audit`/Dependabot/`uv lock --check`. Also addresses the pinned `PyJWT<2.13` cap that blocks security fixes. |

#### D. Quality Gates & CI

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-25 | **Lint + format gate (`ruff`)** | Enforces a baseline and catches unused imports / dead code / broad excepts mechanically. | LOW | `ruff>=0.16.8` is already a dev dependency but has **no config and no CI step**. Lowest-cost, highest-leverage gate. |
| TS-26 | **Type-check gate (`mypy`)** | The public API is typed; without a checker, annotations rot and `Any` spreads. | LOW–MED | Start non-strict on `encino_orm/` and ratchet. **Exclude the `exec()`-generated REST/GraphQL layers** (AF-12) or type-check them only after refactor. |
| TS-27 | **Coverage measured with a threshold** | 507 test functions with no coverage number means the *shape* of the gaps is unknown; regressions have no baseline. | LOW | Add `pytest-cov`, publish `--cov-report=term-missing`, fail under a floor. Do not chase 100% (AF-13). |
| TS-28 | **Multi-engine CI matrix (MariaDB, SQL Server, Oracle, Redis)** | The `COUNT(*)` bug shipped precisely because CI only ran MySQL + PostgreSQL. Dialect regressions are invisible without per-engine execution. | HIGH | MySQL/PG services already exist. MariaDB + Redis are cheap containers; MSSQL (`mssql/server`) is feasible in Actions; Oracle (`gvenzl/oracle-free`) is heavy but available. Where truly infeasible, a *justified* mock is acceptable — but not for SQL-dialect logic. |
| TS-29 | **Concurrency / stress tests for the pool** | The pool's races are the highest-severity class of bug in the library and are currently untested. Tests are the *proof* for TS-1/TS-2/TS-8. | MED | `tests/test_pool.py` is sequential only. Add: N concurrent acquirers assert `size <= max_size`; parallel inserts assert distinct `last_id`; release-after-close; `close()` with checked-out connections. |
| TS-30 | **Regression test per bug fix + `CHANGELOG.md` for breaking changes** | The project's own decision (PROJECT.md Key Decisions) and the only credible definition of "fixed." | LOW | Each of TS-10/12/13 gets a test that fails before and passes after. 0.3.0 allows breaking changes *only* if documented. |

#### E. Observability & Operability

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-31 | **Automatic query instrumentation via a hook** | Users expect an ORM to instrument queries automatically; a tracer they must remember to call on every path will not be used and will not reflect production traffic. | MED | `QueryTracer`/`OtelQueryTracer` are exported but **never referenced inside the package** — pure manual API. Add a `Db.tracer` hook invoked by `execute`/`fetch_*`. |
| TS-32 | **OpenTelemetry stable DB semantic conventions** | The ecosystem standard; non-standard attributes are invisible to standard dashboards and OTel Collector processors. | LOW–MED | Current `OtelQueryTracer` emits legacy experimental keys (`db.system`, `db.operation`, `db.statement`, `db.elapsed_ms`, `db.rows`). Stable keys: `db.system.name`, `db.operation.name`, `db.query.text`, `db.collection.name`, `db.namespace`, `db.response.status_code`, `error.type`, `db.response.returned_rows`, `server.address`/`server.port`. Note stable `db.system.name` values exist for `mysql`, `mariadb`, `postgresql`, `microsoft.sql_server`; `oracle.db` and `sqlite` are still development-status values. |
| TS-33 | **PII-safe logging (params opt-in, sanitized query text)** | Connection strings and query params routinely contain credentials/PII; logging them by default is a compliance incident. | MED | `QueryTracer.record` logs `params=%r` unconditionally. OTel guidance: parameter values are **opt-in**, `db.query.text` should be sanitized (literals replaced) unless parameterized. Gate params behind a flag; default off in production presets. |
| TS-34 | **Bounded metric accumulation** | Unbounded lists are a slow memory leak in a long-lived process. | LOW | `observability.py:71,80-81` appends every latency forever. Use a `deque(maxlen=...)` or reservoir sampling; expose the bound. |
| TS-35 | **Pool metrics exposed and accurate** | Operators need size/idle/waits/timeouts to size pools and alert on saturation. | LOW | `PoolDb.stats` exists but lacks idle count; must be accurate once TS-1/TS-2 land. asyncpg exposes `get_size/get_idle_size/get_max_size/get_min_size`. |
| TS-36 | **Slow-query threshold logging** | The cheapest, highest-value production signal; catches missing indexes and N+1s before users do. | LOW | Trivial once TS-31 wiring exists. |

#### F. Performance

| ID | Feature | Why Expected | Complexity | Notes |
|----|---------|--------------|------------|-------|
| TS-37 | **Precompiled / cached placeholder translation** | Re-running a regex substitution on every execute is pure per-query overhead in the hot path. | MED | `postgresql.py:22-29`, `sqlite.py:22-29`, `oracle.py:18-35`. Cache the translated SQL on the `Query` instance (or compile at build time). Must not regress TS-19. |
| TS-38 | **Batched `copy_table`** | One round-trip per row makes bulk transfer unusable at scale. | MED | `transfer.py:155-167`. Batch 500–1000 rows into multi-value INSERTs or reuse the `insert_many` path. |
| TS-39 | **Benchmark suite with numeric targets in CI** | "Production-grade performance" is unfalsifiable without measurements; also guards TS-37/TS-38 against regressions. | MED | PROJECT.md constraint: optimizations must not regress correctness and must be *measured*, not perceived. |

---

### Differentiators (Competitive Advantage)

Not required for credibility, but these are where `encino_orm` can be *better* than SQLAlchemy/Django/Tortoise/Piccolo for this niche.

| ID | Feature | Value Proposition | Complexity | Notes |
|----|---------|-------------------|------------|-------|
| D-1 | **Six-engine conformance test harness** | A single parameterized suite that runs identical semantics against all six engines, with a published per-engine capability matrix. No mainstream async Python ORM covers MSSQL + Oracle + MariaDB + PostgreSQL + MySQL + SQLite under one API. | HIGH | Directly prevents the class of bug that motivated this milestone. Publish "supported / best-effort / unsupported" per capability. |
| D-2 | **Built-in cache with automatic write-invalidation** | SQLAlchemy/Django/Tortoise have no first-class ORM cache; users bolt on `dogpile.cache` or hand-roll it. An ORM-integrated cache-aside that is correct by default is genuinely differentiating. | MED | Depends on TS-13. Keep the invalidation contract simple and explicit; resist distributed coherence (AF-9). |
| D-3 | **First-class OpenTelemetry instrumentation shipped in the box** | Most ORMs require third-party instrumentation packages or app-side wrapping. Shipping stable-semconv spans + pool metrics with zero config is a real selling point. | MED | Depends on TS-31/32/33. |
| D-4 | **Self-healing pool with a documented, observable policy** | Explicit, documented behavior for recycle / reap / reset / reconnect — with metrics — beats "it's a QueuePool, good luck." | MED | Depends on TS-1..TS-6. |
| D-5 | **Fail-closed security defaults** | Already partially true (`_ALLOWED_ALGORITHMS` blocks `none`/algorithm confusion; missing `SECRET` fails closed; `verify_token` requires `exp`). Extending this to identifiers and config is a defensible security posture. | LOW–MED | Depends on TS-18/21. Market as "secure defaults," backed by tests. |
| D-6 | **Migration reconciliation for engines without transactional DDL** | MySQL/Oracle cannot roll back DDL, so most tools just leave you exposed. A recorded-intent + reconcile-on-startup protocol is better than the status quo. | MED–HIGH | Depends on TS-11. Be honest about guarantees per engine. |
| D-7 | **Pydantic-native typed models with identifier validation at definition time** | Type-safe models that also validate schema identifiers is a coherent story that query-builder-first ORMs lack. | LOW | Already largely present (`model.py:227-249`). Formalize and document. |
| D-8 | **Per-task transaction affinity via `contextvars`** | Correct-by-construction transaction scoping under asyncio (no thread-local footguns). Already implemented; rarely done well elsewhere. | LOW | `pool.py:26-29,162-171`. Harden with TS-8 and concurrency tests. |
| D-9 | **Published reliability contract per engine** | A table stating exactly what is guaranteed (transactional DDL? savepoints? reconnect? isolation levels?) per engine. Turns implicit behavior into a documented promise. | LOW | Output of TS-28; cheap to produce, high trust value. |

---

### Anti-Features (Commonly Requested, Often Problematic)

Deliberately **not** build these in the 0.3.0 hardening milestone. Each is either explicitly out of scope in PROJECT.md or a well-known trap.

| ID | Anti-Feature | Why Requested | Why Problematic | Alternative |
|----|--------------|---------------|-----------------|-------------|
| AF-1 | **New database engines** | "Support DuckDB/CockroachDB/Mongo" is the most common ORM ask. | Every new dialect multiplies the conformance matrix that is already under-tested; it directly dilutes the hardening goal. | PROJECT.md Out of Scope. Ship D-9's capability matrix; revisit post-0.3.0. |
| AF-2 | **Declaring 1.0 / freezing the API** | Signals stability to adopters. | Promises backward compatibility before the reliability contract exists; 0.3.0 *needs* freedom to break pool/migration semantics. | Stay 0.x; document breaking changes in `CHANGELOG.md` (TS-30). |
| AF-3 | **Cosmetic public-API redesign / renames** | Cleaner names, "better" ergonomics. | Churn with zero reliability value; breaks users for aesthetics only. | PROJECT.md: only break for security, correctness or stability. |
| AF-4 | **Alembic-style autogenerate migration engine** | Users want `makemigrations`. | Model diffing + autogenerate is a large product in itself and is orthogonal to *migration safety*. `diff_schema` already covers introspection. | Fix TS-11/TS-12; keep migrations explicit; document the safety model. |
| AF-5 | **Automatic retry of arbitrary write transactions** | "Just retry on any error = resilience." | Retrying non-idempotent writes duplicates data. SQLAlchemy is explicit that pre-ping does **not** cover mid-transaction drops; the app must decide. | Retry only *classified* transient/lock errors (TS-4/TS-16), opt-in, never on arbitrary exceptions. |
| AF-6 | **Wrapping a driver-native pool in a second pool** | "More pooling = more reliable." | Double-pooling causes two independent limits, nested checkout deadlocks, and double the timeouts to reason about. | One pool per engine (TS-1..TS-9). Document that driver-native pools are bypassed by `PoolDb`. |
| AF-7 | **A mandatory background reaper daemon task** | "Reap idle connections automatically." | Requires event-loop lifecycle ownership, breaks clean shutdown, and leaks tasks in tests/CLIs. | Lazy close on `release()`/`acquire()` (TS-6) — asyncpg-style lifetime is a parameter, not a daemon. |
| AF-8 | **Telemetry enabled by default** | "Observability out of the box." | Logging params/PII by default is a compliance risk; full tracing by default costs performance and cardinality. | Opt-in instrumentation with safe defaults (TS-31/32/33). |
| AF-9 | **Distributed / cross-process cache coherence (Redis pub/sub invalidation)** | Multi-worker deployments see stale reads. | Solves a problem beyond single-process correctness; adds a hard dependency and a new failure mode. Fix local invalidation first (TS-13). | Document the multi-process limitation; recommend short TTLs or per-worker caches. |
| AF-10 | **Read/write splitting, replicas, sharding, routing** | Scale-out requests. | Large distributed-systems surface with no bearing on correctness of the six engines; wrong abstractions here are very expensive. | Document that callers compose multiple `Db`/`PoolDb` instances themselves. |
| AF-11 | **Catch-all `except Exception` "resilience" wrappers** | Makes tests green and hides errors. | Converts hard failures into silent corruption; defeats TS-16 and masks real bugs. | Typed exception taxonomy (TS-16) + targeted retry (AF-5 note). |
| AF-12 | **Extending the `exec()`-generated REST/GraphQL codegen** | Fast path to dynamic handlers. | Unanalyzable, untyped, debug-by-print, and brittle for composite PKs. Extending it deepens the worst debt in the repo. | Refactor to closures/factories (`graphql/schema.py:108-116` already shows the pattern) *only* as needed to satisfy TS-26. |
| AF-13 | **100% coverage as a stated goal** | "Coverage = quality." | Rewards testing trivial lines; the real gaps are concurrency, dialect parity and destructive schema paths (which are hard to cover, not many lines). | Threshold + targeted high-risk coverage (TS-27, TS-29, TS-28). |
| AF-14 | **A custom SQL parser / query optimizer** | "Faster queries, smarter ORM." | Enormous, endless, and duplicates what the database already does; also risks breaking TS-19 parameterization. | Measure (TS-39), then optimize the measured hot paths (TS-37/38). |
| AF-15 | **Caching reads by default** | "Free performance." | Opt-out caching produces stale reads by surprise; the existing cache is opt-in for good reason. | Keep `CachedModel` opt-in; make it *correct* (TS-13). |

---

## Feature Dependencies

```
TS-16 (error taxonomy)
    ├──requires──> TS-4 (disconnect classification)
    └──requires──> TS-32 (OTel error.type / db.response.status_code)

TS-4 ──requires──> TS-3 (health check + auto-reconnect)
TS-3 ──enhances──> TS-5 (recycle) + TS-6 (idle reaping)
TS-3 ──conflicts──> AF-5 (blind retry)   [retry must be classified, not blanket]

TS-1 (race-free checkout) ──requires──> TS-29 (concurrency tests are the proof)
TS-2 (rollback-on-release) ──requires──> TS-1  [both mutate pool bookkeeping; land together]
TS-2 ──conflicts──> current implicit-commit behavior  →  breaking change → TS-30
TS-8 (per-connection last_id) ──requires──> TS-1
TS-9 (close/dispose) ──requires──> TS-1

TS-10 (dialect-correct count) ──requires──> TS-28 (multi-engine CI to prove)
TS-11 (migration atomicity) ──requires──> TS-12 (rollback bookkeeping)
TS-11 ──requires──> TS-28 (prove on PG/MySQL/Oracle; DDL atomicity differs per engine)
TS-18 (identifier validation, 6 dialects) ──requires──> TS-28
TS-20 (introspection identifier validation) ──enhances──> TS-18

TS-13 (cache invalidation) ──conflicts──> AF-9 (distributed coherence)
TS-13 ──enhances──> D-2

TS-31 (auto instrumentation hook) ──requires──> TS-16
TS-32 (stable semconv) ──requires──> TS-31
TS-33 (PII-safe logging) ──requires──> TS-31
TS-34 (bounded buffers) ──enhances──> TS-31
TS-36 (slow-query logging) ──requires──> TS-31

TS-37 (placeholder caching) ──requires──> TS-39 (prove no regression)
TS-38 (batched copy_table) ──requires──> TS-39
TS-15 (bulk atomicity) ──enhances──> TS-38

TS-25 (ruff) ──enables──> TS-26 (mypy) ──enables──> all subsequent phases
TS-27 (coverage) ──enables──> TS-29 / TS-28 targeting
TS-28 ──enables──> D-1 / D-9
```

### Dependency Notes

- **TS-25 → TS-26 (do first):** Lint and type gates are the cheapest interventions in the whole milestone and they reduce churn for every later phase. Land them before touching pool/migration internals. Sequence `ruff` first, then a non-strict `mypy` ratchet.
- **TS-1 + TS-2 + TS-8 + TS-9 are one unit of work:** They all mutate the same pool bookkeeping and the same release path. Splitting them across phases invites conflicting fixes. TS-29 is their acceptance evidence.
- **TS-2 is the milestone's key breaking change:** Switching release-from-commit to release-from-rollback changes observable behavior for anyone relying on the implicit commit. Must be in `CHANGELOG.md` (TS-30).
- **TS-4 gates TS-3:** You cannot safely auto-reconnect without distinguishing disconnect errors from query errors. TS-16 (the public exception taxonomy) then depends on TS-4.
- **TS-28 gates all dialect correctness work:** TS-10, TS-18 and TS-11 cannot be *proven* done without per-engine execution. This makes CI matrix work a prerequisite, not a cleanup task — the project's own Key Decision says as much.
- **TS-16 gates observability:** OTel's `error.type` and `db.response.status_code` are only meaningful once driver errors are classified.
- **TS-31 is the missing observability keystone:** Without automatic wiring, TS-32/33/36 have no traffic to observe. Current tracers are exported but unused inside the package.
- **TS-39 gates performance claims:** PROJECT.md forbids "perceived" improvements; benchmarks are the mechanism that makes TS-37/38 verifiable and prevents regressions.
- **AF-5 vs TS-3:** Both are about recovery, but blind retry of non-idempotent writes is a data-corruption anti-feature. Retry must be scoped to classified transient errors and be opt-in.
- **AF-6 vs TS-1:** If `PoolDb` wraps a driver that already pools, the two limits conflict. Choose one pooling layer and document it.

---

## 0.3.0 Scope Definition

### Launch With (0.3.0) — P1

Everything in PROJECT.md's Active list, plus the two gaps this research surfaces that are prerequisites to proving it.

**Correctness (the reason for the milestone)**
- [ ] TS-10 — count/paginate/list_tables correct on all engines (alias `AS n`)
- [ ] TS-12 — rollback bookkeeping so migrations re-apply
- [ ] TS-11 — migration apply atomic, or documented reconciliation per engine
- [ ] TS-13 — `CachedModel` write-invalidation (store-then-invalidate)
- [ ] TS-30 — regression test per fix + `CHANGELOG.md`

**Security**
- [ ] TS-18 — identifier allow-list validation in all six dialect builders
- [ ] TS-20 — validate introspection-derived identifiers before `ALTER TABLE`
- [ ] TS-21 — explicit secret/config injection over mutable globals
- [ ] TS-22 — documented trust boundaries for `Filter.raw` / `Query` / `db.fn.*`
- [ ] TS-23 — dev-only credentials marked; OIDC trusted publishing
- [ ] TS-24 — dependency/vulnerability scanning in CI

**Concurrency & pool**
- [ ] TS-1 — race-free checkout (never exceeds `max_size`)
- [ ] TS-2 — release policy = rollback (documented breaking change)
- [ ] TS-8 — per-connection/task `last_id`
- [ ] TS-9 — deterministic close/dispose
- [ ] TS-3 + TS-4 — health check + classified reconnect for direct connections
- [ ] TS-29 — concurrency/stress tests (the proof for the above)

**Quality gates & CI**
- [ ] TS-25 — `ruff` config + CI gate
- [ ] TS-26 — `mypy` (non-strict, ratcheting)
- [ ] TS-27 — `pytest-cov` + threshold
- [ ] TS-28 — multi-engine CI matrix (MariaDB + Redis minimum; MSSQL/Oracle or justified mocks)
- [ ] TS-16 — error taxonomy (needed by TS-3; also unblocks observability)

**Performance**
- [ ] TS-37 — cached placeholder translation
- [ ] TS-38 — batched `copy_table`
- [ ] TS-39 — benchmark suite with numeric targets
- [ ] TS-6 — idle reaping above `min_size` (lazy, in `release()`)

**Release**
- [ ] TS-30 — `CHANGELOG.md` complete for all 0.3.0 breaks

### Add After Validation (0.3.x) — P2

Trigger: 0.3.0 is published and the reliability contract holds in real use.

- [ ] TS-5 — connection recycling by age / max queries — *trigger: first "stale connection after idle" report*
- [ ] TS-31 — automatic query instrumentation hook — *trigger: users asking why tracers show no data*
- [ ] TS-32 — OTel stable semantic conventions — *trigger: OTel Collector/dashboard integration*
- [ ] TS-33 — PII-safe logging (params opt-in) — *trigger: first compliance review*
- [ ] TS-34 — bounded metric buffers — *trigger: long-running process memory growth*
- [ ] TS-35 — pool metrics incl. idle count — *trigger: operator asks for pool sizing data*
- [ ] TS-36 — slow-query logging — *trigger: performance incident*
- [ ] TS-17 — documented isolation-level configuration — *trigger: user needs `SERIALIZABLE`*
- [ ] TS-15 — verify/document bulk-write atomicity per driver — *trigger: bulk-load incident*
- [ ] D-9 — published per-engine reliability contract — *output of TS-28*

### Future Consideration (0.4+) — P3

Defer until the reliability contract is proven and adopted.

- [ ] D-1 — full six-engine conformance harness (beyond CI smoke)
- [ ] D-2 — cache as a marketed differentiator (correctness first via TS-13)
- [ ] D-3 — OTel as a headline feature
- [ ] D-4 — self-healing pool as a documented product promise
- [ ] D-6 — MySQL/Oracle migration reconciliation as a differentiator
- [ ] AF-4 alternative — migration safety tooling *if* users ask, after TS-11 is solid
- [ ] AF-1 — new engines (revisit only after 0.3.0/0.4.0 stabilize)

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| TS-10 count/paginate dialect fix | HIGH | LOW | P1 |
| TS-12 migration rollback bookkeeping | HIGH | MEDIUM | P1 |
| TS-13 cache invalidation | HIGH | LOW–MEDIUM | P1 |
| TS-11 migration atomicity | HIGH | MEDIUM–HIGH | P1 |
| TS-18 identifier validation (6 dialects) | HIGH | LOW–MEDIUM | P1 |
| TS-1 race-free pool checkout | HIGH | LOW–MEDIUM | P1 |
| TS-2 rollback-on-release | HIGH | LOW–MEDIUM | P1 |
| TS-8 per-connection `last_id` | HIGH | LOW–MEDIUM | P1 |
| TS-29 pool concurrency tests | HIGH | MEDIUM | P1 |
| TS-16 error taxonomy | HIGH | MEDIUM | P1 |
| TS-3 reconnect for direct connections | HIGH | MEDIUM | P1 |
| TS-28 multi-engine CI matrix | HIGH | HIGH | P1 |
| TS-25 ruff gate | MEDIUM | LOW | P1 |
| TS-26 mypy gate | MEDIUM | LOW–MEDIUM | P1 |
| TS-27 coverage gate | MEDIUM | LOW | P1 |
| TS-30 regression tests + CHANGELOG | HIGH | LOW | P1 |
| TS-21 secret injection | MEDIUM | LOW–MEDIUM | P1 |
| TS-20 sync_schema identifier validation | MEDIUM | LOW | P1 |
| TS-22 trust-boundary docs | MEDIUM | LOW | P1 |
| TS-23 OIDC publishing / dev creds | MEDIUM | LOW | P1 |
| TS-24 dependency scanning | MEDIUM | LOW | P1 |
| TS-37 placeholder caching | MEDIUM | MEDIUM | P1 |
| TS-38 batched copy_table | MEDIUM | MEDIUM | P1 |
| TS-39 benchmarks | MEDIUM | MEDIUM | P1 |
| TS-9 close/dispose | MEDIUM | LOW–MEDIUM | P1 |
| TS-6 idle reaping | MEDIUM | MEDIUM | P1 |
| TS-31 auto instrumentation | MEDIUM | MEDIUM | P2 |
| TS-32 OTel stable semconv | MEDIUM | LOW–MEDIUM | P2 |
| TS-33 PII-safe logging | MEDIUM | MEDIUM | P2 |
| TS-36 slow-query logging | MEDIUM | LOW | P2 |
| TS-34 bounded buffers | LOW–MEDIUM | LOW | P2 |
| TS-35 pool metrics (idle) | LOW–MEDIUM | LOW | P2 |
| TS-5 connection recycling | MEDIUM | LOW–MEDIUM | P2 |
| TS-17 isolation-level config | MEDIUM | LOW–MEDIUM | P2 |
| TS-15 bulk-write atomicity docs | MEDIUM | MEDIUM | P2 |
| D-1 conformance harness | HIGH | HIGH | P3 |
| D-2 cache differentiator | MEDIUM | MEDIUM | P3 |
| D-3 OTel differentiator | MEDIUM | MEDIUM | P3 |
| D-9 reliability contract doc | HIGH | LOW | P2 |

**Priority key:**
- P1: Must ship in 0.3.0 — without these the "production-grade" claim is not defensible
- P2: Should have; add once 0.3.0 validates the contract
- P3: Nice to have; future consideration

---

## Competitor Feature Analysis

| Feature | SQLAlchemy 2.0 async | Django ORM (async) | Tortoise ORM | asyncpg (driver) | `encino_orm` approach |
|---------|----------------------|--------------------|--------------|------------------|------------------------|
| Pool implementation | `AsyncAdaptedQueuePool` (asyncio-aware) | Driver-native pool (`pool=True` for psycopg/oracledb) or third-party | Driver-native / `asyncpg` pool | Native `Pool` | Own `PoolDb` over six drivers — **must not double-pool (AF-6)** |
| Disconnect handling | Pessimistic `pool_pre_ping` + optimistic `is_disconnect()` + `Pool.recreate()` invalidation | `CONN_HEALTH_CHECKS` per request; closes unusable connections | Connection retry (incl. within transactions) | Server-side; `Connection.reset()` on release | Add `is_disconnect` (TS-4) + health check wiring (TS-3) |
| Reset on release | `reset_on_return="rollback"` (default); customizable | Closes/recycles per request | Reset via pool | Runs `pg_advisory_unlock_all; CLOSE ALL; UNLISTEN *; RESET ALL` | Currently **commits** — invert to rollback (TS-2) |
| Recycling | `pool_recycle` (age) | `CONN_MAX_AGE` | Driver/pool options | `max_queries` | Add both (TS-5) |
| Idle reaping | Lazy shrink on checkout | `close_old_connections()` | Driver/pool options | `max_inactive_connection_lifetime` (default 300s) | Lazy reap in `release()` (TS-6) |
| Checkout timeout | `pool_timeout` → `TimeoutError` | N/A (per-request connections) | Driver/pool options | `Pool.acquire(timeout=...)` | `PoolExhaustedError` + timeout (TS-7) |
| Pool introspection | `Pool.status()` | — | — | `get_size/get_idle_size/get_max_size/get_min_size` | `PoolDb.stats` — extend with idle (TS-35) |
| Transaction API | `AsyncSession` / `begin()` / savepoints | `atomic()` / `ATOMIC_REQUESTS` | `atomic()` decorator | `Connection.transaction()` | `transaction()` ctx + contextvar affinity (TS-14, D-8) |
| Transactional DDL | Per-dialect flag drives migration behavior | Engine-dependent | Engine-dependent | n/a | Must be explicit per engine (TS-11) |
| Migration safety | Alembic: `transactional_ddl`, `begin_transaction()`, `batch_alter_table` for SQLite | `migrate` + atomic-aware backends | Aerich | n/a | Fix rollback + atomicity; no autogenerate (AF-4) |
| Observability | Third-party / events | Django DB instrumentation | Third-party | `add_query_logger` (0.29+) | Own tracers, currently **unwired** — wire + stable semconv (TS-31/32) |
| Cache | None built-in (`dogpile.cache` external) | None built-in | None built-in | n/a | `CachedModel` + backends — **correctness first** (TS-13, D-2) |
| Identifier validation | Dialect quoting + `quoted_name` | Quoted identifiers | Quoted identifiers | n/a | Allow-list `_IDENTIFIER_RE` everywhere (TS-18) |
| Bulk insert atomicity | Session-level | `bulk_create` (partially atomic per backend) | `bulk_create` | `executemany` atomic since 0.22 | Verify + document per driver (TS-15) |
| Multi-engine scope | ~15 dialects, mature | 5 backends | ~7 backends | PostgreSQL only | 6 engines incl. MSSQL + Oracle — **the core differentiator** |

**Read of the table:** `encino_orm` is not behind on features; it is behind on the *guarantees* around those features. The competitors' advantage is not API surface but decades of hardened failure semantics (pre-ping, reset-on-return, disconnect classification, lifecycle verbs). The 0.3.0 work is closing exactly that gap — which is why almost every P1 item is a *correctness* item, not a new capability.

---

## Sources

**Primary (official documentation, HIGH confidence)**
- SQLAlchemy 2.0 — Connection Pooling: `reset_on_return`, `pool_pre_ping`, `pool_recycle`, `pool_size`/`max_overflow`/`pool_timeout`, disconnect invalidation, `Pool.recreate()`, FIFO vs LIFO — https://docs.sqlalchemy.org/en/20/core/pooling.html
- SQLAlchemy 2.0 — async engine uses `AsyncAdaptedQueuePool` (`QueuePool` is not asyncio-compatible) — same source, "Connection Pool Configuration" note.
- SQLAlchemy 2.0 — pre-ping does **not** cover connections dropped mid-transaction; the application must retry the transaction — same source, "Disconnect Handling - Pessimistic".
- Django 5.2 — Databases: persistent connections, `CONN_MAX_AGE`, `CONN_HEALTH_CHECKS`, `close_old_connections()`, ASGI guidance, per-backend pool options — https://docs.djangoproject.com/en/5.2/ref/databases/
- asyncpg — Connection Pools API: `create_pool(min_size, max_size, max_queries, max_inactive_connection_lifetime, setup, init, reset)`, `Pool.expire_connections()`, `get_size()/get_idle_size()/get_max_size()/get_min_size()`, `Connection.reset()` default reset query, `Connection.is_closed()`, `is_in_transaction()`, `executemany` atomic since 0.22, `add_query_logger` (0.29+) — https://magicstack.github.io/asyncpg/current/api/index.html
- Alembic — `transactional_ddl` per dialect, `context.begin_transaction()` for transactional DDL, `batch_alter_table` (recreate mode for SQLite), version table as source of truth — https://alembic.sqlalchemy.org/en/latest/api/runtime.html and /ops.html
- OpenTelemetry — Semantic Conventions for database client spans (stable): `db.system.name`, `db.collection.name`, `db.namespace`, `db.operation.name`, `db.response.status_code`, `error.type`, `db.query.text` sanitization, `db.query.parameter.<key>` opt-in, `db.response.returned_rows`, `db.query.summary`; well-known `db.system.name` values incl. `mariadb`, `microsoft.sql_server`, `mysql`, `postgresql` (stable), `oracle.db`, `sqlite` (development) — https://opentelemetry.io/docs/specs/semconv/database/database-spans/
- OWASP — SQL Injection Prevention Cheat Sheet: prepared statements (Option 1), allow-list input validation for table/column names (Option 3), least privilege — https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Microsoft Azure Architecture Center — Cache-Aside Pattern: update the data store **before** invalidating the cache; staleness window between write and next read; LRU eviction and expiry considerations — https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside

**Peer projects (official docs, HIGH confidence)**
- Tortoise ORM — `BaseDBAsyncClient` (acquire_connection returns the current context connection when in a transaction), connection retry (changelog 0.12.1: "Fixed connection retry to work with transactions"), `atomic()` transaction decorator, multi-connection config — https://github.com/tortoise/tortoise-orm/blob/develop/docs/connections.rst and /docs/transactions.rst
- Piccolo ORM — identified as a peer async ORM/builder; not researched in depth (no specific claims made above).

**Project-local evidence (HIGH confidence — read directly)**
- `.planning/PROJECT.md` — scope, constraints, Active requirements, Key Decisions (regression test per fix, multi-engine coverage as done-criterion).
- `.planning/codebase/CONCERNS.md` — known bugs (`COUNT(*)`, cache invalidation, migration rollback/atomicity), security gaps (identifier validation, JWT globals, dev credentials), pool races, scaling limits (no reaper, no reconnect), CI gaps.
- `encino_orm/pool.py` — `acquire()` check-then-act (`:111-146`), shared `_last_id` (`:63`, `:236-237`), implicit commit (`:199-204`, `:239-242`), `close()` (`:152-160`), `transaction()` + contextvar (`:26-29`, `:162-171`).
- `encino_orm/base.py` — `_check_identifier` (`:59-64`), `retry`/`is_lock_error` (`:74-92`), count mismatch (`:151`), correct `AS n` pattern (`:168-172`).
- `encino_orm/model/cached.py`, `cache_backend.py` — no invalidation; unbounded memory backend.
- `encino_orm/migration.py` — rollback bookkeeping (`:25-29`); all six dialect `migrate()` implementations per CONCERNS.
- `encino_orm/observability.py` — unbounded `_latencies` (`:71`, `:80-81`); legacy OTel attribute names (`:139-149`); tracers never referenced elsewhere in the package (verified by grep).
- `encino_orm/security/guard.py` — mutable module globals (`:13-15`).
- `.github/workflows/ci.yml` — MySQL + PostgreSQL services only; `uv run pytest -q` with no lint/type/coverage step.
- `pyproject.toml` — `ruff` present in dev deps but unconfigured; no `mypy`, `pytest-cov`, or coverage config.

---

*Feature research for: production hardening of a multi-engine async Python ORM*
*Researched: 2026-09-17*
