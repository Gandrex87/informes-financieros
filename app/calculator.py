"""
Calculator: lee Postgres y construye el payload del JSON listo para mandar al
servicio. Esta version cubre slide 1 + slide 2.


# Fuentes de datos

## 1. finanzas_automation.ventas_comerciales (datos crudos)
Una fila por operacion inmobiliaria. Alimentada desde el Sheet "COMERCIAL LION
VALENCIA" (pestañas "Ventas VLC 2026" y "Alquiler VLC 2026").

Campos relevantes:
    - fecha_senal:        fecha de la señalizacion (pagas y señales)
    - fecha_arras:        fecha de firma de arras
    - honorarios_totales: importe de honorarios de la operacion
    - inmueble:           direccion (alquileres llevan prefijo "ALQ.-")
    - arras_firmadas:     'SI' | 'NO'
    - condicionadas:      'SI' | 'NO'
    - tipo:               'compraventa' | (otros para alquiler)

De aqui sacamos: importes y conteos del mes actual y del mes anterior.

## 2. informes_financieros.contabilidad_mensual (snapshot mensual agregado)
Una fila por (sede, escenario, anyo, mes). Alimentada desde el Sheet contable
manual de Lion mediante un workflow de n8n (rango B62:V107 del Sheet).

PK: (sede, escenario, anyo, mes). Hoy solo se carga escenario='con_crm'.

De aqui sacamos:
    - Ingresos (contables, intermediacion, alquileres como "resto_ingresos")
    - Margenes y rentabilidades (ya calculados en el Sheet)
    - EBITDA, break even, etc.
    - YoY de pagas_señales y arras_firmadas (necesario porque ventas_comerciales
      NO tiene datos de 2025; usamos los agregados manuales que contabilidad cargo).

## 3. Constantes hardcodeadas en codigo
    - OBJETIVO_RENTABILIDAD: "20 %" — objetivo corporativo fijo.
    - tramo_comision: "3 %" — pendiente mover a tabla parametros_sede_mes
      cuando varie por sede o mes.


# Mapeo token JSON -> fuente

Token                       | Fuente
----------------------------+--------------------------------------------
reservas_totales            | ventas_comerciales: SUM(honorarios) WHERE fecha_senal en mes
n_ops_reservas              | ventas_comerciales: COUNT(*) WHERE fecha_senal en mes
contratos_firmados          | ventas_comerciales: SUM(honorarios) WHERE fecha_arras en mes AND arras_firmadas='SI'
n_ops_contratos             | ventas_comerciales: COUNT(*) idem
reservas_mes_anterior       | ventas_comerciales: idem reservas pero mes-1
reservas_año_anterior       | contabilidad_mensual.pagas_señales del año anterior
contratos_mes_anterior      | ventas_comerciales: idem contratos pero mes-1
contratos_año_anterior      | contabilidad_mensual.arras_firmadas del año anterior
ingresos_totales            | contabilidad_mensual.ingresos_contables
ingresos_ventas             | contabilidad_mensual.honorarios_intermediacion
ingresos_alquiler           | contabilidad_mensual.resto_ingresos
ingresos_mes_anterior       | contabilidad_mensual.ingresos_contables (mes-1)
margen_bruto                | contabilidad_mensual.rentabilidad_bruta_pct (formato porcentaje)
rentabilidad_op             | contabilidad_mensual.rentabilidad_operativa_pct
resultado_op                | contabilidad_mensual.ebitda_no_extras
objetivo_rentabilidad       | constante "20 %"
tramo_comision              | constante "3 %" (pendiente parametros_sede_mes)


# Calculos derivados

Todas las variaciones (var_X_mom) se calculan en Python:
    (actual - anterior) / anterior

Los deltas de operaciones (delta_ops_*) son restas simples:
    n_ops_actual - n_ops_anterior

Los colores condicionales (_color_overrides) se decide aqui mismo:
    "verde" si la variacion >= 0, "rojo" si < 0.


# Discrepancias conocidas (P-18 en PENDIENTES.md)

Algunos importes del calculator no cuadran con el PDF de abril 2026:
    - reservas_totales: -6.100 €
    - contratos_firmados: -10.576 €
    - contratos_año_anterior: -58.858 €
Hipotesis: ventas_comerciales tiene menos operaciones registradas que el
cuadro manual del Sheet. Pendiente validar con contabilidad. Los numeros
del calculator vienen directos de la tabla — si la tabla falta operaciones,
las falta el informe.
"""
import logging
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.db import connection
from app.formatter import (
    format_delta_ops_full,
    format_euro,
    format_euro_compacto,
    format_int,
    format_int_signed,
    format_mes_anyo,
    format_mes_anyo_upper,
    format_mes_capitalizado,
    format_mes_short_anyo,
    format_mes_short_upper_year,
    format_mes_upper,
    format_mes_year3_upper,
    format_numero,
    format_pct,
    format_pct_signed,
    format_pct_with_arrow,
    format_trimestre,
)

