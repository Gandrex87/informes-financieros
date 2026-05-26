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
    _limpia_inmueble_alq,
    _mes_anterior,
    _mes_siguiente,
    _query_alquileres_cobrados_mes,
    _query_arras_cobradas_mes,
    _query_break_even,
    _query_cobros_pendientes,
    _query_comercial,
    _query_comisiones_atrasos,
    _query_contable,
    _query_pipeline_alquileres,
    _query_pipeline_ventas,
    _query_tramo_comision,
    _variacion,
    _variacion_tasa,
)
# Narrativa templating determinista del slide 6 (Break Even). Vive en
# calculator_valencia.py; la reutilizamos tal cual aunque el "importe base"
# de Alicante sea arras_firmadas y no facturacion_cobrada (decision usuario
# 2026-05-22: comunicar mal este matiz es aceptable hoy, se ajusta si chirria).
from app.calculator_valencia import _narrativa_break_even
from app.formatter import (
    format_delta_ops_full,
    format_euro,
    format_int,
    format_int_signed,
    format_mes_anyo,
    format_mes_anyo_upper,
    format_mes_capitalizado,
    format_mes_short_anyo,
    format_mes_upper,
    format_mes_year3_upper,
    format_numero,
    format_pct,
    format_pct_signed,
    format_pct_signed_compacto,
    format_pct_with_arrow,
    format_trimestre,
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

# Slide 8 - facturacion objetivo proyectada (marcador movil de la barra del
# slide 8). PROVISIONAL hardcoded (similar a INVERSION_TECNOLOGICA en
# calculator.py de Valencia). El PDF manual de Alicante abril 2026 mostraba
# "Estimacion: 160.000 €" como objetivo manual de direccion. En Valencia el
# patron es facturacion_objetivo_proy = break_even_proy ("el minimo a
# facturar es el break even") — en Alicante no aplica porque el "objetivo"
# del PDF (160k) NO coincide con el break_even_proy (77k segun BD).
# Pendiente confirmar con contabilidad la fuente real.
FACTURACION_OBJETIVO_PROY_PROVISIONAL = Decimal("160000.00")


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

    # --- Slide 3: ticket medio (importe medio por operacion de arras) ---
    ticket_medio = None
    if com_actual.arras_n_ops > 0 and com_actual.arras_total is not None:
        ticket_medio = com_actual.arras_total / com_actual.arras_n_ops
    ticket_medio_prev = None
    if com_prev.arras_n_ops > 0 and com_prev.arras_total is not None:
        ticket_medio_prev = com_prev.arras_total / com_prev.arras_n_ops
    var_ticket_medio_mom = _variacion(ticket_medio, ticket_medio_prev)

    # --- Slide 4: Pipeline pendiente de firma ---
    # Alicante NO tiene obra nueva (decision estructural, confirmada en BD:
    # cero filas con 'urb.', 'kent', etc.). Por eso _query_pipeline_ventas se
    # llama SIN inmuebles_excluir_ilike (default = tupla vacia).
    pipeline_ventas_rows = _query_pipeline_ventas(SEDE)
    ventas_pendientes = [
        {"nombre": r["inmueble"], "importe": format_euro(r["honorarios"])}
        for r in pipeline_ventas_rows
    ]
    total_ventas_pipeline = sum((r["honorarios"] or 0) for r in pipeline_ventas_rows)

    # Pipeline alquileres: mismo filtro que Valencia. Alicante tiene muy pocas
    # operaciones de alquiler en BD; cuando todas estan 'SI' o 'CAIDA', la
    # lista sale vacia y los slots quedan en blanco.
    pipeline_alq_rows = _query_pipeline_alquileres(SEDE)
    pipeline_alquiler = [
        {
            "nombre": f"▌ {_limpia_inmueble_alq(r['inmueble'])}",
            "importe": format_euro(r["honorarios"]),
        }
        for r in pipeline_alq_rows
    ]
    total_pipeline_alquiler = sum((r["honorarios"] or 0) for r in pipeline_alq_rows)

    # Total pipeline = ventas + alquileres. NO se suma obra nueva (no existe
    # en Alicante).
    total_pipeline = total_ventas_pipeline + total_pipeline_alquiler
    n_ops_pipeline = len(pipeline_ventas_rows) + len(pipeline_alq_rows)

    # --- Slide 5: Cobros pendientes de liquidacion ---
    # Estado vivo: lo pendiente de cobrar AHORA en pago_agentes (no fotografia
    # del cierre del mes). Filtrado por sede='Alicante' tras la migracion
    # 2026-05-21 de pago_agentes.
    cobros_pendientes_rows = _query_cobros_pendientes(SEDE)
    cobros_pendientes = [
        {"nombre": r["inmueble"], "importe": format_euro(r["importe"])}
        for r in cobros_pendientes_rows
    ]
    total_pendiente_cobro_num = sum(
        (Decimal(str(r["importe"])) if r["importe"] else Decimal(0))
        for r in cobros_pendientes_rows
    )

    # --- Mes siguiente: para slide 5 ("Prioridad <mes>:"), slide 8 (BE
    # proyectado) y slide 10 (Proximos pasos mayo).
    anyo_next, mes_next = _mes_siguiente(anyo, mes)

    # --- Slide 8: Estimacion Break Even mayo (proyeccion) ---
    # Misma fuente que slide 6 pero del MES SIGUIENTE. Si la fila no existe
    # en contabilidad_mensual (mes futuro sin cargar), los importes salen
    # vacios pero los estados (labels fijos) sí se emiten.
    break_even_proy = _query_break_even(SEDE, escenario, anyo_next, mes_next)

    # --- Slide 6: Break Even y objetivos de facturacion ---
    # Decision usuario 2026-05-22: el slide tiene DOS bases distintas
    # convivendo:
    #   - base_be (= arras firmadas): marcador movil de la barra + estados
    #     de la tabla (✓ SUPERADO / FALTAN). Coherencia visual con la bolita
    #     amarilla del marcador.
    #   - ingresos_be (= ingresos_contables): margen de seguridad +
    #     narrativa. Igual que Valencia (la narrativa habla de "facturacion
    #     cobrada", concepto de ingresos).
    # No es contradictorio: el marcador comunica "lo que hemos vendido en
    # arras"; la narrativa explica "lo que hemos cobrado vs gastos".
    base_be = com_actual.arras_total              # estados y marcador
    ingresos_be = cont_actual.ingresos_contables  # narrativa y margen seguridad
    break_even_mes = _query_break_even(SEDE, escenario, anyo, mes)
    if break_even_mes is not None:
        be_break_even = break_even_mes.break_even
        be_m10 = break_even_mes.ingresos_margen_10
        be_m20 = break_even_mes.ingresos_margen_20
        be_m30 = break_even_mes.ingresos_margen_30
        be_m40 = break_even_mes.ingresos_margen_40
    else:
        be_break_even = be_m10 = be_m20 = be_m30 = be_m40 = None

    # Helper local: estado de cada umbral comparado contra base_be (arras).
    def _estado_umbral(umbral: Decimal | None) -> str:
        if umbral is None or base_be is None:
            return ""
        if base_be >= umbral:
            return "✓ SUPERADO"
        return f"FALTAN: {format_euro(umbral - base_be)}"

    # Margen de seguridad: ingresos_contables - break_even (igual que
    # Valencia). NO usa arras firmadas: la narrativa habla de facturacion
    # cobrada y el margen de seguridad debe coincidir conceptualmente.
    margen_seguridad = None
    if ingresos_be is not None and be_break_even is not None:
        margen_seguridad = ingresos_be - be_break_even

    narrativa_break_even = _narrativa_break_even(
        ingresos_be, be_break_even, margen_seguridad,
    )

    # --- Slide 7: Comisiones de directores ---
    # Parte A: FIRMADO Y COBRADO EN <mes>. Lo cobrado en el mes por tipo de
    # operacion x tramo_comision_pct = comision del mes.
    arras_cobradas = _query_arras_cobradas_mes(SEDE, anyo, mes)
    alq_cobrados = _query_alquileres_cobrados_mes(SEDE, anyo, mes)
    ventas_cobradas = arras_cobradas if arras_cobradas is not None else Decimal(0)
    alquileres_cobrados = alq_cobrados if alq_cobrados is not None else Decimal(0)
    comision_ventas_mes = ventas_cobradas * tramo_comision_pct
    comision_alquileres_mes = alquileres_cobrados * tramo_comision_pct
    subtotal_comision_mes = comision_ventas_mes + comision_alquileres_mes

    # Parte C: COBRADO DE MESES ANTERIORES.
    # Resuelto 2026-05-26: ingesta carga ahora filas con sede='Alicante' en
    # informes_financieros.comisiones_atrasos_directores. Estado vivo
    # (sin filtro de anyo/mes). Mismo patron exacto que Valencia (ver
    # calculator_valencia.py:_query_comisiones_atrasos consumption block):
    # - mes_origen de BD '(Feb.)' -> mostrar sin parentesis 'Feb.'
    # - porcentaje de BD 0.03 -> mostrar como '(3%)'
    # - importe formateado a 2 decimales para coherencia con subtotales.
    comisiones_atrasos_rows = _query_comisiones_atrasos(SEDE)
    comisiones_atrasos = [
        {
            "nombre": row["inmueble"] or "",
            "mes": (row["mes_origen"] or "").strip("()"),
            "tramo": (
                f"({int(row['porcentaje'] * 100)}%)"
                if row["porcentaje"] is not None else ""
            ),
            "importe": format_euro(row["importe"], decimales=2),
        }
        for row in comisiones_atrasos_rows
    ]
    subtotal_comision_atrasos = sum(
        (Decimal(str(row["importe"])) if row["importe"] else Decimal(0))
        for row in comisiones_atrasos_rows
    )

    # Parte B: calculo final.
    # OJO Alicante: N_DIRECTORES = 1, asi que comision_variable_por_director =
    # total_comision_repartir (no se divide). total_por_director suma sueldo.
    total_comision_repartir = subtotal_comision_mes + subtotal_comision_atrasos
    comision_variable_por_director = total_comision_repartir / N_DIRECTORES
    total_por_director = comision_variable_por_director + SUELDO_FIJO_DIRECTOR

    # --- Slide 3: datos para el grafico de barras (2 periodos en Alicante) ---
    # Valencia usa 3 periodos (Abr'25, Mar'26, Abr'26 - incluye YoY). Alicante
    # solo 2 (Mar'26, Abr'26) porque no hay datos 2025 de Alicante en la BD.
    # chart_generator.py acepta 2 o 3 periodos.
    # format_mes_short_anyo devuelve "Mar '26" (ya con espacio antes del
    # apostrofe). Lo usamos directo sin replace adicional.
    chart_periodos = [
        {
            "etiqueta": format_mes_short_anyo(anyo_prev, mes_prev),
            "reservas": float(señales_mes_anterior) if señales_mes_anterior is not None else 0.0,
            "contratos": float(arras_mes_anterior) if arras_mes_anterior is not None else 0.0,
        },
        {
            "etiqueta": format_mes_short_anyo(anyo, mes),
            "reservas": float(com_actual.señales_total) if com_actual.señales_total is not None else 0.0,
            "contratos": float(com_actual.arras_total) if com_actual.arras_total is not None else 0.0,
        },
    ]

    # --- Color overrides ---
    color_overrides: dict[str, str] = {}
    # Slide 2
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
    if var_ticket_medio_mom is not None:
        color_overrides["var_ticket_medio_mom"] = "verde" if var_ticket_medio_mom >= 0 else "rojo"
    # Slide 8: margen de seguridad. Verde si se cubre el break even, rojo si
    # hay deficit (margen negativo = mes en perdidas). En plantilla esta
    # verde fijo; sin este override, un deficit saldria verde y comunicaria
    # lo contrario de la realidad. Mismo criterio que Valencia.
    if margen_seguridad is not None:
        color_overrides["margen_seguridad"] = "verde" if margen_seguridad >= 0 else "rojo"
    # Slide 9: semaforo estrategico. Los tokens *_observacion y *_riesgo
    # tienen el MISMO valor que sus equivalentes del slide 2 / 5+10. Si
    # usaramos el mismo texto, apply_color_overrides pintaria todas las
    # cajas (busca por VALOR, no por token). Añadimos zero-width space
    # (U+200B) al final para que cada caja sea unica para la busqueda
    # pero indistinguible a la vista. Mismo truco que Valencia (slide 11).
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom_observacion"] = "amarillo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom_observacion"] = "amarillo"
    color_overrides["total_pendiente_cobro_riesgo"] = "rojo"

    # Slide 6: color de los 5 estados (columna ESTADO de la tabla derecha).
    # "✓ SUPERADO" -> verde; "FALTAN: <X> €" -> rojo. Solo coloreamos los
    # *_estado (no los importes), porque los importes tambien aparecen en
    # la barra/linea de tiempo izquierda y no queremos pintarla.
    # OJO Alicante: el color usa base_be (arras_firmadas), MISMA base que el
    # texto del estado (ver _estado_umbral). Valencia usa ingresos_be porque
    # alli texto y color comparten esa base; en Alicante texto y color
    # tienen que coincidir igual o aparecerian estados textuales SUPERADO
    # en rojo, y viceversa.
    for _tok, _umbral in (
        ("break_even_estado", be_break_even),
        ("margen_10_estado", be_m10),
        ("margen_20_estado", be_m20),
        ("margen_30_estado", be_m30),
        ("margen_40_estado", be_m40),
    ):
        if base_be is not None and _umbral is not None:
            color_overrides[_tok] = "verde" if base_be >= _umbral else "rojo"

    return {
        "_color_overrides": color_overrides,
        "_chart_reservas_arras": chart_periodos,

        # --- Slide 6: marcador movil de la barra (Break Even mes actual) ---
        # Equivalente al slide 8 de Valencia pero el marcador es
        # {{contratos_firmados}} (arras firmadas), no {{ingresos_totales}}.
        # El valor a posicionar es base_be = com_actual.arras_total (decision
        # 2026-05-22: el marcador y los estados de la tabla del slide 6
        # usan la misma base para que sean coherentes visualmente).
        # La plantilla Alicante slide 6 tiene los 5 cuadros guia invisibles
        # con tokens {{_carril_*}} (sin sufijo, mismos nombres que Valencia
        # slide 8); no hay colision porque cada sede tiene su propia plantilla.
        "_break_even_position_slide_6_alc": {
            "contratos_firmados": base_be,
            "break_even": be_break_even,
            "margen_10": be_m10,
            "margen_20": be_m20,
            "margen_30": be_m30,
        },

        # --- Slide 8: marcador movil de la barra (Break Even proyectado) ---
        # Valores numericos crudos que generator.py extrae para posicionar
        # {{facturacion_objetivo_proy}} en uno de los 5 carriles de la
        # barra (deficit / BE-M10 / M10-M20 / M20-M30 / superior). La
        # plantilla Alicante slide 8 tiene los 5 cuadros guia invisibles
        # con tokens {{_carril_proy_*}} (mismos nombres que Valencia
        # slide 10), pero en slide_index=7 (no 9 como Valencia). Por eso
        # usamos la clave _break_even_position_slide_8_alc que el generator
        # encamina a CONFIG_SLIDE_8_ALICANTE (slide_index=7).
        # OJO: en Alicante facturacion_objetivo_proy es una constante
        # manual (FACTURACION_OBJETIVO_PROY_PROVISIONAL=160.000 €), no
        # viene de BD. Los 4 umbrales SI vienen de BD (break_even_proy).
        # Decision usuario 2026-05-25: el marcador se posiciona segun donde
        # cae la constante 160.000 € respecto a los umbrales reales del
        # mes siguiente. Patron identico a Valencia (el valor a posicionar
        # es el mismo que muestra el marcador).
        "_break_even_position_slide_8_alc": {
            "facturacion_objetivo_proy": FACTURACION_OBJETIVO_PROY_PROVISIONAL,
            "break_even_proy": (
                break_even_proy.break_even if break_even_proy else None
            ),
            "margen_10_proy": (
                break_even_proy.ingresos_margen_10 if break_even_proy else None
            ),
            "margen_20_proy": (
                break_even_proy.ingresos_margen_20 if break_even_proy else None
            ),
            "margen_30_proy": (
                break_even_proy.ingresos_margen_30 if break_even_proy else None
            ),
        },

        # --- Identificacion ---
        "sede": SEDE,
        "sede_upper": SEDE.upper(),
        "mes_año": format_mes_anyo(anyo, mes),
        "mes_año_upper": format_mes_anyo_upper(anyo, mes),
        "mes_anterior_short": format_mes_short_anyo(anyo_prev, mes_prev),
        "mes_anterior_capitalizado": format_mes_capitalizado(mes_prev),
        # Formatos de mes usados en slide 3 (cabeceras de las tarjetas).
        "mes_anterior_upper": format_mes_year3_upper(anyo_prev, mes_prev),
        "mes_año_upper_short": format_mes_year3_upper(anyo, mes),

        # --- Slide 1: Portada ---
        "reservas_totales": format_euro(com_actual.señales_total),
        "contratos_firmados": format_euro(com_actual.arras_total),
        "ingresos_totales": format_euro(cont_actual.ingresos_contables),
        "tramo_comision": format_pct(tramo_comision_pct, decimales=0),

        # --- Slide 2: tarjeta Reservas ---
        # Variaciones MoM con format_pct_signed_compacto (max 1 decimal,
        # omite ',0' si entero al redondear). Decision 2026-05-22:
        # uniformizar las 4 variaciones del slide 2 con este patron, que
        # coincide con el estilo del PDF manual de Alicante.
        "var_reservas_mom": format_pct_signed_compacto(var_reservas_mom),
        "n_ops_reservas": format_int(com_actual.señales_n_ops),
        "delta_ops_reservas": format_int_signed(delta_ops_reservas, suffix="ops"),
        "reservas_mes_anterior": format_euro(señales_mes_anterior),
        # YoY: emitido aunque la plantilla actual de Alicante no lo muestre.
        "reservas_año_anterior": format_euro(señales_anyo_anterior),

        # --- Slide 2: tarjeta Contratos firmados ---
        "var_contratos_mom": format_pct_signed_compacto(var_contratos_mom),
        "n_ops_contratos": format_int(com_actual.arras_n_ops),
        "delta_ops_contratos": format_int_signed(delta_ops_contratos, suffix="ops"),
        "contratos_mes_anterior": format_euro(arras_mes_anterior),
        "contratos_año_anterior": format_euro(arras_anyo_anterior),

        # --- Slide 2: tarjeta Ingresos ---
        "var_ingresos_mom": format_pct_signed_compacto(var_ingresos_mom),
        "ingresos_mes_anterior": format_euro(cont_prev.ingresos_contables if cont_prev else None),
        # Alicante NO muestra desglose ventas/alquiler (no tiene alquileres).
        # margen_bruto: usamos rentabilidad_bruta_pct igual que Valencia.
        # Alicante PDF muestra "60,00%" (2 decimales), Valencia "60%".
        "margen_bruto": format_pct(cont_actual.rentabilidad_bruta_pct, decimales=2),

        # --- Slide 2: tarjeta Rentabilidad REAL ---
        # OJO: diferencia con Valencia. Alicante usa _real_pct y ebitda_real
        # (incluye gastos_extra). Valencia usa _operativa_pct y ebitda_no_extras.
        "rentabilidad_op": format_pct(cont_actual.rentabilidad_real_pct, decimales=2),
        "var_rentab_mom": format_pct_signed_compacto(var_rentab_mom),
        "resultado_op": format_euro(cont_actual.ebitda_real),
        "objetivo_rentabilidad": "20 %",

        # --- Slide 3: Tarjeta PAGAS Y SEÑALES ---
        "n_ops_reservas_mes_anterior": format_int(com_prev.señales_n_ops),
        "var_reservas_mom_arrow": format_pct_with_arrow(var_reservas_mom, decimales=1),
        "delta_ops_reservas_full": format_delta_ops_full(
            com_actual.señales_n_ops, com_prev.señales_n_ops,
        ),

        # --- Slide 3: Tarjeta CONTRATOS DE ARRAS ---
        "n_ops_contratos_mes_anterior": format_int(com_prev.arras_n_ops),
        "var_contratos_mom_arrow": format_pct_with_arrow(var_contratos_mom, decimales=1),
        "delta_ops_contratos_full": format_delta_ops_full(
            com_actual.arras_n_ops, com_prev.arras_n_ops,
        ),

        # --- Slide 3: Tarjeta TICKET MEDIO ---
        "ticket_medio": format_euro(ticket_medio),
        "ticket_medio_mes_anterior": format_euro(ticket_medio_prev),
        "var_ticket_medio_mom": format_pct_signed(var_ticket_medio_mom, decimales=1),

        # --- Slide 4: Pipeline pendiente de firma ---
        # Trimestre derivado del mes actual (Q1/Q2/Q3/Q4). Usado en titulo.
        "trimestre": format_trimestre(mes),
        # Listas que generator.expand_lists transformara en slots numerados:
        # - ventas_pendientes -> venta_pend_N_{nombre,importe}  (n_max=21)
        # - pipeline_alquiler -> venta_alq_pend_N_{nombre,importe}  (n_max=7)
        "ventas_pendientes": ventas_pendientes,
        "pipeline_alquiler": pipeline_alquiler,
        # Totales agregados a la derecha. Alicante NO emite total_obra_nueva.
        "total_ventas_pipeline": format_euro(total_ventas_pipeline),
        "total_pipeline_alquiler": format_euro(total_pipeline_alquiler),
        "total_pipeline": format_euro(total_pipeline),
        "n_ops_pipeline": format_int(n_ops_pipeline),

        # --- Slide 6: Break Even y objetivos de facturacion ---
        # Importes de los 5 umbrales (BE, M10/20/30/40) leidos de
        # contabilidad_mensual. Mismos tokens que Valencia (la plantilla los
        # comparte; solo cambia la base de comparacion = base_be).
        "break_even": format_euro(be_break_even),
        "margen_10_objetivo": format_euro(be_m10),
        "margen_20_objetivo": format_euro(be_m20),
        "margen_30_objetivo": format_euro(be_m30),
        "margen_40_objetivo": format_euro(be_m40),
        # Estados de la columna ESTADO ("✓ SUPERADO" o "FALTAN: X €").
        # Comparados contra base_be = contratos_firmados (decision Alicante).
        "break_even_estado": _estado_umbral(be_break_even),
        "margen_10_estado": _estado_umbral(be_m10),
        "margen_20_estado": _estado_umbral(be_m20),
        "margen_30_estado": _estado_umbral(be_m30),
        "margen_40_estado": _estado_umbral(be_m40),
        # Tarjeta MARGEN DE SEGURIDAD: importe y narrativa.
        "margen_seguridad": format_euro(margen_seguridad),
        "narrativa_break_even": narrativa_break_even,

        # --- Slide 7: Comisiones de directores ---
        # Banner superior: "VOLUMEN DE FACTURACION DEL MES DE <ABRIL>" y
        # "<4 %> TRAMO MAXIMO ALCANZADO".
        "mes_informe_upper": format_mes_upper(mes),
        # Parte A (FIRMADO Y COBRADO EN <mes>). Decimales 2 para precision.
        "ventas_cobradas_mes": format_euro(ventas_cobradas, decimales=2),
        "comision_ventas_mes": format_euro(comision_ventas_mes, decimales=2),
        "alquileres_cobrados_mes": format_euro(alquileres_cobrados, decimales=2),
        "comision_alquileres_mes": format_euro(comision_alquileres_mes, decimales=2),
        "subtotal_comision_mes": format_euro(subtotal_comision_mes, decimales=2),
        # Parte C (COBRADO DE MESES ANTERIORES). Provisional desde mock;
        # cuando se cargue comisiones_atrasos_directores con sede='Alicante'
        # se sustituye por la lista real desde _query_comisiones_atrasos.
        "comisiones_atrasos": comisiones_atrasos,
        "subtotal_comision_atrasos": format_euro(subtotal_comision_atrasos, decimales=2),
        # Parte B (calculo final). N_DIRECTORES=1 => total_a_repartir =
        # comision_variable_por_director (no se divide).
        "total_comision_repartir": format_euro(total_comision_repartir, decimales=2),
        "comision_variable_por_director": format_euro(comision_variable_por_director, decimales=2),
        "sueldo_fijo_director": format_euro(SUELDO_FIJO_DIRECTOR, decimales=2),
        "total_por_director": format_euro(total_por_director, decimales=2),

        # --- Slide 8: Estimacion Break Even mayo (proyeccion) ---
        # 4 umbrales del mes siguiente (BE, M10, M20, M30) leidos de
        # contabilidad_mensual fila mes+1. Sin Margen 40 (decision tokenizacion).
        # facturacion_objetivo_proy = break_even_proy (mismo importe: el
        # minimo a facturar es el break even). Patron igual que Valencia.
        "mes_siguiente_upper_solo": format_mes_upper(mes_next),
        "break_even_proy": format_euro(
            break_even_proy.break_even if break_even_proy else None),
        # facturacion_objetivo_proy: constante manual provisional (160.000 €),
        # NO derivada de BD. Ver FACTURACION_OBJETIVO_PROY_PROVISIONAL en
        # cabecera del modulo.
        "facturacion_objetivo_proy": format_euro(FACTURACION_OBJETIVO_PROY_PROVISIONAL),
        "margen_10_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_10 if break_even_proy else None),
        "margen_20_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_20 if break_even_proy else None),
        "margen_30_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_30 if break_even_proy else None),
        # Estados proyectados: labels corporativos fijos (NO dependen del
        # mes ni del valor). Solo Alicante los emite (Valencia los tiene
        # como texto literal en plantilla, no tokenizados). Decision
        # tokenizacion 2026-05-19.
        "break_even_estado_proy": "SUPERVIVENCIA",
        "margen_10_estado_proy": "OBJETIVO",
        "margen_20_estado_proy": "ÓPTIMO",
        "margen_30_estado_proy": "EXCELENCIA",

        # --- Slide 5: Cobros pendientes de liquidacion ---
        # Lista que generator.expand_lists transformara en slots cobro_N_*
        # (n_max=26 en LIST_SPECS).
        "cobros_pendientes": cobros_pendientes,
        # Tarjeta izquierda muestra el total grande sin el simbolo €
        # (la plantilla pone el € como texto fijo separado).
        "total_pendiente_cobro_sin_euro": format_numero(total_pendiente_cobro_num),
        # Misma cifra CON € para reuso en slide 10 (Proximos pasos: Aceleracion
        # de cobros). El valor exacto debe coincidir caja a caja para el match.
        "total_pendiente_cobro": format_euro(total_pendiente_cobro_num),
        # "Prioridad <mes capitalizado>:" del slide 5.
        "mes_siguiente_capitalizado": format_mes_capitalizado(mes_next),
        # Nota opcional (ej. "Cobrada el 7/05/2026"). Hoy vacia: cuando la
        # ingesta marque cobros recientes podriamos rellenarla; mientras
        # tanto, replicamos el patron de Valencia.
        "nota_cobros": "",

        # --- Slide 10: Proximos pasos mayo (hoja de ruta) ---
        # Cuadricula 2x2. Tokens reutilizados de otros slides:
        # - total_pendiente_cobro (slide 5), trimestre (slide 4),
        #   total_pipeline, n_ops_pipeline (slide 4), objetivo_rentabilidad
        #   (slide 2). Aqui solo añadimos los 4 propios de este slide.
        # Tarjeta 1 (titulo: "PROXIMOS PASOS — <MES SIGUIENTE>"):
        "mes_siguiente_upper": format_mes_anyo_upper(anyo_next, mes_next),
        # Tarjeta 2 (Blindaje de operaciones): "0 €" + "0 Arras Condicionadas".
        # Alicante NO tiene operaciones condicionadas (decision estructural
        # 2026-05-15). El calculator emite 0 directamente. Tokens reutilizan
        # los nombres de Valencia (slide 6 condicionadas) por simetria.
        "volumen_riesgo": "0 €",
        "n_ops_condicionadas": "0",
        # Tarjeta 3 (Conversion de pipeline): "Superar facturacion de <Mes>".
        # mes_capitalizado se refiere al MES EN CURSO ("Abril"), no al
        # siguiente: la frase compara mayo contra abril.
        "mes_capitalizado": format_mes_capitalizado(mes),

        # --- Slide 9: Semaforo estrategico ---
        # Tokens reutilizados (mismo valor, distinto token name + ZWS):
        # - Columna OBSERVACION (amarillo): mismo valor que var_*_mom del
        #   slide 2 pero con zero-width space para no pintar tambien las
        #   cajas del slide 2.
        # - Columna RIESGO (rojo): mismo valor que total_pendiente_cobro del
        #   slide 5 + slide 10, con ZWS por la misma razon.
        # Tokens de FORTALEZAS (rentabilidad_op, ticket_medio, var_ticket_medio_mom)
        # ya estan emitidos arriba para slides 2 y 3; se reutilizan tal cual
        # (color verde fijo en plantilla, sin override).
        # Mismo formato compacto que en slide 2 + ZWS al final (zero-width
        # space, U+200B). Coherencia visual: slide 9 muestra los mismos
        # numeros que slide 2.
        "var_reservas_mom_observacion": format_pct_signed_compacto(var_reservas_mom) + "​",
        "var_contratos_mom_observacion": format_pct_signed_compacto(var_contratos_mom) + "​",
        "total_pendiente_cobro_riesgo": format_euro(total_pendiente_cobro_num) + "​",
    }
