import unittest

from backend_factura import (
    extraer_ep_naturgy_gc,
    extraer_excesos_potencia_naturgy_gc,
    extraer_reactiva_facturada_naturgy_gc,
    extraer_regularizaciones_ssaa_naturgy_gc,
)


class NaturgyReactivaTest(unittest.TestCase):
    def test_ep_dobles_conservan_fechas_y_no_se_agregan(self):
        texto = """
EP P1 30.06.2026 0 kW 06.07.2026 393 kW R 1,00000 393,0 kW 0,0 kW
EP P2 30.06.2026 0 kW 06.07.2026 508 kW R 1,00000 508,0 kW 0,0 kW
EP P1 06.07.2026 0 kW 31.07.2026 84 kW R 1,00000 84,0 kW 0,0 kW
EP P2 06.07.2026 0 kW 31.07.2026 57 kW R 1,00000 57,0 kW 0,0 kW
"""

        resultado = extraer_ep_naturgy_gc(texto)

        self.assertEqual(
            [(x.periodo, x.periodo_inicio, x.periodo_fin, x.exceso_kw)
             for x in resultado],
            [
                ("P1", "30/06/2026", "06/07/2026", 393.0),
                ("P2", "30/06/2026", "06/07/2026", 508.0),
                ("P1", "06/07/2026", "31/07/2026", 84.0),
                ("P2", "06/07/2026", "31/07/2026", 57.0),
            ],
        )

    def test_excesos_de_potencia_con_importes_en_linea_separada(self):
        texto = """
EXCESOS DE POTENCIA ACCESO 01.07.2026 -
983,72 Eur
15.07.2026
"""

        self.assertEqual(
            extraer_excesos_potencia_naturgy_gc(texto),
            983.72,
        )

    def test_excesos_de_potencia_en_linea_unica(self):
        self.assertEqual(
            extraer_excesos_potencia_naturgy_gc(
                "EXCESOS DE POTENCIA ACCESO 983,72 Eur"
            ),
            983.72,
        )

    def test_suma_excesos_de_varios_tramos_de_condiciones(self):
        texto = """
EXCESOS DE POTENCIA ACCESO 01.07.2026 -
439,82 Eur
06.07.2026
EXCESOS DE POTENCIA ACCESO 07.07.2026 -
373,65 Eur
31.07.2026
"""

        self.assertEqual(
            extraer_excesos_potencia_naturgy_gc(texto),
            813.47,
        )

    def test_regularizaciones_ssaa_conservan_todos_los_periodos(self):
        texto = """
REGULARIZACIÓN DE SERVICIOS DE AJUSTE
01.04.2026 - 30.04.2026 642.702 kWh 0,00863329 5.548,63 Eur
REGULARIZACIÓN DE SERVICIOS DE AJUSTE
01.05.2026 - 31.05.2026 677.076 kWh 0,00772730 5.231,97 Eur
REGULARIZACIÓN DE SERVICIOS DE AJUSTE
01.06.2026 - 30.06.2026 744.668 kWh 0,00346285 2.578,67 Eur
"""

        resultado = extraer_regularizaciones_ssaa_naturgy_gc(texto)

        self.assertEqual(len(resultado), 3)
        self.assertEqual(
            [item.importe for item in resultado],
            [5548.63, 5231.97, 2578.67],
        )
        self.assertIn("01.04.2026 - 30.04.2026", resultado[0].concepto)

    def test_formato_compacto_sin_fechas(self):
        texto = """
REACTIVA ACCESO P1 1.329 kVArh 0,041554 55,23 Eur
REACTIVA ACCESO P2 1.096 kVArh 0,041554 45,54 Eur
"""

        resultado = extraer_reactiva_facturada_naturgy_gc(texto)

        self.assertEqual(resultado["P1"]["exceso"], 1329.0)
        self.assertEqual(resultado["P2"]["exceso"], 1096.0)
        self.assertEqual(resultado["P1"]["precio"], 0.041554)
        self.assertEqual(resultado["P1"]["coste"], 55.23)
        self.assertEqual(resultado["P2"]["coste"], 45.54)

    def test_formato_historico_con_fechas(self):
        texto = (
            "REACTIVA ACCESO P1 01.06.2026 - 30.06.2026 "
            "100 kVArh 0,041554 4,16 Eur"
        )

        resultado = extraer_reactiva_facturada_naturgy_gc(texto)

        self.assertEqual(resultado["P1"]["exceso"], 100.0)
        self.assertEqual(resultado["P1"]["coste"], 4.16)


if __name__ == "__main__":
    unittest.main()
