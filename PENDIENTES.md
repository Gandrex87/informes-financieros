# Pendientes — Próximas iteraciones

Estado a **2026-05-14** tras cerrar varios hitos:
- **Sprint 1** ✅: tokenización completa de los 12 slides + pipeline funcional con datos mock locales.
- **Sprint 2** ✅: servicio FastAPI + dockerización + integración con n8n local. Validado end-to-end: n8n llama al servicio en red Docker compartida y recibe el PDF.
- **Sprint 3** ✅: colores condicionales (P-04) + integración Postgres real para slides 1, 2 y 3 (lado izquierdo).
- **Sprint 4** ✅: documentación (`docs/MAPEO_DATOS.md`) + gráfico del slide 3 (P-05) + slide 4 completo (KPIs + pipeline pendiente).
- **Sprint 5** ✅: slide 5 completo (pipeline ventas + obra nueva + alquileres + totales agregados).
- **Sprint 6** ✅: slide 6 completo (operaciones condicionadas + tarjeta de alerta con severidad y color condicional).
- **Sprint 7** ✅: slide 11 completo (semáforo estratégico con asignación fija + 5 tokens nuevos + fix URL Drive→Slides para gráficos).
- **Sprint 8** ✅: slide 12 completo (hoja de ruta con tokens reutilizados + 2 constantes provisionales pendientes).
- **Sprint 9** ✅ (parcial): slide 9 Partes A y B (firmado/cobrado del mes + cálculo final). Parte C (tabla atrasos) pausada por fuente sin confirmar. Documentado el carácter HÍBRIDO del informe.
- **Sprint 10** ✅: slide 7 (cobros pendientes desde `pago_agentes`) + `total_pendiente_cobro` del slide 12 ahora deriva de la misma fuente (ya no provisional).
- **Sprint 11** ✅: validador de tokens (P-12), 92 tests pytest (P-13), API Key opcional (P-17), puerto y red Docker configurables por entorno.
- **Sprint 12** ✅: **MIGRACIÓN A PRODUCCIÓN COMPLETA** (P-01). Service Account + Shared Drive corporativa (sistemas@). Servicio desplegado en el servidor, validado end-to-end desde curl y n8n. Fix del SSL idle (clientes Google por petición).

- **Sprint 13** ✅: token `mes_anterior_capitalizado` (slide 2 "vs Marzo" dinámico). Incidente P-27 resuelto (ingesta cargaba NULL por cambio de etiquetas en el Sheet).

- **Sprint 14** ✅: debug slide por slide (2→12) + extracción `calculator_base.py`. Fix color slide 2 card 1 (bug producción: `_observacion` pintaba el slide 2 en amarillo → sufijo `​`). P-20 cerrado (desfase obra nueva = datos faltantes en ingesta, no bug). Datos faltantes de condicionadas insertados a mano → P-28 abierto.

- **Sprint 15** ✅: **slides 8 y 10 integrados** (Break Even mes actual + proyección mes+1, escenario `con_crm` sin extras, narrativa determinista 3 ramas, estados ✓SUPERADO/FALTAN, margen seguridad con color condicional). **Posicionamiento dinámico** del marcador `{{ingresos_totales}}` en la barra del slide 8 vía `updatePageElementTransform` con interpolación proporcional entre los 4 hitos (módulo nuevo `app/break_even_chart.py`, 21 tests unitarios, script `scripts/simular_break_even.py` para validar escenarios). **Fuentes resumen mensual:** `contratos_firmados` y derivados ahora desde `resumen_mensual_arras` + `resumen_mensual_alquileres` (slides 1/2/3, gráfico incluido); `reservas_alquiler` (slide 4) desde `resumen_mensual_alquiler_senales`. **Tramo de comisión dinámico** desde `pagos_directores` (P-22 cerrado). **Fix `var_rentab_mom`** (slide 2 card 4): puntos porcentuales en vez de variación relativa. **Filtro slide 7** `fecha_arras_sin_condic IS NOT NULL` (excluye operaciones "PONER FECHA"). **`n_max`** alineados con plantilla: ventas_pendientes 18→21, operaciones_condicionadas 12→22 (corrige bug latente de tokens literales visibles). MAPEO_DATOS actualizado con sección de **Aprendizajes técnicos** (12 puntos).

