import pytest

from encino_orm import Engine, PoolDb, SqliteDb, Weekday, create_db
from encino_orm.query import Query
from encino_orm.sql import SqlFunctions


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
    from encino_orm.model import Filter

    db = SqliteDb()
    sql, params = Filter.raw(f"created_at > {db.fn.now()}", []).to_sql()
    assert sql == "created_at > datetime('now')"
    assert params == []


def test_mssql_oracle_functions():
    assert _f("mssql").now() == "GETDATE()"
    assert _f("oracle").now() == "SYSDATE"
    assert _f("mariadb").now() == "NOW()"
    assert _f("mssql").date_add("d", 1, "day") == "DATEADD(day, 1, d)"
    assert _f("mssql").date_sub("d", 1, "day") == "DATEADD(day, -1, d)"
    assert _f("oracle").date_add("d", 1, "day") == "d + INTERVAL '1 day'"
    assert _f("mssql").year("d") == "DATEPART(year, d)"
    assert _f("oracle").month("d") == "EXTRACT(MONTH FROM d)"
    assert _f("mssql").weekday("d") == "((DATEPART(WEEKDAY, d) + @@DATEFIRST - 2) % 7)"
    assert _f("oracle").weekday("d") == "EXTRACT(ISODOW FROM d) - 1"
    assert _f("mssql").length("d") == "LEN(d)"
    assert _f("oracle").length("d") == "length(d)"
    assert _f("mssql").substring("d", 1, 3) == "SUBSTRING(d, 1, 3)"
    assert _f("oracle").substring("d", 1, 3) == "SUBSTR(d, 1, 3)"
    assert _f("mssql").concat("a", "b") == "CONCAT(a, b)"
    assert _f("oracle").concat("a", "b") == "a || b"
    assert _f("mssql").random() == "NEWID()"
    assert _f("oracle").random() == "DBMS_RANDOM.VALUE"
    assert _f("mssql").uuid() == "NEWID()"
    assert _f("oracle").uuid() == "SYS_GUID()"
    assert _f("mssql").date_format("d", "yyyy-MM-dd") == "FORMAT(d, 'yyyy-MM-dd')"
    assert _f("oracle").date_format("d", "YYYY-MM-DD") == "to_char(d, 'YYYY-MM-DD')"


def test_mssql_substring_requires_length():
    with pytest.raises(ValueError):
        _f("mssql").substring("d", 1)


def test_date_diff():
    assert _f("sqlite").date_diff("a", "b", "day") == "((strftime('%s', a) - strftime('%s', b)) / 86400)"
    assert _f("mysql").date_diff("a", "b", "day") == "(TIMESTAMPDIFF(SECOND, b, a) / 86400)"
    assert _f("postgresql").date_diff("a", "b") == "(EXTRACT(EPOCH FROM (a - b)) / 86400)"
    assert _f("mssql").date_diff("a", "b", "hour") == "(DATEDIFF(SECOND, b, a) / 3600)"
    assert _f("oracle").date_diff("a", "b", "day") == "(((CAST(a AS DATE) - CAST(b AS DATE)) * 86400) / 86400)"
    assert _f("sqlite").date_diff("a", "b", "second") == "(strftime('%s', a) - strftime('%s', b))"


def test_date_diff_calendar():
    assert _f("mysql").date_diff("a", "b", "month") == "TIMESTAMPDIFF(MONTH, b, a)"
    assert _f("mssql").date_diff("a", "b", "year") == "DATEDIFF(YEAR, b, a)"
    assert _f("oracle").date_diff("a", "b", "month") == "MONTHS_BETWEEN(a, b)"
    assert _f("oracle").date_diff("a", "b", "year") == "(MONTHS_BETWEEN(a, b) / 12)"
    assert _f("sqlite").date_diff("a", "b", "month") == "CAST((julianday(a) - julianday(b)) / 30.44 AS INTEGER)"
    assert _f("postgresql").date_diff("a", "b", "year") == "EXTRACT(YEAR FROM AGE(a, b))"


def test_date_diff_invalid_unit():
    with pytest.raises(ValueError):
        _f("sqlite").date_diff("a", "b", "fortnight")


