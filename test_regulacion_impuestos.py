import unittest
from datetime import date

from backend_factura import (
    FacturaLeida,
    PotenciaContratadaPeriodo,
    _verificar_impuestos,
)
from regulacion_iee import TIPO_GENERAL_IEE, obtener_referencia_iee
from regulacion_iva import obtener_referencia_iva


class RegulacionImpuestos2026Test(unittest.TestCase):
    def test_iee_reducido_termina_el_31_de_mayo(self):
        self.assertEqual(
            obtener_referencia_iee(date(2026, 5, 31), "2.0TD").tipo_pct,
            0.5,
        )
        self.assertEqual(
            obtener_referencia_iee(date(2026, 6, 1), "2.0TD").tipo_pct,
            TIPO_GENERAL_IEE,
        )

    def test_iee_general_sigue_disponible_despues_de_julio(self):
        self.assertEqual(
            obtener_referencia_iee(date(2026, 8, 1), "2.0TD").tipo_pct,
            TIPO_GENERAL_IEE,
        )

    def test_iva_reducido_solo_en_tramo_efectivo_y_hasta_10_kw(self):
        self.assertEqual(
            obtener_referencia_iva(date(2026, 5, 31), [4.6, 4.6]).tipo_pct,
            10.0,
        )
        self.assertEqual(
            obtener_referencia_iva(date(2026, 6, 1), [4.6, 4.6]).tipo_pct,
            21.0,
        )
        self.assertEqual(
            obtener_referencia_iva(date(2026, 5, 1), [15.0, 15.0]).tipo_pct,
            21.0,
        )

    def test_verifica_fila_iva_visalia_con_tipo_repetido(self):
        factura = FacturaLeida(
            formato="visalia_domesticos",
            comercializadora="Visalia",
            fecha_factura="11/08/2026",
            iva=18.27,
            potencias_contratadas=[
                PotenciaContratadaPeriodo("P1", 4.6),
                PotenciaContratadaPeriodo("P2", 4.6),
            ],
        )

        _verificar_impuestos(factura, "IVA 21 % 87,00 € 21 % 18,27 €")

        self.assertIsNotNone(factura.verificacion_iva)
        self.assertEqual(factura.verificacion_iva.estado, "🟢")
        self.assertEqual(factura.verificacion_iva.tipo_regulado_pct, 21.0)
        self.assertEqual(factura.verificacion_iva.importe_regulado_eur, 18.27)


if __name__ == "__main__":
    unittest.main()
