import unittest
import pandas as pd
from backend_comparador_luz import (
    calcular_ahorro_seleccion_vs_indexados,
    calcular_escenarios_indexados_mensuales,
    comparar_ofertas_fijas,
    consumos_por_periodo,
)
from backend_indexado import FormulaIndexada


class ComparadorLuzTest(unittest.TestCase):
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
            resultado.iloc[0]['Precio medio energía (€/kWh)'], 0.0406
        )


if __name__ == '__main__':
    unittest.main()
