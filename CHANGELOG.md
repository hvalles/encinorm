# Changelog

Todos los cambios notables del proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). Mientras esté
en `0.x`, **no hay garantía de estabilidad** (ver `README.md`).

## [Unreleased]

### Cambiado

- **CAMBIO DE COMPORTAMIENTO (formato de clave de caché).** La clave de caché de
  `CachedModel` ahora incluye la huella del `scope()` activo:
  `sha1(tabla:[pk=...]|scope=<huella>)`. Una entrada cacheada bajo un tenant ya no
  se sirve a otro, cerrando la lectura cruzada y la escritura cruzada de tenant
  (CR-02). Sin `scope()` activo la clave no cambia respecto al formato anterior.
  Al ser un cambio de formato, un backend compartido entre versiones puede
  conservar claves del formato viejo como entradas huérfanas hasta que expire su
  TTL; el nuevo formato no las sirve. Nota de ownership: esta entrada es ADITIVA y
  no prejuzga la enumeración de cambios incompatibles del milestone, que posee la
  Fase 8 (`08-04`).

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
- `Query` aplica el contrato de cardinalidad sin carve-outs: pasar valores a una
  plantilla sin `{n}` ahora lanza `ValueError` (antes los valores se descartaban en
  silencio) y `{00}` se normaliza a `parameter_0000` en vez de dejar una clave que
  el adaptador no resuelve. El camino compatible `Query(sql, [])` se conserva. Nota
  de ownership: esta entrada es ADITIVA y no prejuzga la enumeración de cambios
  incompatibles del milestone, que posee la Fase 8 (`08-04`).
- `QueryBuilder` valida el nombre de tabla del modelo (constructor) y el de cada
  destino de `join()` con la allowlist estricta, de modo que un `_table` no
  identificador (p. ej. de un modelo dinámico o generado por codegen) lanza
  `ValueError` ANTES de generar SQL, en vez de interpolarse en el `FROM`/`JOIN`
  (fail-closed). Las posiciones de expresión (`select`/`group_by`/`order_by`)
  conservan su allowlist tolerante a puntos, por decisión.
- En los dialectos `merge` (MSSQL/Oracle), el objetivo de conflicto de un `MERGE`
  DEBE ser una columna presente en los datos insertados; si no lo es, el builder
  lanza `ValueError` con un mensaje accionable en vez de emitir
  `ON (dst.<col> = src.<col>)` sobre una columna inexistente (antes: MSSQL 207
  `Invalid column name` / Oracle `ORA-00904`). En consecuencia, `Model.upsert()` con
  el conflicto por defecto (PK) sobre un modelo de PK autoincremental ahora falla en
  voz alta, y el llamador debe pasar `conflict=` con una columna de datos (la PK `id`
  no está en el INSERT). No es una mejora de la semántica del upsert: es un fallo
  cerrado.
- `Model.insert(replace=True)` en MSSQL/Oracle se renderiza como `MERGE`, que no
  expone el id de la fila en la frontera del driver; antes devolvía y asignaba el
  `last_id()` cacheado, que podía ser el id de OTRA fila (un `update()` posterior
  apuntaba a la fila equivocada). Ahora devuelve `0` ("id no disponible") y deja
  `self.id` intacto. Aclaraciones: (a) el camino no-merge (`INSERT` plano y `replace`
  en PostgreSQL) sigue devolviendo el id real sin cambios; (b) la captura del id
  DENTRO del insert (`OUTPUT INSERTED.id` / `SCOPE_IDENTITY`) pertenece a la Fase 4
  (`04-02`, POOL-03), y el fallback `columns[0]` del `MERGE` (semántica preexistente,
  incorrecta) sigue sin corregir y con dueño.
- `rollback_migration` ejecuta el `down` y **borra** la fila `{name}` del ledger en
  vez de insertar una fila `{name}:down`: la fila pasa a `rolling_back` durante el
  `down` y se elimina al terminar, de modo que re-aplicar la misma migración vuelve
  a ejecutar su `up` (antes la fila `{name}` sobrevivía y el re-apply era un no-op
  silencioso). CAMBIO INCOMPATIBLE: quien consultara filas con sufijo `:down` en
  `migrate_status()` ya no las verá; el ledger solo lista migraciones realmente
  aplicadas. Nota de ownership: esta entrada es ADITIVA y no prejuzga la enumeración
  de cambios incompatibles del milestone, que posee la Fase 8 (`08-04`).
