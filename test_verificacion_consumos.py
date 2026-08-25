import unittest
import io

import pandas as pd

from backend_verificacion_consumos import (
    calcular_energia_indexada,
    calcular_energia_fija,
    calcular_excesos_desde_curva,
    calcular_potencia_confirmada,
    debe_prorratear_excesos_tramo,
    estado_verificacion_energia_real,
    preparar_archivos_factura,
    preparar_curva_factura,
    reconstruir_total_beta,
    tabla_conciliacion_consumos,
)


class VerificacionConsumosTest(unittest.TestCase):
    def test_reconoce_los_tres_tipos_con_prorrateo_cuadratico(self):
        for tipo in ("Tipo 1", "Tipo 2", "Tipo 3", "1", "2", "3"):
            with self.subTest(tipo=tipo):
                self.assertTrue(
                    debe_prorratear_excesos_tramo(
                        "01/07/2026", "16/07/2026",
                        numero_tramos=1, tipo_suministro=tipo,
                    )
                )

    def test_prorratea_ruptura_de_mes_natural_con_un_solo_tramo(self):
        self.assertTrue(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "16/07/2026", numero_tramos=1,
                tipo_suministro="Tipo 2",
            )
        )

    def test_prorratea_ruptura_de_mes_natural_en_tipo_3(self):
        self.assertTrue(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "16/07/2026", numero_tramos=1,
                tipo_suministro="Tipo 3",
            )
        )

    def test_no_prorratea_un_ciclo_ordinario_entre_dos_meses(self):
        self.assertFalse(
            debe_prorratear_excesos_tramo(
                "15/07/2026", "14/08/2026", numero_tramos=1,
                tipo_suministro="Tipo 2",
            )
        )

    def test_no_prorratea_un_mes_natural_completo(self):
        self.assertFalse(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "31/07/2026", numero_tramos=1,
                tipo_suministro="Tipo 1",
            )
        )

    def test_varios_tramos_prorratean_solo_en_tipos_1_2_y_3(self):
        self.assertTrue(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "31/07/2026", numero_tramos=2,
                tipo_suministro="Tipo 1",
            )
        )

    def test_no_extiende_el_ciclo_natural_a_tipos_4_y_5(self):
        self.assertFalse(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "16/07/2026", numero_tramos=1,
                tipo_suministro="Tipo 4",
            )
        )
        self.assertFalse(
            debe_prorratear_excesos_tramo(
                "01/07/2026", "16/07/2026", numero_tramos=2,
                tipo_suministro="Tipo 5",
            )
        )

    def test_precio_final_ponderado_con_curva_cuartohoraria(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.date_range(
                "2026-07-01 00:00", periods=8, freq="15min"
            ),
            "periodo": ["P1"] * 4 + ["P2"] * 4,
            "consumo_neto_kWh": [1.0] * 4 + [2.0] * 4,
        })
        precios = pd.DataFrame({
            "fecha": ["2026-07-01", "2026-07-01"],
            "hora": [0, 1],
            "precio_6.1": [100.0, 200.0],
        })

        detalle, total = calcular_energia_indexada(
            curva, precios, "6.1", "QH"
        )

        self.assertEqual(total, 2.0)
        self.assertAlmostEqual(detalle["Consumo medida (kWh)"].sum(), 12.0)
        self.assertAlmostEqual(total / 12.0, 1 / 6)

    def test_precio_ponderado_rechaza_horas_sin_precio(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.to_datetime([
                "2026-07-01 00:00", "2026-07-01 01:00"
            ]),
            "periodo": ["P1", "P2"],
            "consumo_neto_kWh": [1.0, 1.0],
        })
        precios = pd.DataFrame({
            "fecha": ["2026-07-01"],
            "hora": [0],
            "precio_6.1": [100.0],
        })

        with self.assertRaisesRegex(ValueError, "Faltan precios Telemindex"):
            calcular_energia_indexada(curva, precios, "6.1", "H")

    def test_prepara_ciclo_completo_y_resume_periodos(self):
        horas = [f"{hora:02d}:00" for hora in range(24)]
        curva = pd.DataFrame({
            "Fecha": ["01/06/2026"] * 24,
            "Hora": horas,
            "Consumo (kWh)": [1.0] * 24,
            "Periodo": ["P3"] * 24,
        })
        resultado = preparar_curva_factura(
            curva, "01/06/2026", "01/06/2026", atr="2.0"
        )
        self.assertTrue(resultado.cobertura["completa"])
        self.assertEqual(resultado.consumos_periodos, {"P3": 24.0})

    def test_compara_factura_y_medida_con_diferencia_con_signo(self):
        tabla = tabla_conciliacion_consumos(
            {"P1": 100.0, "P2": 50.0, "P3": 200.0},
            {"P1": 98.0, "P2": 55.0, "P3": 200.0},
        )
        total = tabla.iloc[-1]
        self.assertEqual(total["Factura (kWh)"], 350.0)
        self.assertEqual(total["Medida (kWh)"], 353.0)
        self.assertEqual(total["Diferencia (kWh)"], 3.0)

    def test_valora_medida_con_precios_confirmados(self):
        detalle, total = calcular_energia_fija(
            {"P1": 100.0, "P2": 50.0, "P3": 200.0},
            {"P1": 0.20, "P2": 0.15, "P3": 0.10},
        )
        self.assertEqual(len(detalle), 3)
        self.assertEqual(total, 47.50)

    def test_semaforo_energia_real_compara_costes(self):
        self.assertEqual(estado_verificacion_energia_real(50.0, 50.01), "🟢")
        self.assertEqual(estado_verificacion_energia_real(48.0, 50.0), "🟢 ⚠️")
        self.assertEqual(estado_verificacion_energia_real(52.0, 50.0), "🔴")

    def test_semaforo_energia_real_exige_datos_completos(self):
        self.assertEqual(
            estado_verificacion_energia_real(
                50.0, 50.0, cobertura_completa=False
            ),
            "🟡",
        )
        self.assertEqual(
            estado_verificacion_energia_real(
                50.0, 50.0, precios_completos=False
            ),
            "🟡",
        )

    def test_reune_varios_csv_antes_de_comprobar_cobertura(self):
        archivos = []
        for inicio, fin, nombre in ((0, 12, "parte_1.csv"), (12, 24, "parte_2.csv")):
            lineas = ["Fecha;Hora;Consumo (kWh);Periodo"]
            lineas.extend(
                f"01/06/2026;{hora:02d}:00;1.0;P3"
                for hora in range(inicio, fin)
            )
            archivo = io.BytesIO(("\n".join(lineas) + "\n").encode("utf-8"))
            archivo.name = nombre
            archivos.append(archivo)

        resultado = preparar_archivos_factura(
            archivos, "01/06/2026", "01/06/2026", atr="2.0"
        )

        self.assertTrue(resultado.cobertura["completa"])
        self.assertEqual(resultado.consumos_periodos, {"P3": 24.0})

    def test_calcula_potencia_confirmada(self):
        detalle, total = calcular_potencia_confirmada([
            {
                "periodo": "P1", "potencia_kw": 4.0, "dias": 30,
                "precio_eur_kw_dia": 0.10,
            },
            {
                "periodo": "P2", "potencia_kw": 4.0, "dias": 30,
                "precio_eur_kw_dia": 0.05,
            },
        ])
        self.assertEqual(len(detalle), 2)
        self.assertEqual(total, 18.0)

    def test_calcula_excesos_qh_reutilizando_termino_potencia(self):
        curva = pd.DataFrame({
            "fecha_hora": [pd.Timestamp("2026-06-01 00:00")],
            "periodo": ["P1"],
            "consumo_neto_kWh": [25.25],
        })
        detalle, total = calcular_excesos_desde_curva(
            curva, "QH", "6.1", 2026, {"P1": 100.0}
        )
        self.assertAlmostEqual(total, 3.43, places=2)
        self.assertAlmostEqual(
            detalle.loc[0, "Maxímetro (kW)"], 101.0, places=6
        )
        self.assertAlmostEqual(
            detalle.loc[0, "Raíz Σ excesos² (kW)"], 1.0, places=6
        )

    def test_prorratea_coste_de_curva_16_31_sin_alterar_la_raiz(self):
        tepp_p1 = 3.431797
        raiz_objetivo = 9837.38 / tepp_p1
        curva = pd.DataFrame({
            "fecha_hora": [
                pd.Timestamp("2026-07-01 00:00"),
                pd.Timestamp("2026-07-16 23:45"),
            ],
            "periodo": ["P1", "P1"],
            "consumo_neto_kWh": [
                (100.0 + raiz_objetivo) / 4,
                25.0,
            ],
        })

        detalle_bruto, total_bruto = calcular_excesos_desde_curva(
            curva, "QH", "6.1", 2026, {"P1": 100.0}, prorratear=False
        )
        detalle_prorrateado, total_prorrateado = calcular_excesos_desde_curva(
            curva, "QH", "6.1", 2026, {"P1": 100.0}, prorratear=True
        )

        self.assertEqual(total_bruto, 9837.38)
        self.assertEqual(total_prorrateado, 5077.36)
        self.assertAlmostEqual(
            detalle_prorrateado.loc[0, "Factor prorrateo"], 16 / 31
        )
        columna_raiz = next(
            columna for columna in detalle_bruto.columns
            if columna.startswith("Raíz")
        )
        self.assertAlmostEqual(
            detalle_bruto.loc[0, columna_raiz],
            detalle_prorrateado.loc[0, columna_raiz],
        )

    def test_un_exceso_confirmado_a_cero_modifica_el_total(self):
        resultado = reconstruir_total_beta(
            total_factura=121.0,
            potencia_facturada=10.0,
            potencia_verificada=10.0,
            energia_facturada=50.0,
            energia_verificada=50.0,
            otros_facturados={"excesos_potencia": 10.0},
            otros_confirmados={"excesos_potencia": 0.0},
            iee_facturado=0.0,
            iva_facturado=21.0,
        )
        self.assertEqual(resultado["total_verificado"], 111.0)

    def test_reconstruye_total_y_recalcula_impuestos(self):
        resultado = reconstruir_total_beta(
            total_factura=101.64,
            potencia_facturada=10.0,
            potencia_verificada=12.0,
            energia_facturada=50.0,
            energia_verificada=45.0,
            otros_facturados={"otros": 20.0},
            otros_confirmados={"otros": 20.0},
            iee_facturado=4.0,
            iva_facturado=17.64,
            base_iee_factura=80.0,
            tipo_iee_pct=5.0,
            base_iva_factura=84.0,
            tipo_iva_pct=21.0,
        )
        self.assertEqual(resultado["iee_verificado"], 3.85)
        self.assertEqual(resultado["iva_verificado"], 16.98)
        self.assertEqual(resultado["total_verificado"], 97.83)


if __name__ == "__main__":
    unittest.main()
