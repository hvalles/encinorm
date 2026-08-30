from dataclasses import dataclass


@dataclass(frozen=True)
class Index:
    """Declaración de un índice (regular o único) sobre un modelo.

    ``columns`` es una secuencia de especificaciones de columna:
      - ``str`` -> columna con orden por defecto (ASC).
      - ``(nombre, "ASC" | "DESC")`` -> columna con dirección explícita.

    Ejemplos::

        Index("rfc", unique=True)
        Index([("created_at", "DESC")])
        Index(["rfc", ("created_at", "DESC")], name="idx_rfc_fecha")
    """

    columns: tuple = ()
    name: str | None = None
    unique: bool = False

    def __post_init__(self):
        if isinstance(self.columns, str):
            object.__setattr__(self, "columns", (self.columns,))
        else:
            object.__setattr__(self, "columns", tuple(self.columns))
