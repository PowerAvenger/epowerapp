"""Referencias regulatorias del Impuesto Especial sobre la Electricidad.

La interfaz pública de este módulo no depende del almacenamiento. Hoy utiliza
tramos declarados en código; más adelante puede leerlos de Excel, CSV o una
fuente externa manteniendo ``obtener_referencia_iee``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


TIPO_GENERAL_IEE = 5.11269632


@dataclass(frozen=True)
class TramoIEE:
    fecha_inicio: date
    fecha_fin: date
    tipo_pct: float
    fuente: str


@dataclass(frozen=True)
class ReferenciaIEE:
    fecha: date
    tipo_pct: float
    minimo_eur_mwh: float
    uso: str
    fuente: str


TRAMOS_IEE: tuple[TramoIEE, ...] = (
    TramoIEE(
        date(2015, 1, 1), date(2021, 9, 15), TIPO_GENERAL_IEE,
        "Ley 38/1992, artículo 99",
    ),
    TramoIEE(
        date(2021, 9, 16), date(2023, 12, 31), 0.5,
        "RDL 17/2021 y prórrogas hasta el 31/12/2023",
    ),
    TramoIEE(
        date(2024, 1, 1), date(2024, 3, 31), 2.5,
        "RDL 8/2023, artículo 22",
    ),
    TramoIEE(
        date(2024, 4, 1), date(2024, 6, 30), 3.8,
        "RDL 8/2023, artículo 22",
    ),
    TramoIEE(
        date(2024, 7, 1), date(2026, 3, 21), TIPO_GENERAL_IEE,
        "Ley 38/1992, artículo 99",
    ),
    TramoIEE(
        date(2026, 3, 22), date(2026, 5, 31), 0.5,
        "RDL 7/2026, artículo 40",
    ),
    TramoIEE(
        date(2026, 6, 1), date(2026, 7, 31), TIPO_GENERAL_IEE,
        "RDL 7/2026, artículo 40.2; condición de IPC para junio",
    ),
)


def es_uso_industrial_por_atr(atr: str | None) -> bool:
    """Criterio operativo actual; queda aislado para poder sustituirlo.

    La norma también contempla otros supuestos industriales. Con los datos de
    factura disponibles se considera alta tensión (tarifas 6.x) como industrial.
    """
    tarifa = (atr or "").replace(" ", "").upper()
    return tarifa.startswith("6.")


def obtener_referencia_iee(
    fecha: date,
    atr: str | None,
) -> ReferenciaIEE | None:
    tramo = next(
        (
            item for item in TRAMOS_IEE
            if item.fecha_inicio <= fecha <= item.fecha_fin
        ),
        None,
    )
    if not tramo:
        return None
    industrial = es_uso_industrial_por_atr(atr)
    return ReferenciaIEE(
        fecha=fecha,
        tipo_pct=tramo.tipo_pct,
        minimo_eur_mwh=0.5 if industrial else 1.0,
        uso="industrial" if industrial else "otros usos",
        fuente=tramo.fuente,
    )
