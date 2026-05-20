"""
Posicionamiento dinamico del marcador {{ingresos_totales}} en la barra
del slide 8 (Break Even).

La plantilla del slide 8 tiene una "barra/linea de tiempo" vertical con 4
hitos a alturas Y fijas (de arriba a abajo): MARGEN 30%, MARGEN 20%,
MARGEN 10%, BREAK EVEN (0%). Entre ellos vive el marcador
{{ingresos_totales}} ("FACTURACION COBRADA"), que en la plantilla esta
colocado a mano entre 30% y 20% porque para el mes original cuadraba.

Para que el slide 8 sea correcto en otros meses (donde los ingresos
pueden caer mas arriba/abajo), movemos el shape de {{ingresos_totales}}
via Slides API segun la posicion proporcional que le corresponde dentro
de la barra.

Logica separada en dos capas:
- locate_breakeven_anchors(): lee la plantilla y devuelve las anclas
  Y reales de los 4 hitos + el objectId del marcador a mover. Asi el
  codigo se adapta si en la plantilla se mueven los hitos.
- compute_marker_y(): funcion PURA (sin Slides API) que dado los valores
  y las anclas calcula el Y destino. Facil de testear unitariamente.
- apply_breakeven_marker_position(): orquesta: obtiene anclas, calcula
  Y, manda updatePageElementTransform.
"""
from dataclasses import dataclass
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Indice del slide 8 en la plantilla (0-based).
SLIDE_8_INDEX = 7

# Tokens que identifican los 4 hitos de la barra y el marcador.
TOKEN_MARGEN_30 = "{{margen_30_objetivo}}"
TOKEN_MARGEN_20 = "{{margen_20_objetivo}}"
TOKEN_MARGEN_10 = "{{margen_10_objetivo}}"
TOKEN_BREAK_EVEN = "{{break_even}}"
TOKEN_INGRESOS = "{{ingresos_totales}}"


@dataclass
class BreakEvenAnchors:
    """Anclas Y de los 4 hitos del slide 8 + objectId del marcador.

    Y_* son las coordenadas Y (EMU) de los shapes de cada hito en la
    plantilla. marker_object_id es el shape del slide 8 a mover.
    """
    y_margen_30: float
    y_margen_20: float
    y_margen_10: float
    y_break_even: float
    marker_object_id: str


def compute_marker_y(
    ingresos: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
    anchors: BreakEvenAnchors,
) -> float | None:
    """Calcula la Y donde debe ir el marcador {{ingresos_totales}}.

    Interpola linealmente entre el hito inmediatamente inferior y el
    superior segun la posicion del ingreso. Topa a los extremos:
    - ingresos <= break_even   -> Y = Y_break_even (fondo).
    - ingresos >= margen_30    -> Y = Y_margen_30  (techo).

    Devuelve None si falta algun dato (no se mueve el marcador).
    Recuerda: Y crece hacia abajo en Slides API, asi que un valor
    mayor de ingresos = Y menor (mas arriba).
    """
    if ingresos is None or valor_break_even is None or valor_margen_10 is None \
       or valor_margen_20 is None or valor_margen_30 is None:
        return None

    ingresos = Decimal(str(ingresos))
    vbe = Decimal(str(valor_break_even))
    v10 = Decimal(str(valor_margen_10))
    v20 = Decimal(str(valor_margen_20))
    v30 = Decimal(str(valor_margen_30))

    if ingresos <= vbe:
        return anchors.y_break_even
    if ingresos >= v30:
        return anchors.y_margen_30

    # Encontrar el tramo (V_b, V_a) y sus anclas (Y_b, Y_a).
    if ingresos < v10:
        v_b, v_a, y_b, y_a = vbe, v10, anchors.y_break_even, anchors.y_margen_10
    elif ingresos < v20:
        v_b, v_a, y_b, y_a = v10, v20, anchors.y_margen_10, anchors.y_margen_20
    else:  # v20 <= ingresos < v30
        v_b, v_a, y_b, y_a = v20, v30, anchors.y_margen_20, anchors.y_margen_30

    # Interpolacion proporcional dentro del tramo.
    ratio = (ingresos - v_b) / (v_a - v_b)
    return float(y_b) + float(ratio) * (float(y_a) - float(y_b))


