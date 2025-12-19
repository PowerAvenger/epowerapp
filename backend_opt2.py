import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dateutil.relativedelta import relativedelta
import pvlib
import numpy as np
import cvxpy as cp
from scipy.optimize import minimize
import plotly.graph_objects as go
import math

import plotly.io as pio
import dataframe_image as dfi
import nest_asyncio
import streamlit as st

# PEAJES Y CARGOS TP 2025
pyc_tp = {
    '2.0': {
        'P1': 26.93055,
        'P2': 0.697588,
        'P3': None,
        'P4': None,
        'P5': None,
        'P6': None
    },
    '3.0': {
        'P1': 19.658495,
        'P2': 10.251651,
        'P3': 4.262536,
        'P4': 3.681551,
        'P5': 2.328167,
        'P6': 1.356394
    },
    '6.1': {
        'P1': 28.791866,
        'P2': 15.077643,
        'P3': 6.55917,
        'P4': 5.172085,
        'P5': 1.932805,
        'P6': 0.916088
    },
    '6.2': {
        'P1': 19.628657,
        'P2': 10.931799,
        'P3': 3.575439,
        'P4': 2.605951,
        'P5': 1.153201,
        'P6': 0.554036
    },
    '6.3': {
        'P1': 13.200058,
        'P2': 7.707603,
        'P3': 2.994066,
        'P4': 2.256289,
        'P5': 0.921080,
        'P6': 0.441352
    },
    '6.4': {
        'P1': 7.768462,
        'P2': 4.529595,
        'P3': 1.385270,
        'P4': 1.093534,
        'P5': 0.448232,
        'P6': 0.209555
    }
}

# VALORES DE KP PARA 2025 TIPOS 1, 2 Y 3
kp = {
    '2.0': {
        'P1': 1.000000,
        'P2': 0.019259,
        'P3': None,
        'P4': None,
        'P5': None,
        'P6': None
    },
    '3.0': {
        'P1': 1.000000,
        'P2': 0.528543,
        'P3': 0.167641,
        'P4': 0.128181,
        'P5': 0.036261,
        'P6': 0.036261
    },
    '6.1': {
        'P1': 1.000000,
        'P2': 0.528704,
        'P3': 0.198416,
        'P4': 0.139813,
        'P5': 0.002956,
        'P6': 0.002632
    },
    '6.2': {
        'P1': 1.000000,
        'P2': 0.567139,
        'P3': 0.149306,
        'P4': 0.090974,
        'P5': 0.003567,
        'P6': 0.003168
    },
    '6.3': {
        'P1': 1.000000,
        'P2': 0.602540,
        'P3': 0.196297,
        'P4': 0.127930,
        'P5': 0.004201,
        'P6': 0.003698
    },
    '6.4': {
        'P1': 1.000000,
        'P2': 0.597853,
        'P3': 0.145188,
        'P4': 0.100919,
        'P5': 0.003001,
        'P6': 0.002000
    }
}

# VALORES TEP MODO 2 (EXCESOS) PARA 2025
tep = {
    '2.0': 2.953979,
    '3.0': 3.361213,
    '6.1': 3.332942,
    '6.2': 3.292963,
    '6.3': 3.099043,
    '6.4': 2.732620
}


meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']






def leer_curva_normalizada(pot_con):
    df_in = st.session_state.df_norm
    # --- Leer CSV detectando delimitador automáticamente ---
    #df_in = pd.read_csv(curva, sep=None, engine='python', encoding='utf-8')
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

    # --- Diccionario de colores ---
    colores_periodo = {
        'P1': 'red',
        'P2': 'orange',
        'P3': 'yellow',
        'P4': 'lightblue',
        'P5': 'darkblue',
        'P6': 'green'
    }

    df_in['pot_con'] = df_in['periodo'].map(pot_con)
    df_in['potencia'] = df_in['consumo'] * 4
    df_in['excesos'] = np.where(df_in['potencia']-df_in['pot_con'] < 0, 0, df_in['potencia']-df_in['pot_con'])
    df_in['excesos_cuad'] = df_in['excesos'].pow(2)

    # --- Resumen ---
    fecha_ini = df_in['fecha_hora'].min().date()
    fecha_fin = df_in['fecha_hora'].max().date()
    print(f"\n📆 Rango temporal: {fecha_ini} → {fecha_fin}")
    print(f"🔢 Registros: {len(df_in):,}")

    print('df curva de carga')
    print(df_in)

    return df_in


