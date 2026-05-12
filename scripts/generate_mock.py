"""
CLI: genera el informe usando datos mock locales y guarda el PDF en output/.

Uso:
    python scripts/generate_mock.py
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


def main() -> int:
    data_file = ROOT / "data" / "mock_abril_2026.json"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pdf = ROOT / "output" / f"informe_mock_{timestamp}.pdf"

    print(f"Cargando datos mock desde {data_file.name}...")
    data = json.loads(data_file.read_text(encoding="utf-8"))
    print(f"  {len(data)} campos cargados.\n")

    slides, drive = build_clients(ROOT)

    try:
        pdf_bytes = generate_report(data, slides, drive)
    except GenerationError as e:
        print(f"ERROR: {e}")
        return 1

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_bytes)
    print(f"\nListo. PDF guardado en:\n  {output_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
