import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from data_beta.contract_editor import (
    actualizar_condicion,
    crear_condicion_desde_anterior,
    numero_contractual,
)
from data_beta.db import connect, initialize_database


class TestContractEditor(unittest.TestCase):
    def test_numero_contractual_admite_formato_espanol(self):
        self.assertEqual(numero_contractual("1250,00"), 1250.0)
        self.assertEqual(numero_contractual("1.250,00"), 1250.0)
        self.assertEqual(numero_contractual("1250.00"), 1250.0)

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Path(self.tempdir.name) / "test.sqlite3"
        initialize_database(self.db)
        with connect(self.db) as connection:
            lote = connection.execute(
                """INSERT INTO import_batches(
                    source_system, entity_type, source_name, source_sha256, row_count
                ) VALUES ('TEST', 'condicion', 'test', 'test', 1)"""
            ).lastrowid
            registro = connection.execute(
                """INSERT INTO legacy_records(
                    batch_id, source_key, row_number, payload_json
                ) VALUES (?, '308', 1, ?)""",
                (lote, json.dumps({
                    "P1": 100, "P2": 100, "P1 REF": "95,00",
                    "TP P1": 0.1, "TE P1": 0.2,
                })),
            ).lastrowid
            suministro = connection.execute(
                """INSERT INTO suministros(cups20, cups_original)
                VALUES ('ES0021000007417788PD', 'ES0021000007417788PD')"""
            ).lastrowid
            contrato = connection.execute(
                """INSERT INTO contratos(
                    suministro_id, comercializadora, origen
                ) VALUES (?, 'TEST', 'TEST')""",
                (suministro,),
            ).lastrowid
            self.condicion = connection.execute(
                """INSERT INTO filas_contrato_origen(
                    source_system, legacy_record_id, legacy_contract_id,
                    suministro_id, comercializadora, fecha_inicio_condiciones,
                    tipo_precio, contrato_id
                ) VALUES ('TEST', ?, '308', ?, 'TEST', '2026-01-01', 'FIJO', ?)""",
                (registro, suministro, contrato),
            ).lastrowid

    def tearDown(self):
        self.tempdir.cleanup()

    def test_edita_fin_y_registra_auditoria(self):
        actualizar_condicion(
            self.condicion, date(2026, 1, 1), date(2026, 7, 31),
            {f"P{i}": 100 + i for i in range(1, 7)}, "Completar fin", self.db,
        )
        with connect(self.db) as connection:
            fila = connection.execute(
                "SELECT fecha_fin_condiciones FROM filas_contrato_origen WHERE id = ?",
                (self.condicion,),
            ).fetchone()
            cambios = connection.execute(
                "SELECT COUNT(*) FROM cambios_condiciones_contractuales"
            ).fetchone()[0]
        self.assertEqual(fila[0], "2026-07-31")
        self.assertEqual(cambios, 1)

    def test_nueva_condicion_copia_precios_y_cierra_anterior(self):
        nueva = crear_condicion_desde_anterior(
            self.condicion, date(2026, 8, 1), None,
            {f"P{i}": 80 + i for i in range(1, 7)},
            "Aplicación RDL 7/2026", True, self.db,
        )
        with connect(self.db) as connection:
            anterior = connection.execute(
                "SELECT fecha_fin_condiciones FROM filas_contrato_origen WHERE id = ?",
                (self.condicion,),
            ).fetchone()
            payload = json.loads(connection.execute(
                """SELECT l.payload_json FROM filas_contrato_origen f
                JOIN legacy_records l ON l.id = f.legacy_record_id WHERE f.id = ?""",
                (nueva,),
            ).fetchone()[0])
        self.assertEqual(anterior[0], "2026-07-31")
        self.assertEqual(payload["P1"], 81.0)
        self.assertEqual(payload["P1 REF"], "95,00")
        self.assertEqual(payload["TP P1"], 0.1)
        self.assertEqual(payload["TE P1"], 0.2)


if __name__ == "__main__":
    unittest.main()
