"""Evaluador seguro de expresiones (sin `eval`, whitelist vía `ast`)."""

from __future__ import annotations

import ast
import operator
from typing import Any

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_CMP = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

_FUNCTIONS = {
    "IF": lambda cond: 1 if cond else 0,
    "lower": str.lower,
    "upper": str.upper,
    "concat": lambda *args: "".join(str(a) for a in args),
    "round": round,
    "abs": abs,
    "AND": lambda *args: 1 if all(args) else 0,
    "OR": lambda *args: 1 if any(args) else 0,
    "NOT": lambda x: 1 if not x else 0,
    "IN": lambda x, *args: 1 if x in args else 0,
    "BETWEEN": lambda x, lo, hi: 1 if lo <= x <= hi else 0,
}


class ExpressionError(ValueError):
    """Error al evaluar una expresión (p. ej. nombre desconocido o tipo inválido)."""


def evaluate(expr: str, row: dict, functions: dict | None = None) -> Any:
    """Evalúa `expr` sobre `row` y las funciones extra (fusionadas con `_FUNCTIONS`)."""
    merged = {**_FUNCTIONS, **(functions or {})}
    tree = ast.parse(expr, mode="eval")
    return _walk(tree.body, row, merged)


def _walk(node, row: dict, functions: dict) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in row:
            return row[node.id]
        if node.id in functions:
            return functions[node.id]
        raise ExpressionError(f"nombre desconocido: {node.id!r}")
    if isinstance(node, ast.BinOp):
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ExpressionError(f"operador no permitido: {ast.dump(node)}")
        return op(_walk(node.left, row, functions), _walk(node.right, row, functions))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY.get(type(node.op))
        if op is None:
            raise ExpressionError(f"operador no permitido: {ast.dump(node)}")
        return op(_walk(node.operand, row, functions))
    if isinstance(node, ast.Compare):
        left = _walk(node.left, row, functions)
        for op_node, comparator in zip(node.ops, node.comparators):
            op = _CMP.get(type(op_node))
            if op is None:
                raise ExpressionError(f"comparación no permitida: {ast.dump(node)}")
            right = _walk(comparator, row, functions)
            if not op(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ExpressionError(f"llamada no permitida: {ast.dump(node)}")
        fn = functions.get(node.func.id)
        if fn is None:
            raise ExpressionError(f"función no permitida: {node.func.id!r}")
        if node.keywords:
            raise ExpressionError("argumentos por nombre no permitidos")
        args = [_walk(a, row, functions) for a in node.args]
        return fn(*args)
    raise ExpressionError(f"expresión no permitida: {ast.dump(node)}")
