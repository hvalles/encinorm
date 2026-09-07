from dataclasses import dataclass, field
from typing import Any


@dataclass
class Reference:
    name: str
    model_class: type
    match_keys: dict          # {campo_remoto: campo_local}
    on_delete: str | None = None
    _cached: Any = field(default=None, init=False, repr=False)
    _cached_keys: Any = field(default=None, init=False, repr=False)


@dataclass
class HasMany:
    name: str
    model_class: type
    foreign_key: str | dict          # str -> {pk[0]: str}; dict -> {campo_padre: campo_hijo}
    _cached: Any = field(default=None, init=False, repr=False)
    _cached_key: Any = field(default=None, init=False, repr=False)

    @property
    def match_keys(self) -> dict:
        """Mapeo normalizado ``{campo_padre: campo_hijo}``.

        Un `foreign_key` de tipo `str` se interpreta como apuntando al primer
        campo de la clave primaria del padre (compatibilidad con el `id`).
        """
        if isinstance(self.foreign_key, str):
            return {self.model_class._pk_fields()[0]: self.foreign_key}
        return dict(self.foreign_key)
