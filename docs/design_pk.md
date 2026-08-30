# Documento de Diseño — Claves primarias (compuestas / naturales) en `load` y CRUD

Este documento analiza las recomendaciones **C** de `prompts/analisys-07.md` y
detalla el diseño de una **clave primaria configurable** (simple, natural o
**compuesta**) y de **claves foráneas compuestas**, que se utilicen de forma
coherente en `load`, `search`, `update`, `delete`, `save`, `upsert`, relaciones
y las capas REST/GraphQL.

> Complementa `docs/design_model.md`, `docs/design_crud.md` y
> `docs/design_missing.md`. Es **aditivo**: el comportamiento por defecto
> (clave `id` auto-incremental) no cambia.

---

## 1. Análisis de las recomendaciones C (analisys-07)

| # | Recomendación | Análisis / decisión |
|---|---------------|---------------------|
| C.6 | **PK compuestas** y/o `load` por clave natural genérica. | Es la pieza de mayor valor de C. Hoy el ORM asume `id` único en ~15 puntos. Se diseña en este documento. |
| C.7 | Observabilidad: OpenTelemetry + histogramas de latencia sobre `QueryTracer`. | Fuera del alcance de este documento; es aditivo y no interfiere con PK. Se documenta aparte (evolución de `encinorm/observability.py`). |
| C.8 | Revisar `validate()` para evitar el re-dump. | Independiente de PK; mejora puntual en `Model.validate`. No bloquea la PK. |
| C.9 | `Decimal` en SQLite (escalado entero o `TEXT` con coerción). | Independiente de PK; ya documentado como "Pendiente" en analisys-07 §4. |

**Conclusión:** de las recomendaciones C, la C.6 (clave primaria flexible) es la
que requiere un cambio de diseño estructural; C.7–C.9 son mejoras puntuales y
aditivas. Este documento detalla C.6.

---

## 2. Estado actual: puntos donde se asume `id`

| # | Ubicación | Asunción actual |
|---|-----------|-----------------|
| 1 | `Model` (clase) | `id: int \| None = None` está fijo en el modelo base. |
| 2 | `load()` / `save()` / `update()` / `delete()` | `_normalize_keys(keys, default=("id",))`. |
| 3 | `insert()` | omite el campo `id` y asigna `self.id = await db.last_id()`. |
| 4 | `insert_many()` / `upsert()` | excluyen `id` de las columnas. |
| 5 | `to_ddl()` (`types.py`) | `if field == "id":` → `table['pk']` (auto-incremento). |
| 6 | `sync_schema()` / `diff_schema()` | omiten `field == "id"`. |
| 7 | `_resolve_has_many()` / `batch_has_many()` | `getattr(self, "id")` (FK del hijo apunta al `id` del padre). |
| 8 | `http/routes.py` | ruta `/{id}` con `id: int` fijo. |
| 9 | `graphql/types.py` / `schema.py` | `strawberry.ID` y argumento `id` fijo. |
| 10 | `introspection/codegen.py` | `_INHERITED` incluye `id`; no emite PK desde la BD. |
| 11 | `_resolve_reference()` / `batch_reference()` | **ya** soportan `match_keys` multi-columna (1:1); `batch_reference` solo 1 llave. |

La clave primaria no está modelada como concepto; está implícita en el campo `id`.

---

## 3. Diseño propuesto

### 3.1. Declaración declarativa

Se añade un `ClassVar` al modelo base, con el nombre de **campo(s)** que forman
la clave primaria:

```python
class Model(BaseModel):
    _primary_key: ClassVar[tuple[str, ...]] = ("id",)   # default: surrogate actual
```

Semántica:

- `("id",)` → clave **auto-incremental** (comportamiento actual, sin cambios).
- `("code",)` → clave **natural simple** (sin auto-incremento; el usuario asigna).
- `("tenant_id", "code")` → clave **compuesta** (sin auto-incremento).

Los nombres son **lógicos** (de atributo) y se resuelven con `_col()` como el resto
de campos, respetando `Column.name`.

