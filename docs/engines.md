# Agregar un motor de base de datos

Esta guía explica cómo extender encino_orm con un nuevo motor (por ejemplo,
**CockroachDB**). El diseño aísla toda la lógica
específica de un motor en **una sola clase** que implementa el contrato `Db`,
más tres puntos de registro (pool, DDL e introspección).

## Arquitectura relevante

```
encino_orm/
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
| MariaDB     | `%(parameter_0000)s` | `%s`        |
| PostgreSQL  | `%(parameter_0000)s` | `$1`, `$2`, … |
| SQL Server  | `%(parameter_0000)s` | `?`         |
| Oracle      | `%(parameter_0000)s` | `:name` (nombrado) |

## Contrato `Db` (métodos abstractos)

Debes implementar, como mínimo:

```python
from encino_orm import Query

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
    def insert(
        self, tabla: str, data: dict, ignore_duplicated=False, replace=False,
        conflict: list[str] | None = None, *, schema: str | None = None,
        returning: str | None = None,
    ): ...
    def delete(self, tabla: str, keys: dict, *, schema: str | None = None): ...
    def update(self, tabla: str, keys: dict, values: dict, *, schema: str | None = None): ...

    # Ejecución / consulta
    async def execute(self, qry: Query) -> int: ...
    async def execute_insert(self, qry: Query) -> int | None: ...
    async def fetch_all(self, qry: Query) -> list[dict]: ...
    async def fetch_one(self, qry: Query) -> dict | None: ...
    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]: ...
    async def exists(self, qry: Query) -> bool: ...
    async def last_id(self) -> int: ...  # DEPRECADO: usa execute_insert()

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
from encino_orm.introspection.types import ColumnSpec, _normalize

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

Copia `encino_orm/sqlite.py` como plantilla y renómbralo. Implementa los métodos
del contrato y, sobre todo, `_prepare`:

```python
# encino_orm/mimotor.py
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

### 2. Implementa la captura del id y el manejo de errores

- `execute_insert(qry)`: ejecuta un INSERT y devuelve el id capturado **dentro
  de la misma sentencia**, o `None` si el motor no lo expone (p. ej. un
  `MERGE`). El `Query` transporta la metadata `returns_id`/`id_column` que fija
  `build_insert(returning=<col>)`. Mecanismo por motor:
  - **SQLite/MySQL/MariaDB:** `cursor.lastrowid` inmediatamente tras el
    `INSERT` (el SQL no cambia).
  - **PostgreSQL:** `INSERT ... RETURNING <pk>` + `fetchrow`. `lastval()` **NO
    es correcto**: es *session-scoped* y devuelve el último `nextval` de la
    sesión (de cualquier tabla y de cualquier tarea que comparta la conexión).
  - **MSSQL:** `OUTPUT INSERTED.<pk>` en el MISMO statement. `@@IDENTITY` **NO
    es correcto** (session-scoped y contaminable por triggers) y
    `SCOPE_IDENTITY()` en un `execute` separado devuelve `NULL`.
  - **Oracle:** `RETURNING <pk> INTO :ret_id` (opt-in). `MERGE ... RETURNING`
    no está soportado (ORA-00933).
- `last_id()` está **DEPRECADO** (emite `DeprecationWarning`): el id post-hoc es
  incorrecto bajo concurrencia. Usa `Db.execute_insert(qry)` o el valor de
  retorno de `Model.insert()`.
- `is_lock_error(exc)`: opcional; devuelve `True` ante deadlocks/bloqueos
  re-reintentables para que `retry()` funcione.
- `is_disconnect_error(exc)`: opcional pero **obligatorio** para que la
  auto-reconexión funcione. Devuelve `True` cuando el error del driver es una
  pérdida de conexión (socket muerto, sesión matada, fichero inalcanzable).
  Regla dura: **exclusión mutua con `is_lock_error`** — un lock NUNCA puede
  clasificarse como desconexión, o el reintento con backoff de `retry()` dejaría
  de reconocerlo. Clasifica por tipo/errno/SQLSTATE/`.full_code`; el substring de
  mensaje solo es **refuerzo** donde el código es genérico (el `HY000` de ODBC en
  MSSQL, cuyos mensajes vienen localizados).
- `_translate_error(exc)`: opcional; mapea la excepción del driver a la taxonomía
  pública (ver abajo). El punto ÚNICO de traducción es `Db._translate_exception`,
  que `_with_reconnect` invoca en todos sus relanzados. Orden: (1) si
  `is_lock_error(exc)` → devuelve el ORIGINAL sin traducir; (2) si ya es
  `EncinoOrmError` → tal cual; (3) si `is_disconnect_error(exc)` →
  `ConnectionLostError`; (4) en otro caso delega en el hook del adaptador. El
  hook NO construye SQL ni interpola valores y nunca incluye `_connect_kwargs`
  (contienen `password`).

**Taxonomía pública de errores.** Las excepciones del driver no deben salir del
adaptador (el contrato de importación diferida prohíbe al usuario depender del
driver). La jerarquía conserva los nombres y bases existentes (`ConnectionError`,
`QueryError`), pero la traducción **REEMPLAZA** la excepción del driver por la de
la librería: `except sqlite3.IntegrityError:` deja de capturarla; captura el tipo
de `encino_orm` o inspecciona `__cause__`.

```python
EncinoOrmError
├── ConnectionError
│   └── ConnectionLostError        # pérdida de conexión (RESL-01/02)
├── OperationalError               # fallo operativo/infra del motor (NO es QueryError)
└── QueryError
    ├── IntegrityError             # UNIQUE / FK / NOT NULL / CHECK
    └── ProgrammingError           # sintaxis / identificador / tipo inválido
