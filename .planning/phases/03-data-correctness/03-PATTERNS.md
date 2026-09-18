# Phase 3: Data Correctness - Pattern Map

**Mapped:** 2026-09-18
**Files analyzed:** 25 (17 modificados, 3 nuevos de test, 3 tests extendidos, 2 docs/gates)
**Analogs found:** 25 / 25 (todos tienen analog exacto o role-match; ninguno sin analog)

> Nota de método: todos los adaptadores comparten la misma forma de `migrate()`/`_ensure_migrations_table()`; el map de analog por adaptador apunta a su propio fichero (exact) más el adaptador canónico para la receta nueva. Las decisiones D-01…D-17 y las enmiendas D-15/D-16/D-17 de `03-CONTEXT.md` y `03-RESEARCH.md` son autoritativas sobre cualquier sketch de este documento.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `encino_orm/migration.py` | service (migration runner/ledger) | state-machine + CRUD | sí mismo (`migration.py`) + `base.py` (logger/transaction) | exact |
| `encino_orm/dialects/strategies.py` | config (dialect data map) | lookup/transform | `UPSERT_KIND` + `LIMITS` (mismo fichero) | exact |
| `encino_orm/dialects/__init__.py` | config (barrel) | re-export | su propio bloque de imports/`__all__` | exact |
| `encino_orm/base.py` | abstract base (config attr) | n/a | `dialect: str = ""` / `transaction()` | exact |
| `encino_orm/pool.py` | wrapper (delegation) | request-response | propiedades `MAX_PARAMS`/`MAX_ROWS` + `migrate` | exact |
| `encino_orm/sqlite.py` | adapter (migration) | DDL + ledger | `migrate`/`_ensure_migrations_table`/`columns_of` propios | exact |
| `encino_orm/mysql.py` | adapter (migration) | DDL + ledger | idem MySQL | exact |
| `encino_orm/mariadb.py` | adapter (migration) | DDL + ledger | hereda `MysqlDb`; solo `dialect`/`LIMITS` | exact |
| `encino_orm/postgresql.py` | adapter (migration) | DDL + ledger | idem PostgreSQL (usa `async with self.transaction()`) | exact |
| `encino_orm/mssql.py` | adapter (migration) | DDL + ledger | idem MSSQL | exact |
| `encino_orm/oracle.py` | adapter (migration) | DDL + ledger | idem Oracle | exact |
| `encino_orm/model/cached.py` | model (cache-aside) | store-then-invalidate | su propio `load()` + `model.py` métodos de escritura | exact |
| `encino_orm/model/model.py` | model (CRUD) | CRUD + transacción | su propio `insert_many` | exact |
| `encino_orm/model/cache_backend.py` | cache backend | key-value store (LRU) | su propio `MemoryCacheBackend` | exact |
| `encino_orm/__init__.py` | barrel | re-export | bloque `from .migration import (...)` + `__all__` | exact |
| `tests/test_migration_reconcile.py` | test (nuevo) | fake-Db / unit | `tests/test_d_recommendations.py::LockDb` + `test_dialect_builders.py::_ModelDbRegistrador` | role-match |
| `tests/test_cache_backend.py` | test (nuevo) | DB-free unit | `tests/test_cached_model.py` | role-match |
| `tests/test_dialect_ddl.py` | test (nuevo) | DB-free unit | `tests/test_dialect_builders.py` (asserts de map) | role-match |
| `tests/test_migrations.py` | test (extend) | integration SQLite | su propio `TestMigrationRunner` | exact |
| `tests/test_cached_model.py` | test (extend) | unit + SQLite | su propio `TestCachedModel` | exact |
| `tests/test_sqlite.py` | test (extend) | integration SQLite | su propio `test_migrate_is_idempotent` | exact |
| `tools/ci/check_coverage_floors.py` | CI gate (config) | batch/read | su propio `FLOORS` | exact |
| `docs/guide.md` | docs | prosa | §10 Caché (líneas 475-507) | exact |
| `docs/design/5-security.md` | docs | prosa | afirmación obsoleta del hook (línea ~203) | role-match |
| `CHANGELOG.md` | docs | prosa | entrada `[Unreleased]` | role-match |

---

## Pattern Assignments

### `encino_orm/migration.py` (service, state-machine + CRUD)

**Analog:** el propio módulo (`encino_orm/migration.py`, 56 líneas) + `encino_orm/base.py`.

**Imports pattern** (`migration.py:1-6`):
```python
from dataclasses import dataclass

from .exceptions import MigrationError
from .query import Query
```
Añadir `import logging` y `logger = logging.getLogger("encino_orm")` siguiendo la convención de `base.py:1-11`:
```python
import logging
...
logger = logging.getLogger("encino_orm")
```

