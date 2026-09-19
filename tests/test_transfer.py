import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from encino_orm import Query
from encino_orm.cli import main
from encino_orm.dialects import build_insert, strategy_for
from encino_orm.introspection import columns_of
from encino_orm.introspection.types import ColumnSpec
from encino_orm.sqlite import SqliteDb
from encino_orm.transfer import (
    _normalize_value,
    _serialize_for_target,
    build_ddl,
    copy_database,
    copy_table,
)


def _col(name, datatype, pk=False):
    return ColumnSpec(
        name=name, raw_type=datatype, datatype=datatype, nullable=True, primary_key=pk
    )


class FakeDb:
    """Doble del DESTINO que espié `copy_table`: registra cada `execute`.

    Simula los atributos de límites de los adaptadores reales (MAX_PARAMS /
    MAX_ROWS) y el ciclo de transacción (commit en éxito, rollback en fallo).
    `execute` puede fallar en el N-ésimo intento (`fail_at`) para probar la
    propagación de errores sin transacción colgada.
    """

    def __init__(self, *, dialect="sqlite", max_params=500, max_rows=1000, fail_at=None):
        self.dialect = dialect
        self.MAX_PARAMS = max_params
        self.MAX_ROWS = max_rows
        self.executes = []
        self.insert_calls = []
        self.events = []
        self.fail_at = fail_at

    @asynccontextmanager
    async def transaction(self):
        self.events.append("begin")
        try:
            yield self
            self.events.append("commit")
        except BaseException:
            self.events.append("rollback")
            raise

    async def execute(self, qry):
        if self.fail_at is not None and len(self.executes) + 1 == self.fail_at:
            raise RuntimeError("fallo simulado")
        self.executes.append(qry)
        return 1

    def insert(self, tabla, data):
        qry = build_insert(tabla, data, strategy=strategy_for(self.dialect))
        self.insert_calls.append(qry)
        return qry


class TestBuildDdl:
    def test_sqlite_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True), _col("nombre", "str")], "sqlite")
        assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
        assert "nombre TEXT" in ddl

    def test_mysql_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True), _col("nombre", "str")], "mysql")
        assert "id INT AUTO_INCREMENT PRIMARY KEY" in ddl
        assert "nombre VARCHAR(255)" in ddl

    def test_postgres_auto_pk(self):
        ddl = build_ddl("users", [_col("id", "int", pk=True)], "postgresql")
        assert "id SERIAL PRIMARY KEY" in ddl

    def test_composite_pk(self):
        ddl = build_ddl(
            "m",
            [_col("tenant_id", "int", pk=True), _col("code", "str", pk=True)],
            "sqlite",
        )
        assert "PRIMARY KEY (tenant_id, code)" in ddl


class TestValueTranslation:
    def test_date_from_str(self):
        assert _normalize_value("2026-09-07", "date") == date(2026, 9, 7)

    def test_date_targets(self):
        d = date(2026, 9, 7)
        assert _serialize_for_target(d, "date", "sqlite") == "2026-09-07"
        assert _serialize_for_target(d, "date", "mysql") is d
        assert _serialize_for_target(d, "date", "postgresql") is d

    def test_datetime_from_str(self):
        assert _normalize_value("2026-01-01 14:00:00", "datetime") == datetime(2026, 1, 1, 14, 0, 0)

    def test_datetime_targets(self):
        dt = datetime(2026, 1, 1, 14, 0, 0)
        assert _serialize_for_target(dt, "datetime", "sqlite") == "2026-01-01 14:00:00"
        assert _serialize_for_target(dt, "datetime", "mysql") == dt
        assert _serialize_for_target(dt, "datetime", "postgresql") is dt

    def test_datetime_aware_normalized_to_naive(self):
        aware = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
        assert _serialize_for_target(aware, "datetime", "sqlite") == "2026-01-01 09:00:00"
        assert _serialize_for_target(aware, "datetime", "mysql") == datetime(2026, 1, 1, 9, 0, 0)

    def test_bool_targets(self):
        assert _serialize_for_target(True, "bool", "sqlite") == 1
        assert _serialize_for_target(True, "bool", "mysql") == 1
        assert _serialize_for_target(True, "bool", "postgresql") is True

    def test_numeric_targets(self):
        assert _serialize_for_target(Decimal("10.50"), "numeric", "sqlite") == "10.50"
        assert _serialize_for_target(Decimal("10.50"), "numeric", "mysql") == Decimal("10.50")
        assert _serialize_for_target(Decimal("10.50"), "numeric", "postgresql") == Decimal("10.50")

    def test_str_from_jsonb_like_value(self):
        assert _normalize_value({"a": 1}, "str") == '{"a": 1}'

    def test_json_from_str(self):
        assert _normalize_value('{"a": 1}', "json") == {"a": 1}

    def test_json_passthrough(self):
        assert _normalize_value({"a": 1}, "json") == {"a": 1}

    def test_json_targets(self):
        assert _serialize_for_target({"a": 1}, "json", "sqlite") == '{"a": 1}'
        assert _serialize_for_target({"a": 1}, "json", "mysql") == '{"a": 1}'
        assert _serialize_for_target({"a": 1}, "json", "postgresql") == {"a": 1}

    def test_blob(self):
        assert _normalize_value(b"x", "blob") == b"x"
        assert _normalize_value(memoryview(b"x"), "blob") == b"x"