def test_group_concat():
    assert _f("sqlite").group_concat("name", ";") == "group_concat(name, ';')"
    assert _f("mysql").group_concat("name", ";") == "GROUP_CONCAT(name SEPARATOR ';')"
    assert _f("postgresql").group_concat("name", ";") == "string_agg(name::text, ';')"
    assert _f("mssql").group_concat("name", ";") == "STRING_AGG(CAST(name AS NVARCHAR(MAX)), ';')"
    assert _f("oracle").group_concat("name", ";") == "LISTAGG(name, ';')"


def test_coalesce_nullif():
    assert _f("sqlite").coalesce("a", "b", 0) == "COALESCE(a, b, 0)"
    assert _f("oracle").coalesce("a", "b") == "COALESCE(a, b)"
    assert _f("mssql").nullif("a", "b") == "NULLIF(a, b)"


def test_lower_upper_ilike():
    assert _f("sqlite").lower("x") == "lower(x)"
    assert _f("oracle").upper("x") == "upper(x)"
    assert _f("postgresql").ilike("name", "%a%") == "name ILIKE '%a%'"
    assert _f("mysql").ilike("name", "%a%") == "LOWER(name) LIKE LOWER('%a%')"
    assert _f("sqlite").ilike("name", "%a%") == "LOWER(name) LIKE LOWER('%a%')"
    assert _f("oracle").ilike("name", "%a%") == "LOWER(name) LIKE LOWER('%a%')"


def test_geo_distance_native():
    assert _f("mysql").geo_distance(1, 2, 3, 4) == "ST_Distance_Sphere(POINT(2, 1), POINT(4, 3))"
    assert _f("mariadb").geo_distance(1, 2, 3, 4) == "ST_Distance_Sphere(POINT(2, 1), POINT(4, 3))"
    assert _f("mssql").geo_distance(1, 2, 3, 4) == (
        "geography::Point(1, 2, 4326).STDistance(geography::Point(3, 4, 4326))"
    )
    assert _f("mysql").geo_distance(1, 2, 3, 4, "km") == "(ST_Distance_Sphere(POINT(2, 1), POINT(4, 3)) / 1000)"


def test_geo_distance_haversine():
    frag = _f("sqlite").geo_distance(1, 2, 3, 4)
    assert "6371000" in frag
    assert "asin(sqrt" in frag
    assert "radians" in frag
    assert _f("oracle").geo_distance(1, 2, 3, 4).count("3.14159265358979323846") == 4


def test_geo_distance_col():
    assert _f("postgresql").geo_distance_col("lat", "lon", 19.43, -99.13, "km") == _f(
        "postgresql"
    ).geo_distance("lat", "lon", 19.43, -99.13, "km")


def test_geo_distance_invalid_unit():
    with pytest.raises(ValueError):
        _f("sqlite").geo_distance(1, 2, 3, 4, "parsec")


def test_filter_geo_within():
    from encino_orm.model import Filter

    f = Filter.geo_within("lat", "lon", 19.43, -99.13, 5)
    sql, params = f.to_sql()
    assert "lat BETWEEN" in sql
    assert "lon BETWEEN" in sql
    assert "AND" in sql
    assert len(params) == 4


def test_column_validation():
    with pytest.raises(ValueError):
        _f("sqlite").lower("x; DROP TABLE t")
    with pytest.raises(ValueError):
        _f("sqlite").date_add("d; DROP", 1, "day")
    with pytest.raises(ValueError):
        _f("postgresql").geo_distance_col("lat; DROP", "lon", 1, 2)
    with pytest.raises(ValueError):
        _f("sqlite").group_concat("name) UNION SELECT 1 --", ";")

    # nombres calificados (alias.columna) siguen siendo válidos
    assert _f("sqlite").lower("t.name") == "lower(t.name)"


async def test_geo_distance_integration_sqlite():
    db = await create_db("sqlite", database=":memory:")
    try:
        rows = await db.fetch_all(Query(f"SELECT {db.fn.geo_distance(0, 0, 0, 1, 'km')} AS d", []))
        assert abs(rows[0]["d"] - 111.195) < 0.5
    finally:
        await db.close()

