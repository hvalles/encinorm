# Architecture Research

**Domain:** Async multi-engine Python ORM (`encino_orm`) — production hardening of an existing layered architecture
**Researched:** 2026-09-17
**Confidence:** HIGH (pool/transaction/lifecycle patterns verified against SQLAlchemy 2.0 and asyncpg authoritative docs); MEDIUM (DI refactor shape and `exec()` replacement are design recommendations for this specific codebase)

## Scope & Framing

This is a **brownfield hardening milestone**, not a redesign. The layered architecture
(`Db` ABC → 6 adapters → Model/Filter/QueryBuilder → optional lazy layers) is sound and
must be preserved. Every recommendation below is deliberately scoped to *where a concern
belongs* inside the existing layers, so fixes do not regress the import-lazy contract,
the `contextvars`-based state model, or the adapter-localization of dialect behavior.

The single most important structural insight from research:

> The current pool bugs are not "missing locks" — they are **state placed in the wrong
> layer**. `_last_id`, transaction state, and connection health are all **per-connection**
> concerns that the current code stores on the **pool** or discards. The canonical designs
> (SQLAlchemy `Pool`, asyncpg `Pool`) solve this by making a *connection handle* the unit
> of state, and making *reset-on-return* the default lifecycle contract. Restructuring
> around a `PooledConnection` handle fixes `acquire()` races, `last_id` cross-talk, and
> implicit-commit in one architectural move rather than three patches.

## Standard Architecture

### Target System Overview

The layer boundaries stay identical; new internal components are introduced **inside**
the connection layer and a new dialect-builder seam is introduced **inside** the core.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                     Optional product layers (lazy imports)                │
│  HTTP/REST · GraphQL · Security (SecurityConfig injected) · Introspection │
│  closures instead of exec() · config objects instead of module globals    │
└─────────┬────────────────────┬─────────────────┬────────────────────────┘
          │                    │                 │
          ▼                    ▼                 ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        ORM layer  `encino_orm/model/`                     │
│  Model · Filter · QueryBuilder · Records · references · CachedModel       │
│  (CachedModel gains write-invalidation hooks)                            │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ resolve_db() / bind() / session()
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│         Connection & context  `pool.py` · `context.py`  [REWORKED]       │
│  ┌────────────────────────────┐   ┌──────────────────────────────────┐   │
│  │ PoolDb (facade, Db ABC)    │   │ ConnectionRegistry (DI, was       │   │
│  │  _idle: Queue[PooledConn]  │   │  module global _default_db)       │   │
│  │  _in_use: set[PooledConn]  │   │  resolve_db(registry=None)        │   │
│  │  _lock: asyncio.Lock       │   └──────────────────────────────────┘   │
│  │  _size / _max_size         │                                          │
│  │  _generation (invalidate)  │   ┌──────────────────────────────────┐   │
│  │  _reaper_task (idle trim)  │   │ PooledConnection (handle)        │   │
│  │  reset_on_release=rollback │   │  db · created_at · last_used     │   │
│  └────────────────────────────┘   │  generation · last_id · in_use   │   │
│                                   └──────────────────────────────────┘   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│      Core abstractions  `base.py` · `query.py` · `dialects/`  [SEAM]      │
│  Db (ABC + concrete template methods) · Query (compiled-SQL cache)        │
│  dialects/builders.py  ← single choke point: validation + DML SQL         │
│  Db.retry (lock) · Db._with_reconnect (disconnect)  ← two distinct paths  │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │ implements hooks only
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│     Driver adapters (placeholders / DDL / last_id / error classification) │
│  sqlite · mysql · mariadb · postgresql · mssql · oracle                   │
│  each overrides: _prepare, _conflict_clause, is_lock_error,               │
│                  is_disconnect_error — NOT full insert/update/delete      │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation | Layer |
|-----------|----------------|------------------------|-------|
| `PoolDb` (facade) | Public `Db` interface; owns admission, reset, reaping, close semantics | Delegates to `PooledConnection`; guarded bookkeeping | Connection |
| `PooledConnection` | **Unit of per-connection state**: driver handle, `last_id`, timestamps, generation, in-use flag | `@dataclass(slots=True)` wrapper | Connection |
| `PoolDb._lock` | Guards `_size` / `_idle` / `_in_use` mutations | `asyncio.Lock`; **never held across `connect()`** | Connection |
| `_reaper_task` | Trim idle connections above `min_size`; expire by lifetime | `asyncio.Task` started in `connect()`, cancelled in `close()` | Connection |
| `ConnectionRegistry` | Injectable holder for process-default connection | Small class; `set_default_db` delegates to a module singleton instance | Context |
| `dialects/builders.py` | Build validated `INSERT`/`UPDATE`/`DELETE` SQL with `{n}` placeholders | Pure functions; `_check_identifier` on every table/column | Core |
| `Query` | Value object; cache compiled native-placeholder SQL per dialect | `query.compiled(dialect)` memoized on instance | Core |
| `Db.retry` | Re-run on **lock/deadlock** errors with jittered backoff | Existing; unchanged | Core |
| `Db._with_reconnect` | Reconnect **once** on disconnect-class error, only outside a transaction | New template method; adapters supply `is_disconnect_error` | Core |
| `is_disconnect_error` | Classify driver exceptions as connection-loss | Per-adapter (asyncpg `ConnectionDoesNotExistError`, etc.) | Adapter |
| `_conflict_clause` | Dialect-specific upsert/ignore fragment | Per-adapter hook (`OR IGNORE`, `ON CONFLICT`, `ON DUPLICATE`, `MERGE`) | Adapter |
| `SecurityConfig` | Frozen dataclass holding `secret`, `get_db`, algorithms | Injected into `get_current_user`/`require` factories | Optional |
| Handler factory | Build REST/GraphQL handlers without `exec()` | Closure + `__signature__` (REST); existing closure pattern (GraphQL) | Optional |

