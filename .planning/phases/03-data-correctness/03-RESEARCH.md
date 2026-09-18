# Phase 3: Data Correctness - Research

**Researched:** 2026-09-18
**Domain:** Migraciones versionadas (ledger + reconciliación) y cache-aside con invalidación por escritura, sobre seis motores con DDL transaccional/no transaccional.
**Confidence:** HIGH (stack sin dependencias nuevas; arquitectura verificada leyendo el código vivo y docs oficiales; dos incógnitas quedan como decisiones abiertas, no como incertidumbre técnica).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Reconciliación de migraciones (DATA-02)
- **D-01:** **Máquina de estados de 2 fases.** La tabla de migraciones gana una columna `status` con valores `pending` / `applied` / `rolling_back`. `migrate()` inserta la fila como **`pending` ANTES** de ejecutar el DDL y la promueve a `applied` **después**. En motores con DDL transaccional (PostgreSQL/SQLite/SQL Server) la fila y el DDL van en la misma transacción, así que un `pending` nunca sobrevive; la maquinaria es inerte allí.
- **D-02:** **Un `pending` es ambiguo → fallo ruidoso.** Al reconciliar, un `pending` significa "no sabemos si el DDL corrió". Se lanza **`MigrationError` incluyendo el SQL de la migración y la instrucción de resolución**. **NUNCA** se re-ejecuta el DDL automáticamente (peligroso con DDL no idempotente) ni se asume `applied` (eso sería el registro mintiendo, justo lo que la fase elimina).
- **D-03:** **Dónde corre la reconciliación:** una comprobación dentro de `migrate()` (antes de aplicar cualquier migración) **y** una API pública `reconcile_migrations(db)` para el arranque de la aplicación. Cubre al que migra y al que solo arranca.
- **D-04:** **La columna `status` existe en los 6 motores, uniforme.** Sin ramas de dialecto en el runner. OJO: `_ensure_migrations_table` usa `CREATE TABLE IF NOT EXISTS`, que **no** añade columnas a una tabla ya existente → hace falta un **`ALTER TABLE` idempotente** (detectar la columna en el catálogo y añadirla solo si falta) para instalaciones existentes.
- **D-05:** **Resolución humana con un helper:** `resolve_migration(db, name, *, applied: bool)`. El humano responde una sola pregunta —"¿corrió el SQL?"— y el helper **infiere la acción** del estado actual de la fila (ver D-08). No se le pide escribir SQL a mano.

#### Ledger de rollback (DATA-01)
- **D-06:** **`rollback_migration` ejecuta el `down` y BORRA la fila `{name}`; NO registra `{name}:down`.** El `down` no es una migración aplicada del usuario, así que `migrate_status()` sigue mostrando solo migraciones realmente aplicadas. Re-aplicar funciona porque `{name}` ya no existe. (`down is None` sigue siendo `MigrationError`, como hoy.)
- **D-07:** **Estado `rolling_back` propio durante el `down`.** La fila `{name}` pasa a `rolling_back` antes de ejecutar el `down` y se borra después. Un estado propio (en vez de reutilizar `pending`) es lo que permite que la reconciliación **sepa la dirección** y dé instrucciones específicas.
- **D-08:** **Tabla de resolución de `resolve_migration`** (acción inferida del estado + la respuesta del humano):

  | Estado de la fila | `applied` (¿corrió el SQL?) | Acción |
  |---|---|---|
  | `pending` | `True` | Marcar `applied` (el DDL sí corrió) |
  | `pending` | `False` | Borrar la fila (re-migrar) |
  | `rolling_back` | `False` | Borrar la fila (el `down` sí corrió) |
  | `rolling_back` | `True` | Restaurar `applied` (el `down` no corrió) y reintentar el rollback |

#### Invalidación de caché (DATA-03)
- **D-09:** **Invalidar en TODAS las rutas de escritura:** `update`, `delete`, `save`, `upsert` e `insert_many`. `insert` puro **no** invalida (no había fila cacheada para esa clave). Se aplica aquí la **lección de Fase 2**: un "choke point" declarado no lo es hasta barrer todas las posiciones de escritura.
- **D-10:** **Store-then-invalidate.** Se escribe en la BD y **solo tras el commit** se invalida la caché, enganchado al hook `after_commit` que `_transactional` ya dispara. Si la invalidación falla, el peor caso es una lectura obsoleta acotada por el TTL — nunca se pierde el dato. Es el patrón cache-aside documentado.
- **D-11:** **Solo la clave afectada**, sin invalidación de namespace. `CachedModel.load()` solo cachea por clave de PK (`_cache_key(keys)`), así que no existen entradas por filtro que haya que barrer.
- **D-12:** **Fallo de invalidación = log warning y continuar (fail-open).** La escritura ya se commiteó; propagar el error daría al llamador un fallo sobre una escritura exitosa, y el dato quedaría inconsistente igualmente hasta el TTL.

#### Cota de `MemoryCacheBackend` (DATA-04)
- **D-13:** **LRU con `max_size=1024` por defecto.** `get` y `set` mueven la clave al final (`OrderedDict.move_to_end`); al insertar con el store lleno se desaloja la entrada menos recientemente usada. 1024 no rompe los tests existentes.
- **D-14:** **Contrato dev/test documentado** en el docstring y en los docs: el backend en memoria es para desarrollo y pruebas, no para producción. `RedisCacheBackend` no cambia (Redis ya acota y expira).

### the agent's Discretion
- Si añadir pisos de cobertura para `migration.py`/`cached.py`/`cache_backend.py` en `tools/ci/check_coverage_floors.py` (el mecanismo ya existe desde Fase 2).
- La forma exacta del `ALTER TABLE` idempotente por dialecto (consulta al catálogo + `ADD COLUMN`).
- Nombres exactos y firma de los métodos nuevos (`reconcile_migrations`, `resolve_migration`, la columna `status`).
- Si `insert_many` invalida por lote o clave a clave.
- Si `migrate_status()` cambia de forma al exponer `status`.

