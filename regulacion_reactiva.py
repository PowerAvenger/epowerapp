"""Reglas comunes para la facturación de energía reactiva inductiva."""

from __future__ import annotations

import math


LIMITE_REACTIVA_SOBRE_ACTIVA = 0.33
COS_PHI_SIN_PENALIZACION = 0.95
COS_PHI_PENALIZACION_ALTA = 0.80
PRECIO_REACTIVA_MEDIA_EUR_KVARH = 0.0415540
PRECIO_REACTIVA_ALTA_EUR_KVARH = 0.0623320
PERIODO_INDUCTIVA_EXENTO = "P6"
FUENTE_REACTIVA = "Resolución CNMC de 18/12/2025, BOE-A-2025-26348, anexo III"


def factor_potencia(energia_activa_kwh: float, reactiva_kvarh: float) -> float | None:
    if energia_activa_kwh <= 0:
        return None
    return energia_activa_kwh / math.sqrt(
        energia_activa_kwh**2 + reactiva_kvarh**2
    )


def exceso_reactiva_inductiva(
    energia_activa_kwh: float,
    reactiva_kvarh: float,
    periodo: str,
) -> float:
    if periodo.upper() == PERIODO_INDUCTIVA_EXENTO:
        return 0.0
    return max(
        reactiva_kvarh - energia_activa_kwh * LIMITE_REACTIVA_SOBRE_ACTIVA,
        0.0,
    )


def precio_reactiva_inductiva(cos_phi: float | None, periodo: str) -> float:
    if cos_phi is None or periodo.upper() == PERIODO_INDUCTIVA_EXENTO:
        return 0.0
    if cos_phi >= COS_PHI_SIN_PENALIZACION:
        return 0.0
    if cos_phi >= COS_PHI_PENALIZACION_ALTA:
        return PRECIO_REACTIVA_MEDIA_EUR_KVARH
    return PRECIO_REACTIVA_ALTA_EUR_KVARH


def tramos_reactiva() -> list[dict[str, str | float]]:
    return [
        {"Periodos": "P1-P5", "cos φ": "≥ 0,95", "Precio (€/kVArh)": 0.0},
        {
            "Periodos": "P1-P5",
            "cos φ": "0,80 ≤ cos φ < 0,95",
            "Precio (€/kVArh)": PRECIO_REACTIVA_MEDIA_EUR_KVARH,
        },
        {
            "Periodos": "P1-P5",
            "cos φ": "< 0,80",
            "Precio (€/kVArh)": PRECIO_REACTIVA_ALTA_EUR_KVARH,
        },
        {
            "Periodos": "P6",
            "cos φ": "Reactiva inductiva exenta",
            "Precio (€/kVArh)": 0.0,
        },
    ]
