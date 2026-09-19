# Phase 6: Config & Optional-Layer Hygiene - Research

**Researched:** 2026-09-19
**Domain:** Eliminación de estado global mutable de configuración (conexión por defecto, secreto JWT y dependency de conexión) y de la indirección `exec()` en las capas opcionales HTTP (FastAPI) y GraphQL (Strawberry), sin cambiar el contrato observable (OpenAPI / SDL), más documentación de fronteras de confianza de los escapes SQL.
**Confidence:** **HIGH** en el mapa del estado actual (todo el código citado se leyó con anchors) y en la viabilidad de las tres técnicas centrales: **la equivalencia OpenAPI del `exec()`→closure está verificada empíricamente** (spec JSON idéntica byte a byte, con la ruta de parcheo confirmada), **el aislamiento de namespace GraphQL por build está verificado empíricamente** (namespace de módulo sin mutar, cero fugas en `sys.modules`, dos schemas sucesivos funcionales), y **la forma `SecurityConfig` frozen + factorías está verificada empíricamente** (200/401/403 end-to-end con mutación posterior de los globales sin efecto). **MEDIUM** en las decisiones de forma pública (firma exacta de `ConnectionRegistry`, si `create_crud`/`build_schema` reciben `config=`, y quién posee el `exec()` de `graphql/schema.py`). **HIGH** en que la fase **no necesita dependencias nuevas**.

> **No existe `06-CONTEXT.md`.** La fase no ha pasado por `/gsd-discuss-phase` (`.planning/phases/06-config-optional-layer-hygiene/` está vacío, verificado). Por eso no hay sección `## User Constraints (from CONTEXT.md)`; en su lugar se citan como restricciones vinculantes las decisiones ya bloqueadas en `ROADMAP.md` (Phase 6: goal, 5 criterios de éxito, planes `06-01`…`06-05`, líneas 301-325) y los Constraints de `PROJECT.md`.

<user_constraints>
## User Constraints (from ROADMAP.md — no CONTEXT.md exists)

### Locked Decisions (ROADMAP Phase 6, líneas 301-325)

- **Goal de la fase:** "No mutable module-level global decides which database or which secret is in play, and generated handlers stop being built with `exec()` — without changing the HTTP or GraphQL contract."
- **Plan `06-01`:** `ConnectionRegistry` reemplaza el global `_default_db`, con shims retrocompatibles deprecados — **CFG-01**.
- **Plan `06-02`:** `SecurityConfig` inmutable + factorías de guards reemplazan los globales mutables `SECRET`/`GET_DB`, con globales deprecados — **CFG-02**.
- **Plan `06-03`:** Sustituir los handlers generados con `exec()` por closures/`__signature__` como refactor que preserva comportamiento, **custodiado por un snapshot OpenAPI tomado antes y después** — **CFG-03**.
- **Plan `06-04`:** `build_schema` de GraphQL usa un namespace por build y deja de mutar el namespace del módulo — **CFG-04**.
- **Plan `06-05`:** Documentación explícita de las fronteras de confianza de `Filter.raw`, `Query` y `db.fn.*` — **CFG-05**.
- **Success Criterion 1:** dos instancias de `ConnectionRegistry` en el mismo proceso resuelven a sus propias bases de datos, y el shim global deprecado sigue funcionando con un `DeprecationWarning`.
- **Success Criterion 2:** `SecurityConfig` es frozen y los guards se construyen desde configuración inyectada; mutar `SECRET`/`GET_DB` **deja de cambiar el comportamiento**.
- **Success Criterion 3:** el esquema OpenAPI generado es **idéntico antes y después** del rewrite `exec()`→closure, y los path params siguen validando.
- **Success Criterion 4:** dos llamadas sucesivas a `build_schema` **no mutan** estado del namespace de módulo de GraphQL.
- **Success Criterion 5:** las fronteras de confianza de `Filter.raw`, `Query` y `db.fn.*` están documentadas **con ejemplos seguros e inseguros**.
- **Ordenamiento interno duro:** "Level 4 (config) must precede Level 5 (codegen) so public signatures change once" (`ROADMAP:306`).
- **Dependencia:** "Depends on: Phase 1 (independent of Phases 4/5; may run in parallel)" (`ROADMAP:306`). Fase 1 está completa (gates ruff/mypy/pytest verdes, verificado: `ruff check .` → "All checks passed!").
- **Modo:** standard. **Research:** needed — "`__signature__` for FastAPI path params is a community pattern (MEDIUM confidence) and GraphQL namespace isolation is explicitly untested" (`ROADMAP:317`). **Esta investigación cierra ambos flags.**

### Constraints de PROJECT.md (vinculantes)

- **Contrato de importación diferida:** el núcleo no puede adquirir dependencias duras de las capas opcionales. `context.py` **no puede** importar `pool.py` a nivel de módulo (hoy lo hace dentro de `resolve_db`, `context.py:49`); `security/config.py` **no puede** importar `fastapi`/`PyJWT` a nivel de módulo (hoy `guard.py` los importa dentro de cada dependency, `guard.py:36,64`).
- **0.x:** los cambios incompatibles se permiten pero **deben** documentarse en `CHANGELOG.md` (sección `[Unreleased]`, ya en uso con 2 entradas de comportamiento).
- **Sin regresiones de corrección:** "las optimizaciones no pueden regresar la corrección". El rewrite `exec()`→closure es **behavior-preserving** y debe demostrarlo.
- **Alcance:** sin nuevos motores; sin declarar 1.0.

### the agent's Discretion (deducido; no hay CONTEXT.md)

- Firma exacta de `ConnectionRegistry` (`__slots__`/atributo, `resolve()` de instancia vs. estático, si acepta `default_db` en el constructor) y si `Model._get_db` aprende a recibir un registry.
- Si `resolve_db()` conserva firma sin parámetros o gana `registry: ConnectionRegistry | None = None`.
- Qué campo exacto lleva `SecurityConfig` (¿`algorithms`? ¿rotación por callable/iterable de secretos, como sugiere `PITFALLS.md:435`?).
- Si `get_default_db()` emite `DeprecationWarning` al leer o solo `set_default_db()` al escribir.
- Si `create_crud` y `build_schema` ganan un parámetro `config=`/`registry=` como composition root (lo sugiere `.planning/research/ARCHITECTURE.md:419-420`; **ningún requisito CFG lo exige**).
- **Qué plan posee el `exec()` de `graphql/schema.py:103`.** El ROADMAP atribuye el `S102` de `graphql/schema.py` a CFG-03 (`pyproject.toml:163-167` lo comenta, `01-01-SUMMARY.md:136`), pero el texto de `06-04` es el dueño del archivo. Ver **Open Question 3**.
- Si se levanta el cap `PyJWT>=2.8,<2.13` y se retiran los 5 `--ignore` GHSA de `ci.yml:241-245` (propiedad declarada de Fase 6 / CFG-02 en `STATE.md:117,226`, `01-VERIFICATION.md:70`, `01-02-SUMMARY.md:282,290`, **pero ausente del texto de la Fase 6 en ROADMAP**). Ver **Open Question 1**.
- Si se levantan las supresiones de gates asignadas a la fase: `ruff` `S102`/`B008` (`pyproject.toml:163-170,182-184`) y las 5 entradas del ratchet mypy (`pyproject.toml:257,266,276-279`). Ver **Open Question 4**.

### Deferred Ideas (OUT OF SCOPE)

- **Eliminar** los globales `SECRET`/`GET_DB`/`_default_db` (no solo deprecarlos) → Fase 8 `REL-01` (`ROADMAP:370`): la release 0.2.7 los emite como `DeprecationWarning` de runtime y 0.3.0 los retira.
- Congelar los globales con un `freeze()` que lanza `RuntimeError` → **anti-patrón explícito** (`PITFALLS.md:430-439`, Pitfall 16): rompe los tests y sigue siendo incorrecto para multi-tenant/rotación.
- `_FIELD_ADAPTERS` como `WeakKeyDictionary` y `QueryTracer._latencies` acotado → Fase 7 `PERF-04` (`ROADMAP:349`).
- **Extender** el codegen REST/GraphQL basado en `exec()` → **Out of Scope explícito** (`REQUIREMENTS.md:125`): "Se sustituye, no se amplía".
- Reciclado de conexiones del pool → Fase 4/v2 `RELI-03`.
- Ampliar el scope de la documentación de fronteras a alias de `QueryBuilder` → fuera de CFG-05 (`02-VERIFICATION.md:309`).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CFG-01 | `ConnectionRegistry` reemplaza el global `_default_db`, con shims retrocompatibles deprecados | §2: el global vive en `context.py:20`; lo escriben `set_default_db` (`:26-29`) y lo leen `get_default_db` (`:32-34`) y `resolve_db` (`:61-62`). Forma del registry, cadena de resolución preservada, shims y riesgo de `filterwarnings=["error"]` (`pyproject.toml:62-63`) documentados. |
| CFG-02 | `SecurityConfig` inmutable y factorías de guards reemplazan los globales mutables `SECRET`/`GET_DB` | §3: globales en `guard.py:14-15`, leídos solo por `_resolve` (`:24-31`); factorías ya existen con parámetros explícitos (`:34,57`). Diseño frozen verificado end-to-end; los 401/403 se lanzan **dentro** de `guard.py:50,70`, no en `http/errors.py`. |
| CFG-03 | Los handlers generados con `exec()` se sustituyen por closures/`__signature__` con snapshot OpenAPI antes/después | §4: **dos** sitios `exec()` — `http/routes.py:73` y `graphql/schema.py:103`. Equivalencia OpenAPI verificada empíricamente (JSON idéntico) y SDL GraphQL idéntica. Mecanismo de snapshot con syrupy (ya es dependencia dev fijada, `pyproject.toml:303`). |
| CFG-04 | `build_schema` usa un namespace por build y deja de mutar el namespace del módulo | §5: mutación en `graphql/schema.py:178,185` sobre `sys.modules["encino_orm.graphql.schema"]`; verificado que el namespace del módulo acumula `Agente`/`AgenteFilter`/… entre builds. Solución de módulo sintético verificada (cero mutación, cero fuga, dos schemas funcionales). |
| CFG-05 | Fronteras de confianza de `Filter.raw`, `Query` y `db.fn.*` documentadas con ejemplos seguros/inseguros | §6: `Filter.raw` (`filter.py:113-115`) **no tiene docstring** y su fragmento se reemite verbatim (`_rebind_raw`, `:218-224`); `Query` documenta su contrato y límites (`query.py:8-47`); `SqlFunctions` (`sql.py:33-42`) ya declara "texto de confianza". Verificado que **ningún parser HTTP/GraphQL emite `raw`** (grep: 0 construcciones en `encino_orm/`). |
</phase_requirements>

## Summary

La fase toca **cinco** superficies pequeñas y bien delimitadas, no una refactorización transversal:

1. **Un global de proceso** para la conexión por defecto (`context.py:20`) leído en un único punto (`resolve_db`, `context.py:61-62`).
2. **Dos globales de proceso** para el secreto JWT y la dependency de conexión (`guard.py:14-15`), leídos en un único punto (`_resolve`, `guard.py:24-31`).
3. **Dos sitios `exec()`**: `http/routes.py:73` (handlers CRUD de FastAPI) y `graphql/schema.py:103` (resolvers de PK de Strawberry).
4. **Dos `setattr` sobre un módulo importado** (`graphql/schema.py:178,185`) que acumulan tipos generados en el namespace de `encino_orm.graphql.schema`.
5. **Cero documentación de frontera** en los escapes SQL (`Filter.raw` no tiene docstring; `Query`/`db.fn.*` la tienen parcial).