### Deferred Ideas (OUT OF SCOPE)
- **Centralizar la lógica de `migrate()` en un solo módulo** (como se hizo con los builders en Fase 2): la duplicación en 6 adaptadores sigue ahí, pero centralizarla es un refactor mayor que no exige DATA-02. Candidato para una fase posterior.
- **Ledger de rollbacks histórico** (tabla separada con el detalle de cada reversión): descartado en D-06 por superficie extra; se reconsidera si alguien necesita auditoría de reversiones.
- **Write-through / caché por consulta**: descartado en D-11; hoy `CachedModel` solo cachea por PK.
- **Reintento automático de DDL asumiendo idempotencia**: descartado en D-02; peligroso con DDL no idempotente.
- **`MemoryCacheBackend` con purga de expirados antes de desalojar**: descartado en D-13 por simplicidad; se reconsidera si aparece presión de memoria en tests.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | El ledger de `rollback_migration` está corregido: re-aplicar una migración tras el rollback funciona | `rollback_migration` debe marcar `rolling_back`, ejecutar `down` y **borrar** la fila `{name}` (D-06/D-07). Test de regresión `apply → rollback → apply` en SQLite (siempre activo). Ver §Arquitectura patrón 2. |
| DATA-02 | `migrate()` es atómico o registra la intención primero y reconcilia al arrancar (`transactional_ddl` por dialecto) | `transactional_ddl` por dialecto + patrón "record-intent-first" con una **única** `async with db.transaction()` (el commit implícito del DDL en MySQL/MariaDB/Oracle publica el `pending`). `reconcile_migrations` + `resolve_migration`. Ver §Arquitectura patrón 1 y §Desconocido 1. |
| DATA-03 | `CachedModel` invalida la caché en `update` **y** `delete` (store-then-invalidate), sin lecturas obsoletas | Overrides de `update`/`delete`/`upsert` (+ `save` por delegación) que invalidan **después** de que `super()` retorna (post-commit). Fail-open (D-12). Ver §Desconocido 3. |
| DATA-04 | `MemoryCacheBackend` está acotado o documentado explícitamente como solo dev/test | `OrderedDict` + `move_to_end` + `popitem(last=False)` con `max_size=1024`; contrato dev/test en docstring y `docs/guide.md` §10. Ver §Arquitectura patrón 4. |
</phase_requirements>

## Summary

La fase se apoya en cuatro cambios quirúrgicos, todos verificables contra el código vivo:

1. **Ledger de rollback (DATA-01).** Hoy `rollback_migration` (`encino_orm/migration.py:25-29`) llama `db.migrate("{name}:down", ...)`: ejecuta el `down` **e inserta** la fila `:down`, pero nunca borra `{name}`. El fix es D-06/D-07: marcar `rolling_back`, ejecutar `down`, borrar `{name}`.
2. **Migración atómica o reconciliable (DATA-02).** Los seis `migrate()` ejecutan `DDL → insert(registro) → commit`. En PostgreSQL/SQLite/SQL Server el DDL es transaccional y se puede envolver en una transacción; en MySQL/MariaDB/Oracle **cada DDL hace un commit implícito ANTES de ejecutarse** (verificado en docs oficiales), así que la única forma honesta es registrar la intención primero y reconciliar. La buena noticia: **no hace falta `db.commit()` explícito en el runner** — el commit implícito del DDL en los motores no transaccionales publica el `pending`, y en los transaccionales la transacción se encarga. Esto además es obligatorio porque **`PoolDb.commit()` lanza `ConnectionError`** (`pool.py:245-248`): el runner debe usar `async with db.transaction()` y nunca `db.commit()` directo, o `rollback_migration(pool, m)` explota.
3. **Invalidación de caché (DATA-03).** `CachedModel` solo define `load`; `update`/`delete`/`upsert`/`save`/`insert_many` resuelven a `Model` y **nadie llama `cache.delete`** (grep = 0). El hook `after_commit` existe pero **no dispara para `upsert` ni `insert_many`** (bypassan `_transactional`) y **no recibe la acción ni la clave**. La forma correcta es overridear los métodos de escritura en `CachedModel` e invalidar tras `super()` (que ya retorna post-commit). `insert_many` es `classmethod` y **no tiene acceso a la caché de instancia**: es la única incógnita de diseño real (ver Open Questions).
4. **Cota de caché (DATA-04).** `MemoryCacheBackend._store` es un `dict` sin cota. LRU con `OrderedDict` mantiene `len(cache._store)` (usado por `tests/test_cached_model.py:36`) y `max_size=1024` no rompe nada.

**Primary recommendation:** implementar el runner con una sola `async with db.transaction()` por operación (sin `db.commit()` explícito), ramificando solo en `transactional_ddl` para decidir si el `pending` se compensa o se deja para reconciliación; y resolver la invalidación con overrides en `CachedModel`, no con el hook `after_commit`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Máquina de estados del ledger (`pending`/`applied`/`rolling_back`) | Core runner (`encino_orm/migration.py`) | — | El runner es el dueño del protocolo; los adaptadores solo ejecutan SQL. |
| `transactional_ddl` por dialecto | Seam de dialectos (`dialects/strategies.py`) | Adaptadores (class attr) | Dato de dialecto, igual que `UPSERT_KIND`/`LIMITS`; una sola fuente de verdad. |
| `ALTER TABLE ADD COLUMN` idempotente | Adaptador (`_ensure_migrations_table`) | Introspección (`columns_of`) | Solo el adaptador conoce su catálogo y su sintaxis de ALTER. |
| Reconciliación en `migrate()` | Core runner | Adaptador (llamada diferida) | Evita duplicar el texto de resolución en seis ficheros. |
| API pública `reconcile_migrations`/`resolve_migration` | Core runner (`migration.py`) | Barrel `encino_orm/__init__.py` + docs | Es contrato de producto (arranque de app). |
| Invalidación de caché por escritura | Capa modelo (`model/cached.py`) | Hook `after_commit` (modelo mental) | El método conoce `keys` y el momento post-commit; el hook no. |
| Cota LRU del backend en memoria | `model/cache_backend.py` | Docs (`guide.md` §10) | Responsabilidad del backend, no del modelo. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| stdlib `collections.OrderedDict` | Python ≥3.10 | LRU de `MemoryCacheBackend` | `move_to_end`/`popitem(last=False)` es la implementación canónica de LRU en stdlib; no añade dependencias. |
| stdlib `logging` | Python ≥3.10 | Warning fail-open de invalidación | Convención del repo: `logging.getLogger("encino_orm")`. |
| stdlib `hashlib`/`json` | Python ≥3.10 | Clave/valor de caché | Ya en uso (`model/cached.py`). |
| `pytest` + `pytest-asyncio` | 9.1.1 / 1.4.0 | Tests de regresión | Ya configurados (`asyncio_mode="auto"`). |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (ninguna nueva) | — | — | Esta fase **no instala dependencias externas**. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `OrderedDict` LRU a mano | `functools.lru_cache` / `cachetools` | `lru_cache` es sync y no soporta TTL; `cachetools` añade una dependencia por ~10 líneas de stdlib. Rechazado. |
| Chequeo de catálogo + `ADD COLUMN` | `ADD COLUMN IF NOT EXISTS` uniforme | Solo PostgreSQL y MariaDB lo soportan; SQLite/MySQL/SQL Server/Oracle no. Un guard de excepción por motor es frágil (ver §Desconocido 1). |
| Override de métodos en `CachedModel` | Hook `after_commit` | El hook no dispara en `upsert`/`insert_many` ni conoce la clave/acción. Ver §Desconocido 2. |

