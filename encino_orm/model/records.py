from pydantic import BaseModel, Field

DEFAULT_LIMIT = 50
MAX_LIMIT = 1000


def _int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def normalize_limit_page(limit, page=1):
    """Clamp de paginación: `page` >= 1; `limit` ∈ [1, MAX_LIMIT] (`None` se respeta).

    Devuelve la tupla ``(limit, page)`` normalizada. ``limit=None`` se conserva
    para las operaciones internas que esperan "sin límite" (p. ej. `batch_*`).
    """
    page = _int(page, 1)
    if page < 1:
        page = 1
    if limit is None:
        return None, page
    limit = _int(limit, DEFAULT_LIMIT)
    if limit < 1:
        limit = DEFAULT_LIMIT
    return min(limit, MAX_LIMIT), page


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
