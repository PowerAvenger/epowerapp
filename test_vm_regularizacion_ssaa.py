import unittest

from backend_factura import extraer_regularizacion_ssaa_vm


class TestRegularizacionSsaaVm(unittest.TestCase):
    def test_extrae_importe_en_fila_de_ajustes_diversos(self):
        texto = """
Ajustes diversos Regularización servicios ajuste conforme a cláusula 5.2 del contrato para periodo 30,34 €
de 26/02/2026 al 30/06/2026
Actualización FNEE 2026                                         0,61 €
"""

        self.assertEqual(extraer_regularizacion_ssaa_vm(texto), 30.34)

    def test_extrae_importe_despues_del_intervalo_en_texto_lineal(self):
        texto = """
Regularización servicios ajuste conforme a cláusula 5.2 del contrato para periodo
de 26/02/2026 al 30/06/2026                                      30,34 €
"""

        self.assertEqual(extraer_regularizacion_ssaa_vm(texto), 30.34)

    def test_no_confunde_actualizacion_fnee_con_regularizacion_ssaa(self):
        texto = "Actualización FNEE 2026  0,61 €"

        self.assertEqual(extraer_regularizacion_ssaa_vm(texto), 0.0)


if __name__ == "__main__":
    unittest.main()
