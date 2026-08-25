"""Cálculo reutilizable de la fórmula indexada vigente en Telemindex."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


ATRS_INDEXADOS = ("2.0", "3.0", "6.1")
POSICIONES_FORMULA = {"perdidas", "tm", "neto"}


@dataclass(frozen=True)
class FormulaIndexada:
    desvios_apant: float = 0.0
    margen: float = 0.0
    margen_pos: str = "tm"
    incluir_fnee: bool = False
    fnee_pos: str = "perdidas"
    cf_pct: float = 0.0


def _validar_formula_y_componentes(
    df: pd.DataFrame,
    formula: FormulaIndexada,
) -> pd.DataFrame:
    if formula.margen_pos not in POSICIONES_FORMULA:
        raise ValueError(f"Ubicación de margen no válida: {formula.margen_pos}.")
    if formula.fnee_pos not in POSICIONES_FORMULA:
        raise ValueError(f"Ubicación de FNEE no válida: {formula.fnee_pos}.")
    requeridas = {"spot", "ssaa", "osom"}
    if formula.incluir_fnee:
        requeridas.add("fnee")
    for atr in ATRS_INDEXADOS:
        requeridas.update({f"ppcc_{atr}", f"perd_{atr}", f"pyc_{atr}"})
    faltantes = sorted(requeridas.difference(df.columns))
    if faltantes:
        raise ValueError(
            "Faltan componentes para calcular el precio indexado: "
            + ", ".join(faltantes)
        )
    resultado = df.copy()
    for columna in requeridas:
        resultado[columna] = pd.to_numeric(resultado[columna], errors="coerce")
        invalidos = resultado[columna].isna() | ~np.isfinite(resultado[columna])
        if invalidos.any():
            raise ValueError(
                f"El componente {columna} contiene {int(invalidos.sum())} "
                "valores vacíos o no numéricos."
            )
    return resultado


def calcular_precios_atr_formula(
    df: pd.DataFrame,
    formula: FormulaIndexada,
) -> pd.DataFrame:
    """Ejecuta, sin Streamlit, la misma fórmula vigente en Telemindex."""
    tm_rate = 0.015
    cf = formula.cf_pct / 100
    margen = formula.margen
    resultado = _validar_formula_y_componentes(df, formula)

    for atr in ATRS_INDEXADOS:
        base = (
            resultado["spot"]
            + resultado["ssaa"]
            + resultado[f"ppcc_{atr}"]
            + resultado["osom"]
        )
        base += 0.0
        base += formula.desvios_apant

        if formula.incluir_fnee and formula.fnee_pos == "perdidas":
            base += resultado["fnee"]

        base_coste = base.copy()
        base_precio = base.copy()

        if formula.margen_pos == "perdidas":
            resultado[f"margen_{atr}"] = (
                margen * (1 + resultado[f"perd_{atr}"]) * (1 + tm_rate) * (1 + cf)
            )
            base_precio += margen

        base_coste *= 1 + resultado[f"perd_{atr}"]
        base_precio *= 1 + resultado[f"perd_{atr}"]

        if formula.margen_pos == "tm":
            resultado[f"margen_{atr}"] = margen * (1 + tm_rate) * (1 + cf)
            base_precio += margen

        if formula.incluir_fnee and formula.fnee_pos == "tm":
            base_coste += resultado["fnee"]
            base_precio += resultado["fnee"]

        base_coste *= 1 + tm_rate
        base_precio *= 1 + tm_rate
        base_coste *= 1 + cf
        base_precio *= 1 + cf

        if formula.incluir_fnee and formula.fnee_pos == "neto":
            base_coste += resultado["fnee"]
            base_precio += resultado["fnee"]

        if formula.margen_pos == "neto":
            resultado[f"margen_{atr}"] = margen
            base_precio += margen

        resultado[f"coste_{atr}"] = base_coste
        resultado[f"precio_{atr}"] = base_precio + resultado[f"pyc_{atr}"]

    return resultado
