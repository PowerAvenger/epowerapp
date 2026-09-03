import unittest

import pandas as pd

from backend_simulindex import construir_prevision_indexados_2026
from backend_telemindex import evol_diario


class PrevisionEvolTelemindexTest(unittest.TestCase):
    def test_prevision_reutiliza_regresion_lineal_de_simulindex(self):
        historico = pd.DataFrame({
            "spot": [40.0, 50.0, 60.0],
            "precio_2.0": [8.0, 10.0, 12.0],
            "precio_3.0": [9.0, 11.0, 13.0],
            "precio_6.1": [10.0, 12.0, 14.0],
        })
        curva = pd.DataFrame({
            "fecha": pd.to_datetime(["2026-08-01", "2026-09-01", "2026-12-01"]),
            "precio": [55.0, 70.0, 80.0],
            "tipo": ["OMIE", "FTB mensual", "FTB trimestral"],
        })
        prevista = construir_prevision_indexados_2026(
            historico, curva, ajuste_hist=0.5
        )
        self.assertEqual(prevista["fecha"].dt.month.tolist(), [9, 12])
        self.assertAlmostEqual(prevista.iloc[0]["precio_2.0"], 14.5)
        self.assertAlmostEqual(prevista.iloc[1]["precio_6.1"], 18.5)

    def test_real_continua_y_simulacion_punteada_hasta_fin_de_ano(self):
        reales = pd.DataFrame({
            "fecha": pd.to_datetime(["2026-08-30", "2026-08-31"]),
            "año": [2026, 2026],
            "precio_2.0": [100.0, 110.0],
            "precio_3.0": [110.0, 120.0],
            "precio_6.1": [120.0, 130.0],
        })
        prevista = pd.DataFrame({
            "fecha": pd.to_datetime([
                "2026-09-01", "2026-10-01", "2026-11-01", "2026-12-01"
            ]),
            "precio_2.0": [12.0] * 4,
            "precio_3.0": [13.0] * 4,
            "precio_6.1": [14.0] * 4,
        })
        _, figura = evol_diario(reales, df_prevision_2026=prevista)
        reales_2026 = [t for t in figura.data if t.name == "2026"]
        simuladas = [t for t in figura.data if t.name == "2026 simulado"]
        self.assertEqual(len(reales_2026), 3)
        self.assertTrue(all(t.line.dash == "solid" for t in reales_2026))
        self.assertEqual(len(simuladas), 3)
        self.assertTrue(all(t.line.dash == "dot" for t in simuladas))
        self.assertTrue(all(pd.Timestamp(t.x[-1]).month == 12 for t in simuladas))
        self.assertTrue(all(pd.Timestamp(t.x[-1]).day == 31 for t in simuladas))


if __name__ == "__main__":
    unittest.main()
