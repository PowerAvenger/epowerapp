import tempfile
import unittest
from pathlib import Path

from backend_contractual import cargar_acceso_medida_cups
from data_beta.db import connect, initialize_database


class TestAccesoMedidaContractual(unittest.TestCase):
    def test_asocia_axon_principal_a_suministro_axon(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "prueba.sqlite3"
            initialize_database(ruta)
            with connect(ruta) as conexion:
                conexion.execute(
                    """
                    INSERT INTO suministros(
                        cups20, cups_original, proveedor_curva_actual
                    ) VALUES (?, ?, ?)
                    """,
                    ("ES123456789012345678", "ES123456789012345678", "AXON"),
                )
                conexion.execute(
                    """
                    UPDATE suministros SET credencial_curva_ref = 'axon_principal'
                    WHERE cups20 = 'ES123456789012345678'
                    """
                )

            acceso = cargar_acceso_medida_cups(
                "ES123456789012345678XX", db_path=ruta
            )

            self.assertEqual(acceso["proveedor"], "AXON")
            self.assertEqual(acceso["credencial_ref"], "axon_principal")

    def test_cups_ausente_no_tiene_acceso(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "prueba.sqlite3"
            initialize_database(ruta)
            self.assertEqual(
                cargar_acceso_medida_cups("ES123456789012345678", ruta), {}
            )
