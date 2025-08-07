import pandas as pd
import plotly.express as px

import streamlit as st
from datetime import datetime
from backend_comun import colores_precios





#ESTE CÓDIGO ES PARA ACCEDER A LOS DIFERENTES SHEETS
#sólo lo usamos para meff
def acceder_google_sheets(spreadsheet_id): #sheet_name=None
    sheet = st.session_state.client.open_by_key(spreadsheet_id)
    # Primera hoja por defecto
    worksheet = sheet.sheet1  
    # Obtener los datos como DataFrame
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    return worksheet, df

@st.cache_data()
def obtener_historicos_meff():
    #ID hoja de registro de usuarios
    SPREADSHEET_ID = st.secrets['SHEET_MEFF_ID']
    worksheet_meff, df_historicos_FTB = acceder_google_sheets(SPREADSHEET_ID)
    
    df_historicos_FTB['Fecha']=pd.to_datetime(df_historicos_FTB['Fecha'], format='%Y-%m-%d')
    # obtenemos la fecha del último registro
    ultimo_registro = df_historicos_FTB['Fecha'].max().date()

    #print ('df_historicos_FTB')
    #print (df_historicos_FTB)
    
    return df_historicos_FTB, ultimo_registro

def obtener_meff_trimestral(df_FTB):
    #filtramos por Periodo 'Trimestral'
    df_FTB_trimestral = df_FTB[df_FTB['Cod.'].str.startswith('FTBCQ')]
    #eliminamos columnas innecesarias
    df_FTB_trimestral = df_FTB_trimestral.iloc[:,[0,1,5,7,14]]
    df_FTB_trimestral = df_FTB_trimestral.copy()

    print('df ftb trimestral inicial')
    print(df_FTB_trimestral)


    # ESTO ES PARA EL SIMULINDEX DE SIEMPRE
    # calculamos año y trimestre de la fecha actual
    current_date = datetime.now()
    current_trim = (current_date.month - 1) // 3 + 1
    current_year = current_date.year % 100  # Tomamos los últimos dos dígitos del año
    # generamos los trimestres siguientes al actual
    next_quarters = []
    for i in range(1, 5):
        next_trim = current_trim + i
        next_year = current_year
        if next_trim > 4:  # Si pasamos de Q4, volvemos a Q1 y aumentamos el año
            next_trim = next_trim % 4
            if next_trim==0:
                next_trim=4
            next_year += 1
        next_quarters.append(f'Q{next_trim}-{next_year}')

    df_FTB_trimestral_simulindex = df_FTB_trimestral[df_FTB_trimestral['Entrega'].isin(next_quarters)]

    

    # ESTO ES PARA OBTENER UN LISTADO DE TRIMESTRES DESDEL EL PRIMERO DE HISTÓRICOS HASTA EL ACTUAL, PARA COMPARAR FUTUROS CON MEDIAS OMIP
    # construir cadena tipo Q4-25
    trimestre_actual = f"Q{current_trim}-{current_year:02d}"
    # Función para convertir "Q3-25" a número ordenable
    def trimestre_a_num(t):
        q, y = t.split('-')
        trimestre = int(q[1])
        anio = int(y)
        return anio * 4 + trimestre

    # Número del trimestre actual
    num_actual = trimestre_a_num(trimestre_actual)

    # Lista ordenada y filtrada
    lista_trimestres_hist = sorted(
        df_FTB_trimestral['Entrega'].unique(),
        key=trimestre_a_num
    )
    lista_trimestres_hist = [t for t in lista_trimestres_hist if trimestre_a_num(t) <= num_actual]

    

    # Elimina las columnas temporales si lo deseas
    #df_FTB_trimestral_filtrado = df_FTB_trimestral_filtrado.drop(columns=['Entrega_Año', 'Entrega_Trim', 'Trim_Año'])

    print('df ftb trimestral simulindex')
    print(df_FTB_trimestral_simulindex)
    #print(df_FTB_trimestral_filtrado.dtypes)

    

    #VALOR EXPORTADO
    fecha_ultimo_omip=df_FTB_trimestral_simulindex['Fecha'].max().strftime('%d.%m.%Y')
    #VALOR EXPORTADO
    media_omip_simulindex = round(df_FTB_trimestral_simulindex['Precio'].iloc[-4:].mean(),2)

           
    
        
    return df_FTB_trimestral, df_FTB_trimestral_simulindex, fecha_ultimo_omip, media_omip_simulindex, lista_trimestres_hist, trimestre_actual

def obtener_grafico_meff_simulindex(df_FTB_trimestral_filtrado):
    graf_omip_trim=px.line(df_FTB_trimestral_filtrado,
        x='Fecha',
        y='Precio',
        facet_col='Entrega',
        labels={'Precio':'€/MWh'}
        )
    
    graf_omip_trim.update_layout(
        xaxis=dict(
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)'
            ),  
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(step="all")  # Visualizar todos los datos
                ]),
                #visible=True
            )
        )
    )
    return graf_omip_trim

