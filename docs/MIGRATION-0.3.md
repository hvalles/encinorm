# Guía de migración a 0.3.0

`0.3.0` acumula las rupturas incompatibles preparadas durante las Fases 2–7 del
milestone: no solo los *shims* deprecados en `0.2.7`, sino también los cambios de
*hardening* que endurecen contratos de seguridad y de corrección. Esta guía
presenta cada ruptura como un par **Antes (0.2.6)** / **Después (0.3.0)** y cierra
con una acción concreta.

> **Alcance.** El inventario cubre los cambios incompatibles acumulados desde
> `0.2.6`. El detalle completo y su justificación viven en `CHANGELOG.md`; esta
> guía es el camino de adaptación. Los ejemplos usan credenciales ficticias de
> desarrollo (`admin` / `Admin_123`), nunca valores reales.

`0.2.7` emitió un `DeprecationWarning` de runtime para los cambios que podían
avisarse sin degradar la defensa. Las rupturas *fail-closed* (validación de
identificadores, contrato de cardinalidad de `Query`) **no** pueden emitir un
aviso previo: rechazan el valor antes de aceptarlo, y degradar esa defensa para
poder avisar reabriría la superficie de inyección. Por eso se documentan aquí.

## Query: contrato de cardinalidad

`Query` exige que el conjunto de placeholders `{n}` de la plantilla coincida
exactamente con la lista de valores. El camino compatible `Query(sql, [])` se
conserva sin cambios.

**Antes (0.2.6):** los valores sobrantes se descartaban en silencio y `{00}` podía
dejar una clave que el adaptador no resolvía.

```python
q = Query("SELECT * FROM t WHERE id = {0}", [1, 2, 3])  # 2 y 3 se ignoraban
```

**Después (0.3.0):** la cardinalidad se valida y un desajuste lanza `ValueError`.

```python
q = Query("SELECT * FROM t WHERE id = {0}", [1])   # correcto
Query("SELECT * FROM t WHERE id = {0}", [1, 2])    # ValueError
```

`rebind` se eliminó (ruptura limpia, sin *shim*): su sustituto es
`with_params()`, que devuelve una **copia** nueva en vez de mutar el objeto.

**Acción:** ajusta la lista de valores al número de `{n}` y sustituye cualquier
uso de `rebind` por `with_params()`.

## Validación estricta de identificadores

Todo identificador que se interpola en SQL (`_table`, destinos de `join()`,
columnas de índice, nombres de columna de `insert_many`) pasa por una allowlist
estricta *fail-closed* antes de generar la sentencia.

**Antes (0.2.6):** un `_table` o un `Index` no identificador se interpolaba tal
cual en la DDL/DML, incluida una carga hostil.

```python
class Agente(Model):
    _table = "agentes; DROP TABLE x --"  # se interpolaba verbatim
```

**Después (0.3.0):** la validación lanza `ValueError` **antes** de generar SQL.

```python
class Agente(Model):
    _table = "agentes"  # identificador válido

# ValueError: nombre de tabla inválido: 'agentes; DROP TABLE x --'
```

La allowlist tolerante a puntos (expresiones calificadas como `mm.agente`) se
conserva a propósito en las posiciones de expresión de `select`/`group_by`/
`order_by`; no se unifica con la estricta.

**Acción:** si tu modelo dinámico o generado por codegen construía `_table` con
un nombre no identificador, corrígelo antes de migrar.

## PoolDb.acquire() devuelve un handle

`PoolDb.acquire()` ya no devuelve un `Db` crudo: devuelve un `PooledConnection`
(un handle con `driver`, `last_used`, `generation`, `checked_out` y
`owner_task`).

**Antes (0.2.6):** `acquire()` devolvía el `Db` directamente.

```python
db = await pool.acquire()
await db.execute(qry)
await pool.release(db)
```

**Después (0.3.0):** `acquire()` devuelve el handle y el `Db` vive en `.driver`.

```python
from encino_orm import PooledConnection

handle: PooledConnection = await pool.acquire()
await handle.driver.execute(qry)
await pool.release(handle)  # release() acepta el handle o el Db
```

**Acción:** usa `handle.driver` para el `Db` subyacente. `release()` sigue
aceptando ambos, así que puedes migrar de forma incremental.

## Liberación, cierre y reaping del pool

La política de liberación cambió de "confirmar el sobrante" a "revertir por
defecto", y `close()` dejó de cerrar conexiones en uso.

**Antes (0.2.6):** `release()` no tocaba la transacción y un sobrante abierto se
confirmaba por accidente; `close()` cerraba también las conexiones retenidas.

```python
pool = PoolDb(dsn, min_size=1, max_size=4)  # liberación implícita vieja
await pool.close()  # cerraba también las conexiones en uso
```

