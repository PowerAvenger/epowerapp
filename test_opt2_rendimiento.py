import unittest

import numpy as np
import pandas as pd

from backend_opt2 import (
    _costes_rapidos_por_periodo,
    _preparar_calculo_rapido,
    calcular_costes,
    meses,
)


class TestCalculoRapidoPotencia(unittest.TestCase):
    def _comparar(self, datos, potencias, pyc, tepp):
        contexto = _preparar_calculo_rapido(datos, potencias)
        rapido = _costes_rapidos_por_periodo(
            contexto, potencias, pyc, tepp
        )
        _, _, _, df_potencia, df_excesos = calcular_costes(
            datos, '3.0', pyc, tepp, meses, potencias
        )
        for periodo in potencias:
            self.assertAlmostEqual(
                rapido[periodo][0], df_potencia[periodo].sum(), places=8
            )
            self.assertAlmostEqual(
                rapido[periodo][1], df_excesos[periodo].sum(), places=8
            )

    def test_equivalencia_curva(self):
        fechas = pd.date_range('2026-01-01', periods=24 * 40, freq='h')
        periodos = np.resize(['P1', 'P2', 'P3', 'P4', 'P5', 'P6'], len(fechas))
        datos = pd.DataFrame(
            {
                'fecha_hora': fechas,
                'mes_nom': fechas.strftime('%b'),
                'periodo': periodos,
                'potencia': 50 + np.arange(len(fechas)) % 37,
            }
        )
        potencias = {f'P{i}': 55.0 + i for i in range(1, 7)}
        pyc = {f'P{i}': 8.0 - i / 2 for i in range(1, 7)}
        tepp = {f'P{i}': 0.1 + i / 100 for i in range(1, 7)}
        self._comparar(datos, potencias, pyc, tepp)

    def test_equivalencia_maximetros(self):
        indices = pd.period_range('2025-01', periods=12, freq='M')
        datos = pd.DataFrame(
            {
                'periodo_mes': indices.astype(str),
                'mes_nom': [str(i) for i in range(12)],
                'dias_facturacion': indices.days_in_month,
                **{
                    f'P{i}': 30 + i + np.arange(12)
                    for i in range(1, 7)
                },
            }
        )
        potencias = {f'P{i}': 35.0 + i for i in range(1, 7)}
        pyc = {f'P{i}': 8.0 - i / 2 for i in range(1, 7)}
        tepp = {f'P{i}': 0.01 + i / 1000 for i in range(1, 7)}
        self._comparar(datos, potencias, pyc, tepp)


if __name__ == '__main__':
    unittest.main()
