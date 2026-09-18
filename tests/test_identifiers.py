"""Tests del allowlist estricto de identificadores SQL (sin base de datos).

Fija la tabla accept/reject de `check_identifier` y, en la segunda mitad del
plan, comprueba a nivel de fuente que el allowlist tenga una única definición
en todo el paquete `encino_orm/`.
"""

from pathlib import Path

import pytest
from pydantic import create_model

from encino_orm.dialects import IDENTIFIER_RE, check_identifier
from encino_orm.model import Model
from encino_orm.model.types import to_ddl

# Raíz del paquete inspeccionada por el guard de fuente.
RAIZ_PAQUETE = Path(__file__).resolve().parents[1] / "encino_orm"
ALLOWLIST_LITERAL = "^[A-Za-z_][A-Za-z0-9_]*$"

# Nombres que el allowlist estricto debe aceptar tal cual.
ACEPTADOS = ["t", "_x", "a1", "T_1"]

# Nombres que deben rechazarse: inyección, citado, cualificado, arranque
# no-alfabético, vacío, espacios, guiones y valores no-str.
RECHAZADOS = [
    "t; DROP TABLE x; --",
    "`x`",
    "a.b",
    "1abc",
    "",
    "a b",
    "a-b",
    "t;--",
    None,
    123,
]


@pytest.mark.parametrize("value", ACEPTADOS)
def test_check_identifier_acepta(value):
    assert check_identifier(value, "tabla") == value


@pytest.mark.parametrize("value", RECHAZADOS)
def test_check_identifier_rechaza(value):
    with pytest.raises(ValueError) as exc:
        check_identifier(value, "tabla")
    # Convención del repo: el valor ofensivo se cita con repr().
    assert repr(value) in str(exc.value)


def test_check_identifier_mensaje_exacto():
    with pytest.raises(ValueError) as exc:
        check_identifier("t;--", "nombre de tabla")
    assert str(exc.value) == "nombre de tabla inválido: 't;--'"


def test_check_identifier_salto_final_sigue_aceptado():
    """Caracteriza el anclaje ``$``: un salto final NO se rechaza hoy.

    En Python ``$`` casa también justo antes de un ``\\n`` final, así que el
    allowlist canónico acepta ``"tabla\\n"``. Este plan es un movimiento puro y
    conserva ese comportamiento; endurecerlo (p. ej. con ``\\Z`` o
    ``fullmatch``) cambia lo que se acepta y corresponde a un commit aparte.
    """
    assert check_identifier("tabla\n", "tabla") == "tabla\n"


def test_identificador_re_es_allowlist_estricta():
    assert IDENTIFIER_RE.pattern == r"^[A-Za-z_][A-Za-z0-9_]*$"


def test_allowlist_tiene_una_unica_definicion_en_la_fuente():
    """Guard de fuente: exactamente un fichero contiene el allowlist estricto.

    Reintroducir una copia local (Pitfall A) hace fallar este test, de modo que
    no puede volver a haber seis definiciones divergentes.
    """
    portadores = [
        fichero.relative_to(RAIZ_PAQUETE.parent).as_posix()
        for fichero in sorted(RAIZ_PAQUETE.rglob("*.py"))
        if "__pycache__" not in fichero.parts
        and ALLOWLIST_LITERAL in fichero.read_text(encoding="utf-8")
    ]
    assert portadores == ["encino_orm/dialects/identifiers.py"]


class TestNombreDeColumnaPorDefecto:
    """WR-06: el nombre de columna por defecto (campo pydantic) se valida.

    Al validar en el ÚNICO punto donde se construye el mapa, todos los
    consumidores (`_column_map`, `to_ddl`, `insert_many`) heredan el chequeo.
    """

    @staticmethod
    def _modelo_hostil():
        M = create_model("M", __base__=Model, **{"a; DROP TABLE x --": (str | None, None)})
        M._table = "t"
        return M

    def test_column_map_rechaza_nombre_de_campo_no_identificador(self):
        M = self._modelo_hostil()
        with pytest.raises(ValueError) as exc:
            M._column_map()
        assert "nombre de columna inválido" in str(exc.value)
        assert repr("a; DROP TABLE x --") in str(exc.value)

    def test_to_ddl_hereda_la_validacion(self):
        M = self._modelo_hostil()
        with pytest.raises(ValueError):
            to_ddl(M, "sqlite")

    @pytest.mark.asyncio
    async def test_insert_many_hereda_la_validacion(self):
        M = self._modelo_hostil()
        # El mapa se computa antes de tocar la db: un doble cualquiera basta.
        with pytest.raises(ValueError):
            await M.insert_many(db=object(), rows=[{}])

    def test_modelo_dinamico_normal_sigue_mapeando(self):
        M = create_model("M", __base__=Model, **{"a": (str | None, None)})
        M._table = "t"
        assert M._column_map()["a"] == "a"
