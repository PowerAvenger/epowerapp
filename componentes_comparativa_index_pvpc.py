import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend_comun import aplicar_estilo
from formato_es import formato_cent_eur_kwh, formato_euros, formato_pct


def _resumir_perfilados(datos, agrupador):
    resumen = (
        datos.groupby(agrupador, as_index=False)
        .agg(
            suma_perfil=("perfil_20", "sum"),
            suma_index=("index_ponderado", "sum"),
            suma_pvpc=("pvpc_ponderado", "sum"),
        )
    )
    resumen["index_20"] = resumen["suma_index"] / resumen["suma_perfil"] / 10
    resumen["pvpc"] = resumen["suma_pvpc"] / resumen["suma_perfil"] / 10
    resumen["diferencial"] = resumen["index_20"] - resumen["pvpc"]
    return resumen


def _anadir_areas(figura, datos, columna_fecha, columna_index, columna_pvpc):
    datos = datos.dropna(
        subset=[columna_fecha, columna_index, columna_pvpc]
    ).sort_values(columna_fecha).reset_index(drop=True)
    lineas = tuple(figura.data)
    leyendas = set()

    def tramo(x0, x1, index0, index1, pvpc0, pvpc1, index_mejor):
        nombre = "Index mejor" if index_mejor else "Index peor"
        color = "rgba(65, 255, 115, 0.42)" if index_mejor else "rgba(255, 85, 85, 0.40)"
        figura.add_trace(go.Scatter(
            x=[x0, x1, x1, x0], y=[index0, index1, pvpc1, pvpc0],
            mode="lines", line=dict(width=0), fill="toself", fillcolor=color,
            name=nombre, showlegend=nombre not in leyendas, hoverinfo="skip",
        ))
        leyendas.add(nombre)

    for indice in range(len(datos) - 1):
        actual, siguiente = datos.iloc[indice], datos.iloc[indice + 1]
        x0, x1 = pd.Timestamp(actual[columna_fecha]), pd.Timestamp(siguiente[columna_fecha])
        index0, index1 = actual[columna_index], siguiente[columna_index]
        pvpc0, pvpc1 = actual[columna_pvpc], siguiente[columna_pvpc]
        diferencia0, diferencia1 = pvpc0 - index0, pvpc1 - index1
        if diferencia0 * diferencia1 < 0:
            proporcion = abs(diferencia0) / (abs(diferencia0) + abs(diferencia1))
            cruce_x = x0 + (x1 - x0) * proporcion
            cruce_y = index0 + (index1 - index0) * proporcion
            tramo(x0, cruce_x, index0, cruce_y, pvpc0, cruce_y, diferencia0 > 0)
            tramo(cruce_x, x1, cruce_y, index1, cruce_y, pvpc1, diferencia1 > 0)
        elif diferencia0 != 0 or diferencia1 != 0:
            tramo(x0, x1, index0, index1, pvpc0, pvpc1, (diferencia0 or diferencia1) > 0)

    numero_areas = len(figura.data) - len(lineas)
    if numero_areas:
        figura.data = figura.data[-numero_areas:] + lineas


def _anadir_resumen_anual(figura, metricas):
    for fila in metricas.itertuples(index=False):
        diferencial_pct = fila.diferencial / fila.pvpc * 100 if fila.pvpc else 0.0
        tipo = "Sobrecoste" if diferencial_pct > 0 else "Ahorro"
        color = "rgba(255, 85, 85, 0.32)" if diferencial_pct > 0 else "rgba(65, 255, 115, 0.32)"
        figura.add_annotation(
            x=pd.Timestamp(int(fila.anio), 7, 1), y=.98, xref="x", yref="paper",
            text=f"<b>{int(fila.anio)}</b><br>{tipo} de Index vs PVPC: {formato_pct(abs(diferencial_pct), 2)}",
            showarrow=False, bgcolor=color, bordercolor=color, borderpad=5,
            font=dict(size=13),
        )


