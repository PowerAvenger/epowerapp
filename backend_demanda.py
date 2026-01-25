import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go 
import streamlit as st
from datetime import datetime

@st.cache_data
def download_esios (id, fecha_ini, fecha_fin, agrupacion, tipo_agregacion):
    cab = dict()
    cab ['x-api-key']=st.secrets['ESIOS_API_KEY']
    url_id = 'https://api.esios.ree.es/indicators'
    url=f'{url_id}/{id}?&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}&time_agg={tipo_agregacion}'
    print(url)
    datos_origen = requests.get(url, headers = cab).json()
    print(datos_origen)
    short_name = datos_origen['indicator']['short_name']
    name = datos_origen['indicator']['name']
    df_in = pd.DataFrame(datos_origen['indicator']['values'])
    df_in = (df_in
        .assign(datetime = lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
            .to_datetime(vh_['datetime'], utc = True)  # con la fecha local
            .dt
            .tz_convert('Europe/Madrid')
            .dt
            .tz_localize(None),
            short_name = short_name,
            name = name
            ) 
            .loc[:,['datetime','value', 'short_name', 'name']]
    )    
    return df_in

def graficar_media_diaria(df_demand, años_visibles, mes_nombre_actual, año_actual):
    graf_media_evol_mes = px.line(df_demand, x = 'fecha_ficticia', y = 'media_mensual', 
        color = 'año', 
        #color_discrete_sequence = colores_años,
        #width = 1000,
        #height= 600,
        labels = {'media_mensual':'GW', 'fecha_ficticia':'día'},
        #title = f'Evolución mensual de la {tecnologia} - media diaria (GWh)',
        title = f'Evolución mensual de la demanda media diaria (GW) en {mes_nombre_actual} de {año_actual}',
        custom_data = df_demand[['short_name', 'año', 'mes_nombre']],
        #facet_col = 'mes_nombre',
        #facet_col_wrap = 6,
        line_dash='short_name',
        line_dash_map={
            'Demanda real': 'solid',
            'Previsión diaria': 'dot'
            },
    )

    for trace in graf_media_evol_mes.data:
        if trace.name.startswith(str(año_actual)):
            trace.update(line=dict(width=5))
        # Control de visibilidad por año
        año_trace = trace.name.split(',')[0]  # '2026'
        if año_trace not in map(str, años_visibles):
            trace.visible = 'legendonly'

    graf_media_evol_mes.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))

    # Rotos los ejes para que no se sincronicen todos (sol un mes en cada facet col)
    graf_media_evol_mes.update_xaxes(matches=None)
    graf_media_evol_mes.update_xaxes(
        #tickformat='%d-%b',
        tickformat='%d', 
        hoverformat="%d %B",                  # Forza formato uniforme
        showgrid=True
    )

    graf_media_evol_mes.update_layout(
        xaxis = dict(
            #tickformat = '%d-%b',
            tickformat = '%d',
            #tick0='2020-01-01',       # Primer tick el 1-Ene
            dtick='D1',               # Un tick por mes
            showgrid=True,            # Asegura grid visible
            matches = None 
            ),
        hovermode='x unified',
        legend=dict(
            orientation="h",        # horizontal
            yanchor="bottom",
            y=1.02,                 # un poco por encima del gráfico
            xanchor="center",
            x=0.5,                  # centrada horizontalmente
            title_text=None         # sin cabecera
        )
    )

    #graf_media_evol_mes.update_traces(
    #    hovertemplate = '%{customdata[0]}<br>Año: %{customdata[1]} Mes: %{customdata[2]} Día: %{x}<br>Evol media diaria(GWh): %{y:.2f}<extra></extra>',
    #)
    graf_media_evol_mes.update_traces(
        hovertemplate=(
            "Año %{fullData.name}: %{y:.2f} GW"
            "<extra></extra>"
        )
    )

    return graf_media_evol_mes 