### 3.2. Helpers en `Model`

```python
@classmethod
def _pk_fields(cls) -> tuple[str, ...]:
    """Nombres de campo (lógicos) que forman la clave primaria."""
    return getattr(cls, "_primary_key", ("id",))

@classmethod
def _pk_cols(cls) -> tuple[str, ...]:
    """Columnas físicas de la clave primaria (respetando Column.name)."""
    return tuple(cls._col(f) for f in cls._pk_fields())

@classmethod
def _is_auto_pk(cls) -> bool:
    """True si la PK es el surrogate auto-incremental ``id``."""
    return cls._pk_fields() == ("id",)
```

### 3.3. Cambios en CRUD (`model/model.py`)

**`insert()`** — solo omite la clave si es auto-generada; en PK natural/compuesta
la clave se envía como cualquier otra columna:

```python
async def insert(self, *, ignore_duplicated=False, replace=False) -> int:
    ...
    auto = type(self)._is_auto_pk()
    data = {}
    for field, col in self._column_map().items():
        if auto and field == "id":
            continue
        data[col] = _serialize(getattr(self, field))

    new_id = await self._transactional("insert", do_insert)

    if auto:
        _set_private(self, "__loading", True)
        self.id = new_id
        _set_private(self, "__loading", False)
    _set_private(self, "__exists", True)
    _set_private(self, "__dirties", [])
    return new_id if auto else 0
```

- PK natural/compuesta: `new_id` no aplica; los campos PK ya están en `self`.
- Si un campo PK vale `None`, `validate()` (con `required=True` en la columna) lo
  rechaza antes de insertar.

**`load()` / `save()` / `update()` / `delete()`** — el default de `keys` pasa a ser
la clave primaria declarada:

```python
async def load(self, keys=None) -> "Model":
    keys = self._normalize_keys(keys, type(self)._pk_fields())
    ...

async def save(self, keys=None) -> int:
    keys = self._normalize_keys(keys, type(self)._pk_fields())
    ...

async def update(self, keys=None, data=None) -> int:
    keys = self._normalize_keys(keys, type(self)._pk_fields())
    ...

async def delete(self, keys=None, physical=False) -> bool:
    keys = self._normalize_keys(keys, type(self)._pk_fields())
    ...
```

- `_normalize_keys` ya acepta `"a,b"` (string) o tupla/lista, por lo que
  `load(keys="tenant_id,code")` y `load(keys=("tenant_id","code"))` funcionan sin
  cambios en esa función.
- `update()`/`delete()` validan que toda llave tenga valor (ya lo hace `update`);
  se replica la misma guarda en `delete()`.

**`upsert()`** — `conflict` pasa a ser opcional y su default es la clave primaria:

```python
async def upsert(self, conflict: list[str] | None = None, values=None) -> int:
    conflict = conflict or list(type(self)._pk_fields())
    ...
```

**`insert_many()`** — excluye `id` solo si es auto; incluye los campos PK
naturales/compuestos en las columnas:

```python
fields = [f for f in col_map if not (auto and f == "id")]
```

### 3.4. Relaciones

- **1:1 (`_resolve_reference`)** — ya usa `match_keys` (dict `{remoto: local}`) y
  llama a `load(keys=list(ref.match_keys.keys()))`, por lo que **soporta PK
  compuesta sin cambios**.
- **`batch_reference`** — se elimina la restricción de **una sola llave** y se
  implementa el caso compuesto (ver §3.10).
- **1:N (`_resolve_has_many` / `batch_has_many`)** — sustituir el `getattr(self, "id")`
  por la clave del padre, soportando **FK compuesta**:

```python
key = tuple(getattr(self, f) for f in hm.match_keys)   # simple o compuesta
```

  Las claves foráneas compuestas se detallan en §3.10.

### 3.5. Generación de DDL (`model/types.py`)

`to_ddl()` distingue tres casos:

