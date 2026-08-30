# Documento de Diseño — Constraint (declaración declarativa de columnas)

Propuesta para añadir una clase **`Constraint`** que permita declarar, de forma reutilizable, el tipo de dato y las restricciones de una columna, y que se traduzcan automáticamente a `pydantic.Field` y a `Column` (para el DDL). Complementa —no reemplaza— el diseño de `docs/design_model.md` (secciones 3.1 y 3.2.7).

---

## 1. Contexto y Objetivo

Actualmente la declaración de un campo requiere combinar manualmente `Annotated` + `Column` + `pydantic.Field`:

```python
agente: Annotated[str, Column(datatype="str")] = Field(min_length=3, max_length=50)
monto:  Annotated[float, Column(datatype="numeric")] = Field(ge=0, default=0)
```

Esto es verboso y obliga a repetir reglas en cada modelo. El objetivo de `Constraint` es:

| # | Objetivo |
|---|----------|
| 1 | Encapsular tipo de dato + restricciones en **un único objeto reutilizable**. |
| 2 | Permitir **restricciones nombradas** (`STR_100`, `INT_POS`) como vocabulario de dominio. |
| 3 | **Traducir** cada `Constraint` a `pydantic.Field` (validación) y a `Column` (DDL). |
| 4 | Integrarse con `validate()` (antes `not_valid`) sin un motor de validación paralelo. |

---

## 2. Análisis de viabilidad — ¿vale la pena extender el proyecto?

### Veredicto: **Sí, como capa de conveniencia** (azúcar sintáctico), **no** como motor de validación nuevo.

**A favor:**

1. **Elimina duplicación**: definir `STR_100` una vez y reutilizarlo en decenas de modelos.
2. **Centraliza reglas de dominio**: longitudes, rangos y obligatoriedad consistentes.
3. **Vocabulario de dominio**: `STR_100`, `INT_POS` documentan la intención.
4. **Un único punto de traducción**: de `Constraint` salen tanto `Field` (validación) como `Column` (DDL), sin duplicar fuentes de verdad.

**En contra / riesgos:**

1. **Complejidad de integración con pydantic v2**: requiere traducir `Constraint` a `Field` en la definición de clase (`__init_subclass__`) o implementar `__get_pydantic_core_schema__`.
2. **Riesgo de doble fuente de verdad**: si `Constraint` valida por su cuenta **además** de pydantic, ambas lógicas pueden divergir. Se evita haciendo que `Constraint` **solo traduzca** a `Field` y que `validate()` siga delegando en pydantic.
3. **Ambigüedad de nombres** (ver sección 5): `max` en `str` significa *longitud*, mientras que en `int`/`numeric` significa *valor*; y "positivo" vs `ge=0`.

**Conclusión:** extender vale la pena **solo** si `Constraint` es una capa fina sobre `Column` + `Field` con una única ruta de traducción. Si implicara un sistema de validación paralelo, **no** sería redituable.

---

## 3. Diseño propuesto

### 3.1. Clase `Constraint`

Especificación **inmutable** que agrupa tipo de dato, obligatoriedad, nombre de columna y reglas de validación:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class Constraint:
    datatype: str                    # int, bool, str, datetime, date, numeric, blob, float
    required: bool = False           # False -> campo opcional (None permitido)
    name: str | None = None          # nombre de columna en la BD (equivalente a Column.name)
    field_kwargs: dict = field(default_factory=dict)  # kwargs para pydantic.Field
    validators: tuple = ()           # funciones extra (equivalente a `constraint=func`)
```

### 3.2. Fábricas por tipo

```python
class Constraint:
    @classmethod
    def str(cls, min_length=None, max_length=None, pattern=None,
            required=False, name=None) -> "Constraint": ...

    @classmethod
    def int(cls, ge=None, gt=None, le=None, lt=None,
            required=False, name=None) -> "Constraint": ...

    @classmethod
    def numeric(cls, ge=None, gt=None, le=None, lt=None,
                required=False, name=None) -> "Constraint": ...

    @classmethod
    def bool(cls, required=False, name=None) -> "Constraint": ...

    @classmethod
    def datetime(cls, required=False, name=None) -> "Constraint": ...

    @classmethod
    def date(cls, required=False, name=None) -> "Constraint": ...

    @classmethod
    def blob(cls, required=False, name=None) -> "Constraint": ...
