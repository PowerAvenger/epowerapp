from datetime import date

import pandas as pd
import streamlit as st

from backend_comun import carga_mibgas, colores_precios
from backend_escalacv import (
    cargar_datos_escalacv,
    graficar_comparativa_spot_horaria_mensual,
    graficar_comparativa_spot_mensual,
    graficar_media_acumulada_periodo,
)
from backend_demanda import (
    graficar_media_diaria,
    obtener_demanda_mensual_dashboard,
)
from backend_telemindex import (
    graficar_diferencial_precios_mensuales,
    graficar_media_acumulada_mensual_atr,
    graficar_precios_medios_horarios,
)
from backend_mibgas import (
    filtrar_por_producto,
    graficar_comparativa_gas_mensual,
    graficar_da_2026_acumulado,
)
from backend_redata_potgen import (
    COLORES_MIX_GENERACION,
    graficar_mix_comparativo,
    graficar_mix_queso,
    leer_json as leer_json_redata,
    preparar_mix_generacion_mensual,
)
from utilidades import generar_menu, init_app, init_app_index
from formato_es import (
    formato_cent_eur_kwh,
    formato_eur_mwh,
    formato_numero_es,
    formato_pct,
)


if (
    not st.session_state.get("usuario_autenticado", False)
    and not st.session_state.get("usuario_free", False)
):
    st.switch_page("epowerapp.py")

generar_menu()

fecha_hoy = date.today()
ALTURA_GRAFICOS = 500
TAMAÑO_TITULOS_GRAFICOS = 22
TAMAÑO_LEYENDAS_GRAFICOS = 14


def configurar_figura_dashboard(figura, titulo=None):
    """Aplica una geometría común a todas las figuras del dashboard."""
    cambios = {
        "height": ALTURA_GRAFICOS,
        "margin": dict(l=45, r=20, t=30, b=50),
        "legend": dict(
            orientation="h",
            yanchor="top",
            y=0.88,
            xanchor="center",
            x=0.5,
            title_text=None,
            font=dict(size=TAMAÑO_LEYENDAS_GRAFICOS),
        ),
        "yaxis": dict(domain=[0.0, 0.74]),
    }
    if titulo is not None:
        cambios["title"] = dict(
            text=titulo,
            x=0.5,
            xanchor="center",
            y=0.98,
            yanchor="top",
            font=dict(size=TAMAÑO_TITULOS_GRAFICOS),
        )
    else:
        titulo_actual = figura.layout.title.text
        cambios["title"] = dict(
            text=titulo_actual,
            x=0.5,
            xanchor="center",
            y=0.98,
            yanchor="top",
            font=dict(size=TAMAÑO_TITULOS_GRAFICOS),
        )
    figura.update_layout(**cambios)
    return figura


meses = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

st.sidebar.header("Período del dashboard")
año_dashboard = st.sidebar.selectbox(
    "Año",
    options=list(range(fecha_hoy.year, 2023, -1)),
    key="indicadores_año",
)
mes_dashboard = st.sidebar.selectbox(
    "Mes",
    options=list(meses),
    index=fecha_hoy.month - 1,
    format_func=lambda numero: meses[numero].capitalize(),
    key="indicadores_mes",
)

st.sidebar.header("Escala CV")
componente = st.sidebar.radio(
    "Componente de mercado",
    options=["SPOT", "SSAA", "SPOT+SSAA"],
    key="indicadores_escala_componente",
)
predator_mode = False
if componente == "SPOT+SSAA":
    predator_mode = st.sidebar.toggle(
        "Predator Mode",
        key="indicadores_escala_predator",
    )

st.sidebar.header("Comparativa de generación")
tipo_mix_comparativo = st.sidebar.selectbox(
    "Visualización del mix",
    options=["Barras", "Quesos concéntricos", "Quesos paralelos"],
    key="indicadores_tipo_mix_comparativo_v2",
)
unidad_mix_comparativo = st.sidebar.selectbox(
    "Unidad de generación",
    options=["% del mix", "GWh"],
    key="indicadores_unidad_mix_comparativo",
)

st.subheader(f"Evolución del mes de {meses[mes_dashboard]}.")

with st.spinner("Cargando datos de mercado..."):
    datos, _, fecha_fin = cargar_datos_escalacv(
        componente=componente,
        file_id_spot=st.secrets["FILE_ID_SPOT"],
        file_id_ssaa=st.secrets["FILE_ID_SSAA"],
        creds_dict=st.secrets["GOOGLE_SHEETS_CREDENTIALS"],
    )
    datos_spot_comparativa, _, fecha_fin_spot = cargar_datos_escalacv(
        componente="SPOT",
        file_id_spot=st.secrets["FILE_ID_SPOT"],
        file_id_ssaa=st.secrets["FILE_ID_SSAA"],
        creds_dict=st.secrets["GOOGLE_SHEETS_CREDENTIALS"],
    )