```python
def to_ddl(model_class, engine="sqlite") -> str:
    pk_fields = model_class._pk_fields()
    auto = model_class._is_auto_pk()
    lines = []
    for field, col in model_class._column_map().items():
        if auto and field == "id":
            lines.append(f"  {col} {table['pk']}")     # AUTOINCREMENT/SERIAL
            continue
        dt = _field_datatype(model_class, field, model_class.model_fields[field])
        lines.append(f"  {col} {table[dt]}")

    if not auto:
        pk_cols = [model_class._col(f) for f in pk_fields]
        lines.append(f"  PRIMARY KEY ({', '.join(pk_cols)})")

    # ... FOREIGN KEY ... (sin cambios)
```

Resultados por caso:

| Caso | DDL |
|------|-----|
| `_primary_key = ("id",)` (default) | `id INTEGER PRIMARY KEY AUTOINCREMENT` / `INT AUTO_INCREMENT PRIMARY KEY` / `SERIAL PRIMARY KEY` (hoy). |
| `("code",)` | `code VARCHAR(255), PRIMARY KEY (code)` |
| `("tenant_id","code")` | `tenant_id INT, code VARCHAR(255), PRIMARY KEY (tenant_id, code)` |

- `_field_datatype` no requiere cambios: los campos PK naturales/compuestos usan
  su propio datatype (solo `id` auto usa `table['pk']`).
- El bloque `PRIMARY KEY (...)` se añade **antes** de las cláusulas `FOREIGN KEY`.

### 3.6. `sync_schema()` / `diff_schema()`

Sustituir `if field == "id": continue` por saltar únicamente la PK **auto**:

```python
if field == "id" and type(self)._is_auto_pk():
    continue
```

- Los campos PK naturales/compuestos se tratan como columnas normales en el diff.
- **Limitación:** si un campo PK falta en la BD, `ADD COLUMN` lo crea como columna
  simple (no como parte de la PK) — SQLite no puede alterar la PK sin recrear la
  tabla. Se documenta.

### 3.7. Capa REST (`http/routes.py`)

`get`/`put`/`delete` pasan de `{id}` fijo a parámetros derivados de la PK:

```python
pk_fields = model._primary_key

# simple
@router.get(prefix + "/{id}")                  # pk=("id",)
async def get(id: int, ...): ...

# compuesta
@router.get(prefix + "/{p1}/{p2}")             # pk=("tenant_id","code")
async def get(p1: int, p2: str, ...):
    obj = await _cursor(model, db, tenant_id=p1, code=p2).load()
```

- `create` devuelve `_cursor(model, db, **{f: getattr(obj, f) for f in pk_fields})`
  en lugar de `id=obj.id`.
- Implementación: el generador `register_crud` construye la ruta y los argumentos
  de path a partir de `model._primary_key` (con los tipos de `model_fields`).

### 3.8. Capa GraphQL (`graphql/types.py`, `schema.py`)

- `build_type` ya mapea `id` a `strawberry.ID`; para PK natural simple (ej. `code`)
  se mantiene el tipo del campo. Los campos PK compuestos se exponen como campos
  escalares normales (no hay cambio en el ObjectType).
- `_get_resolver` / `_update_resolver` / `_delete_resolver` generan sus argumentos
  desde `model._primary_key`:

```python
def _get_resolver(model, gtype):
    # simple: (id: ID)      compuesta: (tenantId: Int, code: String)
    async def resolver(info, **kwargs):
        keys = {f: kwargs[f] for f in model._primary_key}
        obj = await cursor(model, conn, **keys).load()
        ...
```

- La conversión `strawberry.ID`→`int` se conserva solo para `id`.

### 3.9. Introspección / codegen (`introspection/codegen.py`)

`columns_of()` **ya** devuelve `primary_key` por columna. En `generate_model`:

1. Detectar las columnas PK (`c.primary_key`).
2. Si la PK es exactamente `("id",)` → no emitir nada (hereda el default).
3. En otro caso, emitir `_primary_key = ("campo1", "campo2", ...)` usando
   `_field_name(c.name)` para mapear columnas→atributos, y marcar esos campos
   `required=True`.

