import unittest

from backend_factura import (
    EnergiaPeriodo,
    _extraer_energia_endesa_empresas,
    _extraer_maximetros_endesa_empresas,
    _extraer_reactiva_endesa_empresas,
)


TEXTO_ENDESA = """
Consumo P3 7.812,000 kWh x 0,039503 Eur/kWh 308,60 €
Consumo P4 6.106,000 kWh x 0,030047 Eur/kWh 183,47 €
Consumo P6 10.230,000 kWh x 0,025349 Eur/kWh 259,32 €
Energia precio indexado P3 7.812,000 kWh x 0,08648690 Eur/kWh 675,64 €
Energia precio indexado P4 6.106,000 kWh x 0,07620620 Eur/kWh 465,32 €
Energia precio indexado P6 10.230,000 kWh x 0,07865590 Eur/kWh 804,65 €
ENERGÍA REACTIVA INDUCTIVA kWh
real real P1 0 0,00 0,041
P2 0 0,00 0,041
ENERGÍA ACTIVA kWh P3 2.799 0,94 221,040
P11.18.1 0,000 0,000 1,00 0,000 0,000 P4 2.379 0,93 364,020
P41.18.4 0,000 0,000 1,006.106,000 6.106,000 P6 0 1,00 364,020
EXCESOS DE POTENCIA
Periodo horario Contratada Máxima AC K
P1 70,000 0,000
P2 70,000 0,000
P3 70,000 0,000
P4 70,000 0,000
P5 80,000 0,000
P6 100,000 0,000
"""


class TestEndesaEmpresas(unittest.TestCase):
    def test_combina_componentes_de_energia(self):
        energia = _extraer_energia_endesa_empresas(TEXTO_ENDESA)
        self.assertEqual([x.periodo for x in energia], ["P3", "P4", "P6"])
        self.assertAlmostEqual(sum(x.consumo_kwh for x in energia), 24148.0)
        self.assertAlmostEqual(sum(x.coste_eur for x in energia), 2697.0)

    def test_lee_reactiva_y_excluye_p6(self):
        energia = _extraer_energia_endesa_empresas(TEXTO_ENDESA)
        reactiva = _extraer_reactiva_endesa_empresas(TEXTO_ENDESA, energia, 24.31)
        self.assertEqual([x.periodo for x in reactiva], ["P3", "P4"])
        self.assertAlmostEqual(sum(x.exceso_facturado_kvarh for x in reactiva), 585.06)
        self.assertAlmostEqual(sum(x.coste_facturado_eur for x in reactiva), 24.31)

    def test_lee_seis_maximetros_aunque_sean_cero(self):
        maximetros = _extraer_maximetros_endesa_empresas(TEXTO_ENDESA)
        self.assertEqual(len(maximetros), 6)
        self.assertTrue(all(x.potencia_kw == 0 for x in maximetros))


if __name__ == "__main__":
    unittest.main()
