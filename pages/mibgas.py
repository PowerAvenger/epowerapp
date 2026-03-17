import streamlit as st
import pandas as pd
#import pygwalker as pyg
#from pygwalker.api.streamlit import StreamlitRenderer

import plotly.express as px
from datetime import datetime
from utilidades import generar_menu, init_app, init_app_index
from backend_comun import carga_mibgas
from backend_mibgas import (filtrar_por_producto, graficar_qs, graficar_da_corrido, graficar_da_comparado,
                            descargar_sendeco, obtener_sendeco, graficar_gas_co2,
                            obtener_spot_mensual, construir_df_mensual, graf_simul_spot)



if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()
init_app()

st.sidebar.header('⚡ Gas & Furious ⚡')
zona_mensajes = st.sidebar.empty()
if 'df_sheets' not in st.session_state:
    zona_mensajes.warning('Cargando históricos. Espera a que estén disponibles...', icon = '⚠️')


#inicializamos variables de sesión


init_app_index()

if 'mibgas_simul' not in st.session_state:
    st.session_state.mibgas_simul = 30


df_mibgas_base = carga_mibgas()
#df_mibgas_base=df_mibgas_base.rename(columns={'Product':'producto','First Day Delivery':'fecha','Last Price\n[EUR/MWh]':'precio_gas'})
#df_mibgas_base["precio_gas"] = pd.to_numeric(df_mibgas_base["precio_gas"], errors="coerce")

productos_q = ['GQES_Q+1', 'GQES_Q+2', 'GQES_Q+3', 'GQES_Q+4']
dfs_q = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_q]
df_mg_q = pd.concat(dfs_q, ignore_index=True)


graf_qs = graficar_qs(df_mg_q)

df_mg_da = filtrar_por_producto(df_mibgas_base, 'GDAES_D+1')
print('mibgas da')
print(df_mg_da)

df_medias = df_mg_da.groupby("año_entrega", as_index=False)["precio_gas"].mean()
df_medias["precio_gas"] = df_medias["precio_gas"].round(2)
# Convertir a texto con coma decimal
df_medias["precio_str"] = df_medias["precio_gas"].astype(str).str.replace('.', ',')

graf_da_corrido = graficar_da_corrido(df_mg_da)
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



df_spot_mensual = obtener_spot_mensual()
print (df_spot_mensual)

df_total_data = df_total_data_gas_co2.merge(df_spot_mensual, on = 'fecha_entrega', how = 'left')

df_mensual = construir_df_mensual(df_total_data)


#valor_mibgas_previsto = 40


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
graf_hist, simul_spot, simul_gas = graf_simul_spot(df_mensual, df_validacion, st.session_state.mibgas_simul)



graf_co2_gas = graficar_gas_co2(df_total_data_gas_co2)


#LAYOUT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes = st.sidebar.empty()

tab1, tab2, tab3, tab4 = st.tabs(['Históricos', 'Futuros', 'CO2', 'Simulador'])

with tab1:
    with st.container():
        col1,col2 = st.columns([.9,.1])
        with col1:
            st.write(graf_da_corrido)
            st.write(graf_da_comparado)
            
            
        with col2:
            st.metric("Precio medio gas 2024 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2024, "precio_str"].values[0])
            st.metric("Precio medio gas 2025 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2025, "precio_str"].values[0])
            st.metric("Precio medio gas 2026 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2026, "precio_str"].values[0])




with tab2:
    with st.container():
        col1,col2 = st.columns([.9,.1])
        with col1:
            st.write(graf_qs)
        
        



with tab3:
    st.write(graf_co2_gas)



with tab4:

    col1, col2 = st.columns([.25,.75])
    with col1:
        st.success('Bienvenido a la simulación baratera del precio medio OMIE anual a partir de MIBGAS')
        col11, col12 = st.columns(2)
        with col11:
            st.number_input('Introduce el valor previsto MIBGAS 2026', min_value=26, max_value=70, key='mibgas_simul')
            if st.session_state.get("precio_omie_previsto", None):
                st.metric('Valor OMIE previsto s/OMIP', st.session_state.precio_omie_previsto)
        with col12:
            st.metric('Valor de OMIE 2026 esperado', simul_spot)
            if simul_gas is not None:
                st.metric('Valor de gas 2026 esperado', simul_gas)

    with col2:        
        st.write(graf_hist)

        #renderer = StreamlitRenderer(df_mensual)
        #renderer.explorer()