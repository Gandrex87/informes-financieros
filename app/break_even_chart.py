"""
Posicionamiento dinamico de un marcador en una barra vertical con HITOS
y CARRILES discretos. Usado hoy en:

- Slide 8 Valencia (Break Even): marcador {{ingresos_totales}} que se
  mueve segun la facturacion cobrada respecto a los umbrales del mes.
- Slide 10 Valencia (Break Even proyectado mes siguiente): marcador
  {{facturacion_objetivo_proy}} que se mueve segun la facturacion
  objetivo proyectada respecto a los umbrales proyectados.

Estructura comun de los slides:
- 4 o 5 hitos visibles a Y fijas (BREAK EVEN, MARGEN N%).
- 5 cuadros INVISIBLES con tokens guia {{_carril_*}} (lo coloca el usuario
  manualmente en la plantilla). Cada uno marca el Y donde aparecera el
  marcador segun el tramo en el que cae el valor a posicionar.
- 1 shape MARCADOR con el token cuyo valor se posiciona.
- (Opcional) 1 shape acompañante con token {{_marker_dot*}}: un circulo
  decorativo que se mueve junto al marcador preservando su offset Y.

Cambio 2026-05-25: posicionamiento DISCRETO por carriles (antes era
interpolacion proporcional Y, que provocaba solapes con las cajas de
hito). Tradeoff aceptado: se pierde la informacion fina de "cuanto se
cubre dentro del tramo", pero gana legibilidad.

Cambio 2026-05-25 (tarde): generalizado para soportar el slide 10 ademas
del 8. La logica de carriles + transform + offset del dot es identica; lo
que varia es:
  - Indice del slide en la plantilla.
  - Token del marcador a mover.
  - Tokens de los 5 cuadros guia.
  - Token del dot acompañante opcional.

Esto se modela en `BreakEvenChartConfig`. Las funciones publicas
`apply_slide_8_marker_position()` y `apply_slide_10_marker_position()`
son delgadas y delegan en `_apply_marker_position(config, ...)`.
"""
from dataclasses import dataclass
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


# ---------- Configuracion por slide ----------

@dataclass(frozen=True)
class BreakEvenChartConfig:
    """Configuracion del posicionamiento de un slide concreto.

    Cada instancia describe UN slide con su barra/marcador. La logica de
    posicionamiento (compute_marker_y, locate_anchors, apply) recibe esta
    config y opera sin saber a que slide concreto pertenece.
    """
    name: str  # solo para logging (ej. "slide 8" o "slide 10").
    slide_index: int  # 0-based.
    token_marker: str  # ej. "{{ingresos_totales}}"
    token_marker_dot: str  # ej. "{{_marker_dot}}"
    token_carril_deficit: str
    token_carril_be_m10: str
    token_carril_m10_m20: str
    token_carril_m20_m30: str
    token_carril_superior: str


# Configuracion canonica del slide 8 (Break Even mes actual, Valencia).
CONFIG_SLIDE_8 = BreakEvenChartConfig(
    name="slide 8",
    slide_index=7,  # 0-based
    token_marker="{{ingresos_totales}}",
    token_marker_dot="{{_marker_dot}}",
    token_carril_deficit="{{_carril_deficit}}",
    token_carril_be_m10="{{_carril_be_m10}}",
    token_carril_m10_m20="{{_carril_m10_m20}}",
    token_carril_m20_m30="{{_carril_m20_m30}}",
    token_carril_superior="{{_carril_superior}}",
)


# Configuracion del slide 10 (Break Even proyectado mes siguiente).
# Mismo patron que el 8 pero con tokens sufijo `_proy`.
CONFIG_SLIDE_10 = BreakEvenChartConfig(
    name="slide 10",
    slide_index=9,  # 0-based
    token_marker="{{facturacion_objetivo_proy}}",
    token_marker_dot="{{_marker_dot_proy}}",
    token_carril_deficit="{{_carril_proy_deficit}}",
    token_carril_be_m10="{{_carril_proy_be_m10}}",
    token_carril_m10_m20="{{_carril_proy_m10_m20}}",
    token_carril_m20_m30="{{_carril_proy_m20_m30}}",
    token_carril_superior="{{_carril_proy_superior}}",
)