**Installation:**
```bash
# Sin instalación: la fase no añade paquetes.
```

**Version verification:** No se recomiendan paquetes nuevos; no aplica `npm view`/`pip index`. Las versiones existentes se confirmaron localmente: `pytest 9.1.1`, `pytest-asyncio 1.4.0`, `coverage 7.16.1`, `asyncpg 0.31.0`, `aiosqlite 0.22.1`, `aioodbc 0.5.0`, `oracledb 4.0.2` `[VERIFIED: .venv]`.

## Package Legitimacy Audit

**Esta fase no instala paquetes externos.** Todo el trabajo usa stdlib (`collections`, `logging`) y dependencias ya presentes. No se ejecutó slopcheck porque no hay instalaciones que auditar.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────────────────┐
   App startup ───► │ reconcile_migrations(db)  [público, migration.py]        │
                    │   SELECT name,status,sql_text WHERE status IN            │
                    │     ('pending','rolling_back')                           │
                    └───────────────┬─────────────────────────────────────────┘
                                    │ filas no-vacías
                                    ▼
                         ┌──────────────────────┐
                         │ MigrationError       │  ← incluye el SQL + instrucción
                         │ (D-02: NUNCA re-run) │     de resolve_migration()
                         └──────────────────────┘

   apply_migration(db,m) ─► db.migrate(name, up)
        │
        ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ _ensure_migrations_table()  (por adaptador)                          │
   │   CREATE TABLE IF NOT EXISTS ... (…, status VARCHAR(20) NOT NULL     │
   │        DEFAULT 'applied')                                            │
   │   si falta la columna (columns_of): ALTER TABLE … ADD status …       │
   └───────────────┬──────────────────────────────────────────────────────┘
                   ▼
   ┌───────────────────────────────┐   reconcile_migrations(self)  (D-03)
   │ SELECT 1 WHERE name={0}       │──► si existe → return (idempotente)
   └───────────────┬───────────────┘
                   ▼ (no existe)
   ┌──────────────────────────────────────────────────────────────────────┐
   │ async with db.transaction():                                         │
   │     INSERT (name, status='pending', sql_text)                        │
   │     execute(up)              ← commit implícito del DDL en MySQL/    │
   │                                 MariaDB/Oracle publica el pending    │
   │     UPDATE status='applied'                                          │
   │ except: si el DDL no corrió → compensar borrando el pending          │
   │         (si el DDL sí corrió y falló el promote → dejar pending)     │
   └──────────────────────────────────────────────────────────────────────┘

   rollback_migration(db,m) ─► db.transaction():
        UPDATE status='rolling_back'
        execute(down)
        DELETE row
      except: compensar UPDATE status='applied' (el down no corrió)
              si la compensación falla → queda 'rolling_back' para reconciliar

   CachedModel.update/delete/upsert ─► super() (commit) ─► cache.delete(_cache_key(keys))
```

### Recommended Project Structure
```text
encino_orm/
├── migration.py            # MIGRATIONS_TABLE + apply/rollback/reconcile/resolve
├── dialects/
│   └── strategies.py       # + TRANSACTIONAL_DDL (nuevo dato de dialecto)
├── model/
│   ├── cached.py           # + overrides de escritura + _invalidate fail-open
│   └── cache_backend.py    # MemoryCacheBackend LRU acotado
├── base.py                 # + transactional_ddl (class attr, default True)
├── sqlite.py / mysql.py / mariadb.py / postgresql.py / mssql.py / oracle.py
│                           # _ensure_migrations_table + migrate (6 sitios)
└── pool.py                 # transactional_ddl delegado al template
```

### Pattern 1: Máquina de estados de 2 fases con record-intent-first
**What:** `migrate()` inserta `pending` antes del DDL y lo promueve a `applied` después; `reconcile_migrations` falla ruidosamente ante un `pending`/`rolling_back`.
**When to use:** Siempre (uniforme en los seis motores). La rama `transactional_ddl=False` es la que hace observable el `pending`; en la rama `True` la transacción lo elimina en el rollback.
**Example:**
```python
# Source: docs oficiales de commit implícito (MySQL/MariaDB) + diseño D-01/D-02.
# El runner NO llama db.commit(): usa db.transaction() (obligatorio para PoolDb).
async def _apply(db, name: str, qry: Query) -> None:
    ddl_done = False
    try:
        async with db.transaction():
            await db.execute(db.insert(MIGRATIONS_TABLE, {
                "name": name, "status": "pending", "sql_text": qry.sql,
            }))
            await db.execute(qry)
            ddl_done = True
            await db.execute(db.update(MIGRATIONS_TABLE, {"name": name}, {"status": "applied"}))
    except Exception:
        if not ddl_done:
            # El DDL no corrió (atómico por sentencia en los 6 motores): limpiar.
            async with db.transaction():
                await db.execute(db.delete(MIGRATIONS_TABLE, {"name": name}))
        # Si ddl_done y falló el promote → el pending queda para reconciliación.
        raise
