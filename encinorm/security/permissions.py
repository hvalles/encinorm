"""Resolución de permisos efectivos (tri-estado, negación por defecto)."""

from encinorm.model import Filter

from .exceptions import AuthorizationError
from .models import Roldet, RolUsuario

# Operaciones soportadas (mapean a los endpoints CRUD y al ORM).
OPS = ("read", "create", "update", "delete", "remove")

# Identidad usada para los requests anónimos (rol Público).
PUBLIC_USER_ID = "public"


class PermissionSet:
    """Permisos efectivos de un usuario, resueltos una vez por request."""

    def __init__(self, user_id: str | None, rules: dict[str, dict[str, bool]]):
        self.user_id = user_id
        self._rules = rules          # {modelo: {op: True|False}}

    def can(self, modelo: str, op: str) -> bool:
        rule = self._rules.get(modelo) or self._rules.get("*")
        if rule is None:
            return False
        return bool(rule.get(op, False))     # negación por defecto

    def require(self, modelo: str, op: str) -> None:
        if not self.can(modelo, op):
            raise AuthorizationError(modelo, op)

    @classmethod
    async def for_user(cls, db, user_id: str | None) -> "PermissionSet":
        if user_id is None:
            user_id = PUBLIC_USER_ID        # rol Público para anónimos (str)
        # 1) roles del usuario, ordenados por `orden` asc
        roles = await RolUsuario.cursor(db).search(
            Filter.eq("user_id", user_id) & Filter.eq("enabled", True),
            columns=["rol_id", "orden"],
        )
        roles = sorted(roles, key=lambda r: (r.orden is None, r.orden or 0))
        rol_ids = [r.rol_id for r in roles if r.rol_id is not None]
        if not rol_ids:
            return cls(user_id, {})
        # 2) permisos por modelo, en orden de rol
        dets = await Roldet.cursor(db).search(Filter.in_("rol_id", rol_ids))
        order = {rid: i for i, rid in enumerate(rol_ids)}
        ordered = sorted(dets, key=lambda d: order.get(d.rol_id, 0))
        rules: dict[str, dict[str, bool]] = {}
        for d in ordered:
            m = d.modelo
            slot = rules.setdefault(m, {})
            for op in OPS:
                if op not in slot and getattr(d, f"perm_{op}") is not None:
                    slot[op] = bool(getattr(d, f"perm_{op}"))     # primer valor explícito
        return cls(user_id, rules)
