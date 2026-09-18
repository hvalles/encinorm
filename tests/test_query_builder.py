import inspect
import pathlib

import pytest
from pydantic import Field, create_model

from encino_orm.model import DuplicateAliasError, Filter, Model, QueryBuilder, col
from encino_orm.query import Query


class _RecordingDb:
    """Db mínima que registra los `Query` y devuelve una fila fija."""

    def __init__(self, row):
        self.row = row
        self.queries = []

    async def fetch_one(self, qry):
        self.queries.append(qry)
        return self.row

    async def fetch_all(self, qry, *args, **kwargs):
        self.queries.append(qry)
        return [self.row]

    async def fetch_many(self, qry, limit, page=1):
        self.queries.append(qry)
        return [self.row]


class _RecordingDbPaginado:
    """Doble que registra la delegación de paginación en el adaptador (WR-03).

    Separa `fetch_all`/`fetch_one`/`fetch_many` para poder afirmar CUÁL se usó y
    con qué `(limit, page)`, sin `unittest.mock`.
    """

    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [{"nombre": "Ana"}]
        self.fetch_all_calls = []
        self.fetch_one_calls = []
        self.fetch_many_calls = []

    async def fetch_all(self, qry, *args, **kwargs):
        self.fetch_all_calls.append(qry)
        return self.rows

    async def fetch_one(self, qry):
        self.fetch_one_calls.append(qry)
        return self.rows[0] if self.rows else None

    async def fetch_many(self, qry, limit, page=1):
        self.fetch_many_calls.append((qry, limit, page))
        return self.rows


class Region(Model):
    _table = "regiones"
    region: str | None = Field(default=None)


class Agente(Model):
    _table = "agentes"
    agente: str | None = Field(default=None)
    region_id: int | None = None
    monto: float = 0.0


