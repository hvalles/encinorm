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
- **Documentos de diseño** (`design_*.md`) — arquitectura interna:
  - `design_model.md` — el núcleo `Model`.
  - `design_constraint.md` — restricciones y tipos de dato.
  - `design_crud.md` — operaciones CRUD.
  - `design_security.md` — RBAC y JWT.
  - `design_graphql.md` — capa GraphQL.
  - `design_from_db.md` — introspección y codegen.
  - `design_missing.md` — migraciones, bulk, scope, observabilidad, CLI.
  - `design_pk.md` — claves primarias (simples/compuestas) y foráneas.
  - `design_singleton.md` — conexión por defecto / ambiente.

## Convenciones

- Todo el código asíncrono usa `async`/`await` (corrutinas).
- Los nombres de modelo/clase son `PascalCase`; las tablas y columnas, `snake_case`.
- Los métodos CRUD devuelven `Model`, `int` o listas tipadas; los errores se
  lanzan como excepciones (`ValidationError`, `NotFoundError`, `FailOnUpdate`, …).
