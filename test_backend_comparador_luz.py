import unittest
import pandas as pd
from backend_comparador_luz import (
    calcular_merma_margen_fijo,
    calcular_ahorro_seleccion_vs_indexados,
    calcular_escenarios_indexados_mensuales,
    comparar_costes_mensuales,
    comparar_costes_mensuales_referenciados,
    comparar_ofertas_fijas,
    construir_curva_coste_oferta_fija,
    consumos_por_periodo,
    filtrar_ofertas_elegibles,
    referenciar_comparativa_costes,
)
from backend_ofertas_fijas import ofertas_catalogo_para_atr
from backend_indexado import FormulaIndexada
from backend_pricing_indexados import calcular_escenarios_pricing_mensuales


class ComparadorLuzTest(unittest.TestCase):
    def test_calcula_merma_con_margen_y_otros_costes(self):
        escenarios = {
            "Indexado": pd.DataFrame({
                "coste_total": [120.0], "coste_margen": [10.0],
                "coste_otros": [5.0],
            })
        }

        salida = calcular_merma_margen_fijo(100.0, escenarios)

        self.assertEqual(salida.iloc[0]["Resultado (€)"], -10.0)
        self.assertEqual(salida.iloc[0]["Merma (€)"], 20.0)
        self.assertEqual(salida.iloc[0]["Colchón consumido (%)"], 200.0)
        self.assertEqual(salida.iloc[1]["Resultado (€)"], -5.0)
        self.assertAlmostEqual(
            salida.iloc[1]["Colchón consumido (%)"], 133.3333333333
        )

    def test_filtra_tramos_de_consumo_escritos_con_simbolos(self):
        ofertas = pd.DataFrame({
            'oferta': [
                'TOTAL | A TU AIRE | < 4.000 KWh | RESIDENCIAL',
                'TOTAL | A TU AIRE | > 4.000 KWh | RESIDENCIAL',
            ],
        })

        compatibles, excluidas = filtrar_ofertas_elegibles(ofertas, 4175)

        self.assertEqual(compatibles['oferta'].tolist(), [
            'TOTAL | A TU AIRE | > 4.000 KWh | RESIDENCIAL'
        ])
        self.assertEqual(len(excluidas), 1)
        self.assertIn('supera 4,000 kWh', excluidas.iloc[0]['Motivo exclusión'])

    def test_comparativa_mensual_admite_cualquier_referencia(self):
        referencia = pd.DataFrame({
            "fecha": ["2026-01-01", "2026-02-01"],
            "coste_total": [100.0, 80.0],
        })
        seleccion = pd.DataFrame({
            "fecha": ["2026-01-01", "2026-02-01"],
            "coste_total": [90.0, 95.0],
        })

        salida = comparar_costes_mensuales_referenciados(
            referencia, seleccion
        )

        self.assertEqual(
            salida["Coste referencia (€)"].tolist(), [100.0, 80.0]
        )
        self.assertEqual(
            salida["Coste selección (€)"].tolist(), [90.0, 95.0]
        )

    def test_construye_curva_de_coste_para_oferta_fija(self):
        curva = pd.DataFrame({
            "periodo": ["P1", "P2"],
            "consumo_neto_kWh": [100.0, 200.0],
        })
        oferta = pd.Series({
            "P1": 0.10, "P2": 0.20, "Fee (€/MWh)": 10.0,
        })

        salida = construir_curva_coste_oferta_fija(curva, oferta)

        self.assertAlmostEqual(salida.loc[0, "coste_total"], 11.0)
        self.assertAlmostEqual(salida.loc[1, "coste_total"], 42.0)

    def test_referencia_comparativa_sin_alterar_orden_por_coste(self):
        resultados = pd.DataFrame({
            "Oferta": ["Fija A", "Indexado", "Cobertura"],
            "Coste (€)": [900.0, 1000.0, 1100.0],
        })

        salida = referenciar_comparativa_costes(resultados, "Indexado")

        self.assertEqual(
            salida["Oferta"].tolist(), ["Fija A", "Indexado", "Cobertura"]
        )
        self.assertEqual(
            salida["Δ referencia (€)"].tolist(), [-100.0, 0.0, 100.0]
        )
        self.assertEqual(
            salida["Δ referencia (%)"].tolist(), [-10.0, 0.0, 10.0]
        )
        self.assertEqual(
            salida["Es referencia"].tolist(), [False, True, False]
        )

    def test_compara_costes_mensuales_de_dos_curvas(self):
        fechas = ["2026-01-01", "2026-01-02", "2026-02-01"]
        indexado = pd.DataFrame({
            "fecha": fechas, "coste_total": [10.0, 20.0, 30.0]
        })
        seleccion = pd.DataFrame({
            "fecha": fechas, "coste_total": [8.0, 16.0, 35.0]
        })

        salida = comparar_costes_mensuales(indexado, seleccion)

        self.assertEqual(salida["Coste indexado (€)"].tolist(), [30.0, 30.0])
        self.assertEqual(salida["Coste selección (€)"].tolist(), [24.0, 35.0])

    def test_ahorro_seleccion_frente_a_tres_indexados(self):
        resultados = pd.DataFrame({
            'Oferta': ['Fija elegida', 'Indexado C', 'Indexado A', 'Indexado B'],
            'Coste total (€)': [900.0, 1200.0, 1000.0, 1100.0],
        })

        ahorro = calcular_ahorro_seleccion_vs_indexados(
            resultados, 'Fija elegida'
        )

        self.assertEqual(
            ahorro['Oferta'].tolist(),
            ['Indexado A', 'Indexado B', 'Indexado C'],
        )
        self.assertEqual(ahorro['Ahorro (€)'].tolist(), [100.0, 200.0, 300.0])
        self.assertAlmostEqual(ahorro.iloc[0]['Ahorro (%)'], 10.0)

    def test_consumos_y_fee(self):
        curva = pd.DataFrame({'consumo_neto_kWh': [100, 200], 'dh_6p': ['P1', 'P2']})
        consumos = consumos_por_periodo(curva, '3.0')
        oferta = pd.DataFrame([{'oferta': 'A', 'Fee (€/MWh)': 10, 'P1': .1, 'P2': .2}])
        resultado = comparar_ofertas_fijas(consumos, oferta)
        self.assertAlmostEqual(resultado.iloc[0]['Coste energía (€)'], 53.0)

    def test_indexado_converge_en_mes_y_periodo(self):
        referencia = pd.DataFrame({
            'fecha': pd.date_range('2025-01-01', periods=12, freq='MS'),
            'dh_6p': 'P1', 'spot': 50.0, 'ssaa': 0.0, 'rad3': 0.0,
            'osom': 0.0, 'perd_3.0': 0.0, 'ppcc_3.0': 0.0,
            'pyc_3.0': 0.0,
        })
        consumos = pd.DataFrame({
            'mes': range(1, 13), 'P1': 100.0,
            **{f'P{i}': 0.0 for i in range(2, 7)},
        })
        resultado = calcular_escenarios_indexados_mensuales(
            referencia, consumos, '3.0', FormulaIndexada(),
            {'A': 40.0}, 0.0, 0.0, 0.0,
        )
        self.assertAlmostEqual(
            resultado.iloc[0]['Precio medio energía (€/kWh)'], 0.103952
        )

    def test_comparadores_comparten_pricing_y_conservan_seis_periodos(self):
        fechas = pd.date_range('2025-01-01', periods=12, freq='MS')
        referencia = pd.DataFrame({
            'fecha': fechas.repeat(6),
            'dh_6p': [f'P{i}' for _ in fechas for i in range(1, 7)],
            'spot': 50.0, 'ssaa': 10.0, 'rad3': 0.0,
            'osom': 1.0, 'perd_3.0': 0.0,
            'ppcc_3.0': 2.0, 'pyc_3.0': 0.0,
        })
        consumos = pd.DataFrame({
            'mes': range(1, 13),
            **{f'P{i}': 100.0 for i in range(1, 7)},
        })
        argumentos = (
            referencia, consumos, '3.0', FormulaIndexada(),
            {'Indexado A': 40.0}, 20.0, 0.0, 1.0,
        )
        pricing = calcular_escenarios_pricing_mensuales(*argumentos)
        comparador_luz = calcular_escenarios_indexados_mensuales(*argumentos)

        self.assertAlmostEqual(
            pricing.iloc[0]['Precio medio energía (€/kWh)'],
            comparador_luz.iloc[0]['Precio medio energía (€/kWh)'],
        )
        self.assertEqual(
            set(pricing.attrs['detalle']['Periodo']),
            {f'P{i}' for i in range(1, 7)},
        )

    def test_pricing_usa_apuntamientos_y_componentes_vigentes(self):
        fechas = pd.date_range('2025-01-01', periods=12, freq='MS')
        referencia = pd.DataFrame({
            'fecha': fechas.repeat(2),
            'dh_6p': ['P1', 'P2'] * 12,
            'spot': [50.0, 100.0] * 12,
            'ssaa': [10.0, 30.0] * 12,
            'rad3': 0.0,
            'osom': [2.0, 4.0] * 12,
            'perd_3.0': 0.0,
            'ppcc_3.0': [3.0, 9.0] * 12,
            'pyc_3.0': 999.0,  # Pricing usa la tabla prevista, no este histórico.
        })
        consumos = pd.DataFrame({
            'mes': range(1, 13),
            'P1': 100.0, 'P2': 100.0,
            **{f'P{i}': 0.0 for i in range(3, 7)},
        })
        resultado = calcular_escenarios_pricing_mensuales(
            referencia, consumos, '3.0', FormulaIndexada(),
            {'A': 75.0}, 20.0, 0.0, 1.0,
        )
        detalle = resultado.attrs['detalle'].groupby('Periodo').first()

        self.assertAlmostEqual(detalle.loc['P1', 'Precio (€/MWh)'], 131.357)
        self.assertAlmostEqual(detalle.loc['P2', 'Precio (€/MWh)'], 184.059)
        self.assertAlmostEqual(
            resultado.loc[0, 'Precio medio energía (€/kWh)'],
            (131.357 + 184.059) / 2000,
        )

    def test_oferta_de_catalogo_conserva_id_para_gestionarla(self):
        catalogo = [{
            'id': 'version-1',
            'nombre': 'Oferta semanal',
            'vigencia_desde': '2026-09-10',
            'vigencia_hasta': '2026-09-17',
            'tarifas': [{
                'atr': '2.0', 'P1': .25, 'P2': .17, 'P3': .14,
                'P4': None, 'P5': None, 'P6': None,
            }],
        }]

        salida = ofertas_catalogo_para_atr(catalogo, '2.0')

        self.assertEqual(salida.loc[0, 'ID oferta'], 'version-1')


if __name__ == '__main__':
    unittest.main()
