"""
FastAPI app que expone la generacion del informe como servicio HTTP.

Endpoints:
    GET  /health            ping + info de la cuenta autenticada
    POST /generar-informe   recibe datos, devuelve PDF binario
"""
import logging
import os
import secrets
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import APIKeyHeader
from googleapiclient.errors import HttpError

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from app.auth import build_clients  # noqa: E402
from app.calculator import build_payload_slide_2  # noqa: E402
from app.generator import GenerationError, generate_report  # noqa: E402
from app.schemas import (  # noqa: E402
    GenerarDesdeDBRequest,
    GenerarInformeRequest,
    HealthResponse,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# --- Autenticacion por API Key ---
# Si API_KEY esta definida en .env, los endpoints de generacion la exigen
# en el header X-API-Key. Si NO esta definida, el servicio funciona SIN auth
# (modo local/desarrollo) avisando con un warning. En produccion: definir
# siempre API_KEY.
_API_KEY = os.environ.get("API_KEY", "").strip()
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    """Dependency que valida el header X-API-Key.

    - Sin API_KEY configurada: pasa siempre (modo local), warning al arrancar.
    - Con API_KEY: exige que el header coincida exactamente (comparacion
      en tiempo constante para no filtrar info por timing).
    """
    if not _API_KEY:
        return  # modo sin auth (local/desarrollo)
    if not api_key or not secrets.compare_digest(api_key, _API_KEY):
        raise HTTPException(status_code=401, detail="API Key invalida o ausente.")


def get_google_clients():
    """Crea clientes Google FRESCOS por peticion.

    NO se cachean al arranque: una conexion SSL idle (firewall/NAT del
    servidor cierra conexiones inactivas) reutilizada da
    'SSL record layer failure'. Con Service Account el coste de recrearlos
    es minimo (firmar un JWT, milisegundos — sin flujo OAuth interactivo).
    """
    return build_clients(ROOT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _API_KEY:
        logger.info("API Key ACTIVADA: los endpoints de generacion exigen X-API-Key.")
    else:
        logger.warning(
            "API Key NO configurada: el servicio acepta peticiones sin "
            "autenticacion. Define API_KEY en .env antes de produccion."
        )
    # Validacion temprana de credenciales al arrancar (falla rapido si el
    # service_account.json no esta o es invalido), pero NO se cachean los
    # clientes — cada peticion crea los suyos (conexion fresca).
    logger.info("Validando credenciales Google...")
    build_clients(ROOT)
    logger.info("Credenciales OK. Los clientes se crean por peticion.")
    yield


app = FastAPI(
    title="Informes Financieros API",
    description="Genera el Informe Directores Comerciales en PDF.",
    version="0.1.0",
    lifespan=lifespan,
)


def _safe_filename(sede: str, mes_año: str) -> str:
    """Normaliza sede + mes para usar como filename. Sin acentos, sin espacios."""
    raw = f"informe_{sede}_{mes_año}".lower()
    nfkd = unicodedata.normalize("NFKD", raw)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return "".join(c if c.isalnum() else "_" for c in ascii_only) + ".pdf"


@app.get("/health", response_model=HealthResponse)
def health():
    template_id = os.environ.get("SLIDES_TEMPLATE_ID", "")
    user_email = None
    try:
        _slides, drive = get_google_clients()
        about = drive.about().get(fields="user(emailAddress)").execute()
        user_email = about.get("user", {}).get("emailAddress")
    except HttpError as e:
        logger.warning("No se pudo leer about: %s", e)
    return HealthResponse(status="ok", template_id=template_id, user_email=user_email)


@app.post("/generar-informe", dependencies=[Depends(require_api_key)])
def generar_informe(req: GenerarInformeRequest):
    """Genera el informe y devuelve el PDF binario.

    Recibe el payload completo de tokens (mock / cliente externo lo compone).
    """
    try:
        slides_client, drive_client = get_google_clients()
        pdf_bytes = generate_report(
            data=req.to_data_dict(),
            slides_client=slides_client,
            drive_client=drive_client,
        )
    except GenerationError as e:
        logger.exception("Error generando informe")
        raise HTTPException(status_code=502, detail=str(e))

    filename = _safe_filename(req.sede, req.mes_año)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/generar-desde-db", dependencies=[Depends(require_api_key)])
def generar_desde_db(req: GenerarDesdeDBRequest):
    """Genera el informe leyendo los datos directamente de Postgres.

    Cobertura actual: slides 1 y 2. Resto de slides quedaran con
    tokens {{xxx}} sin reemplazar hasta que se amplie el calculator.
    """
    try:
        payload = build_payload_slide_2(
            sede=req.sede,
            anyo=req.anyo,
            mes=req.mes,
            escenario=req.escenario,
        )
    except ValueError as e:
        # Datos faltantes en Postgres (ej. no hay contabilidad cargada).
        logger.warning("Datos insuficientes: %s", e)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error leyendo datos de Postgres")
        raise HTTPException(status_code=500, detail=f"Error de DB: {e}")

    try:
        slides_client, drive_client = get_google_clients()
        pdf_bytes = generate_report(
            data=payload,
            slides_client=slides_client,
            drive_client=drive_client,
        )
    except GenerationError as e:
        logger.exception("Error generando informe")
        raise HTTPException(status_code=502, detail=str(e))

    filename = _safe_filename(req.sede, f"{req.anyo}_{req.mes:02d}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
