# Documento de Diseño — encino_orm

Librería asíncrona de interfaz unificada para múltiples motores de base de datos (SQLite, MySQL, PostgreSQL) orientada a desarrolladores Python que trabajan con `asyncio`.

---

## 1. Introducción y Objetivos

**encino_orm** es una capa de abstracción sobre `aiosqlite`, `aiomysql` y `asyncpg` que expone una interfaz común (`Db`) para ejecutar operaciones DML, DDL y consultas sin preocuparse por el motor subyacente. El desarrollador escribe el mismo código, y el backend de conexión se encarga de traducirlo al dialecto correspondiente.

### Objetivos

| # | Objetivo |
|---|----------|
| 1 | Proveer una clase abstracta `Db` con métodos asíncronos estándar. |
| 2 | Implementar backends para SQLite, MySQL y PostgreSQL. |
| 3 | Incluir una clase `Query` que evite inyección SQL mediante parámetros posicionales. |
| 4 | Soportar ciclo de vida completo: `connect`, `close`, `commit`, `rollback`, `transaction`. |
| 5 | Sistema de migraciones DDL versionado y reproducible, con registro en BD. |
| 6 | Pool de conexiones integrado para entornos web (FastAPI, aiohttp). |
| 7 | Paginación de consultas mediante `fetch_many`. |
| 8 | Query inmutable y hashable, reutilizable con nuevos valores (`with_params`) manteniendo la plantilla SQL. |


### Audiencia

Desarrolladores Python que usan `asyncio` y requieren cambiar de motor de BD sin reescribir la capa de datos.

---

## 2. Modelo de Datos y Clases

### 2.1. `Query`

Encapsula una sentencia SQL y sus parámetros, aplicando formateo seguro contra inyección. Es un value object **inmutable a nivel de atributo** y hashable: los valores se sustituyen con `with_params()`, que devuelve una **copia** nueva y deja intacto el original.

**Contrato de entrada.** `Query(sql_con_{n}, [valores])`. Los índices pueden aparecer dispersos o repetidos en el texto (`{1}` antes de `{0}`, o `{0}` dos veces), pero el conjunto de índices detectados debe ser exactamente `range(len(values))`: ningún índice fuera de rango y ningún parámetro declarado sin usar. La violación lanza `ValueError` en la construcción. Los valores SIEMPRE viajan como parámetros ligados; la plantilla nunca se interpola con valores.

```python
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


class Query:
    __slots__ = ("_fields", "_ignore_duplicated", "_params", "_sql", "_sql_template")

    def __init__(self, sql: str, fields: list | None = None, *,
                 ignore_duplicated: bool = False):
        values = list(fields or [])
        indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}
        if indices != set(range(len(values))):
            raise ValueError(
                f"placeholders {sorted(indices)} no cuadran con {len(values)} parámetros"
            )
        params = {f"parameter_000{i}": v for i, v in enumerate(values)}
        compiled = _PLACEHOLDER_RE.sub(lambda m: f"%(parameter_000{int(m.group(1))})s", sql)
        object.__setattr__(self, "_sql_template", sql)
        object.__setattr__(self, "_fields", values)
        object.__setattr__(self, "_ignore_duplicated", bool(ignore_duplicated))
        object.__setattr__(self, "_sql", compiled)
        object.__setattr__(self, "_params", params)

    @property
    def sql(self) -> str: ...             # SQL compilado con %(parameter_0000)s
    @property
    def params(self) -> dict: ...         # {"parameter_0000": valor, ...}
    @property
    def sql_template(self) -> str: ...    # plantilla original con {0}...{n}
    @property
    def fields(self) -> list: ...         # valores de entrada
    @property
    def ignore_duplicated(self) -> bool: ...
    @property
    def query(self) -> list: ...          # compatibilidad de lectura: [sql, params]

    def with_params(self, fields: list) -> "Query":
        """Copia con nuevos valores; revalida la cardinalidad."""
        return Query(self.sql_template, fields,
                     ignore_duplicated=self.ignore_duplicated)
```

