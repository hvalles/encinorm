# encino_orm

## What This Is

`encino_orm` es un ORM asíncrono de interfaz unificada para seis motores de base de datos (SQLite, MySQL, MariaDB, PostgreSQL, SQL Server y Oracle), construido sobre `pydantic` v2. Ofrece un modelo declarativo, CRUD tipado, relaciones, consultas componibles, migraciones y capas opcionales de producto (REST, GraphQL, RBAC/JWT y codegen). Está en fase experimental (`v0.2.6`) y su objetivo actual es alcanzar fiabilidad de nivel producción para uso interno y publicación en PyPI.

## Core Value

El ORM debe ser **confiable en producción sobre cualquiera de los seis motores**: correcto bajo concurrencia, seguro frente a inyección y configuraciones erróneas, y predecible en rendimiento. Si todo lo demás falla, la corrección y la seguridad de los datos no pueden fallar.

## Requirements

### Validated

<!-- Capacidades ya presentes en el código y confirmadas por la suite de pruebas. -->

- ✓ Modelo declarativo pydantic con CRUD completo (`insert`, `save`, `upsert`, `load`, `update`, `delete`, `search`, `count`, `paginate`, `insert_many`) — existing
- ✓ Seis adaptadores de motor tras la interfaz abstracta `Db` (`sqlite.py`, `mysql.py`, `mariadb.py`, `postgresql.py`, `mssql.py`, `oracle.py`) — existing
- ✓ `PoolDb` con afinidad transaccional por tarea vía `contextvar` y `session()` — existing
- ✓ Relaciones 1:1 y 1:N con carga por lotes (`batch_reference` / `batch_has_many`) para evitar N+1 — existing
- ✓ `Filter` componible inmutable y `QueryBuilder` con `join`, `group_by`, agregados y subconsultas — existing
- ✓ Esquema: `create_table`, migraciones versionadas, `diff_schema` y `sync_schema` — existing
- ✓ Hooks de ciclo de vida y caché (`CachedModel` + `CacheBackend`, backend de memoria y Redis) — existing
- ✓ Conexión implícita (`set_default_db`, `bind`, `session`, `resolve_db`) — existing
- ✓ Observabilidad (`trace_id`, `QueryTracer`, `OtelQueryTracer`) — existing
- ✓ Capas opcionales de importación diferida: REST (`create_crud`), GraphQL (`build_schema`), seguridad RBAC+JWT y codegen/CLI — existing
- ✓ Defensa sistémica de inyección SQL: todo pasa por `Query` y los identificadores se validan con `_IDENTIFIER_RE` en la capa `Model` — existing
- ✓ Suite de ~507 funciones de prueba; CI con servicios MySQL y PostgreSQL — existing
- ✓ Red de seguridad de CI verificable: `ruff` (lint+format) bloqueante, `mypy` no estricto con ratchet por módulo + `py.typed` en el wheel, `pytest-cov` con combine por pata y ratchet no-baja (82), y escaneo de dependencias (`uv lock --check` + `uv audit` + `pip-audit`) — Validated in Phase 1
- ✓ Interruptor de motores requeridos (`ENCINO_ORM_REQUIRE_ENGINES`) que falla en vez de omitir, gate JUnit `skipped > 0` fail-closed, y release gateado por CI (`needs: [ci]` vía reusable workflow) — Validated in Phase 1
- ✓ Suite de 19 tests de caracterización del pool que congelan el comportamiento actual antes del refactor de Fase 4 — Validated in Phase 1
- ✓ Seam único `encino_orm/dialects/` para validación de identificadores y construcción DML (builders compartidos `insert`/`update`/`delete`/`upsert`, con allowlist estricta y escape hatch `schema=`); el alias de `QueryBuilder` y el nombre de columna por defecto también se validan — Validated in Phase 2
- ✓ `Query` inmutable y hashable, con `with_params()` (reemplaza a `rebind`), compilación `{n}` por regex y validación de cardinalidad — Validated in Phase 2
- ✓ Alias explícito `AS n` en los 7 sitios de agregados (`Model.count`, `Db.list_tables`, `QueryBuilder.count/sum/avg/min/max`) — Validated in Phase 2
- ✓ `list_tables(name=)` funcional en los seis motores (tabla derivada + valor ligado) — Validated in Phase 2
- ✓ `MAX_PARAMS`/`MAX_ROWS` por dialecto con procedencia documentada; `insert_many` deriva su `chunk` — Validated in Phase 2
- ✓ Snapshots de SQL por dialecto (syrupy) en el job SQLite sin BD; CI con MariaDB + Redis requeridos y job `engine-heavy` para MSSQL/Oracle — Validated in Phase 2 (run live de `engine-heavy` pendiente de CI)
- ✓ Migraciones: ledger con `status` en los seis motores, `rollback_migration` corregido (re-aplicar tras el rollback funciona) y `migrate()` de dos fases (`pending` → DDL → `applied`) con `reconcile_migrations`/`resolve_migration` y `TRANSACTIONAL_DDL` por dialecto; compensación por identidad de fila — Validated in Phase 3
- ✓ `CachedModel`: dominio de caché canónico por PK, invalidación de TODAS las filas afectadas (clave de escritura no-PK), clave namespaced por `scope()`, sonda con el valor serializado y fail-open; sin lecturas obsoletas tras una escritura — Validated in Phase 3
- ✓ `MemoryCacheBackend` acotado con LRU (`max_size=1024`) y documentado como dev/test-only — Validated in Phase 3
- ✓ SEC-01: `Model.update`/`delete` aplican el `scope()` activo al DML (`WHERE` ligado); una escritura con clave no-PK no cruza tenants — Validated in Phase 3
- ✓ `PooledConnection` concentra el estado por conexión; `acquire()` reserva-antes-de-await (nunca supera `max_size`) con ownership por tarea; `PoolDb._last_id` eliminado — Validated in Phase 4
- ✓ El id se captura DENTRO del INSERT por conexión/tarea (`Db.execute_insert`, `returning=` opt-in: `lastrowid`/`RETURNING`/`OUTPUT INSERTED`/`RETURNING INTO`); `last_id()` post-hoc deprecado; MERGE de Oracle ejecutable (ORA-38104) — Validated in Phase 4
- ✓ `reset_on_release` (rollback por defecto, `"commit"` deprecado con warning) con commit/rollback explícito en `execute`/`_run`; `close()` idempotente que respeta al tenedor; reaper perezoso por encima de `min_size` — Validated in Phase 4
- ✓ Tests de concurrencia/estrés deterministas (barrera `asyncio.Event`, piso 3.10) con `pytest-timeout`/`pytest-repeat` — Validated in Phase 4
- ✓ RESL-01: cada adaptador clasifica desconexiones (`is_disconnect_error`) sin solaparse con lock/deadlock (`is_lock_error`) — Validated in Phase 5
- ✓ RESL-02: `_with_reconnect` reconecta exactamente una vez y solo fuera de transacción (lecturas re-ejecutan; escritura pre-ejecución ejecuta; escritura mid-statement reconecta y relanza para no duplicar) — Validated in Phase 5
- ✓ RESL-03: conexiones directas con `pre_ping` y `max_connection_lifetime` (reaper perezoso, sin daemon; nunca dentro de una transacción) — Validated in Phase 5
- ✓ RESL-04: taxonomía pública de errores (`ConnectionLostError`/`OperationalError`/`IntegrityError`/`ProgrammingError`) con traducción única que preserva `__cause__` y no toca los locks — Validated in Phase 5
- ✓ CFG-01: `ConnectionRegistry` inyectable reemplaza el global `_default_db`; shims deprecados con `DeprecationWarning` — Validated in Phase 6
- ✓ CFG-02: `SecurityConfig` inmutable + factorías de guards; mutar `SECRET`/`GET_DB` deja de cambiar el comportamiento; fail-closed ante secreto vacío — Validated in Phase 6
- ✓ CFG-03: handlers REST/GraphQL generados con `exec()` sustituidos por closures + `__signature__`, con snapshot OpenAPI/SDL antes/después byte-idéntico — Validated in Phase 6
- ✓ CFG-04: `build_schema` usa un namespace por build sin mutar el módulo ni filtrar `sys.modules` — Validated in Phase 6
- ✓ CFG-05: fronteras de confianza de `Filter.raw`/`Query`/`db.fn.*` documentadas con ejemplos seguros/inseguros — Validated in Phase 6

