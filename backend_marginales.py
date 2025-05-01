import requests
import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
import re

@st.cache_data(ttl=1000)
def obtener_marginales(mes, año, dia_fin):
    path = "https://www.omie.es/sites/default/files/dados/AGNO_" + str(año) + "/MES_" + str(mes) + "/TXT/INT_PDBC_MARCA_TECNOL_1_01_" + str(mes) +"_"+str(año)+"_" +str(dia_fin) +"_" + str(mes) +"_" +str(año)+".TXT"
    print (path)
    data = requests.get(path).content
    # decode data
    data = data.decode('latin-1')

    # skip first 2 rows
    data = data.split('\r\n')[2::]
    del data[1]

    string_without_line_breaks = ""
    for line in data:
        stripped_line = line
        string_without_line_breaks += stripped_line


    new = string_without_line_breaks.split(';')

    if mes == "10":
        cuenta = 25
    else:
        cuenta = 24

    datos = ""
    contador = 0
    for x in new:
        if contador > cuenta:
                datos += '\r\n' + x + ';'
                contador = 1
        else:
                datos +=  x + ';'
                contador = contador + 1


    df = pd.read_csv(io.StringIO(datos), sep=";")
    df = df[['Día', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24']]


    df = pd.melt(df, id_vars='Día', value_vars=['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', '21', '22', '23', '24'],
                var_name='hora', value_name='tecnologia')
    df = df.dropna()


    df['hora'] = df['hora'].astype(str).astype(int)
    df = df.sort_values(['Día', 'hora'])
    df = df.rename(columns={"Día": "fecha"})
    
    #df['fecha'] = pd.to_datetime(df['fecha'], dayfirst=True)
    df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce', dayfirst=True).dt.date #format='mixed'
    

    data=pd.DataFrame(df)
    #tabla exportable de las tec marg por horas
    df_tecmarg=data.copy()

    #df_tecmarg2=data.copy()
    tecnologias = ['HI', 'BG', 'RE', 'TCC', 'TER', 'NU', 'MIE','MIP','II']
    # Función para separar tecnologías basadas en la lista conocida
    def split_tecnologias(tecnologia):
        pattern = '|'.join(tecnologias)  # Crear un patrón de las tecnologías conocidas
        return re.findall(pattern, tecnologia)
    
    df_tecmarg['tecnologia_separada'] = df_tecmarg['tecnologia'].apply(split_tecnologias)
    df_tecmarg = df_tecmarg.explode('tecnologia_separada').drop(columns='tecnologia').rename(columns={'tecnologia_separada': 'tecnologia'})
    
    #df_tecmarg['tecnologia']=df_tecmarg['tecnologia'].str[:2]
    #df_tecmarg['tecnologia']=df_tecmarg['tecnologia'].replace('TC','CC')
    print(df_tecmarg)

    return df_tecmarg #, df_tecmarg2

@st.cache_data #(ttl=10000)
def download_esios_id(id,fecha_ini,fecha_fin,agrupacion):
    token = st.secrets['ESIOS_API_KEY']
    cab = {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key' : token
    }
    url_id = 'https://api.esios.ree.es/indicators'
    url=f'{url_id}/{id}?geo_ids[]=3&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}'
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
        )
    #dataframe con los valores horarios de las tecnologias
    #lo mezclamos con el spot horario
    df_spot=datos.copy()
    df_spot=df_spot.loc[:,['datetime','value']]
    df_spot['fecha']=df_spot['datetime'].dt.date
    df_spot['hora']=df_spot['datetime'].dt.hour
    df_spot.set_index('datetime', inplace=True)
    df_spot['hora']+=1
    df_spot['fecha'] = pd.to_datetime(df_spot['fecha']).dt.date
    
    return df_spot 


color_map = {
        'TCC': '#ED7D31',
        'HI': '#00B0F0',
        'BG': '#4472C4',
        'RE': '#77DD77',
        'NU': '#9B59B6', #morado suave
        'TER': '#8B4513'
    }


def graf_1(df_spotmarg_horario,df_spot_horario,altura):
    
    symbol_map = {
        'TCC': 'triangle-up',
        'HI': 'square',
        'BG': 'circle',
        'RE': 'diamond'
        }
    
    #gráfico inicial con puntos que indican los precios medios horarios de cada tecnología
    graf_1 = px.scatter(df_spotmarg_horario, x='hora', y='value', color='tecnologia', 
            title='Precios medios marginales según tecnología', 
            labels={'hora': 'Hora', 'value': '€/MWh', 'tecnologia': 'Tecnología'},
            symbol='tecnologia',
            color_discrete_map=color_map,
            symbol_map=symbol_map,
            height=altura
            )
    #tamaño de los marcadores del gráfico anterior
    graf_1.update_traces(
        marker=dict(size=5)
    )

    #lim_sup_spot=df_spot_horario['value'].max() + 10
    lim_sup_spot=df_spotmarg_horario['value'].max() + 10
    print(lim_sup_spot)
    #parámetros para representar el eje x del gráfico
    graf_1.update_layout(
        xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]),
        title={'x':0.5,'xanchor':'center'},
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=-0.2,  # Colocarla ligeramente por encima del gráfico
            xanchor="center",  # Alineación horizontal centrada
            x=0.5,  # Posición horizontal centrada
        ),
        yaxis=dict(range=[0,lim_sup_spot]),
    )
        
    
    #añadimos las medias móviles de puntitos
    for tech in df_spotmarg_horario['tecnologia'].unique():
        df_tech = df_spotmarg_horario[df_spotmarg_horario['tecnologia'] == tech]

        # Línea de media móvil
        graf_1.add_trace(go.Scatter(
            x=df_tech['hora'],
            y=df_tech['media_movil'],
            mode='lines',
            #name=f'{tech} Media Móvil',
            line=dict(width=3,dash='dot'),  # Ancho de la línea
            line_color=color_map.get(tech, 'black'),
            showlegend=False
            )
        )

    #definimos la linea del spot, en negro y gruesa
    spot_line = go.Scatter(x=df_spot_horario['hora'], 
        y=df_spot_horario['value'], 
        mode='lines',
        name='OMIE', 
        line=dict(width=4,color='yellow') #, color='black'
        )
    # Agregar la traza adicional al gráfico
    graf_1.add_trace(spot_line)


    #self.grafico = graf_1

    return graf_1

