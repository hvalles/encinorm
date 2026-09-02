# Documentación de encinorm

Bienvenido a la documentación de **encinorm**, el ORM asíncrono de interfaz
unificada para SQLite, MySQL y PostgreSQL.

## Primeros pasos

- **[Getting started](getting-started.md)** — instalación y tu primer modelo en
  5 minutos.
- **[Guía de uso](guide.md)** — modelos, restricciones, CRUD, filtros,
  relaciones, claves primarias/foráneas, migraciones y caché.
- **[Integraciones](integrations.md)** — REST (FastAPI), GraphQL, seguridad
  (RBAC + JWT), codegen/CLI y observabilidad.

## Para desarrolladores

- **[Agregar un motor](engines.md)** — cómo extender encinorm con un nuevo motor
  de base de datos (contrato `Db`, placeholders, DDL e introspección).
- **[Créditos](credits.md)** — herramientas y tecnologías utilizadas.
- **Documentos de diseño** (`docs/design/`) — arquitectura interna:
  - [`design/0-design.md`](design/0-design.md) — capa `Db` y arquitectura base.
  - [`design/1-model.md`](design/1-model.md) — el núcleo `Model`.
  - [`design/2-constraint.md`](design/2-constraint.md) — restricciones y tipos de dato.
  - [`design/3-graphql.md`](design/3-graphql.md) — capa GraphQL.
  - [`design/4-crud.md`](design/4-crud.md) — operaciones CRUD.
  - [`design/5-security.md`](design/5-security.md) — RBAC y JWT.
  - [`design/6-from_db.md`](design/6-from_db.md) — introspección y codegen.
  - [`design/7-missing.md`](design/7-missing.md) — migraciones, bulk, scope, observabilidad, CLI.
  - [`design/8-pk.md`](design/8-pk.md) — claves primarias (simples/compuestas) y foráneas.
  - [`design/9-singleton.md`](design/9-singleton.md) — conexión por defecto / ambiente.
  - [`design/10-report.md`](design/10-report.md) — reporteador financiero (`encinorm-report`).

## Convenciones

- Todo el código asíncrono usa `async`/`await` (corrutinas).
- Los nombres de modelo/clase son `PascalCase`; las tablas y columnas, `snake_case`.
- Los métodos CRUD devuelven `Model`, `int` o listas tipadas; los errores se
  lanzan como excepciones (`ValidationError`, `NotFoundError`, `FailOnUpdate`, …).
