"""Vigencias contractuales independientes de las versiones de condiciones."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .db import DEFAULT_DB_PATH, connect, initialize_database


def _fecha(valor) -> date | None:
    if valor is None or str(valor).strip() == "":
        return None
    return pd.Timestamp(valor).date()


def listar_periodos_cups(cups, db_path: str | Path = DEFAULT_DB_PATH) -> list[dict]:
    if not Path(db_path).is_file():
        return []
    initialize_database(db_path)
    cups20 = re.sub(r"[^A-Z0-9]", "", str(cups or "").upper())[:20]
    if len(cups20) != 20:
        return []
    with connect(db_path) as connection:
        filas = connection.execute(
            """
            SELECT p.id, p.contrato_id, p.fecha_inicio, p.fecha_vencimiento,
                p.observaciones, c.comercializadora,
                c.referencia_comercializadora
            FROM periodos_contrato p
            JOIN contratos c ON c.id = p.contrato_id
            JOIN suministros s ON s.id = c.suministro_id
            WHERE s.cups20 = ?
            ORDER BY p.fecha_inicio, p.id
            """,
            (cups20,),
        ).fetchall()
    return [dict(fila) for fila in filas]


def guardar_periodo_contrato(
    contrato_id: int, inicio, vencimiento=None, observaciones="",
    periodo_id: int | None = None, db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """Guarda una vigencia confirmada y rechaza fechas solapadas."""
    fecha_inicio = _fecha(inicio)
    fecha_vencimiento = _fecha(vencimiento)
    if fecha_inicio is None:
        raise ValueError("Indica la fecha de inicio del contrato.")
    if fecha_vencimiento and fecha_vencimiento < fecha_inicio:
        raise ValueError("El vencimiento no puede ser anterior al inicio.")
    initialize_database(db_path)
    with connect(db_path) as connection:
        contrato = connection.execute(
            "SELECT id FROM contratos WHERE id = ?", (int(contrato_id),)
        ).fetchone()
        if contrato is None:
            raise ValueError("El contrato seleccionado no existe.")
        otros = connection.execute(
            """
            SELECT id, fecha_inicio, fecha_vencimiento
            FROM periodos_contrato
            WHERE contrato_id = ? AND (? IS NULL OR id <> ?)
            """,
            (int(contrato_id), periodo_id, periodo_id),
        ).fetchall()
        for otro in otros:
            otro_inicio = _fecha(otro["fecha_inicio"])
            otro_fin = _fecha(otro["fecha_vencimiento"])
            if (
                (fecha_vencimiento is None or otro_inicio <= fecha_vencimiento)
                and (otro_fin is None or fecha_inicio <= otro_fin)
            ):
                raise ValueError(
                    "La vigencia se solapa con otra del mismo contrato."
                )
        datos = (
            fecha_inicio.isoformat(),
            fecha_vencimiento.isoformat() if fecha_vencimiento else None,
            str(observaciones or "").strip() or None,
        )
        if periodo_id is None:
            resultado = connection.execute(
                """
                INSERT INTO periodos_contrato(
                    contrato_id, fecha_inicio, fecha_vencimiento, observaciones
                ) VALUES (?, ?, ?, ?)
                """,
                (int(contrato_id), *datos),
            )
            return int(resultado.lastrowid)
        resultado = connection.execute(
            """
            UPDATE periodos_contrato
            SET fecha_inicio = ?, fecha_vencimiento = ?, observaciones = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND contrato_id = ?
            """,
            (*datos, int(periodo_id), int(contrato_id)),
        )
        if resultado.rowcount != 1:
            raise ValueError("La vigencia seleccionada ya no existe.")
        return int(periodo_id)


def sugerir_cambios_contrato(
    periodos: list[dict], condiciones: pd.DataFrame,
    fecha_min, fecha_max,
) -> list[dict]:
    """Sugiere inicios de contrato con consumo anterior en la curva."""
    if not periodos or condiciones is None or condiciones.empty:
        return []
    minimo, maximo = _fecha(fecha_min), _fecha(fecha_max)
    ordenados = sorted(periodos, key=lambda fila: fila["fecha_inicio"])
    sugerencias = []
    for indice, periodo in enumerate(ordenados):
        inicio = _fecha(periodo["fecha_inicio"])
        if inicio is None or inicio <= minimo or inicio > maximo:
            continue
        anteriores = condiciones.loc[
            (condiciones["inicio_condicion"] < pd.Timestamp(inicio))
            & condiciones["fin_condicion"].notna()
            & (condiciones["fin_condicion"] < pd.Timestamp(inicio))
        ].sort_values("fin_condicion")
        if anteriores.empty:
            continue
        fin = min(maximo, _fecha(periodo["fecha_vencimiento"]) or maximo)
        if indice + 1 < len(ordenados):
            fin = min(
                fin, _fecha(ordenados[indice + 1]["fecha_inicio"])
                - timedelta(days=1),
            )
        if fin < inicio:
            continue
        sugerencias.append({
            "inicio": inicio,
            "fin": fin,
            "vencimiento": _fecha(periodo["fecha_vencimiento"]),
            "periodo_id": int(periodo["id"]),
            "condicion_referencia_id": int(
                anteriores.iloc[-1]["condicion_id"]
            ),
            "comercializadora": periodo["comercializadora"],
            "referencia": periodo["referencia_comercializadora"],
        })
    return sugerencias
