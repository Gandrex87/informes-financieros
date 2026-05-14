# Pendientes — Próximas iteraciones

Estado a **2026-05-14** tras cerrar varios hitos:
- **Sprint 1** ✅: tokenización completa de los 12 slides + pipeline funcional con datos mock locales.
- **Sprint 2** ✅: servicio FastAPI + dockerización + integración con n8n local. Validado end-to-end: n8n llama al servicio en red Docker compartida y recibe el PDF.
- **Sprint 3** ✅: colores condicionales (P-04) + integración Postgres real para slides 1, 2 y 3 (lado izquierdo).
- **Sprint 4** ✅: documentación (`docs/MAPEO_DATOS.md`) + gráfico del slide 3 (P-05) + slide 4 completo (KPIs + pipeline pendiente).
- **Sprint 5** ✅: slide 5 completo (pipeline ventas + obra nueva + alquileres + totales agregados).

Próximos pasos: extender calculator a slides 6-12, validar P-18 y P-20 con contabilidad, operacionalización (cuenta corporativa).

---

## ✅ Hecho

### Plataforma técnica
- Pipeline Slides → PDF funcional (OAuth de usuario, Drive API export).
- 12 slides tokenizados con ~120 tokens + 6 listas variables (`pipeline_alquiler`, `comisiones_atrasos`, `operaciones_condicionadas`, `cobros_pendientes`, `ventas_pendientes`, `obras_nuevas`).
- Helper `slots()` + `expand_lists()` para manejar listas de longitud variable.
- Servicio FastAPI con endpoints `GET /health`, `POST /generar-informe` (payload completo) y `POST /generar-desde-db` (lee Postgres internamente).
- Dockerfile + docker-compose con healthcheck y volumen de credenciales.
- Conexión a la red de n8n (`sesion-idealista_default`) para que llame al servicio por nombre de contenedor (`http://informes-financieros-api:8000`).
- Workflow n8n probado tanto con payload completo como con `/generar-desde-db` ({sede, anyo, mes}).
- Datos mock realistas (`data/mock_abril_2026.json`) con el contenido completo del informe abril 2026.

### Colores condicionales (P-04 — cerrado)
- Paleta corporativa en `app/colors.py`.
- Helpers `find_text_locations()` + `apply_color_overrides()` en `app/color_helpers.py`.
- Soporte para shapes sueltos y celdas de tablas nativas (`cellLocation`).
- Convención declarativa: el cliente envía `_color_overrides` en el payload; el servicio aplica sin interpretar valores.
- Aplicado en slides 2, 3, 4, 8, 11.

### Integración Postgres (slides 1, 2, 3 y 4 completos)
- Schema `informes_financieros.contabilidad_mensual` con PK `(sede, escenario, anyo, mes)`.
- Workflow n8n carga el cuadro contable del Sheet (rango `B62:V107`) con upsert `ON CONFLICT`.
- Calculator (`app/calculator.py`) lee de `ventas_comerciales` + `contabilidad_mensual` y compone el payload.
- Formatter (`app/formatter.py`) con locale es_ES manual (sin dependencia del SO): euros, porcentajes, deltas, flechas `▲`/`▼` automáticas, meses.
- Color overrides emitidos automáticamente por el calculator según signo de cada variación.
- Discrepancias documentadas en P-18.

### Gráfico del slide 3 (P-05 — cerrado)
- `app/chart_generator.py` con matplotlib: gráfico de barras agrupadas Reservas vs Contratos.
- `app/image_helpers.py`: sube PNG temporal a Drive con permiso público, `replaceAllShapesWithImage`, cleanup.
- Paleta corporativa: `#F6B26B` (melocotón) para Reservas, `#7AB8E5` (azul claro) para Contratos. Fondo transparente. Etiquetas del color de su barra.
- Token placeholder en plantilla: `{{grafico_reservas_arras}}`.
- Datos del payload en clave especial `_chart_reservas_arras` (no es token, no pasa por `replaceAllText`).

