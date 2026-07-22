"""Referencias temporales del FNEE compartidas por indexado y facturas."""

from datetime import date


FNEE_TRAMOS = [
    ("2023-01-01", 0.264),
    ("2023-03-31", 0.498),
    ("2024-03-24", 0.975),
    ("2025-03-05", 1.429),
    ("2026-03-01", 2.658),
]


def referencia_fnee(fecha: date, diferencial: bool = False) -> float | None:
    """Devuelve €/MWh completos o el incremento frente al tramo anterior."""
    aplicables = [
        (date.fromisoformat(inicio), valor)
        for inicio, valor in FNEE_TRAMOS
        if date.fromisoformat(inicio) <= fecha
    ]
    if not aplicables:
        return None
    valor = aplicables[-1][1]
    if not diferencial:
        return valor
    if len(aplicables) < 2:
        return None
    return round(valor - aplicables[-2][1], 6)


def hay_cambio_fnee(inicio: date, fin: date) -> bool:
    return any(
        inicio < date.fromisoformat(fecha) <= fin
        for fecha, _ in FNEE_TRAMOS
    )
