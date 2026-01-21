import pandas as pd
import plotly.express as px
import plotly.graph_objects as go 
import streamlit as st

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import io
from googleapiclient.http import MediaIoBaseDownload
import json
import numpy as np



meses_español = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
    7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"
    }
meses_completos = pd.DataFrame({
        'mes': range(1, 13),
        'mes_nombre': [meses_español[m] for m in range(1, 13)]
    })

from backend_comun import rango_componentes

def get_limites_componentes():
    datos_limites = rango_componentes()
    df_limites = pd.DataFrame(datos_limites)
    etiquetas = df_limites['valor_asignado'][:-1]
    valor_asignado_a_rango = {
        row['valor_asignado']: row['rango'] for _, row in df_limites.iterrows()
    }
    return df_limites, etiquetas, valor_asignado_a_rango


colores = {
        'muy bajo': '#90EE90',  # Verde claro (fácil y suave a la vista)
        'bajo': '#2E8B57',  # Verde oscuro (tono natural)
        'medio': '#4682B4',  # Azul acero (transición a tonos fríos)
        'alto': '#1E3A5F',  # Azul profundo (sólido pero no agresivo)
        'muy alto': '#804674',  # Morado rosado (punto de transición)
        'chungo': '#B04E5A',  # Naranja oscuro (advertencia sin ser agresivo)
        'xtrem': '#A31E1E',  # Rojo anaranjado (peligro intermedio)
        'defcon3': 'darkred',  # Rojo fuerte (nivel crítico)
        'defcon2': '#800000',  # Rojo oscuro intenso (máximo riesgo)
    #    'Desconocido': 'gray'  # Neutralidad
    }




@st.cache_data
def leer_json(file_id, _creds_dict):
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    creds = Credentials.from_service_account_info(_creds_dict, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    datos_json = json.load(buffer)
    
    # Convertir a DataFrame
    datos = pd.DataFrame(datos_json)
    datos['datetime'] = pd.to_datetime(datos['datetime'], utc=True)
    datos['datetime'] = datos['datetime'].dt.tz_convert('Europe/Madrid').dt.tz_localize(None)
    
    if 'id' in datos.columns and 'name' in datos.columns:
        # Datos de SSAA
        datos = datos[['datetime', 'id', 'value', 'name']]
        datos = datos.groupby('datetime', as_index=False)['value'].sum()
    else:
        # Datos tipo spot
        datos = datos[['datetime', 'value']]
        
    datos['fecha']=datos['datetime'].dt.date
    datos['hora']=datos['datetime'].dt.hour
    datos['dia']=datos['datetime'].dt.day
    datos['mes']=datos['datetime'].dt.month
    datos['año']=datos['datetime'].dt.year
    datos.set_index('datetime', inplace=True)

    fecha_ini = datos['fecha'].min()
    fecha_fin = datos['fecha'].max()
    
    return datos, fecha_ini, fecha_fin

#gráfico con todos los valores diarios desde el 2018
def diarios_totales(datos, fecha_ini, fecha_fin):    
    datos_dia = datos.copy()
    datos_dia = datos_dia.drop(columns=['hora'])
    datos_dia['mes_nombre']=datos_dia['mes'].map(meses_español)

    #print('datos dia de datos diarios totales')
    #print(datos_dia)

    

    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)
    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_dia=datos_dia.groupby('fecha').agg({
            'value_spot':'mean',
            'value_ssaa':'mean',
            'dia':'first',
            'mes':'first',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()
        datos_dia = datos_dia.melt(id_vars=['fecha', 'año', 'mes', 'mes_nombre', 'dia'], var_name='componente', value_name='value')
        # 1. Agrupamos para recomponer la suma por fecha
        valor_total_diario = datos_dia.groupby(['fecha', 'año'])['value'].sum().reset_index(name='value_total')

        # 2. Calculamos la media anual de esa suma
        media_anual = valor_total_diario.groupby('año')['value_total'].mean()

        # 3. Asociamos esa media anual a cada año original en datos_dia
        datos_dia['media_anual'] = datos_dia['año'].map(media_anual)


    
    else:
        datos_dia=datos_dia.groupby('fecha').agg({
            'value':'mean',
            'dia':'first',
            'mes':'first',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()

        media_anual = datos_dia.groupby('año')['value'].mean()
        datos_dia['media_anual'] = datos_dia['año'].map(media_anual)

    
    
    datos_dia['value'] = datos_dia['value'].round(2)
    datos_dia[['dia','mes','año']] = datos_dia[['dia','mes','año']].astype(int)
    
    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_dia['escala']=pd.cut(datos_dia['value'],bins=df_limites['rango'],labels=etiquetas,right=False)
    datos_dia['color']=datos_dia['escala'].map(colores)
    escala_dia=datos_dia['escala'].unique()
    escala_ordenada_dia = sorted(escala_dia, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_dia['escala']=pd.Categorical(datos_dia['escala'],categories=escala_ordenada_dia, ordered=True)

    

    print('datos diarios de todos los años')
    print(datos_dia)

    #GRÁFICO PRINCIPAL CON LOS PRECIOS MEDIOS DIARIOS DE TODOS LOS AÑOS. ecv es escala cavero vidal-----------------------------------------------------------
    #componente = st.session_state.get('componente', 'SPOT')
    
    if componente in ['SPOT']:
        title = f'Precios medios diarios del SPOT. 2018-2025'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Precios medios diarios del SPOT+SSAA. 2018-2025'
        tick_y = 20
    else:
        title = f'Precios medios diarios de los SSAA. 2018-2025'
        tick_y = 4

    if componente == 'SPOT+SSAA' and dos_colores:
        graf_ecv_diario = px.bar(datos_dia, x='fecha', y='value', 
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #category_orders = {'escala':escala_ordenada_dia},
            labels = {'fecha':'fecha','value':'precio medio diario €/MWh'}, #, 'escala':'escala_cv'},
            #title = f'Precios del mercado diario OMIE. 2018-2025',
            title=title,
            #hover_name = 'escala'
        )
    else:
        graf_ecv_diario = px.bar(datos_dia, x='fecha', y='value', 
            color = 'escala',
            color_discrete_map = colores,
            category_orders = {'escala':escala_ordenada_dia},
            labels = {'fecha':'fecha','value':'€/MWh', 'escala':'escala_cv'},
            #title = f'Precios del mercado diario OMIE. 2018-2025',
            title=title,
            hover_name = 'escala'
        )

    # añadimos gráficos de línea para la medias anuales
    for año in datos_dia['año'].unique():
        datos_año = datos_dia[datos_dia['año'] == año]
        fecha_inicio = datos_año['fecha'].min()
        fecha_final = datos_año['fecha'].max()
        media_valor = datos_año['media_anual'].iloc[0]
        graf_ecv_diario.add_trace(
            go.Scatter(
                x=[fecha_inicio, fecha_final],
                y=[media_valor, media_valor],
                mode = 'lines',
                name = 'media anual',
                line = dict(color = 'yellow', dash = 'dot'),
                showlegend = bool(año == datos_dia['año'].unique()[0])
            )
        )

    graf_ecv_diario.update_xaxes(
        tickformat = "%Y",  # Mostrar sólo el mes abreviado (Ej: Jan, Feb)
        tickvals = pd.date_range(
            start = datos_dia['fecha'].min(),
            #end=datos_dia['fecha'].max(),
            end = fecha_fin,
            freq = 'YS'  # Generar ticks al inicio de cada AÑO
        ),
        showgrid=True,
    )

    graf_ecv_diario.update_traces(
        marker_line_width = 0,
        #customdata = datos_dia['escala'],
        hovertemplate = (
            #"<b>Escala:</b> %{customdata}<br>"
            "<b>Fecha:</b> %{x|%d-%m-%Y}<br>"  # Formato DD-MM-YYYY
            "<b>Precio:</b> %{y:.2f} €/MWh<br>"
        )
    )

    ymax = datos_dia['value'].max()

    
    graf_ecv_diario.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis=dict(
            range = [fecha_ini, fecha_fin],
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)'
            ),  
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="Último año", step="year", stepmode="backward"),
                    dict(label="Año anterior", step="year", stepmode="todate"),
                    dict(step="all", label='Todo')  # Visualizar todos los datos
                ]),
            ),
        ),
        yaxis=dict(
            #range=[0, 200],             # Forzar el rango del eje Y
            tickmode="linear",            # Escala lineal
            tick0=0,                      # Comenzar en 0
            dtick=tick_y,
            rangemode="tozero",                      
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="right",
                x=1,
                y=1.15,
                xanchor="right",
                yanchor="top",
                bgcolor="rgba(0,0,0,0)",
                bordercolor="rgba(0,0,0,0)",
                showactive=False,
                buttons=[
                    dict(
                        label="🔓 Escala automática",
                        method="relayout",
                        args=[{"yaxis.autorange": True}]
                    ),
                    dict(
                        label="🔒 Fijar [0, 200]",
                        method="relayout",
                        args=[{"yaxis.range": [0, 200]}]
                    )
                ],
                
            )
        ]

    )
    
    
    

    return datos_dia, graf_ecv_diario