**Objeto de valor + helper de coerción** (`migration.py:9-17`):
```python
@dataclass(frozen=True)
class Migration:
    name: str
    up: Query | str
    down: Query | str | None = None  # opcional (rollback)


def _to_query(sql: Query | str) -> Query:
    return sql if isinstance(sql, Query) else Query(sql, [])
```
Mantener `Migration` frozen y `_to_query`; el runner nuevo debe operar sobre `Query` normalizada.

**El bug exacto de DATA-01 a corregir** (`migration.py:25-29`):
```python
async def rollback_migration(db, m: Migration) -> None:
    """Revierte una migración aplicando su `down` (si existe)."""
    if m.down is None:
        raise MigrationError(f"{m.name} no tiene down")
    await db.migrate(f"{m.name}:down", _to_query(m.down))   # ← inserta `:down`, nunca borra `{name}`
```
Reemplazar por D-06/D-07: marcar `rolling_back` → ejecutar `down` → **borrar** la fila `{name}`. Usar `async with db.transaction()`, **nunca `db.commit()`** (`pool.py:245-248` lanza `ConnectionError`).

**Import diferido** (`migration.py:44-51`): `importlib`/`Path` se importan dentro de `migrations_from_dir`; conservar ese estilo para no cargar coste al importar el paquete.

**Patrón de transacción a copiar** (`base.py:40-47`):
```python
@asynccontextmanager
async def transaction(self):
    try:
        yield
        await self.commit()
    except Exception:
        await self.rollback()
        raise
```
El runner solo puede usar `async with db.transaction()`; en `PoolDb` esto fija la conexión por contextvar (`pool.py:178-187`) y es el único camino válido.

**Mensaje de error con SQL + instrucción** (D-02; sketch en `03-RESEARCH.md:374-393`): construir el detalle con `f"  - {r['name']} [{r['status']}] SQL: {r['sql_text']}"` y cerrar con la instrucción de `resolve_migration`. Mensajes en español, `MigrationError` de `.exceptions`.

**Firma sugerida del runner compartido** (RESEARCH `03-RESEARCH.md:196-216`): un helper `_apply(db, name, qry)` que haga `INSERT pending → execute(up) → UPDATE applied` dentro de **una** `async with db.transaction()`, compensando el `pending` solo si el DDL no corrió. Los seis adaptadores lo llaman. Ver "Shared Patterns → Runner compartido".

---

### `encino_orm/dialects/strategies.py` (config, lookup)

**Analog:** el propio fichero. `TRANSACTIONAL_DDL` es un dato de dialecto idéntico en forma a `UPSERT_KIND` y `LIMITS`.

**Mapa string→valor + literal de validación** (`strategies.py:56-66`):
```python
UPSERT_KIND: dict[str, str] = {
    "sqlite": "on_conflict",
    "mysql": "on_duplicate",
    "mariadb": "on_duplicate",
    "postgresql": "on_conflict",
    "mssql": "merge",
    "oracle": "merge",
}

UPSERT_KINDS = ("on_conflict", "on_duplicate", "merge")
```
Copiar esta forma para:
```python
# DDL transaccional (ROLLBACK posible) vs commit implícito del DDL.
# OJO: MySQL 8.0/MariaDB ≥10.6 son "atomic" a nivel de SENTENCIA (crash-safe)
# pero NO rollbackables: el commit implícito ocurre ANTES del DDL (Pitfall 2).
TRANSACTIONAL_DDL: dict[str, bool] = {
    "sqlite": True,
    "mysql": False,
    "mariadb": False,
    "postgresql": True,
    "mssql": True,
    "oracle": False,
}
```

**Registro del mapa + `__all__`** (`strategies.py:139-171`): añadir `TRANSACTIONAL_DDL` al final del fichero y a `__all__` (lista ordenada alfabéticamente). Si se prefiere un helper en vez de leer el dict desde los adaptadores, copiar `strategy_for` (`:149-155`):
```python
def strategy_for(dialect: Engine | str) -> InsertStrategy:
    key = dialect.value if isinstance(dialect, Engine) else dialect
    try:
        return _STRATEGIES[key]
    except KeyError:
        raise ValueError(f"dialecto desconocido: {dialect!r}") from None
```

---

### `encino_orm/dialects/__init__.py` (barrel)

