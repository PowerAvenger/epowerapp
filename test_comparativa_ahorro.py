import unittest

import pandas as pd

from backend_curvadecarga import calcular_comparativa_ahorro


class TestComparativaAhorro(unittest.TestCase):
    def test_compara_mismo_consumo_y_rango(self):
        fechas = pd.to_datetime(["2026-01-01 00:00", "2026-02-01 00:00"])
        actual = pd.DataFrame({
            "fecha_hora": fechas,
            "consumo_neto_kWh": [100.0, 200.0],
            "coste_total": [12.0, 24.0],
        })
        referencia = pd.DataFrame({
            "fecha_hora": fechas,
            "consumo_neto_kWh": [100.0, 200.0],
            "coste_total": [10.0, 20.0],
        })

        resultado = calcular_comparativa_ahorro(actual, referencia)

        self.assertTrue(resultado["ok"])
        self.assertAlmostEqual(resultado["coste_referencia"], 30.0)
        self.assertAlmostEqual(resultado["coste_real"], 36.0)
        self.assertAlmostEqual(resultado["diferencia"], 6.0)
        self.assertAlmostEqual(resultado["diferencia_pct"], 20.0)
        self.assertIsNotNone(resultado["fig_acumulado"])
        cascada = resultado["fig_acumulado"].data[0]
        self.assertEqual(list(cascada.measure), ["relative", "relative", "total"])
        self.assertEqual(list(cascada.y), [-2.0, -4.0, -6.0])
        perfil = resultado["fig_perfil_costes"]
        self.assertEqual(
            [traza.name for traza in perfil.data],
            ["Consumo medio", "Coste referencia", "Coste real contractual"],
        )
        perfil_precios = resultado["fig_perfil_precios"]
        self.assertEqual(
            [traza.name for traza in perfil_precios.data],
            [
                "Diferencial fijo − indexado",
            ],
        )

    def test_rechaza_consumos_distintos(self):
        actual = pd.DataFrame({
            "fecha_hora": pd.to_datetime(["2026-01-01"]),
            "consumo_neto_kWh": [101.0], "coste_total": [12.0],
        })
        referencia = pd.DataFrame({
            "fecha_hora": pd.to_datetime(["2026-01-01"]),
            "consumo_neto_kWh": [100.0], "coste_total": [10.0],
        })
        self.assertFalse(calcular_comparativa_ahorro(actual, referencia)["ok"])


if __name__ == "__main__":
    unittest.main()
