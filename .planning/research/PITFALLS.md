# Pitfalls Research

**Domain:** Production-hardening a brownfield async multi-engine Python ORM (`encino_orm` 0.2.6 → 0.3.0)
**Researched:** 2026-09-17
**Confidence:** HIGH (all code-level claims verified by reading the repo; async/CI/coverage/SemVer/DDL claims verified against official docs — see Sources)

> **Framing.** The failure mode of a *hardening* milestone is not "the fix didn't work." It is
> **"the fix worked, the tests went green, and the library is now less trustworthy than before."**
> Every pitfall below is a way that hardening makes a working library worse: gates that pass while
> proving nothing, security fixes that break legitimate use, concurrency fixes that deadlock,
> performance fixes that exceed protocol limits, and release changes that reach users who never
> opted in. Phase labels reference `ARCHITECTURE.md` Levels and `FEATURES.md` `TS-n` IDs so the
> roadmap can reuse them directly.

---

## Critical Pitfalls

### Pitfall 1: Green CI that verifies nothing — dialect suites silently skip

**What goes wrong:**
CI reports success while zero tests executed against four of the six engines. `tests/test_postgresql.py:67`, `test_oracle.py:103`, `test_mssql.py:124,135`, `test_mariadb.py:38` and `test_redis_cache.py:28,35` all catch a connection exception and call `pytest.skip(...)`. A skipped suite is a *passing* suite. `.github/workflows/ci.yml:25-52` starts only MySQL and PostgreSQL, so MariaDB, SQL Server, Oracle and Redis always skip. The `COUNT(*)` bug is the direct consequence: it was never skipped *and* never failed, because it never ran.

Worse, the skip is triggered by a bare `except Exception` around connection setup. A broken or renamed driver, a typo in an env var, or a wrong password all produce **skip, not failure**. Renaming `ENCINO_ORM_POSTGRES_HOST` in CI would silently delete all PostgreSQL coverage and CI would stay green.

**Why it happens:**
"Skip when the service isn't there" is the correct ergonomics for *local* development and the wrong contract for *CI*. Developers copy the local pattern into the CI path because both use the same fixture. Nobody adds a "was this engine actually exercised?" assertion because a green checkmark feels like verification.

**How to avoid:**
1. Introduce an explicit requirement switch: `ENCINO_ORM_REQUIRE_ENGINES=postgresql,mariadb` (or one `ENCINO_ORM_REQUIRE_<ENGINE>` per engine). The connection fixture calls `pytest.fail(...)` instead of `pytest.skip(...)` when the engine is required, and `skip` otherwise. Set it per engine-job in CI.
2. Never let `except Exception` decide skip-vs-fail. Catch the *specific* driver connection error type (`asyncpg.PostgresError`, `oracledb.Error`, `pyodbc.Error`, `redis.RedisError`) and let import errors, `TypeError`, and `KeyError` fail loudly.
3. Add a post-run gate that parses the JUnit XML and fails if `skipped > 0` in a required-engine job. `pytest --junitxml=report.xml` plus a 10-line check is enough; there is no pytest flag that does this correctly on its own.
4. Add `--strict-markers` and `xfail_strict = true` to `[tool.pytest.ini_options]`. `xfail` is a second silent-pass mechanism and is currently unguarded.

**Warning signs:**
- CI duration does not grow after adding an engine.
- `pytest -q` output shows `NNN skipped` and nobody can name which tests.
- An engine-specific test file has never failed in CI history (`git log` shows no failure/red build touching it).
- Local `uv run pytest` and CI `uv run pytest` report the same skip count.

**Phase to address:**
**P1 — Safety Net (Level 0).** The requirement switch and the skip gate must land *before* any correctness fix, otherwise every subsequent "fix verified" claim is unverifiable. Directly enables **TS-28** and **TS-29**.

---

### Pitfall 2: Aggregate line coverage that masks untested dialect paths

**What goes wrong:**
Adding `pytest-cov` with `fail_under = 85` will pass on day one — while the code that is actually broken is untested. This is not hypothetical: `encino_orm/model/model.py:792` is `return row["COUNT(*)"] if row else 0`. That line is **executed** by the SQLite test suite, so coverage.py marks it covered. It raises `KeyError: 'COUNT(*)` on PostgreSQL because asyncpg returns the key `count`. The bug and the coverage both come from the same line.

The general shape: for six engines there are six result-shape contracts and one shared code path. Coverage is computed over *shared* lines, so dialect-specific *behavior* is invisible. A single `fail_under` number is structurally incapable of detecting this class of bug.

`coverage.py`'s `fail_under` is also config-only (not a CLI/report parameter), so there is no per-file threshold escape hatch: you cannot say "90% overall but 100% for `postgresql.py`" in one run.

**Why it happens:**
Coverage is treated as a quality score rather than a measurement of *which behaviors were exercised*. The number is computed once across the whole session, so one engine's tests pay for another engine's untested lines. `COVERAGE` looks like a gate but is really a floor on the union.

**How to avoid:**
1. **Per-engine coverage runs, combined with `[paths]`.** Run the suite once per engine with a distinct data file, then `coverage combine`. Use `[tool.coverage.paths]` so the six runs merge correctly. This yields *union* coverage — still not per-dialect, but it makes the "one engine covers for all" illusion explicit and stops it being accidental.
2. **Require per-dialect integration tests as the done criterion, not a coverage number.** Each `TS-n` correctness fix gets an assertion in every engine's test module, or an explicit written justification for why the engine cannot be tested. `FEATURES.md` already frames `TS-28` as the gate for `TS-10`/`TS-11`/`TS-18`; enforce that.
3. **Use `dynamic_context = "test_function"`** so `coverage html --contexts` answers "which test covered `model.py:792`?" The answer will be "a SQLite test," which is the finding.
4. **Add per-dialect coverage as a separate CI job** that runs only `tests/test_<engine>.py` with `--cov=encino_orm.<engine>` and its own `fail_under`. This is the only mechanism that produces a dialect-specific threshold without a custom script.
5. **Consider mutation testing (`mutmut`) on the six dialect modules** instead of chasing a coverage number. Mutation score is the metric that distinguishes "line executed" from "behavior asserted," and the dialect modules are small enough for it to be practical.
6. **Do not turn on `fail_under` at all until per-engine tests exist.** A threshold set before the tests is a permanent license to under-test.

**Warning signs:**
- `pytest --cov` reports a high number but `tests/test_postgresql.py` has no assertion on `count`, `paginate`, `list_tables`, `sync_schema`, or `last_id`.
- A bug is found in production on engine X that "was covered."
- Coverage does not change when you delete an engine's test file.
- `# pragma: no cover` appears in dialect branches.

**Phase to address:**
**P1 — Safety Net (Level 0)** for tooling and context configuration; **P2 — Dialect Seam & Engine Parity (Level 1)** for the per-engine tests that make the number meaningful. Directly governs **TS-27**.

---

### Pitfall 3: The pool race "fix" deadlocks, or the release-policy "fix" breaks documented autocommit

**What goes wrong:**
Two independent traps in the same 40 lines of `pool.py`:

**(a) A naive lock around `acquire()` deadlocks.** `PoolDb.acquire()` (`pool.py:111-146`) blocks on `await self._pool.get()` when the pool is exhausted. If you wrap the whole method in `async with self._lock`, a task holding the lock while waiting for a connection blocks every task that would *release* a connection — the release path also needs the lock. Result: permanent deadlock, or a cascade of `PoolExhaustedError` under load. The correct fix is narrow: reserve the slot (`self._size += 1`) **before** `await self._create_connection()`, and guard only the bookkeeping (`_size`, `_connections`, `_last_used`), never the queue wait.

