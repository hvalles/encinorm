"""Allowlist estricta de identificadores SQL, en un único punto de validación.

Este módulo es el ÚNICO lugar donde se decide si un identificador (tabla,
columna, índice o savepoint) es aceptable para interpolarlo en SQL. Los valores
de usuario nunca se interpolan; los identificadores sí, y por eso pasan por
`check_identifier` antes de construir cualquier sentencia.

La allowlist NO se relaja nunca para aceptar nombres cualificados
(``esquema.tabla``) ni citados: ampliar la clase de caracteres reabre la
superficie de inyección. El caso legítimo de nombre cualificado se cubre con un
parámetro ``schema=`` explícito que se valida por separado.

Nota: ``encino_orm/sql.py`` y ``encino_orm/model/query_builder.py`` mantienen su
propia ``_COLUMN_RE``, que a propósito SÍ acepta puntos para expresiones
calificadas (``mm.agente``, ``a.b``). Es una allowlist distinta y no se unifica
con esta.
"""

import re

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_identifier(value: str, label: str) -> str:
    """Valida que `value` sea un identificador SQL seguro (evita inyección)."""
    if not isinstance(value, str) or not IDENTIFIER_RE.match(value):
        raise ValueError(f"{label} inválido: {value!r}")
    return value