**Analog:** su propio bloque (`dialects/__init__.py:5-39`). Añadir `TRANSACTIONAL_DDL` al import de `.strategies` y a `__all__` (orden alfabético; el proyecto exige barrel + `__all__` sincronizados, ver `AGENTS.md` §Module Design).

---

### `encino_orm/base.py` (abstract base, config attr)

**Analog:** atributos de clase existentes.
```python
class Db(ABC):
    MAX_TRIES = 9
    WAITERS: ClassVar[list[float]] = [x * 0.02 for x in range(1, 11)]
    MAX_WAIT = len(WAITERS) - 1

    dialect: str = ""
```
(`base.py:14-19`). Añadir el class attr con default seguro:
```python
transactional_ddl: bool = True  # default conservador; cada adaptador lo fija desde TRANSACTIONAL_DDL
```
No hace falta tocar `migrate`/`migrate_status` abstractos (`base.py:127-131`); su firma no cambia.

---

### `encino_orm/pool.py` (wrapper, delegation)

**Analog:** propiedades de delegación al template (`pool.py:77-89`):
```python
@property
def dialect(self) -> str:
    return self._engine

@property
def MAX_PARAMS(self) -> int:
    """Techo de parámetros por sentencia del motor subyacente (no del pool)."""
    return self._template.MAX_PARAMS
```
Añadir una property análoga `transactional_ddl` que devuelva `self._template.transactional_ddl` (RESEARCH lo pide en `03-RESEARCH.md:189`).

**Restricción crítica** (`pool.py:245-248`):
```python
async def commit(self):
    raise ConnectionError(
        "commit() se gestiona con pool.transaction(); no lo llames directamente"
    )
```
Es la prueba de que `migration.py` no puede llamar `db.commit()` (Pitfall 3). `PoolDb.migrate` delega con `_run` (`pool.py:293-294`), que hace commit best-effort al devolver la conexión (`pool.py:218-231`); el runner debe apoyarse en `async with db.transaction()`.

---

### `encino_orm/{sqlite,mysql,mariadb,postgresql,mssql,oracle}.py` (adapters, DDL + ledger)

**Analog por adaptador:** su propio `migrate()`/`_ensure_migrations_table()`. Además, la receta idempotente debe copiar `Model.sync_schema` (`model/model.py:905-922`), que ya implementa catálogo + `ALTER ... ADD` + `check_identifier`.

**Patrón de idempotencia por nombre a preservar** (`sqlite.py:222-234`; idéntico en `mysql.py:248-260`, `mssql.py:317-329`, `oracle.py:317-329`):
```python
async def migrate(self, name: str, qry: Query):
    self._ensure_connected()
    await self._ensure_migrations_table()

    existing = await self.fetch_one(
        Query(f"SELECT id FROM {_MIGRATIONS_TABLE} WHERE name = {{0}}", [name])
    )
    if existing is not None:
        return

    await self.execute(qry)
    await self.execute(self.insert(_MIGRATIONS_TABLE, {"name": name, "sql_text": qry.sql}))
    await self.commit()
```
Notas de migración al nuevo flujo:
- La comprobación de idempotencia se mantiene, pero la reconciliación (D-03) corre **antes** de aplicar: `await reconcile_migrations(self)` tras `_ensure_migrations_table()`.
- `self.commit()` directo se sustituye por el helper compartido con `async with db.transaction()` (excepto PostgreSQL, que ya usa `async with self.transaction()` en `postgresql.py:244-246`).
- La fila se inserta con `status='pending'` y se promueve a `'applied'`.

**DDL transaccional (PostgreSQL) — patrón de referencia** (`postgresql.py:234-246`):
```python
async with self.transaction():
    await self.execute(qry)
    await self.execute(self.insert(_MIGRATIONS_TABLE, {"name": name, "sql_text": qry.sql}))
```

**`_MIGRATIONS_TABLE` (constante duplicada en los 6)** — `sqlite.py:16`, `mysql.py:18`, `mariadb` (hereda), `postgresql.py:16`, `mssql.py:14`, `oracle.py:20`:
```python
_MIGRATIONS_TABLE = "_encino_orm_migrations"
```
El runner compartido necesita **una sola fuente de verdad**; RESEARCH pone `MIGRATIONS_TABLE` en `migration.py` (`03-RESEARCH.md:180`). Decisión de diseño para el planner (ver "No Analog Found").