Ejemplo de salida (tabla sin `id`):

```python
class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "code")

    tenant_id: int(required=True)
    code: STR_30(required=True)
    role: STR_50()
```

### 3.10. Claves foráneas compuestas

La PK compuesta exige que las **relaciones que la referencian** también sean
compuestas. Se generalizan `Reference.match_keys` y `HasMany.foreign_key` para
aceptar un mapeo de varias columnas.

#### 3.10.1. Representación

| Relación | Declaración | Forma del mapeo |
|----------|-------------|-----------------|
| 1:1 / FK (lado hijo) | `Reference.match_keys` | `dict` `{campo_remoto: campo_local}` — **ya soporta** varias columnas. |
| 1:N (colección inversa, lado padre) | `HasMany.foreign_key` | `str` (simple) **o** `dict` `{campo_padre: campo_hijo}` (compuesta). |

`Reference.match_keys` conserva su semántica actual (`{remoto: local}`), pero se
**valida** contra la `_primary_key` del modelo referenciado. `HasMany.foreign_key`
se amplía: un `str` se interpreta como `{padre._primary_key[0]: str}` (compatibilidad
con el `id` actual).

```python
# model/references.py (concepto)
@dataclass
class HasMany:
    name: str
    model_class: type
    foreign_key: str | dict             # str -> {pk[0]: str}; dict -> {padre: hijo}
    _cached: Any = field(default=None, init=False, repr=False)
    _cached_key: Any = field(default=None, init=False, repr=False)

    @property
    def match_keys(self) -> dict:       # {campo_padre: campo_hijo} normalizado
        if isinstance(self.foreign_key, str):
            return {self.model_class._pk_fields()[0]: self.foreign_key}
        return dict(self.foreign_key)
```

#### 3.10.2. Validación

Al registrar la relación (en `__init__` / `add_reference` / `add_has_many`):

- El conjunto de **claves remotas** debe coincidir con la `_primary_key` del modelo
  referenciado/padre: `set(match_keys.keys()) == set(referenced._pk_fields())`.
  - Para el default `("id",)`, `match_keys={"id": "region_id"}` sigue siendo válido
    (sin cambios para el código actual).
- El orden no importa (se compara como conjuntos), pero el DDL y las consultas
  iteran el dict respetando el orden de `_primary_key` para una salida determinista.

#### 3.10.3. Resolución 1:1 (`_resolve_reference`)

Sin cambios funcionales: ya itera `match_keys` y llama
`load(keys=list(ref.match_keys.keys()))`. Al validar que las claves remotas son la
PK del referenciado, la carga por clave compuesta es correcta.

#### 3.10.4. `batch_reference` multi-llave

Se elimina `if len(ref.match_keys) != 1: raise`. Para el caso compuesto:

- Se recogen los **pares** (tuplas) de claves locales presentes en la colección.
- Se construye un filtro **OR de ANDs** por par único:
  `(c1 = ? AND c2 = ?) OR (c1 = ? AND c2 = ?) ...`, o bien un `IN` por columna y
  cruce en Python. Se recomienda OR-de-ANDs (una sola consulta, portable entre
  motores).
- Se indexa el resultado por la tupla de claves remotas y se asigna el `_cached`
  de cada instancia.

```python
# encinorm/model/model.py (concepto)
@classmethod
async def batch_reference(cls, models, name):
    ref = models[0]._references.get(name)
    remote_fields = list(ref.match_keys.keys())
    local_fields = [ref.match_keys[r] for r in remote_fields]

    pairs = {
        tuple(getattr(m, lf) for lf in local_fields)
        for m in models
        if all(getattr(m, lf) is not None for lf in local_fields)
    }
    if not pairs:
        return

    cond = None
    for pair in pairs:
        sub = None
        for rf, val in zip(remote_fields, pair):
            eq = Filter.eq(rf, val)
            sub = eq if sub is None else sub & eq
        cond = sub if cond is None else cond | sub

    rows = await ref.model_class(db=models[0]._db).search(cond)
    index = {tuple(getattr(r, rf) for rf in remote_fields): r for r in rows}
    for m in models:
        key = tuple(getattr(m, lf) for lf in local_fields)
        if key in index:
            m._references[name]._cached = index[key]
            m._references[name]._cached_keys = dict(zip(remote_fields, key))
```