datos_mes = datos[
    (datos["año"] == año_dashboard) & (datos["mes"] == mes_dashboard)
].copy()

with st.spinner("Preparando precios de indexado..."):
    init_app()
    init_app_index()
    datos_indexado = st.session_state.df_sheets.copy()
    datos_indexado["fecha"] = pd.to_datetime(datos_indexado["fecha"])
    datos_indexado_mes = datos_indexado[
        (datos_indexado["fecha"].dt.year == año_dashboard)
        & (datos_indexado["fecha"].dt.month == mes_dashboard)
    ].copy()
with st.spinner("Preparando demanda peninsular..."):
    datos_demanda, ultimo_real_demanda, hay_prevision_demanda = (
        obtener_demanda_mensual_dashboard(año_dashboard, mes_dashboard)
    )
    if not datos_demanda.empty:
        # Normalizamos también al salir de la caché: en Streamlit Cloud una
        # respuesta antigua de ESIOS puede recuperar esta columna como object.
        datos_demanda["datetime"] = (
            pd.to_datetime(
                datos_demanda["datetime"],
                format="mixed",
                errors="coerce",
                utc=True,
            )
            .dt.tz_convert("Europe/Madrid")
            .dt.tz_localize(None)
        )
        datos_demanda = datos_demanda.dropna(subset=["datetime"])

with st.spinner("Preparando mercado de gas..."):
    datos_mibgas = carga_mibgas()
    datos_mibgas_da = filtrar_por_producto(datos_mibgas, "GDAES_D+1")
    datos_mibgas_mes = datos_mibgas_da[
        (datos_mibgas_da["fecha_entrega"].dt.year == año_dashboard)
        & (datos_mibgas_da["fecha_entrega"].dt.month == mes_dashboard)
    ].copy()

with st.spinner("Preparando mix de generación..."):
    datos_generacion = leer_json_redata(
        st.secrets["FILE_ID_GEN"],
        "estructura-generacion",
    )
    datos_mix_generacion = preparar_mix_generacion_mensual(
        datos_generacion,
        año=año_dashboard,
        mes=mes_dashboard,
    )

    año_actual_mix = fecha_hoy.year
    año_base_mix = 2025
    fechas_mix_actual = datos_generacion.loc[
        (datos_generacion["año"] == año_actual_mix)
        & (datos_generacion["mes_num"] == mes_dashboard),
        "fecha",
    ]
    ultima_fecha_mix_actual = (
        fechas_mix_actual.max() if not fechas_mix_actual.empty else None
    )
    dia_limite_mix = (
        ultima_fecha_mix_actual.day
        if ultima_fecha_mix_actual is not None
        and not pd.isna(ultima_fecha_mix_actual)
        else None
    )
    datos_mix_actual_comparativa = preparar_mix_generacion_mensual(
        datos_generacion,
        año=año_actual_mix,
        mes=mes_dashboard,
        hasta_dia=dia_limite_mix,
    )
    datos_mix_base_comparativa = preparar_mix_generacion_mensual(
        datos_generacion,
        año=año_base_mix,
        mes=mes_dashboard,
        hasta_dia=dia_limite_mix,
    )

tab_evolucion, tab_comparativa = st.tabs(
    ["Evolución mensual", "Comparativa mensual"]
)

col1, col2, col3 = tab_evolucion.columns(3)