```

### Pattern 2: Rollback con estado direccional
**What:** marcar `rolling_back`, ejecutar `down`, borrar la fila; compensar a `applied` si el `down` falla.
**When to use:** `rollback_migration`.
**Example:**
```python
# Source: D-06/D-07 + commit implícito del DDL en MySQL/MariaDB/Oracle.
async def rollback_migration(db, m: Migration) -> None:
    if m.down is None:
        raise MigrationError(f"{m.name} no tiene down")
    row = await _get_row(db, m.name)
    if row is None or row["status"] != "applied":
        raise MigrationError(f"{m.name} no está aplicada; usa resolve_migration() si está ambigua")
    try:
        async with db.transaction():
            await db.execute(db.update(MIGRATIONS_TABLE, {"name": m.name}, {"status": "rolling_back"}))
            await db.execute(_to_query(m.down))
            await db.execute(db.delete(MIGRATIONS_TABLE, {"name": m.name}))
    except Exception:
        try:
            async with db.transaction():
                await db.execute(db.update(MIGRATIONS_TABLE, {"name": m.name}, {"status": "applied"}))
        except Exception as exc:  # fail-open: queda rolling_back para reconciliar
            logger.warning("no se pudo restaurar %s a applied: %r", m.name, exc)
        raise
```

### Pattern 3: Store-then-invalidate por override
**What:** invalidar la clave afectada **después** de que `super()` retorna (post-commit).
**When to use:** `CachedModel.update/delete/upsert`; `save` queda cubierto por delegación.
**Example:**
```python
# Source: Microsoft cache-aside (escribe el store primero, invalida después).
async def update(self, keys=None, data=None) -> int:
    count = await super().update(keys=keys, data=data)   # commit ya ocurrió
    await self._invalidate(keys)
    return count
```

### Pattern 4: LRU acotado en stdlib
**What:** `OrderedDict` + `move_to_end` + `popitem(last=False)`.
**When to use:** `MemoryCacheBackend`.
**Example:**
```python
# Source: stdlib collections.OrderedDict.
async def set(self, key, value, ttl):
    expires_at = time.monotonic() + ttl if ttl else None
    self._store[key] = (value, expires_at)
    self._store.move_to_end(key)
    while len(self._store) > self._max_size:
        self._store.popitem(last=False)
