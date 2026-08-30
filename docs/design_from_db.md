# Documento de Diseño — generación de modelos desde la base de datos

Helper que, a partir de una conexión establecida, **(A)** expone un vocabulario de
tipos de dato genéricos reutilizables en un archivo independiente, **(B)** lee las
tablas (y sus columnas) de la base de datos con filtros y paginación, y **(C)**
genera el archivo Python con el `Model` correspondiente a una tabla. La pieza
central es el **mapeo inverso de tipos**: si el tipo de la columna coincide con un
preset del vocabulario se usa ese preset; si **no** está en el conjunto, el modelo
aplica un `make_constraint(...)` directo al campo.

> Complementa `docs/design_model.md` (ORM), `docs/design_constraint.md`
> (`Constraint`/`make_constraint`). Se apoya en `prompts/analisys-05.md`. No
> modifica `Db` ni `Constraint`; es la **contraparte inversa** de `to_ddl()`.

---

## 1. Contexto y Objetivos

El flujo *forward* (`Model → to_ddl → migrate`) ya existe. Falta el **flujo
inverso** (*database-first*): dado un esquema existente (p. ej. una base legacy),
descubrir sus tablas y generar modelos editables, en lugar de escribirlos a mano.

| # | Objetivo |
|---|----------|
| 1 | Vocabulario de **tipos genéricos** reutilizables (`STR_100`, `INT_POS`, `CURRENCY`, `FLOAT`, `DATETIME`, …) en un archivo independiente. |
| 2 | **Listar tablas** de la BD (con filtro por nombre y paginación). |
| 3 | **Leer columnas** de una tabla (nombre, tipo, `nullable`, PK). |
| 4 | **Generar** el archivo `.py` con el `Model` de una tabla (folder como parámetro). |
| 5 | Mapeo de tipos: **preset del vocabulario si existe**, si no **`make_constraint(...)`** al campo. |
| 6 | No modificar `Db` ni `Constraint`; operar por `db.dialect` con funciones standalone. |

---

## 2. Veredicto del análisis

Ver `prompts/analisys-05.md`. Resumen:

- **(A) Vocabulario de tipos** — viable, alto valor, bajo riesgo: es instanciar
  `make_constraint` con presets en un módulo nuevo.
- **(B) Introspección** — viable, valor medio-alto: hoy no existe una API pública
  para listar tablas/columnas (solo `Model._existing_columns`, privado y acoplado).
- **(C) Codegen** — viable como *scaffolding* (no migración inversa); el mapeo de
  tipos es *lossy* y tiene casos ambiguos (`TINYINT(1)`, `VARCHAR(n)`, `DECIMAL`).
- **No modificar `Db`**: la introspección se implementa como funciones standalone
  que consultan el catálogo según `db.dialect` (consistente con `http`/`security`).

---

## 3. Arquitectura y ubicación

```
encinorm/
├── encinorm/
│   ├── model/
│   │   ├── ...                       # Model, Constraint, types (existente)
│   │   └── domain.py                 # NUEVO: vocabulario de tipos genéricos
│   └── introspection/                # NUEVO (subpaquete opcional)
│       ├── __init__.py               # list_tables, columns_of, generate_model
│       ├── tables.py                 # list_tables + columns_of (SQL por motor)
│       ├── types.py                  # mapa inverso + resolve_field_type
│       └── codegen.py                # generate_model (emite el archivo .py)
└── docs/
    └── design_from_db.md             # este documento
```

- `encinorm.model.domain` solo importa de `encinorm.model.constraint`; **nunca al
  revés**. `encinorm.introspection` importa de `encinorm.model` y `encinorm.query`.
- Sin dependencias nuevas (stdlib `pathlib`/`json` + `Query`/`Db` ya existentes).

---

## 4. Vocabulario de tipos genéricos (`domain.py`)

Conjunto de **uso común** definido con `make_constraint`. Son el conjunto contra el
que se compara cada columna durante el codegen (sección 6):

