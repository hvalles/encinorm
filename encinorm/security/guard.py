"""Guard y dependencies de FastAPI (imports perezosos de `fastapi`).

`fastapi` es opcional: se importa dentro de cada dependency (a nivel de request),
nunca al importar `encinorm.security`, para que el núcleo no dependa de FastAPI.
"""

from dataclasses import dataclass

from .exceptions import AuthenticationError, AuthorizationError
from .jwt import verify_token
from .permissions import PermissionSet

# Configuración global que la aplicación sobreescribe en su arranque:
SECRET: str | None = None      # p. ej. os.environ["SECRET_KEY"]
GET_DB = None                  # dependency de conexión (session(pool) de design_crud.md)


@dataclass
class CurrentUser:
    user_id: str | None = None
    permissions: PermissionSet | None = None


def _resolve(secret, get_db):
    secret = secret if secret is not None else SECRET
    if not secret:
        raise AuthenticationError("SECRET no configurado para la dependency de seguridad")
    db_dep = get_db if get_db is not None else GET_DB
    if db_dep is None:
        raise AuthenticationError("get_db no configurado para la dependency de seguridad")
    return secret, db_dep


def get_current_user(secret: str | None = None, get_db=None):
    """Dependency: resuelve la identidad desde el header `Authorization: Bearer`."""
    from fastapi import Depends, HTTPException
    from fastapi.security import HTTPBearer

    secret, db_dep = _resolve(secret, get_db)

    async def _dep(authorization=Depends(HTTPBearer(auto_error=False)),
                   db=Depends(db_dep)) -> CurrentUser:
        if authorization is None:
            # anónimo -> rol Público
            return CurrentUser(None, await PermissionSet.for_user(db, None))
        try:
            payload = verify_token(authorization.credentials, secret)
        except AuthenticationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user_id = payload.get("sub")
        return CurrentUser(user_id, await PermissionSet.for_user(db, user_id))

    return _dep


def require(modelo: str, op: str, secret: str | None = None, get_db=None):
    """Dependency de orden superior: autentica + autoriza una operación.

    Devuelve una dependency de FastAPI que resuelve al usuario vía
    `get_current_user` y exige el permiso `op` sobre `modelo`; lanza `403`
    (vía `HTTPException`) si no puede.
    """
    from fastapi import Depends, HTTPException

    async def _dep(user: CurrentUser = Depends(get_current_user(secret, get_db))) -> None:
        try:
            user.permissions.require(modelo, op)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return _dep
