"""Contrato SDL y aislamiento de namespace de ``build_schema`` (CFG-03/CFG-04).

Este modulo congela dos propiedades del esquema GraphQL generado:

1. La **SDL** (``schema.as_str()``) es un contrato observable. El snapshot
   ``tests/__snapshots__/test_graphql_namespace.ambr`` se captura CONTRA el
   ``exec()`` que hoy construye ``_pk_resolver`` y debe quedar BYTE-IDÉNTICO
   tras el rewrite a closures + ``__signature__``. Un diff en el ``.ambr``
   significa que el contrato cambio y el rewrite debe corregirse, NUNCA
   regenerar el snapshot.
2. Dos llamadas sucesivas a ``build_schema`` siguen ejecutando relaciones,
   filtros autorreferentes (``and``/``or``/``not``) y mutations, y las
   operaciones por PK (``get``/``update``/``delete``, simple y compuesta)
   se comportan igual.

Flujo de actualizacion del snapshot (tras un cambio DELIBERADO de SDL):

    uv run pytest tests/test_graphql_namespace.py --snapshot-update

y REVISAR el diff del ``.ambr`` antes de commitearlo. Un ``.ambr`` regenerado
sin revisar "bendice" una regresion (T-06-04-01). syrupy es *sound*: un
snapshot ausente FALLA, no se omite, asi que el ``.ambr`` va en el MISMO commit
que este fichero y ANTES de tocar ``encino_orm/graphql/schema.py``.
"""

import sys
from typing import ClassVar

import pytest

import encino_orm.graphql.schema as schema_mod
from encino_orm.graphql import build_schema
from encino_orm.model import Model
from encino_orm.sqlite import SqliteDb
from tests.test_graphql import Agente, Region


class Ciudad(Model):
    """Tercer modelo, usado para ejercitar un segundo build con tipos distintos."""

    _table = "ciudades"
    ciudad: str | None = None


class Sonda(Model):
    """Modelo sonda: ningun otro build lo registra, para aislar la no-mutacion."""

    _table = "sondas"
    sonda: str | None = None


class Membresia(Model):
    """PK compuesta (patron de ``tests/test_pk.py``) para las operaciones por PK."""

    _table = "membresias"
    _primary_key = ("tenant_id", "code")
    _fields_disabled: ClassVar[list] = ["id"]
    tenant_id: int | None = None
    code: str | None = None
    role: str | None = None


@pytest.fixture
async def db():
    d = SqliteDb()
    await d.connect(database=":memory:")
    await Region(d).create_table()
    await Agente(d).create_table()
    await Ciudad(d).create_table()
    await Membresia(d).create_table()
    yield d
    await d.close()


def test_sdl_snapshot(snapshot):
    """La SDL completa queda congelada contra el ``exec()`` vigente."""
    assert build_schema([Region, Agente]).as_str() == snapshot


async def test_dos_builds_sucesivos_funcionan(db):
    """Dos schemas construidos seguidos ejecutan relación, filtros y mutation."""
    s1 = build_schema([Region, Agente])
    s2 = build_schema([Region, Agente])

    rid = await Region(db, region="Norte").insert()
    await Agente(db, agente="Héctor", region_id=rid).insert()

    for schema in (s1, s2):
        # Relación (has_many + reference).
        rel = await schema.execute(
            "{ agentes { agente region { region } } }", context_value={"db": db}
        )
        assert rel.errors is None
        assert rel.data["agentes"][0]["region"]["region"] == "Norte"

        # Filtro autorreferente: and / or / not.
        f_and = await schema.execute(
            '{ agentes(filter: { and: [ { agente: { eq: "Héctor" } } ] }) { agente } }',
            context_value={"db": db},
        )
        assert f_and.errors is None
        assert [a["agente"] for a in f_and.data["agentes"]] == ["Héctor"]

        # `or`/`not` usan una rama que no coincide para que el resultado no
        # dependa de la mutation (que ya añadio "Ana" en el build anterior).
        f_or = await schema.execute(
            '{ agentes(filter: { or: [ { agente: { eq: "Héctor" } }, '
            '{ agente: { eq: "Nadie" } } ] }) { agente } }',
            context_value={"db": db},
        )
        assert f_or.errors is None
        assert [a["agente"] for a in f_or.data["agentes"]] == ["Héctor"]

        f_not = await schema.execute(
            '{ agentes(filter: { not: { agente: { eq: "Nadie" } } }) { agente } }',
            context_value={"db": db},
        )
        assert f_not.errors is None
        assert "Héctor" in [a["agente"] for a in f_not.data["agentes"]]

        # Mutation de creación.
        created = await schema.execute(
            'mutation { agente_create(data: { agente: "Ana" }) { agente } }',
            context_value={"db": db},
        )
        assert created.errors is None
        assert created.data["agente_create"]["agente"] == "Ana"