**`_ensure_migrations_table` actual (sin `status`)** (`sqlite.py:241-250`):
```python
async def _ensure_migrations_table(self):
    self._ensure_connected()
    await self._connection.execute(
        f"CREATE TABLE IF NOT EXISTS {_MIGRATIONS_TABLE} ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "name TEXT NOT NULL UNIQUE, "
        "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
        "sql_text TEXT NOT NULL)"
    )
    await self._connection.commit()
```
Añadir `status VARCHAR(20) NOT NULL DEFAULT 'applied'` al `CREATE` y, para instalaciones existentes, el `ALTER` idempotente.

**Receta del `ALTER` idempotente — analog directo `sync_schema`** (`model/model.py:905-922`):
```python
check_identifier(self._table, "tabla")
existing = await self._existing_columns_info()          # -> {col: raw_type} vía columns_of()
...
check_identifier(col, "columna")
# `ADD COLUMN` no es sintaxis válida en SQL Server ni en Oracle;
# `ADD <col> <tipo>` lo es en los seis motores.
await self._get_db().execute(Query(f"ALTER TABLE {self._table} ADD {col} {ddl}", []))
```
Adaptar a:
```python
cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
if "status" not in cols:
    try:
        await self._execute_raw(
            f"ALTER TABLE {MIGRATIONS_TABLE} ADD status VARCHAR(20) NOT NULL DEFAULT 'applied'"
        )
        await self._connection.commit()
    except Exception:
        await self.rollback()          # best-effort (no hay `_safe_rollback` en el repo)
        if "status" not in {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}:
            raise                      # verify-then-swallow (Pitfall 6)
```
El guard re-lee el catálogo en vez de matchear códigos de error del driver (RESEARCH `:64-65`, `:336-340`).

**Query de catálogo por motor** (`columns_of`):
- SQLite `sqlite.py:118-132` → `PRAGMA table_info(...)`, `r["name"]`.
- MySQL/MariaDB `mysql.py:125-139` → `SHOW COLUMNS FROM ...`, `r["Field"]`.
- PostgreSQL `postgresql.py:133-154` → `information_schema.columns`, `r["column_name"]`.
- MSSQL `mssql.py:163-193` → `INFORMATION_SCHEMA.COLUMNS`, `r["name"]` (ya lowercase).
- Oracle `oracle.py:160-198` → `USER_TAB_COLUMNS`, `r["name"]` (lowercase).

**`_execute_raw` + commit por motor**:
- MySQL `mysql.py:141-148`; MSSQL `mssql.py:145-151`; Oracle `oracle.py:145-151` (Oracle no tiene cursor.close asíncrono). SQLite ejecuta directo sobre `self._connection` (`sqlite.py:243`).
- Tras el `ALTER`, MSSQL/Oracle deben resetear `self._in_tx = False` como ya hacen sus `_ensure_migrations_table` (`mssql.py:347-348`, `oracle.py:353-354`).

**Asignación del class attr** — copiar el patrón `MAX_PARAMS = LIMITS["mssql"].max_params` (`mssql.py:40-41`):
```python
transactional_ddl = TRANSACTIONAL_DDL["sqlite"]   # etc.
```
En `mariadb.py` (hereda de `MysqlDb`) fijar `transactional_ddl = TRANSACTIONAL_DDL["mariadb"]` junto a `MAX_PARAMS`/`MAX_ROWS` (`mariadb.py:14-18`).

---

### `encino_orm/model/cached.py` (model, store-then-invalidate)

**Analog:** su propio `load()` (rehidratación) + los métodos de escritura de `model.py`.

**Estado privado y constructor** (`cached.py:13-15`):
```python
def __init__(self, db: Db = None, cache: CacheBackend = None, **kwargs):
    super().__init__(db=db, **kwargs)
    _set_private(self, "_cache", cache)
```

**`_cache_key` (única clave cacheada, D-11)** (`cached.py:17-20`):
```python
def _cache_key(self, keys) -> str:
    parts = [f"{k}={getattr(self, k)}" for k in keys]
    raw = f"{self._table}:[{'&'.join(parts)}]"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
```

**`load()` — único punto que escribe caché hoy** (`cached.py:22-47`): en miss llama `await cache.set(key, payload, duration)`; en hit rehidrata con `_set_private(...)` y `_set_private(obj, "_cache", cache)`. La invalidación nueva debe usar la MISMA clave `_cache_key(keys)`; no hay entradas por filtro que barrer.

**Firmas de escritura a overridear** (en `model/model.py`):
```python
async def update(self, keys=None, data=None) -> int:          # :688
async def delete(self, keys=None, physical: bool = False) -> bool:  # :726
async def upsert(self, conflict: list[str] | None = None, values: dict | None = None) -> int:  # :595
async def save(self, keys=None) -> int:                        # :535  (delega en update/insert)
```
`save` (`model.py:535-541`) llama `self.load(...)` y luego `self.update(keys=keys)` o `self.insert()`; al overridear `update` queda cubierto (D-15).

