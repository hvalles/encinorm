import pytest
from pydantic import ValidationError as PydanticValidationError

from encinorm.model import Constraint, Model, make_constraint
from encinorm.model.types import to_ddl


STR_100 = make_constraint(str, max_length=100)
STR_50_REQ = make_constraint(str, max_length=50, required=True)
INT_POS = make_constraint(int, ge=0)


def positivo(v):
    if v is not None and v < 0:
        raise ValueError("debe ser positivo")
    return v


EDAD = make_constraint(int, validators=(positivo,))


class Agente(Model):
    _table = "agentes"
    agente: STR_50_REQ()
    rfc: STR_100(name="rfc_col")
    edad: INT_POS()


class Persona(Model):
    _table = "personas"
    edad: EDAD()


class TestConstraintFactories:
    def test_str(self):
        c = Constraint.str(max_length=100, required=False)
        assert c.datatype == "str"
        assert c.field_kwargs == {"max_length": 100}
        assert c.required is False
        assert c.to_column().datatype == "str"
        assert c.to_field().default is None

    def test_int_required(self):
        c = Constraint.int(ge=0, required=True)
        assert c.datatype == "int"
        assert c.field_kwargs == {"ge": 0}
        assert c.to_field().is_required() is True

    def test_numeric(self):
        c = Constraint.numeric(ge=0, le=100)
        assert c.datatype == "numeric"
        assert c.field_kwargs == {"ge": 0, "le": 100}


class TestMakeConstraint:
    def test_required_enforced(self):
        with pytest.raises(PydanticValidationError):
            Agente()  # agente es obligatorio

    def test_optional_defaults_none(self):
        a = Agente(agente="Héctor")
        assert a.rfc is None
        assert a.edad is None

    def test_max_length_enforced(self):
        with pytest.raises(PydanticValidationError):
            Agente(agente="x" * 51)

    def test_ge_enforced(self):
        with pytest.raises(PydanticValidationError):
            Agente(agente="Héctor", edad=-5)

    def test_validator(self):
        with pytest.raises(PydanticValidationError):
            Persona(edad=-1)
        assert Persona(edad=5).edad == 5

    def test_column_name_from_constraint(self):
        assert Agente._column_map()["rfc"] == "rfc_col"

    def test_ddl_uses_constraint(self):
        ddl = to_ddl(Agente, "sqlite")
        assert "agente TEXT" in ddl
        assert "rfc_col TEXT" in ddl
        assert "edad INTEGER" in ddl

    def test_datatype_inference_and_override(self):
        f = make_constraint(float, ge=0)()
        assert f.__metadata__[0].datatype == "numeric"
        f2 = make_constraint(float, datatype="float", ge=0)()
        assert f2.__metadata__[0].datatype == "float"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            make_constraint(object)