with col1:
    st.caption(
        "SPOT y SSAA ESIOS ID · "
        "valores en €/MWh · "
        f"último dato: {fecha_fin.strftime('%d.%m.%Y')}"
    )
    if datos_mes.empty:
        st.warning("No hay datos para el período seleccionado.")
    else:
        valores_mercado = (
            datos_mes.assign(
                fecha=pd.to_datetime(datos_mes["fecha"], errors="coerce").dt.floor("D"),
                value=pd.to_numeric(datos_mes["value"], errors="coerce"),
            )
            .dropna(subset=["fecha", "value"])
            .groupby("fecha")["value"]
            .mean()
        )
        metricas_spot = st.columns(3)
        metricas_spot[0].metric(
            "Media mensual",
            formato_eur_mwh(valores_mercado.mean(), 2, False) or "Sin datos",
        )
        metricas_spot[1].metric(
            "Mínimo",
            formato_eur_mwh(valores_mercado.min(), 2, False) or "Sin datos",
            delta=(
                valores_mercado.idxmin().strftime("%d.%m.%Y")
                if not valores_mercado.empty else None
            ),
            delta_color="off",
        )
        metricas_spot[2].metric(
            "Máximo",
            formato_eur_mwh(valores_mercado.max(), 2, False) or "Sin datos",
            delta=(
                valores_mercado.idxmax().strftime("%d.%m.%Y")
                if not valores_mercado.empty else None
            ),
            delta_color="off",
        )
        _, figura = graficar_media_acumulada_periodo(
            datos_mes,
            mes_num=mes_dashboard,
            componente=componente,
            predator_mode=predator_mode,
            año=año_dashboard,
        )
        figura = configurar_figura_dashboard(figura)
        st.plotly_chart(figura, use_container_width=True)

    if datos_mibgas_mes.empty:
        st.warning("No hay datos MIBGAS D+1 para el período seleccionado.")
    else:
        ultima_fecha_gas = datos_mibgas_mes["fecha_entrega"].max()
        st.caption(
            "MIBGAS D+1 · valores en €/MWh · "
            f"último dato del período: {ultima_fecha_gas.strftime('%d.%m.%Y')}"
        )
        valores_gas = pd.to_numeric(
            datos_mibgas_mes["precio_gas"], errors="coerce"
        ).dropna()
        metricas_gas = st.columns(3)
        metricas_gas[0].metric(
            "Media mensual",
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
            mes=mes_dashboard,
        )
        figura_gas = configurar_figura_dashboard(
            figura_gas,
            "Evolución diaria del gas MIBGAS D+1",
        )
        st.plotly_chart(figura_gas, use_container_width=True)

with col2:
    ultima_fecha_indexado = (
        datos_indexado_mes["fecha"].max()
        if not datos_indexado_mes.empty else None
    )
    st.caption(
        "Perfil horario medio mensual · sin ponderación por curva de carga"
        + (
            f" · último dato: {ultima_fecha_indexado.strftime('%d.%m.%Y')}"
            if ultima_fecha_indexado is not None else ""
        )
    )
    if datos_indexado_mes.empty:
        st.warning("No hay datos de indexado para el período seleccionado.")
    else:
        metricas_peso_spot = st.columns(3)
        for contenedor, atr in zip(
            metricas_peso_spot, ("2.0", "3.0", "6.1")
        ):
            spot_medio = pd.to_numeric(
                datos_indexado_mes["spot"], errors="coerce"
            ).mean()
            precio_medio_atr = pd.to_numeric(
                datos_indexado_mes[f"precio_{atr}"], errors="coerce"
            ).mean()
            peso_spot = (
                spot_medio / precio_medio_atr
                if pd.notna(spot_medio)
                and pd.notna(precio_medio_atr)
                and precio_medio_atr != 0
                else None
            )
            contenedor.metric(
                f"Peso SPOT ATR {atr}",
                (
                    formato_pct(peso_spot * 100, 1, True)
                    if peso_spot is not None else "Sin datos"
                ),
            )
        figura_indexado = graficar_precios_medios_horarios(
            datos_indexado_mes,
            colores_precios,
            incluir_curva=False,
            leyenda_horizontal=True,
        )
        figura_indexado = configurar_figura_dashboard(
            figura_indexado,
            "Precios horarios medios según peaje",
        )
        st.plotly_chart(figura_indexado, use_container_width=True)

        st.caption(
            "Media acumulada diaria mensual según ATR · valores en c€/kWh · "
            "sin ponderación por curva de carga"
            + (
                f" · último dato: {ultima_fecha_indexado.strftime('%d.%m.%Y')}"
                if ultima_fecha_indexado is not None else ""
            )
        )
        metricas_indexado = st.columns(3)
        for contenedor, columna, atr in zip(
            metricas_indexado,
            ("precio_2.0", "precio_3.0", "precio_6.1"),
            ("2.0", "3.0", "6.1"),
        ):
            precio_medio = pd.to_numeric(
                datos_indexado_mes[columna], errors="coerce"
            ).mean() / 10
            contenedor.metric(
                f"Precio medio {atr}",
                formato_cent_eur_kwh(precio_medio, 2, False) or "Sin datos",
            )
        _, figura_indexado_acumulada = graficar_media_acumulada_mensual_atr(
            datos_indexado_mes,
            colores_precios,
            año=año_dashboard,
            mes=mes_dashboard,
        )
        figura_indexado_acumulada = configurar_figura_dashboard(
            figura_indexado_acumulada,
            "Media acumulada diaria según peaje",
        )
        st.plotly_chart(figura_indexado_acumulada, use_container_width=True)

