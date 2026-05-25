"""
CLI: genera el PDF de Alicante leyendo datos reales de Postgres.

Paralelo a generar_desde_db.py (que es para Valencia). Usa
calculator_alicante.build_payload y apunta al template de Slides de Alicante.

Cobertura actual: SOLO slide 1 (portada). El resto de slides quedaran con
{{tokens}} sin reemplazar mientras se va integrando slide por slide.

Uso:
    python scripts/generar_alicante_desde_db.py 2026 4
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.auth import build_clients
from app.calculator import template_id_for
from app.calculator_alicante import build_payload
from app.generator import GenerationError, generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: python scripts/generar_alicante_desde_db.py <anyo> <mes>")
        print("Ej:  python scripts/generar_alicante_desde_db.py 2026 4")
        return 1

    anyo = int(sys.argv[1])
    mes = int(sys.argv[2])

    print(f"Generando informe Alicante {anyo}-{mes:02d}...")
    print(f"Leyendo datos de Postgres via calculator_alicante...")
    payload = build_payload(anyo, mes)
    print(f"  {len(payload)} campos calculados.")

    template_id = template_id_for("Alicante")
    slides, drive = build_clients(ROOT)
    print(f"Generando PDF (template {template_id})...")
    try:
        pdf_bytes = generate_report(
            payload, slides, drive,
            template_id=template_id,
        )
    except GenerationError as e:
        print(f"ERROR: {e}")
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pdf = ROOT / "output" / f"informe_db_alicante_{anyo}_{mes:02d}_{timestamp}.pdf"
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_bytes)

    print(f"\nListo. PDF guardado en:\n  {output_pdf}")
    print("\nNOTA: solo el slide 1 tiene datos reales.")
    print("Los slides 2-10 mostraran tokens {{xxx}} sin reemplazar — es esperado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