```

### Anti-Patterns to Avoid
- **Envolver el DDL en `async with self.transaction()` en los seis motores sin ramificar:** en MySQL/MariaDB/Oracle el DDL commitea implícitamente y la transacción es teatro (Pitfall 8). El `pending` debe sobrevivir para que la reconciliación sea real.
- **Llamar `db.commit()` desde `migration.py`:** `PoolDb.commit()` lanza `ConnectionError` por diseño. Usar `async with db.transaction()`.
- **Usar el hook `after_commit` como único mecanismo de invalidación:** no dispara en `upsert`/`insert_many` ni conoce la clave.
- **Borrar el `pending` cuando falla el promote a `applied`:** borrarlo haría re-ejecutable un DDL que ya corrió. Solo se compensa si el DDL **no** corrió.
- **Interpolar identificadores sin `check_identifier`:** el `ALTER TABLE` y el nombre de tabla del ledger deben validarse (aunque sean constantes, por la regla del repo).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LRU con expiración | Estructuras de heap/listas propias | `collections.OrderedDict` | `move_to_end`/`popitem(last=False)` es exacto y O(1); a mano se meten bugs de orden. |
| Detección de columna existente | Parsear el DDL o catch genérico de excepciones | `columns_of()` (ya existe en los 6 adaptadores) | El catálogo es la fuente de verdad; el catch genérico traga errores no relacionados (regla del research). |
| Reintento/reconciliación de migraciones | Un mini-runner de DDL idempotente | La máquina de estados + `resolve_migration` (D-01…D-08) | Re-ejecutar DDL no idempotente corrompe; el humano decide con el SQL delante. |
| Invalidación distribuida | Pub/sub de Redis | Invalidate local por clave (D-11) | Fuera de alcance (AF-9); documentar la limitación multi-proceso. |
| Serialización de caché | Formato binario propio | `json.dumps(model_dump(mode="json"))` (existente) | Compatibilidad y legibilidad; ya funciona con ambos backends. |

**Key insight:** en este dominio lo "hecho a mano" que hay que evitar es la **atomicidad ficticia**: envolver DDL no transaccional en un `BEGIN/COMMIT` parece correcto y no lo es. La defensa es un dato por dialecto (`transactional_ddl`) que se **lee en runtime** y un test de inyección de fallo que demuestre que el estado ambiguo se **detecta**.

## Runtime State Inventory

> Esta fase **modifica el esquema de una tabla de estado en runtime** (`_encino_orm_migrations`) en instalaciones existentes. Aplica el inventario.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Tabla `_encino_orm_migrations` en bases existentes de los 6 motores, con columnas `id,name,applied_at,sql_text` y filas de migraciones ya aplicadas. | **Migración de datos + edición de código:** `ALTER TABLE … ADD status VARCHAR(20) NOT NULL DEFAULT 'applied'` backfillea las filas existentes como `applied` (correcto: una fila solo existe tras un DDL exitoso). El código nuevo escribe `status` explícito. |
| Live service config | Ninguno — el ledger vive en la BD del usuario, no en configuración de servicio externa. | Ninguna. |
| OS-registered state | Ninguno — no hay tareas programadas ni servicios que embeban el nombre del ledger. | Ninguna. |
| Secrets/env vars | Ninguno — no hay claves ni variables de entorno ligadas al ledger ni a la caché (salvo `ENCINO_ORM_REDIS_URL`, de tests, que no cambia). | Ninguna. |
| Build artifacts | Ninguno — paquete Python puro; no hay binarios ni artefactos con el nombre del ledger. | Ninguna. |

**Canonical question:** *después de actualizar todo el código, ¿qué sistemas en runtime siguen teniendo el esquema viejo?* → Las bases de datos de usuarios existentes con `_encino_orm_migrations` sin columna `status`. El `ALTER TABLE` idempotente en `_ensure_migrations_table` es el único punto que lo resuelve, y corre en el primer `migrate()`/`migrate_status()`/`reconcile_migrations()` tras el upgrade.

## Common Pitfalls

### Pitfall 1: "Atomicidad" ficticia en motores con commit implícito de DDL
**What goes wrong:** envolver DDL+registro en una transacción en MySQL/MariaDB/Oracle parece arreglar DATA-02, pasa un test en SQLite y sigue roto en producción.
**Why it happens:** el DDL hace commit implícito **antes** de ejecutarse; la transacción ya no existe cuando corre el DDL.
**How to avoid:** `transactional_ddl` por dialecto leído en runtime; en `False`, el `pending` se publica (commit implícito del DDL) y la reconciliación lo detecta. Test de inyección de fallo que afirme la **detección**, no la imposibilidad.
**Warning signs:** un solo `async with transaction()` uniforme; `transactional_ddl` documentado pero nunca leído; ningún test que observe un `pending`.
**Fuente:** PITFALLS.md Pitfall 8; MySQL implicit-commit docs; MariaDB implicit-commit docs.

### Pitfall 2: Confundir "DDL atómico" (crash-safe) con "DDL transaccional" (rollbackable)
**What goes wrong:** MySQL 8.0 ("Atomic DDL") y MariaDB ≥10.6 ("Atomic ALTER TABLE") hacen que un DDL caído no deje estado parcial **a nivel de sentencia**, y alguien "corrige" `transactional_ddl` a `True` para MariaDB. Pero **no se puede hacer ROLLBACK** de un DDL ya commiteado.
**Why it happens:** los docs de ambos motores usan la palabra "atomic" para crash-atomicity.
**How to avoid:** mantener `False` para MySQL/MariaDB/Oracle; dejar un comentario en `TRANSACTIONAL_DDL` citando el commit implícito, no la atomicidad de sentencia.
**Warning signs:** un PR que pone MariaDB en `True` citando "Atomic ALTER TABLE".

### Pitfall 3: El runner llama `db.commit()` y rompe con `PoolDb`
**What goes wrong:** `rollback_migration(pool, m)` o un `migrate()` que llame `await db.commit()` explota con `ConnectionError("commit() se gestiona con pool.transaction()…")` (`pool.py:245-248`).
**Why it happens:** el contrato de `PoolDb` prohíbe `commit()` directo; se asume que todos los `Db` se comportan igual.
**How to avoid:** el runner usa **solo** `async with db.transaction()` (que en `PoolDb` fija una conexión vía contextvar y commitea al salir). Nunca `db.commit()`.
**Warning signs:** un test de `rollback_migration` con `SqliteDb` pasa y con `PoolDb("sqlite", …)` falla.

### Pitfall 4: El hook `after_commit` no cubre todas las escrituras
**What goes wrong:** enganchar la invalidación solo a `after_commit` deja obsoletos `upsert` e `insert_many` (no pasan por `_transactional`), y el hook no recibe la acción ni la clave.
**Why it happens:** `upsert` usa su propio `retry(do_upsert)` (`model/model.py:648-652`) e `insert_many` su propio `db.transaction()` (`:572`); ninguno ejecuta `_run_hooks`.
**How to avoid:** overridear los métodos de escritura en `CachedModel` e invalidar tras `super()`.
**Warning signs:** un test que hace `upsert` y luego `load` sigue devolviendo el valor viejo.

### Pitfall 5: `insert_many` no tiene caché a la que invalidar
**What goes wrong:** `Model.insert_many` es `classmethod`; `CachedModel` guarda `_cache` por instancia. No hay forma de invalidar sin cambiar la API.
**Why it happens:** la caché es de instancia y el método es de clase.
**How to avoid:** decisión abierta (ver Open Questions). Recomendación: `CachedModel.insert_many(..., cache=None)` opcional que invalida las PK presentes en `rows`; o documentar el no-op (justificado: un INSERT puro no puede crear una entrada obsoleta para una clave que ya existía, porque violaría UNIQUE).
**Warning signs:** intentar acceder a `cls._cache` (no existe) o usar un global.

### Pitfall 6: `ALTER TABLE` no idempotente en carrera multi-proceso
**What goes wrong:** dos procesos arrancan a la vez, ambos ven la columna ausente y ambos ejecutan el `ALTER`; uno recibe error de columna duplicada y el arranque falla.
**Why it happens:** `CREATE TABLE IF NOT EXISTS` no añade columnas, y el chequeo+ALTER no es atómico.
**How to avoid:** patrón "verify-then-swallow": capturar el fallo del `ALTER`, hacer rollback best-effort, **re-consultar el catálogo**, y solo re-lanzar si la columna sigue ausente. Esto no requiere conocer el código de error exacto de cada motor.
**Warning signs:** catch genérico que se traga cualquier error del `ALTER`.

### Pitfall 7: Docs que describen la invalidación como si ya existiera
**What goes wrong:** `docs/guide.md:486` afirma "invalida al actualizar/borrar", pero no existe ninguna llamada a `cache.delete`. Dejar el doc como está perpetúa la mentira (Pitfall 25 del research).
**How to avoid:** el fix de DATA-03 hace verdadera la frase; añadir además el contrato dev/test de `MemoryCacheBackend` (D-14) y la nota de limitación multi-proceso.
**Warning signs:** un lector confía en el doc y descubre la lectura obsoleta en producción.

### Pitfall 8: `filterwarnings = ["error"]` convierte cualquier warning nuevo en fallo de suite
**What goes wrong:** código nuevo que emita un `DeprecationWarning`/`ResourceWarning` tumba la suite.
**How to avoid:** no introducir warnings; `OrderedDict` y `logging` no emiten ninguno. No añadir entradas nuevas a la allowlist de `filterwarnings` sin justificación escrita.

## Code Examples

### Consultar el catálogo para el ALTER idempotente (los 6 motores)
```python
# Source: implementaciones existentes de columns_of() en cada adaptador.
# SQLite:       PRAGMA table_info(<tabla>)                -> row["name"]
# MySQL/MariaDB: SHOW COLUMNS FROM <tabla>                -> row["Field"]
# PostgreSQL:   information_schema.columns                -> row["column_name"]
# SQL Server:   INFORMATION_SCHEMA.COLUMNS                -> row["name"]
# Oracle:       USER_TAB_COLUMNS (table_name=UPPER(...))  -> row["name"]
cols = {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}
if "status" not in cols:
    try:
        await self._execute_raw(
            f"ALTER TABLE {MIGRATIONS_TABLE} ADD status VARCHAR(20) NOT NULL DEFAULT 'applied'"
        )
        await self._connection.commit()
    except Exception:
        await self._safe_rollback()          # best-effort; ver nota de motor abajo
        if "status" not in {c.name.lower() for c in await self.columns_of(MIGRATIONS_TABLE)}:
            raise
