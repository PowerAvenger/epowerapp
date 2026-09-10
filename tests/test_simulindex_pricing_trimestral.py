import unittest

import pandas as pd

from backend_indexado import FormulaIndexada
from backend_simulindex import (
    calcular_cobertura_trimestral_horaria,
    construir_escenarios_pricing_trimestral,
    construir_forward_mensual_trimestre,
)


class PricingTrimestralTest(unittest.TestCase):
    def test_forward_trimestral_prioriza_mensuales_y_completa_con_trimestre(self):
        mensuales = pd.DataFrame({
            "Entrega": ["oct-26", "nov-26"],
            "Entrega_dt": pd.to_datetime(["2026-10-01", "2026-11-01"]),
            "Fecha": pd.to_datetime(["2026-09-08", "2026-09-08"]),
            "Precio": [70.0, 75.0],
        })
        trimestrales = pd.DataFrame({
            "Entrega": ["Q4-26"],
            "Fecha": pd.to_datetime(["2026-09-08"]),
            "Precio": [72.0],
        })

        curva = construir_forward_mensual_trimestre(
            mensuales, trimestrales, "Q4-26"
        )

        self.assertEqual(curva["OMIP (€/MWh)"].tolist(), [70.0, 75.0, 72.0])
        self.assertEqual(
            curva["Origen"].tolist(),
            ["Futuro mensual", "Futuro mensual", "Futuro trimestral"],
        )

    def test_cobertura_sustituye_spot_y_reescala_ssaa_horario(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.to_datetime([
                "2026-04-01 00:00", "2026-04-01 01:00",
                "2026-05-01 00:00", "2026-05-01 01:00",
            ]),
            "periodo": ["P1", "P1", "P2", "P2"],
            "consumo_neto_kWh": [100.0, 100.0, 200.0, 200.0],
            "spot": [40.0, 90.0, 30.0, 80.0],
            "ssaa": [6.0, 11.0, 12.0, 22.0],
            "rad3": [1.0, 1.0, 2.0, 2.0],
            "osom": [0.0, 0.0, 0.0, 0.0],
        })
        for atr in ["2.0", "3.0", "6.1", "6.2"]:
            curva[f"ppcc_{atr}"] = 0.0
            curva[f"perd_{atr}"] = 0.0
            curva[f"pyc_{atr}"] = 0.0

        objetivos_ssaa = pd.DataFrame(
            20.0,
            index=[f"2025-{mes:02d}" for mes in range(1, 13)],
            columns=[f"P{i}" for i in range(1, 7)],
        )
        detalle, resumen = calcular_cobertura_trimestral_horaria(
            curva, 50.0, "3.0", FormulaIndexada(),
            objetivos_ssaa, 2.0, 0.0
        )

        self.assertTrue(detalle["spot"].eq(50.0).all())
        medias_ssaa = (detalle["ssaa"] - 2.0).groupby(
            [detalle["fecha_hora"].dt.month, detalle["periodo"]]
        ).mean()
        self.assertTrue(medias_ssaa.eq(20.0).all())
        self.assertEqual(resumen.loc["Consumo (kWh)", "TOTAL"], 600.0)

    def test_limita_consumos_al_trimestre_y_aplica_forward(self):
        periodos = [f"P{i}" for i in range(1, 7)]
        consumos = pd.DataFrame({
            "fecha_hora": pd.to_datetime(["2026-04-01", "2026-05-01", "2026-06-01"]),
            "periodo": ["P1", "P2", "P3"],
            "consumo_neto_kWh": [100.0, 200.0, 300.0],
        })
        filas_componentes = []
        for mes in range(1, 13):
            for periodo in periodos:
                filas_componentes.append({
                    "mes_pricing": pd.Period(f"2025-{mes:02d}", freq="M"),
                    "dh_6p": periodo,
                    "perd_3.0": 0.0,
                })
        componentes = pd.DataFrame(filas_componentes)
        indice = [f"2025-{mes:02d}" for mes in range(1, 13)]
        apuntamientos = pd.DataFrame(1.0, index=indice, columns=periodos)
        ssaa = pd.DataFrame(0.0, index=indice, columns=periodos)
        tabla_atr = pd.DataFrame(
            0.0, index=["2.0TD", "3.0TD", "6.1TD", "6.2TD"], columns=periodos
        )

        escenarios = construir_escenarios_pricing_trimestral(
            consumos, "Q2-26", [50.0, 60.0, 70.0], "3.0",
            apuntamientos, ssaa, componentes, "dh_6p",
            tabla_atr, tabla_atr, 0.0, 0.0, 0.0,
            FormulaIndexada(),
        )

        self.assertEqual(len(escenarios), 3)
        self.assertEqual(
            escenarios[0]["df_resumen"].loc["Consumo (kWh)", "TOTAL"],
            600.0,
        )
        self.assertLess(
            escenarios[0]["df_resumen"].loc["Coste (€)", "TOTAL"],
            escenarios[2]["df_resumen"].loc["Coste (€)", "TOTAL"],
        )


if __name__ == "__main__":
    unittest.main()