# VALORES MEDIOS DIARIOS DEL AÑO SELECCIONADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#def diarios(datos, fecha_ini, fecha_fin): 
def diarios(datos, fecha_ini, fecha_fin, datos_comparar):       
    datos_dia = datos.copy()
    datos_dia = datos_dia.drop(columns=['hora'])
    datos_dia['mes_nombre']=datos_dia['mes'].map(meses_español)

    

    print('datos_dia')
    print(datos_dia)

    
    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)
    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_dia=datos_dia.groupby('fecha').agg({
            'value_spot':'mean',
            'value_ssaa':'mean',
            'dia':'first',
            'mes':'first',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()
        datos_dia = datos_dia.melt(id_vars=['fecha', 'año', 'mes', 'mes_nombre', 'dia'], var_name='componente', value_name='value')
        datos_dia['media'] = datos_dia.groupby('componente')['value'].expanding().mean().reset_index(level=0, drop=True)
        
    
    else:
        datos_dia=datos_dia.groupby('fecha').agg({
            'value':'mean',
            'dia':'first',
            'mes':'first',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()   

        datos_dia['media'] = datos_dia['value'].expanding().mean()
        datos_dia['media_movil'] = datos_dia['value'].rolling(window=14, min_periods=1).mean()
        
    

    datos_dia['value'] = datos_dia['value'].round(2)
    datos_dia[['dia','mes','año']] = datos_dia[['dia','mes','año']].astype(int)
    

    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_dia['escala']=pd.cut(datos_dia['value'],bins=df_limites['rango'],labels=etiquetas,right=False)
    datos_dia['color']=datos_dia['escala'].map(colores)
    escala_dia=datos_dia['escala'].unique()

   

    escala_ordenada_dia = sorted(escala_dia, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_dia['escala']=pd.Categorical(datos_dia['escala'],categories=escala_ordenada_dia, ordered=True)
    
    #datos_dia['media'] = datos_dia['value'].expanding().mean()
    #datos_dia.reset_index(inplace=True)

    datos_comp = datos_comparar.copy()
    datos_comp['fecha'] = pd.to_datetime(
        datos_comp['fecha'],
        errors='coerce'
    )
    datos_comp['media'] = datos_comp['value'].expanding().mean()
    # extraemos mes y día del año comparado
    datos_comp['mes'] = datos_comp['fecha'].dt.month
    datos_comp['dia'] = datos_comp['fecha'].dt.day

    print('datos a comparar')
    print(datos_comp)

    # reconstruimos la fecha usando el AÑO SELECCIONADO
    año_base = st.session_state.año_seleccionado_esc

    datos_comp['fecha_alineada'] = pd.to_datetime(
        dict(
            year=año_base,
            month=datos_comp['mes'],
            day=datos_comp['dia']
        ),
        errors='coerce'
    )

    # eliminamos 29 de febrero si no existe en el año base
    datos_comp = datos_comp.dropna(subset=['fecha_alineada'])



    #GRÁFICO PRINCIPAL CON LOS PRECIOS MEDIOS DIARIOS DEL AÑO. ecv es escala cavero vidal------------------
    componente = st.session_state.get('componente', 'SPOT')
    if componente in ['SPOT']:
        title = f'Precios medios diarios del SPOT. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Precios medios diarios del SPOT+SSAA. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    else:
        title = f'Precios medios diarios de los SSAA. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 4

    if componente in ['SPOT+SSAA'] and dos_colores:
        graf_ecv_diario = px.bar(datos_dia, x='fecha', y='value', 
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #category_orders = {'escala':escala_ordenada_dia},
            labels = {'fecha':'fecha','value':'€/MWh'}, #, 'escala':'escala_cv'},
            #title = f'Precios medios del mercado diario OMIE. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            #hover_name = 'escala'
        )
        for comp in ['value_spot', 'value_ssaa']:
            df_comp = datos_dia[datos_dia['componente'] == comp]
            graf_ecv_diario.add_trace(
                go.Scatter(
                    x = df_comp['fecha'],
                    y = df_comp['media'],
                    mode = 'lines',
                    name = f'media {comp}',
                    line = dict(color = 'yellow', dash = 'dot')
                )
            )
            
    else:    

        graf_ecv_diario = px.bar(datos_dia, x='fecha', y='value', 
            color = 'escala',
            color_discrete_map = colores,
            category_orders = {'escala':escala_ordenada_dia},
            labels = {'fecha':'fecha','value':'precio medio diario €/MWh', 'escala':'escala_cv'},
            #title = f'Precios medios del mercado diario OMIE. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            hover_name = 'escala'
        )

        # añadimos gráfico de línea para la media
        graf_ecv_diario.add_trace(
            go.Scatter(
                x = datos_dia['fecha'],
                y = datos_dia['media'],
                mode = 'lines',
                name = 'media',
                line = dict(color = 'yellow', dash = 'dot')
            )
        )

        # añadimos gráfico de línea para la media movil
        graf_ecv_diario.add_trace(
            go.Scatter(
                x = datos_dia['fecha'],
                y = datos_dia['media_movil'],
                mode = 'lines',
                name = 'media_movil',
                line = dict(color = 'orange', dash = 'dot'),
                visible='legendonly'   # 👈 MISMO EFECTO que en demanda
            )
        )

    # añadimos gráfico de línea para la media del año a comparar

    graf_ecv_diario.add_trace(
        go.Scatter(
            x=datos_comp['fecha_alineada'],
            y=datos_comp['media'],
            mode='lines',
            name=f"Media acumulada {st.session_state.año_seleccionado_comp}",
            line=dict(color='#5F7D8C', width=2, dash='dot'),
            visible='legendonly'   # 👈 MISMO EFECTO que en demanda
        )
    )
    

    graf_ecv_diario.update_xaxes(
        tickformat = "%b",  # Mostrar sólo el mes abreviado (Ej: Jan, Feb)
        tickvals = pd.date_range(
            start = datos_dia['fecha'].min(),
            #end=datos_dia['fecha'].max(),
            end = fecha_fin,
            freq = 'MS'  # Generar ticks al inicio de cada mes
        ),
        showgrid=True
    )

    graf_ecv_diario.update_traces(
        marker_line_width = 0,
        #customdata = datos_dia['escala'],
        hovertemplate = (
            #"<b>Escala:</b> %{customdata}<br>"
            "<b>Fecha:</b> %{x|%d-%m-%Y}<br>"  # Formato DD-MM-YYYY
            "<b>Precio:</b> %{y:.2f} €/MWh<br>"
        )
    )

    ymax = datos_dia['value'].max()

    graf_ecv_diario.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis=dict(
            range = [fecha_ini, fecha_fin],
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)'
            ),  
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=365, step="day", label='all')  # Visualizar todos los datos
                ]),
            ),
        ),
        yaxis=dict(
            #range=[0, ymax],             # Forzar el rango del eje Y
            tickmode="linear",            # Escala lineal
            tick0=0,                      # Comenzar en 0
            dtick=tick_y                      # Incrementos de 20
        ),
    )
    
    return datos_dia, graf_ecv_diario


