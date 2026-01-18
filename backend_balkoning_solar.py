import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pvlib
import streamlit as st
@st.cache_data()
def obtener_pvgis_horario(latitud, longitud, año_pvgis, inclinacion, orientacion, potencia_paneles):
    df_pvgis, _, _=pvlib.iotools.get_pvgis_hourly(
        latitude=latitud,
        longitude=longitud,
        start=año_pvgis, end=año_pvgis, 
        raddatabase='PVGIS-ERA5', components=False, 
        surface_tilt=inclinacion, surface_azimuth=orientacion, #slope=surface_tilt, azimuth: ATENCIÓN la convención de pvgis es sur=0, pero pvlib sur=180
        outputformat='json', 
        usehorizon=False, userhorizon=None, 
        pvcalculation=True, peakpower=potencia_paneles, pvtechchoice='crystSi', mountingplace='free', #peakpower en kWp instalados de paneles
        loss=14, trackingtype=0, optimal_surface_tilt=False, optimalangles=False, 
        url='https://re.jrc.ec.europa.eu/api/', 
        map_variables=False, 
        timeout=30
    )

    return df_pvgis #, meta, inputs


def arreglar_pvgis(df):
    df_pvgis = df.copy()
    #creamos columna datetime sin zona horaria
    df_pvgis['fecha_hora']=df_pvgis.index
    df_pvgis['fecha_hora']=df_pvgis['fecha_hora'].dt.tz_localize(None)
    #restamos 30 minutos 
    df_pvgis['fecha_hora']=df_pvgis['fecha_hora'] - pd.to_timedelta(30,unit='m')
    #pasamos la potencia de generación fv a kWh y renombramos
    df_pvgis['P']=df_pvgis['P']/1000
    df_pvgis=df_pvgis.rename(columns={'P':'gen_fv'})
    df_pvgis['mes_num'] = df_pvgis['fecha_hora'].dt.month
    df_pvgis['dia'] = df_pvgis['fecha_hora'].dt.day
    df_pvgis['hora'] = df_pvgis['fecha_hora'].dt.hour

    return df_pvgis

@st.cache_data()
def leer_curva_normalizada(curva):
    # --- Leer CSV detectando delimitador automáticamente ---
    df_in = pd.read_csv(curva, sep=None, engine='python', encoding='utf-8')
    print("📄 Fichero leído correctamente:")
    print(df_in.head())

    # --- Renombrar columnas clave para homogeneizar ---
    renombrar = {
        'consumo_kWh': 'consumo',
        'excedentes_kWh': 'vertidos',
        'reactiva_kVArh': 'reactiva',
        'capacitiva_kVArh': 'capacitiva',
        'fecha_hora': 'fecha_hora',
        'periodo': 'periodo'
    }
    df_in = df_in.rename(columns=renombrar)

    # --- Asegurar tipo datetime ---
    df_in['fecha_hora'] = pd.to_datetime(df_in['fecha_hora'], errors='coerce')

    # --- Añadir columnas auxiliares ---
    df_in['hora'] = df_in['fecha_hora'].dt.hour
    df_in['mes_num'] = df_in['fecha_hora'].dt.month
    df_in['dia'] = df_in['fecha_hora'].dt.day

    # --- Normalizar columna periodo ---
    df_in['periodo'] = df_in['periodo'].astype(str).str.strip().str.upper()
    df_in['periodo'] = df_in['periodo'].apply(lambda x: f"P{x[-1]}" if not x.startswith('P') and x[-1].isdigit() else x)

    # --- Crear nombre de mes ---
    meses = {
        1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
        7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"
    }
    df_in['mes_nom'] = df_in['mes_num'].map(meses)



    # --- Resumen ---
    fecha_ini = df_in['fecha_hora'].min().date()
    fecha_fin = df_in['fecha_hora'].max().date()
    print(f"\n📆 Rango temporal: {fecha_ini} → {fecha_fin}")
    print(f"🔢 Registros: {len(df_in):,}")

    return df_in