Próximos pasos: Slide 9 Parte C pendiente fuente (P-23). Cambiar API Key débil de producción (P-26). Decisión P-25 (cobros que no caben — alivia con filtro IS NOT NULL del slide 7). Endurecer ingesta ante NULL (P-27). Confirmar comportamiento ingesta vs filas manuales (P-28). Bug etiqueta plantilla slide 2 card 1 (`{{mes_anterior_short}}`→`{{mes_año_anterior_short}}`). Validar P-18, P-21 con contabilidad.

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
- Token global del slide: `trimestre` (Q1/Q2/Q3/Q4 derivado del mes).

### Slide 6 — Operaciones condicionadas (riesgo operativo)
- Query nueva: `_query_operaciones_condicionadas()` filtrada por `pendiente_fecha_condicionada = TRUE` (flag específico de ventas condicionadas vivas).
- Tabla de operaciones individuales (sin agrupar por inmueble) con `n_max=12`.
- Tarjeta de alerta con etiqueta semántica `impacto_facturacion` ("Crítico" / "Alto" / "Estable") y color condicional del `volumen_riesgo` (rojo / amarillo / verde).
- Función `_clasifica_impacto()` con rangos: `>80k Crítico`, `>30k Alto`, `<=30k Estable`.
- Color override del importe `volumen_riesgo` aplicado dinámicamente desde el calculator (no color fijo de plantilla).

### Slide 11 — Semáforo estratégico
- Asignación FIJA de KPIs a columnas (no dinámica). Plantilla hardcodea qué KPI va en cada columna.
- 5 tokens nuevos: `var_reservas_mom_observacion`, `var_contratos_mom_observacion`, `rentabilidad_op_signed`, `volumen_riesgo_short`, `mes_siguiente_capitalizado`.
- Tokens `_observacion` con el mismo valor que sus equivalentes del slide 2 pero distinto nombre, para poder colorearlos en amarillo independientemente.
- Helpers nuevos: `format_euro_compacto()` (135855 → "135,9 k €", soporta sufijos k/M) y `format_mes_capitalizado()`.
- Calculator: `_mes_siguiente()` helper, simétrico a `_mes_anterior`.
- Color override de `rentabilidad_op_signed`: verde si ≥ 20 % (objetivo), rojo si menor.
- Color override de `volumen_riesgo_short`: hereda umbrales de `_clasifica_impacto()` del slide 6.
- Color override de `var_*_mom_observacion`: amarillo siempre (semántica de la columna).

### Fix técnico — URL de imagen + timing para Slides API
- Cambiado en `app/image_helpers.py`: el endpoint `drive.google.com/uc?id=X` ya no es fiable (a veces devuelve HTML de virus-scan en lugar de bytes de imagen). Reemplazado por `drive.google.com/thumbnail?id=X&sz=w2000` que sirve bytes directos.
- Añadido `_wait_public_url_ready()`: tras subir el PNG y darle permiso público, espera hasta 10s a que la URL responda 200 antes de pasársela a Slides API. Necesario porque la propagación interna de Drive puede tardar unos segundos.
- Añadido reintento con backoff exponencial en `replace_shape_with_image` (hasta 3 intentos, esperas 1s → 2s → 4s). Solo reintenta si el error es "image not publicly accessible"; cualquier otro error se propaga inmediatamente.
- Resultado: cero deps nuevas (urllib de stdlib), tolerancia a timing inestable de Drive, comportamiento silencioso cuando todo va bien.

