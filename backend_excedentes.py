import pandas as pd 
import plotly.express as px
import requests
import streamlit as st
from plotly.subplots import make_subplots
import plotly.graph_objects as go

@st.cache_data
def download_esios_id(id, fecha_ini, fecha_fin, agrupacion, geo_ids):
        
    token = st.secrets['ESIOS_API_KEY']
    cab = {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key' : token
    }

    url_id = 'https://api.esios.ree.es/indicators'
    if geo_ids is None:
        url=f'{url_id}/{id}?1&time_agg=average&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}'    
    else:        
        url=f'{url_id}/{id}?geo_ids[]=8741&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}'
    print(url)
    datos_origen = requests.get(url, headers=cab).json()

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
     
    return datos


def obtener_file(file):
    print(file)
    df_file=pd.read_csv(file, sep=';')
    df_origen=df_file.copy()
    df_origen=df_origen.iloc[:,[1,3,4,5]]

    #renombramos columnas
    df_origen=df_origen.rename(columns={'FECHA-HORA':'fecha_hora','PERIODO TARIFARIO':'dh','CONSUMO Wh':'demanda','GENERACION Wh':'vertido'})
    #pasamos a kWh
    df_origen[['demanda','vertido']] /= 1000
    #convertimos a fecha_hora a datetime y restamos una hora (para luego agrupar correctamente por dias)
    df_origen['fecha_hora']=pd.to_datetime(df_origen['fecha_hora'])
    df_origen['fecha_hora']=df_origen['fecha_hora']-pd.Timedelta(hours=1)
    #creamos columnas de fecha y hora
    df_origen['fecha']=df_origen['fecha_hora'].dt.date
    #df_origen['fecha']=pd.to_datetime(df_origen['fecha_hora'].dt.date)
    df_origen['hora']=df_origen['fecha_hora'].dt.hour
    df_origen['hora']+=1

    #movemos las columnas de fecha y hora
    cols=df_origen.columns.tolist()
    cols.remove('fecha')
    cols.remove('hora')
    pos_fecha_hora=cols.index('fecha_hora')
    print(pos_fecha_hora)
    cols.insert(pos_fecha_hora +1,'fecha')
    cols.insert(pos_fecha_hora +2,'hora')
    df_origen=df_origen[cols]

    df_origen['demanda_neteo']=df_origen['demanda']-df_origen['vertido']
    df_origen.loc[df_origen['demanda_neteo']<0 , 'demanda_neteo']=0
    df_origen['vertido_neteo']=df_origen['vertido']-df_origen['demanda']
    df_origen.loc[df_origen['vertido_neteo']<0 , 'vertido_neteo']=0

    id_exc=1739
    id_pvpc=10391
    fecha_ini_curva=df_origen['fecha'].min().strftime('%Y-%m-%d')
    fecha_fin_curva=df_origen['fecha'].max().strftime('%Y-%m-%d')
    agrupacion='hour'
    df_excedentes=download_esios_id(id_exc,fecha_ini_curva,fecha_fin_curva,agrupacion,None)
    df_excedentes=df_excedentes.rename(columns={'datetime':'fecha_hora','value':'precio_exc'})
    df_pvpc=download_esios_id(id_pvpc,fecha_ini_curva,fecha_fin_curva,agrupacion,8741)
    df_pvpc=df_pvpc.rename(columns={'datetime':'fecha_hora','value':'precio_pvpc'})

    df_origen=pd.merge(df_origen,df_pvpc,on='fecha_hora')
    df_origen=pd.merge(df_origen,df_excedentes,on='fecha_hora')

    df_origen['coste_pvpc']=df_origen['demanda_neteo']*df_origen['precio_pvpc']/1000
    df_origen['coste_exc']=df_origen['vertido_neteo']*df_origen['precio_exc']/1000

    demanda=round(df_origen['demanda'].sum(),2)
    vertido=round(df_origen['vertido'].sum(),2)
    demanda_neteo=round(df_origen['demanda_neteo'].sum(),2)
    vertido_neteo=round(df_origen['vertido_neteo'].sum(),2)

    coste_exc=round(df_origen['coste_exc'].sum(),2)
    coste_pvpc=round(df_origen['coste_pvpc'].sum(),2)

    precio_medio_exc=round(coste_exc/vertido_neteo,3)
    precio_medio_pvpc=round(coste_pvpc/demanda_neteo,3)

    df_coste_24h=df_origen.groupby('hora')[['vertido_neteo', 'coste_exc','demanda_neteo','coste_pvpc']].sum()
    df_coste_24h.reset_index(inplace=True)

    df_demver_24h=df_origen.groupby('hora')[['demanda_neteo','vertido_neteo']].mean()
    df_demver_24h.reset_index(inplace=True)  

    return df_origen, df_coste_24h, df_demver_24h, demanda, demanda_neteo,vertido,vertido_neteo, fecha_ini_curva, fecha_fin_curva, precio_medio_exc, coste_exc, precio_medio_pvpc, coste_pvpc


