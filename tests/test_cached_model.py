import pytest
from pydantic import Field

from encino_orm.model import (
    CachedModel,
    FailOnUpdate,
    Filter,
    MemoryCacheBackend,
    scope,
)
from encino_orm.query import Query


class Cliente(CachedModel):
    _table = "clientes"
    _primary_key = ("rfc",)
    rfc: str | None = Field(default=None)
    nombre: str | None = Field(default=None)


DDL = (
    "CREATE TABLE clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT UNIQUE, nombre TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


class _FailingDeleteCache:
    """Backend cuyo `delete` siempre falla; prueba el fail-open de D-12."""

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        raise RuntimeError("backend caído")


class ClientePK(CachedModel):
    """Modelo con PK por defecto (`id`) para el caso CR-01: la clave de ESCRITURA
    (`rfc`) no coincide con la de LECTURA (`load()` usa la PK)."""

    _table = "clientes_pk"
    rfc: str | None = Field(default=None)
    nombre: str | None = Field(default=None)


DDL_PK = (
    "CREATE TABLE clientes_pk (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT UNIQUE, nombre TEXT, "
    "enabled INTEGER DEFAULT 1, created_at TEXT, updated_at TEXT)"
)


class ClienteScope(CachedModel):
    """Modelo para CR-01 multi-fila y CR-02: `grupo` NO es único (una escritura por
    él afecta a varias filas) y `tenant` es la columna de aislamiento por `scope()`."""

    _table = "clientes_scope"
    rfc: str | None = Field(default=None)
    grupo: str | None = Field(default=None)
    tenant: str | None = Field(default=None)
    nombre: str | None = Field(default=None)


DDL_SCOPE = (
    "CREATE TABLE clientes_scope (id INTEGER PRIMARY KEY AUTOINCREMENT, rfc TEXT UNIQUE, "
    "grupo TEXT, tenant TEXT, nombre TEXT, enabled INTEGER DEFAULT 1, created_at TEXT, "
    "updated_at TEXT)"
)


def _pk_key() -> str:
    """Clave del dominio canónico (`id=1`) que `load()` debe escribir SIEMPRE."""
    return ClientePK._cache_key_for(("id",), {"id": 1})


def _rfc_key() -> str:
    """Clave de LECTURA no-PK que el dominio canónico ya NO debe poblar."""
    return ClientePK._cache_key_for(("rfc",), {"rfc": "R1"})


def _scope_pk_key(i: int) -> str:
    """Clave canónica (`id=i`) del modelo con `grupo` no-único."""
    return ClienteScope._cache_key_for(("id",), {"id": i})


@pytest.fixture
async def db(connected_db):
    await connected_db.execute(Query(DDL, []))
    return connected_db


@pytest.fixture
async def db_pk(connected_db):
    await connected_db.execute(Query(DDL_PK, []))
    return connected_db


@pytest.fixture
async def db_scope(connected_db):
    await connected_db.execute(Query(DDL_SCOPE, []))
    return connected_db


class TestCachedModel:
    @pytest.mark.asyncio
    async def test_load_populates_cache(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await c.load(keys=["rfc"], duration=600)
        assert obj.nombre == "Héctor"
        assert getattr(obj, "__exists") is True
        assert len(cache._store) == 1

    @pytest.mark.asyncio
    async def test_load_hits_cache(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c1 = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c1.load(keys=["rfc"])

        # borrar de la BD para demostrar que se sirve desde caché
        await db.execute(Query("DELETE FROM clientes WHERE rfc = {0}", ["XAXX010101000"]))

        c2 = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await c2.load(keys=["rfc"])
        assert obj.nombre == "Héctor"
        assert getattr(obj, "__exists") is True

    @pytest.mark.asyncio
    async def test_cache_key_sha1(self, db):
        c = Cliente(db, rfc="XAXX010101000")
        key = c._cache_key(["rfc"])
        assert isinstance(key, str)
        assert len(key) == 40  # sha1 hexdigest

    @pytest.mark.asyncio
    async def test_update_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        c.nombre = "Nuevo"
        await c.update(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

        fresh = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await fresh.load(keys=["rfc"])
        assert obj.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_delete_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        await c.delete(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

    @pytest.mark.asyncio
    async def test_upsert_invalidates(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        cache = MemoryCacheBackend()
        c = Cliente(db, rfc="XAXX010101000", nombre="Otro", cache=cache)
        await c.load(keys=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is not None

        await c.upsert(conflict=["rfc"])
        assert await cache.get(c._cache_key(["rfc"])) is None

        fresh = Cliente(db, rfc="XAXX010101000", cache=cache)
        obj = await fresh.load(keys=["rfc"])
        assert obj.nombre == "Otro"

    @pytest.mark.asyncio
    async def test_invalidate_fail_open(self, db):
        await Cliente(db, rfc="XAXX010101000", nombre="Héctor").insert()

        c = Cliente(db, rfc="XAXX010101000", cache=_FailingDeleteCache())
        c.nombre = "Nuevo"
        count = await c.update(keys=["rfc"])
        assert count == 1

        row = await db.fetch_one(
            Query("SELECT nombre FROM clientes WHERE rfc = {0}", ["XAXX010101000"])
        )
        assert row["nombre"] == "Nuevo"

    @pytest.mark.asyncio
    async def test_insert_many_invalidates(self, db):
        nuevo_rfc = "XAXX010101001"
        cache = MemoryCacheBackend()
        key = Cliente._cache_key_for(("rfc",), {"rfc": nuevo_rfc})
        await cache.set(key, b"x", 60)

        await Cliente.insert_many(db, [{"rfc": nuevo_rfc, "nombre": "Nuevo"}], cache=cache)
        assert await cache.get(key) is None

    @pytest.mark.asyncio
    async def test_insert_many_without_cache_does_not_invalidate(self, db):
        otro_rfc = "XAXX010101002"
        cache = MemoryCacheBackend()
        key = Cliente._cache_key_for(("rfc",), {"rfc": otro_rfc})
        await cache.set(key, b"x", 60)

        await Cliente.insert_many(db, [{"rfc": otro_rfc, "nombre": "Sin cache"}])
        assert await cache.get(key) is not None

    @pytest.mark.asyncio
    async def test_invalidate_also_pk_domain_cr01(self, db_pk):
        """CR-01: un write por una clave distinta de la PK debe invalidar TAMBIÉN la
        entrada de la PK que `load()` escribe por defecto; si no, un `load()` posterior
        devuelve el valor viejo."""
        cache = MemoryCacheBackend()
        c = ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo")
        await c.insert()

        loaded = await ClientePK(db_pk, cache=cache, id=c.id).load()
        pk_key = loaded._cache_key(list(ClientePK._pk_fields()))
        assert await cache.get(pk_key) is not None

        c.nombre = "Nuevo"
        await c.update(keys=["rfc"])

        assert await cache.get(pk_key) is None
        again = await ClientePK(db_pk, cache=cache, id=c.id).load()
        assert again.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_cr01_non_pk_read_caches_under_pk_only(self, db_pk):
        """El dominio de caché es canónico: una lectura no-PK aprende la PK de la
        fila y cachea SOLO bajo ella; no deja entrada bajo la clave de lectura."""
        cache = MemoryCacheBackend()
        await ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo").insert()

        obj = await ClientePK(db_pk, cache=cache, rfc="R1").load(keys=["rfc"])
        assert obj.nombre == "Viejo"
        assert await cache.get(_pk_key()) is not None
        assert await cache.get(_rfc_key()) is None

        # Una lectura no-PK NO acierta en caché: si la fila desaparece de la BD,
        # el siguiente `load(keys=["rfc"])` lo refleja (no sirve la entrada PK).
        await db_pk.execute(Query("DELETE FROM clientes_pk WHERE rfc = {0}", ["R1"]))
        gone = await ClientePK(db_pk, cache=cache, rfc="R1").load(keys=["rfc"])
        assert getattr(gone, "__exists") is False

    @pytest.mark.asyncio
    async def test_cr01_update_without_instance_pk_invalidates_pk_entry(self, db_pk):
        """CR-01: un `update(keys=["rfc"])` desde una instancia SIN la PK (`id=None`)
        resuelve la PK real de la fila e invalida esa única entrada."""
        cache = MemoryCacheBackend()
        await ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo").insert()

        loaded = await ClientePK(db_pk, cache=cache, id=1).load()
        assert loaded.nombre == "Viejo"
        assert await cache.get(_pk_key()) is not None

        w = ClientePK(db_pk, cache=cache, rfc="R1", nombre="Nuevo")
        assert w.id is None
        await w.update(keys=["rfc"])

        assert await cache.get(_pk_key()) is None
        again = await ClientePK(db_pk, cache=cache, id=1).load()
        assert again.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_cr01_upsert_without_instance_pk_invalidates_pk_entry(self, db_pk):
        """CR-01: el caso canónico `upsert(conflict=["rfc"])` con el auto-`id` sin
        asignar debe invalidar la entrada cacheada bajo la PK real."""
        cache = MemoryCacheBackend()
        await ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo").insert()

        loaded = await ClientePK(db_pk, cache=cache, id=1).load()
        assert loaded.nombre == "Viejo"
        assert await cache.get(_pk_key()) is not None

        w = ClientePK(db_pk, cache=cache, rfc="R1", nombre="Nuevo")
        assert w.id is None
        await w.upsert(conflict=["rfc"])

        assert await cache.get(_pk_key()) is None
        again = await ClientePK(db_pk, cache=cache, id=1).load()
        assert again.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_cr01_delete_without_instance_pk_invalidates_pk_entry(self, db_pk):
        """CR-01: un `delete(keys=["rfc"])` desde una instancia SIN la PK resuelve
        la PK real antes del borrado (una vez borrada, el SELECT ya no la hallaría)."""
        cache = MemoryCacheBackend()
        await ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo").insert()

        loaded = await ClientePK(db_pk, cache=cache, id=1).load()
        assert loaded.nombre == "Viejo"
        assert await cache.get(_pk_key()) is not None

        w = ClientePK(db_pk, cache=cache, rfc="R1")
        assert w.id is None
        await w.delete(keys=["rfc"])

        assert await cache.get(_pk_key()) is None

    @pytest.mark.asyncio
    async def test_cr01_update_by_pk_invalidates_non_pk_cached_entry(self, db_pk):
        """Residual inverso: `load(keys=["rfc"])` (que cachea bajo la PK) seguido de
        un `update()` por PK debe invalidar esa entrada; el `load(keys=["rfc"])`
        posterior va a BD y devuelve el valor NUEVO."""
        cache = MemoryCacheBackend()
        await ClientePK(db_pk, cache=cache, rfc="R1", nombre="Viejo").insert()

        await ClientePK(db_pk, cache=cache, rfc="R1").load(keys=["rfc"])
        assert await cache.get(_pk_key()) is not None

        w = ClientePK(db_pk, cache=cache, id=1, nombre="Nuevo")
        await w.update()

        assert await cache.get(_pk_key()) is None
        again = await ClientePK(db_pk, cache=cache, rfc="R1").load(keys=["rfc"])
        assert again.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_cr01_multifila_invalida_todas_las_pks(self, db_scope):
        """CR-01 multi-fila: una escritura por una clave NO-única (`grupo`) afecta a
        VARIAS filas; la invalidación debe borrar la entrada de PK de TODAS, no solo
        la de una sonda `fetch_one`."""
        cache = MemoryCacheBackend()
        await ClienteScope(
            db_scope, cache=cache, rfc="R1", grupo="G", tenant="T", nombre="A"
        ).insert()
        await ClienteScope(
            db_scope, cache=cache, rfc="R2", grupo="G", tenant="T", nombre="B"
        ).insert()

        loaded1 = await ClienteScope(db_scope, cache=cache, id=1).load()
        loaded2 = await ClienteScope(db_scope, cache=cache, id=2).load()
        assert loaded1.nombre == "A"
        assert loaded2.nombre == "B"
        assert await cache.get(_scope_pk_key(1)) is not None
        assert await cache.get(_scope_pk_key(2)) is not None

        w = ClienteScope(db_scope, cache=cache, grupo="G", nombre="Nuevo")
        assert w.id is None
        await w.update(keys=["grupo"])

        assert await cache.get(_scope_pk_key(1)) is None
        assert await cache.get(_scope_pk_key(2)) is None

        again1 = await ClienteScope(db_scope, cache=cache, id=1).load()
        again2 = await ClienteScope(db_scope, cache=cache, id=2).load()
        assert again1.nombre == "Nuevo"
        assert again2.nombre == "Nuevo"

    @pytest.mark.asyncio
    async def test_cr02_scope_no_aislado_no_sirve_otro_tenant(self, db_scope):
        """CR-02 lectura: la clave de caché incluye el `scope()` activo, así que una
        entrada poblada por el tenant A no se sirve al tenant B."""
        await ClienteScope(db_scope, rfc="R1", grupo="G", tenant="A", nombre="secreto").insert()

        cache = MemoryCacheBackend()
        with scope(Filter.eq("tenant", "A")):
            propio = await ClienteScope(db_scope, id=1, cache=cache).load()
            assert propio.nombre == "secreto"
            assert getattr(propio, "__exists") is True

        with scope(Filter.eq("tenant", "B")):
            ajeno = await ClienteScope(db_scope, id=1, cache=cache).load()
            assert getattr(ajeno, "__exists") is False
            assert ajeno.nombre is None

    @pytest.mark.asyncio
    async def test_cr02_scope_bloquea_escritura_cruzada(self, db_scope):
        """CR-02 escritura: sin un acierto de caché que salte el `scope`, el tenant B
        no puede ver la fila de A, así que `update()` lanza `FailOnUpdate` y la fila
        conserva su valor."""
        await ClienteScope(db_scope, rfc="R1", grupo="G", tenant="A", nombre="secreto").insert()

        cache = MemoryCacheBackend()
        with scope(Filter.eq("tenant", "A")):
            await ClienteScope(db_scope, id=1, cache=cache).load()

        with scope(Filter.eq("tenant", "B")), pytest.raises(FailOnUpdate):
            await ClienteScope(db_scope, id=1, cache=cache, nombre="PWNED").update()

        row = await db_scope.fetch_one(
            Query("SELECT nombre FROM clientes_scope WHERE id = {0}", [1])
        )
        assert row["nombre"] == "secreto"

    @pytest.mark.asyncio
    async def test_cr02_mismo_scope_si_acierta(self, db_scope):
        """CR-02 intra-tenant: el aislamiento por scope no rompe el cacheo del MISMO
        tenant; un segundo `load()` bajo el mismo scope se sirve de la caché."""
        await ClienteScope(db_scope, rfc="R1", grupo="G", tenant="A", nombre="secreto").insert()

        cache = MemoryCacheBackend()
        with scope(Filter.eq("tenant", "A")):
            await ClienteScope(db_scope, id=1, cache=cache).load()

        # borrar de la BD para demostrar que el segundo load sale de la caché
        await db_scope.execute(Query("DELETE FROM clientes_scope WHERE id = {0}", [1]))

        with scope(Filter.eq("tenant", "A")):
            obj = await ClienteScope(db_scope, id=1, cache=cache).load()
            assert obj.nombre == "secreto"
            assert getattr(obj, "__exists") is True

    @pytest.mark.asyncio
    async def test_cr02_clave_depende_del_scope(self, db_scope):
        """CR-02 clave: la clave de caché cambia con el `scope` activo y sin scope es
        la original (compatibilidad)."""
        k_out = ClienteScope._cache_key_for(("id",), {"id": 1})
        with scope(Filter.eq("tenant", "A")):
            k_a = ClienteScope._cache_key_for(("id",), {"id": 1})
        with scope(Filter.eq("tenant", "B")):
            k_b = ClienteScope._cache_key_for(("id",), {"id": 1})
        assert k_a != k_out
        assert k_a != k_b
        assert k_b != k_out