with col3:
    if ultimo_real_demanda is None:
        st.caption("Demanda real peninsular · ESIOS · valores en GW")
    else:
        st.caption(
            "Demanda real peninsular"
            + (" y prevista" if hay_prevision_demanda else "")
            + " · valores en GW"
            + f" · último real: {ultimo_real_demanda.strftime('%d.%m.%Y')}"
        )
    if datos_demanda.empty:
        st.warning("No hay datos de demanda para el período seleccionado.")
    else:
        datos_demanda_evolucion = datos_demanda[
            datos_demanda["año"] == año_dashboard
        ].copy()
        valores_demanda = (
            datos_demanda_evolucion[
                datos_demanda_evolucion["short_name"] == "Demanda real"
            ]
            .assign(
                datetime=lambda datos_: pd.to_datetime(
                    datos_["datetime"], errors="coerce"
                ).dt.floor("D"),
                GW=lambda datos_: pd.to_numeric(datos_["GW"], errors="coerce"),
            )
            .dropna(subset=["datetime", "GW"])
            .groupby("datetime")["GW"]
            .mean()
        )
        metricas_demanda = st.columns(3)
        metricas_demanda[0].metric(
            "Media mensual",
            formato_numero_es(valores_demanda.mean(), 2)
            if not valores_demanda.empty else "Sin datos",
        )
        metricas_demanda[1].metric(
            "Mínimo",
            formato_numero_es(valores_demanda.min(), 2)
            if not valores_demanda.empty else "Sin datos",
            delta=(
                valores_demanda.idxmin().strftime("%d.%m.%Y")
                if not valores_demanda.empty else None
            ),
            delta_color="off",
        )
        metricas_demanda[2].metric(
            "Máximo",
            formato_numero_es(valores_demanda.max(), 2)
            if not valores_demanda.empty else "Sin datos",
            delta=(
                valores_demanda.idxmax().strftime("%d.%m.%Y")
                if not valores_demanda.empty else None
            ),
            delta_color="off",
        )
        figura_demanda = graficar_media_diaria(
            datos_demanda_evolucion,
            años_visibles=[str(año_dashboard)],
            mes_nombre_actual=meses[mes_dashboard].capitalize(),
            año_actual=año_dashboard,
            incluir_barras_diarias=True,
        )
        figura_demanda = configurar_figura_dashboard(
            figura_demanda,
            "Demanda diaria y media acumulada",
        )
        st.plotly_chart(figura_demanda, use_container_width=True)

    if datos_mix_generacion.empty:
        st.warning("No hay datos de generación para el período seleccionado.")
    else:
        ultima_fecha_generacion = datos_generacion.loc[
            (datos_generacion["año"] == año_dashboard)
            & (datos_generacion["mes_num"] == mes_dashboard),
            "fecha",
        ].max()
        st.caption(
            "Estructura de generación REData · valores en GWh · "
            f"último dato del período: {ultima_fecha_generacion.strftime('%d.%m.%Y')}"
        )
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
        figura_mix = configurar_figura_dashboard(
            figura_mix,
            "Mix de generación (%)",
        )
        figura_mix.update_traces(
            domain=dict(x=[0.0, 0.66], y=[0.0, 0.74]),
            selector=dict(type="pie"),
        )
        figura_mix.update_layout(
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.37,
                xanchor="left",
                x=0.69,
                title_text=None,
                font=dict(size=TAMAÑO_LEYENDAS_GRAFICOS),
            )
        )
        st.plotly_chart(figura_mix, use_container_width=True)


# COMPARATIVA MENSUAL
año_actual_comparativa = fecha_hoy.year
año_base_comparativa = 2025
_, figura_spot_comparativa, medias_spot = graficar_comparativa_spot_mensual(
    datos_spot_comparativa,
    mes=mes_dashboard,
    año_actual=año_actual_comparativa,
    año_comparacion=año_base_comparativa,
)
datos_spot_horaria_comparativa, figura_spot_horaria_comparativa = (
    graficar_comparativa_spot_horaria_mensual(
        datos_spot_comparativa,
        mes=mes_dashboard,
        año_actual=año_actual_comparativa,
        año_comparacion=año_base_comparativa,
    )
)
datos_gas_comparativa, figura_gas_comparativa = (
    graficar_comparativa_gas_mensual(
    datos_mibgas_da,
    mes=mes_dashboard,
    año_actual=año_actual_comparativa,
    año_comparacion=año_base_comparativa,
    )
)
media_spot_actual = medias_spot.get(año_actual_comparativa)
media_spot_base = medias_spot.get(año_base_comparativa)
diferencia_spot = None
diferencia_spot_pct = None
if media_spot_actual is not None and media_spot_base is not None:
    diferencia_spot = media_spot_actual - media_spot_base
    if media_spot_base != 0:
        diferencia_spot_pct = diferencia_spot / media_spot_base * 100