**Después (0.3.0):** `release()` revierte por defecto (`reset_on_release="rollback"`)
y `close()` es idempotente: solo cierra las ociosas.

```python
pool = PoolDb(dsn, min_size=1, max_size=4, reset_on_release="rollback")
await pool.close()  # las conexiones en uso siguen vivas hasta liberarse
```

`reset_on_release="commit"` restaura la política vieja pero queda **DEPRECADO**
(emite `DeprecationWarning` al construir el pool). Un valor distinto de
`"rollback"`/`"commit"` lanza `ValueError`. Las conexiones ociosas por encima de
`min_size` se cierran tras `idle_timeout` mediante un reaper perezoso (sin
daemon); con `idle_timeout=None` el reaper está desactivado.

**Acción:** si dependías del commit accidental al liberar, migra a `async with
db.transaction()` o ejecuta el commit explícito antes de `release()`. No uses
`reset_on_release="commit"` en código nuevo.

## last_id() y captura del id de inserción

El id de una inserción se captura **dentro** de la sentencia que lo produce, no
después.

**Antes (0.2.6):** `last_id()` se leía tras la sentencia; bajo concurrencia podía
devolver el id de **otra** fila (el cache de id vivía a nivel de pool).

```python
await db.execute(qry)
nuevo_id = await db.last_id()  # id de otra fila bajo concurrencia
```

**Después (0.3.0):** usa `execute_insert(qry)` o el retorno de `Model.insert()`.

```python
nuevo_id = await db.execute_insert(qry)
# o, con un modelo:
agente = await Agente.insert(...)
nuevo_id = agente.id
```

`last_id()` queda **DEPRECADO** (emite `DeprecationWarning`) porque solo devuelve
un id *best-effort*.

**Acción:** sustituye cada `last_id()` post-hoc por `execute_insert` o por el
retorno de `Model.insert`. En MSSQL/Oracle con `replace=True` (render `MERGE`)
`Model.insert` devuelve `0` ("id no disponible") y deja `self.id` intacto.

## Caché de CachedModel: clave y dominio por PK

La clave de caché incorpora la huella del `scope()` activo y el dominio pasa a
ser siempre la **PK canónica** de la fila (no la clave de lectura).

**Antes (0.2.6):** la clave era `sha1(tabla:[pk=...])`, sin huella de tenant, y
una lectura por clave no-PK podía dejar la entrada bajo esa misma clave.

```python
clave = sha1("agentes:[rfc=XAXX010101000]")  # sin scope
```

**Después (0.3.0):** la clave es `sha1(tabla:[pk=...]|scope=<huella>)` y el
dominio es la PK de la fila.

```python
# dentro de scope(tenant):
clave = sha1("agentes:[id=1]|scope=<huella>")
```

Sin `scope()` activo la clave es idéntica a la del formato anterior, así que el
camino sin multi-tenancy no cambia. Al ser un cambio de formato, un backend
compartido puede conservar claves del formato viejo como entradas huérfanas hasta
que expire su TTL; el nuevo formato no las sirve.

`CachedModel` además invalida la entrada de **todas** las filas afectadas por una
escritura (no solo una), después del commit y de forma *fail-open*.

**Acción:** si compartes un backend de caché entre versiones, deja expirar las
claves viejas o vacía el almacén al desplegar. Asegúrate de que lector y escritor
corren bajo el mismo `scope()`.

## Migraciones: ledger y flujo de dos fases

El runner de migraciones inserta la fila `pending` **antes** del DDL y la promueve
a `applied` después; el ledger gana una columna `status`.

**Antes (0.2.6):** la fila se insertaba tras el DDL; un fallo parcial dejaba el
esquema cambiado sin registro (el ledger mentía).

```python
await db.execute(up_ddl)
await db.execute(ledger_insert)  # si el DDL fallaba a medias, no había fila
```

**Después (0.3.0):** primero `pending`, luego el DDL, luego `applied`.

```python
await db.execute(ledger_insert_pending)
await db.execute(up_ddl)
await db.execute(ledger_mark_applied)
```

Un `pending` huérfano (posible en motores con commit implícito de DDL:
MySQL/MariaDB/Oracle) se detecta con `reconcile_migrations()`, que **nunca**
re-ejecuta DDL ni asume `applied`, y se resuelve con
`resolve_migration(db, name, applied=...)`. `rollback_migration` ahora **borra**
la fila del ledger (antes dejaba una fila `{name}:down`).

**Acción:** si consultabas `migrate_status()` buscando filas con sufijo `:down`,
esas filas ya no existen. Ejecuta `create_table`/`ALTER TABLE` idempotente una vez
para añadir la columna `status` a instalaciones existentes (lo hace el propio
runner).

## Taxonomía de errores y traducción de excepciones

Las excepciones del driver se traducen a la taxonomía de la librería
(`ConnectionLostError`, `OperationalError`, `IntegrityError`, `ProgrammingError`).

