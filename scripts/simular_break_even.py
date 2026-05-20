"""
Genera un PDF SIMULADO del informe para probar el posicionamiento dinamico
del marcador {{ingresos_totales}} en la barra de break even del slide 8.

Lee el payload real de (sede, anyo, mes) desde Postgres y sobrescribe
SOLO el valor de ingresos_totales con el valor que pases por CLI. Recalcula
los tokens dependientes (margen_seguridad, estados de cada margen, color del
margen de seguridad y posicion del marcador) para que el slide 8 sea
coherente con el ingreso simulado.

Util para validar visualmente como queda el slide 8 en escenarios que no
ocurrieron en la BD real (ej. "no llega al 20%", "supera el 30%", "no
cubre el break even").

Uso:
    python scripts/simular_break_even.py <ingresos>
    python scripts/simular_break_even.py <ingresos> <sede> <anyo> <mes>

Ejemplos:
    python scripts/simular_break_even.py 320000
    python scripts/simular_break_even.py 200000 Valencia 2026 4
    python scripts/simular_break_even.py 650000 Valencia 2026 4

Defaults: sede=Valencia, anyo=2026, mes=4.

El PDF queda en output/ con un nombre que incluye el ingreso simulado,
para no pisar el PDF "real" ni los anteriores simulados.
"""
import logging
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Forzar UTF-8 en stdout (Windows usa cp1252 por defecto, rompe con € y ✓).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Logging a nivel INFO para ver el posicionamiento del marcador y otras
# trazas del generator (mismo formato que generar_desde_db.py).
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.auth import build_clients  # noqa: E402
from app.calculator import build_payload_slide_2  # noqa: E402
from app.formatter import format_euro  # noqa: E402
from app.generator import generate_report  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    try:
        ingresos_sim = Decimal(sys.argv[1])
    except Exception:
        print(f"Error: '{sys.argv[1]}' no es un numero valido para ingresos.")
        return 2

    sede = sys.argv[2] if len(sys.argv) > 2 else "Valencia"
    anyo = int(sys.argv[3]) if len(sys.argv) > 3 else 2026
    mes = int(sys.argv[4]) if len(sys.argv) > 4 else 4

    print(f"=== Simulacion break even: {sede} {anyo}-{mes:02d} con ingresos = {ingresos_sim} EUR ===")
    print(f"Leyendo payload real de Postgres...")

    payload = build_payload_slide_2(sede, anyo, mes)

    # Anclas de valor (vienen del calculator como Decimal) para recalculo
    be = payload["_break_even_position"]["break_even"]
    m10 = payload["_break_even_position"]["margen_10"]
    m20 = payload["_break_even_position"]["margen_20"]
    m30 = payload["_break_even_position"]["margen_30"]

    print(f"  break_even = {be}    m10 = {m10}    m20 = {m20}    m30 = {m30}")

    # 1) Valor numerico para el posicionamiento dinamico del marcador
    payload["_break_even_position"]["ingresos"] = ingresos_sim

    # 2) Token visible (afecta slide 1 portada, slide 2 card, slide 8 marcador, slide 9 banner)
    payload["ingresos_totales"] = format_euro(ingresos_sim)

    # 3) Recalcular margen de seguridad (positivo o negativo segun cubra el BE)
    ms = ingresos_sim - be
    payload["margen_seguridad"] = format_euro(ms)

    # 4) Recalcular estados de cada umbral
    def estado(umbral: Decimal) -> str:
        if ingresos_sim >= umbral:
            return "✓ SUPERADO"
        return f"FALTAN: {format_euro(umbral - ingresos_sim)}"

    payload["break_even_estado"] = estado(be)
    payload["margen_10_estado"] = estado(m10)
    payload["margen_20_estado"] = estado(m20)
    payload["margen_30_estado"] = estado(m30)
    payload["margen_40_estado"] = estado(
        payload["_break_even_position"].get("margen_40", m30)
        if payload["_break_even_position"].get("margen_40") is not None
        else m30
    )

    # 5) Color del margen_seguridad coherente con el signo
    payload["_color_overrides"]["margen_seguridad"] = "verde" if ms >= 0 else "rojo"

    print()
    print("Tokens del slide 8 tras simulacion:")
    for k in ("ingresos_totales", "margen_seguridad",
              "break_even_estado", "margen_10_estado",
              "margen_20_estado", "margen_30_estado"):
        print(f"  {k:<24} = {payload[k]}")
    print()

    # 6) Generar PDF
    print("Llamando a Slides API...")
    slides_c, drive_c = build_clients(ROOT)
    pdf_bytes = generate_report(payload, slides_c, drive_c)

    # Nombre con el ingreso simulado, no pisa nada
    importe_str = str(int(ingresos_sim)).replace(".", "")
    out = ROOT / "output" / f"informe_SIMULADO_{sede.lower()}_{anyo}_{mes:02d}_ing{importe_str}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)

    print()
    print(f"PDF guardado en: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
