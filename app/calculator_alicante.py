"""
Calculator de Alicante — compone el payload del informe Directores Comerciales.

Módulo INDEPENDIENTE de calculator.py (Valencia) por decisión de arquitectura
(ver memory/project_arquitectura_multisede.md y docs/MIGRACION_MULTISEDE.md):
no se combinan ramas if sede==... — Valencia y Alicante son módulos paralelos
que comparten helpers/queries via calculator_base.

DIFERENCIAS estructurales respecto a Valencia (Alicante NUNCA las lleva):
- Sin alquileres (no hay slide 4 Gestión alquileres ni columna alquileres
  poblada en pipeline).
- Sin operaciones condicionadas (no hay slide 6).
- Sin obra nueva en el pipeline (slide 5 Alicante = slide 5 Valencia sin obra
  nueva).
- Sin comparativa interanual / YoY en slide 3 (no había datos de Alicante
  antes de 2026).
- 1 director (Valencia tiene 2): la comisión variable NO se divide.
- Tramo comisión 4 % (Valencia 3 %).
- Sueldo fijo bruto director 1.933,73 € (Valencia 2.666,67 €).

Implementación incremental: este archivo se va ampliando slide por slide al
ritmo que el usuario valide el resultado en el PDF. Hoy cubre solo slide 1.
"""
import logging
from decimal import Decimal
from typing import Any

from app.calculator_base import (
    _mes_anterior,
    _query_comercial,
    _query_contable,
    _query_tramo_comision,
    _variacion,
    _variacion_tasa,
)
from app.formatter import (
    format_euro,
    format_int,
    format_int_signed,
    format_mes_anyo,
    format_mes_anyo_upper,
    format_mes_capitalizado,
    format_mes_short_anyo,
    format_pct,
    format_pct_signed,
)

logger = logging.getLogger(__name__)

# La sede es fija en este modulo (a diferencia de calculator.py que la recibe
# como parametro). Si en el futuro hay que duplicar el calculator para una
# tercera sede, este modulo sirve de plantilla.
SEDE = "Alicante"

# --- Constantes especificas de Alicante ---
# El tramo de comision YA NO es constante: se lee dinamicamente de
# informes_financieros.pagos_directores filtrando por sede='Alicante'
# (ver _query_tramo_comision). Abril 2026: PELAYO 0.0400 -> "4 %".

# Numero de directores. En Alicante es 1 (a diferencia de Valencia con 2):
# la comision variable NO se divide. Afecta al calculo final del slide 7
# (comision_variable_por_director = total_a_repartir / N_DIRECTORES).
N_DIRECTORES = 1

# Sueldo fijo bruto mensual por director.
SUELDO_FIJO_DIRECTOR = Decimal("1933.73")


