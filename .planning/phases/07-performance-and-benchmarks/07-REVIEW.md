---
phase: 07-performance-and-benchmarks
reviewed: 2026-09-19T16:22:08Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - encino_orm/dialects/builders.py
  - encino_orm/dialects/strategies.py
  - encino_orm/dialects/__init__.py
  - encino_orm/transfer.py
  - encino_orm/observability.py
  - .github/workflows/ci.yml
  - pyproject.toml
  - tests/test_benchmarks.py
  - tests/test_dialect_builders.py
  - tests/test_transfer.py
  - tests/_transfer_helpers.py
  - tests/test_mssql.py
  - tests/test_mysql.py
  - tests/test_oracle.py
  - tests/test_postgresql.py
findings:
  critical: 0
  high: 1
  medium: 2
  low: 3
  info: 3
  total: 9
status: issues_found
resolved: 2026-09-19T18:00:00Z
resolution: aplicado
---

# Phase 7: Code Review Report

**Reviewed:** 2026-09-19T16:22:08Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Fase 7 (PERF-01..04) revisada sobre el rango `cd71a4f^..HEAD`. Verifiqué el SQL
multi-VALUES/`INSERT ALL` en el seam de dialectos, la matemática de chunk de
`copy_table`, la semántica de rollback, el harness de benchmarks y el job CI.
Sondas empíricas ejecutadas: `test_dialect_builders.py` + `test_transfer.py` (130
passed), 6 benchmarks (passed, 3.5 s), `ruff check`/`format --check` limpios, y dos
probes ad-hoc que confirman HR-01 y MR-01.

**Atribución de alcance (git blame/log):** el cambio de `observability.py`
(`deque(maxlen=…)`, `latency_window`, guard `>= 1`) es el commit `6cf670e` (PERF-04),
**ancestro** de la base del rango (`cd71a4f^`) — no aparece en el diff del rango; lo
revisé por instrucción explícita y **no encontré defectos** (ventana acotada
documentada, percentiles operan sobre la ventana, `reset()` limpia, `deque` soporta
`min/max/sum/sorted`). El cambio `_FIELD_ADAPTERS` (WeakKeyDictionary) **NO es parte
de la Fase 7**: `git log -S` lo sitúa en el commit ancestral `184f647`; fuera de
alcance.

**Veredicto:** implementación competente — inmunidad a inyección verificada, límites
de dialecto aplicados, rollback probado, equivalencia fila-por-fila probada, Oracle
`INSERT ALL` verificado en motor real — con **un defecto de integridad de datos en la
API pública nueva** (HR-01: filas desparejas corrompen valores en silencio) y **un
camino degradado que emite SQL inválido y queda pinado por un test nuevo** (MR-01).
Ambos son triviales de arreglar y tocan el valor central del proyecto.

### Tabla por fichero

| Fichero | Hallazgos |
|---|---|
| `encino_orm/dialects/builders.py` | HR-01, MR-02 |
| `encino_orm/dialects/strategies.py` | — (`multi_values` correcto; Oracle único `False`) |
| `encino_orm/dialects/__init__.py` | — (export en `__all__` correcto) |
| `encino_orm/transfer.py` | MR-01, LR-01 |
| `encino_orm/observability.py` | — (revisado; sin hallazgos) |
| `.github/workflows/ci.yml` | LR-03 |
| `pyproject.toml` | — (marker actualizado coherente) |
| `tests/test_dialect_builders.py` | — (cobertura byte-a-byte sólida; falta caso ragged de HR-01) |
| `tests/test_transfer.py` | MR-01 (pina SQL inválido), IN-02 |
| `tests/test_benchmarks.py` | LR-02, LR-03, IN-01, IN-03 |
| `tests/_transfer_helpers.py` | — (equivalencia canónica correcta) |
| `tests/test_mssql|mysql|oracle|postgresql.py` | — (sondas cross-engine bien formadas) |

### Verificación de requerimientos