### Slide 4 — Gestión de alquileres
- Queries especializadas para alquileres en el calculator (`_query_alquileres_mes`, `_query_pipeline_alquileres`).
- Convención: `fecha_arras` representa fecha de firma del contrato para alquileres (la ingesta hace el mapeo desde "FECHA CONTRATO").
- Pipeline pendiente excluye estados `'SI'` (ya firmadas) y `'CAÍDA - 0'` (con tilde, etiqueta exacta de la BD). Ordenado por importe descendente.
- Helper `_limpia_inmueble_alq()` para quitar el prefijo `ALQ.-` del nombre.
- 2 nuevos color overrides condicionales (`var_reservas_alquiler_mom`, `var_contratos_alquiler_mom`).

### Slide 5 — Pipeline Q2 (ventas + obra nueva + alquileres)
- 3 sub-secciones: pipeline de ventas (3 columnas, `n_max=15`), obra nueva (2 promociones agrupadas, `n_max=4`), alquileres (reusa `pipeline_alquiler` del slide 4).
- Queries nuevas en calculator: `_query_pipeline_ventas()`, `_query_obra_nueva()`.
- Pipeline ventas: excluye obra nueva conocida (`%victoria kent%` y `urb.%santa%b_rbara%`) pero NO `urb.%` genérico (hay ventas normales con ese prefijo, ej. `Urb. Loma de Caballeros 3`).
- Obra nueva: filtra por `arras_firmadas IS DISTINCT FROM 'CAÍDA - 0'` (incluye NULL y todos los estados activos). Agrupa con `CASE WHEN` por promoción.
- DISTINCT defensivo contra P-19 en pipeline ventas.
- Totales agregados: `total_ventas_pipeline`, `total_obra_nueva`, `total_pipeline` (suma de los tres), `n_ops_pipeline`.
- Discrepancia P-20 documentada (Altos de Santa Bárbara da 587k vs 505k del PDF).

### Documentación
- `docs/MAPEO_DATOS.md`: tabla por slide con tokens, fuentes, fórmulas y estado.
- `PENDIENTES.md` (este documento).
- Memoria del proyecto en `~/.claude/projects/.../memory/` con decisiones arquitectónicas.

---

## 🟡 Discrepancias en observación — verificar con contabilidad

### P-20 · Diferencia importe obra nueva "Altos de Santa Bárbara"

Calculator devuelve **587.450 €** para la promoción `Urb. Altos de Santa Bárbara` en slide 5 (21 operaciones agregadas). El PDF original de abril 2026 mostraba **505.850 €**. Diferencia ~82k €.

La promoción `C. VICTORIA KENT` cuadra exactamente (94.240 €).

**Datos en BD confirmados correctos** según validación con el cliente.

**Hipótesis:**
- El PDF original podría haber filtrado por un subconjunto (ej. solo las firmadas en el mes en curso, solo las cobradas, etc.) que aún no contemplamos en el calculator.
- O el cuadro manual original tenía operaciones desactualizadas.

**Acción:** preguntar a contabilidad qué criterio aplica para el "total acumulado" de cada promoción de obra nueva en el slide 5. Cuando se aclare, ajustar el filtro en `_query_obra_nueva()`.

---

### P-19 · Duplicados aislados en `ventas_comerciales`

Detectados 2 inmuebles con filas duplicadas idénticas (mismo `fecha_senal`, `honorarios_totales`, asesor; solo difieren en `id` y `created_at`):

- `C. Nicolas David 13` (fecha_senal 2026-05-08, 11.700 €) — duplicado.
- `C. Poeta Mas y Ros 72` (fecha_senal 2026-05-08, 9.157,23 €) — duplicado.

**Hipótesis:** re-ejecución puntual de la ingesta sin `ON CONFLICT` que evite duplicados.

**Mitigación aplicada (parche temporal):** las queries de pipeline en `calculator.py` para slide 5 usan `DISTINCT ON` o `GROUP BY` para no contar duplicados.

