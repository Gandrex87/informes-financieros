"""
Helpers para transformar datos estructurados en tokens planos.

La Slides API solo entiende replaceAllText con tokens individuales,
pero queremos manejar listas en el JSON/Postgres. Estos helpers
convierten listas en slots numerados.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def slots(
    items: list[dict],
    prefix: str,
    n_max: int,
    fields: list[str],
    on_overflow: str = "warn",
) -> dict[str, str]:
    """Convierte una lista de dicts en slots numerados.

    Ejemplo:
        items = [{"nombre": "X", "importe": "100"}, {"nombre": "Y", "importe": "200"}]
        slots(items, "pipeline", n_max=4, fields=["nombre", "importe"])
        # =>
        # {
        #   "pipeline_1_nombre": "X", "pipeline_1_importe": "100",
        #   "pipeline_2_nombre": "Y", "pipeline_2_importe": "200",
        #   "pipeline_3_nombre": "",  "pipeline_3_importe": "",
        #   "pipeline_4_nombre": "",  "pipeline_4_importe": "",
        # }
    """
    if len(items) > n_max:
        msg = f"slots('{prefix}'): {len(items)} items pero n_max={n_max}. Truncando."
        if on_overflow == "error":
            raise ValueError(msg)
        if on_overflow == "warn":
            logger.warning(msg)

    result: dict[str, str] = {}
    for i in range(n_max):
        for field in fields:
            key = f"{prefix}_{i + 1}_{field}"
            if i < len(items):
                result[key] = str(items[i].get(field, ""))
            else:
                result[key] = ""
    return result


def expand_lists(data: dict[str, Any], specs: list[dict]) -> dict[str, str]:
    """Expande listas dentro de un dict a slots planos.

    Una misma clave puede aparecer en varios specs (con distintos prefijos)
    para alimentar varios juegos de slots desde la misma lista de datos.
    """
    list_keys = {s["key"] for s in specs}
    result = {k: v for k, v in data.items() if k not in list_keys}
    for spec in specs:
        items = data.get(spec["key"], [])
        result.update(
            slots(
                items=items,
                prefix=spec["prefix"],
                n_max=spec["n_max"],
                fields=spec["fields"],
            )
        )
    return result