```python
# encinorm/model/domain.py (concepto)
from datetime import date, datetime

from encinorm.model import make_constraint


def _coerce_datetime(v):
    """Acepta `datetime` o string ISO; devuelve `datetime` (normaliza)."""
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    raise ValueError("datetime inválido")


STR_10         = make_constraint(str, max_length=10)
STR_15         = make_constraint(str, max_length=15)
STR_20         = make_constraint(str, max_length=20)
STR_30         = make_constraint(str, max_length=30)
STR_50         = make_constraint(str, max_length=50)
STR_100        = make_constraint(str, max_length=100)
STR_255        = make_constraint(str, max_length=255)
STR_500        = make_constraint(str, max_length=500)
TEXT           = make_constraint(str)                       # sin límite de longitud
INT            = make_constraint(int)
INT_POS        = make_constraint(int, ge=0)                 # no negativo
CURRENCY       = make_constraint(float, ge=0)               # datatype "numeric"
FLOAT          = make_constraint(float, datatype="float")
FLOAT_POS      = make_constraint(float, datatype="float", ge=0)
BOOL           = make_constraint(bool)
DATE           = make_constraint(date)
DATETIME       = make_constraint(datetime, validators=(_coerce_datetime,))
BLOB           = make_constraint(bytes)                     # datatype "blob"
```

| Preset | Tipo Python | datatype lógico | Restricción |
|--------|-------------|-----------------|-------------|
| `STR_10` / `STR_15` / `STR_20` / `STR_30` / `STR_50` / `STR_100` / `STR_255` / `STR_500` | `str \| None` | `str` | `max_length` |
| `TEXT` | `str \| None` | `str` | sin límite |
| `INT` / `INT_POS` | `int \| None` | `int` | `ge=0` (`INT_POS`) |
| `CURRENCY` | `float \| None` | `numeric` | `ge=0` |
| `FLOAT` / `FLOAT_POS` | `float \| None` | `float` | `ge=0` (`FLOAT_POS`) |
| `BOOL` | `bool \| None` | `bool` | — |
| `DATE` | `date \| None` | `date` | — |
| `DATETIME` | `datetime \| None` | `datetime` | `AfterValidator(_coerce_datetime)` |
| `BLOB` | `bytes \| None` | `blob` | — |

- Todos son **opcionales** (`required=False`): la obligatoriedad se decide por
  `nullable` de la columna (`required=True` si `NOT NULL`).
- `CURRENCY` usa `float` (no `Decimal`): `_serialize()` no convierte `Decimal` y
  SQLite no lo adapta (ver decisión 1).

---

## 5. Introspección (`tables.py`)

### 5.1. `list_tables`

Lista las tablas del catálogo con **filtro por nombre** y **paginación**:

```python
# encinorm/introspection/tables.py (concepto)
from encinorm.model import Records
from encinorm.query import Query

async def list_tables(db, *, name: str = "", limit: int = 50, page: int = 1) -> Records:
    base, params = _tables_query(db.dialect)          # SELECT ... FROM <catálogo>
    if name:
        base += " WHERE name LIKE {0}"                # filtro por patrón
        params.append(f"%{name}%")
    total = (await db.fetch_one(Query(f"SELECT COUNT(*) FROM ({base})", params)))["COUNT(*)"]
    offset = (page - 1) * limit
    rows = await db.fetch_many(Query(base + f" LIMIT {limit} OFFSET {offset}", params), limit, page)
    return Records(rows=rows, total=total, limit=limit, page=page)
```

SQL de catálogo por motor (se excluyen las tablas internas):

| Motor | Consulta |
|-------|----------|
| SQLite | `SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name <> '_encinorm_migrations'` |
| MySQL | `SELECT table_name AS name FROM information_schema.tables WHERE table_schema = DATABASE()` |
| PostgreSQL | `SELECT tablename AS name FROM pg_catalog.pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')` |

### 5.2. `columns_of`

Devuelve la especificación de columnas de una tabla (nombre, tipo crudo, `nullable`,
PK). Extrae y generaliza la lógica hoy privada de `Model._existing_columns`:

```python
async def columns_of(db, table: str) -> list[ColumnSpec]:
    ...
# ColumnSpec: dataclass(name, raw_type, datatype, nullable, primary_key, max_length)
```

| Motor | Consulta de columnas |
|-------|----------------------|
| SQLite | `PRAGMA table_info({table})` → `name`, `type`, `notnull`, `pk` |
| MySQL | `SHOW COLUMNS FROM {table}` → `Field`, `Type`, `Null`, `Key` |
| PostgreSQL | `information_schema.columns` → `column_name`, `data_type`, `is_nullable`, `column_default` |

---

## 6. Mapeo de tipos y codegen

### 6.1. Normalización DB → datatype lógico

El tipo crudo de la BD se normaliza a un `datatype` lógico (`str/int/bool/numeric/
datetime/date/blob`) + atributos (`max_length`, `unsigned`, `precision`):

