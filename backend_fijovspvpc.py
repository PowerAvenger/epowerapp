import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import datetime
from datetime import datetime
import numpy as np
import cvxpy as cp



def download_esios_id(id, fecha_ini, fecha_fin, agrupacion):
                       
    token = st.secrets['ESIOS_API_KEY']
    cab = {
        'User-Agent': 'Mozilla/5.0',
        'x-api-key' : token
    }
    url_id = 'https://api.esios.ree.es/indicators'
    url=f'{url_id}/{id}?geo_ids[]=8741&time_agg=average&start_date={fecha_ini}T00:00:00&end_date={fecha_fin}T23:59:59&time_trunc={agrupacion}'
    print(url)
    datos_raw = requests.get(url, headers=cab).json()
    #print(datos)

    return datos_raw
                       

@st.cache_data
def obtener_datos_horarios():

    #obtenemos la fecha de hoy
    fecha_hoy = datetime.today().date()
    #leemos el csv de históricos
    df_historicos = pd.read_csv('local_bbdd/pvpc_data.csv', sep = ';', index_col = 0)
    #obtenemos el último registro
    ultimo_registro_pvpc = df_historicos['datetime'].iloc[-1]

    print(f'ultimo registro pvpc {ultimo_registro_pvpc}')

    #lo pasamos a datetime date
    ultimo_registro_pvpc_fecha = pd.to_datetime(ultimo_registro_pvpc).date()
    #descargar datos de REE nuevos si necesario
    if fecha_hoy >= ultimo_registro_pvpc_fecha:
        
        fecha_ini = ultimo_registro_pvpc_fecha
        fecha_fin = fecha_hoy
        id = '10391'
        agrupacion = 'hour'
        datos_origen = download_esios_id(id,fecha_ini, fecha_fin, agrupacion)
    #tabla limpia de datos REE
    df_datos_raw = pd.DataFrame(datos_origen['indicator']['values'])
    #concatemos registros para actualizar csv eliminando duplicados
    df_datos_horarios_raw = pd.concat([df_historicos, df_datos_raw]).drop_duplicates(subset = ['datetime'])
    df_datos_horarios_raw.to_csv('local_bbdd/pvpc_data.csv', sep = ';')

    df_datos_horarios_pvpc = (df_datos_horarios_raw
      .assign(datetime = lambda vh_: pd #formateamos campo fecha, desde un str con diferencia horaria a un naive
            .to_datetime(vh_['datetime'],utc=True)  # con la fecha local
            .dt
            .tz_convert('Europe/Madrid')
            .dt
            .tz_localize(None)
            ) 
      .loc[:,['datetime','value']]
      )
    df_datos_horarios_pvpc['fecha'] = df_datos_horarios_pvpc['datetime'].dt.date
    df_datos_horarios_pvpc['hora'] = df_datos_horarios_pvpc['datetime'].dt.hour
    df_datos_horarios_pvpc['dia'] = df_datos_horarios_pvpc['datetime'].dt.day
    df_datos_horarios_pvpc['mes'] = df_datos_horarios_pvpc['datetime'].dt.month
    df_datos_horarios_pvpc['año'] = df_datos_horarios_pvpc['datetime'].dt.year
    df_datos_horarios_pvpc.set_index('datetime', inplace = True)
    df_datos_horarios_pvpc['hora'] += 1
    df_datos_horarios_pvpc = df_datos_horarios_pvpc.reset_index()
    df_datos_horarios_pvpc['fecha'] = pd.to_datetime(df_datos_horarios_pvpc['fecha'])
    
    
    

    
    
    df_perfiles_origen = pd.read_excel('utils/perfiles_iniciales_de_consumo.xlsx')
    #creamos un dataframe solo con perfil 20
    df_perfil_20 = df_perfiles_origen.iloc[:,:-3]
    df_perfil_20.rename(columns = {'P2.0TD,0m,d,h' : 'perfil_20', 'Hora' : 'hora'}, inplace = True)
    df_perfil_20 = df_perfil_20.drop(['Mes', 'Día', 'año'], axis = 1)
    df_perfil_20['hora'] = df_perfil_20['hora'].astype(int)
    df_perfil_20['fecha'] = pd.to_datetime(df_perfil_20['fecha'])
    

    #PERIODOS
    #hacerlo para añadir periodos del excel original de PowerQuery
    #df_periodos = pd.read_excel('conversor periodos liquicomun.xlsx', index_col = 0)
    df_periodos = pd.read_excel('utils/periodos_horarios.xlsx', index_col = 0, parse_dates=['fecha'])
    #df_periodos_2024_3p = df_periodos[df_periodos['año']==2024]
    df_periodos_3p = df_periodos.drop(['dh_6p'], axis = 1).reset_index()
    df_periodos_3p['hora'] += 1
    df_periodos_3p = df_periodos_3p.drop(['mes', 'dia', 'año'], axis = 1)
    df_periodos_3p['fecha'] = pd.to_datetime(df_periodos_3p['fecha'], dayfirst=True)
    df_periodos_3p['hora'] = df_periodos_3p['hora'].astype(int)
    
    df_datos_horarios_combo = df_datos_horarios_pvpc.merge(df_periodos_3p, on = ['fecha', 'hora'], how = 'left')
    df_datos_horarios_combo = df_datos_horarios_combo.merge(df_perfil_20, on = ['fecha', 'hora'], how = 'left')
    df_datos_horarios_combo = df_datos_horarios_combo.rename(columns = {'value' : 'pvpc'})
    df_datos_horarios_combo['pvpc_perfilado'] = df_datos_horarios_combo['pvpc'] * df_datos_horarios_combo['perfil_20']

    pvpc_medio=df_datos_horarios_combo['pvpc'].mean()
    num_horas=df_datos_horarios_combo['perfil_20'].count()
    suma_perfil = df_datos_horarios_combo['perfil_20'].sum()
    suma_pvpc_medio_perf = df_datos_horarios_combo['pvpc_perfilado'].sum()
    pvpc_medio_perf = suma_pvpc_medio_perf / suma_perfil

    #ultimo_registro_pvpc = df_datos_horarios_pvpc['fecha'].max()
    primer_registro_pvpc = df_datos_horarios_combo.loc[df_datos_horarios_combo['dh_3p'].notna(), 'fecha'].min()
    ultimo_registro_pvpc = df_datos_horarios_combo.loc[df_datos_horarios_combo['dh_3p'].notna(), 'fecha'].max()
    
    dias_registrados = (ultimo_registro_pvpc - primer_registro_pvpc).days + 1
    valor_minimo_horario = df_datos_horarios_pvpc['value'].min()
    valor_maximo_diario = df_datos_horarios_pvpc['value'].max()
    valor_minimo_horario, valor_maximo_diario

    print(df_datos_horarios_combo)

    return ultimo_registro_pvpc, dias_registrados, df_datos_horarios_combo


