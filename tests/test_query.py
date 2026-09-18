"""Tests puros (sin BD) del value object `Query` (DIAL-05, decisiones D-01…D-06).

Cubren inmutabilidad de atributo, `with_params()`, la compilación por regex de
los `{n}` reales (dispersos y duplicados) con validación de cardinalidad, la
igualdad/hash y la compatibilidad de lectura `query`/`fields`/`sql_template`.
"""

import pathlib

import pytest

from encino_orm import Query
from encino_orm.sqlite import _to_positional

_ENCINO_ROOT = pathlib.Path(__file__).resolve().parents[1] / "encino_orm"
_DESIGN_DOC = pathlib.Path(__file__).resolve().parents[1] / "docs" / "design" / "0-design.md"


class TestImmutability:
    def test_attribute_reassignment_raises(self):
        q = Query("a={0}", [1])
        with pytest.raises(AttributeError):
            q.sql = "x"
        with pytest.raises(AttributeError):
            q.fields = []
        with pytest.raises(AttributeError):
            q.ignore_duplicated = True

    def test_typo_attribute_raises(self):
        q = Query("SELECT 1", [])
        with pytest.raises(AttributeError):
            q.atributo_inexistente = 1

    def test_in_place_mutation_is_out_of_contract_but_does_not_raise(self):
        # La inmutabilidad es de ATRIBUTO, no profunda: `fields` es una lista
        # mutable y su mutación in situ no lanza (uso NO soportado; además
        # invalida el hash, que se calcula del estado vivo).
        q = Query("a={0}", [1])
        q.fields.append(2)
        assert q.fields == [1, 2]


class TestWithParams:
    def test_returns_new_object_and_leaves_original_intact(self):
        q = Query("a={0} AND b={1}", [1, 2])
        q2 = q.with_params([10, 20])
        assert q2 is not q
        assert q2.sql_template == q.sql_template
        assert q2.sql == q.sql
        assert q2.params == {"parameter_0000": 10, "parameter_0001": 20}
        assert q.params == {"parameter_0000": 1, "parameter_0001": 2}
        assert q.fields == [1, 2]

    def test_preserves_ignore_duplicated(self):
        q = Query("a={0}", [1], ignore_duplicated=True)
        assert q.with_params([2]).ignore_duplicated is True

    def test_revalidates_cardinality(self):
        q = Query("a={0}", [1])
        with pytest.raises(ValueError):
            q.with_params([1, 2])
        with pytest.raises(ValueError):
            q.with_params([])


class TestRebindRemoved:
    def test_rebind_and_format_are_gone(self):
        assert not hasattr(Query, "rebind")
        assert not hasattr(Query, "format")


class TestNoRebindInSource:
    def test_no_def_rebind_anywhere_in_encino_orm(self):
        # Guard anti-podredumbre: el literal exacto `def rebind(` no puede
        # reaparecer. `Filter._rebind_raw` (def _rebind_raw) NO coincide.
        offenders = []
        for path in sorted(_ENCINO_ROOT.rglob("*.py")):
            rel = str(path.relative_to(_ENCINO_ROOT)).replace("\\", "/")
            if "def rebind(" in path.read_text(encoding="utf-8"):
                offenders.append(rel)
        assert offenders == []


class TestCompilation:
    def test_sparse_indices(self):
        q = Query("a={1} AND b={0}", [10, 20])
        assert q.sql == "a=%(parameter_0001)s AND b=%(parameter_0000)s"
        assert q.params == {"parameter_0000": 10, "parameter_0001": 20}

    def test_duplicate_indices(self):
        q = Query("a={0} OR b={0}", [7])
        assert q.sql == "a=%(parameter_0000)s OR b=%(parameter_0000)s"
        assert q.params == {"parameter_0000": 7}

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError) as exc:
            Query("a={0} AND b={2}", [1, 2])
        msg = str(exc.value)
        assert "[0, 2]" in msg
        assert "2 parámetros" in msg

    def test_unused_parameter_raises(self):
        with pytest.raises(ValueError) as exc:
            Query("a={0}", [1, 2])
        msg = str(exc.value)
        assert "[0]" in msg
        assert "2 parámetros" in msg

    def test_no_placeholders_with_empty_fields(self):
        q = Query("SELECT 1", [])
        assert q.sql == "SELECT 1"
        assert q.params == {}
        assert q.query == ["SELECT 1", {}]

    def test_no_placeholders_with_default_fields(self):
        q = Query("SELECT 1")
        assert q.sql == "SELECT 1"
        assert q.params == {}
        assert q.fields == []

    def test_sql_template_preserved(self):
        q = Query("a={0}", [1])
        assert q.sql_template == "a={0}"


