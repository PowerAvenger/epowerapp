import unittest

import pandas as pd

from backend_escalacv import calcular_spreads_diarios


class TestSpreadsDiarios(unittest.TestCase):
    def test_calcula_primero_cada_dia_y_despues_su_media(self):
        datos = pd.DataFrame(
            {
                'fecha': [
                    pd.Timestamp('2026-01-01').date(),
                    pd.Timestamp('2026-01-01').date(),
                    pd.Timestamp('2026-01-02').date(),
                    pd.Timestamp('2026-01-02').date(),
                ],
                'value': [10.0, 30.0, 100.0, 110.0],
            }
        )

        spreads = calcular_spreads_diarios(datos)

        self.assertEqual(spreads['spread_diario'].tolist(), [20.0, 10.0])
        self.assertEqual(spreads['spread_diario'].mean(), 15.0)
        self.assertEqual(spreads['registros'].tolist(), [2, 2])


if __name__ == '__main__':
    unittest.main()
