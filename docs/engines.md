# Agregar un motor de base de datos

Esta guía explica cómo extender encinorm con un nuevo motor (por ejemplo,
**MSSQL**, **Oracle** o **CockroachDB**). El diseño aísla toda la lógica
específica de un motor en **una sola clase** que implementa el contrato `Db`,
más tres puntos de registro (pool, DDL e introspección).

## Arquitectura relevante

```
encinorm/
├── base.py            # Db (ABC): contrato + list_tables/paginate + transaction/retry
├── engine.py          # Engine (enum) + engine_of/is_* + funciones portables db.fn
├── query.py           # Query: SQL + parámetros (formato intermedio)
├── pool.py            # PoolDb + registro _ENGINES
├── sqlite.py          # motor SQLite (SQL nativo: placeholders, catálogo, columnas)
├── mysql.py
├── postgresql.py
└── model/types.py     # DDL_MAP (datatype lógico -> DDL por motor)
└── introspection/types.py  # ColumnSpec + _normalize (agnóstico del motor)
```

### El protocolo `Query`

Los *builders* (`insert`, `update`, `delete`, …) construyen un `Query` cuyo SQL
usa placeholders genéricos `{0}`, `{1}`, …:

```python
Query("INSERT INTO t (a) VALUES ({0})", [42])
```

`Query.__init__` convierte esos `{n}` a placeholders **intermedios**
`%(parameter_0000)s` con un dict `{parameter_0000: 42, ...}`. Cada motor
implementa `_prepare(qry)` para traducirlos a su placeholder nativo:

| Motor       | Intermedio         | Nativo       |
|-------------|--------------------|--------------|
| SQLite      | `%(parameter_0000)s` | `?`         |
| MySQL       | `%(parameter_0000)s` | `%s`        |
| PostgreSQL  | `%(parameter_0000)s` | `$1`, `$2`, … |

## Contrato `Db` (métodos abstractos)

Debes implementar, como mínimo:

```python
from encinorm import Query

class MiMotorDb(Db):
    dialect = "mimotor"          # identificador del motor

    async def connect(self, **kwargs): ...   # abre la conexión
    async def close(self): ...               # cierra la conexión
    async def is_alive(self) -> bool: ...    # SELECT 1 / ping
    async def in_transaction(self) -> bool: ...

    async def commit(self): ...
    async def rollback(self, save_point: str = None): ...
    async def save_point(self, name: str): ...

    # Builders (construyen Query, NO ejecutan)
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False): ...
    def delete(self, tabla: str, keys: dict): ...
    def update(self, tabla: str, keys: dict, values: dict): ...

    # Ejecución / consulta
    async def execute(self, qry: Query) -> int: ...
    async def fetch_all(self, qry: Query) -> list[dict]: ...
    async def fetch_one(self, qry: Query) -> dict | None: ...
    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]: ...
    async def exists(self, qry: Query) -> bool: ...
    async def last_id(self) -> int: ...

    # Migraciones
    async def migrate(self, name: str, qry: Query): ...
    async def migrate_status(self) -> list[dict]: ...
```

`transaction()`, `retry()` y `wait()` ya están implementados en `Db`; puedes
sobreescribir `transaction()` si tu driver expone un contexto transaccional
propio (como hace `asyncpg`).

Además, para soportar **introspección** (codegen, `diff_schema`, `transfer`),
implementa **opcionalmente** (si no, lanzan `NotImplementedError`):

```python
from encinorm.introspection.types import ColumnSpec, _normalize

    # Introspección (opcional)
    def _tables_sql(self) -> str:
        return "SELECT ... AS name FROM <catálogo> ..."

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(f"... {table} ...", []))
        return [ColumnSpec(name=..., raw_type=..., datatype=_normalize(...)[0], ...) for ...]
```

`list_tables()` (filtro por nombre + paginación + `Records`) **ya está
implementado** en `Db` y usa `_tables_sql()`.

## Paso a paso

### 1. Crea el módulo del motor

Copia `encinorm/sqlite.py` como plantilla y renómbralo. Implementa los métodos
del contrato y, sobre todo, `_prepare`:

