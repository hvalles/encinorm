# Requirements: encino_orm — Hardening 0.3.0

**Defined:** 2026-09-17
**Core Value:** El ORM debe ser confiable en producción sobre cualquiera de los seis motores: correcto bajo concurrencia, seguro frente a inyección y configuraciones erróneas, y predecible en rendimiento.

## v1 Requirements

Requisitos para el release 0.3.0. Cada uno se mapea a una fase del roadmap.

### CI Gates & Test Infrastructure

- [x] **CI-01**: Un interruptor `ENCINO_ORM_REQUIRE_ENGINES` hace que un motor requerido ausente **falle** la suite en lugar de omitirla con `skip`
- [x] **CI-02**: Un gate post-run sobre JUnit-XML falla el job de CI si `skipped > 0`
- [x] **CI-03**: `ruff` (lint + format) está configurado y es un job bloqueante de CI
- [x] **CI-04**: `mypy` (no estricto, con ratchet) pasa y existe el marcador `py.typed`
- [x] **CI-05**: `pytest-cov` reporta con `parallel = true` + `coverage combine` por motor y un umbral ratchet bajo
- [x] **CI-06**: La configuración de pytest se endurece (`--strict-markers`, `xfail_strict`, `filterwarnings = ["error"]`, ambos loop scopes, markers declarados)
- [x] **CI-07**: El escaneo de dependencias/vulnerabilidades (`uv lock --check`, `uv audit` o `pip-audit`) corre en CI
- [x] **CI-08**: El workflow de release depende de CI, de modo que ninguna publicación ocurre sin gates verdes
- [x] **CI-09**: Existen tests de caracterización de los invariantes del pool **antes** de refactorizarlo

### Dialect Seam & Engine Parity

- [x] **DIAL-01**: `_IDENTIFIER_RE`/`_check_identifier` están centralizados en un único módulo como refactor puro, sin cambio de comportamiento
- [x] **DIAL-02**: Los builders DML (`insert`/`update`/`delete`) son compartidos en `dialects/` y validan cada tabla/columna en los seis motores
- [x] **DIAL-03**: `count`/`paginate`/`list_tables` devuelven resultados correctos en PostgreSQL, SQL Server y Oracle (alias `AS n`)
- [x] **DIAL-04**: Los identificadores derivados de introspección se validan antes de interpolarlos en `ALTER TABLE` (`sync_schema`)
- [x] **DIAL-05**: `Query` es correcto: sin sentinel frágil `{0}`, inmutable/hashable, y con `with_params()` que devuelve una copia (reemplaza al mutante `rebind`, que se elimina)
- [x] **DIAL-06**: Existen constantes `MAX_PARAMS`/`MAX_ROWS` por dialecto
- [x] **DIAL-07**: Los snapshots de SQL por dialecto (syrupy) corren en el job SQLite siempre activo
- [x] **DIAL-08**: La matriz de CI cubre múltiples motores (MariaDB + Redis como servicios; MSSQL/Oracle en un job separado)
- [x] **DIAL-09**: Existen tests de integración por motor para `count`/`paginate`/`list_tables`/`sync_schema`/`last_id`

### Data Correctness

- [x] **DATA-01**: El ledger de `rollback_migration` está corregido: re-aplicar una migración tras el rollback funciona
- [x] **DATA-02**: `migrate()` es atómico o registra la intención primero y reconcilia al arrancar (`transactional_ddl` por dialecto)
- [x] **DATA-03**: `CachedModel` invalida la caché en `update` **y** `delete` (store-then-invalidate), sin lecturas obsoletas
- [x] **DATA-04**: `MemoryCacheBackend` está acotado o documentado explícitamente como solo dev/test

### Row-level Security (multi-tenancy)

- [x] **SEC-01**: `Model.update`/`delete` aplican el `scope()` activo al DML (`WHERE` ligado), de modo que una escritura por claves no-PK no modifica ni borra filas de otro tenant

### Pool Correctness & Concurrency

- [x] **POOL-01**: Existe un handle `PooledConnection` que concentra el estado por conexión (driver, `last_id`, timestamps, generación, en-uso)
- [x] **POOL-02**: `acquire()` es libre de carreras (reserva-antes-de-await) y nunca supera `max_size`
- [x] **POOL-03**: `last_id` se captura **dentro** del insert (`RETURNING`/`SCOPE_IDENTITY`/`lastrowid` inmediato) por conexión/tarea; el `last_id()` post-hoc queda deprecado (El plan `04-02` posee además el fix del `SET` del `MERGE` de Oracle — ORA-38104 — que hace ejecutable `Model.insert(replace=True)` allí; registrado por el plan `02-12`.)
- [x] **POOL-04**: Existe una política `reset_on_release` configurable con rollback por defecto, más warning de deprecación y entrada de CHANGELOG
- [x] **POOL-05**: Un contador de generación y un reaper perezoso cierran conexiones inactivas por encima de `min_size` sin daemon en background
- [x] **POOL-06**: `close()` es idempotente y nunca cierra una conexión en uso por el llamador
- [ ] **POOL-07**: Existen tests deterministas de concurrencia/estrés compatibles con Python 3.10 (barrera `asyncio.Event`) más `pytest-timeout`

