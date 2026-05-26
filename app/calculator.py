"""
Dispatcher de calculator por sede.

Cumple la decision arquitectonica Opcion B (ver
`memory/project_arquitectura_multisede.md` y `docs/MIGRACION_MULTISEDE.md`):
cada sede tiene su propio modulo de calculator (`calculator_valencia.py`,
`calculator_alicante.py`) y este dispatcher solo se encarga de elegir cual
invocar segun la sede pedida.

NO se combinan ramas `if sede ==` con logica de negocio: la unica rama
condicional aceptable aqui es el routing al modulo correcto. Cualquier
calculo o constante de negocio especifico de sede vive en su modulo.
"""
import os
from typing import Any

from app.calculator_base import SEDES_VALIDAS


def template_id_for(sede: str) -> str:
    """Resuelve el ID del Slides plantilla para la sede pedida.

    Lee `SLIDES_TEMPLATE_ID_<SEDE>` del entorno (ej.
    `SLIDES_TEMPLATE_ID_VALENCIA`, `SLIDES_TEMPLATE_ID_ALICANTE`). Si la
    variable no existe o esta vacia, lanza RuntimeError explicito en lugar
    de generar un PDF con la plantilla equivocada (leccion P-27).
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")
    var = f"SLIDES_TEMPLATE_ID_{sede.upper()}"
    tid = os.environ.get(var, "").strip()
    if not tid:
        raise RuntimeError(
            f"Falta la variable de entorno {var} para la sede {sede!r}. "
            f"Configura .env con la ID del Slides plantilla de {sede}."
        )
    return tid


def build_payload(
    sede: str,
    anyo: int,
    mes: int,
    escenario: str = "con_crm",
) -> dict[str, Any]:
    """Compone el payload de tokens segun la sede.

    Despacha al calculator correspondiente. La sede se valida pronto
    contra SEDES_VALIDAS.
    """
    if sede not in SEDES_VALIDAS:
        raise ValueError(f"Sede invalida: {sede!r}. Esperado uno de {SEDES_VALIDAS}.")

    if sede == "Valencia":
        # Import diferido para no penalizar el arranque cuando solo se usa
        # una sede, y para evitar ciclos si en el futuro hay imports cruzados.
        from app.calculator_valencia import build_payload as _build
        return _build(sede=sede, anyo=anyo, mes=mes, escenario=escenario)

    if sede == "Alicante":
        from app.calculator_alicante import build_payload as _build
        return _build(anyo=anyo, mes=mes, escenario=escenario)

    if sede == "Castellon":
        from app.calculator_castellon import build_payload as _build
        return _build(anyo=anyo, mes=mes, escenario=escenario)

    # Inalcanzable: SEDES_VALIDAS ya filtro arriba. Defensa por si se añade
    # una sede al set sin añadirla aqui.
    raise AssertionError(f"Sede '{sede}' valida pero sin dispatch implementado.")
