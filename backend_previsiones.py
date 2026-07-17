import pandas as pd
import streamlit as st

from backend_simulindex import (
    construir_curva_2026,
    obtener_historicos_meff,
    obtener_meff_mensual,
    obtener_meff_trimestral,
)


def _normalizar_spot_mensual(df_spot):
    """Normaliza históricos OMIE diarios/mensuales al formato de la curva híbrida."""
    df = df_spot.copy()

    if not isinstance(df.index, pd.DatetimeIndex):
        columna_fecha = next(
            (col for col in ("fecha", "fecha_entrega") if col in df.columns),
            None,
        )
        if columna_fecha is None:
            raise ValueError("El histórico OMIE no contiene una columna de fecha.")
        df[columna_fecha] = pd.to_datetime(df[columna_fecha])
        df = df.set_index(columna_fecha)
    else:
        df.index = pd.to_datetime(df.index)

    columna_spot = "spot" if "spot" in df.columns else "value"
    if columna_spot not in df.columns:
        raise ValueError("El histórico OMIE no contiene valores SPOT.")

    mensual = (
        df[[columna_spot]]
        .rename(columns={columna_spot: "spot"})
        .resample("M")
        .mean()
        .sort_index()
    )
    mensual["spot"] = pd.to_numeric(mensual["spot"], errors="coerce").round(2)
    return mensual


@st.cache_data(show_spinner=False)
def obtener_prevision_omie_anual(df_spot):
    """Devuelve la curva híbrida OMIE-OMIP y su resumen anual compartido."""
    df_spot_mensual = _normalizar_spot_mensual(df_spot)
    df_historicos_ftb, _ = obtener_historicos_meff()

    (
        df_ftb_trimestral,
        _,
        fecha_ultimo_omip_trimestral,
        _,
        _,
        _,
        _,
    ) = obtener_meff_trimestral(df_historicos_ftb)

    (
        df_ftb_mensual,
        _,
        _,
        _,
        _,
        _,
    ) = obtener_meff_mensual(df_historicos_ftb)

    curva_mensual = construir_curva_2026(
        df_spot_mensual,
        df_ftb_mensual,
        df_ftb_trimestral,
        fecha_ultimo_omip_trimestral,
    )
    media_anual = round(curva_mensual["precio"].mean(), 2)

    return {
        "año": int(curva_mensual["fecha"].dt.year.iloc[0]),
        "media_anual": media_anual,
        "fecha_corte": fecha_ultimo_omip_trimestral,
        "curva_mensual": curva_mensual,
    }


def guardar_prevision_omie_en_sesion(prevision):
    """Mantiene las claves históricas mientras los consumidores son migrados."""
    st.session_state.prevision_omie_anual = prevision
    st.session_state.precio_omie_previsto = prevision["media_anual"]