def _walk_text_shapes(elements, parent_translate_y: float = 0.0):
    """Itera recursivamente shapes de texto en pageElements y dentro de
    elementGroups, devolviendo (objectId, y_absoluta, texto_completo).

    Y absoluta = translateY del shape + translateY del grupo padre
    (Slides Y es relativa al contenedor: dentro de un grupo, hay que
    componer con la Y del grupo). Esto importa porque los hitos del
    slide 8 estan dentro de grupos.
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


def locate_breakeven_anchors(slides, presentation_id: str) -> BreakEvenAnchors | None:
    """Lee la plantilla y devuelve las anclas Y de los 4 hitos del slide 8.

    Identifica los shapes por el TOKEN que contienen ({{margen_N_objetivo}},
    {{break_even}}, {{ingresos_totales}}). Solo busca dentro del slide 8 — el
    token {{ingresos_totales}} tambien aparece en slide 1 portada y NO debe
    moverse alli.

    Camina recursivamente dentro de elementGroups (4 de los 5 hitos del slide 8
    estan agrupados en la plantilla) y compone la Y absoluta del shape con la
    del grupo padre.

    Devuelve None (con WARNING) si falta alguno de los 5 shapes esperados;
    en ese caso el caller debe omitir el reposicionamiento.
    """
    pres = slides.presentations().get(presentationId=presentation_id).execute()
    slides_list = pres.get("slides", [])
    if len(slides_list) <= SLIDE_8_INDEX:
        logger.warning("Plantilla con menos de %d slides; no se posiciona break even.", SLIDE_8_INDEX + 1)
        return None

    # target_token -> (objectId, y_abs)
    target_tokens: dict[str, tuple[str, float] | None] = {
        TOKEN_MARGEN_30: None,
        TOKEN_MARGEN_20: None,
        TOKEN_MARGEN_10: None,
        TOKEN_BREAK_EVEN: None,
        TOKEN_INGRESOS: None,
    }

    for oid, y_abs, full, _el in _walk_text_shapes(
        slides_list[SLIDE_8_INDEX].get("pageElements", [])
    ):
        for tok in target_tokens:
            if tok in full and target_tokens[tok] is None:
                target_tokens[tok] = (oid, y_abs)

    missing = [tok for tok, v in target_tokens.items() if v is None]
    if missing:
        logger.warning(
            "Slide 8 sin algun shape de break even (%s); no se posiciona marcador.",
            ", ".join(missing),
        )
        return None

    return BreakEvenAnchors(
        y_margen_30=target_tokens[TOKEN_MARGEN_30][1],
        y_margen_20=target_tokens[TOKEN_MARGEN_20][1],
        y_margen_10=target_tokens[TOKEN_MARGEN_10][1],
        y_break_even=target_tokens[TOKEN_BREAK_EVEN][1],
        marker_object_id=target_tokens[TOKEN_INGRESOS][0],
    )


def apply_breakeven_marker_position(
    slides,
    presentation_id: str,
    ingresos: Decimal | float | None,
    valor_break_even: Decimal | float | None,
    valor_margen_10: Decimal | float | None,
    valor_margen_20: Decimal | float | None,
    valor_margen_30: Decimal | float | None,
) -> None:
    """Posiciona el marcador {{ingresos_totales}} en la barra del slide 8.

    Idempotente: usa modo ABSOLUTE en el transform (no relativo al
    actual). Si algun dato falta o la plantilla no tiene los hitos
    esperados, registra un WARNING y no toca nada (el shape queda
    donde estaba en la plantilla).
    """
    anchors = locate_breakeven_anchors(slides, presentation_id)
    if anchors is None:
        return

    y_destino = compute_marker_y(
        ingresos, valor_break_even, valor_margen_10,
        valor_margen_20, valor_margen_30, anchors,
    )
    if y_destino is None:
        logger.warning("Falta algun dato para posicionar marcador break even; no se mueve.")
        return

    # Para preservar X y escala del shape, leemos su transform actual y
    # solo cambiamos translateY. Usamos ABSOLUTE para que el transform
    # final coincida exactamente con lo que enviamos. Busqueda recursiva
    # (defensiva por si la plantilla cambia y el marcador queda dentro
    # de un grupo).
    pres = slides.presentations().get(presentationId=presentation_id).execute()
    current_transform = None
    for oid, _y_abs, _full, el in _walk_text_shapes(
        pres["slides"][SLIDE_8_INDEX].get("pageElements", [])
    ):
        if oid == anchors.marker_object_id:
            current_transform = el.get("transform", {})
            break
    if current_transform is None:
        logger.warning("Marcador break even no encontrado al releer; no se mueve.")
        return

    new_transform = {
        "scaleX": current_transform.get("scaleX", 1),
        "scaleY": current_transform.get("scaleY", 1),
        "translateX": current_transform.get("translateX", 0),
        "translateY": y_destino,
        "unit": current_transform.get("unit", "EMU"),
    }

    slides.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [{
            "updatePageElementTransform": {
                "objectId": anchors.marker_object_id,
                "transform": new_transform,
                "applyMode": "ABSOLUTE",
            }
        }]},
    ).execute()
    logger.info(
        "Slide 8: marcador {{ingresos_totales}} posicionado en Y=%.0f (anchors m30=%.0f m20=%.0f m10=%.0f be=%.0f).",
        y_destino, anchors.y_margen_30, anchors.y_margen_20, anchors.y_margen_10, anchors.y_break_even,
    )