### Resilience

- [ ] **RESL-01**: Cada adaptador clasifica errores de desconexión mediante `is_disconnect_error`
- [ ] **RESL-02**: `_with_reconnect` reconecta una sola vez y **solo** cuando no hay transacción abierta
- [ ] **RESL-03**: Las conexiones directas soportan `pre_ping` y `max_connection_lifetime`
- [ ] **RESL-04**: Existe una taxonomía pública de errores que traduce excepciones de driver a excepciones de la librería

### Config & Optional-Layer Hygiene

- [ ] **CFG-01**: `ConnectionRegistry` reemplaza el global `_default_db`, con shims retrocompatibles deprecados
- [ ] **CFG-02**: `SecurityConfig` inmutable y factorías de guards reemplazan los globales mutables `SECRET`/`GET_DB`
- [ ] **CFG-03**: Los handlers generados con `exec()` se sustituyen por closures/`__signature__` en un refactor que preserva comportamiento, con snapshot OpenAPI antes/después
- [ ] **CFG-04**: `build_schema` de GraphQL usa un namespace por build y deja de mutar el namespace del módulo
- [ ] **CFG-05**: Las fronteras de confianza de `Filter.raw`, `Query` y `db.fn.*` están documentadas explícitamente

### Performance

- [ ] **PERF-01**: `copy_table` inserta por lotes con tamaño por dialecto (`min(MAX_PARAMS // n_columnas, MAX_ROWS)`)
- [ ] **PERF-02**: Existe una suite de benchmarks con objetivos numéricos y un gate que falla ante una regresión deliberada de 2×
- [ ] **PERF-03**: La salida del profiler (`py-spy`/`cProfile`) se compromete **antes** de cualquier optimización
- [ ] **PERF-04**: `QueryTracer._latencies` está acotado y `_FIELD_ADAPTERS` usa `WeakKeyDictionary`

### Release

- [ ] **REL-01**: Se publica 0.2.7 con `DeprecationWarning`s en runtime por cada ruptura de 0.3.0
- [ ] **REL-02**: Se publica 0.3.0rc1 antes de 0.3.0
- [ ] **REL-03**: La publicación usa OIDC trusted publishing; `PYPI_API_TOKEN` se elimina y el entorno `pypi` está protegido
- [ ] **REL-04**: `CHANGELOG.md` enumera cada cambio incompatible con comportamiento viejo/nuevo y existe `MIGRATION-0.3.md` con ejemplos
- [ ] **REL-05**: El README incluye guía de pinning (`~=0.2.6`), warning de credenciales solo-desarrollo y se corrige el enlace muerto a `prompts/`

## v2 Requirements

Diferidos a 0.3.x/0.4+. Rastreados pero fuera del roadmap actual.

### Observabilidad

- **OBSV-01**: Instrumentación automática de queries en todos los motores
- **OBSV-02**: Convenciones semánticas estables de OpenTelemetry (`db.system.name`, `db.operation.name`, `db.query.text`, `db.response.status_code`)
- **OBSV-03**: Logging seguro de PII (valores de parámetros opt-in, nunca por defecto)
- **OBSV-04**: Logging de slow queries configurable
- **OBSV-05**: Métricas del pool con conteo de conexiones inactivas

### Data & Config avanzados

- **DATA-05**: Documentación de atomicidad de escrituras bulk por driver
- **DATA-06**: Configuración de nivel de aislamiento por transacción
- **DATA-07**: Cache de placeholders de `Query` (TS-37) — reabrir solo si el profiler lo muestra en el top 5 de hot paths

### Fiabilidad de producto

- **RELI-01**: Contrato público de fiabilidad por motor (documentado y verificado)
- **RELI-02**: Harness de conformidad de los seis motores
- **RELI-03**: Reciclado de conexiones (`max_connection_lifetime` para pool)
- **RELI-04**: Pool auto-reparable como promesa de producto
- **RELI-05**: Reconciliación de migraciones para MySQL/Oracle

## Out of Scope

Excluido explícitamente. Documentado para prevenir reincorporaciones.