async def test_build_schema_con_modelo_distinto_funciona(db):
    """Un segundo build con otros modelos no rompe el esquema recién creado."""
    build_schema([Region, Agente])
    schema = build_schema([Ciudad])

    await Ciudad(db, ciudad="Madrid").insert()
    result = await schema.execute("{ ciudades { ciudad } }", context_value={"db": db})
    assert result.errors is None
    assert [c["ciudad"] for c in result.data["ciudades"]] == ["Madrid"]


async def test_operaciones_pk_siguen_funcionando(db):
    """``get``/``update``/``delete`` (PK simple) y ``get`` (PK compuesta)."""
    schema = build_schema([Region, Agente, Membresia])

    await Agente(db, agente="Héctor", region_id=1).insert()

    got = await schema.execute("{ agente(id: 1) { agente region_id } }", context_value={"db": db})
    assert got.errors is None
    assert got.data["agente"]["agente"] == "Héctor"

    missing = await schema.execute("{ agente(id: 999) { agente } }", context_value={"db": db})
    assert missing.errors is None
    assert missing.data["agente"] is None

    updated = await schema.execute(
        'mutation { agente_update(id: 1, data: { agente: "Héctor M." }) { agente region_id } }',
        context_value={"db": db},
    )
    assert updated.errors is None
    assert updated.data["agente_update"]["agente"] == "Héctor M."
    assert updated.data["agente_update"]["region_id"] == 1

    deleted = await schema.execute("mutation { agente_delete(id: 1) }", context_value={"db": db})
    assert deleted.errors is None
    assert deleted.data["agente_delete"] is True

    deleted_missing = await schema.execute(
        "mutation { agente_delete(id: 999) }", context_value={"db": db}
    )
    assert deleted_missing.errors is None
    assert deleted_missing.data["agente_delete"] is False

    # PK compuesta (`tenant_id` int + `code` str).
    await Membresia(db, tenant_id=7, code="admin", role="owner").insert()
    composite = await schema.execute(
        '{ membresia(tenant_id: 7, code: "admin") { role } }', context_value={"db": db}
    )
    assert composite.errors is None
    assert composite.data["membresia"]["role"] == "owner"


def test_build_schema_no_muta_el_namespace_del_modulo():
    """Dos builds sucesivos no acumulan tipos en el namespace del modulo real.

    Se incluye un build con el modelo sonda ``Sonda`` (que ningun otro test
    registra) para que la asercion no dependa del orden de ejecucion: los
    builds previos ya pudieron dejar ``Region``/``Agente`` en el namespace.
    """
    before = set(vars(schema_mod))
    build_schema([Region, Agente])
    build_schema([Sonda])
    assert set(vars(schema_mod)) == before


def test_build_schema_no_fuga_modulos_sinteticos():
    """El namespace por build se registra solo durante la construccion del schema."""
    build_schema([Region, Agente])
    build_schema([Ciudad])
    assert not [k for k in sys.modules if "_build_" in k]
