"""Referencia efectiva del IVA aplicable al suministro eléctrico."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReferenciaIVA:
    fecha: date
    tipo_pct: float
    potencia_maxima_kw: float
    limite_reducido_kw: float
    fuente: str


# El RDL 7/2026 preveía inicialmente junio, condicionado al IPC de abril.
# La condición no se cumplió y el periodo efectivo terminó el 31/05/2026.
INICIO_IVA_REDUCIDO_2026 = date(2026, 3, 22)
FIN_IVA_REDUCIDO_2026 = date(2026, 5, 31)
LIMITE_POTENCIA_IVA_REDUCIDO_KW = 10.0


def obtener_referencia_iva(
    fecha: date,
    potencias_kw: list[float],
) -> ReferenciaIVA | None:
    """Devuelve el tipo legal usando fecha de factura y potencia máxima."""
    potencias_validas = [float(valor) for valor in potencias_kw if valor is not None]
    if not potencias_validas:
        return None

    potencia_maxima = max(potencias_validas)
    aplica_reducido = (
        INICIO_IVA_REDUCIDO_2026 <= fecha <= FIN_IVA_REDUCIDO_2026
        and potencia_maxima <= LIMITE_POTENCIA_IVA_REDUCIDO_KW
    )
    return ReferenciaIVA(
        fecha=fecha,
        tipo_pct=10.0 if aplica_reducido else 21.0,
        potencia_maxima_kw=potencia_maxima,
        limite_reducido_kw=LIMITE_POTENCIA_IVA_REDUCIDO_KW,
        fuente=(
            "RDL 7/2026, artículo 42; periodo efectivo 22/03/2026-31/05/2026"
            if aplica_reducido
            else "Ley 37/1992, artículo 90; tipo general del IVA"
        ),
    )