REGION_DDL = (
    "CREATE TABLE regiones (id INTEGER PRIMARY KEY AUTOINCREMENT, region TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)
AGENTE_DDL = (
    "CREATE TABLE agentes (id INTEGER PRIMARY KEY AUTOINCREMENT, agente TEXT, "
    "region_id INTEGER, monto REAL, enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(REGION_DDL, []))
    await connected_db.execute(Query(AGENTE_DDL, []))
    return connected_db


async def _seed(db):
    rid1 = await Region(db, region="Norte").insert()
    rid2 = await Region(db, region="Sur").insert()
    await Agente(db, agente="Ana", region_id=rid1, monto=10).insert()
    await Agente(db, agente="Luis", region_id=rid2, monto=50).insert()
    return rid1, rid2


class TestQueryBuilder:
    @pytest.mark.asyncio
    async def test_where_and_select(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).where(Filter.eq("enabled", 1)).select("agente").all()
        assert sorted(r["agente"] for r in rows) == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_join(self, db):
        await _seed(db)
        qb = QueryBuilder(Agente, db)
        qb.join(Region, "r", Filter.eq("mm.region_id", col("r.id")))
        rows = await qb.select("mm.agente", "r.region").where(Filter.eq("r.region", "Norte")).all()
        assert rows == [{"agente": "Ana", "region": "Norte"}]

    @pytest.mark.asyncio
    async def test_column_alias(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente AS nombre").order_by("agente").all()
        assert [r["nombre"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_order_and_limit_pagination(self, db):
        await _seed(db)
        p1 = await QueryBuilder(Agente, db).select("agente").order_by("agente").limit(1).all()
        p2 = (
            await QueryBuilder(Agente, db)
            .select("agente")
            .order_by("agente")
            .limit(1, page=2)
            .all()
        )
        assert [r["agente"] for r in p1] == ["Ana"]
        assert [r["agente"] for r in p2] == ["Luis"]

    @pytest.mark.asyncio
    async def test_count_sum_exists(self, db):
        await _seed(db)
        assert await QueryBuilder(Agente, db).count() == 2
        assert await QueryBuilder(Agente, db).sum("monto") == 60.0
        assert await QueryBuilder(Agente, db).avg("monto") == 30.0
        assert await QueryBuilder(Agente, db).min("monto") == 10.0
        assert await QueryBuilder(Agente, db).max("monto") == 50.0
        assert await QueryBuilder(Agente, db).where(Filter.eq("agente", "Ana")).exists() is True
        assert await QueryBuilder(Agente, db).where(Filter.eq("agente", "Zzz")).exists() is False

    @pytest.mark.asyncio
    async def test_aggregate_sql_aliases_as_n(self):
        fake = _RecordingDb({"n": 5})
        qb = QueryBuilder(Agente, fake)

        assert await qb.count() == 5
        assert "COUNT(*) AS n" in fake.queries[-1].sql_template
        assert await qb.sum("monto") == 5
        assert "SUM(monto) AS n" in fake.queries[-1].sql_template
        assert await qb.avg("monto") == 5
        assert "AVG(monto) AS n" in fake.queries[-1].sql_template
        assert await qb.min("monto") == 5
        assert "MIN(monto) AS n" in fake.queries[-1].sql_template
        assert await qb.max("monto") == 5
        assert "MAX(monto) AS n" in fake.queries[-1].sql_template

    @pytest.mark.asyncio
    async def test_join_subquery(self, db):
        await _seed(db)
        sub = QueryBuilder(Agente, db).where(Filter.gt("monto", 20))
        qb = QueryBuilder(Agente, db)
        qb.join_subquery(sub, None, Filter.eq("mm.id", col("sq1_mm.id")))
        rows = await qb.select("mm.agente").all()
        assert [r["agente"] for r in rows] == ["Luis"]


class TestSortBy:
    @pytest.mark.asyncio
    async def test_asc_default(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente").all()
        assert [r["agente"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_desc_string(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente desc").all()
        assert [r["agente"] for r in rows] == ["Luis", "Ana"]

    @pytest.mark.asyncio
    async def test_asc_string(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by("agente asc").all()
        assert [r["agente"] for r in rows] == ["Ana", "Luis"]

    @pytest.mark.asyncio
    async def test_tuple_direction(self, db):
        await _seed(db)
        rows = await QueryBuilder(Agente, db).select("agente").sort_by(("agente", "desc")).all()
        assert [r["agente"] for r in rows] == ["Luis", "Ana"]

    @pytest.mark.asyncio
    async def test_multiple_fields(self, db):
        await _seed(db)
        rows = (
            await QueryBuilder(Agente, db)
            .select("region_id", "agente")
            .sort_by("region_id desc", "agente")
            .all()
        )
        assert [r["region_id"] for r in rows] == [2, 1]

    @pytest.mark.asyncio
    async def test_invalid_direction(self, db):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, db).sort_by("agente sideways")


class TestPaginacionDelegadaAlAdaptador:
    """WR-03: `all`/`first`/`exists` delegan la paginación en el adaptador.

    `LIMIT`/`OFFSET` no es sintaxis válida en SQL Server ni en Oracle (usan
    `OFFSET … FETCH NEXT`); el SQL del core no debe contener un `LIMIT` en línea.
    """

    @pytest.mark.asyncio
    async def test_all_con_limit_no_emite_limit_inline(self):
        fake = _RecordingDbPaginado()
        rows = await QueryBuilder(Agente, fake).limit(2, page=3).all()
        assert rows == [{"nombre": "Ana"}]
        assert len(fake.fetch_many_calls) == 1
        qry, limit, page = fake.fetch_many_calls[0]
        assert (limit, page) == (2, 3)
        assert "LIMIT" not in qry.sql_template
        assert "OFFSET" not in qry.sql_template
        assert fake.fetch_all_calls == []

    @pytest.mark.asyncio
    async def test_first_no_emite_limit_inline(self):
        fake = _RecordingDbPaginado()
        row = await QueryBuilder(Agente, fake).first()
        assert row == {"nombre": "Ana"}
        assert len(fake.fetch_one_calls) == 1
        assert "LIMIT" not in fake.fetch_one_calls[0].sql_template

    @pytest.mark.asyncio
    async def test_exists_no_emite_limit_inline(self):
        fake = _RecordingDbPaginado()
        assert await QueryBuilder(Agente, fake).exists() is True
        assert len(fake.fetch_one_calls) == 1
        assert "LIMIT" not in fake.fetch_one_calls[0].sql_template

        fake_vacio = _RecordingDbPaginado(rows=[])
        assert await QueryBuilder(Agente, fake_vacio).exists() is False

    @pytest.mark.asyncio
    async def test_all_sin_limit_sigue_usando_fetch_all(self):
        fake = _RecordingDbPaginado()
        await QueryBuilder(Agente, fake).all()
        assert len(fake.fetch_all_calls) == 1
        assert fake.fetch_many_calls == []


class TestAliasInjection:
    """Regresión de CR-01: ningún alias llega a `FROM`/`JOIN` sin validar.

    Reproduce el payload literal del informe de verificación (una primitiva de
    inyección SQL por el parámetro público `alias=`) y prueba que ahora lanza
    `ValueError` antes de construir SQL y sin alcanzar el driver.
    """

    def test_alias_con_inyeccion_en_constructor_lanza(self):
        with pytest.raises(ValueError) as exc:
            QueryBuilder(Agente, None, alias="mm WHERE 1=0 UNION SELECT nombre FROM usuarios --")
        assert "alias inválido" in str(exc.value)

    def test_alias_no_identificador_en_constructor_lanza(self):
        for alias in ["a b", "a.b", "1x", "", "a-b", None]:
            with pytest.raises(ValueError):
                QueryBuilder(Agente, None, alias=alias)

    def test_join_con_alias_inyectado_lanza(self):
        # `join` es puro: no necesita conexión para validar el alias.
        qb = QueryBuilder(Agente, None)
        with pytest.raises(ValueError):
            qb.join(Region, "a b", Filter.eq("mm.region_id", col("r.id")))

    def test_join_subquery_con_alias_inyectado_lanza(self):
        sub = QueryBuilder(Agente, None)
        qb = QueryBuilder(Agente, None)
        with pytest.raises(ValueError):
            qb.join_subquery(sub, "x; DROP TABLE t --", Filter.eq("mm.id", col("sq1_mm.id")))

    def test_alias_por_defecto_y_autogenerado_siguen_validos(self):
        assert QueryBuilder(Agente, None)._build_base()[0] == "FROM agentes mm"
        sub = QueryBuilder(Agente, None)
        qb = QueryBuilder(Agente, None)
        qb.join_subquery(sub, None, Filter.eq("mm.id", col("sq1_mm.id")))
        sql, _ = qb._build_base()
        assert "JOIN (SELECT * FROM agentes mm) sq1_mm ON" in sql

    @pytest.mark.asyncio
    async def test_el_driver_nunca_se_alcanza_con_alias_hostil(self):
        fake = _RecordingDb({"id": 1})
        with pytest.raises(ValueError):
            await QueryBuilder(
                Agente, fake, alias="mm WHERE 1=0 UNION SELECT nombre FROM usuarios --"
            ).all()
        assert fake.queries == []

    def test_alias_duplicado_sigue_lanzando_duplicate_alias_error(self):
        qb = QueryBuilder(Agente, None)
        qb.join(Region, "r", Filter.eq("mm.region_id", col("r.id")))
        with pytest.raises(DuplicateAliasError):
            qb.join(Region, "r", Filter.eq("mm.region_id", col("r.id")))


class TestTablaInjection:
    """Regresión de CR-01 (ronda 2): ningún `_table` llega a `FROM`/`JOIN` sin validar.

    La ronda anterior cerró el vector público `alias=`, pero `_build_base()`
    seguía interpolando `self._model_class._table` (y cada `_table` de destino de
    `join`) sin pasar por la allowlist estricta: `Model._table` solo se validaba
    dentro de `Model._build_column_map()`, que `QueryBuilder` nunca dispara. El
    escenario real es el de los modelos dinámicos/code-generated
    (`create_model`, `introspection.generate_model`), no una constante escrita a
    mano. Se reproduce el payload literal del informe de verificación.
    """

    @staticmethod
    def _modelo_tabla_hostil():
        M = create_model("Evil", __base__=Model, **{"nombre": (str | None, None)})
        M._table = "t; DROP TABLE usuarios --"
        return M

    def test_tabla_con_inyeccion_en_constructor_lanza(self):
        Evil = self._modelo_tabla_hostil()
        with pytest.raises(ValueError) as exc:
            QueryBuilder(Evil, None)
        assert "nombre de tabla inválido" in str(exc.value)
        assert repr("t; DROP TABLE usuarios --") in str(exc.value)

    def test_tabla_hostil_en_join_lanza(self):
        # El alias `h` es válido a propósito: el fallo solo puede venir del `_table`.
        Evil = self._modelo_tabla_hostil()
        qb = QueryBuilder(Agente, None)
        with pytest.raises(ValueError) as exc:
            qb.join(Evil, "h", Filter.eq("mm.agente", col("h.agente")))
        assert "nombre de tabla inválido" in str(exc.value)

    def test_tabla_no_identificador_en_constructor_lanza(self):
        for table in ["a b", "a.b", "1x", "", "a-b", None, "t;--"]:
            M = create_model("Evil", __base__=Model, **{"nombre": (str | None, None)})
            M._table = table
            with pytest.raises(ValueError):
                QueryBuilder(M, None)

    @pytest.mark.asyncio
    async def test_el_driver_nunca_se_alcanza_con_tabla_hostil(self):
        Evil = self._modelo_tabla_hostil()
        fake = _RecordingDb({"id": 1})
        with pytest.raises(ValueError):
            await QueryBuilder(Evil, fake).all()
        assert fake.queries == []

    def test_tabla_valida_sigue_byte_identica(self):
        assert QueryBuilder(Agente, None)._build_base()[0] == "FROM agentes mm"
        qb = QueryBuilder(Agente, None)
        qb.join(Region, "r", Filter.eq("mm.region_id", col("r.id")))
        sql, _ = qb._build_base()
        assert "JOIN regiones r ON" in sql

    def test_tabla_hostil_en_subquery_no_construye(self):
        # La subquery se valida en su PROPIO constructor: no puede inyectarse por
        # `join_subquery` porque el `QueryBuilder` hostil ni siquiera se construye.
        Evil = self._modelo_tabla_hostil()
        with pytest.raises(ValueError):
            QueryBuilder(Evil, None)


class TestBarridoDeIdentificadores:
    """Barrido CR-01 (ronda 2): evidencia de que `_table` era el último punto.

    Las posiciones de EXPRESIÓN (`select`/`group_by`/`order_by`/`sort_by` y los
    agregados) usan `_safe_column` con `_COLUMN_RE`, que a propósito SÍ acepta
    puntos para expresiones calificadas (`mm.agente`). Es una allowlist DISTINTA
    de la estricta y NO se unifica (Pitfall 10: unificar sería un cambio de
    comportamiento y relajarla reabriría la superficie de inyección). Este barrido
    fija esa decisión y confirma que `_table` era el único punto que necesitaba la
    allowlist estricta.
    """

    HOSTIL = "x; DROP TABLE t --"

    def test_select_rechaza_expresion_hostil(self):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, None).select(self.HOSTIL)

    def test_select_acepta_columna_calificada(self):
        qb = QueryBuilder(Agente, None).select("mm.agente")
        assert qb._render_select() == "mm.agente"

    def test_group_by_y_order_by_rechazan_expresion_hostil(self):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, None).group_by("x;--")
        with pytest.raises(ValueError):
            QueryBuilder(Agente, None).order_by("x;--")

    def test_group_by_y_order_by_aceptan_columna_calificada(self):
        qb = QueryBuilder(Agente, None).group_by("mm.agente").order_by("mm.agente")
        sql, _ = qb._build_full()
        assert "GROUP BY mm.agente" in sql
        assert "ORDER BY mm.agente" in sql

    def test_sort_by_rechaza_expresion_hostil(self):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, None).sort_by("x;--")

    def test_sort_by_valido_produce_direccion(self):
        qb = QueryBuilder(Agente, None).sort_by("agente desc")
        sql, _ = qb._build_full()
        assert "ORDER BY agente DESC" in sql

    @pytest.mark.asyncio
    async def test_agregados_rechazan_columna_hostil(self):
        # OJO: `sum/avg/min/max` llaman a `_ensure_db()` ANTES de `_safe_column`.
        # Con `db=None` el `ValueError` lo lanzaría `_ensure_db` y el test pasaría
        # aunque `_safe_column` desapareciera; por eso se usa un fake db y se
        # aserta el MENSAJE concreto de la allowlist de columnas.
        for method in ("sum", "avg", "min", "max"):
            fake = _RecordingDb({"n": 1})
            qb = QueryBuilder(Agente, fake)
            with pytest.raises(ValueError) as exc:
                await getattr(qb, method)("x;--")
            assert "nombre de columna inválido" in str(exc.value)

    def test_alias_de_columna_hostil_rechazado(self):
        with pytest.raises(ValueError):
            QueryBuilder(Agente, None).select("agente AS 'x'")

    def test_build_base_no_interpola_tablas_sin_validar(self):
        fuente = pathlib.Path("encino_orm/model/query_builder.py").read_text(encoding="utf-8")
        # Exactamente dos validaciones de `_table`: constructor y join.
        assert fuente.count('check_identifier(model_class._table, "nombre de tabla")') == 1
        assert fuente.count('check_identifier(other._table, "nombre de tabla")') == 1
        # El FROM/JOIN interpolan las referencias que YA pasaron por la allowlist.
        base = inspect.getsource(QueryBuilder._build_base)
        assert "FROM {self._model_class._table}" in base
        assert "JOIN {join['model_class']._table}" in base

    def test_contrato_de_identificadores_documentado(self):
        fuente = pathlib.Path("encino_orm/model/query_builder.py").read_text(encoding="utf-8")
        assert "Contrato de identificadores del módulo" in fuente
