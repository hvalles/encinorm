"""Formateo de valores según `Format` (lo aplican los renderers)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def format_value(value, fmt) -> str:
    """Devuelve la representación en texto de `value` según `fmt` (o `str` si no hay formato)."""
    if value is None:
        return ""
    if fmt is None:
        return str(value)
    if fmt.kind == "date":
        if isinstance(value, (datetime, date)):
            return value.strftime(fmt.pattern or "%Y-%m-%d")
        return str(value)
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float, Decimal)):
        num = value
        if fmt.percent_scale:
            num = num * 100
        neg = num < 0
        if fmt.decimals is not None:
            text = f"{abs(num):.{fmt.decimals}f}"
        else:
            text = f"{abs(num):g}"
        if fmt.thousands:
            text = _add_thousands(text)
        if fmt.kind == "percent":
            text = f"{text}%"
        if fmt.symbol:
            text = (fmt.symbol + text) if fmt.symbol_position == "prefix" else (text + fmt.symbol)
        if neg:
            text = f"({text})" if fmt.negative == "paren" else f"-{text}"
        return text
    return str(value)


def _add_thousands(text: str) -> str:
    int_part, dot, frac = text.partition(".")
    try:
        grouped = f"{int(int_part):,}"
    except (ValueError, OverflowError):
        grouped = int_part
    return grouped + (dot + frac if dot else "")


def excel_number_format(fmt) -> str | None:
    """Traduce un `Format` a un formato de número de Excel (None si no aplica)."""
    if fmt is None:
        return None
    if fmt.kind == "date":
        return fmt.pattern or "YYYY-MM-DD"
    d = fmt.decimals if fmt.decimals is not None else 0
    frac = ("." + "0" * d) if d else ""
    base = ("#,##" if fmt.thousands else "#") + "0" + frac
    if fmt.kind == "percent":
        base = base + "%" if fmt.percent_scale else base + '"%"'
    if fmt.symbol:
        quoted = f'"{fmt.symbol}"'
        base = quoted + base if fmt.symbol_position == "prefix" else base + quoted
    if fmt.negative == "paren":
        return f"{base};({base})"
    return base
