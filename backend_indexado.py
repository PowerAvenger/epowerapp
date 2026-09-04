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


# Horas de entrega (1-24) marcadas como "Fijo" en el cuadrante combo.
# Los extremos son inclusivos.
HORARIO_FIJO_COMBO = {
    1: (10, 18),
    2: (9, 18),
    3: (8, 19),
    4: (8, 19),
    5: (6, 20),
    6: (6, 20),
    7: (7, 20),
    8: (8, 20),
    9: (8, 19),
    10: (8, 18),
    11: (9, 18),
    12: (10, 17),
}


def calcular_combo_index_fijo(
    df_curva: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    omie_fijo: float = 40.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cotiza únicamente las horas fijas del cuadrante con OMIE sustituido.

    Devuelve el detalle horario completo y el precio del bloque fijo ponderado
    por su consumo en EUR/MWh para P1-P6 y Total. Las horas indexadas no forman
    parte del resumen. La hora del cuadrante es la hora de entrega 1-24, por lo
    que una marca temporal a las 00:00 corresponde a la hora 1.
    """
    if atr not in ATRS_INDEXADOS:
        raise ValueError(f"ATR no soportado: {atr}.")
    requeridas = {"fecha_hora", "consumo_neto_kWh", "spot"}
    faltantes = sorted(requeridas.difference(df_curva.columns))
    if faltantes:
        raise ValueError("Faltan columnas en la curva: " + ", ".join(faltantes))

    detalle = df_curva.copy()
    detalle["fecha_hora"] = pd.to_datetime(
        detalle["fecha_hora"], errors="coerce"
    )
    detalle["consumo_neto_kWh"] = pd.to_numeric(
        detalle["consumo_neto_kWh"], errors="coerce"
    )
    detalle["spot_original"] = pd.to_numeric(detalle["spot"], errors="coerce")
    invalidas = detalle["fecha_hora"].isna() | detalle["consumo_neto_kWh"].isna()
    if invalidas.any():
        raise ValueError(
            f"La curva contiene {int(invalidas.sum())} filas sin fecha o consumo válido."
        )

    detalle["hora_entrega"] = detalle["fecha_hora"].dt.hour + 1
    limites = detalle["fecha_hora"].dt.month.map(HORARIO_FIJO_COMBO)
    detalle["es_fijo"] = [
        inicio <= hora <= fin
        for hora, (inicio, fin) in zip(detalle["hora_entrega"], limites)
    ]
    detalle["tipo_combo"] = np.where(detalle["es_fijo"], "Fijo", "Indexado")
    detalle["spot"] = detalle["spot_original"].where(
        ~detalle["es_fijo"], float(omie_fijo)
    )
    detalle = calcular_precios_atr_formula(detalle, formula)

    periodo = _columna_periodo_desglose(detalle, atr)
    detalle["periodo_combo"] = periodo
    detalle["coste_combo_eur"] = (
        detalle[f"precio_{atr}"] * detalle["consumo_neto_kWh"] / 1000
    )
    detalle_fijo = detalle[detalle["es_fijo"]].copy()
    resumen_fijo = resumir_precio_ponderado(detalle_fijo, atr)
    return detalle, resumen_fijo


def resumir_precio_ponderado(
    detalle: pd.DataFrame,
    atr: str,
) -> pd.DataFrame:
    """Resume precio, consumo y coste por periodo y total."""
    if atr not in ATRS_INDEXADOS:
        raise ValueError(f"ATR no soportado: {atr}.")
    periodo = _columna_periodo_desglose(detalle, atr)
    filas = []
    for nombre in [*[f"P{i}" for i in range(1, 7)], "Total"]:
        grupo = (
            detalle
            if nombre == "Total"
            else detalle[periodo == nombre]
        )
        consumo_grupo = pd.to_numeric(
            grupo["consumo_neto_kWh"], errors="coerce"
        ).sum()
        coste_grupo = (
            pd.to_numeric(grupo[f"precio_{atr}"], errors="coerce")
            * pd.to_numeric(grupo["consumo_neto_kWh"], errors="coerce")
            / 1000
        ).sum()
        filas.append({
            "Periodo": nombre,
            "Consumo (kWh)": consumo_grupo,
            "Coste (EUR)": coste_grupo,
            "Precio medio (EUR/MWh)": (
                coste_grupo / consumo_grupo * 1000
                if consumo_grupo > 0 else np.nan
            ),
        })
    return pd.DataFrame(filas).set_index("Periodo")


def _media_con_pesos(valores: pd.Series, pesos: pd.Series | None = None) -> float:
    valores = pd.to_numeric(valores, errors="coerce")
    if pesos is None:
        return float(valores.mean())
    pesos = pd.to_numeric(pesos, errors="coerce")
    validos = valores.notna() & pesos.notna() & (pesos >= 0)
    peso_total = pesos[validos].sum()
    if not validos.any() or peso_total <= 0:
        return float("nan")
    return float((valores[validos] * pesos[validos]).sum() / peso_total)


def _columna_periodo_desglose(df: pd.DataFrame, atr: str) -> pd.Series:
    if "periodo" in df.columns:
        periodo = df["periodo"].astype(str).str.upper()
        if periodo.str.fullmatch(r"P[1-6]").any():
            return periodo
    columna = "dh_3p" if atr == "2.0" else "dh_6p"
    if columna not in df.columns:
        raise ValueError(f"No existe la columna de periodos {columna}.")
    periodo = df[columna].astype(str).str.upper()
    return periodo.where(periodo.str.startswith("P"), "P" + periodo)


def construir_desglose_precio_indexado(
    df: pd.DataFrame,
    atr: str,
    formula: FormulaIndexada,
    columna_consumo: str | None = None,
) -> pd.DataFrame:
    """Concilia las aportaciones de la fórmula con el precio final.

    Devuelve medias en EUR/MWh para el total y para cada periodo. Cuando se
    facilita una columna de consumo, todas las medias usan ese mismo peso.
    """
    if atr not in ATRS_INDEXADOS:
        raise ValueError(f"ATR no soportado: {atr}.")
    calculado = calcular_precios_atr_formula(df, formula)
    periodo = _columna_periodo_desglose(calculado, atr)
    pesos = calculado[columna_consumo] if columna_consumo else None
    tm_rate = 0.015
    cf = formula.cf_pct / 100

    aportaciones = pd.DataFrame(index=calculado.index)
    aportaciones["OMIE"] = calculado["spot"]
    aportaciones["SSAA (global)"] = calculado["ssaa"]
    aportaciones["OSOM"] = calculado["osom"]
    aportaciones["PPCC"] = calculado[f"ppcc_{atr}"]
    aportaciones["Desvíos apantallados"] = formula.desvios_apant

    subtotal_perdidas = aportaciones.sum(axis=1)
    if formula.incluir_fnee and formula.fnee_pos == "perdidas":
        aportaciones["FNEE · antes de pérdidas"] = calculado["fnee"]
        subtotal_perdidas += calculado["fnee"]
    if formula.margen_pos == "perdidas":
        aportaciones["Margen · antes de pérdidas"] = formula.margen
        subtotal_perdidas += formula.margen

    aportaciones["Pérdidas reales"] = subtotal_perdidas * calculado[f"perd_{atr}"]
    subtotal_tm = subtotal_perdidas + aportaciones["Pérdidas reales"]
    if formula.incluir_fnee and formula.fnee_pos == "tm":
        aportaciones["FNEE · antes de TM"] = calculado["fnee"]
        subtotal_tm += calculado["fnee"]
    if formula.margen_pos == "tm":
        aportaciones["Margen · antes de TM"] = formula.margen
        subtotal_tm += formula.margen

    aportaciones["Tasa municipal (TM)"] = subtotal_tm * tm_rate
    subtotal_cf = subtotal_tm + aportaciones["Tasa municipal (TM)"]
    aportaciones["Coste financiero (CF)"] = subtotal_cf * cf

    if formula.incluir_fnee and formula.fnee_pos == "neto":
        aportaciones["FNEE · en neto"] = calculado["fnee"]
    if formula.margen_pos == "neto":
        aportaciones["Margen · en neto"] = formula.margen
    aportaciones["PyC"] = calculado[f"pyc_{atr}"]
    aportaciones["Precio final"] = calculado[f"precio_{atr}"]

    columnas_resultado = sorted(
        periodo.dropna().unique(), key=lambda valor: int(str(valor)[1:])
    ) + ["Total"]
    filas = []
    for componente in aportaciones.columns:
        fila = {"Componente": componente}
        for nombre_periodo in columnas_resultado[:-1]:
            mascara = periodo == nombre_periodo
            pesos_periodo = pesos[mascara] if pesos is not None else None
            fila[nombre_periodo] = _media_con_pesos(
                aportaciones.loc[mascara, componente], pesos_periodo
            )
        fila["Total"] = _media_con_pesos(aportaciones[componente], pesos)
        filas.append(fila)
    return pd.DataFrame(filas, columns=["Componente", *columnas_resultado])


def construir_desglose_ssaa_c2(
    df: pd.DataFrame,
    componentes: list[str] | tuple[str, ...],
    atr: str,
    columna_consumo: str | None = None,
) -> pd.DataFrame:
    """Resume los componentes C2 que forman el SSAA global."""
    faltantes = [columna for columna in componentes if columna not in df.columns]
    if faltantes:
        raise ValueError("Faltan componentes C2: " + ", ".join(faltantes))
    periodo = _columna_periodo_desglose(df, atr)
    pesos = df[columna_consumo] if columna_consumo else None
    detalle = df[list(componentes)].apply(pd.to_numeric, errors="coerce")
    detalle["SSAA C2 reconstruido"] = detalle.sum(axis=1, min_count=len(componentes))
    if "ssaa" in df.columns:
        detalle["SSAA global usado"] = pd.to_numeric(df["ssaa"], errors="coerce")
        detalle["Diferencia vs global"] = (
            detalle["SSAA C2 reconstruido"] - detalle["SSAA global usado"]
        )
    columnas_resultado = sorted(
        periodo.dropna().unique(), key=lambda valor: int(str(valor)[1:])
    ) + ["Total"]
    filas = []
    for componente in detalle.columns:
        fila = {"Componente SSAA": componente.upper()}
        for nombre_periodo in columnas_resultado[:-1]:
            mascara = periodo == nombre_periodo
            pesos_periodo = pesos[mascara] if pesos is not None else None
            fila[nombre_periodo] = _media_con_pesos(
                detalle.loc[mascara, componente], pesos_periodo
            )
        fila["Total"] = _media_con_pesos(detalle[componente], pesos)
        filas.append(fila)
    return pd.DataFrame(filas, columns=["Componente SSAA", *columnas_resultado])