```

Cada fábrica rellena `datatype` y traduce sus argumentos a `field_kwargs` de pydantic:

| Fábrica | Parámetro | `field_kwargs` resultante |
|---------|-----------|---------------------------|
| `str` | `min_length` / `max_length` | `min_length` / `max_length` |
| `str` | `pattern` | `pattern` |
| `int`/`numeric` | `ge` / `gt` / `le` / `lt` | `ge` / `gt` / `le` / `lt` |

### 3.3. Traducción a `pydantic.Field`

```python
def to_field(self) -> pydantic.FieldInfo:
    default = ... if self.required else None   # obligatorio vs opcional
    return pydantic.Field(default=default, **self.field_kwargs)
```

- `required=True` → `Field(...)` (sin default; el campo es obligatorio).
- `required=False` → `Field(None)` (opcional; el tipo se vuelve `T | None`).

> `to_field`/`to_column` son los helpers que consume `make_constraint` (sección 3.7); no los invoca `Model` directamente.

### 3.4. Traducción a `Column` (DDL)

```python
def to_column(self) -> Column:
    return Column(datatype=self.datatype, name=self.name)
```

Esto mantiene la traducción de tipos por motor en `types.py` (`DDL_MAP`), sin mezclarla con la validación.

### 3.5. Integración con `Model`

Como `make_constraint` (sección 3.7) ya emite `Annotated[T, Constraint(...), Field(...)]`, **pydantic valida directamente** vía el `Field` embebido, y `Model` solo lee el metadato `Constraint` para el DDL:

```python
class Model(BaseModel):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for name, ann in cls.__annotations__.items():
            for meta in get_args(ann):
                if isinstance(meta, Constraint):
                    cls._columns[name] = meta.to_column()   # datatype + name -> DDL
```

No se reescriben anotaciones: `Constraint` viaja como metadato extra (ignorado por pydantic) y `Field` aporta la validación.

### 3.6. Integración con `validate()`

Las restricciones se ejecutan cuando `validate()` se invoca (según `@before_insert`/`@before_update`):

- `Constraint` → `Field`/`validators` → pydantic valida al construir/asignar.
- `validate()` **delega en pydantic** (captura `ValidationError` y reformatea a `dict[columna, mensaje]`), sin un motor paralelo:

```python
async def validate(self) -> dict | None:
    try:
        self.__class__.model_validate(self.model_dump())
    except ValidationError as exc:
        return {e["loc"][0]: f"{e['msg']} | valor actual {e.get('input')}" for e in exc.errors()}
    return None
```

### 3.7. Restricciones nombradas como funciones (vocabulario de dominio)

Para que `STR_100` se use como **llamada a una función** cuyos parámetros (`name=None`, `required=False`) pueden sobreescribirse y que **devuelva el `Annotated` correspondiente**, se usa una fábrica de orden superior `make_constraint`:

```python
from typing import Annotated
from decimal import Decimal
from datetime import datetime, date
from pydantic import Field, AfterValidator

PY_TYPE_TO_DATATYPE = {
    str: "str", int: "int", bool: "bool",
    float: "numeric", Decimal: "numeric",
    datetime: "datetime", date: "date", bytes: "blob",
}

def make_constraint(py_type, *, datatype=None, required=False, name=None,
                    validators=(), **base):
    if datatype is None:
        try:
            datatype = PY_TYPE_TO_DATATYPE[py_type]
        except KeyError:
            raise TypeError(f"Sin datatype inferido para {py_type!r}; indícalo con datatype=...")

    def build(name=name, required=required, **overrides):
        field_kwargs = {**base, **overrides}
        t = py_type if required else (py_type | None)
        default = ... if required else None
        return Annotated[
            t,
            Constraint(datatype=datatype, name=name, required=required,
                       field_kwargs=field_kwargs, validators=validators),
            Field(default=default, **field_kwargs),
            *(AfterValidator(v) for v in validators),
        ]
    return build

