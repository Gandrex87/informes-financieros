# Migración multi-sede — Decisiones de modelo de datos

Documento vivo durante la integración de Alicante (Sprint 16+). Cada tabla
de Postgres se discute slide por slide y se decide:

- **Compartida con columna `sede`**: una sola tabla, filas distinguidas por
  la columna `sede` (`'Valencia'`, `'Alicante'`).
- **Separada por sede**: dos tablas con sufijo (`*_valencia`, `*_alicante`).
- **Sin cambios**: la tabla queda como está (ya tiene `sede` o solo aplica
  a una sede).

## TL;DR para agentes que retomen este trabajo

Si vas a **añadir una sede nueva** o vienes a **entender cómo está montado el
multi-sede hoy**, el orden de lectura recomendado es:

1. **Este "TL;DR"** (resumen ejecutivo del estado actual).
2. **"Trampas conocidas"** al final del documento (lecciones aprendidas con
   sangre — leerlas evita repetir bugs reales en producción).
3. **"Checklist resumido para Castellón"** (los pasos exactos a seguir).
4. El resto del documento (historia y razonamiento de cada decisión) solo
   cuando necesites contexto profundo de por qué algo es como es.

### Estado del modelo de datos (2026-05-22)

Todas las tablas relevantes son **COMPARTIDAS con columna `sede`** (decisión
2026-05-20/22). El experimento inicial de separar `ventas_comerciales` en
`*_valencia`/`*_alicante` se revirtió el mismo día por innecesario. La
separación por sede SOLO se aplicó a `pagos_directores` inicialmente y
también se revirtió a compartida el 2026-05-21.

Tablas hoy con `sede`:
- `finanzas_automation.ventas_comerciales`
- `informes_financieros.contabilidad_mensual` (ya la tenía desde el inicio)
- `informes_financieros.pagos_directores` (movida desde `finanzas_automation` 2026-05-21)
- `informes_financieros.pago_agentes`
- `informes_financieros.comisiones_atrasos_directores`
- `informes_financieros.resumen_mensual_arras` (movida desde `finanzas_automation` 2026-05-22)
- `informes_financieros.resumen_mensual_arras__sin_condicion` (movida 2026-05-22)
- `informes_financieros.resumen_mensual_alquileres` (movida 2026-05-22)
- `informes_financieros.resumen_mensual_alquiler_senales` (movida 2026-05-22)

### Estado del código (2026-05-22)

- `app/calculator.py` → **DISPATCHER**. Funciones: `build_payload(sede,
  anyo, mes, escenario)` y `template_id_for(sede)`.
- `app/calculator_valencia.py` → calculator de Valencia. Función entrada
  `build_payload(sede=..., anyo=..., mes=..., escenario=...)`.
- `app/calculator_alicante.py` → calculator de Alicante. Función entrada
  `build_payload(anyo=..., mes=..., escenario=...)` (sin `sede`, es
  constante `SEDE = "Alicante"`).
- `app/calculator_base.py` → queries comunes parametrizadas por `sede` +
  helpers + dataclasses. Cada query valida `sede in SEDES_VALIDAS`.
- `app/generator.py` → `generate_report` ahora requiere `template_id`
  **obligatorio**. El caller resuelve el template via
  `calculator.template_id_for(sede)`.

### Estado de la configuración (2026-05-22)

Variables de entorno:
- ❌ Eliminada: `SLIDES_TEMPLATE_ID` (genérico).
- ✅ Nuevas: `SLIDES_TEMPLATE_ID_VALENCIA`, `SLIDES_TEMPLATE_ID_ALICANTE`.
- Si falta una → `RuntimeError` explícito (lección P-27: nunca generar PDF
  con plantilla equivocada).

Estas variables deben estar **simultáneamente en tres sitios**:
1. `.env` local (para desarrollo).
2. `.env` del servidor de producción.
3. `docker-compose.yml` (bloque `environment:` del servicio `informes-api`).

**Saltarse el punto 3 fue causa de un bug en producción 2026-05-22** — ver
Trampa 9 al final del documento.

### Diagnóstico rápido

`GET /health` (sin auth, pensado para diagnóstico) devuelve:

```json
{
  "status": "ok",
  "templates": {"Valencia": "1HQ...", "Alicante": "1uQ..."},
  "user_email": "informes-bot-prod@..."
}
```

Si una sede no aparece en `templates`, el problema es de configuración
(no de código). Ver Trampa 10.

---

## Heurística acordada (2026-05-20)

> "Tabla compartida con columna `sede` cuando el esquema y la semántica son
> idénticos entre Valencia y Alicante. Tabla separada cuando el esquema o el
> control operativo divergen."

Excepciones tomadas por el usuario para reforzar aislamiento operativo: ver
decisiones por tabla abajo.

## Convención de naming

- Columna: `sede TEXT NOT NULL`
- Valores: `'Valencia'`, `'Alicante'` (coherente con `contabilidad_mensual`,
  que ya usa esos valores).
- **Sin** `CHECK` constraint sobre `sede` (permite añadir nuevas sedes sin
  migración futura, ej. Castellón).
- Tablas separadas: sufijo `_valencia` / `_alicante` en minúsculas.

## Resolución en el código

Decidido **(A) helper en base con validación estricta**: las queries
genéricas siguen viviendo en `calculator_base.py` y reciben `sede` como
parámetro. Para tablas separadas, una función `_tabla_<nombre>(sede)`
devuelve el nombre real, validando estrictamente la sede para evitar SQL
injection:

