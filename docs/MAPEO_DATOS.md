# Mapeo de datos del informe

Para cada slide, qué tokens aparecen visualmente, de dónde sale cada dato, cómo
se calcula y su estado actual de integración con Postgres.

Este documento sirve a la vez como:
- Roadmap del proyecto (qué falta integrar).
- Referencia para validación con contabilidad ("¿de dónde sale tal cifra?").
- Trazabilidad histórica si cambian las fuentes.

> **Alcance:** este documento describe el informe de **Valencia** (12 slides).
> Las diferencias estructurales del informe de **Alicante** (10 slides, sin
> alquileres ni obra nueva ni operaciones condicionadas, rentabilidad real en
> vez de operativa, 1 director) están documentadas en
> `docs/MIGRACION_MULTISEDE.md` y en
> `memory/project_diferencias_valencia_alicante.md`. Para añadir una sede
> nueva (ej. Castellón) seguir la guía al final de `MIGRACION_MULTISEDE.md`.

## Convenciones

| Etiqueta | Significa |
|---|---|
| **VC** | tabla `finanzas_automation.ventas_comerciales` (datos crudos, una fila por operación) |
| **CM** | tabla `informes_financieros.contabilidad_mensual` (snapshot mensual del Sheet contable) |
| **RM-arras** | tabla `informes_financieros.resumen_mensual_arras` (totales mensuales de ventas, 2025+2026; columna `sede`). Movida desde `finanzas_automation` el 2026-05-22 con `sede`. |
| **RM-arras-sin-condic** | tabla `informes_financieros.resumen_mensual_arras__sin_condicion` (cobradas del mes, slide 9 Parte A; columna `sede`). Movida desde `finanzas_automation` el 2026-05-22 con `sede`. |
| **RM-alq** | tabla `informes_financieros.resumen_mensual_alquileres` (totales mensuales de alquileres cobrados; columna `sede`). Movida desde `finanzas_automation` el 2026-05-22 con `sede`. |
| **RM-alq-señales** | tabla `informes_financieros.resumen_mensual_alquiler_senales` (señales/reservas de alquiler por mes; columna `sede`). Movida desde `finanzas_automation` el 2026-05-22 con `sede`. |
| **PD** | tabla `informes_financieros.pagos_directores` (1 fila por director, mes y sede; alimenta el tramo de comisión dinámico). Movida desde `finanzas_automation` el 2026-05-21 y añadida columna `sede`. |
| **constante** | valor hardcodeado en código (a mover a `parametros_sede_mes` cuando varíe por sede o mes) |
| **derivado** | calculado por Python a partir de otros datos |
| **manual** | aún no integrado; viene del cliente (n8n o JSON mock) |

> **Nota sobre alquileres 2025:** las dos tablas de resumen de alquileres
> (`resumen_mensual_alquileres`, `resumen_mensual_alquiler_senales`) solo tienen
> filas para 2026 porque **el negocio de alquileres nació en 2026** (no existía
> en 2025). Eso hace que el YoY de contratos (slide 3) sume solo ventas para
> el año anterior — y es el dato correcto, no una asimetría a arreglar.

**Estado:**
- ✅ Integrado y leyendo de Postgres.
- ⚠️ Integrado con discrepancia conocida (ver P-18 en PENDIENTES.md).
- ⏳ Pendiente de integrar (valor mock todavía).

---

## ⚠️ IMPORTANTE: el informe es HÍBRIDO (foto histórica + estado vivo)

Antes de leer los slides, hay que entender una característica clave del diseño
actual: **no todos los datos del informe son reproducibles para un mes pasado**.

El informe mezcla dos naturalezas de datos:

### 🟢 Datos HISTÓRICOS — respetan el mes pedido (reproducibles)

Salen de tablas **inmutables** (una fila por mes, no se sobrescriben). Si pides
el informe de marzo 2026 en septiembre, estos datos serán **los de marzo**:

| Concepto | Fuente | Por qué es fiable |
|---|---|---|
| Ingresos, márgenes, rentabilidad, break even, EBITDA | `contabilidad_mensual` | Snapshot mensual cargado del Sheet, una fila por (sede, escenario, anyo, mes) |
| **Contratos firmados del mes** (importe + nº ops, slide 1/2/3) | `resumen_mensual_arras` + `resumen_mensual_alquileres` | **Cambio 2026-05-20:** ya NO se calcula desde `ventas_comerciales`; viene de la suma de las 2 tablas resumen mensual. Una fila por mes. |
| **Señales de alquiler del mes** (importe + nº ops, slide 4 tarjeta Reservas) | `resumen_mensual_alquiler_senales` | **Cambio 2026-05-20:** ya NO desde `ventas_comerciales`; viene de tabla resumen. |
| Comisiones cobradas del mes (ventas y alquileres, slide 9) | `resumen_mensual_arras__sin_condicion`, `resumen_mensual_alquileres` | Tablas resumen mensual, una fila por mes |
| Reservas del mes (señales sumadas de ventas+alquileres) | `ventas_comerciales` filtrado por `fecha_senal` en el mes | El filtro es por fecha del evento, que no cambia |
| **Tramo de comisión del mes** (slide 1 y 9) | `informes_financieros.pagos_directores` (suma de `porcentaje` filtrado por `(sede, anyo, mes)`) | **2026-05-20:** ya NO es constante `0.03` hardcoded; se lee dinámicamente. **2026-05-21:** tabla movida a schema `informes_financieros` y añadido filtro por sede. Valencia abril `'3 %'`, Alicante abril `'4 %'`. |
| Comparativas MoM / YoY | derivadas de los anteriores | Cálculo relativo al mes pedido |

### 🔴 Datos de ESTADO VIVO — reflejan la foto de HOY, NO del mes pedido

Salen de `ventas_comerciales` filtrando por **estado actual** de la operación.
`ventas_comerciales` es una tabla mutable: cuando una operación cambia de
estado (de pendiente a firmada, de condicionada a liberada), su fila **se
actualiza**, no se guarda una versión histórica. Por tanto **no se puede saber
qué estado tenía una operación en un mes pasado**.

| Concepto | Slide | Filtro | Por qué NO es histórico |
|---|---|---|---|
| Pipeline pendiente de alquiler | 4, 5 | `arras_firmadas='NO'` (vivas) | Muestra lo pendiente AHORA, no al cierre del mes pedido |
| Pipeline pendiente de ventas | 5 | `arras_firmadas='NO'` (vivas) | Idem |
| Obra nueva | 5 | estado actual de las promociones | Idem |
| Operaciones condicionadas | 6 | `pendiente_fecha_condicionada=TRUE` | Muestra las condicionadas vivas AHORA |

### Consecuencia práctica

- El informe es **fiable si se genera al cierre del mes** (primeros días del
  mes siguiente): en ese momento el "estado vivo" coincide con el "estado al
  cierre".
- Si se **regenera un mes pasado** tiempo después: los KPIs financieros salen
  correctos, pero el pipeline / condicionadas reflejan el estado de hoy, no el
  de aquel cierre. Sería un informe parcialmente inconsistente.

### Solución futura (no implementada)

Tabla `informes_financieros.reportes_generados` que guarde el **payload JSON
completo** al generar cada informe, con `(sede, anyo, mes, generado_at)`. Al
regenerar un mes, usar el snapshot guardado en lugar de recalcular. Esto da
reproducibilidad total. Pendiente — ver decisión en memoria del proyecto y
P-08 en PENDIENTES.md.

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
| `contratos_firmados` | RM-arras + RM-alq | **Suma** de `resumen_mensual_arras.honorarios` + `resumen_mensual_alquileres.honorarios_cobrados` para `(anio, mes)`. Abril 2026: 483.327 + 22.075 = **505.402 €**. Función `_query_contratos_resumen`. | ✅ |
| `ingresos_totales` | CM | `ingresos_contables` | ✅ |
| `tramo_comision` | PD | **Dinámico:** `SUM(porcentaje)` de `informes_financieros.pagos_directores` para `(sede, anio, mes)`. Abril 2026: Valencia (ALEX 0,015 + FADIA 0,015) = `"3 %"`; Alicante (PELAYO 0,04) = `"4 %"`. Función `_query_tramo_comision(sede, anyo, mes)`. Funciona con N directores variables sin tocar código. Resuelve P-22. | ✅ |

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
| `reservas_año_anterior` | CM | `_query_contable` con período YoY (mismo mes, año−1) → `contabilidad_mensual.pagas_señales`. **El valor es correcto** (año anterior). | ⚠️ ver P-18 |

