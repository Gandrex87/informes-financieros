"""
Formateo de valores numericos al estilo es_ES, listo para Slides.

Sin dependencia de locale del SO (no es portable entre OS y contenedores).
Reglas hardcodeadas: separador miles '.', separador decimal ',', simbolo €.
"""
from decimal import Decimal
from typing import Union

Number = Union[int, float, Decimal, None]


def _to_decimal(value: Number) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def format_euro(value: Number, decimales: int = 0) -> str:
    """Formato '547.139 €' o '370.926,53 €' segun decimales.

    Reglas:
        - Sin decimales por defecto (importes redondeados).
        - Separador miles '.', decimal ',' (es_ES).
        - Espacio antes del simbolo €.
    """
    d = _to_decimal(value)
    if d is None:
        return ""
    quant = Decimal(10) ** -decimales
    d = d.quantize(quant)
    # Conversion manual para evitar locale del sistema.
    sign = "-" if d < 0 else ""
    d = abs(d)
    entero, _, dec = f"{d:.{decimales}f}".partition(".")
    entero_fmt = ".".join(_chunks_right(entero, 3))
    if decimales > 0:
        return f"{sign}{entero_fmt},{dec} €"
    return f"{sign}{entero_fmt} €"


def format_pct(value: Number, decimales: int = 2) -> str:
    """Convierte 0.6116 -> '61,16 %'. El valor llega como decimal (0..1)."""
    d = _to_decimal(value)
    if d is None:
        return ""
    d = d * 100
    return _fmt_pct(d, decimales)


def format_pct_signed(value: Number, decimales: int = 2) -> str:
    """Igual que format_pct pero con signo siempre: '+6,70 %' o '-1,82 %'."""
    d = _to_decimal(value)
    if d is None:
        return ""
    d = d * 100
    signed = "+" if d >= 0 else ""
    return signed + _fmt_pct(d, decimales)


def format_int_signed(value: Number, suffix: str = "") -> str:
    """Convierte 3 -> '+3', -18 -> '-18'. Con suffix opcional: '+3 ops'."""
    d = _to_decimal(value)
    if d is None:
        return ""
    n = int(d)
    body = f"{n:+d}"
    return f"{body} {suffix}".strip()


def format_int(value: Number) -> str:
    """Convierte 42 -> '42'."""
    d = _to_decimal(value)
    if d is None:
        return ""
    return str(int(d))


def format_pct_with_arrow(value: Number, decimales: int = 1) -> str:
    """Convierte una variacion decimal a '▲ +33,7 %' o '▼ -6,6 %'.

    Recibe el valor como decimal (0.337 = 33,7%). Flecha ▲ si positivo o
    cero, ▼ si negativo. Signo siempre presente. Si value es None, "".
    """
    d = _to_decimal(value)
    if d is None:
        return ""
    arrow = "▲" if d >= 0 else "▼"
    return f"{arrow} {format_pct_signed(d, decimales)}"


def format_delta_ops_full(actual: Number, anterior: Number, suffix: str = "ops") -> str:
    """Convierte (actual, anterior) -> '-18 ops (-30 %)' o '+3 ops (+8 %)'.

    Calcula la diferencia absoluta + la variacion porcentual y las junta.
    Si anterior es None o 0, omite la parte porcentual.
    """
    a = _to_decimal(actual)
    p = _to_decimal(anterior)
    if a is None or p is None:
        return ""
    diff = int(a - p)
    body_abs = f"{diff:+d} {suffix}"
    if p == 0:
        return body_abs
    pct = (a - p) / p
    pct_str = format_pct_signed(pct, decimales=0)
    return f"{body_abs} ({pct_str})"


# ---------- Internos ----------

def _fmt_pct(d: Decimal, decimales: int) -> str:
    sign = "-" if d < 0 else ""
    d = abs(d)
    entero, _, dec = f"{d:.{decimales}f}".partition(".")
    if decimales > 0:
        return f"{sign}{entero},{dec} %"
    return f"{sign}{entero} %"


def _chunks_right(s: str, n: int) -> list[str]:
    """Parte un string en chunks de N desde la derecha. '1234567' -> ['1', '234', '567']."""
    return [s[max(0, i - n):i] for i in range(len(s), 0, -n)][::-1]


# Mapeo: numero del mes -> nombre español capitalizado.
MESES_ES = [
    "", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MESES_ES_SHORT = [
    "", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sept", "Oct", "Nov", "Dic",
]


def format_mes_anyo(anyo: int, mes: int) -> str:
    """4, 2026 -> 'Abril 2026'."""
    return f"{MESES_ES[mes]} {anyo}"


def format_mes_anyo_upper(anyo: int, mes: int) -> str:
    """4, 2026 -> 'ABRIL 2026'."""
    return format_mes_anyo(anyo, mes).upper()


def format_mes_short_anyo(anyo: int, mes: int) -> str:
    """3, 2026 -> 'Mar '26'."""
    yy = str(anyo)[-2:]
    return f"{MESES_ES_SHORT[mes]} '{yy}"


def format_mes_year3_upper(anyo: int, mes: int) -> str:
    """3, 2026 -> 'MAR 2026'."""
    return f"{MESES_ES_SHORT[mes].upper()} {anyo}"


def format_mes_short_upper_year(anyo: int, mes: int) -> str:
    """4, 2025 -> 'ABR'25'."""
    yy = str(anyo)[-2:]
    return f"{MESES_ES_SHORT[mes].upper()}'{yy}"


def format_trimestre(mes: int) -> str:
    """4 -> 'Q2', 7 -> 'Q3', etc. Trimestre al que pertenece el mes."""
    if not 1 <= mes <= 12:
        return ""
    return f"Q{(mes - 1) // 3 + 1}"