# MEDIAS MENSUALES PARA UN AÑO DETERMINADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
#+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def mensuales(datos_dia):    
    print('datos dia para tratar mes')
    print(datos_dia)

    datos_mes = datos_dia.copy()
    datos_mes = datos_mes.drop(columns=['fecha','dia'])

    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)
    peso_comp = st.session_state.get('peso_comp', False)
    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_mes = datos_mes.groupby(['mes','componente']).agg({
            'value':'mean',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()

        print('datos mes antes de media')
        print(datos_mes)
        #datos_dia = datos_dia.melt(id_vars=['año', 'mes_nombre'], var_name='componente', value_name='value')
        datos_mes['media'] = datos_mes.groupby('componente')['value'].expanding().mean().reset_index(level=0, drop=True)
        media_spot = datos_dia[datos_dia['componente'] == 'value_spot'].sort_values('fecha')['media'].iloc[-1]
        media_ssaa = datos_dia[datos_dia['componente'] == 'value_ssaa'].sort_values('fecha')['media'].iloc[-1]
    else:
        datos_mes = datos_mes.groupby('mes').agg({
            'value':'mean',
            'año':'first',
            'mes_nombre':'first'
        }).reset_index()   

        datos_mes['media'] = datos_mes['value'].expanding().mean()
        


    
    datos_mes['value'] = datos_mes['value'].round(2)
    datos_mes[['mes','año']] = datos_mes[['mes','año']].astype(int)
    #datos_mes['media'] = datos_mes['value'].expanding().mean()
    

    media_mensual=round(datos_dia['value'].mean(),2)
    
    


    

    # Unir con tus datos por mes (asumiendo que sólo falta alguno)
    datos_mes = pd.merge(meses_completos, datos_mes, on=['mes', 'mes_nombre'], how='left')

    datos_mes['media'] = round(datos_mes['media'], 2)

    df_fila_espacio = pd.DataFrame({'mes': [13], 'value': [0], 'año': [None], 'mes_nombre': ['']})
    df_fila_media = pd.DataFrame({'mes': [14], 'value':[media_mensual], 'año':[None], 'mes_nombre':['media']})
    datos_mes = pd.concat([datos_mes, df_fila_espacio, df_fila_media], ignore_index=True)
    orden_meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic', '', 'media']
    datos_mes['mes_nombre'] = pd.Categorical(datos_mes['mes_nombre'], categories = orden_meses, ordered = True)
    datos_mes = datos_mes.sort_values(by='mes_nombre')

    
     
   
    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_mes['escala']=pd.cut(datos_mes['value'],bins=df_limites['rango'],labels=etiquetas,right=False)
    datos_mes['color']=datos_mes['escala'].map(colores)
    escala_mes = datos_mes['escala'].dropna().unique()
    escala_ordenada_mes = sorted(escala_mes, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_mes['escala']=pd.Categorical(datos_mes['escala'],categories=escala_ordenada_mes, ordered=True)


    if componente in ['SPOT+SSAA'] and dos_colores:
        componentes = ['value_spot', 'value_ssaa']
        meses_extra = [('', 13), ('media', 14)]

        for comp in componentes:
            for nombre, num in meses_extra:
                if not ((datos_mes['mes'] == num) & (datos_mes['componente'] == comp)).any():
                    fila_extra = {
                        'mes': num,
                        'mes_nombre': nombre,
                        'componente': comp,
                        'value': 0 if nombre == '' else datos_mes[datos_mes['componente'] == comp]['value'].mean(),
                        'año': np.nan,
                        'media': np.nan
                    }
                    datos_mes = pd.concat([datos_mes, pd.DataFrame([fila_extra])], ignore_index=True) 
                    datos_mes.loc[(datos_mes['mes'] == 14) & (datos_mes['componente'] == 'value_spot'), 'value'] = media_spot
                    datos_mes.loc[(datos_mes['mes'] == 14) & (datos_mes['componente'] == 'value_ssaa'), 'value'] = media_ssaa

        totales_mes = datos_mes.dropna(subset=['componente', 'value']) \
            .groupby('mes')['value'].transform('sum')
        datos_mes['peso_%'] = (datos_mes['value'] / totales_mes * 100).round(2)                

    datos_mes['value'] = round(datos_mes['value'], 2)
    print('datos_mes')
    print(datos_mes)

    #print(datos_mes)
    #GRAFICO DE BARRAS CON MEDIAS MENSUALES---------------------
    componente = st.session_state.get('componente', 'SPOT')
    if componente in ['SPOT']:
        title = f'Precios medios mensuales del SPOT. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Precios medios mensuales del SPOT+SSAA. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    else:
        title = f'Precios medios mensuales de los SSAA. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 4
    
    if componente == 'SPOT+SSAA' and dos_colores and peso_comp:
        graf_ecv_mensual = px.bar(datos_mes, x = 'mes_nombre', y = 'peso_%',
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #color_discrete_map = colores,
            #category_orders={'escala':escala_ordenada_mes},
            category_orders = {'mes_nombre': orden_meses},
            
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            title = f'Peso en % del SPOT y de los SSAA. Año {st.session_state.año_seleccionado_esc}',
            #title=title,
            text = 'peso_%',
            #text_auto=True
        ) 
    elif componente == 'SPOT+SSAA' and dos_colores:
        graf_ecv_mensual = px.bar(datos_mes, x = 'mes_nombre', y = 'value',
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #color_discrete_map = colores,
            #category_orders={'escala':escala_ordenada_mes},
            category_orders = {'mes_nombre': orden_meses},
            
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            #title = f'Precios medios mensuales. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            text = 'value',
            #text_auto=True
        )
    
    else:
        graf_ecv_mensual = px.bar(datos_mes, x = 'mes_nombre', y = 'value',
            color = 'escala',
            color_discrete_map = colores,
            #category_orders={'escala':escala_ordenada_mes},
            category_orders = {'mes_nombre':datos_mes['mes_nombre'], 'escala':escala_ordenada_mes},
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            #title = f'Precios medios mensuales. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            text = 'value',
            #text_auto=True
        )
        # añadimos gráfico de línea para la media
        graf_ecv_mensual.add_trace(
            go.Scatter(
                x = datos_mes['mes_nombre'],
                y = datos_mes['media'],
                mode = 'lines',
                name = 'media',
                line = dict(color = 'yellow', dash = 'dot')
            )
        )
        graf_ecv_mensual.add_trace(
            go.Scatter(
                x=datos_mes['mes_nombre'],
                y=[media_mensual]*len(datos_mes),
                mode='lines',
                line=dict(color='yellow',width=2, dash='dash'),
                name='media'
            )
        )
        
    graf_ecv_mensual.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis = dict(
            tickmode = 'array',
            tickvals = orden_meses,
            ticktext = orden_meses
        ),
        yaxis=dict(
            #range=[0, ymax],             # Forzar el rango del eje Y
            tickmode="linear",            # Escala lineal
            tick0=0,                      # Comenzar en 0
            dtick=tick_y                      # Incrementos de 20
        ),   
    )
    
    #graf_ecv_mensual.update_traces(
    #    textangle=0,
    #    textposition='inside',  # o 'outside' si prefieres fuera de la barra
    #    insidetextanchor='start'  # o 'middle' o 'end' según alineación horizontal)
    #)
    return graf_ecv_mensual


## MEDIAS MENSUALES DE UN MES SELECCIONADO A LO LARGO DE LOS AÑOS

def evolucion_mensual(df):
    """
    Calcula la evolución del precio medio mensual de un mes concreto
    a lo largo de todos los años.

    Parámetros:
    -----------
    df : DataFrame con columnas ['año', 'mes', 'value']
    
    Retorna:
    --------
    gráfico con el valor medio mensual seleccionado de todos los años disponibles
    """

    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)
    peso_comp = st.session_state.get('peso_comp', False)
    # Agrupar por año y mes
    
    if componente in ['SPOT+SSAA'] and dos_colores:
        if st.session_state.mes_seleccionado_esc != 'todos':
            df_mensual = df.groupby(['año','mes','componente']).agg({
                'value':'mean',
                'mes_nombre':'first'
            }).reset_index()
            totales_mes = df_mensual.dropna(subset=['componente', 'value']) \
            .groupby(['año', 'mes'])['value'].transform('sum')
        else:
            df_mensual = df.groupby(['año','componente']).agg({
                'value':'mean',
                'mes_nombre':'first'
            }).reset_index()
            totales_mes = df_mensual.dropna(subset=['componente', 'value']) \
            .groupby('año')['value'].transform('sum')
       
        df_mensual['media'] = df_mensual.groupby('componente')['value'].expanding().mean().reset_index(level=0, drop=True)
        #media_spot = df[df['componente'] == 'value_spot'].sort_values('fecha')['media'].iloc[-1]
        #media_ssaa = df[df['componente'] == 'value_ssaa'].sort_values('fecha')['media'].iloc[-1]

        #totales_mes = df_mensual.dropna(subset=['componente', 'value']) \
        #    .groupby(['año', 'mes'])['value'].transform('sum')
        df_mensual['peso_%'] = (df_mensual['value'] / totales_mes * 100).round(2) 
    else:
        if st.session_state.mes_seleccionado_esc != 'todos':
            df_mensual = df.groupby(['año','mes']).agg({
                'value':'mean',
                'mes_nombre':'first'
            }).reset_index() 
        else:
            df_mensual = df.groupby(['año']).agg({
                'value':'mean',
                'mes_nombre':'first'
            }).reset_index() 

          
    df_mensual['value']=round(df_mensual['value'],2)

    print('medias mensuales de todos los meses')
    print(df_mensual)

    # Filtrar solo el mes elegido
    if st.session_state.mes_seleccionado_esc != 'todos':
        datos_mes = df_mensual[df_mensual['mes_nombre'] == st.session_state.mes_seleccionado_esc]
    else:
        datos_mes = df_mensual

       

    print('medias mensuales del mes seleccionado')
    print(datos_mes)

    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_mes['escala']=pd.cut(datos_mes['value'],bins=df_limites['rango'],labels=etiquetas,right=False)
    datos_mes['color']=datos_mes['escala'].map(colores)
    escala_mes = datos_mes['escala'].dropna().unique()
    escala_ordenada_mes = sorted(escala_mes, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_mes['escala']=pd.Categorical(datos_mes['escala'],categories=escala_ordenada_mes, ordered=True)

    

    if componente in ['SPOT']:
        title = f'Precios medios mensuales del SPOT. Mes seleccionado: {st.session_state.mes_seleccionado_esc}'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Precios medios mensuales del SPOT+SSAA. {st.session_state.mes_seleccionado_esc}'
        tick_y = 20
    else:
        title = f'Precios medios mensuales de los SSAA. {st.session_state.mes_seleccionado_esc}'
        tick_y = 4
    
    if componente == 'SPOT+SSAA' and dos_colores and peso_comp:
        graf_ecv_mensual = px.bar(datos_mes, x = 'año', y = 'peso_%',
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #color_discrete_map = colores,
            #category_orders={'escala':escala_ordenada_mes},
            #category_orders = {'mes_nombre': orden_meses},
            
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            title = f'Peso en % del SPOT y de los SSAA.Mes {st.session_state.mes_seleccionado_esc}',
            #title=title,
            text = 'peso_%',
            #text_auto=True
        ) 
    elif componente == 'SPOT+SSAA' and dos_colores:
        graf_ecv_mensual = px.bar(datos_mes, x = 'año', y = 'value',
            color = 'componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'},
            #color_discrete_map = colores,
            #category_orders={'escala':escala_ordenada_mes},
            #category_orders = {'mes_nombre': orden_meses},
            
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            #title = f'Precios medios mensuales. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            text = 'value',
            #text_auto=True
        )
    
    else:
        graf_ecv_mensual = px.bar(datos_mes, x = 'año', y = 'value',
            color = 'escala',
            color_discrete_map = colores,
            category_orders={'escala':escala_ordenada_mes},
            #category_orders = {'mes_nombre':datos_mes['mes_nombre'], 'escala':escala_ordenada_mes},
            labels = {'value':'€/MWh', 'escala':'escala_cv','mes_nombre':'mes'},
            #title = f'Precios medios mensuales. Año {st.session_state.año_seleccionado_esc}',
            title=title,
            text = 'value',
            #text_auto=True
        )
        
        
        
    graf_ecv_mensual.update_layout(
        title={'x':0.5,'xanchor':'center'},
        xaxis = dict(
            tickmode = 'array',
            #tickvals = orden_meses,
            #ticktext = orden_meses
        ),
        yaxis=dict(
            #range=[0, ymax],             # Forzar el rango del eje Y
            tickmode="linear",            # Escala lineal
            tick0=0,                      # Comenzar en 0
            dtick=tick_y                      # Incrementos de 20
        ),   
    )
    
    #graf_ecv_mensual.update_traces(
    #    textangle=0,
    #    textposition='inside',  # o 'outside' si prefieres fuera de la barra
    #    insidetextanchor='start'  # o 'middle' o 'end' según alineación horizontal)
    #)
    return graf_ecv_mensual

    
    
# DATOS HORARIOS PARA UN DÍA SELECCIONADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def horarios(datos):
    #datos_horarios = datos[datos['año'] == st.session_state.get('año_seleccionado_esc', 2025)] #.copy()
    datos_horarios = datos.copy()
    #datos_horarios['fecha'] = pd.to_datetime(datos_horarios['fecha'], format='%d/%m/%Y')

    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_horarios['escala']=pd.cut(datos_horarios['value'],bins=df_limites['rango'],labels=etiquetas,right=True)
    lista_escala=datos_horarios['escala'].unique()
    datos_horarios['color']=datos_horarios['escala'].map(colores)
    

    
    escala_horaria=['muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2']
    escala_ordenada_hora = sorted(escala_horaria, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_horarios['escala']=pd.Categorical(datos_horarios['escala'],categories=escala_ordenada_hora, ordered=True)

    #print(datos_horarios.dtypes)

    fecha_max = datos_horarios['fecha'].max()
    if st.session_state.dia_seleccionado_esc > fecha_max:
        datos_horarios_filtrado = datos_horarios[datos_horarios['fecha'] == fecha_max]
    else:
        datos_horarios_filtrado = datos_horarios[datos_horarios['fecha'] == st.session_state.dia_seleccionado_esc]
    
    #print('datos horarios filtrado')
    #print(datos_horarios_filtrado)


    """
    Esto es para la curva de precios medios horarios del año seleccionado
    """
    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)
    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_horarios_filtrado = datos_horarios_filtrado.melt(id_vars='hora', value_vars=['value_spot', 'value_ssaa'], var_name='componente', value_name='value_bis')
        datos_horarios_filtrado = datos_horarios_filtrado.rename(columns={'value_bis': 'value'})

    #    pt_curva_horaria = datos.pivot_table(
    #        values = ['value_spot','value_ssaa'],
    #        index = 'hora'
    #    )
    #    pt_curva_horaria = pt_curva_horaria.melt(id_vars='hora', var_name='componente', value_name='value')
    #    pt_curva_horaria = pt_curva_horaria.reset_index()
        
    #else:    
    #    pt_curva_horaria = datos.pivot_table(
    #        values = 'value',
    #        index = 'hora'
    #    ).reset_index()


    #pt_curva_horaria = pt_curva_horaria['value'].round(2)
    #print('datos horarios filtrado')
    #print(datos_horarios_filtrado)

    #print('curva horaria')
    #print(pt_curva_horaria)

    # GRAFICO DE VALORES HORARIOS POR DIA FILTRADO----------------------------------------------
    componente = st.session_state.get('componente', 'SPOT')
    if componente in ['SPOT']:
        title = f'Perfil horario del SPOT. Día {st.session_state.dia_seleccionado_esc.strftime("%d/%m/%Y")}'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Perfil horario del SPOT+SSAA. Día {st.session_state.dia_seleccionado_esc.strftime("%d/%m/%Y")}'
        tick_y = 20
    else:
        title = f'Perfil horario de los SSAA. Día {st.session_state.dia_seleccionado_esc.strftime("%d/%m/%Y")}'
        tick_y = 4

    if componente == 'SPOT+SSAA' and dos_colores:
        graf_horaria_dia = px.bar(
            datos_horarios_filtrado,
            x = 'hora',
            y = 'value',
            title = title,
            labels = {'value': '€/MWh', 'escala':'escala_cv'},
            color='componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'}
            #category_orders = {'escala':escala_ordenada_hora},
        )
    else:

        graf_horaria_dia = px.bar(
            datos_horarios_filtrado,
            x='hora',
            y='value',
            title=title,
            labels={'value': '€/MWh', 'escala':'escala_cv'},
            color='escala',
            color_discrete_map=colores,
            category_orders = {'escala':escala_ordenada_hora},
        )

    #graf_horaria_linea = go.Scatter(
    #    x=pt_curva_horaria['hora'],
    #    y=pt_curva_horaria['value'],
    #    name='Media Anual',
    #    mode='lines',
    #    line=dict(color='yellow', width=3),  # opcional: dar estilo a la línea
    #)

    #graf_horaria_dia.add_trace(graf_horaria_linea)

    min_horarios = datos_horarios['value'].min()
    max_horarios = datos_horarios['value'].max()
    #min_media = pt_curva_horaria['value'].min()
    #max_media = pt_curva_horaria['value'].max()
    #min_y = min(min_horarios,min_media)
    #max_y = max(max_horarios, max_media)
    
    graf_horaria_dia.update_layout(
        yaxis=dict(
            #range=[min_y,max_y],
            autorange = True,
            tickmode="linear",            # Escala lineal
            #tick0=0,                      # Comenzar en 0
            dtick=tick_y                     # Incrementos de 20
       
        ),
        title={'x': 0.5, 'xanchor': 'center'},
        #legend=dict(
        #    orientation="v",  # Leyenda horizontal
        #    x=0.5,
        #    xanchor="center",
        #    y=1,
        #    yanchor="top",
        #),
        bargap = .5
    )        

    return datos_horarios, graf_horaria_dia, datos_horarios_filtrado
    
    
