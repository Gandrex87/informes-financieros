"""
Base común del calculator — sede-agnóstico.

Contiene lo que comparten TODAS las sedes (hoy Valencia, futuro Alicante):
- Dataclasses de filas de BD.
- Helpers puros (aritmética de fechas, variaciones, clasificación).
- Queries genéricas a Postgres que no dependen del informe de una sede
  concreta.

NO contiene el ensamblaje del payload (eso es específico de cada sede:
calculator_valencia.py, calculator_alicante.py) ni constantes de negocio
de una sede (nº directores, tramo comisión, etc.).

NOTA sobre filtro de sede: las queries comerciales/contables hoy NO filtran
por sede en el SQL (solo hay datos de Valencia en Postgres). Cuando se
integre Alicante (otro Sheet, otra tabla o columna `sede`), habrá que
añadir el filtro real. Marcado con TODO. Extracción mecánica: el
comportamiento es idéntico al calculator.py monolítico anterior.
"""
import logging
import os
from dataclasses import dataclass
from decimal import Decimal

from app.db import connection

logger = logging.getLogger(__name__)

# Mapeo numero de mes -> string usado en las tablas resumen_mensual_*.
# Septiembre tiene dos variantes segun la tabla (ver _query_alquileres_cobrados_mes).
_MES_LABEL_3 = ["", "ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]


# ----- Dataclasses (filas de BD) -----

@dataclass
class ComercialMes:
    """Datos comerciales de un mes desde ventas_comerciales (ventas + alquileres)."""
    señales_total: Decimal | None
    señales_n_ops: int
    arras_total: Decimal | None
    arras_n_ops: int


@dataclass
class AlquilerMes:
    """Datos solo de alquileres de un mes.

    Para alquileres, fecha_arras representa la fecha de firma del CONTRATO
    (la ingesta hace ese mapeo desde "FECHA CONTRATO" del Sheet).
    """
    señales_total: Decimal | None
    señales_n_ops: int
    contratos_total: Decimal | None
    contratos_n_ops: int


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


# ----- Helpers puros -----

def _mes_anterior(anyo: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return anyo - 1, 12
    return anyo, mes - 1


def _mes_siguiente(anyo: int, mes: int) -> tuple[int, int]:
    if mes == 12:
        return anyo + 1, 1
    return anyo, mes + 1


def _variacion(actual: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Calcula (actual - anterior) / anterior. Devuelve None si no se puede."""
    if actual is None or anterior is None or anterior == 0:
        return None
    return (actual - anterior) / anterior


def _clasifica_impacto(volumen_riesgo: Decimal | None) -> tuple[str, str]:
    """Devuelve (etiqueta, color) segun el volumen en riesgo.

    Rangos acordados:
        > 80.000        -> 'Crítico'  (rojo)
        > 30.000 y <=80k -> 'Alto'     (amarillo)
        <= 30.000       -> 'Estable'  (verde)

    Si volumen es None o 0: 'Estable' (verde).
    """
    if volumen_riesgo is None or volumen_riesgo <= Decimal("30000"):
        return ("Estable", "verde")
    if volumen_riesgo <= Decimal("80000"):
        return ("Alto", "amarillo")
    return ("Crítico", "rojo")


def _limpia_inmueble_alq(inmueble: str) -> str:
    """Quita el prefijo 'ALQ.-' de los nombres de inmuebles de alquiler.

    Ej: 'ALQ.- C. Pintor Domingo 42' -> 'C. Pintor Domingo 42'.
    """
    if not inmueble:
        return ""
    prefijo = "ALQ.-"
    if inmueble.startswith(prefijo):
        return inmueble[len(prefijo):].strip()
    return inmueble.strip()


# ----- Queries comunes (las usan todas las sedes) -----
# TODO multi-sede: añadir filtro de sede en el SQL cuando Alicante tenga
# datos en Postgres (otro Sheet -> otra tabla o columna `sede`).

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


def _query_arras_cobradas_mes(anyo: int, mes: int) -> Decimal | None:
    """Lee resumen_mensual_arras__sin_condicion.cobradas para un mes.

    Es la base de calculo de la comision de ventas del slide 9.
    Filtro por anio + mes (string 3 letras, ej. 'abr'). Solo Valencia.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    mes_label = _MES_LABEL_3[mes]
    sql = f"""
        SELECT cobradas
        FROM {schema}.resumen_mensual_arras__sin_condicion
        WHERE anio = %(anyo)s AND mes = %(mes_label)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"anyo": anyo, "mes_label": mes_label})
        row = cur.fetchone()
    return row["cobradas"] if row else None


def _query_alquileres_cobrados_mes(anyo: int, mes: int) -> Decimal | None:
    """Lee resumen_mensual_alquileres.honorarios_cobrados para un mes.

    Base de calculo de la comision de alquileres del slide 9.
    OJO: esta tabla usa 'sept' (4 letras) para septiembre, distinto a
    resumen_mensual_arras__sin_condicion que usa 'sep'. Para mes != 9
    el label de 3 letras funciona en ambas.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    mes_label = "sept" if mes == 9 else _MES_LABEL_3[mes]
    sql = f"""
        SELECT honorarios_cobrados
        FROM {schema}.resumen_mensual_alquileres
        WHERE anio = %(anyo)s AND mes = %(mes_label)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"anyo": anyo, "mes_label": mes_label})
        row = cur.fetchone()
    return row["honorarios_cobrados"] if row else None


def _query_cobros_pendientes() -> list[dict]:
    """Cobros pendientes de liquidacion (slide 7).

    Fuente: informes_financieros.pago_agentes, columna pte_facturar (TEXT).
    pte_facturar puede ser: 'CAÍDA', '0', o un numero > 0 (lo pendiente).

    Filtro:
    - Solo strings numericos puros (descarta 'CAÍDA').
    - Valor > 1 para descartar basura de coma flotante de la ingesta
      (ej. '0.21000000000003638' que es ruido, no un cobro real). Ver P-24.

    Sin filtro de mes: es el estado vivo de cobros pendientes (dato de tipo
    "foto actual", ver seccion HIBRIDO en docs/MAPEO_DATOS.md).

    Ordenado por importe descendente.
    """
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    sql = f"""
        SELECT inmueble, CAST(pte_facturar AS NUMERIC) AS importe
        FROM {schema}.pago_agentes
        WHERE pte_facturar ~ '^[0-9]+\\.?[0-9]*$'
          AND CAST(pte_facturar AS NUMERIC) > 1
        ORDER BY importe DESC;
    """
    with connection() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
    return [{"inmueble": r["inmueble"], "importe": r["importe"]} for r in rows]
