from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .db import DEFAULT_DB_PATH, connect, initialize_database


TIPOS_ANALISIS = {"VERIFICACION", "COMPARATIVA_AHORRO"}


def _json_compatible(value: Any) -> Any:
    """Convierte el snapshot sin perder el valor mostrado por la aplicación."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_compatible(asdict(value))
    if hasattr(value, "to_dict"):
        try:
            return _json_compatible(value.to_dict(orient="records"))
        except TypeError:
            return _json_compatible(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    if hasattr(value, "item"):
        return _json_compatible(value.item())
    return str(value)


def _json_canonico(value: Any) -> str:
    return json.dumps(
        _json_compatible(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    )


def guardar_analisis(
    *,
    tipo: str,
    cups: str,
    numero_factura: str | None,
    fecha_factura: str | None,
    ciclo_inicio: str,
    ciclo_fin: str,
    estado: str,
    total_facturado_eur: float,
    total_referencia_eur: float,
    diferencia_eur: float,
    diferencia_pct: float | None,
    componentes: list[dict[str, Any]],
    snapshot: dict[str, Any],
    referencias: list[dict[str, Any]] | None = None,
    version_calculo: str = "1",
    creado_por: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[int, bool]:
    """Guarda una ejecución inmutable. Devuelve ``(id, creada)``."""
    tipo = str(tipo).strip().upper()
    if tipo not in TIPOS_ANALISIS:
        raise ValueError(f"Tipo de análisis no soportado: {tipo}")
    if not ciclo_inicio or not ciclo_fin:
        raise ValueError("El ciclo de facturación debe estar completo.")

    initialize_database(db_path)
    snapshot_json = _json_canonico(snapshot)
    digest = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    with connect(db_path) as connection:
        suministro = connection.execute(
            "SELECT id FROM suministros WHERE cups20 = ?",
            (str(cups).strip()[:20],),
        ).fetchone()
        if suministro is None:
            raise ValueError("El CUPS no existe en la BBDD local.")
        suministro_id = int(suministro[0])
        contrato = connection.execute(
            """
            SELECT id FROM contratos
            WHERE suministro_id = ?
              AND (vigente_desde IS NULL OR vigente_desde <= ?)
              AND (vigente_hasta IS NULL OR vigente_hasta >= ?)
            ORDER BY COALESCE(vigente_desde, '') DESC, id DESC
            LIMIT 1
            """,
            (suministro_id, ciclo_fin, ciclo_inicio),
        ).fetchone()
        existente = connection.execute(
            "SELECT id FROM analisis_factura WHERE tipo = ? AND snapshot_sha256 = ?",
            (tipo, digest),
        ).fetchone()
        if existente:
            return int(existente[0]), False

        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            """
            INSERT INTO analisis_factura(
                tipo, suministro_id, contrato_id, numero_factura, fecha_factura,
                ciclo_inicio, ciclo_fin, estado, total_facturado_eur,
                total_referencia_eur, diferencia_eur, diferencia_pct,
                version_calculo, snapshot_sha256, snapshot_json, creado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tipo, suministro_id, int(contrato[0]) if contrato else None,
                numero_factura, fecha_factura, ciclo_inicio, ciclo_fin, estado,
                float(total_facturado_eur), float(total_referencia_eur),
                float(diferencia_eur),
                float(diferencia_pct) if diferencia_pct is not None else None,
                str(version_calculo), digest, snapshot_json, creado_por,
            ),
        )
        analisis_id = int(cursor.lastrowid)
        for orden, componente in enumerate(componentes):
            connection.execute(
                """
                INSERT INTO componentes_analisis_factura(
                    analisis_id, orden, componente, facturado_eur,
                    referencia_eur, diferencia_eur, diferencia_pct,
                    estado, detalle_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analisis_id, orden, str(componente["componente"]),
                    componente.get("facturado_eur"),
                    componente.get("referencia_eur"),
                    componente.get("diferencia_eur"),
                    componente.get("diferencia_pct"), componente.get("estado"),
                    _json_canonico(componente.get("detalle"))
                    if componente.get("detalle") is not None else None,
                ),
            )
        for referencia in referencias or []:
            connection.execute(
                """
                INSERT INTO referencias_analisis_factura(
                    analisis_id, condicion_id, rol, referencia_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    analisis_id, referencia.get("condicion_id"),
                    str(referencia["rol"]), _json_canonico(referencia),
                ),
            )
    return analisis_id, True


def cargar_analisis(
    analisis_id: int, db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    initialize_database(db_path)
    with connect(db_path) as connection:
        cabecera = connection.execute(
            "SELECT * FROM analisis_factura WHERE id = ?", (int(analisis_id),)
        ).fetchone()
        if cabecera is None:
            raise ValueError("El análisis solicitado no existe.")
        componentes = connection.execute(
            """SELECT * FROM componentes_analisis_factura
            WHERE analisis_id = ? ORDER BY orden""",
            (int(analisis_id),),
        ).fetchall()
        referencias = connection.execute(
            """SELECT * FROM referencias_analisis_factura
            WHERE analisis_id = ? ORDER BY id""",
            (int(analisis_id),),
        ).fetchall()
    resultado = dict(cabecera)
    resultado["snapshot"] = json.loads(resultado.pop("snapshot_json"))
    resultado["componentes"] = [dict(fila) for fila in componentes]
    resultado["referencias"] = [
        {**dict(fila), "referencia": json.loads(fila["referencia_json"])}
        for fila in referencias
    ]
    return resultado
