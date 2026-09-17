from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from .db import DEFAULT_DB_PATH, connect, initialize_database


PERIODOS = tuple(f"P{i}" for i in range(1, 7))


def _fecha_iso(valor: date | str | None) -> str | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor.isoformat()
    return date.fromisoformat(str(valor)).isoformat()


def numero_contractual(valor) -> float:
    """Convierte números del legado en formato español o internacional."""
    if valor is None or str(valor).strip() == "":
        return 0.0
    texto = str(valor).strip().replace(" ", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def cargar_condicion_edicion(
    condicion_id: int, db_path: str | Path = DEFAULT_DB_PATH,
) -> dict:
    initialize_database(db_path)
    with connect(db_path) as connection:
        fila = connection.execute(
            """
            SELECT f.*, l.payload_json
            FROM filas_contrato_origen f
            JOIN legacy_records l ON l.id = f.legacy_record_id
            WHERE f.id = ?
            """,
            (int(condicion_id),),
        ).fetchone()
    if fila is None:
        raise ValueError("La condición seleccionada ya no existe.")
    salida = dict(fila)
    salida["payload"] = json.loads(salida.pop("payload_json") or "{}")
    return salida


def actualizar_condicion(
    condicion_id: int,
    inicio,
    fin,
    potencias: dict[str, float],
    motivo: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    potencias_referencia: dict[str, float] | None = None,
    tipo_precio: str | None = None,
    precios_energia: dict[str, float] | None = None,
) -> None:
    anterior = cargar_condicion_edicion(condicion_id, db_path)
    inicio_iso, fin_iso = _fecha_iso(inicio), _fecha_iso(fin)
    if not inicio_iso:
        raise ValueError("La condición debe tener fecha de inicio.")
    if fin_iso and fin_iso < inicio_iso:
        raise ValueError("La fecha final no puede ser anterior a la inicial.")
    payload = dict(anterior["payload"])
    payload.update({
        periodo: numero_contractual(potencias.get(periodo))
        for periodo in PERIODOS
    })
    if potencias_referencia is not None:
        payload.update({
            f"{periodo} REF": numero_contractual(
                potencias_referencia.get(periodo)
            )
            for periodo in PERIODOS
        })
    tipo_precio_nuevo = str(
        tipo_precio or anterior.get("tipo_precio") or ""
    ).strip().upper()
    if tipo_precio_nuevo not in {"FIJO", "INDEX PT"}:
        raise ValueError("El tipo de precio debe ser FIJO o INDEX PT.")
    if precios_energia is not None:
        payload.update({
            f"TE {periodo}": numero_contractual(
                precios_energia.get(periodo)
            )
            for periodo in PERIODOS
        })
    if tipo_precio_nuevo == "FIJO" and not any(
        numero_contractual(payload.get(f"TE {periodo}")) > 0
        for periodo in PERIODOS
    ):
        raise ValueError(
            "Una condición FIJO debe tener al menos un precio TE positivo."
        )
    nuevos = {
        "inicio": inicio_iso, "fin": fin_iso,
        "tipo_precio": tipo_precio_nuevo,
        "potencias": {periodo: payload[periodo] for periodo in PERIODOS},
        "potencias_referencia": {
            periodo: payload.get(f"{periodo} REF") for periodo in PERIODOS
        },
    }
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE filas_contrato_origen
            SET fecha_inicio_condiciones = ?, fecha_fin_condiciones = ?,
                tipo_precio = ?
            WHERE id = ?
            """,
            (inicio_iso, fin_iso, tipo_precio_nuevo, int(condicion_id)),
        )
        connection.execute(
            "UPDATE legacy_records SET payload_json = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), anterior["legacy_record_id"]),
        )
        connection.execute(
            """
            INSERT INTO cambios_condiciones_contractuales(
                condicion_id, contrato_id, accion, datos_anteriores_json,
                datos_nuevos_json, motivo
            ) VALUES (?, ?, 'ACTUALIZAR', ?, ?, ?)
            """,
            (
                int(condicion_id), anterior["contrato_id"],
                json.dumps(anterior, ensure_ascii=False, default=str),
                json.dumps(nuevos, ensure_ascii=False), motivo.strip() or None,
            ),
        )


def crear_condicion_desde_anterior(
    condicion_origen_id: int,
    inicio,
    fin,
    potencias: dict[str, float],
    motivo: str,
    cerrar_anterior: bool = True,
    db_path: str | Path = DEFAULT_DB_PATH,
    potencias_referencia: dict[str, float] | None = None,
) -> int:
    origen = cargar_condicion_edicion(condicion_origen_id, db_path)
    inicio_iso, fin_iso = _fecha_iso(inicio), _fecha_iso(fin)
    if not inicio_iso:
        raise ValueError("La nueva condición debe tener fecha de inicio.")
    if fin_iso and fin_iso < inicio_iso:
        raise ValueError("La fecha final no puede ser anterior a la inicial.")
    if not origen.get("contrato_id"):
        raise ValueError("La condición de origen no está enlazada a un contrato.")
    payload = dict(origen["payload"])
    payload.update({
        periodo: numero_contractual(potencias.get(periodo))
        for periodo in PERIODOS
    })
    if potencias_referencia is not None:
        payload.update({
            f"{periodo} REF": numero_contractual(
                potencias_referencia.get(periodo)
            )
            for periodo in PERIODOS
        })
    token = uuid4().hex
    source_key = f"manual-condition-{token}"
    digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()
    cierre_anterior = (date.fromisoformat(inicio_iso) - timedelta(days=1)).isoformat()

    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if cerrar_anterior:
            inicio_origen = origen.get("fecha_inicio_condiciones")
            if inicio_origen and cierre_anterior < inicio_origen:
                raise ValueError("El cierre dejaría la condición anterior sin vigencia.")
            connection.execute(
                "UPDATE filas_contrato_origen SET fecha_fin_condiciones = ? WHERE id = ?",
                (cierre_anterior, int(condicion_origen_id)),
            )
        batch = connection.execute(
            """
            INSERT INTO import_batches(
                source_system, entity_type, source_name, source_sha256, row_count
            ) VALUES ('MANUAL', 'condiciones_contrato', ?, ?, 1)
            """,
            (source_key, digest),
        )
        registro = connection.execute(
            """
            INSERT INTO legacy_records(batch_id, source_key, row_number, payload_json)
            VALUES (?, ?, 1, ?)
            """,
            (batch.lastrowid, source_key, json.dumps(payload, ensure_ascii=False)),
        )
        nueva = connection.execute(
            """
            INSERT INTO filas_contrato_origen(
                source_system, legacy_record_id, legacy_contract_id,
                suministro_id, titular_id, comercializadora,
                referencia_comercializadora, referencia_acceso, tarifa,
                fecha_inicio_condiciones, fecha_fin_condiciones, tipo_precio,
                proveedor_curva_legacy, contrato_id
            ) VALUES ('MANUAL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                registro.lastrowid, source_key, origen["suministro_id"],
                origen["titular_id"], origen["comercializadora"],
                origen["referencia_comercializadora"], origen["referencia_acceso"],
                origen["tarifa"], inicio_iso, fin_iso, origen["tipo_precio"],
                origen["proveedor_curva_legacy"], origen["contrato_id"],
            ),
        )
        nueva_id = int(nueva.lastrowid)
        datos_nuevos = {
            "inicio": inicio_iso, "fin": fin_iso,
            "potencias": {periodo: payload[periodo] for periodo in PERIODOS},
            "potencias_referencia": {
                periodo: payload.get(f"{periodo} REF") for periodo in PERIODOS
            },
            "condicion_origen_id": int(condicion_origen_id),
            "cierre_anterior": cierre_anterior if cerrar_anterior else None,
        }
        connection.execute(
            """
            INSERT INTO cambios_condiciones_contractuales(
                condicion_id, contrato_id, accion, datos_nuevos_json, motivo
            ) VALUES (?, ?, 'CREAR', ?, ?)
            """,
            (
                nueva_id, origen["contrato_id"],
                json.dumps(datos_nuevos, ensure_ascii=False), motivo.strip() or None,
            ),
        )
    return nueva_id
