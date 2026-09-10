import io
import unittest
from unittest.mock import patch

import pandas as pd

from backend_comun import filtrar_intervalos_inexistentes_madrid

from backend_curvadecarga import (
    DatadisLimiteConsultas,
    _normalizar_maximetros_datadis,
    _normalizar_reactiva_datadis,
    agrupar_curva_horaria,
    analizar_calidad_curva,
    analizar_cobertura_periodo,
    cargar_matriz_periodos_zonas,
    clave_cache_consumo_datadis,
    dataframe_como_archivo_curva,
    detectar_periodos_en_fuente,
    dividir_energias_curva,
    inferir_zonas_por_periodos,
    normalize_curve_simple,
    obtener_consumo_datadis,
    obtener_consumo_datadis_cacheado,
    rango_meses_datadis,
    recortar_curva_periodo,
    resumir_consumo_por_periodo,
)
from servicio_curva import (
    aviso_resolucion_curva,
    limpiar_curva_sesion,
    normalizar_fuentes_curva,
    obtener_curva_sesion,
    publicar_curva_sesion,
)


class CurvasComunesTest(unittest.TestCase):
    def test_aviso_resolucion_cuartohoraria(self):
        nivel, mensaje = aviso_resolucion_curva("qh")

        self.assertEqual(nivel, "info")
        self.assertIn("QH (cuartohoraria, intervalos de 15 minutos)", mensaje)

    def test_aviso_resolucion_horaria_advierte_sobre_excesos(self):
        nivel, mensaje = aviso_resolucion_curva("H")

        self.assertEqual(nivel, "warning")
        self.assertIn("intervalos de 60 minutos", mensaje)
        self.assertIn("excesos de potencia", mensaje)

    def test_infiere_una_zona_en_curva_de_seis_periodos(self):
        matriz = cargar_matriz_periodos_zonas()
        matriz = matriz[matriz["fecha_hora"].dt.year.eq(2025)]
        curva = matriz[["fecha_hora", "p6_peninsula"]].rename(
            columns={"p6_peninsula": "periodo"}
        )

        zonas, cobertura = inferir_zonas_por_periodos(curva)

        self.assertEqual(zonas, ["peninsula"])
        self.assertEqual(cobertura, 1.0)

    def test_tres_periodos_puede_ser_compatible_con_varias_zonas(self):
        matriz = cargar_matriz_periodos_zonas()
        matriz = matriz[matriz["fecha_hora"].dt.year.eq(2025)]
        curva = matriz[["fecha_hora", "p3"]].rename(
            columns={"p3": "periodo"}
        )

        zonas, _ = inferir_zonas_por_periodos(curva)

        self.assertEqual(
            zonas, ["peninsula", "baleares", "canarias", "ceuta", "melilla"]
        )

    def test_duplicado_de_octubre_se_conserva_y_se_identifica(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.to_datetime([
                "2025-10-26 02:00", "2025-10-26 02:00"
            ]),
            "consumo_kWh": [1.0, 2.0],
        })

        diagnostico = analizar_calidad_curva(curva, frecuencia="H")

        self.assertEqual(diagnostico["duplicados_fecha_hora"], 1)
        self.assertEqual(diagnostico["duplicados_cambio_hora_octubre"], 1)
        self.assertEqual(curva["consumo_kWh"].tolist(), [1.0, 2.0])

    def test_prelectura_detecta_periodos_y_restaura_el_archivo(self):
        archivo = io.BytesIO((
            "Fecha;Hora;Consumo (kWh);Periodo\n"
            "01/07/2025;00:00;1;P3\n"
        ).encode("utf-8"))
        archivo.name = "con_periodos.csv"
        archivo.seek(7)

        self.assertTrue(detectar_periodos_en_fuente(archivo))
        self.assertEqual(archivo.tell(), 7)

    def test_prelectura_no_confunde_curva_sin_periodos(self):
        archivo = io.BytesIO((
            "Fecha;Hora;Consumo (kWh)\n"
            "01/07/2025;00:00;1\n"
        ).encode("utf-8"))
        archivo.name = "sin_periodos.csv"

        self.assertFalse(detectar_periodos_en_fuente(archivo))

    def test_servicio_publica_la_curva_activa_con_contrato_compatible(self):
        lineas = ["Fecha;Hora;Consumo (kWh);Periodo"]
        lineas.extend(
            f"01/07/2025;{hora:02d}:00;1,25;P3" for hora in range(24)
        )
        archivo = io.BytesIO(("\n".join(lineas) + "\n").encode("utf-8"))
        archivo.name = "curva_servicio.csv"

        resultado = normalizar_fuentes_curva(archivo, atr="3.0")
        estado = {}
        publicar_curva_sesion(estado, resultado)

        self.assertEqual(resultado.frecuencia, "H")
        self.assertEqual(resultado.atr, "2.0")
        self.assertEqual(len(resultado.df_norm_h), 24)
        self.assertIs(estado["df_norm"], resultado.df_norm)
        self.assertIs(estado["df_norm_h"], resultado.df_norm_h)
        self.assertIsNotNone(obtener_curva_sesion(estado))
        self.assertEqual(estado["curva_actual"]["atr"], "2.0")
        self.assertAlmostEqual(estado["consumo_total"], 30.0)

    def test_servicio_rechaza_archivos_con_frecuencias_distintas(self):
        horario = io.BytesIO((
            "Fecha;Hora;Consumo (kWh);Periodo\n"
            "01/07/2025;00:00;1;P3\n"
            "01/07/2025;01:00;1;P3\n"
        ).encode("utf-8"))
        horario.name = "horaria.csv"
        cuarto_horario = io.BytesIO((
            "Fecha;Hora;Consumo (kWh);Periodo\n"
            "01/07/2025;00:15;0,25;P3\n"
            "01/07/2025;00:30;0,25;P3\n"
            "01/07/2025;00:45;0,25;P3\n"
            "01/07/2025;01:00;0,25;P3\n"
        ).encode("utf-8"))
        cuarto_horario.name = "cuartohoraria.csv"

        with self.assertRaisesRegex(ValueError, "resoluciones temporales distintas"):
            normalizar_fuentes_curva([horario, cuarto_horario], atr="2.0")

    def test_servicio_limpia_la_curva_activa(self):
        estado = {
            "curva_actual": {"version": 1},
            "df_norm": pd.DataFrame({"a": [1]}),
            "df_norm_h": pd.DataFrame({"a": [1]}),
            "curva_uploader_version": 4,
        }

        limpiar_curva_sesion(estado)

        self.assertNotIn("curva_actual", estado)
        self.assertNotIn("df_norm", estado)
        self.assertNotIn("df_norm_h", estado)
        self.assertEqual(estado["curva_uploader_version"], 5)

    def test_elimina_hora_inexistente_del_cambio_de_marzo(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.to_datetime([
                "2026-03-29 01:00",
                "2026-03-29 02:00",
                "2026-03-29 03:00",
                "2026-03-30 02:00",
            ]),
            "consumo_kWh": [1.0, 2.0, 3.0, 4.0],
        })

        resultado = filtrar_intervalos_inexistentes_madrid(curva)

        self.assertEqual(len(resultado), 3)
        self.assertNotIn(
            pd.Timestamp("2026-03-29 02:00"),
            resultado["fecha_hora"].tolist(),
        )
        self.assertIn(
            pd.Timestamp("2026-03-30 02:00"),
            resultado["fecha_hora"].tolist(),
        )

    def test_dividir_energias_no_modifica_fechas_horas_ni_periodos(self):
        original = pd.DataFrame({
            "fecha_hora": pd.to_datetime(["2025-07-01 00:00"]),
            "hora": [0],
            "periodo": ["P6"],
            "consumo_kWh": [5255.0],
            "consumo_neto_kWh": [5255.0],
            "reactiva_kVArh": [1800.0],
        })

        resultado = dividir_energias_curva(original)

        self.assertEqual(resultado.loc[0, "consumo_kWh"], 5.255)
        self.assertEqual(resultado.loc[0, "consumo_neto_kWh"], 5.255)
        self.assertEqual(resultado.loc[0, "reactiva_kVArh"], 1.8)
        self.assertEqual(resultado.loc[0, "periodo"], "P6")
        self.assertEqual(resultado.loc[0, "hora"], 0)
        self.assertEqual(
            resultado.loc[0, "fecha_hora"], original.loc[0, "fecha_hora"]
        )
        self.assertEqual(original.loc[0, "consumo_kWh"], 5255.0)

    def test_r1_se_detecta_como_reactiva_sin_confundir_otros_cuadrantes(self):
        lineas = [
            "dia_semana;fecha;hora;D.H.;periodo;prelacion;"
            "M.Lin;AI;AE;R1;R2;R3;R4"
        ]
        lineas.extend(
            f"MAR;01/07/2025;{hora}:00;Tarifa-2021 ;6;1;"
            f"N;247;0;{40 + hora};999;888;777"
            for hora in range(24)
        )
        archivo = io.BytesIO(("\n".join(lineas) + "\n").encode("cp1252"))
        archivo.name = "medidas_profiltek.csv"

        _, normalizada, _, _, _, frecuencia = normalize_curve_simple(archivo)

        self.assertEqual(frecuencia, "H")
        self.assertEqual(normalizada["reactiva_kVArh"].iloc[0], 40)
        self.assertEqual(normalizada["reactiva_kVArh"].iloc[-1], 63)
        self.assertNotEqual(normalizada["reactiva_kVArh"].iloc[0], 999)

    def test_fecha_prevalece_sobre_dia_semana_en_csv_platek(self):
        lineas = ["dia_semana;fecha;hora;D.H.;periodo;prelacion;;;AI"]
        lineas.extend(
            f"MAR;01/07/2025;{hora}:00;Tarifa-2021 ;6;1;;;5255"
            for hora in range(24)
        )
        archivo = io.BytesIO(("\n".join(lineas) + "\n").encode("cp1252"))
        archivo.name = "medidas_platek.csv"

        _, normalizada, _, periodos_origen, _, frecuencia = (
            normalize_curve_simple(archivo)
        )

        self.assertEqual(frecuencia, "H")
        self.assertTrue(periodos_origen)
        self.assertEqual(len(normalizada), 24)
        self.assertEqual(
            normalizada["fecha_hora"].iloc[0],
            pd.Timestamp("2025-07-01 00:00:00"),
        )

    def test_csv_cp1252_con_fecha_ddmmyyyy_y_hora_sin_cero_inicial(self):
        lineas = ["fecha;hora;ENERGÍA ACTIVA (kWh);periodo"]
        lineas.extend(
            f"01/07/2025;{hora}:00;1,25;P1"
            for hora in range(24)
        )
        archivo = io.BytesIO(("\n".join(lineas) + "\n").encode("cp1252"))
        archivo.name = "curva_cp1252.csv"

        _, normalizada, _, periodos_origen, _, frecuencia = (
            normalize_curve_simple(archivo)
        )

        self.assertEqual(frecuencia, "H")
        self.assertTrue(periodos_origen)
        self.assertEqual(len(normalizada), 24)
        self.assertTrue(normalizada["fecha_hora"].notna().all())
        self.assertEqual(
            normalizada["fecha_hora"].iloc[0],
            pd.Timestamp("2025-07-01 00:00:00"),
        )
        self.assertAlmostEqual(normalizada["consumo_kWh"].sum(), 30.0)

    def test_maximetros_datadis_usan_periodo_y_no_hora_limite(self):
        datos = {"maxPower": [
            {
                "cups": "ES123", "date": "2026/06/30", "time": "23:45",
                "maxPower": 0.0, "period": "3",
            },
            {
                "cups": "ES123", "date": "2026/07/10", "time": "10:00",
                "maxPower": 8.828, "period": "1",
            },
        ]}

        resultado, exacto = _normalizar_maximetros_datadis(
            datos, "30/06/2026", "31/07/2026"
        )

        self.assertTrue(exacto)
        self.assertEqual(resultado["period"].tolist(), ["P1", "P3"])
        self.assertNotIn("fecha_hora_local", resultado.columns)

    def test_reactiva_datadis_solo_es_exacta_para_mes_natural(self):
        datos = {"reactiveEnergy": {"energy": [
            {"date": "2026/07", "energyP1": 10.0, "energyP2": 5.0}
        ]}}

        mensual, exacto_mensual = _normalizar_reactiva_datadis(
            datos, "30/06/2026", "31/07/2026"
        )
        parcial, exacto_parcial = _normalizar_reactiva_datadis(
            datos, "10/07/2026", "31/07/2026"
        )

        self.assertTrue(exacto_mensual)
        self.assertEqual(mensual.loc[0, "P1"], 10.0)
        self.assertFalse(exacto_parcial)
        self.assertEqual(len(parcial), 1)

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
