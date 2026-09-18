# Changelog

Todos los cambios notables del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Mientras esté
en `0.x`, **no hay garantía de estabilidad** (ver `README.md`).

## [Unreleased]

### Corregido

- `indexes_ddl` valida las columnas de índice no mapeadas con la allowlist
  estricta: un spec que no es un campo del modelo ni un identificador simple
  (p. ej. `"a; DROP TABLE x --"`) antes se interpolaba tal cual en la DDL y ahora
  lanza `ValueError` (fail-closed); un identificador simple (`Index("no_existe")`)
  sigue aceptándose. Además, el nombre de columna por defecto (el campo pydantic)
  se valida al construir el mapa de columnas, de modo que `to_ddl` e
  `insert_many` rechazan identificadores no válidos. Nota de ownership: esta
  entrada es ADITIVA y no prejuzga la enumeración de cambios incompatibles del
  milestone, que posee la Fase 8 (`08-04`).
- `QueryBuilder.all()`, `first()` y `exists()` dejan de emitir un `LIMIT` en
  línea: la paginación la aplica el adaptador (`fetch_many`/`fetch_one`), de modo
  que la consulta es válida en los seis motores (SQL Server y Oracle usan
  `OFFSET … FETCH NEXT`). Antes, esas tres rutas fallaban con error de sintaxis en
  T-SQL y Oracle. Mismo patrón que `Model.search`.
- `Model.upsert()` en MariaDB emite `ON DUPLICATE KEY UPDATE` en vez de
  `ON CONFLICT`, que MariaDB no implementa (el camino estaba roto: el motor
  rechazaba la sentencia con error 1064).
- `Model.insert(replace=True)` usa la clave primaria del modelo como objetivo de
  conflicto en PostgreSQL; antes usaba la primera columna del INSERT, que no es la
  PK con `id` autoincremental, y PostgreSQL rechazaba la sentencia. Nota de
  alcance: (a) en MSSQL/Oracle (`merge`) el objetivo sigue siendo el fallback a la
  primera columna, porque su `src` derivado no contiene la PK autoincremental
  (documentado, sin cambio en esta ronda); (b) en un modelo de PK autoincremental
  `id` no forma parte del INSERT, así que `ON CONFLICT (id)` nunca se dispara y
  `replace=True` se comporta como un INSERT normal (no reemplaza) — antes
  PostgreSQL fallaba en voz alta, ahora la sentencia es válida pero no reemplaza.
  Comportamiento explícito, no silencioso.
- Correcciones de EJECUCIÓN del `MERGE` en MSSQL/Oracle (defectos preexistentes
  descubiertos al añadir cobertura de `Model.insert(replace=True)`): SQL Server
  exige que `MERGE` termine en `;` y Oracle exige `FROM dual` en el subquery del
  `USING`. Se aplican SOLO al SQL que va al driver, sin alterar el SQL que producen
  los builders/adaptadores (golden strings y snapshots intactos). Nota de
  ownership: aditiva, igual que la anterior; la Fase 8 (`08-04`) posee la
  enumeración del milestone.

## [0.2.6] - 2026-09-11

### Corregido

- Compatibilidad con Python 3.13: se sustituye `Annotated.__class_getitem__`
  (eliminado en Python 3.13) por la forma de subíndice `Annotated[...]` con
  tupla, manteniendo a la vez la compatibilidad con Python 3.10 en
  `encino_orm/model/constraint.py` y `encino_orm/model/model.py`.

## [0.2.5] - 2026-09-10

### Seguridad

- Límite máximo de paginación (`MAX_LIMIT=1000`) y normalización de `limit`/`page`
  en `search`, `paginate` y `QueryBuilder.limit` para evitar DoS; el `PUT`/listado
  de REST devuelve `422` ante valores fuera de rango y GraphQL limita a 50 por
  defecto.
- `transfer` (`copy_table`/`build_ddl`) valida los nombres de tabla y columna
  antes de interpolar en SQL.
- `db.fn.date_format` escapa las comillas del patrón (evita inyección por
  literales).
- `db.fn.*` valida los nombres de columna (identificadores) antes de incrustarlos
  en los fragmentos SQL.
- `Model._col` valida el identificador resultante, cerrando la inyección por
  `keys`/`conflict` no confiables en `load`/`update`/`delete`/`save`/`upsert`.

## [0.2.4] - 2026-09-10

### Añadido

