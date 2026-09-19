# Fronteras de confianza (SQL)

Esta página documenta los tres puntos de `encino_orm` donde el llamador puede
introducir **texto SQL** en una sentencia. La regla transversal es una sola:

> **Los valores SIEMPRE viajan ligados como parámetros; nunca se interpola
> entrada no confiable en la plantilla SQL.**

`Filter.raw`, `Query` y `db.fn.*` son escapes deliberados: aceptan fragmentos de
SQL que la librería **no** valida. Su contrato es *trusted input only*: si el
fragmento depende de entrada de usuario, sanearla o ligarla es responsabilidad
del llamador. Los ejemplos de esta página usan marcadores de posición; nunca
credenciales ni datos reales.

## Filter.raw

`Filter.raw(sql, params)` (`encino_orm/model/filter.py`) construye una condición
de filtrado a partir de un fragmento SQL literal y una lista de parámetros. Es
el único punto de `Filter` que acepta SQL libre.

**Qué valida hoy.** Nada sobre `sql`: `_rebind_raw` (`filter.py`) solo reindexa
los placeholders `{n}` para que encajen con el resto del árbol y reemite el
fragmento **verbatim**. Los valores de `params` sí se ligan. `_safe_field` y
`_qual` validan únicamente nombres de campo, no el fragmento RAW.

### Ejemplo SEGURO

Fragmento constante con placeholders `{n}`; los valores viajan ligados:

```python
f = Filter.raw("precio > {0} AND precio < {1}", [10, 100])
```

### Ejemplo INSEGURO

Interpolar entrada no confiable dentro del fragmento; el valor acaba formando
parte del SQL y no puede ligarse:

```python
nombre_del_usuario = obtener_nombre_del_request()
f = Filter.raw(f"nombre = '{nombre_del_usuario}'", [])  # inyección SQL
```

## Query

`Query(sql, fields)` (`encino_orm/query.py`) es el contenedor de sentencia +
valores por el que pasa **toda** ejecución. Compila los placeholders `{n}` de la
plantilla a la forma del adaptador y liga cada valor como parámetro.

**Qué valida hoy.** La cardinalidad de los `{n}`: el conjunto de índices
detectados debe ser exactamente `range(len(values))`; pasar valores a una
plantilla sin `{n}` es un `ValueError` (no un descarte silencioso). Los valores
nunca se interpolan: se pasan ligados al driver (`query.py`).

### Ejemplo SEGURO

Plantilla constante y valores en la lista de parámetros:

```python
user_id = obtener_id_del_request()
q = Query("SELECT * FROM t WHERE id = {0}", [user_id])
```

### Ejemplo INSEGURO

Interpolar el valor en la plantilla anula el binding y abre la inyección:

```python
user_id = obtener_id_del_request()
q = Query(f"SELECT * FROM t WHERE id = {user_id}", [])  # inyección SQL
```

**Limitación declarada.** Un `{n}` dentro de un literal de cadena se interpreta
como placeholder; esta versión no parsea literales SQL (`query.py`). Si la
plantilla contiene un literal con llaves, hay que construirlo con cuidado.

## db.fn.*

`db.fn.*` (`encino_orm/sql.py`, clase `SqlFunctions`) devuelve **fragmentos SQL**
(texto de confianza) traducidos al dialecto del motor, para incrustar en `Query`
o `Filter.raw`; no son valores a enlazar.

**Qué valida hoy.** Los nombres de columna que recibe cada función pasan por una
allowlist (`_COLUMN_RE`, que admite el punto para nombres cualificados) antes de
incrustarse. La entrada de usuario nunca debe llegar a un argumento de columna.

### Ejemplo SEGURO

Incrustar el fragmento de confianza en una plantilla constante:

```python
q = Query(f"SELECT * FROM t WHERE creado > {db.fn.now()}", [])
```

### Ejemplo INSEGURO

Concatenar entrada no confiable al fragmento de confianza:

```python
user_input = obtener_filtro_del_request()
q = Query(f"SELECT * FROM t WHERE nombre = {db.fn.now()} AND x = '{user_input}'", [])
```

## Resumen

| Escape | Qué valida | Regla del llamador |
|--------|------------|--------------------|
| `Filter.raw` | Solo reindexa `{n}`; reemite verbatim | No interpolar entrada no confiable; usar `params` |
| `Query` | Cardinalidad estricta de `{n}` vs. `len(values)` | Poner los valores en la lista, nunca en la plantilla |
| `db.fn.*` | Allowlist de nombres de columna | Incrustar solo fragmentos de confianza |

Ningún parser HTTP (`encino_orm/http/parsing.py`) ni GraphQL
(`encino_orm/graphql/filters.py`) puede emitir `Filter.raw`: sus conjuntos de
operadores son cerrados y un test de regresión lo congela
(`tests/test_trust_boundaries.py`).