#### 3.10.5. Resolución 1:N (`_resolve_has_many` / `batch_has_many`)

Usan `hm.match_keys` (normalizado a `{campo_padre: campo_hijo}`):

```python
# encinorm/model/model.py (concepto)
async def _resolve_has_many(self, name) -> list:
    hm = self._has_many[name]
    key_vals = tuple(getattr(self, p) for p in hm.match_keys)
    if hm._cached is not None and hm._cached_key == key_vals:
        return hm._cached

    f = None
    for parent_f, child_f in hm.match_keys.items():
        eq = Filter.eq(child_f, getattr(self, parent_f))
        f = eq if f is None else f & eq
    cursor = hm.model_class.model_construct()
    _set_private(cursor, "_db", self._db)
    children = await cursor.search(f)
    hm._cached = children
    hm._cached_key = key_vals
    return children
```

`batch_has_many` aplica el mismo patrón OR-de-ANDs de §3.10.4 para agrupar hijos
por la tupla `(campo_hijo_1, campo_hijo_2, ...)`.

#### 3.10.6. DDL de FK compuesta

`to_ddl()` **ya** genera `FOREIGN KEY (local_cols) REFERENCES remote (remote_cols)`
a partir de `_references_def` con `on_delete`. Con `match_keys` de varias columnas,
emite la FK compuesta sin cambios adicionales:

```sql
FOREIGN KEY (tenant_id, user_id) REFERENCES memberships (tenant_id, user_id) ON DELETE CASCADE
```

- La restricción FK vive en el **hijo**; se declara vía `_references_def` /
  `add_reference`. `_has_many_def` solo añade la colección inversa (no genera FK).
- `on_delete` se soporta igual que hoy, también para FK compuestas.

#### 3.10.7. Ejemplo

```python
class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "user_id")
    tenant_id: int(required=True)
    user_id: int(required=True)
    role: STR_50()

class AuditLog(Model):
    _table = "audit_logs"
    tenant_id: int(required=True)
    user_id: int(required=True)
    detail: TEXT()
    _references_def = {
        "membership": {
            "model": Membership,
            "match_keys": {"tenant_id": "tenant_id", "user_id": "user_id"},
            "on_delete": "cascade",
        },
    }

# colección inversa en el padre (compuesta)
Membership._has_many_def = {
    "logs": {"model": AuditLog, "foreign_key": {"tenant_id": "tenant_id", "user_id": "user_id"}},
}

logs = await membership["logs"]   # WHERE tenant_id=.. AND user_id=..
```

---

## 4. Ejemplo de uso

```python
class Membership(Model):
    _table = "memberships"
    _primary_key = ("tenant_id", "code")

    tenant_id: int
    code: STR_30(required=True)
    role: STR_50()

m = Membership(db, tenant_id=7, code="admin", role="owner")
await m.insert()

# load por clave compuesta
got = await Membership(db, tenant_id=7, code="admin").load()
assert got._exists

# búsqueda/CRUD usan la PK por defecto
await m.update(data=["role"])        # WHERE tenant_id=7 AND code='admin'
await m.delete()                     # WHERE tenant_id=7 AND code='admin'

# claves explícitas (equivalente)
await Membership(db, tenant_id=7, code="admin").load(keys="tenant_id,code")
```

---

## 5. Resumen de cambios por archivo