### Slide 12 — Hoja de ruta
- La mayoría de tokens son **reutilizados** de slides anteriores (volumen_riesgo, n_ops_condicionadas, total_pipeline, n_ops_pipeline, objetivo_rentabilidad, trimestre).
- 1 token nuevo derivado: `mes_siguiente_upper` (formato `"MAYO 2026"`).
- 2 constantes provisionales agrupadas en cabecera del calculator: `INVERSION_TECNOLOGICA_PROVISIONAL = "27k€"` y `TOTAL_PENDIENTE_COBRO_PROVISIONAL = "204.392 €"`. Pendiente confirmar fuente real con contabilidad.
- Texto "Objetivo: Maximizar liquidez en Q2" → reemplazado en plantilla por `{{trimestre}}` para que se ajuste al trimestre del mes que se genera.
- Barras superiores de color son fijas en plantilla (decorativas, no condicionales).

### Migración a producción (P-01 — CERRADO)
- `sistemas@lioncapitalg.com` es Google Workspace real → se migró a **Service Account** (no OAuth). El token NO caduca (resuelve el problema del refresh_token de 7 días).
- GCP nuevo proyecto, Service Account `informes-bot-prod@...`, JSON en `credentials/service_account.json` (chmod 600, NO en git).
- Shared Drive corporativa "Informes Financieros" (`0AE8Yvf40XImDUk9PVA`). SA miembro con rol Administrador. Plantilla copiada ahí (`1HQTRCoeiFm4Ptc6RVTNWwTfJ2jsfWkXELbJ47xkgcpU`).
- `app/auth.py`: soporta `AUTH_METHOD` = `service_account` | `oauth` (rollback). `.env` usa `service_account`.
- `supportsAllDrives=True` añadido a TODAS las llamadas Drive (copy/delete/create/get) — obligatorio para Shared Drives.
- Servicio desplegado en el servidor (`/home/n8n/informes-financieros`), red `app-network`, puerto host `8012`. Validado end-to-end desde curl y n8n: PDF correcto.

### Fix técnico — SSL idle connection (clientes Google por petición)
- **Síntoma:** `SSL record layer failure` al copiar la plantilla, solo en producción y solo cuando pasaba tiempo entre el arranque del servicio y la primera petición.
- **Causa:** los clientes Google se creaban 1 vez al arranque (`lifespan`) y se cacheaban. El firewall/NAT del servidor cierra conexiones SSL inactivas; al reutilizar una conexión muerta → SSL error. En local no pasaba (se probaba justo tras arrancar, conexión fresca).
- **Fix:** `app/main.py` ya NO cachea clientes. `get_google_clients()` los crea **frescos por petición**. Con Service Account el coste es mínimo (firmar JWT, ~ms). El `lifespan` solo valida credenciales al arrancar.
- **Aprendizaje transversal:** cualquier servicio que cachee clientes HTTP de larga vida detrás de un firewall con timeout de idle tendrá este problema. No cachear conexiones idle de larga duración en este servidor.

### Flujo de despliegue establecido
```
LOCAL (dev, AUTH_METHOD=service_account igual que prod)
  → git add/commit/push
  → SERVIDOR: git pull + docker compose up -d --build  (--build OBLIGATORIO)
  → smoke test: logs (Auth: Service Account) + curl /health
```
- `.env` y `credentials/` NO viajan por git — se configuran 1 vez por entorno.
- Diferencias local↔prod viven solo en `.env`: `HOST_PORT` (8011/8012), `DOCKER_NETWORK` (sesion-idealista_default / app-network), `API_KEY`.
- ⚠️ Si un cambio introduce una **variable de entorno nueva**: hay que añadirla manualmente al `.env` del servidor (el `git pull` trae el compose pero no el `.env`). Señalarlo explícitamente en cada cambio así.

### Documentación
- `docs/MAPEO_DATOS.md`: tabla por slide con tokens, fuentes, fórmulas y estado.
- `docs/API_SPEC.md`: spec para consumo desde el ERP (endpoints, auth, errores, puerto).
- `PENDIENTES.md` (este documento).
- Memoria del proyecto en `~/.claude/projects/.../memory/` con decisiones arquitectónicas.

---

## 🟡 Discrepancias en observación — verificar con contabilidad

### P-27 · Fragilidad de la ingesta ante cambios de etiquetas en el Excel

