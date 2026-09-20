# Roadmap: encino_orm — Production Hardening (0.2.6 → 0.3.0)

## Overview

This is a **correctness release, not a feature release**. `encino_orm` already has broad engine and
API coverage; what it lacks is the reliability, security and operability contract that production
users assume an ORM already honors. Nearly every P1 item is a *guarantee to be established*, not a
capability to be added.

The work is a strictly ordered hardening campaign: build a safety net that can actually fail
(Phase 1) → create one dialect seam and prove engine parity (Phase 2) → settle data-correctness
semantics (Phase 3, parallel to 2) → make the pool correct under concurrency (Phase 4) → add
resilience to connection loss (Phase 5) → remove mutable-global and `exec()` indirection (Phase 6) →
measure before optimizing (Phase 7) → ship the deprecation path and release (Phase 8).

**Core value:** correct under concurrency, safe against injection and misconfiguration, predictable
in performance — on any of the six engines.

**Brownfield note:** the layered architecture (`Db` ABC → six adapters → `Model`/`Filter`/
`QueryBuilder` → optional lazy layers) is sound and must be preserved. Every phase is scoped to
*where a concern belongs* inside existing layers; no phase may regress the import-lazy contract, the
`contextvars` state model, or adapter-localized dialect behavior.

**Mode note:** las ocho fases están en `**Mode:** standard`. El flag `mvp` se retiró de todas ellas
tras la verificación de la Fase 1: este milestone es hardening/infraestructura (dialectos, datos,
pool, resiliencia, config, rendimiento, release) y ninguna fase entrega un user flow, así que la
guía de "vertical slice" no aplica. Ver `01-HUMAN-UAT.md` ítem 3 para el caso original.

## Hard Ordering Constraints

These are not preferences. Violating any of them invalidates later verification.

1. **CI gates before any breaking change.** CI-09 (pool invariant characterization tests) must land
   *before* POOL work begins — a pool refactor cannot be verified against tests written afterwards.

2. **Centralize before validating.** DIAL-01 is a separate, zero-behavior-change commit. DIAL-02
   (validation) is a separate, bisectable commit on top of it. Merging them makes the security change
   unbisectable and lets it silently miss five of six dialects.

3. **POOL-01…POOL-06 are one unit.** They mutate the same pool bookkeeping and the same release path;
   splitting them across phases or releases invites conflicting fixes.

4. **RESL depends on POOL.** Reconnect and health checks need the `PooledConnection` handle and the
   generation counter to exist first.

5. **PERF depends on DIAL constants + POOL.** Batch sizing needs per-dialect `MAX_PARAMS`/`MAX_ROWS`;
   the idle-reaper work needs the pool handle.

6. **REL is sequenced before the first breaking change reaches users.** 0.2.7 (runtime deprecations)
   → 0.3.0rc1 → 0.3.0, in that order, on PyPI. 0.2.7 is cut from the `v0.2.6` maintenance line, **not**
   from hardened `main` — the deprecations describe the old behavior while it still exists.

7. **DATA runs parallel to DIAL.** Disjoint modules (`migration.py`, `model/cached.py`,
   `model/cache_backend.py` vs. `dialects/`, `query.py`, adapters). No file overlap.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Safety Net — CI Gates & Test Infrastructure** - Make CI able to fail: lint, types, per-engine coverage, required-engine switch, and pool characterization tests before any refactor (completed 2026-09-17)
- [x] **Phase 2: Dialect Seam & Engine Parity** - One identifier-validation choke point, shared DML builders, `Query` correctness, and proof that count/paginate/list_tables work on all six engines (completed 2026-09-18)
- [x] **Phase 3: Data Correctness** - Migration ledger, atomic-or-reconciled `migrate()`, and `CachedModel` write-invalidation (parallel to Phase 2) (completed 2026-09-18)
- [x] **Phase 4: Pool Correctness & Concurrency** - `PooledConnection` handle, race-free `acquire()`, in-insert `last_id`, explicit release policy, lazy reaper, deterministic stress tests (completed 2026-09-19)
- [x] **Phase 5: Resilience** - Classified disconnects, single reconnect outside transactions, `pre_ping`/lifetime for direct connections, public error taxonomy (completed 2026-09-19)
- [x] **Phase 6: Config & Optional-Layer Hygiene** - `ConnectionRegistry` + `SecurityConfig` replace mutable globals; `exec()` codegen becomes closures; trust boundaries documented (completed 2026-09-19)
- [x] **Phase 7: Performance & Benchmarks** - Profile first, then batched `copy_table`, a benchmark gate that fails a 2× regression, and bounded tracer/cache structures (completed 2026-09-19)
- [ ] **Phase 8: Release 0.3.0** - 0.2.7 deprecation release, OIDC trusted publishing, 0.3.0rc1, complete CHANGELOG + MIGRATION-0.3.md, README pinning guidance

## Phase Details

### Phase 1: Safety Net — CI Gates & Test Infrastructure

**Goal**: CI can actually fail. Lint, format, types, per-engine coverage, a required-engine switch and
pool characterization tests all exist and block merge, so that every later "fix verified" claim is
backed by a signal that would have caught the `COUNT(*)` bug.
**Mode:** standard
<!-- El flag `mvp` se retiró en la verificación de Fase 1: es una fase de infraestructura de CI, sin user flow (ver 01-HUMAN-UAT.md, ítem 3). -->
**Depends on**: Nothing (first phase)
**Requirements**: CI-01, CI-02, CI-03, CI-04, CI-05, CI-06, CI-07, CI-08, CI-09
**Success Criteria** (what must be TRUE):

  1. Removing a required engine's CI service makes its job **fail**, not skip
  2. Any skipped test fails the CI job through the JUnit-XML `skipped > 0` gate
  3. A lint, format, or type violation, or a coverage drop below the ratchet floor, fails CI before merge
  4. A publish attempt cannot run while CI gates are red
  5. Pool invariant characterization tests exist and pass against the **unmodified** pool

