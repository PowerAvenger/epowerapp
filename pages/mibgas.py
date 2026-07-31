import streamlit as st
import pandas as pd
#import pygwalker as pyg
#from pygwalker.api.streamlit import StreamlitRenderer

import plotly.express as px
from datetime import datetime
from utilidades import generar_menu, init_app
from backend_comun import carga_mibgas, carga_total_sheets
from backend_mibgas import (
    filtrar_por_producto, graficar_qs, graficar_futuros_mibgas, graficar_da_corrido, graficar_da_2026_acumulado, graficar_da_comparado,
    construir_comparativa_diaria_mibgas_omie, graficar_comparativa_diaria_mibgas_omie,
    construir_resumen_mensual_omie_mibgas, estimar_omie_mensual_desde_gas,
    ajustar_modelo_lineal_omie_gas, graficar_diagnostico_ratio_gas,
    graficar_modelo_lineal_omie_gas,
    construir_relacion_horaria_omie_mibgas, graficar_mapa_calor_relacion_omie_mibgas,
    graficar_relacion_omie_mibgas_por_mes, graficar_relacion_omie_mibgas_por_hora,
    descargar_sendeco, obtener_sendeco, graficar_gas_co2,
    obtener_spot_mensual, construir_df_mensual, graf_simul_spot, obtener_spot_diario,
    obtener_mibgas_mensual, graficar_mibgas_mensual_historico, construir_curva_mibgas_2026, graficar_curva_mibgas_2026,
    construir_media_prevista_mibgas_2026_diaria, graficar_media_prevista_mibgas_2026,
    construir_curva_mibgas_mensual_12m, graficar_curva_mibgas_mensual_12m,
    construir_evolucion_media_mibgas_forward_12m, añadir_mibgas_real_12m_alineado_forward,
    graficar_evolucion_media_mibgas_forward
    )
from backend_previsiones import (
    guardar_prevision_omie_en_sesion,
    obtener_prevision_omie_anual,
)



if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()

# Gas solo necesita las columnas históricas de fecha y SPOT. Evitamos
# init_app_index(), que además carga componentes y recalcula indexados.
if "df_sheets" not in st.session_state:
    if "df_sheets_old" not in st.session_state:
        carga_total_sheets()
    st.session_state.df_sheets = st.session_state.df_sheets_old.copy()

st.sidebar.header('⚡ Gas & Furious ⚡')
zona_mensajes = st.sidebar.empty()

if 'mibgas_simul' not in st.session_state:
    st.session_state.mibgas_simul = 40

df_mibgas_base = carga_mibgas()
ultima_fecha_mibgas = df_mibgas_base['Trading day'].max()
st.sidebar.info(f'Última fecha disponible: {ultima_fecha_mibgas.strftime("%d.%m.%Y")}')
if st.sidebar.button('Actualizar datos', use_container_width=True):
    carga_mibgas.clear()
    st.rerun()

# FUTUROS M MESES
productos_m = ['GMAES', 'GMES_M+2', 'GMES_M+3', 'GMES_M+4', 'GMES_M+5', 'GMES_M+6']
dfs_m = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_m]
df_mg_m = pd.concat(dfs_m, ignore_index=True)
graf_ms = graficar_futuros_mibgas(df_mg_m, tipo="M")

# FUTUROS Q TRIMESTRES
productos_q = ['GQES_Q+1', 'GQES_Q+2', 'GQES_Q+3', 'GQES_Q+4']
dfs_q = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_q]
df_mg_q = pd.concat(dfs_q, ignore_index=True)
#graf_qs = graficar_qs(df_mg_q)
graf_qs = graficar_futuros_mibgas(df_mg_q, tipo="Q")

# FUTUROS Y AÑOS
productos_y = ['GYES_Y+1', 'GYES_Y+2', 'GYES_Y+3', 'GQES_Y+4']
dfs_y = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_y]
df_mg_y = pd.concat(dfs_y, ignore_index=True)
#graf_ys = graficar_qs(df_mg_y)
graf_ys = graficar_futuros_mibgas(df_mg_y, tipo="Y")


df_mg_da = filtrar_por_producto(df_mibgas_base, 'GDAES_D+1')
#print('mibgas da')
#print(df_mg_da)