> **Bug de plantilla card 1 (etiqueta vs valor):** la card 1 emparejaba
> `{{mes_anterior_short}}` (= mes−1, ej. `Mar '26`) con `{{reservas_año_anterior}}`
> (= año−1, ej. `359.135 €`): la etiqueta era del mes anterior pero el valor del
> año anterior. El token de etiqueta correcto **ya lo emite el calculator**:
> `mes_año_anterior_short` (`format_mes_short_anyo(anyo_yoy, mes_yoy)` →
> `Abr '25`). Fix = en la plantilla de producción, cambiar en esa línea
> `{{mes_anterior_short}}` por `{{mes_año_anterior_short}}`. NO requiere tocar
> Python. Aplica igual a la card 2 con `{{contratos_año_anterior}}`.

### Tarjeta · Contratos firmados (ventas y alquiler)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `contratos_firmados` | RM-arras + RM-alq | (igual que slide 1: suma de las 2 tablas resumen del mes) | ✅ |
| `var_contratos_mom` | derivado | `(contratos_actual - contratos_mes-1) / contratos_mes-1`, ambos lados desde RM-arras + RM-alq | ✅ |
| `n_ops_contratos` | RM-arras + RM-alq | Suma de `num_operaciones` de ambas tablas para el mes. Abril 2026: 33+7 = 40. | ✅ |
| `delta_ops_contratos` | derivado | `n_ops_actual - n_ops_mes-1` (formato `±N ops`) | ✅ |
| `contratos_mes_anterior` | RM-arras + RM-alq | Misma suma para `(anyo_prev, mes_prev)` | ✅ |
| `contratos_año_anterior` | RM-arras + RM-alq | Misma suma para el mismo mes del año anterior. ⚠️ Como alquileres no existía en 2025, solo suma ventas → es el dato correcto, no un error. | ✅ |

### Tarjeta · Ingresos totales

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ingresos_totales` | CM | `ingresos_contables` | ✅ |
| `var_ingresos_mom` | derivado | `(ingresos_actual - ingresos_mes-1) / ingresos_mes-1` | ✅ |
| `ingresos_ventas` | CM | `honorarios_intermediacion` | ✅ |
| `ingresos_alquiler` | CM | `resto_ingresos` (confirmado: lo que no es intermediación = alquileres) | ✅ |
| `ingresos_mes_anterior` | CM | `ingresos_contables` del mes-1 | ✅ |
| `margen_bruto` | CM | **`rentabilidad_bruta_pct`** (decimal 0..1, ej. `0.6116` → `61 %`). ⚠️ NO confundir con la columna homónima `contabilidad_mensual.margen_bruto`, que es un IMPORTE en € (ej. `258.999,10`), no un %. El token usa el `_pct`. | ✅ |

### Tarjeta · Rentabilidad operativa

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `rentabilidad_op` | CM | `rentabilidad_operativa_pct` | ✅ |
| `var_rentab_mom` | derivado | **Diferencia en PUNTOS PORCENTUALES** (no variación relativa). Abril 30,38% − marzo 30,99% = `-0,61 %`. Ambos lados ya son % → resta directa, NO `(a-b)/b`. Si fuese variación relativa daría -1,97 % (engañoso). | ✅ |
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
| `contratos_mes_anterior` | RM-arras + RM-alq | (idem slide 2) | ✅ |
| `n_ops_contratos_mes_anterior` | RM-arras + RM-alq | suma `num_operaciones` mes-1 | ✅ |
| `contratos_firmados` | RM-arras + RM-alq | (idem slide 2) | ✅ |
| `n_ops_contratos` | RM-arras + RM-alq | suma `num_operaciones` mes actual | ✅ |
| `var_contratos_mom_arrow` | derivado | `▲`/`▼` + porcentaje (mismo cálculo que `var_contratos_mom`) | ✅ |
| `delta_ops_contratos_full` | derivado | `±N ops (±X %)` (con `num_operaciones` de RM) | ✅ |

### Tarjeta · Comparativa interanual (vs ABRIL 2025)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_año_anterior` | CM | `pagas_señales` del año anterior | ⚠️ |
| `contratos_año_anterior` | RM-arras + RM-alq | Suma de las 2 tablas para el mes del año anterior. Como alquileres no existía en 2025, solo suma ventas. | ✅ |
| `var_reservas_yoy` | derivado | `(reservas_actual - reservas_año_anterior) / reservas_año_anterior` | ⚠️ |
| `var_contratos_yoy` | derivado | `(contratos_actual - contratos_año_anterior) / contratos_año_anterior` con ambos lados desde RM | ✅ |

### Tarjeta · Ticket medio por operación

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ticket_medio` | derivado | `honorarios / num_operaciones` desde **RM-arras + RM-alq** del mes (no desde VC). Abril 2026: 505.402 / 40 = `12.635 €`. | ✅ |
| `ticket_medio_mes_anterior` | derivado | mismo cálculo aplicado al mes-1 con RM | ✅ |
| `var_ticket_medio_mom` | derivado | `(ticket_medio - ticket_medio_mes-1) / ticket_medio_mes-1` (variación relativa porque los lados son importes, no %) | ✅ |

### Colores condicionales del slide 3

| Token | Verde si | Rojo si |
|---|---|---|
| `var_reservas_mom_arrow` | ≥ 0 | < 0 |
| `var_contratos_mom_arrow` | ≥ 0 | < 0 |
| `var_reservas_yoy` | ≥ 0 | < 0 |
| `var_contratos_yoy` | ≥ 0 | < 0 |
| `var_ticket_medio_mom` | ≥ 0 | < 0 |

### Lado derecho — Gráfico de barras ✅

Gráfico de barras agrupadas: 3 períodos (`Abr '25`, `Mar '26`, `Abr '26`) × 2 series (Reservas, Contratos Firmados).

**Estado:** ✅ integrado.

**Implementación:**
- Generado con matplotlib en `app/chart_generator.py` (función `generar_grafico_reservas_arras`).
- Paleta: barras Reservas `#F6B26B` (melocotón), barras Contratos `#7AB8E5` (azul claro). Fondo transparente. Etiquetas del color de su barra.
- El PNG se sube temporalmente a Drive, se sustituye en la plantilla con `replaceAllShapesWithImage` apuntando al token `{{grafico_reservas_arras}}`, y se borra de Drive tras exportar el PDF.
- Helpers: `app/image_helpers.py` (upload, replace, cleanup).

**Datos:** los 6 valores (3 períodos × 2 series) vienen del calculator en el campo especial `_chart_reservas_arras` del payload (no es un token, no pasa por `replaceAllText`). Las 3 barras de **Contratos Firmados** salen ahora de **RM-arras + RM-alq** (no de `ventas_comerciales`), coherente con el resto del slide 3.

---

## Slide 4 — Gestión de alquileres

Dos tarjetas con KPIs de alquileres + lista pipeline pendiente de firma.

### Convención clave

Para alquileres, **`fecha_arras`** representa la **fecha de firma del contrato**
(la ingesta hace ese mapeo desde "FECHA CONTRATO" del Sheet). El nombre de la
columna se mantiene por compatibilidad con ventas, pero su significado en
alquileres es distinto.

Filtro base de todos los queries de alquileres: `inmueble LIKE 'ALQ.-%'`.

### Tarjeta · Reservas (señales)