```python
# encinorm/mimotor.py
import re

_PLACEHOLDER_RE = re.compile(r"%\(([A-Za-z0-9_]+)\)s")

def _to_native(sql: str, params: dict) -> tuple[str, list]:
    values = []
    def repl(match):
        values.append(params[match.group(1)])
        return "?"                    # o "%s", "$n", etc.
    return _PLACEHOLDER_RE.sub(repl, sql), values

class MimotorDb(Db):
    dialect = "mimotor"

    def _prepare(self, qry: Query) -> tuple[str, list]:
        return _to_native(qry.query[0], qry.query[1])

    # ... resto de métodos ...
```

### 2. Implementa `last_id` y el manejo de errores

- `last_id()`: usa el mecanismo nativo (`last_insert_rowid()`, `lastrowid`,
  `lastval()`, …). Devuelve `0` si no aplica (clave no auto-incremental).
- `is_lock_error(exc)`: opcional; devuelve `True` ante deadlocks/bloqueos
  re-reintentables para que `retry()` funcione.

### 3. Implementa las migraciones

Copia `_ensure_migrations_table`/`migrate`/`migrate_status` de un motor existente
adaptando el DDL de la tabla `_encinorm_migrations` a tu motor.

### 4. Registra el motor

```python
# encinorm/pool.py
from .mimotor import MimotorDb

_ENGINES = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "postgresql": PostgresDb,
    "mimotor": MimotorDb,     # <-- añade aquí
}
```

```python
# encinorm/engine.py
class Engine(str, Enum):
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MIMOTOR = "mimotor"        # <-- habilita create_db(Engine.MIMOTOR, ...) y el CLI
```

### 5. Añade el mapeo DDL

```python
# encinorm/model/types.py
DDL_MAP["mimotor"] = {
    "pk": "...",        # clave primaria auto-incremental
    "str": "...",
    "int": "...",
    "bool": "...",
    "datetime": "...",
    "date": "...",
    "numeric": "...",
    "float": "...",
    "blob": "...",
    "json": "...",
}
```

### 6. Implementa la introspección (en tu motor)

```python
# encinorm/mimotor.py
from .introspection.types import ColumnSpec, _normalize

class MimotorDb(Db):
    # ...

    def _tables_sql(self) -> str:
        return "SELECT name FROM <catálogo> WHERE ..."

    async def columns_of(self, table: str) -> list[ColumnSpec]:
        rows = await self.fetch_all(Query(f"... FROM {table}", []))
        return [
            ColumnSpec(
                name=..., raw_type=..., datatype=_normalize(...)[0],
                nullable=..., primary_key=..., max_length=_normalize(...)[1],
                unsigned=_normalize(...)[2],
            )
            for ...
        ]
```

`list_tables()` (filtro + paginación) ya lo provee `Db` sobre `_tables_sql()`.

### 7. Exporta el motor

```python
# encinorm/__init__.py
from .mimotor import MimotorDb
```

El CLI ya lista los motores desde `Engine` (`_ENGINE_CHOICES = [e.value for e in Engine]`),
así que al añadir `MIMOTOR` al enum queda disponible automáticamente.

### 8. Escribe pruebas

Sigue el patrón de `tests/test_mysql.py`: crea una fixture que se **omite** si el
servidor no está disponible, y valida `connect`/CRUD/`last_id`/`migrate` contra
el motor real.

## Checklist

- [ ] Clase que hereda `Db` con `dialect` y todos los abstractos.
- [ ] `_prepare` traduce `%(...)s` al placeholder nativo.
- [ ] `insert`/`update`/`delete` respetan los flags `ignore_duplicated`/`replace`.
- [ ] `last_id()` correcto y `is_lock_error()` (si aplica).
- [ ] Migraciones con tabla `_encinorm_migrations` idempotente.
- [ ] `_tables_sql()` y `columns_of()` (introspección, opcional) para codegen/diff/transfer.
- [ ] Registro en `Engine` (enum), `_ENGINES` y `DDL_MAP`.
- [ ] Exportación en `encinorm/__init__.py`.
- [ ] Pruebas de integración que se omiten si no hay servidor.

## Referencia

- `encinorm/base.py` — el contrato `Db` y `transaction()`/`retry()`.
- `encinorm/query.py` — el formato intermedio `Query`.
- `encinorm/sqlite.py` — implementación mínima de referencia.
- `encinorm/postgresql.py` — ejemplo con `transaction()` propio y errores de
  bloqueo de `asyncpg`.
- `encinorm/mysql.py` — ejemplo con `DictCursor` y `lastrowid`.
