import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from backend_informa import (
    _fusionar_captura_anterior,
    normalizar_filtros_informa,
    parsear_tarjeta_informa,
    validar_captura_informa,
)


TARJETA_20 = """0

CYE Energía | PRECIO FIJO | E11 PT4

Residencial y pyme - Fijo
CONTRATAR
OFERTA PDF
COMISIONES

Potencia (€/kWdía)

P1: 0.086861
P2: 0.012946

Energía (€/kWh)

P1: 0.292257
P2: 0.210983
P3: 0.193206

Comisión energía (€/mWh):

4.223999938964844

Comisión potencia (€):

1.5360000610351563

MÁS INFORMACIÓN

válida hasta el 2026-10-10"""


class InformaParserTest(unittest.TestCase):
    def test_30_restringe_captura_a_pyme_fijo(self):
        filtros = normalizar_filtros_informa(
            "3.0 TD", "Indexado", "Residencial"
        )

        self.assertEqual(filtros, ("3.0 TD", "Fijo", "PYME"))

    def test_61_restringe_captura_a_pyme_fijo(self):
        filtros = normalizar_filtros_informa(
            "6.1 TD", "Indexado", "Residencial y Pyme"
        )

        self.assertEqual(filtros, ("6.1 TD", "Fijo", "PYME"))

    def test_parsea_tarjeta_20_visible(self):
        oferta = parsear_tarjeta_informa(TARJETA_20, "2.0 TD")

        self.assertEqual(oferta["indice_web"], 0)
        self.assertEqual(oferta["atr"], "2.0")
        self.assertEqual(oferta["vigencia_hasta"], "2026-10-10")
        self.assertEqual(oferta["energia"]["P3"], 0.193206)
        self.assertEqual(oferta["potencia"]["P2"], 0.012946)
        self.assertAlmostEqual(oferta["comision_energia_eur_mwh"], 4.223999938964844)
        self.assertAlmostEqual(oferta["comision_potencia_eur"], 1.5360000610351563)

    def test_rechaza_periodos_incompletos(self):
        with self.assertRaisesRegex(ValueError, "Periodos incompletos"):
            parsear_tarjeta_informa(TARJETA_20.replace("P3: 0.193206", ""), "2.0")

    def test_admite_oferta_sin_fecha_fin(self):
        tarjeta = TARJETA_20.replace("válida hasta el 2026-10-10", "")
        oferta = parsear_tarjeta_informa(tarjeta, "2.0 TD")

        self.assertIsNone(oferta["vigencia_hasta"])
        self.assertEqual(oferta["nombre"], "CYE Energía | PRECIO FIJO | E11 PT4")

    def test_valida_secuencia_completa_desde_cero(self):
        segunda = TARJETA_20.replace(
            "0\n\nCYE Energía", "1\n\nCYE Energía", 1
        )
        ofertas = validar_captura_informa([TARJETA_20, segunda], "2.0 TD")

        self.assertEqual([oferta["indice_web"] for oferta in ofertas], [0, 1])

    def test_rechaza_huecos_en_indices(self):
        tercera = TARJETA_20.replace(
            "0\n\nCYE Energía", "2\n\nCYE Energía", 1
        )
        with self.assertRaisesRegex(ValueError, "Faltan los índices: 1"):
            validar_captura_informa([TARJETA_20, tercera], "2.0 TD")

    def test_fusiona_el_cero_previo_con_la_captura_uno_en_adelante(self):
        segunda = TARJETA_20.replace(
            "0\n\nCYE Energía", "1\n\nCYE Energía", 1
        )
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "diagnostico.json"
            ruta.write_text(json.dumps({
                "navegacion": {
                    "familia_atr": "2.0 TD",
                    "contrato": "Fijo",
                    "segmento": "Residencial y Pyme",
                },
                "tarjetas": [TARJETA_20],
            }), encoding="utf-8")
            with patch("backend_informa.RUTA_DATOS_DIAGNOSTICO", ruta):
                fusionadas = _fusionar_captura_anterior(
                    [segunda], "2.0 TD", "Fijo", "Residencial y Pyme"
                )

        self.assertEqual(
            [int(texto.lstrip().splitlines()[0]) for texto in fusionadas],
            [0, 1],
        )

    def test_no_fusiona_capturas_de_filtros_distintos(self):
        segunda = TARJETA_20.replace(
            "0\n\nCYE Energía", "1\n\nCYE Energía", 1
        )
        with tempfile.TemporaryDirectory() as directorio:
            ruta = Path(directorio) / "diagnostico.json"
            ruta.write_text(json.dumps({
                "navegacion": {
                    "familia_atr": "2.0 TD",
                    "contrato": "Fijo",
                    "segmento": "Residencial",
                },
                "tarjetas": [TARJETA_20],
            }), encoding="utf-8")
            with patch("backend_informa.RUTA_DATOS_DIAGNOSTICO", ruta):
                fusionadas = _fusionar_captura_anterior(
                    [segunda], "2.0 TD", "Fijo", "Residencial y Pyme"
                )

        self.assertEqual(len(fusionadas), 1)
        self.assertTrue(fusionadas[0].lstrip().startswith("1"))


if __name__ == "__main__":
    unittest.main()
