"""Autenticación JWT: envoltura delgada de PyJWT.

`PyJWT` es una dependencia opcional; se importa de forma perezosa para que
`encino_orm` y `encino_orm.model` funcionen sin él. encino_orm no gestiona
credenciales ni hashing (lo hace la aplicación al emitir el token en el login).
"""

import time

from .exceptions import AuthenticationError


def _now() -> int:
    return int(time.time())


_ALLOWED_ALGORITHMS = frozenset({
    "HS256", "HS384", "HS512",
    "RS256", "RS384", "RS512",
    "ES256", "ES384", "ES512",
    "PS256", "PS384", "PS512",
})


def _check_algorithm(algorithm: str) -> str:
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise ValueError(f"algoritmo JWT no permitido: {algorithm!r}")
    return algorithm


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
    _check_algorithm(algorithm)
    payload = {"sub": user_id, "type": "access", "iat": _now(),
               "exp": _now() + expires_seconds, **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)


def _filter_algorithms(algorithms: list[str] | None) -> list[str]:
    algorithms = algorithms or ["HS256"]
    for a in algorithms:
        if a not in _ALLOWED_ALGORITHMS:
            raise ValueError(f"algoritmo JWT no permitido: {a!r}")
    return list(algorithms)


def verify_token(token: str, secret: str, algorithms: list[str] | None = None) -> dict:
    jwt = _jwt()
    algorithms = _filter_algorithms(algorithms)
    try:
        payload = jwt.decode(
            token, secret, algorithms=algorithms, options={"require": ["exp"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token caducado") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("token inválido") from exc
    if payload.get("type") == "refresh":
        raise AuthenticationError("token de refresco no válido como access")
    return payload


def emit_refresh(user_id: str, secret: str, expires_seconds: int = 604800,
                 algorithm: str = "HS256", **claims) -> str:
    jwt = _jwt()
    _check_algorithm(algorithm)
    payload = {"sub": user_id, "type": "refresh", "iat": _now(),
               "exp": _now() + expires_seconds, **claims}
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_refresh(token: str, secret: str, algorithms: list[str] | None = None) -> dict:
    jwt = _jwt()
    algorithms = _filter_algorithms(algorithms)
    try:
        payload = jwt.decode(
            token, secret, algorithms=algorithms, options={"require": ["exp"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("token caducado") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("token inválido") from exc
    if payload.get("type") != "refresh":
        raise AuthenticationError("token no es de refresco")
    return payload
