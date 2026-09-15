import pandas as pd
import streamlit as st

from backend_simulindex import (
    construir_curva_2026,
    construir_curva_omip_mensual_12m,
    obtener_historicos_meff,
    obtener_meff_mensual,
    obtener_meff_trimestral,
)


@st.cache_data(show_spinner=False)
def obtener_prevision_omip_12m(fecha_ref=None):
    """Devuelve la curva y la media OMIP de los 12 meses móviles siguientes."""
    fecha_ref = pd.Timestamp(fecha_ref or pd.Timestamp.today()).normalize()
    historicos, _ = obtener_historicos_meff()
    trimestral = obtener_meff_trimestral(historicos)[0]
    mensual = obtener_meff_mensual(historicos)[0]
    curva = construir_curva_omip_mensual_12m(
        mensual,
        trimestral,
        fecha_ref,
    )
    return {
        "fecha_referencia": fecha_ref,
        "media_12m": round(curva["precio"].mean(), 2),
        "curva_mensual": curva,
    }


def guardar_prevision_omip_12m_en_sesion(prevision):
    """Publica una única previsión móvil para todos los comparadores."""
    st.session_state.prevision_omip_12m = prevision
    st.session_state.precio_omip_previsto = prevision["media_12m"]


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


def construir_curva_telemindex_con_omip_m(
    curva_mensual,
    df_ftb_mensual,
    fecha_ref=None,
    numero_cotizaciones=3,
):
    """Añade OMIP M a una copia de la curva usada solo por Telemindex.

    El precio de OMIP M es la media de las últimas cotizaciones disponibles
    del contrato con entrega en el mes en curso, igual que en SPO.
    """
    curva = curva_mensual.copy()
    if curva.empty or df_ftb_mensual.empty:
        return curva, None

    fecha_ref = pd.Timestamp.today() if fecha_ref is None else pd.Timestamp(fecha_ref)
    mes_ref = fecha_ref.to_period("M")
    futuros = df_ftb_mensual.copy()
    futuros["Fecha"] = pd.to_datetime(futuros["Fecha"], errors="coerce")
    futuros["Entrega_dt"] = pd.to_datetime(
        futuros["Entrega_dt"], errors="coerce"
    )
    futuros["Precio"] = pd.to_numeric(futuros["Precio"], errors="coerce")

    cotizaciones_m = futuros[
        futuros["Entrega_dt"].dt.to_period("M").eq(mes_ref)
        & futuros["Fecha"].le(fecha_ref)
    ].dropna(subset=["Fecha", "Precio"])
    cotizaciones_m = cotizaciones_m.sort_values("Fecha")

    if cotizaciones_m.empty:
        return curva, None

    ultimas = cotizaciones_m.tail(numero_cotizaciones)
    precio_omip_m = round(float(ultimas["Precio"].mean()), 2)
    fila_omip_m = pd.DataFrame([{
        "mes": mes_ref.month,
        "fecha": mes_ref.to_timestamp(),
        "precio": precio_omip_m,
        "tipo": "FTB mensual M",
    }])
    curva = pd.concat([curva, fila_omip_m], ignore_index=True)
    curva = curva.sort_values(["fecha", "tipo"]).reset_index(drop=True)

    return curva, {
        "entrega": mes_ref.to_timestamp(),
        "precio": precio_omip_m,
        "fecha_cotizacion": cotizaciones_m["Fecha"].max(),
        "numero_cotizaciones": len(ultimas),
    }


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
    curva_telemindex, omip_mes_actual = construir_curva_telemindex_con_omip_m(
        curva_mensual,
        df_ftb_mensual,
    )
    media_anual = round(curva_mensual["precio"].mean(), 2)

    return {
        "año": int(curva_mensual["fecha"].dt.year.iloc[0]),
        "media_anual": media_anual,
        "fecha_corte": fecha_ultimo_omip_trimestral,
        "curva_mensual": curva_mensual,
        "curva_telemindex": curva_telemindex,
        "omip_mes_actual": omip_mes_actual,
    }


def guardar_prevision_omie_en_sesion(prevision):
    """Mantiene las claves históricas mientras los consumidores son migrados."""
    st.session_state.prevision_omie_anual = prevision
    st.session_state.precio_omie_previsto = prevision["media_anual"]