### Active

<!-- Alcance actual: hardening hacia 0.3.0. Son hipótesis hasta que se implementen y verifiquen. -->

**Corrección de bugs conocidos**
- [ ] `upsert` con claves de conflicto globales no se acota por `scope()` (residual documentado; mitigación: unicidad multi-tenant `(tenant, clave)`)

**Seguridad**
- [x] La configuración de JWT/secretos deja de depender de globales mutables; se prefiere inyección explícita por dependencia — Validated in Phase 6 (`SecurityConfig`)
- [ ] Las credenciales de desarrollo (`docker-compose.yml`) están marcadas como solo-desarrollo y los workflows de release migran a trusted publishing/OIDC
- [x] Documentación explícita de superficies de confianza (`Filter.raw`, `Query`, fragmentos `db.fn.*`) — Validated in Phase 6 (`docs/trust-boundaries.md`)

**Concurrencia y pool**
- [x] Reconexión automática o envoltorio de salud para conexiones directas (no-pool) — Validated in Phase 5 (`pre_ping`/`max_connection_lifetime`)
- [ ] (Residual menor documentado) `connect()` sin `close()` intermedio puede duplicar el lote; endurecer con guard de idempotencia en una pasada de calidad del pool

**Calidad y CI**
- [x] El job `engine-heavy` (MSSQL + Oracle) tuvo su primer run verde en CI (2026-09-18); el fallo previo era el piso de cobertura global aplicado a una pata parcial, resuelto con `--cov-fail-under=0`

