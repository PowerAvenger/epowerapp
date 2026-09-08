import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

import utilidades
from backend_escalacv import combinar_series_mercado


class EstadoSesion(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def serie(valores):
    indice = pd.DatetimeIndex(
        ["2026-01-01 00:00", "2026-01-01 01:00"],
        name="datetime",
    )
    datos = pd.DataFrame({"value": valores}, index=indice)
    datos["fecha"] = datos.index.date
    datos["hora"] = datos.index.hour
    datos["dia"] = datos.index.day
    datos["mes"] = datos.index.month
    datos["año"] = datos.index.year
    return datos


class TestDatosMercadoComunes(unittest.TestCase):
    def setUp(self):
        self.estado = EstadoSesion()
        self.spot = serie([50.0, 60.0])
        self.ssaa = serie([5.0, 7.0])
        self.fecha = datetime.date(2026, 1, 1)
        self.carga = MagicMock(
            return_value=(
                (self.spot, self.fecha, self.fecha),
                (self.ssaa, self.fecha, self.fecha),
            )
        )
        self.streamlit = SimpleNamespace(
            session_state=self.estado,
            secrets={
                "FILE_ID_SPOT": "spot",
                "FILE_ID_SSAA": "ssaa",
                "GOOGLE_SHEETS_CREDENTIALS": {"test": True},
            },
        )

    def test_precarga_una_vez_y_reutiliza_las_dos_series(self):
        with (
            patch.object(utilidades, "st", self.streamlit),
            patch.object(utilidades, "cargar_series_mercado", self.carga),
        ):
            primera = utilidades.init_datos_mercado()
            segunda = utilidades.init_datos_mercado()

        self.assertEqual(self.carga.call_count, 1)
        self.assertIs(primera[0][0], segunda[0][0])
        self.assertIs(primera[1][0], segunda[1][0])

    def test_spot_mas_ssaa_se_construye_desde_la_precarga(self):
        with (
            patch.object(utilidades, "st", self.streamlit),
            patch.object(utilidades, "cargar_series_mercado", self.carga),
        ):
            datos, fecha_ini, fecha_fin = utilidades.obtener_datos_mercado(
                "SPOT+SSAA"
            )

        self.assertEqual(datos["value"].tolist(), [55.0, 67.0])
        self.assertEqual(datos["value_spot"].tolist(), [50.0, 60.0])
        self.assertEqual(datos["value_ssaa"].tolist(), [5.0, 7.0])
        self.assertEqual((fecha_ini, fecha_fin), (self.fecha, self.fecha))

    def test_actualizar_vacia_y_vuelve_a_cargar_ambas_series(self):
        lector = MagicMock()
        with (
            patch.object(utilidades, "st", self.streamlit),
            patch.object(utilidades, "cargar_series_mercado", self.carga),
            patch.object(utilidades, "leer_json", lector),
        ):
            utilidades.init_datos_mercado()
            utilidades.actualizar_datos_mercado()

        self.assertEqual(self.carga.call_count, 2)
        self.carga.clear.assert_called_once_with()
        lector.clear.assert_called_once_with()

    def test_cambio_octubre_empareja_las_dos_horas_sin_multiplicarlas(self):
        indice = pd.DatetimeIndex(
            [
                "2025-10-26 01:00",
                "2025-10-26 02:00",
                "2025-10-26 02:00",
                "2025-10-26 03:00",
            ],
            name="datetime",
        )
        spot = pd.DataFrame({"value": [10.0, 20.0, 30.0, 40.0]}, index=indice)
        ssaa = pd.DataFrame({"value": [1.0, 2.0, 3.0, 4.0]}, index=indice)

        combinado = combinar_series_mercado(spot, ssaa)

        self.assertEqual(len(combinado), 4)
        self.assertEqual(combinado["value"].tolist(), [11.0, 22.0, 33.0, 44.0])


if __name__ == "__main__":
    unittest.main()