**Plans**: 5 plans
**Research**: not needed — ruff/mypy/pytest-cov/uv configuration is exhaustively documented in STACK.md with version-verified config sketches

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Upgrade `uv` to 0.12.15, land ruff format-only commit (registered in `.git-blame-ignore-revs`), then the narrow `ruff check` ruleset as a blocking CI job — CI-03

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — `mypy` non-strict with `--warn-unused-ignores` + `py.typed` marker, and the dependency/vulnerability scanning job (`uv lock --check`, `uv audit`, `pip-audit`) — CI-04, CI-07

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Harden pytest config (`--strict-markers`, `xfail_strict`, `filterwarnings = ["error"]`, both loop scopes, declared markers) and wire `pytest-cov` with `parallel = true`, per-engine `COVERAGE_FILE` + `coverage combine`, low ratchet floor — CI-05, CI-06

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — `ENCINO_ORM_REQUIRE_ENGINES` switch that fails instead of skipping, JUnit-XML post-run `skipped > 0` gate, and `release.yml` `needs:` CI — CI-01, CI-02, CI-08

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 01-05-PLAN.md — Characterization tests for pool invariants (checkout cap, `last_id` scoping, release semantics, `close()` behavior) written against the current implementation — CI-09

**Waves:** 1 → 01-01; 2 → 01-02; 3 → 01-03; 4 → 01-04; 5 → 01-05. The chain is forced by `pyproject.toml` and `ci.yml` overlap across 01-01…01-04; 01-05 lands last so its characterization tests are validated against every gate above them. 01-02 is the only non-autonomous plan (a blocking package-legitimacy checkpoint).

### Phase 2: Dialect Seam & Engine Parity

**Goal**: Identifier validation and DML construction live in exactly one place inside the core, and the
library demonstrably returns correct results on all six engines — not just SQLite.
**Mode:** standard
**Depends on**: Phase 1
**Requirements**: DIAL-01, DIAL-02, DIAL-03, DIAL-04, DIAL-05, DIAL-06, DIAL-07, DIAL-08, DIAL-09
**Success Criteria** (what must be TRUE):

  1. `_check_identifier` lives in exactly one module and all six adapters import it, with the existing suite passing unchanged (pure-refactor proof)
  2. `insert`/`update`/`delete` reject an invalid table or column with `ValueError` before the driver is reached, on all six engines; `sync_schema` rejects introspection-derived names before interpolating them into `ALTER TABLE`
  3. `count`/`paginate`/`list_tables` return correct results on PostgreSQL, SQL Server and Oracle — no `KeyError: 'COUNT(*)'`
  4. `Query` is immutable and hashable, **`with_params()` returns a copy** (`rebind` is DELETED per D-01/D-06, not fixed), per-dialect `MAX_PARAMS`/`MAX_ROWS` constants exist, and committed SQL snapshots assert dialect output on the always-on SQLite job
  5. The CI matrix runs per-engine integration tests for `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` on MariaDB, Redis, MSSQL and Oracle

**Plans**: 5 plans executed + 4 gap-closure plans (`02-06`…`02-09`, added after verification returned `gaps_found`)
**Research**: needed — syrupy dialect-snapshot adoption, `testcontainers` Oracle/MSSQL topology, and the `Query` immutability refactor shape are design recommendations without documented consensus

Plans:

**Wave 1**

- [x] 02-01-PLAN.md — Centralize `_IDENTIFIER_RE`/`_check_identifier` into `dialects/identifiers.py` as a pure refactor with zero behavior change, in its own commit — DIAL-01

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Shared `dialects/builders.py` + `strategies.py` with `build_insert`/`update`/`delete`/`build_upsert` validating every table and column; `Model.upsert`'s dialect branches (`ON DUPLICATE KEY`/`MERGE`/`ON CONFLICT`) move into the seam; validate introspection-derived identifiers in `sync_schema` before `ALTER TABLE`; `PoolDb.insert` stops dropping `conflict` — DIAL-02, DIAL-04

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — `Query` correctness (regex over real `{n}`, immutable/hashable, `rebind` replaced by `with_params()`) plus per-dialect `MAX_PARAMS`/`MAX_ROWS` constants with provenance — DIAL-05, DIAL-06

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-04-PLAN.md — Dialect-correct `AS n` alias for `count`/`paginate`/`list_tables` **and** `QueryBuilder.sum/avg/min/max` (7 sites, not 3), with per-engine integration tests covering `sync_schema` and `last_id` as well — DIAL-03, DIAL-09

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 02-05-PLAN.md — Per-dialect SQL snapshots via syrupy on the always-on SQLite job, the full multi-engine CI matrix (MariaDB + Redis as services; MSSQL/Oracle in a separate single-Python-version job), and the per-module coverage-floor gate owed by Phase 1 D-04/D-06 — DIAL-07, DIAL-08

