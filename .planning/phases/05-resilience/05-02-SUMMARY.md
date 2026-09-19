---
phase: 05-resilience
plan: 02
subsystem: database
tags: [resilience, reconnect, transaction-guard, write-safety, a2-policy, sqlite-memory, pool]

# Dependency graph
requires:
  - phase: 05-resilience
    provides: "is_disconnect_error por adaptador + FakeResilientDb (05-01)"
provides:
  - "Db._with_reconnect(fn, *, retry) — template method que reconecta EXACTAMENTE UNA VEZ y solo fuera de transacción"
  - "Db._reconnect() in-place (close() guardado + connect(**self._connect_kwargs))"
  - "Db._is_reconnectable(exc) — cubre is_disconnect_error y la ConnectionError de librería (caída en reposo)"
  - "Wrappers públicos concretos execute/execute_insert/fetch_* → privados _execute/_execute_insert/_fetch_*"
  - "Estado _connect_kwargs/_connected_at en Db y en los cinco adaptadores"
  - "SqliteDb._reconnect rechaza ':memory:' (evita pérdida silenciosa de datos)"
  - "Bloque RESL-02 de tests/test_resilience.py (12 tests) + asserts en tests/test_base.py"
affects: [05-03, 05-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Template method de recuperación: clasificar el original → guard de tx → reconectar una vez → política A2 (retry or pre_execution)"
    - "Público concreto que delega en privado concreto sobreescribible (precedente last_id/_last_id_value); NO @abstractmethod para no romper dobles (Pitfall 10)"
    - "Reconexión in-place (close + connect con kwargs originales) para conservar el handle del pool (Fase 4)"
    - "Separación estricta de caminos: lock → retry() con backoff; disconnect → _with_reconnect sin bucle; la misma instancia de lock se relanza"

key-files:
  created: []
  modified:
    - encino_orm/base.py
    - encino_orm/sqlite.py
    - encino_orm/mysql.py
    - encino_orm/postgresql.py
    - encino_orm/mssql.py
    - encino_orm/oracle.py
    - tests/test_resilience.py
    - tests/test_base.py

key-decisions:
  - "Política A2 implementada literal: lecturas (retry=True) re-ejecutan; escrituras pre-ejecución (OrmConnectionError) ejecutan porque la sentencia nunca llegó al driver; escrituras mid-statement reconectan y RELANZAN; dentro de tx siempre se relanza"
  - "El alias OrmConnectionError (from .exceptions import ConnectionError as OrmConnectionError) es la única importación de .exceptions en base.py; 05-04 la extenderá en la misma línea"
  - "Los privados _execute/_execute_insert/_fetch_* son concretos con NotImplementedError, no @abstractmethod, para que LockDb/LedgerDb y los dobles que sobreescriben el público sigan instanciándose"
  - "SQLite :memory: rechaza reconectar lanzando ConnectionError; 05-04 lo refinará a ConnectionLostError (subclase, test sigue verde)"
  - "PoolDb no cambia: _run resuelve el wrapper del adaptador con getattr y PoolDb sobreescribe los públicos (sin doble reconexión)"

patterns-established:
  - "Reconexión exactamente-una-vez sin bucle ni backoff, estrictamente separada de retry()"
  - "Guard de transacción como defensa de integridad del Core Value: nunca reconectar dentro de tx"

requirements-completed: [RESL-02]

# Metrics
duration: 9min
completed: 2026-09-19
---

# Phase 5 Plan 02: Resilience Summary

**Template method `Db._with_reconnect` que reconecta exactamente una vez y solo fuera de transacción, con la política A2 segura frente a duplicación de escrituras, y wrappers públicos concretos que delegan en privados `_`-prefijados de cada adaptador**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-09-19T05:03:00Z
- **Completed:** 2026-09-19T05:12:00Z
- **Tasks:** 3
- **Files modified:** 8 (0 creados, 8 modificados)

## Accomplishments

- `Db._with_reconnect(fn, *, retry)` es un template method que clasifica la excepción ORIGINAL, respeta el guard `await self.in_transaction()`, reconecta una sola vez y aplica la política A2 por tipo de operación.
- `_is_reconnectable` cubre los dos caminos reales: la excepción tipada del driver y la `ConnectionError` de la librería lanzada por `_ensure_connected()` en una caída en reposo (Pitfall 1).
- `_reconnect` reconecta in-place con los kwargs ORIGINALES (`_connect_kwargs`), es no-op si nunca hubo conexión y envuelve el `close()` en `try/except` (Pitfall 6). Nunca loguea el dict (contiene `password`).
- Los cinco métodos de ejecución de `Db` pasan de `@abstractmethod` a wrappers concretos; los privados `_execute`/`_execute_insert`/`_fetch_*` nacen concretos con `NotImplementedError` (Pitfall 10).
- Los cinco adaptadores renombran sus métodos a `_`-prefijados, guardan `_connect_kwargs`/`_connected_at` y limpian `_connected_at` en `close()`.
- `SqliteDb._reconnect` rechaza `:memory:` (base nueva y vacía = pérdida silenciosa de datos, Pitfall 2); una BD en fichero reconecta sin perder filas.
- Bloque RESL-02 de 12 tests deterministas con `FakeResilientDb` + asserts en `test_base.py`. `pool.py` intacto.

## Task Commits

Each task was committed atomically:

1. **Task 1: `_with_reconnect` + `_reconnect` + `_is_reconnectable` + wrappers públicos concretos** — `aec8596` (feat)
2. **Task 2: rename a `_execute`/`_fetch_*` + estado de conexión + `:memory:` en los seis adaptadores** — `c9bab4c` (feat)
3. **Task 3: bloque RESL-02 + verificación de no-regresión** — `d2a8612` (test)

**Plan metadata:** (este commit) docs(05-02): completa el plan de resiliencia RESL-02

## Files Created/Modified

- `encino_orm/base.py` — import `ConnectionError as OrmConnectionError`; estado `_connect_kwargs`/`_connected_at`; `_is_reconnectable`/`_reconnect`/`_with_reconnect`; wrappers públicos concretos y privados con `NotImplementedError`.
- `encino_orm/sqlite.py` — rename a privados; `_connect_kwargs={"database": database}`; `_connected_at` en connect/close; `_reconnect` rechaza `:memory:`.
- `encino_orm/mysql.py` — rename; kwargs originales guardados antes de `aiomysql.connect`; `_connected_at` en connect/close. Heredado por MariaDB sin tocarlo.
- `encino_orm/postgresql.py` — rename; kwargs originales; `_connected_at` en connect/close.
- `encino_orm/mssql.py` — rename; `_connect_kwargs` con los kwargs individuales (no el `conn_str`); `_connected_at`.
- `encino_orm/oracle.py` — rename; `_connect_kwargs` con los kwargs individuales (no el `dsn`); `_connected_at`.
- `tests/test_resilience.py` — bloque RESL-02: 12 tests (selector `-k reconnect`).
- `tests/test_base.py` — los cinco públicos ya no son abstractos; `Db._execute`/`Db._fetch_one` lanzan `NotImplementedError`.

## Evidencia de la política A2 (connects/executes por escenario)

| Escenario | Test | connect | close | fn | Resultado |
|-----------|------|---------|-------|----|-----------|
| Lectura fuera de tx | `test_lectura_desconectada_fuera_de_tx_reconecta_una_vez` | 1 | 1 | fetches=2 | devuelve el valor |
| Escritura pre-ejecución (`OrmConnectionError`) | `test_escritura_pre_ejecucion_reconecta_y_ejecuta` | 1 | 1 | executes=2 | devuelve `"ok"` (primera ejecución real) |
| Escritura mid-statement (driver) | `test_escritura_mid_statement_reconecta_pero_no_reejecuta` | 1 | 1 | executes=1 | RELANZA (sin duplicar) |
| Desconexión dentro de tx | `test_desconexion_dentro_de_tx_relanza_sin_reconectar` | 0 | 0 | executes=1 | RELANZA (guard) |
| Fallo persistente | `test_fallo_persistente_no_hace_bucle` | 1 | 1 | fetches=2 | RELANZA (sin bucle) |
| Error no reconectable | `test_error_no_reconectable_relanza` | 0 | — | — | RELANZA |
| Lock | `test_lock_no_se_reconecta_y_conserva_la_excepcion` | 0 | — | — | misma instancia |
| `_reconnect` sin conexión previa | `test_reconnect_noop_si_nunca_conecto` | 0 | — | — | no-op |

## Decisions Made

- **A2 literal y documentada:** el docstring de `_with_reconnect` enumera la política por operación. La rama "triunfa" del Success Criterion 2 se cubre con una lectura y una escritura pre-ejecución; la escritura mid-statement reconecta pero relanza.
- **Alias obligatorio `OrmConnectionError`:** única importación de `.exceptions` en `base.py` (05-04 la extenderá en la misma línea). Evita sombrear el builtin `ConnectionError`.
- **`_connect_kwargs` en SQLite = `{"database": database}` con el default ya resuelto**, para que `_reconnect` use la misma BD.
- **No se tocó `tests/_resilience_helpers.py`:** su puente `_DB_CON_TEMPLATE = hasattr(Db, "_with_reconnect")` se activó solo al existir el template method; `FakeResilientDb` reenvía a `super()` sin cambios.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] El literal `time.time()` en un docstring rompía el criterio de aceptación**
- **Found during:** Task 1 (verificación de aceptación)
- **Issue:** `grep -c "time.time()" encino_orm/base.py` debe devolver 0, pero el comentario decía "jamás `time.time()`".
- **Fix:** se reformuló a "nunca el reloj de pared, inmune a saltos de hora".
- **Files modified:** `encino_orm/base.py`
- **Commit:** `aec8596`

