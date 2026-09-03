from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from .db import DEFAULT_DB_PATH, connect, initialize_database


def clean(value: object) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def cups20(value: object) -> str:
    cups = "".join(str(value or "").upper().split())
    if len(cups) < 20:
        raise ValueError(f"CUPS no valido: {value!r}")
    return cups[:20]


def iso_date(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Fecha no reconocida: {text!r}")


def read_tsv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _start_batch(
    connection: sqlite3.Connection,
    path: Path,
    source_system: str,
    entity_type: str,
    row_count: int,
) -> tuple[int, bool]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    existing = connection.execute(
        """
        SELECT id FROM import_batches
        WHERE source_system = ? AND entity_type = ? AND source_sha256 = ?
        """,
        (source_system, entity_type, digest),
    ).fetchone()
    if existing:
        return int(existing["id"]), False
    cursor = connection.execute(
        """
        INSERT INTO import_batches(
            source_system, entity_type, source_name, source_sha256, row_count
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (source_system, entity_type, path.name, digest, row_count),
    )
    return int(cursor.lastrowid), True


def _legacy_record(
    connection: sqlite3.Connection,
    batch_id: int,
    source_key: str,
    row_number: int,
    row: dict[str, str],
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO legacy_records(batch_id, source_key, row_number, payload_json)
        VALUES (?, ?, ?, ?)
        """,
        (batch_id, source_key, row_number, json.dumps(row, ensure_ascii=False)),
    )
    return int(cursor.lastrowid)


def _upsert_titular(
    connection: sqlite3.Connection,
    legacy_id: object,
    nombre: object,
    nif: object = None,
    direccion_1: object = None,
    direccion_2: object = None,
) -> int:
    legacy = int(str(legacy_id).strip()) if clean(legacy_id) else None
    name = clean(nombre)
    if not name:
        raise ValueError("El titular no tiene nombre")
    if legacy is not None:
        existing = connection.execute(
            "SELECT id FROM titulares WHERE legacy_excel_id = ?", (legacy,)
        ).fetchone()
    else:
        existing = connection.execute(
            "SELECT id FROM titulares WHERE nombre_legal = ? AND nif IS ?",
            (name, clean(nif)),
        ).fetchone()
    if existing:
        connection.execute(
            """
            UPDATE titulares SET
                nombre_legal = ?,
                nif = COALESCE(?, nif),
                direccion_facturacion_1 = COALESCE(?, direccion_facturacion_1),
                direccion_facturacion_2 = COALESCE(?, direccion_facturacion_2),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, clean(nif), clean(direccion_1), clean(direccion_2), existing["id"]),
        )
        return int(existing["id"])
    cursor = connection.execute(
        """
        INSERT INTO titulares(
            legacy_excel_id, nombre_legal, nif,
            direccion_facturacion_1, direccion_facturacion_2
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (legacy, name, clean(nif), clean(direccion_1), clean(direccion_2)),
    )
    return int(cursor.lastrowid)


def _is_excluded(
    connection: sqlite3.Connection,
    source_system: str,
    entity_type: str,
    source_key: object,
) -> bool:
    return connection.execute(
        """
        SELECT 1 FROM legacy_exclusions
        WHERE source_system = ? AND entity_type = ? AND source_key = ?
        """,
        (source_system, entity_type, str(source_key).strip()),
    ).fetchone() is not None


def _upsert_suministro(connection: sqlite3.Connection, row: dict[str, str]) -> int:
    original = clean(row.get("CUPS") or row.get("cups"))
    canonical = cups20(original)
    existing = connection.execute(
        "SELECT id FROM suministros WHERE cups20 = ?", (canonical,)
    ).fetchone()
    values = {
        "cups_original": original,
        "denominacion": clean(row.get("DENOMINACION") or row.get("denominacion")),
        "direccion_1": clean(row.get("DIRECCION_SUMINISTRO_1") or row.get("address")),
        "direccion_2": clean(row.get("DIRECCION_SUMINISTRO_2")),
        "codigo_postal": clean(row.get("postalCode")),
        "municipio": clean(row.get("municipality")),
        "provincia": clean(row.get("province")),
        "distribuidora": clean(row.get("DISTRIBUIDORA") or row.get("distributor")),
        "codigo_distribuidora": clean(row.get("distributorCode")),
        "atr": clean(row.get("ATR") or row.get("atr")),
        "tipo_punto_medida": clean(row.get("TPM") or row.get("pointType")),
        "tg_legacy": clean(row.get("TG")),
        "referencia_contrato_acceso": clean(row.get("REF_CONTRATO_ACCESO")),
    }
    tpm = int(values["tipo_punto_medida"]) if values["tipo_punto_medida"] else None
    if existing:
        connection.execute(
            """
            UPDATE suministros SET
                cups_original = COALESCE(?, cups_original),
                denominacion = COALESCE(?, denominacion),
                direccion_1 = COALESCE(?, direccion_1),
                direccion_2 = COALESCE(?, direccion_2),
                codigo_postal = COALESCE(?, codigo_postal),
                municipio = COALESCE(?, municipio),
                provincia = COALESCE(?, provincia),
                distribuidora = COALESCE(?, distribuidora),
                codigo_distribuidora = COALESCE(?, codigo_distribuidora),
                atr = COALESCE(?, atr),
                tipo_punto_medida = COALESCE(?, tipo_punto_medida),
                tg_legacy = COALESCE(?, tg_legacy),
                referencia_contrato_acceso = COALESCE(?, referencia_contrato_acceso),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                values["cups_original"], values["denominacion"], values["direccion_1"],
                values["direccion_2"], values["codigo_postal"], values["municipio"],
                values["provincia"], values["distribuidora"],
                values["codigo_distribuidora"], values["atr"], tpm,
                values["tg_legacy"], values["referencia_contrato_acceso"], existing["id"],
            ),
        )
        return int(existing["id"])
    cursor = connection.execute(
        """
        INSERT INTO suministros(
            cups20, cups_original, denominacion, direccion_1, direccion_2,
            codigo_postal, municipio, provincia, distribuidora,
            codigo_distribuidora, atr, tipo_punto_medida, proveedor_curva_actual,
            tg_legacy, referencia_contrato_acceso
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            canonical, values["cups_original"], values["denominacion"],
            values["direccion_1"], values["direccion_2"], values["codigo_postal"],
            values["municipio"], values["provincia"], values["distribuidora"],
            values["codigo_distribuidora"], values["atr"], tpm,
            "AXON" if row.get("ID_CUPS") else None,
            values["tg_legacy"], values["referencia_contrato_acceso"],
        ),
    )
    return int(cursor.lastrowid)


def import_excel_supplies(path: str | Path, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    path = Path(path)
    rows = read_tsv(path)
    initialize_database(db_path)
    with connect(db_path) as connection:
        batch_id, is_new = _start_batch(connection, path, "EXCEL", "suministros", len(rows))
        if not is_new:
            return {"rows": len(rows), "imported": 0, "reused_batch": 1}
        for number, row in enumerate(rows, start=2):
            _legacy_record(connection, batch_id, row["ID_CUPS"], number, row)
            if _is_excluded(
                connection, "EXCEL", "titular", row.get("ID_TITULAR_CONTRATO")
            ):
                _upsert_suministro(connection, row)
                continue
            titular_id = _upsert_titular(
                connection,
                row.get("ID_TITULAR_CONTRATO"),
                row.get("TITULAR_CONTRATO"),
            )
            suministro_id = _upsert_suministro(connection, row)
            connection.execute(
                """
                INSERT INTO titularidades_suministro(
                    suministro_id, titular_id, estado_fecha, origen,
                    legacy_id_cups, observaciones
                ) VALUES (?, ?, 'pendiente', 'EXCEL', ?, ?)
                ON CONFLICT(suministro_id, titular_id) DO UPDATE SET
                    legacy_id_cups = excluded.legacy_id_cups
                """,
                (
                    suministro_id,
                    titular_id,
                    int(row["ID_CUPS"]),
                    "Cambio real de titularidad; fechas pendientes de confirmar",
                ),
            )
    return {"rows": len(rows), "imported": len(rows), "reused_batch": 0}


def import_datadis_supplies(path: str | Path, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    path = Path(path)
    rows = read_tsv(path)
    initialize_database(db_path)
    with connect(db_path) as connection:
        batch_id, is_new = _start_batch(connection, path, "SVA_DATADIS", "suministros", len(rows))
        if not is_new:
            return {"rows": len(rows), "imported": 0, "reused_batch": 1}
        for number, row in enumerate(rows, start=2):
            canonical = cups20(row.get("cups"))
            _legacy_record(connection, batch_id, canonical, number, row)
            _upsert_suministro(connection, row)
    return {"rows": len(rows), "imported": len(rows), "reused_batch": 0}


def _insert_contract_rows(
    connection: sqlite3.Connection,
    rows: Iterable[dict[str, str]],
    batch_id: int,
    source_system: str,
) -> int:
    count = 0
    for number, row in enumerate(rows, start=2):
        if source_system == "EXCEL":
            source_key = clean(row.get("ID_CONTRATO")) or str(number)
            holder_id = _upsert_titular(
                connection,
                row.get("ID_TITULAR_CONTRATO"),
                row.get("TITULAR CONT."),
                row.get("NIF"),
                row.get("DIR. FACT. 1"),
                row.get("DIR. FACT. 2"),
            )
            supply_id = _upsert_suministro(connection, row)
            connection.execute(
                """
                UPDATE suministros
                SET proveedor_curva_actual = 'AXON', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (supply_id,),
            )
            start = None
            end = None
            conditions_start = iso_date(row.get("Fecha inicio contrato"))
            conditions_end = iso_date(row.get("Fecha final contrato"))
            marketer = clean(row.get("COMER"))
            commercial_ref = clean(row.get("REF. CONT"))
            access_ref = clean(row.get("REF. CONT. ACC"))
            tariff = clean(row.get("TARIFA"))
            price_type = clean(row.get("PRECIO E"))
            curve_provider = clean(row.get("TG"))
        else:
            source_key = str(number - 1)
            holder_id = None
            supply_id = _upsert_suministro(connection, row)
            start = iso_date(row.get("ini_contrato"))
            end = iso_date(row.get("fin_contrato"))
            conditions_start = iso_date(row.get("ini_cond"))
            conditions_end = iso_date(row.get("fin_cond"))
            marketer = clean(row.get("comercializadora"))
            commercial_ref = clean(row.get("num_contrato"))
            access_ref = None
            tariff = clean(row.get("atr"))
            price_type = clean(row.get("tipo"))
            curve_provider = None
        legacy_id = _legacy_record(connection, batch_id, source_key, number, row)
        connection.execute(
            """
            INSERT INTO filas_contrato_origen(
                source_system, legacy_record_id, legacy_contract_id,
                suministro_id, titular_id, comercializadora,
                referencia_comercializadora, referencia_acceso, tarifa,
                fecha_inicio, fecha_fin, fecha_inicio_condiciones,
                fecha_fin_condiciones, tipo_precio, proveedor_curva_legacy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_system, legacy_id, source_key, supply_id, holder_id,
                marketer, commercial_ref, access_ref, tariff, start, end,
                conditions_start, conditions_end, price_type, curve_provider,
            ),
        )
        count += 1
    return count


def import_contracts(
    path: str | Path,
    source_system: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    if source_system not in {"EXCEL", "SVA"}:
        raise ValueError("source_system debe ser EXCEL o SVA")
    path = Path(path)
    rows = read_tsv(path)
    initialize_database(db_path)
    with connect(db_path) as connection:
        batch_id, is_new = _start_batch(
            connection, path, source_system, "contratos", len(rows)
        )
        if not is_new:
            return {"rows": len(rows), "imported": 0, "reused_batch": 1}
        imported = _insert_contract_rows(connection, rows, batch_id, source_system)
    return {"rows": len(rows), "imported": imported, "reused_batch": 0}


def import_confirmed_contracts(
    path: str | Path,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Importa contratos comerciales confirmados sin mezclar sus condiciones."""
    path = Path(path)
    rows = read_tsv(path)
    initialize_database(db_path)
    with connect(db_path) as connection:
        batch_id, is_new = _start_batch(
            connection, path, "USER_CONFIRMED", "contratos", len(rows)
        )
        if not is_new:
            return {"rows": len(rows), "imported": 0, "reused_batch": 1}
        for number, row in enumerate(rows, start=2):
            canonical = cups20(row.get("CUPS"))
            supply = connection.execute(
                "SELECT id FROM suministros WHERE cups20 = ?", (canonical,)
            ).fetchone()
            if not supply:
                raise ValueError(f"No existe el suministro {canonical}")
            if clean(row.get("DENOMINACION")):
                connection.execute(
                    """
                    UPDATE suministros
                    SET denominacion = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (clean(row.get("DENOMINACION")), supply["id"]),
                )
            holder = connection.execute(
                "SELECT id FROM titulares WHERE legacy_excel_id = ?",
                (int(row["ID_TITULAR_CONTRATO"]),),
            ).fetchone()
            if not holder:
                raise ValueError(
                    f"No existe el titular Excel {row['ID_TITULAR_CONTRATO']}"
                )
            source_key = clean(row.get("REF. CONT.")) or f"{canonical}:{number}"
            _legacy_record(connection, batch_id, source_key, number, row)
            existing_current = connection.execute(
                """
                SELECT id FROM contratos
                WHERE suministro_id = ? AND comercializadora = ?
                ORDER BY id
                """,
                (supply["id"], clean(row.get("COMER"))),
            ).fetchall()
            date_status = (
                "confirmada" if iso_date(row.get("INICIO_CONTRATO")) else "pendiente"
            )
            if len(existing_current) == 1:
                connection.execute(
                    """
                    UPDATE contratos SET
                        titular_id = ?, referencia_comercializadora = ?,
                        referencia_acceso = COALESCE(?, referencia_acceso),
                        tarifa = COALESCE(?, tarifa), vigente_desde = ?,
                        vigente_hasta = ?, ultima_renovacion = ?,
                        proxima_renovacion = ?, estado_fecha = ?,
                        origen = 'USER_CONFIRMED', observaciones = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        holder["id"], clean(row.get("REF. CONT.")),
                        clean(row.get("REF. CONT. ACC.")), clean(row.get("TARIFA")),
                        iso_date(row.get("INICIO_CONTRATO")),
                        iso_date(row.get("FIN_CONTRATO")),
                        iso_date(row.get("ULTIMA_RENOVACION")),
                        iso_date(row.get("PROXIMA_RENOVACION")), date_status,
                        clean(row.get("OBSERVACIONES")), existing_current[0]["id"],
                    ),
                )
                continue
            connection.execute(
                """
                INSERT INTO contratos(
                    suministro_id, titular_id, comercializadora,
                    referencia_comercializadora, referencia_acceso, tarifa,
                    vigente_desde, vigente_hasta, ultima_renovacion,
                    proxima_renovacion, estado_fecha, origen, observaciones
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          'USER_CONFIRMED', ?)
                ON CONFLICT(
                    suministro_id, comercializadora, referencia_comercializadora
                ) DO UPDATE SET
                    titular_id = excluded.titular_id,
                    referencia_acceso = excluded.referencia_acceso,
                    tarifa = excluded.tarifa,
                    vigente_desde = excluded.vigente_desde,
                    vigente_hasta = excluded.vigente_hasta,
                    ultima_renovacion = excluded.ultima_renovacion,
                    proxima_renovacion = excluded.proxima_renovacion,
                    estado_fecha = 'confirmada',
                    observaciones = excluded.observaciones,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    supply["id"], holder["id"], clean(row.get("COMER")),
                    clean(row.get("REF. CONT.")), clean(row.get("REF. CONT. ACC.")),
                    clean(row.get("TARIFA")), iso_date(row.get("INICIO_CONTRATO")),
                    iso_date(row.get("FIN_CONTRATO")),
                    iso_date(row.get("ULTIMA_RENOVACION")),
                    iso_date(row.get("PROXIMA_RENOVACION")),
                    date_status,
                    clean(row.get("OBSERVACIONES")),
                ),
            )
    return {"rows": len(rows), "imported": len(rows), "reused_batch": 0}


def link_contract_conditions(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Relaciona cada fila Excel con el contrato comercial que la contiene."""
    initialize_database(db_path)
    with connect(db_path) as connection:
        result = connection.execute(
            """
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
            WHERE f.source_system = 'EXCEL'
            """
        )
    return result.rowcount


def infer_holder_periods_from_excel_contracts(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Propone cambios de titular sin convertirlos en fechas confirmadas."""
    changed = 0
    with connect(db_path) as connection:
        supplies = connection.execute(
            """
            SELECT suministro_id
            FROM titularidades_suministro
            GROUP BY suministro_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for supply in supplies:
            starts = connection.execute(
                """
                SELECT
                    titular_id,
                    MIN(COALESCE(fecha_inicio, fecha_inicio_condiciones)) AS first_start
                FROM filas_contrato_origen
                WHERE source_system = 'EXCEL'
                  AND suministro_id = ?
                  AND titular_id IS NOT NULL
                  AND COALESCE(fecha_inicio, fecha_inicio_condiciones) IS NOT NULL
                GROUP BY titular_id
                ORDER BY first_start
                """,
                (supply["suministro_id"],),
            ).fetchall()
            if not starts:
                continue
            for index, item in enumerate(starts):
                end = None
                if index + 1 < len(starts):
                    next_start = datetime.fromisoformat(starts[index + 1]["first_start"]).date()
                    end = (next_start - timedelta(days=1)).isoformat()
                result = connection.execute(
                    """
                    UPDATE titularidades_suministro
                    SET vigente_desde = ?, vigente_hasta = ?, estado_fecha = 'inferida'
                    WHERE suministro_id = ? AND titular_id = ?
                    """,
                    (
                        item["first_start"], end,
                        supply["suministro_id"], item["titular_id"],
                    ),
                )
                changed += result.rowcount
    return changed
