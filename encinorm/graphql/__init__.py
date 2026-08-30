"""Subpaquete opcional `encinorm.graphql` (Strawberry GraphQL).

Genera tipos, queries y mutations a partir de los `Model` de encinorm.
`strawberry-graphql` es dependencia opcional (extras `graphql`).
"""

from .schema import build_schema

__all__ = ["build_schema"]