**Cambio 2026-05-20:** fuente migrada de `ventas_comerciales` a la nueva tabla
`resumen_mensual_alquiler_senales` (`honorarios_cobrados` + `num_operaciones`).
Función `_query_alquiler_senales_resumen`. Solo tiene datos 2026 (negocio
de alquileres nació en 2026). Mismo caso especial septiembre: usa `'sept'`
(4 letras).

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_alquiler` | RM-alq-señales | `honorarios_cobrados` del mes. Abril 2026: `27.415 €`. | ✅ |
| `var_reservas_alquiler_mom` | derivado | `(reservas_alq_actual - reservas_alq_mes-1) / reservas_alq_mes-1` con flecha `▲`/`▼` | ✅ |
| `n_ops_reservas_alquiler` | RM-alq-señales | `num_operaciones` del mes. Abril 2026: `12`. | ✅ |
| `delta_ops_reservas_alquiler` | derivado | `n_ops_actual - n_ops_mes-1` con sufijo `op.` (abril vs marzo: 12−18 = `-6 op.`) | ✅ |

### Tarjeta · Contratos firmados

Filtro común de los 4 tokens (un contrato de alquiler firmado en el mes pedido):

```sql
FROM ventas_comerciales
WHERE inmueble LIKE 'ALQ.-%'                              -- es alquiler
  AND fecha_arras >= make_date(anyo, mes, 1)              -- fecha firma contrato
  AND fecha_arras <  make_date(anyo, mes, 1) + INTERVAL '1 month'
  AND arras_firmadas = 'SI'                               -- contrato efectivamente firmado
```

Recordatorio: en alquileres `fecha_arras` = **fecha de firma del contrato** (la
ingesta mapea ahí "FECHA CONTRATO"). `arras_firmadas = 'SI'` excluye `'NO'` y
`'CAÍDA - 0'` (canceladas).

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `contratos_alquiler` | VC | `SUM(honorarios_totales)` con el filtro de arriba | ✅ |
| `var_contratos_alquiler_mom` | derivado | `(contratos_alq_actual - contratos_alq_mes-1) / contratos_alq_mes-1` con flecha `▲`/`▼` | ✅ |
| `n_ops_contratos_alquiler` | VC | `COUNT(*)` con el filtro de arriba (= nº contratos firmados en el mes) | ✅ |
| `delta_ops_contratos_alquiler` | derivado | `n_ops_contratos_alq(mes) - n_ops_contratos_alq(mes-1)`, formateado con signo y sufijo `ops.` (ej. `+2 ops.`) | ✅ |

### Pipeline pendiente de firma (lista variable)

Operaciones de alquiler que se han señalizado pero aún no han firmado contrato.
**Sin filtro de mes** — incluye señalizaciones de meses anteriores que siguen vivas.

**Filtro:**
```sql
WHERE sede = %(sede)s                    -- multi-sede
  AND inmueble LIKE 'ALQ.-%'
  AND fecha_senal IS NOT NULL
  AND (arras_firmadas IS NULL OR arras_firmadas NOT IN ('SI', 'CAÍDA - 0'))