df_mibgas_mensual = obtener_mibgas_mensual(df_mg_da)
graf_mibgas_mensual_historico = graficar_mibgas_mensual_historico(df_mibgas_mensual)
df_curva_mibgas_2026 = construir_curva_mibgas_2026(df_mibgas_mensual, df_mg_m, df_mg_q)
precio_medio_mibgas_2026 = round(df_curva_mibgas_2026["precio"].mean(), 2)
graf_mibgas_2026 = graficar_curva_mibgas_2026(df_curva_mibgas_2026, precio_medio_mibgas_2026)
df_media_mibgas_2026 = construir_media_prevista_mibgas_2026_diaria(df_mg_da, df_mg_m, df_mg_q)
graf_media_mibgas_2026 = graficar_media_prevista_mibgas_2026(df_media_mibgas_2026)

df_mibgas_año_movil = construir_curva_mibgas_mensual_12m(df_mg_m, df_mg_q)
num_meses_mibgas_año_movil = df_mibgas_año_movil["precio"].notna().sum()
precio_medio_mibgas_año_movil = round(df_mibgas_año_movil["precio"].mean(), 2)
graf_mibgas_año_movil = graficar_curva_mibgas_mensual_12m(df_mibgas_año_movil, precio_medio_mibgas_año_movil)
df_evol_media_mibgas_forward = construir_evolucion_media_mibgas_forward_12m(
    df_mg_m=df_mg_m,
    df_mg_q=df_mg_q,
    fecha_inicio="01.01.2024"
)
df_evol_media_mibgas_forward = añadir_mibgas_real_12m_alineado_forward(
    df_evol=df_evol_media_mibgas_forward,
    df_mg_da=df_mg_da,
    col_fecha_evol="Fecha",
    col_fecha_real="fecha_entrega",
    col_real="precio_gas",
    meses=12,
    exigir_ventana_completa=True
)
graf_evol_media_mibgas_forward = graficar_evolucion_media_mibgas_forward(
    df_evol_media_mibgas_forward
)

df_medias = df_mg_da.groupby("año_entrega", as_index=False)["precio_gas"].mean()
df_medias["precio_gas"] = df_medias["precio_gas"].round(2)
df_medias["precio_str"] = df_medias["precio_gas"].astype(str).str.replace('.', ',')
gas_media_2026 = df_medias.loc[
    df_medias["año_entrega"] == 2026,
    "precio_gas"
]
gas_media_2026 = float(gas_media_2026.iloc[0]) if not gas_media_2026.empty else None
print("GAS media 2026:", gas_media_2026)

graf_da_corrido = graficar_da_corrido(df_mg_da)
graf_da_2026_acumulado = graficar_da_2026_acumulado(df_mg_da)
graf_da_comparado = graficar_da_comparado(df_mg_da)



# SENDECO========================================================================
año_actual=datetime.now().year
descargar_sendeco(año_actual)
df_sendeco = obtener_sendeco()

df_sendeco_anual = (
    df_sendeco
    .groupby('año', as_index=False)['co2_€ton']
    .mean()
    .rename(columns={'co2_€ton': 'co2_medio_€ton'})
)


df_total_data_gas_co2=pd.merge(df_mg_da,df_sendeco, on='fecha_entrega',how='left')
df_total_data_gas_co2['co2_€ton']=df_total_data_gas_co2['co2_€ton'].fillna(method='ffill')
df_total_data_gas_co2['co2_€ton']=df_total_data_gas_co2['co2_€ton'].fillna(method='bfill')

ratio_precio_co2=0.35

df_total_data_gas_co2['co2']=round(df_total_data_gas_co2['co2_€ton']*ratio_precio_co2,2)
df_total_data_gas_co2['año'] = df_total_data_gas_co2['fecha_entrega'].dt.year
df_total_data_gas_co2['día_del_año'] = df_total_data_gas_co2['fecha_entrega'].dt.dayofyear
graf_co2_gas = graficar_gas_co2(df_total_data_gas_co2)


df_spot_mensual = obtener_spot_mensual(st.session_state.df_sheets)
print (df_spot_mensual)

df_total_data = df_total_data_gas_co2.merge(df_spot_mensual, on = 'fecha_entrega', how = 'left')

df_mensual = construir_df_mensual(df_total_data)


