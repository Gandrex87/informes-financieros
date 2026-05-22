"""
Base común del calculator — sede-agnóstico.

Contiene lo que comparten TODAS las sedes (Valencia y Alicante):
- Dataclasses de filas de BD.
- Helpers puros (aritmética de fechas, variaciones, clasificación).
- Queries genéricas a Postgres que reciben `sede` como parametro y filtran
  con `WHERE sede = %(sede)s`. `SEDES_VALIDAS` valida el parametro pronto.

NO contiene el ensamblaje del payload (eso es específico de cada sede:
calculator.py / calculator_valencia.py, calculator_alicante.py) ni
constantes de negocio de una sede (nº directores, sueldo fijo, etc.).

Estado multi-sede (2026-05-22): todas las tablas usadas por las queries de
este modulo tienen columna `sede` y viven en `informes_financieros` salvo
`ventas_comerciales` (en `finanzas_automation`). Ver docs/MIGRACION_MULTISEDE.md.
"""
import logging
import os
from dataclasses import dataclass
from decimal import Decimal

from app.db import connection

logger = logging.getLogger(__name__)

# Sedes validas. Las queries con filtro por sede validan contra este set para
# fallar pronto ante una sede desconocida (evita queries sin resultados
# silenciosas si llega un parametro mal escrito).
SEDES_VALIDAS = {"Valencia", "Alicante"}


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
    """Snapshot contable de un mes desde contabilidad_mensual.

    Sobre ebitda/rentabilidad: la tabla tiene dos variantes.
    - `_no_extras` / `_operativa_pct`: excluye gastos_extra (ingresos puros
      de la operativa). Usado por Valencia en el slide 2 tarjeta 4.
    - `_real` / `_real_pct`: incluye gastos_extra (resultado neto real).
      Usado por Alicante en el slide 2 tarjeta 4 ("RENTABILIDAD REAL").
    Ambas se exponen aqui; cada calculator decide cual mostrar.
    """
    pagas_señales: Decimal | None
    arras_firmadas: Decimal | None
    ingresos_contables: Decimal | None
    honorarios_intermediacion: Decimal | None
    resto_ingresos: Decimal | None
    margen_bruto: Decimal | None
    rentabilidad_bruta_pct: Decimal | None
    ebitda_no_extras: Decimal | None
    rentabilidad_operativa_pct: Decimal | None
    ebitda_real: Decimal | None
    rentabilidad_real_pct: Decimal | None


@dataclass
class ContratosResumenMes:
    """Contratos firmados de un mes desde las tablas resumen mensual.

    Suma ventas (resumen_mensual_arras) + alquileres
    (resumen_mensual_alquileres) para un (anio, mes). Es la fuente del
    token contratos_firmados (slide 1 y 2) y derivados.
    """
    honorarios: Decimal | None
    num_operaciones: int


@dataclass
class BreakEvenMes:
    """Umbrales de break even y objetivos de margen (slide 8).

    Desde contabilidad_mensual. Variante SIN extras (break_even,
    ingresos_margen_N); las columnas *_con_extras no se usan en el slide 8.
    """
    break_even: Decimal | None
    ingresos_margen_10: Decimal | None
    ingresos_margen_20: Decimal | None
    ingresos_margen_30: Decimal | None
    ingresos_margen_40: Decimal | None


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


def _variacion_tasa(actual: Decimal | None, anterior: Decimal | None) -> Decimal | None:
    """Variacion porcentual entre dos TASAS (no importes), tolerando
    denominador negativo.

    Cuando se compara una tasa (rentabilidad, margen, etc.) y el mes anterior
    fue negativo, la formula clasica (actual - anterior) / anterior invierte
    el signo del resultado: una mejora (de -27% a +32%) sale como -216%,
    comunicando lo contrario de la realidad.

    Heuristica acordada (decision usuario 2026-05-21): cuando anterior < 0,
    devolver abs(ratio) para que el signo refleje la direccion del cambio
    (mejora = positivo, empeoramiento = negativo). Equivalente a calcular el
    ratio contra |anterior|.

    NO usar para comparar importes monetarios: ahi se usa _variacion clasica.
    Esta funcion es especifica de comparaciones de tasas con posible
    denominador negativo.
    """
    if actual is None or anterior is None or anterior == 0:
        return None
    ratio = (actual - anterior) / anterior
    if anterior < 0:
        # Reflejar la direccion real del cambio: si actual > anterior es mejora.
        return abs(ratio) if actual > anterior else -abs(ratio)
    return ratio


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
# Tabla ventas_comerciales unificada con columna sede (ver
# docs/MIGRACION_MULTISEDE.md). Cada query filtra por sede.