def obtener_tabla_filtrada(df_datos_horarios_combo, fecha_ini, fecha_fin, consumo):
    #filtrado por fechas streamlit. datos horarios
    #fecha_ini='2024-08-01'
    #fecha_fin='2024-08-31'
    df_datos_horarios_combo_filtrado=df_datos_horarios_combo[(df_datos_horarios_combo['fecha'] >= fecha_ini) & (df_datos_horarios_combo['fecha']<=fecha_fin)]
    df_datos_horarios_combo_filtrado_consumo=df_datos_horarios_combo_filtrado.copy()
    suma_perfil=df_datos_horarios_combo_filtrado['perfil_20'].sum()

    #variable de consumo streamlit
    #consumo=300

    #calculamos el consumo perfilado
    df_datos_horarios_combo_filtrado_consumo['perfil_20']=df_datos_horarios_combo_filtrado['perfil_20']*consumo/suma_perfil
    df_datos_horarios_combo_filtrado_consumo['pvpc_perfilado']=df_datos_horarios_combo_filtrado_consumo['pvpc']*df_datos_horarios_combo_filtrado_consumo['perfil_20']/1000
    df_datos_horarios_combo_filtrado_consumo=df_datos_horarios_combo_filtrado_consumo.rename(columns={'perfil_20':'consumo','pvpc_perfilado':'coste'})
    df_datos_horarios_combo_filtrado_consumo['precio']=df_datos_horarios_combo_filtrado_consumo['coste']/df_datos_horarios_combo_filtrado_consumo['consumo']

    suma_consumo=df_datos_horarios_combo_filtrado_consumo['consumo'].sum()
    #coste total del pvpc perfilado en el rango filtrado
    coste_pvpc_perfilado=df_datos_horarios_combo_filtrado_consumo['coste'].sum()

    print('df horarios fecha filtrada y consumo perfilado')
    print (df_datos_horarios_combo_filtrado_consumo)
    #df_datos_horarios_combo_filtrado_consumo.to_csv('df.csv')

    media_precio_perfilado=coste_pvpc_perfilado/suma_consumo

    pt_horario_filtrado=pd.pivot_table(
        df_datos_horarios_combo_filtrado_consumo,
        index='hora',
        #columns='dh_3p',
        values=['consumo','coste','precio'],
        aggfunc='mean'
    )
    pt_horario_filtrado.reset_index(inplace=True)
    
    umbral_verde=0.1
    umbral_rojo=0.15

    pt_horario_filtrado['color'] = pt_horario_filtrado['precio'].apply(
        lambda x: 'barato' if x <= umbral_verde else ('soportable' if umbral_verde < x <= umbral_rojo else 'caro')
    )

    return df_datos_horarios_combo_filtrado_consumo, pt_horario_filtrado, media_precio_perfilado,coste_pvpc_perfilado


