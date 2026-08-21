import io
import unittest
from unittest.mock import patch

import pandas as pd

from backend_curvadecarga import (
    DatadisLimiteConsultas,
    agrupar_curva_horaria,
    analizar_cobertura_periodo,
    clave_cache_consumo_datadis,
    dataframe_como_archivo_curva,
    normalize_curve_simple,
    obtener_consumo_datadis,
    obtener_consumo_datadis_cacheado,
    rango_meses_datadis,
    recortar_curva_periodo,
    resumir_consumo_por_periodo,
)


class CurvasComunesTest(unittest.TestCase):
    def test_rango_datadis_amplia_el_ciclo_a_meses_completos(self):
        inicio, fin = rango_meses_datadis("17/05/2026", "16/06/2026")
        self.assertEqual(inicio, pd.Timestamp("2026-05-01"))
        self.assertEqual(fin, pd.Timestamp("2026-06-30"))

    def test_clave_datadis_no_incluye_password(self):
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "5",
        }
        clave = clave_cache_consumo_datadis(
            "usuario", "123A", suministro,
            "17/05/2026", "16/06/2026", True,
        )
        self.assertEqual(clave[2:6], ("ES123", "2", "2026/05", "2026/06"))

    @patch("backend_curvadecarga.obtener_consumo_datadis")
    def test_descarga_datadis_se_reutiliza_desde_cache(self, descargar):
        curva = pd.DataFrame({
            "Fecha": ["01/05/2026"],
            "Hora": ["00:00"],
            "Consumo (kWh)": [1.25],
        })
        descargar.return_value = (curva, "H", None)
        cache = {}
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "5",
        }

        primero = obtener_consumo_datadis_cacheado(
            cache, "usuario", "secreto", suministro,
            "17/05/2026", "16/06/2026",
        )
        segundo = obtener_consumo_datadis_cacheado(
            cache, "usuario", "otro-secreto", suministro,
            "17/05/2026", "16/06/2026",
        )

        self.assertFalse(primero[4])
        self.assertTrue(segundo[4])
        self.assertEqual(descargar.call_count, 1)
        self.assertIsNot(primero[0], segundo[0])

    def test_normaliza_csv_y_recorta_el_periodo_facturado(self):
        contenido = (
            "Fecha;Hora;Consumo (kWh);Periodo\n"
            "31/05/2026;23:00;1,0;P3\n"
            "01/06/2026;00:00;2,0;P3\n"
            "01/06/2026;01:00;3,0;P3\n"
            "02/06/2026;00:00;4,0;P3\n"
        ).encode("utf-8")
        archivo = io.BytesIO(contenido)
        archivo.name = "curva.csv"

        _, normalizada, _, _, _, frecuencia = normalize_curve_simple(archivo)
        recortada = recortar_curva_periodo(
            normalizada, "01/06/2026", "01/06/2026"
        )

        self.assertEqual(frecuencia, "H")
        self.assertEqual(len(recortada), 2)
        self.assertEqual(resumir_consumo_por_periodo(recortada), {"P3": 5.0})

    def test_agrupa_cuartos_horarios(self):
        fechas = pd.date_range("2026-06-01", periods=4, freq="15min")
        curva = pd.DataFrame({
            "fecha_hora": fechas,
            "fecha": fechas.date,
            "hora": fechas.hour,
            "consumo_neto_kWh": [0.25] * 4,
            "reactiva_kVArh": [0.0] * 4,
            "vertido_neto_kWh": [0.0] * 4,
            "generacion_kWh": [0.0] * 4,
            "periodo": ["P3"] * 4,
            "tipo_dia": ["L-V"] * 4,
        })
        horaria = agrupar_curva_horaria(curva, "QH")
        self.assertEqual(len(horaria), 1)
        self.assertEqual(horaria.loc[0, "consumo_neto_kWh"], 1.0)

    def test_detecta_huecos_en_el_periodo_facturado(self):
        fechas = pd.date_range("2026-06-01", periods=24, freq="1h").delete(5)
        curva = pd.DataFrame({"fecha_hora": fechas})
        cobertura = analizar_cobertura_periodo(
            curva, "01/06/2026", "01/06/2026", "H"
        )
        self.assertFalse(cobertura["completa"])
        self.assertEqual(cobertura["intervalos_ausentes"], 1)
        self.assertEqual(cobertura["intervalos_esperados"], 24)

    def test_convierte_dataframe_en_archivo_reutilizable(self):
        archivo = dataframe_como_archivo_curva(
            pd.DataFrame({"a": [1]}), "datadis_h.csv"
        )
        self.assertEqual(archivo.name, "datadis_h.csv")
        self.assertIn(b"a", archivo.getvalue())

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch(
        "backend_curvadecarga._descargar_consumo_datadis",
        side_effect=DatadisLimiteConsultas("HTTP 429"),
    )
    def test_un_429_se_reintenta_tres_veces_sin_fallback_h(
        self, descargar, _autenticar
    ):
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }
        with self.assertRaises(DatadisLimiteConsultas):
            obtener_consumo_datadis(
                "usuario", "secreto", suministro,
                "01/07/2026", "31/08/2026",
                preferir_qh=True,
                session=object(),
            )
        self.assertEqual(descargar.call_count, 3)
        self.assertEqual(
            pd.Timestamp(descargar.call_args_list[1].args[3]),
            pd.Timestamp("2026-06-01"),
        )
        self.assertEqual(
            pd.Timestamp(descargar.call_args_list[2].args[3]),
            pd.Timestamp("2026-05-01"),
        )

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch("backend_curvadecarga._descargar_consumo_datadis")
    def test_datadis_puede_recuperarse_de_un_429(
        self, descargar, _autenticar
    ):
        descargar.side_effect = [
            DatadisLimiteConsultas("HTTP 429"),
            pd.DataFrame({
                "date": ["2026/07/01"],
                "time": ["00:00"],
                "consumptionKWh": [1.0],
            }),
        ]
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }

        curva, frecuencia, _ = obtener_consumo_datadis(
            "usuario", "secreto", suministro,
            "01/07/2026", "31/07/2026",
            session=object(),
        )

        self.assertEqual(descargar.call_count, 2)
        self.assertEqual(
            pd.Timestamp(descargar.call_args_list[1].args[3]),
            pd.Timestamp("2026-06-01"),
        )
        self.assertEqual(frecuencia, "H")
        self.assertEqual(len(curva), 1)

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch("backend_curvadecarga._descargar_consumo_datadis")
    def test_datadis_reintenta_hasta_obtener_consumos(
        self, descargar, _autenticar
    ):
        descargar.side_effect = [
            pd.DataFrame(),
            pd.DataFrame(),
            pd.DataFrame({
                "date": ["2026/07/01"],
                "time": ["00:00"],
                "consumptionKWh": [1.0],
            }),
        ]
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }

        curva, frecuencia, _ = obtener_consumo_datadis(
            "usuario", "secreto", suministro,
            "01/07/2026", "31/07/2026",
            session=object(),
        )

        self.assertEqual(descargar.call_count, 3)
        self.assertEqual(frecuencia, "H")
        self.assertEqual(len(curva), 1)

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch(
        "backend_curvadecarga._descargar_consumo_datadis",
        return_value=pd.DataFrame(),
    )
    def test_datadis_limita_a_tres_respuestas_vacias(
        self, descargar, _autenticar
    ):
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }

        with self.assertRaisesRegex(ValueError, "no ha devuelto consumos"):
            obtener_consumo_datadis(
                "usuario", "secreto", suministro,
                "01/07/2026", "31/07/2026",
                session=object(),
            )

        self.assertEqual(descargar.call_count, 3)

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch(
        "backend_curvadecarga._descargar_consumo_datadis",
        side_effect=RuntimeError("QH no disponible"),
    )
    def test_un_error_qh_tampoco_provoca_peticion_h(
        self, descargar, _autenticar
    ):
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }
        with self.assertRaisesRegex(RuntimeError, "QH no disponible"):
            obtener_consumo_datadis(
                "usuario", "secreto", suministro,
                "01/07/2026", "31/08/2026",
                preferir_qh=True,
                session=object(),
            )
        self.assertEqual(descargar.call_count, 1)

    @patch("backend_curvadecarga.autenticar_datadis", return_value="token")
    @patch("backend_curvadecarga._descargar_consumo_datadis")
    def test_datadis_solicita_horaria_por_defecto(self, descargar, _autenticar):
        descargar.return_value = pd.DataFrame({
            "date": ["2026/07/01"],
            "time": ["00:00"],
            "consumptionKWh": [1.0],
        })
        suministro = {
            "cups": "ES123",
            "distributorCode": "2",
            "pointType": "3",
        }
        _, frecuencia, _ = obtener_consumo_datadis(
            "usuario", "secreto", suministro,
            "01/07/2026", "31/07/2026",
            session=object(),
        )
        self.assertEqual(frecuencia, "H")
        self.assertEqual(descargar.call_args.args[5], "0")


if __name__ == "__main__":
    unittest.main()