**Waves:** 1 → 02-01; 2 → 02-02; 3 → 02-03; 4 → 02-04; 5 → 02-05. The chain is fully serial: `02-01` must be a pure-refactor commit before any validation lands (Hard Ordering Constraint #2); `02-02`'s builders need the `Query` construction contract that `02-03` finalizes, and its acceptance is byte-identical SQL; `02-04` fixes the aggregate result keys on top of the settled `Query`; `02-05` freezes the SQL in snapshots and proves parity in CI. `02-05` is the only non-autonomous plan (a blocking `syrupy` package-legitimacy checkpoint).

**Deviation from the roadmap's original 3-task cap:** `02-02` carries 5 tasks and `02-05` carries 4, documented in-plan with reasons (atomic seam + `Model.upsert` absorption in the first; a blocking package-legitimacy checkpoint in the second). Splitting `02-02` would break the byte-identical-SQL acceptance oracle and the `02-VALIDATION.md` task map.

**Gap closure (added after `02-VERIFICATION.md` returned `gaps_found`).** The five ROADMAP Success Criteria pass, but the two goal clauses do not hold as functional statements. Four new plans close the verified gaps. They do NOT re-run `02-01`…`02-05`; they extend the seam those plans built.

**Wave 1** *(independent of each other; both build on the executed `02-01`…`02-05`)*

- [x] 02-06-PLAN.md — Make the identifier allowlist a real choke point: validate `QueryBuilder`'s `alias=`/`join()`/`join_subquery()` aliases and the default pydantic field name in `_build_column_map`, and close the raw `indexes_ddl` fallback — closes GAP 1 (CR-01 reproduced SQL-injection primitive + WR-06) — DIAL-01, DIAL-02
- [x] 02-07-PLAN.md — Enforce `Query`'s documented cardinality contract (no `indices and` carve-out) and compile from the normalised index so `{00}` cannot leak a `KeyError`; sync the published `docs/design/0-design.md` §2.1 sketch and example with the code and guard it with a source test — closes GAP 2 (WR-01/WR-02/WR-07) — DIAL-05

**Wave 2** *(blocked on `02-06`: shared `query_builder.py` / `model/model.py` / `test_query_builder.py`)*

- [x] 02-08-PLAN.md — Engine parity: route `QueryBuilder.all()/first()/exists()` through `fetch_many`/`fetch_one` and cover them on all six engines (today: zero coverage); make MariaDB `upsert` emit `ON DUPLICATE KEY UPDATE`; derive `Model.insert(replace=True)`'s conflict target from the primary key — closes GAP 3 (WR-03/WR-04/WR-05) — DIAL-02, DIAL-03, DIAL-09

**Wave 3** *(blocked on `02-08`: same six per-engine test files and the same `deferred-items.md`)*

- [x] 02-09-PLAN.md — Fix `Db.list_tables(name=)` on the four engines where it is dead (filter on a real column of a derived table, value bound, `LOWER()` on both sides), with a per-engine test and a DB-free dialect snapshot — closes GAP 4 and leaves no unowned deferral — DIAL-03, DIAL-09
- [x] 02-10-PLAN.md — Validate `QueryBuilder`'s `_table` (constructor) and each join target's `_table` with the strict allowlist, and sweep every remaining interpolation point — closes GAP A / CR-01 — DIAL-01, DIAL-02
- [x] 02-11-PLAN.md — Fail closed in `_merge_sql` when a conflict column is absent from the INSERT columns (CR-02, `Model.upsert` on MSSQL/Oracle), and stop `Model.insert` consuming a stale `last_id()` on a MERGE (CR-03, the regression 02-08 introduced) — DIAL-02, DIAL-09
- [x] 02-12-PLAN.md — Document the 02-07 `Query` cardinality change in `CHANGELOG.md` and correct the false "no unowned items" claim in `deferred-items.md`, assigning the Oracle ORA-38104 limitation to Phase 4 / `04-02` / POOL-03 — DIAL-02, DIAL-05

**Gap-closure waves (round 1):** 1 → `02-06`, `02-07`; 2 → `02-08`; 3 → `02-09`. **Round 2:** 1 → `02-10`, `02-11`; 2 → `02-12`. GAP 5 (per-adapter coverage floors) stays deferred pending a green `engine-heavy` run and is NOT planned here; the gap-closure plans do not contradict it.

**Gap closure ronda 3 (02-10…02-12).** The re-verification returned `gaps_found` with three BLOCKER (CR-01: `QueryBuilder._build_base()` interpolated an unvalidated `_table` into `FROM`/`JOIN`; CR-02: `Model.upsert()` with its documented default conflict emitted `ON (dst.id = src.id)` on MSSQL/Oracle where `src.id` is absent; CR-03: MSSQL `insert(replace=True)` returned another row's stale `last_id()`, a regression introduced by round 2) and two WARNING (WR-01: the deferral log falsely claimed no Phase-2 item remained unowned while ORA-38104 was PENDIENTE and CR-02 was unlogged; WR-02: the 02-07 `Query` cardinality change was absent from `CHANGELOG.md`). `02-10` and `02-11` run in parallel (wave 1, disjoint files: `query_builder.py`/`test_query_builder.py` vs `dialects/builders.py`/`model/model.py`/the MSSQL+Oracle tests) and `02-12` closes the documentation and ownership in wave 2 (CHANGELOG, `deferred-items.md`, this roadmap, REQUIREMENTS). GAP F (per-adapter coverage floors) stays deferred pending a green `engine-heavy` run and is NOT planned here.

### Phase 3: Data Correctness

**Goal**: Migrations and the read cache stop lying. A rolled-back migration can be re-applied, a failed
`migrate()` leaves a reconcilable state, and cached rows are never stale after a write.
**Mode:** standard
**Depends on**: Phase 1 (parallel to Phase 2 — disjoint modules, no file overlap)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04
**Success Criteria** (what must be TRUE):

  1. After `rollback_migration`, re-applying the same migration succeeds — with a regression test that fails before the fix and passes after
  2. `migrate()` either completes atomically, or on a dialect without transactional DDL records intent first and reconciles on next startup
  3. `CachedModel.update()` and `CachedModel.delete()` never leave a stale cached row readable (store-then-invalidate)
  4. `MemoryCacheBackend` is bounded, or explicitly documented as dev/test-only

**Plans**: 13 plans (5 originales + 2 de cierre ronda 2: `03-06`, `03-07` + 3 de cierre ronda 3: `03-08`, `03-09`, `03-10` + 3 de cierre ronda 4: `03-11`, `03-12`, `03-13`)
**Research**: not needed — `transactional_ddl` branching and cache-aside invalidation follow Alembic and Microsoft's documented patterns

Plans:

**Wave 1**

- [x] 03-01-PLAN.md — Ledger con columna `status` en los seis motores (+ `ALTER` idempotente para instalaciones legacy) y `rollback_migration` corregido: marca `rolling_back`, ejecuta el `down` y **borra** `{name}` (nunca inserta `{name}:down`), con `MIGRATIONS_TABLE` como fuente única — DATA-01, DATA-02
- [x] 03-03-PLAN.md — `CachedModel` invalida la clave afectada tras `update`/`delete`/`upsert` (overrides post-commit, fail-open) y `insert_many(cache=...)` invalida opcionalmente — DATA-03
- [x] 03-05-PLAN.md — `MemoryCacheBackend` acotado con LRU (`max_size=1024`) y contrato dev/test-only en el docstring, con tests DB-free — DATA-04

**Wave 2** *(blocked on `03-01`: mismos ficheros `migration.py` y los seis adaptadores)*

- [x] 03-02-PLAN.md — `TRANSACTIONAL_DDL` por dialecto + `Db`/`PoolDb.transactional_ddl`, `migrate()` de dos fases (`pending` → DDL → `applied`) con `reconcile_migrations()` y `resolve_migration()` (D-08/D-17), y los seis `migrate()` rewired — DATA-02

**Wave 3** *(blocked on `03-01`, `03-02`, `03-03` y `03-05`: el CHANGELOG y la guía documentan sus cambios)*

- [x] 03-04-PLAN.md — Documenta en `docs/guide.md` §10 el contrato dev/test-only y la limitación multi-proceso, y registra en `CHANGELOG.md` los cambios incompatibles de la fase — DATA-04

**Wave 1 (gap-closure ronda 2)** *(ficheros disjuntos: caché vs runner de migraciones)*

- [x] 03-06-PLAN.md — Dominio de caché canónico por PK en `CachedModel` + resolución de la PK real de la fila antes de invalidar (cierra CR-01/GAP A): una escritura sin la PK en la instancia (`id=None`) invalida la entrada de la PK; el residual inverso desaparece por construcción — DATA-03
- [x] 03-07-PLAN.md — `_apply` solo borra la fila del ledger si esta llamada la insertó y sigue `pending` (cierra WR-01/GAP B) y documenta la re-emisión de `rollback_migration` en el docstring + el error de reconciliación (cierra IN-01/GAP C) — DATA-02

**Waves:** 1 → `03-01`, `03-03`, `03-05` (disjuntos: migraciones, invalidación de caché y backend LRU); 2 → `03-02` (comparte `migration.py` y los seis adaptadores con `03-01`); 3 → `03-04` (docs-only: la guía y el CHANGELOG describen los cambios de los otros cuatro). Los cinco planes son autónomos.

**Gap-closure ronda 2 (03-06, 03-07).** La re-verificación (`03-VERIFICATION-FINAL.md`) devolvió `gaps_found` con un BLOCKER y dos residuales. **GAP A / CR-01 (BLOCKER, DATA-03):** el fix de `03-03` deriva la clave de la PK de los valores de la PROPIA instancia de escritura, así que el caso canónico `upsert(conflict=['rfc'])` / `update(keys=['rfc'])` desde una instancia con el auto-`id` en `None` deja viva la entrada `[id=1]` cacheada por `load()` (reproducido A2/B2/C2). La premisa de D-11 es falsa; `03-06` la supersede convirtiendo el dominio de caché en canónico (SOLO la PK de la fila) y resolviendo la PK real de la fila afectada antes de invalidar — el residual inverso desaparece por construcción. **GAP B / WR-01 (DATA-02):** la compensación pre-DDL de `_apply` borra `WHERE name={name}` sin probar propiedad, así que un `migrate()` concurrente en MySQL/MariaDB/Oracle puede eliminar la fila que otro proceso acaba de publicar; `03-07` condiciona el borrado a que ESTA llamada haya insertado la fila y a `status='pending'`. **GAP C / IN-01 (DATA-02):** falta la mitad "reintentar el rollback" de la fila 4 de D-08; `03-07` documenta la re-emisión de `rollback_migration` en el docstring y en el texto del error de reconciliación (el helper no recibe el SQL del `down`, así que automatizarlo cambiaría la firma de D-05/D-17). **Waves (ronda 2):** 1 → `03-06`, `03-07` (ficheros disjuntos: caché vs runner de migraciones); ambos autónomos. DATA-01, DATA-02 (salvo WR-01) y DATA-04 no se reabren.

**Gap-closure ronda 3 (`03-08`, `03-09`, `03-10`).** La revisión de código de la ronda 2 (`03-REVIEW-GAPS.md`) devolvió 2 Critical y 3 Warning. **CR-01 multi-fila (Critical, DATA-03):** `_resolve_pk_values` resuelve UNA fila (`super().load` → `fetch_one`) mientras `Model.update`/`delete` afectan a TODAS las filas que casan las claves de escritura; una escritura por una clave no-única deja entradas de PK obsoletas. **CR-02 (Critical, seguridad):** la clave de caché `sha1(tabla:[pk=...])` ignora el `scope()` activo, así que un hit sirve datos de otro tenant y habilita una escritura cruzada; la ronda 2 amplió la superficie (toda lectura no-PK puebla la entrada compartida por PK) y la documentación afirmaba un aislamiento inexistente. **WR-01 residual:** la compensación compara `{name, status}` (no prueba propiedad) y puede borrar la fila `pending` re-publicada por otro runner tras un rollback. **WR-02:** TOCTOU entre la sonda de PK y la escritura. **WR-03:** docs/CHANGELOG sobreafirman "esa única entrada" y el scope. Decision: `03-08` (caché: invalidación de TODAS las PKs afectadas, clave namespaced por `scope()`, re-sonda post-escritura que acota WR-02), `03-09` (migraciones: compensación por identidad `id` con fallback documentado para Oracle, y compensación que no enmascara el error raíz), `03-10` (docs/CHANGELOG alineados). **Waves (ronda 3):** 1 → `03-08`, `03-09` (ficheros disjuntos: caché vs runner); 2 → `03-10` (docs-only, describe lo entregado por ambos).

**Wave 1 (gap-closure ronda 3)** *(ficheros disjuntos: caché vs runner de migraciones)*

- [x] 03-08-PLAN.md — `CachedModel` invalida las entradas de TODAS las filas que casa una escritura (`_resolve_pk_values` multi-fila vía `search` ligado, scope-aware) y namespaces la clave con `current_scope().digest()`; re-sonda post-escritura que acota el TOCTOU — DATA-03
- [x] 03-09-PLAN.md — La compensación del runner borra por identidad de fila (`{id: ledger_id}`) cuando el motor expone `last_id()` (fallback documentado para Oracle) y no enmascara el error raíz — DATA-02

**Wave 2 (gap-closure ronda 3)** *(docs-only: describen lo entregado por 03-08 y 03-09)*

- [x] 03-10-PLAN.md — Alinea `docs/guide.md`, `docs/design/5-security.md` y `CHANGELOG.md` con la invalidación multi-fila, el namespace de scope y el residual TOCTOU (cierra WR-03) — DATA-03, DATA-02

**Gap-closure ronda 4 (`03-11`, `03-12`, `03-13`).** La revisión de la ronda 3 (`03-REVIEW-GAPS-R3.md`) devolvió 1 Critical y 4 Warning. **CR-R3-01 (Critical, seguridad/SEC-01):** `Model.update`/`delete` solo PRE-comprueban el `scope()` con `load()`; el DML emitido no lleva predicado de alcance, así que una clave de escritura no-PK y no única modifica/borra filas de otro tenant (reproducido sobre SQLite). Es el residual raíz de CR-02 que la ronda 3 no cerró y su documentación sobreafirmó. **WR-R3-01:** la invalidación multi-fila de la ronda 3 sub-cubre bajo scope (dependiente de CR-R3-01; se resuelve por construcción al acotar el DML). **WR-R3-02:** `_union` no es fail-open con valores de PK no hashables (TypeError tras el commit). **WR-R3-03/WR-R3-04:** overclaim "escritura cruzada cerrada" + bullet contradictorio "única entrada" + falta documentar que las escrituras deben correr bajo el mismo scope que las lecturas. **IN-R3-01/03:** afirmación incorrecta sobre `last_id()` de Oracle; promesa de huella estable de scope demasiado fuerte. Decision: `03-11` (DML acotado por scope en la capa `Model`, sin tocar builders ni adaptadores — cierra CR-R3-01/WR-R3-01), `03-12` (`_union` hashable + invalidación post-escritura fail-open — cierra WR-R3-02), `03-13` (docs/CHANGELOG veraces — cierra WR-R3-03/04 e IN-R3-01/03). **Waves (ronda 4):** 1 → `03-11`, `03-12` (ficheros disjuntos: `model.py` vs `cached.py`); 2 → `03-13` (docs-only).

**Wave 1 (gap-closure ronda 4)** *(ficheros disjuntos: DML del modelo vs invalidación de caché)*

- [x] 03-11-PLAN.md — `Model.update`/`delete` aplican el `scope()` activo al WHERE del DML (helper `_scoped_dml` sobre el `Query` del builder, params ligados); sin scope el DML es idéntico — SEC-01
- [x] 03-12-PLAN.md — `_union` deduplica por huella hashable y la invalidación post-escritura es fail-open incluso con PKs no hashables — DATA-03

**Wave 2 (gap-closure ronda 4)** *(docs-only: describen lo entregado por 03-11 y 03-12)*

- [x] 03-13-PLAN.md — CHANGELOG/guía/diseño de seguridad veraces: SEC-01, escrituras bajo el mismo scope, residuales de `upsert` y de huella determinista — SEC-01, DATA-03, DATA-02

### Phase 4: Pool Correctness & Concurrency

**Goal**: `PoolDb` is correct under concurrency. Per-connection state lives on a per-connection handle,
admission never exceeds `max_size`, `last_id` belongs to the insert that produced it, and release
semantics are explicit instead of accidental.
**Mode:** standard
**Depends on**: Phase 1 (CI-09 characterization tests) and Phase 2 (dialect constants used by reset paths)
**Requirements**: POOL-01, POOL-02, POOL-03, POOL-04, POOL-05, POOL-06, POOL-07
**Success Criteria** (what must be TRUE):

  1. Under N concurrent tasks on a pool of size M, live connections never exceed M and no `acquire()` raises spuriously
  2. Concurrent inserts on pooled connections each return their own id (no cross-talk), and post-hoc `last_id()` emits a `DeprecationWarning`
  3. Releasing a connection with an open transaction rolls it back by default; `reset_on_release="commit"` restores the old behavior, and standalone `pool.execute(INSERT)` still commits
  4. `close()` is idempotent and never closes a connection currently held by a caller
  5. Idle connections above `min_size` are closed by the lazy reaper, and deterministic Python-3.10-compatible concurrency/stress tests pass under `pytest-timeout`

**Plans**: 6 plans
**Research**: needed — the `PooledConnection` refactor shape and the `last_id` API-contract change are breaking-change design decisions

Plans:

- [x] 04-01: `PooledConnection` handle consolidating per-connection state (driver, `last_id`, timestamps, generation, in-use) and reserve-before-await `acquire()` that never locks across the await; task-ownership binding on the `_current_connection` contextvar; `PoolDb._last_id` removed — POOL-01, POOL-02
- [x] 04-02: Capture `last_id` **inside** the insert (`RETURNING` / `OUTPUT INSERTED` / immediate `lastrowid`) per connection/task via opt-in `returning=<col>` + `Db.execute_insert`; deprecate post-hoc `last_id()` with a centralized warning; migrate the 29 test call sites + 2 internal callers — POOL-03. Owns too the Oracle `MERGE` `SET` fix (**ORA-38104**): exclude `conflict_cols` from `WHEN MATCHED THEN UPDATE SET` (as `build_upsert` already does with `update_cols`) so `Model.insert(replace=True)` is executable on Oracle — registered by plan `02-12` (see `.planning/phases/02-dialect-seam-engine-parity/deferred-items.md`).
- [x] 04-03: `reset_on_release` policy (rollback by default, configurable commit), with explicit commit-or-rollback in `execute`/`_run` first so standalone writes are not silently dropped; `DeprecationWarning` + CHANGELOG entry — POOL-04
- [x] 04-04: Generation counter + lazy idle reaper closing connections above `min_size` (no background daemon), and an idempotent `close()` that never closes an in-use connection; retire the `encino_orm.pool` mypy-ratchet entry — POOL-05, POOL-06
- [x] 04-05: Test infrastructure only (dev deps `pytest-timeout`/`pytest-repeat` + `uv lock`, `stress` marker, CI `--timeout-method=signal`, shared `EventBarrier` helper); no behavior assertions — POOL-07 *(logical `04-05a`; split from the original `04-05` to isolate the blocking-human package-legitimacy checkpoint)*
- [x] 04-06: Deterministic concurrency/stress tests using a hand-rolled `asyncio.Event` barrier (never `asyncio.Barrier`/`TaskGroup` on 3.10) asserting the final pool behavior, with `pytest-timeout` per marker and a `pytest-repeat` stress variant behind the `stress` marker — POOL-07 *(logical `04-05b`)*

### Phase 5: Resilience

**Goal**: Connection loss is classified, handled once, and never silently duplicates a write. Direct
(non-pooled) connections survive idle periods, and driver failures surface as library exceptions.
**Mode:** standard
**Depends on**: Phase 4 (needs `PooledConnection` + generation counter)
**Requirements**: RESL-01, RESL-02, RESL-03, RESL-04
**Success Criteria** (what must be TRUE):

  1. Each of the six adapters classifies a simulated disconnect as a disconnect error, and does not misclassify a lock/deadlock error
  2. A disconnect **outside** a transaction reconnects once and the operation succeeds; the same disconnect **inside** a transaction raises instead of retrying
  3. Direct (non-pooled) connections survive an idle period via `pre_ping` and `max_connection_lifetime`
  4. Driver exceptions are translated into a documented public library error taxonomy

**Plans**: 4 plans
**Research**: needed — the error-taxonomy boundary and per-driver disconnect classification require adapter-level API research

Plans:

- [x] 05-01: `is_disconnect_error` per adapter across all six engines — RESL-01
- [x] 05-02: `Db._with_reconnect` template method that reconnects exactly once and only when `in_transaction()` is false, kept strictly separate from the lock/deadlock retry path — RESL-02
- [x] 05-03: `pre_ping` + `max_connection_lifetime` policy for direct (non-pooled) connections — RESL-03
- [x] 05-04: Public error taxonomy translating driver exceptions into library exceptions — RESL-04

### Phase 6: Config & Optional-Layer Hygiene

**Goal**: No mutable module-level global decides which database or which secret is in play, and
generated handlers stop being built with `exec()` — without changing the HTTP or GraphQL contract.
**Mode:** standard
**Depends on**: Phase 1 (independent of Phases 4/5; may run in parallel). Level 4 (config) must precede Level 5 (codegen) so public signatures change once.
**Requirements**: CFG-01, CFG-02, CFG-03, CFG-04, CFG-05
**Success Criteria** (what must be TRUE):

  1. Two `ConnectionRegistry` instances in the same process resolve to their own databases, and the deprecated global shim still works with a `DeprecationWarning`
  2. `SecurityConfig` is frozen and guards are built from injected config; mutating `SECRET`/`GET_DB` no longer changes behavior
  3. The generated OpenAPI schema is identical before and after the `exec()` → closure rewrite, and path parameters still validate
  4. Two successive `build_schema` calls do not mutate module-level GraphQL namespace state
  5. `Filter.raw`, `Query` and `db.fn.*` trust boundaries are documented with safe/unsafe examples

**Plans**: 5 plans
**Research**: needed — `__signature__` for FastAPI path params is a community pattern (MEDIUM confidence) and GraphQL namespace isolation is explicitly untested

Plans:

**Wave 1** *(parallel, disjoint: `context.py` vs `security/*`)*

- [x] 06-01-PLAN.md — `ConnectionRegistry` replacing the `_default_db` global, with deprecated backward-compatible shims; migrates `tests/test_singleton.py` to the undeprecated path under `filterwarnings=["error"]` — CFG-01
- [x] 06-02-PLAN.md — Immutable `SecurityConfig` + `security_dependencies(config)` guard factories replacing mutable `SECRET`/`GET_DB`, with deprecated globals; migrates `B008` to `Annotated` — CFG-02

**Wave 2** *(parallel, disjoint: `http/routes.py` vs `graphql/schema.py`; blocked on Wave 1 so public signatures change once)*

- [x] 06-03-PLAN.md — Replace `exec()`-generated REST handlers with closures/`__signature__` as a behavior-preserving refactor, guarded by an OpenAPI snapshot taken **before** the rewrite — CFG-03 (HTTP)
- [x] 06-04-PLAN.md — Replace the GraphQL `_pk_resolver` `exec()` with closures/`__signature__` (guarded by an SDL snapshot taken before the rewrite) **and** make `build_schema` use a per-build namespace — CFG-03 (GraphQL) + CFG-04

**Wave 3** *(blocked on Waves 1–2; single owner of the shared files)*

- [x] 06-05-PLAN.md — Explicit trust-boundary documentation for `Filter.raw`, `Query` and `db.fn.*` (`docs/trust-boundaries.md` + regression test), deprecation banners for `set_default_db` in `README.md`/`docs/getting-started.md`, `CHANGELOG.md` entries for CFG-01…05, retirement of the `S102`/`B008`/mypy-ratchet suppressions naming Phase 6 (incl. `encino_orm.http.parsing`), and the isolated `PyJWT>=2.8,<2.15` cap bump with `uv lock` + `uv audit`/`pip-audit` and the 5 GHSA ignores removed — CFG-05

**Waves:** 1 → `06-01`, `06-02`; 2 → `06-03`, `06-04`; 3 → `06-05`. The Wave 1 pair is disjoint (`context.py`+`__init__.py` vs `security/*`). The Wave 2 pair is disjoint (`http/routes.py` vs `graphql/schema.py`) and waits for Wave 1 so the public config signatures are frozen before the OpenAPI/SDL snapshots are captured. `06-05` runs last because it is the single owner of `pyproject.toml`, `CHANGELOG.md`, `mkdocs.yml` and `ci.yml` (Pitfall 8: three parallel plans editing the same gate block would conflict). All five plans are autonomous (no checkpoints; no new packages).

**Deviation documented (Open Question 3).** The ROADMAP text attributes CFG-03 to "handlers" and CFG-04 to the GraphQL namespace, but the second `exec()` site is `graphql/schema.py:103`. To keep `06-03` and `06-04` disjoint in files, **`06-04` owns all of `graphql/schema.py`** (exec → closures + per-build namespace) with **two** guardians (SDL snapshot + namespace non-mutation), and `06-03` owns HTTP + OpenAPI only.

### Phase 7: Performance & Benchmarks

**Goal**: Every performance claim is measured before it is made. Profiler output is committed first,
batched inserts remove real round-trips, and a benchmark gate fails on a deliberate regression.
**Mode:** standard
**Depends on**: Phase 2 (per-dialect `MAX_PARAMS`/`MAX_ROWS`) and Phase 4 (pool handle for reaper work)
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-04
**Success Criteria** (what must be TRUE):

  1. Profiler output (`py-spy`/`cProfile`) is committed to the repo **before** any optimization commit lands
  2. A benchmark suite with numeric targets runs in CI, and a deliberate 2× regression fails the gate
  3. `copy_table` inserts in batches sized per dialect (`min(MAX_PARAMS // n_columns, MAX_ROWS)`) and produces exactly the same rows as the row-by-row path
  4. `QueryTracer._latencies` is bounded and `_FIELD_ADAPTERS` no longer retains model classes indefinitely

**Plans**: 4 plans
**Research**: needed — per-dialect parameter ceilings (MSSQL 2100, Oracle 1000-element `IN`, asyncpg ~32767) are documented but not empirically verified; measure before sizing batches

Plans:

- [x] 07-01: Run and commit profiler output (`py-spy`/`cProfile`) on a representative workload, before any optimization — PERF-03
- [x] 07-02: Benchmark harness (warmup, ≥5 reps, median + p95 + σ, logging disabled) benchmarking **sync units directly** — SQL build, placeholder translation, batch sizing — with numeric targets and a 2× regression gate — PERF-02
- [x] 07-03: Batched `copy_table` with per-dialect batch sizing (`min(MAX_PARAMS // n_columns, MAX_ROWS)`), preferring array binding/`executemany` for Oracle/PostgreSQL, with row-equivalence tests — PERF-01
- [x] 07-04: Bound `QueryTracer._latencies` with `deque(maxlen=N)` and switch `_FIELD_ADAPTERS` to `WeakKeyDictionary` — PERF-04

**Fase 7 COMPLETA** (2026-09-19). Verificación: `07-VERIFICATION.md` PASS 4/4
(la verdad 4 se confirmó en fuente: `observability.py:85` deque acotado +
`model.py:30` WeakKeyDictionary; el cambio `observability.py` quedó en `6cf670e`,
ancestro del rango de revisión). Code review `07-REVIEW.md` con
`issue_founds` → 1 High / 2 Medium / 3 Low / 3 Info, **resuelto** en dos commits
atómicos (`edf8318` HR-01+MR-02, `8228dc5` MR-01+LR-01+LR-02+IN-01/IN-03); LR-03
aceptado como riesgo documentado (3 corridas CI verdes consecutivas, σ ~1,3%). CI
10/10 jobs verde y docs desplegadas tras el push de cierre. Sin cambios de API;
requisitos PERF-01..04 `[x]` en REQUIREMENTS.md.

### Phase 8: Release 0.3.0

**Goal**: The deprecation path is shipped, not planned. Users on `>=0.2.6` get warned by 0.2.7, then
get a release candidate, then a documented 0.3.0 — with no way to publish past a red CI gate.
**Mode:** standard
**Depends on**: Phases 2–7 (all breaking-change semantics must be settled). Phase 6 may run in parallel but its API changes must be frozen before 0.3.0rc1.
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05
**Success Criteria** (what must be TRUE):

  1. 0.2.7 is published to PyPI with runtime `DeprecationWarning`s for every 0.3.0 breaking change, **before** any 0.3.0 artifact is published
  2. 0.3.0rc1 is published before 0.3.0, using OIDC trusted publishing with no `PYPI_API_TOKEN` and a protected `pypi` environment
  3. `CHANGELOG.md` enumerates every breaking change with old and new behavior, and `MIGRATION-0.3.md` shows before/after examples
  4. The README documents `~=0.2.6` pinning, warns that dev credentials are dev-only, and the `prompts/` link no longer 404s

**Plans**: 8 plans
**Research**: not needed — SemVer deprecation guidance and PyPI trusted publishing are official, stable and fully sourced

Plans:

**Wave 1**

- [x] 08-01-PLAN.md — 0.2.7 `DeprecationWarning`s para cada ruptura 0.3.0 que puede avisar (implicit commit on release, mutable `SECRET`/`GET_DB`, post-hoc `last_id()`), justificación escrita de la ruptura fail-closed (identificadores) y guard de la allowlist tolerante a puntos, versión + CHANGELOG `[0.2.7]` (debajo de `[Unreleased]`) + dry-run de build, y checkpoint de publicación del tag `v0.2.7` — REL-01

**Wave 2** *(independientes entre sí; 08-04 comparte `CHANGELOG.md` con 08-01, ya en wave 1)*

- [x] 08-02-PLAN.md — OIDC trusted publishing (`id-token: write`, `uv publish --trusted-publishing always`) en ambos workflows, entorno `pypi` protegido, eliminación de `PYPI_API_TOKEN` y validación en TestPyPI — REL-03
- [x] 08-04-PLAN.md — `CHANGELOG.md` con cada ruptura en viejo/nuevo y `docs/MIGRATION-0.3.md` con pares Antes/Después, registrada en la nav de MkDocs, con guard de fuente — REL-04

**Wave 3** *(08-05, 08-06 y 08-07 son docs/código con ficheros disjuntos; 08-06 documenta todas las retiradas)*

- [x] 08-05-PLAN.md — README con pinning `~=0.2.6` (no `>=`), aviso de credenciales solo-desarrollo y `.env.example` rastreado, con guard de higiene del README — REL-05
- [x] 08-06-PLAN.md — Retirada de APIs deprecadas: `set_default_db`/`get_default_db`, globales mutables `SECRET`/`GET_DB` y fallback legacy; documentación de todas las retiradas (`### Eliminado`) en CHANGELOG + MIGRATION-0.3 y resolución de la nota de ownership — REL-01, REL-04
- [x] 08-07-PLAN.md — Limpieza de enlaces muertos a `prompts/` en `docs/**` y guard parametrizado de enlaces — REL-05

**Wave 4** *(08-08 retira `last_id()`; depende de 08-06 para no dejar pines de warning obsoletos)*

- [ ] 08-08-PLAN.md — Retirada de la API post-hoc `Db.last_id()`/`PoolDb.last_id()` y del helper de warning, con actualización de los tests de pool y motores — REL-01

**Wave 5** *(publicación final; depende de todas las retiradas)*

- [ ] 08-03-PLAN.md — Verificación del gate CI + entorno `pypi`, corte y publicación de 0.3.0rc1, y promoción a 0.3.0 — REL-02

**Waves:** 1 → `08-01`; 2 → `08-02`, `08-04`; 3 → `08-05`, `08-06`, `08-07`; 4 → `08-08`; 5 → `08-03`. La cadena de publicación es estricta (0.2.7 → retiradas → 0.3.0rc1 → 0.3.0) y `CHANGELOG.md`/`docs/MIGRATION-0.3.md` son ficheros compartidos, de modo que las olas quedan determinadas por esos dos hechos. `08-01`, `08-02` y `08-03` son no autónomos: D-04 exige un checkpoint humano por publicación real. `08-03` lleva 4 tareas (dos checkpoints de publicación) por la misma razón.

## Research Corrections Carried Into This Roadmap

These corrections override statements elsewhere in the repo. Do not build on the old premises.

1. **PostgreSQL `lastval()` is session-scoped, not transaction-scoped.** `ARCHITECTURE.md` describes
   it as transaction-scoped and is wrong. Consequences: outside a transaction, a shared pooled
   connection can return another task's id with no error; inside a transaction it is still wrong if
   any trigger inserts into another table with its own sequence; if the INSERT touched no sequence it
   returns stale data or raises `ObjectNotInPrerequisiteState`. **The only correct answer on
   PostgreSQL is `INSERT ... RETURNING <pk>`**, which changes `Db.insert`'s return contract. POOL-03
   must capture the id inside the insert (`RETURNING` / `SCOPE_IDENTITY` / immediate `lastrowid`).
   **Corregido 2026-09-18** en `.planning/research/ARCHITECTURE.md` (session-scoped, no
   transaction-scoped).

2. **Neither `pytest-benchmark` nor `pytest-codspeed` measures coroutines.** Verified by reading
   plugin source: pytest-codspeed's `BenchmarkFixture.__call__` is literally
   `return target(*args, **kwargs)`, so an async target only "benchmarks" coroutine-object creation.
   The stated goals are CPU/sync-bound, so **benchmark the sync units directly** (SQL build,
   placeholder translation, batch sizing). For end-to-end async latency use a hand-rolled
   `time.perf_counter` harness inside an async test with a loose budget. Do not gate on
   `@pytest.mark.benchmark` over an async test until empirically validated.

3. **TS-37 (placeholder caching) is deferred, not in scope.** A `re.sub` over a ~200-byte SQL string
   costs ~1 µs against a ~1 ms round-trip — under 1% by Amdahl's law. It is tracked as v2 `DATA-07`
   and may be re-opened only if placeholder translation appears in the profiler's top 5 hot paths in
   Phase 7. The `Query` correctness bugs (DIAL-05) are independent and still land in Phase 2.

4. **Python 3.10 floor rules out `asyncio.Barrier`, `asyncio.timeout`, `TaskGroup` and `except*`** in
   library code *and tests*. POOL-07 must use a hand-rolled `asyncio.Event` barrier. `hypothesis`'s
   `RuleBasedStateMachine` is the fallback if the hand-rolled barrier proves awkward.

5. **POOL-04 ordering is safety-critical.** Flipping release-from-commit to release-from-rollback
   naively turns every standalone `pool.execute(INSERT)` into a silent data-loss bug. Sequence:
   (i) make `execute`/`_run` commit-or-rollback explicitly, (ii) then roll back leftovers with a
   `DeprecationWarning`, (iii) keep `TestPoolAutocommit` passing.

6. **Phase 2 corrections discovered during its research (they override the Phase 2 text above).**
   - **The `COUNT(*)` result-key bug is SEVEN sites, not three.** `Model.count` (`model/model.py:795`),
     `Db.list_tables` (`base.py:158`) and `QueryBuilder.count/sum/avg/min/max`
     (`model/query_builder.py:246,254,263,271,279`) all index the result row by the expression text.
     The correct pattern already exists at `base.py:174-177` (`AS n` → `row["n"]`). Leaving
     `sum/avg/min/max` unfixed falsifies the phase goal. DIAL-03 is satisfied only when all seven
     are aliased.

   - **`rebind` is DELETED, not fixed** (CONTEXT D-01/D-06). Success Criterion 4 and the original
     02-03 bullet said "fix `rebind`"; both are stale and have been rewritten to `with_params()`.

   - **`Query` is mutated post-construction** by `mssql.py:223` and `oracle.py:225`
     (`q.ignore_duplicated = True`), and two existing tests assert that attribute. The immutability
     refactor must promote it to a constructor field, not delete it.

   - **The `Query` typed accessors must exist before the builder seam** (`02-02`) can pass
     `ignore_duplicated` at construction and read `.sql`/`.params`. Hence `02-02` adds the
     accessors additively and `02-03` delivers the breaking change (immutability, cardinality,
     `with_params()`), so DIAL-05 never touches the six adapters (CONTEXT D-02).

   - **`PoolDb.insert` silently drops `conflict`** (`pool.py:180`); through a pool, PostgreSQL's
     `replace` always falls back to `columns[0]`.

   - **CI blockers for the MSSQL/Oracle job:** `ubuntu-latest` (24.04) ships no ODBC driver, so an
     explicit `msodbcsql18` + `unixodbc` install step is mandatory; and the lighter `oracle-free`
     image uses `FREEPDB1` while `docker-compose.yml` uses `XE`/`XEPDB1`, so the job must override
     `ENCINO_ORM_ORACLE_SERVICE`. The `engine-heavy` job must select tests by FILE, not by marker,
     or the `optional_engine` markers would deselect every MSSQL/Oracle test and the job would run
     zero tests.

   - **`syrupy` install is gated behind a blocking `checkpoint:human-verify`** (slopcheck `[SUS]`,
     a name-similarity false positive vs `scrapy`).

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
Phases 2 and 3 may execute in parallel (disjoint modules). Phase 6 may run parallel to 4/5.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Safety Net — CI Gates & Test Infrastructure | 5/5 | Complete   | 2026-09-17 |
| 2. Dialect Seam & Engine Parity | 12/12 | Complete   | 2026-09-18 |
| 3. Data Correctness | 13/13 | Complete    | 2026-09-18 |
| 4. Pool Correctness & Concurrency | 6/6 | Complete    | 2026-09-19 |
| 5. Resilience | 4/4 | Complete    | 2026-09-19 |
| 6. Config & Optional-Layer Hygiene | 5/5 | Complete    | 2026-09-19 |
| 7. Performance & Benchmarks | 0/4 | Not started | - |
| 8. Release 0.3.0 | 6/8 | In Progress|  |

**Coverage:** 47/47 v1 requirements mapped ✓ (no orphans, no duplicates)

---
*Roadmap created: 2026-09-17*
*Milestone: encino_orm 0.2.6 → 0.3.0 (production hardening)*