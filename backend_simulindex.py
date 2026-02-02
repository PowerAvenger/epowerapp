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

    #print('df ftb trimestral inicial')
    #print(df_FTB_trimestral)


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

    #print('df ftb trimestral simulindex')
    #print(df_FTB_trimestral_simulindex)
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

    #print(df_FTB_trimestral_cobertura)
    # Colores para cada mes del trimestre
    colores_mes = ['red', 'green', 'yellow']
    colores_mes = ['#FF8C00', '#00E676', '#FFD600']

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
    trimestre, año_corto = trimestre_cobertura.split('-')
    año = 2000 + int(año_corto)

    # Meses del trimestre (tipo [1,2,3])
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
        #title=f"OMIP {trimestre_cobertura} vs OMIE"
    )

    graf_omip_trim_cober.update_layout(
        title=dict(
            text = f"OMIP {trimestre_cobertura} vs OMIE",
            x = 0.5,
            xanchor = 'center'
        ),
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
        yaxis_title="€/MWh",
        showlegend=False,
        height = 500
    )

    # Añadir las tres líneas horizontales
    for i, mes_num in enumerate(meses_trimestre):
        # Filtrar el valor spot para ese mes y año
        # Filtrar datos del mes y año
        filtro = (df_mes.index.month == mes_num) & (df_mes.index.year == año)
        df_filtrado = df_mes.loc[filtro, 'spot']

        if df_filtrado.empty:
            # Saltar este mes si no hay datos
            continue

        spot_val_mes = df_filtrado.iloc[0]
        #spot_val_mes = df_mes.loc[(df_mes.index.month == mes_num) & (df_mes.index.year == anio), 'spot'].iloc[0]



        mes_label = f"{meses_esp[mes_num]}-{str(año)[2:]}"
        texto_anotacion = f"{mes_label}: {spot_val_mes:.2f}"

        graf_omip_trim_cober.add_hline(
            y=spot_val_mes,
            line_dash="dash",
            line_color=colores_mes[i],
            annotation_text=texto_anotacion,
            annotation_position="top left",
            annotation_font_size=14,          # 👈 tamaño del texto
            annotation_font_color=colores_mes[i],  # opcional
            annotation_font_family="Arial"    # opcional
        )

    return graf_omip_trim_cober



def obtener_meff_mensual(df_FTB, df_mes):
    #filtramos por Periodo 'Mensual'
    df_FTB_mensual = df_FTB[df_FTB['Cod.'].str.startswith('FTBCM')]
    #eliminamos columnas innecesarias
    df_FTB_mensual = df_FTB_mensual.iloc[:,[0,1,5,7,14]]
    df_FTB_mensual = df_FTB_mensual.copy()

    #print('df_FTB_mensual')
    #print (df_FTB_mensual)

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

    #print('df_FTB_mensual_filtrado')
    #print(df_FTB_mensual_filtrado)

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
def hist_mensual_ORIGINAL():
    #df_in=pd.read_excel('data.xlsx')
    df_in = st.session_state.df_sheets
    df_in['fecha'] = pd.to_datetime(df_in['fecha'])
    df_in = df_in.set_index('fecha')
    # creamos un df de salida
    #if "df_norm_h" in st.session_state and st.session_state.df_norm_h is not None and st.session_state.rango_temporal == "Selecciona un rango de fechas":
    #    df_out = df_in.loc[:,['spot','precio_2.0', 'precio_3.0','precio_6.1','consumo_neto_kWh', 'coste_total']]
    #else:
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