| SQLite | MySQL | PostgreSQL | datatype | atributos |
|--------|-------|-----------|----------|-----------|
| `TEXT` | `VARCHAR(n)` / `CHAR(n)` / `TEXT` | `varchar(n)` / `text` | `str` | `max_length=n` |
| `INTEGER` | `INT` / `BIGINT` / `SMALLINT` / `TINYINT` | `integer` / `bigint` / `smallint` | `int` | `unsigned?` |
| `INTEGER`/`BOOLEAN` | `TINYINT(1)` | `boolean` | `bool` | — (ambiguo, ver decisión 4) |
| `REAL` | `FLOAT` / `DOUBLE` | `real` / `double precision` | `float` | — |
| — | `DECIMAL(p,s)` | `numeric` | `numeric` | `precision` |
| (ISO en `TEXT`) / `DATETIME` | `DATETIME` / `TIMESTAMP` | `timestamp` | `datetime` | — |
| (ISO en `TEXT`) / `DATE` | `DATE` | `date` | `date` | — |
| `BLOB` | `BLOB` | `bytea` | `blob` | — |

### 6.2. `resolve_field_type` — preset si existe, si no `make_constraint`

Regla central: **si el tipo coincide con un preset del vocabulario se referencia el
preset; si no, se emite un `make_constraint(...)`** para ese campo:

```python
# encinorm/introspection/types.py (concepto)
_PRESET = {
    ("str", 10):  "STR_10",
    ("str", 15):  "STR_15",
    ("str", 20):  "STR_20",
    ("str", 30):  "STR_30",
    ("str", 50):  "STR_50",
    ("str", 100): "STR_100",
    ("str", 255): "STR_255",
    ("str", 500): "STR_500",
    ("str", None): "TEXT",
    ("int", "pos"): "INT_POS",
    ("int", None):  "INT",
    ("float", "pos"): "FLOAT_POS",
    ("float", None):  "FLOAT",
    ("bool", None): "BOOL",
    ("numeric", None): "CURRENCY",
    ("datetime", None): "DATETIME",
    ("date", None): "DATE",
    ("blob", None): "BLOB",
}

def resolve_field_type(col: ColumnSpec) -> str:
    """Devuelve la expresión Python que tipa el campo."""
    key = _preset_key(col)                     # (datatype, atributo discriminante)
    if key in _PRESET:
        return _PRESET[key]                     # p. ej. "STR_50"
    # fallback: tipo no contemplado -> make_constraint explícito
    return _make_constraint_expr(col)           # p. ej. "make_constraint(str, max_length=123)"
```

Casos de fallback (el tipo **no** está en el conjunto):

```python
# VARCHAR(123): longitud no coincide con ningún preset (10/15/20/30/50/100/255/500)
"make_constraint(str, max_length=123)"
# numeric con precisión no estándar
"make_constraint(float, ge=0, le=99999999)"
# tipo no reconocido -> str por defecto
"make_constraint(str)"
```

### 6.3. `generate_model` — emite el archivo `.py`

```python
# encinorm/introspection/codegen.py (concepto)
from pathlib import Path

def generate_model(db, table: str, *, folder: str, class_name: str | None = None) -> Path:
    """Genera `folder/<archivo>.py` con el `Model` de la tabla."""
    cols = await columns_of(db, table)
    cls = class_name or _class_name(table)      # "agentes" -> "Agentes" (editable)
    lines = [
        "from encinorm.model import Model, make_constraint",
        "from encinorm.model.domain import (STR_10, STR_15, STR_20, STR_30, "
        "    STR_50, STR_100, STR_255, STR_500, TEXT, INT, INT_POS, CURRENCY, "
        "    FLOAT, FLOAT_POS, BOOL, DATE, DATETIME, BLOB)",
        "",
        f"class {cls}(Model):",
        f'    _table = "{table}"',
    ]
    if not _has_inherited(cols):                # tabla sin enabled/created_at/updated_at
        lines.append('    _fields_disabled = ["enabled", "created_at", "updated_at"]')
    for c in cols:
        if _is_inherited_id(c):                 # PK autoincremental "id" -> implícito
            continue
        fname = _field_name(c.name)             # sanitiza + resuelve colisiones
        type_expr = resolve_field_type(c)       # preset o make_constraint
        req = "required=True" if not c.nullable else ""
        name_arg = f', name="{c.name}"' if fname != c.name else ""
        lines.append(f"    {fname}: {type_expr}({req}{name_arg})")
    path = Path(folder) / f"{_snake(cls)}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
```

### 6.4. Ejemplo de salida