comp_col1, comp_col2, comp_col3 = tab_comparativa.columns(3)
comp_col1.caption(
    "SPOT ESIOS ID · precios en €/MWh · "
    f"último dato: {fecha_fin_spot.strftime('%d.%m.%Y')}"
)
info_actual, info_base, info_diferencia = comp_col1.columns(3)
info_actual.metric(
    f"SPOT medio {año_actual_comparativa}",
    formato_eur_mwh(media_spot_actual, 2, False) or "Sin datos",
)
info_base.metric(
    f"SPOT medio {año_base_comparativa}",
    formato_eur_mwh(media_spot_base, 2, False) or "Sin datos",
)
if diferencia_spot is None:
    texto_diferencia = "Sin datos"
    delta_formateado = None
else:
    signo_diferencia = "+" if diferencia_spot > 0 else ""
    diferencia_formateada = formato_eur_mwh(diferencia_spot, 2, False)
    if diferencia_spot_pct is None:
        delta_formateado = None
    else:
        signo_delta = "+" if diferencia_spot_pct > 0 else ""
        delta_formateado = (
            f"{signo_delta}{formato_pct(diferencia_spot_pct, 2, True)}"
        )
    texto_diferencia = f"{signo_diferencia}{diferencia_formateada}"
info_diferencia.metric(
    f"Diferencia {año_actual_comparativa} − {año_base_comparativa}",
    texto_diferencia,
    delta=delta_formateado,
    delta_color="inverse",
)

with comp_col1:
    if not figura_spot_comparativa.data:
        st.warning("No hay datos SPOT para la comparación seleccionada.")
    else:
        figura_spot_comparativa = configurar_figura_dashboard(
            figura_spot_comparativa,
            f"Evolución diaria del SPOT · {meses[mes_dashboard]}",
        )
        st.plotly_chart(figura_spot_comparativa, use_container_width=True)

        st.caption(
            "Diferenciales del perfil horario medio · "
            f"{año_actual_comparativa} − {año_base_comparativa} · "
            "valores en €/MWh"
        )
        perfiles_spot_horarios = datos_spot_horaria_comparativa.pivot(
            index="hora",
            columns="año",
            values="value",
        )
        metrica_spot_h_media, metrica_spot_h_min, metrica_spot_h_max = (
            comp_col1.columns(3)
        )
        if not {
            año_actual_comparativa,
            año_base_comparativa,
        }.issubset(perfiles_spot_horarios.columns):
            valor_spot_h_media = valor_spot_h_min = valor_spot_h_max = (
                "Sin datos"
            )
            hora_diferencial_min = hora_diferencial_max = None
        else:
            diferencial_spot_horario = (
                perfiles_spot_horarios[año_actual_comparativa]
                - perfiles_spot_horarios[año_base_comparativa]
            ).dropna()
            if diferencial_spot_horario.empty:
                valor_spot_h_media = valor_spot_h_min = valor_spot_h_max = (
                    "Sin datos"
                )
                hora_diferencial_min = hora_diferencial_max = None
            else:
                estadisticas_diferencial = (
                    diferencial_spot_horario.mean(),
                    diferencial_spot_horario.min(),
                    diferencial_spot_horario.max(),
                )
                valores_diferencial = [
                    ("+" if valor > 0 else "")
                    + formato_eur_mwh(valor, 2, False)
                    for valor in estadisticas_diferencial
                ]
                (
                    valor_spot_h_media,
                    valor_spot_h_min,
                    valor_spot_h_max,
                ) = valores_diferencial
                hora_diferencial_min = int(
                    diferencial_spot_horario.idxmin()
                )
                hora_diferencial_max = int(
                    diferencial_spot_horario.idxmax()
                )
        metrica_spot_h_media.metric(
            "Diferencial horario medio",
            valor_spot_h_media,
        )
        metrica_spot_h_min.metric(
            "Diferencial horario mínimo",
            valor_spot_h_min,
            delta=(
                f"Hora {hora_diferencial_min:02d}"
                if hora_diferencial_min is not None
                else None
            ),
            delta_color="off",
        )
        metrica_spot_h_max.metric(
            "Diferencial horario máximo",
            valor_spot_h_max,
            delta=(
                f"Hora {hora_diferencial_max:02d}"
                if hora_diferencial_max is not None
                else None
            ),
            delta_color="off",
        )

        figura_spot_horaria_comparativa = configurar_figura_dashboard(
            figura_spot_horaria_comparativa,
            f"Perfil horario medio del SPOT · {meses[mes_dashboard]}",
        )
        st.plotly_chart(
            figura_spot_horaria_comparativa,
            use_container_width=True,
        )

