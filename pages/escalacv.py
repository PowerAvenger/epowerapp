import streamlit as st
from utilidades import (generar_menu, init_app_json_escalacv, 
                        init_app, init_app_index
)

from backend_escalacv import (diarios_totales, diarios, mensuales, horarios, medias_horarias, evolucion_mensual, meses_español, 
                              obtener_df_scatter_mensual, 
                              graficar_estimacion_inicial,
                              obtener_punto_anual_real, recalibrar_intercepto_con_punto, graficar_scatter_combo, obtener_puntos_anuales, 
                              graficar_simulacion_cuadratica
)
import datetime
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go 

if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()




#if 'inicio' not in st.session_state:
#    st.cache_data.clear()
#    st.session_state.inicio = True

fecha_hoy=datetime.today().date()
num_mes_actual = fecha_hoy.month
mes_actual = meses_español[num_mes_actual]

if 'año_seleccionado_esc' not in st.session_state:
    st.session_state.año_seleccionado_esc = 2026
    st.session_state.año_anterior_esc = 2026
if 'año_seleccionado_comp' not in st.session_state:
    st.session_state.año_seleccionado_comp = 2025
    st.session_state.año_anterior_comp = 2025

if 'mes_seleccionado_esc' not in st.session_state:
    st.session_state.mes_seleccionado_esc = mes_actual
    #st.session_state.año_anterior_esc = 2025    

if 'componente' not in st.session_state:
    st.session_state.componente = 'SPOT'





init_app_json_escalacv()
#init_datos_combinados_escalacv()

datos_total = st.session_state.datos_total_escalacv
fecha_ini = st.session_state.fecha_ini_escalacv
fecha_fin = st.session_state.fecha_fin_escalacv

ultimo_registro = datos_total['fecha'].max()
valor_minimo_horario_total = datos_total['value'].min()
valor_maximo_horario_total = datos_total['value'].max()
fecha_min_horario_total = datos_total.loc[datos_total['value'].idxmin(), 'fecha'] 
fecha_max_horario_total = datos_total.loc[datos_total['value'].idxmax(), 'fecha'] 

#DATOS DIARIOS DESDE 2018
datos_totales, graf_ecv_total = diarios_totales(datos_total, fecha_ini, fecha_fin)
valor_minimo_diario_total = datos_totales['value'].min()
valor_maximo_diario_total = datos_totales['value'].max()
fecha_min_diario_total = datos_totales.loc[datos_totales['value'].idxmin(), 'fecha'] 
fecha_max_diario_total = datos_totales.loc[datos_totales['value'].idxmax(), 'fecha']

#FILTRAMOS POR EL AÑO SELECCIONADO
datos_año_filtrado = datos_total[datos_total['año'] == st.session_state.año_seleccionado_esc]
fecha_ini_año = datos_año_filtrado['fecha'].min()
fecha_fin_año = datetime(st.session_state.año_seleccionado_esc, 12, 31) 
#FILTRAMOS POR EL AÑO COMPARADO
datos_año_comparado = datos_totales[datos_totales['año'] == st.session_state.año_seleccionado_comp]

#datos diarios
#datos_dia, graf_ecv_diario = diarios(datos_año_filtrado, fecha_ini_año, fecha_fin_año)
datos_dia, graf_ecv_diario = diarios(datos_año_filtrado, fecha_ini_año, fecha_fin_año, datos_año_comparado)
valor_medio_diario = round(datos_dia['value'].mean(),2)
valor_minimo_diario = datos_dia['value'].min()
valor_maximo_diario = datos_dia['value'].max()
fecha_min_diario = datos_dia.loc[datos_dia['value'].idxmin(), 'fecha'] 
fecha_max_diario = datos_dia.loc[datos_dia['value'].idxmax(), 'fecha'] 
#fechas para slider valores horarios de un día concreto
fecha_min_select_dia = datos_dia['fecha'].min()#.date()
fecha_max_select_dia = datos_dia['fecha'].max()#.date()
print (f'fecha min dia select: {fecha_min_select_dia}')
print (f'fecha max dia select: {fecha_max_select_dia}')



graf_ecv_mensual = mensuales(datos_dia)
graf_ecv_evol_mes_años = evolucion_mensual(datos_totales)
#graf_ecv_mensual = mensuales(datos_año_filtrado)




if 'dia_seleccionado_esc' not in st.session_state:
    st.session_state.dia_seleccionado_esc = fecha_max_select_dia

if st.session_state.dia_seleccionado_esc > fecha_max_select_dia:
    st.session_state.dia_seleccionado_esc = fecha_max_select_dia

