import unittest

import pandas as pd

from componentes_ofertas_fijas import (
    actualizar_seleccion_ofertas,
    aplicar_seleccion_ofertas,
    campos_pendientes_tarifas,
    construir_ofertas,
    normalizar_excel_ofertas,
    oferta_actual_desde_tarifas,
    periodos_con_consumo,
    preparar_tarifas_extraidas,
)


class OfertasFijasComunesTest(unittest.TestCase):
    def test_conserva_checks_al_recrear_el_selector(self):
        ofertas = pd.DataFrame([
            {"oferta": "Oferta A", "P1": 0.10},
            {"oferta": "Oferta B", "P1": 0.20},
        ])
        primera = aplicar_seleccion_ofertas(ofertas, None)
        primera.loc[primera["oferta"].eq("Oferta B"), "Comparar"] = False
        estado = actualizar_seleccion_ofertas(primera)

        restaurada = aplicar_seleccion_ofertas(ofertas, estado)

        self.assertEqual(restaurada["Comparar"].tolist(), [True, False])

    def test_oferta_nueva_se_selecciona_sin_perder_estado_anterior(self):
        estado = {"Oferta A": False}
        ofertas = pd.DataFrame([
            {"oferta": "Oferta A"},
            {"oferta": "Oferta nueva"},
        ])

        restaurada = aplicar_seleccion_ofertas(ofertas, estado)

        self.assertEqual(restaurada["Comparar"].tolist(), [False, True])

    def test_solo_exige_periodos_con_consumo(self):
        activos, vacios = periodos_con_consumo(
            pd.Series({"P1": 0, "P2": 0, "P3": 10, "P4": 20, "P5": 0, "P6": 30}),
            "6.1TD",
        )
        self.assertEqual(activos, ["P3", "P4", "P6"])
        self.assertEqual(vacios, ["P1", "P2", "P5"])

    def test_20_no_exige_p4_p5_p6(self):
        activos, vacios = periodos_con_consumo(
            pd.Series({
                "P1": 10, "P2": 20, "P3": 30,
                "P4": 40, "P5": 50, "P6": 60,
            }),
            "2.0 TD",
        )

        self.assertEqual(activos, ["P1", "P2", "P3"])
        self.assertEqual(vacios, [])
        salida = construir_ofertas(pd.DataFrame([{
            "oferta": "Oferta 2.0",
            "P1": 0.20,
            "P2": 0.15,
            "P3": 0.10,
            "P4": None,
            "P5": None,
            "P6": None,
        }]), activos)
        self.assertEqual(salida.loc[0, ["P4", "P5", "P6"]].tolist(), [0.0, 0.0, 0.0])

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

    def test_prepara_y_confirma_todos_los_peajes_de_una_oferta(self):
        extraida = pd.DataFrame([
            {
                "oferta": "2.0 TD", "ATR": "3.0",
                "P1": .25, "P2": .17, "P3": .14,
                "P4": None, "P5": None, "P6": None,
            },
            {
                "oferta": "3.0 TD", "ATR": "3.0",
                **{f"P{i}": .10 + i / 100 for i in range(1, 7)},
            },
        ])

        tarifas = preparar_tarifas_extraidas(extraida)
        oferta_20 = oferta_actual_desde_tarifas(
            tarifas, "Oferta semanal", "2.0 TD", ["P1", "P2", "P3"],
            "2026-09-10", "2026-09-17",
        )

        self.assertEqual(tarifas["ATR"].tolist(), ["2.0", "3.0"])
        self.assertEqual(campos_pendientes_tarifas(tarifas), [])
        self.assertEqual(oferta_20.loc[0, "oferta"], "Oferta semanal")
        self.assertEqual(oferta_20.loc[0, "Vigencia desde"], "2026-09-10")
        self.assertEqual(
            oferta_20.loc[0, ["P4", "P5", "P6"]].tolist(),
            [0.0, 0.0, 0.0],
        )


if __name__ == "__main__":
    unittest.main()