## Recommended Project Structure

```text
encino_orm/
├── base.py                 # Db ABC + concrete template methods (retry, reconnect, DML)
├── query.py                # Query + compiled-SQL cache per dialect
├── dialects/               # [NEW] shared dialect seam
│   ├── __init__.py
│   ├── builders.py         # build_insert/update/delete + identifier validation
│   └── strategies.py       # conflict/upsert strategy objects (prefix/suffix/target)
├── sqlite.py               # adapter: hooks only (_prepare, _conflict_clause, errors)
├── mysql.py
├── mariadb.py
├── postgresql.py
├── mssql.py
├── oracle.py
├── pool.py                 # PoolDb facade + PooledConnection handle
├── context.py              # ConnectionRegistry + resolve_db/bind/session
├── security/
│   ├── config.py           # [NEW] SecurityConfig (frozen dataclass)
│   └── guard.py            # factories take config; module globals deprecated
├── http/
│   └── routes.py           # closure-based handlers, no exec()
└── graphql/
    └── schema.py           # no module-namespace mutation; per-build namespace
```

### Structure Rationale

- **`dialects/` is a new seam, not a new layer.** It sits *inside* the core (depends only
  on `query.py` + the identifier regex) and is consumed by `Db` template methods. It is not
  a peer of the driver adapters — adapters override *hooks*, they no longer own DML SQL.
  This preserves the documented anti-pattern "no engine branches outside the adapter":
  dialect differences remain in the adapter as small hook overrides.
- **`PooledConnection` lives in `pool.py`, not a new module.** It is an implementation
  detail of `PoolDb`; splitting it into a module adds indirection without a boundary.
  If `pool.py` grows past ~350 lines, extract to `pool_core.py` with `PoolDb` as the public
  facade. Do not put it in `context.py` — context resolution must not know pool internals.
- **`ConnectionRegistry` replaces a module global with an injectable object** while keeping
  `set_default_db()` / `get_default_db()` as thin, deprecated-friendly shims. This is the
  minimal change that satisfies "no mutable module globals read at request time" without
  breaking `encino_orm.__init__` exports.
- **`SecurityConfig` lives in `security/`,** not core — the core must never import it.
  The guard factories already accept explicit `secret`/`get_db`; the config object just
  formalizes and freezes what is already there.

## Architectural Patterns

### Pattern 1: Reserve-before-await pool admission

**What:** Pool capacity is reserved **under lock before** the long `await connect()`, so
two concurrent acquirers can never both pass the `size < max` check.

**When to use:** Every pool admission path (`acquire`, and `connect` warm-up).