# Configuracion del slide 6 de Alicante (Break Even mes actual).
# Equivalente al slide 8 de Valencia (mismo patron, mismos carriles sin
# sufijo `_proy`) PERO con marcador distinto:
# - Valencia slide 8 posiciona {{ingresos_totales}} contra umbrales BD.
# - Alicante slide 6 posiciona {{contratos_firmados}} (arras firmadas)
#   contra los mismos umbrales BD. Decision usuario 2026-05-22: en
#   Alicante la base del marcador y los estados de tabla es arras_total,
#   coherente entre sí. Ver Trampa 5 en docs/MIGRACION_MULTISEDE.md.
# slide_index=5 (0-based) porque Alicante tiene 10 slides en otro orden.
CONFIG_SLIDE_6_ALICANTE = BreakEvenChartConfig(
    name="slide 6 alicante",
    slide_index=5,  # 0-based
    token_marker="{{contratos_firmados}}",
    token_marker_dot="{{_marker_dot}}",
    token_carril_deficit="{{_carril_deficit}}",
    token_carril_be_m10="{{_carril_be_m10}}",
    token_carril_m10_m20="{{_carril_m10_m20}}",
    token_carril_m20_m30="{{_carril_m20_m30}}",
    token_carril_superior="{{_carril_superior}}",
)


# Configuracion del slide 8 de Alicante (Break Even proyectado mes siguiente).
# Equivalente al slide 10 de Valencia (mismos tokens con sufijo `_proy`)
# PERO con slide_index distinto: la plantilla Alicante tiene 10 slides en
# total y el BE proyectado vive en el indice 7 (slide 8 humano).
# CONFIG_SLIDE_10 (slide_index=9) NO sirve para Alicante; busca en el
# indice 9 que en Alicante es "Proximos pasos" (sin carriles).
CONFIG_SLIDE_8_ALICANTE = BreakEvenChartConfig(
    name="slide 8 alicante",
    slide_index=7,  # 0-based
    token_marker="{{facturacion_objetivo_proy}}",
    token_marker_dot="{{_marker_dot_proy}}",
    token_carril_deficit="{{_carril_proy_deficit}}",
    token_carril_be_m10="{{_carril_proy_be_m10}}",
    token_carril_m10_m20="{{_carril_proy_m10_m20}}",
    token_carril_m20_m30="{{_carril_proy_m20_m30}}",
    token_carril_superior="{{_carril_proy_superior}}",
)


# ---------- Estructuras y logica pura ----------

@dataclass
class BreakEvenAnchors:
    """Anclas Y de los 5 carriles + objectId del marcador (y opcional dot).

    Y_carril_* son las coordenadas Y (EMU) de los 5 cuadros guia invisibles
    leidos de la plantilla. marker_object_id es el shape del marcador a mover.

    marker_dot_object_id y dot_y_offset son OPCIONALES: si la plantilla
    tiene el shape acompañante, el codigo lo mueve junto al marcador
    preservando el offset Y original (dot_y_offset = Y_dot - Y_marker en
    la plantilla original). Si no existe, ambos son None.
    """
    y_carril_deficit: float
    y_carril_be_m10: float
    y_carril_m10_m20: float
    y_carril_m20_m30: float
    y_carril_superior: float
    marker_object_id: str
    marker_dot_object_id: str | None = None
    dot_y_offset: float | None = None


def compute_marker_y(
    valor_a_posicionar: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
    anchors: BreakEvenAnchors,
) -> float | None:
    """Devuelve la Y del CARRIL donde debe ir el marcador.

    Posicionamiento discreto: cada tramo tiene una Y fija (el carril
    correspondiente), sin interpolacion. Cinco ramas:
    - valor < break_even        -> carril DEFICIT (zona inferior)
    - break_even <= valor < m10 -> carril BE_M10
    - m10 <= valor < m20        -> carril M10_M20
    - m20 <= valor < m30        -> carril M20_M30
    - valor >= m30              -> carril SUPERIOR

    `valor_a_posicionar` es ingresos_contables en slide 8 y
    facturacion_objetivo_proy en slide 10 — la logica es la misma.

    Devuelve None si falta algun dato (no se mueve el marcador).
    """
    if (
        valor_a_posicionar is None or valor_break_even is None
        or valor_margen_10 is None or valor_margen_20 is None
        or valor_margen_30 is None
    ):
        return None

    valor = Decimal(str(valor_a_posicionar))
    vbe = Decimal(str(valor_break_even))
    v10 = Decimal(str(valor_margen_10))
    v20 = Decimal(str(valor_margen_20))
    v30 = Decimal(str(valor_margen_30))

    if valor < vbe:
        return anchors.y_carril_deficit
    if valor < v10:
        return anchors.y_carril_be_m10
    if valor < v20:
        return anchors.y_carril_m10_m20
    if valor < v30:
        return anchors.y_carril_m20_m30
    return anchors.y_carril_superior


