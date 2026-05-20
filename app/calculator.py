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
from decimal import Decimal
from typing import Any

from app.db import connection
from app.calculator_base import (
    _MES_LABEL_3,
    AlquilerMes,
    BreakEvenMes,
    ComercialMes,
    ContableMes,
    ContratosResumenMes,
    _clasifica_impacto,
    _limpia_inmueble_alq,
    _mes_anterior,
    _mes_siguiente,
    _query_arras_cobradas_mes,
    _query_alquileres_cobrados_mes,
    _query_alquiler_senales_resumen,
    _query_break_even,
    _query_cobros_pendientes,
    _query_comercial,
    _query_contable,
    _query_contratos_resumen,
    _query_tramo_comision,
    _variacion,
)
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

# Slide 9 - el tramo de comision ya NO es constante: se calcula
# dinamicamente como SUM(porcentaje) de pagos_directores del mes
# (ver _query_tramo_comision en calculator_base). Resuelve P-22.

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


def _narrativa_break_even(
    ingresos: Decimal | None,
    break_even: Decimal | None,
    margen_seguridad: Decimal | None,
) -> str:
    """Genera el texto de analisis del slide 8 (templating determinista).

    Decision de diseño del proyecto: narrativa por plantilla en Python, NO
    LLM (la consistencia importa mas que la variedad en un documento
    financiero). Tres ramas segun la relacion facturacion/break even.
    """
    if ingresos is None or break_even is None or margen_seguridad is None:
        return ""
    fact = format_euro(ingresos)
    be = format_euro(break_even)
    if margen_seguridad > 0:
        ms = format_euro(margen_seguridad)
        return (
            f"La facturación cobrada ({fact}) supera el punto de equilibrio "
            f"({be}), con un margen de seguridad de {ms}. La operación es "
            f"rentable este mes; el excedente sobre el break even amortigua "
            f"posibles desviaciones."
        )
    if margen_seguridad == 0:
        return (
            f"La facturación cobrada ({fact}) iguala exactamente el punto de "
            f"equilibrio ({be}). No hay margen de seguridad: cualquier "
            f"desviación negativa llevaría el mes a pérdidas."
        )
    deficit = format_euro(-margen_seguridad)
    return (
        f"La facturación cobrada ({fact}) NO alcanza el punto de equilibrio "
        f"({be}); faltan {deficit} para cubrir la estructura de costes. El "
        f"mes cierra por debajo del break even."
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

    # Contratos firmados (slide 1/2 y derivados): suma de las tablas
    # resumen mensual (ventas + alquileres), NO ventas_comerciales.
    contr_actual = _query_contratos_resumen(anyo, mes)
    contr_prev = _query_contratos_resumen(anyo_prev, mes_prev)
    contr_yoy = _query_contratos_resumen(anyo_yoy, mes_yoy)

    # Slide 4: alquileres
    alq_actual = _query_alquileres_mes(anyo, mes)
    alq_prev = _query_alquileres_mes(anyo_prev, mes_prev)
    pipeline_alq_rows = _query_pipeline_alquileres()
    # Slide 4 - tarjeta Reservas/Señales: fuente = tabla resumen
    # resumen_mensual_alquiler_senales (NO ventas_comerciales).
    alq_sen_actual = _query_alquiler_senales_resumen(anyo, mes)
    alq_sen_prev = _query_alquiler_senales_resumen(anyo_prev, mes_prev)

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

    # Slide 8: break even del mes (variante sin extras, mismo escenario)
    break_even_mes = _query_break_even(sede, escenario, anyo, mes)

    # Slide 10: break even PROYECTADO del mes siguiente (misma tabla/escenario,
    # fila del mes+1 ya cargada en contabilidad_mensual).
    break_even_proy = _query_break_even(sede, escenario, anyo_next, mes_next)

    if cont_actual is None:
        raise ValueError(
            f"No hay datos contables para sede={sede} escenario={escenario} "
            f"{anyo}-{mes:02d}. Carga primero contabilidad_mensual."
        )

    # --- Variaciones MoM ---
    # Contratos: fuente = tablas resumen mensual (contr_*), no
    # ventas_comerciales. Reservas/ingresos/rentab siguen igual.
    var_reservas_mom = _variacion(com_actual.señales_total, com_prev.señales_total)
    var_contratos_mom = _variacion(contr_actual.honorarios, contr_prev.honorarios)
    var_ingresos_mom = _variacion(
        cont_actual.ingresos_contables,
        cont_prev.ingresos_contables if cont_prev else None,
    )
    # Rentabilidad operativa: ambos lados YA son % (fraccion 0..1). La
    # "variacion" es la DIFERENCIA EN PUNTOS PORCENTUALES (abril - marzo),
    # no la variacion relativa de _variacion. Ej: 0.3038 - 0.3099 = -0.0061
    # -> format_pct_signed lo muestra como -0,61 %.
    _rentab_prev = cont_prev.rentabilidad_operativa_pct if cont_prev else None
    if cont_actual.rentabilidad_operativa_pct is None or _rentab_prev is None:
        var_rentab_mom = None
    else:
        var_rentab_mom = cont_actual.rentabilidad_operativa_pct - _rentab_prev

    # --- Deltas de operaciones ---
    delta_ops_reservas = com_actual.señales_n_ops - com_prev.señales_n_ops
    delta_ops_contratos = contr_actual.num_operaciones - contr_prev.num_operaciones

    # --- Datos comparativos ---
    señales_mes_anterior = com_prev.señales_total
    señales_anyo_anterior = cont_yoy.pagas_señales if cont_yoy else None
    arras_mes_anterior = contr_prev.honorarios
    arras_anyo_anterior = contr_yoy.honorarios

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
            "contratos": float(contr_actual.honorarios) if contr_actual.honorarios is not None else 0.0,
        },
    ]

    # --- Calculos especificos del slide 3 ---
    # Variaciones YoY (comparativa interanual). Contratos: ambos lados
    # desde tablas resumen (contr_actual vs contr_yoy), fuente coherente.
    var_reservas_yoy = _variacion(com_actual.señales_total, señales_anyo_anterior)
    var_contratos_yoy = _variacion(contr_actual.honorarios, arras_anyo_anterior)

    # --- Calculos especificos del slide 4 (alquileres) ---
    # Señales: fuente resumen (alq_sen_*). Contratos alquiler: sigue
    # ventas_comerciales (alq_*), sin cambios.
    var_reservas_alquiler_mom = _variacion(alq_sen_actual.honorarios, alq_sen_prev.honorarios)
    var_contratos_alquiler_mom = _variacion(alq_actual.contratos_total, alq_prev.contratos_total)
    delta_ops_reservas_alquiler = alq_sen_actual.num_operaciones - alq_sen_prev.num_operaciones
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
    # El tramo de comision es DINAMICO: suma de los porcentajes de los
    # directores del mes en pagos_directores (ej. abril: 0.015+0.015=0.03).
    # Si falta el dato fallamos explicito en lugar de generar un PDF con
    # comision 0 silenciosa (leccion P-27: dato faltante de ingesta).
    tramo_comision_pct = _query_tramo_comision(anyo, mes)
    if tramo_comision_pct is None:
        raise ValueError(
            f"No hay tramo de comision en pagos_directores para "
            f"{anyo}-{mes:02d}. Carga primero pagos_directores."
        )
    ventas_cobradas = arras_cobradas if arras_cobradas is not None else Decimal(0)
    alquileres_cobrados = alq_cobrados if alq_cobrados is not None else Decimal(0)
    comision_ventas_mes = ventas_cobradas * tramo_comision_pct
    comision_alquileres_mes = alquileres_cobrados * tramo_comision_pct
    subtotal_comision_mes = comision_ventas_mes + comision_alquileres_mes

    # Parte B: calculo final. subtotal_atrasos hoy es constante provisional
    # (pendiente fuente real de "COBRADO DE MESES ANTERIORES", P-23).
    subtotal_comision_atrasos = SUBTOTAL_COMISION_ATRASOS_PROVISIONAL
    total_comision_repartir = subtotal_comision_mes + subtotal_comision_atrasos
    comision_variable_por_director = total_comision_repartir / N_DIRECTORES
    total_por_director = comision_variable_por_director + SUELDO_FIJO_DIRECTOR

    # --- Calculos especificos del slide 8 (Break Even y objetivos) ---
    # ingresos_contables es la "facturacion cobrada" que se compara contra
    # cada umbral. Estado: '✓ SUPERADO' si la facturacion alcanza el umbral,
    # 'FALTAN: <X> €' (lo que falta) si no. Variante SIN extras.
    ingresos_be = cont_actual.ingresos_contables

    def _estado_umbral(umbral: Decimal | None) -> str:
        if umbral is None or ingresos_be is None:
            return ""
        if ingresos_be >= umbral:
            return "✓ SUPERADO"
        return f"FALTAN: {format_euro(umbral - ingresos_be)}"

    if break_even_mes is not None:
        be_break_even = break_even_mes.break_even
        be_m10 = break_even_mes.ingresos_margen_10
        be_m20 = break_even_mes.ingresos_margen_20
        be_m30 = break_even_mes.ingresos_margen_30
        be_m40 = break_even_mes.ingresos_margen_40
    else:
        be_break_even = be_m10 = be_m20 = be_m30 = be_m40 = None

    # Margen de seguridad = facturacion cobrada - break even.
    # Positivo si se ha superado el punto muerto.
    margen_seguridad = None
    if ingresos_be is not None and be_break_even is not None:
        margen_seguridad = ingresos_be - be_break_even

    narrativa_break_even = _narrativa_break_even(
        ingresos_be, be_break_even, margen_seguridad,
    )

    # Ticket medio = contratos_firmados / n_ops_contratos (fuente resumen)
    ticket_medio = None
    if contr_actual.num_operaciones > 0 and contr_actual.honorarios is not None:
        ticket_medio = contr_actual.honorarios / contr_actual.num_operaciones
    ticket_medio_prev = None
    if contr_prev.num_operaciones > 0 and contr_prev.honorarios is not None:
        ticket_medio_prev = contr_prev.honorarios / contr_prev.num_operaciones
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
    # Slide 8: margen de seguridad. Verde si se cubre el break even,
    # rojo si hay deficit (margen negativo = el mes cierra en perdidas).
    # En plantilla esta en verde fijo; sin este override un deficit
    # saldria en verde, comunicando lo contrario de la realidad.
    if margen_seguridad is not None:
        color_overrides["margen_seguridad"] = "verde" if margen_seguridad >= 0 else "rojo"
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

    # --- Tramo de comision: dinamico desde pagos_directores (ej. "3 %") ---
    tramo_comision = format_pct(tramo_comision_pct, decimales=0)

    return {
        "_color_overrides": color_overrides,
        "_chart_reservas_arras": chart_periodos,
        # Valores numericos crudos para el posicionamiento dinamico del
        # marcador {{ingresos_totales}} en la barra del slide 8. El
        # generator lo extrae y manda updatePageElementTransform.
        "_break_even_position": {
            "ingresos": cont_actual.ingresos_contables,
            "break_even": be_break_even,
            "margen_10": be_m10,
            "margen_20": be_m20,
            "margen_30": be_m30,
        },

        # Identificacion
        "sede": sede,
        "sede_upper": sede.upper(),
        "mes_año": format_mes_anyo(anyo, mes),
        "mes_año_upper": format_mes_anyo_upper(anyo, mes),
        "mes_anterior_short": format_mes_short_anyo(anyo_prev, mes_prev),
        # Mes anterior capitalizado sin año, para textos "vs Marzo" del slide 2.
        "mes_anterior_capitalizado": format_mes_capitalizado(mes_prev),
        "mes_año_anterior_short": format_mes_short_anyo(anyo_yoy, mes_yoy),

        # Slide 1 - portada
        "reservas_totales": format_euro(com_actual.señales_total),
        "contratos_firmados": format_euro(contr_actual.honorarios),
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
        "n_ops_contratos": format_int(contr_actual.num_operaciones),
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
        "n_ops_contratos_mes_anterior": format_int(contr_prev.num_operaciones),
        "var_contratos_mom_arrow": format_pct_with_arrow(var_contratos_mom, decimales=1),
        "delta_ops_contratos_full": format_delta_ops_full(
            contr_actual.num_operaciones, contr_prev.num_operaciones
        ),

        # Tarjeta Comparativa interanual (vs ABRIL 2025)
        "var_reservas_yoy": format_pct_signed(var_reservas_yoy, decimales=0),
        "var_contratos_yoy": format_pct_signed(var_contratos_yoy, decimales=0),

        # Tarjeta Ticket medio
        "ticket_medio": format_euro(ticket_medio),
        "ticket_medio_mes_anterior": format_euro(ticket_medio_prev),
        "var_ticket_medio_mom": format_pct_signed(var_ticket_medio_mom, decimales=1),

        # --- Slide 4: Gestion de alquileres ---
        # Tarjeta Reservas (señales) - fuente resumen_mensual_alquiler_senales
        "reservas_alquiler": format_euro(alq_sen_actual.honorarios),
        "var_reservas_alquiler_mom": format_pct_with_arrow(var_reservas_alquiler_mom, decimales=2),
        "n_ops_reservas_alquiler": format_int(alq_sen_actual.num_operaciones),
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

        # --- Slide 8: Break Even y objetivos de facturación ---
        # ingresos_totales y mes_año_upper/sede_upper ya se emiten arriba.
        "break_even": format_euro(be_break_even),
        "margen_10_objetivo": format_euro(be_m10),
        "margen_20_objetivo": format_euro(be_m20),
        "margen_30_objetivo": format_euro(be_m30),
        "margen_40_objetivo": format_euro(be_m40),
        "margen_seguridad": format_euro(margen_seguridad),
        "break_even_estado": _estado_umbral(be_break_even),
        "margen_10_estado": _estado_umbral(be_m10),
        "margen_20_estado": _estado_umbral(be_m20),
        "margen_30_estado": _estado_umbral(be_m30),
        "margen_40_estado": _estado_umbral(be_m40),
        "narrativa_break_even": narrativa_break_even,

        # --- Slide 10: Break Even proyectado (mes siguiente) ---
        # contabilidad_mensual fila mes+1, mismo escenario. Sin estados ni
        # narrativa (la plantilla solo muestra umbrales). facturacion_objetivo
        # = break even proyectado (decision: el minimo a facturar). El slide
        # solo llega a margen 30% (no hay 40% proyectado).
        "mes_siguiente_upper_solo": format_mes_upper(mes_next),
        "break_even_proy": format_euro(
            break_even_proy.break_even if break_even_proy else None),
        "facturacion_objetivo_proy": format_euro(
            break_even_proy.break_even if break_even_proy else None),
        "margen_10_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_10 if break_even_proy else None),
        "margen_20_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_20 if break_even_proy else None),
        "margen_30_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_30 if break_even_proy else None),

        # --- Slide 6: Operaciones condicionadas ---
        "operaciones_condicionadas": operaciones_condicionadas,
        "volumen_riesgo": format_euro(volumen_riesgo),
        "n_ops_condicionadas": format_int(n_ops_condicionadas),
        "impacto_facturacion": impacto_etiqueta,

        # --- Slide 9: Comisiones (Parte A: firmado y cobrado en el mes) ---
        # Mes del informe en mayusculas sin año, para "FIRMADO Y COBRADO EN ABRIL".
        "mes_informe_upper": format_mes_upper(mes),
        "tramo_comision": tramo_comision,
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
        # Tokens "_observacion" tienen el mismo valor visible que var_*_mom
        # pero con un sufijo ​ (espacio de ancho cero, invisible). Sin
        # ese sufijo el texto seria identico al del slide 2 y, como
        # apply_color_overrides busca por VALOR de texto y no por token, el
        # override amarillo del slide 11 pintaba tambien las cajas del slide 2
        # (gana el ultimo). El ​ los hace distintos para la busqueda
        # pero indistinguibles a la vista.
        "var_reservas_mom_observacion": format_pct_signed(var_reservas_mom, decimales=1) + "​",
        "var_contratos_mom_observacion": format_pct_signed(var_contratos_mom, decimales=2) + "​",
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


