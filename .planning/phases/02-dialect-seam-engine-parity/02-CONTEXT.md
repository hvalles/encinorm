# Phase 2: Dialect Seam & Engine Parity - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Crear **un único punto de validación y construcción DML** dentro del core (`dialects/`), corregir `Query`, y **probar la paridad real** de `count`/`paginate`/`list_tables`/`sync_schema`/`last_id` en los seis motores.

Entrega: seam de dialectos + builders compartidos, `Query` inmutable y correcto, alias `AS n` en los sitios del bug `COUNT(*)`, constantes `MAX_PARAMS`/`MAX_ROWS` por dialecto, snapshots de SQL por dialecto, matriz CI multi-motor y tests de integración por motor.

**No** entrega: correcciones de caché/migraciones (Fase 3), refactor del pool (Fase 4), resiliencia (Fase 5).

</domain>

<decisions>
## Implementation Decisions

### Refactor de `Query` (DIAL-05)
- **D-01:** **Ruptura limpia.** `Query` pasa a ser inmutable y `rebind` se **elimina**. No se dejan shims deprecados. Justificación: `rebind` no se usa en ningún punto de `encino_orm/` ni de `tests/` — solo está documentado en `docs/design/0-design.md`. Se documenta la ruptura en `CHANGELOG.md` y en `MIGRATION-0.3.md` (Fase 8).
- **D-02:** **Interfaz con accesores tipados + compatibilidad de lectura.** El `Query` inmutable expone accesores tipados `sql` y `params`, y mantiene una property `query` de **solo lectura** que devuelve `[sql, params]`. Objetivo: que DIAL-05 **no toque los 6 adaptadores** (que hoy leen `qry.query[0]`/`qry.query[1]` en su `_prepare` y en las migraciones). Los adaptadores migran a los accesores tipados en DIAL-02, cuando ya se reescriben los builders.
- **D-03:** **Igualdad y hash estrictos.** `__eq__` compara plantilla SQL + params. `__hash__` se calcula sobre `(sql_template, tupla_de_params)` y lanza **`TypeError` explícito** si algún valor de los params no es hashable (list/dict), en lugar de devolver un hash engañoso. Esto habilita un cache-key real para DATA-07 (v2) y falla ruidosamente.
- **D-04:** **Se mantiene `{n}` como contrato de entrada.** La firma sigue siendo `Query(sql_con_{n}, [valores])`. Se arregla la compilación: detección por regex de los `{n}` **reales** (no `enumerate` sobre el dict de params), soporte de índices dispersos o duplicados, y **validación de cardinalidad** (el número de placeholders debe cuadrar con la lista de params) con error claro. No se añade el modo dict nombrado en esta fase.
- **D-05:** **Se actualiza `docs/design/0-design.md`** a la API nueva (inmutable, `with_params()` en lugar de `rebind`) con una nota de migración. El sitio de docs se publica, así que no debe documentar una API eliminada.

### Ajuste de requisito derivado de D-01
- **D-06:** La redacción de **DIAL-05** en `REQUIREMENTS.md` dice literalmente *"sin sentinel frágil `{0}`, inmutable/hashable, y `rebind` funciona"*. Al eliminar `rebind`, la letra del requisito cambia: se reformula a **"`Query` inmutable con `with_params()` que devuelve una copia"**. El roadmapper/planner debe reflejar esta reformulación en la trazabilidad.

### Áreas no discutidas (quedan a criterio de research + planning)
El usuario eligió discutir únicamente el refactor de `Query`. Las cuatro áreas restantes **siguen en alcance** (DIAL-01/02/03/04/06/07/08/09) pero **sin decisión de usuario**, así que research/planning deben resolverlas sujetas a estas restricciones ya fijadas:
- **Validación de identificadores (DIAL-01/02/04):** restricción dura de `research/PITFALLS.md` — centralizar `_IDENTIFIER_RE`/`_check_identifier` como **refactor puro con cero cambio de comportamiento en un commit propio**, y añadir la validación como **commit separado y bisectable**. Ojo: el allowlist `^[A-Za-z_][A-Za-z0-9_]*$` rechaza `schema.tabla`, nombres citados y no-ASCII; aplicarlo sin más rompe uso legítimo y empuja a SQL a mano (menos seguro). Documentar la decisión tomada.
- **Matriz CI multi-motor (DIAL-08):** D-01 de Fase 1 exige que el interruptor sea extensible sin rediseño; el job `test` hoy tiene servicios `mysql` + `postgres` con `timeout-minutes: 15`. Decidir qué motores pasan a requeridos y cómo se tratan MSSQL/Oracle (testcontainers en job separado de una sola versión de Python, mocks justificados, o solo local) — ver `research/SUMMARY.md` Fase 2 y el flag de investigación.
- **Piso de cobertura por dialecto (D-04/D-06 de Fase 1):** prometido para esta fase. `coverage.py` **no** tiene `fail_under` por archivo, así que requiere un script sobre `coverage json`. El baseline CI-equivalente medido es ~84%; el global está en `fail_under = 82`.
- **Snapshots syrupy (DIAL-07):** decidir el alcance (builders compartidos × 6 dialectos vs todo el SQL generado vs solo insert/update/delete) y si el snapshot es gate o advisory. Los snapshots deben correr en el job SQLite siempre activo, sin BD.