#valor_mibgas_previsto = 40
df_spot_diario = obtener_spot_diario(st.session_state.df_sheets)
print (df_spot_diario)
omie_media_2026 = round(df_spot_diario.loc[df_spot_diario["fecha"].dt.year == 2026, "spot"].mean(),2)
print(omie_media_2026)
df_comparativa_diaria_mibgas_omie = construir_comparativa_diaria_mibgas_omie(
    df_mg_da,
    df_spot_diario,
)
df_comparativa_diaria_historica = construir_comparativa_diaria_mibgas_omie(
    df_mg_da,
    df_spot_diario,
    año=None,
)
df_resumen_mensual_omie_mibgas = construir_resumen_mensual_omie_mibgas(
    df_comparativa_diaria_historica
)
graf_comparativa_diaria_mibgas_omie = graficar_comparativa_diaria_mibgas_omie(
    df_comparativa_diaria_mibgas_omie
)
df_relacion_horaria_omie_mibgas = construir_relacion_horaria_omie_mibgas(
    df_mg_da,
    st.session_state.df_sheets,
)
graf_mapa_calor_omie_mibgas = graficar_mapa_calor_relacion_omie_mibgas(
    df_relacion_horaria_omie_mibgas
)
graf_relacion_por_mes, df_relacion_por_mes = (
    graficar_relacion_omie_mibgas_por_mes(
        df_relacion_horaria_omie_mibgas
    )
)
graf_relacion_por_hora, df_relacion_por_hora = (
    graficar_relacion_omie_mibgas_por_hora(
        df_relacion_horaria_omie_mibgas
    )
)


df_validacion = pd.DataFrame({
    'año': [2024, 2025, 2021, 2019, 2018],
    'precio_gas': [35.95,34.72, 47.3, 15.27, 28.95],   # MIBGAS real
    'omie': [63.03,65.28, 111.93, 47.68, 57.29]          # SPOT real
})
df_validacion = pd.DataFrame({
    'año': [2024, 2025, 2021, 2018],
    'precio_gas': [35.95, 34.72, 47.3, 28.95],   # MIBGAS real
    'omie': [63.03, 65.28, 111.93, 57.29]        # SPOT real
})

colores_precios = {'precio_gas': 'goldenrod', '': 'darkred', 'precio_6.1': '#1C83E1'}
graf_hist, simul_spot, simul_gas = graf_simul_spot(
    df_mensual,
    df_validacion,
    st.session_state.mibgas_simul,
    omie_media_2026=omie_media_2026,
    gas_media_2026=gas_media_2026,
    omie_previsto=st.session_state.get("precio_omie_previsto"),
    gas_previsto=precio_medio_mibgas_2026,
)






#LAYOUT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes.empty()

tab1, tab2, tab3, tab4, tab5 = st.tabs(['Históricos', 'Futuros', 'CO2', 'Simulador', 'Previsión anual'])