if st.session_state.año_seleccionado_esc != st.session_state.año_anterior_esc: 
    st.session_state.dia_seleccionado_esc = datetime(st.session_state.año_seleccionado_esc, 1, 1)
    st.session_state.año_anterior_esc = st.session_state.año_seleccionado_esc
if isinstance(st.session_state.dia_seleccionado_esc, datetime):
    st.session_state.dia_seleccionado_esc = st.session_state.dia_seleccionado_esc.date()


#datos_horarios, graf_horario_dia, datos_horarios_filtrado = horarios(datos_total)

print('datos año filtrado')
print(datos_año_filtrado)

datos_horarios, graf_horario_dia, datos_horarios_filtrado = horarios(datos_año_filtrado)
#valores del dia seleccionado
valor_medio_diario_select = round(datos_horarios_filtrado['value'].mean(),2)
valor_minimo_horario_select = round(datos_horarios_filtrado['value'].min(),2)
valor_maximo_horario_select = round(datos_horarios_filtrado['value'].max(),2)
hora_min_select = datos_horarios_filtrado.loc[datos_horarios_filtrado['value'].idxmin(), 'hora']
hora_max_select = datos_horarios_filtrado.loc[datos_horarios_filtrado['value'].idxmax(), 'hora']

valor_medio_horario = round(datos_horarios['value'].mean(),2)
valor_minimo_horario = round(datos_horarios['value'].min(),2)
valor_maximo_horario = round(datos_horarios['value'].max(),2)
fecha_min_horario = datos_horarios.loc[datos_horarios['value'].idxmin(), 'fecha']
fecha_max_horario = datos_horarios.loc[datos_horarios['value'].idxmax(), 'fecha']

medias_horarias_filtrado, graf_medias_horarias = medias_horarias(datos_año_filtrado)

#st.write(ultimo_registro) 
#   fecha_descarga=pasar_fecha()
    #st.write(ultima_descarga)

años_lista = list(range(2018, 2027)) #se pone un año más del actual
años_comp = [
    a for a in años_lista
    if a != st.session_state.año_seleccionado_esc
]
meses_lista = ['todos', 'ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic']


# ELEMENTOS DE LA BARRA LATERAL DE OPCIONES-----------------------------------------------------------------------------------------------
#st.sidebar.header('', divider='rainbow')
st.sidebar.subheader('Escala Cavero-Vidal')
st.sidebar.markdown(f':blue-background[Sección dedicada a **Roberto Cavero García**]')
st.sidebar.selectbox('Selecciona el año a visualizar', options = años_lista, key = 'año_seleccionado_esc')
st.sidebar.selectbox('Selecciona el año a comparar la media anual', options = años_comp, key = 'año_seleccionado_comp')
st.sidebar.selectbox('Selecciona el mes', options = meses_lista, key = 'mes_seleccionado_esc')
st.sidebar.date_input('Selecciona el día', min_value= fecha_min_select_dia, max_value=fecha_max_select_dia, key = 'dia_seleccionado_esc')
st.sidebar.radio('Selecciona el componente de mercado', options=['SPOT', 'SSAA', 'SPOT+SSAA'], key = 'componente')

if st.session_state.componente == 'SPOT+SSAA':
    st.sidebar.toggle('Predator Mode', key = 'dos_colores')
if 'dos_colores' in st.session_state and st.session_state.dos_colores:
    st.sidebar.toggle('Peso componentes', key = 'peso_comp')






    
# VISUALIZACIÓN ÁREA PRINCIPAL---------------------------------------------------------------------------------------------------------
# Gráfijo fijo de medias diarias y anuales
with st.container():
    col1,col2=st.columns([0.8,0.2])
    with col1:
        st.plotly_chart(graf_ecv_total)
        #st.plotly_chart(graf_ecv_diario)
    with col2:
        st.subheader('Datos en €/MWh',divider='rainbow')
        #st.metric(f'Precio medio diario {st.session_state.año_seleccionado}', value=valor_medio_diario)
        st.metric(f'Precio mínimo diario ( {fecha_min_diario_total})', value=valor_minimo_diario_total)
        st.metric(f'Precio máximo diario ({fecha_max_diario_total})', value=valor_maximo_diario_total)

# Gráfico interactivo de medias diarias según el año seleccionado
with st.container():
    col1,col2=st.columns([0.8,0.2])
    with col1:
        #st.plotly_chart(graf_ecv_total)
        st.plotly_chart(graf_ecv_diario)
    with col2:
        st.subheader('Datos en €/MWh',divider='rainbow')
        st.metric(f'Precio medio diario {st.session_state.año_seleccionado_esc}', value=valor_medio_diario)
        st.metric(f'Precio mínimo diario ( {fecha_min_diario})', value=valor_minimo_diario)
        st.metric(f'Precio máximo diario ({fecha_max_diario})', value=valor_maximo_diario)

