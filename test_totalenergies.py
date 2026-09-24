import unittest
from textwrap import dedent

from backend_factura import analizar_factura


class TotalEnergiesTest(unittest.TestCase):
    def test_extrae_variante_felec_con_periodo_de_facturacion(self):
        texto = dedent("""
        TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA, S.A.U.
        Nº Factura FELEC2600591897
        Fecha emisión factura: 8 de septiembre de 2026
        Periodo de facturación: De 01/08/2026 al 31/08/2026
        Código unificado de punto de suministro(CUPS): ES0021000008990252CD
        Referencia del contrato de suministro (TOTALENERGIES ELECTRICIDAD Y GAS ESPAÑA, S.A.): 397288
        Peaje de acceso: 3.0TD
        Término Potencia Tarifa Acceso
        P1 50,000 kW x 31 Días x 0,04091804 €/kW día 63,42 €
        Término Potencia
        P1 50,000 kW x 31 Días x 0,001753 €/kW día 2,72 €
        Término Cargos Potencia Acceso
        P1 50,000 kW x 31 Días x 0,01490916 €/kW día 23,11 €
        Término Energía Tarifa Acceso
        P1 2016,00 kWh x 0,02751100 €/kWh 55,46 €
        Término Cargos Energía Acceso
        P1 2016 kWh x 0,03584100 €/kWh 72,26 €
        Término Energía Variable
        P1 2016 kWh x 0,149251 €/kWh 300,89 €
        Información de consumo eléctrico
        Fecha 31/05/2026 31/08/2026 REAL 31/05/2026 31/08/2026 REAL
        P1 49.530 51.546 2.016 17.294 18.313 1.019 0,00 0,00 0,00
        P2 92.062 93.540 1.478 33.145 33.850 705 0,00 0,00 0,00
        P3 58.988 62.320 3.332 23.237 24.707 1.470 0,00 20,17 0,00
        P4 45.148 47.642 2.494 16.578 17.679 1.101 0,00 16,28 0,00
        P5 38.042 38.042 0 13.978 13.978 0 0,00 0,00 0,00
        P6 160.616 170.172 9.556 55.681 59.893 4.212 0,00 18,07 0,00
        Detalle de la factura
        Término Reactiva Distribuidora
        Término Reactiva Distribuidora 50,67 €
        Impuesto Electricidad
        5,1 % sobre 3.394,42 € 173,55 €
        Impuesto IVA 21% sobre 3.574,11 € 750,56 €
        TOTAL IMPORTE FACTURA 4.324,67 €
        """)

        factura = analizar_factura(texto)

        self.assertEqual(factura.formato, "totalenergies")
        self.assertEqual(factura.numero_factura, "FELEC2600591897")
        self.assertEqual(factura.fecha_factura, "08/09/2026")
        self.assertEqual(factura.periodo_inicio, "01/08/2026")
        self.assertEqual(factura.periodo_fin, "31/08/2026")
        self.assertEqual(factura.periodo_consumo_inicio, "01/06/2026")
        self.assertEqual(factura.periodo_consumo_fin, "31/08/2026")
        self.assertEqual(factura.cups, "ES0021000008990252CD")
        self.assertEqual(factura.numero_contrato, "397288")
        self.assertEqual(factura.iee, 173.55)
        self.assertEqual(factura.iva, 750.56)
        self.assertIsNotNone(factura.verificacion_iva)
        self.assertEqual(factura.verificacion_iva.base_eur, 3574.11)
        self.assertEqual(factura.verificacion_iva.tipo_pct, 21.0)
        self.assertEqual(
            factura.verificacion_iva.importe_facturado_eur, 750.56
        )
        self.assertEqual(factura.total, 4324.67)
        self.assertEqual(factura.potencia, 89.25)
        self.assertEqual(factura.energia, 428.61)
        self.assertEqual(factura.reactiva, 50.67)
        self.assertEqual(
            [item.potencia_kw for item in factura.maximetros],
            [0.0, 0.0, 20.17, 16.28, 0.0, 18.07],
        )
        self.assertEqual(
            [item.energia_reactiva_kvarh for item in factura.reactiva_periodos],
            [1019.0, 705.0, 1470.0, 1101.0, 0.0, 4212.0],
        )
        self.assertFalse(any(
            concepto.concepto == "Cargos regulados"
            for concepto in factura.otros
        ))


if __name__ == "__main__":
    unittest.main()
