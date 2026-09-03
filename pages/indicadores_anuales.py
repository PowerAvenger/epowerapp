from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from backend_comun import (
    carga_mibgas,
    colores_precios,
    construir_media_acumulada_prevista,
)
from backend_escalacv import (
    cargar_datos_escalacv,
    graficar_comparativa_spot_horaria_mensual,
    graficar_media_acumulada_periodo,
)
from backend_demanda import (
    graficar_demanda_anual,
    obtener_demanda_anual_dashboard,
)
from backend_mibgas import (
    construir_curva_mibgas_2026,
    filtrar_por_producto,
    graficar_da_2026_acumulado,
    obtener_mibgas_mensual,
)
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)
from backend_spot import resumir_spot
from backend_redata_potgen import (
    COLORES_MIX_GENERACION,
    graficar_mix_comparativo,
    graficar_mix_queso,
    leer_json as leer_json_redata,
    preparar_mix_generacion_anual,
)
from formato_es import (
    formato_cent_eur_kwh,
    formato_eur_mwh,
    formato_numero_es,
    formato_pct,
)
from backend_telemindex import (
    analizar_dependencia_omie,
    graficar_diferencial_precios_mensuales,
    graficar_media_acumulada_mensual_atr,
    graficar_precios_medios_horarios,
)
from utilidades import generar_menu, init_app, init_app_index


if (
    not st.session_state.get("usuario_autenticado", False)
    and not st.session_state.get("usuario_free", False)
):
    st.switch_page("epowerapp.py")

generar_menu()
init_app()

fecha_hoy = date.today()

año_dashboard = st.sidebar.selectbox(
    "Año",
    options=list(range(fecha_hoy.year, 2023, -1)),
    key="indicadores_anuales_año",
)
año_base_comparativa = año_dashboard - 1

st.subheader(f"Evolución del año {año_dashboard}.")

with st.spinner("Cargando datos de mercado..."):
    datos_spot, _, _ = cargar_datos_escalacv(
        componente="SPOT",
        file_id_spot=st.secrets["FILE_ID_SPOT"],
        file_id_ssaa=st.secrets["FILE_ID_SSAA"],
        creds_dict=st.secrets["GOOGLE_SHEETS_CREDENTIALS"],
    )

with st.spinner("Preparando mercado de gas..."):
    datos_mibgas = carga_mibgas()
    datos_mibgas_da = filtrar_por_producto(datos_mibgas, "GDAES_D+1")
    datos_mibgas_año = datos_mibgas_da[
        datos_mibgas_da["fecha_entrega"].dt.year == año_dashboard
    ].copy()

with st.spinner("Preparando precios de indexado..."):
    init_app_index()
    datos_indexado = st.session_state.df_sheets.copy()
    datos_indexado["fecha"] = pd.to_datetime(datos_indexado["fecha"])
    datos_indexado_año = datos_indexado[
        datos_indexado["fecha"].dt.year == año_dashboard
    ].copy()

with st.spinner("Preparando demanda peninsular..."):
    datos_demanda_año, ultima_fecha_demanda = obtener_demanda_anual_dashboard(
        año_dashboard
    )
    datos_demanda_base, _ = obtener_demanda_anual_dashboard(
        año_base_comparativa
    )

with st.spinner("Preparando mix de generación..."):
    datos_generacion = leer_json_redata(
        st.secrets["FILE_ID_GEN"],
        "estructura-generacion",
    )
    datos_mix_generacion = preparar_mix_generacion_anual(
        datos_generacion,
        año=año_dashboard,
    )
    fechas_generacion = datos_generacion.loc[
        datos_generacion["año"] == año_dashboard,
        "fecha",
    ]
    ultima_fecha_generacion = (
        fechas_generacion.max() if not fechas_generacion.empty else None
    )

datos_spot_año = datos_spot[datos_spot["año"] == año_dashboard].copy()
fechas_disponibles = pd.to_datetime(
    datos_spot_año["fecha"],
    errors="coerce",
).dropna()
ultima_fecha = fechas_disponibles.max() if not fechas_disponibles.empty else None
ultima_fecha_gas = (
    datos_mibgas_año["fecha_entrega"].max()
    if not datos_mibgas_año.empty
    else None
)
ultima_fecha_indexado = (
    datos_indexado_año["fecha"].max()
    if not datos_indexado_año.empty
    else None
)


def limitar_hasta_fecha_equivalente(datos, columna_fecha, fecha_corte):
    """Recorta cualquier año al mismo mes y día de la fecha de corte."""
    if fecha_corte is None or datos.empty:
        return datos.iloc[0:0].copy()
    fechas = pd.to_datetime(datos[columna_fecha], errors="coerce")
    orden_dia = fechas.dt.month * 100 + fechas.dt.day
    limite = fecha_corte.month * 100 + fecha_corte.day
    return datos[orden_dia <= limite].copy()


