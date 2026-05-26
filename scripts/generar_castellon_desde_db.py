"""
CLI: genera el PDF de Castellón leyendo datos reales de Postgres.

Paralelo a generar_alicante_desde_db.py / generar_desde_db.py. Usa
calculator_castellon.build_payload y apunta al template de Slides de Castellón.

Cobertura actual: BLOQUE 1 (andamiaje) — solo tokens de identidad (sede,
mes, tramo) tienen valor real. El resto se emite como string vacío para que
el PDF salga sin {{xxx}} literales pero también sin datos.

Bloques 2-4 (ver docs/superpowers/specs/2026-05-26-castellon-design.md) irán
rellenando KPIs, pipeline, cobros, BE, comisiones y semáforo.

Uso:
    python scripts/generar_castellon_desde_db.py 2026 5
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
from app.calculator_castellon import build_payload
from app.generator import GenerationError, generate_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    if len(sys.argv) < 3:
        print("Uso: python scripts/generar_castellon_desde_db.py <anyo> <mes>")
        print("Ej:  python scripts/generar_castellon_desde_db.py 2026 5")
        return 1

    anyo = int(sys.argv[1])
    mes = int(sys.argv[2])

    print(f"Generando informe Castellón {anyo}-{mes:02d}...")
    print(f"Leyendo datos de Postgres via calculator_castellon...")
    payload = build_payload(anyo, mes)
    print(f"  {len(payload)} campos calculados.")

    template_id = template_id_for("Castellon")
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
    output_pdf = ROOT / "output" / f"informe_db_castellon_{anyo}_{mes:02d}_{timestamp}.pdf"
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    output_pdf.write_bytes(pdf_bytes)

    print(f"\nListo. PDF guardado en:\n  {output_pdf}")
    print("\nInforme completo: slides 1-10 con datos reales.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
