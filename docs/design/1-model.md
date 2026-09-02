# Documento de Diseño — EncinoModel

Módulo de capa de modelos ORM asíncrono construido sobre **encinorm** (la librería de interfaz unificada de base de datos descrita en `docs/design/0-design.md`). Los modelos heredan de `pydantic` y se vinculan a una tabla de la base de datos mediante el atributo `_table`.

> **Nota de nomenclatura:** en el prompt original se hace referencia a la librería como *"encinoorm"*. En este repositorio el paquete se llama **`encinorm`** (ver `pyproject.toml`). El presente módulo se denominará **`EncinoModel`** y vivirá como subpaquete `encinorm.model`.

---

## 1. Introducción y Objetivos

**EncinoModel** aporta una capa de mapeo objeto-relacional (ORM) sobre la interfaz `Db` de encinorm. Permite definir modelos de datos como clases `pydantic` que saben persistirse y consultarse a sí mismas, sin escribir SQL manualmente.

### Objetivos

| # | Objetivo |
|---|----------|
| 1 | Modelos que heredan de `pydantic.BaseModel` y se vinculan a una tabla vía el atributo `_table`. |
| 2 | Reutilizar la interfaz `Db` (SQLite, MySQL, PostgreSQL) como backend de comunicación. |
| 3 | Operaciones CRUD asíncronas: `insert`, `update`, `delete`, `load`, `search`. |
| 4 | Seguimiento automático del estado del registro: `__exists` y `__dirties`. |
| 5 | Relaciones entre modelos con carga perezosa (`lazy loading`) mediante `add_reference` con acceso por índice (`a["region"]`). |
| 6 | Caché en Redis (u otro backend) mediante `CachedModel` con backend inyectable. |
| 7 | Validación de campos con reglas declarativas y traducción de tipos por motor. |
| 8 | Hooks/triggers del ciclo de vida (`before_insert`, `before_update`, `before_delete`, `before_commit`, `after_commit`). |
| 9 | Constructor de consultas (`Query`) con `join`, `exists` y funciones de agregado. |

### Audiencia

Desarrolladores Python, preferentemente de **FastAPI**, que usan `asyncio` y desean una capa de modelos tipada y validada sin abandonar el control del backend de datos.

---

## 2. Contexto y Convenciones

### 2.1. Campos predeterminados

Toda tabla gestionada por EncinoModel tendrá, por defecto, los siguientes campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | `int` | Llave primaria autoincremental. |
| `enabled` | `tinyint` | Estado del registro (`1` válido, `0` eliminado lógicamente). |
| `created_at` | `datetime` | Fecha de creación. **Nunca** se actualiza. |
| `updated_at` | `datetime` | Fecha de última actualización. Se refresca automáticamente tras cada `update`/`delete`. |

```python
from datetime import datetime
from encinorm.model import Model

class Agente(Model):
    _table = "agentes"
    id: int
    agente: str
    # id, enabled, created_at, updated_at se heredan del Model base
```

### 2.2. Reglas de mapeo campo ↔ columna

1. Cada atributo del modelo corresponde a una columna de la tabla, **excepto**:
   - Los que inician con `_` (guion bajo), que son **internos** y no se persisten (`_table`, `_db`, `__exists`, `__dirties`, etc.).
   - Los atributos/propiedades que apuntan a otro `Model` (o descendiente), que se tratan como **relaciones** y no como columnas.
2. El nombre de columna por defecto es el nombre del atributo; puede sobreescribirse con `Column(name=...)` (nombre real de la columna en la BD), lo que permite mapear modelos a tablas existentes con otra nomenclatura.

### 2.3. Campos heredados opcionales (desactivación)

Los cuatro campos predeterminados (`id`, `enabled`, `created_at`, `updated_at`) pueden **desactivarse** o **mapearse** por modelo para soportar tablas existentes que no siguen el patrón de EncinoModel:

```python
class Legacy(Model):
    _table = "legacy"
    # desactivar campos no usados
    _fields_disabled = ["enabled", "created_at", "updated_at"]
    # o mapear a columnas con otro nombre (vía Column.name)
    id: Annotated[int, Column(name="legacy_id")]
```

| Mecanismo | Efecto |
|-----------|--------|
| `_fields_disabled: list[str]` | Lista de campos heredados a excluir de todo DML/DQL. |
| `Column(name=...)` | Mapa `atributo -> nombre_columna` (reemplaza el antiguo `_fields_aliases`). |

---

## 3. Modelo de Datos y Clases

### 3.1. Declaración de campos (`Column` + `pydantic` nativo)

La declaración de campos se apoya en **`pydantic` nativo** para la validación y en un marcador liviano **`Column`** (vía `Annotated`) para la metadata ORM. No se crea una clase `Field` propia: evita depender de los internals de `pydantic` y separa validación (pydantic) de traducción a DDL (`types.py`).

```python
from typing import Annotated
from dataclasses import dataclass

@dataclass(frozen=True)
class Column:
    datatype: str = "str"          # int, bool, str, datetime, date, numeric, blob, float
    name: str | None = None        # nombre de columna en la BD (si difiere del atributo)
```

**Uso:**

```python
from pydantic import Field
from encinorm.model import Model, Column

class Agente(Model):
    _table = "agentes"
    id: int
    agente: Annotated[str, Column(datatype="str", name="agente")]
    monto: Annotated[float, Column(datatype="numeric")] = Field(ge=0, default=0)
```

