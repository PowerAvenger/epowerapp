import unittest

import pandas as pd

from backend_indexado import FormulaIndexada, calcular_combo_index_fijo


class ComboIndexFijoTest(unittest.TestCase):
    def _curva(self):
        fechas = pd.to_datetime([
            '2025-01-01 08:00',  # hora de entrega 9: Indexado en enero
            '2025-01-01 09:00',  # hora de entrega 10: Fijo en enero
            '2025-01-01 17:00',  # hora de entrega 18: Fijo en enero
            '2025-01-01 18:00',  # hora de entrega 19: Indexado en enero
        ])
        df = pd.DataFrame({
            'fecha_hora': fechas,
            'consumo_neto_kWh': [100.0, 100.0, 300.0, 100.0],
            'spot': [70.0, 70.0, 70.0, 70.0],
            'dh_6p': ['P1', 'P1', 'P2', 'P2'],
            'ssaa': 0.0,
            'osom': 0.0,
            'fnee': 0.0,
        })
        for atr in ('2.0', '3.0', '6.1'):
            df[f'ppcc_{atr}'] = 0.0
            df[f'perd_{atr}'] = 0.0
            df[f'pyc_{atr}'] = 0.0
        return df

    def test_resume_solo_casillas_fijas_y_pondera_su_consumo(self):
        detalle, resumen = calcular_combo_index_fijo(
            self._curva(), '6.1', FormulaIndexada(), 40.0
        )

        self.assertEqual(detalle['es_fijo'].tolist(), [False, True, True, False])
        self.assertEqual(resumen.loc['Total', 'Consumo (kWh)'], 400.0)
        # La fórmula incluye la tasa municipal del 1,5 %.
        self.assertAlmostEqual(
            resumen.loc['Total', 'Precio medio (EUR/MWh)'], 40.6
        )
        self.assertAlmostEqual(
            resumen.loc['P1', 'Precio medio (EUR/MWh)'], 40.6
        )
        self.assertAlmostEqual(
            resumen.loc['P2', 'Precio medio (EUR/MWh)'], 40.6
        )
        self.assertTrue(pd.isna(resumen.loc['P3', 'Precio medio (EUR/MWh)']))


if __name__ == '__main__':
    unittest.main()