# DATOS HORARIOS PARA UN DÍA SELECCIONADO+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def medias_horarias(datos):
    #datos_horarios = datos[datos['año'] == st.session_state.get('año_seleccionado_esc', 2025)] #.copy()
    datos_horarios=datos.copy()

    #print('datos recibidos por medias horarias')
    #print(datos_horarios)
    # --- 4. Calcular medias horarias ---

    componente = st.session_state.get('componente', 'SPOT')
    dos_colores = st.session_state.get('dos_colores', False)

    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_horarios = (
            datos_horarios
            .groupby('hora', as_index=False)[['value','value_spot','value_ssaa']]
            #.groupby('hora', as_index=False)['value']
            .mean()
        )
    else:
        datos_horarios = (
            datos_horarios
            #.groupby('hora', as_index=False)[['value','value_spot','value_ssaa']]
            .groupby('hora', as_index=False)['value']
            .mean()
        )
        
    
    #datos_horarios['fecha'] = pd.to_datetime(datos_horarios['fecha'], format='%d/%m/%Y')

    df_limites, etiquetas, valor_asignado_a_rango = get_limites_componentes()
    datos_horarios['escala']=pd.cut(datos_horarios['value'],bins=df_limites['rango'],labels=etiquetas,right=True)
    lista_escala=datos_horarios['escala'].unique()
    datos_horarios['color']=datos_horarios['escala'].map(colores)
    

    
    escala_horaria=['muy bajo', 'bajo', 'medio', 'alto', 'muy alto', 'chungo', 'xtrem', 'defcon3', 'defcon2']
    escala_ordenada_hora = sorted(escala_horaria, key=lambda x: valor_asignado_a_rango[x], reverse=True)
    datos_horarios['escala']=pd.Categorical(datos_horarios['escala'],categories=escala_ordenada_hora, ordered=True)

    #print(datos_horarios.dtypes)

    #fecha_max = datos_horarios['fecha'].max()
    #if st.session_state.dia_seleccionado_esc > fecha_max:
    #    datos_horarios_filtrado = datos_horarios[datos_horarios['fecha'] == fecha_max]
    #else:
    #    datos_horarios_filtrado = datos_horarios[datos_horarios['fecha'] == st.session_state.dia_seleccionado_esc]
    
    datos_horarios_filtrado = datos_horarios.copy()
    #print('datos horarios filtrado')
    #print(datos_horarios_filtrado)


    """
    Esto es para la curva de precios medios horarios del año seleccionado
    """
    
    if componente in ['SPOT+SSAA'] and dos_colores:
        datos_horarios_filtrado = datos_horarios_filtrado.melt(id_vars='hora', value_vars=['value_spot', 'value_ssaa'], var_name='componente', value_name='value_bis')
        datos_horarios_filtrado = datos_horarios_filtrado.rename(columns={'value_bis': 'value'})

    #    pt_curva_horaria = datos.pivot_table(
    #        values = ['value_spot','value_ssaa'],
    #        index = 'hora'
    #    )
    #    pt_curva_horaria = pt_curva_horaria.melt(id_vars='hora', var_name='componente', value_name='value')
    #    pt_curva_horaria = pt_curva_horaria.reset_index()
        
    #else:    
    #    pt_curva_horaria = datos.pivot_table(
    #        values = 'value',
    #        index = 'hora'
    #    ).reset_index()


    #pt_curva_horaria = pt_curva_horaria['value'].round(2)
    #print('datos horarios filtrado')
    #print(datos_horarios_filtrado)

    #print('curva horaria')
    #print(pt_curva_horaria)

    # GRAFICO DE VALORES HORARIOS POR DIA FILTRADO----------------------------------------------
    componente = st.session_state.get('componente', 'SPOT')
    if componente in ['SPOT']:
        title = f'Perfil horario medio del SPOT. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    elif componente in ['SPOT+SSAA']:
        title = f'Perfil horario medio del SPOT+SSAA. Año {st.session_state.año_seleccionado_esc}'
        tick_y = 20
    else:
        title = f'Perfil horario medio de los SSAA. Día Año {st.session_state.año_seleccionado_esc}'
        tick_y = 4

    if componente == 'SPOT+SSAA' and dos_colores:
        graf_horaria_dia = px.bar(
            datos_horarios_filtrado,
            x = 'hora',
            y = 'value',
            title = title,
            labels = {'value': '€/MWh', 'escala':'escala_cv'},
            color='componente',
            color_discrete_map={'value_spot': 'green', 'value_ssaa': 'lightgreen'}
            #category_orders = {'escala':escala_ordenada_hora},
        )
    else:

        graf_horaria_dia = px.bar(
            datos_horarios_filtrado,
            x='hora',
            y='value',
            title=title,
            labels={'value': '€/MWh', 'escala':'escala_cv'},
            color='escala',
            color_discrete_map=colores,
            category_orders = {'escala':escala_ordenada_hora},
        )

    #graf_horaria_linea = go.Scatter(
    #    x=pt_curva_horaria['hora'],
    #    y=pt_curva_horaria['value'],
    #    name='Media Anual',
    #    mode='lines',
    #    line=dict(color='yellow', width=3),  # opcional: dar estilo a la línea
    #)

    #graf_horaria_dia.add_trace(graf_horaria_linea)

    min_horarios = datos_horarios['value'].min()
    max_horarios = datos_horarios['value'].max()
    #min_media = pt_curva_horaria['value'].min()
    #max_media = pt_curva_horaria['value'].max()
    #min_y = min(min_horarios,min_media)
    #max_y = max(max_horarios, max_media)
    
    graf_horaria_dia.update_layout(
        yaxis=dict(
            #range=[min_y,max_y],
            autorange = True,
            tickmode="linear",            # Escala lineal
            #tick0=0,                      # Comenzar en 0
            dtick=tick_y                     # Incrementos de 20
       
        ),
        title={'x': 0.5, 'xanchor': 'center'},
        #legend=dict(
        #    orientation="v",  # Leyenda horizontal
        #    x=0.5,
        #    xanchor="center",
        #    y=1,
        #    yanchor="top",
        #),
        bargap = .5
    )        

    return datos_horarios_filtrado, graf_horaria_dia
    
    
