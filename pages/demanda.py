import streamlit as st
from backend_demanda import (download_esios_id_5m, graf_1, download_esios_id_month, graf_2, graf_2b, graf_2c,
    calcular_datos_anual, graf_3, graf_3bis, actualizar_historicos, graf_ranking_mes, ranking_mensual, graf_diferencias, diferencias_mes
    )
from datetime import datetime
import pandas as pd
from dateutil.relativedelta import relativedelta
import plotly.express as px
import base64
from utilidades import generar_menu, init_app


if not st.session_state.get('usuario_autenticado', False):
    st.switch_page('epowerapp.py')

generar_menu()



#--------------------------------------------------------------------------------------------------

if "cache_cleared" not in st.session_state:
    st.cache_data.clear()  # Limpiar caché al iniciar
    st.session_state.cache_cleared = True  # Evita que se borre en cada interacción


if 'añadir_autoconsumo' not in st.session_state:
    st.session_state.añadir_autoconsumo = False

fechahora_hoy = datetime.now() #formato fecha_hora
fecha_hoy = datetime.now().date() #formato fecha
fecha_ini_mes_anterior = (fecha_hoy.replace(day=1) - relativedelta(months=1)) #usado para download mensual del mes anterior y asegurar los datos en el cambio de mes

##DESCARGAMOS DATOS DEL ID1293 DEMANDA REAL MW CINCOMINUTAL FECHA=HOY
try:
    datos, ultimo_registro = download_esios_id_5m('1293', fecha_hoy, fecha_hoy, 'five_minutes') #tipo_agregacion = 'sum'
except Exception as e:
    # por si realizamos la descarga durante la primera hora del mes
    datos, ultimo_registro = None, None

#print(horas_transcurridas)
    
##DESCARGAMOS DATOS DEL ID1293 DEMANDA MEDIA REAL MENSUAL MW FECHA=HOY. USADOS PARA LA GRAFICA 2
try:
    datos_mensual, mes_previsto, demanda_real, mes_previsto_nombre, meses_seleccion, media_real = download_esios_id_month('1293', fecha_ini_mes_anterior, fecha_hoy, 'month', 'average', ultimo_registro)
except Exception as e:
    datos_mensual, mes_previsto, demanda_real, mes_previsto_nombre, meses_seleccion, media_real = None, None, None, None, None, None
    print(f'error {e}')


##OBTENEMOS HISTORICOS Y LOS ACTUALIZAMOS CON LOS DATOS MENSUALES API REE. USADOS PARA LA GRAFICA 2
datos_mensual, años_registro = actualizar_historicos(datos_mensual) #demanda_prevista_acumulada, demanda_prevista_media

demanda_real = "{:,}".format(int(demanda_real)).replace(",", ".")
media_real = "{:,.2f}".format(float(media_real)).replace(".", ",")


#todas estas variables son str
años_lista = años_registro.tolist()
años_lista = [str(año) for año in años_registro]
año_actual = (años_lista[-1])
año_anterior = int(años_lista[-2])
año_pordefecto_1 = (años_lista[-3])
año_pordefecto_2 = (años_lista[-2])

#if 'mes_seleccionado' not in st.session_state:
#    st.session_state.mes_seleccionado = 12
#    st.session_state.mes_numero = 12
#    st.session_state.año_seleccionado_1 = año_pordefecto_1
#    st.session_state.año_seleccionado_2 = año_pordefecto_2


if datos is not None and not datos.empty:
    fecha_ultimo_registro = ultimo_registro.strftime("%d.%m.%Y")
    hora_ultimo_registro = ultimo_registro.strftime("%H:%M")

    #st.metric('Fecha', value = fecha_ultimo_registro)
    #st.metric('Hora', value = hora_ultimo_registro)