```

### Reconciliación (D-02/D-03)
```python
# Source: diseño D-02/D-03/D-05/D-08.
async def reconcile_migrations(db) -> None:
    rows = await db.fetch_all(Query(
        f"SELECT name, status, sql_text FROM {MIGRATIONS_TABLE} "
        "WHERE status IN ({0}, {1}) ORDER BY id", ["pending", "rolling_back"],
    ))
    if not rows:
        return
    detail = "\n".join(
        f"  - {r['name']} [{r['status']}] SQL: {r['sql_text']}" for r in rows
    )
    raise MigrationError(
        "Migraciones en estado ambiguo (no se re-ejecuta DDL automáticamente).\n"
        f"{detail}\n"
        "Resuelve cada una con resolve_migration(db, name, applied=<bool>) "
        "tras verificar el catálogo real."
    )
```

### Invalidación fail-open (D-12)
```python
# Source: convención de logging del repo + D-12.
logger = logging.getLogger("encino_orm")

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

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `migrate()` = `DDL → registro → commit` | `pending` antes del DDL + promoción + reconciliación | Fase 3 | El ledger deja de mentir en MySQL/MariaDB/Oracle. |
| `rollback_migration` inserta `{name}:down` | Borra `{name}` y marca `rolling_back` durante el `down` | Fase 3 | Re-aplicar funciona; el estado direccional permite reconciliar. |
| Caché que solo escribe en `load` | Invalidate en `update`/`delete`/`upsert` (+`save`) | Fase 3 | Sin lecturas obsoletas tras escritura. |
| `dict` sin cota | LRU con `max_size=1024` | Fase 3 | Sin fuga de memoria en procesos largos. |

**Deprecated/outdated:**
- La fila `{name}:down` del ledger: eliminada (D-06).
- El catch de excepción de columna duplicada como mecanismo primario: reemplazado por consulta al catálogo (el catch queda solo como guardia de carrera).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MySQL/MariaDB devuelven error 1060 (`ER_DUP_FIELDNAME`) al añadir una columna existente | Desconocido 1 | Bajo: no se usa como mecanismo primario; el patrón verify-then-swallow no necesita el código. |
| A2 | SQL Server devuelve error 2705 ("column names in each table must be unique") al añadir una columna existente | Desconocido 1 | Bajo: igual que A1; la página oficial no se pudo recuperar (404) en esta sesión. |
| A3 | En D-08, para `rolling_back` el parámetro `applied` significa "la migración sigue aplicada" (es decir, `applied=True` ⇔ el `down` NO corrió), invirtiendo la lectura literal del encabezado "(¿corrió el SQL?)" | Desconocido 1 / Open Q2 | **Medio-alto:** si se implementa la lectura literal, `resolve_migration` borraría una fila cuya migración sigue aplicada. Las **acciones** de la tabla D-08 son autoconsistentes; el encabezado es el engañoso. Confirmar con el usuario. |
| A4 | SQL Server permite ROLLBACK de `CREATE TABLE`/`ALTER TABLE` (DDL transaccional) | Desconocido 1 | Medio: si no, `transactional_ddl=True` para MSSQL sería incorrecto y el `pending` no se publicaría. La asignación viene bloqueada del roadmap/PITFALLS; no se pudo citar doc oficial en esta sesión. |
| A5 | `CachedModel.insert_many` no puede acceder a una caché de instancia por ser `classmethod` | Desconocido 3 / Open Q1 | Medio: obliga a una decisión de API (kwarg opcional o no-op documentado). |

## Open Questions

1. **`insert_many` y la caché (D-09).**
   - What we know: `Model.insert_many` es `classmethod`; `_cache` es de instancia; un INSERT puro no puede crear una entrada obsoleta para una clave existente (violaría UNIQUE).
   - What's unclear: cómo honrar D-09 sin cambiar la API de forma incompatible.
   - Recommendation: `CachedModel.insert_many(cls, db=None, rows=None, *, chunk=None, cache=None)` — kwarg opcional; si se pasa, invalida las PK presentes en `rows` (una `delete` por clave). Si no, no-op documentado. Alternativa más simple: documentar que `insert_many` no invalida y por qué es seguro, y bajar la exigencia de D-09 para ese método (requiere confirmación del usuario).

2. **Semántica de `applied` en `resolve_migration` para `rolling_back` (D-05/D-08).**
   - What we know: las acciones de la tabla D-08 son autoconsistentes (`rolling_back`+False→borrar; `rolling_back`+True→restaurar `applied`).
   - What's unclear: el encabezado "(¿corrió el SQL?)" sugiere lo contrario para `rolling_back` (ver A3).
   - Recommendation: implementar las **acciones** literalmente y documentar el parámetro como "¿debe quedar registrada como aplicada?" (True) / "no aplicada" (False), con la pregunta concreta por estado en el docstring. Confirmar con el usuario antes de fijar el contrato público.