# módulo de dominio: constraints.py
STR_100    = make_constraint(str, max_length=100)                 # infiere datatype="str"
STR_50_REQ = make_constraint(str, max_length=50, required=True)
INT_POS    = make_constraint(int, ge=0)
MONTO      = make_constraint(float, ge=0, le=999_999_999.99)      # infiere datatype="numeric"
PRECIO     = make_constraint(float, datatype="float", ge=0)       # override explícito

class Agente(Model):
    _table = "agentes"
    id: int
    agente: STR_50_REQ()                        # str, max_length=50, required
    rfc: STR_100(name="rfc_col")                # str|None, max_length=100, col "rfc_col"
    monto: MONTO(required=True)                 # float, ge=0..le=999_999_999.99, required
```

**Comportamiento:**
- `STR_100` es una **función**; se invoca siempre: `STR_100(...)`.
- `datatype` se **infiere** de `py_type` vía `PY_TYPE_TO_DATATYPE`; se omite en la firma salvo que se quiera forzar (p. ej. `float` → `"numeric"` o `"float"`).
- `name`, `required` y `**overrides` son parámetros sobreescribibles; el resto (`max_length`, `ge`, …) viene del preset base.
- Devuelve `Annotated[py_type, Constraint(...), Field(...), AfterValidator(...)]`:
  - `required=True` → tipo `py_type` y `Field(...)` (obligatorio).
  - `required=False` → tipo `py_type | None` y `Field(None)` (opcional).
  - `validators` → se emiten como `AfterValidator` en el `Annotated` (validación pydantic).

---

## 4. Ejemplos

### 4.1. Uso directo (fábrica genérica)

```python
class Cliente(Model):
    _table = "clientes"
    nombre: make_constraint(str, max_length=100, required=True)()
    edad: make_constraint(int, ge=0)()
```

### 4.2. Uso con nombre de columna (tabla existente)

```python
class Legacy(Model):
    _table = "legacy"
    codigo: STR_100(name="legacy_code")
```

### 4.3. Validación personalizada adicional

```python
def rfc_valido(nombre, valor):
    if valor and not valor.isalnum():
        raise ValueError("RFC debe ser alfanumérico")

RFC = make_constraint(str, max_length=13, required=True, validators=(rfc_valido,))

class Contribuyente(Model):
    rfc: RFC()
```

---

## 5. Decisiones y ambigüedades

| # | Punto | Decisión / nota |
|---|-------|-----------------|
| 1 | `max` en `str` vs `int` | Para `str`, `max`/`min` son **longitud** (alias de `max_length`/`min_length`); para `int`/`numeric`, los límites de valor usan `ge/gt/le/lt`. Se recomienda `max_length`/`min_length` como nombre canónico en `str`. |
| 2 | "INT_POS entero positivo" vs `ge=0` | `ge=0` = no negativo; "positivo estricto" sería `gt=0`. Se debe documentar el significado de cada restricción nombrada. |
| 3 | `required=False` | Traduce a tipo `T | None` con default `None`; no a "valor con default". |
| 4 | `not_valid` vs `validate` | El prompt usa `not_valid`; en `design_model.md` el nombre canónico es `validate()`. |
| 5 | Doble validación | `Constraint` **no** valida por sí solo; solo traduce a `Field`. `validate()` delega en pydantic para evitar divergencia. |
| 6 | `STR_100` como función | `STR_100` es una **función** (`make_constraint`) que devuelve el `Annotated`; debe invocarse (`STR_100(...)`), no usarse como objeto en `Annotated`. |
| 7 | `datatype` inferido | `make_constraint(py_type, ...)` infiere `datatype` desde `PY_TYPE_TO_DATATYPE`; se conserva `datatype=` como override solo para casos ambiguos (`float`→`"numeric"`/`"float"`, `Decimal`). |

---

## 6. Ubicación en el proyecto

```
encinorm/model/
├── column.py          # Column (dataclass, existente)
├── constraint.py      # NUEVO: Constraint + fábricas por tipo
├── types.py           # DDL_MAP (existente)
└── model.py           # integración __init_subclass__ + _columns
```

Sin cambios en la interfaz `Db` ni en `QueryBuilder`.
