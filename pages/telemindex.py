import streamlit as st
from backend_telemindex import filtrar_datos, aplicar_margen, graf_principal, pt5_trans, pt1, pt7_trans, costes_indexado, evol_mensual 
from backend_comun import autenticar_google_sheets, carga_rapida_sheets, carga_total_sheets, colores_precios

import pandas as pd
import datetime

from utilidades import generar_menu, init_app, init_app_index


if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')


#inicializamos variables de sesión
generar_menu()
init_app()
init_app_index()

zona_mensajes = st.sidebar.empty() 

df_filtrado, lista_meses = filtrar_datos()
try:
    fecha_ultima_filtrado = df_filtrado['fecha'].iloc[-1]
except:
    #st.session_state.dia_seleccionado = '2025-01-01'
    st.session_state.dia_seleccionado = datetime.date(2025,1,1)
    df_filtrado, lista_meses = filtrar_datos()

#ejecutamos la función para obtener la tabla resumen y precios medios
tabla_precios, media_20, media_30, media_61, media_spot, media_ssaa = pt5_trans(df_filtrado)
media_20 = round(media_20 / 10, 1)
media_30 = round(media_30 / 10, 1)
media_61 = round(media_61 / 10, 1)
media_spot = round(media_spot, 2)
media_ssaa = round(media_ssaa, 2)
media_combo = media_spot + media_ssaa
sobrecoste_ssaa = ((media_combo / media_spot) - 1) * 100

#tabla resumen de costes ATR
tabla_atr = pt7_trans(df_filtrado)
tabla_costes = costes_indexado(df_filtrado)

df_precios_mensuales, graf_mensual = evol_mensual(st.session_state.df_sheets, colores_precios)

#generar_menu()

#ELEMENTOS DE LA BARRA LATERAL ---------------------------------------------------------------------------------------

#st.sidebar.header('', divider='rainbow')
st.sidebar.header('Histórico de indexados')
st.sidebar.write(f'Última fecha disponible: {st.session_state.ultima_fecha_sheets}')

st.sidebar.subheader('Opciones')
with st.sidebar.container(border=True):
    st.sidebar.radio("Seleccionar rango temporal", ['Por años', 'Por meses', 'Selecciona un rango de fechas'], key = "rango_temporal")

    if st.session_state.rango_temporal == 'Por años':
        st.sidebar.selectbox('Seleccione el año', options = [2025, 2024, 2023], key = 'año_seleccionado') 
        st.session_state.texto_precios = f'Año {st.session_state.año_seleccionado}, hasta el día {fecha_ultima_filtrado}'
    elif st.session_state.rango_temporal =='Por meses' : 
        col_sb1, col_sb2 = st.sidebar.container().columns(2)      
        with col_sb1:
            st.sidebar.selectbox('Seleccione el año', options = [2025, 2024, 2023], key = 'año_seleccionado') 
        with col_sb2:
            st.sidebar.selectbox('Seleccionar mes', lista_meses, key = 'mes_seleccionado')
            st.session_state.texto_precios = f'Seleccionado: {st.session_state.mes_seleccionado} de {st.session_state.año_seleccionado}'
    else:
        #st.sidebar.date_input('Selecciona un día', min_value = datetime.date(2023, 1, 1), max_value = st.session_state.ultima_fecha_sheets, key = 'dia_seleccionado')
        with st.sidebar.form(key='form_fechas_telemindex'):
            st.date_input('Selecciona un rango de días', min_value = datetime.date(2023, 1, 1), max_value = datetime.date(2025, 12, 31), key = 'dias_seleccionados')    
            #st.session_state.texto_precios = f'Día seleccionado {st.session_state.dia_seleccionado}'
            inicio, fin = st.session_state.dias_seleccionados
            st.session_state.texto_precios = (f"Rango seleccionado: {inicio.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}")
            st.form_submit_button('Actualizar cálculos')
with st.sidebar.container():
#if st.sidebar.toggle('Marca si quieres añadir margen'):
    #st.sidebar.slider("Añadir margen al gusto (en €/MWh)", min_value = 0, max_value = 50, value = 0, key = 'margen', on_change = aplicar_margen, args=(df_filtrado,))
    st.sidebar.slider("Añadir margen al gusto (en €/MWh)", min_value = 0, max_value = 50, key = 'margen', on_change = aplicar_margen, args=(df_filtrado,))
    st.sidebar.caption(f'Se ha añadido {st.session_state.margen} €/MWh')
