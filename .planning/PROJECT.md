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

### Active

<!-- Alcance actual: hardening hacia 0.3.0. Son hipótesis hasta que se implementen y verifiquen. -->

**Corrección de bugs conocidos**
- [ ] `count()` / `paginate()` / `list_tables()` devuelven resultados correctos en PostgreSQL, SQL Server y Oracle (eliminar `KeyError: 'COUNT(*)'` alineando el alias `AS n`)
- [ ] `CachedModel` invalida la caché en `update()` y `delete()`; no hay lecturas obsoletas
- [ ] `rollback_migration` + `apply_migration` permite re-aplicar una migración correctamente
- [ ] `migrate()` es atómico o reconcilia el estado tras fallo parcial
- [ ] Cada corrección incluye un test de regresión que falla antes y pasa después

**Seguridad**
- [ ] `Db.insert` / `Db.update` / `Db.delete` validan `tabla` y cada clave de columna con `_check_identifier` en los seis dialectos
- [ ] La configuración de JWT/secretos deja de depender de globales mutables; se prefiere inyección explícita por dependencia
- [ ] Las credenciales de desarrollo (`docker-compose.yml`) están marcadas como solo-desarrollo y los workflows de release migran a trusted publishing/OIDC
- [ ] `sync_schema` valida los nombres de columna derivados de introspección antes de interpolarlos en `ALTER TABLE`
- [ ] Documentación explícita de superficies de confianza (`Filter.raw`, `Query`, fragmentos `db.fn.*`)

**Concurrencia y pool**
- [ ] `PoolDb.acquire()` es libre de carreras; nunca supera `max_size` bajo concurrencia
- [ ] `last_id()` es correcto por conexión/tarea; sin cruces entre inserts concurrentes
- [ ] Política definida de commit vs rollback al liberar una conexión con transacción abierta
- [ ] Reconexión automática o envoltorio de salud para conexiones directas (no-pool)
- [ ] Tests de concurrencia y estrés del pool que cubran estos caminos

**Calidad y CI**
- [ ] `ruff` (lint + format) y `mypy` configurados como dependencias de desarrollo
- [ ] `pytest-cov` con reporte y umbral de cobertura
- [ ] CI ejecuta gates obligatorios de lint, tipos y cobertura
- [ ] Matriz multi-motor en CI (MariaDB, SQL Server, Oracle, Redis) mediante servicios o contenedores, o mocks equivalentes justificados
- [ ] Escaneo de dependencias/seguridad (`pip-audit`, Dependabot o `uv lock --check`)

**Rendimiento**
- [ ] `copy_table` inserta por lotes en lugar de una fila por round-trip
- [ ] La traducción de placeholders se precompila/cachea en lugar de re-parsear con regex en cada ejecución
- [ ] El pool cierra conexiones ociosas por encima de `min_size` (reaper o política en `release()`)
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
*Last updated: 2026-09-17 after initialization*