Los slots van con guion bajo y la superficie legible se expone con **properties sin setter**: un `__slots__` plano es un descriptor escribible (asignar `q.fields = []` tendría éxito), y declarar a la vez el slot `"fields"` y la property `fields` lanza `ValueError` al crear la clase. La inmutabilidad es de **atributo, no profunda**: `q.fields` es una lista mutable y `q.params` expone el dict interno por referencia, así que `q.fields.append(v)` no lanza; es un uso NO soportado que además invalida el hash (que se calcula del estado vivo). Otra limitación conocida: un `{n}` dentro de un literal de cadena se interpreta como placeholder; esta versión no parsea literales SQL.

**Ejemplos:**

```python
# Con placeholders
q = Query("insert into grupos (grupo, enabled) values ({0},{1})", ["Grupo A", 1])
# q.sql    -> "insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)"
# q.params -> {"parameter_0000": "Grupo A", "parameter_0001": 1}

# Índices dispersos y duplicados
q = Query("a={1} AND b={0} OR c={0}", [10, 20])
# q.sql -> "a=%(parameter_0001)s AND b=%(parameter_0000)s OR c=%(parameter_0000)s"

# Raw SQL (sin placeholders, fields vacío)
q = Query("SELECT * FROM usuarios", [])
# q.sql    -> "SELECT * FROM usuarios"
# q.params -> {}

# Reutilizar la plantilla con nuevos valores: devuelve una COPIA
q = Query("insert into grupos (grupo, enabled) values ({0},{1})", ["Grupo A", 1])
q2 = q.with_params(["Grupo B", 0])
# q2.sql    -> "insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)"
# q2.params -> {"parameter_0000": "Grupo B", "parameter_0001": 0}
# q sigue intacta, con fields == ["Grupo A", 1]

# Pasar valores a una plantilla SIN {n} viola el contrato de cardinalidad y
# lanza ValueError (no descarta los parámetros en silencio):
# Query("SELECT * FROM usuarios", []).with_params(["Grupo B", 0])  # -> ValueError
```

> **Migración:** `rebind` se eliminó en 0.3.0 (ruptura limpia, sin shims). Su sustituto es `with_params()`, que **devuelve una copia** en vez de mutar el objeto en sitio. La igualdad y el hash se calculan sobre `(plantilla_sql, valores)`; el flag `ignore_duplicated` queda excluido a propósito.

> **Seguridad:** Todo SQL debe pasar por `Query`. No se aceptan strings SQL crudos fuera de `Query` en ningún método de ejecución.

### 2.2. `Db` (Interfaz Abstracta)

```python
class Db(ABC):
    # --- Variables definidas ---
    MAX_TRIES = 9
    WAITERS = [x*0.02 for x in range(1,11)]
    MAX_WAIT = len(WAITERS)-1

    # --- Ciclo de vida ---
    @abstractmethod
    async def connect(self, **kwargs): ...
    @abstractmethod
    async def is_alive(self): ...
    @abstractmethod
    async def close(self): ...
    @abstractmethod
    async def transaction(self) -> AsyncContextManager: ...
    @abstractmethod
    async def in_transaction(self): ...
    @abstractmethod
    async def commit(self): ...
    @abstractmethod
    async def rollback(self, save_point: str = None): ...
    @abstractmethod
    async def save_point(self, name: str): ...
    @staticmethod
    async def wait(waiter: int = -1):
        """Mecanismo de espera en caso de bloqueo por deadlock en la base de datos."""
        if waiter < 0:
            waiter = random.randint(0, Db.MAX_WAIT)
        await asyncio.sleep(Db.WAITERS[waiter])
        return waiter
    # --- DML Builders (construyen Query, no ejecutan) ---
    @abstractmethod
    def insert(self, tabla: str, data: dict, ignore_duplicated=False, replace=False) -> Query: ...
    @abstractmethod
    def delete(self, tabla: str, keys: dict) -> Query: ...
    @abstractmethod
    def update(self, tabla: str, keys: dict, values: dict) -> Query: ...

    # --- Ejecución / Consulta ---
    @abstractmethod
    async def execute(self, qry: Query) -> int: ...
    @abstractmethod
    async def fetch_all(self, qry: Query) -> list[dict]: ...
    @abstractmethod
    async def fetch_one(self, qry: Query) -> dict | None: ...
    @abstractmethod
    async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]: ...
    @abstractmethod
    async def exists(self, qry: Query) -> bool: ...
    @abstractmethod
    async def last_id(self) -> int: ...

    # --- Migraciones ---
    @abstractmethod
    async def migrate(self, name: str, qry: Query): ...
    @abstractmethod
    async def migrate_status(self) -> list[dict]: ...
```

