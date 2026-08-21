import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import requests
import glob
import numpy as np
from datetime import datetime,date
from backend_comun import aplicar_estilo
# Definimos los colores manualmente
COLOR_MIBGAS_2026 = "#ff69b4"
color_media_futuro = "#CC8DF0"

colores = {
    2024: "lightblue",
    2025: "#1E90FF",
    2026: COLOR_MIBGAS_2026
    #2025: "darkblue"
}




# función para crear un df según el producto
def filtrar_por_producto(df, producto):
    df_f = df[df['producto'] == producto].copy()
    #df_f['fecha'] = pd.to_datetime(df_f['fecha'], dayfirst=True, errors='coerce')
    #df_f['fecha_entrega'] = pd.to_datetime(df_f['fecha_entrega'], dayfirst=False, errors='coerce').dt.date
    #df_f['año_entrega'] = df_f['fecha_entrega'].dt.year
    return df_f

def graficar_futuros_mibgas(df_mg, tipo="Q"):
    """
    tipo="M" -> futuros mensuales
    tipo="Q" -> futuros trimestrales
    tipo="Y" -> futuros anuales
    """

    df_mg = df_mg.copy()

    # Asegurar fechas
    df_mg["Trading day"] = pd.to_datetime(df_mg["Trading day"])
    df_mg["fecha_entrega"] = pd.to_datetime(df_mg["fecha_entrega"])

    # =====================================================
    # 1. Crear etiqueta de producto según tipo
    # =====================================================
    if tipo == "M":
        col_periodo = "mes"

        df_mg[col_periodo] = df_mg["fecha_entrega"].dt.strftime("%Y-%m")

        def _key(lbl):
            return pd.Period(lbl, freq="M")

        titulo = "Evolución de MIBGAS para los próximos meses"
        nombre_leyenda = "Mes"
        num_periodos = 6

    elif tipo == "Q":
        col_periodo = "trimestre"

        df_mg[col_periodo] = (
            "Q"
            + df_mg["fecha_entrega"].dt.quarter.astype(str)
            + "-"
            + df_mg["fecha_entrega"].dt.year.astype(str)
        )

        def _key(lbl):
            q, y = lbl.split("-")
            return (int(y), int(q[1]))

        titulo = "Evolución de MIBGAS para los próximos trimestres"
        nombre_leyenda = "Trimestre"
        num_periodos = 4

    elif tipo == "Y":
        col_periodo = "año"

        df_mg[col_periodo] = (
            "Y-"
            + df_mg["fecha_entrega"].dt.year.astype(str)
        )

        def _key(lbl):
            return int(lbl.split("-")[1])

        titulo = "Evolución de MIBGAS para los próximos años"
        nombre_leyenda = "Año"
        num_periodos = 4

    else:
        raise ValueError("tipo debe ser 'M', 'Q' o 'Y'")

    # =====================================================
    # 2. Ordenar y quedarnos con los últimos periodos
    # =====================================================
    labels = sorted(df_mg[col_periodo].dropna().unique(), key=_key)
    labels = labels[-num_periodos:]

    df_win = df_mg[df_mg[col_periodo].isin(labels)].copy()

    cat = pd.api.types.CategoricalDtype(categories=labels, ordered=True)
    df_win[col_periodo] = df_win[col_periodo].astype(cat)

    df_win = df_win.sort_values(["Trading day", col_periodo])

    # =====================================================
    # 3. Pivotar
    # =====================================================
    df_pivot = (
        df_win
        .pivot(index="Trading day", columns=col_periodo, values="precio_gas")
        .reset_index()
    )

    # =====================================================
    # 4. Colores
    # =====================================================
    palette = px.colors.sequential.Blues[2:8]

    color_map = {
        labels[i]: palette[i]
        for i in range(len(labels))
    }

    # =====================================================
    # 5. Gráfico
    # =====================================================
    fig = px.line(
        df_pivot,
        x="Trading day",
        y=df_pivot.columns[1:],
        labels={
            "value": "€/MWh",
            "variable": nombre_leyenda
        },
        color_discrete_map=color_map,
        title=titulo,
    )

    fig.update_layout(
        hovermode="x unified",
        title_font_size=28,
        title={
            "x": 0.5,
            "xanchor": "center"
        },
        hoverlabel=dict(font_size=18)
    )

    fig.update_xaxes(
        hoverformat="%Y-%m-%d"
    )

    fig.update_traces(
        hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>"
    )

    return fig

def graficar_qs(df_mg_q):
    #df_mg_q['Trading day'] = pd.to_datetime(df_mg_q['Trading day'])
    #df_mg_q['fecha_entrega'] = pd.to_datetime(df_mg_q['fecha_entrega'])

    # Crear columna 'trimestre'
    df_mg_q["trimestre"] = ("Q" + df_mg_q["fecha_entrega"].dt.quarter.astype(str) + "-" + df_mg_q["fecha_entrega"].dt.year.astype(str))

    def _key(lbl):
        q, y = lbl.split("-")
        return (int(y), int(q[1]))  # (año, nº de Q)

    uniq = sorted(df_mg_q["trimestre"].unique(), key=_key)
    labels = uniq[-4:]  # últimos 4 trimestres que haya en el df

    df_win = df_mg_q[df_mg_q["trimestre"].isin(labels)].copy()
    cat = pd.api.types.CategoricalDtype(categories=labels, ordered=True)
    df_win["trimestre"] = df_win["trimestre"].astype(cat)
    df_win = df_win.sort_values(["Trading day", "trimestre"])

    # Pivotar para tener cada trimestre en una columna
    df_pivot = df_win.pivot(index="Trading day", columns="trimestre", values="precio_gas").reset_index()


    #escala de azules (oscuro → claro)
    palette = px.colors.sequential.Blues[3:7]  # 4 tonos (ajusta si necesitas más/menos)

    # tus trimestres ya están en orden en 'labels'
    color_map = {labels[i]: palette[i] for i in range(len(labels))}
    # Gráfico con varias columnas como "wide form"
    fig = px.line(
        df_pivot,
        x="Trading day",
        y=df_pivot.columns[1:], 
        #color="trimestre",
        labels={'value':'€/MWh', 'variable':'Trimestre'},
        color_discrete_map=color_map, # todas las columnas de trimestres
        title='Evolución de MIBGAS para los próximos trimestres',
        #height=800
    )

    # Ajustar el tooltip para que muestre todas las series
    # 1) Un solo tooltip por x (Trading day)
    fig.update_layout(
        hovermode="x unified",
        title_font_size=28, 
        title={'x':0.5, 'xanchor':'center'},
        hoverlabel=dict(font_size=18)
        )

    # 2) Formato de la fecha en el encabezado del tooltip
    fig.update_xaxes(
        hoverformat="%Y-%m-%d",
        
    )

    # 3) Contenido de cada fila del tooltip (nombre del Q y su valor)
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>")

  
    
    return fig

