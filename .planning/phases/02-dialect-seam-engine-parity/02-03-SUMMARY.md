---
phase: 02-dialect-seam-engine-parity
plan: 03
subsystem: database
tags: [orm, query, immutability, hash, dialects, limits, docs, tdd]

# Dependency graph
requires:
  - phase: 02-dialect-seam-engine-parity
    provides: "Seam DML (`dialects/builders.py` + `strategies.py`) y accesores tipados `.sql`/`.params` de `Query` (02-02)"
provides:
  - "`Query` inmutable y hashable: slots privados + properties de solo lectura, `with_params()` y `rebind`/`format` eliminados"
  - "Compilación por regex de los `{n}` REALES con validación de cardinalidad `set(indices) == set(range(len(values)))`"
  - "`DialectLimits` + `LIMITS` con procedencia escrita; `MAX_PARAMS`/`MAX_ROWS` en los 6 adaptadores y en `PoolDb`"
  - "`insert_many` con `chunk` derivado de `min(MAX_PARAMS // n_columnas, MAX_ROWS)`"
  - "`docs/design/0-design.md` §2.1 a la API nueva + guard anti-rebind en tests"
affects: [02-04, 02-05, 04, 07]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Value object inmutable: `__slots__` PRIVADOS + properties sin setter + `object.__setattr__` (la mutabilidad real exige slots privados, no un slot plano)"
    - "Compilación de placeholders por regex de los `{n}` reales (no `enumerate`), aceptando índices dispersos y duplicados"
    - "Techos por dialecto como DATO con procedencia obligatoria: cada `provenance` dice si el número está verificado empíricamente"
    - "Guard de fuente por literal exacto (`def rebind(`) para no confundir `Filter._rebind_raw`"

key-files:
  created:
    - tests/test_query.py
  modified:
    - encino_orm/query.py
    - encino_orm/dialects/strategies.py
    - encino_orm/dialects/__init__.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/mariadb.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - encino_orm/pool.py
    - encino_orm/model/model.py
    - docs/design/0-design.md
    - tests/test_engine.py

key-decisions:
  - "D-03 se implementa al pie de la letra: `__eq__`/`__hash__` sobre (sql_template, fields) y `ignore_duplicated` EXCLUIDO. Dos Queries con el mismo texto y flag distinto comparan iguales; la nota DATA-07 queda escrita en el código y en este SUMMARY (si un caché usa este hash como clave, debe añadir el flag)."
  - "La inmutabilidad es de ATRIBUTO, no profunda (documentado en el docstring y en el design doc): `q.fields.append(v)` y `q.params[...] = v` no lanzan, y mutar en sitio invalida el hash calculado del estado vivo."
  - "El ejemplo del design doc construye el template con valores reales (`[\"Ana\", 1]`) porque la validación de cardinalidad prohíbe `Query('… {0},{1}', [])`; la reutilización es `q.with_params([...])`."
  - "Solo sqlite (32766) y postgresql (32767) están verificados empíricamente/en fuente; mysql/mariadb (65535), mssql (2100) y oracle (65535) quedan marcados NO verificados y su sonda pertenece al job `engine-heavy` de 02-05."

patterns-established:
  - "TDD en `Query`: commit RED de tests (8551051) seguido del commit GREEN de implementación (f130a13)"
  - "Los adaptadores NO fueron tocados por el refactor de `Query` (D-02): siguen leyendo `.sql`/`.params` desde 02-02"

requirements-completed: [DIAL-05, DIAL-06]

# Metrics
duration: 6min
completed: 2026-09-18
---

# Phase 2 Plan 03: Query inmutable + techos por dialecto Summary

**`Query` convertido en value object inmutable y hashable con compilación por regex de los `{n}` reales, validación de cardinalidad y `with_params()` en lugar del eliminado `rebind`; más `DialectLimits`/`LIMITS` con procedencia y `insert_many` derivando su `chunk` de los techos del motor.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-09-18T04:27:58Z
- **Completed:** 2026-09-18T04:34:18Z
- **Tasks:** 3 (la tarea 1 con ciclo TDD RED → GREEN)
- **Files modified:** 14 (1 creado, 13 modificados)

## Accomplishments