### the agent's Discretion
- Estructura interna del seam `dialects/` (nombres de módulos, forma de los hooks por dialecto).
- Forma exacta de `with_params()` y de la validación de cardinalidad.
- Valores concretos de `MAX_PARAMS`/`MAX_ROWS` por dialecto (la investigación los marca como **no verificados empíricamente**: MSSQL 2100, Oracle 1000-elemento `IN`, asyncpg ~32767).
- Selección de qué SQL exacto se congela en los snapshots.

### Folded Todos
Ninguno — no había todos pendientes para esta fase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Contexto de proyecto y alcance
- `.planning/PROJECT.md` — Core value y límites del milestone
- `.planning/REQUIREMENTS.md` — Los 47 requisitos v1; esta fase cubre **DIAL-01…DIAL-09**
- `.planning/ROADMAP.md` — Sección de Fase 2 (5 planes: 02-01…02-05), **Restricciones Duras de Ordenamiento** y sección **Research Corrections Carried Into This Roadmap**
- `.planning/STATE.md` — Posición actual y blockers

### Contexto de la fase anterior (decisiones que aplican aquí)
- `.planning/phases/01-safety-net-ci-gates-test-infrastructure/01-CONTEXT.md` — **D-01** (interruptor extensible), **D-02** (`optional_engine`), **D-04/D-06** (el piso por dialecto se define en Fase 2), **D-09** (no se reescribieron asserts genéricos ni de estado privado)
- `.planning/phases/01-safety-net-ci-gates-test-infrastructure/01-VERIFICATION.md` — Qué quedó probado (gates, cobertura 84%, required-engine switch)
- `.planning/phases/01-safety-net-ci-gates-test-infrastructure/01-HUMAN-UAT.md` — CI-01 y CI-08 probados en GitHub Actions

### Investigación (decisiones y trampas)
- `.planning/research/ARCHITECTURE.md` — El seam `dialects/builders.py` + `strategies.py` y el cache de SQL compilado en `Query`; hooks por dialecto
- `.planning/research/PITFALLS.md` — **Pitfall 10** (validación que rompe uso o se salta dialectos), **Pitfall 19** (sentinel de `Query`), **Pitfall 7** (constantes de batch por dialecto)
- `.planning/research/SUMMARY.md` — Fase 2: criterios, flag de investigación (syrupy + topología testcontainers MSSQL/Oracle) y la corrección sobre `lastval()`
- `.planning/research/STACK.md` — Versiones y configuración de tooling (syrupy, pytest-cov, cobertura)

### Mapa del código
- `.planning/codebase/ARCHITECTURE.md` — Contrato de placeholders (`Query.query[0]` con `%(name)s`), validación de identificadores, y el anti-patrón "añadir ramas de motor fuera del adaptador"
- `.planning/codebase/CONCERNS.md` — Bug de `COUNT(*)`, builders duplicados entre dialectos, builders públicos sin validación
- `.planning/codebase/CONVENTIONS.md` — Estilo, comentarios en español, naming
- `.planning/codebase/TESTING.md` — Patrón skip-on-connection-failure, markers, estructura por motor

### Código y configuración vivos
- `encino_orm/query.py` — El objeto a refactorizar (mutable, sentinel `{0}`, `rebind`)
- `encino_orm/base.py` — `_IDENTIFIER_RE:13`, `_check_identifier:61`, `COUNT(*)` en `:158`, **patrón correcto `AS n` en `:175`**
- `encino_orm/model/model.py` — `_IDENTIFIER_RE:29`, `COUNT(*)` en `:793-795`
- `encino_orm/model/query_builder.py` — `COUNT(*)` en `:244-246`
- `encino_orm/model/types.py` — `_IDENTIFIER_RE:201` y `DDL_MAP`
- `encino_orm/{sqlite,mysql,postgresql,mssql,oracle}.py` — Builders `insert`/`update`/`delete` y `_prepare` (MariaDB hereda de MySQL)
- `encino_orm/transfer.py` — `_IDENTIFIER_RE:16` y `_check_identifier:19` duplicados
- `pyproject.toml` — `[tool.coverage]` (parallel, branch, `fail_under = 82`) y `[tool.pytest.ini_options]` (markers, filterwarnings)
- `.github/workflows/ci.yml` — Job `test` (servicios mysql+postgres), `coverage` (`needs: [test]`), `lint`, `typecheck`, `deps`
- `docs/design/0-design.md` — Documenta la API vieja de `Query` con `rebind` (a actualizar por D-05)
- `tests/test_pool_characterization.py` — Patrón de fakes a mano y barrera `asyncio.Event` (referencia para tests deterministas)
- `tools/ci/check_skips.py` — Script stdlib del gate JUnit

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`Db._check_identifier` (`base.py:61`)** — Ya existe y valida con `_IDENTIFIER_RE`; es el candidato natural a centralizar y reutilizar en los builders de bajo nivel.
- **`base.py:175`** — Ya usa el patrón correcto `SELECT COUNT(*) AS n FROM (...) _encino_orm_count`. Es la plantilla a copiar en los 3 sitios del bug.
- **Traductores `_to_<engine>`** (`sqlite.py:105`, `mysql.py:112`, `postgresql.py:120`, `mssql.py:150`, `oracle.py:144`) — Reciben `(sql, params)` y reescriben `%(name)s` al placeholder nativo. Contrato estable sobre el que montar los builders compartidos.
- **Fakes a mano + `monkeypatch.setitem(pool_module._ENGINES, ...)`** (`tests/test_pool.py`, `tests/test_pool_characterization.py`) — Patrón aceptado del repo; preferirlo a `unittest.mock`.
- **Infraestructura de CI de Fase 1** — Jobs `lint`/`typecheck`/`deps`/`coverage` ya bloqueantes; el interruptor `ENCINO_ORM_REQUIRE_ENGINES` y el marker `optional_engine` ya existen para promover motores.
- **`tools/ci/check_skips.py`** — Gate JUnit stdlib ya probado; los tests nuevos por motor deben pasar por él (sin skips no marcados).

