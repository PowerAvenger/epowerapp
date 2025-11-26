import streamlit as st
from backend_telemindex import filtrar_datos, aplicar_margen, graf_principal, pt5_trans, pt1, pt7_trans, costes_indexado, evol_mensual, construir_df_curva_sheets, añadir_costes_curva 
from backend_comun import autenticar_google_sheets, carga_rapida_sheets, carga_total_sheets, colores_precios
from backend_curvadecarga import graficar_media_horaria, graficar_queso_periodos

import pandas as pd
import datetime

from utilidades import generar_menu, init_app, init_app_index


if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')


#inicializamos variables de sesión
generar_menu()
init_app()
init_app_index()

if "rango_curvadecarga" in st.session_state:
    if st.session_state.rango_temporal == "Selecciona un rango de fechas":
        st.session_state.dias_seleccionados = st.session_state.rango_curvadecarga

zona_mensajes = st.sidebar.empty() 

df_filtrado, lista_meses = filtrar_datos()
try:
    fecha_ultima_filtrado = df_filtrado['fecha'].iloc[-1]
except:
    st.session_state.dia_seleccionado = datetime.date(2025,1,1)
    df_filtrado, lista_meses = filtrar_datos()

if "df_norm_h" in st.session_state and st.session_state.df_norm_h is not None and st.session_state.rango_temporal == "Selecciona un rango de fechas":
    df_curva_sheets = construir_df_curva_sheets(df_filtrado)
    df_curva_sheets = añadir_costes_curva(df_curva_sheets)
    st.session_state.df_curva_sheets = df_curva_sheets
    print("df_curva_sheets generado correctamente")
    df_uso = df_curva_sheets.copy()
    df_uso = df_uso.drop_duplicates(subset=["fecha", "hora", "spot"])
    print(df_uso)

    #consumo total curva
    consumo_total_curva = df_uso['consumo_neto_kWh'].sum()
    #calculamos el coste spot ponderado en €/MWh
    media_spot_curva = round(df_uso['coste_spot'].sum()/(consumo_total_curva/1000),2)
    coste_total_curva = round(df_uso['coste_total'].sum()+consumo_total_curva*st.session_state.margen/1000,2)
    
else:
    st.session_state.df_curva_sheets = None
    print("df_norm_h no está disponible → no se genera df_curva_sheets")
    df_uso = df_filtrado.copy()


#ejecutamos la función para obtener la tabla resumen y precios medios
tabla_precios, media_20, media_30, media_61, media_spot, media_ssaa, media_atr_curva = pt5_trans(df_uso)

print(f'Media precio curva en €/MWh: {media_atr_curva}')
print(f'Media precio 3.0 en €/MWh: {media_30}')

#media_20 = round(media_20 / 10, 1)
media_20 = media_20 / 10
#media_30 = round(media_30 / 10, 1)
media_30 = media_30 / 10
#media_61 = round(media_61 / 10, 1)
media_61 = media_61 / 10
media_spot = round(media_spot, 2)
media_ssaa = round(media_ssaa, 2)
media_combo = media_spot + media_ssaa
sobrecoste_ssaa = ((media_combo / media_spot) - 1) * 100




if "df_norm_h" in st.session_state and st.session_state.df_norm_h is not None and st.session_state.rango_temporal == "Selecciona un rango de fechas":
    media_atr_curva = media_atr_curva / 10
    apuntamiento_spot = round(media_spot_curva/media_spot,3)

    atr_map = {
        "2.0": media_20,
        "3.0": media_30,
        "6.1": media_61
    }
    media_atr = atr_map.get(st.session_state.atr_dfnorm)
    coste_sin_ponderar = round(consumo_total_curva * media_atr / 100,2)
    desvio_coste_total = coste_total_curva-coste_sin_ponderar
    desvio_coste_total_porc = (desvio_coste_total / coste_sin_ponderar) * 100

    print(f'Coste sin ponderar: {coste_sin_ponderar}€')
    print(f'Coste ponderado: {coste_total_curva}€')

#tabla resumen de costes ATR
tabla_atr = pt7_trans(df_uso)
tabla_costes = costes_indexado(df_uso)

df_precios_mensuales, graf_mensual = evol_mensual(st.session_state.df_sheets, colores_precios)



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
        with st.sidebar.form(key='form_fechas_telemindex'):
            # Asegurar que ultima_fecha_sheets es un objeto datetime.date
            ultima_fecha_sheets = st.session_state.ultima_fecha_sheets
            if isinstance(ultima_fecha_sheets, (pd.Timestamp, datetime.datetime)):
                ultima_fecha_sheets = ultima_fecha_sheets.date()
            st.date_input('Selecciona un rango de días', min_value = datetime.date(2023, 1, 1), max_value = ultima_fecha_sheets, key = 'dias_seleccionados')   
            inicio, fin = st.session_state.dias_seleccionados
            st.session_state.texto_precios = (f"Rango seleccionado: {inicio.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}")
            st.form_submit_button('Actualizar cálculos')