3. **`applied_at` al promover un `pending` resuelto.**
   - What we know: `applied_at` tiene `DEFAULT CURRENT_TIMESTAMP` en los 6 dialectos; al insertar `pending` ya se rellena.
   - What's unclear: si `applied_at` debe reflejar el momento de la promoción (y no el del intento).
   - Recommendation: al promover a `applied`, actualizar también `applied_at` con `db.fn.now()`; documentar. Bajo impacto, pero coherente con "el ledger deja de mentir".

4. **¿Detectar drift ledger↔catálogo?**
   - What we know: D-02 acota la reconciliación a estados ambiguos (`pending`/`rolling_back`).
   - What's unclear: una fila `applied` cuyo DDL nunca corrió (o fue revertido fuera de banda) no se detecta.
   - Recommendation: fuera de alcance de esta fase; documentar explícitamente como límite conocido (evita vender la reconciliación como más de lo que es).

5. **Pisos de cobertura (discreción del agente).**
   - Recommendation: añadir pisos bajos para `encino_orm/migration.py`, `encino_orm/model/cached.py` y `encino_orm/model/cache_backend.py` en `tools/ci/check_coverage_floors.py` **solo si** el primer run verde los mide con margen; el script falla cerrado si el módulo no aparece en el reporte, así que un piso mal calibrado bloquea CI.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Todo | ✓ | 3.13.7 en `.venv` (CI 3.10–3.13) | — |
| `uv` | Ejecutar tests/gates | ✓ | 0.12.15 | — |
| `pytest` / `pytest-asyncio` | Tests | ✓ | 9.1.1 / 1.4.0 | — |
| `coverage` | Pisos por módulo | ✓ | 7.16.1 | — |
| `syrupy` | Snapshots de Fase 2 (no de esta fase) | ✓ vía `uv run` | 6.1.1 (pin) | — |
| Docker | Tests de integración multi-motor | ✓ | 29.7.2 | SQLite (`:memory:`) siempre disponible |
| Contenedores MySQL/MariaDB/PostgreSQL/MSSQL/Oracle/Redis | Tests por motor | ✓ (todos corriendo) | — | `engine_unavailable()` omite en local / falla en CI con `ENCINO_ORM_REQUIRE_ENGINES` |