**Primary recommendation:** (a) `ConnectionRegistry` con estado de instancia (`_default_db`) + `resolve()` de instancia, un `_registry` de módulo como default, y `set_default_db`/`get_default_db` como shims que emiten `DeprecationWarning`; (b) `SecurityConfig` frozen en un módulo nuevo `encino_orm/security/config.py` con factorías `security_dependencies(config)` que cierran sobre la config, manteniendo la firma legacy `get_current_user(secret=None, get_db=None)` (ruta explícita, sin warning) y reservando el warning para el fallback a los globales; (c) `exec()` → closures con `__signature__` construida con `inspect.Parameter`/`Signature` (mismos nombres, mismas anotaciones, `__name__="handler"`/`"resolver"`), custodiado por un snapshot **syrupy** del OpenAPI (HTTP) y del SDL (GraphQL) capturados **antes** del rewrite; (d) namespace GraphQL por build vía `types.ModuleType` + `sys.modules[nombre_unico]` + `try/finally` con `del sys.modules[nombre]` tras `strawberry.Schema(...)`; (e) `docs/trust-boundaries.md` nueva + docstring de `Filter.raw` + referencias cruzadas, con un test que congela que los parsers HTTP/GraphQL nunca emiten `raw`.

**Hallazgo que cambia la forma del plan (CFG-03):** el `exec()` **no está solo en HTTP**. `graphql/schema.py:103` genera los resolvers de `get`/`update`/`delete` por PK con `exec()`, y su `sig` (`:54`) codifica los tipos de los argumentos GraphQL. Se verificó empíricamente que la versión closure + `__signature__` produce **SDL idéntica** (`schema.as_str() == schema_after.as_str()` → `True`) y que `get`/`update`/`delete`/`not-found` se comportan igual. Por tanto CFG-03 tiene **dos** sitios de rewrite y necesita **dos** guardianes (OpenAPI + SDL), no uno.

**Hallazgo que acota el riesgo (CFG-02):** `install_error_handlers` (`http/errors.py:7-22`) **no consume configuración de seguridad** — mapea `ValidationError`→422, `FailOnUpdate`→400 y `QueryError`→400. Los 401/403 de autenticación/autorización se lanzan como `HTTPException` **dentro** de `guard.py:50,70`. La premisa "`install_error_handlers` consume el `SecurityConfig`" es **falsa**; el contrato a preservar es el mapeo interno del guard.

**Hallazgo que acota el riesgo (CFG-05):** `Filter.raw` **no se construye en ninguna parte** de `encino_orm/` (grep de `Filter.raw`/`.raw(` → 1 coincidencia, y es texto de docstring en `sql.py:37`). Los parsers `http/parsing.py` (`_OP_MAP:9-20`, `_apply_op:23-32`) y `graphql/filters.py` (`_apply_op:124-149`) usan **conjuntos cerrados de operadores** y no pueden emitir `raw`. La sugerencia de `TS-22` ("añadir un guard de lint/CI que los parsers nunca emitan `raw`") se satisface con un **test de regresión** barato, no con infraestructura nueva.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Resolución de la conexión por defecto (`ConnectionRegistry`) | `encino_orm.context` | `Model._get_db` (consumidor) | Es el módulo que ya posee la cadena de resolución y el contextvar ambiente; `Model` solo consume `resolve_db()`. |
| Estado ambiente por tarea (`bind`/`session`/`_current_connection`) | `contextvars` (`context.py:23`, `pool.py:34`) | `pool.py` | Ya es la primitiva correcta; la fase **no** la sustituye, la conserva como el nivel de precedencia más alto. |
| Configuración de seguridad (`SecurityConfig`) | `encino_orm.security.config` (nuevo) | `security/guard.py` (factorías) | La config es un value object inmutable; los guards son adaptadores de FastAPI que la consumen. |
| Emisión/verificación JWT | `security/jwt.py` (sin cambios de firma) | `security/guard.py` (pasa `config.secret`/`config.algorithms`) | `jwt.py` ya recibe el secreto explícitamente (`jwt.py:51-52,74`); no necesita saber de la config. |
| Mapeo de errores HTTP (401/403/422/400) | `security/guard.py` (401/403) + `http/errors.py` (422/400) | — | Dos fronteras distintas; la fase solo toca la primera. |
| Generación de handlers REST | `encino_orm.http.routes` | `http/__init__.create_crud` (composition root) | El handler y su `__signature__` se construyen en `routes.py`; `create_crud` solo monta. |
| Generación de resolvers GraphQL | `encino_orm.graphql.schema` | `graphql/types.py`/`filters.py` (reciben `module_name`) | `_pk_resolver` construye el resolver; los builders de tipos solo usan `module_name` para `strawberry.lazy`. |
| Namespace de tipos GraphQL | `encino_orm.graphql.schema` (namespace sintético por build) | `strawberry` (`LazyType.resolve_type`) | El namespace debe ser visible a `importlib.import_module` durante la construcción del schema. |
| Fronteras de confianza SQL | `docs/` (prosa) | docstrings de `filter.py`/`query.py`/`sql.py` | Es documentación de contrato, no un control técnico nuevo. |

## Current State Map (deliverable #1)

### A. Inventario de globales mutables a nivel de módulo

| # | Global | Definición | Escrito por | Leído por | Exportado |
|---|--------|-----------|-------------|-----------|-----------|
| G1 | `_default_db` | `context.py:20` (`_default_db = None`) | `set_default_db` (`context.py:26-29`, con `global _default_db`) | `get_default_db` (`context.py:32-34`), `resolve_db` (`context.py:61-62`) | Indirecto: `set_default_db`/`get_default_db` en `__init__.py:2,78,91` |
| G2 | `SECRET` | `security/guard.py:14` (`SECRET: str \| None = None`) | La app anfitriona (`guard.SECRET = ...`, documentado en `docs/integrations.md:112`) | `_resolve` (`guard.py:25`) | **No** está en `security/__init__.py:14-33`; solo accesible como `guard.SECRET` |
| G3 | `GET_DB` | `security/guard.py:15` (`GET_DB = None`) | La app anfitriona (`docs/integrations.md:113`) | `_resolve` (`guard.py:28`) | **No** exportado |

**No son globales mutables de configuración (fuera de alcance, se conservan):**
- `context.py:23` `_ambient_db = contextvars.ContextVar("encino_orm_ambient_db", default=None)` — estado ambiente por tarea, no global.
- `pool.py:34` `_current_connection = contextvars.ContextVar("encino_orm_pool_connection", default=None)` — afinidad de transacción por tarea.
- `observability.py:8` `_trace_id_var` — correlación por tarea.
- `model/model.py:28-31` `_COLUMN_MAPS`, `_FIELD_ADAPTERS`, `_MISSING` — cachés de clase (Fase 7 `PERF-04` posee `_FIELD_ADAPTERS`).

**Cadena de resolución actual (`resolve_db`, `context.py:47-63`), a preservar tal cual:**
```
1. _current_connection.get()  →  si es PooledConnection, devuelve conn.driver  (:51-55)
2. si no es None, devuelve conn                                              (:56-57)
3. _ambient_db.get() (bind/session)                                          (:58-60)
4. _default_db (set_default_db)                                              (:61-62)
5. raise ConnectionError("Sin conexión: pasa `db`, usa `bind()`, `set_default_db()` o `session()`")  (:63)
```

**Consumidor único:** `Model._get_db` (`model/model.py:210-220`) llama `resolve_db()` cuando el modelo no recibió `db` explícito y **cachea** el resultado en el slot privado `_db` (`:216-219`). No hay ningún otro lector de `_default_db` en `encino_orm/` (grep verificado).

### B. Sitios `exec()` (codegen)

| # | Sitio | Función contenedora | Fuente generada | Namespace | Invocado desde | Guard ruff |
|---|-------|--------------------|-----------------|-----------|----------------|------------|
| E1 | `http/routes.py:73` (`exec(src, ns)`) | `_build_path_handler` (`:25-74`) | `decl`/`body` en `:34-63`, unidos en `src` (`:65`) | `ns` en `:66-72` (`_cursor`, `model`, `HTTPException`, `Depends`, `get_db`) | `register_crud` (`:107` get, `:110` put, `:113` delete) | `S102` + `B008` en `pyproject.toml:166` |
| E2 | `graphql/schema.py:103` (`exec(src, ns)`) | `_pk_resolver` (`:50-104`) | `decl`/`body` en `:57-86`, unidos en `src` (`:88`) | `ns` en `:89-102` (`__name__`, `Info`, `Optional`, `strawberry`, `db_session`, `cursor`, `model`, `gtype`, `itype`, `NotFoundError`, `_pk_t{i}`) | `_get_resolver` (`:107-108`), `_update_resolver` (`:123-124`), `_delete_resolver` (`:127-128`) → `_build_query` (`:141`) y `_build_mutation` (`:156,159`) | `S102` en `pyproject.toml:167` |

**Contrato que la firma generada codifica (E1):**
- `get`: `handler({pk}: {int|str}, db=Depends(get_db))` — `routes.py:35`.
- `put`: `handler({pk}: {int|str}, data: model, db=Depends(get_db))` — `:43`.
- `delete`: `handler({pk}: {int|str}, physical: bool = False, db=Depends(get_db))` — `:56`.
- El tipo del path param sale de `_path_type` (`routes.py:15-18`) = `int` si `_base_type(annotation)` es `int`, si no `str`.
- El path es `prefix + _path_suffix(model)` = `"/" + "/".join("{"+f+"}" for f in _primary_key)` (`routes.py:21-22`).
- `register_crud` **no** genera `create`/`list_` con `exec()`; esas dos son funciones normales (`:86-105`) con `db=Depends(get_db)` en el default (origen de los 2 `B008`).

**Contrato que la firma generada codifica (E2):**
- `get`: `resolver(info: Info, {pk}: {_pk_t{i}}) -> Optional[gtype]` — `:58`.
- `update`: `resolver(info: Info, {pk}: {_pk_t{i}}, data: itype) -> gtype` — `:65`.
- `delete`: `resolver(info: Info, {pk}: {_pk_t{i}}) -> bool` — `:78`.
- `_pk_arg_type` (`:42-47`) = `strawberry.ID` para `id`, si no `DATATYPE_TO_TYPE.get(dt, str)`.
- La coerción `id=int(id)` se hace **dentro del cuerpo generado** (`:55`), no en la firma.

### C. Mutación del namespace del módulo GraphQL

`build_schema` (`graphql/schema.py:164-194`):
```python
import sys                                   # :169  (import local)
module_name = __name__                       # :171  -> "encino_orm.graphql.schema"
module = sys.modules[module_name]            # :172
...
setattr(module, model.__name__, typ)         # :178  (ObjectType)
...
setattr(module, f"{model.__name__}Filter", ftype)  # :185 (input de filtro)
```
**Verificado empíricamente:** tras `build_schema([Region, Agente])` el namespace del módulo gana `{'Agente','AgenteFilter','Region','RegionFilter'}`; un segundo `build_schema([Other])` **acumula** `{'Other','OtherFilter', ...}`. Es decir, el namespace del módulo es un **estado global de proceso** que crece con cada build y queda sobrescrito por el último. Los tipos generados usan `strawberry.lazy("encino_orm.graphql.schema")` (`types.py:41,46`; `filters.py:108`) y `LazyType.resolve_type()` hace `importlib.import_module(self.module).__dict__[self.type_name]` — por eso la mutación es necesaria hoy.

**Por qué dos builds sucesivos interfieren:** `StrawberryAnnotation.resolve()` cachea el resultado (`strawberry/annotation.py:152-154`, `__resolve_cache__`), así que un schema **ya construido** sigue funcionando (verificado: schema A ejecutó relaciones correctamente después del build B). El daño observable es (i) el namespace del módulo acumula basura, (ii) el nombre `Region` pasa a apuntar al tipo del **último** build, y (iii) cualquier resolución lazy diferida que ocurra después del segundo build resolvería al tipo equivocado. El criterio 4 mide exactamente (i).