- **R1 — Inyección/interpolación en `build_multi_insert`: SEGURO.** Tabla/schema vía
  `_qualified` y columnas vía `check_identifier` (builders.py:230-232); valores siempre
  como `{n}` encadenados (builders.py:236); contrato de `Query` como backstop
  (query.py:79-86). `test_maliciosos_rechazados` (test_dialect_builders.py:1026-1033) y
  `test_valores_van_como_params_no_interpolados` (:1050-1054) lo pinan. Sin hallazgos.
- **R2 — Batching de `copy_table`: SEGURO salvo hallazgos.** `chunk = max(1,
  min(MAX_PARAMS // max(n,1), MAX_ROWS))` (transfer.py:164); los `LIMITS` reales de los
  seis adaptadores lo mantienen en `[1, MAX_ROWS]` (techo TVC de MSSQL=1000 incluido).
  Equivalencia fila-por-fila con 2.500 filas sqlite→sqlite (test_transfer.py:237-275);
  respeto de `MAX_PARAMS`/`MAX_ROWS` con dobles (:278-326); rollback probado (:354-365).
  La lectura NO pagina (`fetch_all` completo; sin `LIMIT ? OFFSET ?`) — coste de
  memoria, performance, fuera del alcance v1. Sin drift de serialización: ambos caminos
  usan la misma `_serialize` + el mismo seam.
- **R3 — Oracle `INSERT ALL`: CORRECTO; rowcount soslayado por diseño.** Estructura
  `INSERT ALL INTO t (...) VALUES (...) INTO t (...) SELECT 1 FROM DUAL` correcta. El
  rowcount de Oracle para `INSERT ALL` (1, no n) es irrelevante: `copy_table` cuenta
  `len(batch)` y nunca consume el retorno de `dst.execute` (transfer.py:178-189). Sonda
  real sqlite→Oracle de 100 filas pasó (07-03-SUMMARY:91); binds nombrados
  `:parameter_000N` únicos. Nota: la sonda ejerce 100 filas; el chunk real (1000
  filas/6000 binds) sigue sin verificar (provenance honesta "NO verificado").
- **R4 — Cardinalidad de `_placeholders_from`: CORRECTA.** Con offset en pasos de
  `n_cols`, el último índice es `n_rows*n_cols - 1 == len(values) - 1`; el contrato
  `Query` lo certifica para los seis dialectos (tests byte-a-byte + smoke del benchmark
  `len(qry.params) == 1000`).
- **R5 — Concurrencia: SIN RIESGO.** Sin estado mutable compartido nuevo: `batch`,
  `total`, `_serialize` son locales a la corrutina; los `await` no intercalan estado
  compartido más allá de la conexión.
- **R6 — Harness de benchmarks: VÁLIDO con matices (LR-02/LR-03/IN-01/IN-03).**
  Metodología `_measure` correcta (warmup 3, reps 9, `gc.collect()` + `gc.disable()`
  durante el cronometrado), gate = mediana > piso (0.6×). Verifiqué los 6 floors en
  este host (todos pasan). Job CI bien aislado (colección por fichero, sin extras, sin
  coverage; main job excluye `-m "not benchmark"`).
- **R7 — Estilo/convenciones: CUMPLE.** Comentarios en español, params siempre ligados,
  cero `# type: ignore`/`# noqa` añadidos, `ruff check`/`format` limpios, sin líneas
  nuevas > 100 en `encino_orm/`.

## High

### HR-01: `build_multi_insert` acepta filas desparejas y corrompe valores en silencio

**File:** `encino_orm/dialects/builders.py:234-255`

**Issue:** `values = [v for row in rows for v in row]` aplana las filas y el
particionado en tuplas usa `range(0, n_rows*n_cols, n_cols)`, pero **ningún guard
valida `len(row) == len(columns)` por fila**. El contrato de `Query` (query.py:83-86)
solo compara el TOTAL de placeholders contra el TOTAL de valores: con total
coincidente, no hay error y los valores se **desplazan entre filas**.