def actualizar_historicos(datos_mensual):
    historicos=pd.read_csv('local_bbdd/demanda_mensual.csv',sep=';')
    update_historicos = pd.concat([historicos, datos_mensual], ignore_index=True)
    update_historicos = update_historicos.drop_duplicates(subset = ['año', 'mes'], keep = 'last')
    update_historicos = update_historicos.reset_index(drop = True)
    datos_mensual = update_historicos
    datos_mensual.to_csv('local_bbdd/demanda_mensual.csv', sep=";", index=False)
    # Añadimos columna de acumulados
    datos_mensual['acumulado_real_GWh'] = datos_mensual.groupby('año')['demanda_real_GWh'].cumsum()
    datos_mensual['media_real_GWh'] = datos_mensual.groupby('año')['demanda_real_GWh'].expanding().mean().reset_index(level=0, drop=True)

    print('datos_mensual')
    print(datos_mensual)
    # Obtenems    
    años_registro = datos_mensual['año'].unique()
    #demanda_prevista_acumulada = datos_mensual['acumulado_real_GWh'].iloc[-1]
    #demanda_prevista_media = datos_mensual['media_real_GWh'].iloc[-1]
    return datos_mensual, años_registro #, demanda_prevista_acumulada, demanda_prevista_media



#GRÁFICO CON LA EVOLUCIÓN MENSUAL DE LA DEMANDA---------------------------------------------------------------------------------

def graf_2(datos_mensual, mes_previsto_nombre, demanda_prevista, años_visibles):
    if datos_mensual is None or datos_mensual.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    if st.session_state.añadir_autoconsumo:
        titulo = 'Demanda mensual: REAL + AUTOCONSUMO'
    else:
        titulo = 'Demanda mensual: REAL'

    #gráfico de líneas de partida
    graf_2 = px.line(datos_mensual, x = 'mes_nombre', y = 'demanda_GWh', color = 'año', labels = {'demanda_GWh':'Demanda GWh','mes_nombre':'mes'}, title= titulo)
    #hacemos gruesa la del 2025
    #mostramos inicialmente estos años
    #años_visibles = ['2024', '2025', '2026']
    for trace in graf_2.data:
        if trace.name == '2026':
            trace.update(line=dict(width=5))
        if trace.name not in años_visibles:
            trace.visible = 'legendonly'
    #centramos texto y añadimos grid
    graf_2.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=1.02,  # Colocarla ligeramente por encima del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
            title_text=''
        )
    )
    #añadimos circulito para remarcar la previsión del mes en curso
    graf_2.add_scatter(x=[mes_previsto_nombre],y=[demanda_prevista], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color='yellow')),
        name='Demanda prevista',
        text='Demanda prevista'
    )
    return graf_2
    

#GRÁFICO CON LA EVOLUCIÓN MENSUAL ACUMULADA DE LA DEMANDA----------------------------------------------------------------------------------------------
def graf_2b(datos, mes_previsto_nombre, demanda_prevista_acumulada, años_visibles):
    if datos is None or datos.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    if st.session_state.añadir_autoconsumo:
        titulo = 'Demanda mensual acumulada: REAL + AUTOCONSUMO'
    else:
        titulo = 'Demanda mensual acumulada: REAL'

    #gráfico de líneas de partida
    graf_2b = px.line(datos, x = 'mes_nombre', y = 'acumulado_GWh', color = 'año', labels = {'acumulado_GWh':'Demanda acumulada GWh','mes_nombre':'mes'}, title = titulo)
    #hacemos gruesa la del 2025
    #mostramos inicialmente estos años
    #años_visibles = ['2018', '2024', '2025']
    for trace in graf_2b.data:
        if trace.name == '2026':
            trace.update(line=dict(width=5))
        if trace.name not in años_visibles:
            trace.visible = 'legendonly'
    #centramos texto y añadimos grid
    graf_2b.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=1.02,  # Colocarla ligeramente por encima del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
            title_text=''
        )
    )
    #añadimos circulito para remarcar la previsión del mes en curso
    graf_2b.add_scatter(x=[mes_previsto_nombre],y=[demanda_prevista_acumulada], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color='yellow')),
        name='Demanda simulada',
        text='Demanda simulada'
    )
    return graf_2b
    

