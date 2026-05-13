"""
Conexion a Postgres compartida para el calculator.

Crea una conexion bajo demanda (no pool aun, no es necesario para uso mensual).
Cuando vayamos a produccion con concurrencia, migrar a psycopg_pool.
"""
import logging
import os
from contextlib import contextmanager

import psycopg

logger = logging.getLogger(__name__)


def get_dsn() -> str:
    """Construye el DSN a partir de variables de entorno."""
    return (
        f"host={os.environ['POSTGRES_HOST']} "
        f"port={os.environ['POSTGRES_PORT']} "
        f"dbname={os.environ['POSTGRES_DB']} "
        f"user={os.environ['POSTGRES_USER']} "
        f"password={os.environ['POSTGRES_PASSWORD']}"
    )


@contextmanager
def connection():
    """Context manager para obtener una conexion. Se cierra automaticamente."""
    conn = psycopg.connect(get_dsn(), row_factory=psycopg.rows.dict_row)
    try:
        yield conn
    finally:
        conn.close()