- `migrate()` pasa a un flujo de dos fases: la fila se inserta como `pending` **antes**
  de ejecutar el DDL y se promueve a `applied` **después**. En los motores con commit
  implícito de DDL (MySQL/MariaDB/Oracle) un fallo entre ambos pasos deja un `pending`,
  que `reconcile_migrations()` **detecta** (lanza `MigrationError` con el SQL de cada
  fila; nunca re-ejecuta DDL ni asume `applied`) y que se resuelve con
  `resolve_migration(db, name, applied=...)`, donde `applied` significa "¿debe quedar
  registrada como aplicada?". La tabla de migraciones gana una columna `status`
  (`pending`/`applied`/`rolling_back`), con `ALTER TABLE` idempotente para
  instalaciones existentes. Antes el registro se insertaba tras el DDL y un fallo
  parcial dejaba el esquema cambiado sin registro (el ledger mentía).
- `CachedModel` invalida la clave afectada tras `update`, `delete` y `upsert` (y con
  `insert_many(cache=...)`), **después** del commit y de forma **fail-open**: un fallo
  de invalidación registra un warning y no revierte la escritura. Antes la caché nunca
  se invalidaba, así que una lectura posterior podía servir una fila obsoleta hasta que
  expirara el TTL. La invalidación es local al proceso: no hay pub/sub distribuido, de
  modo que en despliegues multi-proceso las entradas obsoletas quedan acotadas por el
  TTL. Nota de ownership: ADITIVA, no prejuzga la enumeración del milestone (`08-04`).
- El dominio de la caché de `CachedModel` pasa a ser la **PK de la fila** (canónico):
  `load(keys=<no-PK>)` consulta la BD, aprende la PK y recachea bajo ella en vez de
  cachear bajo la clave de lectura, y `update`/`delete`/`upsert` resuelven la PK real
  de la fila afectada —de la instancia si las claves de escritura son la PK; de la BD
  con un `SELECT` ligado y con `scope` si no— antes de invalidar esa única entrada.
  Antes, un write por una clave distinta de la PK (`update(keys=['rfc'])` /
  `upsert(conflict=['rfc'])`) dejaba obsoleta la entrada cacheada bajo la PK y una
  lectura posterior podía servir la fila vieja hasta el TTL (CR-01). CAMBIO DE
  COMPORTAMIENTO: una lectura no-PK deja de acierto en caché. Nota de ownership: esta
  entrada es ADITIVA y no prejuzga la enumeración completa del milestone, que posee la
  Fase 8 (`08-04`).
- `MemoryCacheBackend` pasa a estar acotado con LRU (`max_size=1024` por defecto,
  configurable) y se documenta como backend **dev/test-only**; para producción se usa
  `RedisCacheBackend`. Antes era un `dict` sin cota y las claves nunca releídas se
  acumulaban indefinidamente. Nota de ownership: ADITIVA, no prejuzga la enumeración
  del milestone (`08-04`).
- `CachedModel` ahora invalida la entrada de caché de **TODAS las filas afectadas**
  por una escritura, no solo de una: `update`/`delete`/`upsert` con claves de
  escritura no-PK (`update(keys=["grupo"])`) afectan a todas las filas que casan y
  antes se resolvía e invalidaba una sola PK (la de una fila arbitraria), de modo
  que las demás servían datos obsoletos hasta el TTL (CR-01). La resolución
  reutiliza un `SELECT` ligado, scope-aware y con `include_deleted=True`. Nota de
  ownership: esta entrada es ADITIVA y no prejuzga la enumeración del milestone,
  que posee la Fase 8 (`08-04`).
- La compensación pre-DDL del runner de migraciones borra la fila del ledger por
  la **identidad de la fila** que ESTA llamada insertó (`{id: ledger_id}`,
  capturado best-effort con `last_id()`), no por `{name, status='pending'}`: el
  compare-and-delete podía borrar la fila `pending` que otro runner re-publicaba
  tras nuestro rollback (WR-01 residual). Si el motor no expone un `last_id()`
  utilizable (Oracle devuelve 0), se cae al compare-and-delete documentado,
  residual estrecho asignado a la Fase 4 (`04-02`, POOL-03). Además, un fallo de la
  compensación ya no enmascara la excepción original del DDL (IN-01). Nota de
  ownership: esta entrada es ADITIVA y no prejuzga la enumeración del milestone,
  que posee la Fase 8 (`08-04`).

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