with st.container():
    col5,col6,col7=st.columns([.4,.4,.2])
    with col5:
        st.plotly_chart(graf_ecv_mensual)
    with col6:
        st.plotly_chart(graf_medias_horarias)
    with col7:
        st.subheader('Datos en €/MWh',divider='rainbow')
        sub1, sub2 = st.columns([.7,.3])
        with sub1:
            st.metric(f'Precio mínimo horario ({fecha_min_horario})', value=valor_minimo_horario)
            st.metric(f'Precio máximo horario ({fecha_max_horario})', value=valor_maximo_horario)
        with sub2:
            def mod_min():
                st.session_state.dia_seleccionado_esc = fecha_min_horario
            def mod_max():
                st.session_state.dia_seleccionado_esc = fecha_max_horario

            st.button('Seleccionar día', on_click=mod_min, key='mod_min')
            st.button('Seleccionar día', on_click=mod_max)

with st.container():
    col5,col6,col7=st.columns([.4,.4,.2])
    with col5:
        st.write(graf_ecv_evol_mes_años)
    with col6:
        st.write(graf_horario_dia)
    with col7:
        st.subheader('Datos en €/MWh',divider='rainbow')
        st.metric(f'Precio medio diario', value=valor_medio_diario_select)
        st.metric(f'Precio mínimo horario (hora: {hora_min_select})', value=valor_minimo_horario_select)
        st.metric(f'Precio máximo horario (hora: {hora_max_select})', value=valor_maximo_horario_select)

        #st.metric(f'Precio medio diario ( {fecha_min_horario})', value=valor_minimo_horario)



                
with st.container():
    col5,col6,col7=st.columns([.4,.4,.2])
    with col5:
        mostrar_combo = st.button('Mostrar simulación SSAA a partir de SPOT', use_container_width=True)

    if mostrar_combo:
        if "df_sheets" not in st.session_state:
            init_app()
            init_app_index()

        # 2. Construimos DF mensual SOLO una vez
        if "df_scatter_mensual" not in st.session_state:
            obtener_df_scatter_mensual()

    
    if 'df_scatter_mensual' in st.session_state:
        print('df_scatter_mensual')
        print(st.session_state.df_scatter_mensual)
        #grafico base con los scatter omie ssaa mensuales
        graf_scatter_combo = graficar_scatter_combo()
              
        if 'omie_input' not in st.session_state:
            st.session_state.omie_input = 58
        #añadimos 
        p_real = obtener_puntos_anuales()
        graf_scatter_combo, ssaa_simulada, _ = graficar_simulacion_cuadratica(
            graf_scatter_combo,
            st.session_state.df_scatter_mensual,
            {
                2025: p_real[2025],
                2026: p_real[2026],
            },
            st.session_state.omie_input,
            nombre="Curva central",
            color="orange"
        )
        
        

        #graf_scatter_combo, ssaa_simulada, modelo_quad = graficar_simulacion_cuadratica(graf_scatter_combo,st.session_state.df_scatter_mensual, puntos_anuales, st.session_state.omie_input)

        #graf_scatter_combo, ssaa_A, _ = graficar_simulacion_cuadratica(
            graf_scatter_combo,
            st.session_state.df_scatter_mensual,
            {
                2025: p_real[2025],
                2026: {"omie": 54, "ssaa": 23},
            },
            st.session_state.omie_input,
            nombre="Escenario A (54 → 23)",
            color="#2CA02C"
        )
        

        #graf_scatter_combo, ssaa_B, _ = graficar_simulacion_cuadratica(
            graf_scatter_combo,
            st.session_state.df_scatter_mensual,
            {
                2025: p_real[2025],
                2026: {"omie": 58, "ssaa": 19},
            },
            st.session_state.omie_input,
            nombre="Escenario B (58 → 19)",
            color="#D62728"
        )
        
        with col5:
            st.subheader('Micropower 2026 combo SPOT+SSAA', divider='rainbow')
            # 3. Input OMIE anual
            st.number_input("OMIE medio anual esperado (€/MWh)", min_value=0.0, max_value=200.0, step=1.0, key='omie_input')
            c55, c56, c57 =st.columns(3)
            with c55:
                st.metric('SPOT MEDIO', f'{st.session_state.omie_input:,.2f}') 
            with c56:
                st.metric('SSAA MEDIO', f'{ssaa_simulada:,.2f}') 
                
            with c57:
                combo_estimado = st.session_state.omie_input+ssaa_simulada
                st.metric('COMBO SPOT+SSAA',f'{combo_estimado:,.2f}')

                    
            st.plotly_chart(graf_scatter_combo, use_container_width=True)

            

                
        

        
