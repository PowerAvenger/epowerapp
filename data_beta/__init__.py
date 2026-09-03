"""Capa de datos beta de ePowerAPP.

Los datos reales viven fuera de Git, en ``.local_data``. Este paquete solo
contiene el esquema, migraciones e importadores reproducibles.
"""

from .db import DEFAULT_DB_PATH, connect, initialize_database

__all__ = ["DEFAULT_DB_PATH", "connect", "initialize_database"]