def graficar_comparativa_acumulada_anual(
    datos,
    columna_fecha,
    columna_valor,
    años,
    nombre_valor,
    incluir_diario=True,
):
    """Compara valores diarios y medias acumuladas sobre un calendario común."""
    diario = datos.copy()
    diario[columna_fecha] = pd.to_datetime(
        diario[columna_fecha], errors="coerce"
    )
    diario[columna_valor] = pd.to_numeric(
        diario[columna_valor], errors="coerce"
    )
    diario = (
        diario.dropna(subset=[columna_fecha, columna_valor])
        .assign(año=lambda df: df[columna_fecha].dt.year)
        .groupby(["año", columna_fecha], as_index=False)[columna_valor]
        .mean()
        .sort_values(["año", columna_fecha])
    )
    diario["media_acumulada"] = (
        diario.groupby("año")[columna_valor]
        .expanding()
        .mean()
        .reset_index(level=0, drop=True)
    )
    diario["fecha_comun"] = pd.to_datetime(
        "2024-" + diario[columna_fecha].dt.strftime("%m-%d"),
        errors="coerce",
    )
    figura = go.Figure()
    colores = {años[0]: "#09ab3b", años[1]: "#83c9ff"}
    for año in años:
        serie = diario[diario["año"] == año]
        if serie.empty:
            continue
        if incluir_diario:
            figura.add_trace(go.Scatter(
                x=serie["fecha_comun"],
                y=serie[columna_valor],
                mode="lines",
                name=str(año),
                line=dict(
                    color=colores[año],
                    width=3.5 if año == años[0] else 2.5,
                ),
                hovertemplate=(
                    f"{año} · %{{x|%d/%m}}: %{{y:.2f}}<extra></extra>"
                ),
            ))
        figura.add_trace(go.Scatter(
            x=serie["fecha_comun"],
            y=serie["media_acumulada"],
            mode="lines",
            name=f"{nombre_valor} {año}",
            line=dict(color=colores[año], width=3, dash="dot"),
            hovertemplate=(
                f"{año} · %{{x|%d/%m}}: %{{y:.2f}}<extra></extra>"
            ),
        ))
    figura.update_layout(hovermode="x unified")
    figura.update_xaxes(
        range=[pd.Timestamp(2024, 1, 1), pd.Timestamp(2024, 12, 31)],
        dtick="M1",
        tickformat="%b",
        title_text="Mes",
        showgrid=True,
    )
    return diario, figura

tab_evolucion, tab_comparativa = st.tabs(
    ["Evolución anual", "Comparativa anual"]
)
col1, col2, col3 = tab_evolucion.columns(3)

