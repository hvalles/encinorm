# Contexto y conexión implícita

Mecanismos para resolver la conexión por defecto y evitar pasar `db` a cada
instancia.

El default vive en un `ConnectionRegistry` inyectable (estado de instancia) o en
el `_registry` de módulo al que apunta `resolve_db()` sin argumentos. Los shims
`set_default_db`/`get_default_db` se **retiraron** en `0.3.0` (`REL-01`).

::: encino_orm.ConnectionRegistry

::: encino_orm.bind

::: encino_orm.resolve_db

::: encino_orm.session

Fronteras de confianza: ver [trust-boundaries.md](../trust-boundaries.md).
