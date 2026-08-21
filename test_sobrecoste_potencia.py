import unittest

from backend_factura import FacturaLeida, PotenciaFacturadaPeriodo


class SobrecostePotenciaTest(unittest.TestCase):
    def test_compensa_periodos_inferiores_y_superiores_a_boe(self):
        factura = FacturaLeida(
            formato="prueba",
            comercializadora="prueba",
            periodo_inicio="01/01/2026",
            potencia_periodos=[
                PotenciaFacturadaPeriodo(
                    periodo="P1",
                    potencia_kw=4.0,
                    dias=31,
                    precio_facturado_eur_kw_dia=0.05,
                    coste_facturado_eur=6.20,
                    precio_boe_eur_kw_dia=0.06,
                    coste_boe_eur=7.44,
                    sobrecoste_eur=-1.24,
                    resultado="Inferior a BOE",
                ),
                PotenciaFacturadaPeriodo(
                    periodo="P2",
                    potencia_kw=4.0,
                    dias=31,
                    precio_facturado_eur_kw_dia=0.04,
                    coste_facturado_eur=4.96,
                    precio_boe_eur_kw_dia=0.035,
                    coste_boe_eur=4.34,
                    sobrecoste_eur=0.62,
                    resultado="Superior a BOE",
                ),
            ],
        )

        self.assertEqual(factura.sobrecoste_potencia, -0.62)
        self.assertAlmostEqual(
            factura.porcentaje_sobrecoste_potencia,
            -0.62 / (6.20 + 4.96) * 100,
        )
        self.assertEqual(factura.sobrecoste_anual_potencia, -7.30)


if __name__ == "__main__":
    unittest.main()
