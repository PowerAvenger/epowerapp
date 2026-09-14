import unittest

import pandas as pd

from formato_es import (
    formatear_columnas_tabla,
    formato_euros_con_signo,
    formato_pct_con_signo,
    formatear_resumen_mixto,
)


class FormatoSignosTest(unittest.TestCase):
    def test_numero_adimensional_usa_coma_y_deja_nulos_en_blanco(self):
        tabla = pd.DataFrame({"P1": [1.2345, None], "P2": [0.0, pd.NA]})

        salida = formatear_columnas_tabla(
            tabla,
            columnas_numero=["P1", "P2"],
            decimales_numero=3,
        )

        self.assertEqual(salida.loc[0, "P1"], "1,234")
        self.assertEqual(salida.loc[0, "P2"], "0,000")
        self.assertEqual(salida.loc[1, "P1"], "")
        self.assertEqual(salida.loc[1, "P2"], "")

    def test_resumen_deja_vacios_los_periodos_no_aplicables(self):
        resumen = pd.DataFrame(
            {
                "P1": [10.0, 2.0, .2],
                "P4": [0.0, 0.0, None],
                "P5": [0.0, 0.0, None],
            },
            index=["Consumo (kWh)", "Coste (€)", "Precio medio (€/kWh)"],
        )

        salida = formatear_resumen_mixto(
            resumen, periodos_afectados=["P1", "P4"]
        )

        self.assertTrue(salida["P5"].eq("").all())
        self.assertNotEqual(salida.loc["Consumo (kWh)", "P1"], "")
        self.assertEqual(salida.loc["Consumo (kWh)", "P4"], "0")

    def test_euros_con_signo_solo_antepone_mas_a_positivos(self):
        self.assertEqual(formato_euros_con_signo(12.345), "+12,35 €")
        self.assertEqual(formato_euros_con_signo(-12.345), "-12,35 €")
        self.assertEqual(formato_euros_con_signo(0), "0,00 €")

    def test_porcentaje_con_signo_y_dos_decimales(self):
        self.assertEqual(formato_pct_con_signo(1.2, 2), "+1,20 %")
        self.assertEqual(formato_pct_con_signo(-1.2, 2), "-1,20 %")
        self.assertEqual(formato_pct_con_signo(0, 2), "0,00 %")


if __name__ == "__main__":
    unittest.main()