| Feature | Reason |
|---------|--------|
| Nuevos motores de base de datos | El foco es la fiabilidad de los seis existentes, no ampliar la matriz de dialectos |
| Declarar 1.0 / garantía retroactiva | El proyecto sigue experimental; primero hardening, después estabilidad |
| Rediseño estético de la API pública | Solo se aceptan rupturas que mejoren seguridad, corrección o estabilidad |
| Reintento ciego de escrituras arbitrarias | Duplica datos; el reintento solo es seguro para errores de lock, no de desconexión |
| Doble pooling sobre el pool nativo del driver | Añade capas sin beneficio y complica el ciclo de vida |
| Daemon reaper obligatorio en background | El reaper debe ser perezoso y cancelable, no un proceso permanente |
| Coherencia de caché distribuida | Complejidad desproporcionada para este milestone |
| Wrappers catch-all `except Exception` | Oculta fallos reales y contradice el requisito de taxonomía de errores |
| Extender el codegen REST/GraphQL basado en `exec()` | Se sustituye, no se amplía (ver CFG-03) |
| Objetivo de 100% de cobertura | Métrica engañosa; la cobertura por motor importa más que el número global |
| Caché de lectura activada por defecto | Riesgo de lecturas obsoletas; debe ser opt-in |
| Autogenerate de migraciones estilo Alembic | Fuera del alcance de hardening |
| `python-semantic-release` | Genera el changelog desde commits, lo opuesto a explicar rupturas explícitamente |

## Traceability

Qué fase cubre cada requisito.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CI-01 | Phase 1 | Complete |
| CI-02 | Phase 1 | Complete |
| CI-03 | Phase 1 | Complete |
| CI-04 | Phase 1 | Complete |
| CI-05 | Phase 1 | Complete |
| CI-06 | Phase 1 | Complete |
| CI-07 | Phase 1 | Complete |
| CI-08 | Phase 1 | Complete |
| CI-09 | Phase 1 | Complete |
| DIAL-01 | Phase 2 | Complete |
| DIAL-02 | Phase 2 | Complete |
| DIAL-03 | Phase 2 | Complete |
| DIAL-04 | Phase 2 | Complete |
| DIAL-05 | Phase 2 | Complete |
| DIAL-06 | Phase 2 | Complete |
| DIAL-07 | Phase 2 | Complete |
| DIAL-08 | Phase 2 | Complete |
| DIAL-09 | Phase 2 | Complete |
| DATA-01 | Phase 3 | Complete |
| DATA-02 | Phase 3 | Complete |
| DATA-03 | Phase 3 | Complete |
| DATA-04 | Phase 3 | Complete |
| SEC-01 | Phase 3 | Complete |
| POOL-01 | Phase 4 | Complete |
| POOL-02 | Phase 4 | Complete |
| POOL-03 | Phase 4 | Complete |
| POOL-04 | Phase 4 | Complete |
| POOL-05 | Phase 4 | Complete |
| POOL-06 | Phase 4 | Complete |
| POOL-07 | Phase 4 | Pending |
| RESL-01 | Phase 5 | Pending |
| RESL-02 | Phase 5 | Pending |
| RESL-03 | Phase 5 | Pending |
| RESL-04 | Phase 5 | Pending |
| CFG-01 | Phase 6 | Pending |
| CFG-02 | Phase 6 | Pending |
| CFG-03 | Phase 6 | Pending |
| CFG-04 | Phase 6 | Pending |
| CFG-05 | Phase 6 | Pending |
| PERF-01 | Phase 7 | Pending |
| PERF-02 | Phase 7 | Pending |
| PERF-03 | Phase 7 | Pending |
| PERF-04 | Phase 7 | Pending |
| REL-01 | Phase 8 | Pending |
| REL-02 | Phase 8 | Pending |
| REL-03 | Phase 8 | Pending |
| REL-04 | Phase 8 | Pending |
| REL-05 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 47 total
- Mapped to phases: 47 ✓
- Unmapped: 0

**Por fase:**

| Phase | Requirements | Count |
|-------|--------------|-------|
| 1. Safety Net — CI Gates & Test Infrastructure | CI-01…CI-09 | 9 |
| 2. Dialect Seam & Engine Parity | DIAL-01…DIAL-09 | 9 |
| 3. Data Correctness | DATA-01…DATA-04 | 4 |
| 4. Pool Correctness & Concurrency | POOL-01…POOL-07 | 7 |
| 5. Resilience | RESL-01…RESL-04 | 4 |
| 6. Config & Optional-Layer Hygiene | CFG-01…CFG-05 | 5 |
| 7. Performance & Benchmarks | PERF-01…PERF-04 | 4 |
| 8. Release 0.3.0 | REL-01…REL-05 | 5 |

---
*Requirements defined: 2026-09-17*
*Last updated: 2026-09-17 after roadmap creation (traceability complete)*
