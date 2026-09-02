import pytest

from encinorm import Engine, PoolDb, SqliteDb, Weekday, create_db
from encinorm.query import Query
from encinorm.sql import SqlFunctions


def _f(engine):
    return SqlFunctions(engine)


def test_now():
    assert _f("sqlite").now() == "datetime('now')"
    assert _f("mysql").now() == "NOW()"
    assert _f("postgresql").now() == "now()"


def test_date_add_sub():
    assert _f("sqlite").date_add("d", 1, "day") == "datetime(d, '+1 day')"
    assert _f("sqlite").date_sub("d", 1, "day") == "datetime(d, '-1 day')"
    assert _f("mysql").date_add("d", 1, "day") == "DATE_ADD(d, INTERVAL 1 DAY)"
    assert _f("mysql").date_sub("d", 1, "day") == "DATE_SUB(d, INTERVAL 1 DAY)"
    assert _f("postgresql").date_add("d", 1, "day") == "d + INTERVAL '1 day'"
    assert _f("postgresql").date_sub("d", 1, "day") == "d - INTERVAL '1 day'"


def test_date_add_invalid_unit():
    with pytest.raises(ValueError):
        _f("sqlite").date_add("d", 1, "fortnight")


def test_date_parts():
    assert _f("sqlite").year("d") == "CAST(strftime('%Y', d) AS INTEGER)"
    assert _f("mysql").month("d") == "MONTH(d)"
    assert _f("postgresql").day("d") == "EXTRACT(DAY FROM d)"
    assert _f("sqlite").hour("d") == "CAST(strftime('%H', d) AS INTEGER)"


def test_weekday():
    assert _f("sqlite").weekday("d") == "((CAST(strftime('%w', d) AS INTEGER) + 6) % 7)"
    assert _f("mysql").weekday("d") == "WEEKDAY(d)"
    assert _f("postgresql").weekday("d") == "EXTRACT(ISODOW FROM d) - 1"


def test_string():
    assert _f("sqlite").length("d") == "length(d)"
    assert _f("mysql").length("d") == "CHAR_LENGTH(d)"
    assert _f("postgresql").length("d") == "length(d)"
    assert _f("sqlite").substring("d", 1, 3) == "substr(d, 1, 3)"
    assert _f("mysql").substring("d", 1, 3) == "SUBSTRING(d, 1, 3)"
    assert _f("postgresql").substring("d", 1, 3) == "substring(d from 1 for 3)"
    assert _f("postgresql").substring("d", 1) == "substring(d from 1)"
    assert _f("sqlite").concat("a", "b") == "a || b"
    assert _f("mysql").concat("a", "b") == "CONCAT(a, b)"


def test_other():
    assert _f("sqlite").random() == "RANDOM()"
    assert _f("mysql").random() == "RAND()"
    assert _f("mysql").uuid() == "UUID()"
    assert _f("postgresql").uuid() == "gen_random_uuid()"
    with pytest.raises(NotImplementedError):
        _f("sqlite").uuid()


def test_date_format():
    assert _f("sqlite").date_format("d", "%Y-%m-%d") == "strftime('%Y-%m-%d', d)"
    assert _f("mysql").date_format("d", "%Y-%m-%d") == "DATE_FORMAT(d, '%Y-%m-%d')"
    assert _f("postgresql").date_format("d", "YYYY-MM-DD") == "to_char(d, 'YYYY-MM-DD')"


def test_weekday_enum():
    assert Weekday.MONDAY == 0
    assert Weekday.SUNDAY == 6
    assert int(Weekday.FRIDAY) == 4


def test_db_fn():
    assert SqliteDb().fn.now() == "datetime('now')"
    assert PoolDb("mysql").fn.date_add("d", 1, "day") == "DATE_ADD(d, INTERVAL 1 DAY)"


async def test_fn_executes_on_sqlite():
    db = await create_db("sqlite", database=":memory:")
    try:
        rows = await db.fetch_all(Query(f"SELECT {db.fn.now()} AS n", []))
        assert rows and rows[0]["n"]
    finally:
        await db.close()


async def test_fn_date_arithmetic_integration():
    from datetime import datetime

    db = await create_db("sqlite", database=":memory:")
    try:
        await db.execute(Query("CREATE TABLE ev (id INTEGER PRIMARY KEY, fecha TEXT)", []))
        for fecha in ["2026-01-01", "2026-02-01", "2026-03-01"]:
            await db.execute(db.insert("ev", {"fecha": f"{fecha} 00:00:00"}))

        # date_sub sobre una columna real
        rows = await db.fetch_all(Query(
            f"SELECT id, {db.fn.date_sub('fecha', 1, 'month')} AS prev FROM ev ORDER BY id", []
        ))
        assert [r["prev"] for r in rows] == [
            "2025-12-01 00:00:00", "2026-01-01 00:00:00", "2026-02-01 00:00:00"
        ]

        # date_add sobre una columna real
        rows = await db.fetch_all(Query(
            f"SELECT id, {db.fn.date_add('fecha', 1, 'day')} AS nxt FROM ev WHERE id = 1", []
        ))
        assert rows[0]["nxt"] == "2026-01-02 00:00:00"

        # weekday normalizado (0=lunes)
        rows = await db.fetch_all(Query(
            f"SELECT {db.fn.weekday('fecha')} AS wd FROM ev WHERE id = 1", []
        ))
        assert rows[0]["wd"] == datetime(2026, 1, 1).weekday()

        # partes de fecha
        rows = await db.fetch_all(Query(
            f"SELECT {db.fn.year('fecha')} AS y, {db.fn.month('fecha')} AS m FROM ev WHERE id = 1", []
        ))
        assert rows[0]["y"] == 2026
        assert rows[0]["m"] == 1
    finally:
        await db.close()


def test_filter_raw_with_fn():
    from encinorm.model import Filter

    db = SqliteDb()
    sql, params = Filter.raw(f"created_at > {db.fn.now()}", []).to_sql()
    assert sql == "created_at > datetime('now')"
    assert params == []