#DATAFRAME DONDE CRUZAMOS CONSUMO Y GENERACION
def combo_gen_dem(df_in, df_pvgis):
    df_gen_dem = pd.merge(
        df_in[['fecha_hora','consumo','periodo','hora','mes_num','mes_nom','dia']],
        df_pvgis[['mes_num','dia','hora','gen_fv']],
        on=['mes_num','dia','hora'],
        how='inner'
    )

    df_gen_dem['demanda']=df_gen_dem['consumo']-df_gen_dem['gen_fv']
    df_gen_dem['demanda']=df_gen_dem['demanda'].apply(lambda x:0 if x<0 else x)
    df_gen_dem['vertido']=df_gen_dem['gen_fv']-df_gen_dem['consumo']
    df_gen_dem['vertido']=df_gen_dem['vertido'].apply(lambda x:0 if x<0 else x)
    df_gen_dem['autoconsumo']=df_gen_dem['gen_fv']-df_gen_dem['vertido']
    df_gen_dem['autoconsumo']=df_gen_dem['autoconsumo'].apply(lambda x: x if x>0 else 0)

    return df_gen_dem


def generar_be(df_gen_dem):
    df_be = df_gen_dem.groupby('mes_num').agg({
        'mes_nom':'first',
        'consumo': 'sum', 
        'gen_fv': 'sum',
        'demanda':'sum',
        'vertido': 'sum',
        'autoconsumo':'sum',
        
    }).reset_index()

    #calculamos el % de cobertura del consumo, autoconsumo por un lado y demanda por otro
    df_be['%_autoconsumo']=round(df_be['autoconsumo']*100/df_be['consumo'],2)
    df_be['%_demanda']=100-df_be['%_autoconsumo']
    #calculamos el % de aprovechamiento de la generación
    df_be['%_vertido']=round(df_be['vertido']*100/df_be['gen_fv'],2)
    df_be['%_generacion']=100-df_be['%_vertido']

    return df_be


def graficar_con_gen(df_be):
    #GRAFICO CONSUMO Y GENERACIÓN POR MESES
    graf_con_gen=go.Figure()
    graf_con_gen.add_trace(go.Scatter(
        x=df_be['mes_nom'],
        y=df_be['consumo'],
        mode='lines',
        fill='tozeroy',
        #fillcolor='rgba(255, 165, 0, 0.5)',
        fillcolor='rgba(52, 152, 219, 0.5)',
        #line=dict(color='rgba(255, 165, 0, 1)',width=2),
        line=dict(color='rgba(52, 152, 219, 1)',width=2),
        name='consumo',
        
    ))
    graf_con_gen.add_trace(go.Scatter(
        x=df_be['mes_nom'],
        y=df_be['gen_fv'],
        mode='lines',
        fill='tozeroy',
        fillcolor='rgba(255, 255, 102, 0.8)',
        line=dict(color='rgba(255, 255, 102, 1)',width=2),
        name='generación FV'
    ))
    graf_con_gen.update_layout(
        title={
            'text':'Consumo y generación',
            'x':.5,
            'xanchor':'center'
        },
        xaxis_title='mes',
        yaxis_title='kWh',
        xaxis=dict(tickmode='linear'),
        height = 300
    )

    return graf_con_gen



