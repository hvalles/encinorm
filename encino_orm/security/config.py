"""Configuración inmutable de seguridad (value object sin imports opcionales).

`SecurityConfig` sustituye a los globales mutables `SECRET`/`GET_DB`: la
aplicación lo construye en su composition root y lo pasa a
`security_dependencies(config)`, que devuelve factorías de guards cerradas sobre
él. Este módulo solo importa stdlib, de modo que el núcleo nunca adquiere una
dependencia dura de `fastapi`/`PyJWT` (contrato de importación diferida).

La inmutabilidad impide la mutación accidental del llamador; no es una defensa
criptográfica (un `object.__setattr__` explícito seguiría funcionando).
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SecurityConfig:
    """Configuración inmutable de la capa de seguridad.

    `secret` es la clave de firma JWT, `get_db` la dependency de conexión de la
    aplicación y `algorithms` la allowlist de algoritmos que se pasa a
    `verify_token` (que la valida contra su propio conjunto permitido).
    """

    secret: str
    get_db: Callable
    algorithms: tuple[str, ...] = ("HS256",)