Reproducción verificada:
```python
qry = build_multi_insert("t", ["a", "b"], [[1], [2, 3, 4]], strategy=SQLITE_INSERT)
# sin error: sql_template "INSERT INTO t (a,b) VALUES ({0},{1}),({2},{3})"
# fields [1, 2, 3, 4] → la fila 1 (era [1]) se inserta como (1, 2); el valor 2
# de la fila 2 migra a la fila 1; la fila 2 se inserta como (3, 4).
# Con tipos compatibles el motor NO lo rechaza: corrupción silenciosa.
```
`copy_table` es inmune (las filas del lote comparten `keys()` por construcción,
transfer.py:169-171), pero la API es **pública y exportada**
(`dialects/__init__.py:__all__`), el docstring afirma "encadenados en orden fila a
fila" sin documentar el contrato de longitud, y no hay test de filas desparejas
(solo `rows_vacio` y `columnas_vacias`).

**Fix:** validar la longitud de cada fila antes de aplanar, y añadir un test
`test_filas_desparejas_lanzan` (una fila corta y una larga con total coincidente):
```python
    n_cols = len(columns)
    for i, row in enumerate(rows):
        if len(row) != n_cols:
            raise ValueError(
                f"fila {i} con {len(row)} valores para {n_cols} columnas: {row!r}"
            )
```

## Medium

### MR-01: fallback de tabla solo-auto-PK emite `INSERT INTO t () VALUES ()` — error de sintaxis, y el test nuevo lo pina

**File:** `encino_orm/transfer.py:190-196`, `tests/test_transfer.py:351`

**Issue:** Cuando `target_cols == []` (tabla con única PK autoincremental y
`preserve_ids=False`; alcanzable vía CLI con `--no-preserve-ids`, cli.py:122), el
camino fila a fila ejecuta `dst.insert(table, {})` → `INSERT INTO t () VALUES ()`.
**Verificado en SqliteDb real: `OperationalError near ")": syntax error`**
(MySQL/MariaDB lo aceptan; SQLite, MSSQL y Oracle no). El `transaction()` hace
rollback (sin corrupción), pero la copia falla en un camino que la Fase 7 declara
soportado ("Se conserva el camino fila a fila (degradado, explícito)"). El defecto es
pre-existente, pero la fase lo elevó a ruta documentada y el test
`test_tabla_solo_auto_pk` (test_transfer.py:338-351) **congela la plantilla rota**
(`startswith("INSERT INTO t ()")`) con un doble en vez de un SqliteDb real, de modo
que el arreglo deberá tocar también el pin.

**Fix:** emitir SQL de default por dialecto en el fallback (o insertar `len(rows)`
filas con defaults) y reemplazar el assert del test por una verificación de ejecución
contra un SqliteDb real:
```python
# sqlite/postgresql/mssql: INSERT INTO t DEFAULT VALUES
# mysql/mariadb: INSERT INTO t () VALUES ()   (válido en MySQL)
# oracle: INSERT INTO t (id) VALUES (DEFAULT) — o documentar la limitación
```

### MR-02: `ignore_duplicated` en lote es todo-o-nada en MSSQL/Oracle y skip-por-fila en prefix/suffix — asimetría silenciosa

**File:** `encino_orm/dialects/builders.py:257-261` (+ mssql.py:365-366, oracle.py:326-327)

**Issue:** `build_multi_insert` replica el mecanismo de `build_insert` para
`carries_ignore_duplicated` (MSSQL/Oracle): el SQL no cambia y el `Query` lleva el
flag; el adaptador suprime la violación completa del statement (`return 0`).
Para un lote con UNA fila duplicada: SQLite/MySQL/PostgreSQL insertan las no
duplicadas, **MSSQL/Oracle descartan el lote entero en silencio y `execute` devuelve
0** — sin error. El docstring documenta el mecanismo (builders.py:216-223) pero no la
semántica todo-o-nada del lote; ningún test pina el comportamiento batch en
MSSQL/Oracle (solo el flag, test_dialect_builders.py:991-998 y 1014-1020).
`copy_table` no pasa el flag, así que el impacto hoy es solo para usuarios directos de
la API nueva; la asimetría viola la previsibilidad multi-motor del proyecto.

