import types

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from encinorm import session
from encinorm.sqlite import SqliteDb
from encinorm.security import (
    AuthenticationError,
    AuthorizationError,
    CurrentUser,
    PermissionSet,
    Roldet,
    Rol,
    RolUsuario,
    create_tables,
    emit_refresh,
    emit_token,
    get_current_user,
    require,
    seed_roles,
    verify_refresh,
    verify_token,
)
from encinorm.security.permissions import PUBLIC_USER_ID

SECRET = "test-secret-key-that-is-at-least-32-bytes-long!"


@pytest.fixture
async def sec_db():
    db = SqliteDb()
    await db.connect(database=":memory:")
    await create_tables(db)
    await seed_roles(db)
    yield db
    await db.close()


async def _seed_permissions(db):
    """Roles 1 (admin todo), 2 (lee agentes), 3 (niega agentes) + usuarios."""
    await Roldet(db, rol_id=1, modelo="*", perm_read=True, perm_create=True,
                 perm_update=True, perm_delete=True, perm_remove=True).insert()
    await Roldet(db, rol_id=2, modelo="agentes", perm_read=True).insert()
    await Roldet(db, rol_id=3, modelo="agentes", perm_read=False).insert()

    # usuario 42: rol 2 (orden 1) luego rol 3 (orden 2) -> prevalece rol 2
    await RolUsuario(db, rol_id=2, user_id="42", orden=1).insert()
    await RolUsuario(db, rol_id=3, user_id="42", orden=2).insert()
    # administrador 1
    await RolUsuario(db, rol_id=1, user_id="1", orden=1).insert()
    # anónimo -> rol Público (3)
    await RolUsuario(db, rol_id=3, user_id=PUBLIC_USER_ID, orden=1).insert()


class TestSeed:
    @pytest.mark.asyncio
    async def test_seed_roles(self, sec_db):
        roles = await Rol(sec_db, rol="x").search()
        assert [r.rol for r in roles] == ["Administrador", "Usuario Interno", "Público"]
        assert [r.id for r in roles] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_seed_idempotent(self, sec_db):
        assert await seed_roles(sec_db) == []
        roles = await Rol(sec_db, rol="x").search()
        assert len(roles) == 3

    def test_rolusuario_requires_user_id(self):
        with pytest.raises(Exception):
            RolUsuario()  # user_id es obligatorio (STR_50 required)


class TestPermissionSet:
    @pytest.mark.asyncio
    async def test_first_assignment_prevails(self, sec_db):
        await _seed_permissions(sec_db)
        ps = await PermissionSet.for_user(sec_db, "42")
        # rol 2 (lee) prevalece sobre rol 3 (niega)
        assert ps.can("agentes", "read") is True
        # sin regla de create -> negación por defecto
        assert ps.can("agentes", "create") is False

    @pytest.mark.asyncio
    async def test_wildcard(self, sec_db):
        await _seed_permissions(sec_db)
        ps = await PermissionSet.for_user(sec_db, "1")
        assert ps.can("agentes", "read") is True
        assert ps.can("facturas", "remove") is True

    @pytest.mark.asyncio
    async def test_deny_by_default_no_roles(self, sec_db):
        ps = await PermissionSet.for_user(sec_db, "nadie")
        assert ps.can("agentes", "read") is False

    @pytest.mark.asyncio
    async def test_anonymous_uses_public(self, sec_db):
        await _seed_permissions(sec_db)
        ps = await PermissionSet.for_user(sec_db, None)
        assert ps.user_id == PUBLIC_USER_ID
        # Público niega read en agentes
        assert ps.can("agentes", "read") is False

    @pytest.mark.asyncio
    async def test_delete_vs_remove_distinct(self, sec_db):
        # rol 2 solo puede borrado lógico, no físico
        await Roldet(sec_db, rol_id=2, modelo="agentes", perm_read=True, perm_delete=True).insert()
        await RolUsuario(sec_db, rol_id=2, user_id="42", orden=1).insert()
        ps = await PermissionSet.for_user(sec_db, "42")
        assert ps.can("agentes", "delete") is True
        assert ps.can("agentes", "remove") is False

    def test_require_raises_authorization(self):
        ps = PermissionSet("x", {})
        with pytest.raises(AuthorizationError):
            ps.require("agentes", "read")


