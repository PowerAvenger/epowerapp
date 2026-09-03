import unittest

from formato_es import formato_euros_con_signo, formato_pct_con_signo


class FormatoSignosTest(unittest.TestCase):
    def test_euros_con_signo_solo_antepone_mas_a_positivos(self):
        self.assertEqual(formato_euros_con_signo(12.345), "+12,35 €")
        self.assertEqual(formato_euros_con_signo(-12.345), "-12,35 €")
        self.assertEqual(formato_euros_con_signo(0), "0,00 €")

    def test_porcentaje_con_signo_y_dos_decimales(self):
        self.assertEqual(formato_pct_con_signo(1.2, 2), "+1,20 %")
        self.assertEqual(formato_pct_con_signo(-1.2, 2), "-1,20 %")
        self.assertEqual(formato_pct_con_signo(0, 2), "0,00 %")


if __name__ == "__main__":
    unittest.main()
