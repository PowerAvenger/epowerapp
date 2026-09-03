import json
import unittest

import pandas as pd

from backend_contractual import (
    aplicar_costes_extra_mensuales,
    condicion_como_referencia,
    condicion_manual_como_referencia,
)
from backend_indexado import FormulaIndexada


class TestCondicionReferencia(unittest.TestCase):
    def test_extiende_condicion_sin_modificar_original(self):
        original = pd.Series({
            "condicion_id": 47,
            "inicio_condicion": pd.Timestamp("2025-03-26"),
            "fin_condicion": pd.Timestamp("2025-09-30"),
            "tipo_precio": "INDEX PT",
            "payload_json": '{"INDEX CG": "1,300", "CG F": "2"}',
        })
        referencia = condicion_como_referencia(
            original, "2025-10-01", "2026-03-31"
        )
        self.assertEqual(referencia.iloc[0]["condicion_id"], -1)
        self.assertEqual(original["fin_condicion"], pd.Timestamp("2025-09-30"))

    def test_formula_manual_genera_payload_contractual(self):
        formula = FormulaIndexada(margen=1.3, margen_pos="tm")
        referencia = condicion_manual_como_referencia(
            "INDEXADO", "2025-10-01", "2025-12-31", formula=formula
        )
        payload = json.loads(referencia.iloc[0]["payload_json"])
        self.assertEqual(payload["INDEX CG"], 1.3)
        self.assertEqual(payload["CG F"], "2")

    def test_extra_parcial_usa_consumo_del_mes_completo(self):
        curva = pd.DataFrame({
            "fecha_hora": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "consumo_neto_kWh": [10.0, 10.0],
            "coste_total": [1.0, 1.0],
            "tipo_precio_contrato": ["FIJO", "FIJO"],
        })
        extras = pd.DataFrame({"Mes": ["2026-01"], "Importe_EUR": [100.0]})
        resultado = aplicar_costes_extra_mensuales(
            curva, extras, consumos_mensuales_base={"2026-01": 100.0}
        )
        self.assertAlmostEqual(resultado["coste_extra_mensual_asignado"].sum(), 20.0)


if __name__ == "__main__":
    unittest.main()