- **DIAL-05 cumplido (redacción D-06):** `Query` es inmutable a nivel de atributo (`q.sql = "x"`, `q.fields = []`, `q.ignore_duplicated = True` y una errata lanzan `AttributeError`), hashable y con `with_params()` que devuelve una copia. `rebind` y `format` han desaparecido sin shims.
- **Compilación correcta:** el sentinel frágil `sql.find("{0}")` y el `enumerate` contiguo se sustituyen por `_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")`. Índices dispersos (`{1}` antes de `{0}`) y duplicados (`{0}` dos veces) compilan bien; la cardinalidad `set(indices) == set(range(len(values)))` rechaza el índice fuera de rango y el parámetro sin usar con un `ValueError` que nombra los índices y el número de valores.
- **D-02 respetado:** ningún adaptador fue tocado por el refactor de `Query`. Los 3 tests white-box (`test_postgresql.py:22`, `test_mssql.py:28`, `test_oracle.py:33`) que leen `q.query[0]`/`q.query[1]` pasan **sin editarse**; el diff de esos 3 ficheros es vacío.
- **DIAL-06 cumplido:** `DialectLimits(max_params, max_rows, provenance)` y `LIMITS` cubren los 6 dialectos; los 6 adaptadores exponen `MAX_PARAMS`/`MAX_ROWS` como atributos de clase y `PoolDb` delega en su template (no miente sobre los techos del motor subyacente).
- **Consumidor real:** `insert_many` deriva `chunk = max(1, min(MAX_PARAMS // n_columnas, MAX_ROWS))` cuando el llamador no lo fija, con `500` como último recurso para objetos que no exponen las constantes. Un `chunk` explícito se respeta tal cual.
- **D-05 cumplido:** `docs/design/0-design.md` §2.1 documenta el objeto inmutable, la regla de cardinalidad, los accesores y la nota de migración `rebind` → `with_params()`; `mkdocs build --strict` pasa.
- Gates de Fase 1 intactos: `ruff check`, `ruff format --check`, `mypy encino_orm` salen 0; `noqa` sigue en 0.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): tests del `Query` inmutable** - `8551051` (test)
2. **Task 1 (GREEN): `Query` inmutable y hashable** - `f130a13` (feat)
3. **Task 2: `MAX_PARAMS`/`MAX_ROWS` por dialecto + chunk derivado** - `7b36eb0` (feat)
4. **Task 3: design doc a la API nueva + guard anti-rebind** - `25b7bab` (docs)

**Plan metadata:** `docs(02-03): complete ... plan` (hash en `git log`)

_Note: la tarea 1 siguió el ciclo TDD RED → GREEN._

## Files Created/Modified

- `tests/test_query.py` (nuevo) - 24 tests puros sin BD: inmutabilidad, `with_params`, compilación dispersa/duplicada/fuera de rango/sin usar, sin placeholders, hash/eq, `str`, y un guard de fuente que rechaza `def rebind(` bajo `encino_orm/`.
- `encino_orm/query.py` - reescrito como value object: slots privados + properties de solo lectura, `_PLACEHOLDER_RE`, validación de cardinalidad, `with_params()`, `__eq__`/`__hash__`/`__str__`; `rebind`/`format` eliminados.
- `encino_orm/dialects/strategies.py` - `DialectLimits` (frozen) + `LIMITS` con `provenance` por dialecto.
- `encino_orm/dialects/__init__.py` - re-exporta `DialectLimits` y `LIMITS`.
- `encino_orm/{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` - `MAX_PARAMS`/`MAX_ROWS` de clase; `MariadbDb` sobrescribe ambos.
- `encino_orm/pool.py` - properties `MAX_PARAMS`/`MAX_ROWS` que delegan en `self._template`.
- `encino_orm/model/model.py` - `insert_many(..., chunk: int | None = None)` con chunk derivado y docstring actualizado.
- `docs/design/0-design.md` - §2.1 reescrita (sketch, ejemplos, regla de cardinalidad, limitaciones, nota de migración) + `fetch_many` y el ejemplo de insert masivo.
- `tests/test_engine.py` - 7 tests nuevos: techos en los 6 adaptadores, cobertura de `LIMITS`, delegación de `PoolDb`, y 4 casos de chunk derivado/explícito/acotado/fallback.

## Decisions Made

