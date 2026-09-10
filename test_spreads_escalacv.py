import unittest

import pandas as pd

from backend_escalacv import (
    calcular_spreads_diarios,
    calcular_volatilidad_diaria,
    graficar_spreads_historicos,
)


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

    def test_grafico_historico_empieza_en_2018(self):
        spreads = pd.DataFrame(
            {
                'fecha': pd.to_datetime(
                    ['2017-12-31', '2018-01-01', '2026-01-01']
                ),
                'spread_diario': [5.0, 10.0, 20.0],
            }
        )

        figura = graficar_spreads_historicos(spreads)

        self.assertIsNotNone(figura)
        self.assertEqual(list(figura.data[0].y), [10.0, 20.0])
        self.assertEqual(
            pd.to_datetime(list(figura.data[0].x)).min(),
            pd.Timestamp('2018-01-01'),
        )
        self.assertEqual(len(figura.data), 3)
        self.assertEqual(list(figura.data[1].y), [10.0, 10.0, 10.0])
        self.assertEqual(list(figura.data[2].y), [20.0, 20.0, 20.0])
        self.assertEqual(figura.data[1].line.color, 'yellow')
        self.assertEqual(figura.data[1].line.dash, 'dot')
        self.assertEqual(figura.layout.annotations[0].text, '<b>10.00</b>')
        self.assertEqual(figura.layout.annotations[0].yshift, 14)
        self.assertEqual(figura.layout.annotations[0].font.color, 'yellow')
        self.assertEqual(figura.layout.annotations[0].font.family, 'Arial')

        figura_ssaa = graficar_spreads_historicos(
            spreads, componente='SSAA'
        )
        self.assertIn('SSAA', figura_ssaa.layout.title.text)
        self.assertEqual(len(figura.layout.updatemenus), 0)
        self.assertEqual(len(figura_ssaa.layout.updatemenus), 1)
        self.assertEqual(
            figura_ssaa.layout.updatemenus[0].buttons[1].args[0][
                'yaxis.range'
            ],
            [0, 100],
        )

    def test_volatilidad_diaria_usa_todos_los_precios_horarios(self):
        datos = pd.DataFrame(
            {
                'fecha': [
                    pd.Timestamp('2026-01-01').date(),
                    pd.Timestamp('2026-01-01').date(),
                    pd.Timestamp('2026-01-01').date(),
                    pd.Timestamp('2026-01-02').date(),
                    pd.Timestamp('2026-01-02').date(),
                ],
                'value': [10.0, 20.0, 30.0, 100.0, 100.0],
            }
        )

        volatilidad = calcular_volatilidad_diaria(datos)

        self.assertAlmostEqual(
            volatilidad['volatilidad_diaria'].iloc[0], 8.1649658
        )
        self.assertEqual(volatilidad['volatilidad_diaria'].iloc[1], 0.0)
        self.assertEqual(volatilidad['registros'].tolist(), [3, 2])


if __name__ == '__main__':
    unittest.main()
