import streamlit as st
from backend_demanda import (download_esios, download_esios_id_5m, graf_1, download_esios_id_month, graf_2, graf_2b, graf_2c,
    calcular_datos_anual, graf_3, graf_3bis, actualizar_historicos, graf_ranking_mes, ranking_mensual, graf_diferencias, diferencias_mes,
    graficar_media_diaria
    )
from datetime import datetime, timedelta
import pandas as pd
from dateutil.relativedelta import relativedelta
import plotly.express as px
import base64
import calendar
from utilidades import generar_menu, init_app


if not st.session_state.get('usuario_autenticado', False) and not st.session_state.get('usuario_free', False):
    st.switch_page('epowerapp.py')

generar_menu()

if "cache_cleared" not in st.session_state:
    st.cache_data.clear()  # Limpiar caché al iniciar
    st.session_state.cache_cleared = True  # Evita que se borre en cada interacción

if 'añadir_autoconsumo' not in st.session_state:
    st.session_state.añadir_autoconsumo = False


#fechahora_hoy = datetime.now() #formato fecha_hora
#fecha_hoy = datetime.now().date() #formato fecha
#fecha_ini_mes_anterior = (fecha_hoy.replace(day=1) - relativedelta(months=1)) #usado para download mensual del mes anterior y asegurar los datos en el cambio de mes



# Descargamos la demanda real peninsular para el mes en curso
fecha_hoy = datetime.now()
año_hoy = fecha_hoy.year
num_mes_hoy = fecha_hoy.month
#dia_hoy = fecha_hoy.day
#fecha_ayer = fecha_hoy - timedelta(days=1)

años = [2026, 2025, 2018]
id_dem_real = 1293
agrupacion = 'day'
tipo_agregacion = 'average'
lista_dfs = []
for año in años:
    fecha_ini = f'{año}-{num_mes_hoy:02d}-01'
    ultimo_dia_mes = calendar.monthrange(año, num_mes_hoy)[1]
    fecha_fin = f'{año}-{num_mes_hoy:02d}-{ultimo_dia_mes:02d}'
    
    df_in = download_esios(id_dem_real, fecha_ini, fecha_fin, agrupacion, tipo_agregacion)
    lista_dfs.append(df_in)
df_dem_real = pd.concat(lista_dfs, ignore_index=True)


# Descargamos la demanda prevista REE
id_dem_prevista = 460
fecha_mañana = (fecha_hoy + timedelta(days=1))
fecha_mañana_api=fecha_mañana.strftime('%Y-%m-%d')
#fecha_final = fecha_mañana + timedelta(days=15)
fecha_final = datetime(año_hoy, num_mes_hoy, calendar.monthrange(año_hoy, num_mes_hoy)[1])
fecha_final_api = fecha_final.strftime('%Y-%m-%d')
df_dem_prevista = download_esios(id_dem_prevista, fecha_mañana_api, fecha_final_api, agrupacion, tipo_agregacion)


# Unimos real con prevista
df_dem_real = df_dem_real.copy()
df_dem_prevista = df_dem_prevista.copy()
df_demand = pd.concat([df_dem_real, df_dem_prevista], ignore_index=True).sort_values('datetime').reset_index(drop=True)

# Añadimos columnas y arreglamos datos
df_demand['año'] = df_demand['datetime'].dt.year
df_demand['mes'] = df_demand['datetime'].dt.month
df_demand['dia'] = df_demand['datetime'].dt.day
df_demand['value'] = df_demand['value'].astype(float)
df_demand['value'] = df_demand['value'].round(2)
df_demand['value'] /= 1000
df_demand.rename(columns={'value': 'GW'}, inplace=True)
meses = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}
df_demand['mes_nombre'] = df_demand['mes'].map(meses)
meses_seleccion = df_demand['mes_nombre'].unique()
df_demand['media_evol'] = df_demand.groupby('año')['GW'].expanding().mean().reset_index(level=0, drop=True)
df_demand['suma_evol'] = df_demand.groupby('año')['GW'].expanding().sum().reset_index(level=0, drop=True)
df_demand['media_mensual'] = df_demand.groupby(['año', 'mes'])['GW'].expanding().mean().reset_index(level=[0,1], drop=True)


