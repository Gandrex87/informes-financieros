"""
Modulo compartido de autenticacion OAuth.

Primera ejecucion: abre el navegador, pide autorizar la app, guarda token.json.
Ejecuciones siguientes: usa token.json. Si expiro, lo refresca automaticamente.
"""
import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]


def get_credentials(root: Path) -> Credentials:
    client_file = root / os.environ["OAUTH_CLIENT_FILE"]
    token_file = root / os.environ["OAUTH_TOKEN_FILE"]

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Token refrescado.")
        else:
            if not client_file.exists():
                raise FileNotFoundError(
                    f"No se encuentra el OAuth client en {client_file}. "
                    "Descarga el JSON desde GCP y guardalo ahi."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Token nuevo creado via flow OAuth.")
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def build_clients(root: Path):
    creds = get_credentials(root)
    slides = build("slides", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return slides, drive