def obtener_grafico_cober(df_FTB_trimestral_cobertura, df_mes, trimestre_cobertura):

    print(df_FTB_trimestral_cobertura)
    # Colores para cada mes del trimestre
    colores_mes = ['red', 'green', 'yellow']

    # Mapa de trimestres a meses numéricos
    mapa_trimestres = {
        'Q1': [1, 2, 3],
        'Q2': [4, 5, 6],
        'Q3': [7, 8, 9],
        'Q4': [10, 11, 12]
    }

    # Meses abreviados en español
    meses_esp = {
        1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr',
        5: 'may', 6: 'jun', 7: 'jul', 8: 'ago',
        9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic'
    }

    # Separar Qx y año
    trimestre, anio_corto = trimestre_cobertura.split('-')
    anio = 2000 + int(anio_corto)

    # Meses del trimestre
    meses_trimestre = mapa_trimestres[trimestre]
    print(meses_trimestre)

    # Convertir índice a datetime
    df_mes.index = pd.to_datetime(df_mes.index)

    # Crear gráfico principal
    graf_omip_trim_cober = px.line(
        df_FTB_trimestral_cobertura,
        x='Fecha',
        y='Precio',
        labels={'Precio': '€/MWh'},
        title=f"OMIP {trimestre_cobertura} vs OMIE"
    )

    graf_omip_trim_cober.update_layout(
        xaxis=dict(
            rangeslider=dict(
                visible=True,
                bgcolor='rgba(173, 216, 230, 0.5)'
            ),
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(step="all")
                ])
            )
        ),
        xaxis_title="Fecha",
        yaxis_title="Precio",
        showlegend=False
    )

    # Añadir las tres líneas horizontales
    for i, mes_num in enumerate(meses_trimestre):
        # Filtrar el valor spot para ese mes y año
        # Filtrar datos del mes y año
        filtro = (df_mes.index.month == mes_num) & (df_mes.index.year == anio)
        df_filtrado = df_mes.loc[filtro, 'spot']

        if df_filtrado.empty:
            # Saltar este mes si no hay datos
            continue

        spot_val_mes = df_filtrado.iloc[0]
        #spot_val_mes = df_mes.loc[(df_mes.index.month == mes_num) & (df_mes.index.year == anio), 'spot'].iloc[0]



        mes_label = f"{meses_esp[mes_num]}-{str(anio)[2:]}"
        texto_anotacion = f"{mes_label}: {spot_val_mes:.2f}"

        graf_omip_trim_cober.add_hline(
            y=spot_val_mes,
            line_dash="dash",
            line_color=colores_mes[i],
            annotation_text=texto_anotacion,
            annotation_position="top left"
        )
    return graf_omip_trim_cober



def obtener_meff_mensual(df_FTB, df_mes):
    #filtramos por Periodo 'Mensual'
    df_FTB_mensual = df_FTB[df_FTB['Cod.'].str.startswith('FTBCM')]
    #eliminamos columnas innecesarias
    df_FTB_mensual = df_FTB_mensual.iloc[:,[0,1,5,7,14]]
    df_FTB_mensual = df_FTB_mensual.copy()

    print('df_FTB_mensual')
    print (df_FTB_mensual)

    meses_map = {
        'ene': 'jan', 'feb': 'feb', 'mar': 'mar', 'abr': 'apr',
        'may': 'may', 'jun': 'jun', 'jul': 'jul', 'ago': 'aug',
        'sep': 'sep', 'oct': 'oct', 'nov': 'nov', 'dic': 'dec'
    }

    df_FTB_mensual['Entrega'] = df_FTB_mensual['Entrega'].str.lower().replace(meses_map, regex=True)
    df_FTB_mensual['Entrega'] = pd.to_datetime(df_FTB_mensual['Entrega'], format='%b-%y')

    # Aseguramos formato de fechas
    df_FTB_mensual['Entrega'] = pd.to_datetime(df_FTB_mensual['Entrega'])
    df_mes.index = pd.to_datetime(df_mes.index)

    # Añadimos spot mensual
    df_FTB_mensual_filtrado = df_FTB_mensual.copy()

    

    mes_entrega_select = 'jul-25'
    
    # filtramos por 'Entrega' para el mes seleccionado
    df_FTB_mensual_filtrado = df_FTB_mensual[df_FTB_mensual['Entrega'].dt.strftime('%b-%y').str.lower() == mes_entrega_select]

    # Filtrar dejando fuera las fechas de ese mes
    df_FTB_mensual_filtrado = df_FTB_mensual_filtrado[df_FTB_mensual_filtrado['Fecha'].dt.strftime('%b-%y').str.lower() != mes_entrega_select
]
    
    # Obtener spot mensual desde df_mes
    spot_val = df_mes.loc[df_mes.index.strftime('%b-%y').str.lower() == mes_entrega_select, 'spot'].values[0]

    # Añadir columna de color
    df_FTB_mensual_filtrado['color'] = df_FTB_mensual_filtrado['Precio'].apply(lambda p: 'red' if p > spot_val else 'green')

    print('df_FTB_mensual_filtrado')
    print(df_FTB_mensual_filtrado)

    # Gráfico de barras
    fig = px.bar(df_FTB_mensual_filtrado, x='Fecha', y='Precio',
                color='color',
                color_discrete_map={'red': 'red', 'green': 'green'},
                title=f"OMIP vs OMIE {mes_entrega_select.upper()} ({spot_val:.2f})")

    # Línea horizontal de spot
    fig.add_hline(y=spot_val, line_dash="dash", line_color="yellow")

    fig.update_layout(
        xaxis_title="Fecha",
        yaxis_title="Precio",
        showlegend=False
    )

    return df_FTB_mensual, fig

