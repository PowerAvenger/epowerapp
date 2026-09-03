import io
import unittest

from backend_sips import (
    leer_sips_completo, obtener_atr_sips, perfil_anual_meses_naturales,
)


class LectorSipsTest(unittest.TestCase):
    def test_normaliza_atr_y_admite_ausencia(self):
        self.assertEqual(obtener_atr_sips({"tarifa_atr": "3.0TD"}), "3.0")
        self.assertEqual(obtener_atr_sips({"tarifa_atr": "6,1 TD"}), "6.1")
        self.assertIsNone(obtener_atr_sips({"tarifa_atr": ""}))

    def test_perfil_anual_elige_el_registro_mas_reciente_de_cada_mes(self):
        import pandas as pd

        tabla = pd.DataFrame({
            "periodo_mes": [f"2024-{mes:02d}" for mes in range(1, 13)]
            + ["2025-01"],
            "año": [2024] * 12 + [2025],
            "mes": list(range(1, 13)) + [1],
            "P1": list(range(1, 13)) + [99],
        })

        perfil = perfil_anual_meses_naturales(tabla)

        self.assertEqual(len(perfil), 12)
        self.assertEqual(perfil.loc[perfil["mes"] == 1, "P1"].iloc[0], 99)

    def test_lee_ficha_activa_reactiva_y_maximetros(self):
        contenido = (
            "cups;distribuidora;tarifa atr\n"
            "ES001;DISTRIBUIDORA;3.0TD\n\n"
            "cups;f. fin;f.inicio;ea1;ea2;ea3;ea4;ea5;ea6;"
            "er1;er2;er3;er4;er5;er6;pt1;pt2;pt3;pt4;pt5;pt6\n"
            "ES001;2025-01-31;2024-12-31;1.000,5;2;3;4;5;6;"
            "10;20;30;40;50;60;100;200;300;400;500;600\n"
        )
        archivo = io.BytesIO(contenido.encode("utf-8"))

        resultado = leer_sips_completo(archivo)

        self.assertEqual(resultado["metadatos"]["cups"], "ES001")
        self.assertEqual(resultado["metadatos"]["tarifa_atr"], "3.0TD")
        self.assertEqual(resultado["atr"], "3.0")
        self.assertEqual(resultado["consumos"].loc[0, "P1"], 1000.5)
        self.assertEqual(resultado["reactiva"].loc[0, "P6"], 60)
        self.assertEqual(resultado["maximetros"].loc[0, "P4"], 400)
        self.assertEqual(resultado["consumos"].loc[0, "periodo_mes"], "2025-01")

    def test_suma_energias_y_toma_maximo_si_hay_dos_tramos_en_un_mes(self):
        cabecera = (
            "cups;f. fin;f.inicio;ea1;ea2;ea3;ea4;ea5;ea6;"
            "er1;er2;er3;er4;er5;er6;pt1;pt2;pt3;pt4;pt5;pt6"
        )
        fila_1 = "ES001;2025-01-15;2024-12-31;1;0;0;0;0;0;2;0;0;0;0;0;10;0;0;0;0;0"
        fila_2 = "ES001;2025-01-31;2025-01-15;3;0;0;0;0;0;4;0;0;0;0;0;20;0;0;0;0;0"
        archivo = io.BytesIO(
            ("cups;distribuidora\nES001;D\n\n" + cabecera + "\n"
             + fila_1 + "\n" + fila_2 + "\n").encode("utf-8")
        )

        resultado = leer_sips_completo(archivo)

        self.assertEqual(resultado["consumos"].loc[0, "P1"], 4)
        self.assertEqual(resultado["reactiva"].loc[0, "P1"], 6)
        self.assertEqual(resultado["maximetros"].loc[0, "P1"], 20)


if __name__ == "__main__":
    unittest.main()
