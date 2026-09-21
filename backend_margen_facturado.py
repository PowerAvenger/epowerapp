"""Estimación del margen implícito a partir de precios medios facturados."""

from dataclasses import replace

import pandas as pd

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula
from backend_ofertas_fijas import normalizar_atr, periodos_aplicables_atr


def estimar_margen_facturado(
    curva: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    precios_facturados: dict[str, float],
) -> dict:
    """Ajusta el margen de la fórmula a precios de energía P1–P6 en €/kWh.

    Usa las mismas horas y consumos de la curva. Mantiene los demás parámetros
    de la fórmula y calcula su efecto con margen cero y margen uno (€/MWh).
    """
    atr = normalizar_atr(atr)
    if curva.empty:
        raise ValueError("No hay una curva de consumo para comparar.")

    datos = curva.copy()
    datos["periodo"] = datos["periodo"].astype(str).str.strip().str.upper()
    datos["consumo_neto_kWh"] = pd.to_numeric(
        datos["consumo_neto_kWh"], errors="coerce"
    )
    if datos["consumo_neto_kWh"].isna().any() or (
        datos["consumo_neto_kWh"] < 0
    ).any():
        raise ValueError("La curva contiene consumos vacíos o negativos.")

    columna_precio = f"precio_{atr}"
    sin_margen = calcular_precios_atr_formula(
        datos, replace(formula, margen=0.0)
    )
    con_uno = calcular_precios_atr_formula(
        datos, replace(formula, margen=1.0)
    )
    if columna_precio not in sin_margen or columna_precio not in con_uno:
        raise ValueError(f"No hay precios indexados para {atr}TD.")

    datos["precio_sin_margen"] = pd.to_numeric(
        sin_margen[columna_precio], errors="coerce"
    )
    datos["sensibilidad_margen"] = (
        pd.to_numeric(con_uno[columna_precio], errors="coerce")
        - datos["precio_sin_margen"]
    )
    periodos = periodos_aplicables_atr(atr)
    datos = datos.loc[datos["periodo"].isin(periodos)].copy()
    if datos.empty or datos["consumo_neto_kWh"].sum() <= 0:
        raise ValueError("La curva no tiene consumo en los periodos de este ATR.")

    filas = []
    for periodo in periodos:
        tramo = datos.loc[datos["periodo"].eq(periodo)]
        consumo = float(tramo["consumo_neto_kWh"].sum())
        if consumo <= 0:
            continue
        precio_facturado = pd.to_numeric(
            precios_facturados.get(periodo), errors="coerce"
        )
        if pd.isna(precio_facturado) or not 0 < precio_facturado <= 2:
            raise ValueError(
                f"Introduce un precio de energía válido para {periodo} en €/kWh."
            )
        if tramo[["precio_sin_margen", "sensibilidad_margen"]].isna().any().any():
            raise ValueError(f"Faltan componentes de fórmula en {periodo}.")

        consumo_mwh = tramo["consumo_neto_kWh"] / 1000
        coste_base = float((tramo["precio_sin_margen"] * consumo_mwh).sum())
        sensibilidad = float((tramo["sensibilidad_margen"] * consumo_mwh).sum())
        if sensibilidad <= 0:
            raise ValueError(f"No se puede estimar el margen en {periodo}.")
        coste_facturado = consumo * float(precio_facturado)
        coste_formula = coste_base + formula.margen * sensibilidad
        filas.append({
            "Periodo": periodo,
            "Consumo (kWh)": consumo,
            "Precio facturado (€/kWh)": float(precio_facturado),
            "Precio calculado (€/kWh)": coste_formula / consumo,
            "Precio sin margen (€/kWh)": coste_base / consumo,
            "Margen implícito (€/MWh)": (
                coste_facturado - coste_base
            ) / sensibilidad,
            "Margen adicional (€/MWh)": (
                coste_facturado - coste_formula
            ) / sensibilidad,
            "Diferencia vs fórmula (€)": coste_facturado - coste_formula,
            "Coste facturado (€)": coste_facturado,
            "Coste sin margen (€)": coste_base,
            "Coste fórmula (€)": coste_formula,
            "Sensibilidad (€ por €/MWh)": sensibilidad,
        })

    detalle = pd.DataFrame(filas)
    consumo_total = float(detalle["Consumo (kWh)"].sum())
    coste_facturado_total = float(detalle["Coste facturado (€)"].sum())
    coste_base_total = float(detalle["Coste sin margen (€)"].sum())
    coste_formula_total = float(detalle["Coste fórmula (€)"].sum())
    sensibilidad_total = float(detalle["Sensibilidad (€ por €/MWh)"].sum())
    margen_implicito = (
        coste_facturado_total - coste_base_total
    ) / sensibilidad_total

    return {
        "detalle": detalle,
        "consumo_kwh": consumo_total,
        "precio_facturado_medio_eur_kwh": coste_facturado_total / consumo_total,
        "margen_implicito_eur_mwh": margen_implicito,
        "margen_adicional_eur_mwh": (
            coste_facturado_total - coste_formula_total
        ) / sensibilidad_total,
        "margen_formula_eur_mwh": formula.margen,
        "diferencia_coste_vs_formula_eur": (
            coste_facturado_total - coste_formula_total
        ),
        "diferencia_coste_vs_base_eur": (
            coste_facturado_total - coste_base_total
        ),
    }