**Incidente (2026-05-18):** `{{ingresos_totales}}` salió vacío/literal en el PDF. Causa raíz: contabilidad **cambió etiquetas de filas en el Sheet contable**, el workflow n8n de ingesta dejó de mapear esos conceptos, y `contabilidad_mensual.ingresos_contables` se cargó como NULL. El calculator y la plantilla estaban bien — el dato simplemente no existía en Postgres.

**Diagnóstico que despistó:** el validador de tokens decía "coincide" (token OK en ambos lados). El problema no era el token sino el **dato origen NULL**. Aprendizaje: un token vacío en el PDF puede ser (a) token partido en runs, (b) calculator no lo produce, **(c) el dato llegó NULL de la ingesta** — esta última no la detecta `check_tokens.py`.

**Patrón de fondo:** el cuadro contable del Sheet es manual; cualquier cambio de nombre de fila (etiqueta) rompe silenciosamente el mapeo `CONCEPT_TO_COLUMN` del workflow de ingesta. No hay alerta — el INSERT mete NULL y el informe sale incompleto sin avisar.

**Mitigaciones a considerar (no implementadas):**
- Validación en el workflow n8n: si un concepto esperado no se encuentra en el Sheet, fallar/alertar en lugar de insertar NULL.
- O un check en el calculator: si `ingresos_contables IS NULL` para el mes pedido → error explícito ("contabilidad sin cargar para X") en lugar de PDF con huecos.
- Acordar con contabilidad que NO cambien las etiquetas de fila sin avisar (las etiquetas son el contrato de la ingesta).

**Estado:** incidente resuelto (ingesta corregida, datos recargados). El patrón de fragilidad queda anotado para endurecer la ingesta más adelante.

### P-28 · Filas insertadas/corregidas a mano en `ventas_comerciales` (riesgo de divergencia con la ingesta)

**Contexto (2026-05-19):** durante el debug del slide 6 faltaban en
`ventas_comerciales` dos operaciones condicionadas reales por ingesta
incompleta desde el Sheet. Se **insertaron y corrigieron MANUALMENTE** vía SQL
directo a Postgres de producción (saltándose el workflow n8n):

| numero | id | inmueble | honorarios_totales | pendiente_fecha_condicionada |
|---|---|---|---|---|
| 324 | 70411 | Paseo Alameda 41 | 37.500,00 € | TRUE |
| 325 | 70412 | C. Doctor Villena 20 | 13.650,00 € | TRUE |

Efecto: `volumen_riesgo` (slide 6) pasó de `96.471,69 €` a `147.621,69 €`
(9 ops, severidad Crítico). Mismo patrón de causa que P-20 y P-27.

**Riesgo abierto:** un INSERT/UPDATE manual mete filas que la ingesta n8n no
conoce. Si esas 2 operaciones aparecen luego en el **Sheet origen** y la
ingesta vuelve a correr, puede producirse:
- **Duplicado** (si el workflow hace INSERT ciego, no UPSERT por `numero`), o
- **Sobreescritura** de la corrección manual con datos parciales del Sheet.

`numero` es UNIQUE en la tabla → un INSERT con `numero` repetido fallaría, pero
hay que confirmar cómo se comporta exactamente el workflow.

**Acciones:**
1. Confirmar con quien gestiona la ingesta si `Paseo Alameda 41` y
   `C. Doctor Villena 20` están en el Sheet origen y se cargarán en el próximo
   ciclo. Si están, asegurar que el workflow deduplica por `numero` (UPSERT) y
   no duplica/pisa estas filas.
2. Si NO están en el Sheet: registrar que estas 2 filas son **solo manuales**
   (riesgo de perderse si se recarga la tabla desde cero).
3. A futuro: el origen de verdad debe ser el Sheet+ingesta, no parches SQL
   manuales. Vigilar el patrón recurrente (P-20, P-27, P-28) de datos
   faltantes/desfasados por ingesta.

**Estado:** abierto — seguimiento de divergencia, depende de confirmar el
comportamiento del workflow n8n.