#GRÁFICO CON LA EVOLUCIÓN MENSUAL ACUMULADA DE LA DEMANDA----------------------------------------------------------------------------------------------
def graf_2c(datos, mes_previsto_nombre, demanda_prevista_media, años_visibles):
    if datos is None or datos.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    if st.session_state.añadir_autoconsumo:
        titulo = 'Demanda mensual media: REAL + AUTOCONSUMO'
    else:
        titulo = 'Demanda mensual media: REAL'

    #gráfico de líneas de partida
    graf_2c = px.line(datos, x = 'mes_nombre', y = 'media_GWh', color = 'año', labels = {'media_GWh':'Demanda media GWh','mes_nombre':'mes'}, title = titulo)
    #hacemos gruesa la del 2025
    #mostramos inicialmente estos años
    #años_visibles = ['2018', '2024', '2025']
    for trace in graf_2c.data:
        if trace.name == '2026':
            trace.update(line=dict(width=5))
        if trace.name not in años_visibles:
            trace.visible = 'legendonly'
    #centramos texto y añadimos grid
    graf_2c.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=1.02,  # Colocarla ligeramente por encima del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
            title_text=''
        )
    )
    #añadimos circulito para remarcar la previsión del mes en curso
    graf_2c.add_scatter(x=[mes_previsto_nombre],y=[demanda_prevista_media], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color='yellow')),
        name='Demanda simulada',
        text='Demanda simulada'
    )
    return graf_2c

# Obtenemos dataframe de demanda agrupada por años (gráfica 3)
def calcular_datos_anual(datos_mensual, año_anterior): #, mes_previsto):
    #usado para combinar con autoconsumo para gráfico de áreas
    datos_anual_real = datos_mensual.copy()
    datos_anual_real = datos_anual_real[['año', 'demanda_real_GWh']]
    datos_anual_real = datos_anual_real[datos_anual_real['año'] <= año_anterior]
    datos_anual_real = datos_anual_real.groupby('año', as_index = False).sum()
    datos_anual_real['demanda_real_GWh'] = datos_anual_real['demanda_real_GWh'] / 1000
    datos_anual_real = datos_anual_real.rename(columns={'demanda_real_GWh':'demanda_real_TWh'})
    
    datos_anual_total = datos_mensual.copy()
    datos_anual_total = datos_anual_total[['año', 'demanda_GWh']]
    datos_anual_total = datos_anual_total[datos_anual_total['año'] <= año_anterior]
    datos_anual_total = datos_anual_total.groupby('año', as_index = False).sum()
    datos_anual_total['demanda_GWh'] = datos_anual_total['demanda_GWh'] / 1000
    datos_anual_total = datos_anual_total.rename(columns={'demanda_GWh':'demanda_total_TWh'})


    #datos_anual_mes_curso = datos_mensual.copy()
    #datos_anual_mes_curso = datos_anual_mes_curso[datos_anual_mes_curso['mes'] <= mes_previsto]
    #datos_anual_mes_curso = datos_anual_mes_curso.groupby('año', as_index = False).sum()
    
    
    return datos_anual_real, datos_anual_total #,  datos_anual_mes_curso

# GRÁFICO DE AREAS PARA VISUALIZAR EL TOTAL DE LA DEMANDA REAL POR AÑOS
def graf_3(datos_anual):
    if datos_anual is None or datos_anual.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    graf_3 = px.area(datos_anual, x = 'año', y = 'demanda_real_TWh', labels = {'demanda_real_TWh' : 'Demanda Real TWh'}, title = 'Evolución de la Demanda anual: REAL')
    
    valor_minimo=datos_anual['demanda_real_TWh'].min()
    valor_maximo=datos_anual['demanda_real_TWh'].max()
    graf_3.update_layout(
        title={'x':.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            #gridcolor='LightGray',  # Color de las líneas de cuadrícula
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        yaxis=dict(
            range=[valor_minimo-5,valor_maximo+5]
        )
    )


    return graf_3

def graf_3bis(datos_anual):
    if datos_anual is None or datos_anual.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    graf_3bis=px.area(
        datos_anual, 
        x = 'año', y = 'valor', 
        labels = {'valor' : 'Demanda TWh'},
        title = 'Evolución de la Demanda anual: REAL + AUTOCONSUMO',
        color = 'serie',
        color_discrete_map = {'autogen':'orange', 'demanda_real_TWh':"#83c9ff"}, #azul 40 por defecto streamlit
        category_orders = {'serie': ['demanda_real_TWh', 'autogen']}
    )
    
    valor_minimo=datos_anual.loc[datos_anual['serie'] == 'demanda_real_TWh', 'valor'].min()
    valor_maximo=datos_anual.loc[datos_anual['serie'] == 'demanda_real_TWh', 'valor'].max()
    
    graf_3bis.update_layout(
        title={'x':.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            #gridcolor='LightGray',  # Color de las líneas de cuadrícula
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        yaxis=dict(
            range=[valor_minimo-5,valor_maximo+5]
        ),
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=1.0,  # Colocarla ligeramente por debajo del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
            title_text=''
        )
    )


    return graf_3bis


def graf_3bisbis(datos_anual):
    if datos_anual is None or datos_anual.empty:
        raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
    
    graf_3bis=px.area(
        datos_anual, x='año', y='valor', 
        labels={'valor':'Demanda TWh'},
        title='Demanda anual acumulada + PRODUCCION DE AUTOCONSUMO hasta el mes en curso',
        color='serie',
        color_discrete_map={'autogen':'orange','demanda_TWh':"#83c9ff"}, #azul 40 por defecto streamlit
        category_orders={'serie': ['demanda_TWh','autogen']}
    )
    
    valor_minimo=datos_anual.loc[datos_anual['serie']=='demanda_TWh','valor'].min()
    valor_maximo=datos_anual.loc[datos_anual['serie']=='demanda_TWh','valor'].max()
    
    graf_3bis.update_layout(
        title={'x':.5,'xanchor':'center'},
        xaxis=dict(
            showgrid=True,  # Mostrar la cuadrícula horizontal
            #gridcolor='LightGray',  # Color de las líneas de cuadrícula
            gridwidth=1,     # Ancho de las líneas de cuadrícula
            tickmode='linear'
        ),
        yaxis=dict(
            range=[valor_minimo-5,valor_maximo+5]
        ),
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=1.0,  # Colocarla ligeramente por debajo del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
            title_text=''
        )
    )


    return graf_3bis