def _query_comercial(sede: str, anyo: int, mes: int) -> ComercialMes:
    """Lee de ventas_comerciales el resumen comercial de un mes para una sede.

    Incluye VENTAS + ALQUILERES (la slide 1 dice "VENTAS Y ALQUILER").
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
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
        FROM {schema}.ventas_comerciales
        WHERE sede = %(sede)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"sede": sede, "anyo": anyo, "mes": mes})
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
               ebitda_no_extras, rentabilidad_operativa_pct,
               ebitda_real, rentabilidad_real_pct
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
        ebitda_real=row["ebitda_real"],
        rentabilidad_real_pct=row["rentabilidad_real_pct"],
    )


def _query_break_even(sede: str, escenario: str, anyo: int, mes: int) -> BreakEvenMes | None:
    """Lee los umbrales de break even de un mes (slide 8).

    Variante SIN extras (decision de contabilidad). Devuelve None si no hay
    fila contable para ese (sede, escenario, anyo, mes).
    """
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    sql = f"""
        SELECT break_even,
               ingresos_margen_10, ingresos_margen_20,
               ingresos_margen_30, ingresos_margen_40
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
    return BreakEvenMes(
        break_even=row["break_even"],
        ingresos_margen_10=row["ingresos_margen_10"],
        ingresos_margen_20=row["ingresos_margen_20"],
        ingresos_margen_30=row["ingresos_margen_30"],
        ingresos_margen_40=row["ingresos_margen_40"],
    )


def _query_arras_cobradas_mes(sede: str, anyo: int, mes: int) -> Decimal | None:
    """Lee resumen_mensual_arras__sin_condicion.cobradas para una sede y mes.

    Es la base de calculo de la comision de ventas del slide 9. Filtro
    por (sede, anio, mes string 3 letras, ej. 'abr').

    Cambio 2026-05-22: tabla movida a schema informes_financieros y añadida
    columna sede.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    mes_label = _MES_LABEL_3[mes]
    sql = f"""
        SELECT cobradas
        FROM {schema}.resumen_mensual_arras__sin_condicion
        WHERE sede = %(sede)s
          AND anio = %(anyo)s
          AND mes = %(mes_label)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"sede": sede, "anyo": anyo, "mes_label": mes_label})
        row = cur.fetchone()
    return row["cobradas"] if row else None


def _query_alquileres_cobrados_mes(sede: str, anyo: int, mes: int) -> Decimal | None:
    """Lee resumen_mensual_alquileres.honorarios_cobrados para una sede y mes.

    Base de calculo de la comision de alquileres del slide 9.
    OJO: esta tabla usa 'sept' (4 letras) para septiembre, distinto a
    resumen_mensual_arras__sin_condicion que usa 'sep'. Para mes != 9
    el label de 3 letras funciona en ambas.

    Cambio 2026-05-22: tabla movida a schema informes_financieros y añadida
    columna sede.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    mes_label = "sept" if mes == 9 else _MES_LABEL_3[mes]
    sql = f"""
        SELECT honorarios_cobrados
        FROM {schema}.resumen_mensual_alquileres
        WHERE sede = %(sede)s
          AND anio = %(anyo)s
          AND mes = %(mes_label)s;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"sede": sede, "anyo": anyo, "mes_label": mes_label})
        row = cur.fetchone()
    return row["honorarios_cobrados"] if row else None


