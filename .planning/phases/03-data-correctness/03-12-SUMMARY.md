---
phase: 03-data-correctness
plan: 12
status: complete
gap_closure: true
subsystem: database
tags: [cache, invalidation, fail-open, d-12, wr-r3-02, unhashable, pk, sqlite]

# Dependency graph
requires:
  - phase: 03-data-correctness
    provides: "03-08: invalidación multi-fila por PK real (_resolve_pk_values) y unión de sondas before/after (WR-02)"
provides:
  - "_union deduplica por huella hashable (`repr` del valor): no lanza TypeError con PKs list/dict"
  - "helper _invalidate_after_write en encino_orm/model/cached.py: envuelve la unión en try/except y degrada a concatenación de sondas (fail-open D-12)"
  - "update/delete/upsert de CachedModel usan _invalidate_after_write en lugar de llamar a _union fuera de try"
  - "regresión tests/test_cached_model.py::TestCachedModel::test_wr_r3_02_union_no_rompe_fail_open con PK list"
affects: [03-13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "huella hashable de un dict de PK: tuple(sorted((k, repr(v)) for k, v in item.items())) — el repr evita el TypeError sin cambiar el dedupe de PKs escalares"
    - "fail-open en el borde de invalidación post-escritura: try/except + logger.warning + degradación a lista sin deduplicar"

key-files:
  created: []
  modified:
    - encino_orm/model/cached.py
    - tests/test_cached_model.py

key-decisions:
  - "La huella usa `repr(v)` (no serialización JSON ni `str`) porque es estable y no puede lanzar para tipos no hashables; cada valor escalar conserva un repr distinto, así que el dedupe int/str no cambia."
  - "El helper `_invalidate_after_write` no re-lanza nunca: si `_union` falla, concatena las sondas (peor dedupe) y sigue; la escritura ya está commiteada (D-12)."
  - "El test usa `update(keys=[\"grupo\"], data=[\"nombre\"])` (no el `data` por defecto) para no clobbear la PK `k` con `None` y poder verificar que la fila conserva su PK."

patterns-established:
  - "Borde de invalidación fail-open: cualquier paso nuevo del camino post-commit (`_union`, `_invalidate_pks`, `_resolve_pk_values`) debe quedar dentro de un try/except que degrade, no de uno que propague."

requirements-completed: [DATA-03]

# Metrics
duration: 4min
completed: 2026-09-18
---

# Phase 3 Plan 12: `_union` hashable e invalidación post-escritura fail-open Summary

**`CachedModel._union` deduplica por huella `repr` hashable y `update`/`delete`/`upsert` invalidan a través de `_invalidate_after_write` (try/except + degradación), de modo que una PK no hashable (`list`/`dict`) ya no propaga un `TypeError` después del commit (WR-R3-02, D-12).**

## Performance

- **Duration:** 4 min
- **Started:** 2026-09-18T21:14:50Z
- **Completed:** 2026-09-18T21:18:40Z
- **Tasks:** 2 (TDD: RED → GREEN)
- **Files modified:** 2

## Accomplishments

- **WR-R3-02 cerrado:** `_union` usaba `seen.add(tuple(sorted(item.items())))`; con una PK de tipo `list`/`dict` (admitida por pydantic y por `_from_db`, que JSON-decodifica) el `seen.add` lanzaba `TypeError` **después** del commit, violando la garantía fail-open D-12. Ahora la huella es `tuple(sorted((k, repr(v)) for k, v in item.items()))`, siempre hashable.
- **Guardia fail-open añadida:** nuevo helper `_invalidate_after_write(self, *probe_lists)` que ejecuta `_union` dentro de `try/except Exception`; ante cualquier fallo registra un `logger.warning` y degrada a la concatenación de las sondas, luego llama a `_invalidate_pks`. El único eslabón sin guarda del camino post-commit queda cubierto.
- **Los tres overrides usan el helper:** `update`, `delete` y `upsert` sustituyen `await self._invalidate_pks(self._union(pks, pks_after))` por `await self._invalidate_after_write(pks, pks_after)`.
- **Sin cambio para PKs escalares:** `repr` de `int`/`str` es estable y distinto por valor, así que el dedupe de la unión (y por tanto la semántica WR-02) no cambia; las suites existentes (`test_cached_model.py`, `test_cache_backend.py`) siguen verdes.
- **Regresión genuina:** el test reproduce el `TypeError: unhashable type: 'list'` en `cached.py:124` antes del fix y pasa después, con la fila ya actualizada.

## Task Commits

Each task was committed atomically:

1. **Task 1: Regresión RED de fail-open con PK no hashable** - `df8f3d4` (test)
2. **Task 2: `_union` hashable + invalidación post-escritura fail-open (GREEN)** - `83053c4` (fix)
3. **Formato ruff de la regresión** - `6ad2bba` (style)

**Plan metadata:** `docs(03-12): complete plan` (ver abajo)

_Note: TDD con dos commits funcionales: `test(...)` (RED) → `fix(...)` (GREEN). El tercer commit es solo formato; no hubo fase REFACTOR._

## Files Created/Modified

- `tests/test_cached_model.py` - nuevo modelo `ClientePkLista` (`_table="clientes_pk_lista"`, `_primary_key=("k",)`, `k: list | None`), `DDL_PK_LISTA`, fixture `db_pk_lista` y la regresión `test_wr_r3_02_union_no_rompe_fail_open`.
- `encino_orm/model/cached.py` - `_union` con huella `repr`; nuevo `_invalidate_after_write`; `update`/`delete`/`upsert` usan el helper.

## Decisions Made

- **`repr(v)` como huella:** es estable y total (nunca lanza) para cualquier valor; JSON no sirve porque `item` ya contiene valores Python heterogéneos y `repr` conserva distinción por valor en PKs escalares.
- **Degradación a concatenación de sondas:** si `_union` falla, se prefiere invalidar de más (duplicados) que propagar; `_invalidate_pks` ya deduplica de facto por clave de caché y es fail-open por clave.
- **`data=["nombre"]` en el test:** evita que el `data` por defecto escriba `k=None` (la instancia de escritura no lleva la PK) y permite verificar que la fila conserva la PK `list`; no debilita la ruta `_union` porque `_resolve_pk_values` sigue devolviendo la PK no hashable.

## Deviations from Plan

None - plan executed exactly as written.

_(Único ajuste de forma: el plan sugería `update(keys=["grupo"])`; el test usa `update(keys=["grupo"], data=["nombre"])` para no clobbear la PK con `None` y poder asertar la persistencia con la PK intacta. La ruta que ejercita `_union` con la PK `list` es idéntica.)_

## Issues Encountered

- `ruff format --check` marcó `tests/test_cached_model.py` (la llamada `update(...)` de la regresión). Resuelto con `uv run ruff format tests/test_cached_model.py` y commit `style(03-12)`; sin cambio de comportamiento.

## Authentication Gates

None.

## Known Stubs

None. No se introdujeron valores vacíos, placeholders ni componentes sin fuente de datos.

## Threat Flags

None. El cambio **reduce** superficie de amenaza (T-03-12-01 Denial of Service, mitigado): la huella `repr` elimina el `TypeError` y el helper garantiza que la invalidación nunca falla una escritura commiteada. No se añadieron endpoints, rutas de auth ni patrones de acceso a ficheros nuevos. No se instalaron paquetes (T-03-12-SC).

## TDD Gate Compliance

- RED: `df8f3d4` `test(03-12): añade regresión RED de fail-open de _union con PK no hashable` — `TypeError: unhashable type: 'list'` en `encino_orm/model/cached.py:124`, `1 failed, 20 deselected`, exit != 0.
- GREEN: `83053c4` `fix(03-12): _union hashable y invalidación post-escritura fail-open` — `27 passed` (`test_cached_model.py` + `test_cache_backend.py`).
- REFACTOR: no aplicó.

## Verification

- **RED (Task 1):** `uv run pytest tests/test_cached_model.py -k wr_r3_02 -q` → `1 failed, 20 deselected`, exit != 0. Falla en `await self._invalidate_pks(self._union(pks, pks_after))` con `lists = ([{'k': [1, 2]}], [{'k': [1, 2]}])` y `TypeError: unhashable type: 'list'`.
- **GREEN (Task 2):** `uv run pytest tests/test_cached_model.py -k wr_r3_02 -q` → `1 passed, 20 deselected`, exit 0.
- **GREEN suite:** `uv run pytest tests/test_cached_model.py tests/test_cache_backend.py -q` → `27 passed`, exit 0.
- **Acceptance:**
  - `grep -c "def test_wr_r3_02_" tests/test_cached_model.py` → 1.
  - `grep -c "_invalidate_after_write" encino_orm/model/cached.py` → 4 (definición + 3 overrides).
  - `grep -c "repr(v)" encino_orm/model/cached.py` → 1.
- **Gates de fin de plan:**
  - `uv run pytest -q` → `845 passed` (10 snapshots passed), exit 0 (baseline 03-11: 844 passed → +1 test).
  - `uv run ruff check encino_orm tests` → `All checks passed!`, exit 0.
  - `uv run ruff format --check encino_orm tests` → `115 files already formatted`, exit 0.
  - `uv run mypy encino_orm` → `Success: no issues found in 60 source files`, exit 0.
  - No se ejecutó `pytest -m integration`.

## Next Phase Readiness

- WR-R3-02 cerrado; el camino de invalidación post-commit de `CachedModel` es fail-open de extremo a extremo.
- `03-13` (docs/CHANGELOG) puede documentar la huella hashable y la guarda fail-open entregadas aquí.
- Sin solape de ficheros: este plan no tocó `encino_orm/model/model.py` (03-11) ni docs.

---

*Phase: 03-data-correctness*
*Completed: 2026-09-18*

## Self-Check: PASSED

- FOUND: `encino_orm/model/cached.py`
- FOUND: `tests/test_cached_model.py`
- FOUND: `.planning/phases/03-data-correctness/03-12-SUMMARY.md`
- FOUND commits: `df8f3d4`, `83053c4`, `6ad2bba`