with tab1:
    with st.container():
        col1,col2 = st.columns([.9,.1]) 
        with col1:
            st.write(graf_da_corrido)
            st.write(graf_da_comparado)
            st.write(graf_mibgas_mensual_historico)
            st.write(graf_da_2026_acumulado)
            st.plotly_chart(
                graf_comparativa_diaria_mibgas_omie,
                use_container_width=True,
            )
            with st.expander("Ver tabla diaria MIBGAS D+1 vs OMIE"):
                st.dataframe(
                    df_comparativa_diaria_mibgas_omie,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "fecha": st.column_config.DateColumn(
                            "Fecha", format="DD/MM/YYYY"
                        ),
                        "mibgas_d1": st.column_config.NumberColumn(
                            "MIBGAS D+1 (€/MWh)", format="%.2f"
                        ),
                        "omie": st.column_config.NumberColumn(
                            "OMIE (€/MWh)", format="%.2f"
                        ),
                        "rel_omie_gas": st.column_config.NumberColumn(
                            "Rel. OMIE/Gas", format="%.4f"
                        ),
                    },
                )

    col_mapa, col_metricas = st.columns([.85, .15])
    with col_mapa:
        st.plotly_chart(
            graf_mapa_calor_omie_mibgas,
            use_container_width=True,
        )
    with col_metricas:
        if not df_relacion_horaria_omie_mibgas.empty:
            fila_max = df_relacion_horaria_omie_mibgas.loc[
                df_relacion_horaria_omie_mibgas["rel_omie_gas"].idxmax()
            ]
            st.metric(
                "Máx. OMIE/Gas",
                f"{fila_max['rel_omie_gas']:.2f}",
            )
            st.metric(
                "Fecha del máximo",
                fila_max["fecha"].strftime("%d/%m/%Y"),
            )
            st.metric(
                "Hora",
                f"{int(fila_max['hora']):02d}:00",
            )
            st.metric(
                "OMIE",
                f"{fila_max['omie']:.2f} €/MWh",
            )
            st.metric(
                "MIBGAS D+1",
                f"{fila_max['mibgas_d1']:.2f} €/MWh",
            )
        else:
            st.info("No hay datos horarios coincidentes para 2026.")

    col_rel_mes, col_rel_hora = st.columns(2)
    with col_rel_mes:
        st.plotly_chart(
            graf_relacion_por_mes,
            use_container_width=True,
        )
    with col_rel_hora:
        st.plotly_chart(
            graf_relacion_por_hora,
            use_container_width=True,
        )
            
            
        with col2:
            st.metric("Precio medio gas 2024 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2024, "precio_str"].values[0])
            st.metric("Precio medio gas 2025 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2025, "precio_str"].values[0])
            st.metric("Precio medio gas 2026 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2026, "precio_str"].values[0])




with tab2:
    with st.container():
        col1,col2 = st.columns([.9,.1]) 
        with col1:
            st.write(graf_ms)
            st.write(graf_qs)
            st.write(graf_ys) 
        
        



with tab3:
    st.write(graf_co2_gas)



with tab4:

    col1, col2 = st.columns([.25,.75])
    with col1:
        st.success('Bienvenido a la simulación baratera del precio medio OMIE anual a partir de MIBGAS')

        st.info('Puntos de simulación sobre curva')

        # Fila 1: simulación directa MIBGAS -> OMIE.
        col11, col12 = st.columns(2)
        with col11:
            st.number_input('Introduce el valor previsto MIBGAS 2026', min_value=26, max_value=70, key='mibgas_simul')
        with col12:
            st.metric('Valor de OMIE 2026 esperado', simul_spot)

        # Fila 2: simulación inversa OMIE -> MIBGAS a partir de la curva
        # híbrida calculada en Simulindex.
        precio_omie_previsto = st.session_state.get("precio_omie_previsto")
        if precio_omie_previsto is not None:
            col21, col22 = st.columns(2)
            with col21:
                st.metric('Valor OMIE previsto s/OMIP', precio_omie_previsto)
            with col22:
                if simul_gas is not None:
                    st.metric('Valor de gas 2026 esperado', simul_gas)
        else:
            st.caption('La previsión OMIE de Simulindex no está disponible en esta sesión.')
            if st.button('Calcular previsión OMIE 2026', use_container_width=True):
                with st.spinner('Calculando la curva híbrida OMIE-OMIP...'):
                    prevision_omie = obtener_prevision_omie_anual(df_spot_diario)
                    guardar_prevision_omie_en_sesion(prevision_omie)
                st.rerun()

        st.info('Punto según valores actuales OMIE/MIBGAS')

        # Fila 3: valores medios observados en el año en curso.
        col31, col32 = st.columns(2)
        with col31:
            st.metric('Valor medio OMIE 2026 €/MWh', omie_media_2026)
        with col32:
            st.metric("Precio medio gas 2026 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2026, "precio_str"].values[0])

        st.info('Punto según valores futuros')

        # Fila 4: previsiones anuales procedentes de Simulindex y MIBGAS.
        col41, col42 = st.columns(2)
        with col41:
            st.metric(
                'Valor OMIE previsto s/OMIP',
                precio_omie_previsto if precio_omie_previsto is not None else 'No disponible'
            )
        with col42:
            st.metric('Valor MIBGAS previsto (€/MWh)', precio_medio_mibgas_2026)
            
    with col2:        
        st.write(graf_hist)

        #renderer = StreamlitRenderer(df_mensual)
        #renderer.explorer()

    st.divider()
    st.subheader("Estimación mensual OMIE a partir de MIBGAS")
    st.caption(
        "La relación mensual es la media de los ratios diarios "
        "OMIE/MIBGAS. La estimación usa únicamente el mismo mes de años "
        "anteriores."
    )
    meses_estimacion = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre",
        12: "Diciembre",
    }
    col_simul_mensual, col_hist_mensual = st.columns([.32, .68])
    with col_simul_mensual:
        mes_objetivo = st.selectbox(
            "Mes objetivo",
            options=list(meses_estimacion),
            index=7,
            format_func=lambda mes: meses_estimacion[mes],
            key="gas_mes_objetivo_ratio",
        )
        año_objetivo = st.number_input(
            "Año objetivo",
            min_value=2025,
            max_value=2035,
            value=2026,
            step=1,
            key="gas_año_objetivo_ratio",
        )
        gas_mensual_simulado = st.number_input(
            "MIBGAS mensual previsto (€/MWh)",
            min_value=0.01,
            max_value=200.0,
            value=40.0,
            step=0.5,
            format="%.2f",
            key="gas_mensual_simulado_ratio",
        )
        modelo_lineal_mensual = ajustar_modelo_lineal_omie_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
        )
        modelo_lineal_12m = ajustar_modelo_lineal_omie_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
            ultimos_meses=12,
        )
        estimacion_mensual = estimar_omie_mensual_desde_gas(
            df_resumen_mensual_omie_mibgas,
            gas_mensual_simulado,
            mes_objetivo,
            año_objetivo,
        )
        if estimacion_mensual:
            st.metric(
                "OMIE mensual estimado",
                f"{estimacion_mensual['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Ratio histórico medio",
                f"{estimacion_mensual['ratio_medio']:.3f}",
            )
            st.metric(
                "Rango histórico resultante",
                (
                    f"{estimacion_mensual['omie_minimo']:.2f} – "
                    f"{estimacion_mensual['omie_maximo']:.2f} €/MWh"
                ),
            )
            st.caption(
                "Años utilizados: "
                + ", ".join(
                    str(año)
                    for año in estimacion_mensual["años_utilizados"]
                )
            )
        else:
            años_disponibles_mes = (
                df_resumen_mensual_omie_mibgas.loc[
                    df_resumen_mensual_omie_mibgas["mes"] == mes_objetivo,
                    "año",
                ]
                .astype(int)
                .tolist()
            )
            st.warning(
                "No hay ratios históricos anteriores disponibles para ese mes. "
                "Años encontrados: "
                + (
                    ", ".join(str(año) for año in años_disponibles_mes)
                    if años_disponibles_mes
                    else "ninguno"
                )
            )
        if modelo_lineal_mensual:
            st.markdown("#### Corrección por nivel del gas")
            st.metric(
                "OMIE estimado · modelo lineal",
                f"{modelo_lineal_mensual['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Banda residual orientativa",
                (
                    f"{modelo_lineal_mensual['omie_inferior_orientativo']:.2f}"
                    " – "
                    f"{modelo_lineal_mensual['omie_superior_orientativo']:.2f}"
                    " €/MWh"
                ),
            )
            st.caption(
                f"R²: {modelo_lineal_mensual['r2']:.3f} · "
                f"{modelo_lineal_mensual['num_observaciones']} meses · "
                "Correlación gas-ratio: "
                f"{modelo_lineal_mensual['correlacion_ratio_gas']:.3f}"
            )
        if modelo_lineal_12m:
            st.markdown("#### Modelo últimos 12 meses")
            st.metric(
                "OMIE estimado · 12 meses",
                f"{modelo_lineal_12m['omie_estimado']:.2f} €/MWh",
            )
            st.metric(
                "Banda residual · 12 meses",
                (
                    f"{modelo_lineal_12m['omie_inferior_orientativo']:.2f}"
                    " – "
                    f"{modelo_lineal_12m['omie_superior_orientativo']:.2f}"
                    " €/MWh"
                ),
            )
            st.caption(
                f"R²: {modelo_lineal_12m['r2']:.3f} · "
                f"{modelo_lineal_12m['num_observaciones']} meses · "
                "Correlación gas-ratio: "
                f"{modelo_lineal_12m['correlacion_ratio_gas']:.3f}"
            )

    with col_hist_mensual:
        if estimacion_mensual:
            detalle_ratio_mes = estimacion_mensual["detalle"].copy()
            detalle_ratio_mes["año"] = detalle_ratio_mes["año"].astype(str)
            graf_ratio_mes = px.bar(
                detalle_ratio_mes,
                x="año",
                y="ratio_medio_diario",
                text_auto=".3f",
                labels={
                    "año": "Año",
                    "ratio_medio_diario": "Media ratios diarios OMIE/Gas",
                },
                title=(
                    f"Ratio histórico de {meses_estimacion[mes_objetivo]}"
                ),
                color_discrete_sequence=["#4C78A8"],
            )
            graf_ratio_mes.add_hline(
                y=estimacion_mensual["ratio_medio"],
                line_dash="dot",
                line_color="#E74C3C",
                annotation_text="Media histórica",
            )
            graf_ratio_mes.update_layout(
                title={"x": 0.5, "xanchor": "center"},
                showlegend=False,
                height=430,
            )
            st.plotly_chart(graf_ratio_mes, use_container_width=True)

    if modelo_lineal_mensual:
        col_diag_ratio, col_modelo_lineal = st.columns(2)
        with col_diag_ratio:
            st.plotly_chart(
                graficar_diagnostico_ratio_gas(
                    df_resumen_mensual_omie_mibgas
                ),
                use_container_width=True,
            )
        with col_modelo_lineal:
            st.plotly_chart(
                graficar_modelo_lineal_omie_gas(
                    modelo_lineal_mensual,
                    gas_mensual_simulado,
                    etiqueta_objetivo=(
                        f"{meses_estimacion[mes_objetivo]} "
                        f"{int(año_objetivo)}"
                    ),
                    destacar_objetivo=True,
                    mes_objetivo=mes_objetivo,
                ),
                use_container_width=True,
            )
            if modelo_lineal_12m:
                st.plotly_chart(
                    graficar_modelo_lineal_omie_gas(
                        modelo_lineal_12m,
                        gas_mensual_simulado,
                        titulo=(
                            "Modelo lineal OMIE vs MIBGAS · "
                            "últimos 12 meses"
                        ),
                        etiqueta_objetivo=(
                            f"{meses_estimacion[mes_objetivo]} "
                            f"{int(año_objetivo)}"
                        ),
                    ),
                    use_container_width=True,
                )

    with st.expander("Ver tabla mensual OMIE, MIBGAS y ratios diarios"):
        st.dataframe(
            df_resumen_mensual_omie_mibgas,
            hide_index=True,
            use_container_width=True,
            column_config={
                "año": st.column_config.NumberColumn("Año", format="%d"),
                "mes": st.column_config.NumberColumn("Mes", format="%d"),
                "fecha_mes": st.column_config.DateColumn(
                    "Periodo", format="MMM YYYY"
                ),
                "mibgas_medio": st.column_config.NumberColumn(
                    "MIBGAS medio (€/MWh)", format="%.2f"
                ),
                "omie_medio": st.column_config.NumberColumn(
                    "OMIE medio (€/MWh)", format="%.2f"
                ),
                "ratio_medio_diario": st.column_config.NumberColumn(
                    "Media ratios diarios", format="%.4f"
                ),
                "dias_con_datos": st.column_config.NumberColumn(
                    "Días", format="%d"
                ),
            },
        )


with tab5:
    col1, col2 = st.columns(2)
    with col1:
        st.info('Previsión MIBGAS 2026 combinando medias mensuales D+1 y futuros mensuales/trimestrales.', icon="ℹ️")
        st.write(graf_mibgas_2026)
        st.info('Evolucion diaria de la media MIBGAS prevista 2026 en base a D+1 real y futuros combinados.')
        st.write(graf_media_mibgas_2026)

    with col2:
        st.info('Curva MIBGAS 12 meses desde M+1 con futuros mensuales y fallback trimestral.', icon="ℹ️")
        if num_meses_mibgas_año_movil < 12:
            st.warning(
                f'La curva año móvil tiene {num_meses_mibgas_año_movil}/12 meses con precio disponible. '
                'Se muestra la media de los meses disponibles.',
                icon="⚠️"
            )
        st.write(graf_mibgas_año_movil)
        st.info('Evolución de MIBGAS forward 12M desde M+1. Comparativa con MIBGAS D+1 real alineado.', icon="ℹ️")
        st.plotly_chart(graf_evol_media_mibgas_forward, use_container_width=True)