**Trade-offs:** Slightly more bookkeeping (reserve/rollback on failure) but eliminates the
check-then-act race without serializing connection creation under the lock. A lock held
across `await connect()` would serialize all acquisitions and is explicitly wrong.

**Example:**
```python
async def _reserve_slot(self) -> None:
    async with self._lock:
        if self._size >= self._max_size:
            raise _NoCapacity
        self._size += 1          # reserve BEFORE awaiting

async def acquire(self, timeout=None):
    while True:
        lease = self._idle.get_nowait() if not self._idle.empty() else None
        if lease is not None:
            if lease.generation == self._generation and await self._healthy(lease):
                lease.in_use = True
                self._in_use.add(lease)
                return lease.db
            await self._discard(lease)          # stale/expired → close + decrement under lock
            continue
        try:
            await self._reserve_slot()
        except _NoCapacity:
            lease = await self._wait_for_idle(timeout)   # queue.get / wait_for
            lease.in_use = True
            self._in_use.add(lease)
            return lease.db
        try:
            db = await self._create_connection()          # await OUTSIDE the lock
        except BaseException:
            async with self._lock:
                self._size -= 1                            # unreserve on failure
            raise
        lease = PooledConnection(db=db, created_at=time.monotonic(), generation=self._generation)
        async with self._lock:
            self._in_use.add(lease)
        return lease.db
```

### Pattern 2: Per-connection lease state (fixes shared `_last_id`)

**What:** `last_id` is stored on the connection handle that performed the insert, never on
the pool. Outside a transaction it is resolved from a **task-scoped** `contextvar` set by
the same task's last `execute()`.

**When to use:** Any pool-level delegation of connection-scoped values.

**Trade-offs:** Preserves the convenience API while removing cross-talk. The stricter
alternative — requiring `last_id()` only inside `transaction()` — is cleaner but breaks
existing raw-`execute` callers; recommend the contextvar approach with a deprecation note.

**Example:**
```python
# pool.py
_last_id_var = contextvars.ContextVar("encino_orm_pool_last_id", default=0)

async def execute(self, qry):
    conn = _current_connection.get()
    if conn is not None:                       # inside transaction(): unambiguous
        result = await conn.execute(qry)
        if _is_insert(qry):
            _last_id_var.set(await conn.last_id())
        return result
    lease = await self.acquire()
    try:
        result = await lease.db.execute(qry)
        if _is_insert(qry):
            _last_id_var.set(await lease.db.last_id())   # task-scoped, not pool-scoped
        return result
    finally:
        await self._release(lease)             # reset-on-return, see Pattern 3

async def last_id(self):
    conn = _current_connection.get()
    if conn is not None:
        return await conn.last_id()
    return _last_id_var.get()                  # never `self._last_id`
```

Note: `Model.insert()` already runs inside `PoolDb.transaction()`, so its `last_id()` is
already correct today. This pattern hardens the *raw* `pool.execute()` path only.

### Pattern 3: Reset-on-return — rollback by default, never implicit commit

**What:** When a connection returns to the pool with an open transaction, **roll back**.
Commits happen only in an explicit scope (`PoolDb.transaction()`, `session()`).

**When to use:** All `release()` paths.

**Trade-offs:** This is a **behavioral break** for callers doing raw `pool.execute(insert)`
outside a transaction (SQLite/MySQL would previously rely on the implicit commit). That is
exactly the "silently commit partial work" bug and should be fixed, but it must be:
1. configurable as `PoolDb(reset_on_release="rollback" | "commit")` (default `"rollback"`),
2. warned on (`DeprecationWarning` when an open transaction is found on release),
3. documented in `CHANGELOG.md`.

**Authoritative basis:** SQLAlchemy's `Pool` defaults to `reset_on_return="rollback"`;
asyncpg's `Pool.release()` calls `Connection.reset()`, which rolls back. Both canonical
async pools choose rollback, not commit.

**Example:**
```python
async def _release(self, lease: PooledConnection):
    try:
        if await lease.db.in_transaction():
            if self._reset_on_release == "rollback":
                await lease.db.rollback()
                warnings.warn("open transaction rolled back on pool release; "
                              "wrap writes in pool.transaction()", DeprecationWarning)
            else:
                await lease.db.commit()
    except Exception:
        await self._discard(lease)      # reset failed → terminate, create fresh next time
        return
    lease.last_used = time.monotonic()
    lease.in_use = False
    self._in_use.discard(lease)
    if self._closing:
        await lease.db.close()
        return
    await self._idle.put(lease)
```