def build_payload(anyo: int, mes: int, escenario: str = "con_crm") -> dict[str, Any]:
    """Compone el dict de tokens para el informe de Alicante.

    Cobertura actual: SOLO slide 1 (portada). Los siguientes slides se
    iran añadiendo al ritmo que el usuario valide el resultado.

    Args:
        anyo: año del informe (ej. 2026).
        mes: mes del informe (1..12).
        escenario: escenario contable, default "con_crm".

    Returns:
        dict con los tokens listos para mandar al servicio /generar-informe.

    Raises:
        ValueError: si no hay datos contables para esa sede/anyo/mes.
    """
    # --- Calculo de fechas relativas ---
    anyo_prev, mes_prev = _mes_anterior(anyo, mes)
    anyo_yoy, mes_yoy = anyo - 1, mes  # mismo mes del año anterior

    # --- Lecturas Postgres ---
    com_actual = _query_comercial(SEDE, anyo, mes)
    com_prev = _query_comercial(SEDE, anyo_prev, mes_prev)
    cont_actual = _query_contable(SEDE, escenario, anyo, mes)
    cont_prev = _query_contable(SEDE, escenario, anyo_prev, mes_prev)
    cont_yoy = _query_contable(SEDE, escenario, anyo_yoy, mes_yoy)
    tramo_comision_pct = _query_tramo_comision(SEDE, anyo, mes)

    if cont_actual is None:
        raise ValueError(
            f"No hay datos contables para sede={SEDE} escenario={escenario} "
            f"{anyo}-{mes:02d}. Carga primero contabilidad_mensual."
        )
    if tramo_comision_pct is None:
        raise ValueError(
            f"No hay tramo de comision en pagos_directores para "
            f"sede={SEDE} {anyo}-{mes:02d}. Carga primero pagos_directores."
        )

    # --- Variaciones MoM (slide 2) ---
    # Slide 2 tarjeta 1: reservas (señales)
    var_reservas_mom = _variacion(com_actual.señales_total, com_prev.señales_total)
    delta_ops_reservas = com_actual.señales_n_ops - com_prev.señales_n_ops

    # Slide 2 tarjeta 2: contratos firmados (arras)
    var_contratos_mom = _variacion(com_actual.arras_total, com_prev.arras_total)
    delta_ops_contratos = com_actual.arras_n_ops - com_prev.arras_n_ops

    # Slide 2 tarjeta 3: ingresos
    var_ingresos_mom = _variacion(
        cont_actual.ingresos_contables,
        cont_prev.ingresos_contables if cont_prev else None,
    )

    # Slide 2 tarjeta 4: rentabilidad REAL (no operativa, diferencia con
    # Valencia). Usa _variacion_tasa, no _variacion clasica: cuando el mes
    # anterior fue negativo (marzo Alicante: -27,62 %), el ratio clasico
    # invierte el signo y comunica una mejora como -216 %. _variacion_tasa
    # aplica heuristica sobre el denominador negativo para que el signo
    # refleje la direccion real del cambio (decision usuario 2026-05-21).
    var_rentab_mom = _variacion_tasa(
        cont_actual.rentabilidad_real_pct,
        cont_prev.rentabilidad_real_pct if cont_prev else None,
    )

    # --- Datos comparativos para tarjetas ---
    señales_mes_anterior = com_prev.señales_total
    arras_mes_anterior = com_prev.arras_total
    # YoY se calcula aunque la plantilla actual de Alicante no use los
    # tokens; se emiten para no perderlos si la plantilla los recupera.
    señales_anyo_anterior = cont_yoy.pagas_señales if cont_yoy else None
    arras_anyo_anterior = cont_yoy.arras_firmadas if cont_yoy else None

    # --- Color overrides ---
    color_overrides: dict[str, str] = {}
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom"] = "verde" if var_reservas_mom >= 0 else "rojo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom"] = "verde" if var_contratos_mom >= 0 else "rojo"
    if var_ingresos_mom is not None:
        color_overrides["var_ingresos_mom"] = "verde" if var_ingresos_mom >= 0 else "rojo"
    if var_rentab_mom is not None:
        color_overrides["var_rentab_mom"] = "verde" if var_rentab_mom >= 0 else "rojo"

    return {
        "_color_overrides": color_overrides,

        # --- Identificacion ---
        "sede": SEDE,
        "sede_upper": SEDE.upper(),
        "mes_año": format_mes_anyo(anyo, mes),
        "mes_año_upper": format_mes_anyo_upper(anyo, mes),
        "mes_anterior_short": format_mes_short_anyo(anyo_prev, mes_prev),
        "mes_anterior_capitalizado": format_mes_capitalizado(mes_prev),

        # --- Slide 1: Portada ---
        "reservas_totales": format_euro(com_actual.señales_total),
        "contratos_firmados": format_euro(com_actual.arras_total),
        "ingresos_totales": format_euro(cont_actual.ingresos_contables),
        "tramo_comision": format_pct(tramo_comision_pct, decimales=0),

        # --- Slide 2: tarjeta Reservas ---
        "var_reservas_mom": format_pct_signed(var_reservas_mom, decimales=1),
        "n_ops_reservas": format_int(com_actual.señales_n_ops),
        "delta_ops_reservas": format_int_signed(delta_ops_reservas, suffix="ops"),
        "reservas_mes_anterior": format_euro(señales_mes_anterior),
        # YoY: emitido aunque la plantilla actual de Alicante no lo muestre.
        "reservas_año_anterior": format_euro(señales_anyo_anterior),

        # --- Slide 2: tarjeta Contratos firmados ---
        "var_contratos_mom": format_pct_signed(var_contratos_mom, decimales=2),
        "n_ops_contratos": format_int(com_actual.arras_n_ops),
        "delta_ops_contratos": format_int_signed(delta_ops_contratos, suffix="ops"),
        "contratos_mes_anterior": format_euro(arras_mes_anterior),
        "contratos_año_anterior": format_euro(arras_anyo_anterior),

        # --- Slide 2: tarjeta Ingresos ---
        "var_ingresos_mom": format_pct_signed(var_ingresos_mom, decimales=2),
        "ingresos_mes_anterior": format_euro(cont_prev.ingresos_contables if cont_prev else None),
        # Alicante NO muestra desglose ventas/alquiler (no tiene alquileres).
        # margen_bruto: usamos rentabilidad_bruta_pct igual que Valencia.
        # Alicante PDF muestra "60,00%" (2 decimales), Valencia "60%".
        "margen_bruto": format_pct(cont_actual.rentabilidad_bruta_pct, decimales=2),

        # --- Slide 2: tarjeta Rentabilidad REAL ---
        # OJO: diferencia con Valencia. Alicante usa _real_pct y ebitda_real
        # (incluye gastos_extra). Valencia usa _operativa_pct y ebitda_no_extras.
        "rentabilidad_op": format_pct(cont_actual.rentabilidad_real_pct, decimales=2),
        "var_rentab_mom": format_pct_signed(var_rentab_mom, decimales=2),
        "resultado_op": format_euro(cont_actual.ebitda_real),
        "objetivo_rentabilidad": "20 %",
    }