with st.sidebar.container():
    st.sidebar.slider("Añadir margen al gusto (en €/MWh)", min_value = 0, max_value = 50, key = 'margen', on_change = aplicar_margen, args=(df_uso,))
    st.caption(f'Se ha añadido {st.session_state.margen} €/MWh')



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
                #st.metric(':orange[Precio medio 2.0 c€/kWh]',value = media_20)
                st.metric(':orange[Precio medio 2.0 c€/kWh]',value = f"{media_20:.2f}".replace('.', ','))
                if media_atr_curva is not None:
                    st.metric(f'Precio medio curva {st.session_state.atr_dfnorm} c€/kWh',value = f"{media_atr_curva:.2f}".replace('.', ','))
            with col6:
                st.metric(':red[Precio medio 3.0 c€/kWh]',value = f"{media_30:.2f}".replace('.', ','))
                if media_atr_curva is not None:
                    st.metric(f'Consumo curva kWh',value = f"{consumo_total_curva:,.0f}".replace(',', '.'))
            with col7:
                st.metric(':blue[Precio medio 6.1 c€/kWh]',value = f"{media_61:.2f}".replace('.', ','))
                if media_atr_curva is not None:
                    st.metric('Coste total curva €',value = f"{coste_total_curva:,.0f}".replace(',', '.'), delta=f"{desvio_coste_total_porc:,.2f}%".replace('.',','), delta_color='inverse', help = 'El % indica el desvío con respecto al coste medio aritmético')
            with col8:
                st.metric(':green[Precio medio Spot €/MWh]',value = f"{media_spot:.2f}".replace('.', ','))
                if media_atr_curva is not None:
                    st.metric('Precio medio Spot curva €/MWh',value = f"{media_spot_curva:.2f}".replace('.', ','), delta=f"{apuntamiento_spot:,.3f}".replace('.', ','), delta_color='inverse', help = 'Se indica apuntamiento.')
            with col9:
                st.metric(':violet[Precio medio SSAA €/MWh]', value = f"{media_ssaa:.2f}".replace('.', ','), delta = f'{sobrecoste_ssaa:,.1f}%', delta_color = 'inverse', help= 'Se indica su valor medio y en qué % aumenta el precio medio Spot')
        st.empty()
        # gráfico principal de barras y lineas precios medios y omie+ssaa
        #st.plotly_chart(graf_principal(df_filtrado, colores_precios))
        st.plotly_chart(graf_principal(df_uso, colores_precios))
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
        if media_atr_curva is not None:
            st.subheader("Perfil de consumo", divider='rainbow')
            graf_medias_horarias=graficar_media_horaria(st.session_state.df_norm)
            st.plotly_chart(graf_medias_horarias, use_container_width=True)

            st.subheader("Consumo por periodos")
            graf_periodos=graficar_queso_periodos(st.session_state.df_norm)
            st.plotly_chart(graf_periodos, use_container_width=True)
        st.subheader("Tabla resumen de precios por peaje de acceso", divider='rainbow')
        with st.expander("Nota sobre los precios de indexado:"):
            st.caption("Basados en las fórmulas tipo con todos los componentes de mercado y costes regulados. Se incluye FNEE, SRAD y 1€/MWh por diferencias con los SSAA C2. Por supuesto peajes y cargos según tarifa de acceso. Añadir margen al gusto en 'Opciones' de la barra lateral")
            
        with st.container():

            tabla_margen = pd.DataFrame(columns = tabla_precios.columns, index = ['margen_2.0', 'margen_3.0', 'margen_6.1'])
            tabla_margen = tabla_margen.fillna(st.session_state.margen / 10)
                
            texto_precios=f'{st.session_state.texto_precios}. Precios en c€/kWh'
            st.caption(st.session_state.texto_precios)

            st.text ('Precios medios de indexado', help='PRECIO MEDIO (FINAL) DE LA ENERGÍA.Suma de costes (energía y ATR)')
            #st.dataframe(tabla_precios, use_container_width=True)
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
        if media_atr_curva is not None:
            st.subheader("Perfil de consumo", divider='rainbow')
            graf_medias_horarias=graficar_media_horaria(st.session_state.df_norm)
            st.plotly_chart(graf_medias_horarias, use_container_width=True)


if 'df_sheets_full' not in st.session_state:
    zona_mensajes.warning('Cargados datos iniciales. Espera a que estén disponibles todos los datos', icon = '⚠️')
    #SPREADSHEET_ID = st.secrets['SHEET_INDEX_ID']
    st.session_state.df_sheets_full = carga_total_sheets()
    st.session_state.df_sheets = st.session_state.df_sheets_full
    zona_mensajes.success('Cargados todos los datos. Ya puedes consultar los históricos', icon = '👍')