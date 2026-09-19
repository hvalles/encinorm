"""Guard y dependencies de FastAPI (imports perezosos de `fastapi`).

`fastapi` es opcional: se importa dentro de cada dependency (a nivel de request),
nunca al importar `encino_orm.security`, para que el núcleo no dependa de FastAPI.

La configuración viaja en un `SecurityConfig` inmutable que la aplicación
construye y entrega a `security_dependencies(config)`, que devuelve factorías de
guards cerradas sobre esa config. Los globales `SECRET`/`GET_DB` sobreviven como
atributos de módulo normales solo por compatibilidad y alimentan el fallback
deprecado; una vez construido un guard desde config, mutarlos no lo afecta.
"""

import warnings
from dataclasses import dataclass
from typing import Annotated

from .config import SecurityConfig
from .exceptions import AuthenticationError, AuthorizationError
from .jwt import verify_token
from .permissions import PermissionSet

# Configuración global DEPRECADA que la aplicación sobreescribe en su arranque:
SECRET: str | None = None  # p. ej. os.environ["SECRET_KEY"]
GET_DB = None  # dependency de conexión (session(pool) de docs/design/4-crud.md)


@dataclass
class CurrentUser:
    user_id: str | None = None
    permissions: PermissionSet | None = None


def _resolve(secret, get_db):
    """Completa la configuración con los globales si falta algún valor (fail-closed)."""
    secret = secret if secret is not None else SECRET
    if not secret:
        raise AuthenticationError("SECRET no configurado para la dependency de seguridad")
    db_dep = get_db if get_db is not None else GET_DB
    if db_dep is None:
        raise AuthenticationError("get_db no configurado para la dependency de seguridad")
    return secret, db_dep


def _explicit_config(secret, get_db) -> SecurityConfig:
    """Camino explícito: sin warning (Assumption A4)."""
    secret, db_dep = _resolve(secret, get_db)
    return SecurityConfig(secret, db_dep)


def _legacy_config() -> SecurityConfig:
    """Fallback a los globales: emite EXACTAMENTE un `DeprecationWarning`.

    El mensaje nombra los NOMBRES de los globales y su reemplazo, nunca sus
    valores (Pitfall 12). Se valida primero para seguir fallando cerrado sin
    avisar cuando no hay configuración.
    """
    secret, db_dep = _resolve(None, None)
    warnings.warn(
        "los globales SECRET/GET_DB están deprecados; usa SecurityConfig y "
        "security_dependencies(config)",
        DeprecationWarning,
        stacklevel=2,
    )
    return SecurityConfig(secret, db_dep)


def security_dependencies(config: SecurityConfig):
    """Factorías de guards cerradas sobre `config` (multi-tenant y rotación).

    Devuelve la tupla `(get_current_user_factory, require_factory)`. Cada
    factoría importa `fastapi` dentro de sí misma (importación diferida) y usa
    `Annotated[...]` para la inyección, de modo que `B008` no aplica.
    """

    def get_current_user():
        from fastapi import Depends, HTTPException
        from fastapi.security import HTTPBearer

        async def _dep(
            authorization: Annotated[object, Depends(HTTPBearer(auto_error=False))],
            db: Annotated[object, Depends(config.get_db)],
        ) -> CurrentUser:
            if authorization is None:
                # anónimo -> rol Público
                return CurrentUser(None, await PermissionSet.for_user(db, None))
            try:
                payload = verify_token(
                    authorization.credentials,
                    config.secret,
                    list(config.algorithms),
                )
            except AuthenticationError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc
            user_id = payload.get("sub")
            return CurrentUser(user_id, await PermissionSet.for_user(db, user_id))

        return _dep

    def require(modelo: str, op: str):
        from fastapi import Depends, HTTPException

        async def _dep(
            user: Annotated[CurrentUser, Depends(get_current_user())],
        ) -> None:
            try:
                user.permissions.require(modelo, op)
            except AuthorizationError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

        return _dep

    return get_current_user, require


def get_current_user(secret: str | None = None, get_db=None):
    """Dependency: resuelve la identidad desde el header `Authorization: Bearer`.

    Firma legacy preservada: con argumentos explícitos no emite warning; sin
    argumentos cae al fallback deprecado de los globales.
    """
    if secret is not None or get_db is not None:
        config = _explicit_config(secret, get_db)
    else:
        config = _legacy_config()
    get_current_user_factory, _ = security_dependencies(config)
    return get_current_user_factory()


def require(modelo: str, op: str, secret: str | None = None, get_db=None):
    """Dependency de orden superior: autentica + autoriza una operación.

    Devuelve una dependency de FastAPI que resuelve al usuario vía
    `get_current_user` y exige el permiso `op` sobre `modelo`; lanza `403`
    (vía `HTTPException`) si no puede. Firma legacy preservada.
    """
    if secret is not None or get_db is not None:
        config = _explicit_config(secret, get_db)
    else:
        config = _legacy_config()
    _, require_factory = security_dependencies(config)
    return require_factory(modelo, op)
