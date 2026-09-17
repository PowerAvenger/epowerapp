import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data_beta.analysis_history import cargar_analisis, guardar_analisis
from data_beta.db import connect, initialize_database


class TestAnalysisHistory(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "history.sqlite3"
        initialize_database(self.db)
        with connect(self.db) as connection:
            self.suministro = connection.execute(
                """INSERT INTO suministros(cups20, cups_original)
                VALUES ('ES0021000000000001AA', 'ES0021000000000001AA')"""
            ).lastrowid
            connection.execute(
                """INSERT INTO contratos(
                    suministro_id, comercializadora, vigente_desde,
                    vigente_hasta, origen
                ) VALUES (?, 'TEST', '2026-01-01', '2026-12-31', 'TEST')""",
                (self.suministro,),
            )

    def tearDown(self):
        self.tempdir.cleanup()

    def _guardar(self):
        return guardar_analisis(
            tipo="VERIFICACION", cups="ES0021000000000001AA",
            numero_factura="F-1", fecha_factura="2026-04-05",
            ciclo_inicio="2026-03-01", ciclo_fin="2026-03-31",
            estado="CORRECTO", total_facturado_eur=121.0,
            total_referencia_eur=120.0, diferencia_eur=1.0,
            diferencia_pct=0.8333,
            componentes=[{
                "componente": "Energía", "facturado_eur": 100.0,
                "referencia_eur": 99.0, "diferencia_eur": 1.0,
                "diferencia_pct": 1.0101, "estado": "CORRECTO",
            }],
            snapshot={
                "entrada": {"factura": {"numero": "F-1"}},
                "salida": {"detalle": pd.DataFrame([{"P": "P1", "€": 99.0}])},
            },
            referencias=[{"rol": "condiciones", "condicion_id": None,
                          "payload": {"TE P1": 0.1}}],
            db_path=self.db,
        )

    def test_guarda_y_reconstruye_snapshot_completo(self):
        analisis_id, creada = self._guardar()
        resultado = cargar_analisis(analisis_id, self.db)
        self.assertTrue(creada)
        self.assertEqual(resultado["tipo"], "VERIFICACION")
        self.assertEqual(resultado["snapshot"]["salida"]["detalle"][0]["P"], "P1")
        self.assertEqual(resultado["componentes"][0]["referencia_eur"], 99.0)
        self.assertEqual(resultado["referencias"][0]["referencia"]["payload"]["TE P1"], 0.1)

    def test_mismo_snapshot_no_se_duplica(self):
        primero, creada_primero = self._guardar()
        segundo, creada_segundo = self._guardar()
        self.assertTrue(creada_primero)
        self.assertFalse(creada_segundo)
        self.assertEqual(primero, segundo)


if __name__ == "__main__":
    unittest.main()
