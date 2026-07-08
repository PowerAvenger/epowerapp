import streamlit as st
import pandas as pd
#import pygwalker as pyg
#from pygwalker.api.streamlit import StreamlitRenderer

import plotly.express as px
from datetime import datetime
from utilidades import generar_menu, init_app, init_app_index
from backend_comun import carga_mibgas
from backend_mibgas import (
    filtrar_por_producto, graficar_qs, graficar_futuros_mibgas, graficar_da_corrido, graficar_da_2026_acumulado, graficar_da_comparado,
    descargar_sendeco, obtener_sendeco, graficar_gas_co2,
    obtener_spot_mensual, construir_df_mensual, graf_simul_spot, obtener_spot_diario,
    obtener_mibgas_mensual, construir_curva_mibgas_2026, graficar_curva_mibgas_2026,
    construir_media_prevista_mibgas_2026_diaria, graficar_media_prevista_mibgas_2026,
    construir_curva_mibgas_mensual_12m, graficar_curva_mibgas_mensual_12m
    )



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
    st.session_state.mibgas_simul = 40

df_mibgas_base = carga_mibgas()

# FUTUROS M MESES
productos_m = ['GMAES', 'GMES_M+2', 'GMES_M+3', 'GMES_M+4', 'GMES_M+5', 'GMES_M+6']
dfs_m = [filtrar_por_producto(df_mibgas_base, prod) for prod in productos_m]
df_mg_m = pd.concat(dfs_m, ignore_index=True)
graf_ms = graficar_futuros_mibgas(df_mg_m, tipo="M")

# FUTUROS Q TRIMESTRES
productos_q = ['GQES_Q+1', 'GQES_Q+2', 'GQES_Q+3', 'GYES_Q+4']
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
df_curva_mibgas_2026 = construir_curva_mibgas_2026(df_mibgas_mensual, df_mg_m, df_mg_q)
precio_medio_mibgas_2026 = round(df_curva_mibgas_2026["precio"].mean(), 2)
graf_mibgas_2026 = graficar_curva_mibgas_2026(df_curva_mibgas_2026, precio_medio_mibgas_2026)
df_media_mibgas_2026 = construir_media_prevista_mibgas_2026_diaria(df_mg_da, df_mg_m, df_mg_q)
graf_media_mibgas_2026 = graficar_media_prevista_mibgas_2026(df_media_mibgas_2026)

df_mibgas_año_movil = construir_curva_mibgas_mensual_12m(df_mg_m, df_mg_q)
num_meses_mibgas_año_movil = df_mibgas_año_movil["precio"].notna().sum()
precio_medio_mibgas_año_movil = round(df_mibgas_año_movil["precio"].mean(), 2)
graf_mibgas_año_movil = graficar_curva_mibgas_mensual_12m(df_mibgas_año_movil, precio_medio_mibgas_año_movil)

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


df_spot_mensual = obtener_spot_mensual()
print (df_spot_mensual)

df_total_data = df_total_data_gas_co2.merge(df_spot_mensual, on = 'fecha_entrega', how = 'left')

df_mensual = construir_df_mensual(df_total_data)


#valor_mibgas_previsto = 40
df_spot_diario = obtener_spot_diario()
print (df_spot_diario)
omie_media_2026 = round(df_spot_diario.loc[df_spot_diario["fecha"].dt.year == 2026, "spot"].mean(),2)
print(omie_media_2026)


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
graf_hist, simul_spot, simul_gas = graf_simul_spot(df_mensual, df_validacion, st.session_state.mibgas_simul, omie_media_2026=omie_media_2026, gas_media_2026=gas_media_2026)






#LAYOUT++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

zona_mensajes = st.sidebar.empty()

tab1, tab2, tab3, tab4, tab5 = st.tabs(['Históricos', 'Futuros', 'CO2', 'Simulador', 'Previsión anual'])

with tab1:
    with st.container():
        col1,col2 = st.columns([.9,.1])
        with col1:
            st.write(graf_da_corrido)
            st.write(graf_da_comparado)
            st.write(graf_da_2026_acumulado) 
            
            
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
        col11, col12 = st.columns(2)
        with col11:
            st.number_input('Introduce el valor previsto MIBGAS 2026', min_value=26, max_value=70, key='mibgas_simul')
            if st.session_state.get("precio_omie_previsto", None):
                st.metric('Valor OMIE previsto s/OMIP', st.session_state.precio_omie_previsto)
            #from pages.escalacv import valor_medio_diario
            #st.metric('Valor medio OMIE 2026 €/MWh', valor_medio_diario)
            init_app_index()
            
            st.metric('Valor medio OMIE 2026 €/MWh', omie_media_2026)
        with col12:
            st.metric('Valor de OMIE 2026 esperado', simul_spot)
            if simul_gas is not None:
                st.metric('Valor de gas 2026 esperado', simul_gas)
            st.metric("Precio medio gas 2026 (€/MWh)", df_medias.loc[df_medias["año_entrega"] == 2026, "precio_str"].values[0])
            
    with col2:        
        st.write(graf_hist)

        #renderer = StreamlitRenderer(df_mensual)
        #renderer.explorer()


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