**Patrón store-then-invalidate (override)** — RESEARCH `03-RESEARCH.md:250-253`:
```python
async def update(self, keys=None, data=None) -> int:
    count = await super().update(keys=keys, data=data)   # super() ya retorna post-commit
    await self._invalidate(keys)
    return count
```
`super().update` usa `_transactional` (`model.py:419-434`), que retorna tras el commit. `upsert` (`model.py:648-652`) e `insert_many` (`model.py:572`) **no** pasan por `_transactional` (por eso D-15 descarta el hook `after_commit`).

**Helpers de normalización de claves** (`model.py:257-260`, `:314-320`):
```python
@classmethod
def _pk_fields(cls) -> tuple[str, ...]:
    return tuple(getattr(cls, "_primary_key", ("id",)))

@staticmethod
def _normalize_keys(keys, default=("id",)):
    if keys is None:
        keys = default
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.split(",") if k.strip()]
    return list(keys)
```

**Invalidación fail-open (D-12)** — RESEARCH `03-RESEARCH.md:395-409`; usar `logger.warning` con formato `%` perezoso (convención `AGENTS.md` §Logging):
```python
async def _invalidate(self, keys=None) -> None:
    cache = self._cache
    if cache is None:
        return
    keys = self._normalize_keys(keys, type(self)._pk_fields())
    try:
        await cache.delete(self._cache_key(keys))
    except Exception as exc:
        logger.warning("no se pudo invalidar la caché de %s: %r", self._table, exc)
```

**`insert_many` y caché (D-16 / Open Q1):** `Model.insert_many` es `classmethod` (`model.py:543-546`) y no tiene `self._cache`. La recomendación de RESEARCH (`03-RESEARCH.md:436-439`) es `CachedModel.insert_many(cls, db=None, rows=None, *, chunk=None, cache=None)`; si se pasa `cache`, invalidar las PK presentes en `rows`. Requiere construir la clave sin instancia; `_cache_key` es de instancia (`cached.py:17`). Punto de diseño explícito para el planner.

---

### `encino_orm/model/model.py` (model, CRUD)

**Analog:** su propio `insert_many` (`model.py:543-593`).

**Firma actual** (`model.py:543-546`):
```python
@classmethod
async def insert_many(
    cls, db=None, rows: list[dict] | None = None, *, chunk: int | None = None
) -> int:
```
Añadir el kwarg opcional `cache=None` (D-16). El cuerpo usa `async with db.transaction():` (`model.py:572`) — es el motivo por el que el hook `after_commit` no dispara. La invalidación (si se implementa aquí) debe ocurrir **después** de salir de esa transacción.

`_transactional` (`model.py:419-434`) queda como referencia read-only de dónde se dispara `after_commit`; no es el punto de enganche elegido (D-15).

---

### `encino_orm/model/cache_backend.py` (cache backend, LRU)

**Analog:** el propio `MemoryCacheBackend` (`cache_backend.py:11-32`).

**Estado actual sin cota** (`cache_backend.py:11-32`):
```python
class MemoryCacheBackend:
    """Backend en memoria para desarrollo y pruebas."""

    def __init__(self):
        self._store = {}

    async def get(self, key: str) -> bytes | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        expires_at = time.monotonic() + ttl if ttl else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
```

**Protocol ya listo** (`cache_backend.py:5-8`): `delete` existe; no hay que ampliarlo.

**Patrón LRU (D-13)** — RESEARCH `03-RESEARCH.md:260-268`:
```python
async def set(self, key, value, ttl):
    expires_at = time.monotonic() + ttl if ttl else None
    self._store[key] = (value, expires_at)
    self._store.move_to_end(key)
    while len(self._store) > self._max_size:
        self._store.popitem(last=False)
```
`get` también debe hacer `move_to_end`. Mantener `len(cache._store)` (lo usa `tests/test_cached_model.py:36`) y conservar `dict`→`OrderedDict` (`.pop(key, None)`, `.get`, `in` siguen igual). `max_size=1024` por defecto. Contrato dev/test en el docstring (D-14). No tocar `RedisCacheBackend` (`cache_backend.py:35-59`).

---

### `encino_orm/__init__.py` (barrel)

**Analog:** bloque de migraciones (`__init__.py:22-28`) y `__all__` (`:39-80`).
```python
from .migration import (
    Migration,
    apply_migration,
    apply_migrations,
    migrations_from_dir,
    rollback_migration,
)
```
Añadir `reconcile_migrations`/`resolve_migration` al import y a `__all__` (orden alfabético). El proyecto exige barrel + `__all__` sincronizados.

