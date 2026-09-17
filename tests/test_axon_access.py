import tempfile
import unittest
from pathlib import Path

from data_beta.axon_access import listar_suministros_axon
from data_beta.db import connect, initialize_database


class TestListaAxon(unittest.TestCase):
    def test_solo_incluye_suministros_axon_y_su_referencia(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "prueba.sqlite3"
            initialize_database(ruta)
            with connect(ruta) as conexion:
                conexion.executemany(
                    """
                    INSERT INTO suministros(
                        cups20, cups_original, denominacion, atr,
                        proveedor_curva_actual, credencial_curva_ref
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ("ES123456789012345678", "ES123456789012345678",
                         "Edificio", "3.0TD", "AXON", "axon_principal"),
                        ("ES123456789012345679", "ES123456789012345679",
                         "Otro", "2.0TD", "Datadis", None),
                    ),
                )

            self.assertEqual(
                listar_suministros_axon(ruta),
                [{
                    "cups": "ES123456789012345678",
                    "denominacion": "Edificio",
                    "atr": "3.0TD",
                    "credencial_ref": "axon_principal",
                }],
            )

    def test_no_crea_una_base_si_falta(self):
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "ausente.sqlite3"
            self.assertEqual(listar_suministros_axon(ruta), [])
            self.assertFalse(ruta.exists())


if __name__ == "__main__":
    unittest.main()
