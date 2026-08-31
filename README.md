# encinorm · v0.1.0

ORM asíncrono de interfaz unificada para **SQLite**, **MySQL** y **PostgreSQL**,
construido sobre `pydantic`. Proporciona un modelo de datos declarativo, CRUD
tipado, validación, relaciones (1:1 y 1:N), consultas con filtros y agregados,
migraciones, y capas opcionales de producto: REST (FastAPI), GraphQL
(Strawberry), seguridad (RBAC + JWT) y generación de código desde la base de
datos.

> **Estado: experimental (v0.1.0).** Encinnorm se encuentra en **fase
> experimental**: la API pública y su comportamiento pueden cambiar **sin previo
> aviso** en versiones posteriores, **sin garantía de compatibilidad
> retroactiva**. El núcleo ORM está probado sobre los tres motores (más de 350
> pruebas, con integraciones reales de MySQL y PostgreSQL), pero no se recomienda
> depender de una API estable en producción. Documentación de usuario en `docs/`;
> estado de preparación en `prompts/analisys-07.md`.

---

## Características

- **Tres motores** con un único API: `SqliteDb`, `MysqlDb`, `PostgresDb`, y un
  pool de conexiones `PoolDb` con transacciones atómicas por `contextvar`.
- **Modelos declarativos** basados en `pydantic`, con restricciones reutilizables
  (`STR_100`, `INT_POS`, `CURRENCY`, `DATETIME`, `DECIMAL`, `JSON`, …).
- **CRUD completo**: `insert`, `save`, `upsert`, `load`, `update`, `delete`,
  `search`, `count`, `paginate`, `insert_many` (bulk).
- **Claves primarias flexibles**: `id` auto-incremental (por defecto), clave
  natural simple o **clave compuesta**, y claves foráneas compuestas.
- **Relaciones**: referencias 1:1, colecciones 1:N (`has_many`), y carga por
  lotes (`batch_reference`/`batch_has_many`) para evitar N+1.
- **Consultas**: `Filter` componible y `QueryBuilder` con `join`, `group_by`,
  agregados (`sum`/`avg`/`min`/`max`/`count`) y subconsultas.
- **Esquema**: `create_table`, migraciones versionadas, `diff_schema` y
  `sync_schema`.
- **Hooks** de ciclo de vida y **caché** (`CachedModel` + `CacheBackend`).
- **Conexión implícita**: `set_default_db`, `bind` y `session` eliminan la
  necesidad de pasar `db` a cada instancia.
- **Observabilidad**: `trace_id` por request y `QueryTracer` con métricas.
- **Capas opcionales**: REST (`create_crud`), GraphQL (`build_schema`),
  seguridad (`emit_token`, `require`, RBAC tri-estado) y CLI/codegen
  (`encinorm generate models`).

---

## Instalación

```bash
# núcleo (SQLite + MySQL + PostgreSQL)
pip install -e .

# con extras opcionales
pip install -e ".[http,security,graphql]"
```

Extras disponibles:

| Extra      | Incluye                                              |
|------------|------------------------------------------------------|
| `http`     | `fastapi` (REST CRUD)                                 |
| `security` | `fastapi` + `PyJWT` (RBAC + JWT)                      |
| `graphql`  | `strawberry-graphql` (GraphQL)                        |

Requiere **Python 3.10+**.

---

## Inicio rápido

```python
import asyncio
from encinorm import create_db
from encinorm.model import Model, Filter, STR_100, INT_POS

class User(Model):
    _table = "users"
    name: STR_100(required=True)
    age: INT_POS()

async def main():
    db = await create_db("sqlite", database=":memory:")

    await User.cursor(db).create_table()       # genera el DDL y lo aplica

    u = User(db, name="Ana", age=30)
    await u.insert()                           # INSERT (id auto-incremental)

    found = await User.cursor(db, id=u.id).load()   # SELECT por clave primaria
    assert found.name == "Ana"

    adults = await User.cursor(db).search(Filter.ge("age", 18))  # SELECT ... WHERE age >= 18
    assert len(adults) == 1

    await db.close()
```

> Ejemplo completo (incluidos `Filter` y las capas REST/GraphQL) en
> `docs/getting-started.md`.

---

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [Getting started](docs/getting-started.md) | Instalación y primer modelo en 5 minutos. |
| [Guía de uso](docs/guide.md) | Modelos, restricciones, CRUD, filtros, relaciones, claves primarias y foráneas. |
| [Integraciones](docs/integrations.md) | REST, GraphQL, seguridad, codegen/CLI y observabilidad. |
| [Agregar un motor](docs/engines.md) | Guía para desarrolladores: cómo añadir un nuevo motor de base de datos. |
| [Créditos](docs/credits.md) | Herramientas y tecnologías utilizadas. |
| [Diseño](docs/) | Documentos de diseño (`design_*.md`) de la arquitectura interna. |

---

## Pruebas

```bash
uv run pytest              # suite completa (SQLite + MySQL + PostgreSQL)
uv run pytest -m "not integration"   # (si los servidores no están disponibles)
```

Las integraciones de MySQL y PostgreSQL se omiten automáticamente si el servidor
correspondiente no está disponible.

---

## Licencia

Distribuido bajo la licencia [MIT](LICENSE). Consulta el archivo `LICENSE`
para el texto íntegro.

---

## Versionado

El proyecto sigue [Versionado Semántico](https://semver.org). Mientras esté en
`0.x`, **no hay garantía de estabilidad**: cada versión *minor* puede introducir
cambios incompatibles. La estabilidad de la API se declarará a partir de `1.0.0`.

---

## Créditos

Desarrollado con la asistencia de **[OpenCode](https://opencode.ai)** y el modelo
**[DeepSeek V4 Pro](https://www.deepseek.com)**. Véase
[docs/credits.md](docs/credits.md) para el detalle completo.