# leemos los datos de históricos de la excel telemindex
@st.cache_data()
def hist_mensual():
    #df_in=pd.read_excel('data.xlsx')
    df_in = st.session_state.df_sheets
    df_in['fecha'] = pd.to_datetime(df_in['fecha'])
    df_in = df_in.set_index('fecha')
    # creamos un df de salida
    df_out = df_in.loc[:,['spot','precio_2.0', 'precio_3.0','precio_6.1']]
    
    #print('df_out')
    #print(df_out)

    # creamos un df con valores medios mensuales
    df_mes = df_out.resample('M').mean()

    print('df_mes')
    print(df_mes)

    # tomamos los doce últimos y pasamos los precios index a c€/kWh
    df_hist = df_mes.tail(12).copy()
    df_hist['precio_2.0'] = round(df_hist['precio_2.0'] / 10, 1)
    df_hist['precio_3.0'] = round(df_hist['precio_3.0'] / 10, 1)
    df_hist['precio_6.1'] = round(df_hist['precio_6.1'] / 10, 1)
    df_hist['spot'] = round(df_hist['spot'], 2)

    #print('df_hist')
    #print(df_hist)

    return df_hist, df_mes




# GRÁFICO PRINCIPAL DE PRECIOS DE INDEXADO A PARTIR DE OMIP
def graf_hist(df_hist, omip, colores_precios):
    #colores_precios = {'precio_2.0': 'goldenrod', 'precio_3.0': 'darkred', 'precio_6.1': 'cyan'}
    graf_hist = px.scatter(df_hist, x = 'spot', y = ['precio_2.0','precio_3.0','precio_6.1'], trendline = 'ols',
        labels = {'value':'Precio medio de indexado en c€/kWh','variable':'Precios según ATR','spot':'Precio medio mercado mayorista en €/MWh'},
        height = 600,
        color_discrete_map = colores_precios,
        title = 'Simulación de los precios medios de indexado',
        
    )
    graf_hist.update_traces(marker=dict(symbol='square'))
    
    trend_results = px.get_trendline_results(graf_hist)
    #print ('trend_results')
    #print(trend_results)

    #obtención del precio 2.0 simulado a partir del gráfico de tendencia 2.0
    params_20 = trend_results[trend_results['Precios según ATR'] == 'precio_2.0'].px_fit_results.iloc[0].params
    intercept_20, slope_20 = params_20[0], params_20[1]
    simul_20=round(intercept_20+slope_20*omip,1)
                
    #obtención del precio 3.0 simulado a partir del gráfico de tendencia 3.0
    params_30 = trend_results[trend_results['Precios según ATR']=='precio_3.0'].px_fit_results.iloc[0].params
    intercept_30, slope_30 = params_30[0], params_30[1]
    simul_30=round(intercept_30+slope_30*omip,1)
    
    #obtención del precio 6.1 simulado a partir del gráfico de tendencia 6.1
    params_61 = trend_results[trend_results['Precios según ATR']=='precio_6.1'].px_fit_results.iloc[0].params
    intercept_61, slope_61 = params_61[0], params_61[1]
    simul_61=round(intercept_61+slope_61*omip,1)

    graf_hist.add_scatter(x=[omip],y=[simul_20], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color=colores_precios['precio_2.0'])),
        name='Simul 2.0',
        text='Simul 2.0'
    )
    graf_hist.add_scatter(x=[omip],y=[simul_30], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color=colores_precios['precio_3.0'])),
        name='Simul 3.0',
        text='Simul 3.0'
    )
    graf_hist.add_scatter(x=[omip],y=[simul_61], mode='markers', 
        marker=dict(color='rgba(255, 255, 255, 0)',size=20, line=dict(width=5, color=colores_precios['precio_6.1'])),
        name='Simul 6.1',
        text='Simul 6.1'
    )
    graf_hist.add_shape(
        type='line',
        x0=omip,
        y0=0,
        x1=omip,
        y1=simul_20,
        line=dict(color='grey', width=1,dash='dash'),
    )
    graf_hist.update_layout(
            title={'x':0.5,'xanchor':'center'},
    )
    return graf_hist, simul_20, simul_30, simul_61

