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
| Comisiones cobradas del mes (ventas y alquileres) | `resumen_mensual_arras__sin_condicion`, `resumen_mensual_alquileres` | Tablas resumen mensual, una fila por mes |
| Reservas / contratos del mes (importes y conteos) | `ventas_comerciales` filtrado por `fecha_senal`/`fecha_arras` en el mes | El filtro es por fecha del evento, que no cambia |
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

### Lado derecho — Gráfico de barras ✅

Gráfico de barras agrupadas: 3 períodos (`Abr '25`, `Mar '26`, `Abr '26`) × 2 series (Reservas, Contratos Firmados).

**Estado:** ✅ integrado.

**Implementación:**
- Generado con matplotlib en `app/chart_generator.py` (función `generar_grafico_reservas_arras`).
- Paleta: barras Reservas `#F6B26B` (melocotón), barras Contratos `#7AB8E5` (azul claro). Fondo transparente. Etiquetas del color de su barra.
- El PNG se sube temporalmente a Drive, se sustituye en la plantilla con `replaceAllShapesWithImage` apuntando al token `{{grafico_reservas_arras}}`, y se borra de Drive tras exportar el PDF.
- Helpers: `app/image_helpers.py` (upload, replace, cleanup).

**Datos:** los 6 valores (3 períodos × 2 series) vienen del calculator en el campo especial `_chart_reservas_arras` del payload (no es un token, no pasa por `replaceAllText`).

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

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `reservas_alquiler` | VC | `SUM(honorarios_totales) WHERE alquiler AND fecha_senal en el mes` | ✅ |
| `var_reservas_alquiler_mom` | derivado | `(reservas_alq_actual - reservas_alq_mes-1) / reservas_alq_mes-1` con flecha `▲`/`▼` | ✅ |
| `n_ops_reservas_alquiler` | VC | `COUNT(*) WHERE alquiler AND fecha_senal en el mes` | ✅ |
| `delta_ops_reservas_alquiler` | derivado | `n_ops_actual - n_ops_mes-1` con sufijo `op.` | ✅ |

### Tarjeta · Contratos firmados

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `contratos_alquiler` | VC | `SUM(honorarios_totales) WHERE alquiler AND fecha_arras en el mes AND arras_firmadas='SI'` | ✅ |
| `var_contratos_alquiler_mom` | derivado | con flecha `▲`/`▼` | ✅ |
| `n_ops_contratos_alquiler` | VC | `COUNT(*)` con mismo filtro que `contratos_alquiler` | ✅ |
| `delta_ops_contratos_alquiler` | derivado | con sufijo `ops.` | ✅ |

### Pipeline pendiente de firma (lista variable)

Operaciones de alquiler que se han señalizado pero aún no han firmado contrato.
**Sin filtro de mes** — incluye señalizaciones de meses anteriores que siguen vivas.

**Filtro:**
```sql
WHERE inmueble LIKE 'ALQ.-%'
  AND fecha_senal IS NOT NULL
  AND (arras_firmadas IS NULL OR arras_firmadas NOT IN ('SI', 'CAÍDA - 0'))
```

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
(15 slots totales con `n_max=15`).

**Filtro:**
```sql
WHERE inmueble NOT LIKE 'ALQ.-%'         -- no alquileres
  AND arras_firmadas = 'NO'              -- pendiente
  AND inmueble NOT ILIKE '%victoria kent%'           -- excluye obra nueva
  AND inmueble NOT ILIKE 'urb.%santa%b_rbara%'       -- excluye obra nueva
```

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

Slots: `venta_pend_N_nombre` y `venta_pend_N_importe` (N=1..15) via `LIST_SPECS`.

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

### Discrepancia conocida

Los totales del calculator no coinciden exactamente con el PDF original de abril 2026:
- Obra nueva Victoria Kent: calculator `94.240 €` vs PDF `94.240 €` ✅
- Obra nueva Altos Sta Bárbara: calculator `587.450 €` vs PDF `505.850 €` ⚠️

La diferencia de Santa Bárbara (~82k €) está pendiente de validar con
contabilidad. Los datos en BD están correctos según el cliente, pero no
sabemos qué subconjunto contemplaba el PDF original. Ver P-20 en
`PENDIENTES.md`.

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

Lista variable, una fila por operación. Slots `condicionada_N_nombre` + `condicionada_N_importe` con `n_max=12` via `LIST_SPECS`.

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
| `var_reservas_mom_observacion` | derivado | Mismo valor que `var_reservas_mom` del slide 2, token distinto para color independiente | ✅ |
| `var_contratos_mom_observacion` | derivado | Mismo valor que `var_contratos_mom` del slide 2, token distinto para color independiente | ✅ |
| `rentabilidad_op_signed` | CM | `format_pct_signed(rentabilidad_operativa_pct)` — siempre con `+`/`-` explícito | ✅ |
| `volumen_riesgo_short` | derivado | `format_euro_compacto(volumen_riesgo)` — formato `135,9 k €` (sufijo k/M) | ✅ |
| `mes_siguiente_capitalizado` | derivado | Nombre del mes siguiente capitalizado (`Mayo`, `Junio`...). Usado en la narrativa "facturación de X será severo" | ✅ |

