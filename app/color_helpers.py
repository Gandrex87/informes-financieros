"""
Logica para aplicar colores condicionales a tokens reemplazados en la presentacion.

Flujo:
1. Despues del replaceAllText, el cliente sabe que valores quedaron en cada token.
2. Para cada token con override, buscamos en el deck shapes/celdas que contengan
   ese valor exacto.
3. Aplicamos updateTextStyle a cada coincidencia con el color elegido.

Soporta cajas de texto sueltas (shapes) y celdas de tablas nativas.
"""
import logging
from typing import Iterable

from app.colors import get_color

logger = logging.getLogger(__name__)


def _extract_text(text_block: dict) -> str:
    """Extrae el texto plano de un text block (forma comun en shape.text y cell.text)."""
    parts = []
    for el in text_block.get("textElements", []):
        run = el.get("textRun")
        if run and "content" in run:
            parts.append(run["content"])
    return "".join(parts).strip()


def find_text_locations(deck: dict, contains: str) -> list[dict]:
    """Busca shapes/celdas cuyo texto contiene la subcadena dada.

    Devuelve lista de localizaciones, cada una con la info necesaria para
    apuntar a ella con updateTextStyle:

    Para shapes:
        {object_id, kind: "shape", full_text}

    Para celdas de tabla:
        {object_id, kind: "cell", row, col, full_text}
        (object_id es el de la tabla contenedora, no de la celda)
    """
    matches = []
    for slide in deck.get("slides", []):
        for el in slide.get("pageElements", []):
            if "shape" in el:
                text = _extract_text(el["shape"].get("text", {}))
                if contains in text:
                    matches.append({
                        "object_id": el["objectId"],
                        "kind": "shape",
                        "full_text": text,
                    })
            elif "table" in el:
                for row_idx, row in enumerate(el["table"].get("tableRows", [])):
                    for col_idx, cell in enumerate(row.get("tableCells", [])):
                        text = _extract_text(cell.get("text", {}))
                        if contains in text:
                            matches.append({
                                "object_id": el["objectId"],
                                "kind": "cell",
                                "row": row_idx,
                                "col": col_idx,
                                "full_text": text,
                            })
    return matches


def build_color_request(location: dict, color: dict) -> dict:
    """Construye una request updateTextStyle para una localizacion concreta."""
    req = {
        "updateTextStyle": {
            "objectId": location["object_id"],
            "textRange": {"type": "ALL"},
            "style": {"foregroundColor": {"opaqueColor": {"rgbColor": color}}},
            "fields": "foregroundColor",
        }
    }
    if location["kind"] == "cell":
        req["updateTextStyle"]["cellLocation"] = {
            "rowIndex": location["row"],
            "columnIndex": location["col"],
        }
    return req


def apply_color_overrides(
    slides_client,
    presentation_id: str,
    overrides: dict[str, str],
    replaced_data: dict[str, str],
) -> tuple[int, list[str]]:
    """Aplica colores a tokens recien reemplazados.

    Args:
        slides_client: cliente Slides autenticado.
        presentation_id: id de la presentacion (la copia, no la plantilla).
        overrides: {token_name: color_name}, ej. {"margen_30_estado": "rojo"}.
        replaced_data: el dict de datos plano que se uso en replaceAllText,
                       necesario para saber el valor que dejo cada token.

    Returns:
        (total_localizaciones_coloreadas, lista_de_tokens_sin_match).
    """
    if not overrides:
        return 0, []

    # Leemos el deck UNA vez tras los replaces.
    deck = slides_client.presentations().get(presentationId=presentation_id).execute()

    requests = []
    not_found = []
    total_locations = 0

    for token, color_name in overrides.items():
        value = replaced_data.get(token)
        if not value:
            logger.warning(
                "Color override para token '%s' pero no esta en los datos.", token
            )
            not_found.append(token)
            continue

        color = get_color(color_name)
        locations = find_text_locations(deck, str(value))

        if not locations:
            logger.warning(
                "Color override token '%s' (valor=%r): no se encontro en la presentacion.",
                token, value,
            )
            not_found.append(token)
            continue

        for loc in locations:
            requests.append(build_color_request(loc, color))
        total_locations += len(locations)
        logger.info(
            "Color override token '%s' -> %d localizacion(es) con '%s'.",
            token, len(locations), color_name,
        )

    if requests:
        slides_client.presentations().batchUpdate(
            presentationId=presentation_id,
            body={"requests": requests},
        ).execute()

    return total_locations, not_found
