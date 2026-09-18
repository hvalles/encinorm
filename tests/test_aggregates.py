from pathlib import Path

import pytest

from encino_orm.model import Filter, Model, QueryBuilder
from encino_orm.sqlite import SqliteDb

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Claves de indexación por TEXTO DE EXPRESIÓN que introducía el bug del label.
# El alias fijo `AS n` es el único contrato estable entre motores: asyncpg
# devuelve el label en minúsculas y `_rows.py` las fuerza para MSSQL/Oracle.
_CLAVES_PROHIBIDAS = (
    'row["COUNT(*)"]',
    'row[f"SUM(',
    'row[f"AVG(',
    'row[f"MIN(',
    'row[f"MAX(',
)


class Venta(Model):
    _table = "ventas"
    monto: float | None = None
    region_id: int | None = None


class _RecordingDb:
    """Db mínima: registra los `Query` recibidos y devuelve siempre una fila.

    Permite fijar la FORMA del SQL de cada agregado (que debe aliasar `AS n`)
    sin depender de ningún motor.
    """

    def __init__(self, row):
        self.row = row
        self.queries = []

    async def fetch_one(self, qry):
        self.queries.append(qry)
        return self.row


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Venta(d).create_table()
    yield d
    await d.close()


class TestAggregates:
    @pytest.mark.asyncio
    async def test_avg_min_max(self, db):
        for monto, rid in [(10.0, 1), (20.0, 1), (30.0, 2)]:
            await Venta(db, monto=monto, region_id=rid).insert()

        q = Venta(db).query().where(Filter.eq("region_id", 1))
        assert await q.sum("monto") == 30.0
        assert await q.avg("monto") == 15.0
        assert await q.min("monto") == 10.0
        assert await q.max("monto") == 20.0

    @pytest.mark.asyncio
    async def test_aggregates_empty_return_none(self, db):
        q = Venta(db).query().where(Filter.eq("region_id", 999))
        assert await q.avg("monto") is None
        assert await q.min("monto") is None
        assert await q.max("monto") is None

    @pytest.mark.asyncio
    async def test_invalid_column_raises(self, db):
        q = Venta(db).query()
        with pytest.raises(ValueError):
            await q.max("monto; DROP TABLE ventas")


class TestAggregateResultAlias:
    """DIAL-03: los siete lectores leen `row["n"]` de una expresión `AS n`."""

    @pytest.mark.asyncio
    async def test_model_count_aliases_as_n(self):
        fake = _RecordingDb({"n": 3})
        assert await Venta(fake).count() == 3
        assert "SELECT COUNT(*) AS n FROM ventas" in fake.queries[0].sql_template

    @pytest.mark.asyncio
    async def test_query_builder_aggregates_alias_as_n(self):
        fake = _RecordingDb({"n": 7})
        qb = QueryBuilder(Venta, fake)

        assert await qb.count() == 7
        assert "SELECT COUNT(*) AS n" in fake.queries[-1].sql_template

        assert await qb.sum("monto") == 7
        assert "SELECT SUM(monto) AS n" in fake.queries[-1].sql_template

        assert await qb.avg("monto") == 7
        assert "SELECT AVG(monto) AS n" in fake.queries[-1].sql_template

        assert await qb.min("monto") == 7
        assert "SELECT MIN(monto) AS n" in fake.queries[-1].sql_template

        assert await qb.max("monto") == 7
        assert "SELECT MAX(monto) AS n" in fake.queries[-1].sql_template

    @pytest.mark.asyncio
    async def test_empty_aggregate_semantics_are_preserved(self):
        fake = _RecordingDb({"n": None})
        qb = QueryBuilder(Venta, fake)
        assert await qb.sum("monto") == 0
        assert await qb.avg("monto") is None
        assert await qb.min("monto") is None
        assert await qb.max("monto") is None

    @pytest.mark.asyncio
    async def test_model_count_and_paginate_on_sqlite(self, db):
        for monto, rid in [(10.0, 1), (20.0, 1), (30.0, 2)]:
            await Venta(db, monto=monto, region_id=rid).insert()

        assert await Venta(db).count() == 3
        assert await Venta(db).count(Filter.eq("region_id", 1)) == 2

        rec = await Venta(db).paginate(Filter.eq("region_id", 1), limit=1, page=1)
        assert rec.total == 2
        assert len(rec.rows) == 1
        assert rec.limit == 1
        assert rec.page == 1

    def test_no_aggregate_reader_indexes_by_expression_text(self):
        offenders = []
        for path in sorted((_REPO_ROOT / "encino_orm").rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for clave in _CLAVES_PROHIBIDAS:
                if clave in text:
                    offenders.append(f"{path.relative_to(_REPO_ROOT).as_posix()}: {clave}")
        assert offenders == [], f"lectores de agregados por texto de expresión: {offenders}"
