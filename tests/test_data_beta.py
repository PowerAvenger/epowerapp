from __future__ import annotations

import csv
from pathlib import Path

from data_beta.db import initialize_database
from data_beta.importers import cups20, import_excel_supplies
from data_beta.summary import database_summary


def test_cups20_recorta_extensiones() -> None:
    assert cups20("ES0021000004112626DQ0F") == "ES0021000004112626DQ"


def test_importacion_es_repetible(tmp_path: Path) -> None:
    source = tmp_path / "suministros.tsv"
    fields = (
        "ID_CUPS", "TITULAR_CONTRATO", "ID_TITULAR_CONTRATO", "CUPS",
        "DENOMINACION", "DISTRIBUIDORA", "ATR", "TPM", "TG",
        "REF_CONTRATO_ACCESO", "DIRECCION_SUMINISTRO_1", "DIRECCION_SUMINISTRO_2",
    )
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerow(
            {
                "ID_CUPS": "1",
                "TITULAR_CONTRATO": "Titular de prueba",
                "ID_TITULAR_CONTRATO": "7",
                "CUPS": "ES0021000004112626DQ0F",
                "TPM": "4",
                "TG": "DAT",
            }
        )
    db = tmp_path / "beta.sqlite3"
    initialize_database(db)
    first = import_excel_supplies(source, db)
    second = import_excel_supplies(source, db)
    summary = database_summary(db)
    assert first["imported"] == 1
    assert second["imported"] == 0
    assert summary["suministros"] == 1
    assert summary["titulares"] == 1
    assert summary["titularidades_suministro"] == 1