with col1:
    st.caption(
        "SPOT ESIOS ID · valores en €/MWh"
        + (
            f" · último dato: {ultima_fecha.strftime('%d.%m.%Y')}"
            if ultima_fecha is not None
            else ""
        )
    )
    if datos_spot_año.empty:
        st.warning("No hay datos SPOT para el año seleccionado.")
    else:
        resumen_spot = resumir_spot(datos_spot_año)
        valores_spot = resumen_spot["diario"].set_index("fecha")["value"]
        media_anual_spot = resumen_spot["anual"].iloc[0]["value"]
        metricas_spot = st.columns(3)
        metricas_spot[0].metric(
            "Media anual",
            formato_eur_mwh(media_anual_spot, 2, False) or "Sin datos",
        )
        metricas_spot[1].metric(
            "Mínimo",
            formato_eur_mwh(valores_spot.min(), 2, False) or "Sin datos",
            delta=(
                valores_spot.idxmin().strftime("%d.%m.%Y")
                if not valores_spot.empty
                else None
            ),
            delta_color="off",
        )
        metricas_spot[2].metric(
            "Máximo",
            formato_eur_mwh(valores_spot.max(), 2, False) or "Sin datos",
            delta=(
                valores_spot.idxmax().strftime("%d.%m.%Y")
                if not valores_spot.empty
                else None
            ),
            delta_color="off",
        )
        datos_spot_diarios, figura_spot = graficar_media_acumulada_periodo(
            datos_spot_año,
            mes_num=None,
            componente="SPOT",
            predator_mode=False,
            año=año_dashboard,
        )
        prevision_omie_anual = st.session_state.get("prevision_omie_anual")
        prevision_valida = (
            isinstance(prevision_omie_anual, dict)
            and prevision_omie_anual.get("año") == año_dashboard
            and isinstance(
                prevision_omie_anual.get("curva_mensual"), pd.DataFrame
            )
        )
        if (
            not prevision_valida
            and ultima_fecha is not None
            and ultima_fecha < pd.Timestamp(año_dashboard, 12, 31)
            and año_dashboard == fecha_hoy.year
        ):
            with st.spinner("Calculando previsión OMIE hasta el 31 de diciembre..."):
                try:
                    prevision_omie_anual = obtener_prevision_omie_anual(datos_spot)
                except Exception as error_prevision:
                    st.warning(
                        "No se ha podido calcular la previsión OMIE: "
                        f"{error_prevision}"
                    )
                else:
                    guardar_prevision_omie_en_sesion(prevision_omie_anual)
                    prevision_valida = (
                        prevision_omie_anual.get("año") == año_dashboard
                    )

        if prevision_valida:
            datos_spot_previstos = construir_media_acumulada_prevista(
                datos_diarios_reales=datos_spot_diarios,
                curva_mensual_prevista=prevision_omie_anual["curva_mensual"],
                año=año_dashboard,
            )
            if not datos_spot_previstos.empty:
                figura_spot.add_trace(
                    go.Scatter(
                        x=datos_spot_previstos["fecha"],
                        y=datos_spot_previstos["media_acumulada_prevista"],
                        mode="lines",
                        name="Media acumulada prevista",
                        line=dict(color="yellow", width=3, dash="dot"),
                        hovertemplate=(
                            "<b>Media acumulada prevista</b><br>"
                            "%{x|%d-%m-%Y}<br>"
                            "%{y:.2f} €/MWh<extra></extra>"
                        ),
                    )
                )
                ultimo_spot_previsto = datos_spot_previstos.iloc[-1]
                figura_spot.add_annotation(
                    x=ultimo_spot_previsto["fecha"],
                    y=ultimo_spot_previsto["media_acumulada_prevista"],
                    text=(
                        f"Previsión {año_dashboard}: "
                        f"{ultimo_spot_previsto['media_acumulada_prevista']:.2f} "
                        "€/MWh"
                    ),
                    showarrow=False,
                    xanchor="right",
                    yshift=18,
                    font=dict(color="yellow", size=15),
                )
        figura_spot.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Evolución diaria del SPOT y media acumulada anual",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.88,
                xanchor="center",
                x=0.5,
                title_text=None,
                font=dict(size=14),
            ),
            yaxis=dict(domain=[0.0, 0.74]),
        )
        st.plotly_chart(figura_spot, use_container_width=True)

    st.caption(
        "MIBGAS D+1 · valores en €/MWh"
        + (
            f" · último dato: {ultima_fecha_gas.strftime('%d.%m.%Y')}"
            if ultima_fecha_gas is not None
            else ""
        )
    )
    if datos_mibgas_año.empty:
        st.warning("No hay datos MIBGAS D+1 para el año seleccionado.")
    else:
        valores_gas = pd.to_numeric(
            datos_mibgas_año["precio_gas"], errors="coerce"
        ).dropna()
        metricas_gas = st.columns(3)
        metricas_gas[0].metric(
            "Media anual",
            formato_eur_mwh(valores_gas.mean(), 2, False) or "Sin datos",
        )
        metricas_gas[1].metric(
            "Mínimo",
            formato_eur_mwh(valores_gas.min(), 2, False) or "Sin datos",
        )
        metricas_gas[2].metric(
            "Máximo",
            formato_eur_mwh(valores_gas.max(), 2, False) or "Sin datos",
        )
        figura_gas = graficar_da_2026_acumulado(
            datos_mibgas_da,
            año=año_dashboard,
            mes=None,
        )
        for traza in figura_gas.data:
            if traza.name == "Media acumulada diaria":
                traza.update(
                    line=dict(color="gold", width=3, dash="solid")
                )

        if (
            ultima_fecha_gas is not None
            and ultima_fecha_gas < pd.Timestamp(año_dashboard, 12, 31)
            and año_dashboard == fecha_hoy.year
        ):
            productos_mensuales = (
                "GMAES",
                "GMES_M+2",
                "GMES_M+3",
                "GMES_M+4",
                "GMES_M+5",
                "GMES_M+6",
            )
            productos_trimestrales = (
                "GQES_Q+1",
                "GQES_Q+2",
                "GQES_Q+3",
                "GQES_Q+4",
            )
            futuros_mensuales = pd.concat(
                [
                    filtrar_por_producto(datos_mibgas, producto)
                    for producto in productos_mensuales
                ],
                ignore_index=True,
            )
            futuros_trimestrales = pd.concat(
                [
                    filtrar_por_producto(datos_mibgas, producto)
                    for producto in productos_trimestrales
                ],
                ignore_index=True,
            )
            curva_mensual_gas = construir_curva_mibgas_2026(
                obtener_mibgas_mensual(datos_mibgas_da),
                futuros_mensuales,
                futuros_trimestrales,
                año=año_dashboard,
            )
            datos_gas_previstos = construir_media_acumulada_prevista(
                datos_diarios_reales=datos_mibgas_año,
                curva_mensual_prevista=curva_mensual_gas,
                año=año_dashboard,
                col_fecha_real="fecha_entrega",
                col_valor_real="precio_gas",
            )
            if not datos_gas_previstos.empty:
                figura_gas.add_trace(
                    go.Scatter(
                        x=datos_gas_previstos["fecha"],
                        y=datos_gas_previstos["media_acumulada_prevista"],
                        mode="lines",
                        name="Media acumulada prevista",
                        line=dict(color="gold", width=3, dash="dot"),
                        hovertemplate=(
                            "<b>Media acumulada prevista</b><br>"
                            "%{x|%d-%m-%Y}<br>"
                            "%{y:.2f} €/MWh<extra></extra>"
                        ),
                    )
                )
                ultimo_gas_previsto = datos_gas_previstos.iloc[-1]
                figura_gas.add_annotation(
                    x=ultimo_gas_previsto["fecha"],
                    y=ultimo_gas_previsto["media_acumulada_prevista"],
                    text=(
                        f"Previsión {año_dashboard}: "
                        f"{ultimo_gas_previsto['media_acumulada_prevista']:.2f} "
                        "€/MWh"
                    ),
                    showarrow=False,
                    xanchor="right",
                    yshift=18,
                    font=dict(color="gold", size=15),
                )
        figura_gas.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Evolución diaria del gas MIBGAS D+1 y media acumulada anual",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.88,
                xanchor="center",
                x=0.5,
                title_text=None,
                font=dict(size=14),
            ),
            yaxis=dict(domain=[0.0, 0.74]),
        )
        st.plotly_chart(figura_gas, use_container_width=True)