def graficar_da_corrido(df):

    df = df.copy()

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])

    fig = px.line(
        df,
        x="fecha_entrega",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        title="Evolución del precio de MIBGAS D+1 por año",
    )

    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Fecha",
        yaxis_title="Precio gas (€/MWh)",
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        ),

        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            tickmode="linear",
            dtick="M1",
        ),

        hoverlabel=dict(
            font_size=18,
            # bgcolor="rgba(255,255,255,0.75)",  # opcional si quieres transparencia
        )
    )

    fig.update_traces(
        hovertemplate=(
            "<b>%{x|%d/%m/%Y}</b><br>"
            "MIBGAS D+1: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_da_2026_acumulado(df, año=2026, mes=None):

    df = df.copy()
    if mes is None:
        inicio_periodo = pd.Timestamp(year=año, month=1, day=1)
        fin_periodo = pd.Timestamp(year=año, month=12, day=31)
        periodo_titulo = str(año)
    else:
        inicio_periodo = pd.Timestamp(year=año, month=mes, day=1)
        fin_periodo = inicio_periodo + pd.offsets.MonthEnd(0)
        periodo_titulo = inicio_periodo.strftime("%B %Y")

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df[df["fecha_entrega"].dt.year == año].copy()
    if mes is not None:
        df = df[df["fecha_entrega"].dt.month == mes].copy()
    df = df.sort_values("fecha_entrega")

    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            title_font_size=28,
            title={
                "text": f"No hay datos MIBGAS D+1 para {periodo_titulo}",
                "x": 0.5,
                "xanchor": "center"
            },
            xaxis_title="Fecha",
            yaxis_title="Precio gas (€/MWh)",
            hoverlabel=dict(font_size=18)
        )
        fig.update_xaxes(range=[inicio_periodo, fin_periodo])
        fig = aplicar_estilo(fig)
        return fig

    df["media_acumulada_gas"] = df["precio_gas"].expanding().mean()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["fecha_entrega"],
        y=df["precio_gas"],
        mode="lines",
        name="Precio diario",
        line=dict(color=colores.get(año, COLOR_MIBGAS_2026), width=2),
        hovertemplate=(
            "MIBGAS D+1: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    ))

    fig.add_trace(go.Scatter(
        x=df["fecha_entrega"],
        y=df["media_acumulada_gas"],
        mode="lines",
        name="Media acumulada diaria",
        line=dict(color="gold", width=3, dash="dot"),
        hovertemplate=(
            "Media acumulada: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    ))

    fig.update_layout(
        title_font_size=28,
        title={
            "text": f"Evolución diaria y media acumulada MIBGAS D+1 {periodo_titulo}",
            "x": 0.5,
            "xanchor": "center"
        },
        xaxis_title="Fecha",
        yaxis_title="Precio gas (€/MWh)",
        hovermode="x unified",
        hoverlabel=dict(font_size=18),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        )
    )

    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        tickmode="linear",
        dtick="D2" if mes is not None else "M1",
        range=[inicio_periodo, fin_periodo],
        hoverformat="%d/%m/%Y"
    )

    fig = aplicar_estilo(fig)

    return fig


def graficar_comparativa_gas_mensual(
    df,
    mes,
    año_actual,
    año_comparacion=2025,
):
    """Compara precio diario y media acumulada MIBGAS D+1 por día."""
    datos = df.copy()
    datos["fecha_entrega"] = pd.to_datetime(
        datos["fecha_entrega"], errors="coerce"
    )
    datos["precio_gas"] = pd.to_numeric(
        datos["precio_gas"], errors="coerce"
    )
    datos = datos[
        (datos["fecha_entrega"].dt.month == mes)
        & datos["fecha_entrega"].dt.year.isin(
            [año_actual, año_comparacion]
        )
    ].dropna(subset=["fecha_entrega", "precio_gas"])
    diario = (
        datos.assign(año=lambda tabla: tabla["fecha_entrega"].dt.year)
        .groupby(["año", "fecha_entrega"], as_index=False)["precio_gas"]
        .mean()
        .sort_values(["año", "fecha_entrega"])
    )
    diario["día"] = diario["fecha_entrega"].dt.day
    diario["media_acumulada"] = (
        diario.groupby("año")["precio_gas"]
        .expanding()
        .mean()
        .reset_index(level=0, drop=True)
    )

    figura = go.Figure()
    colores_años = {
        año_actual: colores.get(año_actual, COLOR_MIBGAS_2026),
        año_comparacion: colores.get(año_comparacion, "#1E90FF"),
    }
    for año in (año_actual, año_comparacion):
        serie = diario[diario["año"] == año]
        if serie.empty:
            continue
        figura.add_trace(go.Scatter(
            x=serie["día"],
            y=serie["precio_gas"],
            mode="lines+markers",
            name=str(año),
            line=dict(
                color=colores_años[año],
                width=3.5 if año == año_actual else 2.5,
            ),
            marker=dict(size=5),
            hovertemplate=(
                f"{año} · día "
                "%{x}: %{y:.2f} €/MWh<extra></extra>"
            ),
        ))
        figura.add_trace(go.Scatter(
            x=serie["día"],
            y=serie["media_acumulada"],
            mode="lines",
            name=f"Media acumulada {año}",
            line=dict(
                color=colores_años[año],
                width=3,
                dash="dot",
            ),
            hovertemplate=(
                f"Media acumulada {año} · día "
                "%{x}: %{y:.2f} €/MWh<extra></extra>"
            ),
        ))

    figura.update_layout(
        title="",
        hovermode="x unified",
        legend_title_text="",
    )
    figura.update_xaxes(
        title_text="Día",
        tickmode="linear",
        tick0=1,
        dtick=2,
        range=[1, 31],
        showgrid=True,
    )
    figura.update_yaxes(
        title_text="MIBGAS D+1 €/MWh",
        rangemode="tozero",
        showgrid=True,
    )
    return diario, aplicar_estilo(figura)


def construir_comparativa_diaria_mibgas_omie(
    df_mg_da, df_spot_diario, año=2026
):
    """Alinea por fecha MIBGAS D+1 y el precio medio diario de OMIE."""
    df_gas = df_mg_da[["fecha_entrega", "precio_gas"]].copy()
    df_gas["fecha"] = pd.to_datetime(
        df_gas["fecha_entrega"], errors="coerce"
    ).dt.normalize()
    df_gas["mibgas_d1"] = pd.to_numeric(
        df_gas["precio_gas"], errors="coerce"
    )
    df_gas = (
        df_gas
        .dropna(subset=["fecha", "mibgas_d1"])
        .groupby("fecha", as_index=False)["mibgas_d1"]
        .mean()
    )

    df_omie = df_spot_diario[["fecha", "spot"]].copy()
    df_omie["fecha"] = pd.to_datetime(
        df_omie["fecha"], errors="coerce"
    ).dt.normalize()
    df_omie["omie"] = pd.to_numeric(df_omie["spot"], errors="coerce")
    df_omie = (
        df_omie
        .dropna(subset=["fecha", "omie"])
        .groupby("fecha", as_index=False)["omie"]
        .mean()
    )

    df_comparativa = (
        df_gas
        .merge(df_omie[["fecha", "omie"]], on="fecha", how="inner")
        .sort_values("fecha")
    )
    if año is not None:
        df_comparativa = df_comparativa[
            df_comparativa["fecha"].dt.year == año
        ].copy()
    df_comparativa["rel_omie_gas"] = np.where(
        df_comparativa["mibgas_d1"].ne(0),
        df_comparativa["omie"] / df_comparativa["mibgas_d1"],
        np.nan,
    )
    df_comparativa["mibgas_d1"] = df_comparativa["mibgas_d1"].round(2)
    df_comparativa["omie"] = df_comparativa["omie"].round(2)
    df_comparativa["rel_omie_gas"] = df_comparativa[
        "rel_omie_gas"
    ].round(4)

    return df_comparativa.reset_index(drop=True)


def construir_resumen_mensual_omie_mibgas(
    df_comparativa_diaria, año_inicio=2024
):
    """Resume medias diarias y la media mensual de los ratios diarios."""
    columnas = [
        "año", "mes", "fecha_mes", "mibgas_medio", "omie_medio",
        "ratio_medio_diario", "dias_con_datos",
    ]
    if df_comparativa_diaria.empty:
        return pd.DataFrame(columns=columnas)

    df = df_comparativa_diaria.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    for columna in ("mibgas_d1", "omie", "rel_omie_gas"):
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    df = df.dropna(
        subset=["fecha", "mibgas_d1", "omie", "rel_omie_gas"]
    )
    df = df[df["fecha"].dt.year >= año_inicio].copy()
    df["año"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month

    resumen = (
        df.groupby(["año", "mes"], as_index=False)
        .agg(
            mibgas_medio=("mibgas_d1", "mean"),
            omie_medio=("omie", "mean"),
            ratio_medio_diario=("rel_omie_gas", "mean"),
            dias_con_datos=("fecha", "nunique"),
        )
        .sort_values(["año", "mes"])
    )
    resumen["fecha_mes"] = pd.to_datetime(
        dict(
            year=resumen["año"],
            month=resumen["mes"],
            day=1,
        )
    )
    resumen["mibgas_medio"] = resumen["mibgas_medio"].round(2)
    resumen["omie_medio"] = resumen["omie_medio"].round(2)
    resumen["ratio_medio_diario"] = resumen[
        "ratio_medio_diario"
    ].round(4)

    return resumen[columnas].reset_index(drop=True)


def estimar_omie_mensual_desde_gas(
    df_resumen_mensual, gas_eur_mwh, mes, año_objetivo
):
    """Estima OMIE con ratios del mismo mes en años anteriores."""
    historico = df_resumen_mensual[
        (df_resumen_mensual["mes"] == int(mes))
        & (df_resumen_mensual["año"] < int(año_objetivo))
    ].copy()
    historico = historico.dropna(subset=["ratio_medio_diario"])
    if historico.empty:
        return None

    ratio_medio = float(historico["ratio_medio_diario"].mean())
    ratio_minimo = float(historico["ratio_medio_diario"].min())
    ratio_maximo = float(historico["ratio_medio_diario"].max())
    gas = float(gas_eur_mwh)
    return {
        "omie_estimado": gas * ratio_medio,
        "omie_minimo": gas * ratio_minimo,
        "omie_maximo": gas * ratio_maximo,
        "ratio_medio": ratio_medio,
        "ratio_minimo": ratio_minimo,
        "ratio_maximo": ratio_maximo,
        "años_utilizados": historico["año"].astype(int).tolist(),
        "num_observaciones": len(historico),
        "detalle": historico,
    }


def ajustar_modelo_lineal_omie_gas(
    df_resumen_mensual, gas_eur_mwh, min_dias=20, ultimos_meses=None
):
    """Ajusta OMIE mensual = intercepto + pendiente * MIBGAS mensual."""
    datos = df_resumen_mensual[
        df_resumen_mensual["dias_con_datos"] >= int(min_dias)
    ].dropna(
        subset=["mibgas_medio", "omie_medio", "ratio_medio_diario"]
    ).sort_values("fecha_mes").copy()
    if ultimos_meses is not None:
        datos = datos.tail(int(ultimos_meses)).copy()
    if len(datos) < 3 or datos["mibgas_medio"].nunique() < 2:
        return None

    x = datos["mibgas_medio"].to_numpy(dtype=float)
    y = datos["omie_medio"].to_numpy(dtype=float)
    pendiente, intercepto = np.polyfit(x, y, 1)
    ajustado = intercepto + pendiente * x
    residuos = y - ajustado
    suma_residuos = float(np.sum(residuos ** 2))
    suma_total = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - suma_residuos / suma_total if suma_total else 0.0
    rmse = float(np.sqrt(np.mean(residuos ** 2)))
    gas = float(gas_eur_mwh)
    omie_estimado = intercepto + pendiente * gas
    correlacion_ratio_gas = float(np.corrcoef(
        datos["mibgas_medio"].to_numpy(dtype=float),
        datos["ratio_medio_diario"].to_numpy(dtype=float),
    )[0, 1])
    datos["omie_ajustado"] = ajustado

    return {
        "omie_estimado": omie_estimado,
        "omie_inferior_orientativo": omie_estimado - 1.96 * rmse,
        "omie_superior_orientativo": omie_estimado + 1.96 * rmse,
        "pendiente": float(pendiente),
        "intercepto": float(intercepto),
        "r2": r2,
        "rmse": rmse,
        "correlacion_ratio_gas": correlacion_ratio_gas,
        "num_observaciones": len(datos),
        "ultimos_meses": ultimos_meses,
        "datos": datos,
    }


def graficar_diagnostico_ratio_gas(df_resumen_mensual):
    """Visualiza la relación entre gas mensual y media de ratios diarios."""
    datos = df_resumen_mensual[
        df_resumen_mensual["dias_con_datos"] >= 20
    ].dropna(
        subset=["mibgas_medio", "ratio_medio_diario"]
    ).copy()
    fig = px.scatter(
        datos,
        x="mibgas_medio",
        y="ratio_medio_diario",
        color=datos["año"].astype(str),
        custom_data=["fecha_mes", "omie_medio", "dias_con_datos"],
        labels={
            "mibgas_medio": "MIBGAS medio (€/MWh)",
            "ratio_medio_diario": "Media ratios diarios OMIE/Gas",
            "color": "Año",
        },
        title="¿Disminuye el ratio cuando aumenta el gas?",
    )
    if len(datos) >= 2 and datos["mibgas_medio"].nunique() >= 2:
        pendiente, intercepto = np.polyfit(
            datos["mibgas_medio"], datos["ratio_medio_diario"], 1
        )
        x_linea = np.linspace(
            datos["mibgas_medio"].min(),
            datos["mibgas_medio"].max(),
            100,
        )
        fig.add_trace(go.Scatter(
            x=x_linea,
            y=intercepto + pendiente * x_linea,
            mode="lines",
            name="Tendencia",
            line=dict(color="#E74C3C", dash="dash"),
            hoverinfo="skip",
        ))
    fig.update_traces(
        marker=dict(size=10),
        hovertemplate=(
            "<b>%{customdata[0]|%b %Y}</b><br>"
            "MIBGAS: %{x:.2f} €/MWh<br>"
            "Ratio medio diario: %{y:.3f}<br>"
            "OMIE: %{customdata[1]:.2f} €/MWh<br>"
            "Días: %{customdata[2]}"
            "<extra></extra>"
        ),
        selector=dict(mode="markers"),
    )
    fig.update_layout(
        title={"x": 0.5, "xanchor": "center"},
        height=500,
    )
    fig = aplicar_estilo(fig)
    fig.update_layout(height=500)
    return fig


def graficar_modelo_lineal_omie_gas(
    modelo,
    gas_eur_mwh,
    titulo="Modelo lineal mensual OMIE vs MIBGAS",
    etiqueta_objetivo="Estimación",
    destacar_objetivo=False,
    mes_objetivo=None,
):
    """Dibuja observaciones mensuales, recta y punto OMIE estimado."""
    datos = modelo["datos"]
    x_min = min(float(datos["mibgas_medio"].min()), float(gas_eur_mwh))
    x_max = max(float(datos["mibgas_medio"].max()), float(gas_eur_mwh))
    margen = max((x_max - x_min) * 0.08, 1.0)
    x_linea = np.linspace(x_min - margen, x_max + margen, 120)
    y_linea = modelo["intercepto"] + modelo["pendiente"] * x_linea

    datos_grafico = datos.copy()
    datos_grafico["periodo_hover"] = pd.to_datetime(
        datos_grafico["fecha_mes"]
    ).dt.strftime("%m/%Y")
    fig = px.scatter(
        datos_grafico,
        x="mibgas_medio",
        y="omie_medio",
        color=datos["año"].astype(str),
        custom_data=[
            "periodo_hover", "ratio_medio_diario", "dias_con_datos"
        ],
        labels={
            "mibgas_medio": "MIBGAS medio (€/MWh)",
            "omie_medio": "OMIE medio (€/MWh)",
            "color": "Año",
        },
        title=titulo,
    )
    fig.update_traces(
        marker=dict(size=10),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "MIBGAS: %{x:.2f} €/MWh<br>"
            "OMIE: %{y:.2f} €/MWh<br>"
            "Ratio medio diario: %{customdata[1]:.3f}<br>"
            "Días: %{customdata[2]}"
            "<extra></extra>"
        ),
        selector=dict(mode="markers"),
    )
    if destacar_objetivo and mes_objetivo is not None:
        datos_mismo_mes = datos_grafico[
            datos_grafico["mes"].astype(int) == int(mes_objetivo)
        ]
        if not datos_mismo_mes.empty:
            fig.add_trace(go.Scatter(
                x=datos_mismo_mes["mibgas_medio"],
                y=datos_mismo_mes["omie_medio"],
                mode="markers",
                name=f"Histórico mes {int(mes_objetivo):02d}",
                customdata=datos_mismo_mes[
                    ["periodo_hover", "ratio_medio_diario", "dias_con_datos"]
                ].to_numpy(),
                marker=dict(
                    color="#FF8C00",
                    size=18,
                    symbol="square",
                    line=dict(color="white", width=2),
                ),
                hovertemplate=(
                    "<b>%{customdata[0]} · mismo mes objetivo</b><br>"
                    "MIBGAS: %{x:.2f} €/MWh<br>"
                    "OMIE: %{y:.2f} €/MWh<br>"
                    "Ratio medio diario: %{customdata[1]:.3f}<br>"
                    "Días: %{customdata[2]}"
                    "<extra></extra>"
                ),
            ))
    fig.add_trace(go.Scatter(
        x=x_linea,
        y=y_linea,
        mode="lines",
        name="Ajuste lineal",
        line=dict(color="#F4D03F", width=3),
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=[gas_eur_mwh],
        y=[modelo["omie_estimado"]],
        mode="markers",
        name=etiqueta_objetivo,
        marker=dict(
            color="#E74C3C",
            size=20 if destacar_objetivo else 15,
            symbol="square" if destacar_objetivo else "diamond",
            line=dict(color="white", width=2),
        ),
        hovertemplate=(
            f"<b>{etiqueta_objetivo}</b><br>"
            "Gas simulado: %{x:.2f} €/MWh<br>"
            "OMIE estimado: %{y:.2f} €/MWh"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        title={"x": 0.5, "xanchor": "center"},
        height=500,
    )
    fig = aplicar_estilo(fig)
    fig.update_layout(height=500)
    return fig


def graficar_comparativa_diaria_mibgas_omie(df_comparativa, año=2026):
    """Compara las cotizaciones diarias MIBGAS D+1 y OMIE."""
    inicio_año = pd.Timestamp(year=año, month=1, day=1)
    fin_año = pd.Timestamp(year=año, month=12, day=31)
    fig = go.Figure()

    if not df_comparativa.empty:
        fig.add_trace(go.Scatter(
            x=df_comparativa["fecha"],
            y=df_comparativa["mibgas_d1"],
            mode="lines",
            name="MIBGAS D+1",
            line=dict(color=colores.get(año, COLOR_MIBGAS_2026), width=2),
            hovertemplate="MIBGAS D+1: %{y:.2f} €/MWh<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=df_comparativa["fecha"],
            y=df_comparativa["omie"],
            mode="lines",
            name="OMIE",
            line=dict(color="#2ECC71", width=2),
            hovertemplate="OMIE: %{y:.2f} €/MWh<extra></extra>",
        ))

    titulo = f"Evolución diaria MIBGAS D+1 vs OMIE {año}"
    if df_comparativa.empty:
        titulo = f"No hay datos coincidentes MIBGAS D+1 y OMIE para {año}"

    fig.update_layout(
        title_font_size=28,
        title={"text": titulo, "x": 0.5, "xanchor": "center"},
        xaxis_title="Fecha",
        yaxis_title="Precio (€/MWh)",
        hovermode="x unified",
        hoverlabel=dict(font_size=18),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        tickmode="linear",
        dtick="M1",
        range=[inicio_año, fin_año],
        hoverformat="%d/%m/%Y",
    )

    return aplicar_estilo(fig)


def construir_relacion_horaria_omie_mibgas(df_mg_da, df_spot_horario, año=2026):
    """Cruza el SPOT horario con el MIBGAS D+1 de cada día."""
    columnas_salida = [
        "fecha", "mes", "dia", "hora", "omie", "mibgas_d1",
        "rel_omie_gas",
    ]
    columnas_spot = {"fecha", "hora", "spot"}
    if not columnas_spot.issubset(df_spot_horario.columns):
        return pd.DataFrame(columns=columnas_salida)

    df_gas = df_mg_da[["fecha_entrega", "precio_gas"]].copy()
    df_gas["fecha"] = pd.to_datetime(
        df_gas["fecha_entrega"], errors="coerce"
    ).dt.normalize()
    df_gas["mibgas_d1"] = pd.to_numeric(
        df_gas["precio_gas"], errors="coerce"
    )
    df_gas = (
        df_gas
        .dropna(subset=["fecha", "mibgas_d1"])
        .groupby("fecha", as_index=False)["mibgas_d1"]
        .mean()
    )

    df_omie = df_spot_horario[["fecha", "hora", "spot"]].copy()
    df_omie["fecha"] = pd.to_datetime(
        df_omie["fecha"], errors="coerce"
    ).dt.normalize()
    df_omie["hora"] = pd.to_numeric(df_omie["hora"], errors="coerce")
    df_omie["omie"] = pd.to_numeric(df_omie["spot"], errors="coerce")
    df_omie = (
        df_omie
        .dropna(subset=["fecha", "hora", "omie"])
        .groupby(["fecha", "hora"], as_index=False)["omie"]
        .mean()
    )

    df_relacion = df_omie.merge(df_gas, on="fecha", how="inner")
    df_relacion = df_relacion[
        df_relacion["fecha"].dt.year == año
    ].copy()
    df_relacion = df_relacion[df_relacion["mibgas_d1"].ne(0)]
    df_relacion["rel_omie_gas"] = (
        df_relacion["omie"] / df_relacion["mibgas_d1"]
    )
    df_relacion["mes"] = df_relacion["fecha"].dt.month
    df_relacion["dia"] = df_relacion["fecha"].dt.day
    df_relacion["hora"] = df_relacion["hora"].astype(int)
    df_relacion["omie"] = df_relacion["omie"].round(2)
    df_relacion["mibgas_d1"] = df_relacion["mibgas_d1"].round(2)
    df_relacion["rel_omie_gas"] = df_relacion[
        "rel_omie_gas"
    ].round(4)

    return (
        df_relacion[columnas_salida]
        .sort_values(["fecha", "hora"])
        .reset_index(drop=True)
    )


def graficar_mapa_calor_relacion_omie_mibgas(df_relacion, año=2026):
    """Mapa anual de la relación horaria OMIE/MIBGAS."""
    if df_relacion.empty:
        fig = go.Figure()
        fig.update_layout(
            title={
                "text": f"No hay datos horarios OMIE/MIBGAS para {año}",
                "x": 0.5,
                "xanchor": "center",
            },
            xaxis_title="Hora",
            yaxis_title="Día",
            height=650,
        )
        fig = aplicar_estilo(fig)
        fig.update_layout(height=650)
        return fig

    df = df_relacion.copy()
    horas = list(range(int(df["hora"].min()), int(df["hora"].max()) + 1))
    fechas = pd.date_range(df["fecha"].min(), df["fecha"].max(), freq="D")

    def matriz(columna):
        return (
            df.pivot_table(
                index="fecha",
                columns="hora",
                values=columna,
                aggfunc="mean",
            )
            .reindex(index=fechas, columns=horas)
        )

    matriz_rel = matriz("rel_omie_gas")
    matriz_omie = matriz("omie")
    matriz_gas = matriz("mibgas_d1")
    etiquetas_fecha = [fecha.strftime("%d-%b") for fecha in fechas]

    valores = df["rel_omie_gas"].replace([np.inf, -np.inf], np.nan).dropna()
    distancia_centro = max(
        abs(float(valores.quantile(0.02)) - 1),
        abs(float(valores.quantile(0.98)) - 1),
        0.01,
    )
    limite_inferior = 1 - distancia_centro
    limite_superior = 1 + distancia_centro

    customdata = np.dstack([
        matriz_omie.to_numpy(),
        matriz_gas.to_numpy(),
    ])
    fig = go.Figure(go.Heatmap(
        x=horas,
        y=etiquetas_fecha,
        z=matriz_rel.to_numpy(),
        customdata=customdata,
        colorscale="RdBu_r",
        zmin=limite_inferior,
        zmid=1,
        zmax=limite_superior,
        colorbar=dict(title="OMIE/Gas"),
        hovertemplate=(
            "<b>%{y} · hora %{x}</b><br>"
            "Rel. OMIE/Gas: %{z:.2f}<br>"
            "OMIE: %{customdata[0]:.2f} €/MWh<br>"
            "MIBGAS D+1: %{customdata[1]:.2f} €/MWh"
            "<extra></extra>"
        ),
        hoverongaps=False,
    ))

    primer_dia_mes = [
        i for i, fecha in enumerate(fechas)
        if fecha.day == 1 or i == 0
    ]
    ticktext = [fechas[i].strftime("%d-%b") for i in primer_dia_mes]
    altura_mapa = max(850, len(fechas) * 5)
    fig.update_layout(
        title={
            "text": f"Relación horaria OMIE / MIBGAS D+1 · {año}",
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 28},
        },
        xaxis_title="Hora",
        yaxis_title="Día y mes",
        height=altura_mapa,
        hoverlabel=dict(font_size=16),
        margin=dict(l=75, r=30, t=90, b=50),
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=horas,
        ticktext=[f"{hora:02d}" for hora in horas],
        side="bottom",
    )
    fig.update_yaxes(
        tickmode="array",
        tickvals=ticktext,
        ticktext=ticktext,
        autorange="reversed",
    )

    fig = aplicar_estilo(fig)
    fig.update_layout(height=altura_mapa)
    return fig


def graficar_relacion_omie_mibgas_por_mes(df_relacion, año=2026):
    """Compara la relación media OMIE/MIBGAS de cada mes."""
    meses = {
        1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
        5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
    }
    resumen = (
        df_relacion
        .groupby("mes", as_index=False)["rel_omie_gas"]
        .mean()
        .sort_values("mes")
    )
    resumen["mes_nombre"] = resumen["mes"].map(meses)
    resumen["es_maximo"] = False
    if not resumen.empty:
        resumen.loc[
            resumen["rel_omie_gas"].idxmax(), "es_maximo"
        ] = True

    colores_barras = np.where(
        resumen["es_maximo"], "#E74C3C", "#4C78A8"
    )
    fig = go.Figure(go.Bar(
        x=resumen["mes_nombre"],
        y=resumen["rel_omie_gas"],
        marker_color=colores_barras,
        text=resumen["rel_omie_gas"].map(lambda valor: f"{valor:.2f}"),
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Relación media OMIE/Gas: %{y:.2f}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        title={
            "text": f"Relación media OMIE / MIBGAS por mes · {año}",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Mes",
        yaxis_title="Relación media OMIE/Gas",
        showlegend=False,
        height=480,
    )
    fig = aplicar_estilo(fig)
    fig.update_layout(height=480)
    return fig, resumen


def graficar_relacion_omie_mibgas_por_hora(df_relacion, año=2026):
    """Compara la relación media OMIE/MIBGAS de cada hora."""
    resumen = (
        df_relacion
        .groupby("hora", as_index=False)["rel_omie_gas"]
        .mean()
        .sort_values("hora")
    )
    resumen["es_maximo"] = False
    if not resumen.empty:
        resumen.loc[
            resumen["rel_omie_gas"].idxmax(), "es_maximo"
        ] = True

    colores_barras = np.where(
        resumen["es_maximo"], "#E74C3C", "#4C78A8"
    )
    fig = go.Figure(go.Bar(
        x=resumen["hora"],
        y=resumen["rel_omie_gas"],
        marker_color=colores_barras,
        text=resumen["rel_omie_gas"].map(lambda valor: f"{valor:.2f}"),
        textposition="outside",
        hovertemplate=(
            "<b>Hora %{x}</b><br>"
            "Relación media OMIE/Gas: %{y:.2f}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        title={
            "text": f"Relación media OMIE / MIBGAS por hora · {año}",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Hora",
        yaxis_title="Relación media OMIE/Gas",
        showlegend=False,
        height=480,
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=resumen["hora"],
        ticktext=[f"{int(hora):02d}" for hora in resumen["hora"]],
    )
    fig = aplicar_estilo(fig)
    fig.update_layout(height=480)
    return fig, resumen


def graficar_da_comparado(df):

    df = df.copy()

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])

    # Clave interna para ordenar: 01-01, 01-02, ..., 12-31
    df["mmdd"] = df["fecha_entrega"].dt.strftime("%m-%d")

    # Etiqueta visible día-mes
    if "fecha_corta" not in df.columns:
        df["fecha_corta"] = df["fecha_entrega"].dt.strftime("%d-%m")

    # Orden cronológico real por mes-día
    orden_mmdd = sorted(
        df["mmdd"].unique(),
        key=lambda s: (int(s[:2]), int(s[3:]))
    )

    # Mapa mmdd -> fecha_corta
    mapa_fechas = (
        df.drop_duplicates("mmdd")
          .set_index("mmdd")["fecha_corta"]
          .to_dict()
    )

    orden_fechas = [mapa_fechas[v] for v in orden_mmdd]

    # Esta será la X visible y también la cabecera del hover
    df["dia_mes"] = df["mmdd"].map(mapa_fechas)

    fig = px.line(
        df,
        x="dia_mes",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        category_orders={"dia_mes": orden_fechas},
        title="Comparación anual del precio del gas (2024 al 2026)",
    )

    # Etiquetas del eje X cada 15 días
    tickvals = orden_fechas[::15]

    fig.update_xaxes(
        tickmode="array",
        tickvals=tickvals,
        ticktext=tickvals,
        tickangle=0,
        type="category"
    )

    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
        hovermode="x unified",
        hoverlabel=dict(
            font_size=18,
        ),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        )
    )

    # En el hover saldrán todos los años juntos para ese día-mes
    fig.update_traces(
        hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>"
    )

    # Líneas verticales al inicio de cada mes
    cortes_mes = [mapa_fechas[v] for v in orden_mmdd if v.endswith("-01")]

    for dia_mes in cortes_mes:
        fig.add_vline(
            x=dia_mes,
            line_width=1,
            line_dash="dot",
            line_color="rgba(200,200,200,0.2)"
        )

    fig = aplicar_estilo(fig)

    return fig

def graficar_da_comparado_old(df):

    df = df.copy()

      # Claves para orden y etiqueta
    df["mmdd"] = df["fecha_entrega"].dt.strftime("%m-%d")  # '02-29', '10-21', ...
    # Linux/Mac: %-d ; Windows: %#d  (elige el que corresponda)
    

    # Orden cronológico sin datetime: (MM, DD)
    orden_mmdd = sorted(
        df["mmdd"].unique(),
        key=lambda s: (int(s[:2]), int(s[3:]))
    )

    print('df da comparado')
    print(df)
    
    fig = px.line(
        df,
        x="mmdd",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        category_orders={"mmdd": orden_mmdd},
        title="Comparación anual del precio del gas (2024 al 2026)",
        #height=600
    )

     # Forzar eje categórico y aplicar etiquetas legibles
    # Reducimos el número de etiquetas visibles en el eje X
    tickvals = orden_mmdd[::15]  # uno cada 15 días
    ticktext = [df.loc[df["mmdd"] == v, "fecha_corta"].iloc[0] for v in tickvals]
    
    fig.update_xaxes(
        tickmode="array",
        #tickvals=orden_mmdd,
        #ticktext=df.drop_duplicates("mmdd").sort_values("mmdd")["fecha_corta"].tolist(),
        tickvals=tickvals,
        ticktext=ticktext,
        tickangle=0,  # puedes probar 45 si quieres inclinar
        type="category"
    )


    fig.update_layout(
        title_font_size=28, 
        title={'x':0.5, 'xanchor':'center'},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
    )

    cortes_mes = (
        df
        .drop_duplicates("mmdd")
        .loc[df["mmdd"].str.endswith("-01"), "mmdd"]
        .tolist()
    )
    for mmdd in cortes_mes:
        fig.add_vline(
            x=mmdd,
            line_width=1,
            line_dash="dot",
            #line_color="lightgrey",
            line_color="rgba(200,200,200,0.2)"
        )

    return fig


def descargar_sendeco(año):
    url=f'https://www.sendeco2.com/site_sendeco/service/download-csv.php?year={año}'
    res=requests.get(url)
    with open(f'local_bbdd/sendeco_files/sendeco_{año}.csv', 'wb') as file:
            file.write(res.content)
            
    return

def obtener_sendeco():
    #OBTENEMOS UN DATAFRAME CON TODOS LOS HISTÓRICOS DE SENDECO
    ruta_sendeco='local_bbdd/sendeco_files/*.csv'
    #listado de ficheros históricos
    sendecos_csv=glob.glob(ruta_sendeco)
    #dataframe vacio
    df_sendecos=[]
    #creamos dataframes a combinar
    for file in sendecos_csv:
        df=pd.read_csv(file,sep=';')
        df_sendecos.append(df)
    #combinamos
    df_sendeco_combinado=pd.concat(df_sendecos, ignore_index=True)
    #eliminamos columnas innecesarias
    df_sendeco=df_sendeco_combinado.drop(df_sendeco_combinado.columns[[2,3]], axis=1)
    #renombramos
    df_sendeco=df_sendeco.rename(columns={'Fecha':'fecha_entrega','EUA':'co2_€ton'})
    #pasamos fecha a datetime
    #df_sendeco['fecha']=pd.to_datetime(df_sendeco['fecha'],dayfirst=True)
    #df_sendeco['fecha_entrega']=pd.to_datetime(df_sendeco['fecha_entrega'],dayfirst=True).dt.date
    df_sendeco['fecha_entrega']=pd.to_datetime(df_sendeco['fecha_entrega'],dayfirst=True)   
    df_sendeco['año'] = pd.to_datetime(df_sendeco['fecha_entrega']).dt.year

    return df_sendeco




def graficar_gas_co2(df_total_data_gas_co2):
    graf=px.line(df_total_data_gas_co2,
        x='fecha_entrega',
        y=['precio_gas','co2_€ton'],
        labels={'value':'gas €/MWh - CO2 €/Ton','precio_gas':'Mibgas D+1','co2_€ton':'CO2'},
        title='Evolución mibgas D+1 y CO2',
        #width=1000
        
    )

    graf.update_traces(line=dict(color='lightblue'), selector=dict(name='precio_gas'))
    graf.update_traces(line=dict(color='orange'), selector=dict(name='co2_€ton'))

    ymax=max(df_total_data_gas_co2['precio_gas'].max(),df_total_data_gas_co2['co2_€ton'].max())
    graf.update_yaxes(range=[0,ymax+5])
    graf.update_layout(
        xaxis=dict(
                rangeslider=dict(
                    visible=True,
                    bgcolor='rgba(173, 216, 230, 0.5)'
                ),  
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1m", step="month", stepmode="backward"),
                        dict(count=3, label="3m", step="month", stepmode="backward"),
                        dict(step="all")  # Visualizar todos los datos
                    ]),
                    #visible=True
                )
            ),
        title_font_size=28,            
        title={'x':0.5, 'xanchor':'center'},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
    )
    

    return graf

# DF CON LOS VALORES MEDIOS MENSUALES DEL SPOT DE TODO EL HISTÓRICO
# SE USAN PARA VISUALIZARLOS CON LINEAS HORIZONTALES FRENTE A LA EVOLUCIÓN DE OMIP
@st.cache_data
def obtener_spot_mensual(df_sheets):
    df = df_sheets.copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.rename(columns={"fecha": "fecha_entrega"})

    df = df.set_index('fecha_entrega')

    df_spot_mensual = (
        df[['spot']]
        .resample('M')
        .mean()
        .sort_index()
        .reset_index()
    )

    df_spot_mensual['spot'] = df_spot_mensual['spot'].round(2)

    print('df spot diario')
    print(df_spot_mensual)

    return df_spot_mensual

def construir_df_mensual(df):
    # Poner 'fecha' como índice
    df_total_data = df.copy()
    df_total_data = df_total_data.set_index("fecha_entrega").sort_index()
    df_total_data.index = pd.to_datetime(df_total_data.index)

    df_mensual = df_total_data.resample('M').mean(numeric_only=True)
    df_mensual['ratio_omie_gas'] = df_mensual['spot'] / df_mensual['precio_gas']
    df_mensual['mes'] = df_mensual.index.month
    df_mensual['año'] = df_mensual.index.year
    meses_data = {
        'mes': list(range(1, 13)),
        'nombre_mes': ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    }
    df_meses = pd.DataFrame(meses_data)
    #creamos una columna con el nombre del mes
    df_mensual = pd.merge(df_mensual, df_meses, how='left', on='mes')
    df_mensual['mes_año']=df_mensual['nombre_mes'].astype(str) + '_' + df_mensual['año'].astype(str)

    return df_mensual


def graf_simul_spot(
    df,
    df_validacion,
    mibgas,
    omie_media_2026=None,
    gas_media_2026=None,
    omie_previsto=None,
    gas_previsto=None,
):

    fig = px.scatter(
        df,
        x="precio_gas",
        y="spot",
        height=800,
        width=1500,
        title="Simulación del precio medio SPOT a partir de MIBGAS - Año 2026 (€/MWh)",
        custom_data=["mes_año"],
    )

    fig.update_traces(
        name="Valores mensuales",
        showlegend=True,
        marker=dict(symbol="square", color="orange"),
        hovertemplate=(
            "<b>Valores mensuales</b><br>"
            "Mes = %{customdata[0]}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
    )

    # =====================================================
    # CURVA HINGE
    # =====================================================
    x0 = 31.0

    x_val = df_validacion["precio_gas"].to_numpy(float)
    y_val = df_validacion["omie"].to_numpy(float)

    # Nivel base: media OMIE cuando gas <= x0
    base = x_val <= x0
    c_hinge = float(y_val[base].mean())

    # Ajuste derecha: y = c + a*(x-x0)^2 + b*(x-x0)
    mask = x_val > x0
    x_r = x_val[mask] - x0
    y_r = y_val[mask]

    X = np.column_stack([x_r**2, x_r])
    a_h, b_h = np.linalg.lstsq(X, y_r - c_hinge, rcond=None)[0]
    a_h, b_h = float(a_h), float(b_h)

    def hinge(x):
        x = np.asarray(x, dtype=float)

        m_left = 0.6
        y = c_hinge + m_left * (x - x0)

        idx = x > x0
        y[idx] = c_hinge + a_h * (x[idx] - x0) ** 2 + b_h * (x[idx] - x0)

        return y

    # Curva hinge en el rango del histórico
    x_fit = np.linspace(df["precio_gas"].min(), df["precio_gas"].max(), 300)
    y_fit = hinge(x_fit)

    # =====================================================
    # VALORES ANUALES REALES
    # =====================================================
    fig.add_scatter(
        x=df_validacion["precio_gas"],
        y=df_validacion["omie"],
        mode="markers",
        marker=dict(
            symbol="circle",
            size=12,
            color="royalblue",
            line=dict(width=2, color="cyan")
        ),
        name="Valores anuales",
        hovertemplate=(
            "<b>Valores anuales</b><br>"
            "Año %{customdata}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
        customdata=df_validacion["año"]
    )

    # =====================================================
    # PUNTO REAL 2026 YTD: GAS MEDIO 2026 / OMIE MEDIO 2026
    # =====================================================
    if omie_media_2026 is not None and gas_media_2026 is not None:

        fig.add_trace(go.Scatter(
            x=[gas_media_2026],
            y=[omie_media_2026],
            mode="markers+text",
            name="Media 2026",
            marker=dict(
                symbol="diamond",
                size=18,
                color="yellow",
                line=dict(width=3, color="white")
            ),
            text=["Media 2026"],
            textposition="top center",
            hovertemplate=(
                "<b>Media real 2026</b><br>"
                "MIBGAS medio 2026 = %{x:.2f} €/MWh<br>"
                "OMIE medio 2026 = %{y:.2f} €/MWh"
                "<extra></extra>"
            )
        ))

    # =====================================================
    # CURVA DE AJUSTE
    # =====================================================
    fig.add_trace(go.Scatter(
        x=x_fit,
        y=y_fit,
        mode="lines",
        name="Ajuste suave",
        line=dict(color="lime", width=2, dash="dot"),
        hoverinfo="skip"
    ))

    # =====================================================
    # PUNTO PREVISTO HINGE EN MIBGAS
    # =====================================================
    omie_hinge = float(hinge([mibgas])[0])

    fig.add_trace(go.Scatter(
        x=[mibgas],
        y=[omie_hinge],
        mode="markers",
        name="Simulación OMIE",
        marker=dict(
            color="rgba(255,255,255,0)",
            size=20,
            line=dict(width=5, color="lightgreen")
        ),
        hovertemplate=(
            "<b>Simulación OMIE</b><br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        )
    ))

    # Línea vertical simulación OMIE
    fig.add_shape(
        type="line",
        x0=mibgas,
        y0=0,
        x1=mibgas,
        y1=omie_hinge,
        line=dict(color="lightgreen", width=1, dash="dash"),
    )

    # =====================================================
    # SIMULACIÓN INVERSA: OMIE OBJETIVO -> GAS NECESARIO
    # =====================================================
    omie_obj = st.session_state.get("precio_omie_previsto", None)
    mibgas_obj = None

    if omie_obj:

        x_search = np.linspace(0, 120, 2000)
        y_search = hinge(x_search)

        idx = np.argmin(np.abs(y_search - omie_obj))
        mibgas_obj = float(x_search[idx])

        fig.add_trace(go.Scatter(
            x=[mibgas_obj],
            y=[omie_obj],
            mode="markers",
            name="Simulación GAS",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=22,
                line=dict(width=5, color="magenta")
            ),
            hovertemplate=(
                "<b>Simulación GAS</b><br>"
                "OMIE = %{y:.1f} €/MWh<br>"
                "MIBGAS = %{x:.1f} €/MWh"
                "<extra></extra>"
            )
        ))

        xmin = min(df["precio_gas"].min(), df_validacion["precio_gas"].min())

        fig.add_shape(
            type="line",
            x0=xmin,
            y0=omie_obj,
            x1=mibgas_obj,
            y1=omie_obj,
            line=dict(color="magenta", width=1, dash="dash"),
        )

    # =====================================================
    # PUNTO FUTURO: PREVISIONES ANUALES OMIE / MIBGAS
    # =====================================================
    if omie_previsto is not None and gas_previsto is not None:
        fig.add_trace(go.Scatter(
            x=[gas_previsto],
            y=[omie_previsto],
            mode="markers+text",
            name="Punto futuro",
            marker=dict(
                symbol="square",
                size=18,
                color="orange",
                line=dict(width=3, color="white")
            ),
            text=["Punto futuro"],
            textposition="top center",
            hovertemplate=(
                "<b>Punto según valores futuros</b><br>"
                "MIBGAS previsto = %{x:.2f} €/MWh<br>"
                "OMIE previsto = %{y:.2f} €/MWh"
                "<extra></extra>"
            )
        ))

    # =====================================================
    # LAYOUT
    # =====================================================
    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Precio MIBGAS (€/MWh)",
        yaxis_title="Precio OMIE (€/MWh)",
        xaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        yaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        legend=dict(
            font=dict(size=18)
        ),
        hoverlabel=dict(font_size=18)
    )

    if mibgas_obj is not None:
        mibgas_obj = round(mibgas_obj, 2)

    return fig, round(omie_hinge, 2), mibgas_obj


def graf_simul_spot_old(df, df_validacion, mibgas):
    fig = px.scatter(
        df,
        x="precio_gas",
        y="spot",
        height=800,
        width=1500,
        title="Simulación del precio medio SPOT a partir de MIBGAS - Año 2026 (€/MWh)",
        custom_data=["mes_año"],
    )
    fig.update_traces(
        name="Valores mensuales",              # 👈 aparece en leyenda
        showlegend=True,               # 👈 forzado
        marker=dict(symbol="square", color="orange"),
        hovertemplate=(
            "<b>Valores mensuales</b><br>"
            "Mes = %{customdata[0]}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
    )

    # curva hinge
    x0=31.0
    #x0=28.0


    x_val = df_validacion["precio_gas"].to_numpy(float)
    y_val = df_validacion["omie"].to_numpy(float)

    # Nivel base: media OMIE cuando gas <= x0
    base = x_val <= x0
    c_hinge = float(y_val[base].mean())

    # Ajuste derecha: y = c + a*(x-x0)^2 + b*(x-x0)
    mask = x_val > x0
    x_r = x_val[mask] - x0
    y_r = y_val[mask]

    X = np.column_stack([x_r**2, x_r])
    a_h, b_h = np.linalg.lstsq(X, y_r - c_hinge, rcond=None)[0]
    a_h, b_h = float(a_h), float(b_h)

    def hinge(x):
        x = np.asarray(x, dtype=float)
        #y = np.full_like(x, c_hinge, dtype=float)
        m_left = +.6  # pendiente suave hacia abajo
        y = c_hinge + m_left*(x - x0)
        idx = x > x0
        y[idx] = c_hinge + a_h*(x[idx]-x0)**2 + b_h*(x[idx]-x0)
        return y

    # Curva hinge en el rango del histórico
    x_fit = np.linspace(df["precio_gas"].min(), df["precio_gas"].max(), 300)
    y_fit = hinge(x_fit)


    # Valores anuales reales
    fig.add_scatter(
            x=df_validacion['precio_gas'],
            y=df_validacion['omie'],
            mode='markers',
            marker=dict(
                symbol='circle',
                size=12,
                color='royalblue',
                line=dict(width=2, color='cyan')
            ),
            name='Valores anuales',
            hovertemplate=(
                "Año %{customdata}<br>"
                "MIBGAS = %{x:.1f} €/MWh<br>"
                "OMIE = %{y:.1f} €/MWh"
                "<extra></extra>"
            ),
            customdata=df_validacion['año']
        )
    
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_fit,
        mode="lines",
        name="Ajuste suave",
        line=dict(color="lime", width=2, dash="dot"),
        hoverinfo="skip"
    ))

    # Punto previsto hinge en mibgas
    omie_hinge = float(hinge([mibgas])[0])

    fig.add_trace(go.Scatter(
        x=[mibgas], y=[omie_hinge],
        mode="markers",
        name="Simulación OMIE",
        marker=dict(
            color="rgba(255,255,255,0)",
            size=20,
            line=dict(width=5, color="lightgreen")
        ),
        hovertemplate=(
            "<b>Simulación</b><br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        )
    ))

    # Línea vertical
    fig.add_shape(
        type="line",
        x0=mibgas, y0=0,
        x1=mibgas, y1=omie_hinge,
        line=dict(color="lightgreen", width=1, dash="dash"),
    )

    
    omie_obj = st.session_state.get("precio_omie_previsto", None)
    mibgas_obj = None
    if omie_obj:

        # resolver inversa numéricamente
        x_search = np.linspace(0, 120, 2000)
        y_search = hinge(x_search)

        idx = np.argmin(np.abs(y_search - omie_obj))
        mibgas_obj = float(x_search[idx])
        fig.add_trace(go.Scatter(
            x=[mibgas_obj],
            y=[omie_obj],
            mode="markers",
            name="Simulación GAS",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=22,
                line=dict(width=5, color="magenta")
            ),
            hovertemplate=(
                "<b>Simulación GAS</b><br>"
                "OMIE = %{y:.1f} €/MWh<br>"
                "MIBGAS = %{x:.1f} €/MWh<br>"
                
                "<extra></extra>"
            )
        ))
        xmin = min(df["precio_gas"].min(), df_validacion["precio_gas"].min())
        fig.add_shape(
            type="line",
            x0=xmin,
            y0=omie_obj,
            x1=mibgas_obj,
            y1=omie_obj,
            line=dict(color="magenta", width=1, dash="dash"),
        )

    fig.update_layout(
        title_font_size = 28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Precio MIBGAS (€/MWh)",
        yaxis_title="Precio OMIE (€/MWh)",
        xaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        yaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        legend=dict(
            font=dict(size=18)
        ),
        hoverlabel=dict(font_size=18)
    )

    if mibgas_obj is not None:
        mibgas_obj = round(mibgas_obj, 2)

    

    return fig, round(omie_hinge, 2), mibgas_obj


def obtener_mibgas_mensual(df_mg_da):
    df = df_mg_da.copy()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df.dropna(subset=["fecha_entrega", "precio_gas"])

    df_mensual = (
        df
        .set_index("fecha_entrega")
        .resample("MS")["precio_gas"]
        .mean()
        .reset_index()
    )
    df_mensual["precio_gas"] = df_mensual["precio_gas"].round(2)
    df_mensual = df_mensual.dropna(subset=["precio_gas"])

    return df_mensual


def graficar_mibgas_mensual_historico(df_mibgas_mensual):
    df = df_mibgas_mensual.copy()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df.dropna(subset=["fecha_entrega", "precio_gas"]).copy()

    meses = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }
    orden_meses = list(meses.values())

    df["año"] = df["fecha_entrega"].dt.year
    df["mes_num"] = df["fecha_entrega"].dt.month
    df["mes_nombre"] = df["mes_num"].map(meses)
    df = df.sort_values(["año", "mes_num"])

    fig = go.Figure()

    for año in sorted(df["año"].dropna().unique()):
        df_año = df[df["año"] == año].copy()
        fig.add_trace(
            go.Bar(
                x=df_año["mes_nombre"],
                y=df_año["precio_gas"],
                name=str(año),
                marker=dict(color=colores.get(int(año), None)),
                text=[f"{v:.2f}" for v in df_año["precio_gas"]],
                textposition="outside",
                textfont=dict(size=13, color="white"),
                hovertemplate=(
                    "%{fullData.name}: %{y:.2f} €/MWh"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=dict(
            text="Precio medio mensual MIBGAS D+1",
            x=0.5,
            xanchor="center",
            font=dict(size=28)
        ),
        xaxis=dict(
            title="Mes",
            categoryorder="array",
            categoryarray=orden_meses,
            tickfont=dict(size=14)
        ),
        yaxis=dict(
            title="€/MWh",
            range=[0, df["precio_gas"].max() * 1.18],
            title_font=dict(size=16),
            tickfont=dict(size=14)
        ),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        ),
        barmode="group",
        bargap=0.18,
        bargroupgap=0.06,
        barcornerradius=4,
        hovermode="x unified",
        hoverlabel=dict(font_size=16),
        template="plotly_dark",
        height=500
    )

    fig = aplicar_estilo(fig)

    return fig


def normalizar_futuros_mibgas_mensuales(df_mg_m):
    df = df_mg_m.copy()
    df["Trading day"] = pd.to_datetime(df["Trading day"], errors="coerce").dt.normalize()
    df["fecha_entrega"] = (
        pd.to_datetime(df["fecha_entrega"], errors="coerce")
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    return df.dropna(subset=["Trading day", "fecha_entrega", "precio_gas"])


def normalizar_futuros_mibgas_trimestrales(df_mg_q):
    df = df_mg_q.copy()
    df["Trading day"] = pd.to_datetime(df["Trading day"], errors="coerce").dt.normalize()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["inicio_trimestre"] = df["fecha_entrega"].dt.to_period("Q").dt.start_time
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    return df.dropna(subset=["Trading day", "inicio_trimestre", "precio_gas"])


def _ultimo_precio_hasta(df, col_fecha, col_entrega, entrega, fecha_ref):
    df_filtrado = (
        df[
            (df[col_fecha] <= fecha_ref) &
            (df[col_entrega] == entrega)
        ]
        .sort_values(col_fecha)
    )

    if df_filtrado.empty:
        return np.nan, pd.NaT

    fila = df_filtrado.iloc[-1]
    return fila["precio_gas"], fila[col_fecha]


def _precio_futuro_mibgas_para_mes(df_m, df_q, mes_entrega, fecha_ref):
    precio_m, fecha_m = _ultimo_precio_hasta(
        df_m,
        "Trading day",
        "fecha_entrega",
        mes_entrega,
        fecha_ref,
    )

    if pd.notna(precio_m):
        return precio_m, "MIBGAS mensual", fecha_m

    trimestre = (mes_entrega.month - 1) // 3 + 1
    inicio_trimestre = pd.Timestamp(
        mes_entrega.year,
        (trimestre - 1) * 3 + 1,
        1,
    )
    precio_q, fecha_q = _ultimo_precio_hasta(
        df_q,
        "Trading day",
        "inicio_trimestre",
        inicio_trimestre,
        fecha_ref,
    )

    if pd.notna(precio_q):
        return precio_q, "MIBGAS trimestral", fecha_q

    return np.nan, "Sin dato", pd.NaT


def construir_curva_mibgas_2026(df_mibgas_mensual, df_mg_m, df_mg_q, fecha_ref=None, año=2026):
    df_hist = df_mibgas_mensual.copy()
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    if fecha_ref is None:
        fechas_ref = pd.concat([df_m["Trading day"], df_q["Trading day"]]).dropna()
        fecha_ref = fechas_ref.max()

    fecha_ref = pd.to_datetime(fecha_ref).normalize()
    df_hist["fecha_entrega"] = pd.to_datetime(df_hist["fecha_entrega"]).dt.to_period("M").dt.to_timestamp()

    filas = []
    for mes in range(1, 13):
        fecha_mes = pd.Timestamp(año, mes, 1)
        df_hist_mes = df_hist[df_hist["fecha_entrega"] == fecha_mes]

        if not df_hist_mes.empty:
            precio = df_hist_mes["precio_gas"].iloc[-1]
            tipo = "MIBGAS D+1"
            fecha_dato = fecha_mes
        else:
            precio, tipo, fecha_dato = _precio_futuro_mibgas_para_mes(df_m, df_q, fecha_mes, fecha_ref)

        filas.append({
            "fecha": fecha_mes,
            "precio": round(float(precio), 2) if pd.notna(precio) else np.nan,
            "tipo": tipo,
            "fecha_dato": fecha_dato,
        })

    return pd.DataFrame(filas)


def graficar_curva_mibgas_2026(df_curva, precio_medio=None):
    df = df_curva.copy()
    df_hist = df[df["tipo"] == "MIBGAS D+1"]
    df_fut = df[df["tipo"] != "MIBGAS D+1"]
    df_union = df_hist.tail(1)
    df_fut_plot = pd.concat([df_union, df_fut])

    fig = go.Figure()

    if not df_hist.empty:
        fig.add_scatter(
            x=df_hist["fecha"],
            y=df_hist["precio"],
            mode="lines+markers+text",
            name="MIBGAS D+1",
            line=dict(color="seagreen", width=3),
            marker=dict(size=10, symbol="square"),
            text=[f"{v:.1f}" for v in df_hist["precio"]],
            textposition="top center",
            textfont=dict(size=14, color="white"),
            customdata=df_hist["tipo"],
            hovertemplate="<b>%{customdata}</b><br>%{y:.1f} €/MWh<extra></extra>"
        )

    if not df_fut_plot.empty:
        fig.add_scatter(
            x=df_fut_plot["fecha"],
            y=df_fut_plot["precio"],
            mode="lines+markers+text",
            name="MIBGAS futuros",
            line=dict(color="darkorange", width=3, dash="dash"),
            marker=dict(size=10, symbol="square"),
            text=[f"{v:.1f}" if pd.notna(v) else "" for v in df_fut_plot["precio"]],
            textposition="top center",
            textfont=dict(size=14, color="white"),
            customdata=df_fut_plot["tipo"],
            hovertemplate="<b>%{customdata}</b><br>%{x|%b %Y}<br>%{y:.1f} €/MWh<extra></extra>"
        )
        if not df_union.empty:
            fig.data[-1].marker.color = ["rgba(0,0,0,0)"] + ["darkorange"] * (len(df_fut_plot) - 1)

    if precio_medio is not None and pd.notna(precio_medio):
        fig.add_hline(
            y=precio_medio,
            line_dash="dot",
            line_color=color_media_futuro,
            annotation_text=f"Media ≈ {precio_medio:.1f} €/MWh",
            annotation_position="top right",
            annotation_font_size=20,
            annotation_font_color=color_media_futuro
        )

    fig.update_layout(
        title=dict(
            text="PREVISIÓN MIBGAS 2026: Curva híbrida D+1-futuros",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        yaxis=dict(title="€/MWh", range=[0, None]),
        xaxis=dict(tickformat="%b %Y"),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


@st.cache_data()
def construir_media_prevista_mibgas_2026_diaria(df_mg_da, df_mg_m, df_mg_q, año=2026):
    df_da = df_mg_da.copy()
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    df_da["fecha_entrega"] = pd.to_datetime(df_da["fecha_entrega"], errors="coerce").dt.normalize()
    df_da["precio_gas"] = pd.to_numeric(df_da["precio_gas"], errors="coerce")
    df_da = df_da.dropna(subset=["fecha_entrega", "precio_gas"])

    fecha_ini = pd.Timestamp(año, 1, 1)
    fecha_ref_max = df_da.loc[
        df_da["fecha_entrega"].dt.year == año,
        "fecha_entrega"
    ].max()

    fechas_ref = sorted(
        df_da.loc[
            (df_da["fecha_entrega"] >= fecha_ini) &
            (df_da["fecha_entrega"] <= fecha_ref_max),
            "fecha_entrega"
        ].dropna().unique()
    )

    filas = []

    for fecha_ref in fechas_ref:
        fecha_ref = pd.Timestamp(fecha_ref).normalize()
        mes_actual = fecha_ref.month
        precios_mes = []

        for mes in range(1, 13):
            fecha_mes = pd.Timestamp(año, mes, 1)

            if mes < mes_actual:
                filtro_da = (
                    (df_da["fecha_entrega"].dt.year == año) &
                    (df_da["fecha_entrega"].dt.month == mes)
                )
                precio = df_da.loc[filtro_da, "precio_gas"].mean()

            elif mes == mes_actual:
                filtro_da = (
                    (df_da["fecha_entrega"] >= fecha_mes) &
                    (df_da["fecha_entrega"] <= fecha_ref)
                )
                precio = df_da.loc[filtro_da, "precio_gas"].mean()

            else:
                precio, _, _ = _precio_futuro_mibgas_para_mes(
                    df_m,
                    df_q,
                    fecha_mes,
                    fecha_ref,
                )

            precios_mes.append(precio)

        precios_mes = pd.Series(precios_mes, dtype="float")

        if precios_mes.notna().sum() == 12:
            filas.append({
                "fecha_cotizacion": fecha_ref,
                "media_2026": precios_mes.mean(),
            })
        else:
            print(
                f"No se pudo calcular media MIBGAS completa para {fecha_ref.date()}: "
                f"{precios_mes.notna().sum()}/12 meses válidos"
            )

    df_media = pd.DataFrame(filas)

    if not df_media.empty:
        df_media = df_media.sort_values("fecha_cotizacion").reset_index(drop=True)
        df_media["media_2026"] = df_media["media_2026"].round(2)

    return df_media


def graficar_media_prevista_mibgas_2026(df_media_2026, año=2026):
    df = df_media_2026.copy()

    fig = go.Figure()
    inicio_año = pd.Timestamp(año, 1, 1)
    fin_año = pd.Timestamp(año, 12, 31)

    if df.empty:
        fig.update_layout(
            title=dict(
                text=f"Evolución diaria de la media MIBGAS prevista {año}",
                x=0.5,
                xanchor="center",
                font=dict(size=20)
            ),
            yaxis=dict(title="€/MWh"),
            xaxis=dict(title="Fecha de cotización", tickformat="%b-%y", range=[inicio_año, fin_año]),
            template="plotly_dark",
            height=500
        )
        fig = aplicar_estilo(fig)
        return fig

    df["fecha_cotizacion"] = pd.to_datetime(df["fecha_cotizacion"])
    df = df.sort_values("fecha_cotizacion")

    fig.add_scatter(
        x=df["fecha_cotizacion"],
        y=df["media_2026"],
        mode="lines",
        name="Media prevista 2026",
        line=dict(
            color=color_media_futuro,
            width=2,
        ),
        showlegend=True,
        hovertemplate=(
            "<b>Media prevista 2026</b><br>"
            "%{x|%d/%m/%Y}<br>"
            "%{y:.1f} €/MWh"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        title=dict(
            text=f"Evolución diaria de la media MIBGAS prevista {año}",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        yaxis=dict(
            title="€/MWh",
            range=[
                max(0, df["media_2026"].min() - 5),
                df["media_2026"].max() + 5
            ],
            title_font=dict(size=14),
            tickfont=dict(size=14)
        ),
        xaxis=dict(
            title="Fecha de cotización",
            tickformat="%b-%y",
            range=[inicio_año, fin_año],
            tickfont=dict(size=14)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


def construir_curva_mibgas_mensual_12m(df_mg_m, df_mg_q, fecha_ref=None):
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    if fecha_ref is None:
        fechas_ref = pd.concat([df_m["Trading day"], df_q["Trading day"]]).dropna()
        fecha_ref = fechas_ref.max()

    fecha_ref = pd.to_datetime(fecha_ref).normalize()
    filas = []

    for i in range(1, 13):
        fecha = fecha_ref + pd.DateOffset(months=i)
        fecha = pd.Timestamp(fecha.year, fecha.month, 1)
        precio, tipo, fecha_dato = _precio_futuro_mibgas_para_mes(df_m, df_q, fecha, fecha_ref)

        filas.append({
            "fecha": fecha,
            "precio": round(float(precio), 2) if pd.notna(precio) else np.nan,
            "tipo": tipo,
            "fecha_dato": fecha_dato,
        })

    df_curva = pd.DataFrame(filas)
    print("DEBUG MIBGAS curva 12M")
    print("Fecha ref:", fecha_ref)
    print("Productos M:", sorted(df_mg_m["producto"].dropna().unique().tolist()))
    print("Productos Q:", sorted(df_mg_q["producto"].dropna().unique().tolist()))
    print(df_curva)
    print("Meses con precio:", df_curva["precio"].notna().sum(), "/ 12")

    return df_curva


def graficar_curva_mibgas_mensual_12m(df_mibgas, precio_medio=None):
    fig = go.Figure()

    fig.add_scatter(
        x=df_mibgas["fecha"],
        y=df_mibgas["precio"],
        mode="lines+markers+text",
        name="MIBGAS forward 12M",
        line=dict(color="darkorange", width=3, dash="dash"),
        marker=dict(size=10, symbol="square"),
        text=[f"{v:.1f}" if pd.notna(v) else "" for v in df_mibgas["precio"]],
        textposition="top center",
        textfont=dict(size=14, color="white"),
        customdata=df_mibgas["tipo"],
        hovertemplate="<b>%{customdata}</b><br>%{x|%b %Y}<br>%{y:.1f} €/MWh<extra></extra>"
    )

    if precio_medio is not None and pd.notna(precio_medio):
        fig.add_hline(
            y=precio_medio,
            line_dash="dot",
            line_color="white",
            annotation_text=f"Media ≈ {precio_medio:.1f} €/MWh",
            annotation_position="top right",
            annotation_font_size=18
        )

    fig.update_layout(
        title=dict(
            text="Curva MIBGAS año móvil",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        yaxis=dict(title="€/MWh", range=[0, None]),
        xaxis=dict(tickformat="%b %Y"),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


@st.cache_data()
def construir_evolucion_media_mibgas_forward_12m(
    df_mg_m,
    df_mg_q,
    fecha_ref=None,
    fecha_inicio="01.01.2024"
):
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    fecha_inicio = pd.to_datetime(fecha_inicio, dayfirst=True).normalize()

    if fecha_ref is None:
        fechas_ref = pd.concat([df_m["Trading day"], df_q["Trading day"]]).dropna()
        fecha_ref = fechas_ref.max()

    fecha_ref = pd.to_datetime(fecha_ref, dayfirst=True).normalize()

    df_m = df_m[
        (df_m["Trading day"] >= fecha_inicio) &
        (df_m["Trading day"] <= fecha_ref)
    ].copy()
    df_q = df_q[
        (df_q["Trading day"] >= fecha_inicio) &
        (df_q["Trading day"] <= fecha_ref)
    ].copy()

    fechas = sorted(
        set(df_m["Trading day"].dropna().unique()).union(
            set(df_q["Trading day"].dropna().unique())
        )
    )
    fechas = [pd.Timestamp(f).normalize() for f in fechas]

    filas = []

    for f in fechas:
        precios = []
        tipos = []

        for i in range(1, 13):
            mes_forward = f + pd.DateOffset(months=i)
            mes_forward = pd.Timestamp(
                mes_forward.year,
                mes_forward.month,
                1
            )

            precio, tipo, _ = _precio_futuro_mibgas_para_mes(
                df_m,
                df_q,
                mes_forward,
                f
            )

            if pd.notna(precio):
                precios.append(precio)
                tipos.append(tipo)

        if len(precios) == 12:
            filas.append({
                "Fecha": f,
                "media_forward_12m": np.mean(precios),
                "min_forward": np.min(precios),
                "max_forward": np.max(precios),
                "n_meses": len(precios),
                "n_mensuales": tipos.count("MIBGAS mensual"),
                "n_trimestrales": tipos.count("MIBGAS trimestral")
            })

    df_evol = pd.DataFrame(filas)

    if not df_evol.empty:
        df_evol["media_forward_12m"] = df_evol["media_forward_12m"].round(2)
        df_evol["min_forward"] = df_evol["min_forward"].round(2)
        df_evol["max_forward"] = df_evol["max_forward"].round(2)

    return df_evol


@st.cache_data()
def añadir_mibgas_real_12m_alineado_forward(
    df_evol,
    df_mg_da,
    col_fecha_evol="Fecha",
    col_fecha_real="fecha_entrega",
    col_real="precio_gas",
    meses=12,
    exigir_ventana_completa=True
):
    df_out = df_evol.copy()
    df_real = df_mg_da.copy()

    df_out[col_fecha_evol] = pd.to_datetime(
        df_out[col_fecha_evol],
        errors="coerce",
        dayfirst=True
    ).dt.normalize()

    df_real[col_fecha_real] = pd.to_datetime(
        df_real[col_fecha_real],
        errors="coerce",
        dayfirst=True
    ).dt.normalize()

    df_real[col_real] = pd.to_numeric(
        df_real[col_real],
        errors="coerce"
    )

    df_real = (
        df_real
        .dropna(subset=[col_fecha_real, col_real])
        .groupby(col_fecha_real, as_index=False)[col_real]
        .mean()
        .sort_values(col_fecha_real)
    )

    fecha_min_real = df_real[col_fecha_real].min()
    fecha_max_real = df_real[col_fecha_real].max()

    resultados = []

    for fecha_ref in df_out[col_fecha_evol]:
        if pd.isna(fecha_ref):
            resultados.append({
                col_fecha_evol: fecha_ref,
                "mibgas_real_12m_alineado": np.nan,
                "fecha_ini_mibgas_alineado": pd.NaT,
                "fecha_fin_mibgas_alineado": pd.NaT,
                "dias_usados_mibgas_alineado": 0,
                "dias_esperados_mibgas_alineado": np.nan,
                "ventana_completa_mibgas_alineado": False
            })
            continue

        fecha_ini = (fecha_ref + pd.DateOffset(months=1)).replace(day=1)
        fecha_fin = fecha_ini + pd.DateOffset(months=meses) - pd.Timedelta(days=1)

        df_ventana = df_real[
            (df_real[col_fecha_real] >= fecha_ini) &
            (df_real[col_fecha_real] <= fecha_fin)
        ].copy()

        dias_esperados = (fecha_fin - fecha_ini).days + 1
        dias_usados = df_ventana[col_fecha_real].nunique()

        ventana_completa = (
            pd.notna(fecha_min_real)
            and pd.notna(fecha_max_real)
            and fecha_ini >= fecha_min_real
            and fecha_fin <= fecha_max_real
            and dias_usados == dias_esperados
        )

        if exigir_ventana_completa:
            mibgas_real_12m_alineado = (
                df_ventana[col_real].mean()
                if ventana_completa
                else np.nan
            )
        else:
            mibgas_real_12m_alineado = (
                df_ventana[col_real].mean()
                if not df_ventana.empty
                else np.nan
            )

        resultados.append({
            col_fecha_evol: fecha_ref,
            "mibgas_real_12m_alineado": mibgas_real_12m_alineado,
            "fecha_ini_mibgas_alineado": fecha_ini,
            "fecha_fin_mibgas_alineado": fecha_fin,
            "dias_usados_mibgas_alineado": dias_usados,
            "dias_esperados_mibgas_alineado": dias_esperados,
            "ventana_completa_mibgas_alineado": ventana_completa
        })

    df_alineado = pd.DataFrame(resultados)
    df_out = df_out.merge(df_alineado, on=col_fecha_evol, how="left")

    if not df_out.empty:
        df_out["mibgas_real_12m_alineado"] = (
            df_out["mibgas_real_12m_alineado"].round(2)
        )

    return df_out


@st.cache_data()
def graficar_evolucion_media_mibgas_forward(
    df_evol,
    col_real="mibgas_real_12m_alineado",
    col_ventana_completa="ventana_completa_mibgas_alineado",
    nombre_real="MIBGAS real 12M alineado",
    titulo="MIBGAS forward 12M vs MIBGAS real 12M alineado"
):
    df_plot = df_evol.copy()

    df_plot["Fecha"] = pd.to_datetime(
        df_plot["Fecha"],
        errors="coerce",
        dayfirst=True
    )

    df_plot["media_forward_12m"] = pd.to_numeric(
        df_plot["media_forward_12m"],
        errors="coerce"
    )

    df_plot = df_plot.dropna(subset=["Fecha"]).sort_values("Fecha")
    tiene_real = col_real in df_plot.columns

    if tiene_real:
        df_plot[col_real] = pd.to_numeric(df_plot[col_real], errors="coerce")

        if col_ventana_completa in df_plot.columns:
            mask_real_valido = (
                (df_plot[col_ventana_completa] == True) &
                df_plot[col_real].notna()
            )
        else:
            mask_real_valido = df_plot[col_real].notna()

        df_plot["desvio_mibgas"] = np.where(
            mask_real_valido,
            df_plot[col_real] - df_plot["media_forward_12m"],
            np.nan
        )
        df_plot["desvio_mibgas"] = df_plot["desvio_mibgas"].round(2)

        df_plot["desvio_pct"] = np.where(
            mask_real_valido &
            df_plot["media_forward_12m"].notna() &
            (df_plot["media_forward_12m"] != 0),
            df_plot["desvio_mibgas"] / df_plot["media_forward_12m"] * 100,
            np.nan
        )
        df_plot["desvio_pct"] = df_plot["desvio_pct"].round(2)

        def construir_hover(row):
            fecha_txt = row["Fecha"].strftime("%d/%m/%Y") if pd.notna(row["Fecha"]) else ""

            texto = (
                f"<b>{fecha_txt}</b><br><br>"
                f"MIBGAS forward 12M: {row['media_forward_12m']:.2f} €/MWh<br>"
            )

            if pd.notna(row.get(col_real)) and pd.notna(row.get("desvio_mibgas")):
                texto += (
                    f"{nombre_real}: {row[col_real]:.2f} €/MWh<br>"
                    f"Diferencial real - forward: {row['desvio_mibgas']:+.2f} €/MWh<br>"
                    f"Diferencial real - forward: {row['desvio_pct']:+.2f}%"
                )
            else:
                texto += (
                    f"{nombre_real}: N/D<br>"
                    "Diferencial real - forward: N/D<br>"
                    "Diferencial real - forward: N/D"
                )

            return texto

        df_plot["hover_forward"] = df_plot.apply(construir_hover, axis=1)
    else:
        df_plot["hover_forward"] = df_plot.apply(
            lambda row: (
                f"<b>{row['Fecha'].strftime('%d/%m/%Y')}</b><br><br>"
                f"MIBGAS forward 12M: {row['media_forward_12m']:.2f} €/MWh"
            ),
            axis=1
        )

    fig = go.Figure()

    fig.add_scatter(
        x=df_plot["Fecha"],
        y=df_plot["media_forward_12m"],
        mode="lines",
        name="Media MIBGAS forward 12M",
        line=dict(color="darkorange", width=1),
        text=df_plot["hover_forward"],
        hovertemplate="%{text}<extra></extra>"
    )

    if tiene_real:
        if col_ventana_completa in df_plot.columns:
            df_real = df_plot[
                (df_plot[col_ventana_completa] == True) &
                df_plot[col_real].notna()
            ].copy()
        else:
            df_real = df_plot.dropna(subset=[col_real]).copy()

        if not df_real.empty:
            fig.add_scatter(
                x=df_real["Fecha"],
                y=df_real[col_real],
                mode="lines",
                name=nombre_real,
                line=dict(color="lightgreen", width=2),
                hoverinfo="skip",
                hovertemplate=None
            )

    fig.update_layout(
        title=dict(
            text=titulo,
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        yaxis=dict(
            title="€/MWh",
            range=[0, None],
            title_font=dict(size=14),
            tickfont=dict(size=14)
        ),
        xaxis=dict(
            title="Fecha de cotizacion",
            tickfont=dict(size=14)
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="center",
            x=0.5,
            title_text="",
            font=dict(size=14)
        ),
        template="plotly_dark",
        hovermode="x",
        height=500
    )

    fig = aplicar_estilo(fig)

    return fig


@st.cache_data
def obtener_spot_diario(df_sheets):
    df = df_sheets.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.set_index("fecha")

    df_spot_diario = (
        df[["spot"]]
        .resample("D")
        .mean()
        .sort_index()
        .reset_index()
    )

    df_spot_diario["spot"] = df_spot_diario["spot"].round(2)

    return df_spot_diario
    


 
