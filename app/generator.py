"""
Generador del informe: dado un dict de datos, produce el PDF en bytes.

Logica pura (sin filesystem para el output, sin prints), reutilizable
tanto desde el script CLI como desde el endpoint FastAPI.
"""
import io
import logging
import os
from datetime import datetime
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from app.chart_generator import DatoPeriodo, generar_grafico_reservas_arras
from app.color_helpers import apply_color_overrides
from app.image_helpers import (
    delete_drive_file,
    replace_shape_with_image,
    upload_temp_image,
)
from app.token_helpers import expand_lists

logger = logging.getLogger(__name__)


# Clave especial en el payload que define color condicional por token.
COLOR_OVERRIDES_KEY = "_color_overrides"

# Clave del payload con los datos del grafico del slide 3.
CHART_RESERVAS_ARRAS_KEY = "_chart_reservas_arras"
CHART_RESERVAS_ARRAS_TOKEN = "{{grafico_reservas_arras}}"


# Especificacion de listas que se expanden a slots numerados antes de
# enviar al Slides API. Si añades una lista nueva al payload, agregala aqui.
LIST_SPECS = [
    {
        "key": "pipeline_alquiler",
        "prefix": "pipeline_alq",
        "n_max": 8,
        "fields": ["nombre", "importe"],
    },
    {
        "key": "comisiones_atrasos",
        "prefix": "comision_atraso",
        "n_max": 10,
        "fields": ["nombre", "mes", "tramo", "importe"],
    },
    {
        "key": "operaciones_condicionadas",
        "prefix": "condicionada",
        "n_max": 12,
        "fields": ["nombre", "importe"],
    },
    {
        "key": "cobros_pendientes",
        "prefix": "cobro",
        "n_max": 26,
        "fields": ["nombre", "importe"],
    },
    {
        "key": "ventas_pendientes",
        "prefix": "venta_pend",
        "n_max": 21,
        "fields": ["nombre", "importe"],
    },
    {
        # Reutiliza la lista del slide 4 con prefijo distinto para slide 5.
        "key": "pipeline_alquiler",
        "prefix": "venta_alq_pend",
        "n_max": 6,
        "fields": ["nombre", "importe"],
    },
    {
        "key": "obras_nuevas",
        "prefix": "obra_nueva",
        "n_max": 4,
        "fields": ["nombre", "importe"],
    },
]


class GenerationError(Exception):
    """Error generando el informe (problema con APIs de Google)."""


def _copy_template(drive, template_id: str, new_name: str, folder_id: str) -> str:
    body = {"name": new_name}
    if folder_id:
        body["parents"] = [folder_id]
    # supportsAllDrives=True es OBLIGATORIO para operar dentro de Shared Drives
    # (Service Account). Inofensivo con OAuth en Mi unidad.
    copied = drive.files().copy(
        fileId=template_id, body=body, supportsAllDrives=True,
    ).execute()
    return copied["id"]


def _replace_tokens(slides, presentation_id: str, data: dict) -> tuple[int, list[str]]:
    """Reemplaza tokens. Devuelve (total_reemplazos, lista_de_tokens_no_encontrados)."""
    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": f"{{{{{key}}}}}", "matchCase": True},
                "replaceText": str(value),
            }
        }
        for key, value in data.items()
    ]
    response = slides.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": requests},
    ).execute()

    total = 0
    missing = []
    keys = list(data.keys())
    for i, reply in enumerate(response.get("replies", [])):
        count = reply.get("replaceAllText", {}).get("occurrencesChanged", 0)
        total += count
        if count == 0:
            missing.append(keys[i])
    return total, missing


def _export_pdf_bytes(drive, presentation_id: str) -> bytes:
    request = drive.files().export_media(
        fileId=presentation_id,
        mimeType="application/pdf",
    )
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _cleanup_copy(drive, presentation_id: str) -> None:
    drive.files().delete(
        fileId=presentation_id, supportsAllDrives=True,
    ).execute()


