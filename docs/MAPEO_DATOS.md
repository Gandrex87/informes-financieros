# Mapeo de datos del informe

Para cada slide, qué tokens aparecen visualmente, de dónde sale cada dato, cómo
se calcula y su estado actual de integración con Postgres.

Este documento sirve a la vez como:
- Roadmap del proyecto (qué falta integrar).
- Referencia para validación con contabilidad ("¿de dónde sale tal cifra?").
- Trazabilidad histórica si cambian las fuentes.

## Convenciones

| Etiqueta | Significa |
|---|---|
| **VC** | tabla `finanzas_automation.ventas_comerciales` (datos crudos, una fila por operación) |
| **CM** | tabla `informes_financieros.contabilidad_mensual` (snapshot mensual del Sheet contable) |
| **constante** | valor hardcodeado en código (a mover a `parametros_sede_mes` cuando varíe por sede o mes) |
| **derivado** | calculado por Python a partir de otros datos |
| **manual** | aún no integrado; viene del cliente (n8n o JSON mock) |

**Estado:**
- ✅ Integrado y leyendo de Postgres.
- ⚠️ Integrado con discrepancia conocida (ver P-18 en PENDIENTES.md).
- ⏳ Pendiente de integrar (valor mock todavía).

---

## Slide 1 — Portada

KPIs principales y identificación del informe.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `sede` | parámetro de entrada | viene en el body de la API | ✅ |
| `sede_upper` | derivado | `sede.upper()` | ✅ |
| `mes_año` | parámetro de entrada | `Abril 2026` (en español) | ✅ |
| `mes_año_upper` | derivado | `mes_año.upper()` | ✅ |
| `reservas_totales` | VC | `SUM(honorarios_totales) WHERE fecha_senal en el mes` | ⚠️ ver P-18 |
| `contratos_firmados` | VC | `SUM(honorarios_totales) WHERE fecha_arras en el mes AND arras_firmadas='SI'` | ⚠️ ver P-18 |
| `ingresos_totales` | CM | `ingresos_contables` | ✅ |
| `tramo_comision` | constante | `"3 %"` (pendiente parametros_sede_mes) | ✅ |

---

## Slide 2 — Resumen ejecutivo

Cuatro tarjetas con los KPIs del mes y sus comparativas.

### Tarjeta · Reservas totales (ventas y alquiler)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_totales` | VC | (igual que slide 1) | ⚠️ |
| `var_reservas_mom` | derivado | `(reservas_actual - reservas_mes-1) / reservas_mes-1` | ⚠️ |
| `n_ops_reservas` | VC | `COUNT(*) WHERE fecha_senal en el mes` | ✅ |
| `delta_ops_reservas` | derivado | `n_ops_actual - n_ops_mes-1` (formato `±N ops`) | ✅ |
| `reservas_mes_anterior` | VC | mismo SUM que `reservas_totales` pero mes-1 | ⚠️ |
| `reservas_año_anterior` | CM | `pagas_señales` del año anterior, mismo mes | ⚠️ ver P-18 |

### Tarjeta · Contratos firmados (ventas y alquiler)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `contratos_firmados` | VC | (igual que slide 1) | ⚠️ |
| `var_contratos_mom` | derivado | `(contratos_actual - contratos_mes-1) / contratos_mes-1` | ⚠️ |
| `n_ops_contratos` | VC | `COUNT(*) WHERE fecha_arras en mes AND arras_firmadas='SI'` | ⚠️ |
| `delta_ops_contratos` | derivado | `n_ops_actual - n_ops_mes-1` (formato `±N ops`) | ✅ |
| `contratos_mes_anterior` | VC | mismo SUM que `contratos_firmados` pero mes-1 | ⚠️ |
| `contratos_año_anterior` | CM | `arras_firmadas` del año anterior, mismo mes | ⚠️ ver P-18 |

