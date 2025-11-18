import streamlit as st
import time
from io import StringIO
from backend_excedentes import obtener_file, graf_no_neteo_total, graf_neteo_total, graf_no_neteo, graf_coste_exc, graf_coste_pvpc, graf_demver, obtener_dfs

from utilidades import generar_menu

if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()



#usamos ejemplo de curva por defecto
#file = st.file_uploader('Curva de carga a analizar')
if 'df_norm' in st.session_state and "atr_dfnorm" in st.session_state and st.session_state.atr_dfnorm == "2.0":
    file = st.session_state.df_norm
else:
    file = None
zona_mensajes = st.empty()


if file is not None:
    try:
        #stringio = StringIO(file.getvalue().decode("utf-8"))
        #df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc,precio_medio_pvpc, coste_pvpc=obtener_file(stringio)
        df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc,precio_medio_pvpc, coste_pvpc=obtener_dfs(file)
        zona_mensajes.success('Archivo cargado correctamente!')
    except Exception as e:
        zona_mensajes.error(f'Error al cargar el archivo. Asegúrate de que el archivo tenga el formato correcto')
        time.sleep(3)
        zona_mensajes.warning('Se cargará el archivo de ejemplo')
        time.sleep(3)
        zona_mensajes.warning('Por favor, sube una curva de carga 2.0. Lo que estás viendo es un archivo de ejemplo')
        file='curvas/2024 07.csv'
        df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc,precio_medio_pvpc, coste_pvpc=obtener_file(f'curvas/2024 07.csv')
else:
    zona_mensajes.warning('Por favor, sube una curva de carga 2.0. Lo que estás viendo es un archivo de ejemplo')
    #file='curvas/2024 07.csv'
    df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc,precio_medio_pvpc, coste_pvpc=obtener_file(f'curvas/2024 07.csv')
    
#df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc,precio_medio_pvpc, coste_pvpc=obtener_file(f'curvas/2024 07.csv')

if 'df_norm' in st.session_state:
    st.sidebar.toggle('Usar curva cargada', key='toggle_curva', value=True)
neteo = st.sidebar.toggle('Cambia a NETEO (saldos horarios facturables). Recuerda que en la parte superior derecha del gráfico tienes herramientas de zoom.')

col1, col2 = st.columns([.8,.2])
with col1:
    

    if neteo:
        graf2=graf_neteo_total(df_origen)
        st.write(graf2)
    else:
        graf1=graf_no_neteo_total(df_origen)
        st.write(graf1)
with col2:
    st.subheader('Datos generales',divider='rainbow')
    mensaje = f"Se dispone de datos desde el **{fecha_ini_curva}** hasta el **{fecha_fin_curva}**"
    st.markdown(mensaje, unsafe_allow_html=True)
    st.info('Estos son los valores de demanda y excedentes, tanto leídos por el contador como facturados por saldos horarios (NETEO). Valores en kWh.',icon="ℹ️")
    
    col11,col12=st.columns(2)
    with col11:
        st.metric('Lectura de demanda',value=demanda)
        st.metric(f':red-background[Demanda a facturar]', value=demanda_neteo)
    with col12:
        st.metric('Lectura de excedentes', value=vertido)
        st.metric(f':green-background[Excedentes a facturar]', value=vertido_neteo)

col3, col4 = st.columns([.8,.2])
with col3:
    graf3=graf_no_neteo(df_origen)
    st.write(graf3)
with col4:
    st.subheader('Valores horarios por días. Gráfico animado',divider='rainbow')
    mensaje = f"Se dispone de datos desde el **{fecha_ini_curva}** hasta el **{fecha_fin_curva}**"
    #st.markdown(mensaje, unsafe_allow_html=True)
    st.info('Mueve el cursor en la parte inferior del gráfico para visualizar valores horarios según la fecha seleccionada. Valores de contador',icon="ℹ️")
    
col5, col6 = st.columns([.8,.2])
with col5:
    graf4=graf_coste_exc(df_coste_24h)
    st.write(graf4)