#print(datos_mes)

#datos_dia_queso=datos_dia.groupby(['escala'])['escala'].count()
#print(datos_dia_queso)
#datos_dia_queso=datos_dia_queso.reset_index(name='num_dias')
#print (datos_dia_queso)


    
    
    
#print('datos mes')
#print(datos_mes)

    
    
#GRÁFICO DE QUESITOS------------------------------------------------------------------------------------------------------------------------------
#graf_ecv_anual_queso=px.pie(datos_dia_queso, values='num_dias', names='escala',
#    color='escala',
#    color_discrete_map=colores,
#    hole=.4,
#    category_orders={'escala':escala_ordenada_dia},
#    #labels={'num_dias':'num_dias', 'escala':'escala_cv'},
#    title=f'% y número de días según la Escala CV. Año {st.session_state.año_seleccionado}',
    #width=500
#)
#graf_ecv_anual_queso.update_layout(
#    title={'x':0.5,'xanchor':'center'},
#)



#GRÁFICO DE LOS PRECIOS MEDIOS DIARIOS PERO CON DESGLOSE POR MESES. NO USADO!!!!!!!-----------------------------------------------------------------------
def diario_mes(datos_dia, escala_ordenada_dia):
    graf_ecv_anual_meses=px.bar(datos_dia, x='dia', y='value', 
        color='escala',
        color_discrete_map=colores,
        category_orders={'escala':escala_ordenada_dia},
        labels={'value':'€/MWh', 'escala':'escala_cv'},
        title=f'Precios medios del mercado diario OMIE. Año {st.session_state.año_seleccionado_esc}. Por meses.',
        facet_col='mes_nombre',
        facet_col_wrap=4


        )
    # Configurar layout y eliminar prefijos en títulos de facetas
    graf_ecv_anual_meses.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    meses_ordenados = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]


    graf_ecv_anual_meses.update_xaxes(
        showgrid=True,
        #tickformat="%d",
    )
    graf_ecv_anual_meses.update_traces(
        marker_line_width=0
    )
    graf_ecv_anual_meses.update_layout(
        title={'x':0.5,'xanchor':'center'},
        height=800,
        yaxis=dict(
            #range=[0, ymax],             # Forzar el rango del eje Y
            tickmode="linear",            # Escala lineal
            tick0=0,                      # Comenzar en 0
            dtick=20                      # Incrementos de 20
        ),
        
    )
    return graf_ecv_anual_meses

#return datos, datos_dia, datos_mes, graf_ecv_anual, graf_ecv_mensual, graf_horaria, graf_ecv_anual_meses, datos_horarios, pt_curva_horaria, colores #graf_ecv_anual_queso,



    
