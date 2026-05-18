"""
Prueba de autenticacion OAuth con Google Slides y Drive.

Solo lectura. Util para validar credenciales y acceso a la plantilla.
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.auth import build_clients

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    template_id = os.environ["SLIDES_TEMPLATE_ID"]

    print("[1/3] Autenticando (puede abrirse el navegador la primera vez)...")
    slides, drive = build_clients(ROOT)
    print("  OK.")

    print(f"[2/3] Leyendo metadata de la plantilla {template_id}...")
    try:
        meta = drive.files().get(
            fileId=template_id,
            fields="id,name,mimeType,owners(emailAddress),modifiedTime",
            supportsAllDrives=True,
        ).execute()
    except HttpError as e:
        print(f"  ERROR de Drive API: {e}")
        return 1

    print(f"  Nombre: {meta['name']}")
    print(f"  Tipo:   {meta['mimeType']}")
    print(f"  Dueno:  {meta.get('owners', [{}])[0].get('emailAddress', '?')}")
    print(f"  Modif.: {meta['modifiedTime']}")

    print("[3/3] Leyendo estructura de slides...")
    try:
        deck = slides.presentations().get(presentationId=template_id).execute()
    except HttpError as e:
        print(f"  ERROR de Slides API: {e}")
        return 1

    n_slides = len(deck.get("slides", []))
    print(f"  OK. La plantilla tiene {n_slides} slides.")

    print("\nTodo correcto. Tu usuario puede leer la plantilla.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
