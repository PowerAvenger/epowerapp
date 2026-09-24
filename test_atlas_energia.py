import unittest
from textwrap import dedent

from backend_factura import analizar_factura


class AtlasEnergiaTest(unittest.TestCase):
    def test_extrae_factura_indexada_6_1td(self):
        texto = dedent("""
        Número de factura FE26022183 Periodo de facturación 01/06/2026 a 30/06/2026
        Fecha Emisión 13/07/2026 Importe total 4.970,85 €
        Nº de 62252 CUPS ES0031408685935001SM0F
        contrato
        Titular PHIRA COMPONENTES AUTOMOCION, SA suministro OLIVA)
        A08622938 Tarifa de acceso 6.1TD
        Potencia P1: 145,000 P2: 145,000 P3: 145,000 P4: 145,000 P5: 145,000
        (kW) P6: 263,000
        Importe por potencia contratada de los cuales...
        P1 01/06/2026 30/06/2026 145,000 30 0,081083 352,71 285,39 67,32
        P2 01/06/2026 30/06/2026 145,000 30 0,042506 184,90 151,21 33,69
        P3 01/06/2026 30/06/2026 145,000 30 0,018635 81,06 56,58 24,48
        P4 01/06/2026 30/06/2026 145,000 30 0,014778 64,28 39,81 24,47
        P5 01/06/2026 30/06/2026 145,000 30 0,005822 25,33 0,85 24,48
        P6 01/06/2026 30/06/2026 263,000 30 0,002751 21,71 1,36 20,35
        Importe por energía consumida
        P3 01/06/2026 30/06/2026 13.404,000 0,103673 1.389,63 68,80 104,49
        P4 01/06/2026 30/06/2026 6.427,000 0,102826 660,86 17,87 25,05
        P6 01/06/2026 30/06/2026 9.608,000 0,113040 1.086,09 0,28 14,98
        Importe por exceso de potencia
        P3 3,000 0,680379 2,04 0,00 0,00
        Otros
        Obligación financiación Bono Social 30,00 0,019121 € 0,57 €
        Alquiler contador 30 1,372274 € 41,17
        Impuesto especial sobre la electricidad (5,11269632 %) 3.868,61 197,79
        IVA 21% 4.108,14 862,71
        Importe total
        4.970,85 €
        Información del consumo eléctrico
        ACTIVA (kWh) Lectura actual (Real) 30/06/2026 1 1 1 1 1 1
        Consumo 0 0 13.404 6.408 37 9.613
        INDUCTIVA (kVArh) Lectura actual (Real) 30/06/2026 1 1 1 1 1 1
        Consumo 0 0 1.218 1.400 425 1.074
        CAPACITIVA (kVArh)
        Del periodo facturado 0,000 0,000 148,000 144,000 0,000 128,000
        MAXÍMETRO (kW)
        hola@atlas-energia.com
        """)

        factura = analizar_factura(texto)

        self.assertEqual(factura.formato, "atlas_energia")
        self.assertEqual(factura.numero_factura, "FE26022183")
        self.assertEqual(factura.cups, "ES0031408685935001SM0F")
        self.assertEqual(factura.numero_contrato, "62252")
        self.assertEqual(factura.tipo_suministro, "Tipo 3")
        self.assertEqual(factura.potencia, 729.99)
        self.assertEqual(factura.energia, 3136.58)
        self.assertEqual(factura.excesos_potencia, 2.04)
        self.assertEqual(factura.iee, 197.79)
        self.assertEqual(factura.iva, 862.71)
        self.assertEqual(factura.total, 4970.85)
        self.assertEqual(factura.consumo_total_kwh, 29439.0)
        self.assertEqual(factura.suma_componentes, 4970.85)
        self.assertEqual(len(factura.potencia_periodos), 6)
        self.assertEqual(len(factura.potencias_contratadas), 6)
        self.assertEqual(len(factura.energia_periodos), 3)
        self.assertEqual(factura.maximetros[2].potencia_kw, 148.0)
        self.assertEqual(factura.verificacion_iee.estado, "🟢")
        self.assertEqual(factura.verificacion_iva.estado, "🟢")
        self.assertEqual(factura.advertencias, [])


if __name__ == "__main__":
    unittest.main()
