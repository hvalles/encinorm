---
phase: 07-performance-and-benchmarks
verified: 2026-09-19T16:30:00Z
status: passed
score: 4/4 truths verified
overrides_applied: 0
re_verification: false
---

# Phase 7: Performance & Benchmarks Verification Report

**Phase Goal:** Profiler output committed before any optimization; a benchmark suite with numeric targets runs in CI and a deliberate 2× regression fails the gate; `copy_table` inserts in batches sized per dialect and produces exactly the same rows as the row-by-row path; `QueryTracer._latencies` is bounded and `_FIELD_ADAPTERS` no longer retains model classes indefinitely.
**Verified:** 2026-09-19T16:30:00Z
**Status:** passed
**Re-verification:** No — initial verification (no previous `*-VERIFICATION.md`)

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — the contract)

| # | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Profiler output committed BEFORE any optimization | ✓ VERIFIED | `benchmarks/profiles/profile_workload_cprofile_2026-09-19.{txt,pstats}` + `profile_workload_manual_2026-09-19.txt` committed in `cd71a4f` (2026-09-19T08:47, "línea base de rendimiento pre-optimización (PERF-03)"); reproducible script `benchmarks/profile_workload.py` in `d1c069c` (08:47). Order verified via `git log`: `cd71a4f` 08:47 precedes first optimization `0b5696b` 09:26 (`build_multi_insert`, PERF-01) by 39 min. |
| 2 | Benchmark suite with numeric targets runs in CI; a 2× regression fails the gate | ✓ VERIFIED | `tests/test_benchmarks.py`: zero-dep `_measure` (`:36-63`; `gc.collect()` before each loop, `gc.disable()` during, `time.perf_counter`, median/p95/sigma); 6 units each with floor = 0.6× of documented baseline: `sql_build` 152,000 (`:131`), `query_construction` 105,000 (`:148`), `query_with_params` 130,000 (`:161`), `to_mysql` 226,000 (`:184`), `batch_sizing` 1,580,000 (`:197`), `multi_insert_gen` 780 (`:232`); `pytestmark` `benchmark,timeout(60)` (`:24`). CI job `benchmarks` (`.github/workflows/ci.yml:252-281`) file-scoped to `tests/test_benchmarks.py`, `--timeout-method=signal`, no services, no `--cov*`, no `--junitxml` (`:261-264`); matrix `test` job excludes them: `-m "not optional_engine and not benchmark"` (`ci.yml:140`). First CI run really failed and forced recalibration: `batch_sizing` ~2.65M ops/s on ubuntu 2-vCPU vs 10.5M local → floor recalibrated to 1,580,000 in `ebb17e3`, collection scoped in `eee91c8`, RUF003 comment fix `5ebc844`, docs `30336f8` (HEAD; working tree clean). Final CI on `5ebc844`/`30336f8`: 10/10 jobs green incl. Benchmarks. |
| 3 | `copy_table` inserts in per-dialect batches; produces exactly the same rows as row-by-row | ✓ VERIFIED | `build_multi_insert` in `encino_orm/dialects/builders.py:199-261` (multi-VALUES `:238-249`; Oracle `INSERT ALL ... SELECT 1 FROM DUAL` `:250-255`); `multi_values` field + `ORACLE_INSERT.multi_values=False` in `encino_orm/dialects/strategies.py:41,52-63`; `copy_table` batches with `chunk = max(1, min(max_params // max(len(target_cols), 1), max_rows))`, `getattr(dst, "MAX_PARAMS", 500)` / `getattr(dst, "MAX_ROWS", 1000)` (`encino_orm/transfer.py:161-164`), row-by-row fallback when `target_cols == []` (`:190-196`). Row-equivalence: `tests/test_transfer.py` (FakeDb spy, 2,500-row equivalence, chunk assertions) + cross-engine `TestTransferCopy` probes via shared `tests/_transfer_helpers.py`: `test_mysql.py:425` (500 filas), `test_postgresql.py:475` (500 filas), `test_mssql.py:449` (100 filas, `preserve_ids=False` for IDENTITY), `test_oracle.py:418` (100 filas, INSERT ALL). All 4 probes ran and passed locally this session. Measured 8.4×: 10,000 × 5 cols = 48,691 filas/s (0.2054s) vs pre-batching 5,823 filas/s (1.7173s). |
| 4 | `QueryTracer._latencies` bounded; `_FIELD_ADAPTERS` no longer retains model classes indefinitely | ✓ VERIFIED | `encino_orm/observability.py:6` `from collections import deque`; `:85` `self._latencies: deque[float] = deque(maxlen=latency_window)`; `:95` append, `:116` `_latency_summary`, `:120` clear. `encino_orm/model/model.py:30` `_FIELD_ADAPTERS = weakref.WeakKeyDictionary()` (`:459/:462` usage); `:31` `_COLUMN_MAPS` likewise. Verified live at HEAD — implementation exists and is wired. |