**Acciones recomendadas a futuro:**
1. Borrar manualmente las 2 filas duplicadas (`id` mayor).
2. Añadir `UNIQUE (inmueble, fecha_senal, honorarios_totales)` o similar como constraint.
3. Modificar la ingesta n8n para usar `ON CONFLICT DO UPDATE` (igual que hicimos en `contabilidad_mensual`).

**No bloqueante:** afecta solo a este conteo de pipeline; el calculator lo neutraliza vía DISTINCT.

---

### P-18 · Diferencias calculator vs PDF de abril 2026

Tras integrar el calculator (lectura Postgres), 7 campos del slide 2 no cuadran con el PDF de abril 2026 que se generó a mano:

| Campo | Manual (PDF) | Calculator | Dif |
|---|---|---|---|
| `reservas_totales` | 547.139 € | 541.039 € | -6.100 € |
| `reservas_mes_anterior` | 585.720 € | 580.930 € | -4.790 € |
| `contratos_firmados` | 510.842 € | 500.266 € | -10.576 € |
| `n_ops_contratos` | 41 | 38 | -3 ops |
| `contratos_año_anterior` | 388.808 € | 329.950 € | -58.858 € |

Diferencias consistentes: `ventas_comerciales` cuenta MENOS que los cuadros manuales del Sheet.

**Hipótesis:**
- Operaciones faltantes en la migración a `ventas_comerciales`.
- Alquileres registrados en otra tabla.
- Filtros distintos (por ejemplo, condicionadas).

**Acción:** validar con contabilidad antes de generar el primer informe real. Mostrar los números del calculator + diferencia y preguntar dónde están las operaciones que faltan.

**Lo que SÍ se ha confirmado correcto** (no requiere acción):
- Pequeñas diferencias por redondeo en mock (margen_bruto, rentabilidad_op, resultado_op, ingresos_totales).
- `var_rentab_mom` del mock estaba mal calculada aritméticamente.

---

## 🔥 Bloqueantes / Decisiones externas

### P-01 · Migración a cuenta corporativa Google
**Estado:** pendiente confirmación.

Hoy el desarrollo va con `andresrsalamanca@gmail.com` (cuenta personal, 15 GB, sin Shared Drives). Antes de producción hay que migrar a una cuenta corporativa de Lion Capital.

- Candidato: `sistemas@lioncapitalg.com` (cuenta del jefe, posiblemente Google Workspace real).
- Descartado por ahora: `aroncancio@lioncapitalg.com` parece ser Microsoft 365 (la plantilla original venía de SharePoint).

**Tareas cuando se resuelva:**
1. Verificar si la cuenta destino es Workspace real (test en accounts.google.com).
2. Crear nuevo proyecto GCP + Service Account (preferible) o OAuth client.
3. Si Workspace: crear **Shared Drive** corporativa, mover plantilla, dar permiso a la service account.
4. Copiar plantilla a la propiedad corporativa.
5. Actualizar `SLIDES_TEMPLATE_ID` y mecanismo de credenciales en `.env`.
6. Reejecutar tests para validar.

**Bloqueante para:** despliegue real en producción (no para seguir desarrollando en local).

**Caso borde mientras tanto:** la app OAuth está en modo "Testing" en GCP. Los `refresh_token` caducan cada 7 días en ese modo. Mientras sigamos con cuenta personal, hay que regenerar `credentials/token.json` semanalmente. Migrar a Service Account + Shared Drive lo resuelve definitivamente.

---

### P-02 · Validar tratamiento de fondos tenues en slots con diseño
**Estado:** decisión provisional aplicada en todos los slides con listas variables. Pendiente confirmar con diseño.

En slides 4, 5, 6, 7, 9 (todos los que tienen listas variables), los slots dinámicos no llevan fondo blanco tenue cuando exceden los slots "garantizados". Provoca asimetría visual cuando hay muchos items.

**Decisión provisional:** fondo solo en slots garantizados; planos en los extras.

**Alternativa rechazada por coste/beneficio:** fusionar fondo+texto en un mismo shape y ocultar background via API. Probado en slot 7 del slide 4, requiere código Python extra y reaplicar relleno manualmente caja por caja.