### Criterios de aceptación inconsistentes (documentados, no corregidos en código)

**2. `Db()` sigue lanzando `TypeError` (por diseño)**
- El criterio `uv run python -c "from encino_orm.base import Db; Db()"` "no lanza TypeError" contradice la propia frase "Db sigue siendo abstracta por los métodos restantes". Los cinco métodos de ejecución dejan de ser abstractos, pero `connect`/`close`/`is_alive`/`in_transaction`/`commit`/`rollback`/`save_point`/`insert`/`delete`/`update`/`exists`/`migrate`/`migrate_status` siguen siéndolo, así que `Db()` **debe** seguir lanzando `TypeError`. La verificación correcta (y usada) es `assert not getattr(Db.execute, "__isabstractmethod__", False)` + los dobles que heredan de `Db` instanciándose.

## TDD Gate Compliance

- El plan es `type: execute` (no `type: tdd`), así que el gate plan-level no aplica.
- La Task 1 tiene `tdd="true"` pero su `<files>` es solo `encino_orm/base.py`; los tests viven en la Task 3. Por la restricción de no salir de los ficheros de cada tarea, los tests se escribieron tras la implementación (no hubo commit RED separado). El comportamiento queda cubierto por los 12 tests RESL-02 de `d2a8612`.

## Non-regression Evidence