def _crear_grafico(datos, fecha, titulo_index, titulo_pvpc, perfilado=False):
    columna_index = "index_20" if perfilado else "precio_2.0"
    figura = go.Figure()
    figura.add_trace(go.Scatter(
        x=datos[fecha], y=datos[columna_index], mode="lines", name=titulo_index,
        line=dict(color="goldenrod", width=3),
        hovertemplate="Index 2.0: %{y:.2f} c€/kWh<extra></extra>",
    ))
    figura.add_trace(go.Scatter(
        x=datos[fecha], y=datos["pvpc"], mode="lines", name=titulo_pvpc,
        line=dict(color="#A855F7", width=3),
        hovertemplate="PVPC: %{y:.2f} c€/kWh<extra></extra>",
    ))
    _anadir_areas(figura, datos, fecha, columna_index, "pvpc")
    figura.update_xaxes(showgrid=True, dtick="M1", tickformat="%b%y", title_text="Mes")
    figura.update_yaxes(rangemode="tozero", showgrid=True, title_text="Precio medio c€/kWh")
    figura.update_layout(title="", hovermode="x unified", legend_title_text="", height=650)
    for anio in sorted(datos[fecha].dropna().dt.year.unique())[1:]:
        figura.add_vline(
            x=pd.Timestamp(int(anio), 1, 1).timestamp() * 1000,
            line_width=3, line_dash="solid", line_color="rgba(160, 160, 160, 0.75)",
        )
    return aplicar_estilo(figura)


@st.cache_data(show_spinner=False)
def preparar_comparativa_index_pvpc(df_index, df_pvpc):
    """Prepara una sola vez las series y figuras compartidas Index 2.0/PVPC."""
    index = df_index[["fecha", "hora", "precio_2.0"]].copy()
    index["fecha"] = pd.to_datetime(index["fecha"], errors="coerce").dt.normalize()
    index["hora"] = pd.to_numeric(index["hora"], errors="coerce")
    index["precio_2.0"] = pd.to_numeric(index["precio_2.0"], errors="coerce")
    index = index[index["fecha"] >= pd.Timestamp("2024-01-01")]

    pvpc = df_pvpc[["fecha", "hora", "pvpc", "perfil_20"]].copy()
    pvpc["fecha"] = pd.to_datetime(pvpc["fecha"], errors="coerce").dt.normalize()
    for columna in ("hora", "pvpc", "perfil_20"):
        pvpc[columna] = pd.to_numeric(pvpc[columna], errors="coerce")
    pvpc = pvpc[pvpc["fecha"] >= pd.Timestamp("2024-01-01")]

    index_mensual = (
        index.assign(fecha=lambda df: df["fecha"].dt.to_period("M").dt.to_timestamp())
        .groupby("fecha", as_index=False)["precio_2.0"].mean()
    )
    index_mensual["precio_2.0"] /= 10
    pvpc_mensual = (
        pvpc.assign(fecha=lambda df: df["fecha"].dt.to_period("M").dt.to_timestamp())
        .groupby("fecha", as_index=False)["pvpc"].mean()
    )
    pvpc_mensual["pvpc"] /= 10
    mensual = index_mensual.merge(pvpc_mensual, on="fecha", how="inner")
    anual_index = (
        index.assign(anio=index["fecha"].dt.year)
        .groupby("anio", as_index=False)["precio_2.0"].mean()
        .rename(columns={"precio_2.0": "index_20"})
    )
    anual_index["index_20"] /= 10
    anual_pvpc = (
        pvpc.assign(anio=pvpc["fecha"].dt.year)
        .groupby("anio", as_index=False)["pvpc"].mean()
    )
    anual_pvpc["pvpc"] /= 10
    anual = anual_index.merge(anual_pvpc, on="anio", how="inner")
    anual["diferencial"] = anual["index_20"] - anual["pvpc"]

    perfilada = index.merge(pvpc, on=["fecha", "hora"], how="inner").dropna(
        subset=["fecha", "precio_2.0", "pvpc", "perfil_20"]
    )
    perfilada = perfilada[perfilada["perfil_20"] > 0].copy()
    perfilada["anio"] = perfilada["fecha"].dt.year
    perfilada["fecha_mes"] = perfilada["fecha"].dt.to_period("M").dt.to_timestamp()
    perfilada["index_ponderado"] = perfilada["precio_2.0"] * perfilada["perfil_20"]
    perfilada["pvpc_ponderado"] = perfilada["pvpc"] * perfilada["perfil_20"]
    mensual_perfilada = _resumir_perfilados(perfilada, "fecha_mes")
    anual_perfilada = _resumir_perfilados(perfilada, "anio")

    grafico = _crear_grafico(mensual, "fecha", "Index 2.0", "PVPC")
    grafico_perfilado = _crear_grafico(
        mensual_perfilada, "fecha_mes", "Index 2.0 perfilado", "PVPC perfilado", True
    )
    _anadir_resumen_anual(grafico, anual)
    _anadir_resumen_anual(grafico_perfilado, anual_perfilada)
    return grafico, anual, grafico_perfilado, anual_perfilada