- Extra opcional `cache` (`redis`) para `CachedModel` con `RedisCacheBackend`
  probado contra Redis real; servicio `redis` en `docker-compose.yml` y tests de
  caché (`tests/test_redis_cache.py`).

### Seguridad

- `Model.search(columns=...)` y `QueryBuilder.sum(column)` validan los
  identificadores de columna antes de incrustarlos en SQL.
- `columns_of` de SQLite y MySQL valida el nombre de tabla antes de interpolarlo.
- SQL Server conecta con TLS por defecto (`Encrypt=yes`,
  `TrustServerCertificate=no`); configurable con `encrypt`/
  `trust_server_certificate`.
- Codegen (`generate_model`) emite `_table` y `name=` con `repr`, evitando
  inyección de código desde nombres de tabla/columna.
- JWT: separación access/refresh mediante el claim `type` y lista permitida de
  algoritmos (rechaza `"none"`).
- Los nombres de `SAVEPOINT` se validan antes de interpolar en SQL.
- El `PUT` de REST ignora los campos de solo lectura (`id`, `enabled`,
  `created_at`, `updated_at`).

## [0.2.3] - 2026-09-08

### Corregido

- Compatibilidad con Python 3.10: se elimina el *starred unpacking* dentro de
  subíndices `Annotated[...]` (sintaxis PEP 646, sólo válida en Python 3.11+) en
  `encino_orm/model/model.py` y `encino_orm/model/constraint.py`. Ahora el
  paquete funciona realmente con `requires-python = ">=3.10"`.

## [0.2.2] - 2026-09-08

### Añadido

- `Model.has_many(name, *, filter, limit, page, sort_by, include_deleted)`:
  carga una colección 1:N con **filtro previo** a la consulta (la base de datos
  sólo devuelve el subconjunto solicitado, sin materializar toda la colección).
- `batch_has_many(models, name, extra=...)`: filtro común en la carga por lotes.
- `Filter.digest()`: huella `sha1` estable para claves de caché.
- Caché multi-clave en `HasMany` (por clave de padre + filtro/paginación/orden).
- Documentación: sitio MkDocs (Material + `mkdocstrings`) con referencia de API
  generada desde docstrings y publicación a GitHub Pages
  (`.github/workflows/docs.yml`, `mkdocs.yml`, `docs/reference/`).
- `Model.cursor(db=None, **values)`: instancia de consulta sin validación de
  pydantic, para operaciones de lectura (`load`/`search`/`count`/`paginate`) y
  de esquema (`create_table`) sobre modelos con campos `required=True`, sin
  recurrir a `model_construct()` manual.

### Cambiado

- `HasMany` migra su caché de valor único a `dict` multi-clave (clave = clave de
  padre + digest del filtro).

### Corregido

- Ejemplos de `README.md` y `docs/getting-started.md` que requerían definir un
  helper `_cursor()` manual: ahora usan el classmethod `cursor()`.
- `docs/guide.md`: faltaba el ejemplo de `Filter.endswith(...)` junto a
  `Filter.startswith(...)`.

## [0.1.0] - 2026-08-30

### Añadido

- Núcleo ORM asíncrono para SQLite, MySQL y PostgreSQL (`Db`, `PoolDb`,
  `session`, `create_db`).
- `Model` declarativo (basado en `pydantic`) con restricciones reutilizables
  (`make_constraint` y presets `STR_*`, `INT`, `CURRENCY`, `DATETIME`,
  `DECIMAL`, `JSON`, …).
- CRUD completo: `insert`, `save`, `upsert`, `load`, `update`, `delete`,
  `search`, `count`, `paginate`, `insert_many` (bulk).
- Claves primarias simples (auto-incremental), naturales y **compuestas**, y
  claves foráneas compuestas.
- Relaciones 1:1 y 1:N con carga por lotes (`batch_reference`,
  `batch_has_many`).
- `Filter` componible y `QueryBuilder` con `join`, agregados y subconsultas.
- Migraciones versionadas (`Migration`, `migrations_from_dir`), `create_table`,
  `diff_schema` y `sync_schema`.
- Conexión implícita (`set_default_db`, `bind`, `resolve_db`).
- Capas opcionales: REST (FastAPI), GraphQL (Strawberry), seguridad (RBAC + JWT)
  y codegen/CLI (`encino_orm generate models`).
- Observabilidad (`trace_id`, `QueryTracer`) y caché (`CachedModel` +
  `CacheBackend`).
- Documentación de usuario (`README.md` y `docs/`), guía para agregar motores y
  licencia MIT.
