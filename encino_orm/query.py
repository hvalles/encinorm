import re

# Detección de los placeholders REALES `{n}` de la plantilla (D-04). No es el
# sentinel frágil `sql.find("{0}")`: reconoce cualquier índice, no solo el 0.
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


class Query:
    """Sentencia SQL + valores, inmutable a nivel de atributo y hashable.

    Contrato de entrada: ``Query("… {0} … {1}", [v0, v1])``. Los índices pueden
    aparecer dispersos o repetidos en el texto, pero el conjunto de índices
    detectados debe ser EXACTAMENTE ``range(len(values))``, sin excepciones ni
    carve-outs: ningún índice fuera de rango y ningún parámetro declarado sin
    usar. Pasar valores a una plantilla SIN ``{n}`` es un error de contrato
    (``ValueError``), no un descarte silencioso; ``Query("SELECT 1", [])`` y
    ``Query("SELECT 1")`` siguen siendo válidos. La violación lanza
    ``ValueError`` en la construcción. Los valores SIEMPRE viajan como
    parámetros ligados; la plantilla nunca se interpola con valores.

    Los ``{n}`` se compilan a ``%(parameter_0000)s`` desde el índice
    NORMALIZADO con ``int()``, así que ``{0}`` y ``{00}`` son el mismo
    placeholder y la misma clave que el dict de params. Los nombres se preservan
    EXACTAMENTE, de modo que el ``sql_text`` ya almacenado en
    ``_encino_orm_migrations`` no necesita migración.

    Accesores: ``sql`` (compilado), ``params`` (dict), ``sql_template`` (la
    plantilla con los `{n}`), ``fields`` (los valores de entrada),
    ``ignore_duplicated`` y la metadata de captura de id ``returns_id`` /
    ``id_column``. ``query`` se conserva como property de SOLO LECTURA que
    devuelve una lista nueva ``[sql, params]`` en cada acceso.

    Limitaciones conocidas, declaradas explícitamente:

    1. Un ``{n}`` dentro de un literal de cadena se interpreta como placeholder;
       esta versión no parsea literales SQL.
    2. La inmutabilidad es de ATRIBUTO, no profunda. Los slots privados más las
       properties sin setter impiden REASIGNAR ``sql``/``fields``/
       ``ignore_duplicated`` (y una errata de nombre lanza ``AttributeError``,
       porque no hay ``__dict__``), pero ``fields`` es una lista mutable y
       ``params`` expone el dict interno por referencia: ``q.fields.append(v)``
       y ``q.params["x"] = v`` NO lanzan. Mutar en sitio es un uso NO soportado
       y además rompe el contrato de ``__hash__``, porque el hash se calcula en
       cada llamada a partir del estado vivo. La property ``fields`` devuelve la
       lista subyacente (no una copia) para no romper ``list(qry.fields)`` ni
       ``qry.fields == [...]``.
    """

    # Orden natural exigido por RUF023. Las anotaciones de clase son necesarias
    # para que mypy vea los slots escritos con `object.__setattr__` (no crean
    # variables de clase, así que no chocan con `__slots__`).
    __slots__ = (
        "_fields",
        "_id_column",
        "_ignore_duplicated",
        "_params",
        "_returns_id",
        "_sql",
        "_sql_template",
    )
    _fields: list
    _id_column: str | None
    _ignore_duplicated: bool
    _params: dict
    _returns_id: bool
    _sql: str
    _sql_template: str

    def __init__(
        self,
        sql: str,
        fields: list | None = None,
        *,
        ignore_duplicated: bool = False,
        returns_id: bool = False,
        id_column: str | None = None,
    ):
        values = list(fields or [])
        indices = {int(m) for m in _PLACEHOLDER_RE.findall(sql)}
        # Sin carve-out: `set() != set(range(0))` ya es falso, así que el caso
        # "sin placeholders y sin valores" pasa sin condición especial, y
        # "sin placeholders CON valores" lanza (contrato de cardinalidad, D-04).
        if indices != set(range(len(values))):
            raise ValueError(
                f"placeholders {sorted(indices)} no cuadran con {len(values)} parámetros"
            )

        params = {f"parameter_000{i}": v for i, v in enumerate(values)}
        # Compilación desde el índice NORMALIZADO: validación y compilación no
        # pueden discrepar, así que `{0}` y `{00}` producen la misma clave que el
        # dict de params y ningún `KeyError` puede escapar del adaptador.
        compiled = _PLACEHOLDER_RE.sub(lambda m: f"%(parameter_000{int(m.group(1))})s", sql)

        # `object.__setattr__` escribe los slots privados saltándose las
        # properties de solo lectura; no hay `__dict__`, así que una errata de
        # nombre lanza AttributeError.
        object.__setattr__(self, "_sql_template", sql)
        object.__setattr__(self, "_fields", values)
        object.__setattr__(self, "_ignore_duplicated", bool(ignore_duplicated))
        object.__setattr__(self, "_returns_id", bool(returns_id))
        object.__setattr__(self, "_id_column", id_column)
        object.__setattr__(self, "_sql", compiled)
        object.__setattr__(self, "_params", params)

    @property
    def sql(self) -> str:
        """SQL compilado con placeholders intermedios `%(parameter_0000)s`."""
        return self._sql

    @property
    def params(self) -> dict:
        """Parámetros por nombre (`{"parameter_0000": valor}`)."""
        return self._params

    @property
    def sql_template(self) -> str:
        """Plantilla original con los `{n}` (la leen `pool.py` y `base.paginate`)."""
        return self._sql_template

    @property
    def fields(self) -> list:
        """Valores de entrada. Devuelve la MISMA lista subyacente, no una copia."""
        return self._fields

    @property
    def ignore_duplicated(self) -> bool:
        """Flag de constructor (MSSQL/Oracle suprimen la violación en `execute`)."""
        return self._ignore_duplicated

    @property
    def returns_id(self) -> bool:
        """Metadata de ejecución: la sentencia captura el id en el propio INSERT.

        La fija el builder (`build_insert(returning=...)`); la lee el adaptador
        para saber si debe devolver el id capturado (`lastrowid`, `RETURNING`,
        `OUTPUT INSERTED`, `RETURNING … INTO`).
        """
        return self._returns_id

    @property
    def id_column(self) -> str | None:
        """Columna de retorno interpolada en `RETURNING`/`OUTPUT INSERTED`, o `None`."""
        return self._id_column

    @property
    def query(self) -> list:
        """Compatibilidad de lectura (D-02): `[sql_compilado, params]`. Lista nueva."""
        return [self._sql, self._params]

    def with_params(self, fields: list) -> "Query":
        """Devuelve una COPIA con nuevos valores (sustituye al mutante `rebind`).

        Revalida la cardinalidad por construcción y nunca muta ``self``.
        """
        return Query(
            self.sql_template,
            fields,
            ignore_duplicated=self.ignore_duplicated,
            returns_id=self.returns_id,
            id_column=self.id_column,
        )

    def __eq__(self, other) -> bool:
        # D-03: la igualdad se define sobre (plantilla SQL, valores). El flag
        # `ignore_duplicated` y la metadata de captura de id (`returns_id`/
        # `id_column`) quedan EXCLUIDOS a propósito: dos Queries con el mismo
        # texto y valores son equivalentes aunque pidan (o no) el id. Es
        # metadata de EJECUCIÓN, no de identidad del statement.
        if not isinstance(other, Query):
            return NotImplemented
        return self.sql_template == other.sql_template and self.fields == other.fields

    def __hash__(self) -> int:
        # Nota DATA-07: si un futuro caché usa este hash como clave, DEBE añadir
        # `ignore_duplicated` a la clave — el flag no entra aquí (D-03).
        try:
            return hash((self.sql_template, tuple(self.fields)))
        except TypeError as exc:
            raise TypeError(
                f"Query no hashable: hay un parámetro no hashable ({exc}). "
                "Usa valores inmutables o no uses Query como clave."
            ) from exc

    def __str__(self) -> str:
        return f"{self._sql}{self._params}"
