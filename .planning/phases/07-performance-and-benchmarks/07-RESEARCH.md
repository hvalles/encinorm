# Phase 7: Performance & Benchmarks — Research

**Researched:** 2026-09-19
**Domain:** micro-benchmarking, profiler-driven optimization, cross-dialect batch DML, bounded observability structures
**Confidence:** HIGH (empirically probed locally + verified driver source + cited official docs); MEDIUM on unverifiable-here engine ceilings (MSSQL/Oracle) and on CI-vs-local absolute speed parity

> No `CONTEXT.md` exists for Phase 7 (discuss not yet run). The locked inputs are the roadmap Goal, the four PERF requirements in `REQUIREMENTS.md`, and the Success Criteria in `ROADMAP.md` §Phase 7. This research corrects several roadmap/prior-research assumptions with file:line evidence.

## Summary

Phase 7 is a *measure-then-optimize* phase, not a feature phase. Three of the four roadmap plans are confirmed as stated, with two important **corrections** and one **critical discovery**:

1. **Correction (PERF-04):** `_FIELD_ADAPTERS` and `_COLUMN_MAPS` are **already** `weakref.WeakKeyDictionary` (`encino_orm/model/model.py:30-31`). The remaining PERF-04 work is only the bounded `QueryTracer._latencies` — and a *retention test* proving the WeakKeyDictionary half (so it can never silently regress to a strong-dict).
2. **Correction (batch formula):** `Model.insert_many` already derives `chunk = max(1, min(MAX_PARAMS // n_columnas, MAX_ROWS))` (`model.py:597-603`). The formula is correct and `MAX_ROWS=1000` is not arbitrary: it exactly matches SQL Server's **documented 1,000-row table-value-constructor cap** (error 10738), so the universal cap is MSSQL-aligned, not a guess.
3. **Critical discovery (PERF-01):** the roadmap's "reuse the multi-VALUES `insert_many` mechanism for `copy_table`" **fails for Oracle**. Oracle does not support multi-row `VALUES (...), (...)`, and no adapter or test handles this today — `insert_many`'s multi-VALUES SQL has never run against Oracle (or MSSQL) in any test (`tests/test_bulk_upsert.py` is sqlite-only). PERF-01 must therefore branch: multi-VALUES for SQLite/MySQL/MariaDB/PostgreSQL/MSSQL, and `INSERT ALL … SELECT 1 FROM DUAL` (or `executemany`) for Oracle. `executemany`/array-binding is recommended against for PostgreSQL here (see Q5).

**Empirical probes performed this research** (local: CPython 3.13.7, Windows, `.venv` with aiosqlite 0.22.1, aiomysql 0.3.1, asyncpg 0.31.0; Docker: PostgreSQL 16-alpine, MySQL 8.0, MariaDB 11, Redis):

- SQLite: **32767 placeholders OK, 32768 FAIL** (`too many SQL variables`); 1000-row multi-VALUES OK → `max_params=32766` (official SQLITE_MAX_VARIABLE_NUMBER default) is safe but conservatively off-by-one.
- PostgreSQL/asyncpg: **32766 args OK** end-to-end; client-side bound `the number of query arguments cannot exceed 32767` at 32768 (verified in installed source `protocol/prepared_stmt.pyx:130`) → 32767 bound confirmed.
- MySQL 8.0: **65534/65536/65538 args all OK** — the text-protocol path (client-side `%s` substitution in `_to_mysql`, `mysql.py:51-58`) is NOT bound by the 65535 prepared-statement placeholder cap; only `max_allowed_packet` applies. `LIMITS["mysql"].max_params=65535` remains safe, but its provenance ("protocol counter") is wrong for the path actually used.
- Sync-unit baselines (ops/s, warmup+9 reps, median): SQL build via QueryBuilder ~149K; Query construction (placeholder translation) ~236K; `Query.with_params` ~209K; `_to_mysql` rewrite ~625K; batch-sizing formula ~9.6M; multi-VALUES gen (500 rows × 5 cols) ~1.5K.

**Primary recommendation:** the benchmark harness is a **zero-new-dependency** pure-Python `time.perf_counter` loop inside `@pytest.mark.benchmark` tests (`tests/test_benchmarks.py`), run by a new `benchmarks` CI job with `uv run pytest -m benchmark -q`. Gate = per-unit ops/s floors at **0.6× of the measured baseline** (a deliberate 2× regression lands at 0.5× → fails; normal noise ±20% → passes). The main `test` job's filter must change to `-m "not optional_engine and not benchmark"` — today `benchmark`-marked tests would leak into the 4-leg matrix.

---

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research Support |
|----|-------------------------------|------------------|
| PERF-01 | `copy_table` inserts por lotes con tamaño por dialecto (`min(MAX_PARAMS // n_columnas, MAX_ROWS)`) | Q1 (ceilings verified/provenance cited), Q5 (Oracle divergence mandatory), Q7 (edge cases), Q8 (CI coverage). Row-by-row target confirmed at `transfer.py:152-158`. |
| PERF-02 | Suite de benchmarks con objetivos numéricos y un gate que falla ante una regresión deliberada de 2× | Q2 (zero-dep harness design), Q3 (measured baselines + 0.6× floors), Q8 (CI job + main-run exclusion). |
| PERF-03 | Salida del profiler (`py-spy`/`cProfile`) comprometida **antes** de cualquier optimización | Q4 (workload script design, cProfile-only since py-spy is absent, `benchmarks/profiles/` location). |
| PERF-04 | `QueryTracer._latencies` acotado y `_FIELD_ADAPTERS` con `WeakKeyDictionary` | Q6 (deque maxlen=1024, reset semantics, bounded-window doc). Second half already done (`model.py:30-31`) — becomes a retention test. |
</phase_requirements>

## User Constraints

No `CONTEXT.md` file exists for Phase 7 (orchestrator confirmed `has_context: false`). Locked constraints come from the roadmap/requirements chain instead:

- **Core value:** correctness and data safety cannot regress in favor of performance (PROJECT.md; roadmap §Overview).
- **PERF requirements 01–04** as quoted above are the phase's only scope; nothing else in scope.
- **CI gates are blocking and non-advisory:** a job that cannot fail is CI green without verification (established Phase 1/2 doctrine).
- **Benchmarks must benchmark sync units directly** — roadmap correction #2: neither pytest-benchmark nor pytest-codspeed measures coroutines; hand-rolled `time.perf_counter` for end-to-end async latency if ever needed (`.planning/research/SUMMARY.md` §CORRECTION, HIGH confidence).
- **No new engines, no 1.0, no feature work** in this milestone (PROJECT.md constraints).
- **Python 3.10 floor** (library and tests): no `TaskGroup`, `asyncio.timeout`, `except*`.
- `filterwarnings = ["error"]` and `xfail_strict` (pyproject.toml:55-72): benchmark tests must be warning-free or they fail CI.
- Ruff lint + format and mypy are blocking gates; any new file must pass them (this phase adds no lint-suppressions; `tests/**` already allows `S101`).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Batch sizing (chunk derivation) | API/Backend (model + transfer layers) | — | Same formula as `insert_many` (`model.py:597-603`); must read `MAX_PARAMS`/`MAX_ROWS` off the resolved `Db`/`PoolDb`, which is library-core knowledge. |
| Copy-table row batching | API/Backend (`transfer.py`) | Database/Storage (dialect-specific SQL shape) | The batch loop lives in `transfer.py`; but the rendered SQL shape is dialect-owned (multi-VALUES vs Oracle `INSERT ALL`), so the divergence must be expressed as data/strategy in the DIAL seam, not branches in `transfer.py`. |
| Placeholder translation | API/Backend (`query.py` `Query.__init__`) | — | Pure sync CPU work; the benchmark gate owns this measurement, not the adapters. |
| SQL build | API/Backend (`model/query_builder.py`, `dialects/builders.py`) | — | Sync CPU work; gate-tested via `_build_full()` (existing private sync surface). |
| Query latency history | Observability (`observability.py`) | — | `QueryTracer._latencies` is a pure in-process structure; bounding it is a library-core change with no engine interaction. |
| Benchmark gate CI job | CI (`.github/workflows/ci.yml`) | — | New `benchmarks` job, no services; main test matrix filter updated to exclude `benchmark`-marked tests. |