# Función para calcular los costes a partir de las potencias
def calcular_costes(potencias, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con):
    # Obtenemos los valores pyc_tp, kp y tep según la tarifa del suministro
    pyc_tp_tarifa = pyc_tp.get(tarifa, {})
    kp_tarifa = kp.get(tarifa, {})
    tep_tarifa = tep.get(tarifa, {})
    # Copia de df_in para no modificar los datos originales
    df_temp = df_in.copy()
    
    # Actualizamos las potencias optimizadas en la columna 'pot_opt'
    df_temp['pot_opt'] = df_temp['periodo'].map(dict(zip(pot_con.keys(), potencias)))
    
    # Calculamos los excesos y excesos_cuadrado
    df_temp['excesos_opt'] = np.maximum(df_temp['potencia'] - df_temp['pot_opt'], 0)
    df_temp['excesos_cuad_opt'] = df_temp['excesos_opt'] ** 2
    
    # Calculamos el coste de potencia
    df_coste_potfra_temp = pd.DataFrame(index=meses, columns=pot_con.keys())
    for periodo, pot_opt_value in zip(pot_con.keys(), potencias):
        #df_coste_potfra_temp[periodo] = round(pot_opt_value * pyc_tp_tarifa[periodo] / 12, 2)
        df_coste_potfra_temp[periodo] = pot_opt_value * pyc_tp_tarifa[periodo] / 12
    coste_potfra_temp = df_coste_potfra_temp.sum().sum()
    
    # Calculamos el coste de excesos
    df_excesos_temp = pd.pivot_table(df_temp, values='excesos_cuad_opt', index='mes_nom', columns='periodo', aggfunc='sum')
    df_excesos_temp = np.sqrt(df_excesos_temp)
    for periodo, k in kp_tarifa.items():
        #df_excesos_temp[periodo] = round(df_excesos_temp[periodo] * k * tep_tarifa, 2)
        df_excesos_temp[periodo] = df_excesos_temp[periodo] * k * tep_tarifa
    df_excesos_temp.index = pd.Categorical(df_excesos_temp.index, categories=meses, ordered=True)
    #ordenamos
    df_excesos_temp = df_excesos_temp.sort_index()
    coste_excesos_temp = df_excesos_temp.sum().sum()
    
    # Coste total
    coste_tp_temp = coste_potfra_temp + coste_excesos_temp
    return coste_potfra_temp, coste_excesos_temp, coste_tp_temp, df_coste_potfra_temp, df_excesos_temp





# GRÁFICO INICIAL DE COSTES A PARTIR DE LAS POTENCIAS CONTRATADAS
def grafico_costes_con(df_coste_tp_mes):
    graf_costes_potcon = go.Figure()

    # Grupo 1: Coste potencia contratada + excesos contratados
    graf_costes_potcon.add_trace(
        go.Bar(
            x=df_coste_tp_mes.index,
            y=df_coste_tp_mes['coste_pot_mes'],
            name="Coste potencia a facturar",
            marker_color="deepskyblue",
            offsetgroup=0,
        
        )
    )
    graf_costes_potcon.add_trace(
        go.Bar(
            x=df_coste_tp_mes.index,
            y=df_coste_tp_mes['coste_excesos_mes'],
            name="Coste de los excesos a facturar",
            marker_color="blue",
            offsetgroup=0,
            base=df_coste_tp_mes['coste_pot_mes']
        )
    )

    graf_costes_potcon.update_layout(
        #title = f'Coste total previsto 2025 del actual término de potencia del CUPS : {int(coste_tp_potcon)}€',
        #title = f'Coste total previsto 2025 del actual término de potencia del CUPS {cups}: {int(coste_tp_potcon)}€',
        yaxis_title = 'Coste (€)',
        #width=1400
    )

    return graf_costes_potcon


def funcion_objetivo(pot_opt, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con):
    coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(pot_opt, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)
    return coste_potfra_potopt + coste_excesos_potopt


def ajustar_potencias(pot_opt_ini, fijar_P6=False, pot_con=None):
    pot_keys = list(pot_opt_ini.keys())
    pot_vals = [math.ceil(v) for v in pot_opt_ini.values()]

    if fijar_P6 and pot_con is not None:
        p6_fijo = pot_con['P6']
        pot_vals[-1] = p6_fijo

        # Ajuste hacia atrás: ningún valor puede superar P6
        for i in range(len(pot_vals)-2, -1, -1):
            pot_vals[i] = min(pot_vals[i], pot_vals[i+1])

    else:
        # Ajuste normal hacia adelante
        for i in range(1, len(pot_vals)):
            pot_vals[i] = max(pot_vals[i], pot_vals[i-1])

    return dict(zip(pot_keys, pot_vals))








#def graficar_costes_opt(graf_costes_potcon, df_coste_tp_mes, coste_tp_potcon, coste_tp_potopt):
def graficar_costes_opt(graf_costes_potcon, df_coste_tp_mes):
    graf_costes_potcon.add_trace(
        go.Bar(
            x=df_coste_tp_mes.index,
            y=df_coste_tp_mes['coste_pot_mes_opt'],
            name="Coste potencias optimizadas",
            marker_color="lightgreen",
            offsetgroup=1
        )
    )
    graf_costes_potcon.add_trace(
        go.Bar(
            x=df_coste_tp_mes.index,
            y=df_coste_tp_mes['coste_excesos_mes_opt'],
            name="Coste excesos optimizados",
            marker_color="green",
            offsetgroup=1,
            base=df_coste_tp_mes['coste_pot_mes_opt']
        )
    )

    # Configuración del diseño
    graf_costes_potcon.update_layout(
        barmode="group",  # Agrupar los dos grupos
        xaxis_title="Mes",
        yaxis_title="Coste (€)",
        #title = (
            #f'Coste total previsto 2025 del término de potencia del CUPS {cups}.<br>'
            #f'Con las actuales potencias contratadas: {int(coste_tp_potcon)}€<br>'
            #f'Con las potencias optimizadas: {int(coste_tp_potopt)}€<br>'
            #f'Ahorro anual estimado: {ahorro_opt}€'
        #),
        
        #legend_title="Categoría",
        margin=dict(l=40, r=20, t=40, b=40),
        bargap=0.2,
        #width=1400    # Ajusta la separación entre grupos de barras
    )

    return graf_costes_potcon









