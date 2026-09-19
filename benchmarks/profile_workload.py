"""Carga de trabajo reproducible de profiling del núcleo de `encino_orm`.

Determinista (sin aleatoriedad), solo SQLite `:memory:`, sin red y sin drivers
opcionales. Es la línea base pre-optimización (PERF-03): la sección
`copy_table_rowwise` es la evidencia de comparación para 07-03 (PERF-01).

Uso:

    uv run python -W error benchmarks/profile_workload.py --mode=cprofile --scale=1
    uv run python -W error benchmarks/profile_workload.py --mode=manual --scale=1

`--mode=cprofile` genera `benchmarks/profiles/profile_workload_cprofile_YYYY-MM-DD.pstats`
y un `.txt` con el top-40 por cumtime. `--mode=manual` genera la tabla por
sección con `time.perf_counter()`.
"""

import argparse
import asyncio
import cProfile
import datetime
import io
import logging
import os
import pstats
import sys
import time

# El tracer por defecto degrada el rate; se apaga para no contaminar la medición.
logging.getLogger("encino_orm").setLevel(logging.WARNING)

from encino_orm import SqliteDb  # noqa: E402
from encino_orm.model import Model  # noqa: E402
from encino_orm.query import Query  # noqa: E402
from encino_orm.transfer import copy_table  # noqa: E402


class Cliente(Model):
    _table = "clientes"
    nombre: str
    email: str | None = None
    # datetime como TEXT: no disparar la DeprecationWarning del adapter
    # datetime de sqlite3; el modelo normaliza a UTC-naive isoformat
    # (mismo criterio que `encino_orm/model/model.py:36`).
    nacimiento: str | None = None


def _db() -> SqliteDb:
    db = SqliteDb()
    return db


async def _crud_sqlite(scale: int) -> tuple[str, int, float]:
    db = _db()
    await db.connect(database=":memory:")
    try:
        await Cliente(db, nombre="x").create_table()
        n = 500 * scale
        t0 = time.perf_counter()
        for i in range(n):
            c = Cliente(db, nombre=f"cliente-{i}", email=f"c{i}@x.test")
            await c.insert()
        for i in range(n):
            c = Cliente(db, id=i + 1, nombre=f"cliente-{i}")
            await c.load(keys=("id",))
        for i in range(0, n, 3):
            c = Cliente(db, id=i + 1, nombre=f"cliente-{i}", email=f"upd{i}@x.test")
            await c.update(keys=("id",), data={"email": f"upd{i}@x.test"})
        for i in range(n - 1, n - 250 * scale, -1):
            c = Cliente(db, id=i + 1, nombre=f"cliente-{i}")
            await c.delete(keys=("id",), physical=True)
        total = time.perf_counter() - t0
    finally:
        await db.close()
    return "crud_sqlite", n, total


async def _insert_many_chunked(scale: int) -> tuple[str, int, float]:
    db = _db()
    await db.connect(database=":memory:")
    try:
        await Cliente(db, nombre="x").create_table()
        n = 5000 * scale
        rows = [{"nombre": f"cliente-{i}", "email": f"c{i}@x.test"} for i in range(n)]
        t0 = time.perf_counter()
        await Cliente.insert_many(db, rows=rows, chunk=500)
        total = time.perf_counter() - t0
    finally:
        await db.close()
    return "insert_many_chunked", n, total


async def _copy_table_rowwise(scale: int) -> tuple[str, int, float]:
    src = _db()
    dst = _db()
    await src.connect(database=":memory:")
    await dst.connect(database=":memory:")
    try:
        await Cliente(src, nombre="x").create_table()
        n = 2000 * scale
        rows = [{"nombre": f"cliente-{i}", "email": f"c{i}@x.test"} for i in range(n)]
        await Cliente.insert_many(src, rows=rows, chunk=500)
        t0 = time.perf_counter()
        # Línea base pre-07-03 (PERF-03): hoy copy_table es fila a fila.
        await copy_table(src, dst, "clientes", create=True, preserve_ids=True)
        total = time.perf_counter() - t0
    finally:
        await src.close()
        await dst.close()
    return "copy_table_rowwise", n, total


