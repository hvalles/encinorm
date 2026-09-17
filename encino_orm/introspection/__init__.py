"""Subpaquete de introspección y codegen (database-first)."""

from .codegen import generate_model
from .tables import columns_of, list_tables
from .types import ColumnSpec, resolve_field_type

__all__ = [
    "ColumnSpec",
    "columns_of",
    "generate_model",
    "list_tables",
    "resolve_field_type",
]