**Fix:** documentar explícitamente en el docstring de `build_multi_insert` que con
`carries_ignore_duplicated` el flag descarta el lote completo (all-or-nothing,
diferente del skip-por-fila de los demás dialectos) y añadir un test que pinee la
semántica con un spy de `execute`.

## Low

### LR-01: `chunk = max(1, ...)` no cubre `len(target_cols) > max_params`: el lote excede el límite que debe respetar

**File:** `encino_orm/transfer.py:162-164`

**Issue:** Si `max_params // n == 0` (más columnas que el techo de parámetros del
destino), `chunk = max(1, 0) = 1` y cada lote de 1 fila lleva `n` params **>**
`max_params`, violando el límite que la fórmula existe para respetar. Inalcanzable con
los `LIMITS` reales (columnas máx. por motor < max_params en los seis), alcanzable con
un `Db` propio de `MAX_PARAMS` pequeño.

**Fix:** degradar a fila a fila por `dst.insert` (el camino que ya existe para
`target_cols == []`) o fallar con mensaje claro cuando `per_row == 0`.

### LR-02: el canario `test_batch_sizing_floor` mide una copia literal de la fórmula, no el código de producción

**File:** `tests/test_benchmarks.py:189-197`

**Issue:** La unidad mide `max(1, min(32767 // max(5, 1), 1000))` — un duplicado
literal de la fórmula, no el código real (`copy_table`/`insert_many`). Si la fórmula
cambia en producción (p. ej. por un fix de LR-01), el canario sigue verde y no detecta
el drift; el comentario "la misma que insert_many" se vuelve falso sin que el gate
parpadee.

**Fix:** extraer la fórmula a un helper compartido (p. ej. `dialects`/`transfer`) y
medir ese helper, o al menos anclar el test con un assert de igualdad contra el código
de producción.

### LR-03: margen del gate recalibrado a una sola corrida de CI — headroom exacto 1.67× en runners compartidos

**File:** `tests/test_benchmarks.py:97-102,187-197`; `.github/workflows/ci.yml:252-283`

**Issue:** El piso de `batch_sizing` se recalibró a 0.6× de UNA corrida de CI
(2,65M → 1,58M) tras observar 4× de dispersión host↔CI para esa clase de unidad
(aritmética pura limitada por frecuencia de core, no por ancho de banda Python). El
margen resultante es exactamente el umbral de regresión (1,67×): un runner compartido
más cargado que el de la calibración puede hacer fallar el job sin regresión real
(flake del gate). El RESEARCH ya puntuaba la robustez del gate wall-clock como riesgo
MEDIO (07-RESEARCH:551).

**Fix:** en las primeras N corridas, o bien usar el percentil 5 de una serie de
corridas para fijar el piso, o bien bajar los pisos de unidades aritméticas a 0.5×
(umbral 2×) para absorber varianza cross-run de GitHub-hosted runners.

## Info

### IN-01: el docstring de `_measure` sobredeclara la duración de las repeticiones

**File:** `tests/test_benchmarks.py:40-43` vs `86-90`

**Issue:** "apuntando a >= 0.5 s en CI" no se cumple: con `inner=2_000`/`200` y las
líneas base medidas, las ventanas reales son ~5-160 ms por repetición (locales). El
comentario posterior (:86-90) explica que los bursts cortos son deliberados por
thermal-throttle. El docstring debería reflejar la decisión (y el trade-off de ruido
de scheduler de ventanas < 200 ms, mitigado por la mediana de 9).

**Fix:** ajustar el docstring al diseño real (bursts cortos deliberados, mediana de 9
reps como mitigación).

### IN-02: el error de fila despareja (hoy) es un ValueError de Query sin contexto de fila

**File:** `encino_orm/dialects/builders.py:234-236` (vía query.py:83-86)

**Issue:** Hoy una fila despareja con total NO coincidente lanza "placeholders [0, 1]
no cuadran con N parámetros" — cierto pero sin señalar la fila culpable. El fix de
HR-01 lo sustituye por un mensaje con índice de fila; este IN queda resuelto por aquel.

