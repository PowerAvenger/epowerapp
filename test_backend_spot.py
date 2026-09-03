import unittest

import pandas as pd

from backend_spot import media_spot, resumir_spot


class TestBackendSpot(unittest.TestCase):
    def test_no_promedia_diarios_redondeados(self):
        datos = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    ["2026-08-01 00:00", "2026-08-01 00:15",
                     "2026-08-02 00:00", "2026-08-02 00:15"]
                ),
                "value": [118.241, 118.241, 118.249, 118.249],
            }
        )
        resumen = resumir_spot(datos)
        self.assertAlmostEqual(media_spot(datos), 118.245)
        self.assertAlmostEqual(resumen["mensual"].iloc[0]["value"], 118.245)
        self.assertAlmostEqual(
            resumen["diario"].iloc[-1]["media_acumulada"], 118.245
        )

    def test_media_pondera_el_numero_real_de_periodos(self):
        datos = pd.DataFrame(
            {
                "fecha": ["2026-10-24", "2026-10-25", "2026-10-25"],
                "spot": [0.0, 100.0, 100.0],
            }
        )
        resumen = resumir_spot(datos, columna_valor="spot")
        self.assertAlmostEqual(resumen["mensual"].iloc[0]["value"], 200 / 3)
        self.assertAlmostEqual(
            resumen["diario"].iloc[-1]["media_acumulada"], 200 / 3
        )


if __name__ == "__main__":
    unittest.main()
