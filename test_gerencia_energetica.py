import unittest
from textwrap import dedent

from backend_factura import analizar_factura


class GerenciaEnergeticaTest(unittest.TestCase):
    def test_extrae_factura_indexada_6_1td(self):
        texto = dedent("""
        Gerencia Energética SL
        admin@genergetica.com
        Factura Nº C26-0001356 de fecha 12/09/2026
        Período facturado: 31/07/2026 - 31/08/2026 - 31 días
        Importe Total: 5.435,72 €
        Información de Consumos lectura anterior: 31/07/2026; lectura actual: 31/08/2026; última lectura: real
        Energía activa (kWh) 0,0 0,0 7820,0 4898,0 0,0 7266,0 19984,0
        Reactiva inductiva (kVArh) 0,0 0,0 3476,0 1968,0 0,0 1359,0 6803,0
        Máximetro (kW) 0,0 0,0 0,0 0,0 0,0 0,0 0,0
        Referencia Contrato: h505R9RCFzd-001 Código Unificado (CUPS): ES0022000005430144MS1P
        Fecha de Renovación: 29/01/2027
        Peaje de Acceso: 6.1TD
        Potencias Contratadas (kW):
        P1: 90,00; P2: 90,00; P3: 90,00; P4: 90,00; P5: 90,00; P6: 90,00
        Potencia facturada
        P1 90,000 kW x 0,081083 €/kW-día x 31 días 226,22 €
        P2 90,000 kW x 0,042506 €/kW-día x 31 días 118,59 €
        P3 90,000 kW x 0,018636 €/kW-día x 31 días 51,99 €
        P4 90,000 kW x 0,014778 €/kW-día x 31 días 41,23 €
        P5 90,000 kW x 0,005822 €/kW-día x 31 días 16,24 €
        P6 90,000 kW x 0,002751 €/kW-día x 31 días 7,68 €
        Energía facturada
        P3 7.820,0 kWh x 0,012928 €/kWh 101,10 €
        P4 4.898,0 kWh x 0,006678 €/kWh 32,71 €
        P6 7.266,0 kWh x 0,001588 €/kWh 11,54 €
        Reactiva P3 895,4 kVArh x 0,041554 €/kVArh 37,21 €
        Reactiva P4 351,7 kVArh x 0,041554 €/kVArh 14,61 €
        POOL (ii) 19.984,0 kWh x 0,122079 €/kWh x (1 + 0,064427) 2.596,80 €
        COPS (ii) 19.984,0 kWh x 0,033923 €/kWh x (1 + 0,064427) 721,59 €
        MDC (iii) 19.984,0 kWh x 0,015000 €/kWh 299,76 €
        Compensación Energía -8,29 €
        Financiación Bono Social (v) 31 días x 0,019103 €/día 0,59 €
        Impuesto de electricidad
        5,11269632% s/4.269,57 € 218,29 €
        Alquiler equipo de medida 0,144194 €/día x 31 días 4,47 €
        Impuesto Valor Añadido (IVA)
        21,00% s/4.492,33 € 943,39 €
        Total importe de factura 5.435,72 €
        """)

        factura = analizar_factura(texto)

        self.assertEqual(factura.formato, "gerencia_energetica")
        self.assertEqual(factura.numero_factura, "C26-0001356")
        self.assertEqual(factura.cups, "ES0022000005430144MS1P")
        self.assertEqual(factura.numero_contrato, "h505R9RCFzd-001")
        self.assertEqual(factura.fecha_vencimiento_contrato, "29/01/2027")
        self.assertEqual(factura.periodo_inicio, "01/08/2026")
        self.assertEqual(factura.periodo_consumo_inicio, "01/08/2026")
        self.assertEqual(factura.periodo_consumo_fin, "31/08/2026")
        self.assertEqual(factura.potencia, 461.95)
        self.assertEqual(factura.energia, 3763.50)
        self.assertEqual(factura.reactiva, 51.82)
        self.assertEqual(factura.iee, 218.29)
        self.assertEqual(factura.iva, 943.39)
        self.assertEqual(factura.total, 5435.72)
        self.assertEqual(factura.consumo_total_kwh, 19984.0)
        self.assertEqual(factura.suma_componentes, 5435.72)
        self.assertEqual(len(factura.potencia_periodos), 6)
        self.assertEqual(len(factura.energia_periodos), 6)
        self.assertEqual(len(factura.reactiva_periodos), 6)
        self.assertEqual(factura.verificacion_iee.estado, "🟢")
        self.assertEqual(factura.verificacion_iva.estado, "🟢")
        self.assertEqual(factura.advertencias, [])


if __name__ == "__main__":
    unittest.main()
