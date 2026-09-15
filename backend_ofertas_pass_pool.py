"""Carga y validación de ofertas indexadas de tipo pass pool."""

from __future__ import annotations

import json
from pathlib import Path


RUTA_OFERTAS_PASS_POOL = (
    Path(__file__).resolve().parent / "data" / "ofertas_pass_pool.json"
)
PERIODOS = tuple(f"P{i}" for i in range(1, 7))


def cargar_ofertas_pass_pool(ruta=RUTA_OFERTAS_PASS_POOL) -> list[dict]:
    """Lee el catálogo PP persistente y valida sus términos B."""
    ruta = Path(ruta)
    try:
        ofertas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"No se puede leer el catálogo pass pool: {exc}") from exc
    if not isinstance(ofertas, list):
        raise ValueError("El catálogo pass pool debe ser una lista de ofertas.")

    for oferta in ofertas:
        if oferta.get("tipo") != "pass_pool":
            raise ValueError("El catálogo contiene una oferta que no es pass pool.")
        terminos_b = oferta.get("terminos_b", {})
        faltantes = set(PERIODOS).difference(terminos_b)
        if faltantes:
            raise ValueError(
                "Faltan términos B en la oferta pass pool: "
                + ", ".join(sorted(faltantes))
                + "."
            )
        oferta["terminos_b"] = {
            periodo: float(terminos_b[periodo]) for periodo in PERIODOS
        }
    return ofertas


def obtener_oferta_pass_pool(
    identificador: str,
    ruta=RUTA_OFERTAS_PASS_POOL,
) -> dict:
    """Devuelve una oferta PP persistida por su identificador."""
    for oferta in cargar_ofertas_pass_pool(ruta):
        if oferta.get("id") == identificador:
            return oferta
    raise ValueError(f"No existe la oferta pass pool «{identificador}».")
