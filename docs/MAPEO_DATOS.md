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

## Slides 7-12 — Pendientes de integrar

Listado resumido. Cada uno tendrá su sección detallada cuando se ataque.

| Slide | Contenido | Fuentes esperadas | Notas |
|---|---|---|---|
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