# MODIFICAMOS DF DEMAND CON UN PUNTO DE UNIÓN ENTRE LA DEMANDA REAL Y LA PREVISTA
df_real_año_hoy = df_demand[(df_demand['año'] == año_hoy) & (df_demand['short_name'] == 'Demanda real')]
ultimo_real = df_real_año_hoy.sort_values('dia').iloc[-1]
# Previsión 2026
df_prev_año_hoy = df_demand[(df_demand['año'] == año_hoy) & (df_demand['short_name'] == 'Previsión diaria')]
# Crear punto puente
punto_puente = ultimo_real.copy()
punto_puente['short_name'] = 'Previsión diaria'
# Insertar al inicio de la previsión
df_prev_año_hoy = pd.concat([punto_puente.to_frame().T, df_prev_año_hoy], ignore_index=True)
# Reemplazar en df_demand
df_demand = pd.concat([df_demand[~((df_demand['año'] == año_hoy) & (df_demand['short_name'] == 'Previsión diaria'))], df_prev_año_hoy], ignore_index=True)
# Añadir columna para saber si el año es bisiesto
df_demand['datetime'] = pd.to_datetime(df_demand['datetime'],errors='coerce')
df_demand['bisiesto'] = df_demand['datetime'].dt.is_leap_year
# Recalcular el día del año corrigiendo si NO es bisiesto
# Esto evita que el 1-mar de un año no bisiesto se convierta en día 60
df_demand['dia_anual'] = df_demand.apply(
    lambda row: row['datetime'].timetuple().tm_yday if row['bisiesto'] else (
        row['datetime'].timetuple().tm_yday if row['datetime'].month < 3 else row['datetime'].timetuple().tm_yday + 1
    ), axis=1
)
# Ahora puedes generar la fecha ficticia sin errores ni desplazamientos
df_demand['fecha_ficticia'] = pd.to_datetime('2020-01-01') + pd.to_timedelta(df_demand['dia_anual'] - 1, unit='D')

print('df_demand')
print(df_demand)


# FILTRAMOS DF DEMAND CON EL AÑO ACTUAL PARA OBTENER VALORES DE DEMANDA REAL Y PREVISTA
df_año_hoy = df_demand[df_demand['año'] == año_hoy]

# Demanda real → última disponible en el año en curso
idx_real = (df_año_hoy[df_año_hoy['short_name'] == 'Demanda real']['datetime'].idxmax())
ultimo_datetime_real = df_año_hoy.loc[idx_real, 'datetime']
ultimo_registro = ultimo_datetime_real
mes_actual_nombre = df_año_hoy.loc[idx_real, 'mes_nombre']
mes_actual_num = df_año_hoy.loc[idx_real, 'mes']
media_real_GW = df_año_hoy.loc[idx_real, 'media_mensual']
año_actual = df_año_hoy.loc[idx_real, 'año']
# Calculamos la demanda real en GWh
df_mes_real = df_año_hoy[(df_año_hoy['short_name'] == 'Demanda real') & (df_año_hoy['año'] == año_actual) & (df_año_hoy['mes'] == mes_actual_num)]
dias_mes = calendar.monthrange(año_actual, mes_actual_num)[1]
horas_mes = dias_mes * 24
demanda_real_GWh = (df_mes_real['GW'] * 24).sum()

# Previsión diaria → última disponible en 2026
idx_prev = (df_año_hoy[df_año_hoy['short_name'] == 'Previsión diaria']['datetime'].idxmax())
media_prevista_GW = df_año_hoy.loc[idx_prev, 'media_mensual']
demanda_prevista_GWh = media_prevista_GW * horas_mes



# CREAMOS UN DF DE UNA LÍNEA CON LOS DATOS ACTUALIZADOS DE DEMANDA PREVISTA PARA AÑADIR A LOS HISTÓRICOS
df_mes_actual = pd.DataFrame([{
    'demanda_media_GW': media_prevista_GW,
    'año': año_actual,
    'mes': mes_actual_num,
    'mes_nombre': mes_actual_nombre,
    'horas_mes': horas_mes,
    'demanda_real_GWh': demanda_prevista_GWh
}])
##OBTENEMOS HISTORICOS Y LOS ACTUALIZAMOS CON LOS DATOS MENSUALES API REE. USADOS PARA LA GRAFICA 2
#datos_mensual, años_registro = actualizar_historicos(datos_mensual)
datos_mensual, años_registro = actualizar_historicos(df_mes_actual) 