**Rendimiento**
- [ ] `copy_table` inserta por lotes en lugar de una fila por round-trip
- [ ] La traducción de placeholders se precompila/cachea en lugar de re-parsear con regex en cada ejecución
- [ ] Suite de benchmarks con objetivos numéricos medibles en CI

**Release**
- [ ] `CHANGELOG.md` documenta todos los cambios incompatibles introducidos en 0.3.0

### Out of Scope

<!-- Límites explícitos. Incluye el razonamiento para evitar reintroducirlos. -->

- Nuevos motores de base de datos — el foco es la fiabilidad de los seis existentes, no ampliar la matriz de dialectos
- Declarar 1.0 y garantizar compatibilidad retroactiva — el proyecto sigue experimental; primero hardening, después estabilidad
- Renombrar o rediseñar la API pública por motivos estéticos — solo se aceptan rupturas que mejoren seguridad, corrección o estabilidad

## Context

**Estado actual del código (mapeado el 2026-09-17, ver `.planning/codebase/`):**

- `encino_orm` v0.2.6, ~141 archivos versionados, ~507 funciones de prueba.
- Arquitectura por capas: `Db` (ABC) → seis adaptadores → `Model`/`Filter`/`QueryBuilder` → capas opcionales con importación diferida.
- El núcleo nunca debe importar FastAPI, Strawberry, PyJWT, redis ni los drivers MSSQL/Oracle a nivel de módulo.
- Estado de deuda técnica y riesgos detallado en `.planning/codebase/CONCERNS.md` (bugs, seguridad, rendimiento, áreas frágiles, límites de escalado y huecos de cobertura).

