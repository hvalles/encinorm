# Phase 4: Pool Correctness & Concurrency - Research

**Researched:** 2026-09-18
**Domain:** Corrección de un pool de conexiones asíncrono (asyncio) sobre seis motores, con captura del id de inserción dentro de la sentencia y semántica de liberación explícita.
**Confidence:** HIGH en el mapa del estado actual, la carrera de `acquire()` y los mecanismos de captura de id (todo verificado leyendo el código vivo y **sondeando los seis contenedores locales**); MEDIUM en la forma final del handle y en la semántica exacta de `reset_on_release` (decisiones de diseño, no hechos); HIGH en que `pytest-timeout`/`pytest-repeat` cargan con pytest 9.1.1 en un venv aislado.

> **No existe `04-CONTEXT.md`.** La fase no ha pasado por `/gsd-discuss-phase`. Por eso no hay sección `## User Constraints (from CONTEXT.md)`; en su lugar se citan como restricciones vinculantes las decisiones ya bloqueadas en `ROADMAP.md` (los 5 planes `04-01`…`04-05`, los 5 criterios de éxito y las *Research Corrections* #1/#4/#5). Las decisiones de diseño que el planner no pueda deducir de ahí están en **Open Questions** y **Assumptions Log**.

<user_constraints>
## User Constraints (from ROADMAP.md — no CONTEXT.md exists)

### Locked Decisions (ROADMAP Phase 4, líneas 249-274 + Research Corrections)

- **Plan `04-01`:** handle `PooledConnection` que concentra el estado por conexión (driver, `last_id`, timestamps, generación, en-uso) y `acquire()` con reserva-antes-de-await que nunca bloquea cruzando el `await`; binding de propiedad de tarea en el contextvar `_current_connection` — **POOL-01, POOL-02**.
- **Plan `04-02`:** capturar `last_id` **dentro** del insert (`RETURNING` / `SCOPE_IDENTITY` / `lastrowid` inmediato) por conexión/tarea; deprecar `last_id()` post-hoc con warning. Posee además el fix del `SET` del `MERGE` de Oracle (**ORA-38104**): excluir `conflict_cols` de `WHEN MATCHED THEN UPDATE SET` (como ya hace `build_upsert` con `update_cols`) para que `Model.insert(replace=True)` sea ejecutable en Oracle — **POOL-03**.
- **Plan `04-03`:** política `reset_on_release` (rollback por defecto, commit configurable) con commit-or-rollback **explícito en `execute`/`_run` primero** para que las escrituras standalone no se pierdan en silencio; `DeprecationWarning` + entrada de CHANGELOG — **POOL-04**.
- **Plan `04-04`:** contador de generación + reaper perezoso de conexiones inactivas por encima de `min_size` (sin daemon), y `close()` idempotente que nunca cierra una conexión en uso — **POOL-05, POOL-06**.
- **Plan `04-05`:** tests deterministas de concurrencia/estrés con barrera hecha a mano con `asyncio.Event` (nunca `asyncio.Barrier`/`TaskGroup` en 3.10), `pytest-timeout` con el método *signal*, y variante de estrés `pytest-repeat` tras un marker — **POOL-07**.
- **Research Correction #1 (ROADMAP:379-387):** `lastval()` de PostgreSQL es **SESSION-scoped, no transaction-scoped**; la única respuesta correcta en PostgreSQL es `INSERT ... RETURNING <pk>`, lo que cambia el contrato de retorno de `Db.insert`. Ya corregido en `.planning/research/ARCHITECTURE.md:657`.
- **Research Correction #4 (ROADMAP:402-404):** el piso de Python 3.10 prohíbe `asyncio.Barrier`, `asyncio.timeout`, `TaskGroup` y `except*` en código de librería **y en tests**. POOL-07 usa barrera con `asyncio.Event`.
- **Research Correction #5 (ROADMAP:406-409):** el orden de POOL-04 es *safety-critical*: (i) `execute`/`_run` commitean o revierten explícitamente, (ii) **después** `release()` revierte sobrantes con `DeprecationWarning`, (iii) `TestPoolAutocommit` sigue pasando. Invertir el orden convierte cada `pool.execute(INSERT)` standalone en pérdida silenciosa de datos.

### the agent's Discretion (deducido; no hay CONTEXT.md)

- Forma exacta del handle `PooledConnection` (dataclass vs proxy) y si el contextvar guarda el handle o el driver.
- Nombres y firma exactos de la API de captura de id (`execute_insert`, `returning=`, `Query.returns_id`, …).
- Valores admitidos de `reset_on_release` y a qué se engancha el `DeprecationWarning`.
- Semántica exacta del contador de generación.
- Si `session()` pasa a fijar `_current_connection` (cambio de comportamiento).
- Si se añade un piso de cobertura para `encino_orm/pool.py` en `tools/ci/check_coverage_floors.py`.

### Deferred Ideas (OUT OF SCOPE)

- Reintento/reconexión ante desconexión (`pre_ping`, `max_connection_lifetime`) → **Fase 5** (RESL-01…04).
- Pool distribuido / multi-proceso: el pool es por proceso (el "singleton" `set_default_db` es un global de módulo, `context.py:20`).
- Sustituir `asyncio.Queue` por una estructura propia con prioridad/LIFO: fuera de alcance; `Queue` + reserva explícita basta.
- Endurecer el método *thread* de `pytest-timeout` para que no mate el proceso: es una limitación del plugin, no del proyecto.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| POOL-01 | Existe un handle `PooledConnection` que concentra el estado por conexión (driver, `last_id`, timestamps, generación, en-uso) | Hoy el estado está repartido: `_pool`/`_connections`/`_size`/`_last_id`/`_last_used` en `PoolDb` (`pool.py:65-71`) y `_last_id`/`_in_tx` **también** en cada adaptador (`mysql.py:60`, `mssql.py:47`, `oracle.py:57`). §2 (design) y §7 (ownership). |
| POOL-02 | `acquire()` es libre de carreras (reserva-antes-de-await) y nunca supera `max_size` | Carrera exacta en `pool.py:143-149`: `if self._size < self._max_size:` → `await self._create_connection()` → `self._size += 1`. Medida: `_size == 5` con `max_size=2` y 5 tareas (`01-05-SUMMARY.md:88`). §1 y §3. |
| POOL-03 | `last_id` se captura **dentro** del insert por conexión/tarea; `last_id()` post-hoc deprecado. Incluye ORA-38104 | Mecanismo por motor verificado con sondas contra los 6 contenedores. PostgreSQL debe cambiar a `RETURNING` (hoy `lastval()`, `postgresql.py:232-234`); MSSQL usa `@@IDENTITY` en statement aparte (`mssql.py:254-257`); Oracle ya usa `RETURNING ... INTO` (`oracle.py:245-262`) pero **incondicionalmente** (`builders.py:145-146`). ORA-38104 reproducido. §4. |
| POOL-04 | Política `reset_on_release` con rollback por defecto, warning de deprecación y CHANGELOG | Hoy `release()` no toca la transacción (`pool.py:173-175`) y el commit implícito vive en `_run`/`execute` (`pool.py:242-243,284-285`). §5. |
| POOL-05 | Contador de generación + reaper perezoso sin daemon | Hoy solo hay `_needs_check` por `idle_timeout` (`pool.py:128-134`) que reemplaza la conexión **al adquirirla**, no la cierra por encima de `min_size`. §6. |
| POOL-06 | `close()` idempotente que nunca cierra una conexión en uso | Hoy `close()` cierra **todas** las de `_connections`, incluidas las retenidas (`pool.py:181-182`); caracterizado en `test_pool_characterization.py:368-376`. §6. |
| POOL-07 | Tests deterministas 3.10 + `pytest-timeout` (signal) + `pytest-repeat` tras marker | `EventBarrier` ya existe en `test_pool_characterization.py:126-144`. `pytest-timeout 2.4.0` y `pytest-repeat 0.9.4` verificados cargando con pytest 9.1.1 en venv aislado. §8. |
</phase_requirements>

## Summary

El pool tiene **cuatro defectos independientes y reproducibles**, y la fase es un refactor con cambio de contrato público. Todo lo que sigue está anclado al código vivo.

1. **La carrera de admisión es real y está medida.** En `acquire()` (`pool.py:136-171`) la comprobación `if self._size < self._max_size` (`:143`) va seguida de un `await self._create_connection()` (`:144`); el incremento `self._size += 1` ocurre **después** (`:146`). Con `min_size=0, max_size=2` y 5 tareas concurrentes, las 5 pasan la comprobación y el `_size` observado es **exactamente 5** (`tests/test_pool_characterization.py:227-228`, medido en `01-05-SUMMARY.md:88`). El fix es reservar el cupo **antes** del `await` y devolverlo si la conexión falla.

2. **`last_id` no pertenece al insert que lo produjo.** El id vive en **dos sitios**: por conexión (`mysql.py:196`, `mssql.py:255-257`, `oracle.py:262`) y **a nivel de pool** (`pool.py:69`, escrito en `pool.py:281`). Fuera de `transaction()`, `PoolDb.last_id()` devuelve el cache del pool (`pool.py:304`), así que una tarea que no insertó observa el id de otra (`test_pool_characterization.py:258-268`). Además el mecanismo por motor es incorrecto en dos casos: PostgreSQL usa `SELECT lastval()` (`postgresql.py:232-234`), que es **session-scoped** y devuelve el último `nextval` de la sesión (cualquier tabla, cualquier tarea que comparta la conexión); MSSQL usa `SELECT CAST(@@IDENTITY AS INT)` (`mssql.py:255`), que es **session-scoped y contaminable por triggers**.

3. **La semántica de liberación es accidental.** `release()` (`pool.py:173-175`) solo registra `_last_used` y reencola; el commit lo hace el llamador `_run`/`execute` con `if await db.in_transaction(): await db.commit()` (`pool.py:242-243`, `:284-285`). No hay rollback, no hay dedupe (doble `release()` mete dos referencias de la misma conexión en la cola, `test_pool_characterization.py:326-339`), no hay comprobación de propiedad.

4. **`close()` no respeta al tenedor.** `close()` (`pool.py:177-185`) drena la cola y cierra **todas** las entradas de `_connections`, incluidas las que un llamador mantiene (`test_pool_characterization.py:368-376`).

**Primary recommendation:** (a) `acquire()` reserva `_size` antes del `await` y el contextvar `_current_connection` pasa a guardar un `PooledConnection` (handle con `driver`, `last_id`, `last_used`, `generation`, `checked_out`), con `resolve_db()` desenvainando `.driver` para no romper a `Model`; (b) la captura del id se hace con una nueva `Db.execute_insert(qry)` y un `returning=<col>` **opt-in** en `Db.insert` (nunca incondicional: `RETURNING id` sobre una tabla sin columna `id` falla con `UndefinedColumnError`/ORA-00904 — verificado), eliminando el cache `_last_id` del pool; (c) `execute`/`_run` commitean o revierten explícitamente **antes** de que `release()` aplique `reset_on_release="rollback"`; (d) el reaper y `close()` operan solo sobre la cola de ociosas y sobre `_checked_out`.

**Hallazgo que cambia el alcance de POOL-03:** en Oracle, `MERGE ... RETURNING ... INTO` **no es soportado** (ORA-00933 "SQL command not properly ended", verificado contra el contenedor). Por tanto `Model.insert(replace=True)` en Oracle puede volverse **ejecutable** (fix ORA-38104) pero **no puede devolver el id** — el contrato "MERGE devuelve 0 / no asigna `id`" (`model/model.py:540-541`) se mantiene también en Oracle.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Estado por conexión (`driver`, `last_id`, timestamps, generación, in-uso) | Pool (`encino_orm/pool.py`, `PooledConnection`) | Adaptador (dueño del driver) | El pool es quien presta y recupera; el adaptador no puede saber si está en uso. |
| Admisión / reserva de cupo | Pool (`acquire`) | — | Invariante del pool: `_size <= max_size` siempre. |
| Captura del id de inserción | Adaptador (`execute_insert`) | Builder (marca `Query`) | Solo el adaptador conoce el driver (`lastrowid`, `RETURNING`, `OUTPUT`). |
| Política de reset al liberar | Pool (`release`/`_run`/`execute`) | Adaptador (`in_transaction`/`commit`/`rollback`) | El pool decide *cuándo*; el adaptador ejecuta el *cómo*. |
| Reaper de ociosas / `close()` | Pool | — | Solo el pool ve la cola de ociosas y el conjunto en uso. |
| Binding de propiedad de tarea | Pool (`_current_connection`) | `context.py::resolve_db` (desenvaina) | El contextvar es el mecanismo de afinidad por tarea del proyecto. |
| Deprecación de `last_id()` | `Db` (base) | Adaptadores (implementan `_last_id_value`) | Centralizar el warning evita que `filterwarnings=["error"]` estalle en seis sitios. |
| Fix ORA-38104 | `dialects/builders.py` (`_merge_sql`/`build_insert`) | `oracle.py` (solo SQL de driver) | El render del MERGE es compartido; se corrige una vez. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdlib `asyncio` (`Queue`, `Event`, `contextvars`) | Python ≥3.10 | Pool, barrera determinista, afinidad por tarea | Ya en uso (`pool.py:1-2`); `asyncio.Barrier` no existe en 3.10 (Correction #4). |
| stdlib `time.monotonic` | Python ≥3.10 | `last_used` / detección de ociosidad | Ya en uso (`pool.py:118,134,147,174`); monotónico, inmune a saltos de reloj. |
| stdlib `dataclasses` | Python ≥3.10 | `PooledConnection` (value object) | Convención del repo para objetos de valor (`Column`, `Constraint`, `Index`, `Migration`). |
| stdlib `warnings` | Python ≥3.10 | `DeprecationWarning` de `last_id()` y de `reset_on_release="commit"` | Convención estándar; el repo ya importa `warnings` (`mysql.py:4`). |
| `pytest` + `pytest-asyncio` | 9.1.1 / 1.4.0 | Tests | Ya configurados (`asyncio_mode="auto"`, loop scope `function`). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-timeout` | 2.4.0 | Matar tests de barrera colgados (barrera con `parties` mal ajustado cuelga para siempre) | En los tests marcados `concurrency`; método *signal* en CI Linux. `[ASSUMED]` |
| `pytest-repeat` | 0.9.4 | Variante de estrés (`@pytest.mark.repeat(N)` / `--count=N`) | Tras el marker `stress`, excluida de la corrida por defecto o con N pequeño. `[ASSUMED]` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `PooledConnection` como dataclass + `resolve_db()` desenvaina | `PooledConnection` como proxy de `Db` | El proxy exige reimplementar ~15 métodos (`insert/delete/update/execute/fetch_*/last_id/transaction/retry/is_lock_error/MAX_PARAMS/MAX_ROWS/transactional_ddl/dialect`) y `engine_of` lee `.dialect` (`engine.py:35-43`). Desenvainar en `resolve_db` es 3 líneas. |
| Nueva `Db.execute_insert(qry)` | Cambiar el retorno de `Db.execute` a un objeto `(rowcount, last_id)` | Rompe todos los llamadores que hacen `count = await db.execute(...)`: `Model.upsert` (`model.py:678`), `insert_many` (`model.py:619`), `migration.py:56,62,97-114`, `transfer.py:118-157`, `http/`, `graphql/`. Blast radius enorme. |
| `returning=<col>` opt-in en `Db.insert` | Añadir `RETURNING id` incondicionalmente | Verificado: `INSERT ... RETURNING id` sobre una tabla **sin** columna `id` lanza `asyncpg.UndefinedColumnError` (PostgreSQL) y ORA-00904 (Oracle). Rompería `transfer.py:157` (copia tablas arbitrarias) y cualquier `db.insert` directo. |
| `OUTPUT INSERTED.id` en MSSQL | `SELECT SCOPE_IDENTITY()` en statement aparte | Verificado: `SCOPE_IDENTITY()` devuelve **NULL** cuando se ejecuta en un `cursor.execute` separado (el scope es por batch). Solo funciona en el mismo statement, y entonces `cursor.rowcount` pasa a **-1**. `OUTPUT` obliga a manejar el rowcount. |
| `SCOPE_IDENTITY()`/`OUTPUT` en MSSQL | Mantener `@@IDENTITY` | `@@IDENTITY` es session-scoped: un trigger con su propia identidad lo contamina. Es el defecto que POOL-03 corrige. |
| Barrera `asyncio.Event` a mano | `hypothesis` `RuleBasedStateMachine` | Corrección #4 lo deja como *fallback*; `hypothesis` es una dependencia nueva y el repo prefiere stdlib. `EventBarrier` ya existe y está probada. |
| `reset_on_release` con dos valores | Añadir `"none"` (comportamiento actual) | `"none"` es exactamente el comportamiento accidental que la fase elimina; exponerlo invita a reintroducirlo. |

**Installation:**
```bash
# pyproject.toml [dependency-groups].dev — pines exactos, como ruff/syrupy
# (la salida de la config de test está versionada; ver 01-03-SUMMARY.md)
uv add --dev "pytest-timeout==2.4.0" "pytest-repeat==0.9.4"
uv lock   # el job `deps` de CI corre `uv lock --check` (ci.yml:222-225)
```

**Version verification:** `pytest-timeout==2.4.0` y `pytest-repeat==0.9.4` son las últimas publicadas en PyPI (`pip index versions`, 2026-09-18). `pytest-repeat 0.9.4` es del 2025-04-07, requiere Python ≥3.9 y `pytest` sin cap superior; mantenedores `pytest-dev` (bsilverberg, davehunt, nicodemus, okken) — `[VERIFIED: pypi.org/pypi/pytest-repeat/json]`. `pytest-timeout 2.4.0` es la última publicada; su changelog en `master` documenta 2.5.0 (aún no publicada) con "Minimum support Python3.10 and pytest=8.0" — `[VERIFIED: raw.githubusercontent.com/pytest-dev/pytest-timeout/master/README.rst]`. **Ambos plugins se instalaron y se ejecutaron con `pytest==9.1.1` + `pytest-asyncio==1.4.0` en un venv aislado (Python 3.10.18): los plugins cargan (`plugins: asyncio-1.4.0, repeat-0.9.4, timeout-2.4.0`), `@pytest.mark.repeat(3)` produce 3 ejecuciones, y `@pytest.mark.timeout(2)` interrumpe un `await` colgado** — `[VERIFIED: venv aislado en %TEMP%]`. Sin embargo, `slopcheck` no está disponible en esta máquina, así que ambos paquetes quedan `[ASSUMED]` a efectos del planner (ver auditoría).

## Package Legitimacy Audit

> `slopcheck` **no está instalado y no se pudo instalar** en esta máquina (`slopcheck` no encontrado en `PATH`). Por la regla de degradación segura, **todos** los paquetes nuevos de esta fase quedan `[ASSUMED]` y el planner DEBE insertar un `checkpoint:human-verify` antes de cada instalación, aunque la evidencia de registro y de runtime sea fuerte.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pytest-timeout` | PyPI | ~12 años (1.0.0 en 2015) | no consultado (`downloads=-1`) | github.com/pytest-dev/pytest-timeout | no disponible | `[ASSUMED]` — planner añade `checkpoint:human-verify` |
| `pytest-repeat` | PyPI | ~11 años (0.1 en 2015) | no consultado (`downloads=-1`) | github.com/pytest-dev/pytest-repeat | no disponible | `[ASSUMED]` — planner añade `checkpoint:human-verify` |

**Packages removed due to slopcheck [SLOP] verdict:** none (slopcheck no disponible)
**Packages flagged as suspicious [SUS]:** none

**Evidencia adicional (no sustituye al gate):** ambos son plugins oficiales de la organización `pytest-dev`, sin vulnerabilidades reportadas (`vulnerabilities: []`), con repositorio fuente público y mantenimiento activo; ambos cargaron y funcionaron bajo `pytest 9.1.1`/Python 3.10 en venv aislado. **No se añaden dependencias de runtime** (solo `dependency-groups.dev`), así que el contrato de importación diferida del núcleo (`AGENTS.md` §Constraints) no se toca.

## Architecture Patterns

### System Architecture Diagram

```
                        PoolDb
   ┌──────────────────────────────────────────────────────────────────────────┐
   │  _idle: asyncio.Queue[PooledConnection]     (solo OCIOSAS)                │
   │  _checked_out: set[PooledConnection]        (EN USO por una tarea)        │
   │  _size: int  (invariante: <= max_size SIEMPRE)   _generation: int         │
   └──────────────────────────────────────────────────────────────────────────┘

   acquire(timeout)
     │
     ├─► _reap()  ── saca de _idle las ociosas con idle > idle_timeout
     │               y _size > min_size ──► driver.close()  (POOL-05)
     │
     ├─► get_nowait() ──► hay ociosa ──► _checked_out.add(conn) ──► conn
     │
     └─► QueueEmpty
           ├─ _size < max_size?
           │     SÍ: _size += 1        ◄── RESERVA ANTES DEL AWAIT  (POOL-02)
           │         try: conn = await _create_connection()   (await point)
           │         except: _size -= 1; raise                ◄── devuelve el cupo
           │         _checked_out.add(conn) ──► conn
           └─ NO: await queue.get() (o wait_for(timeout)) ──► PoolExhaustedError

   ── operación ──────────────────────────────────────────────────────────────

   PoolDb.execute(qry) / execute_insert(qry) / _run(method, ...)
     │
     ├─ handle = _current_connection.get()      # handle, NO driver
     │    └─ dentro de transaction()/session(): handle ya retenido
     ├─ else: handle = await acquire()
     │
     ├─ result = await getattr(handle.driver, method)(...)   (POOL-01)
     │    └─ execute_insert captura el id EN la sentencia y lo deja en handle.last_id
     │
     └─ finally:
          ┌─ EXPLÍCITO PRIMERO (POOL-04, Correction #5):
          │    éxito  → if driver.in_transaction(): await driver.commit()
          │    error  → if driver.in_transaction(): await driver.rollback()
          └─ release(handle)
                ├─ ownership: handle ∈ _checked_out? si no → warning, ignorar (doble release)
                ├─ reset_on_release: sobrante de transacción → rollback (default) | commit
                ├─ _reap()   (POOL-05)
                └─ _closed? → driver.close()  :  _idle.put(handle)

   close()  (POOL-06)
     ├─ _closed = True; idempotente (2ª llamada no-op)
     ├─ drena _idle y cierra SOLO las ociosas
     └─ las EN USO no se tocan; al liberarse se cierran (rama _closed de release)
```

### Recommended Project Structure
```text
encino_orm/
├── pool.py                 # PooledConnection + PoolDb (handle, acquire/release/reap/close)
├── context.py              # resolve_db() desenvaina _current_connection.driver
├── base.py                 # Db.insert(returning=...), Db.execute_insert(), Db.last_id() deprecado
├── query.py                # Query: + returns_id / id_column (metadata, fuera de __eq__/__hash__)
├── dialects/
│   └── builders.py         # build_insert: RETURNING/OUTPUT opt-in; _merge_sql excluye conflict_cols
├── model/model.py          # Model.insert usa execute_insert (sin last_id post-hoc)
├── migration.py            # _apply usa execute_insert (cierra el residual Oracle)
├── sqlite.py / mysql.py / mariadb.py / postgresql.py / mssql.py / oracle.py
│                           # execute_insert + _last_id_value por motor
tests/
├── test_pool_characterization.py   # inversiones POOL-02/03/04/06 + nuevas de 04/05
├── test_pool.py                    # reset_on_release, close idempotente, standalone commit
└── conftest.py                     # (opcional) EventBarrier compartida
```

### Pattern 1: Reserva-antes-de-await en `acquire()`
**What:** incrementar `_size` (reservar el cupo) **antes** del `await`, y deshacer la reserva si la creación falla.
**When to use:** siempre, en la rama de crecimiento; la rama `get_nowait()` no reserva.
**Example:**
```python
# Source: pool.py:136-171 (defecto) + ROADMAP 04-01.
async def acquire(self, timeout=None) -> PooledConnection:
    if self._closed:
        raise ConnectionError("Pool cerrado")
    self._reap()
    while True:
        try:
            conn = self._idle.get_nowait()
        except asyncio.QueueEmpty:
            if self._size < self._max_size:
                self._size += 1              # reserva ANTES del await
                try:
                    conn = await self._create_connection()
                except BaseException:
                    self._size -= 1          # el cupo vuelve al pool
                    raise
                self._checked_out.add(conn)
                return conn
            ...  # esperar en la cola o PoolExhaustedError con timeout
        else:
            if conn.is_stale() and not await conn.driver.is_alive():
                await self._discard(conn)    # _size -= 1; driver.close()
                continue
            self._checked_out.add(conn)
            return conn
```

### Pattern 2: Captura del id dentro de la sentencia (opt-in)
**What:** `Db.insert(..., returning="id")` marca el `Query` y el motor añade su cláusula de captura; `execute_insert` devuelve el id.
**When to use:** solo cuando el llamador necesita el id (`Model.insert` con PK auto, `migration.py::_apply`). Por defecto `returning=None` → SQL byte-idéntico al actual.
**Example:**
```python
# Source: builders.py:101-146 + sondas verificadas contra los 6 contenedores.
# PostgreSQL  : sql += " RETURNING id"                  -> fetchrow(...)[ "id" ]
# MSSQL       : sql += " OUTPUT INSERTED.id"            -> fetchone()[0]   (rowcount = -1)
# Oracle      : sql += " RETURNING id INTO :ret_id"     -> cursor.var(NUMBER) out
# SQLite/MySQL: SIN cambio de SQL                       -> cursor.lastrowid
def build_insert(table, data, *, strategy, ..., returning=None) -> Query:
    ...
    if returning and strategy.kind == "suffix":        # PostgreSQL
        sql += f" RETURNING {check_identifier(returning, 'columna de retorno')}"
    elif returning and strategy.kind == "merge" and strategy.output_inserted:  # MSSQL
        sql += f" OUTPUT INSERTED.{check_identifier(returning, 'columna de retorno')}"
    elif returning and strategy.returning_id:          # Oracle (plain INSERT)
        sql += f" RETURNING {col} INTO :ret_id"
    return Query(sql, values, ..., returns_id=bool(returning), id_column=returning)
```

### Pattern 3: Reset explícito en `release()` con política
**What:** `execute`/`_run` cierran la transacción (commit en éxito, rollback en error) **antes** de liberar; `release()` aplica la política al sobrante.
**When to use:** siempre. El default es `"rollback"`.
**Example:**
```python
# Source: pool.py:231-244/273-286 (commit implícito) + Correction #5.
async def _run(self, method, *args):
    handle = _current_connection.get()
    if handle is not None:
        return await getattr(handle.driver, method)(*args)
    handle = await self.acquire()
    try:
        result = await getattr(handle.driver, method)(*args)
    except BaseException:
        if await handle.driver.in_transaction():
            await handle.driver.rollback()     # explícito, no en release()
        raise
    else:
        if await handle.driver.in_transaction():
            await handle.driver.commit()       # explícito, no en release()
        return result
    finally:
        await self.release(handle)

async def release(self, conn):
    handle = self._as_handle(conn)
    if handle not in self._checked_out:        # doble release: ignorar
        logger.warning("release() de una conexión que no está en uso: %r", handle)
        return
    self._checked_out.discard(handle)
    if await handle.driver.in_transaction():
        if self._reset_on_release == "commit":
            await handle.driver.commit()
        else:
            await handle.driver.rollback()
    handle.touch()
    self._reap()
    if self._closed:
        await handle.driver.close()
    else:
        await self._idle.put(handle)
```

### Pattern 4: Reaper perezoso (sin daemon)
**What:** `_reap()` se invoca al **entrar** en `acquire()` y al **salir** de `release()`; solo saca de la cola de ociosas y solo por encima de `min_size`.
**When to use:** siempre; es idempotente y O(ociosas).
**Example:**
```python
# Source: pool.py:128-134 (hoy solo chequea liveness al adquirir) + ROADMAP 04-04.
def _reap(self):
    if self._idle_timeout is None:
        return
    keep = []
    while True:
        try:
            conn = self._idle.get_nowait()
        except asyncio.QueueEmpty:
            break
        if self._size > self._min_size and conn.is_idle_for(self._idle_timeout):
            self._size -= 1
            self._connections.discard(conn)
            keep.append(conn)          # cerrar FUERA del bucle (await)
        else:
            self._idle.put_nowait(conn)
    for conn in keep:
        await conn.driver.close()      # o programar; ver Open Question sobre el await
```

### Anti-Patterns to Avoid
- **Poner `RETURNING`/`OUTPUT` incondicional en `build_insert`:** rompe `transfer.py` y cualquier insert sobre tablas sin `id` (verificado: `UndefinedColumnError`, ORA-00904). Debe ser opt-in.
- **Guardar el id en `PoolDb._last_id`:** es el cache compartido entre tareas que POOL-03 elimina (`pool.py:69,281,304`).
- **Commitear dentro de `release()` como único mecanismo:** si se invierte el orden de Correction #5, un `pool.execute(INSERT)` standalone (o un `_run`) deja la escritura sin commit y `release()` la revierte → pérdida silenciosa.
- **Aplicar `reset_on_release` a cualquier `in_transaction()` sin distinguir lectura de escritura:** en MSSQL/Oracle `in_transaction()` devuelve `_in_tx`, que se pone a `True` también en `fetch_all`/`fetch_one`/`fetch_many` (`mssql.py:274,289,309`; `oracle.py:258` en `execute`). Un `DeprecationWarning` disparado por cada SELECT haría estallar `filterwarnings=["error"]`.
- **Que `_current_connection` guarde el handle sin desenvainar en `resolve_db()`:** `Model` llama `.insert/.execute/.last_id` sobre lo que devuelve `resolve_db()` (`model/model.py:533-542`) y `engine_of` lee `.dialect` (`engine.py:35-43`).
- **Cerrar en `close()` lo que está en `_checked_out`:** es exactamente el defecto caracterizado (`test_pool_characterization.py:368-376`).
- **Usar `asyncio.Barrier`/`TaskGroup`/`asyncio.timeout` en los tests:** piso 3.10 (Correction #4); el fichero ya prohíbe esos substrings (`01-05-SUMMARY.md:130`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Captura del id en PostgreSQL | `SELECT lastval()` / `currval(pg_get_serial_sequence(...))` / un `SELECT MAX(id)` | `INSERT ... RETURNING <pk>` | `lastval()` es session-scoped (Correction #1); `currval` falla si un trigger avanza la misma secuencia; `MAX(id)` es una carrera. `RETURNING` es exacto y atómico. |
| Captura del id en MSSQL | `@@IDENTITY` | `OUTPUT INSERTED.<pk>` en el mismo statement | `@@IDENTITY` es session-scoped y contaminable por triggers; `SCOPE_IDENTITY()` en un `execute` separado devuelve **NULL** (verificado). |
| Captura del id en SQLite/MySQL | `SELECT last_insert_rowid()` / una consulta extra | `cursor.lastrowid` inmediatamente tras el INSERT | Ya es el mecanismo de MySQL (`mysql.py:196`); aiosqlite lo expone (verificado: `1`, `2`). |
| Captura del id en Oracle | Reconstruir el id con `MAX(id)` o un `SELECT` | `RETURNING <pk> INTO :ret_id` (ya existe) | Es el mecanismo nativo; el código actual ya lo implementa (`oracle.py:245-262`). |
| Barrera determinista | `asyncio.Barrier` / `time.sleep` / `asyncio.wait_for` sobre un sleep | `EventBarrier` con `asyncio.Event` (liberación en la última llegada) | Ya existe y está probada (`test_pool_characterization.py:126-144`); no depende de temporizadores → no es flaky. |
| Detección de conexión ociosa | Un `asyncio.Task` daemon con `sleep` periódico | Reaper perezoso invocado en `acquire`/`release` | Sin daemon que cancelar en `close()`; determinista y testeable con `monkeypatch` de `time.monotonic`. |
| Dedupe de doble `release()` | Confiar en que el llamador no lo haga | Conjunto `_checked_out` + generación | El doble release está caracterizado como defecto (`test_pool_characterization.py:326-339`). |

**Key insight:** el trabajo hecho a mano que hay que evitar en este dominio es **la captura diferida del id**. `last_id()` post-hoc *parece* correcto porque en un test secuencial lo es; en cuanto hay dos tareas o un trigger, devuelve el id de otra fila sin lanzar ningún error. La defensa es que el id salga **de la misma sentencia** que lo produjo y que el pool no tenga un cache global de id.

## Runtime State Inventory

> Fase de **refactor con cambio de contrato público**: aplica el inventario. No es un rename, pero sí cambia el estado en runtime de procesos vivos y de artefactos versionados.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Ninguno — el pool no persiste estado; `_last_id`/`_last_used` viven en memoria del proceso. | Ninguna migración de datos. |
| Live service config | Ninguno — el pool es por proceso; no hay configuración externa que embeba nombres de estado. | Ninguna. |
| OS-registered state | Ninguno — no hay tareas programadas ni servicios. | Ninguna. |
| Secrets/env vars | Ninguno — `PoolDb.__init__` recibe kwargs de conexión; no hay variables de entorno del pool (las `ENCINO_ORM_*` son de tests y no cambian). | Ninguna. |
| Build artifacts | `uv.lock` debe regenerarse (2 dev deps nuevas); CI `deps` corre `uv lock --check` (`ci.yml:222-225`). `.venv` local queda desactualizado hasta `uv sync`. | `uv lock` + `uv sync` en el mismo commit que `pyproject.toml`. |
| Artefactos de test versionados | `tests/__snapshots__/test_sql_snapshots.ambr` pinea el SQL de Oracle con `RETURNING id INTO :ret_id` (`:85`, `:128`) y los renders `MERGE`; `tests/test_dialect_builders.py:180,191,489` pinea golden strings. | Regenerar con `--snapshot-update` y **revisar el diff visiblemente** (mismo criterio que 02-08). |
| Configuración de gates | `pyproject.toml`: `[[tool.mypy.overrides]]` excluye `encino_orm.pool` con 5 errores (`:236`) y dice que se limpia en Fase 4; `[tool.ruff.lint.per-file-ignores]` ignora `PT011, B017` en `tests/**` "se levantan en Fase 4" (`:127-131`); `encino_orm/pool.py` ignora `PERF203` (`:165`). | Quitar la entrada `encino_orm.pool` del ratchet mypy si queda limpio; levantar `PT011`/`B017` en tests (6 `pytest.raises(Exception)` y ~141 `pytest.raises` sin `match=`); reevaluar el `PERF203` de pool.py. |
| Documentación | `docs/engines.md:133-137` documenta el contrato `last_id()` antiguo; `docs/guide.md` menciona `PoolDb` (`:190`). | Actualizar al nuevo contrato (`execute_insert` + `reset_on_release`). |

**Canonical question:** *después de cambiar el código, ¿qué sistemas en runtime siguen con el estado viejo?* → Ninguno en runtime (el pool es efímero). Lo que sobrevive son los **artefactos versionados** que pinean el SQL y el contrato: snapshots `.ambr`, golden strings de `test_dialect_builders.py`, el ratchet de mypy y los `per-file-ignores` de ruff.

## Common Pitfalls

### Pitfall 1: Invertir el orden de POOL-04 → pérdida silenciosa de escrituras
**What goes wrong:** se cambia `release()` a "rollback por defecto" antes de hacer explícito el commit en `execute`/`_run`. Cada `pool.execute(INSERT)` standalone (y cada `_run("columns_of")` que escriba) se revierte al liberar; el usuario cree que escribió.
**Why it happens:** hoy el commit vive en `_run`/`execute` (`pool.py:242-243`, `:284-285`) y `release()` no toca la transacción; al "mover" la responsabilidad a `release()` se elimina el único commit que había.
**How to avoid:** seguir el orden de Correction #5: (i) commit/rollback explícito en `execute`/`_run`; (ii) `reset_on_release` en `release()`; (iii) `TestPoolAutocommit` (`test_pool.py:311-329`) y `TestPoolStandaloneCommit` (`test_pool.py:221-232`) verdes.
**Warning signs:** `test_dml_visible_across_connections` pasa a ver 0 filas; el `_in_tx` de MSSQL/Oracle queda `True` tras `release()`.

### Pitfall 2: `filterwarnings = ["error"]` convierte el `DeprecationWarning` en fallo de suite
**What goes wrong:** se añade el warning de `last_id()` y **toda** llamada existente (29 en tests, 2 internas en librería) tumba la suite; además `migration.py:107` (librería) se auto-deprecaría.
**Why it happens:** `pyproject.toml:62` pone `filterwarnings = ["error"]` con allowlist vacía.
**How to avoid:** migrar **primero** los llamadores internos (`model/model.py:542`, `migration.py:107`) a `execute_insert`; después añadir el warning; y en tests envolver las aserciones legadas en `pytest.warns(DeprecationWarning)` (o migrarlas). No añadir una entrada a la allowlist sin justificación escrita.
**Warning signs:** `DeprecationWarning: last_id() está deprecado` en el resumen de fallos de pytest; un `pytest.warns` que no captura nada.

### Pitfall 3: `RETURNING id` incondicional rompe inserts legítimos
**What goes wrong:** se añade `RETURNING id` a todo `build_insert` y `transfer.py:157` (copia de tablas arbitrarias) o un `db.insert` directo sobre una tabla sin `id` falla.
**Why it happens:** `id` es el nombre de PK por defecto (`model/model.py:156`), pero el builder es genérico.
**How to avoid:** `returning=<col>` opt-in, por defecto `None`; `Model.insert` lo pasa solo si `_is_auto_pk()` (`model.py:510,287-289`).
**Warning signs:** `UndefinedColumnError: column "id" does not exist` (PG) / `ORA-00904: "ID": invalid identifier` (Oracle) en tests de `transfer` o de inserción cruda. **Ambos reproducidos en las sondas.**

### Pitfall 4: `reset_on_release` disparando sobre lecturas en MSSQL/Oracle
**What goes wrong:** `in_transaction()` en MSSQL/Oracle devuelve un flag de instancia `_in_tx` que se pone a `True` en `execute`, `fetch_all`, `fetch_one` y `fetch_many` (`mssql.py:252,274,289,309`; `oracle.py:258`). Un `release()` que "detecta transacción sobrante" tras un simple SELECT dispara rollback (inocuo) y, si además emite `DeprecationWarning`, rompe la suite bajo `filterwarnings=["error"]`.
**Why it happens:** el flag modela "hay una transacción abierta", no "hay una escritura sin confirmar".
**How to avoid:** enganchar el `DeprecationWarning` a la política `reset_on_release="commit"` (el comportamiento viejo que se deprecia), no a la mera presencia de `in_transaction()`. Documentar que el rollback de una lectura es inocuo.
**Warning signs:** warnings masivos en `test_mssql.py`/`test_oracle.py` tras un `fetch_*`.

### Pitfall 5: `SCOPE_IDENTITY()` en un `execute` separado devuelve NULL
**What goes wrong:** se sustituye `@@IDENTITY` por `SELECT SCOPE_IDENTITY()` en el mismo patrón de dos statements y el id pasa a ser 0/NULL en todos los inserts.
**Why it happens:** `SCOPE_IDENTITY()` es por **scope** (batch); dos `cursor.execute` son dos batches distintos. **Verificado**: `SCOPE_IDENTITY()` → `(None,)` mientras `@@IDENTITY` → `(3,)` en el mismo cursor.
**How to avoid:** usar `OUTPUT INSERTED.<pk>` dentro del propio INSERT (verificado: devuelve `(1,)` y `[(4,)]` con MERGE) y asumir `cursor.rowcount == -1` en ese statement.
**Warning signs:** `last_id()==0` en MSSQL tras un insert exitoso.

### Pitfall 6: `MERGE ... RETURNING` no existe en Oracle
**What goes wrong:** se promete que `Model.insert(replace=True)` en Oracle devuelve el id tras arreglar ORA-38104; no es posible.
**Why it happens:** Oracle rechaza `RETURNING ... INTO` tras un `MERGE` con `ORA-00933: SQL command not properly ended` (**verificado** contra el contenedor).
**How to avoid:** mantener el contrato "MERGE no expone id" (`model/model.py:540-541`) también para Oracle; el fix de ORA-38104 solo garantiza **ejecutabilidad**. Documentarlo en CHANGELOG y en el docstring de `Model.insert`.
**Warning signs:** un test que espera `insert(replace=True) > 0` en Oracle.

### Pitfall 7: La barrera de `parties` mal ajustado cuelga el test para siempre
**What goes wrong:** un test de carrera crea N tareas pero `EventBarrier(parties=M)` con M≠N; la barrera nunca se libera y el test cuelga (no falla) → CI consume el `timeout-minutes: 15` del job (`ci.yml:22`).
**Why it happens:** la barrera libera en la última llegada y no tiene temporizador (a propósito, `test_pool_characterization.py:140-144`).
**How to avoid:** `@pytest.mark.timeout(N)` en cada test de barrera + método *signal* en CI. El fichero de caracterización ya documenta el requisito de igualdad (`:215-217`).
**Warning signs:** pytest sin salida durante minutos; en Windows el método *thread* mata el proceso y **pierde el JUnit XML** (verificado), con lo que `check_skips.py` falla de forma confusa.

### Pitfall 8: El handle en el contextvar rompe `Model` si no se desenvaina
**What goes wrong:** `_current_connection.set(handle)` y `resolve_db()` devuelve el handle; `Model.insert` llama `handle.insert(...)`/`handle.execute(...)`/`handle.last_id()` (`model/model.py:533-542`) y `engine_of(handle)` lee `handle.dialect` (`engine.py:35-43`).
**Why it happens:** hoy el contextvar guarda un `Db` (`pool.py:29,190`) y `resolve_db` lo devuelve tal cual (`context.py:49-53`).
**How to avoid:** `resolve_db()` devuelve `handle.driver`; los tests que inspeccionan `_current_connection.get()` deben actualizarse.
**Warning signs:** `AttributeError: 'PooledConnection' object has no attribute 'insert'`; `ValueError: 'PooledConnection' is not a valid Engine`.

### Pitfall 9: El ratchet de gates (mypy/ruff/coverage) bloquea el merge
**What goes wrong:** el refactor de `pool.py` deja el ratchet de mypy desactualizado (la entrada `encino_orm.pool` sigue excluida con `ignore_errors = true`, `pyproject.toml:230-239`) y `PT011`/`B017` siguen ignorados en tests (`:127-131`) pese a que la fase está declarada como la que los levanta.
**Why it happens:** los gates son bloqueantes y el comentario de `pyproject.toml` asigna explícitamente esas limpiezas a la Fase 4.
**How to avoid:** en el plan de cierre, quitar la entrada `encino_orm.pool` si `uv run mypy encino_orm` sale limpio, y evaluar levantar `PT011`/`B017` (6 `pytest.raises(Exception)` + ~141 `pytest.raises` sin `match=`; un cambio mecánico grande — decisión de alcance en Open Questions).
**Warning signs:** `mypy` verde pero `pyproject.toml` aún excluye el módulo (deuda que crece); o un PR que levanta `PT011` y produce un diff de 141 asserts.

### Pitfall 10: Añadir dev deps sin regenerar el lock
**What goes wrong:** se edita `pyproject.toml` y no se corre `uv lock`; el job `deps` falla en `uv lock --check` (`ci.yml:222-225`).
**Why it happens:** el lock es un artefacto versionado y CI lo verifica.
**How to avoid:** `uv add --dev` (regenera el lock) en el mismo commit.
**Warning signs:** `uv lock --check` no-verde.

## Code Examples

### Estado actual del pool, anclado (para el planner)
```python
# pool.py:65-71  — estado del pool (a repartir en PooledConnection)
self._pool = asyncio.Queue()      # ociosas
self._connections = set()         # TODAS las vivas (incluidas en uso)
self._size = 0
self._connected = False
self._last_id = 0                 # <-- cache COMPARTIDO entre tareas (POOL-03)
self._last_used = {}              # dict keyed por Db
self._stats = {...}

# pool.py:143-149 — LA CARRERA (POOL-02)
if self._size < self._max_size:
    db = await self._create_connection()   # <-- await point
    self._connections.add(db)
    self._size += 1                        # <-- después del await
    self._last_used[db] = time.monotonic()
    self._stats["acquires"] += 1
    return db

# pool.py:173-175 — release accidental (POOL-04/06)
async def release(self, db: Db):
    self._last_used[db] = time.monotonic()
    await self._pool.put(db)               # sin ownership, sin reset, sin dedupe

# pool.py:181-182 — close() cierra lo retenido (POOL-06)
for db in list(self._connections):
    await db.close()

# pool.py:280-281 — cache de id a nivel de pool (POOL-03)
if qry.sql_template.lstrip().upper().startswith(("INSERT", "REPLACE")):
    self._last_id = await db.last_id()
```

### Mecanismo de id por motor — estado actual y objetivo (verificado)
```python
# SQLite  sqlite.py:217-222   SELECT last_insert_rowid()      -> cursor.lastrowid inmediato
#         (verificado: aiosqlite cursor.lastrowid == 1, luego 2)
# MySQL   mysql.py:196,246    cursor.lastrowid                -> cursor.lastrowid (ya correcto)
#         (verificado: INSERT -> 1; ON DUPLICATE KEY sin fila nueva -> 0; REPLACE -> nuevo id)
# PG      postgresql.py:232   SELECT lastval()  [SESSION]     -> INSERT ... RETURNING id
#         (verificado: fetchrow("INSERT ... RETURNING id") -> {'id': 2}; RETURNING id sin columna -> UndefinedColumnError)
# MSSQL   mssql.py:254-257    SELECT @@IDENTITY  [SESSION]    -> OUTPUT INSERTED.id (rowcount = -1)
#         (verificado: OUTPUT -> (1,); SCOPE_IDENTITY() en statement aparte -> (None,); @@IDENTITY -> (3,))
# Oracle  oracle.py:245-262   RETURNING id INTO :ret_id       -> ya correcto (opt-in)
#         (verificado: last_id -> 1; RETURNING id sin columna -> ORA-00904; MERGE RETURNING -> ORA-00933 NO soportado)
```

### ORA-38104: reproducción y fix
```python
# builders.py:137-138 — el SET actualiza la MISMA columna del ON (defecto)
conflict_cols = list(conflict) if conflict else ([columns[0]] if columns else ["id"])
set_sql = ", ".join(f"dst.{c} = src.{c}" for c in columns)   # <-- incluye conflict_cols

# Fix (mismo patrón que build_upsert con update_cols, builders.py:242-254):
update_cols = [c for c in columns if c not in conflict_cols]
if not update_cols:
    raise ValueError("MERGE sin columnas actualizables: todas las del INSERT son de conflicto")
set_sql = ", ".join(f"dst.{c} = src.{c}" for c in update_cols)

# Verificado contra el contenedor Oracle:
#   SET dst.y = src.y              (sin la columna del ON) -> OK
#   SET dst.x = src.x, dst.y = ... (con la columna del ON) -> ORA-38104: Columns referenced
#                                                             in the ON Clause cannot be updated
```

### Barrera determinista 3.10 (reutilizable)
```python
# Source: tests/test_pool_characterization.py:126-144 (ya probada; extraer a helper si se reutiliza).
class EventBarrier:
    def __init__(self, parties: int):
        self._parties, self._arrived = parties, 0
        self._event = asyncio.Event()

    async def wait(self):
        self._arrived += 1
        if self._arrived >= self._parties:
            self._event.set()
        await self._event.wait()
```

### Configuración de pytest-timeout/repeat (propuesta)
```toml
# pyproject.toml [tool.pytest.ini_options]
# `timeout` global 0 (desactivado): el job engine-heavy (Oracle 60-120s) no debe morir por un global.
# El timeout se aplica por marker SOLO a los tests de barrera.
markers = [
    "integration: ...",
    "optional_engine: ...",
    "concurrency: tests de pool/carreras; se excluyen de corridas con xdist",
    "benchmark: ...",
    "stress: variante de estrés con pytest-repeat; se corre con --count=N",
]
```
```python
@pytest.mark.concurrency
@pytest.mark.timeout(10)          # registrado por el plugin; --strict-markers no falla
async def test_no_overshoot_under_barrier(...): ...

@pytest.mark.stress
@pytest.mark.repeat(5)
async def test_no_overshoot_repeated(...): ...
```
```bash
# CI Linux: el método signal permite que la corrida continúe tras el timeout.
uv run pytest -q -m "not optional_engine" --timeout-method=signal --junitxml=junit.xml
# Soak local (opcional): uv run pytest -m stress --count=100
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `acquire()` comprueba `_size < max_size` y luego `await` | Reserva `_size` antes del `await`; devuelve el cupo si la creación falla | Fase 4 (POOL-02) | `_size <= max_size` bajo concurrencia (hoy 5 sobre 2). |
| `last_id` en cache de pool + `lastval()`/`@@IDENTITY` | Captura dentro de la sentencia (`RETURNING`/`OUTPUT`/`lastrowid`/`RETURNING INTO`), id por conexión/tarea | Fase 4 (POOL-03) | El id pertenece a su insert; sin cruce entre tareas; `last_id()` deprecado. |
| `release()` no toca la transacción; el commit está en `_run`/`execute` | `execute`/`_run` commitean o revierten explícitamente; `release()` aplica `reset_on_release` (rollback por defecto) | Fase 4 (POOL-04) | Sin transacciones sobrantes ni escrituras perdidas; semántica explícita. |
| Solo `_needs_check` de liveness al adquirir | Contador de generación + reaper perezoso que cierra ociosas por encima de `min_size` | Fase 4 (POOL-05) | Las conexiones ociosas se cierran de verdad, no solo se reemplazan. |
| `close()` cierra todo, incluidas las retenidas | `close()` idempotente que solo cierra ociosas; las en uso se cierran al liberarse | Fase 4 (POOL-06) | `close()` deja de romper a un llamador activo. |
| `@@IDENTITY` / `lastval()` / `RETURNING` incondicional en Oracle | `OUTPUT INSERTED` / `RETURNING <pk>` opt-in | Fase 4 (POOL-03) | Ids correctos con triggers; inserts sobre tablas sin `id` dejan de romperse. |
| `MERGE` con `SET` de la columna del `ON` | `SET` excluye `conflict_cols` | Fase 4 (POOL-03) | `Model.insert(replace=True)` ejecutable en Oracle (sin id: `MERGE RETURNING` no existe allí). |

**Deprecated/outdated:**
- `Db.last_id()` / `PoolDb.last_id()`: pasan a deprecados con `DeprecationWarning`; el reemplazo es `Db.execute_insert(qry)` (o el retorno de `Model.insert`).
- `PoolDb._last_id`: eliminado (cache compartido entre tareas).
- El commit implícito de `_run`/`execute` sin rama de error: sustituido por commit/rollback explícito.
- `docs/engines.md:133-137` ("usa el mecanismo nativo `lastval()`…"): obsoleto para PostgreSQL.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | El `DeprecationWarning` de POOL-04 se engancha a la política `reset_on_release="commit"` (comportamiento viejo deprecado) y NO a la mera presencia de `in_transaction()` al liberar. | Pitfall 4, §5 | **Medio-alto:** si el usuario esperaba un warning por "sobrante de transacción", el contrato no coincide; y engancharlo a `in_transaction()` rompería la suite (MSSQL/Oracle marcan `_in_tx=True` tras un SELECT). Confirmar. |
| A2 | `reset_on_release` admite exactamente `"rollback"` (default) y `"commit"`; no se expone `"none"`. | Standard Stack / §5 | Bajo: `"none"` es el comportamiento accidental que la fase elimina; si el usuario lo quiere, es aditivo. |
| A3 | `_current_connection` pasa a guardar el handle `PooledConnection` y `resolve_db()` desenvaina `.driver`. | §2 / Pitfall 8 | Medio: alternativa es guardar el driver y mantener un mapa paralelo handle↔driver (más frágil); o hacer del handle un proxy de `Db` (mucha superficie). |
| A4 | `MERGE` en Oracle **no puede** devolver el id (`MERGE ... RETURNING` → ORA-00933, verificado en el contenedor local). | Pitfall 6 / §4 | Medio: si el motor del usuario (Oracle 23ai+) sí lo soporta, se podría capturar; el contrato "MERGE devuelve 0" es conservador y documentado. **Verificar en la versión objetivo antes de prometer lo contrario.** |
| A5 | El método *signal* de `pytest-timeout` interrumpe correctamente un `await` colgado de `pytest-asyncio` en Linux CI. | §8 | Medio: verificado solo el método *thread* (Windows, mata el proceso). El *signal* no se pudo probar en este host Windows. Mitigación: si fallara, el *thread* sigue matando el proceso (JUnit XML perdido → gate confuso). |
| A6 | El contador de generación se asigna por conexión desde un contador del pool y se incrementa en `close()`/`reap()`; `release()` cierra en vez de reencolar los handles de generación antigua. | §6 | Bajo-medio: es una semántica inventada para POOL-05; el requisito solo dice "contador de generación". Cualquier semántica equivalente es válida si es testeable. |
| A7 | El `id` de retorno es la columna `"id"` (nombre de PK por defecto, `model/model.py:156`) y `Model.insert` solo pide `returning` si `_is_auto_pk()` (`:287-289`). | §4 | Bajo: coherente con el `id` hardcodeado que ya usan `builders.py:145` y `mssql.py:255`; los modelos con PK natural no necesitan id. |
| A8 | Levantar `PT011`/`B017` en `tests/**` (declarado para Fase 4 en `pyproject.toml:127-131`) entra en el alcance de esta fase. | Pitfall 9 | Medio: son ~147 asserts; si se levanta, el diff es grande y mecánico; si se difiere, queda deuda declarada. Decisión de alcance. |

**If this table is empty:** no aplica; hay 8 supuestos que requieren confirmación o documentación explícita.

## Open Questions

> **Estado:** todas resueltas por el planificador (2026-09-18) e incorporadas a los planes `04-01`…`04-06`. Cada pregunta lleva su resolución inline.

1. **(RESOLVED) Forma final del handle y del contextvar (POOL-01).**
   - What we know: `_current_connection` hoy guarda un `Db` (`pool.py:29,190`); `resolve_db()` lo devuelve tal cual (`context.py:49-53`); `Model` lo usa como `Db` (`model/model.py:533-542`) y `engine_of` lee `.dialect` (`engine.py:35-43`).
   - What's unclear: si el handle debe ser un value object puro (recomendado) y `resolve_db` desenvaina, o un proxy de `Db`.
   - Recommendation: **dataclass `PooledConnection`** con `driver`, `last_id`, `last_used`, `generation`, `checked_out`, `owner_task`; `_current_connection` guarda el handle; `resolve_db()` devuelve `handle.driver`. Tests que inspeccionan `_current_connection.get()` se actualizan.
   - **RESUELTO:** dataclass `PooledConnection` NO `frozen` (el handle se muta), `_current_connection` guarda el handle y `resolve_db()` devuelve `handle.driver`. Implementado en `04-01` (Tasks 1/3); el proxy de `Db` se descarta (exigiría reimplementar ~15 métodos).

2. **(RESOLVED) ¿`session()` debe fijar `_current_connection`?**
   - What we know: `session()` (`pool.py:321-352`) adquiere, hace `bind(conn)` (`:339`) y libera; **no** fija `_current_connection`. Por eso `pool.execute(q)` dentro de un `async with session(pool)` **adquiere otra conexión** en vez de usar la de la sesión (el patrón documentado usa `conn.execute`, `:332`).
   - What's unclear: si POOL-01 debe corregir esa asimetría (intuitiva) o si es un cambio de comportamiento fuera de alcance.
   - Recommendation: corregirlo (fijar `_current_connection` al handle de la sesión) **solo si** el usuario lo confirma; es un cambio de comportamiento observable. Documentarlo en CHANGELOG si se hace.
   - **RESUELTO:** NO se fija `_current_connection` en `session()` (cambio observable no confirmado; no hay `04-CONTEXT.md` que lo autorice). `session()` sí ata `handle.driver` (no el handle) y cede el driver, para no romper `resolve_db()`/`Model`. Decidido en `04-01` Task 3 y registrado en su SUMMARY.

3. **(RESOLVED) ¿Qué se hace con `last_id()` fuera de una transacción?**
   - What we know: hoy devuelve el cache del pool (`pool.py:304`), que es el defecto. `test_d_recommendations.py:74-81` fija el comportamiento standalone (`assert await pool.last_id() == 1`, luego `2`).
   - What's unclear: si tras deprecarlo debe devolver `0` (sin id atribuible) o el valor de la conexión si aún se mantiene.
   - Recommendation: `0` + `DeprecationWarning` fuera de transacción; actualizar `test_d_recommendations.py` para usar `execute_insert` y asertar el id devuelto (es un test de la feature D3, no de la implementación del pool).
   - **RESUELTO:** fuera de `transaction()` devuelve `0` (sin cache de pool ni cruce entre tareas) y emite `DeprecationWarning`; dentro, lee `_last_id_value()` del driver retenido. `04-01` Task 3 cambia el scoping y `04-02` Tasks 2/3 migran `test_d_recommendations.py` a `execute_insert` y añaden el warning. Se mantiene el orden safety-critical (B2): el warning se habilita en `04-02` Task 3.

4. **(RESOLVED) Alcance de los gates de ruff (`PT011`/`B017`) y mypy.**
   - What we know: `pyproject.toml:127-131` asigna la limpieza a Fase 4; `:230-239` excluye `encino_orm.pool` con 5 errores "se limpia en Fase 4 (POOL-01…06)".
   - What's unclear: si levantar `PT011`/`B017` en todo `tests/**` (147 asserts) cabe en la fase.
   - Recommendation: **sí** quitar `encino_orm.pool` del ratchet mypy (obligatorio: el módulo se reescribe); **evaluar** levantar `PT011`/`B017` y, si el diff es inabarcable, dejar constancia escrita de por qué se difiere (el repo exige justificación para tocar gates).
   - **RESUELTO:** `04-04` Task 3 RETIRA la entrada `encino_orm.pool` del ratchet de mypy (si `uv run mypy encino_orm` queda limpio) y DIFIERE `PT011`/`B017` con justificación escrita en el propio comentario de `pyproject.toml` (≈147 asserts ajenos al alcance de POOL-01…07; levantarlos produciría un diff mecánico inabarcable). No se difiere en silencio.

5. **(RESOLVED) ¿Piso de cobertura para `pool.py`?**
   - What we know: `tools/ci/check_coverage_floors.py` falla cerrado si el módulo no aparece; hoy no hay pisos de adaptador.
   - Recommendation: **no** añadirlo en esta fase; el fichero de tests de pool crecerá y un piso mal calibrado bloquea CI. Reconsiderar tras un run verde con margen.
   - **RESUELTO:** NO se añade piso de cobertura para `pool.py` en esta fase. Decisión registrada en `04-04` Task 3 y en su SUMMARY.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Todo | ✓ | 3.10.18 local (CI 3.10–3.13) | — |
| `uv` | Tests, gates, lock | ✓ | 0.12.15 (mismo pin que CI) | — |
| `pytest` / `pytest-asyncio` | Tests | ✓ | 9.1.1 / 1.4.0 | — |
| `pytest-timeout` | POOL-07 (matar barreras colgadas) | ✗ (no instalado) | — | **Instalar `2.4.0`** (verificado en venv aislado) o el test de barrera cuelga sin límite |
| `pytest-repeat` | POOL-07 (estrés) | ✗ (no instalado) | — | **Instalar `0.9.4`**; sin él la variante de estrés no existe (marker inerte) |
| `coverage` / `syrupy` / `ruff` / `mypy` | Gates de CI | ✓ vía `uv run` | 7.16.1 / 6.1.1 (pin) / 0.16.8 (pin) / 2.3.1 | — |
| Docker + 6 contenedores | Verificación multi-motor | ✓ (los 6 corriendo) | MySQL 8.0, MariaDB 11, PostgreSQL 16, MSSQL 2022, Oracle, Redis | SQLite `:memory:` siempre disponible; `engine_unavailable()` omite en local y falla en CI con `ENCINO_ORM_REQUIRE_ENGINES` |
| `slopcheck` | Gate de legitimidad de paquetes | ✗ | — | No disponible → los 2 paquetes nuevos quedan `[ASSUMED]` + `checkpoint:human-verify` |

**Missing dependencies with no fallback:** ninguna que bloquee (las dos dev deps tienen plan de instalación verificado).
**Missing dependencies with fallback:** `slopcheck` (no hay sustituto; se aplica la degradación segura).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) + **pytest-timeout 2.4.0** + **pytest-repeat 0.9.4** |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`markers` + `stress`, `filterwarnings=["error"]`, `xfail_strict=true`, `addopts="-ra --strict-markers"`) |
| Quick run command | `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q` |
| Full suite command | `uv run pytest -q` (6 contenedores locales); en CI `uv run pytest -q -m "not optional_engine" --timeout-method=signal` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POOL-01 | El estado por conexión vive en el handle; `release()` conoce la propiedad de tarea | unit (fake `Db`) | `uv run pytest tests/test_pool_characterization.py -k handle -x` | ❌ Wave 0 |
| POOL-02 | 5 tareas / `max_size=2` → `_size <= 2` (invierte `test_concurrent_acquire_overshoots_max_size:227-228`) | concurrency (barrera) | `uv run pytest tests/test_pool_characterization.py -k overshoot -x` | ✅ (invertir) |
| POOL-02 | Doble `release()` no duplica la referencia en la cola (invierte `:339`) | unit | `uv run pytest tests/test_pool_characterization.py -k double_release -x` | ✅ (invertir) |
| POOL-03 | Inserts concurrentes devuelven cada uno su id (sin cruce entre tareas) | concurrency + integración SQLite | `uv run pytest tests/test_pool.py -k concurrent_insert_ids -x` | ❌ Wave 0 |
| POOL-03 | `last_id()` post-hoc emite `DeprecationWarning` | unit | `uv run pytest tests/test_pool_characterization.py -k deprecated -x` | ❌ Wave 0 |
| POOL-03 | Id por motor: SQLite/MySQL `lastrowid`, PG `RETURNING`, MSSQL `OUTPUT`, Oracle `RETURNING INTO` | integración (6 motores) | `uv run pytest tests/test_sqlite.py tests/test_mysql.py tests/test_mariadb.py tests/test_postgresql.py tests/test_mssql.py tests/test_oracle.py -k execute_insert -x` | ❌ Wave 0 (los `test_last_id_characterization` existentes se migran) |
| POOL-03 | `Model.insert(replace=True)` es ejecutable en Oracle (invierte `test_model_insert_replace_no_rompe_el_merge`, `test_oracle.py:301,371`) | integración Oracle | `uv run pytest tests/test_oracle.py -k insert_replace -x` | ✅ (invertir) |
| POOL-04 | `release()` con transacción abierta revierte por defecto; `reset_on_release="commit"` confirma (invierte `:309-310`) | unit (fake `Db`) | `uv run pytest tests/test_pool_characterization.py -k release_semantics -x` | ✅ (invertir) |
| POOL-04 | `pool.execute(INSERT)` standalone sigue commiteando y es visible entre conexiones | integración SQLite | `uv run pytest tests/test_pool.py -k standalone_operation_commits tests/test_pool.py -k dml_visible_across_connections` | ✅ (preservar) |
| POOL-05 | El reaper cierra ociosas por encima de `min_size`; `idle_timeout=None` no reap | unit (fake + `monkeypatch` de `time.monotonic`) | `uv run pytest tests/test_pool.py -k reap -x` | ❌ Wave 0 |
| POOL-05 | La generación detecta handles obsoletos (reaper/close) y evita reencolarlos | unit | `uv run pytest tests/test_pool.py -k generation -x` | ❌ Wave 0 |
| POOL-06 | `close()` no cierra una conexión retenida (invierte `:376`); segunda llamada no lanza; se cierra al liberarse | unit | `uv run pytest tests/test_pool_characterization.py -k close -x` | ✅ (invertir) |
| POOL-07 | Barrera determinista sin primitivas 3.11 + `pytest.mark.timeout` en cada test de barrera | concurrency | `uv run pytest -m concurrency -q --timeout-method=signal` | ✅ (extender) |
| POOL-07 | Variante de estrés `pytest-repeat` tras marker `stress` | stress | `uv run pytest -m stress --count=5 -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_pool.py tests/test_pool_characterization.py -q`
- **Per wave merge:** `uv run pytest -q` (6 motores locales)
- **Phase gate:** suite completa verde + `uv run ruff check encino_orm tests` + `uv run ruff format --check encino_orm tests` + `uv run mypy encino_orm` + `uv lock --check` + `check_skips.py` (0 skips) antes de `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_pool.py` — casos nuevos: `reset_on_release` (rollback/commit), reaper, generación, `close()` con conexión retenida, ids concurrentes. Fichero existente, casos nuevos.
- [ ] `tests/test_pool_characterization.py` — **invertir** las 6 aserciones de `01-05-SUMMARY.md:103-112` y **preservar** las de `:114`; eliminar las lecturas de `_last_id` del pool (`:248,260,272,275,280,282`).
- [ ] `tests/test_{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` — migrar `test_last_id_characterization`/`test_insert_execute_and_last_id` a `execute_insert`; invertir las de Oracle `insert(replace=True)`.
- [ ] `tests/conftest.py` (o `tests/_pool_helpers.py`) — extraer `EventBarrier` si se reutiliza en más de un fichero.
- [ ] `pyproject.toml` — markers `stress`; dev deps `pytest-timeout==2.4.0`/`pytest-repeat==0.9.4`; `uv lock`.
- [ ] `.github/workflows/ci.yml` — `--timeout-method=signal` en el job `test` (Linux) y, si aplica, en `engine-heavy`.
- [ ] `tests/__snapshots__/test_sql_snapshots.ambr` — regenerar por los cambios de SQL (Oracle `RETURNING` opt-in, MERGE `SET`).
- [ ] `docs/engines.md`, `docs/guide.md`, `CHANGELOG.md` — contrato nuevo (`execute_insert`, `reset_on_release`, deprecación de `last_id`, Oracle MERGE sin id).

## Security Domain

> `security_enforcement` no está desactivado en `.planning/config.json` (la clave no existe → habilitado). Se incluye.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | sí | El nuevo `returning=<col>` **debe** pasar por `check_identifier` antes de interpolarse en `RETURNING`/`OUTPUT INSERTED` (misma frontera de confianza que `dialects/builders.py:1-13`). El nombre de columna lo elige el llamador, no el usuario final, pero la regla del repo es no interpolar nunca sin validar. |
| V6 Cryptography | no | — |

### Known Threat Patterns for asyncio + multi-motor

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection por nombre de columna de retorno | Tampering | `check_identifier(returning, "columna de retorno")` antes de componer `RETURNING`/`OUTPUT INSERTED`; valores siempre ligados. |
| Fuga de credenciales en el mensaje de `PoolExhaustedError` | Information Disclosure | El mensaje actual solo incluye `timeout` y `max_size` (`pool.py:162`); no añadir `conn_kwargs` (que contienen password). Mantener. |
| Denegación de servicio por agotamiento del pool (espera infinita) | Denial of Service | `acquire(timeout=...)` → `PoolExhaustedError`; `pytest.mark.timeout` en los tests de carrera. |
| Estado cruzado entre tareas (id de otra escritura) | Tampering / Repudiation | Captura del id dentro de la sentencia + id por conexión/tarea; sin cache global (`PoolDb._last_id` eliminado). |
| Escritura silenciosamente perdida al liberar | Tampering (integridad de datos) | Commit/rollback explícito **antes** de `release()` (Correction #5); `TestPoolAutocommit` como regresión. |
| Cerrar una conexión en uso (rompe atomicidad de un tercero) | Denial of Service | `_checked_out` + `close()` que solo cierra ociosas. |

## Sources

### Primary (HIGH confidence)
- Código vivo leído y verificado (anclas file:line en todo el documento): `encino_orm/pool.py`, `base.py`, `context.py`, `query.py`, `engine.py`, `migration.py:65-144`, `model/model.py:492-552,623-683`, `sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`, `dialects/builders.py`, `dialects/strategies.py`, `tests/test_pool.py`, `tests/test_pool_characterization.py`, `tests/conftest.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `tools/ci/check_coverage_floors.py`.
- `.planning/phases/01-.../01-05-SUMMARY.md` — 19 tests de caracterización, baselines medidos (`_size == 5`) y tabla de inversiones.
- `.planning/phases/02-.../deferred-items.md:116-146` — ORA-38104 con dueño `04-02`/POOL-03.
- `.planning/ROADMAP.md:249-274,375-409` — planes, criterios de éxito y Research Corrections #1/#4/#5.
- **Sondas propias contra los 6 contenedores locales** (`docker ps` muestra los 6 corriendo):
  - PostgreSQL: `asyncpg.execute("INSERT ... RETURNING id")` → `1` (no lanza); `fetchrow` → `{'id': 2}`; `RETURNING id` sin columna `id` → `UndefinedColumnError`. `[VERIFIED: contenedor db-postgres-1]`
  - MSSQL: `OUTPUT INSERTED.id` → `(1,)` con `cursor.rowcount == -1`; `SCOPE_IDENTITY()` en `execute` separado → `(None,)`; `@@IDENTITY` → `(3,)`; `MERGE ... OUTPUT INSERTED.id` → `[(4,)]`. `[VERIFIED: contenedor db-mssql-1]`
  - Oracle: `INSERT ... RETURNING id INTO :ret_id` → `last_id()==1`; `RETURNING id` sin columna → `ORA-00904`; `MERGE ... RETURNING ... INTO` → `ORA-00933` (no soportado); `MERGE` con `SET` de la columna del `ON` → `ORA-38104`; `SET` sin ella → OK. `[VERIFIED: contenedor db-oracle-1]`
  - MySQL: `INSERT` → `lastrowid=1`; `ON DUPLICATE KEY UPDATE` sin fila nueva → `lastrowid=0, rowcount=0`; `REPLACE` → `lastrowid` nuevo. `[VERIFIED: contenedor db-mysql-1]`
  - SQLite: `aiosqlite` `cursor.lastrowid` → `1`, luego `2`. `[VERIFIED: aiosqlite 0.22.1]`
  - `pytest==9.1.1` + `pytest-timeout==2.4.0` + `pytest-repeat==0.9.4` + `pytest-asyncio==1.4.0` en venv aislado Python 3.10.18: los plugins cargan; `repeat(3)` → 3 ejecuciones; `timeout(2)` interrumpe un `await` colgado (método *thread* mata el proceso en Windows, como documenta el README). `[VERIFIED: venv aislado en %TEMP%]`
- `pypi.org/pypi/pytest-repeat/json` (0.9.4, 2025-04-07, Python ≥3.9, `pytest-dev`) y `raw.githubusercontent.com/pytest-dev/pytest-timeout/master/README.rst` (métodos *thread*/*signal*, `timeout_method`, marker `timeout`). `[CITED]`

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md:657` — `lastval()` session-scoped (corrección ya aplicada).
- `01-05-SUMMARY.md:103-114` — tabla de inversiones/preservaciones de la caracterización.
- `docs/engines.md:133-137`, `docs/guide.md:190` — contrato documentado que hay que actualizar.

### Tertiary (LOW confidence)
- Compatibilidad de `pytest-timeout 2.4.0` con `pytest 9.1.1`: verificada **empíricamente** en venv aislado (carga y funciona), pero no está declarada en el changelog del plugin (el 2.5.0 no publicado menciona "minimal pytest 8.4"). Si CI falla por incompatibilidad, la mitigación es fijar `pytest-timeout==2.5.0` cuando se publique o usar `--timeout-method=thread` con las consecuencias documentadas.
- `pytest-timeout` con método *signal* interrumpiendo un `await` de `pytest-asyncio` en Linux: no probado en este host Windows (ver A5).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — las dos dev deps están verificadas en venv aislado; el resto es stdlib ya en uso. La legitimidad queda `[ASSUMED]` por ausencia de `slopcheck`.
- Architecture: HIGH en el mapa del estado actual (cada afirmación tiene ancla file:line) y en los mecanismos de id por motor (sondas contra los 6 contenedores); MEDIUM en la forma final del handle y en la semántica de `reset_on_release` (decisiones abiertas, no incertidumbre técnica).
- Pitfalls: HIGH — los 4 defectos del pool están medidos por la caracterización de Fase 1; las trampas de los motores (RETURNING sin columna, SCOPE_IDENTITY cross-batch, MERGE RETURNING en Oracle, ORA-38104) están reproducidas empíricamente.
- Security: HIGH — sin superficie nueva de autenticación; el único control nuevo es `check_identifier` sobre `returning=`.

**Research date:** 2026-09-18
**Valid until:** 2026-10-18 (30 días). Revisar antes si: (a) se publica `pytest-timeout 2.5.0`, (b) cambia el piso de Python o la matriz de CI, (c) el usuario confirma/niega los supuestos A1/A3/A4/A8.