def _diferencial(valor):
    texto = formato_cent_eur_kwh(valor, 2, False)
    return f"+{texto}" if valor > 0 else texto


def render_comparativa_index_pvpc(resultado):
    grafico, anual, grafico_perfilado, anual_perfilado = resultado
    st.subheader("Comparativa mensual Index 2.0 vs PVPC", divider="rainbow")
    anual = anual.sort_values("anio")
    if not anual.empty:
        for columna, fila in zip(st.columns(len(anual), gap="small"), anual.itertuples(index=False)):
            with columna:
                st.markdown(f"#### {int(fila.anio)} (c€/kWh)")
                st.metric("Media Index 2.0", formato_cent_eur_kwh(fila.index_20, 2, False))
                st.metric("Media PVPC", formato_cent_eur_kwh(fila.pvpc, 2, False))
                st.metric("Index − PVPC", _diferencial(fila.diferencial))
    st.plotly_chart(grafico, use_container_width=True)

    st.subheader("Comparativa Index 2.0 vs PVPC perfilada", divider="rainbow")
    anual_perfilado = anual_perfilado.sort_values("anio")
    consumo = st.number_input(
        "Consumo (kWh/año)", min_value=0.0, value=3000.0, step=100.0,
        format="%.0f", key="consumo_index_vs_pvpc",
    )
    if not anual_perfilado.empty:
        columnas = st.columns(len(anual_perfilado) + 1, gap="small")
        for columna, fila in zip(columnas[:-1], anual_perfilado.itertuples(index=False)):
            coste_index = fila.index_20 * consumo / 100
            coste_pvpc = fila.pvpc * consumo / 100
            impacto = coste_index - coste_pvpc
            porcentaje = impacto / coste_pvpc * 100 if coste_pvpc else 0.0
            with columna:
                st.markdown(f"#### {int(fila.anio)} (c€/kWh)")
                st.metric("Index 2.0 perfilado", formato_cent_eur_kwh(fila.index_20, 2, False))
                st.metric("PVPC perfilado", formato_cent_eur_kwh(fila.pvpc, 2, False))
                st.metric("Index − PVPC", _diferencial(fila.diferencial))
                st.metric("Coste Index", formato_euros(coste_index, 2, False))
                st.metric("Coste PVPC", formato_euros(coste_pvpc, 2, False))
                st.metric(
                    "Sobrecoste Index" if impacto > 0 else "Ahorro Index",
                    formato_euros(abs(impacto), 2, False),
                    delta=("+" if porcentaje > 0 else "") + formato_pct(porcentaje, 2),
                    delta_color="inverse",
                )
        coste_total_index = anual_perfilado["index_20"].sum() * consumo / 100
        coste_total_pvpc = anual_perfilado["pvpc"].sum() * consumo / 100
        impacto_total = coste_total_index - coste_total_pvpc
        porcentaje_total = (
            impacto_total / coste_total_pvpc * 100 if coste_total_pvpc else 0.0
        )
        with columnas[-1]:
            anio_inicial = int(anual_perfilado["anio"].min())
            anio_final = int(anual_perfilado["anio"].max())
            st.markdown(f"#### Total {anio_inicial}–{anio_final}")
            st.metric("Coste total Index", formato_euros(coste_total_index, 2, False))
            st.metric("Coste total PVPC", formato_euros(coste_total_pvpc, 2, False))
            st.metric(
                "Sobrecoste Index" if impacto_total > 0 else "Ahorro Index",
                formato_euros(abs(impacto_total), 2, False),
                delta=("+" if porcentaje_total > 0 else "") + formato_pct(porcentaje_total, 2),
                delta_color="inverse",
            )
    st.plotly_chart(grafico_perfilado, use_container_width=True)