## Standard Stack

**Zero new dependencies.** This is a deliberate, evidence-based decision (Q2):

| Component | Choice | Purpose | Why |
|-----------|--------|---------|-----|
| Benchmark framework | None — stdlib `time.perf_counter` + `statistics.median` in a `@pytest.mark.benchmark` test | Measure sync units with median/p95/σ | pytest-benchmark/pytest-codspeed add a dependency; do not measure coroutines (verified by reading plugin source — roadmap correction #2); the marker we need is already registered (pyproject.toml:79). |
| Profiler | `cProfile` (stdlib) via a `benchmarks/profile_workload.py` script | Committed BEFORE any optimization (PERF-03) | py-spy is **not installed** in this environment (`command -v py-spy` empty); cProfile is deterministic, stdlib, and produces reviewable text dumps. |
| Bounded structure | `collections.deque(maxlen=1024)` | `QueryTracer._latencies` | O(1) append/clear, fixed memory; `.clear()` preserves `maxlen` so `reset()` semantics hold. |
| Batch SQL shape | Per-dialect strategy in `dialects/` (multi-VALUES; Oracle `INSERT ALL`) | `copy_table` batches | Keeps dialect divergence in the seam (DIAL doctrine), not in `transfer.py`. |

No new packages are proposed anywhere in this phase → **the package-legitimacy gate is vacuous**; slopcheck was not run because there is nothing to install. If a later plan deviates and adds a package, it MUST go through the gate (planner checkpoint).

### Version verification (installed, used for measurements)

| Package | Version | Verified how |
|---------|---------|--------------|
| CPython (local venv) | 3.13.7 | `.venv/Scripts/python.exe -c` |
| aiosqlite | 0.22.1 | `pip list` |
| aiomysql | 0.3.1 | `pip list` |
| asyncpg | 0.31.0 | `pip list` + source read (`prepared_stmt.pyx:130`) |
| oracledb | 4.0.2 | `pip list` (executemany at `cursor.py:863`) |
| pyodbc / aioodbc | 5.3.0 / 0.5.0 | `pip list` (executemany at `aioodbc/cursor.py:135`) |
| pytest | 9.1.1 | `pip list` |
| pydantic | 2.13.4 | `pip list` |

### Alternatives considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Zero-dep harness | pytest-codspeed 5.0.3 | CodSpeed has a real CI regression service and simulation mode, but is a new runtime dep, needs its own CI action, and its `BenchmarkFixture.__call__` is literally `return target(*args, **kwargs)` — useless for the async paths anyway. Revisit if CI wall-clock flakiness becomes untenable (documented in Open Questions). |
| Zero-dep harness | pytest-benchmark 5.3.0 | Nice local reporting (`--benchmark-json`, compare), but a new dep and no coroutine support; the zero-dep loop gives us median/p95/σ with 30 lines. |
| `INSERT ALL` for Oracle | oracledb `executemany` with batcherrors | `executemany` is the native fastest bulk path but requires a new `Db` method (six adapters), breaks the `Query` abstraction (named `%(name)s` binds don't map to oracledb's positional row tuples), and forks error handling (batcherrors). `INSERT ALL` keeps one `Query` per batch through `db.execute` — same seam, testable in engine-heavy CI. |
| asyncpg COPY for PostgreSQL | `copy_records_to_table` (exists, verified `connection.py:1028`) | COPY is genuinely faster than multi-VALUES, but: asyncpg COPY bypasses the `Query` abstraction, needs a new Db API, converts errors differently, and multi-VALUES already removes the *round-trips* (the actual PERF-01 goal). Amdahl: round-trips dominate a networked copy, not the wire format. Defer (documented as v2 item, see Open Questions). |

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| *(none — this phase adds zero packages)* | — | — | — | — | — | Approved by absence |

**Packages removed due to slopcheck:** none.
**Packages flagged as suspicious:** none.
**Note:** if a plan in this phase proposes any external package, it must be gated behind `checkpoint:human-verify` and re-run the slopcheck protocol; the research recommends against all such proposals.

## Current State (verified file:line evidence)

| Claim | Evidence | Status |
|-------|----------|--------|
| `Model.insert_many` already batches with `min(MAX_PARAMS // n_columns, MAX_ROWS)` | `model.py:570-628`; chunk derivation `597-603`; multi-VALUES gen `610-626` | ✅ verified |
| `_FIELD_ADAPTERS` / `_COLUMN_MAPS` already WeakKeyDictionary | `model.py:30-31` (`weakref.WeakKeyDictionary()`) | ✅ verified — PERF-04 second half DONE |
| `QueryTracer._latencies` is an unbounded list | `observability.py:71` (`self._latencies = []`), append `:81`; `latency_stats` sorts everything `:38-49` | ✅ verified — ENDLESS |
| `copy_table` inserts row-by-row | `transfer.py:152-158`: `for row in rows: … await dst.execute(dst.insert(table, data))` | ✅ verified — real PERF-01 target |
| Per-dialect LIMITS with provenance | `dialects/strategies.py:106-158` | ✅ verified (values discussed in Q1) |
| `benchmark` marker registered but no parser/CI/deps | pyproject.toml:79 (marker text says "pytest-codspeed"); no pytest-codspeed in `[dependency-groups]` (pyproject.toml:293-321) | ✅ verified |
| No `executemany`/COPY/array-binding in adapters | grep over `encino_orm/*.py`: zero hits | ✅ verified — multi-VALUES via `Query` is the only established bulk mechanism |
| No test exercises `insert_many` on MSSQL/Oracle | `tests/test_bulk_upsert.py` boots its own `SqliteDb` (`:22-28`); no mssql/oracle integration tests for bulk | ✅ verified — CRITICAL gap |
| Main CI `test` job filter does **not** exclude `benchmark` | `ci.yml:137-139`: `-m "not optional_engine"` | ✅ verified — MUST change in 07-02 |
| py-spy absent | `command -v py-spy` → empty | ✅ verified |
| Local engines available | Docker: postgres:16-alpine, mysql:8.0, mariadb:11, redis (all `Up`) | ✅ verified |
| MSSQL/Oracle NOT available locally | no containers; only CI `engine-heavy` job covers them | ✅ verified |
| `test_pytest_config.py` asserts marker names only | `tests/test_pytest_config.py:106` (`names` set) — changing marker *description* is safe | ✅ verified |
| `Query.rebind` deleted; `with_params()` is the copy API | `query.py:150-161` | ✅ verified (roadmap correction #2b — research brief's "Query.format/rebind" wording is stale) |
| ruff select list lacks `SLF001` (private access OK in tests) | pyproject.toml:130-132 | ✅ verified — benchmark tests may call `QueryBuilder._build_full()` |

## Answers to Research Questions

### Q1 — Per-dialect parameter ceilings and the batch formula

**Formula verdict: `min(MAX_PARAMS // n_cols, MAX_ROWS)` with `max(1, ...)` is correct.** It is the formula `insert_many` already uses (`model.py:601`); the same expression applies to `copy_table` with `n_cols = len(target_cols)` after introspection. Two properties make it safe on all six engines:

- It never exceeds the dialect's own `MAX_PARAMS` for **any** column count.
- `MAX_ROWS=1000` is NOT arbitrary: SQL Server's documented table-value-constructor cap is exactly **1,000 rows** (`[CITED: learn.microsoft.com/en-us/sql/t-sql/queries/table-value-constructor]`, error 10738). A universal 1000-row ceiling therefore satisfies the most constrained dialect by construction; all other dialects accept far more.

**Ceiling per dialect (evidence):**

| Dialect | `MAX_PARAMS` (LIMITS) | This research | Verdict |
|---------|----------------------|---------------|---------|
| sqlite | 32766 | Official default `SQLITE_MAX_VARIABLE_NUMBER=32766` `[CITED: sqlite.org/limits.html, sqliteLimit.h]`; **empirically 32767 OK, 32768 FAIL**; 1000-row/2000-param multi-VALUES OK | ✅ safe (could be 32767, keep 32766) |
| postgresql | 32767 | asyncpg client bound `if len(args) > 32767` `[VERIFIED: installed source protocol/prepared_stmt.pyx:130]`; **empirically 32766 args end-to-end OK, 32768 client-RAISED** | ✅ verified |
| mysql | 65535 | Documented prepared-statement cap 65535 `[CITED: dev.mysql.com/refman/8.0/en/prepare.html; error 1390]`; **empirically 65538 args OK on the text-protocol path** encino_orm uses (`_to_mysql`, `mysql.py:51-58` → simple query, no COM_STMT_PREPARE) | ✅ safe; provenance wording should change ("prepared-statement cap", not "protocol counter") |
| mariadb | 65535 | Same protocol as MySQL | ✅ safe (same correction applies) |
| mssql | 2100 | Documented max parameters per stored procedure/UDF = 2100 `[CITED: learn.microsoft.com maximum-capacity-specifications]`; table-value constructor ≤ 1000 rows `[CITED: table-value-constructor]`; **engine NOT available locally — NOT empirically verified** | ⚠️ keep, flagged for engine-heavy probe |
| oracle | 65535 | "binds per statement = 65535" has **no citable official doc found**; official PL/SQL Program Limits say bind vars to a program unit = **32768** `[CITED: docs.oracle.com/…/plsql-program-limits (18c/26 docs)]`; IN-list cap 1000 (pre-23c)/65535 (23ai) is a different limit `[CITED: python-oracledb docs]`; **engine NOT available locally — NOT empirically verified** | ⚠️ provenance poor; FLAG — see Q1.1 |

**Q1.1 — Oracle `max_params` decision for the planner:** the only citable documented number for Oracle binds is 32768 (PL/SQL program units). 65535 "binds per SQL statement" is folklore in the docs I could verify. However, `insert_many`/`copy_table` batches on Oracle go through a plain SQL statement (`INSERT ALL`), where the operative cap is the total bound variables the parse accepts. **Recommendation:** keep `65535` but add an explicit engine-heavy probe task in the 07-03 plan (and note the failure mode: if the first Oracle batch of `chunk = min(65535 // n_cols, 1000)` rows fails, reduce `LIMITS["oracle"].max_params` to 32768 and re-run). Do NOT change the constant without a probe; do NOT hard-code a per-table fallback.

**Q1.2 — MSSQL math sanity:** `chunk = min(2100 // n_cols, 1000)`: for n_cols ≥ 3 → ≤700 rows (2100 params max); for n_cols ∈ {1,2} → capped at 1000 rows = 2000 params ≤ 2100. Both the 2100-parameter cap and the 1000-row VALUES cap are honored simultaneously. ✅

### Q2 — Benchmark harness design (zero-new-dependency)

**Recommendation: option (c) — a small pure-Python harness inside `@pytest.mark.benchmark` tests.** Strong reasons, not just "no new deps":

1. Both plugin alternatives are wrong for this phase's actual need: pytest-codspeed's fixture literally returns the target's return value without awaiting (`return target(*args, **kwargs)` — verified by prior research reading the source, `research/SUMMARY.md`), and the roadmap correction #2 already established that neither plugin measures coroutines. Our units are sync — but the zero-dep loop does the same job with no install.
2. The `benchmark` marker is **already registered** (pyproject.toml:79) and the strict-markers harness is already in place; the only miss is a parser.
3. The numbers we need (median + p95 + σ, warmup, ≥5 reps, logging disabled, `gc.collect()` before loops) are exactly the loop below — 30 lines, no magic, no calibration loops of its own.

**Harness contract (specification for 07-02):** per unit, build a callable (closure), then:

```python
def _measure(fn, *, inner=2000, warmup=3, reps=9):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(reps):
        gc.collect()
        t0 = time.perf_counter()
        for _ in range(inner):
            fn()
        samples.append(inner / (time.perf_counter() - t0))
    return statistics.median(samples), _p95(samples), statistics.stdev(samples)
```

- `logging.getLogger("encino_orm").disabled = True` in a module-level fixture so `%`-format debug logging is skipped entirely (the 4-argument `logger.debug` in every adapter would otherwise dominate).
- `gc.collect()` before each timed loop; reps ≥ 9 (brief says ≥5; 9 gives a stable median at negligible cost).
- Assert on **median**, report p95 and σ in the failure message. `inner` scaled per unit so each rep ≥ 0.5 s (batch-sizing: inner≈200_000; SQL build/Query: inner≈2_000; multi-VALUES gen: inner≈200).
- No `pytest.parametrize` over engines — these are DB-free sync units (marker description semantics preserved).
- **Warnings:** the file must not emit any warning (`filterwarnings=["error"]`). Sync units touch no sqlite datetime adapter path, so the existing `ignore:` filter is not even needed here.

**Units for 07-02 (all exist today, no source change):**
1. **SQL build** — `QueryBuilder(...).select(...).join(...).where(...).group_by(...).order_by(...)._build_full()` (private call OK; `SLF001` not in ruff select, pyproject.toml:130-132).
2. **Placeholder translation** — `Query("SELECT … {0} … {n}", [v0…vn])` construction (the `_PLACEHOLDER_RE` findall + cardinality check + `sub` compile + params dict, `query.py:78-103`); a second probe for `with_params()` (the copy path, `query.py:150-161`).
3. **Batch sizing** — the chunk-derivation expression `max(1, min(max_params // max(n_cols, 1), max_rows))` (mirror of `model.py:601`).

**The multi-VALUES generation benchmark belongs to 07-03, not 07-02** (see Q3 note): 07-02 stays zero-source-change; 07-03 authorizes the shared batch-gen helper *and* its bench test in the same plan so the gate measures the real function from day one.

### Q3 — Numeric targets (measured locally, thresholds with 2× gate semantics)

Measured on this machine (CPython 3.13.7/Windows, warmup+9 reps, median):

| Unit | Local median (ops/s) | Local p95 | Proposed threshold (ops/s) |
|------|---------------------:|----------:|---------------------------:|
| SQL build (QueryBuilder full chain incl. join+filter+group+order) | 148,800 | 151,500 | **85,000** |
| Placeholder translation (`Query(...)` construction) | 236,000 | 238,900 | **140,000** |
| `Query.with_params` (copy path) | 209,300 | 216,600 | **120,000** |
| Dialect param rewrite (`_to_mysql`) | 625,100 | 641,900 | **375,000** |
| Batch sizing formula | 9,629,000 | 9,876,500 | **5,000,000** |
| multi-VALUES gen (500 rows × 5 cols) — 07-03 unit | 1,516 | 1,546 | **900** |

**Gate semantics:** threshold = **0.6× of the measured baseline**. A deliberate 2× slowdown lands at 0.5× baseline → below the floor → **gate fails** (requirement PERF-02). Normal CI noise (typically ±10-20%) stays above. This is the honest middle ground between "gate on the exact baseline" (flake-prone on shared CI runners) and "gate on 0.5×" (a true 2× regression would skate by).

**CI-vs-local caveat (for the planner):** ubuntu-latest runners are usually within ±20% of this Windows box for pure-CPU loops, but there is no guarantee. **07-02 must treat its first green CI run as the calibration run:** if a threshold is off by ≤20% in either direction, adjust the committed constant in the SAME commit (documented), preserving the 0.6× relationship to the CI-measured baseline. The gate's purpose is 2×-regression detection, not absolute CPU ranking; an out-of-the-box threshold failure on run #1 is noise, not a regression.

**Note for 07-03's gen benchmark:** the multi-VALUES gen unit is authored by 07-03 together with the helper it measures (see Q5 design). Its threshold uses the same rule: 0.6× of the first CI measurement, calibrated in the same commit. The 1,516 ops/s local number above is the reference seed.

### Q4 — Profiler workload design (07-01)

**Script:** `benchmarks/profile_workload.py` (new dir `benchmarks/`, git-committed), CLI:

- `--mode=cprofile` (default) | `--mode=manual`
- `--scale=N` (multiplier on iterations; default 1 → ~5-10 s runtime)
- `--out=benchmarks/profiles/<name>` for the cProfile dump path

**Workload** (representative, ordered to make the BEFORE-optimization profile meaningful):

1. **Model CRUD on sqlite `:memory:`** — define a small `Model`; create table; then a loop of insert/load/update/delete (~500 iterations) using TEXT columns for datetimes (avoid the sqlite3 datetime-adapter deprecation warning path; existing tests already model this with `creado TEXT`).
2. **`insert_many` chunked** — 5,000 rows in chunk=500 (the multi-VALUES path; this is INSIDE the fast path after 07-03 but is exercise TODAY at its current cost).
3. **`copy_table` row-by-row** — 2,000 rows sqlite→sqlite (`preserve_ids=True`). **This is the profile that PERF-03 wants on record BEFORE 07-03 lands** — after batching, this section of the profile must visibly shrink.
4. **`Query` construction + `with_params` loop** — 20,000 iterations (placeholder translation).
5. **sqlite fetch loop** — `fetch_all` over N rows (driver/IO cost for contrast with pure-CPU units).

**Output artifacts (committed):** `benchmarks/profiles/` with (a) the raw `.pstats` binary (reproducible) and (b) a rendered text table — `pstats.Stats.stream = sys.stdout` and `sort_stats("cumulative").print_stats(40)` — prefixed by a header with the exact command line, Python version, and platform. The text table is the reviewable, PR-diffable artifact; the raw file guarantees the numbers can be re-derived. Filename convention: `profile_workload_<mode>_<yyyy-mm-dd>.pstats` / `.txt` (a single committed run per mode; do NOT accumulate timestamped runs).
**py-spy:** not installed; **cProfile only**. py-spy's sampling adds no value for a short deterministic script (its sampling stabilization needs longer runs) and is an extra dependency.
**Commit point:** the profile artifact must land in 07-01's commit, BEFORE 07-02/07-03 touch any code (`ROADMAP.md` success criterion 1; Hard-Ordering spirit of phases 1-2).

### Q5 — asyncpg array binding / executemany vs multi-VALUES (recommendation)

**Facts verified:**
- asyncpg 0.31.0 has **no `executemany`**; it has `copy_records_to_table` (verified `connection.py:1028`) for COPY-protocol bulk load.
- aiomysql 0.3.1 `executemany` only rewrites simple `%s` bulk inserts (`cursors.py:16-17` regex) — **incompatible with `Query`'s named `%(parameter_0000n)s` placeholders**.
- aioodbc 0.5.0 and oracledb 4.0.2 expose `executemany` (pyodbc qmark / oracledb rows) — each with its own parameter style and error mapping; oracledb's supports batcherrors.
- The established mechanism (`insert_many`, `model.py:610-626`) is multi-VALUES through `Query` — uniform across five dialects, already past DIAL validation, and its batch sizing is the exact formula PERF-01 names.

**Recommendation for PostgreSQL: multi-VALUES, NOT COPY.** The PERF-01 goal is "remove real round-trips" — multi-VALUES cuts round-trips by chunk (N/1000) with zero new API. asyncpg COPY is faster per row but requires a **new `Db` abstract method** (all six adapters implement or raise), a separate error-translation path (COPY errors don't look like query errors), and culture-specific value encoding (`copy_records_to_table` handles it, but dates/decimals normalization belongs to `_serialize_for_target` logic that already exists). Amdahl's law: at 16-alpine + localhost or CI the round-trip removal dominates; the wire-format delta is second-order for this milestone. **Defer COPY as a documented v2 item** (see Open Questions).

**Recommendation for Oracle: `INSERT ALL`, NOT `executemany` — and NOT multi-VALUES.** Oracle rejects multi-row `VALUES (...), (...)`. The batch builder must render, for `kind="merge"` + plain insert (this is the Oracle plain-INSERT path — note `build_insert` renders `INSERT INTO t (...) VALUES (...)` in the `else` branch of `merge` today), the equivalent: `INSERT ALL INTO t (cols) VALUES (...) INTO t (cols) VALUES (...) SELECT 1 FROM DUAL`. This stays inside the **Query/seam abstraction** (one `Query` per batch through `dst.execute`), is testable in the `engine-heavy` CI job, and needs no new `Db` API. `executemany` remains the v2 optimization if INSERT ALL proves slow at scale. The `INSERT ALL` divergence must be expressed in `dialects/builders.py` (new builder `build_multi_insert(table, columns, rows, strategy)`) — data-as-strategy per DIAL doctrine — with MSSQL's `ignore_duplicated` suppression and Oracle's `_MERGE_USING_RE`-style driver-only rewrites staying adapter-local if needed.

### Q6 — `QueryTracer._latencies` bounded deque

- **`deque(maxlen=1024)`** at `observability.py:71`. Rationale: (a) it bounds the worst case (a long-lived process currently grows `_latencies` without limit — TS-34, `research/FEATURES.md:74`); (b) memory ≈ 1,024 × 8 B floats ≈ 8-16 KB with deque overhead — negligible; (c) `latency_stats` sorts on each call (`_percentile`, O(n log n)) — sorting 1,024 floats is ~50-100 µs, acceptable; (d) 1,024 samples is a meaningful percentile window for the tracer's audience (it's a diagnostics/monitoring surface, not a metrology instrument).
- **Constructor param:** `latency_window: int = 1024` on `QueryTracer.__init__` (default constant `MAX_LATENCY_SAMPLES = 1024` per repo `UPPER_SNAKE_CASE` convention) so tests can shrink the window instead of recording 1,025 samples for the bound test. All six current tests in `tests/test_observability.py` (`TestLatencyHistogram`) stay green: `_latency_summary` receives a sequence, `.clear()` on a deque preserves `maxlen`.
- **Doc change required:** `latency_stats` docstring must say "bounded window — the last N queries" (it currently says "de las consultas registradas", which implies full history). Same for the class docstring example.
- **`reset()` semantics:** `self._latencies.clear()` keeps `maxlen` — counters zero, window emptied, bound retained. No behavioral change.
- **`OtelQueryTracer`:** no in-process latency list (spans only) — untouched by PERF-04.
- **PERF-04 second half (WeakKeyDictionary):** already implemented (`model.py:30-31`). 07-04 must add a **regression test**: create a `Model` subclass, populate `_FIELD_ADAPTERS` (which `_validate_field`/`TypeAdapter` caching does on first use), drop all references, `gc.collect()`, assert the class is no longer a key (e.g., `list(_FIELD_ADAPTERS.keys())` empty) — this makes the "no retention" property a locked CI claim instead of an implicitly-true statement. Note `Model` classes are frequently retained by other caches (`_COLUMN_MAPS` is also weak; the relation registries are class-level), so the test must assert on the weak dicts specifically.

### Q7 — `copy_table` batching edge cases (07-03)

The batch loop must preserve **row-equivalence** with today's path (`transfer.py:152-158`) exactly:

| Concern | Current behavior (transfer.py) | Batched design |
|---------|-------------------------------|----------------|
| Per-cell translation | `_normalize_value(row[col.name], col.datatype)` then `_serialize_for_target(..., dialect)` per cell (`:153-156`) | Identical per-cell loops; only the query assembly changes. |
| Column list | `target_cols = [c for c in columns if c.name != auto_pk]` (`:145`) — **constant per copy** | Same list reused for every batch; validated once with `check_identifier` per column before interpolation (DIAL-02 invariant: no unvalidated identifier in SQL). |
| auto_pk exclusion | `auto_pk = _auto_pk_name(columns) if not preserve_ids else None` (`:144`) | Kept verbatim (`target_cols` empty when the table's only column is the auto PK and `preserve_ids=False`). **Edge:** `target_cols == []` is degenerate today (single-auto-PK table, no data columns). Decision for the planner: keep the row-path behavior for that case (fall back to per-row `dst.insert` when `target_cols` is empty) — never emit `INSERT INTO t () VALUES ()`. |
| `truncate` | `DELETE FROM t` inside the same transaction (`:150-151`) | Same — DELETE once, then batch inserts. |
| Transaction | `async with dst.transaction()` wraps everything (`:149`) | Same wrapper around all batches → all-or-nothing, identical to today. |
| Errors | any `dst.execute` failure rolls back and raises | Same (a batch failure rolls back the whole copy). |
| Last partial batch | n/a (single-row loop) | `rows[start : start + chunk]` handles the remainder. |
| Chunk derivation | none today | `max(1, min(dst.MAX_PARAMS // max(len(target_cols), 1), dst.MAX_ROWS))` with sanity fallback 500 when the target doesn't expose the constants (mirror `model.py:597-603`). PoolDb exposes `MAX_PARAMS`/`MAX_ROWS` via delegation (02-03 verified). |
| Oracle syntax | row-by-row `INSERT` works | `INSERT ALL` per batch (Q5) — row-equivalence test on real Oracle in engine-heavy. |

**Row-equivalence tests (demand these in 07-03):** (a) SQLite→SQLite with N > chunk rows (force ≥ 2 batches) asserting identical `SELECT *` ordered rows vs pre-change behavior; (b) `preserve_ids=True` and `preserve_ids=False`; (c) `truncate=True`; (d) JSON/datetime columns (translation round-trip); (e) cross-engine SQLite→PostgreSQL and SQLite→MySQL (available locally + CI `test` job) — these are the first multi-engine validations of the multi-VALUES path; (f) atomicity: a poison row mid-stream → whole copy rolled back, source intact; (g) a batch-spying test: wrap `dst.execute` with a counting recorder (or use a fake `Db` exposing `MAX_PARAMS=8`) asserting `ceil(N/chunk)` execute calls — the round-trip reduction proof. Existing tests in `tests/test_transfer.py` are sqlite-only and already cover (b)/(c)/(d) basics — extend, don't replace.

**SQL shape:** `build_multi_insert` in `dialects/builders.py` rendering multi-VALUES for `prefix`/`suffix` kinds and `INSERT ALL` for Oracle's `merge` kind; every table/column through `check_identifier` (DIAL-02/`build_insert:106-107` precedent); values always as bound `{n}` placeholders (never interpolated — `Query` contract). Byte-identical reuse: `insert_many`'s inline gen (`model.py:610-626`) MAY later adopt the same builder — out of scope to refactor in 07-03 unless trivial (see Open Questions); 07-03's own path uses the new builder exclusively.

### Q8 — CI job placement (benchmarks gate)

**New job `benchmarks`** in `.github/workflows/ci.yml`, placed after `deps` (order immaterial — it has no `needs:`):

```yaml
benchmarks:
  name: Benchmarks (gate 2×)
  runs-on: ubuntu-latest
  timeout-minutes: 10
  steps:
    - uses: actions/checkout@v5
    - uses: astral-sh/setup-uv@v5
      with: { version: "0.12.15", python-version: "3.12", enable-cache: true }
    - run: uv sync --group dev
    - run: uv run pytest -m benchmark -q --timeout-method=signal
```

Design points:
- **Single 3.12 leg** (like `engine-heavy`): dialect/CPU semantics don't depend on interpreter micro-version; the gate's floor already absorbs ±20%. Four legs would multiply wall-clock and flake surface.
- **No services, no coverage, no JUnit:** the gate asserts *inside* the tests (median > floor raises `AssertionError`); the `skipped>0` JUnit gate is not applicable (nothing can skip). If a benchmark test ever skips, `-q` shows it and the floor assert still runs.
- **`timeout: 0` global** (pyproject.toml:90) means no hang protection by default — use `@pytest.mark.timeout(60)` on the benchmark module or rely on the job-level `timeout-minutes: 10`. Recommend the marker (pytest-timeout is installed, pin 2.4.0).
- **Main job filter change (REQUIRED):** `ci.yml:137-139` `-m "not optional_engine"` → `-m "not optional_engine and not benchmark"`. Today `testpaths=["tests"]` collects `tests/test_benchmarks.py` in the 4-leg matrix; without the exclusion each leg pays the harness cost and risks wall-clock flake inside the *functional* suite. The benchmark job then runs `-m benchmark` (an explicit, separate invocation — no coerce ambiguity).
- **Marker description:** update pyproject.toml:79 to describe the zero-dep harness (the text "medidos por pytest-codspeed" is now wrong). Name-only assertion in `test_pytest_config.py:106` unaffected.
- **The 2× gate assertion** (inside the test): `assert median_ops > FLOOR, f"SQL build {median_ops:,.0f} ops/s < {FLOOR}"` — deliberate 2× slowdown → ~0.5× baseline → below the 0.6× floor → AssertionError → red CI. p95 and σ only in the failure message for diagnosis.

## Architecture Patterns

### System Architecture Diagram

```text
                       ┌────────────────────────────────────────────────────┐
                       │                    PHASE 7                         │
                       └────────────────────────────────────────────────────┘
  07-01 PROFILER (BEFORE)            07-02 HARNESS + GATE          07-03 BATCH COPY         07-04 BOUNDED TRACER
  benchmarks/profile_workload.py     tests/test_benchmarks.py      transfer.py               observability.py
  └─ cProfile → benchmarks/          └─ pre-optimization sync      └─ chunk formula           └─ deque(maxlen=1024)
     profiles/*.txt committed           baselines locked              min(MAX_PARAMS//n,      └─ retention test for
     BEFORE 07-03                       (median/p95/σ floors)           MAX_ROWS)                 WeakKeyDictionary
                                                                      └─ build_multi_insert         (model.py:30-31)
  ┌──────────────────────────────────────────────────────────────────────────────────────┐
  │                                 CI (.github/workflows/ci.yml)                         │
  │  test matrix: -m "not optional_engine and not benchmark"  ←  filter changed (Q8)      │
  │  benchmarks job: uv run pytest -m benchmark -q   (no services, 3.12, 10 min)          │
  │      └─ floor asserts: median ops/s > 0.6 × baseline → 2× regression → red CI         │
  └──────────────────────────────────────────────────────────────────────────────────────┘
  Data flow: sync units (QueryBuilder._build_full / Query.__init__ / chunk formula)
  are measured directly; copy_table batch path is measured via the multi-VALUES gen
  helper authored by 07-03; profiler artifacts gate the ORDER (07-01 before 07-03).
```

### Recommended Project Structure

```text
benchmarks/
├── profile_workload.py          # 07-01: --mode=cprofile|manual, --scale, --out
└── profiles/                    # 07-01: committed .pstats + .txt (one run per mode)
tests/
└── test_benchmarks.py           # 07-02: @pytest.mark.benchmark, zero-dep harness, floors
encino_orm/
├── dialects/builders.py         # 07-03: build_multi_insert (multi-VALUES + Oracle INSERT ALL)
├── transfer.py                  # 07-03: batch loop in copy_table
└── observability.py             # 07-04: deque(maxlen), latency_window param, docstring window
```

### Pattern 1: Timeit-style harness (CI-safe micro-benchmark)

**What:** a closure + warmup + rep loop + median/p95/σ; **when:** any CPU-only unit; **spec:** see Q2 code sketch. Source: this research (verified by measurement).

### Pattern 2: Batch loop with dialect default (copy_table)

```python
# 07-03 sketch — values ALWAYS bound; identifiers validated once per copy
n_cols = max(len(target_cols), 1)
chunk = max(1, min(getattr(dst, "MAX_PARAMS", 500) // n_cols,
                   getattr(dst, "MAX_ROWS", 1000)))
for start in range(0, len(rows), chunk):
    batch = rows[start : start + chunk]
    q = build_multi_insert(table, target_cols, [serialized(r) for r in batch],
                           strategy=strategy_for(dialect))
    await dst.execute(q)
```

### Pattern 3: Bounded window with documented semantics

```python
from collections import deque
self._latencies = deque(maxlen=1024)   # bounded window — last N queries
# clear() preserves maxlen → reset() unchanged (observability.py:104-106)
```

### Anti-Patterns to Avoid

- **Gating on wall-clock end-to-end async benchmarks** — flaky in CI (roadmap correction #2; plugins can't even measure coroutines).
- **Adding a per-driver `executemany` path bypassing `Query`** — six new code paths, placeholder-style conflicts (aiomysql regex only rewrites `%s`), new error mapping; the round-trip win is already captured by multi-VALUES.
- **Hard-coding ceilings** — always read `MAX_PARAMS`/`MAX_ROWS` off `dst` (PoolDb delegates); a hard-coded 1000 anywhere duplicates dialect knowledge the seam already owns.
- **Benchmark tests leaking into the functional matrix** — the `-m` filter in the `test` job MUST exclude `benchmark` (Q8).
- **Threshold fishing** — if a floor is adjusted silently on every CI failure, the gate becomes advisory; calibration is ONE documented run (Q3), then floors are locked.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Profiling | A custom sampler/timer tree | `cProfile` stdlib + `pstats` text dump | Deterministic, zero-dep, reviewable; py-spy absent. |
| Percentile computation | New quantile code | Existing `_percentile` (`observability.py:26-35`) | Already linear-interpolated and tested via `latency_stats`. |
| Batch SQL dialect shape | `if dialect == "oracle"` branches in `transfer.py` | `build_multi_insert` in `dialects/builders.py` keyed by `InsertStrategy.kind` | DIAL doctrine: dialect is DATA (strategy), not branches; byte-identical SQL maintained in the seam. |
| Bulk insert on PostgreSQL | A new `Db.copy()`/COPY API | multi-VALUES via `Query` (existing `insert_many` mechanism) | New ABC method = six adapters + new error paths; round-trip removal is the actual goal (Q5). |
| Bounded accumulation | Custom ring buffer | `collections.deque(maxlen=...)` | C-implemented, O(1), `clear()` semantics fit `reset()`. |

**Key insight:** every "fast path" proposed here either already exists (`insert_many`'s chunk formula, the multi-VALUES `Query` mechanism, stdlib profiler/statistics) or is a one-function rhythm (`build_multi_insert`, `deque`). The phase's risk is not engineering novelty — it is **measurement honesty**: the profiler commit order (07-01 before 07-03), the calibration discipline (Q3), and keeping the functional CI matrix free of benchmark noise.

## Common Pitfalls

### Pitfall 1: The 2× gate as flake generator
**What goes wrong:** wall-clock floors on shared CI runners trip on an unlucky rep; maintainers "fix" by weakening floors → gate becomes advisory.
**Why:** shared-runner CPU contention is ±20-30% sometimes; a floor at 0.9× baseline fails on noise.
**How to avoid:** 0.6× floors (2× regression still fails — it lands at 0.5×); 9 reps + median; ONE documented calibration run; lock floors thereafter.
**Warning signs:** CI fails only on the benchmark job with median within 20% of floor.

### Pitfall 2: Benchmarks leaking into the functional matrix
**What goes wrong:** `tests/test_benchmarks.py` collected by `testpaths=["tests"]` runs 4× (3.10-3.13) in the `test` job, adding minutes of wall-clock and a flake surface to the functional suite.
**Why:** `-m "not optional_engine"` only excludes `optional_engine`.
**How to avoid:** change to `-m "not optional_engine and not benchmark"` in the SAME PR that adds the benchmark tests (Q8).
**Warning signs:** `test` job runtime grows by the harness duration after 07-02.

### Pitfall 3: Oracle multi-VALUES emits invalid SQL (silent)
**What goes wrong:** `copy_table` batching wholesale-reuses `insert_many`'s SQL gen; on Oracle every batch raises `ORA-00933` (or similar), and the row-equivalence tests (sqlite-only) never catch it.
**Why:** Oracle has no multi-row `VALUES`; no existing test exercises multi-VALUES on Oracle (Q-current-state, CRITICAL gap).
**How to avoid:** `build_multi_insert` with `INSERT ALL … SELECT 1 FROM DUAL` for Oracle; engine-heavy CI test mandatory; the batch formula's only Oracle consumer must be syntax-verified there.
**Warning signs:** `insert_many`/`copy_table` on Oracle failing at first multi-row exec with no earlier unit test.

### Pitfall 4: Unbounded memory sneaking back in via "statistics"
**What goes wrong:** a future dev replaces the deque "to compute exact percentiles" → unbounded list returns (TS-34 regression).
**Why:** `latency_stats` wording currently implies full history.
**How to avoid:** docstring contract "bounded window — last N queries"; bound test (record N+1 → count == N); keep `latency_window` constructor param.
**Warning signs:** no test asserts the bound; copy of historic samples stored elsewhere.

### Pitfall 5: Warning gates exploding benchmark runs
**What goes wrong:** `filterwarnings=["error"]` fails the benchmark job on any DeprecationWarning (e.g., sqlite3 datetime adapter if a benchmark ever touches datetime-bound sqlite inserts).
**Why:** the suite policy is `error`; benchmarks run under the same pytest config.
**How to avoid:** keep benchmark units DB-free/sync; profile workload uses TEXT columns for dates (Q4); never add a benchmark that inserts datetime into sqlite without a deliberate filter entry.
**Warning signs:** green locally (different interpreter) → red CI on warning text.

### Pitfall 6: `Query.rebind` nostalgia
**What goes wrong:** a plan/benchmark references the deleted `rebind` API or a `Query.format` that doesn't exist.
**Why:** prior research text ("Query.format/rebind") predates 02-03's immutability refactor.
**How to avoid:** placeholder-translation unit = `Query(...)` construction and `with_params()` (`query.py:78-103,150-161`) — the only live translation surface.
**Warning signs:** AttributeError `rebind` in benchmark task descriptions.

## Runtime State Inventory

> Not a rename/refactor/migration phase — omitted. No runtime systems carry Phase-7 state: the only "state" is in-repo (benchmarks/, observability.py, ci.yml), all code/config changes.

## Validation Architecture

`workflow.nyquist_validation: true` (`config.json:19`) → required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (+ pytest-asyncio 1.4.0; pytest-timeout 2.4.0 for the benchmark module) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (strict markers, `filterwarnings=["error"]`, `testpaths=["tests"]`) |
| Quick run command | `uv run pytest -m benchmark -q` (benchmark job / local gate) |
| Full suite command | `uv run pytest -q -m "not optional_engine and not benchmark" --timeout-method=signal` (after 07-02) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-03 | Profile committed before optimization | manual gate (commit order) + script reproducibility | `uv run python benchmarks/profile_workload.py --mode=cprofile` | ❌ Wave 0 (07-01 authors) |
| PERF-02 | Floors assert median > 0.6× baseline; 2× regression fails | benchmark (marker) | `uv run pytest -m benchmark -q` | ❌ Wave 0 (07-02 authors) |
| PERF-01 | Batch copy row-equivalence + chunk/round-trip proofs | unit+integration (sqlite local; mysql/pg CI is per-engine files via `ENCINO_ORM_*` env) | `uv run pytest tests/test_transfer.py tests/test_mysql.py tests/test_postgresql.py -q` (+ engine-heavy MSSQL/Oracle) | ❌ Wave 0 (07-03 extends) |
| PERF-04 | deque bound + weak-dict retention | unit | `uv run pytest tests/test_observability.py tests/test_model.py -q` | ❌ Wave 0 (07-04 authors) |

### Sampling Rate

- **Per task commit:** `uv run pytest -q -m "not optional_engine and not benchmark" -x --timeout-method=signal` (functional suite unchanged) + `uv run pytest -m benchmark -q` when the task touched a benchmarked unit.
- **Per wave merge:** full local suite (sqlite) + benchmark job.
- **Phase gate:** full suite green incl. `benchmarks` job in CI before `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `tests/test_benchmarks.py` — harness + floors (07-02)
- [ ] `tests/test_observability.py` — deque-bound test + weak-dict retention test (07-04)
- [ ] `tests/test_transfer.py` — batch row-equivalence + batch-spy round-trip count (07-03)
- [ ] `benchmarks/profile_workload.py` + `benchmarks/profiles/` artifacts (07-01)
- [ ] CI `benchmarks` job + `test` job `-m` filter change (07-02)

## Security Domain

`security_enforcement` is absent from `config.json` → enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no auth surface in this phase) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (partial) | `check_identifier` on every identifier interpolated by the new `build_multi_insert` (DIAL-02 precedent, `build_insert` at `builders.py:106-107`); values always bound `{n}` params |
| V6 Cryptography | no | — (cProfile dumps/benchmarks contain no secrets; do not commit `.pstats` from runs that bind real credentials — workload uses `:memory:`/test creds only) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via introspected column names in the new batch builder | Tampering | Every table/column through `check_identifier` before interpolation; names come from introspection (trusted) but the invariant is fail-closed regardless (DIAL-02 doctrine). |
| Benchmark tests as a CI backdoor (assert-lowering = advisory gate) | Tampering | Floors are constants in the committed test file; calibration is a single documented commit (Q3); no env-var escape hatches. |
| Secret leakage into committed profiler artifacts | Information Disclosure | Profile workload binds only test data; document in 07-01 that `--src-database`/`--dst-database` paths with real credentials must never be profiled into `benchmarks/profiles/`. |

## Sources

### Primary (HIGH confidence)
- [VERIFIED: installed driver source, this machine] — asyncpg 0.31.0 `protocol/prepared_stmt.pyx:130` (`len(args) > 32767` bound); `connection.py:1028` (`copy_records_to_table`); aiosqlite `core.py:245` (`executemany`); aiomysql `cursors.py:16-17,246` (`executemany` = `%s`-only bulk rewrite); aioodbc `cursor.py:135`; oracledb `cursor.py:863`.
- [VERIFIED: empirical probes, local] — SQLite 32767 OK/32768 FAIL; postgres 32766 OK/32768 client-raise; mysql 65538 OK; 1000-row multi-VALUES OK; sync-unit baselines (Q3 table); docker engine availability.
- [VERIFIED: repository source] — all Current-State table rows with file:line (`model.py:30-31,597-603,610-626`; `observability.py:71,81,104-106`; `transfer.py:144-158`; `strategies.py:106-158`; `query.py:78-103,150-161`; `ci.yml:137-139`; pyproject.toml:62-90,130-132,293-321).
- [CITED: sqlite.org/limits.html + sqliteLimit.h] — `SQLITE_MAX_VARIABLE_NUMBER` default 32766.
- [CITED: learn.microsoft.com table-value-constructor] — INSERT…VALUES ≤ 1,000 rows, error 10738.
- [CITED: learn.microsoft.com maximum-capacity-specifications] — 2,100 parameters per stored procedure/UDF.
- [CITED: dev.mysql.com/refman/8.0/en/prepare.html + error 1390] — 65,535 placeholder cap for prepared statements.
- [CITED: docs.oracle.com plsql-program-limits (18c/26)] — bind vars per program unit 32768; [CITED: python-oracledb docs] — IN-list 1000 (pre-23c)/65535 (23ai).

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — roadmap correction #2 (plugins don't measure coroutines; verified by reading plugin source 2026-09-17); pytest-codspeed `return target(*args, **kwargs)` citation; TS-34/TS-38/TS-39 context.
- `.planning/phases/02-dialect-seam-engine-parity/02-03-SUMMARY.md` — DIAL-06 delivery (LIMITS + chunk derivation + PoolDb delegation); `insert_many` chunk test with fake limits (`MAX_PARAMS=15`).

### Tertiary (LOW confidence, flagged)
- Oracle "65535 binds per SQL statement" (LIMITS provenance) — no citable official doc found; must be probed in engine-heavy CI (Q1.1).
- MSSQL 2100 parameter cap applied to *ad-hoc* parameterized multi-VALUES statements (documented for stored procs/UDFs) — flagged for the engine-heavy sonda referenced in `ci.yml:339-344`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| "copy_table is row-by-row; batch it via insert_many's SQL" (project planning) | Batch with per-dialect `build_multi_insert`, Oracle diverges to INSERT ALL | Phase 7 (this research) | Oracle-safe batching; the insert_many reuse assumption was FALSE for Oracle |
| "pytest-codspeed measures benchmarks" (marker text, pyproject.toml:79) | Zero-dep pure-Python harness; marker text corrected | Phase 7 | No new dependency; gate = floors vs 2× regression |
| Unbounded `QueryTracer._latencies` (TS-34) | `deque(maxlen=1024)` + documented window | Phase 7 | Bounded memory in long-lived processes |
| "mysql 65535 = protocol counter" (LIMITS provenance) | "65535 = prepared-statement cap; text-protocol path is packet-bound" | Phase 7 (probe) | Provenance accuracy; the LIMITS value itself is unchanged |

**Deprecated/outdated:**
- `Query.rebind` — deleted in Phase 2; the translation benchmark targets `Query.__init__` + `with_params()` (research brief's "Query.format/rebind" wording is stale).
- pytest-codspeed/pytest-benchmark as the *stated* benchmark layer (prior research recommendations in `.planning/research/STACK.md`) — superseded by the zero-dep harness for this phase's sync-only scope; revisit only if wall-clock gates prove unmanageable (Open Questions).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CI ubuntu-latest CPU performance is within ±20% of the local Windows box for these sync units | Q3 | First CI run fails a floor by ≤20% → mitigated by the ONE documented calibration run |
| A2 | Oracle `INSERT ALL` with `chunk = min(65535 // n_cols, 1000)` binds is accepted by Oracle (real ceiling unknown) | Q1.1, Q5 | First Oracle batch fails → lower `LIMITS["oracle"].max_params` to 32768, re-run; does NOT affect other engines |
| A3 | `_percentile` sort of 1,024 floats in `latency_stats` is acceptable frequency-wise | Q6 | If stats() is called per-query, add ~60 µs/query overhead → document that stats() is on-demand, not per-record |
| A4 | asyncpg multi-VALUES round-trip reduction is the dominant win vs COPY wire-format for this milestone | Q5 | If a user copies 100M rows, COPY becomes worth the new Db API — tracked as v2 item, not phase scope |
| A5 | 3.12 single leg for the benchmark job is representative | Q8 | If a future CPython changes hot-path perf between 3.10-3.13 > 2×, floors need re-measurement — the 0.6× headroom covers current spread |

## Open Questions

1. **Oracle `max_params` true value.** What we know: 65535 (LIMITS) is uncited folklore; 32768 is the documented PL/SQL unit bound; engine unavailable locally. Unclear: the real SQL-statement bind cap on Oracle 23ai-free. Recommendation: 07-03's engine-heavy task includes a small probe (INSERT ALL with an oversized chunk) and corrects `LIMITS["oracle"]` + provenance from the measured value. Do NOT block the phase on it — the failure mode is a clear error, not silent corruption.
2. **Should 07-03 also refactor `insert_many` to reuse `build_multi_insert`?** Pros: one multi-VALUES generator, one bench target. Cons: touches a tested hot path in a correctness-milestone phase; byte-identical SQL must be asserted. Recommendation for the planner: delegate — 07-03 authors the builder for `copy_table`; unifying `insert_many` is a follow-up unless the diff is trivially byte-identical (an SQL-snapshot comparison decides; do not force it).
3. **Benchmark calibration ownership.** What we know: local baselines → 0.6× floors (Q3). Unclear: exact CI numbers. Recommendation: 07-02's plan contains an explicit "first CI run calibrates within ±20%, same commit" task; a second adjustment without a documented reason must be review-blocked.
4. **sqlite3 datetime adapter fix (pyproject.toml:62-71) lists Phase 7 as a candidate owner.** It is NOT required by PERF-01..04 and the benchmark units avoid the path. Keep out of scope unless a plan wants it as a hygiene bonus — flag in the plan's risks if so.
5. **pytest-benchmark/codspeed re-entry.** If the zero-dep harness proves flaky in CI beyond the calibration tolerance, the fallback is pytest-benchmark 5.3.0 local-only `--benchmark-json` baselines (no gate), or codspeed's simulation mode as a *service-backed* gate. Neither is needed today.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| CPython (local venv) | measurements, probing | ✓ | 3.13.7 | — |
| uv | lock/sync/CI parity | ✓ | 0.12.15 | — |
| Docker: PostgreSQL 16-alpine | postgres probes + cross-engine tests | ✓ | 16 (container) | CI service `postgres:16-alpine` |
| Docker: MySQL 8.0 | mysql probes + cross-engine tests | ✓ | 8.0 (container) | CI service `mysql:8.0` |
| Docker: MariaDB 11 | parity check | ✓ | 11 (container) | CI service `mariadb:11` |
| Docker: Redis | n/a for this phase | ✓ | latest (container) | — |
| MSSQL 2022 | MSSQL ceiling probe (2100, 1000-row cap) | ✗ local | — | **CI `engine-heavy` job only** (ODBC driver install there) |
| Oracle XE/Free | Oracle ceiling probe + INSERT ALL test | ✗ local | — | **CI `engine-heavy` job only** |
| py-spy | PERF-03 profiler (preferred) | ✗ local | — | **cProfile (stdlib)** — committed artifact per recommendation |

**Missing dependencies with no fallback:** none — every requirement has a CI path or a stdlib answer.
**Missing dependencies with fallback:** MSSQL and Oracle probing/tests move to the existing `engine-heavy` CI job (single 3.12 leg, `uv sync --extra mssql --extra oracle`, env vars already wired at `ci.yml:308-356`); py-spy → cProfile.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies by design; every component verified by execution this session.
- Architecture: HIGH for the multi-VALUES + INSERT ALL design (syntax facts verified); MEDIUM for the wall-clock-gate robustness (A1/A3).
- Pitfalls: HIGH — each pitfall tied to verified file:line facts or measured probes.

**Research date:** 2026-09-19
**Valid until:** 2026-10-19 (30 days; driver-version-sensitive ceilings re-verify if asyncpg/aiomysql/oracledb pins move)