with col2:
    st.caption(
        "Perfil horario medio anual · sin ponderación por curva de carga"
        + (
            f" · último dato: {ultima_fecha_indexado.strftime('%d.%m.%Y')}"
            if ultima_fecha_indexado is not None
            else ""
        )
    )
    if datos_indexado_año.empty:
        st.warning("No hay datos de indexado para el año seleccionado.")
    else:
        metricas_elasticidad = st.columns(3)
        for contenedor, atr in zip(
            metricas_elasticidad, ("2.0", "3.0", "6.1")
        ):
            resultados_elasticidad, _ = analizar_dependencia_omie(
                datos_indexado_año,
                atr,
            )
            fila_año = (
                resultados_elasticidad[
                    resultados_elasticidad["año"] == año_dashboard
                ]
                if "año" in resultados_elasticidad.columns
                else pd.DataFrame()
            )
            elasticidad = (
                fila_año["elasticidad"].iloc[0]
                if not fila_año.empty
                else None
            )
            contenedor.metric(
                f"Elasticidad ATR {atr}",
                (
                    formato_pct(elasticidad * 100, 1, True)
                    if elasticidad is not None
                    else "Sin datos"
                ),
            )
        figura_indexado = graficar_precios_medios_horarios(
            datos_indexado_año,
            colores_precios,
            incluir_curva=False,
            leyenda_horizontal=True,
        )
        figura_indexado.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Precios horarios medios anuales según peaje",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.88,
                xanchor="center",
                x=0.5,
                title_text=None,
                font=dict(size=14),
            ),
            yaxis=dict(domain=[0.0, 0.74]),
        )
        st.plotly_chart(figura_indexado, use_container_width=True)

        st.caption(
            "Media acumulada diaria anual según ATR · valores en c€/kWh · "
            "sin ponderación por curva de carga"
            + (
                f" · último dato: {ultima_fecha_indexado.strftime('%d.%m.%Y')}"
                if ultima_fecha_indexado is not None
                else ""
            )
        )
        metricas_indexado = st.columns(3)
        for contenedor, columna, atr in zip(
            metricas_indexado,
            ("precio_2.0", "precio_3.0", "precio_6.1"),
            ("2.0", "3.0", "6.1"),
        ):
            precio_medio = pd.to_numeric(
                datos_indexado_año[columna], errors="coerce"
            ).mean() / 10
            contenedor.metric(
                f"Precio medio {atr}",
                formato_cent_eur_kwh(precio_medio, 2, False) or "Sin datos",
            )
        _, figura_indexado_acumulada = graficar_media_acumulada_mensual_atr(
            datos_indexado_año,
            colores_precios,
            año=año_dashboard,
            mes=None,
        )
        figura_indexado_acumulada.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Media acumulada diaria anual según peaje",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.88,
                xanchor="center",
                x=0.5,
                title_text=None,
                font=dict(size=14),
            ),
            yaxis=dict(domain=[0.0, 0.74]),
        )
        figura_indexado_acumulada.update_xaxes(
            dtick="M1",
            tickformat="%b",
            title_text="Mes",
            range=[
                pd.Timestamp(año_dashboard, 1, 1),
                pd.Timestamp(año_dashboard, 12, 31),
            ],
        )
        st.plotly_chart(
            figura_indexado_acumulada,
            use_container_width=True,
        )