| Archivo | Cambio |
|---------|--------|
| `model/model.py` | `_primary_key` + helpers `_pk_fields`/`_pk_cols`/`_is_auto_pk`; defaults en `load/save/update/delete/upsert`; `insert/insert_many` condicionales; `_resolve_has_many`/`batch_has_many` (FK simple/compuesta); `batch_reference` multi-llave; guarda de llaves en `delete`. |
| `model/types.py` | `to_ddl`: PK compuesta/natural → `PRIMARY KEY (...)`; FK compuesta (ya soportada en `_references_def`); `sync_schema`/`diff_schema` saltan solo PK auto. |
| `model/references.py` | `HasMany.foreign_key` acepta `str \| dict` + propiedad `match_keys` normalizada; validación de FK contra `_primary_key`. |
| `http/routes.py` | rutas/args de path derivados de `_primary_key`. |
| `graphql/types.py` / `schema.py` | argumentos de get/update/delete derivados de `_primary_key`. |
| `introspection/codegen.py` | emitir `_primary_key` desde las columnas PK introspectadas. |

---

## 6. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | Default | `_primary_key = ("id",)` → sin cambios para modelos existentes. |
| 2 | Auto-incremento | Solo cuando `_pk_fields() == ("id",)`. Cualquier otra PK es asignada por el usuario. |
| 3 | PK natural sin `id` | Permitido; `last_id()` no se invoca. Las referencias apuntan a la columna natural vía `match_keys`. |
| 4 | `batch_reference` compuesto | Soportado (OR-de-ANDs por par de claves, una consulta). |
| 5 | `has_many` con padre compuesto | Soportado: `foreign_key` acepta `dict` `{padre: hijo}`. |
| 6 | PK en REST | Ruta con un segmento por campo PK; `create` re-consulta usando `_primary_key`. |
| 7 | PK en GraphQL | Argumentos por campo PK; `ID` solo para `id`. |
| 8 | `sync_schema`/`diff_schema` con PK compuesta | Los campos PK se tratan como columnas; `ADD COLUMN` no puede marcarlas PK en SQLite (recrear tabla). |
| 9 | FK compuesta en DDL | Se declara en el hijo vía `_references_def` (con `on_delete`); `_has_many_def` solo añade la colección inversa. |
| 10 | Validación de FK | `set(match_keys.keys()) == set(referenciado._pk_fields())` al registrar la relación. |

---

## 7. Dependencias

- Ninguna dependencia nueva. Cambios internos en `Model`, `types`, `routes`,
  `schema`/`types` (GraphQL) y `codegen`.

---

## 8. Estrategia de testing

- **PK simple (default)**: regresión de la suite existente (333 tests) sin cambios.
- **PK natural simple**: `load/save/update/delete` por `code`; `to_ddl` emite
  `PRIMARY KEY (code)`; insert sin `id`.
- **PK compuesta**: `load` con tupla/string `"a,b"`; `update`/`delete` usan ambas
  columnas; `upsert` con `ON CONFLICT (a,b)`; `save` idempotente.
- **DDL por motor**: SQLite/MySQL/PostgreSQL para PK simple auto, natural y compuesta.
- **Relaciones**: referencia 1:1 con `match_keys` compuesto; `has_many` con padre PK
  simple natural y con **FK compuesta**; `batch_reference`/`batch_has_many` en una
  sola consulta (simple y compuesta).
- **FK compuesta**: DDL `FOREIGN KEY (a,b) REFERENCES p (a,b)`; resolución 1:1 y
  1:N; `on_delete`; validación de `match_keys` contra `_primary_key`.
- **REST**: rutas generadas para PK simple y compuesta; `create` re-consulta correcta.
- **GraphQL**: get/update/delete con argumentos simples y compuestos.
- **Codegen**: tabla sin `id` genera `_primary_key` y campos `required`.

---

## 9. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `_primary_key` + helpers; defaults en `load/save/update/delete`; `insert` condicional. |
| 2 | `to_ddl` con `PRIMARY KEY (...)`; `sync_schema`/`diff_schema`. |
| 3 | `upsert`/`insert_many` + relaciones (`has_many` con PK simple natural). |
| 4 | FK compuestas: `HasMany.foreign_key` `str\|dict` + `match_keys` validado + `batch_reference`/`batch_has_many` multi-llave. |
| 5 | REST + GraphQL derivados de `_primary_key`. |
| 6 | Codegen (introspecta PK compuesta/natural y FKs). |