def _walk_text_shapes(elements, parent_translate_y: float = 0.0):
    """Itera recursivamente shapes de texto en pageElements y dentro de
    elementGroups, devolviendo (objectId, y_absoluta, texto_completo, el).

    Y absoluta = translateY del shape + translateY del grupo padre
    (Slides Y es relativa al contenedor: dentro de un grupo, hay que
    componer con la Y del grupo).
    """
    for el in elements:
        my_ty = parent_translate_y + el.get("transform", {}).get("translateY", 0)
        if "elementGroup" in el:
            yield from _walk_text_shapes(
                el["elementGroup"].get("children", []), my_ty,
            )
        elif "shape" in el and "text" in el.get("shape", {}):
            full = "".join(
                r.get("textRun", {}).get("content", "")
                for r in el["shape"]["text"].get("textElements", [])
                if r.get("textRun")
            )
            yield (el.get("objectId", ""), my_ty, full, el)


def locate_anchors(
    slides, presentation_id: str, config: BreakEvenChartConfig,
) -> BreakEvenAnchors | None:
    """Lee la plantilla y devuelve las anclas Y de los 5 carriles del slide
    indicado por la config.

    Identifica los shapes por los TOKENS de la config. Solo busca dentro del
    slide pedido (config.slide_index) — el token del marcador puede aparecer
    en otros slides (ej. {{ingresos_totales}} en slide 1) y NO debe moverse
    alli.

    Devuelve None (con WARNING) si falta alguno de los shapes obligatorios
    (5 carriles + marcador); en ese caso el caller debe omitir el
    reposicionamiento. El shape acompañante (dot) es opcional.
    """
    pres = slides.presentations().get(presentationId=presentation_id).execute()
    slides_list = pres.get("slides", [])
    if len(slides_list) <= config.slide_index:
        logger.warning(
            "Plantilla con menos de %d slides; no se posiciona %s.",
            config.slide_index + 1, config.name,
        )
        return None

    # target_token -> (objectId, y_abs). El token del dot es OPCIONAL.
    target_tokens: dict[str, tuple[str, float] | None] = {
        config.token_carril_deficit: None,
        config.token_carril_be_m10: None,
        config.token_carril_m10_m20: None,
        config.token_carril_m20_m30: None,
        config.token_carril_superior: None,
        config.token_marker: None,
        config.token_marker_dot: None,  # opcional
    }
    OPTIONAL_TOKENS = {config.token_marker_dot}

    for oid, y_abs, full, _el in _walk_text_shapes(
        slides_list[config.slide_index].get("pageElements", [])
    ):
        for tok in target_tokens:
            if tok in full and target_tokens[tok] is None:
                target_tokens[tok] = (oid, y_abs)

    missing_required = [
        tok for tok, v in target_tokens.items()
        if v is None and tok not in OPTIONAL_TOKENS
    ]
    if missing_required:
        logger.warning(
            "%s sin algun shape obligatorio (%s); no se posiciona marcador. "
            "Comprueba que la plantilla tiene los 5 cuadros guia y el marcador.",
            config.name, ", ".join(missing_required),
        )
        return None

    # Si el shape acompañante existe, calcular el offset Y respecto al
    # marcador (a preservar en cada movimiento).
    marker_dot_oid: str | None = None
    dot_y_offset: float | None = None
    dot_entry = target_tokens[config.token_marker_dot]
    if dot_entry is not None:
        marker_dot_oid = dot_entry[0]
        marker_y = target_tokens[config.token_marker][1]
        dot_y_offset = dot_entry[1] - marker_y

    return BreakEvenAnchors(
        y_carril_deficit=target_tokens[config.token_carril_deficit][1],
        y_carril_be_m10=target_tokens[config.token_carril_be_m10][1],
        y_carril_m10_m20=target_tokens[config.token_carril_m10_m20][1],
        y_carril_m20_m30=target_tokens[config.token_carril_m20_m30][1],
        y_carril_superior=target_tokens[config.token_carril_superior][1],
        marker_object_id=target_tokens[config.token_marker][0],
        marker_dot_object_id=marker_dot_oid,
        dot_y_offset=dot_y_offset,
    )


