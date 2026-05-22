"""
CLI para probar el calculator. Lee Postgres, compone el dict del slide 2,
y lo imprime. Sin generar PDF.

Uso:
    python scripts/test_calculator.py Valencia 2026 4

Opcionalmente compara contra mock_abril_2026.json mostrando diferencias.
"""
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from app.calculator import build_payload

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main() -> int:
    if len(sys.argv) < 4:
        print("Uso: python scripts/test_calculator.py <sede> <anyo> <mes>")
        print("Ej:  python scripts/test_calculator.py Valencia 2026 4")
        return 1

    sede = sys.argv[1]
    anyo = int(sys.argv[2])
    mes = int(sys.argv[3])

    payload = build_payload(sede, anyo, mes)

    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    # Comparacion contra mock si esta disponible y los parametros coinciden.
    mock_path = ROOT / "data" / f"mock_abril_{anyo}.json"
    if mes == 4 and mock_path.exists():
        print("\n" + "=" * 60)
        print(f"Comparando contra {mock_path.name}...")
        print("=" * 60)
        mock = json.loads(mock_path.read_text(encoding="utf-8"))
        diferencias = 0
        for key, val in payload.items():
            if key == "_color_overrides":
                continue
            mock_val = mock.get(key)
            if mock_val is None:
                continue
            if str(mock_val) != str(val):
                print(f"  DIFF {key}:")
                print(f"    mock:       {mock_val!r}")
                print(f"    calculator: {val!r}")
                diferencias += 1
        if diferencias == 0:
            print("  Sin diferencias en los campos comunes.")
        else:
            print(f"\n  {diferencias} diferencias totales.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
