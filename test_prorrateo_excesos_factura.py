import unittest

from backend_factura import (
    FacturaLeida,
    SobrepasamientoPeriodo,
    verificar_excesos_sobrepasamientos,
)


class ProrrateoExcesosFacturaTest(unittest.TestCase):
    def _factura(self, inicio_lectura, fin_lectura):
        return FacturaLeida(
            formato="prueba",
            comercializadora="prueba",
            atr="6.1TD",
            tipo_suministro="Tipo 2",
            periodo_inicio="01/07/2026",
            periodo_fin=fin_lectura,
            excesos_potencia=0.0,
            sobrepasamientos=[
                SobrepasamientoPeriodo(
                    "P1", 210.3, inicio_lectura, fin_lectura
                ),
                SobrepasamientoPeriodo(
                    "P2", 144.1, inicio_lectura, fin_lectura
                ),
            ],
        )

    def test_prorratea_ep_de_un_tramo_parcial_mensual(self):
        factura = self._factura("30/06/2026", "16/07/2026")

        verificar_excesos_sobrepasamientos(factura)

        self.assertEqual(factura.coste_excesos_calculado, 507.72)
        self.assertTrue(all(item.dias == 16 for item in factura.excesos_verificados))
        self.assertTrue(all(
            abs(item.factor_prorrateo - 16 / 31) < 1e-12
            for item in factura.excesos_verificados
        ))

    def test_no_prorratea_un_mes_completo(self):
        factura = self._factura("30/06/2026", "31/07/2026")

        verificar_excesos_sobrepasamientos(factura)

        self.assertEqual(factura.coste_excesos_calculado, 983.72)
        self.assertTrue(all(
            item.factor_prorrateo == 1.0
            for item in factura.excesos_verificados
        ))


if __name__ == "__main__":
    unittest.main()