### D. Superficie de documentación de fronteras (CFG-05)

| Escape | Anchor | Validación hoy | Docstring hoy |
|--------|--------|----------------|---------------|
| `Filter.raw(sql, params)` | `model/filter.py:113-115`; reemisión en `_rebind_raw` (`:218-224`) | **Ninguna** sobre `sql`: solo se reindexan los `{n}` con `re.sub(r"\{(\d+)\}", ...)`. El fragmento se emite **verbatim**. | **Ausente** (sin docstring) |
| `Query(sql, fields)` | `query.py:8-103` | Cardinalidad estricta de `{n}` vs. `len(values)` (`:79-86`); valores **siempre** ligados (`:88-103`) | Extensa (`:8-47`), incluye las 2 limitaciones conocidas (`:33-46`) |
| `db.fn.*` | `sql.py:33-42` (clase), `_COLUMN_RE` (`:12`), `_col` (`:47-52`) | Allowlist con punto permitido (`^[A-Za-z_][A-Za-z0-9_.]*$`) para nombres de columna | Presente (`:34-42`: "Devuelven **fragmentos SQL** (texto de confianza)") |

## Standard Stack

### Core
| Library | Version (instalada) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| stdlib `inspect` (`Parameter`, `Signature`) | Python ≥3.10 | Construir `__signature__` en los handlers/resolvers generados | Es el mecanismo que FastAPI/Strawberry ya consultan (`fastapi/dependencies/utils.py::get_typed_signature` → `_get_signature` → `inspect.signature`); no requiere dependencia nueva. |
| stdlib `types.ModuleType` + `sys.modules` | Python ≥3.10 | Namespace sintético por build para `strawberry.lazy` | `LazyType.resolve_type()` usa `importlib.import_module(...).__dict__[...]` (verificado en `strawberry/types/lazy_type.py:37-63`); un módulo sintético registrado en `sys.modules` satisface esa ruta sin tocar el módulo real. |
| stdlib `dataclasses.dataclass(frozen=True)` | Python ≥3.10 | `SecurityConfig` inmutable | Ya es el idioma del repo para value objects (`Column`, `Constraint`, `Index`, `Migration` son frozen dataclasses). |
| stdlib `warnings` | Python ≥3.10 | `DeprecationWarning` de los shims | Categoría correcta para deprecaciones (ignorada por defecto fuera de `__main__`/pytest). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `syrupy` | 6.1.1 (fijada en `pyproject.toml:303`) | Snapshot OpenAPI (CFG-03) y SDL GraphQL | Ya es el mecanismo del repo (`tests/__snapshots__/test_sql_snapshots.ambr`); flujo `--snapshot-update` documentado en `tests/test_sql_snapshots.py:12-24`. |
| `httpx` (`ASGITransport`, `AsyncClient`) | 0.28.1 | Probar los guards y los handlers en proceso | Ya es el patrón de `tests/test_security.py:224`, `tests/test_crud.py:133`, `tests/test_pk.py:186`. |
| `fastapi` | 0.141.1 | Objeto bajo prueba | Extra `http`/`security` (`pyproject.toml:26-27`). |
| `strawberry-graphql` | 0.324.4 | Objeto bajo prueba | Extra `graphql` (`pyproject.toml:28`). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Namespace sintético + `sys.modules` (recomendado, verificado) | Referencias directas a las clases de tipo (dos fases: crear todas las clases vacías, luego anotar y aplicar `strawberry.type`) | Eliminaría `strawberry.lazy` por completo (cero `sys.modules`), pero exige mutar `__annotations__` de clases ya creadas y cambiar `_ref_resolver`/`_has_many_resolver` (que hoy devuelven anotaciones lazy, `resolvers.py:49,63`). Más superficie de cambio y **no probado** en esta sesión. Mantener el lazy es menos invasivo. |
| `__signature__` (recomendado, verificado) | `exec()` con `compile(..., "<string>")` o `functools.partial` | `functools.partial` **rompe** el nombre de los params para FastAPI; `exec` es exactamente lo que CFG-03 elimina. `__signature__` es la única vía que conserva nombres+tipos+defaults sin ejecutar código generado. |
| Shims que emiten `DeprecationWarning` al leer/escribir (recomendado) | Sustituir el módulo por un `ModuleType` con `__getattr__`/`__setattr__` (PEP 562 + subclase) | El truco de subclase de módulo funciona pero es no estándar, complica `mkdocstrings`/pickling y añade riesgo sin beneficio: **los nombres pueden seguir siendo atributos normales** porque el objetivo es que *mutarlos no cambie el comportamiento*, y eso se logra cerrando las factorías sobre la config. |
| `SecurityConfig` como dataclass frozen | `NamedTuple` / `attrs` | El repo ya usa frozen dataclasses; `NamedTuple` no aporta y `attrs` sería una dependencia nueva (viola "sin dependencias nuevas"). |

**Installation:**
```bash
# NINGUNA dependencia nueva. CFG-01…05 se implementan con stdlib + lo ya declarado.
# El ÚNICO cambio de dependencia posible es de VERSIÓN, no de paquete:
#   PyJWT>=2.8,<2.13  ->  PyJWT>=2.8,<2.15   (pyproject.toml:26)   [ver Open Question 1]
# Eso exige `uv lock` (uv.lock) y retirar 5 `--ignore` de .github/workflows/ci.yml:241-245.
```

**Version verification:** `[VERIFIED: .venv importlib.metadata, 2026-09-19]` — `fastapi 0.141.1`, `starlette 1.6.0`, `strawberry-graphql 0.324.4`, `httpx 0.28.1`, `pydantic 2.13.4`, `PyJWT 2.12.1`, `syrupy 6.1.1`, CPython **3.13.7**. `[VERIFIED: PyPI index]` — `PyJWT` versiones disponibles: 2.14.0 (latest), 2.13.0, 2.12.1.

## Package Legitimacy Audit

> **No se introduce ningún paquete nuevo.** El único cambio posible es de versión (`PyJWT` 2.12.1 → 2.13.0/2.14.0) sobre una dependencia ya declarada y ya presente en `uv.lock`.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| (ninguno nuevo) | — | — | — | — | — | — |
| `PyJWT` (posible subida de versión) | PyPI | ~11 años (1.0.0 → 2.14.0) | Ampliamente usado | `github.com/jpadilla/pyjwt` | **[OK]** | Aprobado — subir el cap solo si el plan lo decide (Open Question 1) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**⚠️ Advertencia de proceso (verificada en esta sesión):** `slopcheck install <pkg>` **ejecuta un `pip install` real** (`Running: pip install PyJWT`). En este host instaló `PyJWT 2.14.0` a nivel de usuario y desestabilizó el venv; se restauró con `uv sync --all-extras` (`PyJWT 2.12.1`, `git status` limpio, 47 tests verdes). **Para futuras fases: usar `slopcheck scan` o un entorno desechable, nunca `install` sobre el venv del proyecto.**

## Architecture Patterns

### System Architecture Diagram

```
                        App anfitriona (composition root)
                                     │
        ┌────────────────────────────┼──────────────────────────────┐
        │                            │                              │
        ▼                            ▼                              ▼
 ConnectionRegistry(...)     SecurityConfig(secret, get_db)   create_crud(pool, models)
   │  (CFG-01)                    │  (CFG-02)                        │
   │                              │                                  │
   │  set_default()               │  security_dependencies(cfg)      │
   │                              ▼                                  ▼
   │                        get_current_user()/require()      register_crud (CFG-03)
   │                              │                                  │
   │                              │ Depends(...)                     │ closure + __signature__
   │                              │                                  │ (sin exec)
   ▼                              ▼                                  ▼
 ┌──────────────────────────────────────────────┐        ┌──────────────────────────┐
 │ resolve_db(registry=None)  [context.py]      │        │ FastAPI APIRoute         │
 │   1 _current_connection (pool, contextvar)   │        │  inspect.signature(h)    │
 │   2 _ambient_db (bind/session, contextvar)   │        │  -> path params validan  │
 │   3 registry.get_default()  <-- NO global    │        └──────────────────────────┘
 │   4 raise ConnectionError                    │
 └──────────────────────────────────────────────┘
                    │
                    ▼
              Model._get_db()  (model.py:210-220)

 build_schema(models)  (CFG-04)
   │
   ├─ mod = types.ModuleType("encino_orm.graphql._build_<n>")
   ├─ sys.modules[name] = mod              ◄── namespace POR BUILD (no el módulo real)
   ├─ build_type(model, name) / build_filter_input(model, name)
   ├─ strawberry.Schema(...)               ◄── LazyType.resolve_type() importa `name`
   └─ finally: del sys.modules[name]       ◄── sin fuga; el schema ya resolvió y cacheó

 Docs (CFG-05): docs/trust-boundaries.md  ◄── Filter.raw / Query / db.fn.*
```

### Recommended Project Structure
```text
encino_orm/
├── context.py                      # + ConnectionRegistry, resolve_db(registry=None),
│                                   #   shims deprecados con DeprecationWarning
├── __init__.py                     # + exportar ConnectionRegistry (imports + __all__)
├── security/
│   ├── config.py                   # NUEVO: SecurityConfig (frozen) + security_dependencies()
│   ├── guard.py                    # factorías sobre config; firma legacy preservada;
│   │                               #   fallback a globales con DeprecationWarning
│   └── __init__.py                 # + exportar SecurityConfig, security_dependencies
├── http/
│   ├── routes.py                   # _build_path_handler -> closures + __signature__ (sin exec)
│   └── __init__.py                 # sin cambios (o + config=, ver Open Question 2)
└── graphql/
    └── schema.py                   # _pk_resolver -> closures + __signature__ (sin exec);
                                    #   build_schema -> namespace sintético por build
docs/
├── trust-boundaries.md             # NUEVA (CFG-05)
├── reference/{filter,db,sql,context}.md   # + referencias cruzadas
├── integrations.md                 # + ejemplo SecurityConfig (reemplaza guard.SECRET)
└── mkdocs.yml                      # + nav de trust-boundaries.md
tests/
├── test_registry.py                # NUEVO — CFG-01 (criterio 1)
├── test_security.py                # + config frozen + mutación de globales sin efecto (criterio 2)
├── test_http_openapi.py            # NUEVO — CFG-03 (criterio 3)
├── test_graphql_namespace.py       # NUEVO — CFG-04 (criterio 4) + SDL snapshot
├── test_trust_boundaries.py        # NUEVO — CFG-05 (criterio 5): parsers nunca emiten raw
└── __snapshots__/
    ├── test_http_openapi.ambr      # NUEVO — capturado ANTES del rewrite
    └── test_graphql_namespace.ambr # NUEVO — SDL capturada ANTES del rewrite
CHANGELOG.md                        # [Unreleased] (un solo dueño: 06-05)
pyproject.toml                      # gates (un solo dueño: 06-05; ver Pitfall 8)
```

