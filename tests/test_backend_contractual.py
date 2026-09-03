import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from backend_contractual import (
    aplicar_condiciones_contractuales,
    aplicar_costes_extra_mensuales,
    cargar_costes_extra_cups,
    guardar_costes_extra_cups,
    preparar_indexado_contractual,
    resumir_calculo_contractual,
)
from data_beta.db import connect, initialize_database


def _curva_prueba():
    curva = pd.DataFrame({
        "fecha_hora": pd.to_datetime(["2025-09-30 23:00", "2025-10-01 00:00"]),
        "periodo": ["P6", "P1"],
        "consumo_neto_kWh": [10.0, 10.0],
        "spot": [50.0, 50.0],
        "ssaa": [10.0, 10.0],
        "osom": [1.0, 1.0],
        "fnee": [0.0, 0.0],
        "ppcc_2.0": [1.0, 1.0],
        "ppcc_3.0": [1.0, 1.0],
        "ppcc_6.1": [1.0, 1.0],
        "perd_2.0": [0.0, 0.0],
        "perd_3.0": [0.0, 0.0],
        "perd_6.1": [0.0, 0.0],
        "pyc_2.0": [0.0, 0.0],
        "pyc_3.0": [0.0, 0.0],
        "pyc_6.1": [0.0, 0.0],
    })
    curva["fecha"] = curva["fecha_hora"].dt.date
    return curva


def _condiciones_prueba():
    indexado = {
        "INDEX CG": "1,300", "CG F": "2", "INDEX DESVIOS": "0,000",
        "FNEE F": "4", "C FINAN %": "",
    }
    fijo = {f"TE P{i}": "0,156013" for i in range(1, 7)}
    return pd.DataFrame([
        {
            "condicion_id": 55, "inicio_condicion": pd.Timestamp("2025-01-01"),
            "fin_condicion": pd.Timestamp("2025-09-30"),
            "tipo_precio": "INDEX PT", "payload_json": json.dumps(indexado),
        },
        {
            "condicion_id": 44, "inicio_condicion": pd.Timestamp("2025-10-01"),
            "fin_condicion": pd.Timestamp("2025-12-31"),
            "tipo_precio": "FIJO", "payload_json": json.dumps(fijo),
        },
    ])


class CalculoContractualTest(unittest.TestCase):
    def _calcular(self, curva=None, condiciones=None):
        curva = _curva_prueba() if curva is None else curva
        condiciones = _condiciones_prueba() if condiciones is None else condiciones
        precios = preparar_indexado_contractual(curva, condiciones, "6.1")
        return aplicar_condiciones_contractuales(precios, condiciones, "6.1")

    def test_aplica_mix_indexado_fijo_en_fecha_exacta(self):
        resultado = self._calcular()

        self.assertEqual(
            resultado["tipo_precio_contrato"].tolist(), ["INDEXADO", "FIJO"]
        )
        self.assertAlmostEqual(resultado.loc[0, "precio_contrato_eur_mwh"], 64.2495)
        self.assertAlmostEqual(resultado.loc[1, "precio_fijo_te_eur_mwh"], 156.013)
        self.assertAlmostEqual(resultado.loc[1, "coste_total"], 1.56013)
        self.assertIn(
            "sin regularizacion SSAA", resultado.loc[1, "formula_contrato"]
        )

    def test_resumen_conserva_separados_tipo_y_condicion(self):
        resultado = self._calcular()
        resumen = resumir_calculo_contractual(resultado)

        self.assertEqual(len(resumen), 2)
        self.assertEqual(
            set(resumen["tipo_precio_contrato"]), {"INDEXADO", "FIJO"}
        )
        self.assertAlmostEqual(resumen["Consumo_kWh"].sum(), 20.0)

    def test_rechaza_horas_sin_condicion(self):
        condiciones = _condiciones_prueba().iloc[[1]].copy()
        with self.assertRaisesRegex(ValueError, "No hay condicion contractual"):
            self._calcular(condiciones=condiciones)

    def test_hora_sin_intervalo_de_mercado_no_recalcula_indexado(self):
        curva = _curva_prueba()
        curva["precio_indexado_contrato_eur_mwh"] = [None, None]
        curva["formula_indexada_contrato"] = ["Telemindex", None]
        resultado = aplicar_condiciones_contractuales(
            curva, _condiciones_prueba(), "6.1"
        )
        self.assertTrue(pd.isna(resultado.loc[0, "coste_total"]))
        self.assertEqual(
            resultado.loc[0, "estado_precio_horario"],
            "SIN INTERVALO DE MERCADO",
        )

    def test_coste_extra_mensual_conserva_coste_inicial(self):
        resultado = self._calcular()
        extras = pd.DataFrame({"Mes": ["2025-10"], "Importe_EUR": [100.0]})
        ajustado = aplicar_costes_extra_mensuales(resultado, extras)
        octubre = ajustado[ajustado["fecha_hora"].dt.month.eq(10)]
        self.assertAlmostEqual(octubre["coste_extra_mensual_asignado"].sum(), 100.0)
        self.assertAlmostEqual(
            octubre["coste_total"].sum(),
            octubre["coste_total_inicial"].sum() + 100.0,
        )

    def test_rechaza_solape_para_corregirlo_en_base_de_datos(self):
        condiciones = _condiciones_prueba()
        revision = condiciones.iloc[[1]].copy()
        revision["condicion_id"] = 99
        revision["inicio_condicion"] = pd.Timestamp("2025-10-01")
        revision["fin_condicion"] = pd.Timestamp("2025-12-31")
        payload = {f"TE P{i}": "0,200000" for i in range(1, 7)}
        revision["payload_json"] = json.dumps(payload)
        condiciones.loc[1, "inicio_condicion"] = pd.Timestamp("2025-09-01")
        condiciones = pd.concat([condiciones, revision], ignore_index=True).sort_values(
            "inicio_condicion"
        )
        precios = preparar_indexado_contractual(
            _curva_prueba(), condiciones, "6.1"
        )
        with self.assertRaisesRegex(ValueError, "solapadas"):
            aplicar_condiciones_contractuales(precios, condiciones, "6.1")

    def test_guardado_unico_persistente_por_cups_y_mes(self):
        with tempfile.TemporaryDirectory() as temporal:
            db_path = Path(temporal) / "prueba.sqlite3"
            initialize_database(db_path)
            with connect(db_path) as connection:
                connection.execute(
                    "INSERT INTO suministros(cups20, cups_original) VALUES (?, ?)",
                    ("ES0022000009064699LH", "ES0022000009064699LH"),
                )
            filas = pd.DataFrame({
                "Mes": ["2025-10", "2025-11"],
                "Concepto": ["REGULARIZACION SSAA"] * 2,
                "Cantidad_kWh": [552540.0, 526174.0],
                "Precio_unitario_EUR_kWh": [0.00355976, 0.00203719],
                "Importe_EUR": [1966.91, 1071.92],
                "Referencia": ["4T25", "4T25"],
                "Observaciones": ["", ""],
            })
            guardadas, _ = guardar_costes_extra_cups(
                "ES0022000009064699LH", filas, db_path
            )
            recuperadas = cargar_costes_extra_cups(
                "ES0022000009064699LH", db_path
            )
            self.assertEqual(guardadas, 2)
            self.assertEqual(len(recuperadas), 2)
            self.assertAlmostEqual(recuperadas["Importe_EUR"].sum(), 3038.83)


if __name__ == "__main__":
    unittest.main()