```

**Función**: `_query_pipeline_alquileres(sede)` en `calculator_base.py`
(movida desde calculator.py el 2026-05-21). Filtro semántico universal
`LIKE 'ALQ.-%'` por convención de la ingesta — funciona para cualquier
sede con alquileres; sedes sin alquileres reciben lista vacía.

Exclusiones explícitas:
- `'SI'`: ya firmadas (no son pendiente).
- `'CAÍDA - 0'`: operaciones canceladas (atención: con tilde en la `Í`).

**Orden:** por `honorarios_totales DESC`.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `pipeline_alquiler` (lista) | VC | items con `{nombre, importe}`; el nombre quita el prefijo `ALQ.-` y antepone `▌` (barra visual) | ✅ |
| `total_pipeline_alquiler` | derivado | `SUM(honorarios_totales)` del pipeline | ✅ |
| `n_ops_pipeline_alquiler` | derivado | `COUNT(*)` del pipeline | ✅ |
| `nota_pipeline_alquiler` | constante vacía | reservado para texto manual ("* Las 3 operaciones firmadas..."), no automatizable hoy | ⏳ |

La lista se expande automáticamente a slots `pipeline_alq_N_nombre` y `pipeline_alq_N_importe` con `n_max=8` via `LIST_SPECS` del generator.

### Colores condicionales del slide 4

| Token | Verde si | Rojo si |
|---|---|---|
| `var_reservas_alquiler_mom` | ≥ 0 | < 0 |
| `var_contratos_alquiler_mom` | ≥ 0 | < 0 |

---

## Slide 5 — Pipeline Q2 (operaciones pendientes de firma)

Vista agregada de operaciones futuras. Tres sub-secciones independientes
(ventas, alquileres, obra nueva) más cuatro totales en la esquina derecha.

### Token global del slide

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `trimestre` | derivado | `Q{(mes-1)//3 + 1}` — calcula el trimestre del mes en curso (Q1, Q2, Q3, Q4). Usado en el título "VISIBILIDAD {trimestre}". | ✅ |

### Sub-sección · Pipeline de ventas (3 columnas)

Operaciones de venta señalizadas pero aún no firmadas. Se reparten en 3 columnas
(21 slots totales con `n_max=21`, la plantilla tiene `{{venta_pend_1..21_*}}`).

**Filtro:**
```sql
WHERE sede = %(sede)s                    -- multi-sede (Valencia o Alicante)
  AND inmueble NOT LIKE 'ALQ.-%'         -- no alquileres
  AND arras_firmadas = 'NO'              -- pendiente
  -- Exclusiones específicas por sede vienen parametrizadas (ver abajo):
  AND inmueble NOT ILIKE '%victoria kent%'           -- Valencia: obra nueva
  AND inmueble NOT ILIKE 'urb.%santa%b_rbara%'       -- Valencia: obra nueva
```

**Función**: `_query_pipeline_ventas(sede, inmuebles_excluir_ilike)` en
`calculator_base.py` (movida desde calculator.py el 2026-05-21 para que la
use también Alicante). Las exclusiones se pasan como parámetros bindeados
(no f-string, seguro contra SQL injection):

- **Valencia** pasa `PROMOCIONES_OBRA_NUEVA_EXCLUIR = ("%victoria kent%",
  "urb.%santa%b_rbara%")` desde `calculator.py`.
- **Alicante** no pasa nada (default `()`) porque no tiene obra nueva.

Cuando se migre a la decisión arquitectónica pendiente (tabla
`promociones_obra_nueva`), la constante de Valencia desaparece y el
filtro se carga dinámicamente de la tabla.

**Importante sobre el filtro:** NO excluimos `inmueble ILIKE 'urb.%'` genérico
porque hay ventas normales con ese prefijo (ej. `Urb. Loma de Caballeros 3`).
Solo excluimos las **promociones explícitas de obra nueva** conocidas.

**`DISTINCT ON`** defensivo por `(inmueble, fecha_senal, honorarios_totales)`
para neutralizar duplicados puntuales detectados en P-19.

**Orden:** `honorarios_totales DESC`.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ventas_pendientes` (lista) | VC | items `{nombre, importe}`; el nombre se muestra tal cual viene de BD (sin barra Unicode) | ✅ |
| `total_ventas_pipeline` | derivado | `SUM(honorarios_totales)` del pipeline ventas | ✅ |

Slots: `venta_pend_N_nombre` y `venta_pend_N_importe` (N=1..21) via `LIST_SPECS`.

### Sub-sección · Pipeline de alquileres

Reutiliza la lista `pipeline_alquiler` del slide 4 (mismas operaciones, mismos
slots, distinta tokenización: `venta_alq_pend_N_*` con `n_max=5`).

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `pipeline_alquiler` (lista, reusada) | VC | (idem slide 4, ver allí) | ✅ |
| `total_pipeline_alquiler` | derivado | (idem slide 4) | ✅ |

### Sub-sección · Arras por obra nueva

Operaciones de las dos promociones conocidas de obra nueva: `C. VICTORIA KENT` y
`Urb. Altos de Santa Bárbara`. Cada una agrupa N unidades (cada piso/planta es
una fila en BD).

**Filtro especial:** las obras nuevas NO se rigen por `arras_firmadas = 'SI'`
como las ventas normales. Incluimos cualquier estado EXCEPTO `'CAÍDA - 0'`
(usando `IS DISTINCT FROM` para preservar `NULL`).

```sql
WHERE arras_firmadas IS DISTINCT FROM 'CAÍDA - 0'
  AND (inmueble ILIKE '%victoria kent%'
       OR inmueble ILIKE 'urb.%santa%b_rbara%')
GROUP BY promocion
```

El `CASE WHEN` mapea las variantes ortográficas (con/sin tilde, mayúsculas,
nº de unidad) a un nombre canónico por promoción.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `obras_nuevas` (lista) | VC | items `{nombre, importe}` con N=1..2; los slots 3-4 quedarán vacíos | ✅ |
| `total_obra_nueva` | derivado | `SUM(honorarios_totales)` del agrupado | ✅ |

Slots: `obra_nueva_N_nombre` y `obra_nueva_N_importe` (N=1..4) via `LIST_SPECS`.

### Sub-sección · Totales agregados (esquina derecha)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `total_ventas_pipeline` | derivado | (ver arriba) | ✅ |
| `total_obra_nueva` | derivado | (ver arriba) | ✅ |
| `total_pipeline_alquiler` | derivado | (idem slide 4) | ✅ |
| `total_pipeline` | derivado | `total_ventas + total_obra_nueva + total_pipeline_alquiler` | ✅ |
| `n_ops_pipeline` | derivado | suma de COUNT(*) de las 3 sub-secciones | ✅ |

### Decisión arquitectónica pendiente: tabla `promociones_obra_nueva`

Las 2 promociones están hardcoded en el `CASE WHEN` y en el `WHERE` de la query
de obra nueva. Si aparece una tercera promoción (ej. `Urb. Nuevo Horizonte`),
hay que añadirla manualmente en código.

Cuando lleguemos a 3+ promociones, migrar a una tabla:
```sql
CREATE TABLE informes_financieros.promociones_obra_nueva (
    pattern_ilike   TEXT PRIMARY KEY,  -- '%victoria kent%', 'urb.%santa%b_rbara%'
    nombre_visible  TEXT NOT NULL      -- 'C. VICTORIA KENT'
);
```

Y el calculator lee la tabla y construye el `CASE WHEN` dinámicamente.

### Discrepancia obra nueva — RESUELTA (P-20 cerrado, 2026-05-19)

Validación contra PDF original abril 2026:
- Obra nueva Victoria Kent: calculator `94.240 €` vs PDF `94.240 €` ✅
- Obra nueva Altos Sta Bárbara: calculator `587.450 €` ✅

La query de obra nueva es correcta. El desfase histórico (`587.450` vs
`505.850`) **no era un bug de filtro**: se debía a **operaciones ausentes en
`ventas_comerciales`** por una ingesta incompleta desde el Sheet (mismo patrón
que el incidente de etiquetas contables). Una vez completados los datos en
origen, el total cuadra. Cerrado P-20.

**Lección (recurrente):** cuando un total de `ventas_comerciales` no cuadra con
el original y la query está bien, sospechar **datos faltantes en la ingesta**
antes que del código. Verificar con un `SELECT` de los inmuebles esperados
(ver incidente análogo en slide 6 abajo).

---

## Slide 6 — Operaciones condicionadas (riesgo operativo)

Tarjeta de alerta a la izquierda + tabla de operaciones a la derecha.

### Tarjeta de alerta (lado izquierdo)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `volumen_riesgo` | derivado | `SUM(honorarios_totales)` de las condicionadas vivas | ✅ |
| `n_ops_condicionadas` | derivado | `COUNT(*)` de las condicionadas vivas | ✅ |
| `impacto_facturacion` | derivado | Etiqueta semántica según `volumen_riesgo` (ver clasificación abajo) | ✅ |

### Clasificación de severidad (`impacto_facturacion`)

| Rango | Etiqueta | Color del `volumen_riesgo` |
|---|---|---|
| `> 80.000 €` | `Crítico` | rojo |
| `> 30.000 €` y `<= 80.000 €` | `Alto` | amarillo |
| `<= 30.000 €` (incluye 0 y NULL) | `Estable` | verde |

El color de `volumen_riesgo` se aplica via `_color_overrides` desde el calculator (no es color fijo de plantilla). Función `_clasifica_impacto()` en `calculator.py`.

### Tabla de operaciones condicionadas (lado derecho)

Lista variable, una fila por operación. Slots `condicionada_N_nombre` + `condicionada_N_importe` (N=1..22) con `n_max=22` via `LIST_SPECS`. La plantilla tiene `{{condicionada_1..22_*}}`.

**Filtro:**
```sql
WHERE pendiente_fecha_condicionada = TRUE
ORDER BY honorarios_totales DESC
```

`pendiente_fecha_condicionada` es un campo BOOLEAN específico de operaciones de venta condicionadas que aún no se han liberado. El flag es exclusivo de ventas (no aparece en alquileres por convención de la ingesta), así que no se filtra por tipo.

**No se agrupa por inmueble**: pueden aparecer 3 filas de `C. Mercat 47` si hay 3 arras condicionadas distintas en esa propiedad. Cada una tiene su propio importe.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `operaciones_condicionadas` (lista) | VC | items `{nombre, importe}` con N filas | ✅ |

### Incidente: operaciones condicionadas ausentes (2026-05-19)

`volumen_riesgo` salía más bajo que el PDF original. Causa: faltaban en
`ventas_comerciales` dos operaciones condicionadas reales — **`Paseo Alameda 41`**
(honorarios `37.500 €`) y **`C. Doctor Villena 20`** (`13.650 €`) — por ingesta
incompleta desde el Sheet. La query (`pendiente_fecha_condicionada = TRUE`)
estaba bien; el dato no estaba en origen. Tras corregir, `volumen_riesgo` pasó
de `96.471,69 €` a **`147.621,69 €`** (9 operaciones) → severidad `Crítico` (rojo).

**Las 2 filas se insertaron/corrigieron MANUALMENTE en Postgres** (`numero` 324
y 325, `id` 70411/70412), saltándose la ingesta n8n. **Riesgo abierto:** si esas
operaciones aparecen luego en el Sheet origen y la ingesta vuelve a correr,
puede haber duplicado o sobreescritura según cómo deduplique el workflow (¿UPSERT
por `numero` o INSERT ciego?). Seguimiento en **P-28** de `PENDIENTES.md`.

**Diagnóstico estándar** cuando un total de condicionadas/ventas no cuadra:
`SELECT` directo de los inmuebles esperados en `ventas_comerciales`
(comprobando `pendiente_fecha_condicionada` y `honorarios_totales`) **antes** de
sospechar del código. Mismo patrón que slide 5 (obra nueva) y el incidente de
etiquetas contables.

---

## Slide 11 — Semáforo estratégico

Tres columnas semánticas con código de color: Fortalezas (verde), En observación (amarillo), Riesgo crítico (rojo).

### Decisión arquitectónica: asignación FIJA

Los KPIs de cada columna están **hardcodeados en la plantilla**. No hay lógica
dinámica que reasigne KPIs según valor. Si la rentabilidad fuera negativa,
seguiría apareciendo en "Fortalezas" — el color del valor sí cambia.

**Alternativa rechazada:** asignación dinámica (mover KPIs entre columnas según
valor). Implicaría reorganizar shapes via Slides API en cada generación, lo
cual es complejo y frágil. La pista visual del color condicional ya transmite
el sentido.

### Tokens reutilizados (vienen de otros slides)

| Token | Origen | Notas |
|---|---|---|
| `ticket_medio` | Slide 3 | — |
| `var_ticket_medio_mom` | Slide 3 | Hereda color verde/rojo según signo. |
| `objetivo_rentabilidad` | Slide 2 | Constante hardcoded `"20 %"`. |
| `n_ops_condicionadas` | Slide 6 | — |

### Tokens nuevos del slide 11

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `var_reservas_mom_observacion` | derivado | Mismo valor visible que `var_reservas_mom` del slide 2 + sufijo `​` invisible (ver nota abajo) | ✅ |
| `var_contratos_mom_observacion` | derivado | Mismo valor visible que `var_contratos_mom` del slide 2 + sufijo `​` invisible | ✅ |
| `rentabilidad_op_signed` | CM | `format_pct_signed(rentabilidad_operativa_pct)` — siempre con `+`/`-` explícito | ✅ |
| `volumen_riesgo_short` | derivado | `format_euro_compacto(volumen_riesgo)` — formato `135,9 k €` (sufijo k/M) | ✅ |
| `mes_siguiente_capitalizado` | derivado | Nombre del mes siguiente capitalizado (`Mayo`, `Junio`...). Usado en la narrativa "facturación de X será severo" | ✅ |

**Por qué tokens `_observacion` separados Y con sufijo invisible:**

El mecanismo de colores (`apply_color_overrides`) busca shapes **por el VALOR de
texto, no por el nombre del token**. Tener un token distinto NO basta: si
`var_reservas_mom` (slide 2, rojo por negativo) y `var_reservas_mom_observacion`
(slide 11, amarillo) tienen el **mismo texto** `-13,9 %`, la búsqueda encuentra
el valor en AMBOS slides y, como `_observacion` se procesa después, el amarillo
pisaba la card 1 del slide 2.

**Incidente real (2026-05-19, en producción):** slide 2 card 1 mostraba
`-13,9 % vs Mar '26` en **amarillo** en vez de rojo. Confirmado por logs:
`var_reservas_mom_observacion` reportaba 3 localizaciones (debía ser 1, solo el
slide 11) → contaminaba el slide 2.

**Fix aplicado:** los valores `_observacion` llevan un sufijo `​`
(zero-width space, invisible) — `format_pct_signed(...) + "​"`. El texto se
ve idéntico pero es **distinto** para la búsqueda, así el override del slide 11
ya no toca las cajas del slide 2. Tras el fix: cada `_observacion` reporta 1 sola
localización. No tocar ese sufijo al editar `calculator.py`.

### Colores condicionales del slide 11

| Token | Verde si | Amarillo si | Rojo si |
|---|---|---|---|
| `rentabilidad_op_signed` | ≥ 20 % (objetivo) | — | < 20 % |
| `volumen_riesgo_short` | volumen ≤ 30k € | volumen 30k-80k € | volumen > 80k € |
| `var_reservas_mom_observacion` | — | siempre (semántica de la columna) | — |
| `var_contratos_mom_observacion` | — | siempre (semántica de la columna) | — |

`rentabilidad_op_signed` y `volumen_riesgo_short` heredan los umbrales del slide 6 (`_clasifica_impacto`) y del objetivo corporativo (`OBJETIVO_RENTABILIDAD`).

---

## Slide 12 — Hoja de ruta del mes siguiente

Cuatro tarjetas con objetivos para el mes/trimestre siguiente. La mayoría de
tokens son **reutilizados** de slides anteriores (el calculator ya los emite).

### Tokens del slide 12

**Tarjeta 1 — Aceleración de cobros:**

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `total_pendiente_cobro` | derivado (pago_agentes) | **Ya NO es provisional.** `SUM` de los cobros pendientes del slide 7 (`informes_financieros.pago_agentes`, mismo filtro: `sede`, `pte_facturar` numérico puro `> 1`, `fecha_arras_sin_condic IS NOT NULL`), formateado con `€`. El slide 7 emite el mismo número sin `€` (`total_pendiente_cobro_sin_euro`). | ✅ |
| `trimestre` | derivado | (ver slide 5) — usado en "Objetivo: Maximizar liquidez en Q2" | ✅ |

**Tarjeta 2 — Blindaje de operaciones:**

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `volumen_riesgo` | VC | (heredado del slide 6) | ✅ |
| `n_ops_condicionadas` | VC | (heredado del slide 6) | ✅ |

**Tarjeta 3 — Conversión de pipeline:**

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `total_pipeline` | derivado | (heredado del slide 5) | ✅ |
| `n_ops_pipeline` | derivado | (heredado del slide 5) | ✅ |

**Tarjeta 4 — Control de inversión:**

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `objetivo_rentabilidad` | constante | `"20 %"` (heredado del slide 2) | ✅ |
| `inversion_tecnologica` | constante provisional | `"27k€"` hardcoded en `INVERSION_TECNOLOGICA_PROVISIONAL`. **Pendiente confirmar con contabilidad** si es constante anual, acumulado, parámetro mensual u otra cosa. | ⏳ provisional |

**Token global del slide:**

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `mes_siguiente_upper` | derivado | `format_mes_anyo_upper(anyo_next, mes_next)` — produce `"MAYO 2026"` (mes + año en mayúsculas) | ✅ |

### Colores condicionales

**Ninguno.** Las barras superiores de color de las 4 tarjetas (verde, rojo, amarillo, azul) son **decorativas fijas en la plantilla**. La tarjeta 4 siempre es azul, la 1 siempre verde, etc. — independiente de los valores. Si en el futuro contabilidad pidiera que cambiaran según evaluación cualitativa, sería un cambio nuevo.

### Constantes provisionales agrupadas

Al principio de `calculator.py` están agrupadas las constantes pendientes de
mover a su fuente real:

```python
OBJETIVO_RENTABILIDAD = "20 %"  # corporativo, no varía a corto plazo
INVERSION_TECNOLOGICA_PROVISIONAL = "27k€"  # pendiente contabilidad (¿anual? ¿acumulado?)
```

`total_pendiente_cobro` **ya no es constante**: deriva de `pago_agentes`
(igual que slide 7). Ya no existe `TOTAL_PENDIENTE_COBRO_PROVISIONAL` en el
código.

Buscar `PROVISIONAL` en el código localiza los puntos a actualizar cuando se
confirme la fuente real.

---

## Slide 9 — Comisiones de directores

Slide multi-fuente con cálculos derivados. Tres partes: A (firmado y cobrado
en el mes) ✅, B (cálculo final) ✅, C (tabla de atrasos) ⏳ pendiente fuente.

### Token global del slide

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `mes_informe_upper` | derivado | `format_mes_upper(mes)` → `"ABRIL"` (mes en mayúsculas sin año). Usado en "FIRMADO Y COBRADO EN ABRIL". | ✅ |
| `ingresos_totales` | CM | (heredado del slide 2) — banner superior | ✅ |
| `tramo_comision` | PD | **Dinámico (2026-05-20, schema actualizado 2026-05-21):** `SUM(porcentaje)` de `informes_financieros.pagos_directores` para `(sede, anio, mes)`. Mismo token que slide 1. Si no hay filas → `ValueError` explícito (lección P-27: nunca generar PDF con comisión 0 silenciosa). Resuelve P-22. | ✅ |

### Parte A — Firmado y cobrado en el mes ✅

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ventas_cobradas_mes` | `resumen_mensual_arras__sin_condicion.cobradas` | filtro `anio` + `mes` (string 3 letras). Solo Valencia. | ✅ |
| `comision_ventas_mes` | derivado | `ventas_cobradas_mes × tramo_comision_pct` (tramo **dinámico** desde PD, no constante) | ✅ |
| `alquileres_cobrados_mes` | `resumen_mensual_alquileres.honorarios_cobrados` | filtro `anio` + `mes`. OJO: esta tabla usa `'sept'` (4 letras) para septiembre, la otra usa `'sep'`. | ✅ |
| `comision_alquileres_mes` | derivado | `alquileres_cobrados_mes × tramo_comision_pct` | ✅ |
| `subtotal_comision_mes` | derivado | `comision_ventas_mes + comision_alquileres_mes` | ✅ |

### Parte B — Cálculo final ✅ (con constante provisional)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `subtotal_comision_atrasos` | derivado | `SUM(importe_comision)` de la lista `comisiones_atrasos` (Parte C). Antes era constante provisional; cerrado P-23 el 2026-05-21. | ✅ |
| `total_comision_repartir` | derivado | `subtotal_comision_mes + subtotal_comision_atrasos` | ✅ |
| `comision_variable_por_director` | derivado | `total_comision_repartir / N_DIRECTORES` (N=2) | ✅ |
| `sueldo_fijo_director` | constante | `SUELDO_FIJO_DIRECTOR = 2666.67` (bruto mensual, provisional) | ⏳ provisional |
| `total_por_director` | derivado | `comision_variable_por_director + sueldo_fijo_director` | ✅ |

**Constantes del slide 9 — dónde cambiarlas (cabecera de `calculator.py`):**

| Constante | Cambiar cuando... |
|---|---|
| `N_DIRECTORES` | entre o salga un director (marcado con `>>> ... <<<` en código) |
| `SUELDO_FIJO_DIRECTOR` | cambie el sueldo fijo bruto |

> **Constantes eliminadas:**
> - `TRAMO_COMISION_PCT` / `TRAMO_COMISION_LABEL` (P-22 resuelto): el tramo
>   se calcula dinámicamente desde `pagos_directores` vía
>   `_query_tramo_comision`. Para cambiarlo, editar las filas de
>   `pagos_directores` del mes correspondiente.
> - `SUBTOTAL_COMISION_ATRASOS_PROVISIONAL` (P-23 resuelto): el subtotal
>   se calcula dinámicamente desde `comisiones_atrasos_directores` vía
>   `_query_comisiones_atrasos`.

Buscar `PROVISIONAL` o `>>>` en el código localiza todos estos puntos.

### Parte C — Tabla "COBRADO DE MESES ANTERIORES" ✅ (2026-05-21)

**Fuente**: `informes_financieros.comisiones_atrasos_directores`. Una fila
por operación de un mes anterior cobrada en el mes actual, con su tramo
histórico y el importe de comisión resultante. Filtrada por `sede` (la
tabla tiene columna `sede`). Foto viva: sin filtro de `anyo/mes` — la
tabla refleja los atrasos pendientes ahora; cuando se liquidan, la ingesta
los retira.

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `comisiones_atrasos` (lista, `n_max=7`) | `comisiones_atrasos_directores` | Items: `nombre=inmueble`, `mes=mes_origen.strip('()')` (ej. `(Nov.)` → `Nov.`), `tramo="({int(porcentaje*100)}%)"` (ej. `0.03` → `(3%)`), `importe=format_euro(importe_comision, 2)`. Ordenado por `importe DESC`. | ✅ |
| `subtotal_comision_atrasos` | derivado | `SUM(importe_comision)` de las filas filtradas por sede. Alimenta el `total_comision_repartir` de la Parte B. | ✅ |

Función: `_query_comisiones_atrasos(sede)` en `calculator_base.py`.

`n_max=7` coincide con los slots reales de la plantilla
(`comision_atraso_1..7_{nombre,mes,tramo,importe}`).

---

## Slide 7 — Cobros pendientes de liquidación

Tarjeta resumen a la izquierda + tabla 2 columnas a la derecha.

**⚠️ Es un dato de "estado vivo"** (ver sección HÍBRIDO al inicio): muestra los
cobros pendientes AHORA, no al cierre del mes pedido. Sin filtro de mes.

### Fuente

Tabla `informes_financieros.pago_agentes`, columna `pte_facturar` (TEXT).
Valores posibles: `'CAÍDA'`, `'0'`, o un número `> 0` (lo pendiente).

**Filtro:**
```sql
WHERE sede = %(sede)s                      -- multi-sede (añadido 2026-05-21)
  AND pte_facturar ~ '^[0-9]+\.?[0-9]*$'   -- numérico puro (descarta 'CAÍDA')
  AND CAST(pte_facturar AS NUMERIC) > 1     -- umbral anti-basura-float (P-24)
  AND fecha_arras_sin_condic IS NOT NULL    -- excluye 'PONER FECHA' (2026-05-19)
ORDER BY importe DESC
```

**Función**: `_query_cobros_pendientes(sede)`. La tabla `pago_agentes`
ganó columna `sede` el 2026-05-21 y desde entonces se filtra por sede
en la query. Tiene filas para Valencia y Alicante.

El umbral `> 1` descarta basura de coma flotante de la ingesta
(`'0.21000000000003638'` y similares). Ver P-24.

**Filtro `fecha_arras_sin_condic IS NOT NULL` (añadido 2026-05-19):** excluye
operaciones que en el Sheet origen tienen `"PONER FECHA"` como placeholder.
La columna es de tipo `DATE` en Postgres, así que la ingesta castea ese texto
no parseable a `NULL`. Esas operaciones aún no están listas para liquidar y
no deben contar como cobro pendiente. Impacto real abril 2026: pasa de 31 a
24 cobros, de `362.580 €` a `285.783 €` (se excluyen 7 operaciones por
`76.797 €`). Alivia P-25 (menos cobros que slots disponibles).

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `cobros_pendientes` (lista) | `pago_agentes` | items `{nombre=inmueble, importe}`, redondeados a entero (`format_euro`). `n_max=20`, 2 columnas, slots 1-10 izq / 11-20 der | ✅ |
| `total_pendiente_cobro_sin_euro` | derivado | suma de **TODOS** los cobros filtrados (no solo los 20 mostrados), formateado sin `€` | ✅ |
| `nota_cobros` | constante vacía | reservado para texto manual, no automatizable hoy | ⏳ |

**Token relacionado en slide 12:** `total_pendiente_cobro` (con `€`) deriva del
mismo cálculo. Slide 7 y slide 12 muestran el mismo número, coherente.

**Texto dinámico en plantilla:** "Prioridad {{mes_siguiente_capitalizado}}:"
(el cobro se prioriza el mes posterior al cierre).

### ⚠️ P-25 — Riesgo: más cobros que slots

Si hay más de 20 cobros (datos reales: 31), la tabla **trunca a 20** pero el
total incluye los 31. El lector ve 20 filas + un total que no cuadra al
sumarlas. **Decisión de negocio pendiente** (ampliar slots / top N + resumen /
filtro). Ver P-25 en PENDIENTES.md. El mismo riesgo aplica a slides 5 y 6.

---

## Slide 8 — Break Even y objetivos de facturación ✅

Tarjeta izquierda con una **barra/línea de tiempo vertical** (4 hitos: 30%, 20%,
10%, BREAK EVEN) y un marcador `{{ingresos_totales}}` que se **posiciona
dinámicamente** entre los hitos. Tarjeta derecha con tabla de objetivos y
estados.

### Fuente

Tabla `contabilidad_mensual`, escenario `con_crm` (confirmado por contabilidad,
2026-05-19), **variante sin extras**: columnas `break_even` e
`ingresos_margen_10..40` (no las `*_con_extras`). Dataclass `BreakEvenMes`,
query `_query_break_even(sede, escenario, anyo, mes)`.

### Tokens

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `sede_upper`, `mes_año_upper` | (heredados) | ya emitidos arriba | ✅ |
| `ingresos_totales` | CM | `ingresos_contables` (heredado) | ✅ |
| `break_even` | CM | columna `break_even` (variante sin extras) | ✅ |
| `margen_10_objetivo` | CM | `ingresos_margen_10` | ✅ |
| `margen_20_objetivo` | CM | `ingresos_margen_20` | ✅ |
| `margen_30_objetivo` | CM | `ingresos_margen_30` | ✅ |
| `margen_40_objetivo` | CM | `ingresos_margen_40` | ✅ |
| `margen_seguridad` | derivado | `ingresos_contables − break_even`. Positivo si cubre el BE, negativo si déficit. | ✅ |
| `break_even_estado` | derivado | `"✓ SUPERADO"` si `ingresos ≥ umbral`, si no `"FALTAN: <X> €"` (cuánto falta = umbral − ingresos) | ✅ |
| `margen_N_estado` | derivado | (mismo patrón para cada margen 10/20/30/40) | ✅ |
| `narrativa_break_even` | derivado | **Plantilla determinista** (NO LLM) en `_narrativa_break_even`. 3 ramas según el signo de `margen_seguridad`: supera / iguala exactamente / déficit. Cada rama tiene texto propio. | ✅ |

### Colores condicionales del slide 8

`margen_seguridad`:

| Condición | Color |
|---|---|
| `margen_seguridad ≥ 0` (cubre BE) | verde |
| `margen_seguridad < 0` (déficit) | rojo |

Sin este override, el token estaba en verde fijo en la plantilla → un déficit
saldría en verde, comunicando lo contrario de la realidad.

`break_even_estado`, `margen_10_estado`, `margen_20_estado`,
`margen_30_estado`, `margen_40_estado` (2026-05-22):

| Condición | Color |
|---|---|
| `ingresos_contables ≥ umbral` (texto `"✓ SUPERADO"`) | verde |
| `ingresos_contables < umbral` (texto `"FALTAN: <X> €"`) | rojo |

Sin estos overrides, los colores eran fijos en plantilla (verde para BE/m10/m20,
rojo para m30/m40 — coloreado a mano para abril 2026 de Valencia). Era engañoso
en otros meses o sedes donde el estado cambia.

**Solo coloreamos los `*_estado`, no los importes** (`break_even`,
`margen_N_objetivo`): esos tokens también aparecen en la barra/línea de tiempo
de la izquierda. Pintarlos cambiaría el color de los hitos de la barra y
comunicaría algo distinto. Si en un mes hay 3 estados con texto idéntico
(`"✓ SUPERADO"`), el override por valor de texto los pinta los 3
correctamente (mismo color → mismo resultado, sin colisión).

### Posicionamiento dinámico del marcador ✅ (2026-05-20)

La plantilla del slide 8 tiene una barra vertical con 4 hitos a Y fijas (de
arriba a abajo): m30, m20, m10, BE. Entre ellos vive el shape
`{{ingresos_totales}}` ("FACTURACIÓN COBRADA"). Para que el slide refleje
correctamente la facturación de cualquier mes, el shape se **mueve por API**
según los ingresos reales del mes.

**Algoritmo** (`app/break_even_chart.py`):

1. `locate_breakeven_anchors()` lee la plantilla y captura la **Y absoluta**
   de los 4 hitos + el `objectId` del marcador. Camina recursivamente en
   `elementGroup`s y compone `translateY` padre+hijo (4 de los 5 hitos del
   slide 8 viven dentro de grupos).
2. `compute_marker_y()` (función PURA, testeable): según los valores reales
   `(ingresos, break_even, m10, m20, m30)` y las anclas Y, devuelve el Y
   destino:
   - Si `ingresos ≤ break_even` → topa al fondo (Y_break_even).
   - Si `ingresos ≥ margen_30` → topa al techo (Y_margen_30).
   - Si está dentro de un tramo `(V_b, V_a)`: interpolación lineal
     `Y = Y_b + ratio × (Y_a − Y_b)` con `ratio = (ingresos − V_b) / (V_a − V_b)`.
3. `apply_breakeven_marker_position()` envía un `updatePageElementTransform`
   con `applyMode: ABSOLUTE` (idempotente, no acumula al transform actual).

**Detalle clave: la llamada va ANTES de `_replace_tokens`** en el `generator`.
Si se hiciese después, los tokens ya estarían sustituidos por sus valores y
`locate_breakeven_anchors` no podría identificar los hitos.

**Payload:** clave especial `_break_even_position` con los 5 valores numéricos
(`ingresos`, `break_even`, `margen_10/20/30`). El calculator la emite junto a
`_color_overrides` y `_chart_reservas_arras`. El generator la extrae antes del
`expand_lists` (no es un token de `replaceAllText`).

**Defensivo:**
- Si falta cualquier hito en la plantilla → WARNING, no se mueve nada.
- Si falta cualquier valor (None) → WARNING, no se mueve nada.
- El `try/except` en `generator.py` aísla un fallo aquí del resto del PDF.

**El shape `{{ingresos_totales}}` puede llevar acompañado el label "FACTURACIÓN
COBRADA"** dentro del mismo shape (la plantilla lo organiza así). Al mover el
shape, ambos textos se mueven juntos — comportamiento deseado.

**Validación:** 21 tests unitarios de `compute_marker_y` en
`tests/test_break_even_chart.py` (bordes, hitos, interpolación 3 tramos,
None inputs, tipos, monotonía estricta). Script
`scripts/simular_break_even.py <ingresos>` permite generar PDFs con valores
ficticios sin tocar BD, para validar visualmente escenarios extremos
(ingresos < BE, ingresos > m30, etc.).

---

## Slide 10 — Break Even proyectado (mes siguiente) ✅

Versión simplificada del slide 8 con la proyección del **mes+1**. **Sin estados
dinámicos ni narrativa** (los textos "SUPERVIVENCIA / OBJETIVO / ÓPTIMO /
EXCELENCIA" son fijos en plantilla). Solo llega a margen 30% (no hay m40).

### Fuente

`contabilidad_mensual` para `(sede, escenario, anyo_next, mes_next)`. Reutiliza
`_query_break_even` con los valores del mes siguiente.

### Tokens

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `sede_upper` | (heredado) | igual que slide 8 | ✅ |
| `mes_siguiente_upper_solo` | derivado | `format_mes_upper(mes_next)` → `MAYO` (sin año) | ✅ |
| `break_even_proy` | CM mes+1 | `break_even` del mes siguiente | ✅ |
| `facturacion_objetivo_proy` | CM mes+1 | **= `break_even_proy`** (decisión: el mínimo a facturar) | ✅ |
| `margen_10_objetivo_proy` | CM mes+1 | `ingresos_margen_10` del mes siguiente | ✅ |
| `margen_20_objetivo_proy` | CM mes+1 | `ingresos_margen_20` del mes siguiente | ✅ |
| `margen_30_objetivo_proy` | CM mes+1 | `ingresos_margen_30` del mes siguiente | ✅ |

### Dependencia importante

El slide 10 requiere que **la fila del mes+1 ya esté cargada** en
`contabilidad_mensual`. Si no existe (ej. generar el informe antes de que
contabilidad cargue el snapshot del mes siguiente), los 6 tokens proyectados
saldrían vacíos (`format_euro(None)` → `""`). No rompe; el slide queda en
blanco. Conviene que contabilidad cargue siempre el mes siguiente.

---

## Constantes hardcodeadas (a mover a parametros_sede_mes)

Valores que hoy están fijos en código pero deberían ser parámetros por sede/mes:

| Constante | Valor actual | Razón futura |
|---|---|---|
| `OBJETIVO_RENTABILIDAD` | `"20 %"` | Puede variar por sede o cambiar anualmente |
| `INVERSION_TECNOLOGICA_PROVISIONAL` | `"27k€"` | Origen sin confirmar (P-21) |
| `N_DIRECTORES` | `2` (Valencia) / `1` (Alicante) | Si entra/sale un director (slide 9 reparto). Vive en cada calculator. |
| `SUELDO_FIJO_DIRECTOR` | `2.666,67 €` (Valencia) / `1.933,73 €` (Alicante) | Si cambia el sueldo bruto. Vive en cada calculator. |
| `PROMOCIONES_OBRA_NUEVA_EXCLUIR` | `('%victoria kent%', 'urb.%santa%b_rbara%')` (Valencia) | Cuando entre una promoción nueva. Decisión pendiente: migrar a tabla `promociones_obra_nueva`. |

> **Resueltas:**
> - `TRAMO_COMISION_PCT/LABEL` (P-22, 2026-05-20): se calcula dinámicamente
>   desde `pagos_directores`.
> - `SUBTOTAL_COMISION_ATRASOS_PROVISIONAL` (P-23, 2026-05-21): se calcula
>   dinámicamente desde `comisiones_atrasos_directores`.

---

## Decisiones arquitectónicas relacionadas

- **Colores condicionales declarativos**: el calculator decide verde/rojo según signo de cada variación numérica antes del formateo. Documentado en `memory/project_decision_colores_declarativos.md`.
- **Capa de formato**: Postgres devuelve números crudos; `formatter.py` aplica locale es_ES manualmente (sin dependencia de `locale` del SO). Documentado en `memory/project_capa_formato.md`.
- **Reproducibilidad histórica**: cuando se implemente tabla `reportes_generados`, guardar snapshot del payload enviado al servicio para poder regenerar informes pasados con los datos de su momento.

---

## Discrepancias conocidas

Ver **P-18** en [`PENDIENTES.md`](../PENDIENTES.md): los datos de `ventas_comerciales` cuentan menos operaciones que los cuadros agregados manuales del Sheet. Afecta a varios tokens del slide 2 y slide 3. Pendiente validar con contabilidad si faltan operaciones por migrar o si el cuadro manual tiene errores.

---

## Aprendizajes técnicos (sesiones de debug)

Notas no obvias del comportamiento del sistema, descubiertas resolviendo bugs.
Quedan aquí para no repetir el debug en el futuro.

### 1. Diagnóstico de tokens vacíos en el PDF (orden de descarte)

Cuando un token sale vacío o literal en el PDF, **hay 3 causas posibles** y
hay que descartarlas en este orden:

1. **Token partido en `textRun`s** de la plantilla (Slides los fragmenta al
   editar). El validador `check_tokens.py` NO lo detecta. Síntoma: el `{{`
   y el `}}` están en runs distintos.
2. **El calculator no produce el token**. El validador SÍ lo marca (🔴).
3. **El dato llegó NULL de la ingesta** (ej. cambio de etiqueta en el Sheet
   contable, ver P-27). El validador NO lo ve. **Verificar siempre con un
   `SELECT` directo** a la tabla origen cuando 1 y 2 están descartadas.

### 2. Datos faltantes en `ventas_comerciales` ≠ bug de query

Patrón recurrente (P-20 obra nueva, P-28 condicionadas): cuando un total de
`ventas_comerciales` no cuadra con el original Y la query está validada,
**sospechar primero de datos faltantes en la ingesta** antes que del código.
Comprobar con `SELECT` de los inmuebles esperados. Ejemplos resueltos:
- Slide 5 Santa Bárbara: desfase 587k vs 505k → operaciones ausentes.
- Slide 6 condicionadas: `Paseo Alameda 41`, `C. Doctor Villena 20` ausentes.

### 3. Colorea por VALOR de texto, no por nombre de token

`apply_color_overrides` busca shapes **por el valor de texto** que tiene el
token tras `_replace_tokens`, no por el nombre del token. Si dos tokens
distintos (`var_reservas_mom` en slide 2, `var_reservas_mom_observacion` en
slide 11) tienen el **mismo valor visible** (`-13,9 %`), la búsqueda los
encuentra en AMBOS slides y el último override aplicado gana.

**Fix aplicado:** los tokens `_observacion` llevan un sufijo invisible
`​` (zero-width space). Visualmente idéntico, técnicamente distinto.
No tocar ese sufijo en `calculator.py`.

Ver también `feedback_color_caja_unica.md` en memoria.

### 4. Variaciones entre porcentajes: puntos porcentuales vs variación relativa

`_variacion(a, b)` da `(a-b)/b` = **variación relativa**. Correcto cuando
ambos lados son importes (ej. `reservas_actual` vs `reservas_mes-1`).

Pero **cuando ambos lados ya son porcentajes** (ej. `rentabilidad_operativa_pct`
de abril vs marzo), `_variacion` produce un número confuso. Para rentabilidades
hay que hacer **resta directa** (diferencia en puntos porcentuales):
`(0.3038 - 0.3099) = -0.0061` → `-0,61 %`. NO `_variacion` (daría `-1,97 %`).

Aplicado en `var_rentab_mom` (slide 2 card 4) 2026-05-20.

### 5. Slides API: posicionar shapes dentro de `elementGroup`s

`pageElements` solo da el primer nivel del slide. Si un shape vive dentro de
un `elementGroup`, hay que caminar `el["elementGroup"]["children"]`
recursivamente.

Además, la `translateY` de un shape dentro de un grupo es **relativa al
grupo**, no absoluta a la página. Para obtener la Y absoluta hay que
**componer**: `Y_abs = parent.translateY + child.translateY`.

Función helper `_walk_text_shapes` en `app/break_even_chart.py`.

### 6. Posicionar shapes ANTES de `_replace_tokens`

Cualquier paso que necesite identificar shapes por sus tokens `{{...}}`
literales (ej. el posicionamiento del marcador break even) tiene que ir
**ANTES** de la llamada a `_replace_tokens`. Una vez sustituidos los
tokens por sus valores formateados, no hay forma de identificar el shape
("232.188 €" puede ser cualquier cosa).

Orden de pasos en `generator.generate_report`:
1. `_copy_template`
2. **`apply_breakeven_marker_position`** ← antes que replace
3. `_replace_tokens`
4. `apply_color_overrides`
5. Insertar gráfico slide 3
6. `_export_pdf_bytes`

### 7. `updatePageElementTransform`: usar `ABSOLUTE`

Por defecto `applyMode = "RELATIVE"` aplica el transform **encima del
actual**. Para idempotencia (poder re-ejecutar sin acumular desplazamientos),
usar `applyMode = "ABSOLUTE"`: el transform final es exactamente el que
envías.

### 8. Tabla `pago_agentes`: `fecha_arras_sin_condic` y "PONER FECHA"

La columna `fecha_arras_sin_condic` en `pago_agentes` es de tipo `DATE`. Si
en el Sheet origen un comercial escribe `"PONER FECHA"` como placeholder
(operación aún sin fecha definida), la ingesta n8n castea ese texto a
**`NULL`** (no parseable como fecha).

El slide 7 filtra `fecha_arras_sin_condic IS NOT NULL` para excluir esas
filas (no están listas para liquidar). Documentado 2026-05-19.

### 9. Constantes hardcoded vs `pagos_directores`

El tramo de comisión (slide 1 y 9) era una constante `0.03` hardcoded. Pero
realmente **suma los porcentajes de los directores del mes**. Al haber una
tabla `pagos_directores` con una fila por director y mes, el código ahora
lee y suma esos `porcentaje` dinámicamente.

Beneficio colateral: funciona con N directores variable sin tocar código.
Si entra/sale un director, basta con añadir/quitar filas en la tabla.

### 10. Guard explícito vs PDF con dato 0 silencioso

Lección de P-27 (ingesta cargó NULL silenciosamente y el PDF salió con
huecos). Política: si **falta un dato crítico** que sin él el informe queda
incoherente, **lanzar `ValueError` explícito** en el calculator en lugar de
generar un PDF con `0 €` que pase desapercibido.

Aplicado en:
- `_query_contable` → `cont_actual is None`: `raise ValueError("Carga primero contabilidad_mensual")`.
- `_query_tramo_comision` → si no hay filas: `raise ValueError("Carga primero pagos_directores")`.

### 11. `n_max` en `LIST_SPECS` debe coincidir con slots reales de plantilla

`expand_lists(payload, LIST_SPECS)` emite N pares `prefix_i_field` para
i=1..n_max. Si la plantilla tiene **más slots que n_max**, los slots extra
quedan como **tokens literales** en el PDF (`{{condicionada_13_nombre}}`).
**No genera warning** porque "tokens no encontrados" mira el sentido opuesto
(payload con tokens que plantilla no tiene).

Hay que mantener `n_max` ≥ número de slots de la plantilla. Slides actuales:
- `ventas_pendientes`: n_max=21 (slots 1..21 en plantilla).
- `operaciones_condicionadas`: n_max=22 (slots 1..22 en plantilla).
- `cobros_pendientes`: n_max=26.
- `obras_nuevas`: n_max=4.

### 12. Negocio de alquileres nació en 2026

Las tablas `resumen_mensual_alquileres` y `resumen_mensual_alquiler_senales`
solo tienen filas para 2026 porque alquileres no existía como producto en
2025. Eso hace que el YoY de contratos sume solo ventas para el año
anterior — **es el dato correcto**, no una asimetría a corregir.
