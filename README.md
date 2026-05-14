# Informes Financieros — Automatización

Generación automática del Informe Directores Comerciales de Lion Capital Real Estate.

## Estado actual

**Iteración 1.1** — Validar autenticación con Google Slides/Drive API.

## Setup inicial

### 1. Entorno Python

Desde la raíz del proyecto, en PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Credenciales

El archivo `credentials/service_account.json` (ignorado por git) contiene las
credenciales del robot que accede a Google Slides y Drive.

La plantilla de Slides debe estar compartida con la cuenta de servicio del
robot como **Editor**.

Variables de entorno en `.env`:

- `GOOGLE_APPLICATION_CREDENTIALS`: ruta al JSON de credenciales.
- `SLIDES_TEMPLATE_ID`: ID del Google Slides (extraído de la URL).

### 3. Prueba de autenticación

```powershell
python scripts/test_auth.py
```

Si todo va bien, verás los metadatos de la plantilla y el número de slides.

## Estructura

```
informes_financieros/
├── credentials/          # JSON del robot (gitignored)
├── scripts/              # Scripts ejecutables (auth, generación, etc.)
├── informes_valencia_alicante/   # Informes históricos manuales (referencia)
├── .env                  # Variables locales (gitignored)
├── .env.example          # Plantilla de variables
└── requirements.txt
```

docker compose build

docker compose up -d
