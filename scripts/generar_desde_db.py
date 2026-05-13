"""
CLI: genera el PDF leyendo datos reales de Postgres (calculator).

Cubre solo slides 1 y 2. El resto de slides quedaran con {{tokens}}
sin reemplazar — es esperado mientras integramos los datos del resto.

Uso:
    python scripts/generar_desde_db.py Valencia 2026 4
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
from app.calculator import build_payload_slide_2
from app.generator import GenerationError, generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    if len(sys.argv) < 4:
        print("Uso: python scripts/generar_desde_db.py <sede> <anyo> <mes>")
        print("Ej:  python scripts/generar_desde_db.py Valencia 2026 4")
        return 1

    sede = sys.argv[1]
    anyo = int(sys.argv[2])
    mes = int(sys.argv[3])

    print(f"Generando informe slides 1+2 para {sede} {anyo}-{mes:02d}...")
    print(f"Leyendo datos de Postgres via calculator...")
    payload = build_payload_slide_2(sede, anyo, mes)
    print(f"  {len(payload)} campos calculados (excluye _color_overrides).")

    slides, drive = build_clients(ROOT)
    print("Generando PDF...")
    try:
        pdf_bytes = generate_report(payload, slides, drive)
    except GenerationError as e:
        print(f"ERROR: {e}")
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pdf = ROOT / "output" / f"informe_db_{sede.lower()}_{anyo}_{mes:02d}_{timestamp}.pdf"
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_bytes)

    print(f"\nListo. PDF guardado en:\n  {output_pdf}")
    print("\nNOTA: solo slides 1 y 2 tienen datos reales.")
    print("Los slides 3-12 mostraran tokens {{xxx}} sin reemplazar — es esperado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