**Validación (delegada a pydantic):**

| Regla | Mecanismo pydantic |
|-------|--------------------|
| `required` | `Optional`/`None` vs `...` (o `Field(default=...)`). |
| `default` | `Field(default=valor)`. |
| `min` / `max` | `Field(ge=…, gt=…, le=…, lt=…)`. |
| `length=(min,max)` | `Field(min_length=…, max_length=…)` — cuenta **caracteres** (code points), correcto para UTF-8. |
| `constraint=func` | `@field_validator("campo")` o `Annotated[..., AfterValidator(func)]`. |
| nombre de columna | `Column(name=…)` (reemplaza `alias` y `_fields_aliases`). |

**Traducción de tipos:** el `datatype` lógico (`str`, `numeric`, `datetime`, …) se traduce a DDL por motor en `types.py` (`str→TEXT` en SQLite, `str→VARCHAR` en MySQL, etc.), manteniendo la validación y el DDL desacoplados.

```python
# types.py (mapa independiente)
DDL_MAP = {
    "sqlite":  {"str": "TEXT", "int": "INTEGER", "datetime": "TEXT", "numeric": "REAL"},
    "mysql":   {"str": "VARCHAR(255)", "int": "INT", "datetime": "DATETIME", "numeric": "DECIMAL"},
    "postgres":{"str": "TEXT", "int": "INTEGER", "datetime": "TIMESTAMP", "numeric": "NUMERIC"},
}
```

### 3.2. `Model` (clase base)

Clase base que hereda de `pydantic.BaseModel` y aporta el comportamiento ORM.

```python
from datetime import datetime
from typing import ClassVar, Any
from pydantic import BaseModel, PrivateAttr, ConfigDict
from encinorm import Db

class Model(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- Mapeo ---
    _table: ClassVar[str] = ""                          # nombre de la tabla en la BD
    _fields_disabled: ClassVar[list[str]] = []          # campos heredados a desactivar
    _db: Db                                             # interfaz de comunicación (se inyecta al crear el modelo)

    # --- Campos heredados (presentes en toda tabla) ---
    id: int | None = None                # llave primaria, autoincremental
    enabled: int = 1                     # tinyint: 1 válido, 0 eliminado
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # --- Estado interno (no persisten) ---
    __exists: bool = PrivateAttr(default=False)   # True si el registro existe en BD
    __dirties: list[str] = PrivateAttr(default_factory=list)

    def __init__(self, db: Db = None, **kwargs): ...
```

#### 3.2.1. `__init__(db=None, **kwargs)`

- Inyecta la conexión `db` en `_db`.
- Acepta los atributos declarados como `**kwargs`.
- Inicializa `__exists = False` y `__dirties = []`.
- Registra en `__dirties` cualquier campo con valor asignado (para soportar `update` parcial).

#### 3.2.2. `load(keys=["id"])`

Firma: `async def load(keys: list[str] = ["id"]) -> Model`.

- `keys` es una lista o cadena separada por comas con los nombres de los campos usados para **buscar** el registro; los valores se toman del propio modelo.
- Ejecuta un `SELECT` de la tabla filtrando por esos campos.
- Si **encuentra** el registro:
  - Asigna los valores de la BD a los campos del modelo (respetando `Column.name`).
  - Establece `__exists = True`.
- Si **no** encuentra:
  - `__exists = False`.
- En ambos casos reinicializa `__dirties = []`.
- Devuelve un **objeto nuevo** de la clase contenedora con los campos recuperados.

```python
a = Agente(db=CurrentDb, id=100)
a = await a.load()
# si existe: a.__exists == True y los campos quedan hidratados
# si no existe: a.__exists == False
```

#### 3.2.3. `insert()`

Firma: `async def insert() -> int`.

- Ejecuta un `INSERT` en la tabla con los campos del modelo.
- Establece `created_at` y `updated_at`.
- Devuelve el `id` generado.
- Tras insertar, actualiza `__exists = True` y `__dirties = []`.

#### 3.2.4. `update(keys=["id"], data=None)`

Firma: `async def update(keys: list[str] = ["id"], data: list[str] = None) -> None`.

- `keys`: lista de campos usados como llave para identificar el registro (default `["id"]`).
- `data`: lista de campos a actualizar (default `__dirties`). Si está vacía, actualiza **todos** excepto `id` y `created_at`.
- Excluye siempre los campos que inician con `_` y los que son tipo `Model` (o descendientes).
- Actualiza `updated_at` automáticamente.
- **Asignación explícita:** no se especula sobre la actualización. Si `data` está vacía **y** no hay un valor explícito para la llave de identificación (o ninguna llave válida), se **lanza error** (`FailOnUpdate`) sin tocar la base de datos. Toda actualización queda determinada por `keys`/`data`/`__dirties` explícitos.
- Lanza `FailOnUpdate` (excepción personalizada) si la operación no se completa, con la razón emitida por la base de datos.

#### 3.2.5. `delete(keys=["id"], physical:bool=False)`

Firma: `async def delete(keys: list[str] = ["id"], physical:bool=False) -> bool`.