with col3:
    st.caption(
        "Demanda real peninsular · ESIOS · valores en GW"
        + (
            f" · último dato: {ultima_fecha_demanda.strftime('%d.%m.%Y')}"
            if ultima_fecha_demanda is not None
            else ""
        )
    )
    if datos_demanda_año.empty:
        st.warning("No hay datos de demanda para el año seleccionado.")
    else:
        valores_demanda = (
            datos_demanda_año.assign(
                datetime=pd.to_datetime(
                    datos_demanda_año["datetime"], errors="coerce"
                ).dt.floor("D"),
                GW=pd.to_numeric(datos_demanda_año["GW"], errors="coerce"),
            )
            .dropna(subset=["datetime", "GW"])
            .groupby("datetime")["GW"]
            .mean()
        )
        metricas_demanda = st.columns(3)
        metricas_demanda[0].metric(
            "Media anual",
            formato_numero_es(valores_demanda.mean(), 2)
            if not valores_demanda.empty
            else "Sin datos",
        )
        metricas_demanda[1].metric(
            "Mínimo",
            formato_numero_es(valores_demanda.min(), 2)
            if not valores_demanda.empty
            else "Sin datos",
            delta=(
                valores_demanda.idxmin().strftime("%d.%m.%Y")
                if not valores_demanda.empty
                else None
            ),
            delta_color="off",
        )
        metricas_demanda[2].metric(
            "Máximo",
            formato_numero_es(valores_demanda.max(), 2)
            if not valores_demanda.empty
            else "Sin datos",
            delta=(
                valores_demanda.idxmax().strftime("%d.%m.%Y")
                if not valores_demanda.empty
                else None
            ),
            delta_color="off",
        )
        figura_demanda = graficar_demanda_anual(
            datos_demanda_año,
            año_dashboard,
        )
        figura_demanda.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Demanda diaria y media acumulada anual",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=0.88,
                xanchor="center",
                x=0.5,
                title_text=None,
                font=dict(size=14),
            ),
            yaxis=dict(domain=[0.0, 0.74]),
        )
        st.plotly_chart(figura_demanda, use_container_width=True)

    st.caption(
        "Estructura de generación REData · valores en GWh"
        + (
            f" · último dato: {ultima_fecha_generacion.strftime('%d.%m.%Y')}"
            if ultima_fecha_generacion is not None
            else ""
        )
    )
    if datos_mix_generacion.empty:
        st.warning("No hay datos de generación para el año seleccionado.")
    else:
        tecnologias_lideres = (
            datos_mix_generacion[
                datos_mix_generacion["tecnologia"] != "Resto"
            ]
            .nlargest(3, "generacion_GWh")
            .reset_index(drop=True)
        )
        metricas_generacion = st.columns(3)
        for posicion, contenedor in enumerate(metricas_generacion):
            if posicion < len(tecnologias_lideres):
                tecnologia = tecnologias_lideres.iloc[posicion]
                contenedor.metric(
                    tecnologia["tecnologia"],
                    formato_numero_es(tecnologia["generacion_GWh"], 0),
                )
            else:
                contenedor.metric("Sin tecnología", "Sin datos")
        figura_mix = graficar_mix_queso(
            datos_mix_generacion,
            COLORES_MIX_GENERACION,
        )
        figura_mix.update_layout(
            height=500,
            margin=dict(l=45, r=20, t=30, b=50),
            title=dict(
                text="Mix de generación anual (%)",
                x=0.5,
                xanchor="center",
                y=0.98,
                yanchor="top",
                font=dict(size=22),
            ),
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.37,
                xanchor="left",
                x=0.69,
                title_text=None,
                font=dict(size=14),
            ),
        )
        figura_mix.update_traces(
            domain=dict(x=[0.0, 0.66], y=[0.0, 0.74]),
            selector=dict(type="pie"),
        )
        st.plotly_chart(figura_mix, use_container_width=True)


# COMPARATIVA ANUAL
comp_col1, comp_col2, comp_col3 = tab_comparativa.columns(3)

datos_spot_comparativa = datos_spot[
    datos_spot["año"].isin([año_dashboard, año_base_comparativa])
].copy()
datos_spot_metricas = limitar_hasta_fecha_equivalente(
    datos_spot_comparativa,
    "fecha",
    ultima_fecha,
)
medias_spot = (
    datos_spot_metricas.assign(
        año=lambda df: pd.to_datetime(df["fecha"]).dt.year
    )
    .groupby("año")["value"]
    .mean()
    .to_dict()
    if not datos_spot_metricas.empty
    else {}
)

