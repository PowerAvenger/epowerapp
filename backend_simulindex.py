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
    
    return df_historicos_FTB, ultimo_registro

def obtener_meff_trimestral(df_FTB):
    #filtramos por Periodo 'Trimestral'
    df_FTB_trimestral = df_FTB[df_FTB['Cod.'].str.startswith('FTBCQ')]
    #eliminamos columnas innecesarias
    df_FTB_trimestral = df_FTB_trimestral.iloc[:,[0,1,5,7,14]]
    df_FTB_trimestral = df_FTB_trimestral.copy()
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

    # Paso 3: Filtrar el DataFrame para los siguientes cuatro trimestres
    df_FTB_trimestral['Entrega_Año'] = df_FTB_trimestral['Entrega'].str.split('-').str[1].astype(int)
    df_FTB_trimestral['Entrega_Trim'] = df_FTB_trimestral['Entrega'].str.split('-').str[0].str[1].astype(int)

    # Concatenamos trimestre y año para comparar con la lista generada
    df_FTB_trimestral['Trim_Año'] = df_FTB_trimestral['Entrega'].apply(lambda x: x)

    # Filtramos los trimestres que coinciden con los próximos cuatro
    df_FTB_trimestral_filtrado = df_FTB_trimestral[df_FTB_trimestral['Trim_Año'].isin(next_quarters)]

    # Elimina las columnas temporales si lo deseas
    df_FTB_trimestral_filtrado = df_FTB_trimestral_filtrado.drop(columns=['Entrega_Año', 'Entrega_Trim', 'Trim_Año'])
    print(df_FTB_trimestral_filtrado)
    print(df_FTB_trimestral_filtrado.dtypes)
    trimestres_entrega=df_FTB_trimestral_filtrado['Entrega'].unique()

    #VALOR EXPORTADO
    fecha_ultimo_omip=df_FTB_trimestral_filtrado['Fecha'].max().strftime('%d.%m.%Y')
    #VALOR EXPORTADO
    media_omip = round(df_FTB_trimestral_filtrado['Precio'].iloc[-4:].mean(),2)
        
    return df_FTB_trimestral_filtrado, fecha_ultimo_omip, media_omip

def obtener_grafico_meff(df_FTB_trimestral_filtrado):
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

# leemos los datos de históricos de la excel telemindex
@st.cache_data()
def hist_mensual():
    #df_in=pd.read_excel('data.xlsx')
    df_in = st.session_state.df_sheets
    df_in['fecha'] = pd.to_datetime(df_in['fecha'])
    df_in = df_in.set_index('fecha')
    # creamos un df de salida
    df_out = df_in.loc[:,['spot','precio_2.0', 'precio_3.0','precio_6.1']]
    #columnas_objetivo = ['spot', 'precio_2.0', 'precio_3.0', 'precio_6.1']
    #df_out[columnas_objetivo] = df_out[columnas_objetivo].apply(pd.to_numeric, errors='coerce')
    # creamos un df con valores medios mensuales
    df_mes = df_out.resample('M').mean()
    # tomamos los doce últimos y pasamos los precios index a c€/kWh
    df_hist = df_mes.tail(12).copy()
    df_hist['precio_2.0'] = round(df_hist['precio_2.0'] / 10, 1)
    df_hist['precio_3.0'] = round(df_hist['precio_3.0'] / 10, 1)
    df_hist['precio_6.1'] = round(df_hist['precio_6.1'] / 10, 1)
    df_hist['spot'] = round(df_hist['spot'], 2)

    print('df_hist')
    print(df_hist)
    return df_hist

# creamos un gráfico principal con el parámetro 'omip'
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
    print ('trend_results')
    print(trend_results)

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