> **Nota:** `insert`, `delete` y `update` solo construyen el `Query`; la ejecución real la hace `execute`. Esto permite modificar el `Query` antes de ejecutarlo si se desea.

> **Ciclo de vida / recuperación:**
> - `is_alive()` devuelve `True` si la conexión está abierta y responde a una consulta mínima (`SELECT 1`).
> - `in_transaction()` devuelve `True` si el motor mantiene una transacción activa sin confirmar.
> - `save_point(name)` crea un punto de recuperación (`SAVEPOINT name`).
> - `rollback(save_point=None)` revierte toda la transacción; si se pasa `save_point`, revierte solo hasta ese punto
>   (`ROLLBACK TO SAVEPOINT name`) en los motores que lo soporten.
> - `wait(waiter=-1)` es un método **concreto** (no abstracto) de reintento: duerme una espera aleatoria
>   (`WAITERS`) para mitigar bloqueos/deadlocks; `MAX_TRIES` limita los reintentos del decorador de la sección 2.3.

> **Tipo de datos** se debe de considerar las diferencias entre los dialectos DDL de los motores de base de datos, creando un 
mecanismo de enlace entre las diferentes tipos de datos y caracteristicas de la base de datos

### 2.3. Implementaciones Concretas

| Clase           | Motor       | Dependencia    | Placeholder |
|-----------------|-------------|----------------|-------------|
| `SqliteDb(Db)`  | SQLite      | `aiosqlite`    | `?`         |
| `MysqlDb(Db)`   | MySQL       | `aiomysql`     | `%s`        |
| `PostgresDb(Db)`| PostgreSQL  | `asyncpg`      | `$1, $2...` |

Cada implementación resuelve:
- Dialecto SQL específico (placeholders, tipos de dato).
- Palabras reservadas para `INSERT OR IGNORE` / `INSERT OR REPLACE` / `ON DUPLICATE KEY UPDATE` / `ON CONFLICT`.
- Manejo de `lastrowid` / `RETURNING id`.
- Traducción del `format` de `Query` al placeholder nativo del motor al momento de ejecutar.
- Mecanismo de fecha y tiemnpo de acuerdo al estandar ISO8601 vinculdo al datetime de python
- Context Manager para las transacciones y rollback con save point explicito
- `rollback(save_point=None)` revierte toda la transacción, o bien hasta el `save_point` indicado
  (`ROLLBACK TO SAVEPOINT`) si el motor lo soporta.
- Decorador (hasta MAX_TRIES o lo que se le indique al decorador) para reintentos en caso de detectar error de bloqueo
  haciendo una espera aleatoria con db.wait, detectando el choque de acuerdo a cada base de datos.

### 2.4. Sistema de Migraciones

Cada implementación mantiene una tabla interna `_encino_orm_migrations` que registra las migraciones aplicadas, permitiendo reproducibilidad y auditoría.

```sql
CREATE TABLE IF NOT EXISTS _encino_orm_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- varía por motor
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sql_text TEXT NOT NULL
);
```

**Flujo:**