**Por qué tokens `_observacion` separados:**

El mecanismo de colores busca shapes por texto del valor. Si `var_reservas_mom` con valor `-6,6 %` apareciera en slide 2 (color rojo por negativo) y slide 11 (color amarillo en columna observación), no se podrían distinguir. Tokens separados con el mismo valor pero distinto nombre resuelven el conflicto.

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
| `total_pendiente_cobro` | constante provisional | `"204.392 €"` hardcoded en `TOTAL_PENDIENTE_COBRO_PROVISIONAL`. La fuente real está en slide 7, bloqueado por dependencia de datos externos. | ⏳ provisional |
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
INVERSION_TECNOLOGICA_PROVISIONAL = "27k€"  # pendiente contabilidad
TOTAL_PENDIENTE_COBRO_PROVISIONAL = "204.392 €"  # pendiente fuente slide 7
```

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
| `tramo_comision` | constante | `"3 %"` (`TRAMO_COMISION_LABEL`). Pendiente escala por volumen (P-22). | ⏳ provisional |

### Parte A — Firmado y cobrado en el mes ✅

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `ventas_cobradas_mes` | `resumen_mensual_arras__sin_condicion.cobradas` | filtro `anio` + `mes` (string 3 letras). Solo Valencia. | ✅ |
| `comision_ventas_mes` | derivado | `ventas_cobradas_mes × TRAMO_COMISION_PCT` (0.03) | ✅ |
| `alquileres_cobrados_mes` | `resumen_mensual_alquileres.honorarios_cobrados` | filtro `anio` + `mes`. OJO: esta tabla usa `'sept'` (4 letras) para septiembre, la otra usa `'sep'`. | ✅ |
| `comision_alquileres_mes` | derivado | `alquileres_cobrados_mes × 0.03` | ✅ |
| `subtotal_comision_mes` | derivado | `comision_ventas_mes + comision_alquileres_mes` | ✅ |

### Parte B — Cálculo final ✅ (con constante provisional)

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `subtotal_comision_atrasos` | constante provisional | `SUBTOTAL_COMISION_ATRASOS_PROVISIONAL = 1021.89`. Hardcoded del mock hasta confirmar fuente de la Parte C (P-23). | ⏳ provisional |
| `total_comision_repartir` | derivado | `subtotal_comision_mes + subtotal_comision_atrasos` | ✅ |
| `comision_variable_por_director` | derivado | `total_comision_repartir / N_DIRECTORES` (N=2) | ✅ |
| `sueldo_fijo_director` | constante | `SUELDO_FIJO_DIRECTOR = 2666.67` (bruto mensual, provisional) | ⏳ provisional |
| `total_por_director` | derivado | `comision_variable_por_director + sueldo_fijo_director` | ✅ |

**Constantes del slide 9 — dónde cambiarlas (cabecera de `calculator.py`):**

| Constante | Cambiar cuando... |
|---|---|
| `N_DIRECTORES` | entre o salga un director (marcado con `>>> ... <<<` en código) |
| `SUELDO_FIJO_DIRECTOR` | cambie el sueldo fijo bruto |
| `TRAMO_COMISION_PCT` / `TRAMO_COMISION_LABEL` | contabilidad confirme la escala de tramos (P-22) |
| `SUBTOTAL_COMISION_ATRASOS_PROVISIONAL` | se confirme la fuente de "COBRADO DE MESES ANTERIORES" (P-23) |

Buscar `PROVISIONAL` o `>>>` en el código localiza todos estos puntos.

### Parte C — Tabla "COBRADO DE MESES ANTERIORES" ⏳

| Token | Fuente | Cálculo / nota | Estado |
|---|---|---|---|
| `comisiones_atrasos` (lista, `n_max=10`) | sin confirmar | Tabla de operaciones de meses anteriores cobradas este mes (nombre, mes origen, tramo, importe) | ⏳ pendiente fuente (P-23) |

Cuando se confirme la fuente, `subtotal_comision_atrasos` pasará a calcularse
como la suma de esta lista en lugar de la constante provisional.

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
WHERE pte_facturar ~ '^[0-9]+\.?[0-9]*$'   -- numérico puro (descarta 'CAÍDA')
  AND CAST(pte_facturar AS NUMERIC) > 1     -- umbral anti-basura-float (P-24)
ORDER BY importe DESC
```

El umbral `> 1` descarta basura de coma flotante de la ingesta
(`'0.21000000000003638'` y similares). Ver P-24.

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

## Slides 8, 10 — Pendientes de integrar

Listado resumido. Cada uno tendrá su sección detallada cuando se ataque.

| Slide | Contenido | Fuentes esperadas | Notas |
|---|---|---|---|
| 8 | Break Even abril | CM (break_even, ingresos_margen_*, ebitda) + narrativa | Narrativa templating determinista (P-07) |
| 10 | Break Even mayo (proyección) | CM mes+1 (proyectados) | Mismo patrón que slide 8 sin narrativa |

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