@pytest.fixture
async def src():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


@pytest.fixture
async def dst():
    d = SqliteDb()
    await d.connect(database=":memory:")
    yield d
    await d.close()


class TestCopyTable:
    @pytest.mark.asyncio
    async def test_copy_creates_and_copies(self, src, dst):
        await src.execute(
            Query(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "nombre TEXT, edad INTEGER, activo INTEGER, creado TEXT)",
                [],
            )
        )
        await src.execute(
            Query(
                "INSERT INTO users (nombre, edad, activo, creado) "
                "VALUES ('Ana', 30, 1, '2026-09-07')",
                [],
            )
        )
        await src.execute(
            Query(
                "INSERT INTO users (nombre, edad, activo, creado) "
                "VALUES ('Bob', 25, 0, '2026-09-08')",
                [],
            )
        )

        assert await copy_table(src, dst, "users", create=True) == 2

        rows = await dst.fetch_all(Query("SELECT * FROM users ORDER BY id", []))
        assert [r["nombre"] for r in rows] == ["Ana", "Bob"]
        assert [r["edad"] for r in rows] == [30, 25]
        assert [r["activo"] for r in rows] == [1, 0]
        assert [r["creado"] for r in rows] == ["2026-09-07", "2026-09-08"]

    @pytest.mark.asyncio
    async def test_truncate(self, src, dst):
        await src.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )
        await src.execute(Query("INSERT INTO t (v) VALUES ('x')", []))
        await dst.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )
        await dst.execute(Query("INSERT INTO t (v) VALUES ('old')", []))

        await copy_table(src, dst, "t", truncate=True)
        rows = await dst.fetch_all(Query("SELECT v FROM t", []))
        assert [r["v"] for r in rows] == ["x"]

    @pytest.mark.asyncio
    async def test_copy_json_column(self, src, dst):
        await src.execute(
            Query("CREATE TABLE docs (id INTEGER PRIMARY KEY AUTOINCREMENT, payload JSON)", [])
        )
        await src.execute(Query("INSERT INTO docs (payload) VALUES ('{\"a\": 1}')", []))

        assert await copy_table(src, dst, "docs", create=True) == 1
        rows = await dst.fetch_all(Query("SELECT payload FROM docs", []))
        assert rows[0]["payload"] == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_preserve_ids_false_drops_auto_pk(self, src, dst):
        await src.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )
        await src.execute(Query("INSERT INTO t (v) VALUES ('x')", []))
        await dst.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )

        await copy_table(src, dst, "t", preserve_ids=False)
        rows = await dst.fetch_all(Query("SELECT * FROM t", []))
        assert len(rows) == 1
        assert rows[0]["v"] == "x"

    @pytest.mark.asyncio
    async def test_copy_table_por_lotes_equivale_fila_a_fila(self, src, dst):
        # 4 columnas de datos (str/int/float/bool + datetime como TEXT), mismo
        # criterio de tipos que el resto de tests de transfer.
        await src.execute(
            Query(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "nombre TEXT, edad INTEGER, monto REAL, activo INTEGER, creado TEXT)",
                [],
            )
        )
        for i in range(2_500):
            await src.execute(
                Query(
                    "INSERT INTO users (nombre, edad, monto, activo, creado) "
                    "VALUES ({0},{1},{2},{3},{4})",
                    [
                        f"usuario-{i}",
                        i % 90,
                        i / 10.0,
                        i % 2,
                        f"2026-09-{i % 28 + 1:02d} 10:00:00",
                    ],
                )
            )
        # MAX_PARAMS de sqlite es 32766 y MAX_ROWS 1000: 4 columnas → chunk 1000,
        # así que la copia va en 3 lotes multi-VALUES (y sigue siendo correcta).
        assert await copy_table(src, dst, "users", create=True, truncate=True) == 2_500

        src_rows = await src.fetch_all(Query("SELECT * FROM users ORDER BY id", []))
        dst_rows = await dst.fetch_all(Query("SELECT * FROM users ORDER BY id", []))
        assert len(dst_rows) == 2_500
        cols = await columns_of(src, "users")
        for s, d in zip(src_rows, dst_rows, strict=True):
            for col in cols:
                assert _normalize_value(d[col.name], col.datatype) == _normalize_value(
                    s[col.name], col.datatype
                )
        # ids preservados con preserve_ids=True (default).
        assert [r["id"] for r in dst_rows] == [r["id"] for r in src_rows]

    @pytest.mark.asyncio
    async def test_lotes_respetan_MAX_PARAMS(self, src):
        await src.execute(
            Query(
                "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT, b INTEGER, c TEXT)",
                [],
            )
        )
        for i in range(25):
            await src.execute(
                Query(
                    "INSERT INTO t (a, b, c) VALUES ({0},{1},{2})",
                    [f"fila-{i}", i, f"x{i}"],
                )
            )
        spy = FakeDb(dialect="sqlite", max_params=8, max_rows=1_000_000)
        assert await copy_table(src, spy, "t", preserve_ids=False) == 25

        inserts = [q for q in spy.executes if q.sql_template.startswith("INSERT")]
        assert len(inserts) == _ceil(25 / 2)  # chunk = 8 // 3 = 2
        for q in inserts:
            # El lote tiene <= 2 filas → <= 6 parámetros (3 columnas por fila).
            assert len(q.params) <= 6
        assert sum(len(q.params) // 3 for q in inserts) == 25
        # Orden de filas preservado en el encadenado de params.
        passthrough = [v for q in inserts for v in q.fields]
        assert passthrough == [v for i in range(25) for v in (f"fila-{i}", i, f"x{i}")]

    @pytest.mark.asyncio
    async def test_lotes_respetan_MAX_ROWS(self, src):
        await src.execute(
            Query(
                "CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT, b INTEGER, c TEXT)",
                [],
            )
        )
        for i in range(10):
            await src.execute(
                Query(
                    "INSERT INTO t (a, b, c) VALUES ({0},{1},{2})",
                    [f"fila-{i}", i, f"x{i}"],
                )
            )
        spy = FakeDb(dialect="sqlite", max_params=1_000_000, max_rows=3)
        assert await copy_table(src, spy, "t", preserve_ids=False) == 10

        inserts = [q for q in spy.executes if q.sql_template.startswith("INSERT")]
        assert len(inserts) == 4  # ceil(10 / 3)
        assert all(len(q.params) <= 9 for q in inserts)  # <= 3 filas x 3 cols
        assert sum(len(q.params) // 3 for q in inserts) == 10

    @pytest.mark.asyncio
    async def test_copy_table_vacia(self, src):
        await src.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )
        spy = FakeDb()
        assert await copy_table(src, spy, "t") == 0
        inserts = [q for q in spy.executes if q.sql_template.startswith("INSERT")]
        assert inserts == []

    @pytest.mark.asyncio
    async def test_tabla_solo_auto_pk(self, src, dst):
        # `target_cols == []` (solo PK autoincremental y preserve_ids=False): el
        # multi-VALUES sin columnas no existe. Se inserta una fila DEFAULT por
        # fila origen con SQL específico de dialecto. Regresión MR-01: el camino
        # emitía `INSERT INTO t () VALUES ()` y fallaba con error de sintaxis en
        # SqliteDb real (el test anterior lo pinaba con un doble).
        await src.execute(Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)", []))
        for _i in range(3):
            await src.execute(Query("INSERT INTO t DEFAULT VALUES", []))
        assert await copy_table(src, dst, "t", create=True, preserve_ids=False) == 3
        rows = await dst.fetch_all(Query("SELECT id FROM t ORDER BY id", []))
        assert [r["id"] for r in rows] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_mas_columnas_que_MAX_PARAMS_degradan_a_fila_a_fila(self, src):
        # LR-01: `batch_size` devuelve 0 (ni una fila cabe en lote: 3 columnas
        # con MAX_PARAMS=2). La copia degrada al insert de fila única, donde la
        # sentencia lleva exactamente las 3 columnas y se respeta el límite.
        await src.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, a TEXT, b TEXT, c TEXT)", [])
        )
        for i in range(3):
            await src.execute(
                Query("INSERT INTO t (a, b, c) VALUES ({0},{1},{2})", [f"a{i}", f"b{i}", f"c{i}"])
            )
        spy = FakeDb(dialect="sqlite", max_params=2, max_rows=1000)
        assert await copy_table(src, spy, "t", preserve_ids=False) == 3
        inserts = [q for q in spy.executes if q.sql_template.startswith("INSERT")]
        assert len(inserts) == 3  # una sentencia por fila
        assert all(q.sql_template.startswith("INSERT INTO t (a,b,c)") for q in inserts)
        assert all(len(q.params) == 3 for q in inserts)

    @pytest.mark.asyncio
    async def test_error_propagado(self, src):
        await src.execute(
            Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)", [])
        )
        for i in range(3):
            await src.execute(Query("INSERT INTO t (v) VALUES ({0})", [f"v{i}"]))
        spy = FakeDb(fail_at=2)  # falla en el primer INSERT (el execute 1 es el DELETE)
        with pytest.raises(RuntimeError, match="fallo simulado"):
            await copy_table(src, spy, "t", truncate=True)
        assert "begin" in spy.events
        assert "rollback" in spy.events
        assert "commit" not in spy.events


