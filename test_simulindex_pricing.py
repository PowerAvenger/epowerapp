import unittest

import pandas as pd

from backend_opt2 import consumos_mensuales_desde_curva_normalizada


class ConsumosCurvaPricingTest(unittest.TestCase):
    def test_agrupa_por_mes_y_periodo_con_formato_sips(self):
        fechas = pd.date_range('2025-01-01', '2025-12-31 23:00', freq='h')
        curva = pd.DataFrame({
            'fecha_hora': fechas,
            'periodo': ['P1' if fecha.hour < 12 else 'P2' for fecha in fechas],
            'consumo_neto_kWh': 1.0,
        })

        resultado = consumos_mensuales_desde_curva_normalizada(curva)

        self.assertEqual(len(resultado), 12)
        self.assertEqual(
            resultado.columns.tolist(),
            ['periodo_mes', 'año', 'mes', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6'],
        )
        enero = resultado.loc[resultado['mes'] == 1].iloc[0]
        self.assertEqual(enero['P1'], 31 * 12)
        self.assertEqual(enero['P2'], 31 * 12)
        self.assertEqual(enero[['P3', 'P4', 'P5', 'P6']].sum(), 0)
        self.assertEqual(resultado.loc[:, 'P1':'P6'].sum().sum(), len(curva))

    def test_exige_doce_meses_como_el_excel_sips(self):
        curva = pd.DataFrame({
            'fecha_hora': pd.date_range('2025-01-01', periods=24, freq='h'),
            'periodo': 'P1',
            'consumo_neto_kWh': 1.0,
        })

        with self.assertRaisesRegex(ValueError, 'solo contiene 1 meses'):
            consumos_mensuales_desde_curva_normalizada(curva)


if __name__ == '__main__':
    unittest.main()