---

### `tests/test_migration_reconcile.py` (test nuevo, fake-Db)

**Analog principal:** `tests/test_d_recommendations.py::TestD4AutoRetry.LockDb` (`test_d_recommendations.py:153-212`). Es el fake `Db` aceptado por el repo, pero **carece de `_ensure_migrations_table`** — RESEARCH lo advierte (`03-RESEARCH.md:513`): el helper `_ensure_ledger` debe tolerar su ausencia o el fake debe añadirlo.

**Fake `Db` (contrato mínimo)** (`test_d_recommendations.py:153-212`):
```python
class LockDb(Db):
    dialect = "fake"
    def __init__(self):
        self.executes = 0
        self.last = 0
    def is_lock_error(self, exc): return "locked" in str(exc)
    async def wait(self, waiter=-1): return 0
    async def connect(self, **kw): ...
    async def close(self): ...
    async def is_alive(self): return True
    async def in_transaction(self): return False
    async def commit(self): ...
    async def rollback(self, save_point=None): ...
    async def save_point(self, name): ...
    def insert(self, tabla, data, ignore_duplicated=False, replace=False, conflict=None):
        return Query("INSERT INTO p VALUES ({0})", [1])   # Query real, no tupla
    def delete(self, tabla, keys): return ("DELETE", tabla)
    def update(self, tabla, keys, values): return ("UPDATE", tabla)
    async def execute(self, qry): ...
    async def fetch_all(self, qry): return []
    async def fetch_one(self, qry): return None
    async def fetch_many(self, qry, limit, page): return []
    async def exists(self, qry): return False
    async def last_id(self): return self.last
    async def migrate(self, name, qry): ...
    async def migrate_status(self): return []
```

**Fake con `transaction()`/`retry()`** (para ejercitar el runner) — `tests/test_dialect_builders.py:598-628`:
```python
class _ModelDbRegistrador:
    def __init__(self, dialect):
        self.dialect = dialect
        self.insert_calls = []
        self._last = 1
    @asynccontextmanager
    async def transaction(self):
        yield self
    async def retry(self, fn):
        return await fn()
    ...
```
Para el test de inyección de fallo con `transactional_ddl=False` (Pitfall 8): el fake debe simular commit implícito del DDL publicando el `pending` aunque el promote falle; la aserción es que `reconcile_migrations` **detecta** el `pending` (no que sea imposible).

**Fake `Db` determinista con transacción que registra begin/commit/rollback** — `tests/test_pool_characterization.py:29-65`:
```python
@asynccontextmanager
async def transaction(self):
    self.calls.append(("begin",))
    try:
        yield self
        self.calls.append(("commit",))
        self._in_tx = False
    except Exception:
        self.calls.append(("rollback",))
        self._in_tx = False
        raise
```
Patrón aceptado: **fakes a mano + `monkeypatch`**, preferidos a `unittest.mock` (CONTEXT §Reusable Assets).

**Fixtures con `yield` y `@pytest.mark.asyncio`** (aunque `asyncio_mode="auto"`), como `tests/test_migrations.py:15-20`.

**Assertions D-08:** cubrir las 4 filas de la tabla (`pending`+True, `pending`+False, `rolling_back`+False, `rolling_back`+True) y que el parámetro `applied` significa "¿debe quedar aplicada?" (D-17).

---

### `tests/test_cache_backend.py` (test nuevo, DB-free)

**Analog:** `tests/test_cached_model.py` (estructura de clases y asserts sobre `cache._store`).

**Patrón de aserción existente** (`tests/test_cached_model.py:28-36`):
```python
cache = MemoryCacheBackend()
...
assert len(cache._store) == 1
```
Tests DB-free: LRU desaloja la menos usada, `max_size` respetado, `len()` conservado, `delete`. Sin fixture de BD. `@pytest.mark.asyncio` explícito.

---

### `tests/test_dialect_ddl.py` (test nuevo, DB-free)

**Analog:** `tests/test_dialect_builders.py` (asserts directos sobre mapas/estrategias, sin BD). Patrón de import y `pytest.raises(ValueError)`:
```python
with pytest.raises(ValueError):
    strategy_for("mongodb")
```
(`test_dialect_builders.py:594-595`). Asertar el mapa `TRANSACTIONAL_DDL` completo (6 claves) y que MySQL/MariaDB/Oracle son `False`.

---

### `tests/test_migrations.py` (extend)

