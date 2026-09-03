import unittest

import pandas as pd

from backend_mibgas import construir_ratios_maximos_horarios_por_mes


class RatiosMaximosMibgasTest(unittest.TestCase):
    def test_calcula_el_maximo_de_cada_hora_y_mes(self):
        datos = pd.DataFrame({
            "mes": [1, 1, 1, 1, 2],
            "hora": [0, 0, 1, 1, 0],
            "rel_omie_gas": [1.2, 1.8, 2.1, 1.9, 1.4],
        })

        resultado = construir_ratios_maximos_horarios_por_mes(datos)

        self.assertEqual(resultado.loc[0, "Mes"], "Enero")
        self.assertEqual(resultado.loc[0, "00:00"], 1.8)
        self.assertEqual(resultado.loc[0, "01:00"], 2.1)
        self.assertEqual(resultado.loc[1, "Mes"], "Febrero")
        self.assertEqual(resultado.loc[1, "00:00"], 1.4)
        self.assertTrue(pd.isna(resultado.loc[1, "01:00"]))


if __name__ == "__main__":
    unittest.main()
