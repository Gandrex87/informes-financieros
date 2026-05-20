"""
CLI: genera el informe de Alicante usando datos mock locales.

Paralelo a generate_mock.py (Valencia) pero apunta a la plantilla de Alicante.
Usado para validar la tokenización de Alicante slide a slide sin tocar Postgres.

Uso:
    python scripts/generate_mock_alicante.py

El TEMPLATE_ID_ALICANTE está hardcoded aquí (provisional). Cuando integremos
multi-sede en producción, se moverá a una variable .env tipo
SLIDES_TEMPLATE_ID_ALICANTE.
"""
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.auth import build_clients
from app.generator import GenerationError, generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Plantilla de Alicante en Drive. Provisional aqui hasta multi-sede en .env.
TEMPLATE_ID_ALICANTE = "1uQ-LTgElcrY4Kx7j2yEuPDD4JWzAHs_Ju6vIgBM70e8"


def main() -> int:
    data_file = ROOT / "data" / "mock_abril_2026_alicante.json"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pdf = ROOT / "output" / f"informe_mock_alicante_{timestamp}.pdf"

    print(f"Cargando datos mock desde {data_file.name}...")
    data = json.loads(data_file.read_text(encoding="utf-8"))
    print(f"  {len(data)} campos cargados.\n")

    slides, drive = build_clients(ROOT)

    try:
        pdf_bytes = generate_report(
            data,
            slides,
            drive,
            template_id=TEMPLATE_ID_ALICANTE,
        )
    except GenerationError as e:
        print(f"ERROR: {e}")
        return 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_bytes)
    print(f"\nListo. PDF guardado en:\n  {output_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