- si physical es False se ejecuta un borrado lógico, si es True se eliminara de la base de datos.
- **Borrado lógico:** ejecuta `UPDATE ... SET enabled = 0` dejando evidencia del registro.
- Resetea `__exists = False` y `__dirties = []`.
- **Borrado físico:** ejecuta `DELETE FROM ... ` eliminando el registro de la base de datos.
- Resetea `__exists = False` y `__dirties = []`.

#### 3.2.6. `search(filter=None, columns=["*"])`

Firma: `async def search(filter: Filter | None = None, columns: list[str] = ["*"]) -> list[Model]`.

- Devuelve asíncronamente una lista de objetos del modelo que cumplan el criterio.
- `filter`: objeto `Filter` que describe las condiciones (ver 3.6.1).
- `columns`: columnas a recuperar; por defecto todas (`*`).

#### 3.2.7. `validate()` (validación de datos)

Firma: `async def validate(self) -> dict | None`.

Valida que los datos del modelo cumplan los criterios declarados en el propio modelo (reglas de la sección 3.1: `required`, `min`/`max`, `length`, `constraint`, etc.). Permite identificar **qué columna** no cumple y **por qué**.

```python
@before_insert
@before_update
async def validate(self) -> dict | None: ...
```

- **Devuelve** un diccionario con las columnas que incumplen el modelo:
  ```python
  {
      "columna": "[Criterio no cubierto | criterio esperado] + valor actual {value}"
  }
  ```
- Si **todo es válido**, devuelve `None` (sin errores).
- Se ejecuta **automáticamente** dentro de `before_insert` y `before_update`.
- En `before_update`, solo se consideran inválidas las columnas que **se van a actualizar** (según `data`/`__dirties`); las columnas no involucradas no se validan.

```python
class Agente(Model):
    _table = "agentes"
    id: int
    agente: Annotated[str, Column(datatype="str")] = Field(min_length=3, max_length=50)
    monto: Annotated[float, Column(datatype="numeric")] = Field(ge=0)

# si agente="" y monto=-5, validate() devolvería:
# {
#   "agente": "length(min=3, max=50) | valor actual ''",
#   "monto": "min(ge=0) | valor actual -5",
# }
```

> **Convención de retorno:** se adopta `dict | None` en lugar de `dict | False`/`dict | True`. `None` evita la ambigüedad de un booleano (no sugiere "inválido") y de un `True` que colisionaría con un diccionario *truthy*. Uso en hooks: `errores = await self.validate(); if errores: raise ValidationError(errores)`.

### 3.3. `CachedModel` y `CacheBackend`

#### 3.3.1. `CacheBackend` (interfaz inyectable)

El caché es **inyectable**. Se define una interfaz mínima para desacoplar `CachedModel` de la implementación concreta (Redis, Memcached, dict en memoria, etc.):

```python
from typing import Protocol

class CacheBackend(Protocol):
    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    async def delete(self, key: str) -> None: ...
```

Implementaciones previstas:

| Clase | Backend |
|-------|---------|
| `RedisCacheBackend` | `redis` (asíncrono) — opcional, en `[project.optional-dependencies] cache`. |
| `MemoryCacheBackend` | `dict` en memoria — para pruebas y desarrollo. |

#### 3.3.2. `CachedModel`

Hereda de `Model`. Persiste el resultado de `load` en un `CacheBackend` inyectado.

- **Llave:** hash `sha1` construido con `tabla` + nombres de parámetros + valores de `keys`.
- **Formato de llave:** `clientes:[rfc=value]`; si hay más de un campo, se unen con `&` (`clientes:[rfc=X&nombre=Y]`).
- **Duración:** `300` segundos por defecto, sobreescribible por parámetro.

```python
class CachedModel(Model):
    _cache: CacheBackend | None = None      # inyectable vía __init__ o set_cache()

    def __init__(self, db: Db = None, cache: CacheBackend = None, **kwargs): ...

    async def load(self, keys: list[str] = ["id"], duration: int = 300) -> "CachedModel":
        # 1. calcular llave sha1 -> cache.get(key)
        # 2. si existe, hidratar desde caché
        # 3. si no, consultar BD, cache.set(key, valor, ttl=duration)
```

### 3.4. Relaciones y Referencias

#### 3.4.1. `add_reference` (enfoque declarativo)

Se define un mecanismo declarativo de referencias que se agregan **después** de crear el modelo, evitando codificar propiedades a mano:

```python
a = Agente(db=db, id=1, agente="x", region_id=10)
a.add_reference("region", Region, {"id": "region_id"})

region = await a["region"]          # carga perezosa
```

**Acceso a referencias:** se accede mediante índice (`a["region"]`), sobrecargando `__getitem__`:

```python
class Model:
    _references: dict[str, "Reference"] = PrivateAttr(default_factory=dict)

    def add_reference(
        self,
        name: str,
        model_class: type["Model"],
        match_keys: dict[str, str],       # {campo_local: campo_remoto}
        on_delete: str | None = None,     # None | "cascade" | "set_null" | "restrict"
    ) -> None: ...
    def __getitem__(self, name: str) -> Awaitable["Model"]: ...
```

**Comportamiento esperado:**
- La referencia se resuelve a demanda (`await a["region"]`).
- Si cambia el valor de la llave local (`region_id`), el modelo referenciado se **reinicializa**.
- Si no cambió, se reutiliza el valor previamente cargado (caché por instancia).
- `add_reference` lanza `DuplicateReferenceError` si el `name` ya está registrado o si colisiona con un campo/columna existente del modelo.

