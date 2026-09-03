import unittest

import pandas as pd

from backend_fijovspvpc import construir_historico_mensual_pvpc


class HistoricoMensualPvpcTest(unittest.TestCase):
    def test_aplica_el_mismo_corte_al_mes_actual_de_otros_años(self):
        fechas = list(pd.date_range("2025-08-01", "2025-08-31", freq="D"))
        fechas += list(pd.date_range("2026-08-01", "2026-08-10", freq="D"))
        datos = pd.DataFrame({
            "fecha": fechas,
            "pvpc": [100.0] * len(fechas),
            "perfil_20": [1.0] * len(fechas),
        })

        resultado = construir_historico_mensual_pvpc(
            datos,
            consumo_anual=3650,
            potencia_contratada=4,
            precios_potencia_boe={2025: 27.63, 2026: 28.43},
            margen_comercializacion=3.12,
            tipo_iee=0.051127,
            tipo_iva=0.21,
            fecha_referencia="2026-08-10",
        )

        self.assertEqual(resultado["dias_calculados"].tolist(), [10, 10])
        self.assertEqual(
            resultado["precio_ponderado_cent_kwh"].tolist(), [10.0, 10.0]
        )

    def test_separa_boe_y_margen_comercializacion(self):
        datos = pd.DataFrame({
            "fecha": pd.date_range("2026-07-01", "2026-07-31", freq="D"),
            "pvpc": [100.0] * 31,
            "perfil_20": [1.0] * 31,
        })
        resultado = construir_historico_mensual_pvpc(
            datos,
            consumo_anual=3650,
            potencia_contratada=4,
            precios_potencia_boe={2026: 28.43},
            margen_comercializacion=3.12,
            tipo_iee=0.051127,
            tipo_iva=0.21,
            fecha_referencia="2026-08-26",
        ).iloc[0]

        self.assertAlmostEqual(resultado["Potencia BOE"], 28.43 * 4 * 31 / 365)
        self.assertAlmostEqual(
            resultado["Margen comercialización"], 3.12 * 4 * 31 / 365
        )


if __name__ == "__main__":
    unittest.main()