Dada la tabla `agentes(id INTEGER PK, agente VARCHAR(50) NOT NULL, rfc VARCHAR(13),
monto DECIMAL(10,2), creado_en DATETIME)`:

```python
from encinorm.model import Model, make_constraint
from encinorm.model.domain import (STR_10, STR_15, STR_20, STR_30, STR_50,
    STR_100, STR_255, STR_500, TEXT, INT, INT_POS, CURRENCY, FLOAT, FLOAT_POS,
    BOOL, DATE, DATETIME, BLOB)

class Agentes(Model):
    _table = "agentes"
    _fields_disabled = ["enabled", "created_at", "updated_at"]
    agente: STR_50(required=True)
    rfc: make_constraint(str, max_length=13)        # longitud no está en el vocabulario
    monto: CURRENCY()
    creado_en: DATETIME(name="creado_en")
```

Notas del ejemplo:

- `agente` usa `STR_50` (está en el conjunto); `rfc` cae al **fallback**
  `make_constraint(str, max_length=13)` (longitud no contemplada).
- `creado_en` mapea a `DATETIME` pero su nombre de columna difiere del
  atributo (snake_case) → se conserva con `name="creado_en"`.
- La tabla no tiene `enabled`/`created_at`/`updated_at` → `_fields_disabled`.

---

## 7. Dependencias

Ninguna adicional: usa `Query`/`Db` (existente) y stdlib (`pathlib`, `json`). El
subpaquete `introspection` es parte del núcleo (no opcional).

---

## 8. Estrategia de testing

- `pytest` + `pytest-asyncio` contra SQLite `:memory:`.
- Casos:
  - `domain.py`: los presets generan el `Annotated`/DDL esperado (`STR_50` →
    `max_length`, `CURRENCY` → `numeric`, `DATETIME` coacciona string ISO).
  - `list_tables`: lista tablas, excluye internas, filtra por nombre y pagina.
  - `columns_of`: devuelve nombre/tipo/`nullable`/PK correctos.
  - `resolve_field_type`: coincide con preset (p. ej. `VARCHAR(50)` → `STR_50`) y
    produce fallback (`VARCHAR(13)` → `make_constraint(str, max_length=13)`).
  - `generate_model`: crea el archivo, se **importa** y el `Model` hace
    `insert`/`search` sobre la tabla real (round-trip básico).
  - `_fields_disabled` y `Column(name=...)`/colisiones de nombres.

---

## 9. Fases de implementación

| Fase | Alcance |
|------|---------|
| 1 | `model/domain.py`: presets + reexport desde `encinorm.model`. |
| 2 | `introspection/tables.py`: `list_tables` + `columns_of` por motor. |
| 3 | `introspection/types.py`: normalización + `resolve_field_type` (preset/fallback). |
| 4 | `introspection/codegen.py`: `generate_model` + sanitización de nombres. |
| 5 | Tests end-to-end (round-trip generar → importar → CRUD). |

---

## 10. Decisiones / ambigüedades

| # | Punto | Decisión |
|---|-------|----------|
| 1 | `CURRENCY` → `Decimal` vs `float` | **`float`** (`numeric`). `Decimal` no lo serializa `_serialize()` y SQLite falla. |
| 2 | Nomenclatura | Con guion bajo: `STR_100`, `INT_POS`, `CURRENCY`, `FLOAT`, `DATETIME`. |
| 3 | `DATETIME` | `datetime` + `AfterValidator` que acepta string ISO y normaliza. |
| 4 | `TINYINT(1)` (MySQL) | Ambigüedad bool/int: se mapea a `BOOL` por defecto, con override manual. |
| 5 | `DECIMAL(p,s)` / `VARCHAR(n)` no estándar | **Fallback** a `make_constraint(...)` con la precisión/longitud inferida. |
| 6 | Tipo no reconocido | Fallback a `make_constraint(str)` (conservador). |
| 7 | `id`/`enabled`/`created_at`/`updated_at` | Si existen como columnas, se heredan; si no, `_fields_disabled`. |
| 8 | Nombre de clase | `TitleCase` de la tabla + parámetro `class_name` para singularizar manualmente. |
| 9 | Nombres de columna inválidos/reservados | Sanitizar y mapear con `Column(name=...)`/`name=...` (mismo criterio que `security`). |
| 10 | Fidelidad | Es *scaffolding*: no reproduce índices, FKs, defaults ni collation. |
| 11 | Ubicación | Funciones standalone por `db.dialect`; **sin** tocar la interfaz `Db`. |