**Analog:** su propio `TestMigrationRunner` (`test_migrations.py:23-68`) y la fixture `db` (`:15-20`).

**Fixture a reutilizar** (`test_migrations.py:15-20`):
```python
@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()
```
**Regresión DATA-01 `apply → rollback → apply`** — basarse en `test_rollback_migration` (`:49-61`): tras `rollback_migration`, `{name}` ya no existe y re-aplicar debe ejecutar el DDL de nuevo. Añadir aserción de que el ledger tiene una sola fila `{name}` y **ninguna** `{name}:down`.

**`ensure_status` idempotente:** crear tabla legacy sin `status` (SQL crudo) y comprobar que `migrate_status()` la añade y una segunda llamada no falla.

---

### `tests/test_cached_model.py` (extend)

**Analog:** su propio `TestCachedModel` (`test_cached_model.py:26-59`). Reutilizar `Cliente` (`:8-11`), `DDL` (`:14-17`) y la fixture `db` (`:20-23`).

**Patrón "borrar de la BD para demostrar que se sirve desde caché"** (`test_cached_model.py:39-52`) — invertirlo para los tests de invalidación: cachear, escribir, y comprobar que la lectura posterior va a BD (o que `cache.get(key)` es `None`).

**Fail-open:** cache fake que lanza en `delete`; asertar que `update`/`delete` no propagan y que se emite un warning (cuidado con `filterwarnings=["error"]`: el warning de `logging` no es de `warnings`, así que no rompe la suite).

---

### `tests/test_sqlite.py` (extend)

**Analog:** `test_migrate_applies_and_records` (`test_sqlite.py:142-148`), `test_migrate_is_idempotent` (`:163-168`), `test_migrate_status_returns_history_in_order` (`:171-175`). Mantener la regresión de idempotencia (DATA-02).

---

### `tools/ci/check_coverage_floors.py` (CI gate, opcional)

**Analog:** su propio `FLOORS` (`check_coverage_floors.py:23-31`):
```python
FLOORS: dict[str, float] = {
    "encino_orm/dialects/identifiers.py": 100.0,
    "encino_orm/dialects/builders.py": 95.0,
    "encino_orm/query.py": 95.0,
}
```
Si se añaden pisos (discreción, Open Q5), usar claves con separador `/` (el script normaliza con `_norm`, `:34-36`) y **falla cerrado** si el módulo no aparece (`:56-58`). Recomendación de RESEARCH: solo tras el primer run verde con margen; un piso mal calibrado bloquea CI.

---

### `docs/guide.md` (docs)

**Analog:** §10 Caché (`guide.md:475-507`). La línea 486 ya afirma "invalida al actualizar/borrar" — hoy es **falsa** (Pitfall 7); el fix de DATA-03 la hace verdadera. Añadir el contrato dev/test de `MemoryCacheBackend` (D-14) y la limitación multi-proceso (invalidación local, no distribuida; AF-9).

### `docs/design/5-security.md` (docs)

**Analog:** línea ~203, que describe la invalidación mediante un hook `after_commit`. D-15 corrige el mecanismo (overrides en `CachedModel`); actualizar para no perpetuar la descripción obsoleta.

### `CHANGELOG.md` (docs)

Cambios de comportamiento incompatibles (se elimina la fila `{name}:down`; `migrate()` inserta `pending`; `MemoryCacheBackend` acotado). El constraint de `PROJECT.md` exige documentarlos.

---

## Shared Patterns

### Runner compartido y uso de transacción
**Fuente:** `base.py:40-47` + `pool.py:245-248` + RESEARCH `03-RESEARCH.md:196-216`.
**Aplicar a:** `migration.py` y los seis `migrate()`.
```python
# El runner NUNCA llama db.commit(): usa db.transaction() (obligatorio para PoolDb).
async with db.transaction():
    await db.execute(db.insert(MIGRATIONS_TABLE, {
        "name": name, "status": "pending", "sql_text": qry.sql,
    }))
    await db.execute(qry)
    await db.execute(db.update(MIGRATIONS_TABLE, {"name": name}, {"status": "applied"}))
```
En `transactional_ddl=False`, el commit implícito del DDL publica el `pending`; en `transactional_ddl=True`, el rollback lo elimina (D-01). Ramificar por el dato leído en runtime, no envolver uniformemente (Pitfall 1).

### Logging
**Fuente:** `base.py:10-11` (`logger = logging.getLogger("encino_orm")`), `sqlite.py:19-27`.
**Aplicar a:** `migration.py` (warning de compensación fallida), `cached.py` (warning fail-open).
- Formato `%` perezoso, nunca f-strings: `logger.warning("no se pudo invalidar la caché de %s: %r", self._table, exc)`.