with comp_col1:
    st.caption(
        f"SPOT · {año_dashboard} frente a {año_base_comparativa}"
        + (
            f" · metrics hasta el {ultima_fecha.strftime('%d.%m')}"
            if ultima_fecha is not None
            else ""
        )
    )
    media_spot_actual = medias_spot.get(año_dashboard)
    media_spot_base = medias_spot.get(año_base_comparativa)
    metrica_actual, metrica_base, metrica_diferencia = st.columns(3)
    metrica_actual.metric(
        f"SPOT {año_dashboard}",
        formato_eur_mwh(media_spot_actual, 2, False) or "Sin datos",
    )
    metrica_base.metric(
        f"SPOT {año_base_comparativa}",
        formato_eur_mwh(media_spot_base, 2, False) or "Sin datos",
    )
    if media_spot_actual is None or media_spot_base is None:
        diferencia_spot = diferencia_spot_pct = None
    else:
        diferencia_spot = media_spot_actual - media_spot_base
        diferencia_spot_pct = (
            diferencia_spot / media_spot_base * 100
            if media_spot_base != 0
            else None
        )
    metrica_diferencia.metric(
        "Diferencia",
        (
            ("+" if diferencia_spot > 0 else "")
            + formato_eur_mwh(diferencia_spot, 2, False)
            if diferencia_spot is not None
            else "Sin datos"
        ),
        delta=(
            ("+" if diferencia_spot_pct > 0 else "")
            + formato_pct(diferencia_spot_pct, 2, True)
            if diferencia_spot_pct is not None
            else None
        ),
        delta_color="inverse",
    )
    _, figura_spot_comparativa = graficar_comparativa_acumulada_anual(
        datos_spot_comparativa,
        "fecha",
        "value",
        (año_dashboard, año_base_comparativa),
        "SPOT",
    )
    for traza in figura_spot_comparativa.data:
        ancho = 2.2 if str(traza.name).startswith("SPOT ") else 1.6
        traza.update(line=dict(width=ancho))
    figura_spot_comparativa.update_layout(
        height=500,
        title=dict(
            text="Media acumulada anual del SPOT",
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        legend=dict(
            orientation="h",
            y=1.03,
            yanchor="bottom",
            x=0.5,
            xanchor="center",
        ),
        yaxis_title="€/MWh",
    )
    st.plotly_chart(figura_spot_comparativa, use_container_width=True)

    _, figura_spot_horaria = graficar_comparativa_spot_horaria_mensual(
        datos_spot_comparativa,
        mes=None,
        año_actual=año_dashboard,
        año_comparacion=año_base_comparativa,
    )
    st.caption(
        "Diferenciales del perfil horario medio anual · "
        f"{año_dashboard} − {año_base_comparativa} · valores en €/MWh"
        + (
            f" · ambos hasta el {ultima_fecha.strftime('%d.%m')}"
            if ultima_fecha is not None
            else ""
        )
    )
    perfiles_horarios_metricas = (
        datos_spot_metricas.assign(
            año=lambda df: pd.to_datetime(df["fecha"]).dt.year,
            hora=lambda df: pd.to_numeric(df["hora"], errors="coerce"),
            value=lambda df: pd.to_numeric(df["value"], errors="coerce"),
        )
        .dropna(subset=["hora", "value"])
        .groupby(["año", "hora"])["value"]
        .mean()
        .unstack("año")
    )
    metrica_h_media, metrica_h_min, metrica_h_max = st.columns(3)
    if {año_dashboard, año_base_comparativa}.issubset(
        perfiles_horarios_metricas.columns
    ):
        diferencial_horario = (
            perfiles_horarios_metricas[año_dashboard]
            - perfiles_horarios_metricas[año_base_comparativa]
        ).dropna()
    else:
        diferencial_horario = pd.Series(dtype=float)
    if diferencial_horario.empty:
        metrica_h_media.metric("Diferencial horario medio", "Sin datos")
        metrica_h_min.metric("Diferencial horario mínimo", "Sin datos")
        metrica_h_max.metric("Diferencial horario máximo", "Sin datos")
    else:
        diferencial_medio = diferencial_horario.mean()
        diferencial_minimo = diferencial_horario.min()
        diferencial_maximo = diferencial_horario.max()
        hora_minima = int(diferencial_horario.idxmin())
        hora_maxima = int(diferencial_horario.idxmax())
        metrica_h_media.metric(
            "Diferencial horario medio",
            ("+" if diferencial_medio > 0 else "")
            + formato_eur_mwh(diferencial_medio, 2, False),
        )
        metrica_h_min.metric(
            "Diferencial horario mínimo",
            ("+" if diferencial_minimo > 0 else "")
            + formato_eur_mwh(diferencial_minimo, 2, False),
            delta=f"Hora {hora_minima:02d}",
            delta_color="off",
        )
        metrica_h_max.metric(
            "Diferencial horario máximo",
            ("+" if diferencial_maximo > 0 else "")
            + formato_eur_mwh(diferencial_maximo, 2, False),
            delta=f"Hora {hora_maxima:02d}",
            delta_color="off",
        )
    figura_spot_horaria.update_layout(
        height=500,
        title=dict(
            text="Perfil horario medio anual del SPOT",
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=0.88,
            xanchor="center",
            x=0.5,
            title_text=None,
            font=dict(size=14),
        ),
        yaxis=dict(domain=[0.0, 0.74]),
    )
    st.plotly_chart(figura_spot_horaria, use_container_width=True)

with comp_col2:
    datos_indexado_comparativa = datos_indexado[
        datos_indexado["fecha"].dt.year.isin(
            [año_dashboard, año_base_comparativa]
        )
    ].copy()
    datos_indexado_metricas = limitar_hasta_fecha_equivalente(
        datos_indexado_comparativa,
        "fecha",
        ultima_fecha_indexado,
    )
    columnas_indexado_comparativa = [
        "spot", "precio_2.0", "precio_3.0", "precio_6.1"
    ]
    columnas_atr = ["precio_2.0", "precio_3.0", "precio_6.1"]
    medias_indexado = (
        datos_indexado_metricas.assign(
            año=lambda df: df["fecha"].dt.year
        )
        .groupby("año")[columnas_indexado_comparativa]
        .mean()
        .div(10)
    )
    st.caption(
        f"Precios finales ATR · {año_dashboard} frente a "
        f"{año_base_comparativa}"
        + (
            f" · ambos hasta el {ultima_fecha_indexado.strftime('%d.%m')}"
            if ultima_fecha_indexado is not None
            else ""
        )
    )
    metricas_atr = st.columns(3)
    for contenedor, columna, atr in zip(
        metricas_atr, columnas_atr, ("2.0", "3.0", "6.1")
    ):
        if {año_dashboard, año_base_comparativa}.issubset(medias_indexado.index):
            actual = medias_indexado.loc[año_dashboard, columna]
            base = medias_indexado.loc[año_base_comparativa, columna]
            delta = actual - base
            delta_pct = delta / base * 100 if base != 0 else None
            contenedor.metric(
                f"Diferencia {atr}",
                ("+" if delta > 0 else "")
                + formato_cent_eur_kwh(delta, 2, False),
                delta=(
                    ("+" if delta_pct > 0 else "")
                    + formato_pct(delta_pct, 2, True)
                    if delta_pct is not None
                    else None
                ),
                delta_color="inverse",
            )
        else:
            contenedor.metric(f"Diferencia {atr}", "Sin datos")
    resumen_indexado_anual = medias_indexado.reset_index()
    resumen_indexado_anual["mes_num"] = 1
    _, figura_indexado_comparativa = graficar_diferencial_precios_mensuales(
        df_mensual=resumen_indexado_anual,
        anio_base=año_base_comparativa,
        anio_comp=año_dashboard,
        convertir_a_cent_kwh=False,
        mes_num=1,
    )
    figura_indexado_comparativa.update_layout(
        height=500,
        title=dict(
            text="Diferencia anual real de precios (%)",
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        legend=dict(
            orientation="h",
            y=1.03,
            yanchor="bottom",
            x=0.5,
            xanchor="center",
            title_text=None,
        ),
        yaxis_title="Diferencia %",
    )
    st.plotly_chart(figura_indexado_comparativa, use_container_width=True)

    datos_gas_comparativa = datos_mibgas_da[
        datos_mibgas_da["fecha_entrega"].dt.year.isin(
            [año_dashboard, año_base_comparativa]
        )
    ].copy()
    datos_gas_metricas = limitar_hasta_fecha_equivalente(
        datos_gas_comparativa,
        "fecha_entrega",
        ultima_fecha_gas,
    )
    medias_gas = (
        datos_gas_metricas.assign(
            año=lambda df: df["fecha_entrega"].dt.year
        )
        .groupby("año")["precio_gas"]
        .mean()
        .to_dict()
        if not datos_gas_metricas.empty
        else {}
    )
    st.caption(
        f"MIBGAS D+1 · {año_dashboard} frente a {año_base_comparativa}"
        + (
            f" · metrics hasta el {ultima_fecha_gas.strftime('%d.%m')}"
            if ultima_fecha_gas is not None
            else ""
        )
    )
    gas_actual = medias_gas.get(año_dashboard)
    gas_base = medias_gas.get(año_base_comparativa)
    gas_cols = st.columns(3)
    gas_cols[0].metric(
        f"MIBGAS {año_dashboard}",
        formato_eur_mwh(gas_actual, 2, False) or "Sin datos",
    )
    gas_cols[1].metric(
        f"MIBGAS {año_base_comparativa}",
        formato_eur_mwh(gas_base, 2, False) or "Sin datos",
    )
    diferencia_gas = (
        gas_actual - gas_base
        if gas_actual is not None and gas_base is not None
        else None
    )
    gas_cols[2].metric(
        "Diferencia",
        (
            ("+" if diferencia_gas > 0 else "")
            + formato_eur_mwh(diferencia_gas, 2, False)
            if diferencia_gas is not None
            else "Sin datos"
        ),
        delta=(
            formato_pct(diferencia_gas / gas_base * 100, 2, True)
            if diferencia_gas is not None and gas_base != 0
            else None
        ),
        delta_color="inverse",
    )
    _, figura_gas_comparativa = graficar_comparativa_acumulada_anual(
        datos_gas_comparativa,
        "fecha_entrega",
        "precio_gas",
        (año_dashboard, año_base_comparativa),
        "MIBGAS",
    )
    for traza in figura_gas_comparativa.data:
        ancho = 2.2 if str(traza.name).startswith("MIBGAS ") else 1.6
        traza.update(line=dict(width=ancho))
    figura_gas_comparativa.update_layout(
        height=500,
        title=dict(
            text="Media acumulada anual MIBGAS D+1",
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        legend=dict(
            orientation="h",
            y=1.03,
            yanchor="bottom",
            x=0.5,
            xanchor="center",
        ),
        yaxis_title="€/MWh",
    )
    st.plotly_chart(figura_gas_comparativa, use_container_width=True)

with comp_col3:
    demanda_comparativa = pd.concat(
        [datos_demanda_base, datos_demanda_año], ignore_index=True
    )
    demanda_metricas = limitar_hasta_fecha_equivalente(
        demanda_comparativa,
        "datetime",
        ultima_fecha_demanda,
    )
    medias_demanda = (
        demanda_metricas.assign(
            año=lambda df: pd.to_datetime(df["datetime"]).dt.year
        )
        .groupby("año")["GW"]
        .mean()
        .to_dict()
        if not demanda_metricas.empty
        else {}
    )
    st.caption(
        f"Demanda real · {año_dashboard} frente a {año_base_comparativa}"
        + (
            f" · metrics hasta el {ultima_fecha_demanda.strftime('%d.%m')}"
            if ultima_fecha_demanda is not None
            else ""
        )
    )
    demanda_actual = medias_demanda.get(año_dashboard)
    demanda_base = medias_demanda.get(año_base_comparativa)
    demanda_cols = st.columns(3)
    demanda_cols[0].metric(
        f"Demanda {año_dashboard}",
        formato_numero_es(demanda_actual, 2) if demanda_actual is not None else "Sin datos",
    )
    demanda_cols[1].metric(
        f"Demanda {año_base_comparativa}",
        formato_numero_es(demanda_base, 2) if demanda_base is not None else "Sin datos",
    )
    diferencia_demanda = (
        demanda_actual - demanda_base
        if demanda_actual is not None and demanda_base is not None
        else None
    )
    demanda_cols[2].metric(
        "Diferencia",
        (
            ("+" if diferencia_demanda > 0 else "")
            + formato_numero_es(diferencia_demanda, 2)
            if diferencia_demanda is not None
            else "Sin datos"
        ),
        delta=(
            formato_pct(diferencia_demanda / demanda_base * 100, 2, True)
            if diferencia_demanda is not None and demanda_base != 0
            else None
        ),
        delta_color="inverse",
    )
    _, figura_demanda_comparativa = graficar_comparativa_acumulada_anual(
        demanda_comparativa,
        "datetime",
        "GW",
        (año_dashboard, año_base_comparativa),
        "Demanda",
        incluir_diario=False,
    )
    figura_demanda_comparativa.update_layout(
        height=500,
        title=dict(
            text="Demanda media acumulada anual comparada",
            x=0.5,
            xanchor="center",
            font=dict(size=22),
        ),
        legend=dict(
            orientation="h",
            y=1.03,
            yanchor="bottom",
            x=0.5,
            xanchor="center",
        ),
        yaxis_title="GW",
    )
    st.plotly_chart(figura_demanda_comparativa, use_container_width=True)

    generacion_actual = preparar_mix_generacion_anual(
        datos_generacion,
        año_dashboard,
    )
    datos_generacion_base = limitar_hasta_fecha_equivalente(
        datos_generacion[datos_generacion["año"] == año_base_comparativa],
        "fecha",
        ultima_fecha_generacion,
    )
    generacion_base = preparar_mix_generacion_anual(
        datos_generacion_base,
        año_base_comparativa,
    )
    st.caption(
        f"Generación · ambos años hasta "
        + (
            ultima_fecha_generacion.strftime("%d.%m")
            if ultima_fecha_generacion is not None
            else "la última fecha disponible"
        )
    )
    if generacion_actual.empty or generacion_base.empty:
        st.warning("No hay datos suficientes para comparar la generación.")
    else:
        total_actual = generacion_actual["generacion_GWh"].sum()
        total_base = generacion_base["generacion_GWh"].sum()
        diferencia_generacion = total_actual - total_base
        gen_cols = st.columns(3)
        gen_cols[0].metric(
            f"Generación {año_dashboard}",
            formato_numero_es(total_actual, 0) + " GWh",
        )
        gen_cols[1].metric(
            f"Generación {año_base_comparativa}",
            formato_numero_es(total_base, 0) + " GWh",
        )
        gen_cols[2].metric(
            "Diferencia",
            ("+" if diferencia_generacion > 0 else "")
            + formato_numero_es(diferencia_generacion, 0)
            + " GWh",
            delta=formato_pct(
                diferencia_generacion / total_base * 100,
                2,
                True,
            ) if total_base != 0 else None,
            delta_color="inverse",
        )
        figura_generacion_comparativa = graficar_mix_comparativo(
            generacion_actual,
            generacion_base,
            año_actual=año_dashboard,
            año_base=año_base_comparativa,
            tipo="Barras",
            unidad="GWh",
            colores_tecnologia=COLORES_MIX_GENERACION,
        )
        figura_generacion_comparativa.update_layout(
            height=500,
            title=dict(
                text="Generación anual comparada (GWh)",
                x=0.5,
                xanchor="center",
                font=dict(size=22),
            ),
        )
        st.plotly_chart(
            figura_generacion_comparativa,
            use_container_width=True,
        )