### Tarjeta · Ingresos totales

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ingresos_totales` | CM | `ingresos_contables` | ✅ |
| `var_ingresos_mom` | derivado | `(ingresos_actual - ingresos_mes-1) / ingresos_mes-1` | ✅ |
| `ingresos_ventas` | CM | `honorarios_intermediacion` | ✅ |
| `ingresos_alquiler` | CM | `resto_ingresos` (confirmado: lo que no es intermediación = alquileres) | ✅ |
| `ingresos_mes_anterior` | CM | `ingresos_contables` del mes-1 | ✅ |
| `margen_bruto` | CM | `rentabilidad_bruta_pct` formateado como `%` | ✅ |

### Tarjeta · Rentabilidad operativa

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `rentabilidad_op` | CM | `rentabilidad_operativa_pct` | ✅ |
| `var_rentab_mom` | derivado | `rentab_actual - rentab_mes-1` aplicado como variación porcentual | ✅ |
| `resultado_op` | CM | `ebitda_no_extras` | ✅ |
| `objetivo_rentabilidad` | constante | `"20 %"` (objetivo corporativo fijo) | ✅ |

### Colores condicionales del slide 2

| Token | Verde si | Rojo si |
|---|---|---|
| `var_reservas_mom` | ≥ 0 | < 0 |
| `var_contratos_mom` | ≥ 0 | < 0 |
| `var_ingresos_mom` | ≥ 0 | < 0 |
| `var_rentab_mom` | ≥ 0 | < 0 |

Lógica en `calculator.py`: el código mira el signo del valor numérico (no del string) y emite el color en `_color_overrides`. El servicio Slides solo aplica.

---

## Slide 3 — Producción comercial

Lado izquierdo: 4 tarjetas con KPIs comparativos. Lado derecho: gráfico (pendiente).

### Formatos de fecha específicos del slide 3

| Token | Cálculo |
|---|---|
| `mes_anterior_upper` | `MAR 2026` (formato 3 letras + año largo) |
| `mes_año_upper_short` | `ABR 2026` (idem para mes actual) |
| `mes_año_anterior_upper` | `ABRIL 2025` (formato largo + año anterior) |
| `mes_año_anterior_short_upper` | `ABR'25` (formato compacto YoY) |

### Tarjeta · Pagas y señales (ventas y alquiler)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_mes_anterior` | VC | (igual que slide 2) | ⚠️ |
| `n_ops_reservas_mes_anterior` | VC | `COUNT(*) WHERE fecha_senal en mes-1` | ✅ |
| `reservas_totales` | VC | (igual que slide 2) | ⚠️ |
| `n_ops_reservas` | VC | (igual que slide 2) | ✅ |
| `var_reservas_mom_arrow` | derivado | mismo cálculo que `var_reservas_mom` con prefijo `▲`/`▼` según signo | ✅ |
| `delta_ops_reservas_full` | derivado | `±N ops (±X %)` — diferencia absoluta y porcentual | ✅ |

### Tarjeta · Firma de arras y contratos

Mismo patrón que la tarjeta anterior, pero para `contratos_*` y filtrado por `fecha_arras` + `arras_firmadas='SI'`.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `contratos_mes_anterior` | VC | | ⚠️ |
| `n_ops_contratos_mes_anterior` | VC | | ⚠️ |
| `contratos_firmados` | VC | | ⚠️ |
| `n_ops_contratos` | VC | | ⚠️ |
| `var_contratos_mom_arrow` | derivado | `▲`/`▼` + porcentaje | ⚠️ |
| `delta_ops_contratos_full` | derivado | `±N ops (±X %)` | ⚠️ |

### Tarjeta · Comparativa interanual (vs ABRIL 2025)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_año_anterior` | CM | `pagas_señales` del año anterior | ⚠️ |
| `contratos_año_anterior` | CM | `arras_firmadas` del año anterior | ⚠️ |
| `var_reservas_yoy` | derivado | `(reservas_actual - reservas_año_anterior) / reservas_año_anterior` | ⚠️ |
| `var_contratos_yoy` | derivado | `(contratos_actual - contratos_año_anterior) / contratos_año_anterior` | ⚠️ |

