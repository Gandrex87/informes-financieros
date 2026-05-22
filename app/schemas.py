"""
Modelos Pydantic para validar la entrada del endpoint /generar-informe.

Estrategia: payload muy flexible (Dict[str, Any]) porque los tokens
del informe son muchos y heterogeneos. La validacion estricta sera mejor
cuando integremos Postgres y conozcamos el contrato definitivo.

Por ahora exigimos solo los campos minimos imprescindibles.
"""
from typing import Any

from pydantic import BaseModel, Field


class GenerarInformeRequest(BaseModel):
    """Payload del endpoint /generar-informe.

    Acepta cualquier conjunto de tokens. Solo valida que existan los minimos
    (sede y mes_año) para generar un nombre de archivo coherente.

    Las listas variables (pipeline_alquiler, cobros_pendientes, etc.) van
    embebidas en el mismo payload y se expanden a slots automaticamente.

    Campo opcional especial:
        _color_overrides: dict {token_name: color_name}, ej.
            {"margen_30_estado": "rojo", "break_even_estado": "verde"}
        Los colores disponibles estan definidos en app/colors.py.
    """

    sede: str = Field(..., description="Nombre de la sede, ej. 'Valencia'.")
    mes_año: str = Field(..., description="Mes y año en formato 'Abril 2026'.")

    # Permitir cualquier otro campo (el resto de tokens + _color_overrides).
    model_config = {"extra": "allow"}

    def to_data_dict(self) -> dict[str, Any]:
        """Devuelve el payload completo como dict, listo para generator."""
        return self.model_dump()


class HealthResponse(BaseModel):
    status: str
    templates: dict[str, str] = Field(
        default_factory=dict,
        description="Mapa de sede -> Slides template ID. Hay un template por sede.",
    )
    user_email: str | None = None


class GenerarDesdeDBRequest(BaseModel):
    """Payload del endpoint /generar-desde-db.

    Solo recibe identificadores. El servicio se encarga de leer Postgres
    (via calculator) y componer el payload completo internamente.
    """

    sede: str = Field(..., description="Nombre de la sede, ej. 'Valencia'.")
    anyo: int = Field(..., ge=2020, le=2100, description="Año en 4 digitos.")
    mes: int = Field(..., ge=1, le=12, description="Mes 1-12.")
    escenario: str = Field(
        "con_crm",
        description="Escenario contable: 'solo' | 'con_crm'.",
    )
