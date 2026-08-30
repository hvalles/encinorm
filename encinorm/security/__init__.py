"""Subpaquete opcional de seguridad (RBAC + autenticación JWT).

`fastapi` y `PyJWT` son dependencias opcionales: se importan de forma perezosa
en `guard.py` y `jwt.py`, por lo que `encinorm` y `encinorm.model` siguen
funcionando sin ellas.
"""

from .exceptions import AuthenticationError, AuthorizationError, SecurityError
from .guard import CurrentUser, get_current_user, require
from .jwt import emit_refresh, emit_token, verify_refresh, verify_token
from .models import Roldet, Rol, RolUsuario, create_tables, seed_roles
from .permissions import OPS, PUBLIC_USER_ID, PermissionSet

__all__ = [
    "Rol",
    "Roldet",
    "RolUsuario",
    "seed_roles",
    "create_tables",
    "PermissionSet",
    "OPS",
    "PUBLIC_USER_ID",
    "CurrentUser",
    "get_current_user",
    "require",
    "emit_token",
    "verify_token",
    "emit_refresh",
    "verify_refresh",
    "SecurityError",
    "AuthenticationError",
    "AuthorizationError",
]
