# Documento de Diseño — `has_many` filtrado (relaciones 1:N)

> Fecha: 2026-09-08 · Precedente: `prompts/analisys-14.md` y `prompts/27.md`.
> Estado actual: las relaciones 1:N se cargan **completas** por clave foránea;
> este documento diseña la **carga filtrada** (y paginada/ordenada) previa a la
> consulta, sin traer a memoria la colección entera.

---

## 1. Introducción y Objetivos

### Problema

```python
class Region(Model):
    _table = "regions"
    name: str | None = None
    _has_many_def = {"agents": {"model": Agent, "foreign_key": "region_id"}}

region = await Region(db, id=1).load()
agents = await region["agents"]           # list[Agent] por clave foránea
```

`region["agents"]` resuelve en `_resolve_has_many` (`encino_orm/model/model.py:353-370`),
que construye un `Filter` **sólo** con la clave foránea y ejecuta `search(f)`. Si una
región tiene 10,000 agentes, se materializan todos aunque sólo interese un subconjunto
(activos, un mes de pedidos, los que empiezan por "A"). El filtrado posterior ocurre en
Python, tarde y costoso.

### Objetivos

| # | Objetivo |
|---|----------|
| 1 | Acotar la consulta `has_many` **antes** de ejecutarla: `filter` previo a la carga. |
| 2 | Reutilizar `Filter` componible y `search()` (`limit`/`page`/`sort_by`) sin nuevo SQL. |
| 3 | Mantener la carga por lotes (`batch_has_many`) con filtro común, sin perder anti-N+1. |
| 4 | Cachear correctamente por **consulta** (no sólo por padre), con clave estable. |
| 5 | Retrocompatibilidad total: `region["agents"]` y `batch_has_many` sin filtro intactos. |

---

## 2. Estado actual

| Pieza | Ubicación | Comportamiento |
|-------|-----------|----------------|
| `__getitem__` | `model.py:335-338` | Enruta a `_resolve_has_many` / `_resolve_reference`. |
| `_resolve_has_many` | `model.py:353-370` | Carga **toda** la colección por FK; cachea en `_cached`. |
| `batch_has_many` | `model.py:961-1028` | Lote anti-N+1; también carga **todo** (sin filtro). |
| `HasMany` (descriptor) | `references.py:15-32` | Guarda `name`, `model_class`, `foreign_key` y caché. |
| `search(filter, limit, page, sort_by, ...)` | `model.py:704-734` | Ya soporta filtro + `LIMIT/OFFSET` + `ORDER BY`. |
| `Filter` (`&`, `|`, `~`) | `filter.py:31-217` | Árbol componible: `eq`, `between`, `like`, `startswith`, `endswith`, `in_`, … |

`search()` ya hace todo lo necesario; el único eslabón faltante es **exponer un filtro
desde la API de la relación**.

---

## 3. API propuesta

### 3.1. Método `has_many(...)` (recomendado)

Se añade un método de carga explícito, legible y extensible. **No** se sobrecarga
`__getitem__` para no cambiar la semántica simple de `region["agents"]`.

```python
async def has_many(
    self,
    name: str,
    *,
    filter: Filter | None = None,
    limit: int | None = None,
    page: int = 1,
    sort_by: list | None = None,
    include_deleted: bool = False,
) -> list:
    ...
```

Parámetros:

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `name` | `str` | Nombre de la relación registrada en `_has_many_def`. |
| `filter` | `Filter | None` | Filtro adicional; se combina con la FK vía `&`. |
| `limit` / `page` | `int` | Paginación (`LIMIT`/`OFFSET`), reenviados a `search()`. |
| `sort_by` | `list | None` | Orden, reenviado a `search()`. |
| `include_deleted` | `bool` | Si es `False` (default), se aplica el soft-delete `enabled=True`. |

Implementación de la resolución:

```python
async def _resolve_has_many(self, name, extra=None, limit=None, page=1,
                            sort_by=None, include_deleted=False) -> list:
    hm = self._has_many[name]
    f = None
    for parent_f, child_f in hm.match_keys.items():
        eq = Filter.eq(child_f, getattr(self, parent_f))
        f = eq if f is None else f & eq
    if extra is not None:
        f = extra if f is None else f & extra
    children = await cursor.search(f, limit=limit, page=page,
                                   sort_by=sort_by,
                                   include_deleted=include_deleted)
    # cacheo (ver §5)
    ...
    return children
```

> **Compatibilidad**: `region["agents"]` sigue siendo la forma corta que llama a
> `_resolve_has_many(name)` sin filtro (carga completa), preservando el comportamiento
> actual.

### 3.2. Alternativa descartada: tupla posicional en `__getitem__`

```python
region["agents", Filter.eq("enabled", True), 100]
```

Compacta, pero menos legible, rompe la semántica de `region["agents"]` y dificulta
ampliar la firma (p. ej. `sort_by`/`include_deleted`). Se desaconseja.

---

## 4. Ejemplos de uso

### 4.1. Subconjunto por condición

```python
from encino_orm.model import Filter

# sólo agentes activos de la región
activos = await region.has_many("agents", filter=Filter.eq("enabled", True))

# sólo agentes cuyo nombre empieza por "A"
a = await region.has_many("agents", filter=Filter.startswith("name", "A"))
```

### 4.2. Pedidos de un mes concreto (rango de fechas)

```python
from datetime import datetime

inicio = datetime(2026, 8, 1)
fin    = datetime(2026, 8, 31, 23, 59, 59)

pedidos_agosto = await region.has_many(
    "orders",
    filter=Filter.between("created_at", inicio, fin),
)
```

### 4.3. Paginación y orden