### Established Patterns
- **Contrato de placeholders:** `Query.query[0]` lleva `%(name)s` y cada adaptador lo traduce en `_prepare` con un `_PLACEHOLDER_RE` + `_to_<engine>()` a nivel de módulo. Cambiar esto afecta a los 6 adaptadores.
- **Validación de identificadores por regex** antes de interpolar, con `_IDENTIFIER_RE` copiado en 6 módulos y `_check_identifier` duplicado en `transfer.py`.
- **Tests por motor con skip-guard** (`engine_unavailable()` desde Fase 1) y archivos separados (`tests/test_<engine>.py`), sin `@pytest.mark.parametrize`.
- **Tests white-box aceptados:** importar helpers privados directamente (`from encino_orm.postgresql import _rowcount, _to_postgres`).
- **Comentarios y docstrings en español** explicando el *por qué*; sin secciones `Args:`/`Returns:`.
- **Import diferido** obligatorio: el core no puede adquirir dependencias duras de capas opcionales.

### Integration Points
- `encino_orm/query.py` — Refactor de DIAL-05 (inmutable + accesores + hash).
- Los 6 adaptadores (`_prepare`, builders `insert`/`update`/`delete`, `columns_of`, `last_id`) — DIAL-02 y DIAL-03.
- `encino_orm/base.py`, `model/model.py`, `model/query_builder.py` — Los 3 sitios del bug `COUNT(*)`.
- `encino_orm/transfer.py` — Validación y duplicación de regex.
- `.github/workflows/ci.yml` — Expansión de la matriz (DIAL-08) y el piso por dialecto (D-04/D-06).
- `docs/design/0-design.md` — Actualización de la API de `Query`.

</code_context>

<specifics>
## Specific Ideas

- **`rebind` es código muerto internamente:** grep sobre `encino_orm/` y `tests/` no devuelve ningún uso; solo aparece en `docs/design/0-design.md:22,35,66,87,397`. Eso hace que la ruptura limpia (D-01) sea de bajo riesgo real.
- **El sentinel es peor de lo que parece:** `format()` itera `enumerate(cols)`, así que solo reemplaza índices contiguos desde 0. Un `Query("… {0} … {2}", [a, b])` deja `{2}` literal en el SQL, y `sql.find("{0}")` clasifica como "sin params" cualquier SQL cuyo primer placeholder no sea `{0}`.
- **`base.py:158`** es el sitio más engañoso del bug: `fetch_one(...)["COUNT(*)"]` funciona en SQLite/MySQL pero revienta en PostgreSQL (asyncpg devuelve la clave en minúsculas).
- **DIAL-05 cambia de letra** por D-01/D-06: `rebind` → `with_params()`.

</specifics>

<deferred>
## Deferred Ideas

- **Cache de placeholders compilados (TS-37)** — diferido a v2 como `DATA-07`; D-03 deja `Query` *listo* para ello (hashable) sin implementar el cache. Se reabre solo si el profiler de Fase 7 lo muestra en el top 5.
- **Modo de params nombrados (`%(nombre)s` con dict)** — considerado y descartado para esta fase (D-04); posible mejora futura de ergonomía.
- **Piso global de cobertura más alto** — el piso por dialecto (no discutido) es lo prometido para Fase 2; subir el global queda para más adelante.

### Reviewed Todos (not folded)
Ninguno — no había todos pendientes para esta fase.

</deferred>

---

*Phase: 2-Dialect Seam & Engine Parity*
*Context gathered: 2026-09-18*