### P-25 · Slide 7 — más cobros que slots en la plantilla (DECISIÓN DE NEGOCIO)

Los datos reales de cobros pendientes superan los slots de la plantilla:
`slots('cobro'): 31 items pero n_max=20. Truncando.`

**Estado actual:**
- El `total_pendiente_cobro` se calcula sobre los **31** (TODOS), es correcto.
- La tabla solo muestra **20** (los de mayor importe, orden DESC).
- Consecuencia: el lector ve 20 filas + un total que no cuadra al sumarlas (faltan 11 filas por ~la diferencia).

**Es una decisión de presentación de negocio, NO técnica.** Opciones:

- **A.** Ampliar `n_max` en la plantilla (¿caben 35 filas visualmente en 2 columnas sin reducir fuente? ¿y si un mes hay 50?).
- **B.** Top 20 + fila resumen "+ N operaciones más — X €" (total siempre cuadra, escala a cualquier volumen). **Recomendada técnicamente.**
- **C.** El total refleja solo lo mostrado (descartada: total incorrecto, engañoso en finanzas).
- **D.** Filtro de negocio que reduzca el dataset (ej. solo > 1.000 €, o últimos N meses) — requiere criterio de contabilidad.

**Acción:** preguntar a dirección/contabilidad: "Si hay 31 cobros pendientes, ¿quieren verlos todos o las 20 mayores + un resumen del resto?". Implementar según respuesta.

**Mismo riesgo aplica a otros slides con listas variables** (pipeline ventas slide 5 con `n_max=18`, condicionadas slide 6 con `n_max=12`) si los datos reales superan esos topes. Vigilar los WARNING de `slots(...)` en logs.

### P-24 · Basura de coma flotante en `pago_agentes.pte_facturar`

La columna `pte_facturar` (TEXT) tiene valores residuales tipo `'0.21000000000003638'`, `'0.4132229999995616'` — error de precisión IEEE 754, probablemente de restas `honorarios - facturado` en la ingesta. No son cobros reales.

**Mitigación aplicada:** el filtro de `_query_cobros_pendientes()` usa `> 1` (umbral anti-basura). Cualquier cobro real es ≥ cientos de €, así que es seguro.

**Acción a futuro:** revisar la ingesta de `pago_agentes` para que no genere estos residuos (mantener decimales exactos / redondear en origen). Similar a P-19 (duplicados).

### P-23 · Fuente de "COBRADO DE MESES ANTERIORES" (slide 9, Parte C)

La tabla de atrasos del slide 9 (operaciones de meses anteriores cobradas este mes, con su tramo histórico) no tiene fuente confirmada. Hoy `subtotal_comision_atrasos` está hardcoded a `1021.89` (`SUBTOTAL_COMISION_ATRASOS_PROVISIONAL`) para validar la sumatoria de la zona inferior.

**Acción:** preguntar a contabilidad de dónde sale "Cobrado de meses anteriores". Cuando se confirme: implementar `_query_comisiones_atrasos()`, poblar la lista `comisiones_atrasos`, y calcular `subtotal_comision_atrasos` como su suma (en lugar de la constante).

### P-22 · Tramo de comisión — ✅ CERRADO (2026-05-20)

**RESUELTO.** El tramo NO es constante ni escala por volumen: es la **suma de
porcentajes de los directores del mes** en `pagos_directores`. Implementado
`_query_tramo_comision(anyo, mes)` que devuelve `SUM(porcentaje)`. Abril 2026:
ALEX 0,015 + FADIA 0,015 = `0,03` (3%). Eliminadas constantes
`TRAMO_COMISION_PCT/LABEL`. El tramo se refleja dinámicamente en slide 1 y
slide 9, y se usa para calcular `comision_ventas_mes` y `comision_alquileres_mes`.

**Beneficio colateral:** funciona con N directores variable sin tocar código.
Si entra/sale un director, basta con añadir/quitar filas en `pagos_directores`.

**Guard explícito:** si no hay filas para el mes → `ValueError` (no PDF con
comisión 0 silenciosa, lección P-27).

