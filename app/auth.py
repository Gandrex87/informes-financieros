"""
Autenticacion con Google. Soporta dos metodos, elegidos por AUTH_METHOD:

- "service_account" (PRODUCCION): credenciales de maquina, NO caducan.
  Requiere SERVICE_ACCOUNT_FILE. La cuenta de servicio debe tener acceso a
  la plantilla via una Shared Drive donde sea miembro.

- "oauth" (rollback / desarrollo local con Gmail personal): flujo OAuth de
  usuario. El token.json caduca cada ~7 dias si la app esta en modo testing.

El metodo se elige con la variable de entorno AUTH_METHOD. Si no esta
definida, por defecto "oauth" (comportamiento historico, no rompe nada).
"""
import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive",
]


def _service_account_credentials(root: Path):
    """Credenciales de Service Account. No caducan, ideal para produccion."""
    sa_file = root / os.environ["SERVICE_ACCOUNT_FILE"]
    if not sa_file.exists():
        raise FileNotFoundError(
            f"No se encuentra el JSON de la Service Account en {sa_file}. "
            "Descargalo desde GCP (IAM > Cuentas de servicio > Claves)."
        )
    return service_account.Credentials.from_service_account_file(
        str(sa_file), scopes=SCOPES
    )


def _oauth_credentials(root: Path) -> Credentials:
    """Credenciales OAuth de usuario. El token caduca; solo desarrollo/rollback."""
    client_file = root / os.environ["OAUTH_CLIENT_FILE"]
    token_file = root / os.environ["OAUTH_TOKEN_FILE"]

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Token OAuth refrescado.")
        else:
            if not client_file.exists():
                raise FileNotFoundError(
                    f"No se encuentra el OAuth client en {client_file}."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("Token OAuth nuevo creado via flow.")
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def get_credentials(root: Path):
    metodo = os.environ.get("AUTH_METHOD", "oauth").strip().lower()
    if metodo == "service_account":
        logger.info("Auth: Service Account (produccion).")
        return _service_account_credentials(root)
    if metodo == "oauth":
        logger.info("Auth: OAuth de usuario (desarrollo/rollback).")
        return _oauth_credentials(root)
    raise ValueError(
        f"AUTH_METHOD desconocido: '{metodo}'. Usa 'service_account' u 'oauth'."
    )


def build_clients(root: Path):
    creds = get_credentials(root)
    slides = build("slides", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return slides, drive