async def _query_translation(scale: int) -> tuple[str, int, float]:
    n = 20000 * scale
    template = "SELECT {0}, {1}, {2} FROM t WHERE a={3} AND b={4} AND c={5} ORDER BY {6} DESC"
    values = [1, "x", 2.5, 3, "y", 4, "id"]
    t0 = time.perf_counter()
    for _ in range(n):
        q = Query(template, values)
        # La copia con nuevos parámetros ejercita la revalidación de cardinalidad.
        _ = q.with_params(values)
    total = time.perf_counter() - t0
    return "query_translation", n, total


async def _fetch_loop(scale: int) -> tuple[str, int, float]:
    db = _db()
    await db.connect(database=":memory:")
    try:
        await Cliente(db, nombre="x").create_table()
        n = 5000 * scale
        rows = [{"nombre": f"cliente-{i}", "email": f"c{i}@x.test"} for i in range(n)]
        await Cliente.insert_many(db, rows=rows, chunk=500)
        qry = Query("SELECT * FROM clientes", [])
        t0 = time.perf_counter()
        for _ in range(5):
            await db.fetch_all(qry)
        total = time.perf_counter() - t0
    finally:
        await db.close()
    return "fetch_loop", n, total


SECTIONS = [
    _crud_sqlite,
    _insert_many_chunked,
    _copy_table_rowwise,
    _query_translation,
    _fetch_loop,
]


async def _run_manual(scale: int, out: str) -> None:
    results = []
    for section in SECTIONS:
        nombre, n, total = await section(scale)
        results.append((nombre, n, total))
    lines = ["Sección | iteraciones | total s | ops/s"]
    lines.extend(f"{nombre} | {n} | {total:.4f} | {n / total:,.0f}" for nombre, n, total in results)
    text = "\n".join(lines)
    print(text)
    _write_text(out + ".txt", text + "\n")


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _header() -> str:
    plat = os.uname() if hasattr(os, "uname") else "windows"
    return (
        f"argv={sys.argv}\n"
        f"fecha={datetime.date.today().isoformat()}\n"
        f"plataforma={plat}\npython={sys.version.split()[0]}\n\n"
    )


def _write_stats(profiler, path: str):
    if path.endswith(".pstats"):
        profiler.dump_stats(path)
    else:
        _write_text(path, _header() + _stats_text(profiler))


def _stats_text(profiler) -> str:
    stats = io.StringIO()
    pstats.Stats(profiler, stream=stats).sort_stats("cumulative").print_stats(40)
    return stats.getvalue()


async def _run_cprofile(scale: int, out: str) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    for section in SECTIONS:
        await section(scale)
    profiler.disable()
    _write_stats(profiler, out + ".pstats")
    _write_stats(profiler, out + ".txt")
    pstats.Stats(profiler, stream=sys.stdout).sort_stats("cumulative").print_stats(40)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["cprofile", "manual"], default="cprofile")
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    if args.scale < 1:
        parser.error("--scale debe ser un entero positivo (>= 1)")
    date = datetime.date.today().isoformat()
    out = args.out or os.path.join(
        os.path.dirname(__file__), "profiles", f"profile_workload_{args.mode}_{date}"
    )
    expected = os.path.normpath(os.path.join(os.path.dirname(__file__), "profiles"))
    norm_out = os.path.normpath(os.path.dirname(out))
    if norm_out != expected:
        raise ValueError(f"--out debe vivir en benchmarks/profiles/: {out!r}")
    os.makedirs(expected, exist_ok=True)
    if args.mode == "manual":
        asyncio.run(_run_manual(args.scale, out))
    else:
        asyncio.run(_run_cprofile(args.scale, out))


if __name__ == "__main__":
    main()
