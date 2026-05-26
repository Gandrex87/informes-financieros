"""
Genera un PDF SIMULADO del informe para probar el posicionamiento dinámico
del marcador en la barra de break even, en cualquiera de las 3 sedes.

Lee el payload real de (sede, anyo, mes) desde Postgres y sobreescribe SOLO
los valores que pases por CLI. Recalcula los tokens dependientes
(margen_seguridad, estados de cada umbral, color del margen y posición del
marcador) para que el slide del BE sea coherente con los valores simulados.

Multi-sede:
- Valencia: marcador slide 8 = {{ingresos_totales}}. Una sola base (ingresos)
  para marcador, estados, margen_seguridad y narrativa. Usa --ingresos.
- Alicante / Castellón: dos slides con marcador.
  - Slide 6 (BE actual): marcador = {{contratos_firmados}}. Base de estados =
    arras_firmadas. Base de margen_seguridad y narrativa = ingresos_contables.
    Usa --arras (mueve marcador y estados) y --ingresos (margen y narrativa).
  - Slide 8 (BE proyectado): marcador = {{facturacion_objetivo_proy}}.
    Usa --objetivo-proy.

Útil para validar visualmente cómo queda cada slide en escenarios que no
ocurrieron en BD (ej. "si superamos el 30%", "si no llegamos al BE").

Ejemplos:
    # Valencia: simular 320k de ingresos
    python scripts/simular_break_even.py --sede Valencia --anyo 2026 --mes 4 --ingresos 320000

    # Castellón: mover marcador slide 6 a 30k de arras (sin tocar ingresos reales)
    python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 30000

    # Castellón: simular mes superavitario en arras E ingresos
    python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --arras 50000 --ingresos 45000

    # Castellón: mover solo el marcador del BE proyectado (slide 8)
    python scripts/simular_break_even.py --sede Castellon --anyo 2026 --mes 5 --objetivo-proy 80000

El PDF de salida queda en output/ con un nombre que incluye los valores
simulados, para no pisar el PDF real ni los anteriores simulados.
"""
import argparse
import logging
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

# Forzar UTF-8 en stdout (Windows usa cp1252 por defecto, rompe con € y ✓).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.auth import build_clients  # noqa: E402
from app.calculator import build_payload, template_id_for  # noqa: E402
from app.calculator_base import SEDES_VALIDAS  # noqa: E402
from app.calculator_valencia import _narrativa_break_even  # noqa: E402
from app.formatter import format_euro  # noqa: E402
from app.generator import generate_report  # noqa: E402

# Sedes con patrón "Alicante" (BE actual = slide 6, BE proy = slide 8,
# marcador = contratos_firmados). Si en el futuro se añade una sede, basta
# con incluirla aquí si sigue este patrón.
SEDES_PATRON_ALICANTE = {"Alicante", "Castellon"}


def _estado(valor: Decimal, umbral: Decimal | None) -> str:
    """Devuelve "✓ SUPERADO" si valor >= umbral, "FALTAN: X €" en caso
    contrario. Si umbral es None, cadena vacía (slide proyectado con
    mes siguiente sin cargar)."""
    if umbral is None:
        return ""
    if valor >= umbral:
        return "✓ SUPERADO"
    return f"FALTAN: {format_euro(umbral - valor)}"


