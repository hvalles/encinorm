# Documento de Diseño — encinorm

Librería asíncrona de interfaz unificada para múltiples motores de base de datos (SQLite, MySQL, PostgreSQL) orientada a desarrolladores Python que trabajan con `asyncio`.

---

## 1. Introducción y Objetivos

**encinorm** es una capa de abstracción sobre `aiosqlite`, `aiomysql` y `asyncpg` que expone una interfaz común (`Db`) para ejecutar operaciones DML, DDL y consultas sin preocuparse por el motor subyacente. El desarrollador escribe el mismo código, y el backend de conexión se encarga de traducirlo al dialecto correspondiente.

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
| 8 | Query reutilizable: permite cambiar valores (`rebind`) manteniendo la plantilla SQL. |


### Audiencia

Desarrolladores Python que usan `asyncio` y requieren cambiar de motor de BD sin reescribir la capa de datos.

---

## 2. Modelo de Datos y Clases

### 2.1. `Query`

Encapsula una sentencia SQL y sus parámetros, aplicando formateo seguro contra inyección. Las queries pueden reutilizarse con nuevos valores mediante el método `rebind`.

```python
class Query:
    def __init__(self, sql: str, fields: list):
        self.sql_template: str = sql       # SQL original con placeholders {0}...{n}
        self.query: list[str, dict]        # [sql_formateado, diccionario_params]
        self.fields: list                  # valores originales
        self._param_name: str = 'parameter_000'

        if sql.find('{0}') != -1:
            self.query = self.format(sql, fields, self._param_name)
        else:
            # raw SQL sin placeholders
            self.query = [sql, {}]

    def format(self, sql, columns: list = [], name='parameter_000') -> list:
        """Reemplaza {0}...{n} por %(name0)s...%(namen)s y construye el dict de parámetros."""
        if not columns:
            return [sql, {}]

        cols = {}
        for i, val in enumerate(columns):
            cols[f"{name}{i}"] = val

        formatted_sql = sql
        for i, key in enumerate(cols):
            formatted_sql = formatted_sql.replace(f"{{{i}}}", f"%({key})s")

        return [formatted_sql, cols]

    def rebind(self, fields: list):
        """Reconstruye el query con nuevos valores, manteniendo la plantilla SQL original.
        Permite reutilizar la misma query para múltiples ejecuciones con distintos datos."""
        self.fields = fields
        self.query = self.format(self.sql_template, fields, self._param_name)
        return self
```

**Ejemplos:**

```python
# Con placeholders
q = Query("insert into grupos (grupo, enabled) values ({0},{1})", ["Grupo A", 1])
# q.query -> ["insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)",
#             {"parameter_0000": "Grupo A", "parameter_0001": 1}]

# Raw SQL (sin placeholders, fields vacío)
q = Query("SELECT * FROM usuarios", [])
# q.query -> ["SELECT * FROM usuarios", {}]

# Reutilizar query con nuevos valores
q.rebind(["Grupo B", 0])
# q.query -> ["insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)",
#             {"parameter_0000": "Grupo B", "parameter_0001": 0}]
```

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

Cada implementación mantiene una tabla interna `_encinorm_migrations` que registra las migraciones aplicadas, permitiendo reproducibilidad y auditoría.

```sql
CREATE TABLE IF NOT EXISTS _encinorm_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- varía por motor
    name TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sql_text TEXT NOT NULL
);
```

**Flujo:**

1. El usuario invoca `await db.migrate("crear_tabla_usuarios", Query(sql, []))`.
2. El método verifica si el `name` ya existe en `_encinorm_migrations`.
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
    paginated_sql = self._apply_limit_offset(qry.query[0], limit, offset)
    return await self.fetch_all(Query(paginated_sql, list(qry.query[1].values())))
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
class EncinormError(Exception): ...
class ConnectionError(EncinormError): ...
class QueryError(EncinormError): ...
class UnsupportedEngineError(EncinormError): ...
class MigrationError(EncinormError): ...
class PoolExhaustedError(EncinormError): ...
```

---

## 3. Estructura de Carpetas

```
encinorm/
├── encinorm/
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
│   └── design.md
├── pyproject.toml
└── README.md
```

---

## 4. Flujo de Uso (Ejemplo Completo)

```python
import asyncio
from encinorm import create_db, Query, PoolDb

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

    # Insert masivo con Query reutilizable
    q_tpl = Query("insert into usuarios (nombre, activo) values ({0},{1})", [])
    for nombre in ["Ana", "Luis", "María"]:
        q_tpl.rebind([nombre, 1])
        await db.execute(q_tpl)

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
