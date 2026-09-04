import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from backend_indexado import (
    FormulaIndexada,
    calcular_precios_atr_formula,
    construir_desglose_precio_indexado,
    construir_desglose_ssaa_c2,
)


def calculo_historico(df, formula):
    """Copia de control de la lógica previa a la extracción del motor."""
    tm_rate = 0.015
    cf = formula.cf_pct / 100
    margen = formula.margen
    df = df.copy()
    for atr in ["2.0", "3.0", "6.1"]:
        base = df["spot"] + df["ssaa"] + df[f"ppcc_{atr}"] + df["osom"]
        base += 0.0
        base += formula.desvios_apant
        if formula.incluir_fnee and formula.fnee_pos == "perdidas":
            base += df["fnee"]
        base_coste = base.copy()
        base_precio = base.copy()
        if formula.margen_pos == "perdidas":
            df[f"margen_{atr}"] = (
                margen * (1 + df[f"perd_{atr}"]) * (1 + tm_rate) * (1 + cf)
            )
            base_precio += margen
        base_coste *= 1 + df[f"perd_{atr}"]
        base_precio *= 1 + df[f"perd_{atr}"]
        if formula.margen_pos == "tm":
            df[f"margen_{atr}"] = margen * (1 + tm_rate) * (1 + cf)
            base_precio += margen
        if formula.incluir_fnee and formula.fnee_pos == "tm":
            base_coste += df["fnee"]
            base_precio += df["fnee"]
        base_coste *= 1 + tm_rate
        base_precio *= 1 + tm_rate
        base_coste *= 1 + cf
        base_precio *= 1 + cf
        if formula.incluir_fnee and formula.fnee_pos == "neto":
            base_coste += df["fnee"]
            base_precio += df["fnee"]
        if formula.margen_pos == "neto":
            df[f"margen_{atr}"] = margen
            base_precio += margen
        df[f"coste_{atr}"] = base_coste
        df[f"precio_{atr}"] = base_precio + df[f"pyc_{atr}"]
    return df


class MotorIndexadoTest(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "spot": [40.0, 80.0],
            "ssaa": [12.0, 18.0],
            "osom": [0.5, 0.7],
            "fnee": [2.1, 2.2],
            "ppcc_2.0": [3.0, 4.0],
            "ppcc_3.0": [4.0, 5.0],
            "ppcc_6.1": [5.0, 6.0],
            "perd_2.0": [0.16, 0.17],
            "perd_3.0": [0.10, 0.11],
            "perd_6.1": [0.07, 0.08],
            "pyc_2.0": [20.0, 10.0],
            "pyc_3.0": [15.0, 8.0],
            "pyc_6.1": [10.0, 6.0],
            "dh_3p": ["P1", "P2"],
            "dh_6p": ["P3", "P4"],
            "consumo_neto_kWh": [100.0, 300.0],
        })

    def test_equivalencia_exacta_con_todas_las_posiciones(self):
        for margen_pos in ("perdidas", "tm", "neto"):
            for incluir_fnee in (False, True):
                for fnee_pos in ("perdidas", "tm", "neto"):
                    formula = FormulaIndexada(
                        desvios_apant=1.3,
                        margen=5.7,
                        margen_pos=margen_pos,
                        incluir_fnee=incluir_fnee,
                        fnee_pos=fnee_pos,
                        cf_pct=1.25,
                    )
                    with self.subTest(
                        margen_pos=margen_pos,
                        incluir_fnee=incluir_fnee,
                        fnee_pos=fnee_pos,
                    ):
                        assert_frame_equal(
                            calcular_precios_atr_formula(self.df, formula),
                            calculo_historico(self.df, formula),
                            check_exact=True,
                        )

    def test_rechaza_componentes_incompletos(self):
        with self.assertRaisesRegex(ValueError, "ppcc_6.1"):
            calcular_precios_atr_formula(
                self.df.drop(columns="ppcc_6.1"), FormulaIndexada()
            )

    def test_rechaza_componentes_no_numericos(self):
        df = self.df.copy()
        df.loc[0, "spot"] = "sin dato"
        with self.assertRaisesRegex(ValueError, "spot"):
            calcular_precios_atr_formula(df, FormulaIndexada())

    def test_desglose_concilia_precio_final_en_todas_las_posiciones(self):
        for margen_pos in ("perdidas", "tm", "neto"):
            for fnee_pos in ("perdidas", "tm", "neto"):
                formula = FormulaIndexada(
                    desvios_apant=1.3,
                    margen=5.7,
                    margen_pos=margen_pos,
                    incluir_fnee=True,
                    fnee_pos=fnee_pos,
                    cf_pct=1.25,
                )
                tabla = construir_desglose_precio_indexado(
                    self.df, "2.0", formula, "consumo_neto_kWh"
                ).set_index("Componente")
                aportaciones = tabla.drop(index="Precio final").sum(axis=0)
                pd.testing.assert_series_equal(
                    aportaciones,
                    tabla.loc["Precio final"],
                    check_names=False,
                    rtol=1e-12,
                    atol=1e-12,
                )

    def test_desglose_usa_media_ponderada_total_y_periodos(self):
        tabla = construir_desglose_precio_indexado(
            self.df, "2.0", FormulaIndexada(), "consumo_neto_kWh"
        ).set_index("Componente")
        self.assertAlmostEqual(tabla.loc["OMIE", "Total"], 70.0)
        self.assertAlmostEqual(tabla.loc["OMIE", "P1"], 40.0)
        self.assertAlmostEqual(tabla.loc["OMIE", "P2"], 80.0)

    def test_desglose_ssaa_c2_reconstruye_componentes(self):
        df = self.df.assign(
            balx=[1.0, 3.0], dsv=[2.0, 6.0], ssaa=[3.0, 9.0]
        )
        tabla = construir_desglose_ssaa_c2(
            df, ["balx", "dsv"], "2.0", "consumo_neto_kWh"
        ).set_index("Componente SSAA")
        self.assertAlmostEqual(tabla.loc["BALX", "Total"], 2.5)
        self.assertAlmostEqual(tabla.loc["DSV", "Total"], 5.0)
        self.assertAlmostEqual(tabla.loc["SSAA C2 RECONSTRUIDO", "Total"], 7.5)
        self.assertAlmostEqual(tabla.loc["SSAA GLOBAL USADO", "Total"], 7.5)
        self.assertAlmostEqual(tabla.loc["DIFERENCIA VS GLOBAL", "Total"], 0.0)

if __name__ == "__main__":
    unittest.main()
