import unittest

import pandas as pd

from componentes_ofertas_fijas import (
    construir_ofertas,
    normalizar_excel_ofertas,
    periodos_con_consumo,
)


class OfertasFijasComunesTest(unittest.TestCase):
    def test_solo_exige_periodos_con_consumo(self):
        activos, vacios = periodos_con_consumo(
            pd.Series({"P1": 0, "P2": 0, "P3": 10, "P4": 20, "P5": 0, "P6": 30}),
            "6.1TD",
        )
        self.assertEqual(activos, ["P3", "P4", "P6"])
        self.assertEqual(vacios, ["P1", "P2", "P5"])

    def test_normaliza_primera_columna_como_oferta(self):
        tabla = pd.DataFrame([["A", 1, 2, 3, 4, 5, 6]], columns=["Nombre", "P1", "P2", "P3", "P4", "P5", "P6"])
        salida = normalizar_excel_ofertas(tabla)
        self.assertEqual(salida.loc[0, "oferta"], "A")

    def test_construye_todas_las_ofertas_editadas(self):
        filas = pd.DataFrame([
            {"oferta": "A", "P1": 0.11, "P2": 0.12},
            {"oferta": "B", "P1": 0.21, "P2": 0.22},
        ])
        salida = construir_ofertas(filas, ["P1", "P2"])
        self.assertEqual(salida["oferta"].tolist(), ["A", "B"])
        self.assertEqual(salida["P1"].tolist(), [0.11, 0.21])


if __name__ == "__main__":
    unittest.main()