```python
# los 50 pedidos más recientes (página 1)
recientes = await region.has_many(
    "orders",
    filter=Filter.between("created_at", inicio, fin),
    limit=50,
    page=1,
    sort_by=["-created_at"],
)
```

### 4.4. Combinación de filtros (AND/OR)

```python
f = Filter.eq("enabled", True) & Filter.ge("monto", 1000)
filtrados = await region.has_many("orders", filter=f)
```

### 4.5. Forma corta sin filtro (retrocompatible)

```python
todos = await region["agents"]          # carga completa, como hasta ahora
```

---

## 5. Cacheo por clave-digest

### 5.1. Problema

El caché actual (`_cached`/`_cached_key`) se identifica sólo por las claves del padre;
al filtrar, la misma relación con dos filtros distintos devolvería el resultado
equivocado. La clave del caché debe identificar la **consulta completa**:
`claves del padre + filtro + limit/page/sort_by`.

### 5.2. Digest del filtro

Se sigue la convención ya usada por `CachedModel._cache_key`
(`encino_orm/model/cached.py:17-20`, `sha1(...).hexdigest()`):

```python
import hashlib

def _filter_digest(f: Filter) -> str:
    sql, params = f.to_sql()                 # fragmento SQL + params (determinista)
    raw = f"{sql}||{repr(params)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
```

Clave multi-entrada en `HasMany`:

```python
key = f"{key_vals}|{_filter_digest(filtro)}|{limit}|{page}|{repr(sort_by)}"
```

### 5.3. Notas de diseño

- **La precisión viene de la serialización canónica, no del digest.** `to_sql()`
  produce un `(fragmento, params)` determinista; `sha1` sólo lo compacta en una clave
  corta sin colisiones prácticas.
- **md5 vs sha**: para clave de caché (no adversarial) `md5` basta, pero se usa `sha1`
  para mantener un único criterio con `CachedModel` (o `sha256` si se prefiere margen).
- **Estructura**: `HasMany._cached` pasa de valor único a `dict[str, list]` claveado por
  digest; el caso sin filtro puede conservar su clave corta `key_vals`.
- **`batch_has_many`** escribe en la misma estructura multi-entrada.
- **Reutilizable**: la clave en cadena es estable, por lo que sirve si la relación se
  promueve al `CacheBackend` (Redis) sin rediseño.

### 5.4. Alternativa simple

No cachear las llamadas filtradas (sólo memoizar la carga completa sin filtro). Menos
eficiente en usos repetidos, pero sin migrar la estructura de `_cached`.

---

## 6. Carga por lotes (`batch_has_many`) con filtro común

Se añade `extra: Filter | None = None` para que una lista de padres cargue sólo los
hijos que cumplen el filtro común **en una** consulta:

```python
# FK simple
base = Filter.in_(child_field, list(parent_ids))
children = await cursor.search(base & extra if extra else base)
```

```python
# uso
regions = await Region(db).search()
await Region.batch_has_many(regions, "agents", extra=Filter.eq("enabled", True))
```

La FK compuesta aplica el mismo patrón OR-de-ANDs actual y suma `& extra`.

---

## 7. Consideraciones y riesgos

- **Soft-delete y `scope`**: al reutilizar `search()`, `_effective_filter` aplica
  `enabled=True` y el multi-tenant automáticamente; la relación filtrada hereda ese
  comportamiento (correcto).
- **FK compuesta**: la mezcla `fk & extra` funciona igual (bucle sobre `match_keys`).
- **Caché y `batch_has_many`**: hoy `batch_has_many` escribe `_cached` directamente;
  hay que migrarlo a la estructura multi-entrada sin romper la compatibilidad.
- **Retrocompatibilidad**: `region["agents"]` y `batch_has_many` sin `extra` deben
  comportarse idéntico.

---

## 8. Plan de pruebas

| # | Caso | Esperado |
|---|------|----------|
| 1 | `has_many("agents", filter=Filter.eq("enabled", True))` | Sólo los hijos que cumplen. |
| 2 | Filtro por rango de fechas ("pedidos de un mes"). | Sólo los del rango. |
| 3 | Combinación `fk & extra` (AND) sin mezclar resultados de otros padres. | Aislamiento correcto por FK. |
| 4 | `limit`/`page`/`sort_by` sobre la relación. | Paginación y orden correctos. |
| 5 | `batch_has_many(models, "agents", extra=...)`. | 1 consulta; grupos filtrados. |
| 6 | Misma relación con dos filtros distintos (caché por digest). | Resultados correctos e independientes. |
| 7 | Retrocompatibilidad: `region["agents"]` sin filtro. | Carga completa, como antes. |
| 8 | `startswith`/`endswith` en el filtro de la relación. | `LIKE 'A%'` / `LIKE '%ez'`. |

---

## 9. Fases de implementación

| Fase | Alcance | Criterio |
|------|---------|----------|
| **1** | `_resolve_has_many(extra, limit, page, sort_by, include_deleted)` + método `Model.has_many(...)`. | `region.has_many("agents", filter=...)` devuelve el subconjunto. |
| **2** | Caché multi-clave por digest en `HasMany`. | Dos filtros distintos → resultados correctos. |
| **3** | `batch_has_many(models, name, extra=...)`. | Lista de padres con hijos filtrados en 1 consulta. |
| **4** | Pruebas de §8 + documentación (`guide.md`, `CHANGELOG`). | Tests en verde + API documentada. |

---

## Conclusión

La carga filtrada de `has_many` es **viable y de bajo riesgo**: se reutilizan `Filter`
y `search()` existentes, se expone un método explícito `has_many(name, filter=...,
limit=..., page=..., sort_by=...)` y se extiende `batch_has_many` con un filtro común.
El cacheo pasa a una clave por digest (convención `CachedModel`) que identifica la
consulta completa. La API actual (`region["agents"]`) queda intacta.
