"""
Helpers para insertar imagenes generadas dinamicamente en la presentacion.

Flujo tipico:
1. upload_temp_image: sube bytes PNG a Drive, le da permiso publico de lectura,
   y espera a confirmar que la URL responde antes de devolver.
2. replace_shape_with_image: sustituye un shape con texto dado por la imagen.
   Reintenta si la primera llamada falla (puede ser timing con Drive).
3. delete_drive_file: borra el PNG de Drive tras exportar el PDF.

NOTA: el permiso publico es transitorio. La URL es pseudo-aleatoria y se borra
tras exportar. Para un caso con datos sensibles, evaluar Shared Drive en lugar
de cuenta personal.
"""
import io
import logging
import os
import time

import urllib.request
import urllib.error
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)


def _public_url(file_id: str) -> str:
    """URL publica del PNG en Drive que Slides API puede descargar.

    `drive.google.com/uc?id=X` ya no es fiable (devuelve HTML virus-scan).
    `drive.google.com/thumbnail?id=X&sz=w2000` SI sirve bytes directos.
    """
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w2000"


def upload_temp_image(drive, image_bytes: bytes, name: str) -> str:
    """Sube PNG a Drive, lo hace publicamente legible, y espera a que sea
    realmente accesible antes de devolver.

    El "wait" es importante: a veces Drive tarda unos segundos en propagar el
    permiso publico, y si Slides API intenta descargar antes, falla con un 400
    "image not publicly accessible".
    """
    metadata = {"name": name, "mimeType": "image/png"}
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "").strip()
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/png")
    file = drive.files().create(
        body=metadata, media_body=media, fields="id",
        supportsAllDrives=True,
    ).execute()
    file_id = file["id"]

    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
        supportsAllDrives=True,
    ).execute()
    logger.info("Imagen temporal subida: %s", file_id)

    # Espera activa a que la URL publica responda 200. Hasta ~10s.
    _wait_public_url_ready(file_id, timeout_seconds=10.0)
    return file_id


def _wait_public_url_ready(file_id: str, timeout_seconds: float = 10.0) -> bool:
    """Hace HEADs al endpoint thumbnail hasta que responda 200, o timeout.

    Devuelve True si llego a estar listo, False si timeout. No levanta — el
    caller decide si seguir o no (replace_shape_with_image reintenta igual).
    """
    url = _public_url(file_id)
    deadline = time.monotonic() + timeout_seconds
    delay = 0.5
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    logger.info("URL publica lista tras ~%.1fs", time.monotonic() - (deadline - timeout_seconds))
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 2.0)  # backoff suave
    logger.warning("URL publica del PNG %s no confirmada tras %.1fs; sigo igual.", file_id, timeout_seconds)
    return False


def replace_shape_with_image(
    slides_client, presentation_id: str, contains_text: str, image_file_id: str,
    max_retries: int = 3,
) -> int:
    """Sustituye los shapes que contienen el texto dado por la imagen.

    Reintenta hasta `max_retries` veces si Slides API falla por timing en la
    descarga (error 400 con mensaje "publicly accessible"). Backoff exponencial.

    Devuelve el numero de shapes reemplazados.
    """
    request = {
        "replaceAllShapesWithImage": {
            "imageUrl": _public_url(image_file_id),
            "imageReplaceMethod": "CENTER_INSIDE",
            "containsText": {"text": contains_text, "matchCase": True},
        }
    }

    delay = 1.0
    for intento in range(1, max_retries + 1):
        try:
            response = slides_client.presentations().batchUpdate(
                presentationId=presentation_id,
                body={"requests": [request]},
            ).execute()
            reply = response.get("replies", [{}])[0].get("replaceAllShapesWithImage", {})
            count = reply.get("occurrencesChanged", 0)
            logger.info(
                "replaceAllShapesWithImage('%s'): %d shape(s) sustituidos (intento %d).",
                contains_text, count, intento,
            )
            return count
        except HttpError as e:
            es_problema_imagen = (
                e.resp.status == 400
                and "publicly accessible" in str(e).lower()
            )
            if not es_problema_imagen or intento == max_retries:
                raise
            logger.warning(
                "Intento %d falla por timing de imagen; reintentando en %.1fs.",
                intento, delay,
            )
            time.sleep(delay)
            delay = min(delay * 2, 4.0)
    return 0  # no deberia alcanzarse


def delete_drive_file(drive, file_id: str) -> None:
    """Borra un fichero de Drive (best effort, no levanta si falla)."""
    try:
        drive.files().delete(fileId=file_id, supportsAllDrives=True).execute()
        logger.info("Imagen temporal borrada de Drive: %s", file_id)
    except Exception as e:
        logger.warning("No se pudo borrar %s: %s", file_id, e)
