import unittest
from datetime import date

from backend_factura import (
    EnergiaPeriodo,
    FacturaLeida,
    PotenciaContratadaPeriodo,
    _aplicar_referencia_iee,
    _crear_verificacion_impuesto,
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

    def test_iee_usa_fecha_emision_y_no_fin_periodo(self):
        factura = FacturaLeida(
            formato="naturgy",
            comercializadora="Naturgy",
            fecha_factura="05/06/2026",
            periodo_fin="31/05/2026",
            atr="6.1TD",
            iee=51.13,
            energia_periodos=[
                EnergiaPeriodo("P1", 10_000, 0.1, 1_000)
            ],
        )
        verificacion = _crear_verificacion_impuesto(
            "1000", "5,11269632", "51,13", factura.iee, "IEE"
        )

        resultado = _aplicar_referencia_iee(factura, verificacion)

        self.assertEqual(resultado.tipo_regulado_pct, TIPO_GENERAL_IEE)
        self.assertEqual(resultado.importe_regulado_eur, 51.13)
        self.assertEqual(resultado.estado, "🟢")

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
