"""PERF-02: unidades SÍNCRONAS del núcleo medidas con `time.perf_counter`.

Sin base de datos (sin ruido de driver/CI). Cada unidad tiene un piso numérico
(= 0.6x de la línea base medida en CI): una regresión >= 1.67x en cualquiera de
las 6 unidades falla el job `benchmarks`. La calibración de un piso se documenta
en el MISMO commit que lo cambia.

Los tests de este módulo están marcados `benchmark` y quedan EXCLUIDOS de las
corridas normales (`-m "not optional_engine and not benchmark"`); el job
`benchmarks` de CI es quien los ejecuta.
"""

import gc
import logging
import statistics
import time

import pytest

from encino_orm.model import Model
from encino_orm.observability import _percentile
from encino_orm.query import Query

pytestmark = [pytest.mark.benchmark, pytest.mark.timeout(60)]


@pytest.fixture(autouse=True)
def _silence_tracer_logger():
    logger = logging.getLogger("encino_orm")
    was_disabled = logger.disabled
    logger.disabled = True
    yield
    logger.disabled = was_disabled


def _measure(fn, *, inner, warmup=3, reps=9) -> tuple[float, float, float]:
    """Devuelve (mediana, p95, sigma) de ops/s de `fn` (sin argumentos).

    Cada repetición cronometrada ejecuta `inner` llamadas en un bucle for plano.
    Los bursts son CORTOs a propósito (ventanas reales ~5-160 ms): uno largo
    (>= 1 s por repetición) colapsa la medición en este host por
    thermal-throttle del CPU, y los bursts cortos deliberados compensan el ruido
    de scheduler con la MEDIANA de 9 repeticiones (IN-01). `gc.collect()` se
    llama ANTES de cada bucle cronometrado y el GC se desactiva DURANTE la
    medición, restaurando su estado previo después (misma metodología que
    `timeit`); así el cronometrado no se ve contaminado por recolecciones
    automáticas disparadas por las propias asignaciones (IN-03).
    """

    def run():
        for _ in range(inner):
            fn()

    for _ in range(warmup):
        run()
    samples = []
    gc_was_enabled = gc.isenabled()
    for _ in range(reps):
        gc.collect()
        gc.disable()
        try:
            t0 = time.perf_counter()
            run()
            elapsed = time.perf_counter() - t0
        finally:
            if gc_was_enabled:
                gc.enable()
        samples.append(inner / elapsed)
    return statistics.median(samples), _percentile(samples, 0.95), statistics.stdev(samples)


def _assert_floor(nombre, median, p95, std, floor):
    assert median > floor, (
        f"{nombre} {median:,.0f} ops/s < {floor:,} (p95={p95:,.0f}, sigma={std:.0f})"
    )


class _A(Model):
    _table = "a"
    x: int


class _B(Model):
    _table = "b"
    y: int


# --- Unidades y pisos (0.6x de la línea base del harness, calibrados en este
# --- commit; la PRIMERA corrida del job `benchmarks` en CI recalibra ±20% y
# --- ajusta el piso en ese mismo commit, según el plan 07-02) ---

# Metodologia: `inner` corto (semillas del plan 07-02: 2.000/200.000 ops por
# repetición cronometrada). Un `inner` largo (>= 1 s por repetición) colapsa la
# medición en este host por el boost/thermal-throttle del CPU (verificado:
# la fórmula pura de batch mide 10,4M ops/s con bursts de 500K pero 3,6M con
# 5M sostenidos — la misma aritmética, distancia termal, no GC).
#
# Lineas base del harness (mediana de ops/s, runs locales 2026-09-19):
# sql_build ~254K, query_construction ~175K, query_with_params ~221K,
# to_mysql ~377K, batch_sizing ~10,5M, multi_insert_gen ~1,3K. Pisos = 0.6x de
# esas líneas base.
#
# PRIMERA corrida en CI (2026-09-19, runner ubuntu 2-vCPU): 5 de 6 unidades
# pasan ≥ sus pisos locales, pero batch_sizing mide ~2,65M (sigma 33,9K) frente a
# 10,5M locales — la unidad es aritmética pura y su throughput escala con la
# frecuencia del core, no con el ancho de banda Python (resto de unidades).
# Su piso se recalibra a la medida de CI (2,65M x 0.6 = 1,58M) en el MISMO
# commit, según la disciplina de calibración del plan 07-02.
#
# NOTA de calibracion vs RESEARCH Q3: el RESEARCH media to_mysql ~625K y
# Query ~236K con plantillas más pequeñas y una granularidad distinta
# (traducción aislada). El harness real mide la unidad completa
# (`Query.__init__` con validación y `_to_mysql` con plantilla de 6+2
# placeholders), por lo que las líneas base quedan fijadas a lo que ESTA suite
# mide y el piso conserva la semántica de gate 2x (regresión -> 0.5x -> falla).


# 1. Construcción SQL completa (QueryBuilder._build_full) — ~254K medidos.
def test_sql_build_floor():
    from encino_orm import SqliteDb
    from encino_orm.model.filter import Filter
    from encino_orm.model.query_builder import QueryBuilder

    qb = (
        QueryBuilder(_A, db=SqliteDb(), alias="mm")
        .select("mm.x")
        .join(_B, "b", on=Filter.eq("mm.x", 1))
        .where(Filter.gt("mm.y", 0))
        .group_by("mm.x")
        .order_by("mm.x")
    )
    sql, _ = qb._build_full()
    assert "JOIN" in sql  # smoke: la unidad no está rota
    assert "WHERE" in sql

    median, p95, std = _measure(qb._build_full, inner=2_000)
    _assert_floor("sql_build", median, p95, std, 152_000)


