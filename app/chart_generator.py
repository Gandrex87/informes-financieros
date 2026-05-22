"""
Generacion de graficos para el informe usando matplotlib.

Cada funcion produce los bytes de un PNG listo para subir a Drive y luego
insertar en la presentacion via replaceAllShapesWithImage.

Convenciones de estilo (branding del informe):
- Fondo azul oscuro (mismo que las slides).
- Texto blanco.
- Sin grid pesado, lineas sutiles.
- Tipografia sans-serif.
- Importes en euros con separadores españoles.
"""
import io
import logging
from dataclasses import dataclass

import matplotlib
matplotlib.use("Agg")  # backend sin GUI, para servidores
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

logger = logging.getLogger(__name__)

# Paleta del branding (aproximaciones del PDF de referencia)
COLOR_TEXTO = "#FFFFFF"           # blanco
COLOR_BARRA_RESERVAS = "#F6B26B"  # naranja/melocoton claro (branding)
COLOR_BARRA_CONTRATOS = "#7AB8E5"  # azul claro
COLOR_GRID = "#FFFFFF"            # blanco con baja alpha (grid sutil sobre fondo del slide)


@dataclass
class DatoPeriodo:
    """Un periodo del eje X con sus dos series."""
    etiqueta: str          # 'Abr 25', 'Mar 26', 'Abr 26'
    reservas: float
    contratos: float


def generar_grafico_reservas_arras(periodos: list[DatoPeriodo]) -> bytes:
    """Genera el grafico de barras agrupadas Reservas vs Contratos Firmados.

    Args:
        periodos: lista de 2 o 3 DatoPeriodo.
            - 3 periodos: Valencia (mes-anyo-anterior YoY, mes-anterior, actual).
            - 2 periodos: Alicante (mes-anterior, actual) — sin YoY porque no
              hay datos 2025 de Alicante.

    Returns:
        bytes del PNG.
    """
    if len(periodos) not in (2, 3):
        raise ValueError(f"Se esperan 2 o 3 periodos, recibidos {len(periodos)}.")

    etiquetas = [p.etiqueta for p in periodos]
    valores_reservas = [p.reservas for p in periodos]
    valores_contratos = [p.contratos for p in periodos]

    # Tamaño en pulgadas. Aspect ratio aproximado al espacio del slide.
    # Fondo transparente (el slide ya tiene su propio fondo azul oscuro).
    fig, ax = plt.subplots(figsize=(11, 6))
    fig.patch.set_alpha(0.0)
    ax.set_facecolor("none")

    n = len(periodos)
    posiciones = list(range(n))
    ancho_barra = 0.34       # ancho de cada barra
    gap_intra = 0.04         # separacion entre las dos barras del mismo periodo
    offset = ancho_barra / 2 + gap_intra / 2

    pos_reservas = [p - offset for p in posiciones]
    pos_contratos = [p + offset for p in posiciones]

    barras_r = ax.bar(
        pos_reservas, valores_reservas, width=ancho_barra,
        color=COLOR_BARRA_RESERVAS, label="Reservas",
    )
    barras_c = ax.bar(
        pos_contratos, valores_contratos, width=ancho_barra,
        color=COLOR_BARRA_CONTRATOS, label="Contratos Firmados",
    )

    # Etiquetas de valor encima de cada barra. Cada etiqueta del color de su barra.
    for barras, color in ((barras_r, COLOR_BARRA_RESERVAS), (barras_c, COLOR_BARRA_CONTRATOS)):
        for b in barras:
            altura = b.get_height()
            ax.annotate(
                _formato_euro_compacto(altura),
                xy=(b.get_x() + b.get_width() / 2, altura),
                xytext=(0, 5), textcoords="offset points",
                ha="center", va="bottom",
                color=color, fontsize=14, fontweight="bold",
            )

    # Eje X
    ax.set_xticks(posiciones)
    ax.set_xticklabels(etiquetas, color=COLOR_TEXTO, fontsize=13)
    ax.tick_params(axis="x", colors=COLOR_TEXTO, length=0)

    # Eje Y formato euro con separador miles
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_formato_euro_eje))
    ax.tick_params(axis="y", colors=COLOR_TEXTO, labelsize=10)

    # Grid sutil solo horizontal. Alpha bajo para que no compita con las barras.
    ax.grid(axis="y", color=COLOR_GRID, linewidth=0.5, alpha=0.2)
    ax.set_axisbelow(True)

    # Quitar bordes laterales
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_GRID)

    # Leyenda
    leg = ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=2,
        frameon=False, fontsize=12, labelcolor=COLOR_TEXTO,
    )

    # Margen superior para que las etiquetas no se corten
    ymax = max(max(valores_reservas), max(valores_contratos))
    ax.set_ylim(0, ymax * 1.18)

    plt.tight_layout()

    buf = io.BytesIO()
    # transparent=True preserva la transparencia del fondo en el PNG.
    fig.savefig(buf, format="png", transparent=True, dpi=150)
    plt.close(fig)
    return buf.getvalue()


def _formato_euro_compacto(valor: float) -> str:
    """547139.7 -> '547.139,70€'. Para etiquetas dentro del grafico."""
    entero, dec = divmod(round(valor * 100), 100)
    entero_str = f"{int(entero):,}".replace(",", ".")
    return f"{entero_str},{int(dec):02d}€"


def _formato_euro_eje(valor: float, _pos) -> str:
    """600000 -> '600.000,00 €'. Para ticks del eje Y."""
    if valor == 0:
        return "0,00 €"
    entero_str = f"{int(valor):,}".replace(",", ".")
    return f"{entero_str},00 €"