```

- `ConnectionLostError` hereda de `ConnectionError`: `except ConnectionError`
  sigue capturando lo que capturaba.
- `IntegrityError`/`ProgrammingError` heredan de `QueryError`; nota HTTP:
  `install_error_handlers` mapea `QueryError` a **400**.
- `OperationalError` deriva de `EncinoOrmError` (NO de `QueryError`): un fallo de
  INFRAESTRUCTURA (servidor caído, timeout) no es culpa del cliente, así que cae
  al **500** genérico. `ConnectionLostError` también es 500.
- Un error de **lock** nunca se traduce: `retry()` clasifica sobre el tipo/args
  ORIGINALES del driver y `_translate_exception` lo devuelve intacto.

> **Desviación deliberada (chaining).** La convención del repo no usa
> `raise ... from`; aquí la traducción SÍ lo usa (`raise ... from exc`) para
> preservar la causa del driver (`__cause__`), que se perdería al REEMPLAZAR el
> tipo de excepción. Es una excepción consciente justificada por ASVS V7
> (diagnóstico del error de driver).

**Ciclo de vida de la conexión directa.** `pre_ping` y `max_connection_lifetime`
son kwargs OPCIONALES de `connect(**kwargs)`, NO del constructor (`PoolDb` y
`create_db` construyen `cls()` sin argumentos):

- `pre_ping=False` por defecto. Al activarlo, cada operación sondea `is_alive()`
  (un round-trip extra) y reconecta **inmediatamente** si la sonda falla.
- `max_connection_lifetime=None` por defecto. Mide **edad** de conexión con
  `time.monotonic()` (semántica de `pool_recycle`), no inactividad; el reciclado
  a nivel de pool es `RELI-03` (v2).

SQLite es embebido y no tiene socket: `SqliteDb._reconnect()` **rechaza** una base
`:memory:` (reconectar crearía una base vacía y perdería los datos) lanzando
`ConnectionLostError`.

### 3. Implementa las migraciones

Copia `_ensure_migrations_table`/`migrate`/`migrate_status` de un motor existente
adaptando el DDL de la tabla `_encino_orm_migrations` a tu motor.

### 4. Registra el motor

```python
# encino_orm/pool.py
from .mimotor import MimotorDb

_ENGINES = {
    "sqlite": SqliteDb,
    "mysql": MysqlDb,
    "mariadb": MariadbDb,
    "postgresql": PostgresDb,
    "mssql": MssqlDb,
    "oracle": OracleDb,
    "mimotor": MimotorDb,     # <-- añade aquí
}
```

```python
# encino_orm/engine.py
class Engine(str, Enum):
    SQLITE = "sqlite"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    POSTGRESQL = "postgresql"
    MSSQL = "mssql"
    ORACLE = "oracle"
    MIMOTOR = "mimotor"        # <-- habilita create_db(Engine.MIMOTOR, ...) y el CLI
```

### 5. Añade el mapeo DDL

```python
# encino_orm/model/types.py
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
# encino_orm/mimotor.py
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
# encino_orm/__init__.py
from .mimotor import MimotorDb
```

El CLI ya lista los motores desde `Engine` (`_ENGINE_CHOICES = [e.value for e in Engine]`),
así que al añadir `MIMOTOR` al enum queda disponible automáticamente.

### 8. Escribe pruebas

Sigue el patrón de `tests/test_mysql.py`: crea una fixture que se **omite** si el
servidor no está disponible, y valida `connect`/CRUD/`execute_insert`/`migrate`
contra el motor real.

## Checklist

- [ ] Clase que hereda `Db` con `dialect` y todos los abstractos.
- [ ] `_prepare` traduce `%(...)s` al placeholder nativo.
- [ ] `insert`/`update`/`delete` respetan los flags `ignore_duplicated`/`replace`.
- [ ] `execute_insert()` captura el id dentro del INSERT (o `None` si no se pide) y `is_lock_error()` (si aplica).
- [ ] Migraciones con tabla `_encino_orm_migrations` idempotente.
- [ ] `_tables_sql()` y `columns_of()` (introspección, opcional) para codegen/diff/transfer.
- [ ] Registro en `Engine` (enum), `_ENGINES` y `DDL_MAP`.
- [ ] Exportación en `encino_orm/__init__.py`.
- [ ] Pruebas de integración que se omiten si no hay servidor.

## Referencia

- `encino_orm/base.py` — el contrato `Db` y `transaction()`/`retry()`.
- `encino_orm/query.py` — el formato intermedio `Query`.
- `encino_orm/sqlite.py` — implementación mínima de referencia.
- `encino_orm/postgresql.py` — ejemplo con `transaction()` propio y errores de
  bloqueo de `asyncpg`.
- `encino_orm/mysql.py` — ejemplo con `DictCursor` y `lastrowid`.
