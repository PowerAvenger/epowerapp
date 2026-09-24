"""Cálculos puros del comparador PPA de carga base."""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend_indexado import FormulaIndexada, calcular_precios_atr_formula


ATRS_PPA = ("2.0", "3.0", "6.1", "6.2")


def _periodos(df: pd.DataFrame, atr: str) -> pd.Series:
    if "periodo" in df:
        periodo = df["periodo"].astype(str).str.upper()
        if periodo.str.fullmatch(r"P[1-6]").any():
            return periodo
    columna = "dh_3p" if atr == "2.0" else "dh_6p"
    if columna not in df:
        raise ValueError(f"No existe la columna de periodos {columna}.")
    periodo = df[columna].astype(str).str.upper()
    return periodo.where(periodo.str.startswith("P"), "P" + periodo)


def _duracion_intervalo_horas(df: pd.DataFrame) -> pd.Series:
    """Obtiene la duración representada por cada fila; una hora por defecto."""
    if "duracion_horas" in df:
        duracion = pd.to_numeric(df["duracion_horas"], errors="coerce")
    else:
        duracion = pd.Series(1.0, index=df.index, dtype=float)
    if duracion.isna().any() or (duracion <= 0).any():
        raise ValueError("La duración de los intervalos debe ser positiva.")
    return duracion


def repartir_carga_base(
    df: pd.DataFrame,
    potencia_ppa_mw: float,
) -> pd.DataFrame:
    """Separa consumo, cobertura, residual y excedente en cada intervalo."""
    if potencia_ppa_mw < 0:
        raise ValueError("La potencia del PPA no puede ser negativa.")
    if "consumo_neto_kWh" not in df:
        raise ValueError("La curva no contiene consumo_neto_kWh.")

    resultado = df.copy()
    consumo = pd.to_numeric(resultado["consumo_neto_kWh"], errors="coerce")
    if consumo.isna().any() or (consumo < 0).any():
        raise ValueError("La curva contiene consumos vacíos o negativos.")
    volumen = float(potencia_ppa_mw) * 1000 * _duracion_intervalo_horas(resultado)
    resultado["energia_ppa_contratada_kWh"] = volumen
    resultado["energia_ppa_cubierta_kWh"] = np.minimum(consumo, volumen)
    resultado["energia_residual_kWh"] = np.maximum(consumo - volumen, 0.0)
    resultado["energia_excedente_kWh"] = np.maximum(volumen - consumo, 0.0)
    resultado["cobertura_pct"] = np.where(
        consumo > 0, resultado["energia_ppa_cubierta_kWh"] / consumo * 100, 0.0
    )
    return resultado


def _resumir(detalle: pd.DataFrame, atr: str) -> pd.DataFrame:
    periodo = _periodos(detalle, atr)
    filas = []
    for nombre in [*[f"P{i}" for i in range(1, 7)], "Total"]:
        grupo = detalle if nombre == "Total" else detalle.loc[periodo == nombre]
        consumo = grupo["consumo_neto_kWh"].sum()
        cubierto = grupo["energia_ppa_cubierta_kWh"].sum()
        contratado = grupo["energia_ppa_contratada_kWh"].sum()
        residual = grupo["energia_residual_kWh"].sum()
        excedente = grupo["energia_excedente_kWh"].sum()
        referencia = grupo["coste_referencia_eur"].sum()
        escenario = grupo["coste_escenario_ppa_eur"].sum()
        filas.append({
            "Periodo": nombre,
            "Consumo (kWh)": consumo,
            "Cubierto PPA (kWh)": cubierto,
            "Contratado PPA (kWh)": contratado,
            "Residual (kWh)": residual,
            "Excedente (kWh)": excedente,
            "Cobertura (%)": cubierto / consumo * 100 if consumo else 0.0,
            "Aprovechamiento PPA (%)": (
                cubierto / contratado * 100 if contratado else 0.0
            ),
            "Coste referencia (€)": referencia,
            "Coste con PPA (€)": escenario,
            "Ahorro (€)": referencia - escenario,
            "Precio referencia (€/MWh)": referencia / consumo * 1000 if consumo else np.nan,
            "Precio con PPA (€/MWh)": escenario / consumo * 1000 if consumo else np.nan,
        })
    return pd.DataFrame(filas)


def calcular_ppa_indexado(
    df: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    potencia_ppa_mw: float,
    precio_ppa_eur_mwh: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara todo indexado con PPA carga base más residual indexado."""
    if atr not in ATRS_PPA:
        raise ValueError(f"ATR no soportado para indexado: {atr}.")
    if precio_ppa_eur_mwh < 0:
        raise ValueError("El precio PPA no puede ser negativo.")

    base = calcular_precios_atr_formula(df, formula)
    detalle = repartir_carga_base(base, potencia_ppa_mw)
    alternativa = detalle.copy()
    alternativa["spot"] = float(precio_ppa_eur_mwh)
    alternativa = calcular_precios_atr_formula(alternativa, formula)
    columna_precio = f"precio_{atr}"
    consumo = detalle["consumo_neto_kWh"]
    detalle["precio_referencia_eur_mwh"] = base[columna_precio]
    detalle["precio_ppa_final_eur_mwh"] = alternativa[columna_precio]
    detalle["coste_referencia_eur"] = consumo * base[columna_precio] / 1000
    detalle["coste_ppa_cubierto_eur"] = (
        detalle["energia_ppa_cubierta_kWh"] * alternativa[columna_precio] / 1000
    )
    detalle["coste_residual_eur"] = (
        detalle["energia_residual_kWh"] * base[columna_precio] / 1000
    )
    detalle["coste_escenario_ppa_eur"] = (
        detalle["coste_ppa_cubierto_eur"] + detalle["coste_residual_eur"]
    )
    detalle["ahorro_eur"] = (
        detalle["coste_referencia_eur"] - detalle["coste_escenario_ppa_eur"]
    )
    return detalle, _resumir(detalle, atr)


def calcular_ppa_fijo(
    df: pd.DataFrame,
    atr: str,
    precios_fijos_eur_kwh: dict[str, float],
    potencia_ppa_mw: float,
    precio_ppa_eur_mwh: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compara todo fijo con PPA carga base más residual al fijo por periodo."""
    if precio_ppa_eur_mwh < 0:
        raise ValueError("El precio PPA no puede ser negativo.")
    detalle = repartir_carga_base(df, potencia_ppa_mw)
    periodo = _periodos(detalle, atr)
    precio_fijo = periodo.map(precios_fijos_eur_kwh)
    if precio_fijo.isna().any():
        faltantes = sorted(periodo[precio_fijo.isna()].unique())
        raise ValueError("Faltan precios fijos para: " + ", ".join(faltantes))
    detalle["precio_referencia_eur_mwh"] = precio_fijo * 1000
    detalle["precio_ppa_final_eur_mwh"] = float(precio_ppa_eur_mwh)
    detalle["coste_referencia_eur"] = detalle["consumo_neto_kWh"] * precio_fijo
    detalle["coste_ppa_cubierto_eur"] = (
        detalle["energia_ppa_cubierta_kWh"] * precio_ppa_eur_mwh / 1000
    )
    detalle["coste_residual_eur"] = detalle["energia_residual_kWh"] * precio_fijo
    detalle["coste_escenario_ppa_eur"] = (
        detalle["coste_ppa_cubierto_eur"] + detalle["coste_residual_eur"]
    )
    detalle["ahorro_eur"] = (
        detalle["coste_referencia_eur"] - detalle["coste_escenario_ppa_eur"]
    )
    return detalle, _resumir(detalle, atr)