#else:
#    st.session_state.margen = 0
#zona_mensajes = st.sidebar.empty()        

#st.sidebar.write(f'Última fecha disponible: {st.session_state.ultima_fecha_sheets}')


zona_grafica = st.empty()

# ZONA PRINCIPAL DE GRÁFICOS++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
with zona_grafica.container():

    col1, col2 = st.columns([.7,.3])

    #COLUMNA PRINCIPAL
    with col1:
        st.subheader(f'Resumen de precios medios minoristas por peaje de acceso. **:orange[{st.session_state.texto_precios}]**', divider = 'rainbow')
        
        with st.container():
            col5, col6, col7, col8, col9 = st.columns(5)
            with col5:
                st.metric(':orange[Precio medio 2.0 c€/kWh]',value = media_20)
            with col6:
                st.metric(':red[Precio medio 3.0 c€/kWh]',value = media_30)
            with col7:
                st.metric(':blue[Precio medio 6.1 c€/kWh]',value = media_61)
            with col8:
                st.metric(':green[Precio medio Spot €/MWh]',value = media_spot)
            with col9:
                st.metric('Precio medio SSAA €/MWh', value = media_ssaa, delta = f'{sobrecoste_ssaa:,.1f}%', delta_color = 'inverse', help= 'Se indica su valor medio y en qué % aumenta el precio medio Spot')
        st.empty()
        # gráfico principal de barras y lineas precios medios y omie+ssaa
        st.plotly_chart(graf_principal(df_filtrado, colores_precios))
        st.empty()
        st.subheader("Peso de los componentes por peaje de acceso", divider='rainbow')
        _, graf20, graf30, graf61 = pt1(df_filtrado)
        col10,col11,col12=st.columns(3)
        with col10:
            st.write(graf20)    
        with col11:
            st.write(graf30)
        with col12:
            st.write(graf61)
            
        # gráfico de evolución de los precios medios mensuales
        st.subheader("Evolución de los precios medios de indexado", divider='rainbow')
        st.plotly_chart(graf_mensual)

    with col2:
        st.subheader("Tabla resumen de precios por peaje de acceso", divider='rainbow')
        with st.expander("Nota sobre los precios de indexado:"):
            st.caption("Basados en las fórmulas tipo con todos los componentes de mercado y costes regulados. Se incluye FNEE, SRAD y 2€ en desvíos. Por supuesto peajes y cargos según tarifa de acceso. Añadir margen al gusto en 'Opciones' de la barra lateral")
            
        with st.container():

            tabla_margen = pd.DataFrame(columns = tabla_precios.columns, index = ['margen_2.0', 'margen_3.0', 'margen_6.1'])
            tabla_margen = tabla_margen.fillna(st.session_state.margen / 10)
                
            texto_precios=f'{st.session_state.texto_precios}. Precios en c€/kWh'
            st.caption(st.session_state.texto_precios)

            st.text ('Precios medios de indexado', help='PRECIO MEDIO (FINAL) DE LA ENERGÍA.Suma de costes (energía y ATR)')
            st.dataframe(tabla_precios, use_container_width=True)
            
            st.text ('Costes medios de indexado', help = 'COSTE MEDIO DE LA ENERGÍA, sin incluir ATR.')
            st.dataframe(tabla_costes, use_container_width=True)
            
            st.text ('Costes de ATR')
            #tabla_atr['Media'] = (tabla_precios['Media'] - tabla_costes['Media']).fillna(0)
            st.dataframe(tabla_atr, use_container_width=True )
            
            st.text ('Margen')
            st.dataframe(tabla_margen, use_container_width=True )


            #print(tabla_precios)
            #print(tabla_costes)
            #print(tabla_atr)
        


if 'df_sheets_full' not in st.session_state:
    zona_mensajes.warning('Cargados datos iniciales. Espera a que estén disponibles todos los datos', icon = '⚠️')
    #SPREADSHEET_ID = st.secrets['SHEET_INDEX_ID']
    st.session_state.df_sheets_full = carga_total_sheets()
    st.session_state.df_sheets = st.session_state.df_sheets_full
    zona_mensajes.success('Cargados todos los datos. Ya puedes consultar los históricos', icon = '👍')