### P-21 · Origen de `inversion_tecnologica` (slide 12)

Hoy hardcoded como `"27k€"` (`INVERSION_TECNOLOGICA_PROVISIONAL`) en `calculator.py`. Hipótesis posibles:

- **A.** Constante anual: cifra acumulada del año en inversión tecnológica/CRM.
- **B.** Suma acumulada de `gastos_programadores` desde enero hasta el mes generado.
- **C.** Parámetro mensual definido por dirección (futuro `parametros_sede_mes`).

**Acción:** preguntar a contabilidad de dónde sale el `27k€` del PDF de abril 2026 y qué semántica tiene. Según respuesta, ajustar `calculator.py`.

### P-20 · Diferencia importe obra nueva "Altos de Santa Bárbara" — ✅ CERRADO (2026-05-19)

**RESUELTO.** No era un bug de filtro: `_query_obra_nueva()` es correcta. El
desfase (`587.450 €` calculator vs `505.850 €` PDF original para `Urb. Altos de
Santa Bárbara`) se debía a **operaciones ausentes en `ventas_comerciales`** por
ingesta incompleta desde el Sheet (mismo patrón que P-27 etiquetas y el
incidente de condicionadas P-28). Completados los datos en origen, el total
cuadra. `C. VICTORIA KENT` siempre cuadró (94.240 €).

**Lección:** cuando un total de `ventas_comerciales` no cuadra y la query está
validada, sospechar **datos faltantes en la ingesta** antes que del código.
Verificar con `SELECT` de los inmuebles esperados.

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

### P-26 · Cambiar la API Key débil de producción (SEGURIDAD)
**Estado:** abierto. Bloqueante antes de entregar el endpoint al equipo del ERP.

La API Key actual de producción (`LionCapital123`) es **adivinable** (nombre empresa + 123). No protege realmente el endpoint.

**Acción:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# editar API_KEY=<la_nueva> en /home/n8n/informes-financieros/.env
docker compose up -d   # recargar
```
Guardar la clave en gestor de contraseñas, entregarla al ERP por canal seguro. Actualizar el header `X-API-Key` en el workflow de n8n con la nueva clave.

> El servicio funciona técnicamente con clave débil; esto es estrictamente seguridad. No bloquea desarrollo, sí bloquea "entregar a producción de verdad".

---

### P-01 · Migración a cuenta corporativa Google — ✅ CERRADO (2026-05-18)

**RESUELTO.** `sistemas@lioncapitalg.com` resultó ser Google Workspace real. Se migró a **Service Account + Shared Drive corporativa** (mejor que OAuth: el token NO caduca). Servicio desplegado y validado en el servidor de producción, end-to-end desde curl y n8n.

Detalle completo en la sección ✅ Hecho → "Migración a producción". Rollback OAuth documentado en `.env` y en memoria. Lo único que queda relacionado con producción: **P-26** (cambiar la API Key débil).

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

1. **P-26** — rotar API Key débil de producción (bloqueante antes de entrega ERP).
2. **P-23** — confirmar fuente de "COBRADO DE MESES ANTERIORES" (slide 9 Parte C, último bloqueo del calculator de Valencia).
3. **Commit + despliegue** de todo lo de Sprint 15 al servidor de producción.
4. **P-21** — confirmar con contabilidad origen de `inversion_tecnologica` (27k€).
5. **P-28** — confirmar comportamiento de la ingesta n8n vs filas manuales en `ventas_comerciales` (UPSERT por `numero` o INSERT ciego).
6. **P-18** — validar discrepancias del slide 2/3 con contabilidad (acción externa).
7. **Plantilla:** fix card 1 slide 2 (`{{mes_anterior_short}}` → `{{mes_año_anterior_short}}`).
8. **P-27** — endurecer ingesta n8n para fallar si concepto esperado no aparece (NULL silenciosos).
9. **P-09** — arrancar informe Alicante (calculator separado, plantilla nueva, ~10 slides).
10. **P-25** — decisión final cobros que no caben (aliviado pero no resuelto).