#### 3.4.2. Integridad referencial y borrado en cascada (opcional)

Las referencias pueden declarar **opcionalmente** políticas de integridad referencial:

| `on_delete` | Comportamiento |
|-------------|----------------|
| `None` (default) | Sin acción; la relación es solo de lectura perezosa. |
| `"cascade"` | Al eliminar el padre, se eliminan también los registros referenciados. |
| `"set_null"` | Al eliminar el padre, la llave foránea del hijo se pone a `NULL`. |
| `"restrict"` | Se impide eliminar el padre si existen hijos referenciados. |

Estas políticas se traducen a cláusulas `ON DELETE` de llave foránea (`FOREIGN KEY ... REFERENCES ... ON DELETE CASCADE`) o a operaciones equivalentes dentro de la transacción cuando el motor no soporte DDL de integridad. La persistencia conjunta padre-hijos se realiza en la **misma transacción**.

### 3.5. Hooks / Disparadores del ciclo de vida

Se implementan como **decoradores** a nivel de clase.

| Decorador | Momento de ejecución |
|-----------|----------------------|
| `@before_insert` | Antes de ejecutar `INSERT`. |
| `@before_update` | Antes de ejecutar `UPDATE`. |
| `@before_delete` | Antes de ejecutar `DELETE` lógico. |
| `@before_commit` | Dentro de `transaction()`, **antes** del `commit`. Recibe el nombre de la acción (`"insert"`, `"update"`, `"delete"`). Puede lanzar `Exception` y provocar `rollback()`. |
| `@after_commit` | **Fuera** de `transaction()`, después de un commit exitoso. Para procesos externos (envío de correos, colas, webhooks) que pueden bloquearse o interactuar con sistemas aislados. |

```python
class Pedido(Model):
    _table = "pedidos"

    @before_insert
    async def validar_pedido(self): ...

    @before_commit
    async def auditar(self, accion: str): ...

    @after_commit
    async def notificar_externo(self): ...
```

> **Validación integrada:** `validate()` (sección 3.2.7) se ejecuta automáticamente al inicio de `before_insert` y `before_update`. Si devuelve un diccionario de errores (no `None`), la operación se **aborta** con `ValidationError` antes de tocar la base de datos.

#### 3.5.1. Ubicación en la transacción y manejo de fallos

- `before_commit` se ejecuta **dentro** del `transaction()` de `Db`: corre antes del `commit` y cualquier `Exception` que lance desencadena `rollback()`.
- `after_commit` se ejecuta **fuera** de `transaction()`, después del commit. Al interactuar con sistemas aislados (externos) puede bloquearse; por ello no debe formar parte de la transacción de la BD.
- Dado que puede haber **más de una acción** pendiente, `before_commit`/`after_commit` deben **acumularse** y ejecutarse en el mismo orden en que se registraron.
- Se sugiere agregar hooks adicionales para escenarios de fallo y transacciones anidadas:

| Decorador sugerido | Uso |
|--------------------|-----|
| `@after_transaction_fail` | Lógica al fallar la transacción (compensación). |
| `@post_commit_fail` | Lógica de transacciones anidadas para elementos externos tras un fallo posterior al commit. |

### 3.6. Constructor de Consultas (`Filter` y `QueryBuilder`)

#### 3.6.1. Clase `Filter`

Se introduce una clase `Filter` que enriquece al modelo, usada tanto en las operaciones de filtrado (`search`) como en el `QueryBuilder`. Reemplaza la representación cruda de listas por un objeto tipado, componible y validable.

```python
class Filter:
    def __init__(self, *conditions): ...          # condiciones sueltas (unidas con AND)

    # operadores de comparación
    @staticmethod
    def eq(field, value) -> "Filter": ...         # field = value
    @staticmethod
    def ne(field, value) -> "Filter": ...         # field != value
    @staticmethod
    def gt(field, value) -> "Filter": ...         # field > value
    @staticmethod
    def lt(field, value) -> "Filter": ...         # field < value
    @staticmethod
    def ge(field, value) -> "Filter": ...         # field >= value
    @staticmethod
    def le(field, value) -> "Filter": ...         # field <= value
    @staticmethod
    def in_(field, values) -> "Filter": ...       # field IN (...)
    @staticmethod
    def between(field, lo, hi) -> "Filter": ...   # field BETWEEN lo AND hi
    @staticmethod
    def like(field, value) -> "Filter": ...       # field LIKE '%value%'
    @staticmethod
    def startswith(field, value) -> "Filter": ... # field LIKE 'value%'
    @staticmethod
    def endswith(field, value) -> "Filter": ...   # field LIKE '%value'
    @staticmethod
    def is_null(field) -> "Filter": ...           # field IS NULL
    @staticmethod
    def not_null(field) -> "Filter": ...          # field IS NOT NULL
    @staticmethod
    def raw(sql: str, params: list) -> "Filter": ...  # expresión SQL cruda (escape tipado)

    # agrupadores (componibles)
    def and_(self, other: "Filter") -> "Filter": ...
    def or_(self, other: "Filter") -> "Filter": ...
    def not_(self) -> "Filter": ...

    def __and__(self, other): ...                 # &  -> AND
    def __or__(self, other): ...                  # |  -> OR
    def __invert__(self): ...                     # ~  -> NOT

    def to_sql(self, alias: str | None = None) -> tuple[str, list]: ...
```

