import unittest

import pandas as pd

from backend_telemindex import preparar_comparativa_mensual_indexados


class ComparativaMensualIndexadosTest(unittest.TestCase):
    def test_recorta_ambos_anios_al_ultimo_dia_del_anio_comparado(self):
        filas = []
        for anio, ultimo_dia in ((2025, 30), (2026, 7)):
            for dia in range(1, ultimo_dia + 1):
                filas.append(
                    {
                        "fecha": f"{anio}-09-{dia:02d}",
                        "spot": float(dia * 10),
                        "precio_2.0": float(dia * 10),
                        "precio_3.0": float(dia * 10),
                        "precio_6.1": float(dia * 10),
                    }
                )

        resumen, cortes = preparar_comparativa_mensual_indexados(
            pd.DataFrame(filas), 2025, 2026, mes_num=9
        )

        medias = resumen.set_index("año")["spot"].to_dict()
        self.assertEqual(medias[2025], 4.0)
        self.assertEqual(medias[2026], 4.0)
        self.assertEqual(cortes[9], pd.Timestamp("2026-09-07"))


if __name__ == "__main__":
    unittest.main()
