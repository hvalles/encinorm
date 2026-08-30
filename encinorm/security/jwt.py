"""Autenticación JWT: envoltura delgada de PyJWT.

`PyJWT` es una dependencia opcional; se importa de forma perezosa para que
`encinorm` y `encinorm.model` funcionen sin él. encinorm no gestiona
credenciales ni hashing (lo hace la aplicación al emitir el token en el login).
"""

import time

from .exceptions import AuthenticationError


def _now() -> int:
    return int(time.time())


def _jwt():
    try:
        import jwt
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise ImportError(
            "PyJWT no está instalado; agrega la dependencia opcional `security` "
            "(PyJWT>=2.8)."
        ) from exc
    return jwt


def emit_token(user_id: str, secret: str, expires_seconds: int = 900,
               algorithm: str = "HS256", **claims) -> str:
    jwt = _jwt()
    payload = {"sub": user_id, "iat": _now(), "exp": _now() + expires_seconds, **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_token(token: str, secret: str, algorithms: list[str] | None = None) -> dict:
    jwt = _jwt()
    algorithms = algorithms or ["HS256"]
    try:
        return jwt.decode(
            token, secret, algorithms=algorithms, options={"require": ["exp"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token caducado") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("token inválido") from exc


def emit_refresh(user_id: str, secret: str, expires_seconds: int = 604800,
                 algorithm: str = "HS256", **claims) -> str:
    jwt = _jwt()
    payload = {"sub": user_id, "iat": _now(), "exp": _now() + expires_seconds, **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_refresh(token: str, secret: str, algorithms: list[str] | None = None) -> dict:
    return verify_token(token, secret, algorithms)
