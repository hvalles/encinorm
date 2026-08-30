"""Subpaquete de introspección y codegen (database-first)."""

from .tables import columns_of, list_tables
from .types import ColumnSpec, resolve_field_type
from .codegen import generate_model

__all__ = [
    "list_tables",
    "columns_of",
    "ColumnSpec",
    "resolve_field_type",
    "generate_model",
]
