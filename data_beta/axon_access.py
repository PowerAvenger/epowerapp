"""Consultas de solo lectura para el selector privado de suministros Axon."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from .db import DEFAULT_DB_PATH


def listar_suministros_axon(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, str]]:
    ruta = Path(db_path)
    if not ruta.is_file():
        return []
    with closing(sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)) as conexion:
        conexion.row_factory = sqlite3.Row
        filas = conexion.execute(
            """
            SELECT cups20, denominacion, atr, credencial_curva_ref
            FROM suministros
            WHERE UPPER(TRIM(COALESCE(proveedor_curva_actual, ''))) = 'AXON'
            ORDER BY COALESCE(denominacion, ''), cups20
            """
        ).fetchall()
    return [
        {
            "cups": str(fila["cups20"]),
            "denominacion": str(fila["denominacion"] or ""),
            "atr": str(fila["atr"] or "").strip(),
            "credencial_ref": str(fila["credencial_curva_ref"] or ""),
        }
        for fila in filas
    ]
