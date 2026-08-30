"""Excepciones del subpaquete `encinorm.security`."""

from encinorm.exceptions import EncinormError


class SecurityError(EncinormError):
    """Base de los errores de la capa de seguridad."""


class AuthenticationError(SecurityError):
    """La identidad no pudo establecerse (token ausente/inválido/caducado)."""


class AuthorizationError(SecurityError):
    """La identidad es válida pero carece de permiso para la operación."""

    def __init__(self, modelo: str, op: str):
        self.modelo = modelo
        self.op = op
        super().__init__(f"sin permiso para '{op}' sobre '{modelo}'")
