import unittest

import pandas as pd

from backend_simulindex import construir_prevision_indexados_2026
from backend_telemindex import calcular_impacto_anual_previsto, evol_diario
from backend_previsiones import construir_curva_telemindex_con_omip_m


class PrevisionEvolTelemindexTest(unittest.TestCase):
    def test_impacto_anual_aplica_consumos_tipo_por_atr(self):
        reales = pd.DataFrame({
            "fecha": pd.to_datetime(["2025-01-01", "2026-01-01"]),
            "precio_2.0": [100.0, 110.0],
            "precio_3.0": [100.0, 110.0],
            "precio_6.1": [100.0, 110.0],
        })
        prevista = pd.DataFrame({
            "fecha": pd.to_datetime(["2026-02-01"]),
            "precio_2.0": [11.0],
            "precio_3.0": [11.0],
            "precio_6.1": [11.0],
        })

        impacto = calcular_impacto_anual_previsto(reales, prevista)

        self.assertEqual(
            impacto["Consumo tipo (kWh)"].tolist(),
            [1_000.0, 100_000.0, 1_000_000.0],
        )
        self.assertAlmostEqual(impacto.iloc[0]["Impacto (€)"], 10.0)
        self.assertAlmostEqual(impacto.iloc[1]["Impacto (€)"], 1_000.0)
        self.assertAlmostEqual(impacto.iloc[2]["Impacto (€)"], 10_000.0)
        self.assertAlmostEqual(impacto.iloc[0]["Impacto (%)"], 10.0)

    def test_curva_telemindex_incluye_media_ultimas_tres_cotizaciones_omip_m(self):
        curva = pd.DataFrame({
            "mes": [9, 10],
            "fecha": pd.to_datetime(["2026-09-01", "2026-10-01"]),
            "precio": [50.0, 70.0],
            "tipo": ["OMIE", "FTB mensual"],
        })
        futuros = pd.DataFrame({
            "Fecha": pd.to_datetime([
                "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09",
                "2026-09-09",
            ]),
            "Entrega_dt": pd.to_datetime([
                "2026-09-01", "2026-09-01", "2026-09-01", "2026-09-01",
                "2026-10-01",
            ]),
            "Precio": [40.0, 50.0, 60.0, 70.0, 99.0],
        })

        curva_telemindex, resumen = construir_curva_telemindex_con_omip_m(
            curva,
            futuros,
            fecha_ref="2026-09-10",
        )

        omip_m = curva_telemindex[
            curva_telemindex["tipo"].eq("FTB mensual M")
        ].iloc[0]
        self.assertEqual(omip_m["fecha"], pd.Timestamp("2026-09-01"))
        self.assertAlmostEqual(omip_m["precio"], 60.0)
        self.assertAlmostEqual(resumen["precio"], 60.0)
        self.assertEqual(resumen["numero_cotizaciones"], 3)

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