def _query_contratos_resumen(sede: str, anyo: int, mes: int) -> ContratosResumenMes:
    """Contratos firmados de una sede y mes = ventas + alquileres.

    Suma:
    - resumen_mensual_arras.honorarios + num_operaciones (ventas)
    - resumen_mensual_alquileres.honorarios_cobrados + num_operaciones (alq.)

    Fuente del token contratos_firmados (slide 1 y 2) y derivados
    (var MoM/YoY, ticket medio, gráfico slide 3). Filtro (sede, anio, mes
    string 3 letras). resumen_mensual_arras tiene 2025 y 2026.

    OJO septiembre: resumen_mensual_alquileres usa 'sept' (4 letras),
    resumen_mensual_arras usa 'sep' (3 letras). Se resuelve por tabla.

    Cambio 2026-05-22: ambas tablas en informes_financieros con columna
    sede. Filtro homogeneo.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    label_3 = _MES_LABEL_3[mes]
    label_alq = "sept" if mes == 9 else label_3
    with connection() as conn:
        ar = conn.execute(
            f"""
            SELECT honorarios, num_operaciones
            FROM {schema}.resumen_mensual_arras
            WHERE sede = %(sede)s
              AND anio = %(anyo)s
              AND mes = %(mes_label)s;
            """,
            {"sede": sede, "anyo": anyo, "mes_label": label_3},
        ).fetchone()
        al = conn.execute(
            f"""
            SELECT honorarios_cobrados, num_operaciones
            FROM {schema}.resumen_mensual_alquileres
            WHERE sede = %(sede)s
              AND anio = %(anyo)s
              AND mes = %(mes_label)s;
            """,
            {"sede": sede, "anyo": anyo, "mes_label": label_alq},
        ).fetchone()

    ar_hon = ar["honorarios"] if ar and ar["honorarios"] is not None else None
    al_hon = al["honorarios_cobrados"] if al and al["honorarios_cobrados"] is not None else None
    if ar_hon is None and al_hon is None:
        honorarios = None
    else:
        honorarios = (ar_hon or Decimal(0)) + (al_hon or Decimal(0))

    n_ops = (
        (ar["num_operaciones"] if ar and ar["num_operaciones"] else 0)
        + (al["num_operaciones"] if al and al["num_operaciones"] else 0)
    )
    return ContratosResumenMes(honorarios=honorarios, num_operaciones=n_ops)


def _query_alquiler_senales_resumen(sede: str, anyo: int, mes: int) -> ContratosResumenMes:
    """Señales de alquiler de una sede y mes desde resumen_mensual_alquiler_senales.

    Fuente de la tarjeta Reservas/Señales del slide 4 (reservas_alquiler
    y derivados: var MoM, n_ops, delta). Filtro (sede, anio, mes string 3
    letras). OJO septiembre: esta tabla usa 'sept' (4 letras).

    Cambio 2026-05-22: tabla movida a schema informes_financieros y añadida
    columna sede.

    Reutiliza ContratosResumenMes (honorarios + num_operaciones).
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    mes_label = "sept" if mes == 9 else _MES_LABEL_3[mes]
    sql = f"""
        SELECT honorarios_cobrados, num_operaciones
        FROM {schema}.resumen_mensual_alquiler_senales
        WHERE sede = %(sede)s
          AND anio = %(anyo)s
          AND mes = %(mes_label)s;
    """
    with connection() as conn:
        row = conn.execute(sql, {"sede": sede, "anyo": anyo, "mes_label": mes_label}).fetchone()
    if not row:
        return ContratosResumenMes(honorarios=None, num_operaciones=0)
    return ContratosResumenMes(
        honorarios=row["honorarios_cobrados"],
        num_operaciones=row["num_operaciones"] or 0,
    )