def _apply_marker_position(
    slides,
    presentation_id: str,
    config: BreakEvenChartConfig,
    valor_a_posicionar: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
) -> None:
    """Logica interna comun: posiciona el marcador del slide configurado en
    uno de los 5 carriles.

    Idempotente: usa ABSOLUTE en el transform. Si falta algun dato o la
    plantilla no tiene los shapes esperados, registra WARNING y no toca nada.
    """
    anchors = locate_anchors(slides, presentation_id, config)
    if anchors is None:
        return

    y_destino = compute_marker_y(
        valor_a_posicionar, valor_break_even, valor_margen_10,
        valor_margen_20, valor_margen_30, anchors,
    )
    if y_destino is None:
        logger.warning(
            "Falta algun dato para posicionar marcador en %s; no se mueve.",
            config.name,
        )
        return

    # Para preservar X y escala, leer el transform actual del marcador y
    # (opcional) del dot. Busqueda recursiva en grupos.
    pres = slides.presentations().get(presentationId=presentation_id).execute()
    marker_transform = None
    dot_transform = None
    for oid, _y_abs, _full, el in _walk_text_shapes(
        pres["slides"][config.slide_index].get("pageElements", [])
    ):
        if oid == anchors.marker_object_id:
            marker_transform = el.get("transform", {})
        elif (
            anchors.marker_dot_object_id is not None
            and oid == anchors.marker_dot_object_id
        ):
            dot_transform = el.get("transform", {})
        if marker_transform is not None and (
            anchors.marker_dot_object_id is None or dot_transform is not None
        ):
            break
    if marker_transform is None:
        logger.warning("Marcador %s no encontrado al releer; no se mueve.", config.name)
        return

    requests = [
        {
            "updatePageElementTransform": {
                "objectId": anchors.marker_object_id,
                "transform": {
                    "scaleX": marker_transform.get("scaleX", 1),
                    "scaleY": marker_transform.get("scaleY", 1),
                    "translateX": marker_transform.get("translateX", 0),
                    "translateY": y_destino,
                    "unit": marker_transform.get("unit", "EMU"),
                },
                "applyMode": "ABSOLUTE",
            }
        },
    ]

    # Si hay shape acompañante (circulo dorado), moverlo en el MISMO
    # batchUpdate preservando su offset Y original respecto al marcador.
    moved_dot = False
    if (
        anchors.marker_dot_object_id is not None
        and anchors.dot_y_offset is not None
        and dot_transform is not None
    ):
        requests.append({
            "updatePageElementTransform": {
                "objectId": anchors.marker_dot_object_id,
                "transform": {
                    "scaleX": dot_transform.get("scaleX", 1),
                    "scaleY": dot_transform.get("scaleY", 1),
                    "translateX": dot_transform.get("translateX", 0),
                    "translateY": y_destino + anchors.dot_y_offset,
                    "unit": dot_transform.get("unit", "EMU"),
                },
                "applyMode": "ABSOLUTE",
            }
        })
        moved_dot = True

    slides.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests},
    ).execute()
    logger.info(
        "%s: marcador %s posicionado en carril Y=%.0f%s "
        "(carriles: deficit=%.0f, be_m10=%.0f, m10_m20=%.0f, m20_m30=%.0f, superior=%.0f).",
        config.name,
        config.token_marker,
        y_destino,
        f" + dot Y={y_destino + anchors.dot_y_offset:.0f}" if moved_dot else "",
        anchors.y_carril_deficit,
        anchors.y_carril_be_m10,
        anchors.y_carril_m10_m20,
        anchors.y_carril_m20_m30,
        anchors.y_carril_superior,
    )


