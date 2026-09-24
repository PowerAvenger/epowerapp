import unittest
from textwrap import dedent

from backend_factura import analizar_factura


class AdxTest(unittest.TestCase):
    def test_extrae_factura_con_dos_tramos(self):
        texto = dedent("""
        Factura de ELECTRICIDAD comercializada por ADX Renovables, S.L.
        CUPS: ES0031405931051001XT0F
        Factura núm: 260046933 Fecha factura:08-04-2026
        Periodo de facturación: Del 28-02-2026 al 31-03-2026
        Tarifa de Acceso: 30TD
        Ref. contrato de suministro: 0011220
        Fecha fin de contrato: 25-03-2027
        Potencia(s): 5 kW; 6 kW; 6 kW; 6 kW; 6 kW; 17,32 kW
        Término de Potencia P1
        5 kW x 6 días x 0,057197€ 1,72 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Término de Potencia P1
        5 kW x 25 días x 0,057198€ 7,15 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P2
        6 kW x 25 días x 0,031828€ 4,77 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P2
        6 kW x 6 días x 0,031829€ 1,15 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Término de Potencia P3
        6 kW x 25 días x 0,015017€ 2,25 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P3
        6 kW x 6 días x 0,015018€ 0,54 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Término de Potencia P4
        6 kW x 6 días x 0,013387€ 0,48 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Término de Potencia P4
        6 kW x 25 días x 0,013386€ 2,01 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P5
        6 kW x 25 días x 0,009626€ 1,44 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P5
        6 kW x 6 días x 0,009627€ 0,35 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Término de Potencia P6
        17,321 kW x 25 días x 0,008061€ 3,49 €
        (Período comprendido Del 28/02/2026 al 25/03/2026)
        Término de Potencia P6
        17,321 kW x 6 días x 0,008061€ 0,84 €
        (Período comprendido Del 26/03/2026 al 31/03/2026)
        Exceso de potencia 14,79 €
        Término Energía P2
        98,02 kWh x 0,109977€ 10,78 €
        Término Energía P2
        487,98 kWh x 0,157393€ 76,80 €
        Término Energía P3
        78,30 kWh x 0,080332€ 6,29 €
        Término Energía P3
        393,70 kWh x 0,130734€ 51,47 €
        Término Energía P6
        828,61 kWh x 0,104441€ 86,54 €
        Término Energía P6
        205,39 kWh x 0,062953€ 12,93 €
        Energía Reactiva P2
        214 h. kvar x 0,041554€/kVArh 8,89 €
        Energía Reactiva P3
        182 h. kvar x 0,041554€/kVArh 7,56 €
        Financiación Bono Social según TED/733/2022
        31 días x 0,019121€ /día 0,59 €
        P1 7.641 7.641 0 3.480 3.480 0 0
        P2 12.301 11.715 586 4.975 4.568 407 10
        P3 8.190 7.718 472 3.599 3.261 338 10
        P4 7.188 7.188 0 3.550 3.550 0 0
        P5 3.637 3.637 0 1.467 1.467 0 0
        P6 32.356 31.322 1.034 18.169 17.351 818 9
        Impuesto sobre la electricidad
        2,09 x 1 2,09 €
        Alquiler de equipos 11,01 €
        Coste financiero 3,48 €
        Base Imponible 319,41 €
        Impuesto IVA 21,00% 67,08 €
        TOTAL FACTURA 386,49 €
        Razón Social: HIELO VITAL SL
        CIF/NIF Titular:B66484742
        """)

        factura = analizar_factura(texto)

        self.assertEqual(factura.formato, "adx")
        self.assertEqual(factura.numero_factura, "260046933")
        self.assertEqual(factura.cups, "ES0031405931051001XT0F")
        self.assertEqual(factura.numero_contrato, "0011220")
        self.assertEqual(factura.atr, "3.0TD")
        self.assertEqual(factura.periodo_inicio, "01/03/2026")
        self.assertEqual(factura.potencia, 26.19)
        self.assertEqual(factura.energia, 244.81)
        self.assertEqual(factura.excesos_potencia, 14.79)
        self.assertEqual(factura.reactiva, 16.45)
        self.assertEqual(factura.iee, 2.09)
        self.assertEqual(factura.iva, 67.08)
        self.assertEqual(factura.total_otros, 15.08)
        self.assertEqual(factura.total, 386.49)
        self.assertEqual(factura.suma_componentes, 386.49)
        self.assertEqual(factura.consumo_total_kwh, 2092.0)
        self.assertEqual(len(factura.potencia_periodos), 12)
        self.assertEqual(len(factura.energia_periodos), 3)
        self.assertEqual(len(factura.maximetros), 6)
        self.assertEqual(factura.verificacion_fbs.estado, "🟢")
        self.assertEqual(factura.verificacion_iee.estado, "🟢")
        self.assertEqual(factura.verificacion_iva.estado, "🟢")
        self.assertTrue(factura.reconstruccion_total_completa)
        self.assertEqual(factura.advertencias, [])


if __name__ == "__main__":
    unittest.main()