- `TestD4AutoRetry` (`tests/test_d_recommendations.py -k retry`) → **1 passed**: el lock se relanza como la misma instancia y `retry()` sigue reconociéndolo.
- `tests/test_pool.py tests/test_pool_characterization.py tests/test_pool_concurrency.py` → **85 passed, 11 deselected** sin editar `pool.py`.
- `git diff --stat encino_orm/pool.py` → **vacío**.
- `tests/test_sqlite.py tests/test_crud.py tests/test_migrations.py` → **65 passed**.
- `tests/test_mariadb.py` (no integration/optional) → incluido en los 85, herencia verificada.

## Issues Encountered

None. Los seis contenedores no fueron necesarios: los tests RESL-02 usan dobles deterministas; SQLite real cubre el camino de fichero/`:memory:`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `_with_reconnect` es el punto único de clasificación/reconexión: RESL-03 (`pre_ping`/`max_connection_lifetime`) engancha en `_with_reconnect` y RESL-04 (`_translate_exception`) sustituye los `raise` por `raise ... from exc`.
- `_is_reconnectable`/`_reconnect` quedan listos para que 05-04 extienda el import de `.exceptions` (misma línea) y refina `SqliteDb._reconnect` a `ConnectionLostError`.
- Gate de cierre: `uv run pytest -q` → 964 passed; `uv run ruff check encino_orm tests` → 0; `uv run ruff format --check encino_orm tests` → 0; `uv run mypy encino_orm` → Success (ratchet sin tocar).

## Self-Check: PASSED

- [x] `encino_orm/base.py` contiene `_with_reconnect`, `_reconnect`, `_is_reconnectable` (3) y los 5 privados
- [x] `@abstractmethod` baja de 18 a 14 (13 reales + 1 en comentario)
- [x] `OrmConnectionError` usado en `_is_reconnectable` y `pre_execution`; 0 usos del builtin
- [x] 5 privados por adaptador (25), 0 públicos duplicados; `_connect_kwargs`/`_connected_at` >= 2 por fichero
- [x] `SqliteDb._reconnect` presente y `:memory:` sigue referenciado
- [x] `tests/test_resilience.py` con 19 `def test_` (RESL-01 + RESL-02); `-k reconnect` → 12 passed
- [x] `uv run pytest -q` → 964 passed; no-integration/optional → 876 passed
- [x] `uv run ruff check`/`format --check` → 0; `uv run mypy encino_orm` → Success
- [x] Commits `aec8596`, `c9bab4c`, `d2a8612` presentes; `encino_orm/pool.py` sin cambios

## Self-Check: PASSED

---
*Phase: 05-resilience*
*Completed: 2026-09-19*
