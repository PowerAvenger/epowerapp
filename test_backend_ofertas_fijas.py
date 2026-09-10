import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from backend_ofertas_fijas import (
    cargar_catalogo_ofertas,
    catalogo_a_dataframe,
    eliminar_versiones_oferta,
    guardar_version_oferta,
    normalizar_tarifas_oferta,
)


class CatalogoOfertasFijasTest(unittest.TestCase):
    def test_conserva_versiones_y_todos_los_atr(self):
        tarifas = pd.DataFrame([
            {'ATR': '2.0', 'P1': .25, 'P2': .17, 'P3': .14,
             'P4': None, 'P5': None, 'P6': None},
            {'ATR': '6.2', 'P1': .16, 'P2': .15, 'P3': .13,
             'P4': .11, 'P5': .10, 'P6': .12},
        ])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'ofertas.json'
            for semana in (1, 8):
                guardar_version_oferta(
                    'Peninsular 12 meses',
                    date(2026, 9, semana),
                    date(2026, 9, semana + 6),
                    tarifas,
                    ruta,
                )

            catalogo = cargar_catalogo_ofertas(ruta)
            tabla = catalogo_a_dataframe(catalogo)
            self.assertEqual(len(catalogo), 2)
            self.assertEqual(set(tabla['ATR']), {'2.0', '6.2'})
            self.assertEqual(len(tabla), 4)

    def test_admite_vigencia_sin_fecha_fin(self):
        tarifas = pd.DataFrame([{
            'ATR': '3.0',
            **{f'P{i}': 0.10 + i / 100 for i in range(1, 7)},
        }])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'ofertas.json'
            registro = guardar_version_oferta(
                'Oferta abierta', date(2026, 9, 4), None, tarifas, ruta
            )

            self.assertIsNone(registro['vigencia_hasta'])
            self.assertIsNone(cargar_catalogo_ofertas(ruta)[0]['vigencia_hasta'])

    def test_20_no_exige_p4_p5_p6_al_guardar(self):
        tarifas = pd.DataFrame([{
            'ATR': '2.0 TD',
            'P1': .25, 'P2': .17, 'P3': .14,
            'P4': None, 'P5': None, 'P6': None,
        }])

        salida = normalizar_tarifas_oferta(tarifas)

        self.assertEqual(salida.loc[0, 'ATR'], '2.0')
        self.assertTrue(salida.loc[0, ['P4', 'P5', 'P6']].isna().all())

    def test_30_si_exige_p4_p5_p6_al_guardar(self):
        tarifas = pd.DataFrame([{
            'ATR': '3.0',
            'P1': .25, 'P2': .17, 'P3': .14,
            'P4': None, 'P5': None, 'P6': None,
        }])

        with self.assertRaisesRegex(ValueError, r'3\.0TD: P4, P5, P6'):
            normalizar_tarifas_oferta(tarifas)

    def test_elimina_la_version_completa_con_todos_sus_atr(self):
        tarifas = pd.DataFrame([
            {
                'ATR': '2.0', 'P1': .25, 'P2': .17, 'P3': .14,
                'P4': None, 'P5': None, 'P6': None,
            },
            {
                'ATR': '3.0',
                **{f'P{i}': .10 + i / 100 for i in range(1, 7)},
            },
        ])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'ofertas.json'
            guardada = guardar_version_oferta(
                'Oferta eliminable', date(2026, 9, 10), None, tarifas, ruta
            )

            eliminados = eliminar_versiones_oferta([guardada['id']], ruta)

            self.assertEqual(eliminados, [guardada['id']])
            self.assertEqual(cargar_catalogo_ofertas(ruta), [])

if __name__ == '__main__':
    unittest.main()