def diferencias_mes(datos_mensual_tabla, datos_mensual_tabla_mostrar, año_actual):
    #buscamos la demanda mensual GWh del año y mes seleccionados.
    año_seleccionado_2_int = int(st.session_state.año_seleccionado_2)
    año_seleccionado_2_int = int(año_actual)
    año_seleccionado_2_int = int(st.session_state.año_seleccionado_pormeses)
    #demanda_mensual_seleccionada=datos_mensual.loc[(datos_mensual['año']==año_actual_int) & (datos_mensual['mes_nombre']==mes_seleccionado_nombre), 'demanda_GWh'].values[0]
    #demanda_mensual_seleccionada=datos_mensual_tabla.loc[datos_mensual_tabla['año']==año_actual,mes_seleccionado_nombre].values[0]
    demanda_mensual_seleccionada_2 = datos_mensual_tabla.loc[año_seleccionado_2_int, st.session_state.mes_seleccionado_nombre_pormeses]
    
    print('demanda_mensual_seleccionada_2')
    print(demanda_mensual_seleccionada_2)

    demanda_mensual_seleccionada_2 = round(demanda_mensual_seleccionada_2)

    #generamos tabla con las diferencias en valores absolutos
    diferencias_meses  = datos_mensual_tabla_mostrar.data - demanda_mensual_seleccionada_2
    diferencias_mes = diferencias_meses[st.session_state.mes_seleccionado_nombre_pormeses]*(-1)
    df_diferencias_mes = diferencias_mes.to_frame()
    diferencias_mes_mostrar = df_diferencias_mes.style.background_gradient(axis=None)

    #generamos tabla con las diferencias en porcentajes
    diferencias_mes_porc = df_diferencias_mes[st.session_state.mes_seleccionado_nombre_pormeses]/datos_mensual_tabla[st.session_state.mes_seleccionado_nombre_pormeses]*100
    #diferencias_mes_porc=df_diferencias_mes[mes_previsto_nombre]/datos_mensual_tabla[mes_previsto_nombre]*100
    df_diferencias_mes_porc = diferencias_mes_porc.to_frame()
    df_diferencias_mes_porc = df_diferencias_mes_porc.rename(columns={st.session_state.mes_seleccionado_nombre_pormeses:'%'})
    #df_diferencias_mes_porc=df_diferencias_mes_porc.rename(columns={mes_previsto_nombre:'%'})

    #generamos tabla con ambas diferencias
    df_diferencias_mes_completo=pd.concat([df_diferencias_mes,df_diferencias_mes_porc],axis=1)
    df_diferencias_mes_completo=df_diferencias_mes_completo.iloc[:-1]
    df_diferencias_mes_completo=df_diferencias_mes_completo.rename(columns={st.session_state.mes_seleccionado_nombre_pormeses:'Dif. GWh'})
    #df_diferencias_mes_completo=df_diferencias_mes_completo.rename(columns={mes_previsto_nombre:'Dif. GWh'})
    df_diferencias_mes_completo['%']=df_diferencias_mes_completo['%'].round(2)

    print ('diferencias mes completo')
    print (df_diferencias_mes_completo)
    def format_value(val):
        if pd.isna(val):  # Maneja valores NaN
            return ''
        return f'+{val}' if val > 0 else f'{val}'
    diferencias_mes_completo_mostrar = df_diferencias_mes_completo.style.background_gradient(cmap='RdYlGn',axis=0)
    diferencias_mes_completo_mostrar = diferencias_mes_completo_mostrar.format(formatter=format_value)

    df_diferencias_mes_completo_graf=df_diferencias_mes_completo.reset_index()
    return df_diferencias_mes_completo_graf, diferencias_mes_completo_mostrar