### Pattern 1: `ConnectionRegistry` (CFG-01)
**What:** holder inyectable del "default de proceso"; la precedencia (pool → ambiente → default) no cambia, solo cambia **de dónde sale el default**.
**When to use:** siempre en `resolve_db`; el registry es el único punto que lee `_default_db`.
**Example (forma recomendada):**
```python
# context.py — el import de `pool` sigue siendo perezoso (contrato de importación diferida)
class ConnectionRegistry:
    """Holder inyectable de la conexión por defecto (sin global mutable de proceso)."""
    __slots__ = ("_default_db",)

    def __init__(self, default_db=None):
        self._default_db = default_db

    def set_default(self, db) -> None:
        self._default_db = db

    def get_default(self):
        return self._default_db

    def resolve(self):
        from .pool import PooledConnection, _current_connection  # lazy: import circular
        conn = _current_connection.get()
        if isinstance(conn, PooledConnection):
            return conn.driver
        if conn is not None:
            return conn
        ambient = _ambient_db.get()
        if ambient is not None:
            return ambient
        if self._default_db is not None:
            return self._default_db
        raise ConnectionError(
            "Sin conexión: pasa `db`, usa `bind()`, `session()` o el default del registry"
        )

_registry = ConnectionRegistry()

def resolve_db(registry: ConnectionRegistry | None = None):
    return (registry or _registry).resolve()

def set_default_db(db) -> None:          # shim deprecado
    warnings.warn(
        "set_default_db() está deprecado; usa un ConnectionRegistry explícito",
        DeprecationWarning, stacklevel=2,
    )
    _registry.set_default(db)

def get_default_db():                     # shim deprecado
    warnings.warn(
        "get_default_db() está deprecado; usa ConnectionRegistry.get_default()",
        DeprecationWarning, stacklevel=2,
    )
    return _registry.get_default()
```

### Pattern 2: `SecurityConfig` + factorías (CFG-02)
**What:** value object frozen + closures sobre la config. Los globales sobreviven como **atributos normales** para no romper `guard.SECRET = ...`, pero ya no deciden nada cuando el guard se construyó desde config.
**When to use:** en `get_current_user`/`require`; la firma legacy se conserva.
**Example (verificado end-to-end):**
```python
# security/config.py (NUEVO) — sin imports de fastapi/PyJWT a nivel de módulo
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class SecurityConfig:
    secret: str
    get_db: Callable
    algorithms: tuple[str, ...] = ("HS256",)


# security/guard.py
def security_dependencies(config: SecurityConfig):
    def get_current_user():
        from fastapi import Depends, HTTPException
        from fastapi.security import HTTPBearer
        async def _dep(authorization=Depends(HTTPBearer(auto_error=False)),
                      db=Depends(config.get_db)) -> CurrentUser:
            ...
            payload = verify_token(authorization.credentials, config.secret,
                                   list(config.algorithms))
            ...
        return _dep

    def require(modelo: str, op: str):
        from fastapi import Depends, HTTPException
        async def _dep(user: CurrentUser = Depends(get_current_user())) -> None:
            ...
        return _dep

    return get_current_user, require


# Compatibilidad: la firma actual sigue funcionando (ruta explícita, SIN warning)
def get_current_user(secret: str | None = None, get_db=None):
    if secret is not None or get_db is not None:
        return security_dependencies(_config_or_legacy(secret, get_db))[0]()
    return security_dependencies(_legacy_config_with_warning())[0]()
```

**Verificado empíricamente:** con las factorías cerradas sobre `cfg`, un `200` con token válido, `401` con token inválido y `403` anónimo; **mutar `guard.SECRET` y `guard.GET_DB` después no cambia ninguna respuesta** (sigue `200`); el dataclass frozen lanza `FrozenInstanceError`; el fallback legacy emite exactamente 1 `DeprecationWarning`.

### Pattern 3: `exec()` → closures + `__signature__` (CFG-03)
**What:** misma firma observable (nombres, anotaciones, defaults) construida con `inspect` en vez de compilada.
**When to use:** `http/routes.py:_build_path_handler` **y** `graphql/schema.py:_pk_resolver`.
**Example (HTTP, verificado: OpenAPI idéntica):**
```python
# http/routes.py
from inspect import Parameter, Signature

def _build_path_handler(model, get_db, op):
    from fastapi import Depends, HTTPException
    pk = list(model._primary_key)

    if op == "get":
        async def handler(**kwargs):
            db = kwargs.pop("db")
            obj = await _cursor(model, db, **kwargs).load()
            if not obj._exists:
                raise HTTPException(404, detail="no encontrado")
            return obj
    elif op == "put":
        async def handler(data, **kwargs):
            db = kwargs.pop("db")
            ...
    else:
        async def handler(physical: bool = False, **kwargs):
            db = kwargs.pop("db")
            ...

    params = [Parameter(f, Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=_path_type(model, f)) for f in pk]
    if op == "put":
        params.append(Parameter("data", Parameter.POSITIONAL_OR_KEYWORD, annotation=model))
    if op == "delete":
        params.append(Parameter("physical", Parameter.POSITIONAL_OR_KEYWORD,
                                default=False, annotation=bool))
    params.append(Parameter("db", Parameter.POSITIONAL_OR_KEYWORD, default=Depends(get_db)))
    handler.__signature__ = Signature(params)
    handler.__name__ = "handler"          # ← preserva el operationId de OpenAPI
    handler.__qualname__ = "handler"
    return handler
```
**Example (GraphQL, verificado: SDL idéntica):**
```python
# graphql/schema.py
def _pk_resolver(model, gtype, op, itype=None):
    pk = list(model._primary_key)
    arg_types = {f: _pk_arg_type(model, f) for f in pk}
    def _cast(kw):                       # replica `id=int(id)` del código generado (:55)
        return {f: (int(kw[f]) if f == "id" else kw[f]) for f in pk}

    if op == "get":
        async def resolver(info, **kwargs): ...
        ret = Optional[gtype]
    elif op == "update":
        async def resolver(info, data, **kwargs): ...
        ret = gtype
    else:
        async def resolver(info, **kwargs): ...
        ret = bool

    params = [Parameter("info", Parameter.POSITIONAL_OR_KEYWORD, annotation=Info)]
    params += [Parameter(f, Parameter.POSITIONAL_OR_KEYWORD, annotation=arg_types[f]) for f in pk]
    if op == "update":
        params.append(Parameter("data", Parameter.POSITIONAL_OR_KEYWORD, annotation=itype))
    resolver.__signature__ = Signature(params, return_annotation=ret)
    resolver.__name__ = "resolver"
    return resolver
```
**Why it works (cita verificada):** `fastapi/dependencies/utils.py::_get_signature` llama `inspect.signature(call, eval_str=True)`, que devuelve `__signature__` tal cual; `get_typed_annotation` solo transforma anotaciones que sean `str`, así que pasar **objetos de tipo reales** evita cualquier necesidad de `__globals__`. Strawberry lee la firma del resolver para derivar argumentos GraphQL, y con anotaciones reales + `return_annotation` produce el mismo SDL.

### Pattern 4: Namespace GraphQL por build (CFG-04)
**What:** módulo sintético único por build, registrado en `sys.modules` solo mientras se construye el schema.
**When to use:** en `build_schema`, sustituyendo `setattr(module, ...)`.
**Example (verificado: 0 mutaciones, 0 fugas, 2 schemas funcionales):**
```python
# graphql/schema.py
_build_counter = itertools.count(1)

def build_schema(models, *, auto_camel_case: bool = False) -> strawberry.Schema:
    name = f"encino_orm.graphql._build_{next(_build_counter)}"
    mod = types.ModuleType(name)
    mod.__package__ = __package__          # solo relevante si el nombre fuera relativo
    sys.modules[name] = mod
    try:
        type_map = {}
        for model in models:
            typ = build_type(model, name)
            type_map[model] = typ
            setattr(mod, model.__name__, typ)

        input_map = {m: build_input(m) for m in models}
        filter_map = {}
        for model in models:
            ftype = build_filter_input(model, name)
            filter_map[model] = ftype
            setattr(mod, f"{model.__name__}Filter", ftype)

        query = _build_query(models, type_map, filter_map)
        mutation = _build_mutation(models, type_map, input_map)
        return strawberry.Schema(
            query=query, mutation=mutation,
            config=StrawberryConfig(auto_camel_case=auto_camel_case),
        )
    finally:
        del sys.modules[name]              # el schema ya resolvió y cacheó sus LazyType
```
**Why it works:** `LazyType.resolve_type()` (`strawberry/types/lazy_type.py:37-63`) hace `importlib.import_module(self.module).__dict__[self.type_name]`; un módulo ya presente en `sys.modules` se devuelve sin pasar por los finders. `StrawberryAnnotation.resolve()` cachea (`strawberry/annotation.py:152-154`) y el `SchemaConverter` resuelve los lazy durante la construcción (`schema/schema_converter.py:1190-1197`), por lo que el `del` posterior es seguro **para los caminos ejercitados** (relaciones, `has_many`, inputs de filtro autorreferentes, mutations y `as_str()`/SDL — todos verificados tras el `del`).

### Anti-Patterns to Avoid
- **Congelar los globales en vez de inyectar** (`PITFALLS.md:430-439`): un `freeze()` que lanza `RuntimeError` rompe los tests existentes y no resuelve multi-tenant ni rotación de clave.
- **Sustituir el módulo `guard` por una subclase con `__getattr__`/`__setattr__`:** innecesario (basta con que la config gané), no estándar, y complica `mkdocstrings` (la doc se genera con `mkdocstrings[python]`, `pyproject.toml:289`).
- **`functools.partial` como sustituto de `__signature__`:** pierde los nombres de los parámetros y FastAPI deja de reconocer path params.
- **Dejar que la closure se llame distinto de `handler`/`resolver`:** cambia el `operationId` de OpenAPI (`generate_unique_id` usa `route.name`, que sale de `endpoint.__name__`) y rompe el snapshot.
- **`sys.modules` sintético sin `try/finally`:** un fallo a mitad de build deja un módulo huérfano en `sys.modules`.
- **Emitir `DeprecationWarning` en el camino caliente** (`resolve_db`, cada operación): bajo `filterwarnings=["error"]` (`pyproject.toml:62-63`) tumba la suite; el warning debe vivir **solo** en los shims y en el fallback legacy, nunca en `resolve()`/`_dep()`.
- **Migrar `db=Depends(get_db)` a `Annotated` en `create`/`list_` sin snapshot:** es behavior-preserving (verificado con `ruff`), pero debe ir bajo el mismo snapshot OpenAPI.