def graf_2(df_conteo_horario,df_spot_horario,altura):
    

    # Definir el orden de las categorías
    category_order = ['TER','TCC', 'HI', 'BG', 'NU', 'MIE', 'MIP', 'RE']

    # Crear un gráfico de subplots con un eje Y secundario
    graf_2 = make_subplots(specs=[[{"secondary_y": True}]])

    area_fig = px.area(
        df_conteo_horario,
        x='hora',
        y='porcentaje_hora',
        color='tecnologia',
        color_discrete_map=color_map,
        height=altura,
        #title='% de horas marginales según tecnología',
        category_orders={'tecnologia': category_order}  # Ordenar categorías
    )

    # Añadir las trazas del gráfico de áreas al subplot principal
    for trace in area_fig.data:
        graf_2.add_trace(trace, secondary_y=False)

    graf_2.update_traces(
        line=dict(width=0)  # Eliminar bordes de las áreas
    )
    # Agregar el gráfico de líneas con el eje Y secundario
    graf_2.add_trace(
        go.Scatter(
            x=df_spot_horario['hora'],
            y=df_spot_horario['value'],
            mode='lines',
            name='OMIE',
            line=dict(width=4, color='yellow')
        ),
        secondary_y=True  # Eje Y secundario
    )
    
    lim_sup_spot=df_spot_horario['value'].max() + 10

    graf_2.update_layout(
        height=altura,
        title={
            'text': '% de horas marginales según tecnología vs OMIE',
            'x' : 0.5, #centrar titulo horizontalmente
            'xanchor' : 'center'
        },
        xaxis=dict(tickmode='linear',tick0=1,dtick=1,range=[0.5,24.5]), #para representar del 1 al 24
        yaxis=dict(title='% Horas marginales', range=[0, 100]),  # Eje Y principal
        legend=dict(
            orientation="h",  # Leyenda en horizontal
            yanchor="bottom",  # Alineación vertical en la parte inferior de la leyenda
            y=-0.2,  # Colocarla ligeramente por debajo del gráfico
            xanchor="center",  # Alineación horizontal centrada
            #x=0
            x=0.5  # Posición horizontal centrada
        ),
        yaxis2=dict(
            title='OMIE €/MWh',
            overlaying='y',
            side='right',
            showgrid=False,
            range=[0,lim_sup_spot]
            
        ),      # Eje Y secundario
    )
    return graf_2




