"""
Paleta de colores corporativos del informe.

Cada color es un dict {red, green, blue} con valores 0..1 (formato esperado
por la Slides API en rgbColor).

Valores aproximados a partir del PDF de referencia. Pendiente afinar con
hex codes oficiales de Lion Capital si los hay.
"""

COLORS: dict[str, dict[str, float]] = {
    "verde":    {"red": 0.13, "green": 0.78, "blue": 0.45},
    "rojo":     {"red": 0.95, "green": 0.30, "blue": 0.28},
    "amarillo": {"red": 0.95, "green": 0.78, "blue": 0.18},
    "dorado":   {"red": 0.85, "green": 0.65, "blue": 0.22},
    "cian":     {"red": 0.18, "green": 0.78, "blue": 0.75},
    "blanco":   {"red": 1.00, "green": 1.00, "blue": 1.00},
    "azul":     {"red": 0.20, "green": 0.50, "blue": 0.90},
}


def get_color(name: str) -> dict[str, float]:
    """Devuelve el color por nombre. Lanza KeyError con mensaje claro si no existe."""
    if name not in COLORS:
        raise KeyError(
            f"Color '{name}' no esta en la paleta. Disponibles: {sorted(COLORS)}"
        )
    return COLORS[name]
