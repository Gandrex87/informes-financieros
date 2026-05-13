-- Schema para los datos contables agregados por mes y sede.
-- Fuente: Sheet contable mensual que mantiene contabilidad a mano.
--
-- Una fila representa la "instantanea contable" de una sede en un mes
-- bajo un escenario concreto. Hoy solo usamos escenario='con_crm', pero
-- la columna esta preparada para futuros casos (solo_sede, con_consultoria, etc).

CREATE SCHEMA IF NOT EXISTS informes_financieros;

CREATE TABLE IF NOT EXISTS informes_financieros.contabilidad_mensual (
    -- Identificacion
    sede                            TEXT NOT NULL,           -- 'Valencia' | 'Alicante' | 'Castellon' (futuro)
    escenario                       TEXT NOT NULL,           -- 'solo' | 'con_crm' | otros futuros
    anyo                            INTEGER NOT NULL,
    mes                             INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),

    -- Resumen comercial (duplicados con ventas_comerciales, los guardamos
    -- como aparecen en el Sheet para auditoria / referencia).
    pagas_señales                   NUMERIC(14, 2),
    arras_firmadas                  NUMERIC(14, 2),

    -- Pipeline (estados a fecha de cierre del mes)
    pendientes_firma                NUMERIC(14, 2),
    ptes_facturar                   NUMERIC(14, 2),

    -- Ingresos
    ingresos_contables              NUMERIC(14, 2),
    honorarios_intermediacion       NUMERIC(14, 2),
    resto_ingresos                  NUMERIC(14, 2),

    -- Gastos (los importes vienen negativos en el Sheet; los guardamos asi)
    gastos_directos_asesores        NUMERIC(14, 2),
    gastos_operativos               NUMERIC(14, 2),
    gastos_fijos                    NUMERIC(14, 2),
    gastos_variables                NUMERIC(14, 2),
    gastos_programadores            NUMERIC(14, 2),  -- solo en escenario 'con_crm'
    gastos_extra                    NUMERIC(14, 2),
    gastos_extra_relac_actividad    NUMERIC(14, 2),
    gastos_extra_fuera_operativa    NUMERIC(14, 2),

    -- Resultados (margenes y rentabilidades)
    margen_bruto                    NUMERIC(14, 2),
    rentabilidad_bruta_pct          NUMERIC(7, 4),    -- decimal: 0.6116 = 61,16%
    ebitda_no_extras                NUMERIC(14, 2),
    rentabilidad_operativa_pct      NUMERIC(7, 4),
    ebitda_real                     NUMERIC(14, 2),
    rentabilidad_real_pct           NUMERIC(7, 4),

    -- Otros KPIs derivados
    pct_comision_asesores           NUMERIC(7, 4),

    -- Break Even (sin gastos extra)
    break_even                      NUMERIC(14, 2),
    ingresos_margen_10              NUMERIC(14, 2),
    ingresos_margen_20              NUMERIC(14, 2),
    ingresos_margen_30              NUMERIC(14, 2),
    ingresos_margen_40              NUMERIC(14, 2),

    -- Break Even (con gastos extra incluidos)
    break_even_con_extras           NUMERIC(14, 2),
    ingresos_margen_10_con_extras   NUMERIC(14, 2),
    ingresos_margen_20_con_extras   NUMERIC(14, 2),
    ingresos_margen_30_con_extras   NUMERIC(14, 2),
    ingresos_margen_40_con_extras   NUMERIC(14, 2),

    -- Metadata
    actualizado_at                  TIMESTAMP DEFAULT NOW(),

    PRIMARY KEY (sede, escenario, anyo, mes)
);

COMMENT ON TABLE informes_financieros.contabilidad_mensual IS
    'Snapshot mensual de los datos contables agregados por sede. '
    'Alimentado desde el Sheet contable manual de Lion. '
    'Una fila por combinacion (sede, escenario, anyo, mes).';

COMMENT ON COLUMN informes_financieros.contabilidad_mensual.escenario IS
    'Variante contable: "solo" (sede aislada) | "con_crm" (incluye gastos del CRM corporativo).';

COMMENT ON COLUMN informes_financieros.contabilidad_mensual.gastos_programadores IS
    'Coste del CRM corporativo asignado a la sede. Solo aplica en escenario "con_crm".';