logger = logging.getLogger(__name__)

OBJETIVO_RENTABILIDAD = "20 %"  # constante corporativa

# Slide 9 - tramo de comision. Hoy fijo al 3%. Pendiente que contabilidad
# confirme si es una escala por volumen de facturacion (ver P-22).
TRAMO_COMISION_PCT = Decimal("0.03")  # 3%
TRAMO_COMISION_LABEL = "3 %"

# Slide 9 - parametros del calculo de comision por director.
# TODO multi-sede / parametros_sede_mes: cuando varie por sede o entre
# otro director, mover estos valores a una tabla parametros_sede_mes
# con clave (sede, anyo, mes). Por ahora son constantes de Valencia.
#
# >>> SI ENTRA / SALE UN DIRECTOR: cambiar N_DIRECTORES aqui. <<<
# Afecta a comision_variable_por_director = total_a_repartir / N_DIRECTORES.
N_DIRECTORES = 2  # Valencia, constante provisional
SUELDO_FIJO_DIRECTOR = Decimal("2666.67")  # bruto mensual por director, provisional
# Subtotal de "COBRADO DE MESES ANTERIORES". Fuente real sin confirmar
# (pendiente contabilidad, ver P-23). Hardcoded del mock para validar la
# sumatoria de la zona inferior del slide 9.
SUBTOTAL_COMISION_ATRASOS_PROVISIONAL = Decimal("1021.89")

# Slide 12 - constante provisional pendiente de confirmar con contabilidad.
# (total_pendiente_cobro ya NO es provisional: deriva de pago_agentes,
#  igual que slide 7).
INVERSION_TECNOLOGICA_PROVISIONAL = "27k€"  # pendiente origen (¿constante anual? ¿acumulado?)

