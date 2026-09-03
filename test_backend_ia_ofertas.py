import unittest

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

    def test_rechaza_periodos_obligatorios_ausentes(self):
        with self.assertRaisesRegex(ValueError, "P6"):
            validar_oferta_extraida(
                oferta_30("EUR/kWh", [0.2, 0.2, 0.2, 0.2, 0.2, None])
            )


if __name__ == "__main__":
    unittest.main()