# ---------- API publica (una funcion por uso real) ----------

def apply_slide_8_marker_position(
    slides,
    presentation_id: str,
    ingresos: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
) -> None:
    """Posiciona {{ingresos_totales}} en la barra del slide 8 (Break Even
    mes actual).

    Idempotente: usa ABSOLUTE. Si falta algun dato o la plantilla no tiene
    los 5 carriles + marcador, registra WARNING y no toca nada.
    """
    _apply_marker_position(
        slides, presentation_id, CONFIG_SLIDE_8,
        ingresos, valor_break_even,
        valor_margen_10, valor_margen_20, valor_margen_30,
    )


def apply_slide_10_marker_position(
    slides,
    presentation_id: str,
    facturacion_objetivo_proy: Decimal | float | None,
    valor_break_even_proy: Decimal | float | None,
    valor_margen_10_proy: Decimal | float | None,
    valor_margen_20_proy: Decimal | float | None,
    valor_margen_30_proy: Decimal | float | None,
) -> None:
    """Posiciona {{facturacion_objetivo_proy}} en la barra del slide 10
    (Break Even proyectado mes siguiente).

    Compara contra los umbrales PROYECTADOS del mes siguiente (`_proy`).

    Idempotente: usa ABSOLUTE. Si falta algun dato o la plantilla no tiene
    los 5 carriles + marcador, registra WARNING y no toca nada.
    """
    _apply_marker_position(
        slides, presentation_id, CONFIG_SLIDE_10,
        facturacion_objetivo_proy, valor_break_even_proy,
        valor_margen_10_proy, valor_margen_20_proy, valor_margen_30_proy,
    )


def apply_slide_6_alicante_marker_position(
    slides,
    presentation_id: str,
    contratos_firmados: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
) -> None:
    """Posiciona {{contratos_firmados}} en la barra del slide 6 de Alicante
    (Break Even mes actual).

    Equivalente funcional al slide 8 de Valencia, pero el marcador y el
    valor a posicionar son `contratos_firmados` (arras firmadas), no
    `ingresos_totales`. Los 4 umbrales son los del mes actual (sin _proy).

    Idempotente: usa ABSOLUTE. Si falta algun dato o la plantilla no tiene
    los 5 carriles + marcador, registra WARNING y no toca nada.
    """
    _apply_marker_position(
        slides, presentation_id, CONFIG_SLIDE_6_ALICANTE,
        contratos_firmados, valor_break_even,
        valor_margen_10, valor_margen_20, valor_margen_30,
    )


def apply_slide_8_alicante_marker_position(
    slides,
    presentation_id: str,
    facturacion_objetivo_proy: Decimal | float | None,
    valor_break_even_proy: Decimal | float | None,
    valor_margen_10_proy: Decimal | float | None,
    valor_margen_20_proy: Decimal | float | None,
    valor_margen_30_proy: Decimal | float | None,
) -> None:
    """Posiciona {{facturacion_objetivo_proy}} en la barra del slide 8 de
    Alicante (Break Even proyectado mes siguiente).

    Equivalente funcional al slide 10 de Valencia (mismos tokens con
    sufijo `_proy`) pero apunta al slide_index=7 (la plantilla Alicante
    tiene el BE proyectado ahi, no en el indice 9).

    Idempotente: usa ABSOLUTE. Si falta algun dato o la plantilla no tiene
    los 5 carriles + marcador, registra WARNING y no toca nada.
    """
    _apply_marker_position(
        slides, presentation_id, CONFIG_SLIDE_8_ALICANTE,
        facturacion_objetivo_proy, valor_break_even_proy,
        valor_margen_10_proy, valor_margen_20_proy, valor_margen_30_proy,
    )


# ---------- Compatibilidad hacia atras ----------
# El generator.py llama hoy a `apply_breakeven_marker_position()`. Hasta que
# se migre el caller, mantenemos esta funcion como alias del slide 8.

apply_breakeven_marker_position = apply_slide_8_marker_position