def generate_report(
    data: dict,
    slides_client,
    drive_client,
    template_id: str | None = None,
    folder_id: str | None = None,
    copy_name_prefix: str = "_tmp_informe",
) -> bytes:
    """Genera el informe y devuelve el PDF como bytes.

    Args:
        data: dict con todos los tokens (keys planas + listas a expandir).
        slides_client, drive_client: clientes ya autenticados.
        template_id: ID del Slides plantilla. Si None, lee SLIDES_TEMPLATE_ID.
        folder_id: ID carpeta destino en Drive. Si None o vacio, raiz de Mi unidad.
        copy_name_prefix: prefijo del nombre de la copia intermedia.

    Returns:
        bytes del PDF generado.

    Raises:
        GenerationError: si algo falla con las APIs de Google.
    """
    template_id = template_id or os.environ["SLIDES_TEMPLATE_ID"]
    folder_id = folder_id if folder_id is not None else os.environ.get("DRIVE_FOLDER_ID", "").strip()

    # Extraer overrides de color y datos de graficos (no son tokens
    # de replaceAllText, se procesan aparte).
    color_overrides = data.get(COLOR_OVERRIDES_KEY, {}) or {}
    chart_reservas_arras = data.get(CHART_RESERVAS_ARRAS_KEY)

    special_keys = {COLOR_OVERRIDES_KEY, CHART_RESERVAS_ARRAS_KEY}
    data_clean = {k: v for k, v in data.items() if k not in special_keys}

    expanded = expand_lists(data_clean, LIST_SPECS)
    logger.info("Datos: %d campos originales, %d tokens tras expandir.", len(data_clean), len(expanded))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    copy_name = f"{copy_name_prefix}_{timestamp}"

    copy_id = None
    try:
        copy_id = _copy_template(drive_client, template_id, copy_name, folder_id)
        logger.info("Copia creada: %s (%s)", copy_name, copy_id)

        total, missing = _replace_tokens(slides_client, copy_id, expanded)
        logger.info("%d reemplazos efectivos.", total)
        if missing:
            logger.warning("Tokens no encontrados en plantilla: %s", ", ".join(missing))

        if color_overrides:
            colored, not_found = apply_color_overrides(
                slides_client, copy_id, color_overrides, expanded
            )
            logger.info("%d localizaciones coloreadas.", colored)
            if not_found:
                logger.warning("Overrides sin match: %s", ", ".join(not_found))

        # Insertar grafico del slide 3 (si vinieron datos en el payload).
        chart_drive_id = None
        if chart_reservas_arras:
            try:
                periodos = [DatoPeriodo(**p) for p in chart_reservas_arras]
                png_bytes = generar_grafico_reservas_arras(periodos)
                chart_drive_id = upload_temp_image(
                    drive_client, png_bytes, f"_chart_reservas_arras_{copy_id}.png",
                )
                count = replace_shape_with_image(
                    slides_client, copy_id, CHART_RESERVAS_ARRAS_TOKEN, chart_drive_id,
                )
                if count == 0:
                    logger.warning(
                        "Token '%s' no encontrado en la plantilla; el grafico no se inserto.",
                        CHART_RESERVAS_ARRAS_TOKEN,
                    )
            except Exception as e:
                logger.exception("Error insertando grafico: %s", e)

        pdf_bytes = _export_pdf_bytes(drive_client, copy_id)
        logger.info("PDF generado: %d bytes.", len(pdf_bytes))

        # Limpieza del PNG temporal (mejor esfuerzo).
        if chart_drive_id:
            delete_drive_file(drive_client, chart_drive_id)

        return pdf_bytes

    except HttpError as e:
        raise GenerationError(f"Error en Google API: {e}") from e
    finally:
        if copy_id:
            try:
                _cleanup_copy(drive_client, copy_id)
                logger.info("Copia intermedia borrada.")
            except HttpError as e:
                logger.warning("No se pudo borrar la copia %s: %s", copy_id, e)