def graf_diferencias(df_diferencias_mes_completo_graf, año_actual):
    graf_diferencias = px.bar(
        df_diferencias_mes_completo_graf,
        x = 'año', y = 'Dif. GWh',
        #height=300,
        color = 'Dif. GWh',
        color_continuous_scale = 'RdYlGn'
    )
    graf_diferencias.update_layout(
        xaxis = dict(
            tickmode='linear'
            ),
        title = {'text' : f'Diferencia con {st.session_state.mes_seleccionado_nombre_pormeses} {st.session_state.año_seleccionado_pormeses} (GWh)', 'x' : 0.5, 'xanchor' : 'center'},
        legend = dict(
            orientation="h",  # Leyenda en horizontal
            x=0.5,  # Posición horizontal centrada
            xanchor="center",  # Alineación horizontal centrada
            y=1,  # Colocarla ligeramente por encima del gráfico
            yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
        )
    )
    return graf_diferencias


def ranking_mensual(datos_mensual_tabla, año_actual):

    datos_mensual_tabla_graf=datos_mensual_tabla
    datos_mensual_mes_encurso=datos_mensual_tabla_graf[st.session_state.mes_seleccionado_nombre_pormeses]
    datos_mensual_mes_encurso=datos_mensual_mes_encurso.to_frame(name='demanda')
    datos_mensual_mes_encurso=datos_mensual_mes_encurso.reset_index()
    datos_mensual_mes_encurso_ordenado=datos_mensual_mes_encurso.sort_values(by='demanda', ascending=False)
    datos_mensual_mes_encurso_ordenado['año']=datos_mensual_mes_encurso_ordenado['año'].astype(str)
    datos_mensual_mes_encurso_ordenado['color']='blue'
    datos_mensual_mes_encurso_ordenado.loc[datos_mensual_mes_encurso_ordenado['año'] == str(año_actual), 'color']='darkred'
    datos_mensual_mes_encurso_ordenado=datos_mensual_mes_encurso_ordenado.reset_index(drop=True)
    return datos_mensual_mes_encurso_ordenado

def graf_ranking_mes(datos_mensual_mes_encurso_ordenado):
    graf_ranking_mes = px.bar(
        datos_mensual_mes_encurso_ordenado,
        x = datos_mensual_mes_encurso_ordenado.index,
        y = 'demanda',
        color = 'color',
        color_discrete_map = {'blue': '#ADD8E6', 'darkred': 'darkred'},
    )

    min = datos_mensual_mes_encurso_ordenado['demanda'].min()
    max = datos_mensual_mes_encurso_ordenado['demanda'].max()
    
    graf_ranking_mes.update_layout(
        #title = {'text' : f'Ranking de {st.session_state.mes_seleccionado_nombre}s', 'x' : 0.5, 'xanchor' : 'center'},
        legend = dict(
            orientation ='h',  # Leyenda en horizontal
            x = 0.5,  # Posición horizontal centrada
            xanchor = 'center',  # Alineación horizontal centrada
            y = 1,  # Colocarla ligeramente por encima del gráfico
            yanchor = 'top',  # Alineación vertical en la parte inferior de la leyenda
            ),
        yaxis = dict(
            title = 'Demanda GWh',
            range = [min - 1000, max + 1000]
        ),
        showlegend = False
    )

    graf_ranking_mes.update_xaxes(
        ticktext = datos_mensual_mes_encurso_ordenado['año'],
        tickvals = list(range(len(datos_mensual_mes_encurso_ordenado['año']))),
        title = 'Años'
    )
    return graf_ranking_mes





