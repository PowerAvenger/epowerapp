from datetime import date

import pandas as pd
import streamlit as st

from backend_comun import carga_mibgas, colores_precios
from backend_escalacv import (
    cargar_datos_escalacv,
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
from backend_mibgas import filtrar_por_producto, graficar_da_2026_acumulado
from backend_redata_potgen import (
    COLORES_MIX_GENERACION,
    graficar_mix_queso,
    leer_json as leer_json_redata,
    preparar_mix_generacion_mensual,
)
from utilidades import generar_menu, init_app, init_app_index
from formato_es import formato_cent_eur_kwh, formato_eur_mwh, formato_pct


if (
    not st.session_state.get("usuario_autenticado", False)
    and not st.session_state.get("usuario_free", False)
):
    st.switch_page("epowerapp.py")

generar_menu()

fecha_hoy = date.today()
ALTURA_GRAFICOS = 500
TAMAÑO_TITULOS_GRAFICOS = 22


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
            font=dict(size=12),
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
    resumen_indexado_mensual = (
        datos_indexado.assign(
            año=lambda df: df["fecha"].dt.year,
            mes_num=lambda df: df["fecha"].dt.month,
        )
        .groupby(["año", "mes_num"], as_index=False)[
            ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]
        ]
        .mean()
    )
    for columna_precio in ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]:
        resumen_indexado_mensual[columna_precio] /= 10

with st.spinner("Preparando demanda peninsular..."):
    datos_demanda, ultimo_real_demanda, hay_prevision_demanda = (
        obtener_demanda_mensual_dashboard(año_dashboard, mes_dashboard)
    )

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

tab_evolucion, tab_comparativa = st.tabs(
    ["Evolución mensual", "Comparativa mensual"]
)

col1, col2, col3 = tab_evolucion.columns(3)

with col1:
    st.caption(
        "SPOT y SSAA ESIOS ID · "
        f"último dato: {fecha_fin.strftime('%d.%m.%Y')}"
    )
    if datos_mes.empty:
        st.warning("No hay datos para el período seleccionado.")
    else:
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
            "MIBGAS D+1 · "
            f"último dato del período: {ultima_fecha_gas.strftime('%d.%m.%Y')}"
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
    st.caption("Perfil horario medio · sin ponderación por curva de carga")
    if datos_indexado_mes.empty:
        st.warning("No hay datos de indexado para el período seleccionado.")
    else:
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
        st.caption("Demanda real peninsular · ESIOS")
    else:
        st.caption(
            "Demanda real peninsular"
            + (" y prevista" if hay_prevision_demanda else "")
            + f" · último real: {ultimo_real_demanda.strftime('%d.%m.%Y')}"
        )
    if datos_demanda.empty:
        st.warning("No hay datos de demanda para el período seleccionado.")
    else:
        figura_demanda = graficar_media_diaria(
            datos_demanda,
            años_visibles=[str(año_dashboard - 1), str(año_dashboard)],
            mes_nombre_actual=meses[mes_dashboard].capitalize(),
            año_actual=año_dashboard,
        )
        figura_demanda = configurar_figura_dashboard(
            figura_demanda,
            "Demanda real y prevista",
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
            "Estructura de generación REData · "
            f"último dato del período: {ultima_fecha_generacion.strftime('%d.%m.%Y')}"
        )
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
                font=dict(size=12),
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

with comp_col2:
    st.caption(
        "Precios finales según ATR · diferencias en c€/kWh · "
        f"{año_actual_comparativa} frente a {año_base_comparativa}"
    )
    try:
        datos_diferencial, figura_diferencial = graficar_diferencial_precios_mensuales(
            df_mensual=resumen_indexado_mensual,
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
            st.plotly_chart(figura_diferencial, use_container_width=True)