**(b) Changing release-from-commit to release-from-rollback silently removes a documented feature.** `pool.py:199-204` and `pool.py:239-242` commit any open transaction before returning the connection. `tests/test_pool.py:202-213` (`TestPoolStandaloneCommit.test_standalone_operation_commits`) **asserts this behavior**, and `tests/test_pool.py:293-311` (`TestPoolAutocommit.test_dml_visible_across_connections`) depends on it: `await pool.execute(pool.insert("t", {...}))` outside a transaction must persist. `FEATURES.md` `TS-2` recommends inverting this to rollback (matching SQLAlchemy's `reset_on_return="rollback"`). That is the right long-term contract — but shipped naively it turns every standalone `pool.execute(INSERT)` into a **silently discarded write**. A user's "insert then read" code returns nothing and no error is raised.

The correct design is not "commit → rollback." It is an *explicit, documented* policy with three distinct paths: standalone DML = autocommit (commit on success), exception inside the operation = rollback, and leftover open transaction at release = rollback **plus a warning**. Rollback-on-leftover only works once standalone operations stop leaving transactions open — which is a change to `_run`/`execute`, not to `release()`.

**Why it happens:**
Both are textbook race conditions where the intuitive fix (lock it / flip the default) is wrong because the existing behavior is load-bearing. The commit-on-release was added deliberately (the comment at `pool.py:199-201` says so) to make writes visible across pooled SQLite connections. Reverting it without preserving that use case breaks the exact scenario it was written for.

**How to avoid:**
1. Fix the race by **reserving before awaiting**, not by locking. Add a concurrency test that asserts `pool._size <= max_size` after N simultaneous `acquire()` calls where connection creation is deliberately slow (a `FakeDb.connect` that `await asyncio.sleep(0.05)`).
2. Treat `TS-2` as a **breaking change requiring a deprecation release** (see Pitfall 9). Add a `reset_on_return` parameter with the old behavior available, emit a `DeprecationWarning` when it is relied upon, and document the change in `CHANGELOG.md`.
3. Do not touch `release()` until standalone operations no longer leave transactions open. Sequence: (i) make `_run`/`execute` commit-or-rollback explicitly per operation, (ii) then make `release()` rollback leftovers and warn, (iii) then change `TestPoolStandaloneCommit` to assert the new policy *and* keep `TestPoolAutocommit` passing.
4. Never assert private state as the *goal*. `test_max_size_creates_and_reuses` asserting `pool._size == 5` is fine as a diagnostic; the invariant that matters is `_size <= _max_size` under concurrency.

**Warning signs:**
- A concurrency test that passes because the pool was never actually saturated (all `acquire()` calls resolve from the queue).
- `TestPoolAutocommit` deleted or weakened during the pool refactor instead of preserved.
- The pool refactor diff touches `release()` before it touches `_run()`/`execute()`.
- `asyncio.Lock` acquired in `acquire()` before `await self._pool.get()`.

**Phase to address:**
**P4 — Pool Correctness & Concurrency (Level 2).** `TS-1`, `TS-2`, `TS-8`, `TS-9`, `TS-29`. This is the highest-risk phase in the milestone; it must not be split across releases.

---

### Pitfall 4: Refactoring the pool against tests that assert private state and fakes that validate the fake

**What goes wrong:**
The existing pool tests will actively obstruct the fix and then give false confidence afterwards.

- `tests/test_pool.py:102,103,114,115,143,145` assert `pool._size`, `pool._connections`, `pool._last_used`. Any structural fix (introducing a `PooledConnection` handle, moving `_last_used` onto the connection) breaks them. The path of least resistance is to update the assertions — which converts the test from "verifies the invariant" into "describes the implementation." After that, the test can no longer catch a regression.
- `FakeDb.execute` (`tests/test_pool.py:58-62`) sets `self._last = 42` and returns it. `TestPoolTransactionScope.test_operations_use_held_connection` then asserts `rid == 42`. This verifies the **fake's** behavior, not the engine's. The `COUNT(*)` bug is exactly this failure mode at the engine level: `FakeDb.fetch_one` returns whatever the test wants, so the real asyncpg result-key contract is never exercised.
- `test_delegation` (`tests/test_pool.py:122-124`) passes the string `"SELECT 1"` where a `Query` is required. `FakeDb` accepts it. The real `Db.fetch_all` calls `self._prepare(qry)` and would fail. The test therefore documents an API misuse as expected behavior.
- `test_unsupported_engine` (`tests/test_pool.py:321-323`) asserts `pytest.raises(Exception)`. This passes for *any* exception, including a `TypeError` from a typo in `PoolDb.__init__`. `UnsupportedEngineError` is imported but not used here.
- `pool_module._ENGINES` is monkeypatched (`tests/test_pool.py:86`) — a global registry mutation that makes it easy to accidentally test against a fake engine while believing you are testing a real dialect.

**Why it happens:**
Unit tests written against a class with no public seam will reach into privates. Once written, they are treated as spec. During a refactor, "make the tests pass" and "preserve the invariant" diverge, and the faster option wins.

**How to avoid:**
1. **Before touching `pool.py`, write characterization tests for the invariants** and mark them as the ones that must not be weakened: (a) `_size <= max_size` under N-way concurrent acquire; (b) a released connection is either healthy or replaced; (c) `close()` is idempotent and closes every connection exactly once; (d) writes performed inside `transaction()` are all-or-nothing. These are behavior-level and survive refactoring.
2. **Replace private-state assertions with public observations** where possible (`len(pool.stats)`, `pool.stats["size"]`, actual query visibility) rather than deleting them.
3. **Add one real-engine pool test per engine** (or at minimum SQLite-file + PostgreSQL) that exercises `acquire → insert → release → acquire → read` through the real driver. This is the test that would have caught `COUNT(*)` and would catch a bad `last_id`.
4. **Narrow `pytest.raises(Exception)` to the specific type.** Add `ruff` rule `PT011` (`pytest.raises` too broad) to the lint config so this cannot regress.
5. Add `filterwarnings = ["error"]` (with targeted `ignore` entries) so `DeprecationWarning`s raised by the new pool policy actually fail tests instead of being scrolled past.

**Warning signs:**
- The pool fix PR contains more changes to `tests/test_pool.py` assertions than to `pool.py` behavior.
- A refactor that reduces the number of tests in `test_pool.py`.
- No test file exists that connects a `PoolDb` to a real PostgreSQL/MySQL instance.
- `pytest.raises(Exception)` anywhere in `tests/`.

**Phase to address:**
**P1 — Safety Net (Level 0)** for characterization tests and lint rules; **P4 — Pool Correctness (Level 2)** for the refactor they protect. Feeds **TS-29**.

---

### Pitfall 5: `contextvars` connection affinity leaks into child tasks — two tasks share one connection

**What goes wrong:**
`PoolDb.transaction()` (`pool.py:162-171`) and `session()` (`pool.py:277-308`) store the active connection in a module-level `ContextVar` (`pool.py:29`). `asyncio.create_task()` and `asyncio.gather()` **copy the caller's context** into the child task. So this code:

```python
async with pool.transaction():
    await asyncio.gather(
        pool.execute(Query("INSERT INTO a ...", [])),
        pool.execute(Query("INSERT INTO b ...", [])),
    )
```

gives **both** child tasks the same connection and runs two operations concurrently on one driver connection. asyncpg raises `InterfaceError: cannot perform operation: another operation is in progress`; aiomysql/oracledb corrupt the protocol stream; SQLite may interleave cursors. It also means the `finally: await self.release(db)` in `transaction()` can return a connection to the pool while a child task still holds the contextvar and is mid-query.

The mirror-image trap is the opposite mistake: assuming the contextvar *does* propagate. A value `.set()` inside a gathered child does **not** propagate back to the parent, so a "fix" that relies on that is silently a no-op.

**Why it happens:**
`ContextVar` reads like "thread-local, therefore task-local." It is task-local for *writes*, but child tasks inherit a *copy* of the parent's context, so reads inside children see the parent's value. That asymmetry is the bug.

**How to avoid:**
1. **Bind the owning task into the contextvar.** Store `(asyncio.current_task(), connection)` and raise a clear `ConnectionError("connection is bound to another task")` if a different task tries to use it. This turns a protocol-level corruption into an actionable error.
2. Document the rule explicitly: *a pooled transaction-scoped connection is not safe to share across tasks; pass the connection explicitly to child tasks instead of relying on ambient resolution.*
3. Add a regression test: inside `pool.transaction()`, `asyncio.gather` two operations and assert either (a) both succeed because they each acquired their own connection, or (b) a typed error is raised — never a driver-level `InterfaceError` or a hang.
4. Reconcile with `set_default_db` (`context.py:19-34,47-61`): the process-wide default singleton has the same multi-task hazard and additionally leaks across tests. Any concurrency work should include a teardown that clears it.

**Warning signs:**
- Production logs show driver-level "operation in progress" / protocol errors only under load.
- `asyncio.gather` or `create_task` appears inside a `pool.transaction()` / `session()` block in docs or tests.
- A test that creates tasks inside a transaction passes only when the tasks are awaited sequentially.

**Phase to address:**
**P4 — Pool Correctness & Concurrency (Level 2).** Overlaps with `TS-1`/`TS-8`/`TS-9`; the task-ownership check belongs in the same `PooledConnection` refactor. Related to `TS-14` (transaction rollback semantics) as a regression guard.

---

### Pitfall 6: Believing `last_id()` can be fixed by bookkeeping — PostgreSQL's `lastval()` is session-scoped, not transaction-scoped

**What goes wrong:**
`postgresql.py:226-228` implements `last_id()` as `SELECT lastval()`. `PoolDb` then caches that into a single shared `self._last_id` (`pool.py:63,236-237`). `ARCHITECTURE.md` describes `lastval()` as "transaction-scoped" — **it is not.** `lastval()` returns the last sequence value obtained by `nextval` **in the current session**, regardless of transaction boundaries. Consequences:

- Outside a transaction, the pooled connection is shared; between the `INSERT` and the `lastval()` call, another task can run its own `INSERT` on that connection (or the connection is a different one from the pool entirely) → **the wrong row's id is returned**, with no error.
- Inside a transaction, `lastval()` is still wrong if any trigger or rule performs an insert into another table with its own sequence.
- If the `INSERT` did not touch a sequence at all, `lastval()` returns a stale value or raises `ObjectNotInPrerequisiteState`.
- For MSSQL (`mssql.py:309-310`) and Oracle (`oracle.py:306-307`) `last_id()` returns a cached `self._last_id` from the last execute — same cross-talk under a pool.

`TS-8` ("store per-connection") reduces but does not eliminate this: a pooled connection handed to task B will return task A's `lastval()` unless the value is captured at the moment of the insert. The only correct answer on PostgreSQL is `INSERT ... RETURNING <pk>`, which changes `Db.insert` from "build a `Query`" to "build a `Query` whose result carries the id" — an **API change** to `execute()`'s return contract (`postgresql.py:187-193` returns `_rowcount`).

**Why it happens:**
`lastval()` is the PostgreSQL analogue of MySQL's `LAST_INSERT_ID()`, and people assume the scoping matches. MySQL's `LAST_INSERT_ID()` *is* connection-local and unaffected by other tables' inserts; PostgreSQL's `lastval()` is session-local and *is* affected. The similarity of the names hides the semantic gap. Also, `last_id()` works perfectly in every sequential SQLite test, so it looks solved.

**How to avoid:**
1. **Do not claim `TS-8` is done by moving `_last_id` onto the connection.** That is necessary but not sufficient. Define the contract explicitly per engine: PostgreSQL/Oracle → `RETURNING`; MySQL/MariaDB → `cursor.lastrowid` captured immediately after the same `execute`; SQLite → `last_insert_rowid()` captured immediately; MSSQL → `SCOPE_IDENTITY()` / `OUTPUT INSERTED.<pk>`.
2. **Capture the id inside the same operation that performs the insert**, never in a separate call. The API shape that makes this safe is returning the id from `execute`/`insert` rather than exposing a separate `last_id()` lookup. Treat the separate `last_id()` as deprecated once the safe path exists.
3. Add a concurrency regression test per engine: N concurrent inserts on a pooled connection, each asserting it received its own id. This test fails today and is the acceptance evidence for `TS-8`.
4. Correct the `ARCHITECTURE.md` claim about `lastval()` being transaction-scoped, so the roadmap does not build on a false premise.

**Warning signs:**
- A "per-connection `last_id`" fix with no `RETURNING`/`SCOPE_IDENTITY` change and no concurrent test.
- `last_id()` still exists as a public method callable *after* the operation completed and the connection returned.
- The concurrency test for `last_id` runs inserts sequentially.

**Phase to address:**
**P4 — Pool Correctness & Concurrency (Level 2).** `TS-8`. Because it is an API-shape decision, it must be settled *before* the release phase and documented as breaking if `last_id()` semantics change.

---

### Pitfall 7: Batching `copy_table` with a fixed batch size blows past per-dialect parameter and term limits

**What goes wrong:**
`CONCERNS.md` recommends "batch rows (e.g. 500-1000) into multi-value INSERTs." That number is not portable and will fail on at least two of the six engines:

| Engine | Binding limit | Consequence of a 1000-row × 8-column batch (8000 params) |
|--------|---------------|----------------------------------------------------------|
| SQLite | `SQLITE_MAX_VARIABLE_NUMBER` = **999** (pre-3.32) or **32766** (≥3.32); `SQLITE_MAX_COMPOUND_SELECT` = **500** | 8000 params exceeds 999 on older builds; a multi-row `VALUES` is compiled as a compound SELECT, so >500 rows can hit "too many terms in compound SELECT" |
| SQL Server | **2100** parameters per statement | 8000 params → hard error, every time |
| PostgreSQL (`asyncpg`) | ~**32767** (protocol int16) — MEDIUM confidence, verify empirically | Passes at 8000; fails at ~4000 rows × 8 cols |
| Oracle | 65535 binds, but `IN` lists are capped at 1000; array DML is the intended path | Multi-row `VALUES` works but is not the idiomatic bulk path |
| MySQL/MariaDB | `max_allowed_packet` (bytes, not count) | Large batches fail with a packet-size error, not a param-count error |

Additionally, a batched `copy_table` changes failure semantics: a single multi-row INSERT is atomic per statement, so a failure mid-batch leaves earlier batches committed. Today's per-row loop leaves a *different* partial state. Neither is wrong, but the change must be documented or the batch must be wrapped in a transaction.

**Why it happens:**
Batch sizing is derived from "rows per round-trip" intuition, ignoring that the real constraint is *parameters per statement*, which depends on column count and on the engine. SQLite's limit is doubly surprising because it is a *compile-time* constant that varies by build, and because the multi-row `VALUES` → compound-SELECT mechanism is not obvious.

**How to avoid:**
1. Compute batch size per engine as `batch_rows = min(MAX_PARAMS // n_columns, MAX_ROWS)`, with `MAX_PARAMS`/`MAX_ROWS` as per-dialect class attributes (e.g. SQLite `999`/`500`, MSSQL `2100`, PostgreSQL `32000`). Never hardcode a row count.
2. For Oracle and PostgreSQL, prefer array binding / `executemany` over literal multi-row `VALUES` where the driver supports it (asyncpg's `executemany`, oracledb's `executemany`), which sidesteps the param-count issue entirely.
3. Wrap each batch in an explicit transaction and document the partial-failure semantics. Assert row counts after a copy in the test, not just that it did not raise.
4. **Measure before optimizing.** `transfer.py:155-167` is a genuine round-trip bottleneck, so batching is the right call — but prove the win with a benchmark (Pitfall 11) and record the batch-size formula alongside it.

**Warning signs:**
- A literal `BATCH_SIZE = 500` or `1000` in `transfer.py`.
- `copy_table` tests run only against SQLite (where the limit is highest on modern builds and the failure is invisible).
- A "fix" that raises `max_allowed_packet` or tells users to change server settings instead of sizing batches.
- No test with a wide table (e.g. 30+ columns) where the param budget is exhausted at a low row count.

**Phase to address:**
**P7 — Performance & Benchmarks (Level 6)**, with the per-dialect limit constants landing in **P2 — Dialect Seam (Level 1)** so the seam owns them. `TS-38`, gated by `TS-39`. Related: `TS-15` (bulk atomicity).

---

### Pitfall 8: "Atomic migration" wrapped in a transaction on MySQL/MariaDB/Oracle is security theater

**What goes wrong:**
`TS-11` proposes wrapping DDL + ledger insert in a transaction "where the engine supports transactional DDL." The trap is applying that pattern *uniformly* and assuming a `BEGIN`/`COMMIT` block provides atomicity. On MySQL, MariaDB and Oracle, **DDL statements cause an implicit commit before executing** — the transaction is already gone by the time the DDL runs. A failed `CREATE TABLE` leaves the transaction committed; a successful DDL followed by a failed ledger insert leaves the schema changed and unrecorded, exactly the bug `TS-11` is meant to fix.

The current code (`sqlite.py:219-233`, `mysql.py:243-258`, `postgresql.py:230-245`, `mssql.py:312-327`, `oracle.py:309-324`) executes DDL, then inserts the ledger row, then commits. Wrapping that in `async with self.transaction():` on MySQL produces code that *looks* fixed, passes a SQLite-based test, and is still broken on MySQL and Oracle.

**Why it happens:**
"Atomic" is treated as a property of the code structure rather than of the engine. The transactional-DDL distinction is real and per-engine: PostgreSQL, SQLite and SQL Server support it; MySQL/MariaDB and Oracle do not. `FEATURES.md` `TS-11` already names this ("Alembic gates this on per-dialect `transactional_ddl`"), but the pitfall is implementing the branch and forgetting to *test the branch*.

**How to avoid:**
1. Add an explicit per-dialect `transactional_ddl: bool` class attribute (PostgreSQL/SQLite/SQL Server `True`; MySQL/MariaDB/Oracle `False`) and branch on it. Mirror Alembic's naming so the intent is obvious.
2. For `transactional_ddl=False`, use **record-intent-first with reconciliation**: insert `(name, status='pending')`, run the DDL, update to `status='applied'`; on startup, detect `pending` rows and either retry or refuse to proceed with a clear error. This is the only honest design when the engine cannot roll back DDL.
3. **Write a failure-injection test per engine**: make the ledger insert fail (e.g. a stub that raises) after the DDL succeeds, then assert the reconciliation path reports the inconsistency. On MySQL this test *must* show the "schema changed, ledger not recorded" state — asserting that the state is *detected* is the deliverable, not asserting it cannot happen.
4. Also fix `TS-12` in the same change: `rollback_migration` (`migration.py:25-29`) records `"{name}:down"` and never deletes the original `{name}` row, so re-apply is a no-op. The rollback and the ledger-delete must be one operation, with a test that applies → rolls back → applies and asserts the schema change is present.

**Warning signs:**
- A single `async with self.transaction():` added around DDL in all six engines with no dialect branch.
- No test asserts the *detection* of a half-applied migration.
- `transactional_ddl` is documented but never read at runtime.
- `rollback_migration` still inserts a `:down` row without deleting `{name}`.

**Phase to address:**
**P3 — Data Correctness (runs parallel to Level 1; touches `migration.py` + each dialect's `migrate`).** `TS-11`, `TS-12`. Must land before the release phase so the ledger semantics are settled.

---

### Pitfall 9: 0.3.0 breaking changes reach users automatically, with no deprecation release and an irreversible publish

**What goes wrong:**
Four compounding failures:

1. **`>=0.2.6` specifiers auto-upgrade to 0.3.0.** pip does not treat `0.x` specially for `>=`. Anyone who installed with `pip install "encino-orm>=0.2.6"` — the natural thing to write — receives every breaking change in 0.3.0 on their next `pip install -U`, with no warning. SemVer clause 4 says `0.y.z` "MAY change at any time," which is a *license*, not a *migration strategy*.
2. **No deprecation release.** SemVer's guidance is explicit: deprecate in a minor release before removing in a major one. The planned breaks (`TS-2` release-from-rollback, `TS-18` identifier validation rejecting previously-accepted table names, `TS-21` removal of `SECRET`/`GET_DB` globals, `last_id()` semantics) all currently have a straight-line path from 0.2.6 to 0.3.0 with no intermediate warning. `CHANGELOG.md` has no `Deprecated` section in use.
3. **The release workflow bypasses every gate being added.** `release.yml` triggers on `v*` tag push and runs `uv build && uv publish` directly — it does not depend on `ci.yml`. So `ruff`, `mypy`, coverage and the new multi-engine matrix are **not** release gates. A tag pushed from a branch that fails lint still publishes.
4. **PyPI releases are immutable.** A bad 0.3.0 cannot be replaced; you must yank it and publish 0.3.1. Combined with (3), a single accidental `git push --tags` is unrecoverable.

There is also existing changelog drift: `CHANGELOG.md` has no `0.2.0` or `0.2.1` entries (git tags also jump `v0.2.2`→`v0.2.6`), and `[Unreleased]` is empty while `.planning` work proceeds. There is no `__version__` in `encino_orm/__init__.py`, so users cannot introspect the installed version to diagnose a bad upgrade.

**Why it happens:**
"0.x means we can break things" is read as "0.x means we don't need process." Release automation was written to be convenient (tag → publish) and is now a loaded gun. Changelog entries get written at release time from memory, which is when they are least accurate.

**How to avoid:**
1. **Ship a `0.2.7` deprecation release first.** Runtime `DeprecationWarning` for each behavior that 0.3.0 changes (implicit commit on release, unvalidated identifiers, mutable `SECRET`/`GET_DB`, `last_id()` after the operation completes), with the replacement named in the message and in the changelog. This is the single highest-value step for user trust and costs almost nothing.
2. **Publish `0.3.0rc1` before `0.3.0`.** pip does not select pre-releases by default, so the rc reaches only users who opt in — real-world validation without an automatic breakage wave. Then promote the same artifact.
3. **Make the release job depend on CI.** Either `needs:` a reusable CI workflow, or run the gates inline in `release.yml`. Add a `pypi` GitHub Environment with required reviewers so a tag push alone cannot publish.
4. **Gate the changelog in CI.** A small check that the version in `pyproject.toml` has a matching `## [x.y.z]` heading in `CHANGELOG.md`, and that `[Unreleased]` is non-empty when source files changed. Also add `__version__ = importlib.metadata.version("encino-orm")` (with a fallback) to `encino_orm/__init__.py` and a test asserting it matches `pyproject.toml`.
5. **Document the pinning advice prominently** for the 0.x window: `encino-orm~=0.2.6` (not `>=`). Add a `MIGRATION-0.3.md` with before/after snippets for each break.
6. Keep `TS-2` and `TS-18` in the *same* release as the deprecation path, and enumerate every break in the `CHANGELOG.md` `### Changed` / `### Removed` sections (`TS-30`).

**Warning signs:**
- A plan to go straight from 0.2.6 to 0.3.0 with no deprecation release.
- `release.yml` has no `needs: [test, lint, typecheck]`.
- The PyPI job has no environment protection.
- `CHANGELOG.md` `[Unreleased]` is empty late in the milestone.
- README still shows `pip install encino-orm` with no version-pinning guidance.

**Phase to address:**
**P1 — Safety Net (Level 0)** for the CI/release gate wiring; **P8 — Release 0.3.0** for the deprecation release, rc, and changelog. `TS-30`. The gate wiring must precede the first breaking change, not follow it.

---

### Pitfall 10: Security fixes that break legitimate identifiers, or that get applied to five of six dialects

**What goes wrong:**
`TS-18` ("validate identifiers in all six dialect builders") has two failure modes that make it security theater:

**(a) The allow-list rejects valid input, so users bypass it.** `_IDENTIFIER_RE = r"^[A-Za-z_][A-Za-z0-9_]*$"` (`base.py:12`) rejects `schema.table`, `"quoted name"`, `[bracketed]`, backticked identifiers, non-ASCII names, and any name starting with a digit. Those are legitimate in at least one of the six engines. When the validation is added to `Db.insert`/`update`/`delete`, previously-working user code raises `ValueError`. The likely user response is to stop using the typed builders and hand-build a `Query` — which is *less* safe than before.

**(b) Validation without dialect-aware quoting gives the wrong semantics.** A name that passes the regex is interpolated unquoted. `User` on PostgreSQL folds to `user`; on Oracle unquoted identifiers fold to `USER`; on MySQL the fold depends on `lower_case_table_names`. So the allow-list can be perfectly injection-safe and still address the wrong table. Allow-list validation and identifier quoting are two different jobs, and only one of them is currently planned.

**(c) The regex is duplicated in six modules** — `base.py:12`, `mysql.py:15`, `sqlite.py:13`, `transfer.py:15`, `model/model.py:29`, `model/types.py:201` — with `_check_identifier` reimplemented in `base.py:59-64` and `transfer.py:18-20`. Fixing one and missing five is the expected outcome, and the missing five will not be visible in a diff review. The existing divergence (`CONCERNS.md`: MySQL/MariaDB lack a `conflict` parameter; PostgreSQL's `replace` silently falls back to `columns[0]`) shows the copy-paste drift is already happening.

**(d) The Model-layer validation creates false assurance.** `Model` validates table/column names at class-definition time (`model/model.py:227,239,246-249`), which is why the low-level `Db` builders look safe. They are public API. Anyone using `Db.insert` directly — the documented low-level path — gets no validation. Similarly, `sync_schema` interpolates catalog-derived column names into `ALTER TABLE` without validation (`model/model.py:877,885,896,900`), so *the database itself* is an untrusted input source there.

**Why it happens:**
Adding a regex check is a one-line change that feels complete. The hard parts — centralizing it, defining the identifier policy (allow-list vs. quoting), deciding what to do about schema-qualified names, and testing each dialect's fold behavior — are not visible in the one-liner.

**How to avoid:**
1. **Centralize first, as a pure refactor with zero behavior change.** Move `_IDENTIFIER_RE` and `_check_identifier` into one module (`dialects/` per `ARCHITECTURE.md` Level 1) and have all six dialects + `transfer.py` + `model/` import from it. Verify tests stay green. Commit this separately.
2. **Then add validation as its own commit**, so the behavior change is isolated and bisectable. Apply it in `Db.insert`/`Db.update`/`Db.delete` for `tabla` and every dict key, and in `sync_schema` for catalog-derived columns (`TS-20`).
3. **Define and document the identifier policy explicitly**, including the rejected cases. If schema-qualified names must be supported, allow an explicit `schema` parameter validated separately rather than loosening the regex. Do not loosen the regex to accommodate one user.
4. **Add dialect-aware quoting for identifiers** (or document that unquoted identifiers are the contract and case-fold accordingly). Emit the quoting helper from the same central module so all six dialects agree.
5. **Test the rejection, not just the acceptance.** For each dialect, assert that `'; DROP TABLE x; --`, `` `x` ``, `a.b`, `1abc`, `""` raise `ValueError` *and* that no SQL is sent to the driver (use a spy connection). A canary test that asserts "raises before touching the driver" is the difference between validation and theater.
6. Add `bandit` to CI but **scope it**, not blanket. `B608` (hardcoded SQL) will fire on every f-string builder in the six dialects; a blanket run produces hundreds of findings, everyone adds `# nosec`, and the check becomes decoration. Configure it to ignore the centralized builder module and to *not* ignore `security/` or `http/`.
7. Do not treat the `PyJWT<2.13` cap as a security posture. It blocks upstream security fixes. Widen it as part of `TS-24` and add `pip-audit` so the pin is justified by evidence rather than by fear.

**Warning signs:**
- `_IDENTIFIER_RE` still defined in more than one module after the fix.
- Validation added to `Db.insert` but not `Db.update`/`Db.delete`, or to PostgreSQL but not all six.
- No test asserts a `ValueError` for malicious identifiers per dialect.
- A user-facing issue appears asking how to use a schema-qualified table name.
- `# nosec` count grows after adding `bandit`.

**Phase to address:**
**P2 — Dialect Seam & Engine Parity (Level 1)** for centralization + validation (`TS-18`, `TS-20`); **P6 — Config & Optional-Layer Hygiene (Levels 4+5)** for the trust-boundary docs (`TS-22`); **P1** for the scoped dependency scan (`TS-24`). The centralization commit must precede the validation commit — this is the Level 1 hard-ordering constraint in `ARCHITECTURE.md`.

---

### Pitfall 11: Benchmarks that measure noise, logging, or the wrong thing — and optimizing before profiling

**What goes wrong:**
`PROJECT.md` requires "benchmarks with measurable numeric objectives" and forbids perceived improvements. The common ways to satisfy that requirement while measuring nothing:

- **Benchmarking the wrong engine.** SQLite `:memory:` is orders of magnitude faster than PostgreSQL over TCP. A "we improved `insert_many` 3×" claim from a SQLite benchmark says nothing about the engine users care about. Six engines means six results or an explicit statement of which one is the target.
- **Noisy shared CI runners.** GitHub-hosted runners are shared, throttled, and have variable CPU steal. A single run with no warmup and no variance reporting produces a number that cannot distinguish a 5% improvement from noise.
- **Benchmarking with debug logging on.** `_log()` in `postgresql.py:17-19`, `sqlite.py:17-19` formats `%r` of the SQL *and all parameters* on every operation, gated only by `logger.debug`. If the logger is enabled (or if a test configures `logging.basicConfig(level=DEBUG)`), the benchmark measures `repr()` cost, not the ORM. This is a realistic foot-gun because benchmark runs often enable verbose logging.
- **Optimizing placeholder translation because it looks expensive.** `TS-37` caches the regex substitution in `_to_postgres`/`_to_positional`/`_to_named` (`postgresql.py:22-29`, `sqlite.py:22-29`, `oracle.py:18-35`). A `re.sub` over a ~200-byte SQL string is on the order of a microsecond; a database round-trip is on the order of a millisecond. Amdahl's law says the win is <1%. The real bottleneck is round-trips (`copy_table`) and it is already identified. **Do not build a SQL cache before a profiler says to.**
- **A cached translation that is silently wrong.** If caching is pursued, note that `Query` is **mutable** (`rebind()` at `query.py:28-31` rewrites `self.query`) and its placeholder detection is `sql.find("{0}") != -1` (`query.py:7`) — a sentinel that mis-detects when `{0}` appears inside a string literal and, when `fields` is empty, leaves literal `{0}` text in the SQL (`query.py:15-16`). A cache keyed on `Query` identity breaks after `rebind`; a cache keyed on `sql_template` alone breaks when the same template is used with a different parameter set. Any cache must be keyed on `(sql_template, tuple(param_names))` and must be invalidated when `rebind` runs.

**Why it happens:**
Benchmarks are usually written to justify a change rather than to test a hypothesis. Logging overhead and engine choice are invisible because they are configuration, not code. And a regex substitution *looks* like obvious waste.

**How to avoid:**
1. **Profile before optimizing.** Run `py-spy` or `cProfile` on a representative workload (bulk insert, N+1-avoiding batch load, paginated read) against PostgreSQL and SQLite. Write down where the time actually goes. If placeholder translation is not in the top 5, defer `TS-37` and say so in the roadmap.
2. **Benchmark harness requirements**: warmup iterations, ≥5 repetitions, report median **and p95**, report standard deviation, and fail the comparison if the change is within 2×σ. Use `pytest-benchmark` with `--benchmark-json` and commit the JSON as a CI artifact so regressions are visible across runs.
3. **Explicitly disable logging** in the benchmark fixture (or assert `logger.getEffectiveLevel() > DEBUG`) so the measurement is of the ORM.
4. **Benchmark per engine**, and state which engine the target number applies to. A single number labelled "performance" is misleading for a six-engine library.
5. **Every benchmark asserts correctness alongside timing.** A fast path that returns wrong rows is not an optimization. `copy_table` benchmarks must assert the destination row count and a checksum.
6. **Make `TS-39` a gate, not a report.** If the benchmark suite does not fail on regression, it will be ignored. Start with loose thresholds and tighten them; a threshold that has never fired is untested.

**Warning signs:**
- A performance PR with no profiler output.
- Benchmark numbers reported from a single run with no variance.
- Benchmark results differ by >20% between consecutive CI runs on the same commit.
- `TS-37` implemented while `copy_table` is still one round-trip per row.
- Benchmarks run only on SQLite.

**Phase to address:**
**P7 — Performance & Benchmarks (Level 6)**, gated by `TS-39`. The harness and baseline belong here; the per-dialect parameter constants they depend on come from **P2**. `TS-37` should be explicitly deferred unless the profile justifies it.

---

## Moderate Pitfalls

### Pitfall 12: Big-bang lint/type/coverage gates across 141 files

**What goes wrong:**
`ruff>=0.16.8` is already a dev dependency but has no config and no CI step. Turning on `ruff format` across the whole repo produces a diff touching most files, which (a) makes every other change unreviewable, (b) conflicts with every open branch, and (c) buries the real diff. Turning on `mypy` (not even a dependency yet) against a pydantic-heavy codebase with `exec()`-generated handlers will emit hundreds of errors; the pragmatic response is `# type: ignore` on everything, and the gate becomes decoration. `mypy --warn-unused-ignores` is what prevents that rot, and it is usually forgotten.

**Prevention:**
Land gates in three isolated, mechanical commits: (1) `ruff format` only — zero logic changes, added to `.git-blame-ignore-revs`; (2) `ruff check` with a **narrow initial rule set** (`E`, `F`, `I`, `UP`, `PT`, `B`) and `per-file-ignores` for `tests/`; (3) `mypy` non-strict with `ignore_missing_imports = true`, per-module `[[tool.mypy.overrides]]` to start strict on the small, stable modules (`exceptions.py`, `query.py`, `sql.py`) and relax on `model/`. Add `--warn-unused-ignores`. Ratchet by removing ignores, never by adding them in bulk. Run the gates as separate CI jobs so a format failure does not hide a test failure.

**Warning signs:** a lint PR with logic changes in it; `# type: ignore` count increasing release over release; `mypy` excluded from CI "for now"; `ruff` config with a large `ignore` list on day one.

**Phase to address:** **P1 — Safety Net (Level 0).** `TS-25`, `TS-26`, `TS-27`.

---

### Pitfall 13: `exec()`-generated handlers removed without a compatibility plan

**What goes wrong:**
`http/routes.py:65-74` and `graphql/schema.py:85-101` build handlers via `exec()`. Replacing them with closures is correct (`_create_resolver` at `graphql/schema.py:108-116` already shows the pattern), but the generated functions' **signatures are the FastAPI/GraphQL contract**. A closure that receives `**path_params` instead of named parameters changes FastAPI's dependency injection, OpenAPI schema, and validation errors. If done during the same phase as pool work, a regression in route signatures is attributed to the wrong change.

**Prevention:** Do the `exec()` → closure conversion as a **behavior-preserving refactor** in its own phase, with a test that snapshots the OpenAPI path/parameter schema *before* and asserts it is unchanged *after*. Use `__signature__` (`inspect.Signature`) to preserve parameter names for composite PKs. GraphQL: stop `setattr`-ing generated types onto the module namespace (`graphql/schema.py:167-176`) in the same change, and add a test that builds two schemas with same-named models and asserts isolation. This is explicitly flagged as untested in `CONCERNS.md`.

**Warning signs:** route signature tests that only assert the happy path; no OpenAPI snapshot test; `graphql/schema.py` still mutating the module namespace after the refactor.

**Phase to address:** **P6 — Config & Optional-Layer Hygiene (Levels 4+5).**

---

### Pitfall 14: Concurrency tests that are either nondeterministic or that never interleave

**What goes wrong:**
Two opposite failures. **Never interleave:** a "concurrency test" that does `for _ in range(10): await pool.acquire()` is sequential and proves nothing — this is exactly what `tests/test_pool.py:113` does today. **Interleave nondeterministically:** a test that fires 100 tasks and asserts `_size <= max_size` will pass on a fast machine and fail on a loaded CI runner, teaching the team to re-run flaky builds. Also note `asyncio.Barrier` was **added in Python 3.11** and this project supports **Python 3.10** (`requires-python = ">=3.10"`, CI matrix includes 3.10), so barrier-based tests will break the 3.10 leg — as will `asyncio.TaskGroup`.

**Prevention:** Force the interleaving deterministically. Inject a slow connection factory (`await asyncio.sleep(0)` or a controllable `asyncio.Event`) so every acquirer reaches the check-then-act window simultaneously; use `asyncio.Event` + counters (3.10-compatible) instead of `Barrier`/`TaskGroup`. Assert **invariants** (`_size <= max_size`, no connection handed to two tasks, no connection leak after `close()`) rather than exact orderings or counts. Run the concurrency suite as a separate CI job with a higher timeout so a genuine hang fails fast rather than eating the whole matrix. Keep a stress variant behind a marker (`-m stress`) that runs many iterations, and keep the deterministic variant in the default suite.

**Warning signs:** `for` loops labelled as concurrency tests; `asyncio.Barrier`/`TaskGroup` in a repo supporting 3.10; flaky-test retries added to CI; a concurrency test with no assertion on shared state.

**Phase to address:** **P1** (3.10-compatible test utilities + markers) and **P4 — Pool Correctness (Level 2)** (the tests). `TS-29`.

---

### Pitfall 15: `pytest-asyncio` loop-scope ambiguity and hidden cross-test state

**What goes wrong:**
`pyproject.toml:41-44` sets `asyncio_mode = "auto"` but leaves `asyncio_default_fixture_loop_scope` unset. pytest-asyncio emits a deprecation/configuration warning for this and the effective fixture loop scope is implicit. Worse, if a future change sets `loop_scope = "session"` to speed tests up, a leaked pool or `set_default_db` singleton (`context.py:19-34`) survives across tests and produces order-dependent failures. Module-level caches (`_FIELD_ADAPTERS` at `model/model.py:434-449` holding strong references to dynamically generated classes) accumulate across the session and are never released.

**Prevention:** Set `asyncio_default_fixture_loop_scope = "function"` and `asyncio_default_test_loop_scope = "function"` **explicitly** in `[tool.pytest.ini_options]`. Add an autouse teardown fixture that calls `set_default_db(None)` and closes any pool created in the test. Add `filterwarnings = ["error"]` so the configuration warning becomes a failure. Make `_FIELD_ADAPTERS` a `WeakKeyDictionary`. Add `pytest-randomly` (or `-p no:randomly` deliberately) to expose order dependence.

**Warning signs:** deprecation warnings in the pytest summary; test failures that disappear when run alone; memory growth in long test sessions; tests that pass in file order and fail with `-p no:randomly` shuffled.

**Phase to address:** **P1 — Safety Net (Level 0).**

---

### Pitfall 16: Mutable JWT/secret globals "fixed" by freezing, which breaks tests and multi-tenant use

**What goes wrong:**
`security/guard.py:13-15` holds process-wide mutable `SECRET` and `GET_DB`. `TS-21` proposes explicit injection. The trap: implementing "freeze after startup" instead of removal leaves the globals in place, and every test that sets `guard.SECRET = ...` now fails — so the freeze gets removed. Worse, a frozen process-wide secret is still wrong for multi-tenant deployments (one secret for all tenants) and still wrong for key rotation (you cannot rotate without a restart). Meanwhile, removing the globals outright is a breaking change for existing users with no deprecation path.

**Prevention:** Three-step migration: (1) make the explicit-parameter path (`get_current_user(secret=..., get_db=...)`) the documented one and add a runtime `DeprecationWarning` when the globals are used; (2) add an end-to-end test with a live FastAPI app covering valid, expired, malformed and anonymous tokens (`CONCERNS.md` flags this as untested); (3) remove the globals in a later release, after the deprecation release. Support key rotation via a callable/iterable of secrets, not a single string. Keep the existing strengths: fail-closed on missing config, `exp` required, refresh tokens rejected as access tokens, `_ALLOWED_ALGORITHMS` blocking `none`/algorithm confusion (`security/jwt.py:17-28,59-72`) — add regression tests for each before touching the module.

**Warning signs:** `guard.SECRET =` assignments in tests after the "fix"; a `freeze()` that raises `RuntimeError` in tests; no `aud`/`iss` handling; no live-app auth test.

**Phase to address:** **P6 — Config & Optional-Layer Hygiene (Levels 4+5)**, with the deprecation warning in **P8**'s deprecation release. `TS-21`.

---

### Pitfall 17: Unbounded growth and caches with no eviction

**What goes wrong:**
`QueryTracer._latencies` (`observability.py:71,80-81,98-100`) appends every query duration forever unless `reset()` is called. `MemoryCacheBackend._store` (`model/cache_backend.py:11-32`) has no size bound and only removes expired entries on a read of the same key. `_FIELD_ADAPTERS` holds strong references. In a long-running service these are slow memory leaks that only appear after days — the hardest class of bug to attribute. `TS-34` addresses the tracer, but the cache backend is a production path when `CachedModel` is used with the memory backend.

**Prevention:** Use `collections.deque(maxlen=N)` for latencies with a configurable bound; add optional max-size + LRU eviction to `MemoryCacheBackend` and document the memory backend as dev/test-only if no eviction is added; make `_FIELD_ADAPTERS` a `WeakKeyDictionary`. Add a test that inserts 10× the bound and asserts the structure stays at the bound.

**Warning signs:** RSS growth proportional to uptime; `reset()` never called in application code; `CachedModel` with `MemoryCacheBackend` in production docs.

**Phase to address:** **P7 — Performance (Level 6)** for the tracer; **P3 — Data Correctness** for the cache backend, since `CachedModel` invalidation (`TS-13`) touches the same file.

---

### Pitfall 18: Dependency bounds that are either too tight (blocking fixes) or too loose (surprise breaks)

**What goes wrong:**
`pyproject.toml` pins `aiomysql>=0.2,<0.3.2` and `PyJWT>=2.8,<2.13` while leaving `asyncpg`, `aiosqlite`, `fastapi`, `strawberry-graphql`, `redis`, `oracledb`, `aioodbc`, `pyodbc` **unbounded**. `pydantic>=2.13.4` is a very tight lower bound combined with `Annotated`-subclassing workarounds in `model/constraint.py` and `model/model.py:444` — so a pydantic minor bump is likely to break constraint construction. A fresh `uv sync` can pull a breaking minor of any unbounded optional dep. Conversely, `PyJWT<2.13` blocks security fixes.

**Prevention:** Add tested upper bounds (`>=x,<next_major`) for every optional extra; relax the pydantic lower bound to a range that is actually tested; add a CI matrix entry for the **minimum** supported pydantic and Python; add `pip-audit` and `uv lock --check` to CI (`TS-24`); add Dependabot/Renovate with grouped PRs so updates are reviewed rather than absorbed. Do not solve the `aiomysql` problem by widening the cap without a passing CI run against the new version.

**Warning signs:** `uv lock --check` fails on `main`; a dependency PR with no test changes; users reporting "works with pydantic 2.13.4 but not 2.14"; the `PyJWT` cap still present after `pip-audit` is added.

**Phase to address:** **P1 — Safety Net (Level 0).** `TS-24`.

---

### Pitfall 19: `Query`'s `{0}` sentinel and regex placeholder rewrite

**What goes wrong:**
`Query.__init__` (`query.py:7`) decides whether the SQL has placeholders via `sql.find("{0}") != -1`. If a SQL string legitimately contains `{0}` inside a literal (JSON, a template, a regex), it takes the formatting path and corrupts the statement. If `fields` is empty, `format()` returns `[sql, {}]` (`query.py:15-16`) and the literal `{0}` is sent to the driver. `_PLACEHOLDER_RE` (`postgresql.py:13`, `sqlite.py:12`) rewrites `%(name)s` occurrences **anywhere** in the string, including inside string literals, and silently ignores parameters present in the dict but absent from the SQL while raising `KeyError` for the reverse. `rebind()` mutates the instance, so any caching keyed on identity is unsafe.

**Prevention:** Replace the `{0}` sentinel with an explicit `has_placeholders` flag or a parse that respects string literals. Make `Query` immutable (return a new instance from `rebind`) and hashable so it can be a cache key. Add tests for SQL containing `{0}` and `%(name)s` inside literals, and for a parameter dict with extra keys. These are prerequisites for `TS-37` — which is another reason to defer `TS-37` until the profile justifies it.

**Warning signs:** a user report of a query with braces in a JSON path failing; `KeyError: 'parameter_000'`; placeholder-cache hit rate that varies with parameter names.

**Phase to address:** **P2 — Dialect Seam (Level 1)** for the `Query` correctness; **P7** for any caching built on it.

---

## Minor Pitfalls

### Pitfall 20: Version metadata that cannot be introspected
`encino_orm/__init__.py` defines no `__version__`. When a user reports a bug, the only way to know the version is `pip show`. Add `__version__` sourced from package metadata with a test asserting it matches `pyproject.toml`. **Phase: P1.**

### Pitfall 21: Changelog entries written at release time from memory
`CHANGELOG.md` has no `0.2.0`/`0.2.1` entries (matching the missing git tags) and an empty `[Unreleased]`. Entries reconstructed at release time miss the "why" and the migration note. Add a CI check that `[Unreleased]` is non-empty when `encino_orm/**` changed, and use `towncrier`/`scriv` if manual discipline slips. **Phase: P1 (check) / P8 (content).** `TS-30`.

### Pitfall 22: Published docs link to a gitignored directory
`README.md:16` points to `prompts/analisys-07.md`, but `prompts/` is gitignored (`.gitignore:29`). PyPI and CI checkouts show a dead link. Move the content to `docs/` and remove the reference. **Phase: P8.**

### Pitfall 23: Dev credentials presented as if they were configuration
`docker-compose.yml:4-36` hardcodes `admin`/`Admin_123` for MySQL, MariaDB, PostgreSQL, MSSQL and Oracle with no warning. Copy-paste into a real environment is the risk. Add a prominent header comment (`# DEV ONLY — throwaway credentials, never use outside local testing`) and move the values to a `.env.example` with obviously-fake defaults. **Phase: P8.** `TS-23`.

### Pitfall 24: `pytest.raises(Exception)` and broad `except Exception`
`tests/test_pool.py:322` asserts `pytest.raises(Exception)`, which passes for typos and import errors alike. `CONCERNS.md` also notes broad `except Exception` accumulation. Narrow the assertion and enable `ruff` rule `PT011`. **Phase: P1.**

### Pitfall 25: Docs that describe the buggy behavior as intended
`base.py:155-163` documents `paginate` as reliable only for simple SELECTs — good. But `pool.py:199-201` comments describe commit-on-release as intentional without saying it is slated to change, and `README`/`docs/` were never updated for the 0.2.5 security changes. Documentation drift means users cannot tell a bug from a contract. Add a docs review step to the release phase and a test that the README's install snippet pins a compatible range. **Phase: P8.**

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-Term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `pytest.skip` when a DB is unreachable | Local dev works without Docker | CI is green with zero dialect coverage; bugs ship (this is the `COUNT(*)` root cause) | Only locally, and only with a requirement switch that fails in CI |
| Copy-pasting the dialect builder into six modules | Fast to add an engine | Fixes land in 1 of 6 files; drift is invisible in review | Never for validation or quoting logic — centralize in the Level 1 seam |
| `FakeDb`-based tests for pool behavior | Fast, no services needed | Validates the fake, not the engine; the real result-shape contract is never exercised | Acceptable for pool *bookkeeping* only, never as the sole evidence for a dialect contract |
| `fail_under` on aggregate coverage | One-line gate | Passes while dialect paths are untested; gives false assurance | Only after per-engine tests exist; never as the sole correctness gate |
| `# type: ignore` to clear a mypy error | Unblocks the gate | Ignore rot; the gate stops meaning anything | Only with `--warn-unused-ignores` enabled and a linked issue |
| `# nosec` for bandit B608 in dialect builders | Clears the scan | Injection linting becomes decoration | Only in the one centralized builder module, with the trust boundary documented |
| Keeping the process-wide `SECRET` global "frozen" | No breaking change | Multi-tenant and key rotation remain impossible; tests fight the freeze | Never — deprecate then remove |
| `exec()`-generated handlers | Compact route generation | No static analysis, no types, runtime-only syntax errors, brittle composite-PK signatures | Never for new code; migrate behind an OpenAPI snapshot test |
| Single shared `_last_id` on the pool | Trivial to implement | Wrong ids under concurrency; silent data corruption | Never — capture ids in the same operation as the insert |
| `BATCH_SIZE = 500` literal | Reads as "reasonable" | Fails on SQL Server (2100 params) and older SQLite (999) | Never — derive from per-dialect param limits and column count |
| Wrapping DDL in a transaction on all six engines | Looks atomic | MySQL/MariaDB/Oracle implicitly commit DDL; false confidence | Never — branch on `transactional_ddl` and reconcile where it is False |
| One `0.3.0` release for all breaking changes | One migration for users | No opt-out, no warnings, immutable PyPI artifact, no rollback | Never — deprecation release + rc first |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| GitHub Actions service containers | Assuming services work the same on all runners and arches; Oracle/MSSQL images are amd64-only | Service containers are Linux-runner only. Pin image digests, add health checks, and use `--platform linux/amd64` for local ARM via testcontainers |
| Oracle in CI | Starting `gvenzl/oracle-xe:21-slim` alongside five other engines in one job | Oracle XE needs ~2 GB and 1–3 min to accept connections; GH runners have ~7 GB total. Use `oracle-free:slim`, run it in its own job, budget 30+ min, and raise `timeout-minutes` from the current 15 |
| SQL Server in CI | Assuming the container is ready when the port is open | Needs `ACCEPT_EULA=Y`, a strong `MSSQL_SA_PASSWORD`, ≥2 GB RAM, and a `sqlcmd`-based health check. `mcr.microsoft.com/mssql/server:2022-latest` on `ubuntu-latest` |
| MariaDB vs MySQL tests | Sharing one env-var namespace and one test module | Separate `ENCINO_ORM_MARIADB_*` env vars and a separate required-engine flag; the dialects differ (`CONCERNS.md` notes MySQL/MariaDB lack the `conflict` parameter) |
| Redis cache tests | Treating the Redis suite as optional | If `CachedModel` + `RedisCacheBackend` is a supported production path, Redis must be in the required matrix or the path is untested |
| Testcontainers for local dev | Spinning up containers per test function | Use session-scoped fixtures with container reuse; per-test containers make the suite slow enough that people disable it |
| `uv` + optional extras | `uv sync` without the extras needed for a test module | CI already uses `--extra http --extra security --extra graphql`; add `--extra all-db --extra cache` in the engine jobs or those modules import-error into a skip |
| PyPI publishing | Tag push auto-publishes with no review | Use OIDC trusted publishing (`uv publish` with `id-token: write`, no token), a protected `pypi` environment with required reviewers, and TestPyPI first |
| asyncpg parameter binding | Assuming `%s`-style placeholders and no param limit | asyncpg uses `$1`-style; `Db._prepare` translates. Verify the parameter ceiling empirically before sizing batches |
| `pytest-asyncio` loop scopes | Leaving `asyncio_default_fixture_loop_scope` unset | Set both fixture and test loop scope explicitly to `function`; a session-scoped loop leaks pools and the `set_default_db` singleton across tests |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `copy_table` one INSERT per row (`transfer.py:155-167`) | Bulk copy time linear in rows × round-trip latency; unusable over a network | Batch with a per-dialect size derived from `MAX_PARAMS // n_columns`; assert row counts | Immediately for >1k rows, or any non-local DB |
| Placeholder regex re-parsed per execution (`postgresql.py:22-29`, `sqlite.py:22-29`, `oracle.py:18-35`) | Suspected CPU cost in query loops | **Profile first.** Expected win <1% vs. a round-trip; defer `TS-37` unless the profiler disagrees | Only in extremely high-QPS, in-process workloads — likely never at this project's scale |
| Debug logging with `%r` of params on every operation (`_log` in each dialect) | Benchmarks and hot paths dominated by `repr()` and string formatting | Keep `logger.debug` lazy (it already is) but disable logging in benchmark fixtures and assert the effective level | Whenever `logging.basicConfig(level=DEBUG)` is set in an app or a test |
| Pool never shrinks above `min_size` (`pool.py:103-109,140-146`) | Bursts pin up to `max_size` connections for the process lifetime; the DB's connection limit is exhausted by idle pools | Close excess connections in `release()` when the queue already holds enough idle connections (lazy, no background daemon) | With several service replicas or a shared DB |
| Unbounded `QueryTracer._latencies` | RSS grows with uptime; GC pauses | `deque(maxlen=N)` or reservoir sampling | After days of uptime in a busy service |
| Unbounded `MemoryCacheBackend._store` | RSS grows with distinct cache keys; expired entries linger | Optional max-size + LRU, or document as dev/test-only | As soon as cardinality is user-driven |
| `_FIELD_ADAPTERS` strong references to dynamic classes | Memory retained per generated model class (codegen, tests) | `WeakKeyDictionary` | Codegen-heavy or long-lived test sessions |
| Benchmarking SQLite `:memory:` and generalizing | Confident claims that do not hold on PostgreSQL | Benchmark per engine; state the target engine with every number | As soon as a user runs it against a real server |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Validating identifiers in 5 of 6 dialects (duplicated `_IDENTIFIER_RE`) | One dialect remains an injection vector; review cannot see the gap | Centralize in the Level 1 seam; one definition, six importers; a per-dialect rejection test |
| Validation without dialect-aware quoting | Allow-list passes but the name resolves to a different object (Oracle uppercases, PostgreSQL lowercases, MySQL fold depends on config) | Pair validation with a quoting helper; document the fold contract; test case sensitivity per engine |
| Loosening the regex to support `schema.table` | Injection surface re-opens | Add an explicit validated `schema` parameter; never widen the character class |
| Treating Model-layer validation as covering the public `Db` API | `Db.insert`/`update`/`delete` are documented public builders and are unvalidated | Validate in the builders themselves; document `Filter.raw`/`Query`/`db.fn.*` as trusted-input-only (`TS-22`) |
| Interpolating catalog-derived column names into `ALTER TABLE` (`model/model.py:877,885,896,900`) | The database is an untrusted input source for `sync_schema`; exotic names inject or break | Validate with the centralized checker (or quote per dialect) before building DDL (`TS-20`) |
| Blanket `bandit` run producing hundreds of B608 hits | Everyone adds `# nosec`; injection linting becomes decoration | Scope bandit to ignore the centralized builder module only; require a linked issue for each `# nosec` |
| Long-lived `PYPI_API_TOKEN` and no publish review | Supply-chain compromise; irreversible bad release | OIDC trusted publishing + protected environment + TestPyPI first (`TS-23`) |
| `PyJWT<2.13` cap | Blocks upstream security fixes while looking like caution | Widen with a tested range; let `pip-audit` drive the pin (`TS-24`) |
| Hardcoded `admin` passwords in `docker-compose.yml` | Copy-paste into real environments | Mark dev-only; move to `.env.example`; add a CI grep for the string |
| `exec()`-generated handlers with `repr`-interpolated names | Code injection via table/column names if `repr` is ever dropped | Migrate to closures; keep the `repr` discipline as a regression test |

## UX Pitfalls

For a library, "UX" is the developer's first 30 minutes and the upgrade experience.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Breaking 0.3.0 changes with no deprecation release | Users on `>=0.2.6` upgrade silently and break in production | Ship 0.2.7 with `DeprecationWarning`s naming the replacement; document `~=0.2.6` pinning for the 0.x window |
| `KeyError: 'COUNT(*)'` on PostgreSQL with no actionable message | The library's core promise (engine parity) fails with an opaque error | Fix the alias; also add a dialect-aware result-key normalization so a future driver rename surfaces a typed error |
| `ValueError: tabla inválida` on a previously-valid table name | A security fix reads as a regression; users work around it by hand-building SQL | Document the identifier policy and the rejected cases; support schema qualification explicitly |
| `pool.execute(INSERT)` silently not persisting after the rollback change | Data loss with no error | Keep standalone DML autocommit; rollback only leftovers and warn |
| `ConnectionError: Pool no conectado` vs. `PoolExhaustedError` vs. driver errors | Users cannot write a correct retry/503 mapping | Deliver the `TS-16` exception taxonomy before the resilience phase |
| `last_id()` returning another task's id | Silent audit-trail and FK corruption | Capture ids in the same operation; document the deprecation of post-hoc `last_id()` |
| Stale reads from `CachedModel` (300 s default TTL) | "The ORM shows old data" — a trust-destroying first impression | Write-invalidate on `update`/`delete` (`TS-13`); document the store-then-invalidate order |
| A rollback that cannot be undone (`rollback_migration` no-op re-apply) | A one-way door discovered during an incident | Fix the ledger (`TS-12`); test apply → rollback → apply |
| No `__version__` and a changelog with missing releases | Users cannot tell what they are running or what changed | Add `__version__`; make the changelog complete and CI-checked |

## "Looks Done But Isn't" Checklist

- [ ] **Multi-engine CI:** Often missing a **required-engine assertion** — verify each engine job fails (not skips) when its service is absent, by temporarily removing the service.
- [ ] **`COUNT(*)` fix:** Often only fixes `model.py:790-792` — verify all three sites (`model/model.py:790-792`, `model/query_builder.py:240-242`, `base.py:151`) and that `paginate` uses `AS n`.
- [ ] **`CachedModel` invalidation:** Often invalidates on `update` but not `delete`, or invalidates before the write commits — verify store-then-invalidate and a test for both paths, including the `RedisCacheBackend`.
- [ ] **Migration rollback:** Often runs `down` without deleting the `{name}` ledger row — verify re-apply after rollback actually changes the schema.
- [ ] **Atomic migration:** Often wraps DDL in a transaction on engines that implicitly commit — verify the `transactional_ddl=False` branch has a failure-injection test asserting *detection*.
- [ ] **Pool race fix:** Often locks the whole `acquire()` — verify a task waiting on `pool.get()` does not hold the lock, and that `release()` can proceed while another task waits.
- [ ] **`last_id` fix:** Often moves `_last_id` per connection without `RETURNING`/`SCOPE_IDENTITY` — verify a concurrent-insert test asserts each task got its own id.
- [ ] **Identifier validation:** Often applied to `insert` only — verify `update`, `delete`, all six dialects, and `sync_schema`'s catalog-derived names.
- [ ] **Coverage gate:** Often green while dialect modules are untested — verify deleting `tests/test_postgresql.py` makes the gate fail.
- [ ] **Lint/type gates:** Often added to `ci.yml` only — verify `release.yml` cannot publish when they fail.
- [ ] **Benchmarks:** Often a script, not a gate — verify a deliberate 2× regression fails the build.
- [ ] **Deprecation release:** Often skipped — verify `0.2.7` exists with warnings for each 0.3.0 break, or that `0.3.0rc1` was published before `0.3.0`.
- [ ] **Changelog:** Often lists fixes but not breaks — verify every `### Changed`/`### Removed` entry names the old and new behavior.
- [ ] **Trusted publishing:** Often keeps the token as a fallback — verify `PYPI_API_TOKEN` is deleted from repo secrets after the OIDC migration.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| A dialect bug shipped because CI skipped it | MEDIUM | Add the required-engine gate; add the per-engine regression test; release a patch. The damage is user trust, not data |
| Aggregate coverage passed while dialect code was untested | LOW | Add per-engine tests; keep the number but stop treating it as evidence; add mutation testing on dialect modules |
| Pool race fix deadlocked in production | HIGH | Roll back to the previous release immediately; re-implement with reserve-before-await; add the concurrency test before re-releasing |
| Rollback-on-release shipped as a silent data-loss bug | HIGH | Yank the version; publish a patch restoring autocommit; add `reset_on_return` with an explicit default; document in the changelog |
| Shared-connection cross-talk under `gather` | MEDIUM | Add the task-ownership check; document the rule; release a patch that raises a typed error instead of corrupting the protocol |
| Wrong `last_id` values written to production data | HIGH | Fix with `RETURNING`/`SCOPE_IDENTITY`; audit affected rows by timestamp; this is a data-integrity incident, not just a code fix |
| Batch size exceeded an engine's parameter limit | LOW | Make batch size computed from the dialect limit; add a wide-table test; release a patch |
| Migration recorded as applied but not applied (or vice versa) | HIGH | Add a startup reconciliation pass that compares the ledger against the actual catalog and reports drift; require manual confirmation for destructive repairs |
| Identifier validation broke user code | MEDIUM | Add the explicit `schema` parameter; publish a patch and a migration note; do not loosen the regex |
| A bad `0.3.0` published to PyPI | HIGH | PyPI is immutable: **yank** 0.3.0 (yanking is not deletion — it stops new resolutions but keeps existing installs working), publish 0.3.1, add the release environment gate. Do not attempt to overwrite |
| CI matrix flakiness from Oracle/MSSQL container startup | MEDIUM | Move each heavy engine to its own job with a longer timeout and digest-pinned image; use container health checks rather than sleeps |
| Benchmark noise producing false regression alarms | LOW | Increase repetitions, report median/p95 with variance, widen the threshold to 3σ until stable, pin the runner class |
| `# type: ignore` / `# nosec` rot | MEDIUM | Enable `--warn-unused-ignores` and a bandit `nosec` audit; require a linked issue for each; ratchet the count down per release |

## Pitfall-to-Phase Mapping

Phase names follow `ARCHITECTURE.md` Levels; `TS-n` IDs follow `FEATURES.md`. P3 runs in parallel with P2 (different modules: `migration.py`, `model/cached.py`, `model/cache_backend.py`).

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Green CI that skips dialects | P1 — Safety Net (Level 0) | Remove a service from a required-engine job; the job must **fail**, and the JUnit XML must show `skipped == 0` |
| 2. Coverage masking dialect paths | P1 (tooling) + P2 (tests) | Delete `tests/test_postgresql.py`; the per-dialect coverage job must fail. `coverage html --contexts` must attribute `model.py:792` to a PostgreSQL test |
| 3. Pool race deadlock / autocommit removal | P4 — Pool Correctness (Level 2) | N-way concurrent `acquire()` with a slow connection factory asserts `_size <= max_size`; `TestPoolAutocommit` still passes after the reset policy change |
| 4. Refactoring against private-state tests and fakes | P1 (characterization tests) + P4 | The invariant tests are unchanged by the pool refactor; one real-engine pool test per engine exists; no `pytest.raises(Exception)` remains |
| 5. contextvars leaking into child tasks | P4 | `gather` inside `transaction()` raises a typed error (or succeeds with separate connections) — never a driver `InterfaceError` |
| 6. `last_id` session-scoped on PostgreSQL | P4 | N concurrent pooled inserts each assert their own id; the implementation uses `RETURNING`/`SCOPE_IDENTITY`/immediate `lastrowid` |
| 7. Batch size exceeding dialect limits | P2 (constants) + P7 — Performance (Level 6) | A wide-table (30+ col) `copy_table` succeeds on SQL Server and on a SQLite build with a 999-variable limit; row counts asserted |
| 8. Non-atomic migration on implicitly-committing engines | P3 — Data Correctness | Failure-injection test per engine; on MySQL/Oracle it asserts the inconsistency is **detected**; apply → rollback → apply works on all six |
| 9. 0.3.0 breaks reach users automatically | P1 (gates) + P8 — Release 0.3.0 | `release.yml` cannot publish with failing gates; `0.2.7` exists with deprecation warnings; `0.3.0rc1` precedes `0.3.0`; `CHANGELOG.md` enumerates every break |
| 10. Identifier validation that breaks use or misses dialects | P2 (+P6 for docs, P1 for `pip-audit`) | One `_IDENTIFIER_RE` definition; per-dialect malicious-identifier rejection tests assert `ValueError` before the driver is called; schema qualification documented |
| 11. Benchmark methodology / premature optimization | P7 | Profiler output committed before any optimization; benchmarks report median/p95/σ per engine; a deliberate 2× regression fails CI |
| 12. Big-bang lint/type gates | P1 | `ruff format` is its own commit in `.git-blame-ignore-revs`; `mypy` runs non-strict with `--warn-unused-ignores`; `# type: ignore` count is tracked and non-increasing |
| 13. `exec()` removal changing the HTTP/GraphQL contract | P6 — Config & Optional-Layer Hygiene (Levels 4+5) | OpenAPI snapshot test unchanged; two same-named GraphQL models build without cross-contamination |
| 14. Nondeterministic or non-interleaving concurrency tests | P1 (utilities) + P4 | No `asyncio.Barrier`/`TaskGroup` (Python 3.10 leg passes); a slow-factory test deterministically reaches the race window; the stress variant is marked |
| 15. pytest-asyncio loop-scope ambiguity | P1 | Both loop-scope options set explicitly; `filterwarnings = ["error"]` makes the config warning fail; autouse teardown clears `set_default_db` |
| 16. Freezing instead of removing secret globals | P6 (+P8 deprecation) | Explicit injection is the documented path; a live FastAPI test covers valid/expired/malformed/anonymous tokens; no test assigns `guard.SECRET` after removal |
| 17. Unbounded tracer/cache/adapter growth | P3 (cache) + P7 (tracer) | Insert 10× the bound; the structure stays at the bound; `_FIELD_ADAPTERS` is a `WeakKeyDictionary` |
| 18. Dependency bounds too tight or too loose | P1 | `pip-audit` and `uv lock --check` in CI; a minimum-supported-pydantic matrix entry passes; no cap blocks a known security fix |
| 19. `Query` `{0}` sentinel and regex placeholder rewrite | P2 (+P7 if cached) | Tests for `{0}` and `%(name)s` inside string literals pass; `Query` is immutable and hashable |
| 20–25 (version, changelog, docs, dev creds, broad excepts, doc drift) | P1 (checks) + P8 (content) | `__version__` matches `pyproject.toml`; `[Unreleased]` non-empty when source changes; no link to `prompts/`; a CI grep finds no `admin` password |

## Sources

**Verified against official documentation (HIGH):**
- Semantic Versioning 2.0.0 — clause 4 (`0.y.z` "Anything MAY change at any time"), and the FAQ on deprecating functionality (one minor release with the deprecation before removal): https://semver.org/ — HIGH
- MariaDB Knowledge Base, "SQL statements Causing an Implicit Commit" — `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE` etc. implicitly commit; "even if the statement fails with an error, the transaction is committed": https://mariadb.com/kb/en/sql-statements-that-cause-an-implicit-commit/ — HIGH
- coverage.py configuration reference — `[run] branch`, `[report] fail_under`, `dynamic_context = test_function`, `[paths]` for combining runs; `report()` does not accept `fail_under` as a parameter (config-only): https://coverage.readthedocs.io/en/stable/config.html and https://coverage.readthedocs.io/en/stable/contexts.html — HIGH
- pytest-asyncio reference — `asyncio_default_test_loop_scope` defaults to `function`; `asyncio_default_fixture_loop_scope` defaults to `function` and warns when unset; the deprecated `event_loop` fixture was removed in 1.0.0: https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html — HIGH
- Python `asyncio` synchronization primitives — `asyncio.Barrier` "Added in version 3.11" (so unusable under `requires-python = ">=3.10"`); `Lock` is not thread-safe and fair: https://docs.python.org/3/library/asyncio-sync.html — HIGH
- SQLite implementation limits — `SQLITE_MAX_VARIABLE_NUMBER` defaults to **999** before 3.32.0 and **32766** after; `SQLITE_MAX_COMPOUND_SELECT` defaults to **500**; `SQLITE_MAX_COLUMN` bounds "the number of values in an INSERT statement": https://www.sqlite.org/limits.html — HIGH
- testcontainers-python — `PostgresContainer`, `MySqlContainer`, `SqlServerContainer`, `OracleDbContainer` (default `gvenzl/oracle-free:slim`) and `OracleFreeContainer` modules; pytest fixture pattern: https://testcontainers-python.readthedocs.io/ — HIGH
- uv, "Building and publishing a package" — `uv publish` with no credentials when a Trusted Publisher is configured; uv invalidates the short-lived token after publishing: https://docs.astral.sh/uv/guides/package/ — HIGH
- asyncpg API — statement caching, `connect(statement_cache_size=...)`: https://magicstack.github.io/asyncpg/current/api/index.html — HIGH (for caching); the ~32767 parameter ceiling is a protocol `int16` limit and was **not** confirmed in the fetched docs — MEDIUM, verify empirically before sizing batches

**Verified by reading this repository (HIGH):**
- `encino_orm/pool.py` (`acquire` check-then-act at 111-146; shared `_last_id` at 63,236-237; commit-on-release at 199-204,239-242; `_current_connection` ContextVar at 29; `transaction` at 162-171; `session` at 277-308), `encino_orm/model/cached.py`, `encino_orm/migration.py`, `encino_orm/base.py` (`_IDENTIFIER_RE` at 12, `_check_identifier` at 59-64, `list_tables` at 151, `paginate` at 155-173), `encino_orm/query.py` (the `{0}` sentinel at 7, mutable `rebind` at 28-31), `encino_orm/postgresql.py` (placeholder regex at 22-29, `last_id` via `lastval()` at 226-228, builders at 146-183), `encino_orm/sqlite.py`, `encino_orm/security/guard.py` (mutable globals at 13-15), `encino_orm/transfer.py:155-167`, `encino_orm/model/model.py` (count at 790-792, `_FIELD_ADAPTERS` at 434-449, `sync_schema` at 877-900)
- `tests/test_pool.py` (private-state assertions, `FakeDb` semantics, `pytest.raises(Exception)` at 322, sequential "max size" test at 113, `TestPoolStandaloneCommit` at 202-213, `TestPoolAutocommit` at 293-311), `tests/test_postgresql.py:67`, `tests/test_oracle.py:103`, `tests/conftest.py`
- `.github/workflows/ci.yml` (services 25-52, `uv sync` extras 65, tests 67-79), `.github/workflows/release.yml` (tag trigger, token-based publish at 35-38, no dependency on CI), `pyproject.toml` (dependency bounds, `[tool.pytest.ini_options]` missing loop-scope/filterwarnings), `CHANGELOG.md` (missing 0.2.0/0.2.1, empty `[Unreleased]`), `docker-compose.yml`, `README.md:16`
- `.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md` (2026-09-17), `.planning/research/ARCHITECTURE.md`, `.planning/research/FEATURES.md` — cross-referenced for `TS-n` IDs and Level ordering

**Flagged for phase-specific validation (MEDIUM/LOW):**
- SQL Server's 2,100-parameter limit and Oracle's 1,000-element `IN`-list cap are widely documented but were not re-fetched here — verify before finalizing batch sizes (MEDIUM)
- asyncpg's exact maximum parameter count (~32767) — verify empirically with a generated wide INSERT (MEDIUM)
- `asyncio.create_task` context-copy semantics are documented, but the specific failure mode of two child tasks sharing a `PoolDb` transaction connection is an inference from the code plus asyncpg's single-operation-per-connection contract — write the test in P4 to confirm (MEDIUM)
- GitHub-hosted runner memory/disk limits for six simultaneous database containers — confirm against current runner specs before designing the matrix (MEDIUM)
- Oracle/MSSQL container readiness times vary by image tag and runner class — measure once and pin the timeout rather than trusting published figures (MEDIUM)
- `ARCHITECTURE.md` describes PostgreSQL `lastval()` as "transaction-scoped." It is **session-scoped**; correct that document before the roadmap builds on it (HIGH on the correction — see PostgreSQL docs for `lastval()`)

---

*Pitfalls research for: production-hardening a multi-engine async Python ORM (`encino_orm` 0.2.6 → 0.3.0)*
*Researched: 2026-09-17*