```python
SEDES_VALIDAS = {"Valencia", "Alicante"}

def _tabla_ventas_comerciales(sede: str) -> str:
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}")
    return f"ventas_comerciales_{sede.lower()}"
```

Las queries hacen `FROM {tabla}` con f-string sobre ese nombre validado.
Razón de elegir (A) sobre duplicar en cada calculator: la mayoría de
queries son idénticas para ambas sedes; un bug fix se aplica una sola vez.
Si en el futuro una sede necesita una query realmente distinta, esa query
concreta se mueve a su `calculator_<sede>.py`.

## Decisiones por tabla

### `ventas_comerciales` — **COMPARTIDA con `sede`** (decisión final)

- **Decidido**: 2026-05-20
- **Historial de la decisión**: inicialmente se decidió SEPARADA (renombramos
  a `ventas_comerciales_valencia` y se creó el helper en código). Al revisar
  con honestidad técnica, se concluyó que **la separación no aportaba lo
  suficiente para justificar el coste**: esquema y semántica idénticos,
  ausencia (no divergencia) de alquileres/obra nueva en Alicante, y los
  beneficios de aislamiento eran teóricos (un `WHERE sede` da el mismo
  aislamiento práctico). Se revirtió el mismo día.
- **Por qué COMPARTIDA**:
  - Esquema y semántica idénticos entre las dos sedes.
  - Coherente con `contabilidad_mensual` (la tabla con datos financieros más
    sensible, también compartida con `sede` desde el inicio sin problemas).
  - Queries cross-sede triviales (dirección puede pedir "reservas totales
    de la empresa" sin `UNION ALL`).
  - Esquema evoluciona en un solo sitio (un `ALTER TABLE` futuro = 1 vez).
  - Menos complejidad de código (sin helper de nombre de tabla).
- **Cambios SQL aplicados**:
  ```sql
  ALTER TABLE finanzas_automation.ventas_comerciales_valencia
      RENAME TO ventas_comerciales;
  ALTER SEQUENCE finanzas_automation.ventas_comerciales_valencia_id_seq
      RENAME TO ventas_comerciales_id_seq;
  ALTER TABLE finanzas_automation.ventas_comerciales
      ADD COLUMN sede TEXT NOT NULL DEFAULT 'Valencia';
  CREATE INDEX IF NOT EXISTS idx_ventas_comerciales_sede_fecha_senal
      ON finanzas_automation.ventas_comerciales (sede, fecha_senal);
  CREATE INDEX IF NOT EXISTS idx_ventas_comerciales_sede_fecha_arras
      ON finanzas_automation.ventas_comerciales (sede, fecha_arras);
  ```
- **Implicación código**: las 6 queries comerciales (`_query_comercial`,
  `_query_alquileres_mes`, `_query_pipeline_ventas`, `_query_obra_nueva`,
  `_query_operaciones_condicionadas`, `_query_pipeline_alquileres`) reciben
  `sede` y añaden `WHERE sede = %(sede)s` (o `AND sede = ...` en queries con
  WHERE previo). `_query_comercial` valida `sede in SEDES_VALIDAS` para
  fallar pronto ante una sede mal escrita.
- **Implicación ingesta n8n**: el workflow de Valencia debe seguir apuntando
  a `ventas_comerciales`. **AÑADIR** el campo `sede='Valencia'` al
  INSERT/UPSERT (el `DEFAULT 'Valencia'` es red de seguridad, pero conviene
  ser explícito). Workflow de Alicante (a crear) apuntará a la misma tabla
  con `sede='Alicante'`.

### `resumen_mensual_arras` — **COMPARTIDA con `sede`**

- **Decidido**: 2026-05-20
- **Por qué**: esquema y semántica idénticos (totales mensuales agregados).
  Esta tabla NO se manipula manualmente, solo recibe ingesta automática
  desde el Sheet. El riesgo de contaminación es mínimo y la ventaja de
  tener queries cross-sede triviales pesa más.
- **Cambio**: añadir columna `sede TEXT NOT NULL DEFAULT 'Valencia'` y
  ampliar la unique key natural a `(sede, anio, mes)`.
- **Implicación código**: `_query_contratos_resumen` añade
  `AND sede = %(sede)s` y recibe `sede` como parámetro.

### `resumen_mensual_alquileres` — **COMPARTIDA con `sede`** (Alicante sin filas)

- **Decidido**: 2026-05-20
- **Por qué**: alquileres es un producto que hoy solo existe en Valencia,
  pero el usuario prefiere dejar el esquema preparado para multi-sede
  por si Alicante (u otra sede futura) lo añade. Consistente con la
  decisión de `resumen_mensual_arras`.
- **Cambio**: igual que `resumen_mensual_arras`.
- **Implicación código**: `_query_alquileres_cobrados_mes` y
  `_query_contratos_resumen` añaden filtro de sede. El calculator de
  Alicante simplemente lee `SUM = 0` (sin filas), sin error.

### `resumen_mensual_alquiler_senales` — **COMPARTIDA con `sede`** (Alicante sin filas)

- **Decidido**: 2026-05-20 (por extensión, mismo criterio que las otras
  RM)
- **Cambio**: igual.
- **Implicación código**: `_query_alquiler_senales_resumen` filtra por
  sede.

### `pagos_directores` — **COMPARTIDA con `sede`** (decisión final)

- **Decidido inicialmente (2026-05-20):** SEPARADA en `_valencia` y `_alicante`.
- **Decisión final (2026-05-21):** **COMPARTIDA con columna `sede`** y movida
  al schema `informes_financieros`. Mismo razonamiento que motivó el rollback
  de `ventas_comerciales`: el esquema es idéntico, el riesgo de mezclar
  directores se resuelve con `WHERE sede` en la query (igual que en
  `contabilidad_mensual`), y separar dos tablas de ~8 filas cada una no
  aporta lo suficiente para el coste de mantener naming sufijado.
- **Esquema final**: `informes_financieros.pagos_directores` con columnas
  `id, anio, mes, director, porcentaje, importe, created_at, updated_at, sede`.
- **Filas reales abril 2026**:
  - Valencia: ALEX 0.015 + FADIA 0.015 = 0.030 → `"3 %"`
  - Alicante: PELAYO 0.04 → `"4 %"`
- **Implicación código**: `_query_tramo_comision(sede, anyo, mes)` filtra por
  `WHERE sede = %(sede)s` en `informes_financieros.pagos_directores`. El
  caller (Valencia o Alicante) pasa su `sede`.
- **Implicación ingesta n8n**: una tabla, dos sedes. Cada workflow inserta
  con `sede='Valencia'` o `sede='Alicante'` según corresponda.

### `contabilidad_mensual` — **SIN CAMBIOS**

- **Ya tiene** columna `sede` desde antes. Patrón compartido validado en
  producción. No requiere migración para Alicante: solo cargar filas con
  `sede='Alicante'`.

### `pago_agentes` (slide 7) — **COMPARTIDA con `sede`** (2026-05-21)

- **Decidido**: 2026-05-21 — coherente con el resto del modelo unificado.
- **Cambio aplicado**: el usuario añadió columna `sede` a la tabla. Hoy
  contiene filas para Valencia y Alicante.
- **Implicación código**: `_query_cobros_pendientes(sede)` pasa a recibir
  `sede` y filtra con `WHERE sede = %(sede)s`. Valida contra
  `SEDES_VALIDAS` para fallar pronto.
- **Implicación ingesta n8n**: cada workflow debe insertar con el campo
  `sede` correspondiente.

### `comisiones_atrasos_directores` (slide 9 Parte C) — **COMPARTIDA con `sede`** (2026-05-21)

- **Decidido**: 2026-05-21.
- **Fuente confirmada por contabilidad**: `informes_financieros.comisiones_atrasos_directores`
  con columnas `inmueble, mes_origen, porcentaje, honorarios, importe_comision,
  fecha_ingesta, sede`. Estado vivo (foto actual de atrasos pendientes).
- **Cierra P-23**: hasta esa fecha, `subtotal_comision_atrasos` era una
  constante provisional (`1021.89`) hardcoded. Ahora deriva del `SUM` real.
- **Implicación código**: nueva query `_query_comisiones_atrasos(sede)` en
  `calculator_base`; `calculator.py` la usa para construir la lista
  `comisiones_atrasos` (formato del mock) y el `subtotal_comision_atrasos`.

## Estado de la migración

### Tablas BD (todas COMPARTIDAS con `sede` salvo nota)

- [x] `ventas_comerciales` (`finanzas_automation`): columna `sede` añadida
      2026-05-20. Filas para Valencia y Alicante. Índices
      `(sede, fecha_senal)` y `(sede, fecha_arras)`.
- [x] `contabilidad_mensual` (`informes_financieros`): ya tenía `sede` desde
      el inicio. Filas para Valencia y Alicante.
- [x] `pagos_directores` (`informes_financieros`): movida desde
      `finanzas_automation` y añadida columna `sede` (2026-05-21). Filas
      para Valencia (ALEX+FADIA) y Alicante (PELAYO).
- [x] `pago_agentes` (`informes_financieros`): columna `sede` añadida
      2026-05-21. Filas para Valencia y Alicante. `_query_cobros_pendientes`
      filtra por sede.
- [x] `comisiones_atrasos_directores` (`informes_financieros`): tabla nueva
      con columna `sede` desde el inicio (2026-05-21). Cierra P-23.
- [x] `resumen_mensual_arras`: movida a `informes_financieros` con
      columna `sede` (2026-05-22). `_query_contratos_resumen(sede, anyo, mes)`
      filtra por sede.
- [x] `resumen_mensual_arras__sin_condicion`: movida a
      `informes_financieros` con columna `sede` (2026-05-22).
      `_query_arras_cobradas_mes(sede, anyo, mes)` filtra por sede.
- [x] `resumen_mensual_alquileres`: movida a `informes_financieros` con
      columna `sede` (2026-05-22). `_query_alquileres_cobrados_mes(sede,
      anyo, mes)` y `_query_contratos_resumen` filtran por sede. Eliminada
      la guarda temporal de `_query_contratos_resumen`.
- [x] `resumen_mensual_alquiler_senales`: movida a `informes_financieros`
      con columna `sede` (2026-05-22). `_query_alquiler_senales_resumen(sede,
      anyo, mes)` filtra por sede.

### Código

- [x] Queries comerciales / contables / break even / cobros / atrasos /
      tramo de comisión / pipeline ventas y alquileres reciben `sede` y
      filtran con `WHERE sede = %(sede)s`. `SEDES_VALIDAS` valida la
      sede pronto.
- [x] `_query_pipeline_ventas` y `_query_pipeline_alquileres` movidas a
      `calculator_base.py` (2026-05-21) para que las use también Alicante.
      `_query_pipeline_ventas` parametriza el filtro de obra nueva con
      `inmuebles_excluir_ilike` (Valencia pasa `PROMOCIONES_OBRA_NUEVA_EXCLUIR`,
      Alicante default `()`).
- [x] Tests 113/113 ✓. PDF Valencia abril 2026 se regenera idéntico tras
      cada migración.

### Ingesta n8n

- [ ] Cambios pendientes en workflows n8n: añadir `sede` al INSERT/UPSERT
      de las tablas migradas (`ventas_comerciales`, `pagos_directores`,
      `pago_agentes`, `comisiones_atrasos_directores`). Para Valencia el
      `DEFAULT 'Valencia'` cubre temporalmente, pero conviene ser
      explícito en el INSERT. Para Alicante es obligatorio mandar
      `sede='Alicante'` (no hay DEFAULT que la cubra).

### Slides

- [x] **Valencia**: 1-12 completos y validados contra plantilla.
- [x] **Alicante**: 1-10 completos en `calculator_alicante.py` con datos
      reales de Postgres (2026-05-22). Plantilla independiente
      (`SLIDES_TEMPLATE_ID_ALICANTE` en `.env`, resuelta vía
      `calculator.template_id_for("Alicante")`).
      Constantes provisionales que persisten:
      - `FACTURACION_OBJETIVO_PROY_PROVISIONAL = Decimal("160000.00")` (slide 8,
        marcador móvil — direccion lo fija manualmente, fuente real sin
        confirmar; equivalente a `INVERSION_TECNOLOGICA_PROVISIONAL` de
        Valencia).
      - Lista `comisiones_atrasos` hardcoded del PDF manual (slide 7 Parte C)
        mientras la ingesta de `comisiones_atrasos_directores` carga
        sede='Alicante'.

### Arquitectura del calculator multi-sede — Opción B (✅ APLICADA 2026-05-22)

**Decisión final:** dispatcher + un calculator por sede. NO un único calculator
con `if sede ==` (Opción A) ni con `SedeConfig` paramétrico (Opción C).

**Razón:** las diferencias entre sedes son estructurales (slides distintos,
plantilla distinta, distinto conjunto de productos). Una `SedeConfig` no modela
bien diferencias de **estructura del informe**.

**Detonante del refactor:** al desplegar Alicante en producción se descubrió
que el endpoint `/generar-desde-db` usaba siempre `SLIDES_TEMPLATE_ID`
hardcoded (la plantilla de Valencia con 12 slides) y `build_payload_slide_2`
del calculator de Valencia, aunque la petición trajera `sede="Alicante"`.
Resultado: PDF con plantilla de Valencia y datos de Alicante. Forzó completar
el refactor (que estaba en espera).

**Estado actual (2026-05-22):**
- `app/calculator_base.py` — queries comunes parametrizadas por `sede` +
  helpers + dataclasses. Cada query valida `sede in SEDES_VALIDAS`.
- `app/calculator.py` — **DISPATCHER**. Funciones:
  - `build_payload(sede, anyo, mes, escenario)` despacha a
    `calculator_valencia.build_payload(...)` o
    `calculator_alicante.build_payload(...)` según sede.
  - `template_id_for(sede)` lee `SLIDES_TEMPLATE_ID_<SEDE>` del entorno y
    devuelve el ID de la plantilla a usar.
- `app/calculator_valencia.py` — calculator de Valencia (antes vivía en
  `calculator.py`). Función entrada `build_payload(sede, anyo, mes, escenario)`.
- `app/calculator_alicante.py` — calculator de Alicante. Función entrada
  `build_payload(anyo, mes, escenario)` (sin parámetro `sede`, es constante
  `SEDE = "Alicante"`).

**Variables de entorno** (cambio breaking en `.env`):
- ❌ Eliminada: `SLIDES_TEMPLATE_ID`.
- ✅ Nuevas: `SLIDES_TEMPLATE_ID_VALENCIA`, `SLIDES_TEMPLATE_ID_ALICANTE`.
- Si una sede pide su plantilla y la env var no existe → `RuntimeError`
  explícito en lugar de generar un PDF con plantilla equivocada.

**Endpoints actualizados:**
- `GET /health` → devuelve `{templates: {Valencia: ..., Alicante: ...}, user_email: ...}`.
- `POST /generar-informe` y `POST /generar-desde-db` → resuelven el template
  por sede vía `template_id_for(sede)` y pasan `template_id` explícito a
  `generate_report`. Antes el fallback genérico era Valencia siempre.

**`generate_report` (app/generator.py):** `template_id` ahora es
**obligatorio** (antes era `Optional` con fallback a env). Cualquier caller
debe resolver el template antes de invocar `generate_report`.

## Riesgo del orden de aplicación (en migraciones futuras)

El cambio de modelo de datos + el cambio de código + el cambio de ingesta
n8n tienen que aplicarse **coordinados** para evitar downtime:

1. Bajar/pausar workflow n8n de ingesta para que no inserte en tablas
   viejas.
2. Aplicar las queries SQL en una transacción (donde sea posible).
3. Desplegar el cambio de código (`calculator_base` + `dispatcher`).
4. Reanudar/actualizar workflows n8n con los nuevos nombres de tabla.
5. Validar generando un PDF de Valencia abril 2026 (debe seguir saliendo
   idéntico).

Validado en producción durante mayo 2026 con las 5 migraciones de tabla.

---

# Guía para añadir una sede nueva (ej. Castellón)

Esta sección recoge **todo el aprendizaje** acumulado durante la integración
de Alicante (mayo 2026). El objetivo: que un agente futuro pueda añadir
Castellón (o cualquier sede) sin descubrir las mismas trampas. Lee esta
sección entera **antes** de tocar código.

## Resumen ejecutivo del enfoque

La arquitectura multi-sede del proyecto se basa en **3 capas**:

1. **BD compartida con columna `sede`**: una sola tabla por concepto, con
   columna `sede TEXT NOT NULL`. Filas distinguidas por sede. Queries
   filtran con `WHERE sede = %(sede)s`. **No se separan tablas por sede.**
2. **`calculator_base.py`**: queries y helpers compartidos. Cada query
   recibe `sede` como primer parámetro y valida `sede in SEDES_VALIDAS`.
3. **Un calculator por sede** (`calculator_<sede>.py`): compone el dict
   de tokens del payload. Tiene constantes propias (nº directores, sueldo
   fijo, tramo si fuera fijo). **No `if sede ==`**: cada calculator es
   independiente; el dispatcher (caller) elige cuál llamar.

## Pre-requisitos antes de empezar

### 1. Plantilla de Google Slides para la nueva sede

- **Plantilla independiente**. Otro Google Slides (con su propio ID), copiada
  de la sede más parecida (Valencia o Alicante) y adaptada visualmente. NO
  compartas la plantilla con otra sede. El ID se configurará después en
  `SLIDES_TEMPLATE_ID_<SEDE>` del `.env`.
- Decidir **estructuralmente** qué slides lleva (puede ser ≠ a Valencia y
  Alicante). Documentar las diferencias arriba en este documento.
- Compartir la plantilla con la Service Account (`sistemas@…` Workspace) con
  permiso Editor, o moverla a la Shared Drive corporativa.

### 2. Datos en Postgres

Antes de tocar código, **TODAS estas tablas deben tener filas con
`sede='<Sede>'`** (o estar pactado que la sede no aporta datos a esa
tabla — ej. Alicante no tiene `comisiones_atrasos_directores` aún):

- `finanzas_automation.ventas_comerciales`
- `informes_financieros.contabilidad_mensual` (mes a generar + mes anterior
  + mes siguiente para BE proyectado)
- `informes_financieros.pagos_directores` (al menos 1 fila con
  `(anio, mes, sede, porcentaje)` para el tramo de comisión)
- `informes_financieros.pago_agentes` (cobros pendientes)
- `informes_financieros.comisiones_atrasos_directores` (si aplica)
- `informes_financieros.resumen_mensual_arras`
- `informes_financieros.resumen_mensual_arras__sin_condicion`
- `informes_financieros.resumen_mensual_alquileres`
- `informes_financieros.resumen_mensual_alquiler_senales`

Sin estos datos, el calculator emitirá tokens vacíos y el PDF saldrá con
`{{...}}` sin reemplazar (o con valores 0/None). La ingesta n8n debe
**etiquetar explícitamente con `sede`** en el INSERT/UPSERT (no confiar en
el DEFAULT — Alicante no tiene DEFAULT que la cubra).

### 3. Constantes de negocio acordadas con dirección

- Nº directores (`N_DIRECTORES`).
- Sueldo fijo bruto director (`SUELDO_FIJO_DIRECTOR`).
- ¿Hay alquileres? ¿obra nueva? ¿operaciones condicionadas?
  Estas decisiones determinan qué slides lleva el informe.
- ¿Qué columna de rentabilidad se muestra? (`rentabilidad_operativa_pct`
  como Valencia, `rentabilidad_real_pct` como Alicante, u otra).

## Procedimiento slide por slide

Para CADA slide del informe:

### Paso 1: Inspeccionar BD antes de tocar nada

Query directa a Postgres con la sede nueva y el mes a generar. Detectar:
- Si la tabla tiene `sede` y filtra bien.
- Si la sede tiene datos para el mes pedido.
- Discrepancias con cualquier PDF manual de referencia (= "P-18
  equivalente"; verás esto siempre, es naturaleza estado vivo + ingesta
  asíncrona).
- Rarezas en los datos: filas con `arras_firmadas='CAÍDA'` sin `-0`,
  valores 0 que el filtro no excluye, etc.

### Paso 2: Identificar tokens del slide

Mirar:
- El JSON mock de una sede ya integrada (`data/mock_abril_2026_alicante.json`).
- El bloque correspondiente del calculator de una sede ya integrada
  (ej. `calculator.py` Valencia o `calculator_alicante.py`).
- La plantilla de Google Slides de la sede nueva.

Identifica qué tokens reutilizar tal cual, cuáles necesitan formato
distinto, cuáles son nuevos para esta sede.

### Paso 3: Decisiones de negocio surgidas en el slide

**NO asumas nunca**. Si un slide tiene dos interpretaciones razonables,
pregunta al usuario. Ejemplos reales encontrados con Alicante:

- ¿La base del Break Even es `ingresos_contables` (Valencia) o
  `arras_firmadas` (Alicante elige esto para el marcador móvil)?
- ¿La narrativa del Break Even usa el mismo importe o uno distinto?
- ¿`facturacion_objetivo_proy` viene de BD o es constante manual?
- ¿La columna ESTADO del slide BE proyectado se emite o es texto fijo?
- ¿Qué hacemos cuando BD tiene datos vivos que divergen del PDF manual?
  (respuesta default: confiar en BD).

### Paso 4: Reutilizar funciones de `calculator_base`

Si una función ya existe y recibe `sede`, **úsala**. Si vive aún en
`calculator.py` (Valencia) y la necesitas, **muévela a base
parametrizada** antes de seguir (caso real: `_query_pipeline_ventas` movida
a base con `inmuebles_excluir_ilike` parametrizado).

### Paso 5: Ampliar `calculator_<sede>.py`

- Añadir queries necesarias a `calculator_base.py` si no existen.
- En el calculator de la sede: añadir lecturas, cálculos, tokens al
  `return`, color overrides relevantes.
- Documentar **diferencias específicas de la sede** con comentarios `# OJO`
  en el código.

### Paso 6: Dry-run con UTF-8

```powershell
python -X utf8 -c "from app.calculator_<sede> import build_payload; print(build_payload(2026, 4))"
```

⚠️ Windows console NO maneja Unicode (▲ ▼ €) sin `-X utf8`. Sin esto,
`UnicodeEncodeError` aborta el print a mitad y parece que el código falla
cuando solo es el terminal.

### Paso 7: Generar PDF y validar visualmente

```powershell
python scripts/generar_<sede>_desde_db.py 2026 4
```

El usuario abre el PDF y valida visualmente. Si hay tokens `{{...}}` sin
reemplazar, son los que el calculator aún no emite o están mal escritos en
la plantilla (espacios, mayúsculas, ñ).

### Paso 8: Marcar slide completed y al siguiente

Usar TodoWrite para llevar la cuenta visible. No avanzar al siguiente
slide hasta que el actual esté visualmente correcto.

## Trampas conocidas (no las pises de nuevo)

### 1. `apply_color_overrides` busca por SUBCADENA, no por match exacto

`find_text_locations(deck, valor)` recorre **todas las cajas** y devuelve
las que contienen el valor. Implicaciones:

- **Dos tokens con el mismo valor pintan ambas cajas**. Si
  `{{var_reservas_mom}}` (slide 2, color verde) y
  `{{var_reservas_mom_observacion}}` (slide 9, color amarillo) tienen el
  mismo string ("+13,9 %"), el override del slide 9 también pinta la caja
  del slide 2. **Solución**: añadir `​` (zero-width space, U+200B) al
  final de uno de los dos. Visualmente idénticos, distintos para el
  `find_text_locations`.
- **Un valor que aparece en una narrativa pinta la narrativa entera**. Si
  `{{margen_seguridad}}` = "84.907 €" tiene override verde y la narrativa
  dice "...margen de seguridad de 84.907 €...", la narrativa entera sale
  verde. **Solución**: que las narrativas generadas NO contengan los
  valores de tokens con color override. La función `_narrativa_break_even`
  ya está corregida así (2026-05-22).
- **`updateTextStyle` con `textRange: ALL` pinta toda la caja**, no solo
  el rango del valor. Si dos tokens conviven en una caja con colores
  distintos, el último gana. **Solución**: separar en cajas distintas en
  la plantilla.

Ver `memory/feedback_color_caja_unica.md` para detalle completo con casos
reales.

### 2. `_variacion(actual, anterior)` invierte el signo cuando `anterior < 0`

Fórmula clásica `(actual - anterior) / anterior` da resultados engañosos
cuando el denominador es negativo. Caso real: rentabilidad pasó de -27,62 %
(marzo) a +32,25 % (abril) — claramente una mejora. Pero
`(0.3225 - (-0.2762)) / (-0.2762) = -2,1676` → "-216,76 %" rojo.

**Soluciones disponibles** (ver código + memorias):
- `_variacion_tasa` en `calculator_base.py` (heurística `abs(ratio)` si
  `anterior<0`). Hoy usado en `var_rentab_mom` de Alicante.
- Diferencia en puntos porcentuales (resta directa). Memoria
  `feedback_puntos_porcentuales_vs_variacion_relativa.md` dice que ese
  debería ser el patrón estándar al comparar TASAS. Hay inconsistencia
  pendiente de resolver entre las dos memorias; al añadir una sede nueva
  conviene **consultar al usuario** qué fórmula aplicar.

### 3. Discrepancias BD vs PDF manual son normales (P-18 equivalente)

Cuando la nueva sede genera un PDF y los importes no coinciden con el PDF
manual histórico de referencia, **es esperado**:
- La BD se actualiza después de generar el PDF manual.
- Estado vivo: operaciones firmadas/cobradas/caídas cambian.
- Errores en el cuadro manual de origen.

**NO hardcodear los valores del PDF para "que coincida"**. Confiar en BD,
documentar la discrepancia (P-18 equivalente de la sede) y validar con
contabilidad cuando se pueda. Excepción: constantes manuales explícitas
(como `INVERSION_TECNOLOGICA_PROVISIONAL` Valencia o
`FACTURACION_OBJETIVO_PROY_PROVISIONAL` Alicante) que SÍ vienen del PDF
mientras no se aclare su fuente.

### 4. Formato numérico: max 1 decimal omitiendo ',0'

Decisión 2026-05-22 (Alicante): para variaciones MoM del slide 2 usar
`format_pct_signed_compacto(valor, decimales_max=1)` que omite la coma
decimal cuando el valor es entero al redondear. Ejemplos:
- 0.139 → "+13,9 %"
- 2.0102 → "+201 %" (no "+201,0 %")
- 1.64692 → "+164,7 %"

Patrón coincide con el estilo del PDF manual de Alicante. Para Castellón:
preguntar al usuario qué estilo prefiere (mismo que Alicante, mismo que
Valencia con `format_pct_signed`, o mezcla).

### 5. Token `{{contratos_firmados}}` puede tener dos significados según slide

En el slide 6 de Alicante (Break Even), `{{contratos_firmados}}` aparece en
el marcador móvil de la barra ("ARRAS FIRMADAS · 218.990 €") pero los
**estados de la tabla** y el **margen de seguridad** se calculan contra
bases distintas:
- Marcador móvil + estados tabla → `arras_firmadas` (= `contratos_firmados`)
- Margen seguridad + narrativa → `ingresos_contables`

No es contradictorio: el marcador comunica "lo vendido", la narrativa
"lo cobrado". Si Castellón vuelve a aparecer este caso, replicar el patrón
de Alicante o usar la base de Valencia (`ingresos_contables` para todo) si
el slide es estructuralmente igual a Valencia.

### 6. n_max de listas variables: declarado en `LIST_SPECS` (generator.py)

Si la sede nueva tiene slides con listas variables (cobros, pipeline,
condicionadas), los `n_max` se declaran en `app/generator.py` como
`LIST_SPECS`. Si el `n_max` de una lista es menor que los items reales,
el helper `slots()` trunca con WARNING. Ajustar antes de generar.

Ejemplos actuales:
- `ventas_pendientes` → `n_max=21` (3 columnas × 7 filas)
- `pipeline_alquiler` (con prefijo `venta_alq_pend`) → `n_max=7`
- `cobros_pendientes` → `n_max=26`
- `condicionadas` → `n_max=22`

### 7. Plantillas con elementos del PDF de referencia "hardcoded" a colores

Cuando se duplica una plantilla, los colores de cajas (verde/rojo) se
copian tal cual del PDF de referencia. Si el orden de "✓ SUPERADO" / "FALTAN"
cambia respecto al PDF original, los colores fijos quedan **desincronizados
del texto**. Solución: emitir color overrides para los `*_estado` desde el
calculator (ver `calculator_alicante.py:_estado_umbral` + bloque de overrides
slide 6). El color del override **debe usar la misma base** que el cálculo
del texto del estado (en Alicante, `base_be = arras_firmadas`; en Valencia,
`ingresos_be = ingresos_contables`).

### 8. Editor de calculator: NO usar `if sede ==`

Si te tientan los condicionales por sede dentro de funciones compartidas:
**no lo hagas**. Cada sede debe tener su `calculator_<sede>.py`
independiente. Las diferencias estructurales (slides distintos, qué
tabla muestra qué) no encajan en una única función con ramas.

La ÚNICA excepción permitida es `app/calculator.py` (el dispatcher), que
solo enruta `sede → módulo correspondiente` y no contiene lógica de
negocio. Cualquier `if sede ==` fuera de ahí huele a deuda técnica.

### 9. `docker-compose.yml` filtra qué variables del `.env` ven los contenedores

**Lección aprendida en producción 2026-05-22.** Tras el refactor que
añadió `SLIDES_TEMPLATE_ID_VALENCIA` y `SLIDES_TEMPLATE_ID_ALICANTE` al
`.env`, el servicio en producción fallaba con:

> Bad request - please check your parameters
> Falta la variable de entorno SLIDES_TEMPLATE_ID_ALICANTE para la sede 'Alicante'.

Causa: aunque las variables estaban en `.env`, **`docker-compose.yml`
filtra explícitamente** qué env vars llegan al contenedor en su bloque
`environment:`. La línea vieja era:

```yaml
SLIDES_TEMPLATE_ID: ${SLIDES_TEMPLATE_ID}
```

Y no había referencias a las dos nuevas. Resultado: el contenedor leía
`os.environ["SLIDES_TEMPLATE_ID_ALICANTE"]` y devolvía `""`.

**Política**: cada vez que se añade una env var nueva en `.env`, hay que
añadirla también al bloque `environment:` de `docker-compose.yml`. En
local con `.venv` no se nota porque Python lee `.env` directo, pero en
prod con Docker hay un punto de filtrado intermedio.

Cómo diagnosticarlo rápido:

```bash
# Desde el host del servidor:
docker exec informes-financieros-api env | grep SLIDES_TEMPLATE
# Si no aparecen las dos sedes -> docker-compose.yml mal.

# O directamente al /health (no requiere API Key):
curl -s http://localhost:8012/health
# Debe devolver "templates": {"Valencia": "...", "Alicante": "..."}
```

Si `templates` viene vacío o falta una sede, el `compose.yml` está
desactualizado.

Tras corregir `docker-compose.yml` no basta con `docker compose restart`:
hay que **recrear el contenedor** para que relea el bloque `environment`:

```bash
docker compose down
docker compose up -d --build
```

### 10. Endpoint `/health` es el primer chequeo tras desplegar

Resumen práctico: tras cualquier deploy que toque envvars o
configuración de plantilla, **lo primero es llamar a `/health`** y leer
el campo `templates`:

```bash
curl -s http://localhost:8012/health
# Esperado:
# {
#   "status": "ok",
#   "templates": {"Valencia": "1HQ...", "Alicante": "1uQ..."},
#   "user_email": "informes-bot-prod@..."
# }
```

Si:
- `templates` está vacío `{}` → las dos env vars no llegan al
  contenedor (revisar `docker-compose.yml`).
- `templates` tiene solo una sede → revisar la línea exacta del `.env`
  de la sede ausente (espacios sobrantes, comillas, etc.).
- `user_email` es `null` → el contenedor arrancó pero falla al hablar
  con Google (Service Account mal montada o sin permisos sobre el
  Shared Drive).
- Conexión rechazada / timeout → el contenedor no está corriendo
  (`docker ps` para confirmar).

`/health` **no requiere `X-API-Key`**: es público dentro de la red
Docker. Pensado precisamente para que healthchecks y diagnósticos no
dependan de credenciales.

## Checklist resumido para Castellón (o futura sede X)

### Pre-requisitos externos
- [ ] Plantilla Google Slides creada y compartida (Editor) con la Service
      Account corporativa.
- [ ] ID de la plantilla anotado (parte del URL después de `/d/`).
- [ ] Datos de la sede X cargados en Postgres (todas las tablas con
      `sede='X'`).
- [ ] Constantes acordadas con dirección: `N_DIRECTORES`, `SUELDO_FIJO`,
      rentabilidad_op vs real, presencia de alquileres/obra
      nueva/condicionadas.

### Código
- [ ] Añadir `"X"` a `SEDES_VALIDAS` en `app/calculator_base.py`.
- [ ] Crear `app/calculator_<sede>.py` partiendo del calculator más
      parecido (Valencia si la sede tiene todos los productos; Alicante
      si es más simple). Mantener `SEDE = "X"` como constante de módulo.
      Exponer función `build_payload(anyo, mes, escenario)` (sin `sede`
      porque el módulo es de una sola sede).
- [ ] Añadir rama en el dispatcher `app/calculator.py`:
      ```python
      if sede == "X":
          from app.calculator_<sede> import build_payload as _build
          return _build(anyo=anyo, mes=mes, escenario=escenario)
      ```
- [ ] (Opcional) Crear `scripts/generar_<sede>_desde_db.py` para
      iteración rápida en local sin pasar por el endpoint.

### Configuración (CRÍTICO: 3 sitios distintos)

Cada vez que se añade una sede hay que actualizar **TODOS** estos sitios.
Saltarse uno = el servicio en producción falla con un mensaje claro
("Falta la variable de entorno SLIDES_TEMPLATE_ID_X").

- [ ] **`.env` local**: añadir `SLIDES_TEMPLATE_ID_<X>=<ID>`.
- [ ] **`.env` del servidor de producción**: lo mismo.
- [ ] **`docker-compose.yml`** (bloque `environment:` del servicio
      `informes-api`): añadir
      `SLIDES_TEMPLATE_ID_<X>: ${SLIDES_TEMPLATE_ID_<X>}`.
      Sin esto, aunque la variable esté en `.env`, el contenedor no
      la verá (ver Trampa 9).

### Validación
- [ ] Recorrer slides en el orden de la plantilla, validando visualmente
      tras cada uno.
- [ ] Generar PDF de la sede en local: `python scripts/generar_desde_db.py X 2026 4`.
      Debe pasar sin errores; verificar visualmente las primeras 2-3 slides.
- [ ] Hacer commit por hitos (no commit gigante al final).

### Deploy a producción
- [ ] `git push` desde local.
- [ ] En servidor: `git pull`.
- [ ] Confirmar que `.env` del servidor tiene `SLIDES_TEMPLATE_ID_<X>`.
- [ ] **Recrear el contenedor** (no basta `restart`):
      `docker compose down && docker compose up -d --build`.
- [ ] **Validar con `/health`**:
      `curl -s http://localhost:8012/health`. El campo `templates` debe
      incluir la sede X. Si no aparece → revisar Trampa 9.
- [ ] Probar generación end-to-end desde n8n con
      `{"sede": "X", "anyo": ..., "mes": ...}`.

### Documentación
- [ ] Actualizar este documento (`docs/MIGRACION_MULTISEDE.md`) con las
      decisiones específicas de la sede X.
- [ ] Actualizar `memory/project_diferencias_valencia_alicante.md`
      (renombrar a algo más genérico tipo
      `project_diferencias_por_sede.md` si ya hay 3+ sedes).
- [ ] Si la sede X descubre alguna trampa nueva no listada,
      añadirla a la sección "Trampas conocidas".

## Tiempo estimado

Integración de Alicante completa (sesión 2026-05-22):
- Sesión de tokenización de plantilla: ~3 horas (1 vez al inicio).
- Integración slide a slide: ~30 min por slide cuando los datos están
  en BD y no hay decisiones de negocio complejas; hasta 1 h en slides con
  decisiones (BE, Comisiones).
- Total Alicante: ~6-8 horas distribuidas en varias sesiones.

Castellón debería ser **más rápido** porque la arquitectura ya está
probada y el patrón está documentado.
