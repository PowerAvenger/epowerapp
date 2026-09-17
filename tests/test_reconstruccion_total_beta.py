import unittest

from backend_verificacion_consumos import reconstruir_total_beta


class TestReconstruccionTotalBeta(unittest.TestCase):
    def test_excesos_forman_parte_de_la_base_iee(self):
        resultado = reconstruir_total_beta(
            total_factura=115_212.91,
            potencia_facturada=8_345.02,
            potencia_verificada=5_037.80,
            energia_facturada=80_251.75,
            energia_verificada=80_251.75,
            otros_facturados={"excesos": 205.91},
            otros_confirmados={"excesos": 31_253.55},
            claves_otros_base_iee=("excesos",),
            iee_facturado=4_631.38,
            iva_facturado=19_995.63,
            base_iee_factura=90_802.68,
            tipo_iee_pct=5.11269632,
            base_iva_factura=95_434.06,
            tipo_iva_pct=21.0,
        )

        self.assertGreater(resultado["iee_verificado"], 4_631.38)
        self.assertAlmostEqual(
            resultado["base_iee_verificada"],
            90_802.68 - 3_307.22 + 31_047.64,
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