def _query_tramo_comision(sede: str, anyo: int, mes: int) -> Decimal | None:
    """Tramo de comision del mes y sede = SUMA de porcentajes de los directores.

    Fuente: informes_financieros.pagos_directores (una fila por director,
    mes y sede). El tramo es la suma de la columna `porcentaje` de las
    filas de ese (sede, anio, mes). Ejemplos abril 2026:
    - Valencia: ALEX 0.0150 + FADIA 0.0150 = 0.0300 (3%)
    - Alicante: PELAYO 0.0400              = 0.0400 (4%)

    Funciona con N directores variable (no hay que tocar constantes si
    entra/sale un director: se refleja en las filas de la tabla).
    Filtro mes = string 3 letras. Devuelve None si no hay filas para la
    sede en ese mes.

    Cambio 2026-05-21: la tabla se movio de finanzas_automation a
    informes_financieros y gano columna `sede`.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    mes_label = _MES_LABEL_3[mes]
    sql = f"""
        SELECT SUM(porcentaje) AS tramo, COUNT(*) AS n_dir
        FROM {schema}.pagos_directores
        WHERE sede = %(sede)s
          AND anio = %(anyo)s
          AND mes = %(mes_label)s;
    """
    with connection() as conn:
        row = conn.execute(
            sql,
            {"sede": sede, "anyo": anyo, "mes_label": mes_label},
        ).fetchone()
    if not row or row["n_dir"] == 0 or row["tramo"] is None:
        return None
    return row["tramo"]


def _query_pipeline_ventas(
    sede: str,
    inmuebles_excluir_ilike: tuple[str, ...] = (),
) -> list[dict]:
    """Lista de ventas pendientes de firma para una sede.

    Filtro:
    - sede = sede pedida.
    - Es venta (no alquiler): inmueble NOT LIKE 'ALQ.-%'.
    - Pendiente: arras_firmadas = 'NO'.
    - Excluye los inmuebles que matcheen alguno de los patrones en
      `inmuebles_excluir_ilike` (ej. promociones de obra nueva en Valencia,
      que tienen su seccion aparte). Patrones pasados como parametros
      bindeados (no f-string), seguro frente a SQL injection.

    DISTINCT ON defensivo por (inmueble, fecha_senal, honorarios_totales)
    para neutralizar duplicados puntuales detectados en P-19.

    Ordenado por honorarios descendente. Cada sede decide su lista de
    exclusiones en su calculator (default () = sin exclusiones, como
    Alicante que no tiene obra nueva).
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    # Construye las clausulas NOT ILIKE dinamicamente con parametros
    # bindeados, una por patron de exclusion.
    excl_sql = " ".join(
        f"AND inmueble NOT ILIKE %(excl_{i})s"
        for i in range(len(inmuebles_excluir_ilike))
    )
    sql = f"""
        SELECT DISTINCT ON (inmueble, fecha_senal, honorarios_totales)
            inmueble, honorarios_totales
        FROM {schema}.ventas_comerciales
        WHERE sede = %(sede)s
          AND inmueble NOT LIKE 'ALQ.-%%'
          AND arras_firmadas = 'NO'
          {excl_sql}
        ORDER BY inmueble, fecha_senal, honorarios_totales, honorarios_totales DESC NULLS LAST;
    """
    params: dict[str, object] = {"sede": sede}
    for i, patron in enumerate(inmuebles_excluir_ilike):
        params[f"excl_{i}"] = patron
    with connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    items = [{"inmueble": r["inmueble"], "honorarios": r["honorarios_totales"]} for r in rows]
    # DISTINCT ON requiere ORDER BY que empieza por las claves; reordenamos
    # despues por importe para presentacion.
    items.sort(key=lambda r: r["honorarios"] or 0, reverse=True)
    return items