# 
def optimizar_consumo_media_horaria(df: pd.DataFrame):
    """
    Optimiza el perfil medio horario (24h) redistribuyendo el consumo hacia las horas con menor precio medio.
    Mantiene el consumo total constante.

    Parámetros:
    -----------
    df : pd.DataFrame
        DataFrame con al menos las columnas ['hora', 'precio', 'consumo']

    Retorna:
    --------
    df_opt : pd.DataFrame
        DataFrame con la curva media por hora y las columnas optimizadas

    df_perfiles : pd.DataFrame
        DataFrame comparativo con las curvas 'original' y 'optimizada' (por hora)

    resumen : dict
        Métricas de coste original, coste optimizado, ahorro absoluto y ahorro relativo (%)
    """
    if not all(col in df.columns for col in ['hora', 'precio', 'consumo']):
        raise ValueError("El DataFrame debe contener las columnas: 'hora', 'precio', 'consumo'")

    df = df.copy()

    # Añadimos coste si no existe
    if 'coste' not in df.columns:
        df['coste'] = df['consumo'] * df['precio']

    # Calculamos la curva media por hora
    curva_media = df.groupby('hora')[['consumo', 'precio', 'coste']].mean().reset_index()

    print ('curva_media')
    print(curva_media)

    # Ordenamos por precio medio
    curva_ordenada = curva_media.sort_values('precio').copy()



    # Redistribuimos los consumos más altos a precios más bajos
    curva_ordenada['consumo_opt'] = np.sort(curva_media['consumo'])[::-1]
    curva_ordenada['coste_opt'] = curva_ordenada['consumo_opt'] * curva_ordenada['precio']

    # Reasignamos la hora original
    curva_ordenada['hora'] = curva_media.sort_values('precio')['hora'].values

    print ('curva_ordenada')
    print(curva_ordenada)

    df_opt = curva_ordenada.sort_values('hora').reset_index(drop=True)

    print ('df_opt')
    print (df_opt)

    # Creamos el DataFrame de perfiles comparativos
    df_perfiles = pd.DataFrame({
        'hora': df_opt['hora'],
        'original': curva_media.sort_values('hora')['consumo'].values,
        'optimizado': df_opt['consumo_opt'].values
    })

    print ('df perfiles')
    print(df_perfiles)

    # COSTE REAL ANUAL ORIGINAL
    coste_real_original = (df['consumo'] * df['precio']).sum()

    # COSTE REAL ANUAL OPTIMIZADO: aplicamos curva optimizada al año completo
    perfil_opt_dict = dict(zip(df_opt['hora'], df_opt['consumo_opt']))
    df['consumo_opt_aplicado'] = df['hora'].map(perfil_opt_dict)
    df['coste_opt_aplicado'] = df['consumo_opt_aplicado'] * df['precio']

    print ('df')
    print (df)
    coste_real_optimizado = df['coste_opt_aplicado'].sum()

    # Ahorros reales
    ahorro_abs = coste_real_original - coste_real_optimizado
    ahorro_pct = ahorro_abs / coste_real_original * 100

    resumen = {
        'coste_original': coste_real_original,
        'coste_optimizado': coste_real_optimizado,
        'ahorro_abs': ahorro_abs,
        'ahorro_pct': ahorro_pct
    }

    return df_opt, df_perfiles, resumen