- **D-03 literal, con nota DATA-07.** `__eq__`/`__hash__` sobre `(sql_template, fields)`; `ignore_duplicated` EXCLUIDO a propósito. Consecuencia registrada: dos Queries MSSQL con el mismo texto y flags distintos comparan iguales. No hay caché por `Query` en esta fase, así que no hay bug vivo; **si DATA-07 usa este hash como clave de caché, debe añadir `ignore_duplicated` a la clave.**
- **Inmutabilidad de atributo, no profunda.** Documentada en el docstring y en el design doc: reasignación prohibida, mutación in situ fuera de contrato (y rompe el hash).
- **El ejemplo de reutilización del design doc usa valores reales.** La cardinalidad prohíbe `Query("… {0},{1}", [])`; el patrón es crear con valores y llamar a `with_params([...])`.
- **Procedencia honesta en `LIMITS`.** Solo sqlite y postgresql verificados; el resto marcados explícitamente como NO verificados, con la sonda asignada al job `engine-heavy` de 02-05.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Orden de `__slots__` y anotaciones de clase en `Query`**
- **Found during:** Task 1 (GREEN), al correr los gates de Fase 1.
- **Issue:** el plan fijaba literalmente `__slots__ = ("_sql_template", "_fields", "_ignore_duplicated", "_sql", "_params")`, pero RUF023 exige orden natural (el gate `ruff check` fallaba). Además `mypy` no ve los atributos de un `__slots__` escritos vía `object.__setattr__` (`"Query" has no attribute "_sql"`), así que `mypy encino_orm` fallaba con 9 errores.
- **Fix:** se ordenó el tuple (`("_fields", "_ignore_duplicated", "_params", "_sql", "_sql_template")`) y se añadieron anotaciones de clase desnudas (`_sql: str`, etc.), que mypy sí lee y que no crean variables de clase (no chocan con `__slots__` ni con las properties). El invariante del plan —slots SIEMPRE privados + properties sin setter— queda intacto.
- **Files modified:** `encino_orm/query.py`
- **Verification:** `uv run ruff check encino_orm tests` → All checks passed; `uv run mypy encino_orm` → Success (60 files); `tests/test_query.py` → 23 passed.
- **Committed in:** `f130a13` (Task 1 GREEN)

---

**Total deviations:** 1 auto-fixed (1 blocking de gates de lint/tipo, sin cambio de comportamiento).
**Impact on plan:** Ninguno. La superficie pública de `Query` es exactamente la que el plan exige; solo cambia el orden interno de los slots y se añaden anotaciones sin efecto en runtime.

## Issues Encountered

- El primer test del chunk derivado asumía 2 columnas insertables; `Model` inyecta `id`/`enabled`/`created_at`/`updated_at`, así que un modelo con 2 campos declarados tiene 5 columnas insertables (sin el pk auto). Se ajustaron los techos del fake (`MAX_PARAMS=15`, `MAX_ROWS=1000`) para que el chunk derivado fuera observable, en lugar de tocar el código. Resuelto dentro de la autoría de los tests de la tarea 2.

## Verification Evidence

- `uv run pytest -q` (suite completa, extras + servicios locales) → **663 passed** (baseline 632 + 24 de `test_query.py` + 7 de `test_engine.py`).
- `uv run pytest -q -m "not integration and not optional_engine"` → **621 passed, 41 deselected**.
- `uv run pytest tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py -q` → **46 passed** sin editar esos ficheros.
- `uv run pytest tests/test_query.py tests/test_engine.py tests/test_bulk_upsert.py tests/test_pagination_limits.py tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py -q` → **104 passed**.
- `uv run ruff check encino_orm tests` exit 0; `uv run ruff format --check encino_orm tests` exit 0 (111 ficheros); `uv run mypy encino_orm` exit 0 (60 ficheros).
- `uv run mkdocs build --strict` exit 0.
- `grep -rn "def rebind" encino_orm/` → vacío; `grep -rn "\.query\[0\]\|\.query\[1\]" encino_orm/` → vacío; `grep -rn "noqa" encino_orm/` → 0.
- `grep -n "def rebind" docs/design/0-design.md` → vacío; `grep -c "with_params" docs/design/0-design.md` → 7.

## Known Stubs

None — no se introdujo ningún valor hardcodeado, placeholder ni componente sin fuente de datos. El `chunk = 500` es un último recurso explícito y documentado para objetos sin constantes de dialecto, no un stub.

## Threat Flags

None — la superficie nueva (validación de cardinalidad, hash) cae dentro del `<threat_model>` del plan (T-02-14…T-02-19) y no añade límites de confianza nuevos.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 02-04 puede aplicar el alias `AS n` en los 3 sitios del bug `COUNT(*)` sin reabrir `Query` ni los adaptadores.
- 02-05 es dueño de la sonda manual de los techos NO verificados (mysql/mariadb/mssql/oracle) en el job `engine-heavy`, y de los snapshots syrupy.
- **Registrado para la Fase 8 (release):** `rebind` se eliminó sin shims; el `CHANGELOG.md` y `MIGRATION-0.3.md` deben recoger la ruptura y el reemplazo por `with_params()`. No se escribieron en esta fase por decisión D-01.
- **Registrado para DATA-07 (v2):** si un caché usa `hash(Query)` como clave, debe incluir `ignore_duplicated`.

---
*Phase: 02-dialect-seam-engine-parity*
*Completed: 2026-09-18*

## Self-Check: PASSED

- `tests/test_query.py` — FOUND
- `encino_orm/query.py` — FOUND
- `encino_orm/dialects/strategies.py` — FOUND
- `encino_orm/pool.py` — FOUND
- `docs/design/0-design.md` — FOUND
- Commit `8551051` — FOUND
- Commit `f130a13` — FOUND
- Commit `7b36eb0` — FOUND
- Commit `25b7bab` — FOUND