**Traducción a SQL (idéntica a la tabla de operadores original):**

| Operador | Construcción | Traducción SQL |
|----------|--------------|----------------|
| `=` | `Filter.eq("monto", 1000)` | `monto = 1000` |
| `!=` | `Filter.ne("monto", 1000)` | `monto <> 1000` |
| `>` | `Filter.gt("monto", 1000)` | `monto > 1000` |
| `<` | `Filter.lt("monto", 1000)` | `monto < 1000` |
| `>=` | `Filter.ge("monto", 1000)` | `monto >= 1000` |
| `<=` | `Filter.le("monto", 1000)` | `monto <= 1000` |
| `in` | `Filter.in_("monto", (1000,1001,1002))` | `monto IN (1000,1001,1002)` |
| `between` | `Filter.between("monto", 1000, 2000)` | `monto BETWEEN 1000 AND 2000` |
| `like` | `Filter.like("name", "López")` | `name LIKE '%López%'` |
| `startswith` | `Filter.startswith("name", "Ló")` | `name LIKE 'Ló%'` |
| `endswith` | `Filter.endswith("name", "pez")` | `name LIKE '%pez'` |
| `is null` | `Filter.is_null("region_id")` | `region_id IS NULL` |
| `is not null` | `Filter.not_null("region_id")` | `region_id IS NOT NULL` |
| `raw` | `Filter.raw("monto > %(p)s", [1000])` | expresión cruda con parámetros tipados |
| `or` | `Filter.gt("monto",1000).or_(Filter.gt("created_at","2026-01-01"))` | `(monto > 1000 OR created_at > '...')` |
| `and` | `Filter.gt("monto",1000) & Filter.gt("created_at","...")` | `(monto > 1000 AND ...)` — **agrupación predeterminada** |
| `not` | `~Filter.gt("monto", 1000)` | `NOT (monto > 1000)` |

```python
# uso en search
await Agente(db).search(Filter.eq("enabled", 1) & Filter.like("agente", "Héct"))
```

#### 3.6.2. `QueryBuilder` con alias y `join`