def optimizar_consumo_suavizado(df: pd.DataFrame, consumo_total_anual: float, lambda_suavizado: float = 0.6): #0.6 
    """
    Optimiza el consumo horario suavizando la curva y minimizando el coste total.

    Parámetros:
    -----------
    df : pd.DataFrame con columnas 'precio', 'hora', 'consumo'
    consumo_total_anual : float, energía total anual a distribuir
    lambda_suavizado : float, penalización por no suavidad

    Retorna:
    --------
    df_suav : DataFrame con consumo y coste horario optimizado (8760 registros)
    df_perfiles : DataFrame comparativo original vs optimizado (24 horas)
    resumen : dict con costes y ahorro
    """
    if not all(col in df.columns for col in ['precio', 'hora', 'consumo']):
        raise ValueError("El DataFrame debe tener columnas 'precio', 'hora' y 'consumo'.")

    df = df[np.isfinite(df['precio'])].copy()
    n = len(df)
    precios = df['precio'].values

    c = cp.Variable(n)  # consumo por hora

    # Penalización por falta de suavidad (saltos horarios)
    dif_c = c[1:] - c[:-1]
    suavidad = cp.sum_squares(dif_c)

    # Función objetivo = coste + penalización
    objetivo = cp.Minimize(precios @ c + lambda_suavizado * suavidad)

    consumo_minimo = 0.05  # kWh mínimo por hora (ajustable)
    restricciones = [cp.sum(c) == consumo_total_anual, c >= consumo_minimo]

    problema = cp.Problem(objetivo, restricciones)
    problema.solve(solver=cp.SCS)

    if c.value is None:
        raise RuntimeError("La optimización no ha convergido.")

    # Resultados
    df['consumo_opt'] = c.value
    df['consumo_opt'] = np.clip(df['consumo_opt'], 0, None)
    df['coste_opt'] = df['consumo_opt'] * df['precio']
    df['coste_real'] = df['consumo'] * df['precio']

    print ('df suave')
    print(df)

    # Perfil medio horario
    perfil_original = df.groupby('hora')['consumo'].mean().reset_index(name='original')
    perfil_opt = df.groupby('hora')['consumo_opt'].mean().reset_index(name='optimizado')
    df_perfiles = perfil_original.merge(perfil_opt, on='hora')

    # Métricas
    coste_original = df['coste_real'].sum()
    coste_opt = df['coste_opt'].sum()
    ahorro_abs = coste_original - coste_opt
    ahorro_pct = (ahorro_abs / coste_original) * 100

    resumen = {
        'coste_original': coste_original,
        'coste_optimizado': coste_opt,
        'ahorro_abs': ahorro_abs,
        'ahorro_pct': ahorro_pct
    }

    return df, df_perfiles, resumen

def grafico_comparativo_perfiles(df_perfiles):
    color_streamlit = st.get_option("theme.primaryColor")
    fig = px.line(df_perfiles.reset_index(),
        x='hora', 
        y=['original', 'optimizado'],
        title='Comparativa de perfiles horarios (kWh)',
        labels={'value': 'kWh', 'hora': 'Hora del día', 'variable': 'Perfil'},
        height=400,
        color_discrete_map={
                'original': color_streamlit,
                'optimizado': 'lime'
            }
    )

    fig.update_traces(
        line=dict(width=3),
        selector=dict(name='optimizado')
    )
    
    fig.update_layout(
        xaxis=dict(tickmode='linear'),
        title={'x': 0.5, 'xanchor': 'center'},
        legend_title_text='Perfil'
    )

    return fig


def grafico_horario_consumo(pt_horario_filtrado):
    grafico_horario_consumo=px.line(pt_horario_filtrado, 
                                x='hora',y='consumo',
                                title='Curva de consumo perfilada (kWh)',
                                labels={'consumo':'kWh'},
                                height = 350
                                )

    grafico_horario_consumo.update_layout(
        xaxis=dict(tickmode='linear'),
        title={'x':0.5,'xanchor':'center'}
    )

    return grafico_horario_consumo




def grafico_horario_coste(pt_horario_filtrado):
    grafico_horario_coste=px.area(pt_horario_filtrado,
                            x='hora',y='coste',
                            title='Coste del PVPC perfilado (€)',
                            labels={'coste':'(€)'},
                            height = 350
                            )
    grafico_horario_coste.update_layout(
        xaxis=dict(tickmode='linear'),
        title={'x':0.5,'xanchor':'center'}
    )

    return grafico_horario_coste

