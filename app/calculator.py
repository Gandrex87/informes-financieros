"""
Calculator: lee Postgres y construye el payload del JSON listo para mandar al
servicio. Esta version cubre slide 1 + slide 2.

Decisiones:
- Datos crudos vienen de ventas_comerciales (operaciones individuales).
- Datos agregados vienen de contabilidad_mensual (snapshot mensual del Sheet).
- Comparativas YoY: pagas_señales y arras_firmadas de contabilidad_mensual del
  año anterior. NO usamos ventas_comerciales para YoY porque no hay datos 2025.
"""
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.db import connection
from app.formatter import (
    format_euro,
    format_int,
    format_int_signed,
    format_mes_anyo,
    format_mes_anyo_upper,
    format_mes_short_anyo,
    format_pct,
    format_pct_signed,
)

logger = logging.getLogger(__name__)

OBJETIVO_RENTABILIDAD = "20 %"  # constante corporativa


@dataclass
class ComercialMes:
    """Datos comerciales de un mes desde ventas_comerciales."""
    señales_total: Decimal | None
    señales_n_ops: int
    arras_total: Decimal | None
    arras_n_ops: int


@dataclass
class ContableMes:
    """Snapshot contable de un mes desde contabilidad_mensual."""
    pagas_señales: Decimal | None
    arras_firmadas: Decimal | None
    ingresos_contables: Decimal | None
    honorarios_intermediacion: Decimal | None
    resto_ingresos: Decimal | None
    margen_bruto: Decimal | None
    rentabilidad_bruta_pct: Decimal | None
    ebitda_no_extras: Decimal | None
    rentabilidad_operativa_pct: Decimal | None


def _mes_anterior(anyo: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return anyo - 1, 12
    return anyo, mes - 1


def _query_comercial(sede: str, anyo: int, mes: int) -> ComercialMes:
    """Lee de ventas_comerciales el resumen comercial de un mes.

    Incluye VENTAS + ALQUILERES (la slide 1 dice "VENTAS Y ALQUILER").
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    sql = f"""
        SELECT
            COALESCE(SUM(CASE
                WHEN fecha_senal >= make_date(%(anyo)s, %(mes)s, 1)
                 AND fecha_senal < make_date(%(anyo)s, %(mes)s, 1) + INTERVAL '1 month'
                THEN honorarios_totales END), 0) AS senales_total,
            COUNT(*) FILTER (WHERE
                fecha_senal >= make_date(%(anyo)s, %(mes)s, 1)
            AND fecha_senal < make_date(%(anyo)s, %(mes)s, 1) + INTERVAL '1 month'
            ) AS senales_n_ops,
            COALESCE(SUM(CASE
                WHEN fecha_arras >= make_date(%(anyo)s, %(mes)s, 1)
                 AND fecha_arras < make_date(%(anyo)s, %(mes)s, 1) + INTERVAL '1 month'
                 AND arras_firmadas = 'SI'
                THEN honorarios_totales END), 0) AS arras_total,
            COUNT(*) FILTER (WHERE
                fecha_arras >= make_date(%(anyo)s, %(mes)s, 1)
            AND fecha_arras < make_date(%(anyo)s, %(mes)s, 1) + INTERVAL '1 month'
            AND arras_firmadas = 'SI'
            ) AS arras_n_ops
        FROM {schema}.ventas_comerciales;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"anyo": anyo, "mes": mes})
        row = cur.fetchone()
    return ComercialMes(
        señales_total=row["senales_total"],
        señales_n_ops=row["senales_n_ops"],
        arras_total=row["arras_total"],
        arras_n_ops=row["arras_n_ops"],
    )


def _query_contable(sede: str, escenario: str, anyo: int, mes: int) -> ContableMes | None:
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    sql = f"""
        SELECT "pagas_señales", arras_firmadas, ingresos_contables,
               honorarios_intermediacion, resto_ingresos,
               margen_bruto, rentabilidad_bruta_pct,
               ebitda_no_extras, rentabilidad_operativa_pct
        FROM {schema}.contabilidad_mensual
        WHERE sede = %(sede)s AND escenario = %(escenario)s
          AND anyo = %(anyo)s AND mes = %(mes)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {
            "sede": sede, "escenario": escenario, "anyo": anyo, "mes": mes,
        })
        row = cur.fetchone()
    if not row:
        return None
    return ContableMes(
        pagas_señales=row["pagas_señales"],
        arras_firmadas=row["arras_firmadas"],
        ingresos_contables=row["ingresos_contables"],
        honorarios_intermediacion=row["honorarios_intermediacion"],
        resto_ingresos=row["resto_ingresos"],
        margen_bruto=row["margen_bruto"],
        rentabilidad_bruta_pct=row["rentabilidad_bruta_pct"],
        ebitda_no_extras=row["ebitda_no_extras"],
        rentabilidad_operativa_pct=row["rentabilidad_operativa_pct"],
    )


def _variacion(actual: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Calcula (actual - anterior) / anterior. Devuelve None si no se puede."""
    if actual is None or anterior is None or anterior == 0:
        return None
    return (actual - anterior) / anterior


