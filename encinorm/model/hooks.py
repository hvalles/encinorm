"""Decoradores del ciclo de vida del modelo.

Cada decorador marca el método con un atributo ``_encinorm_hook``; ``Model``
los recolecta en ``__init_subclass__`` y los ejecuta en orden de declaración.
"""


def _mark(func, hook: str):
    setattr(func, "_encinorm_hook", hook)
    return func


def before_insert(func):
    return _mark(func, "before_insert")


def before_update(func):
    return _mark(func, "before_update")


def before_delete(func):
    return _mark(func, "before_delete")


def before_commit(func):
    return _mark(func, "before_commit")


def after_commit(func):
    return _mark(func, "after_commit")


def after_transaction_fail(func):
    return _mark(func, "after_transaction_fail")