#todas estas variables son str
años_lista = años_registro.tolist()
años_lista = [str(año) for año in años_registro]
año_actual = (años_lista[-1])
año_anterior = int(años_lista[-2])
año_pordefecto_1 = (años_lista[-3])
año_pordefecto_2 = (años_lista[-2])


#if datos is not None and not datos.empty:
if df_mes_real is not None and not df_mes_real.empty:
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


#demanda_prevista = datos_mensual['demanda_real_GWh'].iloc[-1] 
#demanda_prevista_mostrar = "{:,}".format(int(demanda_prevista)).replace(",", ".")
demanda_prevista_total = datos_mensual['demanda_GWh'].iloc[-1]

if 'año_seleccionado_1' not in st.session_state:
    st.session_state.año_seleccionado_1 = año_pordefecto_1
if 'año_seleccionado_2' not in st.session_state:
    st.session_state.año_seleccionado_2 = año_pordefecto_2
if 'año_seleccionado_pormeses' not in st.session_state:
    st.session_state.año_seleccionado_pormeses = año_actual


if 'mes_seleccionado_nombre_año' not in st.session_state:
    st.session_state.mes_seleccionado_nombre_año = 'Diciembre'
    st.session_state.mes_numero_año = 12
    #st.session_state.año_seleccionado_1 = año_pordefecto_1
    #st.session_state.año_seleccionado_2 = año_pordefecto_2
if 'mes_seleccionado_nombre' not in st.session_state:
    st.session_state.mes_seleccionado_nombre = mes_actual_nombre
    st.session_state.mes_numero = fecha_hoy.month
if 'mes_seleccionado_nombre_pormeses' not in st.session_state:
    st.session_state.mes_seleccionado_nombre_pormeses = mes_actual_nombre
    st.session_state.mes_numero_año_pormeses = fecha_hoy.month


def actualizar_mes_comp_anual():
    """
    Actualiza el mes seleccionado según el año seleccionado para las comparativas anuales
    """
    if st.session_state.año_seleccionado_1 == año_actual or st.session_state.año_seleccionado_2 == año_actual:
        st.session_state.mes_seleccionado_nombre_año = mes_actual_nombre
        st.session_state.mes_numero_año = fecha_hoy.month
        #st.session_state.mes_seleccionado_año = mes_previsto
        print ('hola')
    else:
        st.session_state.mes_seleccionado_nombre_año = 'Diciembre'
        st.session_state.mes_numero_año = 12

def actualizar_mes_comp_mensual():
    """
    Actualiza el mes seleccionado según el año seleccionado para las comparativas anuales
    """
    if st.session_state.año_seleccionado_pormeses == año_actual:
        st.session_state.mes_seleccionado_nombre_pormeses = mes_actual_nombre
        st.session_state.mes_numero_año_pormeses = fecha_hoy.month
        #st.session_state.mes_seleccionado_año = mes_previsto
        print ('hola')
    else:
        st.session_state.mes_seleccionado_nombre_pormeses = 'Diciembre'
        st.session_state.mes_numero_año_pormeses = 12


#meses_hasta_actual_comp_anual = {num: nombre for num, nombre in meses.items() if num <= st.session_state.mes_numero_año}

#print('meses hasta el actual para comparativa mensual')
#print(meses_hasta_actual_comp_anual)
#meses_invertidos_anual = {nombre: num for num, nombre in meses_hasta_actual_comp_anual.items()}


meses_hasta_actual_comp_mensual = {num: nombre for num, nombre in meses.items() if num <= st.session_state.mes_numero_año_pormeses}

print('meses hasta el actual para comparativa mensual')
print(meses_hasta_actual_comp_mensual)
meses_invertidos = {nombre: num for num, nombre in meses_hasta_actual_comp_mensual.items()}



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



# GRAFICAR EVOLUCIÓN DE LA DEMANDA MEDIA DIARIA: REAL Y PREVISTA
años_visibles = ['2025', '2026']
graf_media_evol_mes = graficar_media_diaria(df_demand, años_visibles, mes_actual_nombre, año_hoy)





# VISUALIZACIÓN +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
with st.sidebar:
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

#media_real_GW = "{:,.2f}".format(float(media_real_GW)).replace(".", ",")
#demanda_real_GWh = "{:,}".format(int(demanda_real_GWh)).replace(",", ".")
#media_prevista_GW = "{:,.2f}".format(float(media_prevista_GW)).replace(".", ",")
#demanda_prevista_GWh = "{:,}".format(int(demanda_prevista_GWh)).replace(",", ".")