**Fix:** resuelto por HR-01.

### IN-03: `gc.enable()` incondicional en `finally` no restaura un estado previo desactivado

**File:** `tests/test_benchmarks.py:54-62`

**Issue:** Si otro fixture/plugin dejó el GC desactivado antes de la medición,
`gc.enable()` lo rehabilita globalmente al terminar (mismo patrón que `timeit`; en la
práctica ningún fixture de la suite desactiva GC, así que el riesgo es teórico).

**Fix:** capturar `gc.isenabled()` antes y restaurarlo, o aceptar el patrón timeit
documentándolo.

## Resolución de hallazgos

| Hallazgo | Resolución | Commit |
|---|---|---|
| HR-01 | Guard fail-closed de `len(row) == len(columns)` por fila antes de aplanar, con índice de fila en el mensaje; resuelve también IN-02. Test `test_filas_desparejas_lanzan` pina ambas ramas de render (multi-VALUES y Oracle INSERT ALL). | `edf8318` |
| MR-01 | Fallback `target_cols == []` emite SQL de fila default POR DIALECTO (`_default_row_sql`: `DEFAULT VALUES` en sqlite/postgres/mssql, `() VALUES ()` en mysql/mariadb, `(pk) VALUES (DEFAULT)` en oracle). `test_tabla_solo_auto_pk` ahora ejecuta contra un SqliteDb real (3 filas, ids 1..3) en vez de pinar la plantilla rota con un doble. | `8228dc5` |
| MR-02 | Docstring de `build_multi_insert` documenta la semántica ALL-OR-NOTHING de `carries_ignore_duplicated` (MSSQL/Oracle) frente al skip-por-fila de prefix/suffix; los tests `test_mssql_ignore_duplicated_no_anade_clausula` y `test_oracle_ignore_duplicated_no_anade_clausula` desplazados e intencionados como pin de la semántica. | `edf8318` |
| LR-01 | `batch_size` puede devolver 0; `copy_table` degrada a insert de fila única (`build_insert` por dialecto) cuando `per_row == 0`. Test `test_mas_columnas_que_MAX_PARAMS_degradan_a_fila_a_fila` (FakeDb con max_params=2 y 3 columnas: 3 sentencias de 1 fila, 3 params c/u). | `8228dc5` |
| LR-02 | La fórmula se extrae a producción como `transfer.batch_size` y el canario `test_batch_sizing_floor` la importa y mide directamente. | `8228dc5` |
| LR-03 | ACEPTADO como riesgo documentado: 3 corridas CI consecutivas verdes (σ ~1,3% dentro de job); la garantía real (2 lucas de margen respecto al umbral 1.5x del gate en la prueba posterior de recalibración) reduce el riesgo de flake frente al runner de calibración. Sin cambio de piso en esta fase. | — |
| IN-01 | Docstring de `_measure` reescrito: bursts cortos deliberados (thermal-throttle), mediana de 9 reps como mitigación del ruido de scheduler. | `8228dc5` |
| IN-03 | `_measure` captura `gc.isenabled()` y restaura el estado previo en `finally` en vez de `gc.enable()` incondicional. | `8228dc5` |
| IN-02 | Resuelto por el fix de HR-01 (mensaje con índice de fila). | `edf8318` |

Estado final tras los fixes: `tests/test_transfer.py` + `test_benchmarks.py` + `test_dialect_builders.py` → 138 passed. CI completo tras push: **10/10 jobs verde** en `4a00838` (incluye `Benchmarks (gate 2x)`, `Lint y formato`, `Tipos (mypy)` y `Motores pesados (MSSQL + Oracle)`), docs desplegadas en Pages (`docs.yml` success). Notable: la primera corrida tras los fixes falló solo en mypy (`auto_pk` no estrechado a `str`) y la segunda en ruff S101 (`assert`) — ambos corregidos y verdes en `4a00838`.

---

_Revisado: 2026-09-19_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_