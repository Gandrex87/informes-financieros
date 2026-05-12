# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Propósito

Automatización del **Informe Directores Comerciales** mensual de Lion Capital Real Estate. Hoy es un proceso manual sobre una plantilla de Google Slides (12 slides) que se exporta a PDF. El objetivo final es Google Sheets → Postgres → Python → Google Slides → PDF, multi-sede (Valencia, Castellón, Alicante).

El repo está en **iteración 1.x** (POC del path Slides→PDF con datos mock). Postgres, n8n, FastAPI y matplotlib **todavía no existen en el código** — sólo están en la arquitectura objetivo.

## Comandos

PowerShell desde la raíz:

```powershell
# Setup (una vez)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Verificar credenciales y acceso a la plantilla (no muta nada)
python scripts/test_auth.py

# Generar PDF con datos mock (copia plantilla → reemplaza tokens → exporta PDF → borra copia)
python scripts/generate_mock.py
```

No hay tests, linter ni build configurados todavía.

## Arquitectura

### Flujo actual (iteración 1.2) — [scripts/generate_mock.py](scripts/generate_mock.py)

1. Carga datos mock desde [data/mock_abril_2026.json](data/mock_abril_2026.json) (dict plano `token → string ya formateado`).
2. `drive.files().copy()` de `SLIDES_TEMPLATE_ID` a un archivo temporal `_tmp_informe_<timestamp>`.
3. `slides.presentations().batchUpdate()` con un `replaceAllText` por token. Los tokens en la plantilla tienen forma `{{nombre}}`. Los valores se pasan **ya formateados como string** (incluyen `€`, `%`, signos, comas decimales en español).
4. `drive.files().export_media(mimeType="application/pdf")` → guarda a `output/informe_mock_<timestamp>.pdf`.
5. `drive.files().delete()` de la copia, en `finally`, para no dejar basura en Drive.

Si un token del JSON no aparece en la plantilla, se imprime `AVISO` pero no falla — útil mientras la plantilla y los datos divergen entre iteraciones.

### Autenticación

Service account JSON local (`credentials/service_account.json`, gitignored). La plantilla de Slides **debe estar compartida como Editor** con el email de la service account, o `drive.files().copy()` devuelve 404. `scripts/test_auth.py` imprime ese email para facilitar el share.

Scopes usados en ambos scripts:
- `https://www.googleapis.com/auth/presentations`
- `https://www.googleapis.com/auth/drive`

Variables en `.env` (ver `.env.example`):
- `GOOGLE_APPLICATION_CREDENTIALS` — ruta relativa al JSON.
- `SLIDES_TEMPLATE_ID` — ID del Google Slides extraído de la URL.

### Referencias

- [informes_valencia_alicante/](informes_valencia_alicante/) — PDFs/PPTX históricos generados a mano. Son **la referencia visual de fidelidad** del PDF final, no se tocan.

## Decisiones de diseño a respetar

Estas decisiones están tomadas y no deberían rediscutirse al añadir código nuevo, salvo que el usuario las cuestione explícitamente:

- **Multi-sede desde el inicio.** v1 = Valencia, v2 = Castellón + Alicante. Cualquier estructura nueva (esquema Postgres, firmas de funciones, nombres de archivos de salida) debe llevar `sede` como parámetro, no añadirlo después.
- **Reproducibilidad histórica.** Debe poder regenerarse el informe de un mes pasado con los datos de ese momento. El (futuro) esquema de Postgres incluirá snapshot de datos por reporte y versión de plantilla usada.
- **Narrativa: templating determinista en Python, NO LLM.** La consistencia importa más que la variedad lingüística en un documento financiero.
- **Gráfico slide 3:** matplotlib → PNG → `insertImage`, no gráfico nativo de Slides vinculado a Sheet.
- **Tablas de longitud variable:** estrategia mixta — `insertTableRows` dinámico para tablas medianas (slides 6 y 9); tabla "máxima" con filas ocultas para slide 7 (2 columnas, layout delicado).
- **Comparativa YoY** requiere histórico ≥13 meses. Plan: carga histórica al arrancar, o período de transición con dato YoY manual.

## Estructura del informe (12 slides)

Contexto para entender qué token va dónde:

1. Portada (KPIs + sede + mes)
2. Resumen ejecutivo (4 KPIs con variaciones MoM/YoY)
3. Producción comercial (KPIs + gráfico de barras Mes-1, Mes-12, Mes actual)
4. Gestión alquileres (KPIs + pipeline corto)
5. Pipeline Q2 (lista multi-columna, longitud variable)
6. Operaciones condicionadas (tabla longitud variable)
7. Cobros pendientes (tabla larga ~20 ítems, 2 columnas)
8. Break Even mes actual (KPIs + tabla fija + narrativa generada)
9. Comisiones directores (KPIs + 2 tablas variables + cálculo derivado)
10. Break Even mes siguiente (proyección)
11. Semáforo estratégico (KPIs categorizados Fortalezas/Observación/Riesgo)
12. Hoja de ruta próximo mes (4 KPIs + objetivos)

## Convenciones

- Scripts ejecutables van en [scripts/](scripts/) y resuelven `ROOT` como `Path(__file__).resolve().parent.parent` para poder ejecutarse desde cualquier cwd.
- Comentarios y prints en español (es la lengua del proyecto y del usuario).
- Formato numérico español en los valores que llegan a Slides: `547.139 €`, `+33,70 %`, `-18 ops`. El formateo se hace **antes** de meter el valor en el dict de tokens.
