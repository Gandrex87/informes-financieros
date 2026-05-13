"""
FastAPI app que expone la generacion del informe como servicio HTTP.

Endpoints:
    GET  /health            ping + info de la cuenta autenticada
    POST /generar-informe   recibe datos, devuelve PDF binario
"""
import logging
import os
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
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


# Clientes Google reusados entre requests (auth una sola vez al arrancar).
_clients: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando clientes Google...")
    slides, drive = build_clients(ROOT)
    _clients["slides"] = slides
    _clients["drive"] = drive
    logger.info("Clientes listos.")
    yield
    _clients.clear()


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
        drive = _clients.get("drive")
        if drive:
            about = drive.about().get(fields="user(emailAddress)").execute()
            user_email = about.get("user", {}).get("emailAddress")
    except HttpError as e:
        logger.warning("No se pudo leer about: %s", e)
    return HealthResponse(status="ok", template_id=template_id, user_email=user_email)


@app.post("/generar-informe")
def generar_informe(req: GenerarInformeRequest):
    """Genera el informe y devuelve el PDF binario.

    Recibe el payload completo de tokens (mock / cliente externo lo compone).
    """
    try:
        pdf_bytes = generate_report(
            data=req.to_data_dict(),
            slides_client=_clients["slides"],
            drive_client=_clients["drive"],
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


@app.post("/generar-desde-db")
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
        pdf_bytes = generate_report(
            data=payload,
            slides_client=_clients["slides"],
            drive_client=_clients["drive"],
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
