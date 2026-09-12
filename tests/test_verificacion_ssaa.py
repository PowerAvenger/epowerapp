import unittest

import pandas as pd

from backend_telemindex import calcular_verificacion_ssaa


class TestVerificacionSsaa(unittest.TestCase):
    def test_incluye_mes_parcial_como_estimacion_sin_extrapolar(self):
        curva = pd.DataFrame({
            "fecha": ["2026-03-01", "2026-03-02"],
            "ssaa": [18.0, 20.0],
            "consumo_neto_kWh": [1000.0, 2000.0],
            "perd_2.0": [0.10, 0.20],
        })

        resultado, excluidos = calcular_verificacion_ssaa(
            curva,
            referencia_inferior=13.0,
            referencia_superior=16.0,
            perdidas_pct=0.0,
            apuntamiento=1.0,
            hacienda_local=1.0,
            columna_perdidas_horarias="perd_2.0",
        )

        self.assertEqual(excluidos, [])
        self.assertEqual(resultado.loc[0, "Periodo"], "2026-03")
        self.assertEqual(resultado.loc[0, "Estado"], "Parcial (estimación)")
        self.assertEqual(resultado.loc[0, "Cobertura"], "2/31 días")
        self.assertEqual(resultado.loc[0, "Consumo (MWh)"], 3.0)
        self.assertEqual(resultado.loc[0, "Regularización media mensual (€)"], 9.0)

    def test_excluye_periodo_si_hay_datos_necesarios_nulos(self):
        curva = pd.DataFrame({
            "fecha": ["2026-03-01"],
            "ssaa": [None],
            "consumo_neto_kWh": [1000.0],
        })

        resultado, excluidos = calcular_verificacion_ssaa(curva)

        self.assertTrue(resultado.empty)
        self.assertEqual(excluidos, ["2026-03"])


if __name__ == "__main__":
    unittest.main()