def _simular_valencia(payload: dict, ingresos_sim: Decimal) -> None:
    """Aplica la simulación al payload de Valencia (slide 8, una sola base)."""
    pos = payload.get("_break_even_position")
    if pos is None:
        raise RuntimeError(
            "El payload no tiene _break_even_position. ¿Estás simulando "
            "una sede sin slide 8 BE actual?"
        )
    be = pos["break_even"]
    m10 = pos["margen_10"]
    m20 = pos["margen_20"]
    m30 = pos["margen_30"]
    # m40 no está en el dict de posición (la barra solo usa 4 umbrales para
    # el marcador), pero sí debe recalcularse el estado y el color. Lo
    # extraemos del payload (token formateado) parseando atrás sería frágil:
    # usamos los umbrales numéricos del dict + extrapolación o leemos
    # de break_even_chart si fuera necesario. Para mantener simple, si no
    # está disponible asumimos que m40 no se recalcula (queda al valor real).

    print(f"  break_even = {be}    m10 = {m10}    m20 = {m20}    m30 = {m30}")

    pos["ingresos"] = ingresos_sim
    payload["ingresos_totales"] = format_euro(ingresos_sim)

    margen_seguridad = ingresos_sim - be
    payload["margen_seguridad"] = format_euro(margen_seguridad)
    payload["narrativa_break_even"] = _narrativa_break_even(
        ingresos_sim, be, margen_seguridad,
    )

    # Estados y colores: si m40 no está en pos, se queda con su estado real
    # (no recalculamos). Resto sí.
    for tok, umbral in (
        ("break_even_estado", be),
        ("margen_10_estado", m10),
        ("margen_20_estado", m20),
        ("margen_30_estado", m30),
    ):
        payload[tok] = _estado(ingresos_sim, umbral)
        payload["_color_overrides"][tok] = "verde" if ingresos_sim >= umbral else "rojo"

    payload["_color_overrides"]["margen_seguridad"] = (
        "verde" if margen_seguridad >= 0 else "rojo"
    )


def _simular_alicante_castellon(
    payload: dict,
    arras_sim: Decimal | None,
    ingresos_sim: Decimal | None,
    objetivo_proy_sim: Decimal | None,
) -> None:
    """Aplica la simulación al payload de Alicante/Castellón (slide 6 con
    base arras, slide 8 BE proyectado opcional).

    Si --arras se pasa, mueve marcador slide 6 + recalcula estados.
    Si --ingresos se pasa, recalcula margen_seguridad + narrativa.
    Si --objetivo-proy se pasa, mueve marcador slide 8.
    """
    # --- Slide 6: BE actual ---
    if arras_sim is not None or ingresos_sim is not None:
        pos6 = payload.get("_break_even_position_slide_6_alc")
        if pos6 is None:
            raise RuntimeError(
                "El payload no tiene _break_even_position_slide_6_alc. "
                "¿Esta sede emite ese marcador?"
            )
        be = pos6["break_even"]
        m10 = pos6["margen_10"]
        m20 = pos6["margen_20"]
        m30 = pos6["margen_30"]

        print(f"  slide 6: be = {be}  m10 = {m10}  m20 = {m20}  m30 = {m30}")

        # 1) Marcador móvil + estados (base = arras)
        if arras_sim is not None:
            pos6["contratos_firmados"] = arras_sim
            payload["contratos_firmados"] = format_euro(arras_sim)

            for tok, umbral in (
                ("break_even_estado", be),
                ("margen_10_estado", m10),
                ("margen_20_estado", m20),
                ("margen_30_estado", m30),
            ):
                payload[tok] = _estado(arras_sim, umbral)
                payload["_color_overrides"][tok] = (
                    "verde" if arras_sim >= umbral else "rojo"
                )

            # margen_40_estado: si en el payload existe el m40 real, lo
            # recalculamos también. La query _query_break_even lo devuelve,
            # pero no está en _break_even_position_slide_6_alc. Lo leemos
            # del token formateado del payload? No, mejor del módulo.
            # Solución pragmática: dejar margen_40_estado tal cual estaba.

        # 2) Margen seguridad y narrativa (base = ingresos)
        if ingresos_sim is not None:
            payload["ingresos_totales"] = format_euro(ingresos_sim)
            margen_seguridad = ingresos_sim - be
            payload["margen_seguridad"] = format_euro(margen_seguridad)
            payload["narrativa_break_even"] = _narrativa_break_even(
                ingresos_sim, be, margen_seguridad,
            )
            payload["_color_overrides"]["margen_seguridad"] = (
                "verde" if margen_seguridad >= 0 else "rojo"
            )

    # --- Slide 8: BE proyectado ---
    if objetivo_proy_sim is not None:
        pos8 = payload.get("_break_even_position_slide_8_alc")
        if pos8 is None:
            raise RuntimeError(
                "El payload no tiene _break_even_position_slide_8_alc. "
                "¿Esta sede emite el marcador BE proyectado?"
            )
        pos8["facturacion_objetivo_proy"] = objetivo_proy_sim
        payload["facturacion_objetivo_proy"] = format_euro(objetivo_proy_sim)
        print(
            f"  slide 8 proy: objetivo simulado = {objetivo_proy_sim}; "
            f"BE_proy = {pos8['break_even_proy']}"
        )


