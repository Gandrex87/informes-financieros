# Pendientes — Próximas iteraciones

Estado a **2026-05-12** tras cerrar dos sprints:
- **Sprint 1** ✅: tokenización completa de los 12 slides + pipeline funcional con datos mock locales.
- **Sprint 2** ✅: servicio FastAPI + dockerización + integración con n8n local. Validado end-to-end: n8n llama al servicio en red Docker compartida y recibe el PDF.

Próximos sprints deberían enfocarse en (a) sustituir el mock por datos reales, (b) decisiones que mejoren fidelidad visual (colores condicionales, gráfico), (c) operacionalización (cuenta corporativa, observabilidad).

---

## ✅ Hecho

- Pipeline Slides → PDF funcional (OAuth de usuario, Drive API export).
- 12 slides tokenizados con ~120 tokens + 6 listas variables (`pipeline_alquiler`, `comisiones_atrasos`, `operaciones_condicionadas`, `cobros_pendientes`, `ventas_pendientes`, `obras_nuevas`).
- Helper `slots()` + `expand_lists()` para manejar listas de longitud variable.
- Servicio FastAPI con endpoints `GET /health` + `POST /generar-informe`.
- Dockerfile + docker-compose con healthcheck y volumen de credenciales.
- Conexión a la red de n8n (`sesion-idealista_default`) para que llame al servicio por nombre de contenedor (`http://informes-financieros-api:8000`).
- Workflow n8n probado: Manual Trigger → Code (payload completo) → HTTP Request → PDF binario recibido.
- Datos mock realistas (`data/mock_abril_2026.json`) con el contenido completo del informe abril 2026.

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

### P-04 · Colores condicionales (verde/rojo según estado)
**Estado:** explorado, no implementado. Hoy todos los textos heredan el color del token en la plantilla, sin lógica condicional.

**Casos detectados:**
- Slide 2: variaciones MoM en rojo si negativas, verde si positivas.
- Slide 3: flechas `▲ +33,7 %` (verde) vs `▼ -6,6 %` (rojo).
- Slide 8: estados `✓ SUPERADO` (verde) vs `FALTAN: X €` (rojo).
- Slide 11: clasificación de KPIs en columnas Fortaleza/Observación/Riesgo.

**Camino acordado:**
1. Helper `apply_color_overrides()` en `app/token_helpers.py`.
2. Convención en el JSON: lista `_color_overrides` con `{token: color}`.
3. Paleta de colores corporativos definida en Python.
4. Después de `replaceAllText`, aplicar `updateTextStyle` por cada token con override.

**Colores fijos no condicionales** (ej. dorado de "Facturación cobrada" en slide 8) se aplican en la plantilla, no necesitan código.

**Prioridad sugerida:** alta — mejora visual significativa con coste moderado de implementación.

---

### P-05 · Gráfico del slide 3 (Reservas vs Arras)
**Estado:** no iniciado. Hoy el gráfico está hardcodeado en la plantilla.

Gráfico de barras: 3 períodos (Abr'25, Mar'26, Abr'26) × 2 series (Reservas, Contratos Firmados).

**Camino acordado:**
1. Generar el gráfico con `matplotlib` → PNG.
2. Subir el PNG temporalmente a Drive (en la carpeta de la copia de Slides).
3. `replaceAllShapesWithImage` o `insertImage` sobre un placeholder pre-definido.
4. Borrar el PNG tras exportar el PDF.

**Decisiones a tomar:**
- Paleta de colores (debe coincidir con branding).
- Cómo identificar la región de inserción (object ID estable vs coordenadas).
- ¿Eliminar el gráfico estático actual o usarlo como placeholder?

---

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

1. **P-11** — pedir/recibir datos reales de contabilidad (acción externa, no depende de código).
2. **P-04** — colores condicionales: mejora visual grande, código moderado.
3. **P-12** — comando de validación de tokens: pequeña inversión, evita errores futuros.
4. **P-05** — gráfico del slide 3 con matplotlib.
5. **P-01** — migración cuenta corporativa (cuando se confirme).
6. **P-08** — Postgres + calculator + formatter (cuando lleguen datos reales).
7. **P-07** — narrativa determinista (depende de P-08).
8. **P-15** — workflow n8n con datos reales (depende de P-11 y P-08).
9. **P-17** — API Key antes de pasar a producción.
10. **P-16** — despliegue al servidor (al final, cuando todo lo previo esté validado).
11. **P-09, P-13, P-14** — multi-sede, tests, observabilidad (pulido).