### Pattern 4: Generation counter + background idle reaper

**What:** A monotonic `_generation` invalidates connections after a disconnect event;
a background task trims idle connections above `min_size` and expires connections past
`max_connection_lifetime`.

**When to use:** Pool lifecycle management.

**Trade-offs:** A background task adds shutdown surface — it must be cancellation-safe and
awaited in `close()`. On Windows, `tests/conftest.py` sets the selector event loop policy;
`asyncio.sleep`-based reaping works there, but tests must not leak the task.

**Authoritative basis:** asyncpg uses `expire_connections()` (generation bump — next
acquire replaces) and `max_inactive_connection_lifetime` (default 300 s) to close idle
connections. SQLAlchemy invalidates the whole pool on a disconnect condition.

**Example:**
```python
async def connect(self):
    for _ in range(self._min_size):
        lease = PooledConnection(db=await self._create_connection(), ...)
        await self._idle.put(lease)
        self._size += 1
    self._connected = True
    self._reaper_task = asyncio.create_task(self._reaper())

async def _reaper(self):
    while True:
        await asyncio.sleep(self._reap_interval)
        now = time.monotonic()
        async with self._lock:
            if self._size <= self._min_size:
                continue
            keep = []
            while not self._idle.empty():
                lease = self._idle.get_nowait()
                idle = now - lease.last_used
                expired = (self._max_lifetime is not None
                           and now - lease.created_at > self._max_lifetime)
                if self._size > self._min_size and (idle > self._idle_timeout or expired):
                    self._size -= 1
                    to_close.append(lease)
                else:
                    keep.append(lease)
            for lease in keep:
                self._idle.put_nowait(lease)
        for lease in to_close:                # close OUTSIDE the lock
            await lease.db.close()

async def close(self):
    self._closing = True
    self._connected = False
    if self._reaper_task:
        self._reaper_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reaper_task
    # drain idle; checked-out leases close on release (see Pattern 3 `_closing` branch)
    while not self._idle.empty():
        await (self._idle.get_nowait()).db.close()
    self._size = len(self._in_use)
```

`close()` must **never** close a checked-out connection under the caller; it marks
`_closing` and closes each lease as it is released.

### Pattern 5: Two distinct recovery paths — lock retry vs. disconnect reconnect

**What:** Keep `retry()` (lock/deadlock, backoff, safe to re-run) separate from
`_with_reconnect()` (connection loss, reconnect once). They have different safety rules.

**When to use:** Adapters classify errors; the base applies the policy.

**Trade-offs:** Do **not** reconnect-and-retry inside an open transaction — the write may
have reached the server before the socket dropped, so retrying risks duplicates. SQLAlchemy
documents that `pool_pre_ping` does not recover connections dropped mid-transaction. The
reconnect path therefore applies only when `in_transaction()` is false.

**Example:**
```python
# base.py — new concrete template method
async def _with_reconnect(self, fn):
    try:
        return await fn()
    except Exception as exc:
        if not self.is_disconnect_error(exc) or await self.in_transaction():
            raise                                  # never retry mid-transaction
        await self.close()
        await self.connect(**self._connect_kwargs) # adapter stores kwargs on connect()
        return await fn()                          # single retry

def is_disconnect_error(self, exc: Exception) -> bool:
    return False                                   # adapter override

# pool checkout health (pessimistic, mirrors SQLAlchemy pool_pre_ping)
async def _healthy(self, lease) -> bool:
    if not self._pre_ping and lease.last_used is not None:
        if time.monotonic() - lease.last_used <= self._idle_timeout:
            return True
    return await lease.db.is_alive()
```

Adapter classification is a small hook: e.g. PostgreSQL returns
`asyncpg.ConnectionDoesNotExistError` / `InterfaceError`; each adapter maps its driver's
disconnect exceptions in `is_disconnect_error`.

### Pattern 6: Composition-root DI for configuration (kills module globals)