#Datos estimados de generación por autoconsumo anuales en GWh. ---------------------------------------------------------------------------
#Fuente: APPA.
#2024 9400 fue una media estimativa a partir de la encuesta realizada en el último trimestre del año. Actualizado el 12/02/2025 s/informe APPA
#2025 a ojo buen cubero.
df_gen_autoconsumo_anual = pd.DataFrame({
    'año': [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
    'autogen': [446, 925, 1656, 3007, 4564, 7262, 9243, 11000, 12000]  
})
#coeficientes aplicados al autoconsumo anual (obtenidos del pvgis un poco a pelo)
coeficientes_mensuales = {'Enero': 0.065, 'Febrero': 0.070, 'Marzo': 0.086, 'Abril': 0.090, 
                           'Mayo': 0.096, 'Junio': 0.095, 'Julio': 0.103, 'Agosto': 0.102, 
                           'Septiembre': 0.091, 'Octubre': 0.080, 'Noviembre': 0.063, 'Diciembre': 0.060}


#vamos a generar una tabla con los años y los meses aplicando los coeficientes por meses a los autoconsumos anuales
df_gen_mensual = df_gen_autoconsumo_anual.copy()
for mes, coef in coeficientes_mensuales.items():
    df_gen_mensual[mes] = df_gen_mensual['autogen'] * coef #* 1000
# Eliminamos columna autogen
#df_gen_mensual = df_gen_mensual.drop(columns=['autogen'])
# Eliminamos la columna de autogen ya que la hemos distribuido en los meses
df_gen_mensual.drop(columns=['autogen'], inplace=True)
# Convertimos el DataFrame a formato largo
df_gen_mensual = df_gen_mensual.melt(id_vars=['año'], var_name='mes_nombre', value_name='autogen')
print ('datos df_gen_mensual')
print (df_gen_mensual)

# Unimos con el DataFrame principal
datos_mensual = datos_mensual.merge(df_gen_mensual, on=['año', 'mes_nombre'], how='left')
#datos_mensual['acumulado_GWh'] = datos_mensual.groupby('año')['demanda_GWh'].cumsum()

if st.session_state.añadir_autoconsumo:
    # Sumamos los valores en 'demanda_GWh'
    datos_mensual['demanda_GWh'] = datos_mensual['demanda_real_GWh'] + datos_mensual['autogen']
else:
    datos_mensual['demanda_GWh'] = datos_mensual['demanda_real_GWh']
datos_mensual['acumulado_GWh'] = datos_mensual.groupby('año')['demanda_GWh'].cumsum()
datos_mensual['media_GWh'] = datos_mensual.groupby('año')['demanda_GWh'].expanding().mean().reset_index(level=0, drop=True)
demanda_prevista_acumulada = datos_mensual['acumulado_GWh'].iloc[-1]
demanda_prevista_media = datos_mensual['media_GWh'].iloc[-1]
print (datos_mensual)


#formato tabla de los datos mensuales (lista) de demanda
datos_mensual_tabla = pd.pivot_table(
    data = datos_mensual,
    values = 'demanda_GWh',
    index = 'año',
    columns = 'mes_nombre',
)

meses = {1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio', 
         7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'}
orden_meses = [meses[m] for m in range(1, 13)]
datos_mensual_tabla = datos_mensual_tabla[orden_meses]
datos_mensual_tabla = datos_mensual_tabla.round().astype('Int64')
datos_mensual_tabla_mostrar = datos_mensual_tabla.style.background_gradient(axis = None)



datos_anual_real, datos_anual_total = calcular_datos_anual(datos_mensual, año_anterior) #, datos_anual_mesencurso , st.session_state.mes_seleccionado
print('Imprimimos datos_anual_real')
print(datos_anual_real)
print('Imprimimos datos_anual_total')
print(datos_anual_total)


#GENERAMOS TABLA LARGA CON LA DEMANDA REAL Y EL AUTOCONSUMO, PARA VISUALIZACIÓN DEL GRÁFICO DE ÁREAS
#pasamos a TWh
df_gen_autoconsumo_anual['autogen'] = df_gen_autoconsumo_anual['autogen'] / 1000
df_merged = pd.merge(datos_anual_real, df_gen_autoconsumo_anual, left_on = 'año', right_on = 'año')
print('df_merged')
print(df_merged)
# Convertir el DataFrame a formato largo para graficar con px.area
df_datos_anual_con_autoconsumo = df_merged.melt(id_vars = 'año', value_vars=['autogen', 'demanda_real_TWh'], 
                            var_name = 'serie', value_name = 'valor')
print('Imprimimos df_datos_anual_con_autoconsumo')
print(df_datos_anual_con_autoconsumo)


# GENERAMOS UNA TABLA ORDENADA PARA VISUALIZAR EL RANKING DE AÑOS SEGÚN SEA SOLO DEMANDA REAL O CON AUTOCONSUMO

datos_anual_total_ordenado = datos_anual_total.sort_values(by='demanda_total_TWh', ascending=False)
#datos_mensual_mes_encurso_ordenado.set_index('año',inplace=True)

datos_anual_total_ordenado['año'] = datos_anual_total_ordenado['año'].astype(str)
#datos_mensual_mes_encurso_ordenado.index=datos_mensual_mes_encurso_ordenado.index.astype(str)
datos_anual_total_ordenado['color'] = 'blue'
#datos_anual_total_ordenado.loc[datos_anual_total_ordenado['año'] == st.session_state.año_seleccionado_2, 'color']='darkred'
datos_anual_total_ordenado = datos_anual_total_ordenado.reset_index(drop=True)

min = datos_anual_total_ordenado['demanda_total_TWh'].min()
max = datos_anual_total_ordenado['demanda_total_TWh'].max()
print('datos_anual_total_ordenado')
print(datos_anual_total_ordenado)


# GRÁFICO DE AÑOS ORDENADOS POR DEMANDA------------------------------------------------------------------
graf_total_anual_ordenado = px.bar(
    datos_anual_total_ordenado,
    x = datos_anual_total_ordenado.index,
    y = 'demanda_total_TWh',
    color = 'color',
    color_discrete_map = {'blue': '#ADD8E6'} #, 'darkred': 'darkred'},             
)

if st.session_state.añadir_autoconsumo:
        titulo = 'Ranking según la Demanda anual: REAL + AUTOCONSUMO'
else:
        titulo = 'Ranking según la Demanda anual: REAL'

graf_total_anual_ordenado.update_layout(
    
    title = {'text': titulo, 'x':0.5,'xanchor':'center'},
    legend = dict(
        orientation = 'h',  # Leyenda en horizontal
        x = 0.5,  # Posición horizontal centrada
        xanchor = 'center',  # Alineación horizontal centrada
        y = 1,  # Colocarla ligeramente por encima del gráfico
        yanchor = 'top',  # Alineación vertical en la parte inferior de la leyenda
        ),
        yaxis = dict(title = 'Demanda TWh',
        range = [min - 20, max + 10]
    ),
    showlegend = False,
    bargap = 0.6
)
        
graf_total_anual_ordenado.update_xaxes(
    ticktext = datos_anual_total_ordenado['año'],
    tickvals = list(range(len(datos_anual_total_ordenado['año']))),
    title = 'Años'
)
#----------------------------------------------------------------------------------------------------------------


demanda_prevista = datos_mensual['demanda_real_GWh'].iloc[-1] 
demanda_prevista_mostrar = "{:,}".format(int(demanda_prevista)).replace(",", ".")
demanda_prevista_total = datos_mensual['demanda_GWh'].iloc[-1]

if 'año_seleccionado_1' not in st.session_state:
    st.session_state.año_seleccionado_1 = año_pordefecto_1
if 'año_seleccionado_2' not in st.session_state:
    st.session_state.año_seleccionado_2 = año_pordefecto_2


if 'mes_seleccionado_nombre_año' not in st.session_state:
    st.session_state.mes_seleccionado_nombre_año = 'Diciembre'
    st.session_state.mes_numero_año = 12
    #st.session_state.año_seleccionado_1 = año_pordefecto_1
    #st.session_state.año_seleccionado_2 = año_pordefecto_2
if 'mes_seleccionado_nombre' not in st.session_state:
    st.session_state.mes_seleccionado_nombre = mes_previsto_nombre
    st.session_state.mes_numero = fecha_hoy.month


def actualizar_mes():
    """
    Actualiza el mes seleccionado según el año seleccionado.
    """
    if st.session_state.año_seleccionado_1 == año_actual or st.session_state.año_seleccionado_2 == año_actual:
        st.session_state.mes_seleccionado_nombre_año = mes_previsto_nombre
        st.session_state.mes_numero_año = fecha_hoy.month
        #st.session_state.mes_seleccionado_año = mes_previsto
        print ('hola')
    else:
        st.session_state.mes_seleccionado_nombre_año = 'Diciembre'
        st.session_state.mes_numero_año = 12
        #st.session_state.mes_seleccionado_año = meses_invertidos.get(st.session_state.mes_seleccionado_nombre_año)


#if 'mes_seleccionado_año' not in st.session_state:
#    st.session_state.mes_seleccionado_año = 12
#    st.session_state.año_seleccionado_1 = año_pordefecto_1
#    st.session_state.año_seleccionado_2 = año_pordefecto_2
    #st.session_state.mes_numero = 12

#st.session_state

#nombre_mes = meses[st.session_state.mes_numero]

meses_hasta_actual = {num: nombre for num, nombre in meses.items() if num <= st.session_state.mes_numero_año}
print(meses_hasta_actual)
meses_invertidos = {nombre: num for num, nombre in meses_hasta_actual.items()}



# OBTENEMOS LA DEMANDA ACUMULADA DE LOS AÑOS SELECCIONADOS Y HASTA EL MES SELECCIONADO
datos_anual_acumulado_hasta = datos_mensual.copy()
datos_anual_acumulado_hasta['acumulado_GWh'] = datos_anual_acumulado_hasta['acumulado_GWh'] / 1000
datos_anual_acumulado_hasta = datos_anual_acumulado_hasta.rename(columns={'acumulado_GWh':'acumulado_TWh'})

#demanda_seleccionada_1 = datos_anual_acumulado_hasta.loc[(datos_anual_acumulado_hasta['año'] == int(st.session_state.año_seleccionado_1)) & (datos_anual_acumulado_hasta['mes'] == st.session_state.mes_seleccionado_año), 'acumulado_TWh'].values[0]
#demanda_seleccionada_2 = datos_anual_acumulado_hasta.loc[(datos_anual_acumulado_hasta['año'] == int(st.session_state.año_seleccionado_2)) & (datos_anual_acumulado_hasta['mes'] == st.session_state.mes_seleccionado_año), 'acumulado_TWh'].values[0]
demanda_seleccionada_1 = datos_anual_acumulado_hasta.loc[(datos_anual_acumulado_hasta['año'] == int(st.session_state.año_seleccionado_1)) & (datos_anual_acumulado_hasta['mes'] == st.session_state.mes_numero_año), 'acumulado_TWh'].values[0]
demanda_seleccionada_2 = datos_anual_acumulado_hasta.loc[(datos_anual_acumulado_hasta['año'] == int(st.session_state.año_seleccionado_2)) & (datos_anual_acumulado_hasta['mes'] == st.session_state.mes_numero_año), 'acumulado_TWh'].values[0]


demanda_seleccionada_1_mostrar = "{:,.1f}".format(demanda_seleccionada_1).replace(",", "X").replace(".", ",").replace("X", ".")
demanda_seleccionada_2_mostrar = "{:,.1f}".format(demanda_seleccionada_2).replace(",", "X").replace(".", ",").replace("X", ".")
diferencia = demanda_seleccionada_2-demanda_seleccionada_1
diferencia_mostrar = "{:,.1f}".format(diferencia).replace(",", "X").replace(".", ",").replace("X", ".")
diferencia_porc = (diferencia / demanda_seleccionada_1) * 100
diferencia_porc_mostrar = "{:,.1f}%".format(diferencia_porc).replace(",", "X").replace(".", ",").replace("X", ".")









df_diferencias_mes_completo_graf, diferencias_mes_completo_mostrar = diferencias_mes(datos_mensual_tabla, datos_mensual_tabla_mostrar, año_actual)

print('diferencias mes completo mostrar')
print(diferencias_mes_completo_mostrar)

graf_diferencias = graf_diferencias(df_diferencias_mes_completo_graf, año_actual)

datos_mensual_mes_encurso_ordenado = ranking_mensual(datos_mensual_tabla, año_actual)
graf_ranking_mes = graf_ranking_mes(datos_mensual_mes_encurso_ordenado)


if st.session_state.añadir_autoconsumo:
    texto_dif = 'CONSUMO'
else:
    texto_dif = 'DEMANDA'











# VISUALIZACIÓN +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

#CONFIGURACIÓN PARA EL PRIMER GRUPO DE DATOS-----------------------------------------------------------------
col1, col2, col3 = st.columns([0.25, 0.4, 0.4])


with st.container():
    with col1:
        # cabecera
        st.subheader("Demanda mensual y acumulada", divider ='rainbow')
        # info
        st.info(f'Incluye la demanda prevista para el mes en curso ({mes_previsto_nombre} de {año_actual}). Último registro {fecha_ultimo_registro} {hora_ultimo_registro}',icon="ℹ️")
        # datos del mes en curso: media, real y prevista.
        col1a, col1b, col1c = st.columns(3)
        with col1a:
            st.metric('Demanda real media GW', value = media_real)
        with col1b:
            st.metric('Demanda real GWh', value = demanda_real)
        with col1c:
            st.metric('Demanda prevista GWh', value = demanda_prevista_mostrar)
        
        # interacción autoconsumo
        #FF5722 amarillo anaranjado
        #007BFF azul 
        st.markdown("""
        <div style="background-color:#FF5722; padding: 5px 10px 5px 10px; border-radius: 10px;"> 
            <p style="color:white; font-weight:bold;">¡Interacciona!</p>
            <p style="color:white;">Dale al selector y obtendrás la estimación del CONSUMO (DEMANDA REAL + AUTOCONSUMO)</p>
        </div>
        """, unsafe_allow_html=True)
        st.write('')
        colx, coly = st.columns([.6, .4])
        with colx:
            st.toggle('Estimar el autoconsumo', help = 'Datos de APPA. 2025 es una estimación propia', key = 'añadir_autoconsumo') #,value=st.session_state.get('añadir_autoconsumo',False))
        with coly:
            #st.image('arrow-5818_256.gif', )
            def get_base64_gif(file_path):
                with open(file_path, "rb") as gif_file:
                    return base64.b64encode(gif_file.read()).decode("utf-8")

            gif_base64 = get_base64_gif("images/arrow-5818_256.gif")

            st.markdown(
                f'<img src="data:image/gif;base64,{gif_base64}" width="250" height="50">',
                unsafe_allow_html=True
            )
        # interacción años
        st.markdown("""
        <div style="background-color:#007BFF; padding: 5px 10px 5px 10px; border-radius: 10px;">
            <p style="color:white; font-weight:bold;">¡Interacciona!</p>
            <p style="color:white;">Selecciona los años a comparar. En el caso del año actual, obtendrás la demanda (o consumo) acumulado hasta el mes en curso, así como el diferencial y %. Unidades en TWh.</p>
        </div>
        """, unsafe_allow_html=True)
        st.write('')
        col1aa, col1bb, col1cc = st.columns(3)
        with col1aa:
            st.selectbox('Año a comparar', options = años_lista, key = 'año_seleccionado_1', on_change = actualizar_mes) 
            
        # año 2 a seleccionar para la comparativa
        with col1bb:
            st.selectbox('Año a comparar', options = años_lista, key = 'año_seleccionado_2', on_change = actualizar_mes) #index = años_lista.index(año_pordefecto_2)
            
        # selección del mes (hasta)
        col1aaa, col1bbb, col1ccc = st.columns(3)
        with col1aaa:
            st.metric(f'Demanda {st.session_state.año_seleccionado_1}', value = demanda_seleccionada_1_mostrar)
        with col1bbb:
            st.metric(f'Demanda {st.session_state.año_seleccionado_2}', value = demanda_seleccionada_2_mostrar)
        with col1ccc:    
            #st.selectbox('Hasta el mes de', options = meses_invertidos, index = st.session_state.mes_numero_año - 1, key = 'mes_seleccionado_nombre_año', on_change=actualizar_mes) #
            st.metric('Diferencia',value = diferencia_mostrar, delta = diferencia_porc_mostrar)
        
          
       
            
    with col2:
        if st.session_state.añadir_autoconsumo:
            st.plotly_chart(graf_2(datos_mensual, mes_previsto_nombre, demanda_prevista_total))
            st.plotly_chart(graf_3bis(df_datos_anual_con_autoconsumo))
        else:
            st.plotly_chart(graf_2(datos_mensual, mes_previsto_nombre, demanda_prevista))
            st.plotly_chart(graf_3(datos_anual_real))
    with col3:
        # gráfico de acumulado anual
        #st.plotly_chart(graf_2b(datos_mensual, mes_previsto_nombre, demanda_prevista_acumulada))
        st.plotly_chart(graf_2c(datos_mensual, mes_previsto_nombre, demanda_prevista_media))
        st.plotly_chart(graf_total_anual_ordenado)



#CONFIGURACIÓN PARA EL SEGUNDO GRUPO DE DATOS-----------------------------------------------------------------
col11, col21, col31 = st.columns([0.2, 0.4, 0.4])
with st.container():
    with col11:
        st.subheader("Comparativa por meses",divider='rainbow')
        
        # info
        st.markdown("""
        <div style="background-color:#007BFF; padding: 5px 10px 5px 10px; border-radius: 10px;">
            <p style="color:white; font-weight:bold;">¡Interacciona!</p>
            <p style="color:white;">Selecciona el mes a comparar de 2025. Obtendrás los diferenciales con el mismo mes de otros años, así como el ranking según la demanda (o consumo).</p>
        </div>
        """, unsafe_allow_html=True)
        st.write('')
        
        # lo usamos para actualizar el listado de meses a escoger en función del año 
        # para que en el año en curso aparezca hasta el mes en curso
        #col61, col62, col63=st.columns(3)
        col11a, col11b, col11c = st.columns(3)
        # año 1 a seleccionar para la comparativa
        with col11a:
            st.selectbox('Mes a comparar', options = meses_invertidos, key = 'mes_seleccionado_nombre') #index = st.session_state.mes_numero - 1


        
    with col21:
        
        st.subheader(f'{st.session_state.mes_seleccionado_nombre} {año_actual}: Diferencias respecto al mismo mes (GWh) - {texto_dif}', divider = 'rainbow')
        col2a, col2b, col2c = st.columns([.25, 0.10, .65])
        with col2a:
            st.dataframe(diferencias_mes_completo_mostrar)
        with col2c:
            st.write(graf_diferencias)
    with col31:
            
            st.subheader(f'Ranking de {st.session_state.mes_seleccionado_nombre}s - {texto_dif}', divider = 'rainbow')
            col3a, col3b = st.columns([.65, .35])
            with col3a:
                st.plotly_chart(graf_ranking_mes)





        
 
#st.dataframe(datos_mensual_tabla_mostrar, use_container_width=True)


#PRIMER GRÁFICO---------------------------------------------------------------------
#col1,col2=st.columns([0.2,0.8])
#with col1:
#    if datos is not None and not datos.empty:
#        st.plotly_chart(graf_1(datos))
#    else:
#        st.error('No se disponen de datos.')
    
#with col2:
#    st.subheader("Datos del último registro",divider='rainbow')
#    st.info('De este bloque da datos y gráficos, sólo nos interesa la fecha y hora del  último registro esios id1293.',icon="ℹ️")
    #usado cuando ultimo registro lo obtenía de esios 5min
    #fecha_ultimo_registro=ultimo_registro.strftime("%d.%m.%Y")


#st.session_state

