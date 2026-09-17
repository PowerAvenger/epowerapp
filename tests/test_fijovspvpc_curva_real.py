import unittest

import pandas as pd

from backend_fijovspvpc import calcular_energia_fija, obtener_tabla_curva_real


class ComparativaCurvaRealTest(unittest.TestCase):
    def test_cruza_consumos_reales_y_calcula_ambas_ofertas(self):
        horas = pd.to_datetime(["2026-08-01 00:00", "2026-08-01 01:00"])
        pvpc = pd.DataFrame({
            "datetime": horas,
            "fecha": pd.to_datetime(["2026-08-01"] * 2),
            "hora": [1, 2],
            "pvpc": [100.0, 200.0],
            "dh_3p": ["P1", "P2"],
        })
        curva = pd.DataFrame({
            "fecha_hora": horas,
            "consumo_neto_kWh": [1.0, 3.0],
        })

        datos, _, precio_medio, coste_pvpc = obtener_tabla_curva_real(
            pvpc, curva, "2026-08-01", "2026-08-01"
        )

        self.assertEqual(datos["consumo"].tolist(), [1.0, 3.0])
        self.assertAlmostEqual(coste_pvpc, 0.7)
        self.assertAlmostEqual(precio_medio, 0.175)
        coste_fijo, precio_fijo = calcular_energia_fija(datos, 12.0)
        self.assertAlmostEqual(coste_fijo, 0.48)
        self.assertAlmostEqual(precio_fijo, 12.0)
        coste_3p, precio_3p = calcular_energia_fija(
            datos, 12.0, [20.0, 10.0, 5.0]
        )
        self.assertAlmostEqual(coste_3p, 0.5)
        self.assertAlmostEqual(precio_3p, 12.5)

    def test_hora_repetida_no_duplica_el_consumo(self):
        hora = pd.Timestamp("2026-10-25 02:00")
        pvpc = pd.DataFrame({
            "datetime": [hora, hora],
            "fecha": pd.to_datetime(["2026-10-25"] * 2),
            "hora": [3, 3],
            "pvpc": [100.0, 300.0],
            "dh_3p": ["P3", "P3"],
        })
        curva = pd.DataFrame({
            "fecha_hora": [hora], "consumo_neto_kWh": [2.0],
        })

        datos, _, _, coste = obtener_tabla_curva_real(
            pvpc, curva, "2026-10-25", "2026-10-25"
        )

        self.assertAlmostEqual(datos["consumo"].sum(), 2.0)
        self.assertAlmostEqual(coste, 0.4)

    def test_usa_el_periodo_de_la_curva_para_el_precio_fijo(self):
        hora = pd.Timestamp("2026-08-01 00:00")
        pvpc = pd.DataFrame({
            "datetime": [hora], "fecha": [hora.normalize()],
            "hora": [1], "pvpc": [100.0], "dh_3p": ["P1"],
        })
        curva = pd.DataFrame({
            "fecha_hora": [hora], "consumo_neto_kWh": [2.0],
            "periodo": ["3"],
        })

        datos, _, _, _ = obtener_tabla_curva_real(
            pvpc, curva, "2026-08-01", "2026-08-01"
        )
        coste, _ = calcular_energia_fija(datos, 12.0, [20.0, 10.0, 5.0])

        self.assertAlmostEqual(coste, 0.1)

    def test_rechaza_horas_sin_consumo(self):
        horas = pd.to_datetime(["2026-08-01 00:00", "2026-08-01 01:00"])
        pvpc = pd.DataFrame({
            "datetime": horas,
            "fecha": pd.to_datetime(["2026-08-01"] * 2),
            "hora": [1, 2],
            "pvpc": [100.0, 200.0],
        })
        curva = pd.DataFrame({
            "fecha_hora": [horas[0]], "consumo_neto_kWh": [1.0],
        })

        with self.assertRaisesRegex(ValueError, "1 sin consumo"):
            obtener_tabla_curva_real(pvpc, curva, "2026-08-01", "2026-08-01")


if __name__ == "__main__":
    unittest.main()