**Antes (0.2.6):** la excepción del driver salía cruda y la capturabas tal cual.

```python
import sqlite3

try:
    await Agente.insert(...)
except sqlite3.IntegrityError:   # capturaba la excepción del driver
    ...
```

**Después (0.3.0):** `Db._translate_exception` la **sustituye** por la de
`encino_orm`; la causa original se preserva en `__cause__`.

```python
from encino_orm import IntegrityError

try:
    await Agente.insert(...)
except IntegrityError:            # 400 en la capa HTTP
    ...
```

Un error de **lock** se devuelve sin traducir para no romper `retry()`. En HTTP,
`IntegrityError`/`ProgrammingError` derivan de `QueryError` (400),
`OperationalError` de `EncinoOrmError` (500) y `ConnectionLostError` de
`ConnectionError` (500).

**Acción:** cambia tus `except` de tipos del driver por los tipos de
`encino_orm`; si necesitas el error original, inspecciona `__cause__`.

## Reciclado de conexiones directas

Dos kwargs *opt-in* de `connect()` permiten que una conexión directa sobreviva a
periodos de inactividad.

**Antes (0.2.6):** una conexión directa inactiva moría sin recuperación.

```python
db = SqliteDb()
await db.connect(database="app.db")
```

**Después (0.3.0):** `pre_ping` y `max_connection_lifetime` son *opt-in*.

```python
db = PostgresDb()
await db.connect(
    host="127.0.0.1", port=5432,
    user="admin", password="Admin_123", database="app",
    pre_ping=True,                 # sondea is_alive() antes de cada operación
    max_connection_lifetime=1800,  # recicla por edad (segundos)
)
```

El reciclado mide **edad** con `time.monotonic()`, no inactividad. SQLite
`:memory:` **rechaza** reconectar (crearía una base vacía y perdería los datos)
lanzando `ConnectionLostError`.

**Acción:** activa `pre_ping`/`max_connection_lifetime` solo si tu conexión
directa cruza periodos de inactividad; ambos añaden coste (un round-trip por
operación en `pre_ping`).

## Configuración de proceso y seguridad (CFG-01/CFG-02)

El default de conexión de proceso y la configuración de seguridad dejan de ser
globales mutables.

**Antes (0.2.6):** `set_default_db`/`get_default_db` y `SECRET`/`GET_DB` eran
globales de proceso mutables, compartidos por todas las aplicaciones.

```python
set_default_db(db)
guard.SECRET = "..."      # mutaba el comportamiento global
```

**Después (0.3.0):** un `ConnectionRegistry` inyectable y una `SecurityConfig`
`frozen` reemplazan a los globales.

```python
registry = ConnectionRegistry()
registry.set_default(db)
resolve_db(registry=registry)

config = SecurityConfig(secret="...", get_db=...)
get_current_user, require = security_dependencies(config)
```

En `0.2.7` ambos shims emitían `DeprecationWarning`; mutar los globales deja de
cambiar el comportamiento en `0.3.0`. Para aislar por tenant, pasa `db=`
explícito o usa `bind`/`session` (un `Model` no acepta un registry directamente).

**Acción:** sustituye los globales por un `ConnectionRegistry` explícito y por
`SecurityConfig` + `security_dependencies(config)`.

## Resumen

| Ruptura | Antes (0.2.6) | Después (0.3.0) | Acción |
|---------|---------------|------------------|--------|
| Cardinalidad de `Query` | Valores sobrantes descartados en silencio | `ValueError`; `rebind` eliminado | Ajustar valores; usar `with_params()` |
| Identificadores | Interpolación verbatim | Allowlist estricta `fail-closed` | Usar identificadores válidos |
| `PoolDb.acquire()` | Devuelve `Db` | Devuelve `PooledConnection` | Usar `handle.driver` |
| Liberación del pool | Commit accidental; `close()` cierra en uso | `rollback` por defecto; `close()` idempotente | Commit transaccional explícito |
| `last_id()` | Id post-hoc de otra fila | `execute_insert`/retorno de `insert` | Sustituir `last_id()` |
| Clave/dominio de caché | `sha1(tabla:[pk])`, dominio variable | `sha1(tabla:[pk]\|scope)` y PK canónica | Vaciar/expirar claves viejas |
| Ledger de migraciones | Fila tras el DDL; `{name}:down` | `pending`→`applied`; `status` | Ejecutar `reconcile_migrations()` |
| Taxonomía de errores | Excepción cruda del driver | Traducida (con `__cause__`) | Capturar tipos de `encino_orm` |
| Reciclado de conexiones | Conexión inactiva muere | `pre_ping`/`max_connection_lifetime` | Activar opt-in si aplica |
| Defaults globales | `set_default_db`/`SECRET` mutables | Registry + `SecurityConfig` inmutables | Inyectar registry/config |