class TestJwt:
    def test_emit_verify_roundtrip(self):
        token = emit_token("42", SECRET)
        payload = verify_token(token, SECRET)
        assert payload["sub"] == "42"
        assert "exp" in payload and "iat" in payload

    def test_expired_raises_authentication(self):
        token = emit_token("42", SECRET, expires_seconds=-1)
        with pytest.raises(AuthenticationError):
            verify_token(token, SECRET)

    def test_invalid_token_raises(self):
        with pytest.raises(AuthenticationError):
            verify_token("garbage", SECRET)

    def test_refresh_roundtrip(self):
        token = emit_refresh("42", SECRET)
        payload = verify_refresh(token, SECRET)
        assert payload["sub"] == "42"

    def test_wrong_secret_raises(self):
        token = emit_token("42", SECRET)
        with pytest.raises(AuthenticationError):
            verify_token(token, "otra-clave-distinta-de-32-bytes-o-mas-!")


class TestGuardDependencies:
    @pytest.mark.asyncio
    async def test_get_current_user_anonymous(self, sec_db):
        await _seed_permissions(sec_db)
        dep = get_current_user(secret=SECRET, get_db=_noop_get_db)
        user = await dep(authorization=None, db=sec_db)
        assert isinstance(user, CurrentUser)
        assert user.user_id is None
        assert user.permissions.user_id == PUBLIC_USER_ID

    @pytest.mark.asyncio
    async def test_get_current_user_with_token(self, sec_db):
        await _seed_permissions(sec_db)
        token = emit_token("42", SECRET)
        creds = types.SimpleNamespace(credentials=token)
        dep = get_current_user(secret=SECRET, get_db=_noop_get_db)
        user = await dep(authorization=creds, db=sec_db)
        assert user.user_id == "42"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token_401(self, sec_db):
        from fastapi import HTTPException

        creds = types.SimpleNamespace(credentials="garbage")
        dep = get_current_user(secret=SECRET, get_db=_noop_get_db)
        with pytest.raises(HTTPException) as exc:
            await dep(authorization=creds, db=sec_db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_require_allows(self, sec_db):
        await _seed_permissions(sec_db)
        ps = await PermissionSet.for_user(sec_db, "42")
        dep = require("agentes", "read", secret=SECRET, get_db=_noop_get_db)
        assert await dep(user=CurrentUser("42", ps)) is None

    @pytest.mark.asyncio
    async def test_require_forbidden_403(self, sec_db):
        from fastapi import HTTPException

        await _seed_permissions(sec_db)
        ps = await PermissionSet.for_user(sec_db, "42")
        dep = require("agentes", "create", secret=SECRET, get_db=_noop_get_db)
        with pytest.raises(HTTPException) as exc:
            await dep(user=CurrentUser("42", ps))
        assert exc.value.status_code == 403


async def _noop_get_db():
    raise NotImplementedError  # nunca se invoca: en las pruebas se pasa `db` explícito


class TestGuardIntegration:
    @pytest.mark.asyncio
    async def test_crud_guard_200_401_403(self, sec_db):
        await _seed_permissions(sec_db)

        app = FastAPI()

        async def get_db():
            async with session(sec_db) as conn:
                yield conn

        @app.get("/agentes/")
        async def listar(_=Depends(require("agentes", "read", secret=SECRET, get_db=get_db))):
            return {"ok": True}

        token = emit_token("42", SECRET)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_ok = await client.get("/agentes/", headers={"Authorization": f"Bearer {token}"})
            assert r_ok.status_code == 200

            r_forbidden = await client.get("/agentes/")
            assert r_forbidden.status_code == 403

            r_bad = await client.get("/agentes/", headers={"Authorization": "Bearer invalido"})
            assert r_bad.status_code == 401