def _ceil(x):
    """Entero más pequeño >= x (evita `import math` para un solo uso)."""
    return int(x) if x == int(x) else int(x) + 1


class TestCopyDatabase:
    @pytest.mark.asyncio
    async def test_copies_all_tables(self, src, dst):
        await src.execute(
            Query("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)", [])
        )
        await src.execute(
            Query("CREATE TABLE b (id INTEGER PRIMARY KEY AUTOINCREMENT, y INTEGER)", [])
        )
        await src.execute(Query("INSERT INTO a (x) VALUES ('uno')", []))
        await src.execute(Query("INSERT INTO b (y) VALUES (7)", []))

        result = await copy_database(src, dst, create=True)
        assert result == {"a": 1, "b": 1}

        assert (await dst.fetch_all(Query("SELECT x FROM a", [])))[0]["x"] == "uno"
        assert (await dst.fetch_all(Query("SELECT y FROM b", [])))[0]["y"] == 7

    @pytest.mark.asyncio
    async def test_subset_of_tables(self, src, dst):
        await src.execute(
            Query("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, x TEXT)", [])
        )
        await src.execute(
            Query("CREATE TABLE b (id INTEGER PRIMARY KEY AUTOINCREMENT, y INTEGER)", [])
        )
        await src.execute(Query("INSERT INTO a (x) VALUES ('uno')", []))
        await src.execute(Query("INSERT INTO b (y) VALUES (7)", []))

        result = await copy_database(src, dst, tables=["a"], create=True)
        assert result == {"a": 1}

    @pytest.mark.asyncio
    async def test_missing_table_raises(self, src, dst):
        with pytest.raises(ValueError):
            await copy_table(src, dst, "inexistente")


class TestCliCopy:
    def test_end_to_end(self, tmp_path):
        src_file = tmp_path / "src.db"
        dst_file = tmp_path / "dst.db"

        async def _setup():
            d = SqliteDb()
            await d.connect(database=str(src_file))
            await d.execute(
                Query("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT)", [])
            )
            await d.execute(Query("INSERT INTO t (nombre) VALUES ('Héctor')", []))
            await d.commit()
            await d.close()

        asyncio.run(_setup())

        code = main(
            [
                "copy",
                "sqlite",
                "sqlite",
                "--src-database",
                str(src_file),
                "--dst-database",
                str(dst_file),
                "--create",
            ]
        )
        assert code == 0

        async def _check():
            d = SqliteDb()
            await d.connect(database=str(dst_file))
            rows = await d.fetch_all(Query("SELECT * FROM t", []))
            await d.close()
            return rows

        rows = asyncio.run(_check())
        assert len(rows) == 1
        assert rows[0]["nombre"] == "Héctor"