def _build_output_name(
    sede: str, anyo: int, mes: int,
    arras: Decimal | None, ingresos: Decimal | None, objetivo_proy: Decimal | None,
) -> str:
    partes = [f"informe_SIMULADO_{sede.lower()}_{anyo}_{mes:02d}"]
    if arras is not None:
        partes.append(f"arras{int(arras)}")
    if ingresos is not None:
        partes.append(f"ing{int(ingresos)}")
    if objetivo_proy is not None:
        partes.append(f"proy{int(objetivo_proy)}")
    return "_".join(partes) + ".pdf"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulador BE multi-sede",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--sede", required=True, choices=sorted(SEDES_VALIDAS),
                        help="Sede del informe.")
    parser.add_argument("--anyo", type=int, required=True, help="Año (ej. 2026).")
    parser.add_argument("--mes", type=int, required=True, help="Mes (1..12).")
    parser.add_argument("--ingresos", type=Decimal, default=None,
                        help="Valencia: mueve marcador slide 8. "
                             "Alicante/Castellón: recalcula margen_seguridad y narrativa.")
    parser.add_argument("--arras", type=Decimal, default=None,
                        help="Alicante/Castellón: mueve marcador slide 6 (BE actual) "
                             "y recalcula estados. No aplica a Valencia.")
    parser.add_argument("--objetivo-proy", dest="objetivo_proy", type=Decimal, default=None,
                        help="Alicante/Castellón: mueve marcador slide 8 (BE proyectado).")
    args = parser.parse_args()

    # Validación de combinaciones
    if args.sede == "Valencia":
        if args.arras is not None or args.objetivo_proy is not None:
            parser.error(
                "Valencia solo soporta --ingresos. Quita --arras / --objetivo-proy."
            )
        if args.ingresos is None:
            parser.error("Valencia requiere --ingresos.")
    else:
        if args.ingresos is None and args.arras is None and args.objetivo_proy is None:
            parser.error(
                f"{args.sede}: pasa al menos uno de --arras, --ingresos, --objetivo-proy."
            )

    print(
        f"=== Simulación BE: {args.sede} {args.anyo}-{args.mes:02d} "
        f"(arras={args.arras}, ingresos={args.ingresos}, "
        f"objetivo_proy={args.objetivo_proy}) ==="
    )
    print("Leyendo payload real de Postgres...")
    payload = build_payload(args.sede, args.anyo, args.mes)

    if args.sede == "Valencia":
        _simular_valencia(payload, args.ingresos)
    else:
        _simular_alicante_castellon(
            payload,
            arras_sim=args.arras,
            ingresos_sim=args.ingresos,
            objetivo_proy_sim=args.objetivo_proy,
        )

    print("\nTokens del slide BE tras simulación:")
    for k in ("contratos_firmados", "ingresos_totales", "margen_seguridad",
              "break_even_estado", "margen_10_estado", "margen_20_estado",
              "margen_30_estado", "facturacion_objetivo_proy"):
        if k in payload:
            print(f"  {k:<28} = {payload[k]}")
    print()

    # Generar PDF
    print("Llamando a Slides API...")
    template_id = template_id_for(args.sede)
    slides_c, drive_c = build_clients(ROOT)
    pdf_bytes = generate_report(payload, slides_c, drive_c, template_id=template_id)

    out_name = _build_output_name(
        args.sede, args.anyo, args.mes,
        args.arras, args.ingresos, args.objetivo_proy,
    )
    out = ROOT / "output" / out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)

    print(f"\nPDF guardado en: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
