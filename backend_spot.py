"""Cálculos canónicos de medias SPOT sin redondeos intermedios."""

import pandas as pd


def preparar_periodos_spot(datos, columna_valor=None):
    """Normaliza una serie SPOT de ESIOS/JSON o Telemindex.

    El resultado conserva un registro por periodo de mercado. Los valores no se
    redondean: el redondeo pertenece exclusivamente a la capa de presentación.
    """
    if datos is None or datos.empty:
        return pd.DataFrame(columns=["datetime", "fecha", "value"])

    df = datos.copy()
    if columna_valor is None:
        columna_valor = "value" if "value" in df.columns else "spot"
    if columna_valor not in df.columns:
        raise ValueError("La serie SPOT no contiene una columna 'value' o 'spot'.")

    if "datetime" in df.columns:
        instante = pd.to_datetime(df["datetime"], errors="coerce")
    elif isinstance(df.index, pd.DatetimeIndex):
        instante = pd.Series(df.index, index=df.index)
    elif "fecha" in df.columns:
        instante = pd.to_datetime(df["fecha"], errors="coerce")
    else:
        raise ValueError("La serie SPOT no contiene fecha ni datetime.")

    periodos = pd.DataFrame(
        {
            "datetime": instante.to_numpy(),
            "value": pd.to_numeric(df[columna_valor], errors="coerce").to_numpy(),
        }
    ).dropna(subset=["datetime", "value"])
    periodos["fecha"] = periodos["datetime"].dt.floor("D")
    return periodos.sort_values("datetime").reset_index(drop=True)


def resumir_spot(datos, columna_valor=None):
    """Devuelve periodos y medias diaria, mensual y anual desde una sola base.

    Las medias mensual y anual se calculan directamente sobre los periodos
    originales. La media acumulada diaria usa suma/count acumulados, por lo que
    también es correcta con días de 23/25 horas, 92/100 QH o datos incompletos.
    """
    periodos = preparar_periodos_spot(datos, columna_valor=columna_valor)
    if periodos.empty:
        return {
            "periodos": periodos,
            "diario": pd.DataFrame(columns=[
                "fecha", "value", "suma_periodos", "numero_periodos",
                "media_acumulada", "año", "mes", "dia",
            ]),
            "mensual": pd.DataFrame(columns=[
                "año", "mes", "value", "numero_periodos",
            ]),
            "anual": pd.DataFrame(columns=[
                "año", "value", "numero_periodos",
            ]),
        }

    diario = (
        periodos.groupby("fecha", as_index=False)
        .agg(
            value=("value", "mean"),
            suma_periodos=("value", "sum"),
            numero_periodos=("value", "count"),
        )
        .sort_values("fecha")
    )
    diario["media_acumulada"] = (
        diario["suma_periodos"].cumsum()
        / diario["numero_periodos"].cumsum()
    )
    diario["año"] = diario["fecha"].dt.year
    diario["mes"] = diario["fecha"].dt.month
    diario["dia"] = diario["fecha"].dt.day

    periodos = periodos.assign(
        año=periodos["fecha"].dt.year,
        mes=periodos["fecha"].dt.month,
    )
    mensual = (
        periodos.groupby(["año", "mes"], as_index=False)
        .agg(value=("value", "mean"), numero_periodos=("value", "count"))
    )
    anual = (
        periodos.groupby("año", as_index=False)
        .agg(value=("value", "mean"), numero_periodos=("value", "count"))
    )
    return {
        "periodos": periodos,
        "diario": diario,
        "mensual": mensual,
        "anual": anual,
    }


def media_spot(datos, columna_valor=None):
    """Media aritmética de los periodos SPOT originales, sin redondear."""
    periodos = preparar_periodos_spot(datos, columna_valor=columna_valor)
    return None if periodos.empty else float(periodos["value"].mean())
