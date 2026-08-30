from pydantic import BaseModel, Field


class Records(BaseModel):
    """Resultado paginado de una consulta (DTO con metadatos)."""

    rows: list = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    page: int = 1

    @property
    def total_pages(self) -> int:
        return (self.total + self.limit - 1) // self.limit if self.limit else 1

    @property
    def has_next(self) -> bool:
        return self.page * self.limit < self.total

    @property
    def has_prev(self) -> bool:
        return self.page > 1