# 2. Construcción de Query raíz (plantilla 7 placeholders unicos) — ~175K medidos.
QUERY_TEMPLATE = "SELECT {0}, {1}, {2} FROM t WHERE a={3} AND b={4} AND c={5} ORDER BY {6}"
QUERY_VALUES = [1, "x", 2.5, 3, "y", 4, "id"]


def test_query_construction_floor():
    q = Query(QUERY_TEMPLATE, QUERY_VALUES)
    assert isinstance(q, Query)
    assert len(q.params) == 7  # smoke

    def _build():
        return Query(QUERY_TEMPLATE, QUERY_VALUES)

    median, p95, std = _measure(_build, inner=2_000)
    _assert_floor("query_construction", median, p95, std, 105_000)


# 3. `with_params` (copia con nueva cardinalidad) — ~221K medidos.
WITHPARAMS_VALUES = [1, "x", 2.5, 3, "y"]


def test_query_with_params_floor():
    base = Query("SELECT {0}, {1}, {2}, {3}, {4} FROM t", WITHPARAMS_VALUES)
    q2 = base.with_params(WITHPARAMS_VALUES)
    assert q2 is not base  # smoke: devuelve copia, no muta

    median, p95, std = _measure(lambda: base.with_params(WITHPARAMS_VALUES), inner=2_000)
    _assert_floor("query_with_params", median, p95, std, 130_000)


# 4. `_to_mysql` (traducción de placeholders compilados) — ~377K medidos.
# La entrada real es el `Query` ya compilado (`sql` con `%(parameter_0000)s` y
# `params` con las claves `parameter_000n`), igual que en el camino de ejecución.
MYSQL_TMPL = "SELECT {0}, {1}, {2}, {3}, {4}, {5} FROM t WHERE a={0} AND b IN ({2},{3})"
MYSQL_QUERY = Query(MYSQL_TMPL, [1, 2, 3, 4, 5, 6])


def test_to_mysql_floor():
    from encino_orm.mysql import _to_mysql

    sql, values = _to_mysql(MYSQL_QUERY.sql, MYSQL_QUERY.params)
    assert isinstance(sql, str)
    assert isinstance(values, list)
    assert "%s" in sql
    assert "%(" not in sql

    def _to():
        return _to_mysql(MYSQL_QUERY.sql, MYSQL_QUERY.params)

    median, p95, std = _measure(_to, inner=2_000)
    _assert_floor("to_mysql", median, p95, std, 226_000)


# 5. Fórmula de tamaño de lote `batch_size` (producción: encino_orm.transfer) —
#    ~2,65M en CI (2,65M x 0.6 = piso 1,58M; recalibrado en la primera corrida
#    del job). El canario mide la FUNCIÓN de producción, no una copia literal
#    (LR-02): un cambio en `batch_size` parpadearía el gate en vez de ocultarse.
def test_batch_sizing_floor():
    from encino_orm.transfer import batch_size

    result = batch_size(5, 32767, 1000)
    assert result == 1000  # smoke: 32767//5 = 6553, techado a MAX_ROWS 1000

    median, p95, std = _measure(lambda: batch_size(5, 32767, 1000), inner=200_000)
    _assert_floor("batch_sizing", median, p95, std, 1_580_000)


# 6. Generación multi-VALUES (PERF-01): `build_multi_insert` con el workload del
# plan 07-03 (200 filas x 5 columnas) — ~1.306 medidos (runs locales 2026-09-19).
# El RESEARCH Q3 media 1.516 con un cohort distinto; el piso se calibra con lo que
# ESTA suite mide (misma doctrina que el resto de unidades); la PRIMERA corrida
# del job `benchmarks` recalibra ±20%. Entre más filas por lote más se degrada la
# medición por thermal-throttle del host (verificado: un lote de 500 filas cae de
# ~670 a ~240 ops/s sostenidas), por eso `inner` corto.
MULTI_TABLE = "t"
MULTI_COLS = ["a", "b", "c", "d", "e"]
MULTI_ROWS = [
    [i, f"v{i}", i / 2.0, i % 2 == 0, f"2026-09-{i % 28 + 1:02d} 10:00:00"] for i in range(200)
]


def test_multi_insert_gen_floor():
    from encino_orm.dialects import build_multi_insert, strategy_for
    from encino_orm.engine import Engine

    qry = build_multi_insert(
        MULTI_TABLE, MULTI_COLS, MULTI_ROWS, strategy=strategy_for(Engine.SQLITE)
    )
    assert isinstance(qry, Query)
    assert len(qry.params) == len(MULTI_ROWS) * len(MULTI_COLS)  # smoke: params encadenados
    assert "VALUES" in qry.sql  # smoke: la unidad no está rota
    assert "INSERT ALL" not in qry.sql  # smoke: no es la rama Oracle

    def _gen():
        return build_multi_insert(
            MULTI_TABLE, MULTI_COLS, MULTI_ROWS, strategy=strategy_for(Engine.SQLITE)
        )

    median, p95, std = _measure(_gen, inner=200)
    _assert_floor("multi_insert_gen", median, p95, std, 780)