# NO SE GASTA------------------------------------------------------------------------!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

@st.cache_data    
def download_esios_id_hour(id,fecha_ini,fecha_fin,agrupacion,tipo_agregacion,horas_transcurridas):
        
        cab = dict()
        cab ['x-api-key']=st.secrets['ESIOS_API_KEY']
        url_id = 'https://api.esios.ree.es/indicators'
        url=f'{url_id}/{id}?&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}&time_agg={tipo_agregacion}'
        print(url)
        datos_origen = requests.get(url, headers=cab).json()
        fecha_descarga=datetime.now()
        datos=pd.DataFrame(datos_origen['indicator']['values'])
        datos = (datos
         .assign(datetime=lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
                      .to_datetime(vh_['datetime'],utc=True)  # con la fecha local
                      .dt
                      .tz_convert('Europe/Madrid')
                      .dt
                      .tz_localize(None)
                ) 
             #.drop(['datetime','datetime_utc','tz_time','geo_id','geo_name'],
             #      axis=1) #eliminamos campos
             
             .loc[:,['datetime','value']]
             )
        
        
        #añadimos columnas año y mes
        datos['año']=datos['datetime'].dt.year
        datos['mes']=datos['datetime'].dt.month
        #formateo de año
        datos['año']=datos['año'].astype(int) # str.replace(',','')
        #eliminamos datetime
        datos=datos.drop(columns=['datetime'])
        
        #añadimos la columna mes_nombre
        meses = {
            1: 'Enero',
            2: 'Febrero',
            3: 'Marzo',
            4: 'Abril',
            5: 'Mayo',
            6: 'Junio',
            7: 'Julio',
            8: 'Agosto',
            9: 'Septiembre',
            10: 'Octubre',
            11: 'Noviembre',
            12: 'Diciembre'
        }
        datos['mes_nombre']=datos['mes'].map(meses)
        meses_seleccion=datos['mes_nombre'].unique()

        
        
        ##añadimos una columna con las horas de cada mes
        #calculamos las horas según el mes
        dias_por_mes = {
            1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
            7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
            }
        def calcular_horas(row):
            mes = row['mes']
            dias = dias_por_mes[mes]
            return dias*24
        datos['horas_mes'] = datos.apply(calcular_horas, axis=1)
        
        #pasamos value a GWh
        datos['value']=datos['value']/1000
        #calculamos demanda mensual en GWh
        datos['demanda']=datos['value']*datos['horas_mes']
        #renombramos
        datos=datos.rename(columns={'demanda':'demanda_GWh'})
        datos=datos.rename(columns={'value':'demanda_media_MW'})
        datos_mensual=datos
        

        #obtenemos variables a usar en web
        demanda_prevista=datos['demanda_GWh'].iloc[-1] #es la demanda prevista a visualizar en app
        mes_previsto=datos['mes'].iloc[-1]
        mes_previsto_nombre=datos['mes_nombre'].iloc[-1] #es el mes (nombre) del cual hacemos la prevision. mes actual
        media_real=datos['demanda_media_MW'].iloc[-1]
        #calculamos demanda del mes en curso
        demanda_real=media_real*horas_transcurridas
       

        return fecha_descarga, datos_mensual, demanda_prevista, mes_previsto, demanda_real, mes_previsto_nombre, meses_seleccion
     



# Obtenemos el último registro de esios. NO USADO
@st.cache_data
def download_esios_id_5m(id, fecha_ini, fecha_fin, agrupacion):
    
    token = st.secrets['ESIOS_API_KEY']
    cab = {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key' : token
    }

    url_id = 'https://api.esios.ree.es/indicators'
    url=f'{url_id}/{id}?&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}'
    print(url)
    response = requests.get(url, headers = cab)
    print(response)
    datos_origen = response.json()
    
    datos=pd.DataFrame(datos_origen['indicator']['values'])
    datos = (datos
        .assign(datetime=lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
            .to_datetime(vh_['datetime'],utc=True)  # con la fecha local
            .dt
            .tz_convert('Europe/Madrid')
            .dt
            .tz_localize(None)
            ) 
        .loc[:,['datetime','value']]
        )
    #datos['fecha']=datos['datetime'].dt.date
    #datos['hora']=datos['datetime'].dt.hour
    #datos['dia']=datos['datetime'].dt.day
    #datos['mes']=datos['datetime'].dt.month
    #datos['año']=datos['datetime'].dt.year
    
    ultimo_registro = datos['datetime'].max()
        
    return datos, ultimo_registro #, horas_transcurridas