### Pattern 5 (opcional): `Annotated` para levantar `B008`
Verificado con `ruff check --select B008`: `db=Depends(get_db)` dispara `B008`; `db: Annotated[int, Depends(get_db)]` **no**. Es la vía para retirar los `per-file-ignores` `B008` de `routes.py` y `guard.py` (asignados a Fase 6 en `pyproject.toml:164-170,182-184`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Firma de un handler generado | Concatenar strings y `compile()`/`exec()` | `inspect.Parameter` + `inspect.Signature` en `__signature__` | Es exactamente lo que FastAPI/Strawberry leen; sin `S102`, sin `__globals__` frágil, sin `NameError` de mypy. |
| Namespace para `strawberry.lazy` | Un dict global de tipos o `globals()` del módulo | `types.ModuleType` + `sys.modules[nombre_único]` | `LazyType.resolve_type` usa `importlib.import_module`; cualquier otra cosa exige parchear Strawberry. |
| Deprecación de los shims | Un flag `_deprecated_called` o un `RuntimeError` | `warnings.warn(..., DeprecationWarning, stacklevel=2)` | Categoría correcta, silenciada por defecto para el usuario final, y `pytest.warns` la verifica. |
| Snapshot del contrato HTTP | Comparar dos `dict` a mano en el test | `syrupy` (ya fijado) con `--snapshot-update` revisado | Un snapshot ausente **falla** en syrupy (sound); el diff queda versionado y revisable (`tests/test_sql_snapshots.py:12-24`). |
| Verificar "no muta el namespace" | `assert not hasattr(module, "Region")` | `set(vars(modulo))` antes/después | Mide la propiedad real (acumulación) en vez de un síntoma. |
| Guard anti-`raw` en los parsers | Un plugin de ruff o un script de CI | Un test que recorre los `_OP_MAP`/`_apply_op` y afirma que ningún op produce `raw` | Los parsers usan conjuntos cerrados (`parsing.py:9-20`, `graphql/filters.py:124-149`); el test es más barato y más preciso. |

**Key insight:** el trabajo hecho a mano a evitar es **la introspección de firmas**. Tanto FastAPI como Strawberry ya resuelven parámetros vía `inspect.signature`; el `exec()` era una forma indirecta de construir esa firma. `__signature__` es la vía directa y es el único cambio que preserva el contrato observable (verificado byte a byte en OpenAPI y SDL).

## Runtime State Inventory

> Fase de **refactor + eliminación de globales**: no hay rename de strings, pero sí cambia el estado de procesos vivos y los artefactos versionados.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | Ninguno — la conexión por defecto y la config de seguridad son estado **en memoria** del proceso (`_default_db`, `SECRET`, `GET_DB`). | Ninguna migración. |
| **Live service config** | `docs/integrations.md:112-113` documenta `guard.SECRET = ...` / `guard.GET_DB = ...` como el modo de configuración de una app anfitriona. Es configuración **de código de la app**, no de un servicio externo. | Actualizar la doc al patrón `SecurityConfig` (06-05) manteniendo el ejemplo legacy marcado como deprecado. |
| **OS-registered state** | Ninguno — sin tareas programadas, servicios ni procesos registrados. | Ninguna. |
| **Secrets/env vars** | Ninguno embebido en el repo. Las variables `ENCINO_ORM_*` son de tests (`tests/conftest.py:28`) y no cambian. **Nota de seguridad:** al deprecar `SECRET`, el mensaje del `DeprecationWarning` **no** debe incluir el valor del secreto. | Ninguna; verificar el texto del warning. |
| **Build artifacts / installed packages** | `uv.lock` (si se sube el cap de `PyJWT`, Open Question 1). `dist/` local con artefactos de 0.2.5/0.2.6 (irrelevante). | `uv lock` + `uv lock --check`; retirar los 5 `--ignore` de `ci.yml:241-245`. |
| **Configuración de gates** | `pyproject.toml`: `per-file-ignores` `S102`/`B008` (`:163-170`), `B008` de `guard.py` (`:170`), `B008`/`S105` de `tests/test_security.py` (`:182-184`); ratchet mypy con `encino_orm.security.models` (`:257`), `encino_orm.graphql.*` (`:266`), `encino_orm.http.routes` + `encino_orm.http.parsing` + `encino_orm.security.guard` (`:276-279`). | Retirar cada entrada **cuando su código lo permita** y medir con `uv run ruff check .` + `uv run mypy encino_orm`; si queda un residual ajeno, dejar la causa escrita (precedente `04-04` en `pyproject.toml:249-256`). Ver Open Question 4. |
| **Documentación** | `docs/integrations.md:107-122` (guard legacy), `docs/reference/context.md` (stubs de `set_default_db`/`get_default_db`), `docs/reference/filter.md`/`sql.md`/`db.md` (stubs sin fronteras de confianza), `mkdocs.yml:51-83` (nav). | Actualizar en 06-05; `mkdocs build --strict` es el gate (`.github/workflows/docs.yml`). |
| **Snapshots/golden** | `tests/__snapshots__/test_sql_snapshots.ambr` pinea SQL de los seis dialectos. **El rewrite `exec()`→closure no toca SQL**; el aislamiento de namespace no toca SQL. | Ninguna regeneración esperada; verificar que no cambia. Los snapshots **nuevos** (OpenAPI, SDL) van en el mismo commit que su test (`tests/test_sql_snapshots.py:17-19`). |

**Canonical question:** *después de cambiar el código, ¿qué sistemas en runtime siguen con el estado viejo?* → **Ninguno en runtime** (todo el estado es efímero y por proceso). Lo que sobrevive son los **artefactos versionados**: `uv.lock`/`ci.yml` (si sube el cap de PyJWT), el bloque de gates de `pyproject.toml`, los snapshots nuevos, la documentación y el `CHANGELOG.md`.

## Common Pitfalls

### Pitfall 1: `filterwarnings = ["error"]` convierte cada `DeprecationWarning` en un fallo de suite
**What goes wrong:** se añade el warning a `set_default_db` y de repente `tests/test_singleton.py` falla en 5 sitios **más** su fixture autouse de limpieza (`test_singleton.py:17-20`), y cualquier test nuevo que use la ruta legacy también.
**Why it happens:** `pyproject.toml:62-63` fija `filterwarnings = ["error"]`.
**How to avoid:** (i) los tests que ejercitan la ruta legacy envuelven la llamada en `with pytest.warns(DeprecationWarning):`; (ii) el teardown de limpieza usa el camino **no** deprecado (`_registry.set_default(None)` o `ConnectionRegistry().set_default(None)`); (iii) **nunca** emitir warnings en `resolve()`/`_dep()` (camino caliente).
**Warning signs:** `DeprecationWarning: set_default_db() está deprecado` como causa de fallo en `test_singleton.py`.
**Verificado empíricamente:** un `warnings.warn(..., DeprecationWarning)` sin envolver **falla** el test; con `pytest.warns` pasa.

### Pitfall 2: el snapshot OpenAPI capturado **después** del rewrite "bendice" una regresión
**What goes wrong:** el plan escribe el test, hace el rewrite, corre `--snapshot-update` y el `.ambr` nace ya del código nuevo: el guardián del criterio 3 no prueba nada.
**Why it happens:** syrupy genera el snapshot en la primera corrida si se pasa `--snapshot-update`.
**How to avoid:** orden estricto en `06-03`: (1) escribir `tests/test_http_openapi.py` y generar/commitear el `.ambr` **contra el `exec()` actual**; (2) reescribir `routes.py`; (3) correr el test **sin** `--snapshot-update` — debe pasar con **diff cero** en el `.ambr`. Un diff = contrato cambiado.
**Warning signs:** el commit del rewrite incluye cambios en `tests/__snapshots__/*.ambr`.

### Pitfall 3: el `operationId` de OpenAPI depende de `endpoint.__name__`
**What goes wrong:** se nombra la closure `get_handler`/`_get` en vez de `handler` y el snapshot falla por `operationId` distinto, aunque el comportamiento sea idéntico.
**Why it happens:** FastAPI deriva `route.name` de `endpoint.__name__` y `generate_unique_id` lo usa para el `operationId`.
**How to avoid:** fijar `handler.__name__ = handler.__qualname__ = "handler"` (y `resolver.__name__ = "resolver"` en GraphQL). **Verificado:** con `__name__="handler"` el JSON de OpenAPI es idéntico byte a byte.

### Pitfall 4: `**kwargs` en la closure sin `__signature__` = cero path params
**What goes wrong:** se escribe `async def handler(**kwargs)` "para simplificar" y FastAPI deja de ver `{id}` como path param: la ruta no valida y el handler recibe todo por kwargs.
**Why it happens:** FastAPI construye `Dependant` desde `inspect.signature`; `**kwargs` no declara parámetros nombrados.
**How to avoid:** la `Signature` explícita **debe** listar cada PK, más `data` (put), `physical` (delete) y `db`, en el **mismo orden** que el código generado (`routes.py:35,43,56`). **Verificado:** `GET /api/regiones/abc` → 422 y `GET /api/memberships/abc/2` → 422 (PK compuesta).

### Pitfall 5: `Depends(...)` en `__signature__` debe ser una instancia real, no una anotación
**What goes wrong:** se pone `annotation=Depends(get_db)` en vez de `default=Depends(get_db)` y FastAPI trata el parámetro como path/query param.
**Why it happens:** FastAPI detecta dependencias por `isinstance(param.default, params.Depends)`.
**How to avoid:** `Parameter("db", Parameter.POSITIONAL_OR_KEYWORD, default=Depends(get_db))` sin `annotation`. **Verificado** (200/401/403 con inyección real).

### Pitfall 6: el namespace sintético se borra antes de que Strawberry termine de resolver
**What goes wrong:** se hace `del sys.modules[name]` antes de `strawberry.Schema(...)` (o no se hace nunca, y `sys.modules` crece sin límite).
**Why it happens:** `LazyType.resolve_type()` se invoca durante la construcción (`schema/schema_converter.py:1190-1197`) y queda cacheado por `StrawberryAnnotation.__resolve_cache__` (`strawberry/annotation.py:152-154`).
**How to avoid:** registrar **antes** de construir el schema y borrar en un `finally` **después** de que `strawberry.Schema(...)` retorne. **Verificado:** tras el `del`, relaciones, `has_many`, filtros autorreferentes (`and`/`or`/`not`), mutations y `as_str()` siguen funcionando.
**Riesgo residual:** una ruta de Strawberry no ejercitada (p. ej. `codegen/query_codegen.py:666`, el optimizador de queries) podría resolver un `LazyType` después del `del` y lanzar `ModuleNotFoundError`. Mitigación: el test del criterio 4 debe cubrir `as_str()` + los 4 tipos de operación; si aparece un fallo, conservar el módulo registrado (coste: una entrada de `sys.modules` por build) en vez de romper.

### Pitfall 7: dos registries y `bind()` — la precedencia ambiente gana para **ambos**
**What goes wrong:** se asume que dos `ConnectionRegistry` aíslan por completo, pero dentro de un `bind(db)` o `session(pool)` **cualquier** registry resuelve al ambiente.
**Why it happens:** `_ambient_db` (`context.py:23`) y `_current_connection` (`pool.py:34`) son contextvars de módulo compartidos por diseño (precedencia 1-2 sobre el default).
**How to avoid:** documentarlo como comportamiento **correcto** (el ambiente es más específico que el default de un registry) y probar el criterio 1 **sin** `bind` activo. Añadir un test que fije la precedencia: `with bind(db_b): assert reg_a.resolve() is db_b`.
**Warning signs:** un test de dos registries que pasa por casualidad porque no hay `bind` y falla cuando otro test deja un `bind` colgando.

### Pitfall 8: `pyproject.toml` y `CHANGELOG.md` son archivos compartidos por los 5 planes
**What goes wrong:** `06-02`, `06-03` y `06-04` editan el mismo `[tool.ruff.lint.per-file-ignores]` / ratchet mypy, y todos añaden entradas al `CHANGELOG`; en paralelo (Wave 2) el merge conflictúa.
**Why it happens:** la fase tiene 5 planes y 4 archivos de gate/docs compartidos.
**How to avoid:** **un solo dueño** para `pyproject.toml`, `CHANGELOG.md`, `mkdocs.yml` y `docs/*` (recomendado: `06-05`, que ya corre al final y es el plan de documentación). Los demás planes solo editan código + tests.
**Warning signs:** `git status` mostrando `pyproject.toml` modificado por tres ramas.

### Pitfall 9: el `exec()` de GraphQL se olvida porque el ROADMAP solo menciona "handlers"
**What goes wrong:** se reescribe `http/routes.py` y se deja `graphql/schema.py:103` con `exec()`; `ruff` sigue necesitando el `per-file-ignore` `S102` de `graphql/schema.py` y CFG-03 queda incompleto.
**Why it happens:** el texto de `06-03` dice "handlers" (lenguaje REST) y el `S102` de GraphQL está en un `per-file-ignore` separado (`pyproject.toml:167`).
**How to avoid:** tratar CFG-03 como **dos** sitios de rewrite, cada uno con su guardián (OpenAPI para HTTP, SDL para GraphQL). **Verificado:** la versión closure produce SDL idéntica.

### Pitfall 10: subir el cap de `PyJWT` sin re-verificar los 5 GHSA
**What goes wrong:** se amplía el cap y se retiran los `--ignore` "porque ya hay fix", pero `pip-audit` (feed PyPA, independiente de OSV) puede seguir reportando; o el bump rompe `jwt.decode` en la suite de seguridad.
**Why it happens:** `uv audit` (OSV) y `pip-audit` (PyPA) son feeds distintos (`ci.yml:247-253`).
**How to avoid:** subir el cap en un commit aislado, correr `uv lock --check` + `uv audit` (sin ignores) + `pip-audit`, y solo entonces retirar los `--ignore` de `ci.yml`. Mantener `tests/test_security.py` verde (47 tests verificados en el estado actual).
**Warning signs:** `ci.yml` sin ignores pero `uv.lock` sin regenerar; o `uv.lock` regenerado en el mismo commit que el rewrite de `exec()`.

### Pitfall 11: `resolve_db()` cambia de firma y rompe a los llamadores posicionales
**What goes wrong:** se cambia a `resolve_db(registry)` obligatorio y `model/model.py:218` (y cualquier app) rompe.
**Why it happens:** `resolve_db` está exportado en el barrel (`__init__.py:2,87`) y documentado (`docs/reference/context.md:12`).
**How to avoid:** `registry: ConnectionRegistry | None = None` con default al `_registry` de módulo: la llamada sin argumentos se comporta **exactamente** como hoy.

### Pitfall 12: el mensaje del `DeprecationWarning` de `SECRET` filtra el secreto
**What goes wrong:** un mensaje tipo `f"SECRET={SECRET!r} está deprecado"` escribe el secreto en logs/CI.
**Why it happens:** es tentador incluir el valor para "ayudar a depurar".
**How to avoid:** el mensaje nombra **el nombre** del global y el reemplazo (`SecurityConfig`), nunca el valor. Regla consistente con la decisión de Fase 5 de no loguear `_connect_kwargs`.

## Code Examples

### Estado actual, anclado (para el planner)
```python
# context.py:19-34, 47-63 — el global y sus dos accesos + la cadena
_default_db = None                                       # :20
_ambient_db = contextvars.ContextVar("encino_orm_ambient_db", default=None)  # :23

def set_default_db(db) -> None:                          # :26-29
    global _default_db
    _default_db = db

def get_default_db():                                    # :32-34
    return _default_db

def resolve_db():                                        # :47
    from .pool import PooledConnection, _current_connection   # :49 lazy
    conn = _current_connection.get()                     # :51
    if isinstance(conn, PooledConnection):
        return conn.driver                               # :55
    if conn is not None:
        return conn                                      # :57
    ambient = _ambient_db.get()                          # :58
    if ambient is not None:
        return ambient                                   # :60
    if _default_db is not None:                          # :61
        return _default_db                               # :62
    raise ConnectionError("Sin conexión: pasa `db`, usa `bind()`, `set_default_db()` o `session()`")  # :63
```

```python
# security/guard.py:13-31 — los globales y el único lector
SECRET: str | None = None                                # :14
GET_DB = None                                            # :15

def _resolve(secret, get_db):                            # :24
    secret = secret if secret is not None else SECRET    # :25   <-- LEE G2
    if not secret:
        raise AuthenticationError("SECRET no configurado para la dependency de seguridad")  # :27
    db_dep = get_db if get_db is not None else GET_DB    # :28   <-- LEE G3
    if db_dep is None:
        raise AuthenticationError("get_db no configurado para la dependency de seguridad")  # :30
    return secret, db_dep
```

```python
# graphql/schema.py:169-185 — la mutación del namespace del módulo
import sys
module_name = __name__                                   # :171
module = sys.modules[module_name]                        # :172
for model in models:
    typ = build_type(model, module_name)                 # :176
    type_map[model] = typ
    setattr(module, model.__name__, typ)                 # :178  <-- MUTA el módulo real
...
    setattr(module, f"{model.__name__}Filter", ftype)    # :185  <-- MUTA el módulo real
```

### Evidencia empírica del rewrite (resultados de los prototipos de esta sesión)
```text
# HTTP (proto_http2.py, 2026-09-19, CPython 3.13.7 / fastapi 0.141.1)
before handler has __signature__: False        # confirma que hoy NO hay __signature__ (es exec)
before handler source is exec-generated: True
after handler has __signature__: True
after handler is closure freevars: ('HTTPException', 'model')
OPENAPI IDENTICAL: True                        # json.dumps(spec, sort_keys=True) igual
GET 200 -> 200 ; GET 404 -> 404 ; GET 422 -> 422 ; PUT -> 200 ; DELETE -> 200
LIST -> 200 ; POST -> 201 ; COMPOSITE PK -> 404 ; COMPOSITE PK bad -> 422
COMPOSITE OPENAPI: True

# GraphQL resolvers (proto_graphql_exec.py)
SDL IDENTICAL: True                            # schema.as_str() antes == después
get: None {'agente': {'agente': 'H', 'region_id': 1}}
get missing: None {'agente': None}
update: None {'agente_update': {'agente': 'H2'}}
delete: None {'agente_delete': True}
delete missing: None {'agente_delete': False}

# GraphQL namespace (proto_graphql.py)
module keys ADDED by build_schema: ['Agente','AgenteFilter','Region','RegionFilter']   # HOY muta
module keys ADDED by 2nd build:    ['Agente','AgenteFilter','Other','OtherFilter','Region','RegionFilter']  # ACUMULA
module keys ADDED (per-build ns): []            # 0 mutaciones
sys.modules synthetic still present: []         # 0 fugas
per-build schema A / B / filter / mutation: todos None errors
A == B SDL: True

# Security (proto_security.py)
200: 200 ; 401: 401 ; 403 anonymous: 403
after mutating globals, still 200: 200          # criterio 2
FROZEN: True -> FrozenInstanceError
legacy warn count: 1 DeprecationWarning
legacy under error: DeprecationWarning raised (as in pytest)

# Gates
ruff check .  -> All checks passed!
ruff check --select B008 (probe)  -> 1 error con `db=Depends(...)`, 0 con `Annotated[...]`
pytest tests/test_singleton.py tests/test_security.py tests/test_graphql.py
       tests/test_crud.py tests/test_pk.py tests/test_pagination_limits.py -> 89 passed
pytest (probe DeprecationWarning) -> test sin `pytest.warns` FALLA bajo filterwarnings=["error"]
```

### Fronteras de confianza — texto a documentar (CFG-05)
```python
# SEGURO — Filter.raw con SQL constante y placeholders {n}; los valores van ligados
f = Filter.raw("precio > {0} AND precio < {1}", [10, 100])

# INSEGURO — el fragmento se reemite VERBATIM (filter.py:218-224 no valida nada)
f = Filter.raw(f"nombre = '{nombre_del_usuario}'", [])      # inyección SQL

# SEGURO — Query: plantilla constante, valores siempre ligados (query.py:88-103)
q = Query("SELECT * FROM t WHERE id = {0}", [user_id])

# INSEGURO — interpolar el valor en la plantilla anula el binding
q = Query(f"SELECT * FROM t WHERE id = {user_id}", [])      # inyección SQL

# SEGURO — db.fn.* devuelve un FRAGMENTO de confianza para incrustar (sql.py:34-42)
q = Query(f"SELECT * FROM t WHERE creado > {db.fn.now()}", [])

# INSEGURO — concatenar entrada no confiable al fragmento
q = Query(f"SELECT * FROM t WHERE nombre = {db.fn.now()} AND x = '{user_input}'", [])

# LIMITACIÓN DECLARADA (query.py:35-36): un `{n}` dentro de un literal de cadena
# se interpreta como placeholder; esta versión no parsea literales SQL.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `exec()` para generar handlers con firma dinámica | `inspect.Signature` asignada a `__signature__` | Fase 6 | Sin `S102`, sin `__globals__` frágil, mypy deja de reportar `Name "child.__name__" is not defined`. |
| Mutar `sys.modules[__name__]` para que `strawberry.lazy` resuelva | Módulo sintético por build, registrado solo durante la construcción | Fase 6 | Namespace de módulo inmutable; dos builds dejan de interferir. |
| Global mutable de proceso como "singleton" de conexión | `ConnectionRegistry` inyectable + shims deprecados | Fase 6 | Dos aplicaciones/tenants en el mismo proceso dejan de pisarse. |
| `guard.SECRET`/`guard.GET_DB` mutables | `SecurityConfig` frozen + factorías | Fase 6 | Mutar los globales deja de cambiar el comportamiento; multi-tenant y rotación pasan a ser posibles. |
| Fronteras de confianza implícitas en `Filter.raw`/`Query`/`db.fn.*` | Documentadas con ejemplos seguros/inseguros + test de que los parsers no emiten `raw` | Fase 6 | El usuario ve explícitamente que son "trusted input only". |

**Deprecated/outdated:**
- `.planning/codebase/CONCERNS.md:84` ("`SECRET` and `GET_DB` … are process-wide mutable globals") — obsoleto tras CFG-02 (los globales dejan de decidir).
- `.planning/codebase/CONCERNS.md:149-150` ("`set_default_db()` stores a process-global connection … an unbound `Model` can resolve to the wrong database") — mitigado por CFG-01.
- `docs/design/9-singleton.md:60-99` reproduce el `_default_db` global como diseño — debe apuntar al registry.
- `docs/integrations.md:112-113` (`guard.SECRET = ...`) — pasa a ser el camino deprecado.
- `pyproject.toml:163-170,182-184` (ignores `S102`/`B008`) y `:257,266,276-279` (ratchet) — deben encoger.
- `ci.yml:241-245` (5 `--ignore` GHSA) — retirables si se sube el cap (Open Question 1).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | El namespace sintético puede borrarse de `sys.modules` tras `strawberry.Schema(...)` sin romper ninguna ruta de Strawberry. | §5, Pitfall 6 | **Medio:** una ruta no ejercitada (query optimizer, persisted queries) lanzaría `ModuleNotFoundError`. Verificado para relaciones, `has_many`, filtros, mutations y `as_str()`. Mitigación: si falla, conservar el módulo registrado. |
| A2 | El snapshot OpenAPI completo es estable en toda la matriz 3.10–3.13. | §4, Validation | **Medio:** solo se verificó en 3.13.7. Mitigación: si CI deriva, comparar una **proyección normalizada** (paths + operationIds + parámetros + refs de componentes) en vez del JSON completo. |
| A3 | `get_default_db()` puede emitir `DeprecationWarning` al leer sin romper a los consumidores actuales. | §2 | **Bajo:** no hay consumidores en el repo salvo `__init__.py`/docs; los usuarios externos solo verían un warning silenciado por defecto. Alternativa: advertir solo en `set_default_db`. |
| A4 | La firma legacy `get_current_user(secret=None, get_db=None)` debe seguir funcionando **sin** warning cuando se pasan argumentos explícitos. | §3 | **Bajo:** es la ruta que usan los tests actuales (`test_security.py:160,171,180,189,198`); advertir ahí obligaría a tocar 5 tests sin ganancia. |
| A5 | `create_crud`/`build_schema` **no** necesitan ganar `config=`/`registry=` en esta fase. | §2/§3 | **Medio:** `.planning/research/ARCHITECTURE.md:419-420` lo sugiere y el ROADMAP dice "signatures change once"; si el planner lo decide, `06-01`/`06-02` deben aterrizarlo **antes** del snapshot de `06-03`. |
| A6 | El `exec()` de `graphql/schema.py:103` pertenece a CFG-03 (no solo CFG-04). | §4, Pitfall 9 | **Medio:** el ROADMAP atribuye el `S102` de GraphQL a CFG-03 vía `pyproject.toml:167`, pero el dueño natural del archivo es `06-04`. Recomendación: **`06-04` posee todo `graphql/schema.py`** (exec + namespace) y `06-03` solo HTTP, para mantener los planes disjuntos en archivos. |
| A7 | Subir el cap `PyJWT>=2.8,<2.13` es parte de Fase 6. | §1, Open Q1 | **Medio:** está asignado a Fase 6 en `STATE.md:117,226`, `01-VERIFICATION.md:70` y `01-02-SUMMARY.md:282,290`, pero **no** en el texto de la Fase 6 del ROADMAP. Si se hace, es un cambio de `uv.lock` + `ci.yml` que debe ir en su propio commit. |

**If this table is empty:** — (no lo está; A1/A2/A5/A6/A7 requieren confirmación en discuss/plan.)

## Open Questions (RESOLVED)

> Todas las preguntas abiertas de la investigación quedaron resueltas por el planner en los planes `06-01`…`06-05`. Se conservan aquí con su resolución para trazabilidad.

1. **¿Se sube el cap de `PyJWT` (`>=2.8,<2.13` → `<2.15`) y se retiran los 5 `--ignore` GHSA en esta fase?**
   - What we know: los 5 avisos (9 entradas OSV) tienen fix en 2.13.0; `PyJWT` 2.13.0 y 2.14.0 existen en PyPI (`[VERIFIED: pip index versions PyJWT]`); la propiedad de la Fase 6 está declarada en 4 artefactos pero **no** en el texto del ROADMAP.
   - What's unclear: si el planner lo considera dentro del alcance de CFG-02 o lo difiere.
   - Recommendation: **sí, en un commit aislado dentro de `06-02`** (o en `06-05` como tarea de gates): `pyproject.toml:26` → `PyJWT>=2.8,<2.15`, `uv lock`, `uv audit` + `pip-audit` sin ignores, retirar `ci.yml:241-245`, y dejar `tests/test_security.py` verde. Si algo falla, mantener el cap y **no** tocar los ignores (estado actual, con la causa ya escrita).
   - **RESUELTO por `06-05` Task 3:** commit aislado + `uv lock` + `uv audit`/`pip-audit` sin ignores + retirada de los 5 `--ignore` de `ci.yml`; fail-closed (restaurar cap y conservar ignores si algo falla). La frase final del CHANGELOG la fija Task 3 (W7).

2. **¿`create_crud`/`build_schema` ganan un parámetro `config=`/`registry=` como composition root?**
   - What we know: `.planning/research/ARCHITECTURE.md:419-420` lo propone; `create_crud` ya acepta `get_db=` explícito (`http/__init__.py:13`) y `build_schema` solo `auto_camel_case` (`graphql/schema.py:164`).
   - What's unclear: ningún requisito CFG lo exige; añadirlo agranda la superficie pública sin criterio de éxito que lo cubra.
   - Recommendation: **no** en esta fase (YAGNI). Los composition roots ya reciben `get_db`/`pool`; la config de seguridad se inyecta en las factorías del guard, no en el router. Si se decidiera lo contrario, hacerlo en `06-01`/`06-02` (Wave 1) para que el snapshot de `06-03` se capture con la firma final.
   - **RESUELTO por `06-01`/`06-03`/`06-04`:** `create_crud`/`build_schema` NO ganan `config=`/`registry=` en esta fase; queda escrito en los objetivos de `06-01`, `06-03` y `06-04` y en la nota de orden interno del ROADMAP.

3. **¿Qué plan posee el `exec()` de `graphql/schema.py:103`?**
   - What we know: `S102` está suprimido en `pyproject.toml:167` con comentario que apunta a CFG-03; `01-01-SUMMARY.md:136` y `01-02-PLAN.md:92` atribuyen los errores mypy `Name "child.__name__" is not defined` a CFG-03. El texto de `06-04` es "namespace por build".
   - What's unclear: si el rewrite de `_pk_resolver` vive en `06-03` o en `06-04`.
   - Recommendation: **`06-04` posee todo `graphql/schema.py`** (exec → closures + namespace por build), con **dos** guardianes en el mismo plan: snapshot SDL (antes/después del rewrite) y test de no-mutación del namespace. `06-03` queda con HTTP + OpenAPI. Así `06-03` y `06-04` no comparten archivos y pueden correr en paralelo (Wave 2). Requiere que el planner acepte la desviación respecto a la lectura literal del ROADMAP y lo deje escrito.
   - **RESUELTO por `06-04`** (dueño de todo `graphql/schema.py`: Task 2 reescribe `_pk_resolver`, Task 3 el namespace) y **`06-03`** (HTTP + OpenAPI). La desviación queda registrada en ambos planes y en `ROADMAP.md`.

4. **¿Se levantan las supresiones de gates asignadas a la fase?**
   - What we know: `pyproject.toml:163-170` (`S102` de `routes.py`/`schema.py`, `B008` de `routes.py`/`guard.py`), `:182-184` (`B008`/`S105` de `test_security.py`), `:257,266,276-279` (5 entradas del ratchet mypy). Todas nombran Fase 6. `ruff check .` está verde hoy **con** los ignores.
   - What's unclear: si el `S105` de `tests/test_security.py` desaparece (depende de renombrar la constante `SECRET` del test, `test_security.py:28`).
   - Recommendation: **sí**, como tarea de cierre: retirar cada entrada tras el cambio de código que la justifica, medir con `uv run ruff check .` + `uv run mypy encino_orm`, y si queda un residual **ajeno** al alcance, restaurar la entrada con la causa escrita (precedente `04-04`, `pyproject.toml:249-256`). La evidencia de que `B008` es levantable con `Annotated` está verificada.
   - **RESUELTO por `06-05` Task 3** (retirada de `S102`/`B008` y del ratchet mypy, incluida `encino_orm.http.parsing`; los probes usan `ruff --isolated`), con el código migrado por `06-02` (`Annotated`), `06-03` y `06-04` (closures).

5. **¿La documentación de fronteras vive en una página nueva o en las páginas de referencia existentes?**
   - What we know: `docs/reference/{filter,sql,db}.md` son stubs de `mkdocstrings` de 6-27 líneas; `mkdocs.yml:57-66` las lista.
   - Recommendation: **página nueva `docs/trust-boundaries.md`** (prosa con ejemplos seguros/inseguros, fácil de revisar y de testear) + referencias cruzadas de una línea en los tres stubs + docstring de `Filter.raw` (`filter.py:113-115`). Nav: nueva sección "Seguridad" en `mkdocs.yml` (junto a "Desarrolladores") o bajo "Guía".
   - **RESUELTO por `06-05` Task 1:** página nueva `docs/trust-boundaries.md` + refs cruzadas + nav + docstring de `Filter.raw` + banners de deprecación en `README.md`/`docs/getting-started.md` (W4).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (local) | Todo | ✓ | **3.13.7** (`.venv`) | Piso real de librería: **3.10** (`requires-python`, `ruff target-version = "py310"`, `mypy python_version = "3.10"`). **No usar** `asyncio.timeout`/`TaskGroup`/`except*`. |
| `uv` | Lock/sync/test | ✓ | 0.12.15 | — |
| `fastapi` | CFG-02/CFG-03 | ✓ | 0.141.1 (extra `http`/`security`) | — |
| `starlette` | (transitiva de FastAPI) | ✓ | 1.6.0 | `include_router` crea un `_IncludedRouter`; los tests deben usar `app.openapi()`/httpx, **no** iterar `app.routes` buscando paths. |
| `strawberry-graphql` | CFG-03/CFG-04 | ✓ | 0.324.4 (extra `graphql`) | — |
| `PyJWT` | CFG-02 | ✓ | 2.12.1 | 2.13.0/2.14.0 disponibles en PyPI si se sube el cap (Open Q1). |
| `httpx` | Tests de guards/handlers | ✓ | 0.28.1 | — |
| `syrupy` | Snapshots CFG-03/CFG-04 | ✓ | 6.1.1 (dev, fijado) | Alternativa: golden JSON versionado leído por el test (menos ergonómico). |
| `pytest` / `pytest-asyncio` | Tests | ✓ | 9.1.1 / 1.4.0 | — |
| `ruff` / `mypy` | Gates | ✓ | 0.16.8 (fijado) / ≥2.3.1 | — |
| Docker + contenedores | **No requerido** | ✓ (disponibles) | — | Los tests de la fase son SQLite `:memory:`; **no** se necesitan motores reales. |

**Missing dependencies with no fallback:** ninguna.
**Missing dependencies with fallback:** ninguna.

**Nota de entorno:** el venv local es CPython **3.13.7** (`STACK.md`/`AGENTS.md` afirman 3.10.18 — corrección factual ya señalada en `05-RESEARCH.md:585`). Todos los prototipos de esta sesión corrieron en 3.13.7. El piso 3.10 se mantiene como restricción de código (matriz CI 3.10–3.13).

## Validation Architecture

> `workflow.nyquist_validation = true` en `.planning/config.json:19` → sección incluida.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.1.1 + `pytest-asyncio` 1.4.0 (`asyncio_mode="auto"`, ambos loop scopes `function`) + `syrupy` 6.1.1 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (líneas 41-90) |
| Quick run command | `uv run pytest tests/test_registry.py tests/test_security.py tests/test_http_openapi.py tests/test_graphql_namespace.py -q` |
| Full suite command | `uv run pytest -q -m "not optional_engine"` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CFG-01 (SC1) | Dos `ConnectionRegistry` resuelven a su propia BD; el shim deprecado funciona y avisa | unit (SQLite `:memory:`) | `uv run pytest tests/test_registry.py -q -k registry` | ❌ Wave 0 |
| CFG-01 (SC1) | `set_default_db`/`get_default_db` siguen funcionando con `DeprecationWarning`; precedencia `bind` > default | unit | `uv run pytest tests/test_registry.py -q -k deprecated` | ❌ Wave 0 |
| CFG-02 (SC2) | `SecurityConfig` frozen; guards desde config; mutar `SECRET`/`GET_DB` no cambia la respuesta | integration in-process (httpx `ASGITransport`) | `uv run pytest tests/test_security.py -q -k config` | ❌ Wave 0 (extiende `test_security.py`) |
| CFG-02 | 200/401/403 preservados en el camino nuevo **y** en el legacy | integration | `uv run pytest tests/test_security.py -q` | ✅ (existe; se conserva) |
| CFG-03 (SC3) | OpenAPI idéntico antes/después del rewrite | snapshot (syrupy) | `uv run pytest tests/test_http_openapi.py -q` | ❌ Wave 0 (snapshot capturado **antes** del rewrite) |
| CFG-03 (SC3) | Path params siguen validando (int vs str, PK simple y compuesta) | integration | `uv run pytest tests/test_http_openapi.py tests/test_pk.py -q -k "path or pk"` | ✅ parcial (`test_pk.py:184`) |
| CFG-04 (SC4) | Dos `build_schema` no mutan el namespace del módulo | unit | `uv run pytest tests/test_graphql_namespace.py -q -k namespace` | ❌ Wave 0 |
| CFG-04 | Los dos schemas siguen ejecutando (relaciones, filtros, mutations) tras el segundo build | unit | `uv run pytest tests/test_graphql_namespace.py -q` | ❌ Wave 0 |
| CFG-03 (GraphQL) | SDL idéntica antes/después del rewrite de `_pk_resolver` | snapshot (syrupy) | `uv run pytest tests/test_graphql_namespace.py -q -k sdl` | ❌ Wave 0 |
| CFG-05 (SC5) | `Filter.raw`/`Query`/`db.fn.*` documentados con ejemplos seguros e inseguros | docs build | `uv run mkdocs build --strict` | ✅ (job `docs.yml`); + test de presencia |
| CFG-05 (SC5) | Ningún parser HTTP/GraphQL emite `Filter.raw` | unit (regresión) | `uv run pytest tests/test_trust_boundaries.py -q` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** el archivo de test del plan (p. ej. `uv run pytest tests/test_registry.py -q`).
- **Per wave merge:** `uv run pytest -q -m "not optional_engine"` + `uv run ruff check .`.
- **Phase gate:** suite completa verde + `uv run ruff check .` + `uv run mypy encino_orm` + `uv run mkdocs build --strict` antes de `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_registry.py` — CFG-01 (dos registries, shim deprecado con `pytest.warns`, precedencia).
- [ ] `tests/test_http_openapi.py` + `tests/__snapshots__/test_http_openapi.ambr` — CFG-03; el `.ambr` **generado contra el `exec()` actual** y commiteado **antes** del rewrite.
- [ ] `tests/test_graphql_namespace.py` + `tests/__snapshots__/test_graphql_namespace.ambr` — CFG-04 + SDL; mismo orden estricto.
- [ ] `tests/test_trust_boundaries.py` — CFG-05 (los parsers no emiten `raw`).
- [ ] Extensión de `tests/test_security.py` — CFG-02 (clase nueva `TestSecurityConfig`).
- [ ] Sin fixtures compartidas nuevas en `tests/conftest.py` (`connected_db` en `conftest.py:18-23` cubre SQLite).
- [ ] Framework install: ninguno (todo presente y fijado).

### Cómo probar cada criterio de éxito de forma determinista (deliverable #7)
1. **Criterio 1 (registries):** SQLite `:memory:`, sin servidores ni Docker.
   ```python
   a, b = await create_db("sqlite", database=":memory:"), await create_db("sqlite", database=":memory:")
   ra, rb = ConnectionRegistry(a), ConnectionRegistry(b)
   assert ra.resolve() is a and rb.resolve() is b
   with pytest.warns(DeprecationWarning):
       set_default_db(a)
   assert resolve_db() is a
   with bind(b):                      # precedencia: el ambiente gana para cualquier registry
       assert ra.resolve() is b
   ```
   Teardown sin warning: `_registry.set_default(None)` (nunca `set_default_db(None)`).
2. **Criterio 2 (config):** `pytest.raises(dataclasses.FrozenInstanceError)` al asignar; app FastAPI con `security_dependencies(cfg)` y `httpx.ASGITransport` → 200 con token válido, 401 inválido, 403 anónimo; luego `guard.SECRET = "otro"` / `guard.GET_DB = None` y **repetir las tres** aserciones (deben seguir 200/401/403). **Verificado en el prototipo.**
3. **Criterio 3 (OpenAPI):** `assert snapshot == json.dumps(app.openapi(), indent=2, sort_keys=True)` con el `.ambr` generado **antes** del rewrite; más `GET /api/<tabla>/abc` → 422 y `GET /api/<tabla>/1` → 200. **Verificado:** el JSON completo es idéntico.
4. **Criterio 4 (namespace):** `before = set(vars(encino_orm.graphql.schema))`; `s1 = build_schema(models)`; `s2 = build_schema(models)`; `assert set(vars(...)) == before`; `assert not [k for k in sys.modules if "_build_" in k]`; y ejecutar en **ambos** schemas una query con relación, una con filtro autorreferente y una mutation. **Verificado en el prototipo.**
5. **Criterio 5 (docs):** `uv run mkdocs build --strict` (falla con refs/nav rotos) + `tests/test_trust_boundaries.py` que (a) recorre `_OP_MAP`/`_apply_op` y afirma que no hay ninguna ruta a `Filter.raw`, y (b) lee `docs/trust-boundaries.md` y exige que existan los tres encabezados (`Filter.raw`, `Query`, `db.fn.*`) y al menos un bloque marcado como inseguro. La revisión humana del contenido sigue siendo manual-only (justificación: es prosa; el test solo impide que la página desaparezca o se vacíe).

## Security Domain

> `security_enforcement` ausente en `.planning/config.json` → habilitado. La fase **toca la capa de seguridad** (CFG-02) y **documenta fronteras de inyección** (CFG-05).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | **sí** | `SecurityConfig.secret` inyectado (no global); `verify_token` sigue exigiendo `exp` y rechazando `type=="refresh"` como access (`jwt.py:78,83-84`); `_ALLOWED_ALGORITHMS` (`jwt.py:17-32`) bloquea `none`/confusión de algoritmo. **Preservar** la semántica fail-closed de `_resolve` (`guard.py:26-30`). |
| V3 Session Management | **sí (indirecto)** | La dependency de conexión deja de ser un global: `config.get_db` es explícita por aplicación. No hay sesiones propias. |
| V4 Access Control | **sí** | `require(modelo, op)` sigue delegando en `PermissionSet.require` y mapeando `AuthorizationError`→403 (`guard.py:68-70`). Multi-tenant/rotación de clave pasan a ser posibles (antes imposibles con un único global). |
| V5 Input Validation | **sí** | Path params siguen validados por FastAPI vía `__signature__` (verificado 422); los identificadores SQL ya pasan por las allowlists (`sql.py:12`, `filter.py:5`, `base.py:12`). El rewrite no introduce interpolación nueva. |
| V6 Cryptography | **no (sin cambios)** | No se toca `jwt.py` salvo el paso de `algorithms`; nunca se implementa criptografía a mano. |
| V7 Error Handling & Logging | **sí** | El mensaje del `DeprecationWarning` de `SECRET` **no** debe incluir el valor (Pitfall 12); el fallback legacy mantiene el fail-closed. |

### Known Threat Patterns for esta fase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secreto JWT global compartido entre tenants | Information Disclosure / Elevation | `SecurityConfig` inyectado por aplicación; el global pasa a deprecado y deja de decidir. |
| Rotación de clave imposible sin reinicio | Denial of Service / Repudiation | Config inyectada (permite reconstruir guards con un secreto nuevo); `PITFALLS.md:435` sugiere además soportar callable/iterable de secretos — evaluar en discuss. |
| Fuga del secreto en el mensaje de deprecación o en logs | Information Disclosure | El warning nombra el **nombre** del global y su reemplazo, nunca el valor (Pitfall 12). |
| Inyección SQL por `Filter.raw`/`Query`/`db.fn.*` mal usados | Tampering | CFG-05: frontera documentada con ejemplos seguros/inseguros + test de que los parsers HTTP/GraphQL no pueden emitir `raw`. |
| `exec()` como superficie de ejecución de código | Tampering / Elevation | Se **elimina** (`S102` deja de necesitar supresión); el `__signature__` no ejecuta código generado. |
| Namespace GraphQL mutado por un build contamina a otro (tipo equivocado) | Tampering | Namespace por build; el módulo real queda inmutable. |
| Un `DeprecationWarning` en el camino caliente que un operador silencie con `-W ignore` y con ello oculte avisos reales | Repudiation | Los warnings viven solo en los shims/fallback, nunca por operación. |

## Sources

### Primary (HIGH confidence)
- **Código vivo del repositorio, leído con anchors citados en cada sección:** `encino_orm/context.py`, `security/{guard,jwt,models,exceptions,__init__}.py`, `http/{routes,registry,errors,parsing,__init__}.py`, `graphql/{schema,types,filters,resolvers}.py`, `model/{filter,model}.py`, `query.py`, `sql.py`, `pool.py`, `__init__.py`, `pyproject.toml`, `mkdocs.yml`, `.github/workflows/ci.yml`, `tests/*`, `docs/*`, `CHANGELOG.md`.
- **Prototipos ejecutados en esta sesión (CPython 3.13.7, venv del repo, 2026-09-19):**
  - `exec()`→closure en HTTP: **OpenAPI JSON idéntico** (`json.dumps(..., sort_keys=True)`), 200/404/422/201/PUT/DELETE/LIST y PK compuesta correctos; `__signature__` ausente en el original y presente en la closure (freevars `('HTTPException','model')`).
  - `exec()`→closure en GraphQL: **SDL idéntica** (`schema.as_str()`), `get`/`update`/`delete`/`not-found` correctos.
  - Namespace GraphQL: el build actual **añade** `{Agente, AgenteFilter, Region, RegionFilter}` al módulo y **acumula** en el segundo build; el módulo sintético por build produce **0 mutaciones** y **0 fugas**, y ambos schemas ejecutan (relaciones, `has_many`, filtros autorreferentes, mutations, `as_str()`).
  - `SecurityConfig` frozen + factorías: 200/401/403, `FrozenInstanceError`, mutación posterior de `SECRET`/`GET_DB` sin efecto, 1 `DeprecationWarning` en el fallback legacy.
  - Gates: `ruff check .` → "All checks passed!"; `ruff --select B008` → 1 hallazgo con `db=Depends(...)` y **0** con `Annotated[...]`; `pytest` de los 6 archivos tocados → **89 passed**; un `DeprecationWarning` sin `pytest.warns` **falla** bajo `filterwarnings=["error"]`.
- **Introspección de las librerías instaladas (`.venv`):** `fastapi/dependencies/utils.py` (`_get_signature` → `inspect.signature(call, eval_str=True)`; `get_typed_annotation` solo transforma `str`), `strawberry/types/lazy_type.py:37-63` (`importlib.import_module(...).__dict__[...]`), `strawberry/annotation.py:146-154` (caché `__resolve_cache__`), `strawberry/schema/schema_converter.py:109-116,1188-1197` (resolución de `LazyType` en construcción), `strawberry/types/arguments.py:152-153,239-240`, `strawberry/schema/name_converter.py:119-155`.
- `.planning/ROADMAP.md:301-325` (goal, 5 criterios, 5 planes), `.planning/REQUIREMENTS.md:64-68,125,171-175`, `.planning/PROJECT.md`, `.planning/config.json:19`.

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md:382-420` (Pattern 6: "Composition-root DI for configuration"), `:618` (Anti-Pattern "Set `SECRET`/`GET_DB`/`_default_db` globals and read them per request").
- `.planning/research/PITFALLS.md:430-439` (Pitfall 16: congelar en vez de inyectar), `:275,285` (release de deprecación), `:433` (freeze).
- `.planning/research/FEATURES.md:51-52` (TS-21, TS-22), `.planning/research/SUMMARY.md:287-300` (Phase 6 del milestone).
- `.planning/phases/01-*/01-01-PLAN.md:95,209-213` y `01-01-SUMMARY.md:135-141` (qué supresión de gate posee cada CFG), `01-02-SUMMARY.md:156-165,282,290`, `01-VERIFICATION.md:10-17,70`.
- `.planning/phases/02-*/02-RESEARCH.md:1053-1058` (enunciado de la frontera de confianza que alimenta CFG-05).

### Tertiary (LOW confidence)
- Ninguna. Las decisiones de forma pública restantes están en **Assumptions Log** / **Open Questions**; ninguna afirmación técnica central depende de una única fuente no verificada.

## Metadata

**Confidence breakdown:**
- Estado actual (globales, `exec()`, mutación de namespace, fronteras): **HIGH** — todo leído con anchors y tres de las cuatro propiedades reproducidas empíricamente.
- `exec()`→closure + `__signature__`: **HIGH** — equivalencia OpenAPI y SDL verificadas byte a byte; la ruta de parcheo se validó explícitamente (el primer prototipo fue inválido porque `create_crud` liga `register_crud` en el import; el segundo lo confirmó con `__signature__`/freevars).
- Namespace GraphQL por build: **HIGH** para los caminos ejercitados; **MEDIUM** para rutas no ejercitadas de Strawberry (A1).
- `SecurityConfig` frozen + factorías: **HIGH** — comportamiento end-to-end verificado, incluida la mutación posterior de los globales.
- Forma pública final (firma de `ConnectionRegistry`, `config=` en los composition roots, dueño del `exec()` de GraphQL): **MEDIUM** — decisiones de diseño, no hechos (A5, A6, Open Q2/Q3).
- Gates y cap de `PyJWT`: **MEDIUM** — el trabajo está asignado en artefactos de Fase 1/STATE pero no en el texto del ROADMAP (A7, Open Q1).

**Research date:** 2026-09-19
**Valid until:** 2026-10-19 (30 días). La equivalencia OpenAPI/SDL depende de `fastapi 0.141.1`, `starlette 1.6.0` y `strawberry-graphql 0.324.4` fijados en `uv.lock`; un bump de cualquiera de los tres exige re-verificar los snapshots.