### Excepciones
**Fuente:** `exceptions.py:17-18` (`MigrationError(EncinoOrmError)`).
**Aplicar a:** `migration.py`. Mensajes en español con f-strings; `down is None` sigue lanzando `MigrationError` (D-06). No usar `raise ... from`.

### Validación de identificadores
**Fuente:** `dialects/identifiers.py::check_identifier` (usado en `base.py:58-61`, `model/model.py:908`).
**Aplicar a:** el `ALTER TABLE` del ledger y todo identificador interpolado. Valores (`name`, `status`, `sql_text`) siempre ligados vía `Query`/builders, nunca interpolados.

### Binding de parámetros
**Fuente:** `Query` con placeholders `{n}` (patrón en `migration.py:17`, `sqlite.py:226-227`).
**Aplicar a:** consultas de reconciliación y de `resolve_migration`.
```python
Query(
    f"SELECT name, status, sql_text FROM {MIGRATIONS_TABLE} "
    "WHERE status IN ({0}, {1}) ORDER BY id", ["pending", "rolling_back"],
)
```

### Fakes deterministas en tests
**Fuente:** `tests/test_d_recommendations.py::LockDb`, `tests/test_dialect_builders.py::_ModelDbRegistrador`, `tests/test_pool_characterization.py::FakeDb`.
**Aplicar a:** `tests/test_migration_reconcile.py`, `tests/test_cache_backend.py`, `tests/test_cached_model.py`.
- Fakes a mano + `monkeypatch`; evitar `unittest.mock`.
- `transaction()` como `@asynccontextmanager` que registra `begin`/`commit`/`rollback`.
- Python ≥3.10: no usar `Barrier`/`TaskGroup` (3.11+); si hace falta carrera, `asyncio.Event`.

### Compatibilidad de barrel
**Fuente:** `encino_orm/__init__.py:39-80`, `dialects/__init__.py:20-39`.
**Aplicar a:** `reconcile_migrations`/`resolve_migration`/`TRANSACTIONAL_DDL`: añadir al import **y** a `__all__` (orden alfabético).

---

## No Analog Found

Ningún fichero carece de analog de rol. Dos **comportamientos** son nuevos y quedan gobernados por `03-RESEARCH.md` (no por código existente):

| Behavior | Role | Data Flow | Reason |
|----------|------|-----------|--------|
| Máquina de estados `pending`/`applied`/`rolling_back` + `reconcile_migrations`/`resolve_migration` | service | state-machine | No existe estado de migración más allá de "fila presente = aplicada". El sketch autoritativo está en `03-RESEARCH.md:196-242, 374-409`. |
| Fuente única de `MIGRATIONS_TABLE` + helper `_apply` compartido entre 6 adaptadores | config/service | DDL + ledger | Hoy la constante y la lógica están duplicadas en los seis adaptadores; centralizarlas es una decisión de diseño del planner (RESEARCH `:180`). El analog de "seam centralizado" es `dialects/` de Fase 2. |

**Restricciones de la investigación que el planner DEBE respetar** (de `03-CONTEXT.md:63-66` y `03-RESEARCH.md`):
1. El runner **no** puede llamar `db.commit()`; solo `async with db.transaction()`.
2. `ALTER TABLE ADD COLUMN IF NOT EXISTS` no es portable → catálogo (`columns_of`) + `ADD ... NOT NULL DEFAULT 'applied'` + verify-then-swallow.
3. Pitfall 8: el test de inyección de fallo aserta que `reconcile_migrations` **detecta** el `pending`.
4. No enganchar la invalidación solo a `after_commit` (no dispara en `upsert`/`insert_many`; no recibe clave/acción) — D-15.

## Metadata

**Analog search scope:** `encino_orm/` (raíz, `model/`, `dialects/`), `tests/`, `tools/ci/`, `docs/`.
**Files scanned:** ~35 (leídos en profundidad: `migration.py`, `cached.py`, `cache_backend.py`, `strategies.py`, `base.py`, `pool.py`, `model.py`, `sqlite.py`, `mysql.py`, `postgresql.py`, `mssql.py`, `oracle.py`, `mariadb.py`, `engine.py`, `exceptions.py`, barrels, `test_migrations.py`, `test_cached_model.py`, `test_d_recommendations.py`, `test_dialect_builders.py`, `test_pool_characterization.py`, `check_coverage_floors.py`, `guide.md`).
**Pattern extraction date:** 2026-09-18
