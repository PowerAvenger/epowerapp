import unittest

import pandas as pd

from componentes_comparativa_index_pvpc import preparar_comparativa_index_pvpc


class ComparativaIndexPvpcTest(unittest.TestCase):
    def test_conserva_medias_aritmeticas_y_perfiladas(self):
        fechas = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-02-01"])
        index = pd.DataFrame({
            "fecha": fechas,
            "hora": [1, 2, 1],
            "precio_2.0": [100.0, 200.0, 300.0],
        })
        pvpc = pd.DataFrame({
            "fecha": fechas,
            "hora": [1, 2, 1],
            "pvpc": [90.0, 180.0, 270.0],
            "perfil_20": [1.0, 2.0, 1.0],
        })

        _, anual, _, anual_perfilado = preparar_comparativa_index_pvpc(
            index, pvpc
        )

        self.assertAlmostEqual(anual.iloc[0]["index_20"], 20.0)
        self.assertAlmostEqual(anual.iloc[0]["pvpc"], 18.0)
        self.assertAlmostEqual(anual_perfilado.iloc[0]["index_20"], 20.0)
        self.assertAlmostEqual(anual_perfilado.iloc[0]["pvpc"], 18.0)

    def test_descarta_fechas_anteriores_a_2024(self):
        index = pd.DataFrame({
            "fecha": pd.to_datetime(["2023-12-31", "2024-01-01"]),
            "hora": [1, 1],
            "precio_2.0": [999.0, 100.0],
        })
        pvpc = pd.DataFrame({
            "fecha": pd.to_datetime(["2023-12-31", "2024-01-01"]),
            "hora": [1, 1],
            "pvpc": [999.0, 90.0],
            "perfil_20": [1.0, 1.0],
        })

        _, anual, _, _ = preparar_comparativa_index_pvpc(index, pvpc)

        self.assertEqual(anual["anio"].tolist(), [2024])
        self.assertAlmostEqual(anual.iloc[0]["index_20"], 10.0)


if __name__ == "__main__":
    unittest.main()