def graficar_barras_balance(df_be, tipo_balance, colores_energia):
    """
    Gráfico de barras porcentuales para balances energéticos:
    - cobertura del consumo
    - aprovechamiento de la generación
    """

    if tipo_balance == 'cobertura':
        columnas = ['%_autoconsumo', '%_demanda']
        mapeo = {
            '%_autoconsumo': 'autoconsumo',
            '%_demanda': 'demanda'
        }
        titulo = 'Cobertura del consumo (%)'
        titulo_leyenda = '% de cobertura'

    elif tipo_balance == 'aprovechamiento':
        columnas = ['%_generacion', '%_vertido']
        mapeo = {
            '%_generacion': 'autoconsumo',
            '%_vertido': 'vertido'
        }
        titulo = 'Aprovechamiento de la generación (%)'
        titulo_leyenda = '% de aprovechamiento'

    else:
        raise ValueError("tipo_balance debe ser 'cobertura' o 'aprovechamiento'")

    # 🔹 Pasar a formato largo
    df_plot = df_be.melt(
        id_vars='mes_nom',
        value_vars=columnas,
        var_name='concepto',
        value_name='porcentaje'
    )

    df_plot['concepto'] = df_plot['concepto'].map(mapeo)

    # 🔹 Gráfico
    fig = px.bar(
        df_plot,
        x='mes_nom',
        y='porcentaje',
        color='concepto',
        text_auto=True,
        color_discrete_map=colores_energia
    )

    fig.update_layout(
        title={
            'text': titulo,
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='mes',
        yaxis_title='%',
        bargap=0.5,
        legend=dict(title=titulo_leyenda),
        height=300
    )

    fig.update_traces(textposition='inside')

    return fig



def graficar_quesos_balance(df, parametro, colores_energia, tipo_balance):

    if tipo_balance == 'aprovechamiento':
        titulo = f"Aprovechamiento de la generación FV ({parametro} %)"
    else:
        titulo = f"Cobertura del consumo ({parametro} %)"

    fig = px.pie(
        df,
        values='energia_kwh',
        names='concepto',
        hole=0.4,
        color='concepto',
        color_discrete_map=colores_energia
        #    'Autoconsumo': '#2ECC71',  # verde
        #    'Vertido': '#E74C3C'       # rojo
        
    )
    fig.update_layout(
        title={
            'text': titulo,
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='mes',
        yaxis_title='kWh',
        xaxis=dict(tickmode='linear'),

        # 👉 LEYENDA ABAJO Y CENTRADA
        legend=dict(
            orientation="h",     # horizontal
            x=0.5,               # centrada
            xanchor="center",
            y=-0.1            # debajo del gráfico (ajusta si quieres)
        )
    )
    
    return fig

def graficar_amortizacion(df, coste_inversion):
    fig = px.line(
        df,
        x='Año',
        y='Ahorro acumulado (€)',
        markers=True
    )

    fig.add_hline(
        y=coste_inversion,
        line_dash="dash",
        line_color="red",
        annotation_text="Inversión inicial",
        annotation_position="top left",
        annotation_font=dict(
            size=16,        # 👈 ajusta aquí (14–18 suele ir bien)
            color="red"
        )
    )

    fig.update_layout(
        title={
            'text': 'Amortización de la inversión en autoconsumo',
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title='Año',
        yaxis_title='€ acumulados (valor actual)',
        height=500,
        yaxis=dict(
            tickmode='linear',
            dtick=200
        ),
    )

    return fig

def graficar_ahorro(ahorro_porc):
    colors = [
        "rgba(204, 255, 204, 0.6)",  # Very light green
        "rgba(144, 238, 144, 0.6)",  # Light green
        "rgba(34, 139, 34, 0.6)",    # Medium green
        "rgba(0, 128, 0, 0.6)",      # Dark green
        "rgba(0, 100, 0, 0.6)"       # Very dark green
    ]
    colors = [
        "rgba(213, 245, 227, 0.6)",  # verde muy claro (pastel)
        "rgba(163, 228, 215, 0.6)",  # verde claro
        "rgba(88, 214, 141, 0.6)",   # verde medio (≈ #2ECC71)
        "rgba(40, 180, 99, 0.6)",    # verde intenso
        "rgba(25, 135, 84, 0.6)"     # verde oscuro elegante
    ]
        
    fig_ahorro = go.Figure(go.Indicator(
        mode = "gauge+number",  # Agregar número y delta
        value = ahorro_porc,  # El valor del indicador
        #domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Ahorro Obtenido (%)", 'font': {'size': 30}},
        gauge = {
            'axis': {'range': [None, 25]},  # Rango de 0 a 
            'bar': {'color': "green"},  # Color de la barra
            'bgcolor': "white",  # Fondo blanco
            'steps': [
                {'range': [0, 5], 'color': colors[0]},
                {'range': [5, 10], 'color': colors[1]},
                {'range': [10, 15], 'color': colors[2]},
                {'range': [15, 20], 'color': colors[3]},
                {'range': [20, 25], 'color': colors[4]},
            ],
            #'threshold': {
            #    'line': {'color': "red", 'width': 4},  # Línea roja para indicar el valor
            #    'thickness': 0.75,
            #    'value': value  # El valor que se indica en el gráfico
            #}
        }
    ))

    fig_ahorro.update_traces(number_suffix='%', selector=dict(type='indicator'))
    fig_ahorro.update_layout(
        height=360,
        margin=dict(t=0, b=50, l=20, r=20)
    )

    return fig_ahorro


