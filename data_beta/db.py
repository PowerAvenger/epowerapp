from __future__ import annotations

import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / ".local_data" / "epower_beta.sqlite3"


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE import_batches (
            id INTEGER PRIMARY KEY,
            source_system TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            row_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(source_system, entity_type, source_sha256)
        );

        CREATE TABLE legacy_records (
            id INTEGER PRIMARY KEY,
            batch_id INTEGER NOT NULL REFERENCES import_batches(id),
            source_key TEXT NOT NULL,
            row_number INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            UNIQUE(batch_id, source_key)
        );

        CREATE TABLE titulares (
            id INTEGER PRIMARY KEY,
            legacy_excel_id INTEGER UNIQUE,
            nombre_legal TEXT NOT NULL,
            nif TEXT,
            grupo_empresarial TEXT,
            direccion_facturacion_1 TEXT,
            direccion_facturacion_2 TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE suministros (
            id INTEGER PRIMARY KEY,
            cups20 TEXT NOT NULL UNIQUE,
            cups_original TEXT NOT NULL,
            denominacion TEXT,
            direccion_1 TEXT,
            direccion_2 TEXT,
            codigo_postal TEXT,
            municipio TEXT,
            provincia TEXT,
            distribuidora TEXT,
            codigo_distribuidora TEXT,
            atr TEXT,
            tipo_punto_medida INTEGER CHECK (
                tipo_punto_medida IS NULL OR tipo_punto_medida BETWEEN 1 AND 5
            ),
            proveedor_curva_actual TEXT,
            tg_legacy TEXT,
            referencia_contrato_acceso TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE titularidades_suministro (
            id INTEGER PRIMARY KEY,
            suministro_id INTEGER NOT NULL REFERENCES suministros(id),
            titular_id INTEGER NOT NULL REFERENCES titulares(id),
            vigente_desde TEXT,
            vigente_hasta TEXT,
            estado_fecha TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (estado_fecha IN ('pendiente', 'inferida', 'confirmada')),
            origen TEXT NOT NULL,
            legacy_id_cups INTEGER,
            observaciones TEXT,
            UNIQUE(suministro_id, titular_id)
        );

        CREATE TABLE filas_contrato_origen (
            id INTEGER PRIMARY KEY,
            source_system TEXT NOT NULL,
            legacy_record_id INTEGER NOT NULL REFERENCES legacy_records(id),
            legacy_contract_id TEXT,
            suministro_id INTEGER REFERENCES suministros(id),
            titular_id INTEGER REFERENCES titulares(id),
            comercializadora TEXT,
            referencia_comercializadora TEXT,
            referencia_acceso TEXT,
            tarifa TEXT,
            fecha_inicio TEXT,
            fecha_fin TEXT,
            fecha_inicio_condiciones TEXT,
            fecha_fin_condiciones TEXT,
            tipo_precio TEXT,
            proveedor_curva_legacy TEXT,
            UNIQUE(source_system, legacy_contract_id, legacy_record_id)
        );

        CREATE INDEX idx_titularidades_suministro
            ON titularidades_suministro(suministro_id, vigente_desde, vigente_hasta);
        CREATE INDEX idx_filas_contrato_cups
            ON filas_contrato_origen(suministro_id, fecha_inicio, fecha_fin);
        """,
    ),
    (
        2,
        """
        UPDATE suministros
        SET proveedor_curva_actual = 'AXON', updated_at = CURRENT_TIMESTAMP
        WHERE id IN (
            SELECT DISTINCT suministro_id
            FROM filas_contrato_origen
            WHERE source_system = 'EXCEL' AND suministro_id IS NOT NULL
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE legacy_exclusions (
            id INTEGER PRIMARY KEY,
            source_system TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            source_key TEXT NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_system, entity_type, source_key)
        );

        INSERT INTO legacy_exclusions(
            source_system, entity_type, source_key, reason
        ) VALUES (
            'EXCEL', 'titular', '12',
            'Excluido expresamente de la BBDD beta por el usuario'
        );

        DELETE FROM titularidades_suministro
        WHERE titular_id IN (
            SELECT id FROM titulares WHERE legacy_excel_id = 12
        );

        DELETE FROM titulares
        WHERE legacy_excel_id = 12
          AND NOT EXISTS (
              SELECT 1 FROM filas_contrato_origen
              WHERE titular_id = titulares.id
          );
        """,
    ),
    (
        4,
        """
        CREATE TABLE contratos (
            id INTEGER PRIMARY KEY,
            suministro_id INTEGER NOT NULL REFERENCES suministros(id),
            titular_id INTEGER REFERENCES titulares(id),
            comercializadora TEXT NOT NULL,
            referencia_comercializadora TEXT,
            referencia_acceso TEXT,
            tarifa TEXT,
            vigente_desde TEXT,
            vigente_hasta TEXT,
            estado_fecha TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (estado_fecha IN ('pendiente', 'inferida', 'confirmada')),
            origen TEXT NOT NULL,
            observaciones TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(suministro_id, comercializadora, referencia_comercializadora)
        );

        -- En el Excel legacy estas columnas representan la vigencia de las
        -- condiciones de la fila, no la duración comercial del contrato.
        UPDATE filas_contrato_origen
        SET
            fecha_inicio_condiciones = fecha_inicio,
            fecha_fin_condiciones = fecha_fin,
            fecha_inicio = NULL,
            fecha_fin = NULL
        WHERE source_system = 'EXCEL';

        CREATE INDEX idx_contratos_vigencia
            ON contratos(suministro_id, vigente_desde, vigente_hasta);
        """,
    ),
    (
        5,
        """
        ALTER TABLE contratos ADD COLUMN ultima_renovacion TEXT;
        ALTER TABLE contratos ADD COLUMN proxima_renovacion TEXT;
        """,
    ),
    (
        6,
        """
        ALTER TABLE filas_contrato_origen ADD COLUMN contrato_id INTEGER
            REFERENCES contratos(id);

        UPDATE filas_contrato_origen AS f
        SET contrato_id = (
            SELECT c.id
            FROM contratos c
            WHERE c.suministro_id = f.suministro_id
              AND (c.titular_id IS NULL OR c.titular_id = f.titular_id)
              AND UPPER(c.comercializadora) = UPPER(f.comercializadora)
              AND (
                    c.vigente_desde IS NULL
                    OR f.fecha_inicio_condiciones IS NULL
                    OR f.fecha_inicio_condiciones >= c.vigente_desde
              )
              AND (
                    c.vigente_hasta IS NULL
                    OR f.fecha_inicio_condiciones IS NULL
                    OR f.fecha_inicio_condiciones <= c.vigente_hasta
              )
            ORDER BY c.vigente_desde DESC, c.id DESC
            LIMIT 1
        )
        WHERE f.source_system = 'EXCEL';

        CREATE INDEX idx_filas_condicion_contrato
            ON filas_contrato_origen(contrato_id, fecha_inicio_condiciones);
        """,
    ),
    (
        7,
        """
        CREATE TABLE costes_extra_contractuales (
            id INTEGER PRIMARY KEY,
            suministro_id INTEGER NOT NULL REFERENCES suministros(id),
            mes TEXT NOT NULL,
            concepto TEXT NOT NULL DEFAULT 'REGULARIZACION SSAA',
            cantidad_factura_kwh REAL,
            precio_unitario_eur_kwh REAL,
            importe_eur REAL NOT NULL,
            referencia TEXT,
            observaciones TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(suministro_id, mes, concepto)
        );

        CREATE INDEX idx_costes_extra_suministro_mes
            ON costes_extra_contractuales(suministro_id, mes);
        """,
    ),
)


class ClosingConnection(sqlite3.Connection):
    """Conexion transaccional que tambien libera el fichero al salir del with."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(path: str | Path = DEFAULT_DB_PATH) -> Path:
    db_path = Path(path)
    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (version,)
            )
    return db_path