1. El usuario invoca `await db.migrate("crear_tabla_usuarios", Query(sql, []))`.
2. El método verifica si el `name` ya existe en `_encino_orm_migrations`.
3. Si no existe, ejecuta el SQL, lo registra en la tabla y hace commit.
4. Si ya existe, no hace nada (idempotente).
5. `migrate_status()` devuelve el historial completo de migraciones aplicadas.

```python
# Ejemplo
await db.migrate("v1_crear_usuarios", Query("""
    CREATE TABLE usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        email TEXT UNIQUE
    )
""", []))

await db.migrate("v2_agregar_edad", Query("""
    ALTER TABLE usuarios ADD COLUMN edad INTEGER DEFAULT 0
""", []))

historico = await db.migrate_status()
# [{"name": "v1_crear_usuarios", "applied_at": "...", ...}, ...]
```

### 2.5. Pool de Conexiones (`PoolDb`)

Wrapper que administra un pool de conexiones para entornos concurrentes (FastAPI, aiohttp). Expone la misma interfaz `Db` pero gestiona múltiples conexiones internamente.

```python
class PoolDb(Db):
    def __init__(self, engine: str, min_size: int = 2, max_size: int = 10, **conn_kwargs):
        self._engine = engine
        self._min_size = min_size
        self._max_size = max_size
        self._conn_kwargs = conn_kwargs
        self._pool: asyncio.Queue[Db] = asyncio.Queue()
        self._active: int = 0

    async def connect(self):
        """Inicializa el pool creando min_size conexiones."""
        for _ in range(self._min_size):
            db = await self._create_connection()
            await self._pool.put(db)

    async def acquire(self) -> Db:
        """Obtiene una conexión del pool. Si no hay disponibles y no se alcanzó max_size, crea una nueva."""
        ...

    async def release(self, db: Db):
        """Devuelve la conexión al pool."""
        ...

    async def close(self):
        """Cierra todas las conexiones del pool."""
        ...

    # Los métodos DML/DQL delegan en acquire() -> operación -> release()
    async def fetch_all(self, qry: Query) -> list[dict]:
        db = await self.acquire()
        try:
            return await db.fetch_all(qry)
        finally:
            await self.release(db)
    # ... misma lógica para execute, fetch_one, fetch_many, exists, insert, etc.
```

**Uso típico con FastAPI:**

```python
pool = PoolDb("postgresql", min_size=5, max_size=20, host="...", database="...")
await pool.connect()

async def get_db():
    db = await pool.acquire()
    try:
        yield db
    finally:
        await pool.release(db)

app.include_router(router, dependencies=[Depends(get_db)])
```

### 2.6. Paginación (`fetch_many`)

```python
async def fetch_many(self, qry: Query, limit: int, page: int) -> list[dict]:
    """Ejecuta qry con LIMIT y OFFSET calculado desde page.
    offset = (page - 1) * limit.
    page es 1-indexado."""
    offset = (page - 1) * limit
    paginated_sql = self._apply_limit_offset(qry.sql, limit, offset)
    return await self.fetch_all(Query(paginated_sql, list(qry.params.values())))
```

**Ejemplo:**

```python
# Página 2, 10 registros por página -> offset = 10, limit = 10
resultados = await db.fetch_many(Query("SELECT * FROM usuarios ORDER BY id", []), limit=10, page=2)
```

### 2.7. Módulo de Conexión (Factory)

```python
async def create_db(engine: str, **kwargs) -> Db:
    """Factory asíncrona. engine ∈ {'sqlite','mysql','postgresql'}"""
    if engine == 'sqlite':
        db = SqliteDb()
    elif engine == 'mysql':
        db = MysqlDb()
    elif engine == 'postgresql':
        db = PostgresDb()
    else:
        raise UnsupportedEngineError(engine)
    await db.connect(**kwargs)
    return db
```

### 2.8. Excepciones

