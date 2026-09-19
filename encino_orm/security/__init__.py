"""Subpaquete opcional de seguridad (RBAC + autenticación JWT).

`fastapi` y `PyJWT` son dependencias opcionales: se importan de forma perezosa
en `guard.py` y `jwt.py`, por lo que `encino_orm` y `encino_orm.model` siguen
funcionando sin ellas.
"""

from .config import SecurityConfig
from .exceptions import AuthenticationError, AuthorizationError, SecurityError
from .guard import CurrentUser, get_current_user, require, security_dependencies
from .jwt import emit_refresh, emit_token, verify_refresh, verify_token
from .models import Rol, Roldet, RolUsuario, create_tables, seed_roles
from .permissions import OPS, PUBLIC_USER_ID, PermissionSet

__all__ = [
    "OPS",
    "PUBLIC_USER_ID",
    "AuthenticationError",
    "AuthorizationError",
    "CurrentUser",
    "PermissionSet",
    "Rol",
    "RolUsuario",
    "Roldet",
    "SecurityConfig",
    "SecurityError",
    "create_tables",
    "emit_refresh",
    "emit_token",
    "get_current_user",
    "require",
    "security_dependencies",
    "seed_roles",
    "verify_refresh",
    "verify_token",
]