#NO USADO
def graf_1(datos):
    if datos is None or datos.empty:
        #raise ValueError("Datos no disponibles o vacíos. Asegúrate de ejecutar download_esios_id primero.")
        error = 'Datos no disponibles.'
        return error
    else:
        graf_1=px.line(datos, x='datetime', y='value', labels={'value':'Demanda MW','datetime':'hora'}, title="Demanda real PENÍNSULA hoy (granulado = 5 minutos)")
        graf_1.update_layout(title={'x':0.5,'xanchor':'center'})
    
        return graf_1
        
    

@st.cache_data #(ttl=300)        NO USADO!!!!
def download_esios_id_month(id, fecha_ini, fecha_fin, agrupacion, tipo_agregacion, ultimo_registro):
        
    token = st.secrets['ESIOS_API_KEY']
    cab = {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key' : token
    }
    url_id = 'https://api.esios.ree.es/indicators'
    url=f'{url_id}/{id}?&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}&time_agg={tipo_agregacion}'
    print(url)
    #datos_origen = requests.get(url, headers=cab).json()
    response = requests.get(url, headers=cab)
    print(response)
    datos_origen = response.json()
    
    datos=pd.DataFrame(datos_origen['indicator']['values'])
    datos = (datos
        .assign(datetime=lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
            .to_datetime(vh_['datetime'],utc=True)  # con la fecha local
            .dt
            .tz_convert('Europe/Madrid')
            .dt
            .tz_localize(None)
                ) 
        .loc[:,['datetime','value']]
        )
    
    
    #añadimos columnas año y mes
    datos['año'] = datos['datetime'].dt.year
    datos['mes'] = datos['datetime'].dt.month
    #formateo de año
    datos['año'] = datos['año'].astype(int)

    
    #calculo de las horas transcurridas del mes en curso
    #lo usaremos para calcular la demanda del mes en curso en GWh a partir de la media de la demanda real en MW obtenida del id1293
    
    
    if ultimo_registro !=None:
        fecha_hora_objetivo = pd.Timestamp(ultimo_registro)
        inicio_mes = pd.Timestamp(year=fecha_hora_objetivo.year, month=fecha_hora_objetivo.month, day=1, hour=0, minute=0, second=0)
        diferencia = fecha_hora_objetivo - inicio_mes
        horas_transcurridas = diferencia.total_seconds() / 3600
    else:
        horas_transcurridas = 0
    #eliminamos datetime
    datos=datos.drop(columns=['datetime'])
    
    #añadimos la columna mes_nombre
    meses = {
        1: 'Enero',
        2: 'Febrero',
        3: 'Marzo',
        4: 'Abril',
        5: 'Mayo',
        6: 'Junio',
        7: 'Julio',
        8: 'Agosto',
        9: 'Septiembre',
        10: 'Octubre',
        11: 'Noviembre',
        12: 'Diciembre'
    }
    datos['mes_nombre']=datos['mes'].map(meses)
    meses_seleccion=datos['mes_nombre'].unique()
            
    
    ##añadimos una columna con las horas de cada mes
    #calculamos las horas según el mes
    dias_por_mes = {
        1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
        7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
        }
    def calcular_horas(row):
        mes = row['mes']
        dias = dias_por_mes[mes]
        return dias*24
    datos['horas_mes'] = datos.apply(calcular_horas, axis=1)
    
    #pasamos value a GWh
    datos['value']=datos['value']/1000
    #calculamos demanda mensual en GWh
    datos['demanda']=datos['value']*datos['horas_mes']
    #renombramos
    datos = datos.rename(columns={'demanda':'demanda_real_GWh'})
    datos = datos.rename(columns={'value':'demanda_media_GW'})
    
    num_mes_previsto = datos['mes'].iloc[-1]
    mes_previsto_nombre = datos['mes_nombre'].iloc[-1] #es el mes (nombre) del cual hacemos la prevision. mes actual
    media_real = datos['demanda_media_GW'].iloc[-1]
    #print(media_real)
    #calculamos demanda del mes en curso
    demanda_real = media_real * horas_transcurridas
    
    return datos, num_mes_previsto, demanda_real, mes_previsto_nombre, meses_seleccion, media_real