#CONFIGURACIÓN PARA EL PRIMER GRUPO DE DATOS-----------------------------------------------------------------
#col1, col2, col3 = st.columns([0.25, 0.4, 0.4])
col1, col2, col3 = st.columns(3)


with st.container():
    with col1:
        st.subheader("Demanda media mensual: REAL y PREVISTA", divider ='rainbow')
        st.info(f'Incluye la demanda peninsular real y prevista para el mes en curso ({mes_actual_nombre} de {año_actual}). Último registro {fecha_ultimo_registro} {hora_ultimo_registro}',icon="ℹ️")
        col1a, col1b, col1c, col1d = st.columns(4)
        with col1a:
            st.metric('Demanda real media GW', value = f'{media_real_GW:,.2f}'.replace(".", ","))
        with col1b:
            st.metric('Demanda real GWh', value = f'{demanda_real_GWh:,.0f}'.replace(",", "X").replace(".", ",").replace("X", "."))
        with col1c:
            st.metric('Demanda prevista media GW', value = f'{media_prevista_GW:,.2f}'.replace(".", ","))
        with col1d:
            st.metric('Demanda prevista GWh', value = f'{demanda_prevista_GWh:,.0f}'.replace(",", "X").replace(".", ",").replace("X", "."))
        
        st.plotly_chart(graf_media_evol_mes)

        
        # interacción autoconsumo
        #FF5722 amarillo anaranjado
        #007BFF azul 
        
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
            st.selectbox('Año a comparar', options = años_lista, key = 'año_seleccionado_1', on_change = actualizar_mes_comp_anual) 
            
        # año 2 a seleccionar para la comparativa
        with col1bb:
            st.selectbox('Año a comparar', options = años_lista, key = 'año_seleccionado_2', on_change = actualizar_mes_comp_anual) #index = años_lista.index(año_pordefecto_2)
            
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
            st.plotly_chart(graf_2(datos_mensual, mes_actual_nombre, demanda_prevista_total, años_visibles))
            st.plotly_chart(graf_3bis(df_datos_anual_con_autoconsumo))
        else:
            st.plotly_chart(graf_2(datos_mensual, mes_actual_nombre, demanda_prevista_GWh, años_visibles))
            st.plotly_chart(graf_3(datos_anual_real))
    with col3:
        # gráfico de acumulado anual
        #st.plotly_chart(graf_2b(datos_mensual, mes_previsto_nombre, demanda_prevista_acumulada))
        st.plotly_chart(graf_2c(datos_mensual, mes_actual_nombre, demanda_prevista_media, años_visibles))
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
            <p style="color:white;">Selecciona el mes a comparar del año seleccionado. Obtendrás los diferenciales con el mismo mes de otros años, así como el ranking según la demanda (o consumo).</p>
        </div>
        """, unsafe_allow_html=True)
        st.write('')
        
        # lo usamos para actualizar el listado de meses a escoger en función del año 
        # para que en el año en curso aparezca hasta el mes en curso
        #col61, col62, col63=st.columns(3)
        col11a, col11b, col11c = st.columns(3)
        # año 1 a seleccionar para la comparativa
        with col11a:
            st.selectbox('Año de referencia', options = años_lista, key = 'año_seleccionado_pormeses', on_change=actualizar_mes_comp_mensual)
        with col11b:
            st.selectbox('Mes a comparar', options = meses_invertidos, key = 'mes_seleccionado_nombre_pormeses') #index = st.session_state.mes_numero - 1


        
    with col21:
        
        st.subheader(f'{st.session_state.mes_seleccionado_nombre_pormeses} {st.session_state.año_seleccionado_pormeses}: Diferencias respecto al mismo mes (GWh) - {texto_dif}', divider = 'rainbow')
        col2a, col2b, col2c = st.columns([.25, 0.10, .65])
        with col2a:
            st.dataframe(diferencias_mes_completo_mostrar)
        with col2c:
            st.write(graf_diferencias)
    with col31:
            
            st.subheader(f'Ranking de {st.session_state.mes_seleccionado_nombre_pormeses}s - {texto_dif}', divider = 'rainbow')
            col3a, col3b = st.columns([.65, .35])
            with col3a:
                st.plotly_chart(graf_ranking_mes)
            