```python
class EncinoOrmError(Exception): ...
class ConnectionError(EncinoOrmError): ...
class QueryError(EncinoOrmError): ...
class UnsupportedEngineError(EncinoOrmError): ...
class MigrationError(EncinoOrmError): ...
class PoolExhaustedError(EncinoOrmError): ...
```

---

## 3. Estructura de Carpetas

```
encino_orm/
├── encino_orm/
│   ├── __init__.py          # expone create_db, PoolDb, Db, Query, excepciones
│   ├── base.py              # clase abstracta Db
│   ├── query.py             # clase Query
│   ├── sqlite.py            # SqliteDb
│   ├── mysql.py             # MysqlDb
│   ├── postgresql.py        # PostgresDb
│   ├── pool.py              # PoolDb wrapper
│   ├── migration.py         # lógica base de migraciones (mixin o helper)
│   └── exceptions.py        # jerarquía de excepciones
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # fixtures compartidos (DB en memoria, etc.)
│   ├── test_query.py
│   ├── test_sqlite.py
│   ├── test_mysql.py
│   ├── test_postgresql.py
│   ├── test_migrations.py
│   └── test_pool.py
├── docs/
│   └── 0-design.md
├── pyproject.toml
└── README.md
```

---

## 4. Flujo de Uso (Ejemplo Completo)

```python
import asyncio
from encino_orm import create_db, Query, PoolDb

async def ejemplo_basico():
    db = await create_db("sqlite", database=":memory:")

    # DDL vía migraciones
    await db.migrate("v1_crear_usuarios", Query("""
        CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            activo INTEGER DEFAULT 1
        )
    """, []))

    # Insert
    q = db.insert("usuarios", {"nombre": "Héctor", "activo": 1})
    await db.execute(q)
    print(await db.last_id())  # -> 1

    # Insert con ignore_duplicated
    q2 = db.insert("usuarios", {"nombre": "Héctor", "activo": 1}, ignore_duplicated=True)
    await db.execute(q2)

    # Insert masivo con Query reutilizable (with_params devuelve una copia)
    q_tpl = Query("insert into usuarios (nombre, activo) values ({0},{1})", ["Ana", 1])
    await db.execute(q_tpl)
    for nombre in ["Luis", "María"]:
        await db.execute(q_tpl.with_params([nombre, 1]))

    # Paginación
    pagina1 = await db.fetch_many(Query("SELECT * FROM usuarios ORDER BY id", []), limit=2, page=1)
    pagina2 = await db.fetch_many(Query("SELECT * FROM usuarios ORDER BY id", []), limit=2, page=2)
    print("Página 1:", pagina1)
    print("Página 2:", pagina2)

    # Update
    q_upd = db.update("usuarios", {"id": 1}, {"activo": 0})
    await db.execute(q_upd)

    # Exists
    q_ex = db.exists(Query("SELECT 1 FROM usuarios WHERE id=1", []))
    print(await q_ex)  # -> True

    # Delete
    q_del = db.delete("usuarios", {"id": 4})
    await db.execute(q_del)

    # Historial de migraciones
    for m in await db.migrate_status():
        print(f"  {m['name']} — {m['applied_at']}")

    await db.close()


async def ejemplo_pool():
    pool = PoolDb("sqlite", min_size=2, max_size=5, database="app.db")
    await pool.connect()

    # El pool maneja acquire/release internamente
    usuarios = await pool.fetch_all(Query("SELECT * FROM usuarios", []))
    print(usuarios)

    await pool.close()


asyncio.run(ejemplo_basico())
```

---

## 5. Estrategia de Testing

- `pytest` + `pytest-asyncio`.
- SQLite se prueba en memoria (`:memory:`).
- MySQL y PostgreSQL requieren contenedores Docker o servicios CI (se evaluará usar `testcontainers-python`).
- Pruebas organizadas por módulo: query, motores, migraciones, pool.
- Las pruebas de migraciones verifican idempotencia (ejecutar dos veces la misma migración no falla).

```toml
# pyproject.toml (extracto)
[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "aiosqlite", "aiomysql", "asyncpg"]
```
