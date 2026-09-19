"""Configuración inmutable de seguridad (value object sin imports opcionales).

`SecurityConfig` sustituye a los globales mutables `SECRET`/`GET_DB`: la
aplicación lo construye en su composition root y lo pasa a
`security_dependencies(config)`, que devuelve factorías de guards cerradas sobre
él. Este módulo solo importa stdlib y las excepciones del subpaquete, de modo que
el núcleo nunca adquiere una dependencia dura de `fastapi`/`PyJWT` (contrato de
importación diferida).

La inmutabilidad impide la mutación accidental del llamador; no es una defensa
criptográfica (un `object.__setattr__` explícito seguiría funcionando).

Validación fail-closed (CR-01): un `secret` vacío o un `get_db` ausente se
rechazan AL CONSTRUIR. Sin esto, el camino recomendado (`security_dependencies`)
aceptaba un secreto vacío y PyJWT solo lo avisa, no lo rechaza: un token forjado
con HS256 y clave vacía autenticaba.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .exceptions import AuthenticationError


@dataclass(frozen=True)
class SecurityConfig:
    """Configuración inmutable de la capa de seguridad.

    `secret` es la clave de firma JWT (nunca se incluye en `repr`, WR-01),
    `get_db` la dependency de conexión de la aplicación y `algorithms` la
    allowlist de algoritmos que se pasa a `verify_token` (que la valida contra su
    propio conjunto permitido).
    """

    secret: str = field(repr=False)
    get_db: Callable
    algorithms: tuple[str, ...] = ("HS256",)

    def __post_init__(self):
        # Fail-closed (CR-01): el camino de `SecurityConfig` no pasa por
        # `_resolve()`, así que la validación vive aquí. Nunca se interpola el
        # valor del secreto en el mensaje.
        if not isinstance(self.secret, str) or not self.secret:
            raise AuthenticationError("SECRET no configurado para la dependency de seguridad")
        if self.get_db is None:
            raise AuthenticationError("get_db no configurado para la dependency de seguridad")
        if not self.algorithms:
            raise AuthenticationError("algorithms no puede estar vacío")