with comp_col2:
    columnas_indexado = ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]
    datos_indexado_comparativa = datos_indexado[
        (datos_indexado["fecha"].dt.month == mes_dashboard)
        & datos_indexado["fecha"].dt.year.isin(
            [año_actual_comparativa, año_base_comparativa]
        )
    ].copy()
    fechas_indexado_actual = datos_indexado_comparativa.loc[
        datos_indexado_comparativa["fecha"].dt.year
        == año_actual_comparativa,
        "fecha",
    ].dropna()
    fecha_corte_indexado = (
        fechas_indexado_actual.max()
        if not fechas_indexado_actual.empty
        else None
    )
    if fecha_corte_indexado is not None:
        datos_indexado_comparativa = datos_indexado_comparativa[
            datos_indexado_comparativa["fecha"].dt.day
            <= fecha_corte_indexado.day
        ]
    resumen_indexado_comparativa = (
        datos_indexado_comparativa.assign(
            año=lambda df: df["fecha"].dt.year,
            mes_num=lambda df: df["fecha"].dt.month,
        )
        .groupby(["año", "mes_num"], as_index=False)[columnas_indexado]
        .mean()
    )
    resumen_indexado_comparativa[columnas_indexado] /= 10

    st.caption(
        "Precios finales según ATR · diferencias en c€/kWh · "
        f"{año_actual_comparativa} frente a {año_base_comparativa}"
        + (
            f" · ambos hasta el {fecha_corte_indexado.strftime('%d.%m')}"
            if fecha_corte_indexado is not None
            else ""
        )
    )
    try:
        datos_diferencial, figura_diferencial = graficar_diferencial_precios_mensuales(
            df_mensual=resumen_indexado_comparativa,
            anio_base=año_base_comparativa,
            anio_comp=año_actual_comparativa,
            convertir_a_cent_kwh=False,
            mes_num=mes_dashboard,
        )
    except ValueError as error_diferencial:
        st.warning(str(error_diferencial))
    else:
        if datos_diferencial.empty:
            st.warning("No hay datos para calcular el diferencial del mes seleccionado.")
        else:
            fila_diferencial = datos_diferencial.iloc[0]
            metrica_20, metrica_30, metrica_61 = comp_col2.columns(3)
            for contenedor, atr, columna in (
                (metrica_20, "2.0", "precio_2.0"),
                (metrica_30, "3.0", "precio_3.0"),
                (metrica_61, "6.1", "precio_6.1"),
            ):
                diferencia_abs = fila_diferencial[f"{columna}_delta"]
                diferencia_pct = fila_diferencial[f"{columna}_delta_pct"]
                signo_abs = "+" if diferencia_abs > 0 else ""
                signo_pct = "+" if diferencia_pct > 0 else ""
                contenedor.metric(
                    f"Diferencia {atr}",
                    signo_abs
                    + formato_cent_eur_kwh(diferencia_abs, 2, False),
                    delta=signo_pct + formato_pct(diferencia_pct, 2, True),
                    delta_color="inverse",
                )

            figura_diferencial = configurar_figura_dashboard(
                figura_diferencial,
                f"Diferencia real de precios (%) · {meses[mes_dashboard]}",
            )
            figura_diferencial.update_traces(textfont=dict(size=20))
            figura_diferencial.update_xaxes(
                tickfont=dict(size=16),
                title_font=dict(size=18),
            )
            figura_diferencial.update_yaxes(
                tickfont=dict(size=16),
                title_font=dict(size=18),
            )
            st.plotly_chart(figura_diferencial, use_container_width=True)

    st.caption(
        "MIBGAS D+1 · precios en €/MWh · "
        f"{año_actual_comparativa} frente a {año_base_comparativa}"
    )
    datos_gas_metricas = datos_gas_comparativa
    fechas_gas_actual = datos_gas_comparativa.loc[
        datos_gas_comparativa["año"] == año_actual_comparativa,
        "fecha_entrega",
    ].dropna()
    if not fechas_gas_actual.empty:
        ultimo_dia_gas_actual = fechas_gas_actual.dt.day.max()
        datos_gas_metricas = datos_gas_comparativa[
            datos_gas_comparativa["fecha_entrega"].dt.day
            <= ultimo_dia_gas_actual
        ]
    medias_gas = (
        datos_gas_metricas.groupby("año")["precio_gas"].mean().to_dict()
        if not datos_gas_metricas.empty
        else {}
    )
    media_gas_actual = medias_gas.get(año_actual_comparativa)
    media_gas_base = medias_gas.get(año_base_comparativa)
    metrica_gas_actual, metrica_gas_base, metrica_gas_diferencia = (
        comp_col2.columns(3)
    )
    metrica_gas_actual.metric(
        f"MIBGAS medio {año_actual_comparativa}",
        formato_eur_mwh(media_gas_actual, 2, False) or "Sin datos",
    )
    metrica_gas_base.metric(
        f"MIBGAS medio {año_base_comparativa}",
        formato_eur_mwh(media_gas_base, 2, False) or "Sin datos",
    )
    if media_gas_actual is None or media_gas_base is None:
        texto_diferencia_gas = "Sin datos"
        delta_gas = None
    else:
        diferencia_gas = media_gas_actual - media_gas_base
        signo_gas = "+" if diferencia_gas > 0 else ""
        texto_diferencia_gas = signo_gas + formato_eur_mwh(
            diferencia_gas, 2, False
        )
        if media_gas_base == 0:
            delta_gas = None
        else:
            diferencia_gas_pct = diferencia_gas / media_gas_base * 100
            signo_gas_pct = "+" if diferencia_gas_pct > 0 else ""
            delta_gas = signo_gas_pct + formato_pct(
                diferencia_gas_pct, 2, True
            )
    metrica_gas_diferencia.metric(
        f"Diferencia {año_actual_comparativa} − {año_base_comparativa}",
        texto_diferencia_gas,
        delta=delta_gas,
        delta_color="inverse",
    )

    if not figura_gas_comparativa.data:
        st.warning("No hay datos MIBGAS suficientes para comparar.")
    else:
        figura_gas_comparativa = configurar_figura_dashboard(
            figura_gas_comparativa,
            f"MIBGAS D+1 diario y acumulado · {meses[mes_dashboard]}",
        )
        st.plotly_chart(figura_gas_comparativa, use_container_width=True)

