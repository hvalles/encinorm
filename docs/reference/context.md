# Contexto y conexión implícita

Mecanismos para resolver la conexión por defecto y evitar pasar `db` a cada
instancia.

El default vive en un `ConnectionRegistry` inyectable (estado de instancia, no
un global mutable de proceso). `set_default_db`/`get_default_db` siguen
funcionando como shims **DEPRECADOS** (emiten `DeprecationWarning`) y se retiran
en la Fase 8 (`REL-01`).

::: encino_orm.ConnectionRegistry

::: encino_orm.set_default_db

::: encino_orm.get_default_db

::: encino_orm.bind

::: encino_orm.resolve_db

::: encino_orm.session

Fronteras de confianza: ver [trust-boundaries.md](../trust-boundaries.md).