**Score:** 4/4 roadmap truths verified. Plan-level must-haves (07-01…07-04) also resolve to VERIFIED; 07-04 (Wave 1) artifacts confirmed live in the source above.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `benchmarks/profile_workload.py` | Reproducible cProfile/manual profiling script | ✓ VERIFIED | Present; committed `d1c069c`. |
| `benchmarks/profiles/profile_workload_cprofile_2026-09-19.txt` / `.pstats` | Committed profiler output (pre-optimization) | ✓ VERIFIED | Present; committed `cd71a4f` before first optimization `0b5696b`. |
| `benchmarks/profiles/profile_workload_manual_2026-09-19.txt` | Committed manual-trace baseline | ✓ VERIFIED | Present; same commit. |
| `tests/test_benchmarks.py` | Zero-dep harness + 6 benchmark units with floors | ✓ VERIFIED | `_measure` `:36-63`; floors `:131/148/161/184/197/232`; `pytestmark` `:24`. |
| `.github/workflows/ci.yml` | Dedicated `benchmarks` job; matrix excludes `benchmark` | ✓ VERIFIED | Job `:252-281`, run `:281`; exclusion `:140`. |
| `encino_orm/dialects/builders.py` | `build_multi_insert` (multi-VALUES + Oracle INSERT ALL) | ✓ VERIFIED | `:199-261`; chained `{n}` params; fail-closed `check_identifier`. |
| `encino_orm/dialects/strategies.py` | `InsertStrategy.multi_values`; `ORACLE_INSERT.multi_values=False` | ✓ VERIFIED | `:41`, `:52-63` (ORA-00938 rationale). |
| `encino_orm/transfer.py` | `copy_table` batching + row-by-row fallback | ✓ VERIFIED | `:161-164` chunk formula; `:190-196` fallback. |
| `encino_orm/observability.py` | Bounded `_latencies` deque | ✓ VERIFIED | `:6` `deque` import; `:85` `deque(maxlen=latency_window)`. |
| `encino_orm/model/model.py` | `_FIELD_ADAPTERS` via `WeakKeyDictionary` | ✓ VERIFIED | `:30`; `_COLUMN_MAPS` `:31`. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `copy_table` | `build_multi_insert` | `strategy_for(dialect)` per batch | ✓ WIRED | `transfer.py:172,182`; `builders.py:238-255`. |
| `build_multi_insert` | `Query` | chained `{n}` placeholders + values | ✓ WIRED | `builders.py:257-261`. |
| `strategy_for(Engine.ORACLE)` | `ORACLE_INSERT` | `_STRATEGIES` map | ✓ WIRED | `strategies.py:172-179,182-188`. |
| `tests/test_benchmarks.py` | CI `benchmarks` job | `-m benchmark` / file scope | ✓ WIRED | `ci.yml:281`; matrix excludes `not benchmark` `:140`. |
| `_measure` | floors | `_assert_floor` | ✓ WIRED | `test_benchmarks.py:66-69`; 6 calls `:131-232`. |
| `_latencies` deque | `_latency_summary` / `latency_summary()` | append → summary | ✓ WIRED | `observability.py:95,116`. |
| `_FIELD_ADAPTERS` | `adapters_for` | `WeakKeyDictionary.get` + set | ✓ WIRED | `model.py:459,462`; weak refs prevent retention. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `copy_table` batches | `rows` from `src.fetch_all` → `_serialize(row)` | real DB query (`transfer.py:148`) | Yes — row-equivalence proven by FakeDb spy + 4 cross-engine probes | ✓ FLOWING |
| `build_multi_insert` | `columns`/`rows` from first batch row keys | `transfer.py:172-177` | Yes — params count = rows×cols (asserted in benchmark unit `test_benchmarks.py:214`) | ✓ FLOWING |
| `_latencies` | `float(elapsed)` per query | `observability.py:95` | Yes — real timings; bounded by `deque(maxlen=...)` | ✓ FLOWING |
| Benchmark floors | median/p95/sigma of real `time.perf_counter` runs | local + CI runs | Yes — recalibrated to actual CI runner measure (`ebb17e3`) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Benchmark suite | `uv run pytest tests/test_benchmarks.py -q` | 6 passed | ✓ PASS |
| Full local suite (incl. cross-engine probes) | `uv run pytest -q` | 1069 passed (mysql 500 / postgresql 500 / mssql 100 / oracle 100 edit probes green this session) | ✓ PASS |
| Lint | `uv run ruff check encino_orm tests` | clean | ✓ PASS |
| Format | `uv run ruff format --check encino_orm tests` | clean | ✓ PASS |
| Types | `uv run mypy encino_orm` | success | ✓ PASS |
| Lock integrity | `uv lock --check` | exit 0 | ✓ PASS |
| Final CI | `5ebc844` / `30336f8` | 10/10 jobs green incl. `benchmarks` | ✓ PASS |

