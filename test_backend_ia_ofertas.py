import unittest

import pandas as pd

from backend_ia_ofertas import validar_oferta_extraida


def oferta_30(unidad, valores):
    return {
        "nombre": "Oferta de prueba",
        "unidad_original": unidad,
        "tarifas": [{
            "atr": "3.0 TD",
            **{f"P{i}": valor for i, valor in enumerate(valores, start=1)},
        }],
    }


class OfertasImagenTest(unittest.TestCase):
    def test_infiere_eur_kwh_si_la_captura_omite_unidad(self):
        valores = [0.236937, 0.189129, 0.143711, 0.118314, 0.099016, 0.130487]

        tabla, nombre = validar_oferta_extraida(
            oferta_30("no indicada", valores)
        )

        self.assertEqual(nombre, "Oferta de prueba")
        self.assertEqual(tabla.loc[0, "ATR"], "3.0")
        self.assertAlmostEqual(tabla.loc[0, "P1"], 0.236937)
        self.assertTrue(tabla.attrs["unidad_inferida"])

    def test_convierte_eur_mwh_a_eur_kwh(self):
        tabla, _ = validar_oferta_extraida(
            oferta_30("EUR/MWh", [236.937, 189.129, 143.711, 118.314, 99.016, 130.487])
        )

        self.assertAlmostEqual(tabla.loc[0, "P1"], 0.236937)
        self.assertFalse(tabla.attrs["unidad_inferida"])

    def test_deja_vacio_un_periodo_dudoso_para_corregirlo(self):
        tabla, _ = validar_oferta_extraida(
            oferta_30("EUR/kWh", [0.2, 0.2, 0.2, 0.2, 0.2, None])
        )

        self.assertTrue(pd.isna(tabla.loc[0, "P6"]))
        self.assertEqual(tabla.attrs["campos_revisar"], [{
            "atr": "3.0",
            "periodo": "P6",
            "valor_extraido": None,
        }])

    def test_acepta_coma_decimal_y_descarta_una_escala_imposible(self):
        tabla, _ = validar_oferta_extraida(
            oferta_30(
                "EUR/kWh",
                ["0,253962", 0.216140, 0.152730, 130714, 0.122770, 0.148385],
            )
        )

        self.assertAlmostEqual(tabla.loc[0, "P1"], 0.253962)
        self.assertTrue(pd.isna(tabla.loc[0, "P4"]))
        self.assertEqual(tabla.attrs["campos_revisar"][0]["periodo"], "P4")

    def test_usa_atr_del_contexto_si_no_aparece_en_la_imagen(self):
        resultado = {
            "nombre": None,
            "unidad_original": "no indicada",
            "tarifas": [{
                "atr": "",
                **{f"P{i}": valor for i, valor in enumerate(
                    [0.176839, 0.148796, 0.122222, 0.107121, 0.088909, 0.095518],
                    start=1,
                )},
            }],
        }
        tabla, _ = validar_oferta_extraida(resultado, atr_contexto="6.2TD")
        self.assertEqual(tabla.loc[0, "ATR"], "6.2")
        self.assertAlmostEqual(tabla.loc[0, "P1"], 0.176839)

    def test_recupera_cada_atr_desde_el_nombre_antes_de_usar_el_contexto(self):
        resultado = {
            "nombre": "Tabla de precios",
            "unidad_original": "no indicada",
            "tarifas": [
                {
                    "nombre": "2.0 TD", "atr": "",
                    "P1": 0.273046, "P2": 0.187682, "P3": 0.157153,
                    "P4": None, "P5": None, "P6": None,
                },
                {
                    "nombre": "3.0 TD", "atr": "",
                    "P1": 0.253962, "P2": 0.216140, "P3": 0.152730,
                    "P4": 0.130714, "P5": 0.122770, "P6": 0.148385,
                },
                {
                    "nombre": "6.1 TD", "atr": "",
                    **{f"P{i}": 0.1 for i in range(1, 7)},
                },
                {
                    "nombre": "6.2 TD", "atr": "",
                    **{f"P{i}": 0.1 for i in range(1, 7)},
                },
            ],
        }

        tabla, _ = validar_oferta_extraida(resultado, atr_contexto="3.0TD")

        self.assertEqual(
            tabla["ATR"].tolist(), ["2.0", "3.0", "6.1", "6.2"]
        )
        self.assertEqual(tabla.attrs["campos_revisar"], [])

    def test_nombre_20_prevalece_sobre_atr_incorrecto_de_la_ia(self):
        resultado = {
            "nombre": "Tabla de precios",
            "unidad_original": "EUR/kWh",
            "tarifas": [{
                "nombre": "2.0 TD",
                "atr": "3.0 TD",
                "P1": 0.273046,
                "P2": 0.187682,
                "P3": 0.157153,
                "P4": None,
                "P5": None,
                "P6": None,
            }],
        }

        tabla, _ = validar_oferta_extraida(resultado, atr_contexto="3.0TD")

        self.assertEqual(tabla.loc[0, "ATR"], "2.0")
        self.assertEqual(tabla.attrs["campos_revisar"], [])

    def test_conserva_varias_ofertas_del_mismo_atr(self):
        resultado = {
            "nombre": "Tabla de precios",
            "unidad_original": "EUR/kWh",
            "tarifas": [
                {
                    "nombre": "Oferta A", "atr": "",
                    **{f"P{i}": 0.1 for i in range(1, 7)},
                },
                {
                    "nombre": "Oferta B", "atr": "",
                    **{f"P{i}": 0.2 for i in range(1, 7)},
                },
            ],
        }
        tabla, _ = validar_oferta_extraida(resultado, atr_contexto="6.2TD")
        self.assertEqual(tabla["oferta"].tolist(), ["Oferta A", "Oferta B"])
        self.assertEqual(tabla["ATR"].tolist(), ["6.2", "6.2"])


if __name__ == "__main__":
    unittest.main()