class TestContractEnforcement:
    """Regresión de los dos huecos del contrato de cardinalidad (WR-01/WR-02).

    El carve-out `if indices and ...` aceptaba en silencio parámetros que ningún
    `{n}` usa, y `{00}` se compilaba desde el texto crudo, produciendo una clave
    que no existía en el dict de params. Ambos casos deben fallar/resolverse en
    la construcción, no dentro del adaptador.
    """

    def test_valores_sin_placeholders_ahora_lanza(self):
        with pytest.raises(ValueError) as exc:
            Query("SELECT 1", [1])
        msg = str(exc.value)
        assert "placeholders []" in msg
        assert "1 parámetros" in msg

    def test_sin_placeholders_y_sin_valores_sigue_pasando(self):
        for q in (Query("SELECT 1", []), Query("SELECT 1")):
            assert (q.sql, q.params) == ("SELECT 1", {})

    def test_indice_con_cero_inicial_compila_normalizado(self):
        q = Query("a={00}", [7])
        assert q.sql == "a=%(parameter_0000)s"
        assert q.params == {"parameter_0000": 7}
        # El traductor real del adaptador resuelve la clave: no puede escapar un
        # KeyError desde `_to_positional`.
        assert _to_positional(q.sql, q.params) == ("a=?", [7])

    def test_indice_normal_y_cero_inicial_no_colisionan(self):
        q = Query("a={0} AND b={00}", [7])
        assert q.sql == "a=%(parameter_0000)s AND b=%(parameter_0000)s"
        assert len(q.params) == 1

    def test_with_params_sobre_plantilla_sin_placeholders_lanza(self):
        with pytest.raises(ValueError):
            Query("SELECT 1", []).with_params([1])


class TestReadOnlyCompat:
    def test_query_returns_fresh_list(self):
        q = Query("a={0}", [1])
        first = q.query
        second = q.query
        assert first is not second
        assert first == [q.sql, q.params]
        assert q.query == ["a=%(parameter_0000)s", {"parameter_0000": 1}]

    def test_fields_property_does_not_copy(self):
        q = Query("a={0}", [1])
        assert q.fields is q.fields


class TestEqualityAndHash:
    def test_equal_queries_hash_equal(self):
        assert Query("a={0}", [1]) == Query("a={0}", [1])
        assert hash(Query("a={0}", [1])) == hash(Query("a={0}", [1]))

    def test_ignore_duplicated_excluded_from_eq_and_hash(self):
        # D-03: el flag NO entra en la clave de igualdad/hash (nota DATA-07).
        a = Query("t", [], ignore_duplicated=True)
        b = Query("t", [])
        assert a == b
        assert hash(a) == hash(b)

    def test_different_params_not_equal(self):
        assert Query("a={0}", [1]) != Query("a={0}", [2])

    def test_different_template_not_equal(self):
        assert Query("a={0}", [1]) != Query("b={0}", [1])

    def test_eq_other_type_returns_notimplemented(self):
        assert Query("a={0}", [1]).__eq__(42) is NotImplemented

    def test_unhashable_param_raises_typeerror(self):
        q = Query("a={0}", [[1, 2]])
        with pytest.raises(TypeError) as exc:
            hash(q)
        assert "no hashable" in str(exc.value)

    def test_str_concatenates_sql_and_params(self):
        q = Query("a={0}", [1])
        assert str(q) == "a=%(parameter_0000)s{'parameter_0000': 1}"


class TestDesignDocSync:
    """Guard de fuente: el doc de diseño publicado no puede divergir del código.

    `docs/design/0-design.md` se publica en el sitio de MkDocs; `mkdocs build
    --strict` solo valida sintaxis, no veracidad. Estas aserciones hacen
    ejecutable la afirmación de que el sketch y el ejemplo coinciden con
    `encino_orm/query.py`.
    """

    def test_el_sketch_del_doc_coincide_con_el_codigo(self):
        text = _DESIGN_DOC.read_text(encoding="utf-8")
        assert "int(m.group(1))" in text
        assert "indices and" not in text

    def test_el_ejemplo_de_with_params_del_doc_es_verdadero(self):
        q = Query("insert into grupos (grupo, enabled) values ({0},{1})", ["Grupo A", 1])
        q2 = q.with_params(["Grupo B", 0])
        assert q2.sql == (
            "insert into grupos (grupo, enabled) values (%(parameter_0000)s,%(parameter_0001)s)"
        )
        assert q2.params == {"parameter_0000": "Grupo B", "parameter_0001": 0}
        assert q.fields == ["Grupo A", 1]

    def test_el_doc_no_documenta_rebind_como_api_viva(self):
        text = _DESIGN_DOC.read_text(encoding="utf-8")
        assert "q.rebind(" not in text
        assert "def rebind(" not in text