#@st.cache_data()
def hist_mensual(df_in):
    #df_in = st.session_state.df_sheets

    df_in['fecha'] = pd.to_datetime(df_in['fecha'])
    df_in = df_in.set_index('fecha')

    # columnas base: siempre existen
    cols_base = ['spot', 'precio_2.0', 'precio_3.0', 'precio_6.1']

    # columnas extra: solo si existen
    cols_extra = []
    if 'consumo_neto_kWh' in df_in.columns and 'coste_total' in df_in.columns:
        cols_extra = ['consumo_neto_kWh', 'coste_total']

    # df_out seguro: solo columnas disponibles
    df_out = df_in.loc[:, cols_base + cols_extra]

    # resample mensual
    # precios → mean
    df_mes_prec = df_out[cols_base].resample('M').mean()

    # si no hay curva → df_mes = df_mes_prec
    df_mes = df_mes_prec.copy()

    # si hay datos de consumo y coste → calcular precio_curva
    if len(cols_extra) > 0:
        df_mes_sums = df_out[cols_extra].resample('M').sum()

        # precio mensual curva: € / kWh
        df_mes['precio_curva'] = (
            df_mes_sums['coste_total'] / df_mes_sums['consumo_neto_kWh']
        )

    # últimos 12 meses
    df_hist = df_mes.tail(12).copy()

    # conversión de precios existentes
    df_hist['precio_2.0'] = (df_hist['precio_2.0'] / 10).round(1)
    df_hist['precio_3.0'] = (df_hist['precio_3.0'] / 10).round(1)
    df_hist['precio_6.1'] = (df_hist['precio_6.1'] / 10).round(1)

    df_hist['spot'] = df_hist['spot'].round(2)

    # conversión curva si existe
    if 'precio_curva' in df_hist.columns:
        df_hist['precio_curva'] = (df_hist['precio_curva'] * 100).round(1)
    
    print('df_hist')
    print(df_hist)

    return df_hist, df_mes