**Acción:** consultar con diseño. Si la asimetría no es aceptable, retomar fusión + helper que oculta fondos vacíos.

---

### P-11 · Datos reales desde Google Sheets de contabilidad
**Estado:** pendiente que contabilidad indique dónde están los datos.

Esperando referencias a las hojas con:
- Operaciones de venta y alquiler (todas las columnas: fecha, importe, propiedad, estado, tipo).
- Cobros pendientes.
- Comisiones cobradas de meses anteriores.
- Costes fijos por mes / objetivos de facturación.
- Operaciones condicionadas (con flag de riesgo).

**Bloqueante para:** P-08 (Postgres) y P-15 (n8n con datos reales).

---

## 🚧 Funcionalidad pendiente

### P-07 · Generación determinista de la narrativa
**Estado:** hardcoded en el JSON mock. Decidir patrón antes de integrar Postgres.

Slide 8 (Break Even abril) tiene un párrafo narrativo que valora cualitativamente los resultados.

**Camino recomendado:** templating determinista en Python con f-strings + umbrales para adjetivos cualitativos ("ampliamente", "cómodamente", "ligeramente").

**Alternativas descartadas:** Jinja2 (sobre-ingeniería), LLM puro (no reproducible, no auditable en documento financiero), LLM con guardarrails (postergable a futuro).

**Acción:** escribir `app/narrative.py` con función `narrativa_break_even(ingresos, break_even, arras_firmadas, mes_siguiente)`.

**Prerequisito:** P-08 (Postgres con números crudos) para tener los datos a evaluar contra umbrales.

---

## 🏗️ Arquitectura / Infraestructura

### P-08 · Migrar JSON mock a Postgres + capas calculator/formatter
**Estado:** datos hoy en `mock_abril_2026.json`. El servicio recibe ya-formateados. Pendiente diseñar el esquema real.

**Arquitectura objetivo:**
```
Postgres (NUMERIC, DATE) → calculator.py (KPIs + variaciones) → formatter.py (locale es_ES) → API → Slides
```

**Decisiones de modelado pendientes:**
1. Tabla `operaciones` unificada con columna `tipo` (venta/alquiler) vs tablas separadas → recomendación: unificada.
2. Enum `estado` (señal/arras/cobrado/condicionada) vs columnas booleanas → recomendación: enum.
3. Tabla `reportes_generados` con snapshot del payload enviado + ID de la plantilla usada (para reproducibilidad histórica).
4. Comparativas YoY: requieren ≥13 meses de histórico. Plan provisional: carga inicial manual de los últimos 13 meses, o período de transición con dato YoY introducido a mano.

**Acción:** sesión de modelado dedicada cuando lleguen los datos reales (P-11).

---

### P-09 · Multi-sede (Castellón y Alicante)
**Estado:** diseño contemplado desde el inicio, no implementado.

v1 = Valencia. v2 = Castellón + Alicante.

**Implicaciones:**
- El servicio ya acepta `sede` como campo del payload (sin lógica especial todavía).
- `SLIDES_TEMPLATE_ID` por sede: o **una plantilla compartida** (tokens `{{sede}}` resuelven la diferencia) o **tres plantillas distintas** si el branding varía por ciudad.
- Postgres con columna `sede` en todas las tablas relevantes.
- `parametros_sede` para costes fijos, objetivos, número de directores, sueldo fijo, tramos de comisión.

---

### P-15 · Workflow n8n con datos reales de Sheets
**Estado:** workflow de prueba con payload hardcodeado en nodo Code funciona. Pendiente sustituir por nodos reales.

**Flujo objetivo (cuando exista P-11 + P-08):**
1. Trigger (cron mensual o manual con parámetros `sede`, `mes`, `año`).
2. Nodos Google Sheets para leer las hojas de contabilidad.
3. Nodo Postgres para insertar/actualizar staging.
4. Nodo HTTP llamando al servicio Python (puede ser un endpoint nuevo `/generar-desde-postgres?sede=X&mes=Y`).
5. Distribución del PDF: email a directores, subir a Drive, notificar a Slack/Teams.