with comp_col3:
    if dia_limite_mix is None:
        st.caption(
            "Estructura de generación REData · comparación equiparada"
        )
    else:
        st.caption(
            "Estructura de generación REData · "
            f"ambos años hasta el día {dia_limite_mix}"
        )

    if (
        datos_mix_actual_comparativa.empty
        or datos_mix_base_comparativa.empty
    ):
        st.warning("No hay datos de generación suficientes para comparar.")
    else:
        total_mix_actual = datos_mix_actual_comparativa[
            "generacion_GWh"
        ].sum()
        total_mix_base = datos_mix_base_comparativa[
            "generacion_GWh"
        ].sum()
        diferencia_mix = total_mix_actual - total_mix_base
        diferencia_mix_pct = (
            diferencia_mix / total_mix_base * 100
            if total_mix_base != 0
            else None
        )
        metrica_mix_actual, metrica_mix_base, metrica_mix_diferencia = (
            comp_col3.columns(3)
        )
        metrica_mix_actual.metric(
            f"Generación {año_actual_mix}",
            formato_numero_es(total_mix_actual, 0),
        )
        metrica_mix_base.metric(
            f"Generación {año_base_mix}",
            formato_numero_es(total_mix_base, 0),
        )
        signo_mix = "+" if diferencia_mix > 0 else ""
        delta_mix = None
        if diferencia_mix_pct is not None:
            signo_mix_pct = "+" if diferencia_mix_pct > 0 else ""
            delta_mix = signo_mix_pct + formato_pct(
                diferencia_mix_pct, 2, True
            )
        metrica_mix_diferencia.metric(
            f"Diferencia {año_actual_mix} − {año_base_mix}",
            signo_mix + formato_numero_es(diferencia_mix, 0),
            delta=delta_mix,
            delta_color="inverse",
        )

        figura_mix_comparativa = graficar_mix_comparativo(
            datos_mix_actual_comparativa,
            datos_mix_base_comparativa,
            año_actual=año_actual_mix,
            año_base=año_base_mix,
            tipo=tipo_mix_comparativo,
            unidad=unidad_mix_comparativo,
            colores_tecnologia=COLORES_MIX_GENERACION,
        )
        figura_mix_comparativa = configurar_figura_dashboard(
            figura_mix_comparativa,
            (
                "Generación comparada (GWh)"
                if unidad_mix_comparativo == "GWh"
                else "Mix de generación comparado (%)"
            )
            + f" · {meses[mes_dashboard]}",
        )
        if tipo_mix_comparativo != "Barras":
            figura_mix_comparativa.update_layout(
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.02,
                    xanchor="center",
                    x=0.5,
                    title_text=None,
                    font=dict(size=TAMAÑO_LEYENDAS_GRAFICOS),
                )
            )
        st.plotly_chart(figura_mix_comparativa, use_container_width=True)

    if datos_demanda.empty:
        st.warning("No hay datos de demanda para comparar.")
    else:
        st.caption(
            "Demanda real media · valores en GW · "
            f"{año_dashboard} frente a {año_dashboard - 1}"
            + (
                " · ambos hasta el día "
                f"{pd.Timestamp(ultimo_real_demanda).day}"
                if ultimo_real_demanda is not None
                else ""
            )
        )
        demanda_real_metricas = datos_demanda[
            datos_demanda["short_name"] == "Demanda real"
        ].copy()
        if ultimo_real_demanda is not None:
            dia_limite_demanda = pd.Timestamp(ultimo_real_demanda).day
            demanda_real_metricas = demanda_real_metricas[
                (demanda_real_metricas["año"] != año_dashboard - 1)
                | (
                    demanda_real_metricas["datetime"].dt.day
                    <= dia_limite_demanda
                )
            ]
        medias_demanda_real = (
            demanda_real_metricas
            .groupby("año")["GW"]
            .mean()
            .to_dict()
        )
        energia_demanda_real_gwh = (
            demanda_real_metricas
            .groupby("año")["GW"]
            .sum()
            .mul(24)
            .to_dict()
        )
        media_demanda_actual = medias_demanda_real.get(año_dashboard)
        media_demanda_base = medias_demanda_real.get(año_dashboard - 1)
        energia_demanda_actual = energia_demanda_real_gwh.get(año_dashboard)
        energia_demanda_base = energia_demanda_real_gwh.get(
            año_dashboard - 1
        )
        metrica_demanda_actual, metrica_demanda_base, metrica_demanda_dif = (
            comp_col3.columns(3)
        )
        metrica_demanda_actual.metric(
            f"Demanda real {año_dashboard}",
            (
                formato_numero_es(media_demanda_actual, 2)
                if media_demanda_actual is not None
                else "Sin datos"
            ),
            delta=(
                f"{formato_numero_es(energia_demanda_actual, 0)} GWh"
                if energia_demanda_actual is not None
                else None
            ),
            delta_color="off",
        )
        metrica_demanda_base.metric(
            f"Demanda real {año_dashboard - 1}",
            (
                formato_numero_es(media_demanda_base, 2)
                if media_demanda_base is not None
                else "Sin datos"
            ),
            delta=(
                f"{formato_numero_es(energia_demanda_base, 0)} GWh"
                if energia_demanda_base is not None
                else None
            ),
            delta_color="off",
        )
        if media_demanda_actual is None or media_demanda_base is None:
            texto_diferencia_demanda = "Sin datos"
            delta_demanda = None
        else:
            diferencia_demanda = media_demanda_actual - media_demanda_base
            signo_demanda = "+" if diferencia_demanda > 0 else ""
            texto_diferencia_demanda = signo_demanda + formato_numero_es(
                diferencia_demanda, 2
            )
            if media_demanda_base == 0:
                delta_demanda = None
            else:
                diferencia_demanda_pct = (
                    diferencia_demanda / media_demanda_base * 100
                )
                signo_demanda_pct = "+" if diferencia_demanda_pct > 0 else ""
                delta_demanda = signo_demanda_pct + formato_pct(
                    diferencia_demanda_pct, 2, True
                )
        metrica_demanda_dif.metric(
            f"Diferencia {año_dashboard} − {año_dashboard - 1}",
            texto_diferencia_demanda,
            delta=delta_demanda,
            delta_color="inverse",
        )

        figura_demanda_comparativa = graficar_media_diaria(
            datos_demanda,
            años_visibles=[
                str(año_dashboard - 1),
                str(año_dashboard),
            ],
            mes_nombre_actual=meses[mes_dashboard].capitalize(),
            año_actual=año_dashboard,
        )
        figura_demanda_comparativa = configurar_figura_dashboard(
            figura_demanda_comparativa,
            "Demanda media acumulada comparada",
        )
        st.plotly_chart(
            figura_demanda_comparativa,
            use_container_width=True,
        )