def _query_pipeline_alquileres(sede: str) -> list[dict]:
    """Lista de alquileres con señal pero sin contrato firmado todavia.

    Excluimos:
    - Las firmadas ('SI').
    - Las caidas ('CAÍDA - 0', con tilde en la I).

    Sin filtro de mes: incluye señalizaciones de meses anteriores que aun
    no han firmado. Ordenado por honorarios descendente.

    Filtro semantico universal (LIKE 'ALQ.-%') por convencion de la
    ingesta. Funciona para cualquier sede que tenga alquileres; las que
    no los tengan recibiran lista vacia.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_VENTAS"]
    sql = f"""
        SELECT inmueble, honorarios_totales
        FROM {schema}.ventas_comerciales
        WHERE sede = %(sede)s
          AND inmueble LIKE 'ALQ.-%%'
          AND fecha_senal IS NOT NULL
          AND (arras_firmadas IS NULL OR arras_firmadas NOT IN ('SI', 'CAÍDA - 0'))
        ORDER BY honorarios_totales DESC NULLS LAST;
    """
    with connection() as conn:
        rows = conn.execute(sql, {"sede": sede}).fetchall()
    return [{"inmueble": r["inmueble"], "honorarios": r["honorarios_totales"]} for r in rows]


def _query_comisiones_atrasos(sede: str) -> list[dict]:
    """Lista de COBRADO DE MESES ANTERIORES (slide 9 Parte C).

    Fuente: informes_financieros.comisiones_atrasos_directores. Una fila
    por operacion de un mes anterior cobrada este mes, con su tramo
    historico (porcentaje aplicado) y el importe de comision resultante.

    Estado vivo (sin filtro de anyo/mes): la tabla refleja la foto actual
    de los atrasos pendientes. Cuando se liquidan, la ingesta los retira
    o se sobreescriben. Filtro por sede para no mezclar Valencia/Alicante.

    Resuelve P-23. Antes de tener esta tabla, subtotal_comision_atrasos era
    una constante provisional (1021.89) hardcoded del mock.

    Devuelve filas con keys: inmueble, mes_origen, porcentaje, importe.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    sql = f"""
        SELECT inmueble, mes_origen, porcentaje, importe_comision
        FROM {schema}.comisiones_atrasos_directores
        WHERE sede = %(sede)s
        ORDER BY importe_comision DESC NULLS LAST;
    """
    with connection() as conn:
        rows = conn.execute(sql, {"sede": sede}).fetchall()
    return [
        {
            "inmueble": r["inmueble"],
            "mes_origen": r["mes_origen"],
            "porcentaje": r["porcentaje"],
            "importe": r["importe_comision"],
        }
        for r in rows
    ]


def _query_cobros_pendientes(sede: str) -> list[dict]:
    """Cobros pendientes de liquidacion para una sede (slide 7).

    Fuente: informes_financieros.pago_agentes, columna pte_facturar (TEXT).
    pte_facturar puede ser: 'CAÍDA', '0', o un numero > 0 (lo pendiente).

    Filtro:
    - sede = sede pedida (columna añadida 2026-05-21).
    - Solo strings numericos puros (descarta 'CAÍDA').
    - Valor > 1 para descartar basura de coma flotante de la ingesta
      (ej. '0.21000000000003638' que es ruido, no un cobro real). Ver P-24.
    - fecha_arras_sin_condic IS NOT NULL: excluye operaciones que en el
      Sheet origen tienen "PONER FECHA" (placeholder de fecha pendiente).
      La ingesta castea esa columna a DATE, por lo que el texto no
      parseable se carga como NULL. Esas operaciones aun no estan listas
      para liquidar y no deben contar como cobro pendiente.

    Sin filtro de mes: es el estado vivo de cobros pendientes (dato de tipo
    "foto actual", ver seccion HIBRIDO en docs/MAPEO_DATOS.md).

    Ordenado por importe descendente.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    schema = os.environ["POSTGRES_SCHEMA_INFORMES"]
    sql = f"""
        SELECT inmueble, CAST(pte_facturar AS NUMERIC) AS importe
        FROM {schema}.pago_agentes
        WHERE sede = %(sede)s
          AND pte_facturar ~ '^[0-9]+\\.?[0-9]*$'
          AND CAST(pte_facturar AS NUMERIC) > 1
          AND fecha_arras_sin_condic IS NOT NULL
        ORDER BY importe DESC;
    """
    with connection() as conn:
        cur = conn.execute(sql, {"sede": sede})
        rows = cur.fetchall()
    return [{"inmueble": r["inmueble"], "importe": r["importe"]} for r in rows]
