"""Seam de dialectos: validación de identificadores y construcción DML compartida."""

from .identifiers import IDENTIFIER_RE, check_identifier

__all__ = ["IDENTIFIER_RE", "check_identifier"]
