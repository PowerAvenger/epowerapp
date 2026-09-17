import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from data_beta.contract_periods import (
    guardar_periodo_contrato,
    listar_periodos_cups,
    sugerir_cambios_contrato,
)
from data_beta.db import connect, initialize_database


class TestContractPeriods(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "prueba.sqlite3"
        initialize_database(self.db)
        with connect(self.db) as connection:
            suministro = connection.execute(
                """INSERT INTO suministros(cups20, cups_original)
                VALUES ('ES0022000009064699LH', 'ES0022000009064699LH')"""
            ).lastrowid
            self.contrato = connection.execute(
                """INSERT INTO contratos(
                    suministro_id, comercializadora,
                    referencia_comercializadora, origen
                ) VALUES (?, 'NATURGY', '01422210000194', 'USER_CONFIRMED')""",
                (suministro,),
            ).lastrowid

    def tearDown(self):
        self.tempdir.cleanup()

    def test_registra_renovacion_sin_crear_otro_contrato_comercial(self):
        guardar_periodo_contrato(
            self.contrato, date(2024, 10, 1), date(2025, 9, 30),
            db_path=self.db,
        )
        nuevo_id = guardar_periodo_contrato(
            self.contrato, date(2025, 10, 1), date(2026, 9, 30),
            db_path=self.db,
        )
        periodos = listar_periodos_cups("ES0022000009064699LH", self.db)
        self.assertEqual(len(periodos), 2)
        self.assertEqual(periodos[1]["id"], nuevo_id)

        condiciones = pd.DataFrame([
            {"condicion_id": 55,
             "inicio_condicion": pd.Timestamp("2025-01-01"),
             "fin_condicion": pd.Timestamp("2025-09-30")},
            {"condicion_id": 44,
             "inicio_condicion": pd.Timestamp("2025-10-01"),
             "fin_condicion": pd.Timestamp("2025-10-27")},
            {"condicion_id": 42,
             "inicio_condicion": pd.Timestamp("2025-10-28"),
             "fin_condicion": pd.Timestamp("2025-12-31")},
        ])
        sugerencias = sugerir_cambios_contrato(
            periodos, condiciones, date(2025, 1, 1), date(2026, 9, 16)
        )
        self.assertEqual(len(sugerencias), 1)
        self.assertEqual(sugerencias[0]["inicio"], date(2025, 10, 1))
        self.assertEqual(sugerencias[0]["condicion_referencia_id"], 55)

    def test_rechaza_vigencias_solapadas(self):
        guardar_periodo_contrato(
            self.contrato, date(2025, 1, 1), date(2025, 12, 31),
            db_path=self.db,
        )
        with self.assertRaisesRegex(ValueError, "solapa"):
            guardar_periodo_contrato(
                self.contrato, date(2025, 10, 1), date(2026, 9, 30),
                db_path=self.db,
            )


if __name__ == "__main__":
    unittest.main()
