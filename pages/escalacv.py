import streamlit as st
from utilidades import generar_menu, init_app



from backend_escalacv import leer_json, diarios_totales, diarios, mensuales, horarios
import datetime
from datetime import datetime
import pandas as pd

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()



if 'inicio' not in st.session_state:
    st.cache_data.clear()
    st.session_state.inicio = True

fecha_hoy=datetime.today().date()

if 'año_seleccionado_esc' not in st.session_state:
    st.session_state.año_seleccionado_esc = 2025
    st.session_state.año_anterior_esc = 2025

CREDENTIALS = st.secrets['GOOGLE_SHEETS_CREDENTIALS']

if st.session_state.get('componente', 'SPOT') == 'SPOT':
    FILE_ID = st.secrets['FILE_ID_SPOT']
    datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)
elif st.session_state.get('componente', 'SPOT') == 'SSAA':
    FILE_ID = st.secrets['FILE_ID_SSAA']
    datos_total, fecha_ini, fecha_fin = leer_json(FILE_ID, CREDENTIALS)
else:
    FILE_ID_SPOT = st.secrets['FILE_ID_SPOT']
    FILE_ID_SSAA = st.secrets['FILE_ID_SSAA']
    datos_spot, fecha_ini_spot, fecha_fin_spot = leer_json(FILE_ID_SPOT, CREDENTIALS)
    datos_ssaa, fecha_ini_ssaa, fecha_fin_ssaa = leer_json(FILE_ID_SSAA, CREDENTIALS)

    datos_spot = datos_spot.reset_index()
    datos_ssaa = datos_ssaa.reset_index()
    datos_total = pd.merge(
        datos_spot[['datetime', 'value']].rename(columns={'value': 'value_spot'}),
        datos_ssaa[['datetime', 'value']].rename(columns={'value': 'value_ssaa'}),
        on='datetime',
        how='inner'
    )
    datos_total['value'] = datos_total['value_spot'] + datos_total['value_ssaa']

    datos_total['fecha'] = datos_total['datetime'].dt.date
    datos_total['hora'] = datos_total['datetime'].dt.hour
    datos_total['dia'] = datos_total['datetime'].dt.day
    datos_total['mes'] = datos_total['datetime'].dt.month
    datos_total['año'] = datos_total['datetime'].dt.year
    datos_total.set_index('datetime', inplace=True)
    fecha_ini = datos_total['fecha'].min()
    fecha_fin = datos_total['fecha'].max()


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
fecha_fin_año = datetime(st.session_state.año_seleccionado_esc, 12, 31) #datos_año_filtrado['fecha'].max()
#datos diarios
datos_dia, graf_ecv_diario = diarios(datos_año_filtrado, fecha_ini_año, fecha_fin_año)
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
#graf_ecv_mensual = mensuales(datos_año_filtrado)




if 'dia_seleccionado_esc' not in st.session_state:
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

#st.write(ultimo_registro) 
#   fecha_descarga=pasar_fecha()
    #st.write(ultima_descarga)

años_lista = list(range(2018, 2026))



st.sidebar.selectbox('Selecciona el año', options = años_lista, key = 'año_seleccionado_esc')
st.sidebar.slider('Selecciona el día', min_value= fecha_min_select_dia, max_value=fecha_max_select_dia, key = 'dia_seleccionado_esc')
st.sidebar.radio('Selecciona el componente de mercado', options=['SPOT', 'SSAA', 'SPOT+SSAA'], key = 'componente')

if st.session_state.componente == 'SPOT+SSAA':
    st.sidebar.toggle('Predator Mode', key = 'dos_colores')
if 'dos_colores' in st.session_state and st.session_state.dos_colores:
    st.sidebar.toggle('Peso componentes', key = 'peso_comp')






    

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

col5,col6,col7=st.columns([.4,.4,.2])

with col5:
    st.plotly_chart(graf_ecv_mensual)
with col6:
    st.write(graf_horario_dia)
with col7:

    st.subheader('Datos en €/MWh',divider='rainbow')
    st.metric(f'Precio medio diario', value=valor_medio_diario_select)
    st.metric(f'Precio mínimo horario (hora: {hora_min_select})', value=valor_minimo_horario_select)
    st.metric(f'Precio máximo horario (hora: {hora_max_select})', value=valor_maximo_horario_select)

    #st.metric(f'Precio medio diario ( {fecha_min_horario})', value=valor_minimo_horario)
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
            
        
    

    
