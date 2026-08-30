from typing import Annotated

import pytest
from pydantic import Field

from encinorm.model import Column, Model, to_ddl


class Agente(Model):
    _table = "agentes"
    agente: Annotated[str, Column(name="nombre")] = Field(default=None)
    monto: Annotated[float, Column(datatype="numeric")] = Field(default=0.0)
    region_id: int | None = None


class Legacy(Model):
    _table = "legacy"
    _fields_disabled = ["enabled", "created_at", "updated_at"]
    id: Annotated[int, Column(name="legacy_id")] = None
    nota: str | None = None


def test_to_ddl_sqlite():
    ddl = to_ddl(Agente, "sqlite")
    assert "CREATE TABLE agentes" in ddl
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
    assert "nombre TEXT" in ddl
    assert "monto REAL" in ddl
    assert "region_id INTEGER" in ddl
    assert "enabled INTEGER" in ddl


def test_to_ddl_mysql():
    ddl = to_ddl(Agente, "mysql")
    assert "id INT AUTO_INCREMENT PRIMARY KEY" in ddl
    assert "nombre VARCHAR(255)" in ddl
    assert "monto DECIMAL(10,2)" in ddl


def test_to_ddl_postgres():
    ddl = to_ddl(Agente, "postgres")
    assert "id SERIAL PRIMARY KEY" in ddl
    assert "nombre TEXT" in ddl
    assert "monto NUMERIC" in ddl
    assert "enabled BOOLEAN" in ddl


def test_to_ddl_respects_disabled_and_alias():
    ddl = to_ddl(Legacy, "sqlite")
    assert "legacy_id INTEGER PRIMARY KEY AUTOINCREMENT" in ddl
    assert "nota TEXT" in ddl
    assert "enabled" not in ddl
    assert "created_at" not in ddl


def test_ddl_type_unknown_engine():
    with pytest.raises(ValueError):
        to_ddl(Agente, "oracle")