**What:** Configuration is **data passed at composition time**; request/task state stays in
`contextvars`; no module-level mutable singleton is read during a request.

**When to use:** `security/guard.py` (`SECRET`, `GET_DB`) and `context.py` (`_default_db`).

**Trade-offs:** Touches public signatures (`get_current_user`, `require`, `resolve_db`).
Keep backward-compatible shims that delegate to an injectable object so 0.2.x callers still
work, and mark the shims deprecated.

**Example:**
```python
# security/config.py
@dataclass(frozen=True)
class SecurityConfig:
    secret: str
    get_db: Callable
    algorithms: tuple[str, ...] = ("HS256",)

def security_dependencies(config: SecurityConfig):
    def get_current_user(): ...        # closure over config; no globals
    def require(model: str, op: str): ...
    return get_current_user, require

# context.py
class ConnectionRegistry:
    def __init__(self, default_db=None):
        self._default_db = default_db
    def set_default(self, db): self._default_db = db
    def resolve(self): ...             # current_connection → ambient → default → raise

_registry = ConnectionRegistry()       # single explicit instance, injectable
def set_default_db(db): _registry.set_default(db)          # deprecated shim
def resolve_db(registry: ConnectionRegistry | None = None): ...
```

`create_crud(pool, models, config=...)` and `build_schema(models, config=...)` become the
composition roots that receive config explicitly.

### Pattern 7: Template Method for shared dialect builders

**What:** `Db` provides concrete `insert` / `update` / `delete` that build SQL through
`dialects/builders.py` and delegate only the dialect fragment to an adapter hook.

**When to use:** Replacing the six copy-pasted builders (`sqlite.py:127`, `mysql.py:143`,
`postgresql.py:146`, `mssql.py:180`, `oracle.py:190`, plus MariaDB).

**Trade-offs:** Requires modeling the upsert variance correctly. SQLite uses a *prefix*
(`INSERT OR IGNORE`), PostgreSQL/MySQL use a *suffix* (`ON CONFLICT` / `ON DUPLICATE KEY`),
MSSQL/Oracle use `MERGE`. Model this as a strategy object, not a single string hook.

**Example:**
```python
# dialects/strategies.py
@dataclass(frozen=True)
class InsertStrategy:
    prefix: str = "INSERT"
    suffix: str = ""
    requires_conflict_target: bool = False

SQLITE = InsertStrategy(prefix="INSERT OR REPLACE")   # replace mode
PG     = InsertStrategy(suffix="ON CONFLICT ({target}) DO UPDATE SET {updates}",
                        requires_conflict_target=True)
# adapters override:
#   def _insert_strategy(self, *, replace, ignore_duplicated, conflict) -> InsertStrategy

# dialects/builders.py
def build_insert(table, data, *, strategy, conflict=None):
    table = _check_identifier(table, "tabla")                    # SECURITY: one choke point
    cols = [_check_identifier(c, "columna") for c in data]
    ph = ",".join("{%d}" % i for i in range(len(cols)))
    sql = f"{strategy.prefix} INTO {table} ({','.join(cols)}) VALUES ({ph})"
    if strategy.suffix:
        sql += " " + strategy.suffix.format(target=..., updates=...)
    return Query(sql, list(data.values()))

# base.py
def insert(self, tabla, data, ignore_duplicated=False, replace=False, conflict=None):
    return build_insert(tabla, data,
                        strategy=self._insert_strategy(replace=replace,
                                                       ignore_duplicated=ignore_duplicated,
                                                       conflict=conflict),
                        conflict=conflict)
```