**Hallazgos que motivan este milestone:**

- Bug de `COUNT(*)` específico de PostgreSQL que pasa desapercibido por falta de cobertura de integración multi-motor.
- `CachedModel` nunca invalida, lo que produce lecturas obsoletas en producción.
- Carreras de concurrencia en `PoolDb` (`acquire()`, `_last_id` compartido, commit implícito) sin tests.
- Ausencia total de lint, type-check y cobertura en CI.
- Builders de bajo nivel (`Db.insert/update/delete`) no validan identificadores, a diferencia de la capa `Model`.

**Estado tras Fase 1 (2026-09-18):** la red de seguridad de CI ya está en pie — ruff, mypy+`py.typed`, coverage con ratchet, escaneo de dependencias, interruptor de motores requeridos, gate JUnit y release gateado. La suite pasó de ~507 a 553 tests. Pendiente de verificación humana/CI: que un gate rojo bloquee de verdad la publicación y que quitar un servicio de motor haga fallar el job (ver `01-HUMAN-UAT.md`). Riesgo residual registrado: 5 GHSA de PyJWT 2.12.1 en allowlist temporal hasta Fase 6.

**Estado tras Fase 2 (2026-09-18):** el seam `dialects/` es el único punto de validación de identificadores y construcción DML; `Query` es inmutable; los 7 sitios del bug `COUNT(*)` corregidos; `list_tables(name=)` funciona en los seis motores; y hay snapshots de SQL por dialecto más matriz CI con MariaDB/Redis requeridos y job `engine-heavy` para MSSQL/Oracle. La fase necesitó **3 rondas de gap closure** (12 planes) porque las revisiones descubrieron, uno tras otro, vectores hermanos del mismo defecto: el alias de `QueryBuilder`, luego `_table`, luego `upsert`/`last_id`. Lección: un "choke point" declarado no es un choke point hasta que se barren TODAS las posiciones de interpolación. La suite pasó de 553 a **790 tests**. Pendiente de verificación humana/CI: primer run verde del job `engine-heavy`. Deuda con dueño asignado: captura real de `last_id` en MERGE (`OUTPUT INSERTED.id`) y el `SET` del MERGE de Oracle (ORA-38104) → Fase 4 / `04-02` / POOL-03.

**Entorno técnico:** Python 3.10+, `pydantic>=2.13.4`, `asyncio` de un solo hilo con estado por tarea en `contextvars`. Desarrollo en Windows con `uv`.

## Constraints

- **Tech stack**: Mantener el contrato de importación diferida — el núcleo no puede adquirir dependencias duras de las capas opcionales.
- **Compatibilidad**: Al ser `0.x`, se permiten cambios incompatibles, pero **deben** quedar documentados en `CHANGELOG.md`.
- **Infraestructura**: La cobertura multi-motor depende de contenedores/servicios en CI; Oracle y SQL Server no están disponibles hoy.
- **Rendimiento**: Las optimizaciones no pueden regresar la corrección; se requieren benchmarks medibles, no percepciones.
- **Alcance**: Sin nuevos motores y sin declarar 1.0 en este milestone.
- **Timeline**: Sin plazo definido; priorizar calidad sobre velocidad.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Objetivo de release 0.3.0 con rupturas documentadas | Permite corregir diseño y seguridad sin arrastrar compatibilidad rota | — Pending |
| No congelar la API en 1.0 todavía | El proyecto sigue experimental; el hardening es prerrequisito | — Pending |
| Excluir nuevos motores del alcance | Concentrar esfuerzo en la fiabilidad de los seis motores actuales | — Pending |
| Exigir test de regresión por cada bug corregido | Evita reaparición y da evidencia objetiva de "done" | — Pending |
| Cobertura multi-motor como criterio de done | El bug de `COUNT(*)` demuestra que el sesgo a SQLite oculta fallos dialectales | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-19 after Phase 6 completion*