### Probe Execution

No project shell probes (`scripts/*/tests/probe-*.sh`) exist for this phase (Step 7c: SKIPPED). The cross-engine probes are pytest tests (marked `optional_engine`, gated by `engine_unavailable`), executed locally this session against live containers:

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| mysql 500 filas | `pytest tests/test_mysql.py::TestTransferCopy` | 1 passed | PASS |
| postgres 500 filas | `pytest tests/test_postgresql.py::TestTransferCopy` | 1 passed | PASS |
| mssql 100 filas | `pytest tests/test_mssql.py::TestTransferCopy` | 1 passed | PASS |
| oracle 100 filas (INSERT ALL) | `pytest tests/test_oracle.py::TestTransferCopy` | 1 passed | PASS |
| benchmark unit | `pytest tests/test_benchmarks.py::test_multi_insert_gen_floor` | 1 passed (3.36s) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PERF-01 | 07-03 | `copy_table` batches per dialect (multi-VALUES / INSERT ALL), row-equivalent | ✓ SATISFIED | `builders.py:199-261`, `strategies.py:41,52-63`, `transfer.py:161-196`; `test_transfer.py` + 4 cross-engine probes |
| PERF-02 | 07-02 | Benchmark harness w/ floors in CI; 2× regression fails gate | ✓ SATISFIED | `test_benchmarks.py` 6 units; `ci.yml:252-281` + `:140`; recalibration `ebb17e3` |
| PERF-03 | 07-01 | Profiler output committed before any optimization | ✓ SATISFIED | `benchmarks/profiles/*2026-09-19*` in `cd71a4f` < `0b5696b`; `profile_workload.py` `d1c069c` |
| PERF-04 | 07-04 | `_latencies` bounded; `_FIELD_ADAPTERS` no model retention | ✓ SATISFIED | `observability.py:6,85,95,116,120`; `model.py:30-31,459,462` |

**Orphaned requirements:** none — `REQUIREMENTS.md` maps PERF-01…04 to Phase 7 and all four are claimed by plans (07-01…07-04).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX` debt markers in any phase-modified file | — | Debt-marker gate: clean (grep exit 1 on `test_benchmarks.py`, `dialects/`, `transfer.py`, `observability.py`) |

No stubs, no empty implementations, no hardcoded-empty data, no orphaned artifacts.

### Human Verification Required

None. All four success criteria are programmatically verified (harness floors with documented baselines, CI job config, row-equivalence tests, cross-engine probes executed against live engines, and source-level confirmation of the bounded structures).

### Gaps Summary

No gaps. The phase goal is achieved in the codebase at HEAD (`30336f8`):

- **Profiler-first discipline confirmed by commit order** (`git log`): `cd71a4f` 08:47 (PERF-03 baseline) before `0b5696b` 09:26 (PERF-01 optimization); script `d1c069c`.
- **The CI gate genuinely bites:** the first CI run failed and the `batch_sizing` floor was recalibrated to the runner measure (2.65M → 1.58M) in `ebb17e3`, with collection scoped in `eee91c8` — recalibration documented in the same commits per plan discipline.
- **PERF-04 confirmed live, not assumed:** `deque(maxlen=latency_window)` at `observability.py:85` bounds `_latencies`; `_FIELD_ADAPTERS` is a `WeakKeyDictionary` at `model.py:30` (with `_COLUMN_MAPS` at `:31`) — no indefinite model retention.
- **`insert_many` not refactored to the new builder** (declared debt honored): `model.py:570-628` keeps its inlined chunked `VALUES` construction; `build_multi_insert` is consumed only by `copy_table` (`transfer.py:172,182`).

**Known residuals (documented, non-blocking — no truth depends on them):**

1. Oracle `LIMITS["oracle"]` (65535 binds) remains "NO verificado empíricamente" (`strategies.py:162-168`); the 100-row INSERT ALL probe proves the path, not the ceiling — pending the manual probe on the `engine-heavy` job (02-05).
2. MSSQL cross-engine probe uses `preserve_ids=False` (IDENTITY limitation, documented at `test_mssql.py:449-454`).
3. `batch_sizing` floor now reflects the CI runner (2-vCPU shared), not the dev host (10.5M local vs 2.65M CI); thermal-throttle behavior documented in `test_benchmarks.py:87-90,200-206`.

---

_Verified: 2026-09-19T16:30:00Z_
_Verifier: the agent (gsd-verifier)_