with col6:
    st.subheader('Excedentes PVPC: Facturación',divider='rainbow')
    mensaje = f"Periodo facturado desde el **{fecha_ini_curva}** hasta el **{fecha_fin_curva}**"
    st.markdown(mensaje, unsafe_allow_html=True)
    st.info('En esta sección puedes ver una gráfica del acumulado horario de excedentes contrastada con el valor de los mismos. Como resultado, se obtiene el precio medio del excedente a facturar',icon="ℹ️")
    col61,col62=st.columns(2)
    with col61:
        st.metric(f':green-background[Excedentes a facturar (kWh)]', value=vertido_neteo)
        st.metric(f':violet-background[Precio medio excedente €/kWh]',value=precio_medio_exc)
        #st.metric(f':red-background[Demanda a facturar]', value=demanda_neteo)
    with col62:
        st.metric(f':green-background[Coste a facturar (€)]', value=coste_exc)
        
col7, col8 = st.columns([.8,.2])
with col7:
    graf5=graf_coste_pvpc(df_coste_24h)
    st.write(graf5)
with col8:
    st.subheader('Demanda PVPC: Facturación',divider='rainbow')
    mensaje = f"Periodo facturado desde el **{fecha_ini_curva}** hasta el **{fecha_fin_curva}**"
    st.markdown(mensaje, unsafe_allow_html=True)
    st.info('En esta sección puedes ver una gráfica del acumulado horario de la demanda contrastada con el valor de la misma. Como resultado, se obtiene el precio medio de la demanda a facturar',icon="ℹ️")
    col81,col82=st.columns(2)
    with col81:
        st.metric(f':green-background[Demanda a facturar (kWh)]', value=demanda_neteo)
        st.metric(f':violet-background[Precio medio demanda €/kWh]',value=precio_medio_pvpc)
        #st.metric(f':red-background[Demanda a facturar]', value=demanda_neteo)
    with col82:
        st.metric(f':green-background[Coste a facturar (€)]', value=coste_pvpc)        
            
        
col9, col10 = st.columns([.8,.2])
with col9:
    #graf5=graf_coste_pvpc(df_coste_24h)
    #st.write(graf5)
    st.empty()
with col10:
    st.subheader('Compara con tu oferta en fijo',divider='rainbow')
    mensaje = f"Periodo facturado desde el **{fecha_ini_curva}** hasta el **{fecha_fin_curva}**"
    st.markdown(mensaje, unsafe_allow_html=True)
    st.info('Con los resultados anteriores de los excedentes y demanda PVPC, puedes compararlos con tu oferta en fijo. Introduce precio fijo de compra (consumo) y de venta (excedentes).',icon="ℹ️")

    col101,col102=st.columns(2)
    with col101:
        precio_fijo_demanda=st.number_input('Introduce precio de compra en €/kWh', min_value=0.050, max_value=0.300,value=0.150,step=.001,format='%0.3f')
        coste_fijo_demanda=round(precio_fijo_demanda*demanda_neteo,2)
        st.metric(f':red-background[Coste del consumo (€)]', value=coste_fijo_demanda)

        total_coste_pvpc=round(coste_pvpc-coste_exc,2)
        if total_coste_pvpc < 0:
            total_coste_pvpc=0
        st.metric(f':violet-background[Total PVPC (€)]',value=total_coste_pvpc)

        #st.metric(f':violet-background[Demanda a facturar]', value=demanda_neteo)
    with col102:
        precio_fijo_vertidos=st.number_input('Introduce precio de venta en €/kWh', min_value=0.010, max_value=0.150,value=0.080,step=.001,format='%0.3f')
        coste_fijo_vertidos=round(precio_fijo_vertidos*vertido_neteo,2)
        st.metric(f':green-background[Coste del vertido (€)]', value=coste_fijo_vertidos)

        total_coste_fijo=round(coste_fijo_demanda-coste_fijo_vertidos,2)
        dif_pvpc_fijo=round(total_coste_pvpc-total_coste_fijo,2)
        dif_pvpc_fijo_porc = round((dif_pvpc_fijo/total_coste_pvpc)*100,1)
        st.metric(f':orange-background[Total FIJO (€)]', value=total_coste_fijo, delta=f'{dif_pvpc_fijo_porc}%')
    
