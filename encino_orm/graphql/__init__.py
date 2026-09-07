"""Subpaquete opcional `encino_orm.graphql` (Strawberry GraphQL).

Genera tipos, queries y mutations a partir de los `Model` de encino_orm.
`strawberry-graphql` es dependencia opcional (extras `graphql`).
"""

from .schema import build_schema

__all__ = ["build_schema"]
