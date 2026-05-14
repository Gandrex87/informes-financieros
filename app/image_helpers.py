"""
Helpers para insertar imagenes generadas dinamicamente en la presentacion.

Flujo tipico:
1. upload_temp_image: sube bytes PNG a Drive, le da permiso publico de lectura.
2. replace_shape_with_image: sustituye un shape con texto dado por la imagen.
3. delete_drive_file: borra el PNG de Drive tras exportar el PDF.

NOTA: el permiso publico es transitorio. La URL es pseudo-aleatoria y se borra
tras exportar. Para un caso con datos sensibles, evaluar Shared Drive en lugar
de cuenta personal.
"""
import io
import logging

from googleapiclient.http import MediaIoBaseUpload

logger = logging.getLogger(__name__)


def upload_temp_image(drive, image_bytes: bytes, name: str) -> str:
    """Sube PNG a Drive y lo hace publicamente legible. Devuelve fileId."""
    metadata = {"name": name, "mimeType": "image/png"}
    media = MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype="image/png")
    file = drive.files().create(
        body=metadata, media_body=media, fields="id",
    ).execute()
    file_id = file["id"]

    # Permiso publico para que la Slides API pueda descargar la imagen.
    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()
    logger.info("Imagen temporal subida: %s", file_id)
    return file_id


def replace_shape_with_image(
    slides_client, presentation_id: str, contains_text: str, image_file_id: str,
) -> int:
    """Sustituye los shapes que contienen el texto dado por la imagen.

    Usa replaceAllShapesWithImage de la Slides API. El parametro imageUrl
    apunta a un endpoint de Drive que sirve bytes de imagen directos.

    Notas tecnicas:
    - `drive.google.com/uc?id=X` ya NO es fiable: a veces devuelve HTML
      ("¿estas seguro?") o pagina de virus-scan, lo que rompe Slides API.
    - `drive.google.com/thumbnail?id=X&sz=w2000` SI funciona: sirve bytes de
      imagen directos. El parametro sz=w2000 fuerza ancho de 2000 px (calidad
      alta, evita la miniatura por defecto).

    Devuelve el numero de shapes reemplazados.
    """
    image_url = f"https://drive.google.com/thumbnail?id={image_file_id}&sz=w2000"
    request = {
        "replaceAllShapesWithImage": {
            "imageUrl": image_url,
            "imageReplaceMethod": "CENTER_INSIDE",
            "containsText": {"text": contains_text, "matchCase": True},
        }
    }
    response = slides_client.presentations().batchUpdate(
        presentationId=presentation_id,
        body={"requests": [request]},
    ).execute()
    reply = response.get("replies", [{}])[0].get("replaceAllShapesWithImage", {})
    count = reply.get("occurrencesChanged", 0)
    logger.info("replaceAllShapesWithImage('%s'): %d shape(s) sustituidos.", contains_text, count)
    return count


def delete_drive_file(drive, file_id: str) -> None:
    """Borra un fichero de Drive (best effort, no levanta si falla)."""
    try:
        drive.files().delete(fileId=file_id).execute()
        logger.info("Imagen temporal borrada de Drive: %s", file_id)
    except Exception as e:
        logger.warning("No se pudo borrar %s: %s", file_id, e)
