import unittest

import pandas as pd

from backend_simulindex import (
    construir_curva_omip_mensual_12m,
    construir_evolucion_media_omip,
)


class TestPrevisionAnualOmip(unittest.TestCase):
    def test_septiembre_proyecta_octubre_a_septiembre_y_cuadra_media(self):
        entregas = pd.date_range('2026-10-01', '2027-09-01', freq='MS')
        precios = [90.123 + i for i in range(12)]
        mensuales = pd.DataFrame(
            {
                'Fecha': pd.Timestamp('2026-08-31'),
                'Entrega_dt': entregas,
                'Precio': precios,
            }
        )
        trimestrales = pd.DataFrame(
            columns=['Fecha', 'Inicio Entrega', 'Precio']
        )
        fecha_ref = pd.Timestamp('2026-09-01')

        curva = construir_curva_omip_mensual_12m(
            mensuales, trimestrales, fecha_ref
        )
        evolucion = construir_evolucion_media_omip(
            mensuales,
            trimestrales,
            fecha_ref,
            fecha_inicio='01.01.2026',
        )

        self.assertEqual(curva['fecha'].iloc[0], pd.Timestamp('2026-10-01'))
        self.assertEqual(curva['fecha'].iloc[-1], pd.Timestamp('2027-09-01'))
        self.assertAlmostEqual(
            curva['precio'].mean(),
            evolucion['media_forward_12m'].iloc[-1],
            places=2,
        )
        self.assertEqual(evolucion['Fecha'].iloc[-1], fecha_ref)


if __name__ == '__main__':
    unittest.main()