**Alternativa parcial inmediata:** workflow que **lea el JSON mock desde un nodo Sheets de prueba** y lo envíe al servicio, validando el flow real Sheets → API sin esperar a Postgres.

---

### P-16 · Despliegue al servidor de producción
**Estado:** funciona en local. Pendiente subir al servidor de Lion.

**Camino:**
1. Push del código a git.
2. Pull en el servidor.
3. Subir credentials/ (oauth_client.json + token.json) por canal seguro (NO git).
4. `.env` en el servidor con `SLIDES_TEMPLATE_ID` y, opcionalmente, `DRIVE_FOLDER_ID`.
5. `docker compose up -d --build`.
6. Conectar a la red de Traefik si se desea exponer por HTTPS, o dejarlo solo accesible para n8n por red interna.

**Bloqueante recomendado:** resolver P-01 antes, para no migrar credenciales dos veces.

---

## 🧪 Calidad / Mantenimiento

### P-12 · Validación de tokens contra plantilla
**Estado:** AVISO en runtime cuando un token del JSON no se encuentra en la plantilla. Suficiente, pero no proactivo.

**Mejora:** comando `python scripts/check_tokens.py` que:
1. Lee todos los tokens `{{...}}` de la plantilla via API.
2. Lee todas las keys del JSON mock + listas expandidas.
3. Reporta: tokens en plantilla sin equivalente en datos (rotura segura) y tokens en datos sin equivalente en plantilla (gasto inútil).

Útil cuando se editan plantilla y datos en paralelo.

---

### P-13 · Tests automáticos
**Estado:** ninguno.

- Unitarios: `slots()`, `expand_lists()`, futuros `formatter.py`, futuros `narrative.py`.
- Integración: mock de la Slides API (validar estructura de los batchUpdate requests).
- E2E opcional contra plantilla de test real (gasta cuota API, manual en CI).

---

### P-14 · Logging estructurado y observabilidad
**Estado:** logging básico configurado, formato texto plano.

Mejoras para producción:
- Logging estructurado (JSON) para que n8n / log aggregator parseen.
- Métricas: tiempo de cada paso (copy, replace, export). Detectar regresiones de performance.
- Endpoint `GET /metrics` (Prometheus) opcional.

---

### P-17 · Seguridad del endpoint en producción
**Estado:** sin autenticación. Solo OK en local.

Cuando se exponga el servicio (aunque sea solo en red interna):
- API Key estática en header `X-API-Key`, comparada en un dependency de FastAPI.
- Variable de entorno `API_KEY` en `.env`.
- n8n lo envía en cada request.

Bajo coste de implementación, alto valor antes de exponer públicamente.

---

## 📋 Resumen de prioridad para próximo sprint

Orden sugerido (cada uno desbloquea o aporta valor visible):

1. **Extender calculator a slide 6** (operaciones condicionadas) — siguiente en orden visual.
2. **Extender calculator a slide 8** (Break Even abril) — datos ya en `contabilidad_mensual`, queda solo mapear.
3. **Extender calculator a slide 10** (Break Even mayo proyectado) — mismo patrón que slide 8.
4. **P-18 y P-20** — validar discrepancias con contabilidad (acción externa, en paralelo).
5. **P-07** — narrativa determinista del slide 8 (cuando lleguemos a ese slide).
6. **P-12** — comando de validación de tokens (productividad, opcional).
7. **Calculator slides 7, 9** — los más complejos (cobros pendientes, comisiones con atrasos).
8. **P-01** — migración cuenta corporativa (cuando se confirme).
9. **P-15** — workflow n8n con datos reales (depende del calculator completo).
10. **P-17** — API Key antes de pasar a producción.
11. **P-16** — despliegue al servidor.
12. **P-09, P-13, P-14** — multi-sede, tests, observabilidad (pulido).