# GRÁFICO PRINCIPAL DE PRECIOS DE INDEXADO A PARTIR DE OMIE++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def graf_hist(df_hist, omip, colores_precios):
    series_y = ['precio_2.0','precio_3.0','precio_6.1']
    if 'precio_curva' in df_hist.columns:
        series_y.append('precio_curva')
    #colores_precios = {'precio_2.0': 'goldenrod', 'precio_3.0': 'darkred', 'precio_6.1': 'cyan'}
    graf_hist = px.scatter(df_hist, x = 'spot', y = series_y, trendline = 'ols',
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

    simul_curva = None
    n_meses = df_hist.shape[0]
    if n_meses > 10:
        if 'precio_curva' in df_hist.columns:
            params_curve = trend_results[trend_results['Precios según ATR'] == 'precio_curva'].px_fit_results.iloc[0].params
            intercept_curve, slope_curve = params_curve[0], params_curve[1]
            simul_curva = round(intercept_curve + slope_curve * omip, 1)
        
        if simul_curva is not None:
            graf_hist.add_scatter(
                x=[omip], y=[simul_curva], mode='markers',
                marker=dict(
                    color='rgba(255,255,255,0)',
                    size=20,
                    line=dict(width=5, color=colores_precios['precio_curva'])
                ),
                name='Simul Curva',
                text='Simul Curva'
            )

            graf_hist.add_shape(
                type='line',
                x0=omip,
                y0=0,
                x1=omip,
                y1=simul_curva,
                line=dict(color=colores_precios['precio_curva'], width=1, dash='dash')
            )

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
    return graf_hist, simul_20, simul_30, simul_61, simul_curva


def resumen_periodos_simulado(df_curva, simul_curva):
    """
    Devuelve:
    - df_interno: tabla completa con todos los datos (no visible)
    - df_salida: tabla invertida SOLO con:
        consumo_kWh, precio_sim_c€/kWh, coste_sim_€
        como filas
        P1..P6 + total como columnas
    """

    # Creamos una serie con el consumo por periodos y añadimos el total (kWh)
    consumo = df_curva.groupby('periodo')['consumo_neto_kWh'].sum()
    consumo['total'] = consumo.sum()

    print('consumo')
    print(consumo)
    
    # Creamos una serie con con el coste del indexado base y le añadimos margen si procede
    coste_base = df_curva.groupby('periodo')['coste_total'].sum() #€ sin margen
    coste_base['total'] = coste_base.sum()
    coste_margen = consumo * st.session_state.margen_simulindex / 1000 # € margen
    coste_real = coste_base + coste_margen

    # Creamos una serie con los precios medios reales (€/kWh)
    precio_real = coste_real / consumo  
    
    # Calculamos los ratios precio periodo / precio medio total
    precio_medio_real = precio_real['total']
    ratios = precio_real / precio_medio_real

    # Calculamos los precios simulados por periodos a partir de la media 'simul_curva' previamente calculado. Se añade margen si hay
    precio_sim_total_eurkWh = (simul_curva / 100) + st.session_state.margen_simulindex / 1000
    precio_sim = ratios * precio_sim_total_eurkWh
    precio_sim['total'] = precio_sim_total_eurkWh

    # Calculamos los costes simulados
    coste_sim = consumo * precio_sim

    # ============================================
    #      TABLA INTERMEDIA COMPLETA (interno)
    # ============================================
    df_interno = pd.DataFrame({
        'Consumo (kWh)': consumo,
        'Coste real (€)': coste_real,
        'Precio medio real (c€/kWh)': (precio_real * 100).round(3),
        'Ratio': ratios.round(6),
        'Precio medio simulado (c€/kWh)': (precio_sim * 100).round(3),
        'coste_sim_€': coste_sim.round(2)
    })

    print('df_interno')
    print(df_interno)
    # ============================================
    #      TABLA FINAL INVERTIDA (la que quieres)
    # ============================================

    df_salida = pd.DataFrame({
        'Consumo (kWh)': consumo,
        'Precios medios (c€/kWh)': (precio_sim * 100).round(2),
        'Coste simulado (€)': coste_sim.round(2)
    })

    # invertimos filas ↔ columnas
    df_salida = df_salida.T   # filas → columnas
    df_salida.columns = df_salida.columns.astype(str)

    return df_interno, df_salida 

def estilo_resumen(df):

    styler = df.style

    # Fila consumo (entero con punto)
    styler = styler.format_index(lambda x: x, axis=0)  # no tocar índice

    styler = styler.format(
        subset=pd.IndexSlice['Consumo (kWh)', :],
        formatter=lambda x: f"{x:,.0f}".replace(",", ".") if pd.notnull(x) else ""
    )

    # Fila precio (coma decimal, 2 decimales)
    styler = styler.format(
        subset=pd.IndexSlice['Precios medios (c€/kWh)', :],
        formatter=lambda x: f"{x:,.2f}".replace(".", ",") if pd.notnull(x) else ""
    )

    # Fila coste (entero con punto)
    styler = styler.format(
        subset=pd.IndexSlice['Coste simulado (€)', :],
        formatter=lambda x: f"{x:,.0f} €".replace(",", ".") if pd.notnull(x) else ""
    )

    return styler 

def estilo_excel(df):
    styler = estilo_resumen(df)

    # Cabeceras estilo Excel
    styler = styler.set_table_styles([
        {"selector": "th.col_heading",
         "props": "background-color: #CCE5FF; color: black; font-weight: bold; border: 1px solid #999;"},
        {"selector": "th.row_heading",
         "props": "background-color: #E8E8E8; color: black; font-weight: bold; border: 1px solid #999;"},
        {"selector": "td",
         "props": "border: 1px solid #999; padding: 6px;"},
    ])

    # Alternancia de filas (tipo Excel) usando applymap_index
    def color_filas(index):
        # index es UNA SOLA etiqueta ('consumo_kWh', etc.)
        pos = list(df.index).index(index)  # posición numérica real de la fila
        if pos % 2 == 0:
            return "background-color: #F9F9F9"
        else:
            return "background-color: white"

    styler = styler.applymap_index(color_filas, axis=0)

    return styler