def grafico_horario_precio(pt_horario_filtrado):
    grafico_horario_precio = px.bar(
        pt_horario_filtrado, 
        x = 'hora', y = 'precio',
        title = 'Curva de precios medios (€/kWh)',
        labels = {'precio' : '€/kWh', 'color' : 'precio'},
        color = 'color',
        color_discrete_map = {'barato': '#a5c8e1', 'soportable': '#56729a', 'caro': '#1d3455'},
        category_orders = {'color': ['caro', 'soportable', 'barato']},
        height = 350
    )
    grafico_horario_precio.update_layout(
        xaxis = dict(tickmode = 'linear'),
        title = {'x' : 0.5, 'xanchor' : 'center'}
    )
    return grafico_horario_precio

# %%
#creamos una tabla resumen de: consumo, coste y precios medios
def obtener_datos_por_periodo(df_datos_horarios_combo_filtrado_consumo):
    pt_periodos_filtrado = pd.pivot_table(
        df_datos_horarios_combo_filtrado_consumo,
        index = 'dh_3p',
        #columns='dh_3p',
        values=['consumo','coste','precio'],
        aggfunc={
            'consumo':'sum',
            'coste':'sum',
            'precio':'mean'
        }
    )
    print(pt_periodos_filtrado)
    
    pt_periodos_filtrado['consumo'] = pt_periodos_filtrado['consumo'].astype(int)
    pt_periodos_filtrado["coste"] = pt_periodos_filtrado["coste"].round(2)  # Formato con 2 decimales
    pt_periodos_filtrado["precio"] = pt_periodos_filtrado["precio"].round(2)  # Formato con 2 decimales
    pt_periodos_filtrado.reset_index(inplace=True)
    pt_periodos_filtrado.rename(columns = {'dh_3p': 'periodo'}, inplace=True)
    totales_periodo = pt_periodos_filtrado[['consumo', 'coste']].sum()
    print(totales_periodo)

    print(pt_periodos_filtrado)
    pt_periodos_filtrado_porc = pt_periodos_filtrado[['consumo', 'coste']].div(totales_periodo) * 100
    print(pt_periodos_filtrado_porc)
    pt_periodos_filtrado_porc = pt_periodos_filtrado_porc.round(2)
    pt_periodos_filtrado_porc.insert(0, 'periodo', pt_periodos_filtrado['periodo'])
    pt_periodos_filtrado_porc.reset_index()
    print(pt_periodos_filtrado_porc)


    return pt_periodos_filtrado, pt_periodos_filtrado_porc, totales_periodo

def graf_consumos_queso(pt_periodos_filtrado_porc):

    graf_consumos_queso = px.pie(
        pt_periodos_filtrado_porc, 
        names='periodo',
        values='consumo',  # Valores para el área principal
        color='periodo',  # Diferenciar por colores
        color_discrete_map={'P1': 'red', 'P2': 'orange', 'P3': 'green'},  # Colores personalizados
        title="Consumo por periodos (%)",
        hole=.3,
        labels={'consumo':'consumo (%)'},
        category_orders={'periodo': ['P1', 'P2', 'P3']}
        #hover_data=['dh_3p']
    )

    graf_consumos_queso.update_traces(
        textposition='inside',
        textinfo='label+percent'
    )
    graf_consumos_queso.update_layout(
        legend_title_text='Periodo',  # Cambiar el título de la leyenda
        showlegend=True,
        title={'x':0.5,'xanchor':'center'}  # Asegurar que la leyenda esté visible
    )

    return graf_consumos_queso

def graf_costes_queso(pt_periodos_filtrado_porc):
    graf_costes_queso = px.pie(
        pt_periodos_filtrado_porc, 
        names='periodo',
        values='coste',  # Valores para el área principal
        color='periodo',  # Diferenciar por colores
        color_discrete_map={'P1': 'red', 'P2': 'orange', 'P3': 'green'},  # Colores personalizados
        title="Coste por periodos (%)",
        hole=.3,
        labels={'coste':'coste (%)'},
        category_orders={'periodo': ['P1', 'P2', 'P3']}
        #hover_data=['dh_3p']
    )

    graf_costes_queso.update_traces(
        textposition='inside',
        textinfo='label+percent'
    )
    graf_costes_queso.update_layout(
        legend_title_text='Periodo',  # Cambiar el título de la leyenda
        showlegend=True,
        title={'x':0.5,'xanchor':'center'}  # Asegurar que la leyenda esté visible
    )

    return graf_costes_queso