# Mapeo numero de mes -> string usado en las tablas resumen_mensual_*.
# Septiembre tiene dos variantes segun la tabla (ver _mes_label_*).
_MES_LABEL_3 = ["", "ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]


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


def _mes_anterior(anyo: int, mes: int) -> tuple[int, int]:
    if mes == 1:
        return anyo - 1, 12
    return anyo, mes - 1


def _mes_siguiente(anyo: int, mes: int) -> tuple[int, int]:
    if mes == 12:
        return anyo + 1, 1
    return anyo, mes + 1


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


def _query_alquileres_mes(anyo: int, mes: int) -> AlquilerMes:
    """Lee de ventas_comerciales el resumen de alquileres de un mes.

    Filtro: inmueble LIKE 'ALQ.-%' (convencion de la ingesta).
    Para alquileres, fecha_arras = fecha de firma del contrato.
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
                THEN honorarios_totales END), 0) AS contratos_total,
            COUNT(*) FILTER (WHERE
                fecha_arras >= make_date(%(anyo)s, %(mes)s, 1)
            AND fecha_arras < make_date(%(anyo)s, %(mes)s, 1) + INTERVAL '1 month'
            AND arras_firmadas = 'SI'
            ) AS contratos_n_ops
        FROM {schema}.ventas_comerciales
        WHERE inmueble LIKE 'ALQ.-%%';
    """
    with connection() as conn:
        cur = conn.execute(sql, {"anyo": anyo, "mes": mes})
        row = cur.fetchone()
    return AlquilerMes(
        señales_total=row["senales_total"],
        señales_n_ops=row["senales_n_ops"],
        contratos_total=row["contratos_total"],
        contratos_n_ops=row["contratos_n_ops"],
    )


def _query_pipeline_ventas() -> list[dict]:
    """Lista de ventas pendientes de firma (slide 5).

    Filtro:
    - Es venta (no alquiler): inmueble NOT LIKE 'ALQ.-%'.
    - Pendiente: arras_firmadas = 'NO'.
    - Excluimos las 2 promociones de obra nueva conocidas (van a su seccion aparte).

    NO excluimos todo 'urb.%' porque hay ventas normales con ese prefijo
    (ej. 'Urb. Loma de Caballeros 3'). Solo excluimos las promociones
    de obra nueva explicitas.

    DISTINCT defensivo por (inmueble, fecha_senal, honorarios_totales) para
    neutralizar duplicados puntuales detectados en P-19.

    Ordenado por honorarios descendente.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    sql = f"""
        SELECT DISTINCT ON (inmueble, fecha_senal, honorarios_totales)
            inmueble, honorarios_totales
        FROM {schema}.ventas_comerciales
        WHERE inmueble NOT LIKE 'ALQ.-%%'
          AND arras_firmadas = 'NO'
          AND inmueble NOT ILIKE '%%victoria kent%%'
          AND inmueble NOT ILIKE 'urb.%%santa%%b_rbara%%'
        ORDER BY inmueble, fecha_senal, honorarios_totales, honorarios_totales DESC NULLS LAST;
    """
    with connection() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
    items = [{"inmueble": r["inmueble"], "honorarios": r["honorarios_totales"]} for r in rows]
    # DISTINCT ON requiere ORDER BY que empieza por las claves; reordenamos
    # despues por importe para presentacion.
    items.sort(key=lambda r: r["honorarios"] or 0, reverse=True)
    return items


def _query_obra_nueva() -> list[dict]:
    """Operaciones de obra nueva agrupadas por promocion (slide 5).

    Detecta dos promociones conocidas:
    - 'C. VICTORIA KENT'
    - 'Urb. Altos de Santa Bárbara'

    Filtro: cualquier estado EXCEPTO 'CAÍDA - 0' (operacion caida).
    Las obras nuevas no se rigen por arras_firmadas='SI' como las ventas
    normales — incluimos todas las que esten "vivas".

    Devuelve una fila por promocion con nombre y total de honorarios.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    # Filtro defensivo: solo las promociones explicitamente conocidas.
    # Si aparece una nueva, hay que añadirla aqui (o migrar a una tabla
    # promociones_obra_nueva). Ver discusion en docs/MAPEO_DATOS.md.
    sql = f"""
        SELECT
            CASE
                WHEN inmueble ILIKE '%%victoria kent%%' THEN 'C. VICTORIA KENT'
                WHEN inmueble ILIKE 'urb.%%santa%%b_rbara%%' THEN 'Urb. Altos de Santa Bárbara'
            END AS promocion,
            COALESCE(SUM(honorarios_totales), 0) AS total_honorarios
        FROM {schema}.ventas_comerciales
        WHERE (arras_firmadas IS DISTINCT FROM 'CAÍDA - 0')
          AND (
              inmueble ILIKE '%%victoria kent%%'
              OR inmueble ILIKE 'urb.%%santa%%b_rbara%%'
          )
        GROUP BY promocion
        HAVING COALESCE(SUM(honorarios_totales), 0) > 0
        ORDER BY total_honorarios DESC;
    """
    with connection() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
    return [{"nombre": r["promocion"], "honorarios": r["total_honorarios"]} for r in rows]


def _query_operaciones_condicionadas() -> list[dict]:
    """Operaciones condicionadas vivas (slide 6).

    Filtro: pendiente_fecha_condicionada = TRUE.
    Este flag es exclusivo de ventas (no aparece en alquileres por convencion
    de la ingesta), asi que no hace falta filtrar por tipo.

    Cada fila es una operacion individual. No se agrupa por inmueble: cada
    arras condicionada tiene su propio importe.

    Ordenado por honorarios descendente.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    sql = f"""
        SELECT inmueble, honorarios_totales
        FROM {schema}.ventas_comerciales
        WHERE pendiente_fecha_condicionada = TRUE
        ORDER BY honorarios_totales DESC NULLS LAST;
    """
    with connection() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
    return [{"inmueble": r["inmueble"], "honorarios": r["honorarios_totales"]} for r in rows]


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


def _query_pipeline_alquileres() -> list[dict]:
    """Lista de alquileres con señal pero sin contrato firmado todavia.

    Excluimos:
    - Las firmadas ('SI').
    - Las caidas ('CAÍDA - 0', con tilde en la I).

    Sin filtro de mes: incluye señalizaciones de meses anteriores que aun
    no han firmado. Ordenado por honorarios descendente.
    """
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    sql = f"""
        SELECT inmueble, honorarios_totales
        FROM {schema}.ventas_comerciales
        WHERE inmueble LIKE 'ALQ.-%%'
          AND fecha_senal IS NOT NULL
          AND (arras_firmadas IS NULL OR arras_firmadas NOT IN ('SI', 'CAÍDA - 0'))
        ORDER BY honorarios_totales DESC NULLS LAST;
    """
    with connection() as conn:
        cur = conn.execute(sql)
        rows = cur.fetchall()
    return [{"inmueble": r["inmueble"], "honorarios": r["honorarios_totales"]} for r in rows]


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
    anyo_next, mes_next = _mes_siguiente(anyo, mes)

    # --- Lecturas ---
    com_actual = _query_comercial(sede, anyo, mes)
    com_prev = _query_comercial(sede, anyo_prev, mes_prev)
    cont_actual = _query_contable(sede, escenario, anyo, mes)
    cont_prev = _query_contable(sede, escenario, anyo_prev, mes_prev)
    cont_yoy = _query_contable(sede, escenario, anyo_yoy, mes_yoy)

    # Slide 4: alquileres
    alq_actual = _query_alquileres_mes(anyo, mes)
    alq_prev = _query_alquileres_mes(anyo_prev, mes_prev)
    pipeline_alq_rows = _query_pipeline_alquileres()

    # Slide 5: pipeline Q2 (ventas + obra nueva)
    pipeline_ventas_rows = _query_pipeline_ventas()
    obra_nueva_rows = _query_obra_nueva()

    # Slide 6: operaciones condicionadas
    condicionadas_rows = _query_operaciones_condicionadas()

    # Slide 7: cobros pendientes de liquidacion
    cobros_pendientes_rows = _query_cobros_pendientes()

    # Slide 9: comisiones (zona "FIRMADO Y COBRADO EN <mes>")
    arras_cobradas = _query_arras_cobradas_mes(anyo, mes)
    alq_cobrados = _query_alquileres_cobrados_mes(anyo, mes)

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

    # --- Datos del grafico slide 3 (3 periodos x 2 series) ---
    # No van por replaceAllText; el generator los usa para crear el PNG.
    chart_periodos = [
        {
            "etiqueta": format_mes_short_anyo(anyo_yoy, mes_yoy).replace("'", " '"),
            "reservas": float(señales_anyo_anterior) if señales_anyo_anterior is not None else 0.0,
            "contratos": float(arras_anyo_anterior) if arras_anyo_anterior is not None else 0.0,
        },
        {
            "etiqueta": format_mes_short_anyo(anyo_prev, mes_prev).replace("'", " '"),
            "reservas": float(señales_mes_anterior) if señales_mes_anterior is not None else 0.0,
            "contratos": float(arras_mes_anterior) if arras_mes_anterior is not None else 0.0,
        },
        {
            "etiqueta": format_mes_short_anyo(anyo, mes).replace("'", " '"),
            "reservas": float(com_actual.señales_total) if com_actual.señales_total is not None else 0.0,
            "contratos": float(com_actual.arras_total) if com_actual.arras_total is not None else 0.0,
        },
    ]

    # --- Calculos especificos del slide 3 ---
    # Variaciones YoY (comparativa interanual)
    var_reservas_yoy = _variacion(com_actual.señales_total, señales_anyo_anterior)
    var_contratos_yoy = _variacion(com_actual.arras_total, arras_anyo_anterior)

    # --- Calculos especificos del slide 4 (alquileres) ---
    var_reservas_alquiler_mom = _variacion(alq_actual.señales_total, alq_prev.señales_total)
    var_contratos_alquiler_mom = _variacion(alq_actual.contratos_total, alq_prev.contratos_total)
    delta_ops_reservas_alquiler = alq_actual.señales_n_ops - alq_prev.señales_n_ops
    delta_ops_contratos_alquiler = alq_actual.contratos_n_ops - alq_prev.contratos_n_ops

    # Pipeline alquileres: lista para expand_lists. Prefijo de nombre con
    # el caracter Unicode de barra (ya usamos esa convencion).
    pipeline_alquiler = [
        {
            "nombre": f"▌ {_limpia_inmueble_alq(row['inmueble'])}",
            "importe": format_euro(row["honorarios"]),
        }
        for row in pipeline_alq_rows
    ]
    total_pipeline_alquiler = sum(
        (row["honorarios"] or 0) for row in pipeline_alq_rows
    )
    n_ops_pipeline_alquiler = len(pipeline_alq_rows)

    # --- Calculos especificos del slide 5 ---
    # Pipeline ventas: lista para slots venta_pend_*.
    ventas_pendientes = [
        {"nombre": row["inmueble"], "importe": format_euro(row["honorarios"])}
        for row in pipeline_ventas_rows
    ]
    total_ventas_pipeline = sum(
        (row["honorarios"] or 0) for row in pipeline_ventas_rows
    )

    # Obra nueva: lista para slots obra_nueva_*.
    obras_nuevas = [
        {"nombre": row["nombre"], "importe": format_euro(row["honorarios"])}
        for row in obra_nueva_rows
    ]
    total_obra_nueva = sum(
        (row["honorarios"] or 0) for row in obra_nueva_rows
    )

    # Total agregado del pipeline (ventas + obra nueva + alquileres)
    total_pipeline = total_ventas_pipeline + total_obra_nueva + total_pipeline_alquiler
    n_ops_pipeline = (
        len(pipeline_ventas_rows)
        + len(obra_nueva_rows)
        + n_ops_pipeline_alquiler
    )

    # --- Calculos especificos del slide 6 (operaciones condicionadas) ---
    operaciones_condicionadas = [
        {"nombre": row["inmueble"], "importe": format_euro(row["honorarios"])}
        for row in condicionadas_rows
    ]
    volumen_riesgo = sum(
        (Decimal(str(row["honorarios"])) if row["honorarios"] else Decimal(0))
        for row in condicionadas_rows
    )
    n_ops_condicionadas = len(condicionadas_rows)
    impacto_etiqueta, impacto_color = _clasifica_impacto(volumen_riesgo)

    # --- Slide 7: cobros pendientes de liquidacion ---
    cobros_pendientes = [
        {"nombre": row["inmueble"], "importe": format_euro(row["importe"])}
        for row in cobros_pendientes_rows
    ]
    total_pendiente_cobro_num = sum(
        (Decimal(str(row["importe"])) if row["importe"] else Decimal(0))
        for row in cobros_pendientes_rows
    )

    # --- Slide 9: comisiones (Parte A: firmado y cobrado en el mes) ---
    # La comision es el tramo (hoy 3%) sobre lo cobrado.
    ventas_cobradas = arras_cobradas if arras_cobradas is not None else Decimal(0)
    alquileres_cobrados = alq_cobrados if alq_cobrados is not None else Decimal(0)
    comision_ventas_mes = ventas_cobradas * TRAMO_COMISION_PCT
    comision_alquileres_mes = alquileres_cobrados * TRAMO_COMISION_PCT
    subtotal_comision_mes = comision_ventas_mes + comision_alquileres_mes

    # Parte B: calculo final. subtotal_atrasos hoy es constante provisional
    # (pendiente fuente real de "COBRADO DE MESES ANTERIORES", P-23).
    subtotal_comision_atrasos = SUBTOTAL_COMISION_ATRASOS_PROVISIONAL
    total_comision_repartir = subtotal_comision_mes + subtotal_comision_atrasos
    comision_variable_por_director = total_comision_repartir / N_DIRECTORES
    total_por_director = comision_variable_por_director + SUELDO_FIJO_DIRECTOR

    # Ticket medio = contratos_firmados / n_ops_contratos
    ticket_medio = None
    if com_actual.arras_n_ops > 0 and com_actual.arras_total is not None:
        ticket_medio = com_actual.arras_total / com_actual.arras_n_ops
    ticket_medio_prev = None
    if com_prev.arras_n_ops > 0 and com_prev.arras_total is not None:
        ticket_medio_prev = com_prev.arras_total / com_prev.arras_n_ops
    var_ticket_medio_mom = _variacion(ticket_medio, ticket_medio_prev)

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
    # Slide 3
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom_arrow"] = "verde" if var_reservas_mom >= 0 else "rojo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom_arrow"] = "verde" if var_contratos_mom >= 0 else "rojo"
    if var_reservas_yoy is not None:
        color_overrides["var_reservas_yoy"] = "verde" if var_reservas_yoy >= 0 else "rojo"
    if var_contratos_yoy is not None:
        color_overrides["var_contratos_yoy"] = "verde" if var_contratos_yoy >= 0 else "rojo"
    if var_ticket_medio_mom is not None:
        color_overrides["var_ticket_medio_mom"] = "verde" if var_ticket_medio_mom >= 0 else "rojo"
    # Slide 4
    if var_reservas_alquiler_mom is not None:
        color_overrides["var_reservas_alquiler_mom"] = "verde" if var_reservas_alquiler_mom >= 0 else "rojo"
    if var_contratos_alquiler_mom is not None:
        color_overrides["var_contratos_alquiler_mom"] = "verde" if var_contratos_alquiler_mom >= 0 else "rojo"
    # Slide 6: color del volumen_riesgo segun severidad
    color_overrides["volumen_riesgo"] = impacto_color
    # Slide 11: mismos criterios que slide 6 para version compacta
    color_overrides["volumen_riesgo_short"] = impacto_color
    # Slide 11: rentabilidad operativa con signo, verde si supera el objetivo
    # del 20% corporativo (umbral hardcoded en OBJETIVO_RENTABILIDAD).
    if cont_actual.rentabilidad_operativa_pct is not None:
        objetivo_pct = Decimal("0.20")
        if cont_actual.rentabilidad_operativa_pct >= objetivo_pct:
            color_overrides["rentabilidad_op_signed"] = "verde"
        else:
            color_overrides["rentabilidad_op_signed"] = "rojo"
    # Slide 11: tokens "_observacion" siempre van en amarillo
    # (columna semantica de atencion, no es señal verde/rojo).
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom_observacion"] = "amarillo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom_observacion"] = "amarillo"

    # --- Tramo de comision: por ahora hardcoded, vendra de parametros_sede_mes ---
    tramo_comision = "3 %"

    return {
        "_color_overrides": color_overrides,
        "_chart_reservas_arras": chart_periodos,

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

        # --- Slide 3: Produccion comercial ---
        # Formatos de mes usados en el slide
        "mes_anterior_upper": format_mes_year3_upper(anyo_prev, mes_prev),
        "mes_año_upper_short": format_mes_year3_upper(anyo, mes),
        "mes_año_anterior_upper": format_mes_anyo_upper(anyo_yoy, mes_yoy),
        "mes_año_anterior_short_upper": format_mes_short_upper_year(anyo_yoy, mes_yoy),

        # Tarjeta Pagas y señales (Mar26 vs Abr26)
        "n_ops_reservas_mes_anterior": format_int(com_prev.señales_n_ops),
        "var_reservas_mom_arrow": format_pct_with_arrow(var_reservas_mom, decimales=1),
        "delta_ops_reservas_full": format_delta_ops_full(
            com_actual.señales_n_ops, com_prev.señales_n_ops
        ),

        # Tarjeta Arras y contratos (Mar26 vs Abr26)
        "n_ops_contratos_mes_anterior": format_int(com_prev.arras_n_ops),
        "var_contratos_mom_arrow": format_pct_with_arrow(var_contratos_mom, decimales=1),
        "delta_ops_contratos_full": format_delta_ops_full(
            com_actual.arras_n_ops, com_prev.arras_n_ops
        ),

        # Tarjeta Comparativa interanual (vs ABRIL 2025)
        "var_reservas_yoy": format_pct_signed(var_reservas_yoy, decimales=0),
        "var_contratos_yoy": format_pct_signed(var_contratos_yoy, decimales=0),

        # Tarjeta Ticket medio
        "ticket_medio": format_euro(ticket_medio),
        "ticket_medio_mes_anterior": format_euro(ticket_medio_prev),
        "var_ticket_medio_mom": format_pct_signed(var_ticket_medio_mom, decimales=1),

        # --- Slide 4: Gestion de alquileres ---
        # Tarjeta Reservas (señales)
        "reservas_alquiler": format_euro(alq_actual.señales_total),
        "var_reservas_alquiler_mom": format_pct_with_arrow(var_reservas_alquiler_mom, decimales=2),
        "n_ops_reservas_alquiler": format_int(alq_actual.señales_n_ops),
        "delta_ops_reservas_alquiler": format_int_signed(delta_ops_reservas_alquiler, suffix="op."),

        # Tarjeta Contratos firmados
        "contratos_alquiler": format_euro(alq_actual.contratos_total),
        "var_contratos_alquiler_mom": format_pct_with_arrow(var_contratos_alquiler_mom, decimales=2),
        "n_ops_contratos_alquiler": format_int(alq_actual.contratos_n_ops),
        "delta_ops_contratos_alquiler": format_int_signed(delta_ops_contratos_alquiler, suffix="ops."),

        # Pipeline pendiente de firma (lista que se expandira a slots)
        "pipeline_alquiler": pipeline_alquiler,
        "total_pipeline_alquiler": format_euro(total_pipeline_alquiler),
        "n_ops_pipeline_alquiler": format_int(n_ops_pipeline_alquiler),
        "nota_pipeline_alquiler": "",  # vacia por ahora (decision tomada)

        # --- Slide 7: Cobros pendientes de liquidación ---
        "cobros_pendientes": cobros_pendientes,
        "total_pendiente_cobro_sin_euro": format_numero(total_pendiente_cobro_num),
        "nota_cobros": "",  # vacia por ahora (decision tomada, como slide 4)

        # --- Slide 6: Operaciones condicionadas ---
        "operaciones_condicionadas": operaciones_condicionadas,
        "volumen_riesgo": format_euro(volumen_riesgo),
        "n_ops_condicionadas": format_int(n_ops_condicionadas),
        "impacto_facturacion": impacto_etiqueta,

        # --- Slide 9: Comisiones (Parte A: firmado y cobrado en el mes) ---
        # Mes del informe en mayusculas sin año, para "FIRMADO Y COBRADO EN ABRIL".
        "mes_informe_upper": format_mes_upper(mes),
        "tramo_comision": TRAMO_COMISION_LABEL,
        "ventas_cobradas_mes": format_euro(ventas_cobradas, decimales=2),
        "comision_ventas_mes": format_euro(comision_ventas_mes, decimales=2),
        "alquileres_cobrados_mes": format_euro(alquileres_cobrados, decimales=2),
        "comision_alquileres_mes": format_euro(comision_alquileres_mes, decimales=2),
        "subtotal_comision_mes": format_euro(subtotal_comision_mes, decimales=2),

        # Slide 9 Parte B: calculo final (subtotal_atrasos provisional)
        "subtotal_comision_atrasos": format_euro(subtotal_comision_atrasos, decimales=2),
        "total_comision_repartir": format_euro(total_comision_repartir, decimales=2),
        "comision_variable_por_director": format_euro(comision_variable_por_director, decimales=2),
        "sueldo_fijo_director": format_euro(SUELDO_FIJO_DIRECTOR, decimales=2),
        "total_por_director": format_euro(total_por_director, decimales=2),

        # --- Slide 11: Semáforo estratégico ---
        # Asignacion de KPIs a columnas es fija (no dinamica).
        # Tokens "_observacion" son el MISMO valor que var_*_mom pero con
        # token distinto para poder colorearlos en amarillo (la columna
        # "En observacion" del slide 11). Sin esto, compartirian color con
        # las variaciones del slide 2 al buscar por texto.
        "var_reservas_mom_observacion": format_pct_signed(var_reservas_mom, decimales=1),
        "var_contratos_mom_observacion": format_pct_signed(var_contratos_mom, decimales=2),
        "rentabilidad_op_signed": format_pct_signed(
            cont_actual.rentabilidad_operativa_pct, decimales=2,
        ),
        "volumen_riesgo_short": format_euro_compacto(volumen_riesgo, decimales=1),
        # Mes siguiente capitalizado para la narrativa "impacto en facturacion de X"
        "mes_siguiente_capitalizado": format_mes_capitalizado(mes_next),

        # --- Slide 12: Hoja de ruta del mes siguiente ---
        # La mayoria de tokens del slide 12 ya estan emitidos por slides
        # anteriores (volumen_riesgo, n_ops_condicionadas, total_pipeline,
        # n_ops_pipeline, objetivo_rentabilidad). Aqui solo añadimos los
        # especificos del slide.
        "mes_siguiente_upper": format_mes_anyo_upper(anyo_next, mes_next),
        "inversion_tecnologica": INVERSION_TECNOLOGICA_PROVISIONAL,
        # Ya NO es provisional: deriva del mismo calculo que slide 7
        # (con € aqui porque el slide 12 muestra el simbolo).
        "total_pendiente_cobro": format_euro(total_pendiente_cobro_num),

        # --- Slide 5: Pipeline Q2 ---
        # Trimestre del mes en curso (Q1, Q2, Q3, Q4)
        "trimestre": format_trimestre(mes),
        # Lista ventas pendientes (expand_lists -> slots venta_pend_N_*)
        "ventas_pendientes": ventas_pendientes,
        # Lista obra nueva (expand_lists -> slots obra_nueva_N_*)
        "obras_nuevas": obras_nuevas,
        # Totales agregados a la derecha
        "total_ventas_pipeline": format_euro(total_ventas_pipeline),
        "total_obra_nueva": format_euro(total_obra_nueva),
        "total_pipeline": format_euro(total_pipeline),
        "n_ops_pipeline": format_int(n_ops_pipeline),
    }


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