Se amplía la infraestructura de `encinorm` con un constructor de consultas independiente que soporte `join`, `exists` y **funciones de agregado** (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY`, `HAVING`).

**Alias:** el modelo que inicia la construcción del query recibe el alias **`mm`** (*main model*) de forma predeterminada, configurable por parámetro. Cada modelo referenciado en un `join` recibe un alias propio, de modo que los campos puedan vincularse sin ambigüedad (`mm.region_id = r.id`).

```python
from encinorm import Db

class QueryBuilder:
    def __init__(self, model_class: type["Model"], alias: str = "mm"):
        self._aliases: set[str] = {alias}            # registro de alias de tabla/subquery
        self._column_aliases: dict[str, str] = {}    # alias_columna -> expr (unicidad)

    def select(self, *columns): ...                  # acepta "mm.agente" o "mm.agente AS nombre"
    def join(self, other, alias: str, on: "Filter"): ...     # join con OTRO modelo (distinto)
    def join_subquery(self, subquery: "QueryBuilder", alias: str | None, on: "Filter"): ...
    def where(self, filter: "Filter"): ...
    def group_by(self, *columns): ...
    def having(self, filter: "Filter"): ...
    def order_by(self, *columns): ...
    def limit(self, n: int, page: int = 1): ...
    def exists(self) -> bool: ...               # genera EXISTS(...)
    def count(self) -> int: ...                 # SELECT COUNT(*)
    def sum(self, column) -> int: ...
    async def all(self) -> list[dict]: ...
    async def first(self) -> dict | None: ...
```

**Alias de columna en `select`:** las columnas pueden aliasarse para evitar ambigüedad en el resultado:

```python
qb.join(Region, "r", Filter.eq("mm.region_id", "r.id")) \
  .select("mm.agente AS nombre", "r.region AS region_nombre")

rows = await qb.all()
# rows == [{"nombre": "...", "region_nombre": "..."}]
```

**Reglas del alias de columna:**

| Regla | Detalle |
|-------|---------|
| Sintaxis | `"expresión AS alias"` en `select`; el alias se convierte en la **clave** del `dict` resultante. |
| Unicidad | `_column_aliases` registra cada alias; un alias repetido lanza `DuplicateColumnAliasError`. |
| Alcance en `WHERE`/`ON` | El alias **no** es visible en `where` ni en `join ... on`; ahí se usan los nombres calificados (`mm.agente`). |
| Alcance en `ORDER BY`/`GROUP BY`/`HAVING` | El alias sí es visible en `ORDER BY` (garantizado); en `GROUP BY`/`HAVING` depende del motor (documentado por backend). |
| `*` | `select("mm.*")` expande todas las columnas y **no** admite alias individual. |
| `search()` | Los alias solo aplican a `QueryBuilder` (resultados `dict`); `search()` retorna `Model` y no acepta alias (o requiere mapeo explícito `alias → campo`). |

**`join` solo con modelos distintos:** `join(other, ...)` admite únicamente un `other` de clase distinta al modelo principal. Unir la **misma clase** en `join` lanza `DuplicateAliasError`; el self-join se resuelve con dos instancias (sección 3.6.3).

**Ejemplo de join con alias:**

```python
qb = QueryBuilder(Agente)                      # alias por defecto: mm
qb.join(Region, "r", Filter.eq("mm.region_id", "r.id")) \
  .select("mm.agente", "r.region") \
  .where(Filter.eq("r.enabled", 1))
```

La condición de join se expresa como un `Filter` donde los campos se califican con el alias del modelo (`mm.region_id = r.id`), evitando ambigüedad entre columnas homónimas de modelos distintos.

> **Decisión de diseño:** el `QueryBuilder` se construye **sobre** `Db` (enriqueciéndolo), no reemplazándolo. `Db` sigue siendo la interfaz de bajo nivel; `QueryBuilder` traduce operaciones de alto nivel a objetos `Query` nativos del motor.

#### 3.6.3. Self-join mediante dos instancias (subqueries)

No existe un *self-join* en `join()`. Para unir el modelo **consigo mismo** se crean **dos instancias** de `QueryBuilder` con el mismo modelo y se componen con `join_subquery`, evitando el riesgo de colisión de alias: cada instancia posee su propio `_aliases`.

```python
# self-join: un agente referencia a otro agente (jefe)
main = QueryBuilder(Agente)                     # alias por defecto: mm
sub  = QueryBuilder(Agente)                     # instancia independiente

main.join_subquery(sub, alias=None, on=Filter.eq("mm.jefe_id", "sq1_mm.id")) \
    .select("mm.agente", "sq1_mm.agente")
```

**Unicidad de alias:** cada `join`/`join_subquery` registra su alias en `_aliases`. Si el alias ya existe dentro del mismo query, se lanza `DuplicateAliasError` (la validación es por query, no global).

**Prefijo para subqueries:** si el motor de búsqueda lo requiere (o para evitar colisiones al anidar), las subqueries se nombran con prefijo `sq{índice}_{alias_base}`, por ejemplo `sq1_mm`, `sq2_mm`, … `sqn_mm`. El índice es secuencial dentro del query padre:

```python
main = QueryBuilder(Agente)                 # mm
main.join_subquery(QueryBuilder(Agente).where(Filter.eq("enabled", 1)), alias=None, on=...)
# alias autogenerado -> sq1_mm
main.join_subquery(QueryBuilder(Agente).where(Filter.eq("enabled", 0)), alias=None, on=...)
# alias autogenerado -> sq2_mm
```

**Reglas:**
- `join` admite solo modelos distintos; la misma clase se resuelve vía `join_subquery`.
- `join_subquery` recibe un `QueryBuilder` ya construido; si no se pasa alias, se genera `sq{idx}_{alias_base}`.
- La generación automática también respeta `_aliases` (si `sq1_mm` ya existe, se incrementa el índice).

**Semántica SQL:** para misma clase se emite *table alias* (`FROM agentes mm JOIN agentes sq1_mm ON ...`) en lugar de *derived table*, por rendimiento (usa índices y evita materialización, p. ej. en MySQL). Para subqueries de modelos distintos o con agregación, se emite `JOIN (SELECT ...) sqN_mm`.

### 3.7. Excepciones

Se amplía la jerarquía de `encinorm` con excepciones propias del ORM:

```python
class ModelError(EncinormError): ...
class FailOnUpdate(ModelError): ...          # update no completado
class ValidationError(ModelError): ...       # fallo en reglas de validación
class NotFoundError(ModelError): ...         # load sin resultado (opcional)
class RelationshipError(ModelError): ...     # referencia mal configurada
class DuplicateReferenceError(RelationshipError): ...  # referencia ya existe o colisiona con un campo
class DuplicateAliasError(ModelError): ...   # alias duplicado en un QueryBuilder (tabla/subquery)
class DuplicateColumnAliasError(ModelError): ...  # alias de columna duplicado en select
```

---

## 4. Arquitectura y Estructura de Carpetas

### 4.1. Componentes

- **`Db` (encinorm):** interfaz de bajo nivel ya existente (`base.py`, `sqlite.py`, `mysql.py`). Se agrega `postgresql.py` y, opcionalmente, `pool.py`.
- **`encinorm.model`:** capa ORM nueva que **consume** `Db` y expone `Model`, `CachedModel`, `Column`, `Filter`, hooks y `QueryBuilder`.
- Los modelos generan objetos `Query` de encinorm; la ejecución sigue delegándose a `Db`.

### 4.2. Estructura propuesta

```
encinorm/
├── encinorm/
│   ├── __init__.py            # Db, Query, SqliteDb, MysqlDb, excepciones (ya existente)
│   ├── base.py                # clase abstracta Db
│   ├── query.py               # clase Query (bajo nivel)
│   ├── sqlite.py              # SqliteDb
│   ├── mysql.py               # MysqlDb
│   ├── postgresql.py          # PostgresDb (pendiente en el repo)
│   ├── pool.py                # PoolDb (pendiente)
│   ├── exceptions.py          # jerarquía de excepciones
│   └── model/                 # NUEVO: módulo EncinoModel
│       ├── __init__.py        # Model, CachedModel, Column, Filter, hooks, QueryBuilder
│       ├── column.py          # marcador Column (datatype, name) vía Annotated
│       ├── types.py           # mapa datatype -> DDL por motor (str->TEXT/VARCHAR, etc.)
│       ├── model.py           # Model (base ORM)
│       ├── cached.py          # CachedModel
│       ├── cache_backend.py   # CacheBackend (Protocol) + RedisCacheBackend + MemoryCacheBackend
│       ├── filter.py          # clase Filter (operadores y agrupadores)
│       ├── references.py      # Reference + add_reference + integridad (on_delete)
│       ├── hooks.py           # decoradores before_*/after_*
│       ├── query_builder.py   # QueryBuilder (join entre modelos + join_subquery para self-join, exists, agregados)
│       └── exceptions.py      # ModelError, FailOnUpdate, DuplicateReferenceError, DuplicateAliasError, DuplicateColumnAliasError, etc.
├── tests/
│   ├── conftest.py            # fixtures: SqliteDb en memoria, modelos de ejemplo
│   ├── test_model.py
│   ├── test_cached_model.py
│   ├── test_filter.py
│   ├── test_column.py
│   ├── test_references.py
│   ├── test_validation.py
│   ├── test_hooks.py
│   └── test_query_builder.py
├── docs/
│   ├── 0-design.md              # encinorm (capa Db)
│   └── 1-model.md        # este documento
└── pyproject.toml             # agregar pydantic y cliente de caché
```

### 4.3. Dependencias nuevas (`pyproject.toml`)

```toml
[project]
dependencies = [
    "aiomysql>=0.3.2",
    "aiosqlite",
    "pydantic>=2.0",           # base de los modelos
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]
cache = ["redis>=5.0"]         # para CachedModel (u otro backend)
```

---

## 5. Ejemplos de Uso

### 5.1. CRUD básico

```python
import asyncio
from datetime import datetime
from encinorm import create_db
from encinorm.model import Model

class Agente(Model):
    _table = "agentes"
    id: int
    agente: str

async def main():
    db = await create_db("sqlite", database=":memory:")
    await db.migrate("agentes", Query(
        "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
        "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)", []))

    # Insert
    a = Agente(db, agente="Héctor")
    nuevo_id = await a.insert()

    # Load
    b = Agente(db, id=nuevo_id)
    b = await b.load()
    print(b.agente, b.__exists)   # "Héctor", True

    # Update
    b.agente = "Héctor M."
    await b.update()               # actualiza __dirties (agente) + updated_at

    # Delete lógico
    await b.delete()               # enabled = 0, __exists = False

    # Search
    resultados = await Agente(db).search(
        Filter.eq("enabled", 1) & Filter.like("agente", "Héct"),
        columns=["id", "agente"],
    )

    await db.close()

asyncio.run(main())
```

### 5.2. Relaciones

```python
class Region(Model):
    _table = "regiones"
    id: int
    region: str

class Agente(Model):
    _table = "agentes"
    id: int
    agente: str
    region_id: int

a = Agente(db, id=1, agente="x", region_id=10)
a.add_reference("region", Region, {"id": "region_id"})

region = await a["region"]     # carga Region(id=10) de forma perezosa
print(region.region)

a.region_id = 20               # al cambiar la llave, se reinicializa la referencia
region = await a["region"]     # ahora Region(id=20)
```

### 5.3. `CachedModel`

```python
class Cliente(CachedModel):
    _table = "clientes"
    id: int
    rfc: str

c = Cliente(db, rfc="XAXX010101000", cache=RedisCacheBackend(url="redis://localhost"))
c = await c.load(keys=["rfc"], duration=600)
# llave: sha1("clientes:[rfc=XAXX010101000]") -> TTL 600s en el CacheBackend inyectado
```

### 5.4. Hooks

```python
class Pedido(Model):
    _table = "pedidos"
    id: int
    total: float

    @before_insert
    async def validar_total(self):
        if self.total <= 0:
            raise ValidationError("total debe ser mayor a 0")

    @before_commit
    async def auditar(self):
        # dentro de transaction(): una excepción aquí provoca rollback
        ...

    @after_commit
    async def enviar_notificacion(self):
        # fuera de transaction(): interactúa con sistemas externos (cola)
        await cola.push({"pedido_id": self.id})
```

### 5.5. `QueryBuilder`

```python
qb = QueryBuilder(Agente)                       # alias por defecto: mm
qb.join(Region, "r", Filter.eq("mm.region_id", "r.id")) \
  .select("mm.agente", "r.region") \
  .where(Filter.eq("r.enabled", 1)) \
  .order_by("mm.agente") \
  .limit(10, page=1)

filas = await qb.all()
total = await QueryBuilder(Agente).where(Filter.eq("enabled", 1)).count()
```

---

## 6. Estrategia de Testing

- `pytest` + `pytest-asyncio` (ya configurado en `pyproject.toml`).
- SQLite en memoria (`:memory:`) para las pruebas generales del ORM.
- Fixtures en `conftest.py`: conexión, creación de tablas de ejemplo y modelos.
- Pruebas por módulo: CRUD, estado interno (`__exists`, `__dirties`), filtros, referencias, caché (con un backend fake), hooks y `QueryBuilder`.
- Se debe verificar:
  - `insert` devuelve el `id` y marca `__exists`.
  - `update` respeta `__dirties` y excluye `id`/`created_at`/relaciones.
  - `delete` es lógico (`enabled=0`).
  - `Filter` (`eq`, `ne`, `gt`, `lt`, `in_`, `between`, `like`, `startswith`, `endswith`, `is_null`, `not_null`, `raw`, `and`, `or`, `not`) genera el SQL esperado.
  - `a["region"]` carga perezosamente y `add_reference` lanza `DuplicateReferenceError` ante colisiones.
  - `QueryBuilder` valida alias únicos (`DuplicateAliasError` para tabla/subquery, `DuplicateColumnAliasError` para columnas) y genera prefijos `sq{idx}_mm` para subqueries (self-join vía dos instancias).
  - `validate()` devuelve `None` con datos correctos y un `dict` de errores por columna cuando no; y aborta `insert`/`update` con `ValidationError`.
  - `CachedModel` respeta TTL y formato de llave sha1.
  - Los hooks se ejecutan en orden y ante fallos.

---

## 7. Análisis de viabilidad e inconsistencias

Revisión de los puntos solicitados, con los riesgos y ambigüedades detectados.

### 7.1. Excluir `Master` — **Viable, sin impacto**

- No existe dependencia estructural sobre `Master`; el "detalle maestro" puede reimplementarse más adelante mediante `add_reference` con relación *one-to-many*.
- **Inconsistencia resuelta:** se eliminaron las referencias a `Master` de los objetivos (punto 6), de la estructura de carpetas (`master.py`, `test_master.py`) y de la lista de componentes (sección 4.1).

### 7.2. Clase `Filter` — **Viable, mejora el diseño**

- Centraliza operadores y agrupadores en un solo tipo, reutilizable en `search` y `QueryBuilder`, y permite validar condiciones antes de construir SQL.
- **Ambigüedad resuelta:** la firma de `search` cambia de `filter: list[list]` a `filter: Filter | None`. La tabla de operadores se mantiene como **equivalente** (`Filter.eq(...)`), no se pierde semántica.
- **Inconsistencia a vigilar:** el operador `in` se reserva la palabra clave de Python, por lo que se expone como `Filter.in_` (con guion bajo). Los aliases `&`/`|`/`~` deben respetar precedencia de Python (mayor que `==`), lo que obliga a documentar uso de paréntesis.

### 7.3. Alias en `join` (`mm` / `r`) — **Viable, necesario para joins múltiples**

- El alias por defecto `mm` (configurable en `QueryBuilder(alias=...)`) elimina ambigüedad entre el modelo principal y los referenciados.
- **Inconsistencia detectada:** el documento previo usaba `on: dict` para la condición de join; ahora se unifica con `Filter`. La expresión `mm.region_id = r.id` debe representarse como `Filter.eq("mm.region_id", "r.id")` (los identificadores calificados son **cadenas**, no objetos), porque no hay símbolos Python reales para `mm`/`r`.
- **Riesgo resuelto:** el *self-join* se eliminó de `join()`; unir el modelo consigo mismo se hace con **dos instancias** vía `join_subquery`, por lo que el alias deja de ser ambiguo (cada instancia posee su propio `_aliases` y el prefijo `sq{idx}_mm` evita colisión).

### 7.4. Excluir 3.5.1 (propiedad automática) en favor de `add_reference` — **Viable**

- El mecanismo de propiedad automática queda redundante: `add_reference` + acceso por índice cubre el mismo caso con más flexibilidad.
- **Inconsistencia resuelta:** la sección se eliminó y se reenumeró el resto (3.4.x Relaciones, 3.5 Hooks, 3.6 Filter/QueryBuilder, 3.7 Excepciones).

### 7.5. Excepción por referencia duplicada / colisión de nombre — **Viable**

- Se agrega `DuplicateReferenceError` (subclase de `RelationshipError`).
- **Ambigüedad detectada:** la colisión puede darse contra (a) otra referencia ya registrada, o (b) un campo/columna del modelo. Ambas se rechazan en `add_reference`; falta definir si también se valida colisión contra **métodos/propiedades** de `Model` (ej. `load`, `insert`, `delete`), que de igual forma romperían la resolución de atributos.

### 7.6. Inconsistencias transversales detectadas

| # | Inconsistencia | Resolución propuesta |
|---|----------------|----------------------|
| 1 | `search`/`QueryBuilder` usaban `list[list]`; ahora `Filter`. | Mantener `Filter` como única API pública; aceptar listas solo como compatibilidad interna si se requiere. |
| 2 | Alias de join expresado como string `mm.region_id = r.id` no es Python válido. | Representar condiciones de join/where con `Filter.eq("mm.region_id", "r.id")`. |

---

## 8. Decisiones de diseño (resoluciones)

| # | Pregunta | Decisión |
|---|----------|----------|
| 1 | Tablas existentes que no siguen el patrón | Soportar ambos: `Column(name=...)` por columna y desactivación de campos heredados (`_fields_disabled`). |
| 2 | `update` con `data` vacío / sin llave | Marcar error (`FailOnUpdate`); las asignaciones deben ser explícitas, sin especular sobre la BD. |
| 3 | Backend de caché | Inyectable mediante la interfaz `CacheBackend` (Redis, Memcached, dict en memoria). |
| 4 | Integridad referencial | Borrado en cascada e integridad referencial **opcionales** vía `on_delete` en `add_reference`. |
| 5 | Ubicación de los hooks | `before_commit` dentro de `transaction()` (puede provocar `rollback`); `after_commit` fuera de `transaction()`. |