def build_payload_slide_2(
    sede: str,
    anyo: int,
    mes: int,
    escenario: str = "con_crm",
) -> dict[str, Any]:
    """Compone el dict de tokens para slides 1 y 2.

    Devuelve un dict listo para mandar al servicio /generar-informe.
    Incluye _color_overrides para colores condicionales.
    """
    anyo_prev, mes_prev = _mes_anterior(anyo, mes)
    anyo_yoy, mes_yoy = anyo - 1, mes

    # --- Lecturas ---
    com_actual = _query_comercial(sede, anyo, mes)
    com_prev = _query_comercial(sede, anyo_prev, mes_prev)
    cont_actual = _query_contable(sede, escenario, anyo, mes)
    cont_prev = _query_contable(sede, escenario, anyo_prev, mes_prev)
    cont_yoy = _query_contable(sede, escenario, anyo_yoy, mes_yoy)

    if cont_actual is None:
        raise ValueError(
            f"No hay datos contables para sede={sede} escenario={escenario} "
            f"{anyo}-{mes:02d}. Carga primero contabilidad_mensual."
        )

    # --- Variaciones MoM ---
    var_reservas_mom = _variacion(com_actual.señales_total, com_prev.señales_total)
    var_contratos_mom = _variacion(com_actual.arras_total, com_prev.arras_total)
    var_ingresos_mom = _variacion(
        cont_actual.ingresos_contables,
        cont_prev.ingresos_contables if cont_prev else None,
    )
    var_rentab_mom = _variacion(
        cont_actual.rentabilidad_operativa_pct,
        cont_prev.rentabilidad_operativa_pct if cont_prev else None,
    )

    # --- Deltas de operaciones ---
    delta_ops_reservas = com_actual.señales_n_ops - com_prev.señales_n_ops
    delta_ops_contratos = com_actual.arras_n_ops - com_prev.arras_n_ops

    # --- Datos comparativos ---
    señales_mes_anterior = com_prev.señales_total
    señales_anyo_anterior = cont_yoy.pagas_señales if cont_yoy else None
    arras_mes_anterior = com_prev.arras_total
    arras_anyo_anterior = cont_yoy.arras_firmadas if cont_yoy else None

    # --- Color overrides ---
    color_overrides = {}
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom"] = "verde" if var_reservas_mom >= 0 else "rojo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom"] = "verde" if var_contratos_mom >= 0 else "rojo"
    if var_ingresos_mom is not None:
        color_overrides["var_ingresos_mom"] = "verde" if var_ingresos_mom >= 0 else "rojo"
    if var_rentab_mom is not None:
        color_overrides["var_rentab_mom"] = "verde" if var_rentab_mom >= 0 else "rojo"

    # --- Tramo de comision: por ahora hardcoded, vendra de parametros_sede_mes ---
    tramo_comision = "3 %"

    return {
        "_color_overrides": color_overrides,

        # Identificacion
        "sede": sede,
        "sede_upper": sede.upper(),
        "mes_año": format_mes_anyo(anyo, mes),
        "mes_año_upper": format_mes_anyo_upper(anyo, mes),
        "mes_anterior_short": format_mes_short_anyo(anyo_prev, mes_prev),
        "mes_año_anterior_short": format_mes_short_anyo(anyo_yoy, mes_yoy),

        # Slide 1 - portada
        "reservas_totales": format_euro(com_actual.señales_total),
        "contratos_firmados": format_euro(com_actual.arras_total),
        "ingresos_totales": format_euro(cont_actual.ingresos_contables),
        "tramo_comision": tramo_comision,

        # Slide 2 - tarjeta Reservas
        "var_reservas_mom": format_pct_signed(var_reservas_mom, decimales=1),
        "n_ops_reservas": format_int(com_actual.señales_n_ops),
        "delta_ops_reservas": format_int_signed(delta_ops_reservas, suffix="ops"),
        "reservas_mes_anterior": format_euro(señales_mes_anterior),
        "reservas_año_anterior": format_euro(señales_anyo_anterior),

        # Slide 2 - tarjeta Contratos firmados
        "var_contratos_mom": format_pct_signed(var_contratos_mom, decimales=2),
        "n_ops_contratos": format_int(com_actual.arras_n_ops),
        "delta_ops_contratos": format_int_signed(delta_ops_contratos, suffix="ops"),
        "contratos_mes_anterior": format_euro(arras_mes_anterior),
        "contratos_año_anterior": format_euro(arras_anyo_anterior),

        # Slide 2 - tarjeta Ingresos
        "var_ingresos_mom": format_pct_signed(var_ingresos_mom, decimales=2),
        "ingresos_ventas": format_euro(cont_actual.honorarios_intermediacion),
        "ingresos_alquiler": format_euro(cont_actual.resto_ingresos),
        "ingresos_mes_anterior": format_euro(cont_prev.ingresos_contables if cont_prev else None),
        "margen_bruto": format_pct(cont_actual.rentabilidad_bruta_pct, decimales=0),

        # Slide 2 - tarjeta Rentabilidad operativa
        "rentabilidad_op": format_pct(cont_actual.rentabilidad_operativa_pct, decimales=2),
        "var_rentab_mom": format_pct_signed(var_rentab_mom, decimales=2),
        "resultado_op": format_euro(cont_actual.ebitda_no_extras),
        "objetivo_rentabilidad": OBJETIVO_RENTABILIDAD,
    }