### Tarjeta · Ticket medio por operación

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ticket_medio` | derivado | `contratos_firmados / n_ops_contratos` (importe medio por operación de arras) | ✅ |
| `ticket_medio_mes_anterior` | derivado | mismo cálculo aplicado al mes-1 | ✅ |
| `var_ticket_medio_mom` | derivado | `(ticket_medio - ticket_medio_mes-1) / ticket_medio_mes-1` | ✅ |

### Colores condicionales del slide 3

| Token | Verde si | Rojo si |
|---|---|---|
| `var_reservas_mom_arrow` | ≥ 0 | < 0 |
| `var_contratos_mom_arrow` | ≥ 0 | < 0 |
| `var_reservas_yoy` | ≥ 0 | < 0 |
| `var_contratos_yoy` | ≥ 0 | < 0 |
| `var_ticket_medio_mom` | ≥ 0 | < 0 |

### Lado derecho — Gráfico (pendiente)

Gráfico de barras: 3 períodos (Abr'25, Mar'26, Abr'26) × 2 series (Reservas, Contratos Firmados).

**Estado:** ⏳ pendiente. Ver P-05 en PENDIENTES.md. Camino acordado: generar PNG con matplotlib → subir a Drive → `insertImage` en placeholder del slide → borrar PNG.

---

## Slides 4-12 — Pendientes de integrar

Listado resumido. Cada uno tendrá su sección detallada cuando se ataque.

| Slide | Contenido | Fuentes esperadas | Notas |
|---|---|---|---|
| 4 | Gestión alquileres | VC filtrando `inmueble LIKE 'ALQ.-%%'` + lista pipeline | Patrón slots variables (`n_max=8`) ya en plantilla |
| 5 | Pipeline Q2 | VC con `estado='pendiente'` + 3 listas (ventas/alquiler/obra nueva) | 3 columnas variables |
| 6 | Operaciones condicionadas | VC `WHERE condicionadas='SI' AND fecha_no_condicionada IS NULL` | Tabla `n_max=12` |
| 7 | Cobros pendientes | tabla nueva (¿`cobros_pendientes`?) — fuente sin confirmar | Tabla 2 columnas, `n_max=20` |
| 8 | Break Even abril | CM (break_even, ingresos_margen_*, ebitda) + narrativa | Narrativa templating determinista (P-07) |
| 9 | Comisiones directores | VC (cobradas mes) + CM (% comisión) + tabla atrasos | Multi-fuente, tabla `n_max=10` |
| 10 | Break Even mayo (proyección) | CM mes+1 (proyectados) | Mismo patrón que slide 8 sin narrativa |
| 11 | Semáforo estratégico | reutiliza tokens de slides 2, 3, 6 | Mayoría heredada |
| 12 | Hoja de ruta | tokens derivados de slides 5, 6, 7 + constantes | Mayoría agregados |

---

## Tokens deprecados o sin uso actual

Tokens que el JSON mock todavía contiene pero que el calculator de hoy no produce. Quedarán cubiertos en próximas iteraciones:

- `mes_anterior_short`, `mes_año_anterior_short` (formato `Mar '26`, `Abr '25`) — sí los emite el calculator.
- `mes_siguiente_upper`, `mes_siguiente_upper_solo` — para slide 10.
- Todos los `_proy` (proyección mayo) — slide 10.
- `volumen_riesgo`, `n_ops_condicionadas`, `total_pendiente_cobro`, etc. — slides 6, 7.

---

## Constantes hardcodeadas (a mover a parametros_sede_mes)

Valores que hoy están fijos en código pero deberían ser parámetros por sede/mes:

| Constante | Valor actual | Razón futura |
|---|---|---|
| `OBJETIVO_RENTABILIDAD` | `"20 %"` | Puede variar por sede o cambiar anualmente |
| `tramo_comision` | `"3 %"` | Varía según volumen mensual (escalas) |

Cuando lleguen los datos de comisiones reales, crear tabla `parametros_sede_mes` o similar.

---

## Decisiones arquitectónicas relacionadas

- **Colores condicionales declarativos**: el calculator decide verde/rojo según signo de cada variación numérica antes del formateo. Documentado en `memory/project_decision_colores_declarativos.md`.
- **Capa de formato**: Postgres devuelve números crudos; `formatter.py` aplica locale es_ES manualmente (sin dependencia de `locale` del SO). Documentado en `memory/project_capa_formato.md`.
- **Reproducibilidad histórica**: cuando se implemente tabla `reportes_generados`, guardar snapshot del payload enviado al servicio para poder regenerar informes pasados con los datos de su momento.

---

## Discrepancias conocidas

Ver **P-18** en [`PENDIENTES.md`](../PENDIENTES.md): los datos de `ventas_comerciales` cuentan menos operaciones que los cuadros agregados manuales del Sheet. Afecta a varios tokens del slide 2 y slide 3. Pendiente validar con contabilidad si faltan operaciones por migrar o si el cuadro manual tiene errores.