def graf_no_neteo_total(df_origen):
    graf_no_neteo_total=px.bar(df_origen,x='fecha_hora',y=['demanda','vertido'],
                            color_discrete_map={'demanda':'red','vertido':'green'},
                            animation_frame=None,#'fecha',
                            barmode='group'
                            )

    #maxy=max(df_origen['demanda'].max(),df_origen['vertido'].max())
    graf_no_neteo_total.update_layout(
            #height=altura,
            title={
                'text': 'Demanda y Vertido obtenidos del contador - NO NETEO (kWh)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },
            #xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]), #para representar del 1 al 24
            yaxis=dict(title='kWh'),#range=[0, maxy +.1]),  # Eje Y principal
            legend=dict(
                title='',
                orientation="h",  # Leyenda en horizontal
                yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
                y=1.1,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                x=0.5,  # Posición horizontal centrada
            ),
            #bargap=0.7
            margin=dict(t=80),
            xaxis=dict(
                range=[df_origen['fecha_hora'].iloc[0],df_origen['fecha_hora'].iloc[150]],
                #tickmode='linear',
                #rangeslider=dict(visible=False),
                #fixedrange=False,
                showgrid=True,
                #gridsize=24
            ),
            #dragmode='pan',
            bargap=0.3
            
        )
    return graf_no_neteo_total

def graf_neteo_total(df_origen):
    graf_neteo_total=px.bar(df_origen,x='fecha_hora',y=['demanda_neteo','vertido_neteo'],
                            color_discrete_map={'demanda_neteo':'red','vertido_neteo':'green'},
                            animation_frame=None,#'fecha',
                            barmode='group'
                            )

    #maxy=max(df_origen['demanda'].max(),df_origen['vertido'].max())
    graf_neteo_total.update_layout(
            #height=altura,
            title={
                'text': 'Demanda y Vertido obtenidos por saldos horarios - NETEO (kWh)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },
            #xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]), #para representar del 1 al 24
            yaxis=dict(title='kWh'),#range=[0, maxy +.1]),  # Eje Y principal
            legend=dict(
                title='',
                orientation="h",  # Leyenda en horizontal
                yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
                y=1.1,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                x=0.5,  # Posición horizontal centrada
            ),
            #bargap=0.7
            margin=dict(t=80),
            xaxis=dict(
                range=[df_origen['fecha_hora'].iloc[0],df_origen['fecha_hora'].iloc[150]],
                #tickmode='linear',
                #rangeslider=dict(visible=False),
                #fixedrange=False,
                showgrid=True,
                #gridsize=24
            ),
            #dragmode='pan',
            bargap=0.3
            
        )
    
    return graf_neteo_total

def graf_no_neteo(df_origen):
    graf_no_neteo=px.bar(df_origen,x='hora',y=['demanda','vertido'],
                            color_discrete_map={'demanda':'red','vertido':'green'},
                            animation_frame='fecha',
                            barmode='group'
                            )

    maxy=max(df_origen['demanda'].max(),df_origen['vertido'].max())
    graf_no_neteo.update_layout(
            #height=altura,
            title={
                'text': 'Valores horarios de lecturas de demanda y excedentes. Por días (kWh)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },
            xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]), #para representar del 1 al 24
            yaxis=dict(title='kWh',range=[0, maxy +.1]),  # Eje Y principal
            legend=dict(
                title='',
                orientation="h",  # Leyenda en horizontal
                yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
                y=1.1,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                x=0.5,  # Posición horizontal centrada
            ),
            bargap=0.7
            
        )
    
    return graf_no_neteo

def graf_coste_exc(df_coste_24h):
    
    #preparamos columna de color para representar barras positivas y negativas
    df_coste_24h=df_coste_24h.copy()
    df_coste_24h['color'] = df_coste_24h['vertido_neteo'].apply(lambda x: 'green' if x >= 0 else 'red')

    #preparamos gráfico para usar dos ejes y
    graf_coste_exc = make_subplots(specs=[[{"secondary_y": True}]])

    #eje y primario. vertido neto. es un área
    graf_coste_exc.add_trace(
        go.Scatter(
            x=df_coste_24h['hora'],
            y=df_coste_24h['vertido_neteo'],
            #mode='lines',
            fill='tozeroy',
            fillcolor="#9af8ff",
            mode='lines',
            name='excedentes',
            line=dict(width=2, color="#60b4ff")
        ),
        secondary_y=False,
    )

    #eje y secundario. coste de los vertidos. formato barras
    graf_coste_exc.add_trace(
            go.Bar(
                x=df_coste_24h['hora'],
                y=df_coste_24h['coste_exc'],
                
                name='coste_exc',
                marker=dict(
                    #color="#09ab3b")
                    color=['#09ab3b' if v >= 0 else '#ff4b4b' for v in df_coste_24h['coste_exc']],
                )
            ),
            secondary_y=True  
    )


    ymax=df_coste_24h['vertido_neteo'].max()

    graf_coste_exc.update_layout(
            #height=altura,
            title={
                'text': 'Excedentes vs Coste (facturado)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },

            yaxis=dict(
                title='excedentes (kWh)',
                #overlaying='y',
                side='left',
                showgrid=True,
                range=[0,ymax+5]
            ),     
            xaxis=dict(tickmode='linear',
                    tick0=1,
                    dtick=1,
                    range=[0.5,24.5],
                    title='hora'
                    ), #para representar del 1 al 24
            
            #escala eje y secundario. a partir de cero
            
            yaxis2=dict(title='coste (€)',showgrid=False), # ,range=[0, ymax2+5]
            legend=dict(
                orientation="h",  # Leyenda en horizontal
                yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
                y=1.15,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                #x=0
                x=0.5  # Posición horizontal centrada
            ),
            
            bargap=0.7
            
        )
    
    return graf_coste_exc

def graf_coste_pvpc(df_coste_24h):
    #preparamos para dos ejes y
    graf_coste_pvpc = make_subplots(specs=[[{"secondary_y": True}]])

    #añadimos en eje y izquierdo la demanda neteo
    graf_coste_pvpc.add_trace(
        go.Scatter(
            x=df_coste_24h['hora'],
            y=df_coste_24h['demanda_neteo'],
            #mode='lines',
            fill='tozeroy',
            fillcolor="#ffc7c7",
            mode='lines',
            name='demanda',
            line=dict(width=2, color="#ff2b2b")
        ),
        secondary_y=False,
        
    )

    #añadimos en el eje y derecho el coste de la demanda neteo
    graf_coste_pvpc.add_trace(
            go.Bar(
                x=df_coste_24h['hora'],
                y=df_coste_24h['coste_pvpc'],
                
                name='coste_pvpc',
                marker=dict(color="#ff4b4b")
            ),
            secondary_y=True  # Eje Y secundario
        )


    ymax=df_coste_24h['demanda_neteo'].max()

    graf_coste_pvpc.update_layout(
            #height=altura,
            title={
                'text': 'Demanda vs Coste (facturado)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },

            yaxis=dict(
                title='demanda (kWh)',
                #overlaying='y',
                side='left',
                showgrid=True,
                range=[0,ymax+5]
            ),     
            xaxis=dict(tickmode='linear',
                    tick0=1,
                    dtick=1,
                    range=[0.5,24.5],
                    title='hora'
                    ), #para representar del 1 al 24
            
            #escala eje y secundario. a partir de cero
            
            yaxis2=dict(title='coste (€)',showgrid=False), # ,range=[0, ymax2+5]
            legend=dict(
                orientation="h",  # Leyenda en horizontal
                yanchor="top",  # Alineación vertical en la parte inferior de la leyenda
                y=1.15,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                #x=0
                x=0.5  # Posición horizontal centrada
            ),
            
            bargap=0.7
            
        )
    
    return graf_coste_pvpc

def graf_demver(df_demver_24h):
    #preparamos para dos ejes
    graf_demver = make_subplots(specs=[[{"secondary_y": True}]])

    #añadimos la demanda en el eje y izquierdo
    graf_demver.add_trace(
        go.Scatter(
            x=df_demver_24h['hora'],
            y=df_demver_24h['demanda_neteo'],
            #mode='lines',
            fill='tozeroy',
            fillcolor="#ffc7c7",
            mode='lines',
            name='demanda',
            line=dict(width=2, color="#ff2b2b")
        ),
        secondary_y=False,
        
    )

    graf_demver.add_trace(
            go.Scatter(
                x=df_demver_24h['hora'],
                y=df_demver_24h['vertido_neteo'],
                fill='tozeroy',
                fillcolor="#9af8ff",
                mode='lines',
                name='excedentes',
                line=dict(width=2, color="#60b4ff")
            ),
            secondary_y=False  # Eje Y secundario
        )


    ymax=df_demver_24h['vertido_neteo'].max()

    graf_demver.update_layout(
            #height=altura,
            title={
                'text': 'Perfil de carga (kWh)',
                'x' : 0.5, #centrar titulo horizontalmente
                'xanchor' : 'center'
            },

            yaxis=dict(
                title='kWh',
                #overlaying='y',
                side='left',
                showgrid=True,
                range=[0,ymax+.5]
            ),     
            xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]), #para representar del 1 al 24
            
            #escala eje y secundario. a partir de cero
            
            yaxis2=dict(title='coste (€)',showgrid=False), # ,range=[0, ymax2+5]
            legend=dict(
                orientation="h",  # Leyenda en horizontal
                yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
                y=-0.2,  # Colocarla ligeramente por debajo del gráfico
                xanchor="center",  # Alineación horizontal centrada
                #x=0
                x=0.5  # Posición horizontal centrada
            ),
            
            bargap=0.7
            
        )
    
    return graf_demver