This single seam fixes the security concern ("low-level builders do not validate
identifiers") for all six engines at once, and removes the divergence risk that already
exists (MySQL/MariaDB lacking `conflict`, PostgreSQL defaulting to `columns[0]`).

## Data Flow

### Acquire / Release Flow (target)

```
caller
  │  acquire(timeout)
  ▼
PoolDb ── idle queue hit? ──yes──► generation match? ──yes──► is_alive / pre_ping ──► lease.db
  │                                   │no                          │fail
  │                                   ▼                            ▼
  │                              discard+close            discard+close
  │
  └─ no idle ─► lock{ size<max ? reserve : wait } ─► await connect() ─► PooledConnection
                                                        │fail
                                                        ▼
                                                  lock{ size -= 1 } ─► raise / wait

caller
  │  release(lease)
  ▼
PoolDb ─► in_transaction? ──yes──► reset_on_release=rollback ─► rollback (+DeprecationWarning)
  │                                   │commit (opt-in)
  │                                   ▼
  │                              commit
  └─► reset ok? ──no──► discard + close (next acquire creates fresh)
        │yes
        ▼
   closing? ──yes──► close now
        │no
        ▼
   idle queue.put(lease)
```

### Transaction Flow (explicit scope — unchanged contract)

```
pool.transaction()
  ├─ lease = acquire()
  ├─ _current_connection.set(lease.db)     # contextvar: same conn for all nested calls
  ├─ async with lease.db.transaction():
  │      Model.insert() → execute() → routes to _current_connection (same conn)
  │                     → last_id()  → same conn's last_id   [correct by construction]
  ├─ commit on clean exit / rollback on exception (adapter.transaction)
  └─ finally: _current_connection.reset(); _release(lease)   [reset-on-return]
```

### Reconnect Flow (non-pool, direct `Db`)

```
execute/fetch_* → _with_reconnect(fn)
   fn raises
      ├─ is_disconnect_error? ──no──► re-raise
      ├─ in_transaction()?     ──yes─► re-raise (unsafe to retry)
      └─ yes, no txn ──► close() → connect(**kwargs) → fn() once
```

### Query Build Flow (performance + security)

```
Model.insert → Db.insert → dialects.build_insert
                              ├─ _check_identifier(table, cols)     # validation
                              └─ Query("{0},{1}", params)           # {n} placeholders
                                        │
                                        ▼
                              execute(qry) → qry.compiled(dialect)  # memoized once
                                        │
                                        ▼
                              adapter._prepare(qry) → native placeholders
```

### Config Injection Flow (optional layers)

```
app startup
   ├─ config = SecurityConfig(secret=..., get_db=session(pool))
   ├─ get_current_user, require = security_dependencies(config)
   └─ router = create_crud(pool, models, config=config)
        └─ handlers close over config — no module globals read per request
```

### Key Data Flows

1. **Connection identity:** `acquire()` → `PooledConnection` → `_current_connection`
   contextvar → `resolve_db()`; every operation on a task resolves the same lease.
2. **Write visibility:** writes become durable only via `transaction()` / `session()`
   commit; release never commits.
3. **Invalidation:** disconnect during operation → pool `_generation` bump → all idle
   leases expire on next acquire; in-use lease discarded on release.
4. **Configuration:** composition root → config object → closures; never module global.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Low concurrency (dev/CI) | `min_size=2, max_size=10`; reaper optional. Rollback-on-return may surface latent raw-`execute` writes as `DeprecationWarning` — fix call sites. |
| Moderate concurrency (internal production) | Enable `pre_ping` + `max_connection_lifetime` (e.g. 1800 s) to survive DB restarts and PgBouncer/proxy idle kills; keep `max_size` near DB `max_connections / app_instances`. |
| High concurrency / many instances | Bound `max_size` per process; move to a server-side pooler (PgBouncer) and set `pre_ping` + shorter `idle_timeout`; `max_queries`-style recycling prevents unbounded server-side statement-cache growth. |

### Scaling Priorities

1. **First bottleneck: pool over-subscription.** Today's `acquire()` race lets `_size`
   exceed `max_size`, exhausting the database. Fix first — it is a correctness, not perf,
   issue.
2. **Second bottleneck: stale/idle connections.** No reaper and no recycle means idle
   connections are killed by the server/proxy and surface as errors on next use. Fix with
   reaper + `pre_ping` + generation invalidation.
3. **Third bottleneck: per-row round-trips in `copy_table`** and per-call regex placeholder
   translation. Address after correctness; they are throughput concerns.

## Anti-Patterns

### Anti-Pattern 1: Holding a lock across `await connect()`

**What people do:** Wrap the whole `acquire()` in `async with self._lock:` to "make it safe".
**Why it's wrong:** Serializes every connection creation and every acquisition behind the
slowest network handshake; converts a race into a throughput cliff.
**Do this instead:** Reserve the slot under the lock, release the lock, then `await connect()`
(Pattern 1).

### Anti-Pattern 2: Connection state on the pool

**What people do:** Store `last_id`, transaction flags, or health on the `PoolDb` instance.
**Why it's wrong:** The pool is shared across tasks; any per-connection value becomes
cross-talk under concurrency (the current `_last_id` bug).
**Do this instead:** Put state on `PooledConnection`; use `contextvars` for the current
task's lease (Pattern 2).

### Anti-Pattern 3: Implicit commit on release

**What people do:** "Clean up" a returned connection by committing any open transaction.
**Why it's wrong:** Commits partial state the caller never declared complete; makes
atomicity depend on object lifetime.
**Do this instead:** Roll back on return; commit only in explicit scopes (Pattern 3).
This is the SQLAlchemy and asyncpg default.

### Anti-Pattern 4: Retrying a disconnect inside an open transaction

**What people do:** Catch connection loss and transparently reconnect + retry.
**Why it's wrong:** The statement may have committed before the socket dropped; a retry can
duplicate writes. SQLAlchemy explicitly notes pre-ping cannot recover mid-transaction drops.
**Do this instead:** Only reconnect when `in_transaction()` is false (Pattern 5); surface
the error otherwise.

### Anti-Pattern 5: Module-level mutable config read at request time

**What people do:** Set `SECRET` / `GET_DB` / `_default_db` globals and read them per request.
**Why it's wrong:** Any import or test can overwrite them process-wide; multi-tenant and
test isolation break silently.
**Do this instead:** Inject frozen config objects at composition roots; keep deprecated
shims delegating to an injectable registry (Pattern 6).

### Anti-Pattern 6: Copy-pasting dialect SQL into each adapter

**What people do:** Maintain six near-identical `insert`/`update`/`delete` builders.
**Why it's wrong:** Security fixes (identifier validation) and correctness fixes land in
one dialect and silently miss the others — already visible today.
**Do this instead:** One shared builder + small dialect hook overrides (Pattern 7).

### Anti-Pattern 7: `exec()`-generated handlers

**What people do:** String-concatenate function source and `exec` it at registration.
**Why it's wrong:** No static analysis, no IDE navigation, runtime-only syntax errors,
brittle signature derivation for composite keys.
**Do this instead:** Closures (GraphQL `_create_resolver` already demonstrates this) and
`inspect.Signature` / `__signature__` assignment for FastAPI path params (validate this
technique in the phase — fallback is `request.path_params` + explicit pydantic validation).

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `model/` ↔ `pool.py` | `resolve_db()` / `_current_connection` contextvar | Contract unchanged; pool internals invisible to ORM layer |
| `pool.py` ↔ adapters | `Db` ABC methods + new hooks (`is_disconnect_error`, `_insert_strategy`) | Adapters must not import pool |
| `base.py` ↔ `dialects/` | Direct function calls (pure) | `dialects/` must not import adapters or pool (no cycles) |
| adapters ↔ `Query` | `query.compiled(dialect)` / `_prepare` | Compilation cached on `Query`; adapter stays the owner of native syntax |
| optional layers ↔ config | Injected `SecurityConfig` / registry | Core must never import `security.config` |
| `http/` ↔ `model/` | Closures over `model`/`get_db` | Replace `exec` without changing route paths or response models |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| PostgreSQL (`asyncpg`) | Direct `asyncpg.connect` | `is_disconnect_error` → `ConnectionDoesNotExistError`/`InterfaceError`; `last_id` uses `lastval()` (transaction-scoped) |
| MySQL/MariaDB (`aiomysql`) | Direct connect | `cursor.lastrowid` per connection; no autocommit — reset-on-return is critical |
| SQLite (`aiosqlite`) | Direct connect | WAL; `last_insert_rowid()`; `is_lock_error` on "locked"/"busy" |
| SQL Server (`aioodbc`) | Direct connect | Tuple rows via `_rows._rows_to_dicts`; `MERGE` upsert |
| Oracle (`oracledb`) | Direct connect | Tuple rows; `MERGE` upsert; DDL implicit-commits (affects migration atomicity) |
| Redis (`redis`) | Optional cache backend | Lazy import; not on the pool path |

## Build Order & Dependencies

This ordering is derived from the dependency graph, not from severity alone. Items at the
same level can proceed in parallel.

```text
Level 0 (guards everything, independent)
  └─ CI gates: ruff + mypy + pytest-cov + dependency scan
     (catches regressions from every later change)

Level 1 (foundation seam — unblocks correctness + security)
  └─ dialects/builders.py + Query compiled-SQL cache
       ├─ fixes identifier validation for all six engines
       └─ prerequisite for sync_schema identifier fix + copy_table batching

Level 2 (pool correctness — highest production risk)
  ├─ PooledConnection handle + reserve-before-await acquire
  ├─ per-connection/task-scoped last_id
  ├─ reset-on-return (rollback default, configurable, warned)
  └─ reaper + generation invalidation + safe close()
     depends on: Level 1 only for `_is_insert` helper; can start in parallel

Level 3 (resilience — depends on Level 2)
  ├─ is_disconnect_error per adapter
  ├─ Db._with_reconnect template (non-transactional only)
  └─ pre_ping + max_connection_lifetime policy

Level 4 (config hygiene — independent of Levels 2–3)
  ├─ ConnectionRegistry replacing _default_db
  └─ SecurityConfig + guard factories; deprecate globals

Level 5 (optional-layer quality — depends on Level 4 for injected config)
  ├─ replace exec() with closures/__signature__ in http/routes.py
  └─ GraphQL per-build namespace (stop mutating module namespace)

Level 6 (performance — depends on Level 1 + Level 2)
  ├─ copy_table batching (reuse insert_many SQL generator)
  └─ benchmarks with numeric CI targets
```

**Hard ordering constraints:**

- **Level 1 before Level 2/6** — `_is_insert` and validation must have one home before the
  pool and transfer code are touched, or the same logic gets duplicated again.
- **Level 2 before Level 3** — reconnect/health needs the `PooledConnection` handle and
  the generation counter to exist.
- **Level 2 before any pool concurrency tests can be meaningful** — the tests are the
  verification of Level 2, and CONCERNS.md flags pool concurrency tests as entirely absent.
- **Level 4 before Level 5** — `create_crud`/`build_schema` should accept config at the
  same time their handler generation is rewritten, so signatures change once.
- **CI gates (Level 0) before everything** — without lint/type/coverage, a hardening
  refactor of this size has no safety net.

**Phase-level guidance for the roadmap:**

- Level 0 is a standalone, low-risk phase.
- Levels 1 + 2 together form the core reliability phase; splitting them risks a half-applied
  validation seam.
- Level 3 is a distinct phase (different failure domain: network loss vs. concurrency).
- Levels 4 + 5 group as "architecture hygiene / optional layers" — both are about removing
  indirection (`exec`, globals) rather than runtime correctness.
- Level 6 is a final performance phase with benchmarks as the done criterion.

## Sources

- SQLAlchemy 2.0 Connection Pooling — `reset_on_return` (default `"rollback"`), `pool_pre_ping`, optimistic/pessimistic disconnect handling, `PoolEvents.reset`: https://docs.sqlalchemy.org/en/20/core/pooling.html (HIGH)
- SQLAlchemy 2.0 asyncio extension — `AsyncConnection.invalidate()`: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html (HIGH)
- asyncpg `Pool.release()` source — resets (rolls back) on release, terminates on reset failure, re-arms inactivity timer: https://magicstack.github.io/asyncpg/current/_modules/asyncpg/pool.html (HIGH)
- asyncpg `create_pool()` — `max_inactive_connection_lifetime` (default 300 s), `max_queries` (default 50000), `setup`/`init`/`reset` hooks, `expire_connections()`: https://magicstack.github.io/asyncpg/current/api/index.html (HIGH)
- Codebase analysis — `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md` (2026-09-17) (HIGH)
- `encino_orm` source read directly: `pool.py`, `context.py`, `base.py`, `sqlite.py`, `postgresql.py`, `security/guard.py`, `migration.py`, `model/cached.py`, `http/routes.py`, `graphql/schema.py`, `transfer.py` (HIGH)
- FastAPI `Request.path_params` and path-parameter semantics: https://fastapi.tiangolo.com/reference/httpconnection (MEDIUM — `__signature__` technique is a community pattern, flag for phase validation)

---

*Architecture research for: production-hardening an async multi-engine Python ORM*
*Researched: 2026-09-17*