**Missing dependencies with no fallback:** ninguna.
**Missing dependencies with fallback:** ninguna.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (`asyncio_mode="auto"`, loop scopes `function`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (markers, `filterwarnings=["error"]`, `xfail_strict`) |
| Quick run command | `uv run pytest tests/test_migrations.py tests/test_cached_model.py tests/test_cache_backend.py -q` |
| Full suite command | `uv run pytest -q` (usa los 6 contenedores locales; en CI, `ENCINO_ORM_REQUIRE_ENGINES`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DATA-01 | `apply → rollback → apply` re-aplica el DDL y el ledger tiene una sola fila `{name}` sin `:down` | integration (SQLite) | `uv run pytest tests/test_migrations.py::TestMigrationRunner::test_reapply_after_rollback -x` | ❌ Wave 0 |
| DATA-01 | `rollback_migration` borra `{name}` y no inserta `{name}:down` | unit/integration | `uv run pytest tests/test_migrations.py -k rollback_ledger -x` | ❌ Wave 0 |
| DATA-02 | `TRANSACTIONAL_DDL` mapea los 6 dialectos (PG/SQLite/MSSQL True; MySQL/MariaDB/Oracle False) | unit DB-free | `uv run pytest tests/test_dialect_ddl.py -x` | ❌ Wave 0 |
| DATA-02 | Con `transactional_ddl=False`, un fallo tras el DDL deja `pending` y `reconcile_migrations` lanza `MigrationError` con el SQL | unit (fake `Db`) | `uv run pytest tests/test_migration_reconcile.py -x` | ❌ Wave 0 |
| DATA-02 | `ALTER TABLE` añade `status` a una tabla legacy y es idempotente (segunda ejecución no falla) | integration (SQLite + MySQL si disponible) | `uv run pytest tests/test_migrations.py -k ensure_status -x` | ❌ Wave 0 |
| DATA-02 | `migrate()` sigue siendo idempotente para una migración `applied` | unit | `uv run pytest tests/test_sqlite.py -k migrate_is_idempotent -x` | ✅ (regresión) |
| DATA-02 | `resolve_migration` infiere la acción correcta para las 4 filas de D-08 | unit (fake/ledger SQLite) | `uv run pytest tests/test_migration_reconcile.py -k resolve -x` | ❌ Wave 0 |
| DATA-03 | `update` invalida la clave cacheada (lectura posterior va a BD) | unit | `uv run pytest tests/test_cached_model.py -k update_invalidates -x` | ❌ Wave 0 |
| DATA-03 | `delete` invalida la clave cacheada | unit | `uv run pytest tests/test_cached_model.py -k delete_invalidates -x` | ❌ Wave 0 |
| DATA-03 | `upsert` invalida (y no deja obsoleta la lectura) | unit | `uv run pytest tests/test_cached_model.py -k upsert_invalidates -x` | ❌ Wave 0 |
| DATA-03 | Fallo de `cache.delete` = warning, no propaga (fail-open) | unit (cache fake que lanza) | `uv run pytest tests/test_cached_model.py -k invalidate_fail_open -x` | ❌ Wave 0 |
| DATA-04 | LRU desaloja la clave menos usada al superar `max_size` | unit DB-free | `uv run pytest tests/test_cache_backend.py -k lru -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_migrations.py tests/test_cached_model.py tests/test_cache_backend.py tests/test_migration_reconcile.py -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** suite completa verde antes de `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_migration_reconcile.py` — fake `Db` con `transactional_ddl=False`, ledger en memoria/SQLite, inyección de fallo del promote, `reconcile_migrations` y `resolve_migration` (DATA-02).
- [ ] `tests/test_cache_backend.py` — LRU, `max_size`, `_store` conserva `len()`, `delete` (DATA-04).
- [ ] Extender `tests/test_cached_model.py` — invalidación en `update`/`delete`/`upsert`, fail-open (DATA-03).
- [ ] Extender `tests/test_migrations.py` — regresión `apply→rollback→apply`, ledger sin `:down`, `ensure_status` idempotente (DATA-01/DATA-02).
- [ ] `tests/test_dialect_ddl.py` (o caso en `tests/test_dialect_builders.py`) — mapa `TRANSACTIONAL_DDL` DB-free.
- [ ] (Discreción) Pisos en `tools/ci/check_coverage_floors.py` para `migration.py`, `model/cached.py`, `model/cache_backend.py`.

*(Si el fake `Db` reutiliza el patrón de `tests/test_d_recommendations.py::LockDb`, recordar que **no** tiene `_ensure_migrations_table`: el helper `_ensure_ledger` debe tolerar su ausencia o el fake debe añadirlo.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | sí | `check_identifier` para todo identificador interpolado (nombre de tabla del ledger, columna `status`, sintaxis del `ALTER`); valores (`name`, `status`, `sql_text`) **siempre** ligados vía `Query`/builders. |
| V6 Cryptography | no | — |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection por nombre de migración | Tampering | El `name` viaja como parámetro ligado (`{0}`), nunca interpolado. |
| SQL injection por identificador de tabla/columna en el `ALTER TABLE` | Tampering | Constantes de módulo (`MIGRATIONS_TABLE`, `"status"`) + `check_identifier` antes de interpolar. |
| Ejecución de código arbitrario en `migrations_from_dir` (`exec_module`) | Elevation of Privilege | Riesgo **por diseño** y ya documentado en CONCERNS.md; documentar la frontera de confianza (directorio versionado y no escribible por terceros). |
| Fuga de SQL/credenciales en el mensaje de `MigrationError` | Information Disclosure | El `sql_text` es del desarrollador, no de usuario final; no incluir parámetros ni credenciales. Aceptable, pero no loguear `db` connection strings. |
| Invalidación de caché como vector de DoS (cache fake que lanza) | Denial of Service | Fail-open (D-12): la invalidación nunca propaga; la lectura obsoleta queda acotada por TTL. |
| Estado ambiguo no detectado (reconciliación que siempre pasa) | Repudiation / Tampering | Test de inyección de fallo que **observe** un `pending`; `transactional_ddl` leído en runtime (Pitfall 8). |

## Sources

### Primary (HIGH confidence)
- Código vivo leído y verificado: `encino_orm/migration.py`, `model/cached.py`, `model/cache_backend.py`, `model/model.py` (`_transactional` :419-434, `upsert` :648-652, `insert_many` :572), `base.py` (`transaction` :40-47, `retry` :75-89), `pool.py` (`commit` :245-248, `_run` :218-231), `sqlite.py`/`mysql.py`/`mssql.py`/`oracle.py`/`postgresql.py` (`migrate`/`_ensure_migrations_table`), `dialects/strategies.py`, `tools/ci/check_coverage_floors.py`.
- PostgreSQL ALTER TABLE (`ADD [COLUMN] [IF NOT EXISTS]`): https://www.postgresql.org/docs/current/sql-altertable.html
- SQLite ALTER TABLE (sin `IF NOT EXISTS`; `NOT NULL` exige default no-NULL): https://sqlite.org/lang_altertable.html
- MariaDB ALTER TABLE (`ADD COLUMN [IF NOT EXISTS]`) y commit implícito: https://mariadb.com/docs/server/reference/sql-statements/data-definition/alter/alter-table.md · https://mariadb.com/docs/server/reference/sql-statements/transactions/sql-statements-that-cause-an-implicit-commit.md
- MySQL ALTER TABLE (sin `IF NOT EXISTS`) y commit implícito: https://docs.oracle.com/cd/E17952_01/mysql-8.0-en/alter-table.html · https://docs.oracle.com/cd/E17952_01/mysql-8.0-en/implicit-commit.html
- SQL Server ALTER TABLE (`ADD` sin `IF NOT EXISTS`; `NOT NULL` requiere `DEFAULT`): https://learn.microsoft.com/en-us/sql/t-sql/statements/alter-table-transact-sql
- Oracle ORA-01430 ("column being added already exists in table"): https://docs.oracle.com/error-help/db/ora-01430/
- Verificación local de drivers: `asyncpg 0.31.0` expone `DuplicateColumnError` con `sqlstate == "42701"`; `sqlite3`/`aiosqlite` lanzan `sqlite3.OperationalError("duplicate column name: status")` con `sqlite_errorcode == 1` (genérico) — `[VERIFIED: .venv]`.
- Microsoft cache-aside (escribir el store primero, invalidar después): https://learn.microsoft.com/en-us/azure/architecture/patterns/cache-aside

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` Pitfall 8 (teatro de seguridad) y Pitfall 17 (cachés sin cota); `.planning/research/SUMMARY.md` §Phase 3; `.planning/research/FEATURES.md` TS-11/TS-12/TS-13/TS-34; `.planning/codebase/CONCERNS.md` (bug de rollback, no-atomicidad, caché sin invalidar, `_store` sin cota).
- Alembic `transactional_ddl` / `begin_transaction()`: https://alembic.sqlalchemy.org/en/latest/api/runtime.html (citado en FEATURES.md; no re-fetchado).

### Tertiary (LOW confidence)
- Códigos de error de columna duplicada de MySQL (1060) y SQL Server (2705): documentación estándar ampliamente citada, pero las páginas oficiales no fueron recuperables en esta sesión (403/404). **No se usan como mecanismo primario** (ver A1/A2).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no hay dependencias nuevas; versiones verificadas en `.venv`.
- Architecture: HIGH — el flujo del runner y la imposibilidad de `db.commit()` en `PoolDb` se verificaron leyendo el código; el commit implícito del DDL se verificó en docs oficiales.
- Pitfalls: HIGH/MEDIUM — Pitfall 1-4 y 6 verificados en código/docs; Pitfall 5 (insert_many) es una decisión de diseño, no un hecho.

**Research date:** 2026-09-18
**Valid until:** 2026-10-18 (30 días; el dominio es estable, pero revisar si se actualiza el cap de drivers o si Fase 4 cambia `PoolDb.commit`).
