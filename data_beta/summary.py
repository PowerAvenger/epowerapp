from __future__ import annotations

from pathlib import Path

from .db import DEFAULT_DB_PATH, connect


def database_summary(path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    tables = (
        "import_batches",
        "legacy_records",
        "titulares",
        "suministros",
        "titularidades_suministro",
        "contratos",
        "filas_contrato_origen",
    )
    with connect(path) as connection:
        result = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
        result["cups_con_cambio_titular"] = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT suministro_id
                    FROM titularidades_suministro
                    GROUP BY suministro_id
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
        )
        result["titularidades_pendientes"] = int(
            connection.execute(
                """
                SELECT COUNT(*) FROM titularidades_suministro
                WHERE estado_fecha = 'pendiente'
                """
            ).fetchone()[0]
        )
    return result
