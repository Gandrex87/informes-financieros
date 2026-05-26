"""
Calculator de Castellón — compone el payload del informe Directores Comerciales.

Tercera sede del proyecto (tras Valencia y Alicante). Módulo INDEPENDIENTE de
calculator_valencia.py y calculator_alicante.py por decisión de arquitectura
(ver memory/project_arquitectura_multisede.md y docs/MIGRACION_MULTISEDE.md):
no se combinan ramas if sede==... — cada sede es un módulo paralelo que
comparte helpers/queries vía calculator_base.

Estructura idéntica a Alicante (10 slides). Diferencias respecto a Alicante:
- BD usa 'Castellon' (sin tilde, así se cargó la ingesta); el PDF debe
  mostrar 'Castellón' (con tilde). Se separa SEDE (BD) de SEDE_DISPLAY (PDF).
  Ver memory/project_castellon_bd_vs_display.md.
- Tramo comisión: provisional 4% en constante de módulo. Castellón aún no
  tiene fila en pagos_directores, así que NO se lee de BD como Alicante.
- Métrica de rentabilidad slide 2 tarjeta 4: OPERATIVA (rentabilidad_operativa_pct
  + ebitda_no_extras), igual que Valencia, NO igual que Alicante (que usa REAL).
  Decisión 2026-05-26: excluir gastos extra para tener una métrica más estable.

Implementación incremental por bloques (ver
docs/superpowers/specs/2026-05-26-castellon-design.md).
Bloque 1 (DONE): andamiaje.
Bloque 2 (DONE): slides 1, 2, 3 (KPIs financieros).
Bloque 3 (DONE): slides 4, 5, 6, 7 (pipeline, cobros, BE, comisiones).
Bloque 4 (este commit): slides 8, 9, 10 (BE proyectado, semáforo, próximos pasos).
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
    _variacion,
    _variacion_tasa,
)
# Narrativa templating determinista del slide 6 (Break Even). Reutilizada
# desde calculator_valencia.py (igual que hace calculator_alicante.py).
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
    format_pct_signed_compacto,
    format_pct_with_arrow,
    format_trimestre,
)

logger = logging.getLogger(__name__)

# Identidad de la sede.
# SEDE filtra BD (la columna sede en Postgres está sin tilde).
# SEDE_DISPLAY es lo que ve el lector del PDF (con tilde, ortográficamente
# correcto). La separación está ENCAPSULADA en este módulo — el dispatcher y
# calculator_base solo conocen SEDE.
SEDE = "Castellon"
SEDE_DISPLAY = "Castellón"

# Número de directores. Castellón es como Alicante: 1 director, la comisión
# variable NO se divide.
N_DIRECTORES = 1

# Sueldo fijo bruto del director (igual que Alicante).
SUELDO_FIJO_DIRECTOR = Decimal("1933.73")

# Tramo de comisión PROVISIONAL. A diferencia de Alicante (que lo lee de
# pagos_directores con _query_tramo_comision), Castellón aún no tiene fila
# cargada en esa tabla. TODO: cargar pagos_directores con sede='Castellon' y
# reemplazar esta constante por la query, igual que hace Alicante.
TRAMO_COMISION_PROVISIONAL = Decimal("0.04")

# Objetivo del marcador móvil del slide 8 (Break Even proyectado). Igual que
# Alicante mientras dirección no fije un objetivo específico para Castellón.
FACTURACION_OBJETIVO_PROY_PROVISIONAL = Decimal("160000.00")


def build_payload(
    anyo: int,
    mes: int,
    escenario: str = "con_crm",
) -> dict[str, Any]:
    """Compone el payload de tokens del informe Castellón para (anyo, mes).

    Cobertura actual (Bloque 3): slides 1-7 con datos reales.
    Tokens de slides 8-10: emitidos como string vacío hasta el Bloque 4.

    Raises:
        ValueError: si no hay datos contables para esa sede/anyo/mes.
    """
    # --- Calculo de fechas relativas ---
    anyo_prev, mes_prev = _mes_anterior(anyo, mes)
    anyo_next, mes_next = _mes_siguiente(anyo, mes)

    # --- Lecturas Postgres ---
    com_actual = _query_comercial(SEDE, anyo, mes)
    com_prev = _query_comercial(SEDE, anyo_prev, mes_prev)
    cont_actual = _query_contable(SEDE, escenario, anyo, mes)
    cont_prev = _query_contable(SEDE, escenario, anyo_prev, mes_prev)

    if cont_actual is None:
        raise ValueError(
            f"No hay datos contables para sede={SEDE} escenario={escenario} "
            f"{anyo}-{mes:02d}. Carga primero contabilidad_mensual."
        )

    # Tramo de comisión: constante provisional (NO se lee de BD).
    tramo_comision_pct = TRAMO_COMISION_PROVISIONAL

    # --- Variaciones MoM (slide 2) ---
    var_reservas_mom = _variacion(com_actual.señales_total, com_prev.señales_total)
    delta_ops_reservas = com_actual.señales_n_ops - com_prev.señales_n_ops

    var_contratos_mom = _variacion(com_actual.arras_total, com_prev.arras_total)
    delta_ops_contratos = com_actual.arras_n_ops - com_prev.arras_n_ops

    var_ingresos_mom = _variacion(
        cont_actual.ingresos_contables,
        cont_prev.ingresos_contables if cont_prev else None,
    )

    # Slide 2 tarjeta 4: rentabilidad OPERATIVA (excluye gastos extra).
    # Patrón Valencia, NO Alicante. Decisión 2026-05-26.
    var_rentab_mom = _variacion_tasa(
        cont_actual.rentabilidad_operativa_pct,
        cont_prev.rentabilidad_operativa_pct if cont_prev else None,
    )

    señales_mes_anterior = com_prev.señales_total
    arras_mes_anterior = com_prev.arras_total

    # --- Slide 3: ticket medio ---
    ticket_medio = None
    if com_actual.arras_n_ops > 0 and com_actual.arras_total is not None:
        ticket_medio = com_actual.arras_total / com_actual.arras_n_ops
    ticket_medio_prev = None
    if com_prev.arras_n_ops > 0 and com_prev.arras_total is not None:
        ticket_medio_prev = com_prev.arras_total / com_prev.arras_n_ops
    var_ticket_medio_mom = _variacion(ticket_medio, ticket_medio_prev)

    # --- Slide 3: gráfico 2 periodos (sin YoY) ---
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

    # --- Slide 4: Pipeline pendiente de firma ---
    # Castellón NO tiene obra nueva ni alquileres (decisión estructural).
    # _query_pipeline_ventas sin inmuebles_excluir_ilike (default = tupla vacía).
    pipeline_ventas_rows = _query_pipeline_ventas(SEDE)
    ventas_pendientes = [
        {"nombre": r["inmueble"], "importe": format_euro(r["honorarios"])}
        for r in pipeline_ventas_rows
    ]
    total_ventas_pipeline = sum((r["honorarios"] or 0) for r in pipeline_ventas_rows)

    # Pipeline alquileres: la query es la estándar. Castellón NO tiene
    # alquileres en BD, así que la lista sale vacía y total = 0.
    pipeline_alq_rows = _query_pipeline_alquileres(SEDE)
    pipeline_alquiler = [
        {
            "nombre": f"▌ {_limpia_inmueble_alq(r['inmueble'])}",
            "importe": format_euro(r["honorarios"]),
        }
        for r in pipeline_alq_rows
    ]
    total_pipeline_alquiler = sum((r["honorarios"] or 0) for r in pipeline_alq_rows)

    total_pipeline = total_ventas_pipeline + total_pipeline_alquiler
    n_ops_pipeline = len(pipeline_ventas_rows) + len(pipeline_alq_rows)

    # Mensaje informativo cuando AMBAS columnas (ventas y alquileres) del
    # pipeline están vacías. Decisión 2026-05-26: evita que el slide 4 quede
    # mudo sin contexto cuando un mes cierra sin operaciones pendientes.
    # Si hay al menos una operación en cualquiera de las dos listas, el
    # mensaje sale vacío y el cuadro de texto de la plantilla no muestra
    # nada (queda como espacio neutro).
    if not ventas_pendientes and not pipeline_alquiler:
        mensaje_pipeline_vacio = "Sin operaciones pendientes de firma este mes"
    else:
        mensaje_pipeline_vacio = ""

    # --- Slide 5: Cobros pendientes de liquidación ---
    # Estado vivo: pte_facturar > 1 en pago_agentes filtrado por sede.
    cobros_pendientes_rows = _query_cobros_pendientes(SEDE)
    cobros_pendientes = [
        {"nombre": r["inmueble"], "importe": format_euro(r["importe"])}
        for r in cobros_pendientes_rows
    ]
    total_pendiente_cobro_num = sum(
        (Decimal(str(r["importe"])) if r["importe"] else Decimal(0))
        for r in cobros_pendientes_rows
    )

    # --- Slide 6: Break Even y objetivos de facturación ---
    # Misma estrategia que Alicante: dos bases distintas conviviendo.
    #   - base_be (arras firmadas): estados de la tabla derecha (✓ SUPERADO /
    #     FALTAN). La caja del marcador en la plantilla muestra
    #     {{contratos_firmados}} = arras_total, por lo que los estados deben
    #     compararse contra esa misma base para coherencia visual.
    #   - ingresos_be (ingresos_contables): margen de seguridad y narrativa
    #     (la narrativa habla de "facturación cobrada", concepto de ingresos).
    base_be = com_actual.arras_total
    ingresos_be = cont_actual.ingresos_contables
    break_even_mes = _query_break_even(SEDE, escenario, anyo, mes)
    if break_even_mes is not None:
        be_break_even = break_even_mes.break_even
        be_m10 = break_even_mes.ingresos_margen_10
        be_m20 = break_even_mes.ingresos_margen_20
        be_m30 = break_even_mes.ingresos_margen_30
        be_m40 = break_even_mes.ingresos_margen_40
    else:
        be_break_even = be_m10 = be_m20 = be_m30 = be_m40 = None

    def _estado_umbral(umbral: Decimal | None) -> str:
        if umbral is None or base_be is None:
            return ""
        if base_be >= umbral:
            return "✓ SUPERADO"
        return f"FALTAN: {format_euro(umbral - base_be)}"

    margen_seguridad = None
    if ingresos_be is not None and be_break_even is not None:
        margen_seguridad = ingresos_be - be_break_even

    narrativa_break_even = _narrativa_break_even(
        ingresos_be, be_break_even, margen_seguridad,
    )

    # --- Slide 7: Comisiones de directores ---
    # Parte A: FIRMADO Y COBRADO EN <mes>. Castellón sin alquileres → 0.
    arras_cobradas = _query_arras_cobradas_mes(SEDE, anyo, mes)
    alq_cobrados = _query_alquileres_cobrados_mes(SEDE, anyo, mes)
    ventas_cobradas = arras_cobradas if arras_cobradas is not None else Decimal(0)
    alquileres_cobrados = alq_cobrados if alq_cobrados is not None else Decimal(0)
    comision_ventas_mes = ventas_cobradas * tramo_comision_pct
    comision_alquileres_mes = alquileres_cobrados * tramo_comision_pct
    subtotal_comision_mes = comision_ventas_mes + comision_alquileres_mes

    # Parte C: COBRADO DE MESES ANTERIORES. Castellón aún no tiene filas en
    # comisiones_atrasos_directores → lista vacía, subtotal 0.
    comisiones_atrasos_rows = _query_comisiones_atrasos(SEDE)
    comisiones_atrasos = [
        {
            "nombre": f"{r['inmueble']}:",
            "mes": f"(en {r['mes_origen']},",
            "tramo": f"al {int(r['porcentaje'] * 100)}%)" if r["porcentaje"] is not None else "",
            "importe": format_euro(r["importe"]),
        }
        for r in comisiones_atrasos_rows
    ]
    subtotal_comision_atrasos = sum(
        (Decimal(str(r["importe"])) if r["importe"] else Decimal(0))
        for r in comisiones_atrasos_rows
    )

    # Parte B: cálculo final. N_DIRECTORES=1 → no se divide.
    total_comision_repartir = subtotal_comision_mes + subtotal_comision_atrasos
    comision_variable_por_director = total_comision_repartir / N_DIRECTORES
    total_por_director = comision_variable_por_director + SUELDO_FIJO_DIRECTOR

    # --- Slide 8: Estimación Break Even mes siguiente (proyección) ---
    # Si la fila contable del mes siguiente NO existe o tiene los umbrales
    # NULL (caso típico al iterar antes de cerrar el mes), los tokens salen
    # vacíos. Decisión 2026-05-26: NO bloquear con ValueError; el slide queda
    # parcial (solo el marcador con la constante objetivo) y el resto en
    # blanco hasta que contabilidad cargue junio. Comentario explícito porque
    # el spec original decía lo contrario y este cambio se acordó al iterar.
    break_even_proy = _query_break_even(SEDE, escenario, anyo_next, mes_next)

    # --- Color overrides ---
    color_overrides: dict[str, str] = {}
    # Slide 2: variaciones MoM.
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom"] = "verde" if var_reservas_mom >= 0 else "rojo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom"] = "verde" if var_contratos_mom >= 0 else "rojo"
    if var_ingresos_mom is not None:
        color_overrides["var_ingresos_mom"] = "verde" if var_ingresos_mom >= 0 else "rojo"
    if var_rentab_mom is not None:
        color_overrides["var_rentab_mom"] = "verde" if var_rentab_mom >= 0 else "rojo"
    # Slide 3: arrows.
    if var_reservas_mom is not None:
        color_overrides["var_reservas_mom_arrow"] = "verde" if var_reservas_mom >= 0 else "rojo"
    if var_contratos_mom is not None:
        color_overrides["var_contratos_mom_arrow"] = "verde" if var_contratos_mom >= 0 else "rojo"
    if var_ticket_medio_mom is not None:
        color_overrides["var_ticket_medio_mom"] = "verde" if var_ticket_medio_mom >= 0 else "rojo"
    # Slide 6: margen de seguridad (verde si cubierto, rojo si déficit).
    if margen_seguridad is not None:
        color_overrides["margen_seguridad"] = "verde" if margen_seguridad >= 0 else "rojo"
    # Slide 6: estados de los 5 umbrales. Compara contra base_be (arras),
    # MISMA base que el texto del estado (ver _estado_umbral). Mismo patrón
    # que Alicante.
    for _tok, _umbral in (
        ("break_even_estado", be_break_even),
        ("margen_10_estado", be_m10),
        ("margen_20_estado", be_m20),
        ("margen_30_estado", be_m30),
        ("margen_40_estado", be_m40),
    ):
        if base_be is not None and _umbral is not None:
            color_overrides[_tok] = "verde" if base_be >= _umbral else "rojo"

    # --- Color overrides slide 9 (semáforo) ---
    # Los tokens *_observacion (amarillo) tienen el MISMO valor visible que
    # sus equivalentes del slide 2. apply_color_overrides busca por VALOR de
    # texto, así que pintaría todas las cajas que contengan ese valor.
    # Añadimos zero-width space (U+200B) al final del valor para que el
    # match sea único de cada caja. Mismo truco que Valencia y Alicante (ver
    # feedback_color_caja_unica en memoria).
    # Decisión 2026-05-26: aplicar amarillo SIEMPRE (incluso cuando la
    # variación es None y la caja muestra "—"), para mantener la columna
    # OBSERVACIÓN como bloque visual unificado.
    color_overrides["var_reservas_mom_observacion"] = "amarillo"
    color_overrides["var_contratos_mom_observacion"] = "amarillo"
    # Caja RIESGO del slide 9 (`{{total_pendiente_cobro}}`): color rojo FIJO
    # en plantilla, sin override de código. Decisión 2026-05-26: la plantilla
    # de Castellón usa el mismo token sin sufijo en slides 5, 9 y 10; aplicar
    # override por valor pintaría las tres cajas. Diseño se encarga del rojo
    # estático en la caja del slide 9.

    payload: dict[str, Any] = {
        # Claves especiales (no son tokens, las consume generator.py).
        "_color_overrides": color_overrides,
        "_chart_reservas_arras": chart_periodos,

        # --- Slide 6: marcador móvil sobre la barra BE actual ---
        # Reutiliza el patrón de Alicante slide 6 (clave
        # `_break_even_position_slide_6_alc` en generator.py, apunta a
        # slide_index=5 vía CONFIG_SLIDE_6_ALICANTE). El marcador es
        # `{{contratos_firmados}}` (arras firmadas del mes) y se posiciona
        # según donde cae respecto a los umbrales del mes actual.
        # MISMA base que los estados de la tabla (base_be = arras_total):
        # coherencia visual entre el marcador y los estados ✓ SUPERADO/FALTAN.
        "_break_even_position_slide_6_alc": {
            "contratos_firmados": com_actual.arras_total,
            "break_even": be_break_even,
            "margen_10": be_m10,
            "margen_20": be_m20,
            "margen_30": be_m30,
        },

        # --- Slide 8: marcador móvil sobre la barra BE proyectado ---
        # Reutiliza el patrón de Alicante slide 8 (clave
        # `_break_even_position_slide_8_alc` en generator.py, apunta a
        # slide_index=7 vía CONFIG_SLIDE_8_ALICANTE). El marcador es
        # `{{facturacion_objetivo_proy}}` y se posiciona según donde cae la
        # constante FACTURACION_OBJETIVO_PROY_PROVISIONAL respecto a los
        # umbrales reales del mes siguiente.
        # Si junio aún no está cargado (break_even_proy es None o tiene
        # umbrales None), `_apply_marker_position` registra WARNING y deja
        # el marcador en la posición de plantilla — comportamiento esperado.
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

        # --- Identidad / tiempo ---
        "sede": SEDE_DISPLAY,
        "sede_upper": SEDE_DISPLAY.upper(),
        "mes_año": format_mes_anyo(anyo, mes),
        "mes_año_upper": format_mes_anyo_upper(anyo, mes),
        "mes_año_upper_short": format_mes_year3_upper(anyo, mes),
        "mes_capitalizado": format_mes_capitalizado(mes),
        "mes_informe_upper": format_mes_upper(mes),
        "mes_anterior_capitalizado": format_mes_capitalizado(mes_prev),
        "mes_anterior_short": format_mes_short_anyo(anyo_prev, mes_prev),
        "mes_anterior_upper": format_mes_year3_upper(anyo_prev, mes_prev),
        "mes_siguiente_capitalizado": format_mes_capitalizado(mes_next),
        "mes_siguiente_upper": format_mes_anyo_upper(anyo_next, mes_next),
        "mes_siguiente_upper_solo": format_mes_upper(mes_next),
        "trimestre": format_trimestre(mes),
        "tramo_comision": format_pct(tramo_comision_pct, decimales=0),

        # --- Slide 1: Portada ---
        "reservas_totales": format_euro(com_actual.señales_total),
        "contratos_firmados": format_euro(com_actual.arras_total),
        "ingresos_totales": format_euro(cont_actual.ingresos_contables),

        # --- Slide 2: tarjeta Reservas ---
        "var_reservas_mom": format_pct_signed_compacto(var_reservas_mom),
        "n_ops_reservas": format_int(com_actual.señales_n_ops),
        "delta_ops_reservas": format_int_signed(delta_ops_reservas, suffix="ops"),
        "reservas_mes_anterior": format_euro(señales_mes_anterior),

        # --- Slide 2: tarjeta Contratos firmados ---
        "var_contratos_mom": format_pct_signed_compacto(var_contratos_mom),
        "n_ops_contratos": format_int(com_actual.arras_n_ops),
        "delta_ops_contratos": format_int_signed(delta_ops_contratos, suffix="ops"),
        "contratos_mes_anterior": format_euro(arras_mes_anterior),

        # --- Slide 2: tarjeta Ingresos ---
        "var_ingresos_mom": format_pct_signed_compacto(var_ingresos_mom),
        "ingresos_mes_anterior": format_euro(cont_prev.ingresos_contables if cont_prev else None),
        "margen_bruto": format_pct(cont_actual.rentabilidad_bruta_pct, decimales=2),

        # --- Slide 2: tarjeta Rentabilidad OPERATIVA ---
        "rentabilidad_op": format_pct(cont_actual.rentabilidad_operativa_pct, decimales=2),
        "var_rentab_mom": format_pct_signed_compacto(var_rentab_mom),
        "resultado_op": format_euro(cont_actual.ebitda_no_extras),
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
        "var_ticket_medio_mom": format_pct_signed_compacto(var_ticket_medio_mom),

        # --- Slide 4: Pipeline pendiente de firma ---
        # Listas que generator.expand_lists transformará en slots numerados.
        "ventas_pendientes": ventas_pendientes,
        "pipeline_alquiler": pipeline_alquiler,
        "total_ventas_pipeline": format_euro(total_ventas_pipeline),
        "total_pipeline_alquiler": format_euro(total_pipeline_alquiler),
        "total_pipeline": format_euro(total_pipeline),
        "n_ops_pipeline": format_int(n_ops_pipeline),
        # Mensaje informativo cuando ambas columnas están vacías.
        "mensaje_pipeline_vacio": mensaje_pipeline_vacio,

        # --- Slide 5: Cobros pendientes de liquidación ---
        "cobros_pendientes": cobros_pendientes,
        # Tarjeta izquierda: total grande sin el símbolo € (la plantilla
        # tiene el € separado como texto fijo).
        "total_pendiente_cobro_sin_euro": format_numero(total_pendiente_cobro_num),
        # Misma cifra con € para reuso en slide 10 (Próximos pasos).
        "total_pendiente_cobro": format_euro(total_pendiente_cobro_num),
        # Nota opcional vacía hoy (patrón Alicante).
        "nota_cobros": "",

        # --- Slide 6: Break Even y objetivos de facturación ---
        "break_even": format_euro(be_break_even),
        "margen_10_objetivo": format_euro(be_m10),
        "margen_20_objetivo": format_euro(be_m20),
        "margen_30_objetivo": format_euro(be_m30),
        "margen_40_objetivo": format_euro(be_m40),
        "break_even_estado": _estado_umbral(be_break_even),
        "margen_10_estado": _estado_umbral(be_m10),
        "margen_20_estado": _estado_umbral(be_m20),
        "margen_30_estado": _estado_umbral(be_m30),
        "margen_40_estado": _estado_umbral(be_m40),
        "margen_seguridad": format_euro(margen_seguridad),
        "narrativa_break_even": narrativa_break_even,

        # --- Slide 7: Comisiones de directores ---
        # Parte A (FIRMADO Y COBRADO EN <mes>). Decimales 2 para precisión.
        "ventas_cobradas_mes": format_euro(ventas_cobradas, decimales=2),
        "comision_ventas_mes": format_euro(comision_ventas_mes, decimales=2),
        "alquileres_cobrados_mes": format_euro(alquileres_cobrados, decimales=2),
        "subtotal_comision_mes": format_euro(subtotal_comision_mes, decimales=2),
        # Parte C (COBRADO DE MESES ANTERIORES).
        "comisiones_atrasos": comisiones_atrasos,
        "subtotal_comision_atrasos": format_euro(subtotal_comision_atrasos, decimales=2),
        # Parte B (cálculo final). N_DIRECTORES=1.
        "total_comision_repartir": format_euro(total_comision_repartir, decimales=2),
        "comision_variable_por_director": format_euro(comision_variable_por_director, decimales=2),
        "sueldo_fijo_director": format_euro(SUELDO_FIJO_DIRECTOR, decimales=2),
        "total_por_director": format_euro(total_por_director, decimales=2),

        # --- Slide 8: Estimación Break Even mes siguiente ---
        # Los 4 umbrales vienen de contabilidad_mensual del mes siguiente.
        # Si junio aún no está cargado en BD, salen como "" (format_euro(None)).
        # facturacion_objetivo_proy = constante manual (160.000 €), no derivada
        # de BD. Decisión 2026-05-26 (igual que Alicante).
        "facturacion_objetivo_proy": format_euro(FACTURACION_OBJETIVO_PROY_PROVISIONAL),
        "break_even_proy": format_euro(
            break_even_proy.break_even if break_even_proy else None),
        "margen_10_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_10 if break_even_proy else None),
        "margen_20_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_20 if break_even_proy else None),
        "margen_30_objetivo_proy": format_euro(
            break_even_proy.ingresos_margen_30 if break_even_proy else None),

        # --- Slide 9: Semáforo estratégico ---
        # Tokens reutilizados (mismo valor que slide 2 / slide 5) con
        # zero-width space al final para que cada caja sea localizable
        # individualmente por apply_color_overrides. Patrón idéntico a
        # Alicante. Los color overrides ya se definieron arriba.
        # Tokens de FORTALEZAS (rentabilidad_op, ticket_medio,
        # var_ticket_medio_mom) ya están emitidos arriba para slides 2 y 3;
        # se reutilizan tal cual (verde fijo en plantilla, sin override).
        # Castellón-específico: si la variación MoM es None (caso típico
        # cuando el mes anterior fue 0), mostramos "—" en el semáforo para
        # que la caja no quede visualmente vacía. Decisión 2026-05-26.
        "var_reservas_mom_observacion": (
            format_pct_signed_compacto(var_reservas_mom) or "—"
        ) + "​",
        "var_contratos_mom_observacion": (
            format_pct_signed_compacto(var_contratos_mom) or "—"
        ) + "​",
        # NO emitimos total_pendiente_cobro_riesgo (la plantilla de Castellón
        # usa `{{total_pendiente_cobro}}` ya emitido arriba para el slide 9;
        # color rojo es fijo en plantilla).

        # --- Slide 10: Próximos pasos (hoja de ruta) ---
        # Cuadrícula 2x2. Tokens reutilizados de otros slides
        # (total_pendiente_cobro, total_pipeline, n_ops_pipeline,
        # objetivo_rentabilidad, mes_siguiente_upper, mes_capitalizado,
        # trimestre) ya están emitidos arriba. Solo añadimos los propios
        # del slide 10.
        # Tarjeta blindaje: Castellón NO tiene operaciones condicionadas
        # (decisión estructural). Emitimos 0 directamente.
        "volumen_riesgo": "0 €",
        "n_ops_condicionadas": "0",
    }

    # Listas que aún no se usan (slides ya cubiertos no las necesitan; las
    # claves siguen aquí porque LIST_SPECS de generator.py las expande).
    payload["operaciones_condicionadas"] = []
    payload["obras_nuevas"] = []

    return payload
