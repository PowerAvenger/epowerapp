import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from backend_ofertas_fijas import (
    cargar_catalogo_ofertas,
    catalogo_a_dataframe,
    copiar_oferta_con_horquilla_ssaa,
    eliminar_versiones_oferta,
    ofertas_catalogo_para_atr,
    guardar_version_oferta,
    normalizar_tarifas_oferta,
    periodos_aplicables_atr,
    periodos_potencia_atr,
    precios_energia_oferta,
)


class CatalogoOfertasFijasTest(unittest.TestCase):
    def test_periodos_energia_y_potencia_20_son_distintos(self):
        self.assertEqual(
            periodos_aplicables_atr('2.0TD'), ['P1', 'P2', 'P3']
        )
        self.assertEqual(periodos_potencia_atr('2.0TD'), ['P1', 'P2'])

    def test_copia_temporal_aplica_exceso_ssaa_apuntado(self):
        oferta = pd.Series({
            "oferta": "Base", "P1": .10, "P2": .20,
            "P3": .30, "P4": pd.NA, "P5": pd.NA, "P6": pd.NA,
        })

        curva = pd.DataFrame({
            "fecha": ["2026-01-01", "2026-02-01"],
            "ssaa": [20.0, 10.0],
            "consumo_neto_kWh": [10_000, 10_000],
            "coste_ssaa": [220.0, 100.0],
            "perd_2.0": [0.10, 0.10],
        })
        copia, detalle = copiar_oferta_con_horquilla_ssaa(
            oferta, "Base con riesgo", 16.77, curva,
            columna_perdidas="perd_2.0",
        )

        self.assertAlmostEqual(detalle["ajuste_eur_mwh"], 1.98346225)
        self.assertAlmostEqual(detalle["sobrecoste_eur"], 39.669245)
        self.assertAlmostEqual(copia.loc[0, "P1"], .10198346225)
        mensual = detalle["detalle_mensual"]
        self.assertAlmostEqual(mensual.loc[0, "Sobrecoste (€)"], 39.669245)
        self.assertAlmostEqual(mensual.loc[1, "Sobrecoste (€)"], 0.0)
        self.assertAlmostEqual(mensual.loc[0, "Diferencial (€/MWh)"], 3.23)
        self.assertAlmostEqual(mensual.loc[1, "Diferencial (€/MWh)"], 0.0)
        self.assertAlmostEqual(mensual.loc[0, "Pérdidas (%)"], 10.0)
        self.assertTrue(pd.isna(copia.loc[0, "P4"]))

    def test_aplica_fee_sin_alterar_los_precios_base(self):
        oferta = pd.Series({
            "P1": .10, "P2": .20, "Fee (€/MWh)": 10,
        })

        precios = precios_energia_oferta(oferta)

        self.assertAlmostEqual(precios["P1"], .11)
        self.assertAlmostEqual(precios["P2"], .21)
        self.assertAlmostEqual(oferta["P1"], .10)

    def test_proyecta_catalogo_normalizando_el_atr(self):
        catalogo = [{
            "id": "v1",
            "nombre": "Oferta común",
            "vigencia_desde": "2026-09-01",
            "vigencia_hasta": "2026-09-30",
            "tarifas": [{
                "atr": "2.0", "P1": .2, "P2": .15, "P3": .1,
                "P4": None, "P5": None, "P6": None,
            }],
        }]

        salida = ofertas_catalogo_para_atr(catalogo, "2.0 TD")

        self.assertEqual(salida.loc[0, "ID oferta"], "v1")
        self.assertEqual(salida.loc[0, "oferta"], "Oferta común")

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
