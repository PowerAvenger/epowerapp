import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
#from dateutil.relativedelta import relativedelta
#import pvlib
import numpy as np
import cvxpy as cp
from scipy.optimize import minimize
import plotly.graph_objects as go
import math

#import plotly.io as pio
#import dataframe_image as dfi
#import nest_asyncio
import streamlit as st

# PEAJES Y CARGOS TP 2025. NO USADOS DE MOMENTO
pyc_tp_2025 = {
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

# VALORES PyC TP PARA 2026 (€/kW·año) USADOS PARA OPTIMIZACIÓN (DE MOMENTO)
pyc_tp = {
    '2.0': {
        'P1': 27.704413,
        'P2': 0.725423,
        'P3': None,
        'P4': None,
        'P5': None,
        'P6': None
    },
    '3.0': {
        'P1': 20.376927,
        'P2': 10.617621,
        'P3': 4.481534,
        'P4': 3.886333,
        'P5': 2.513851,
        'P6': 1.442287
    },
    '6.1': {
        'P1': 29.595368,
        'P2': 15.514709,
        'P3': 6.801881,
        'P4': 5.393829,
        'P5': 2.125113,
        'P6': 1.004181
    },
    '6.2': {
        'P1': 20.103588,
        'P2': 11.115668,
        'P3': 3.709113,
        'P4': 2.728152,
        'P5': 1.265617,
        'P6': 0.605381
    },
    '6.3': {
        'P1': 13.053392,
        'P2': 5.878863,
        'P3': 3.062065,
        'P4': 2.332116,
        'P5': 1.010041,
        'P6': 0.481394
    },
    '6.4': {
        'P1': 7.905445,
        'P2': 4.585787,
        'P3': 1.460005,
        'P4': 1.158560,
        'P5': 0.492827,
        'P6': 0.230511
    }
}


# VALORES TEPp PARA 2026 (€/kW)
tepp = {
    '2.0': {
        'P1': 2.968850,
        'P2': 0.056473,
        'P3': None,
        'P4': None,
        'P5': None,
        'P6': None
    },
    '3.0': {
        'P1': 3.325715,
        'P2': 1.757877,
        'P3': 0.557353,
        'P4': 0.427494,
        'P5': 0.119179,
        'P6': 0.119179
    },
    '6.1': {
        'P1': 3.431797,
        'P2': 1.818277,
        'P3': 0.680379,
        'P4': 0.478581,
        'P5': 0.010172,
        'P6': 0.008984
    },
    '6.2': {
        'P1': 3.243495,
        'P2': 1.826897,
        'P3': 0.483612,
        'P4': 0.294055,
        'P5': 0.011467,
        'P6': 0.010143
    },
    '6.3': {
        'P1': 3.063808,
        'P2': 1.844204,
        'P3': 0.617738,
        'P4': 0.402624,
        'P5': 0.013069,
        'P6': 0.011406
    },
    '6.4': {
        'P1': 2.736629,
        'P2': 1.630338,
        'P3': 0.409096,
        'P4': 0.284221,
        'P5': 0.008441,
        'P6': 0.005787
    }
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
#def calcular_costes(potencias, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con):
def calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, potencias):
    # Obtenemos los valores pyc_tp, kp y tep según la tarifa del suministro
    pyc_tp_tarifa = pyc_tp.get(tarifa, {})
    #kp_tarifa = kp.get(tarifa, {})
    #tep_tarifa = tep.get(tarifa, {})
    tepp_tarifa = tepp.get(tarifa, {})
    # Copia de df_in para no modificar los datos originales
    df_temp = df_in.copy()
    
    # Actualizamos las potencias optimizadas en la columna 'pot_opt'
    #df_temp['pot_opt'] = df_temp['periodo'].map(dict(zip(pot_con.keys(), potencias)))
    df_temp['pot_opt'] = df_temp['periodo'].map(potencias)
    
    # Calculamos los excesos y excesos_cuadrado
    df_temp['excesos_opt'] = np.maximum(df_temp['potencia'] - df_temp['pot_opt'], 0)
    df_temp['excesos_cuad_opt'] = df_temp['excesos_opt'] ** 2
    
    # Calculamos el coste de potencia
    df_coste_potfra_temp = pd.DataFrame(index=meses, columns=potencias.keys())
    for periodo, pot_opt_value in potencias.items():
    #for periodo, pot_opt_value in zip(pot_con.keys(), potencias):
        #df_coste_potfra_temp[periodo] = round(pot_opt_value * pyc_tp_tarifa[periodo] / 12, 2)
        df_coste_potfra_temp[periodo] = pot_opt_value * pyc_tp_tarifa[periodo] / 12
    coste_potfra_temp = df_coste_potfra_temp.sum().sum()
    
    # Calculamos el coste de excesos
    df_excesos_temp = pd.pivot_table(df_temp, values='excesos_cuad_opt', index='mes_nom', columns='periodo', aggfunc='sum')
    df_excesos_temp = np.sqrt(df_excesos_temp)
    for periodo, x in tepp_tarifa.items():
        #df_excesos_temp[periodo] = round(df_excesos_temp[periodo] * k * tep_tarifa, 2)
        if periodo in df_excesos_temp.columns:
            df_excesos_temp[periodo] = df_excesos_temp[periodo] * x 
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


def funcion_objetivo(pot_opt, df_in, tarifa, pyc_tp, tepp, meses, pot_con):
    #pot_opt son las potencias a optimizar en base a la suma de costes (return)
    #coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(pot_opt, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)
    potencias = dict(zip(pot_con.keys(), pot_opt))
    coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, potencias)
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

#FUNCIÓN GLOBAL PARA OPTIMIZAR++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con):
    #pot_con = st.session_state.df_pot["Potencia (kW)"].to_dict()
    #fijar_P6 = st.session_state["mantener_potencia"] == "Mantener"
    #tarifa = st.session_state.atr_dfnorm
    print(f'fijar_P6 = {fijar_P6}')

    #df_in = leer_curva_normalizada(pot_con)

    #potencias_contratadas = list(pot_con.values())
    #coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(potencias_contratadas, df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)
    coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, pot_con)
    df_coste_potfra_potcon['coste_pot_mes'] = df_coste_potfra_potcon.sum(axis=1)
    totales_potfra_potcon = df_coste_potfra_potcon.sum()
    totales_potfra_potcon.name = 'total año'
    #df_coste_potfra_potcon = pd.concat([df_coste_potfra_potcon, totales_potfra_potcon.to_frame().T])
    
    df_coste_excesos_potcon['coste_excesos_mes'] = df_coste_excesos_potcon.sum(axis=1)
    totales_excesos_potcon = df_coste_excesos_potcon.sum()
    totales_excesos_potcon.name = 'total año'
    #df_coste_excesos_potcon = pd.concat([df_coste_excesos_potcon, totales_excesos_potcon.to_frame().T])
    
    df_coste_tp_mes = pd.concat([df_coste_potfra_potcon['coste_pot_mes'], df_coste_excesos_potcon['coste_excesos_mes']], axis=1)

    graf_costes_potcon= grafico_costes_con(df_coste_tp_mes)



    pot_inicial = list(pot_con.values())  # Valores iniciales de las potencias contratadas
    constraints = [{'type': 'ineq', 'fun': lambda x, i=i: x[i + 1] - x[i]} for i in range(len(pot_inicial) - 1)]
    # Si fijar_p6 es True, agregamos la restricción para que P6 sea igual a pot_con['P6']
    if fijar_P6:
        constraints.append({
            'type': 'eq',  # 'eq' para que la restricción sea igual (P6 debe ser igual a pot_con['P6'])
            'fun': lambda x: x[-1] - pot_con['P6']  # Asegura que la última potencia (P6) sea igual a la contratada
        })


    
    # Optimización
    resultado = minimize(
        funcion_objetivo,
        pot_inicial,  # Valores iniciales
        args=(df_in, tarifa, pyc_tp, tepp, meses, pot_con),  # Argumentos adicionales
        method='SLSQP',
        constraints=constraints,
        bounds=[(0, None)] * len(pot_inicial)  # Las potencias deben ser >= 0
    )

    pot_opt_ini = dict(zip(pot_con.keys(), resultado.x))
    coste_minimizado = resultado.fun

    print("Potencias óptimas:", pot_opt_ini)
    print("Coste minimizado:", coste_minimizado)
    print("¿Optimización exitosa?", resultado.success)
    print("Mensaje de optimización:", resultado.message)

    pot_opt = ajustar_potencias(pot_opt_ini, fijar_P6=fijar_P6, pot_con=pot_con)

    coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, pot_opt)
    #coste_potfra_potopt, coste_excesos_potopt, coste_tp_potopt, df_coste_potfra_potopt, df_coste_excesos_potopt = calcular_costes(list(pot_opt.values()), df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)

    
    df_coste_potfra_potopt['coste_pot_mes_opt'] = df_coste_potfra_potopt.sum(axis=1)
    df_coste_excesos_potopt['coste_excesos_mes_opt'] = df_coste_excesos_potopt.sum(axis=1)
    totales_potfra_potopt = df_coste_potfra_potopt.sum()
    print(f'total coste potencia a facturar OPTIMIZADA: {totales_potfra_potopt}')
    totales_potfra_potopt.name = 'total año'
    #df_coste_potfra_potopt = pd.concat([df_coste_potfra_potopt, totales_potfra_potopt.to_frame().T])
    
    totales_excesos_potopt = df_coste_excesos_potopt.sum()
    totales_excesos_potopt.name = 'total año'
    #df_coste_excesos_potopt = pd.concat([df_coste_excesos_potopt, totales_excesos_potopt.to_frame().T])
    

    
    df_coste_tp_mes_opt = pd.concat([df_coste_potfra_potopt['coste_pot_mes_opt'], df_coste_excesos_potopt['coste_excesos_mes_opt']], axis=1)

    
    df_coste_tp_mes = pd.concat([df_coste_tp_mes, df_coste_tp_mes_opt,], axis=1)
    

    ahorro_opt = int(coste_tp_potcon - coste_tp_potopt)
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon

    graf_costes_potcon = graficar_costes_opt(graf_costes_potcon, df_coste_tp_mes)

    

    df_potencias = pd.DataFrame({
        'Potencias (kW)': ['Contratadas', 'Optimizadas'],
        'P1': [pot_con['P1'], pot_opt['P1']],
        'P2': [pot_con['P2'], pot_opt['P2']],
        'P3': [pot_con['P3'], pot_opt['P3']],
        'P4': [pot_con['P4'], pot_opt['P4']],
        'P5': [pot_con['P5'], pot_opt['P5']],
        'P6': [pot_con['P6'], pot_opt['P6']],
        'Coste Total (€)': [int(coste_tp_potcon), int(coste_tp_potopt)]
    })

    pot_rangos = {}
    for periodo in pot_con.keys():
        min_pot = min(pot_con[periodo], pot_opt[periodo])
        max_pot = max(pot_con[periodo], pot_opt[periodo])
        intervalo = max(1, (max_pot - min_pot) // 10)
        #pot_rangos[periodo] = np.arange(min_pot, max_pot + intervalo, intervalo)
        # Crear el rango de potencias y añadir las potencias optimizadas y contratadas
        rango_potencias = np.arange(min_pot, max_pot, intervalo)
        
        # Asegurarnos de incluir las potencias optimizadas y contratadas en el rango
        pot_rangos[periodo] = np.unique(np.concatenate([rango_potencias, [pot_con[periodo], pot_opt[periodo]]]))
        # Verificar si la potencia máxima (contratada o optimizada) está en el rango y agregarla si no
        if pot_rangos[periodo][-1] != max_pot:
            pot_rangos[periodo] = np.append(pot_rangos[periodo], max_pot)
    
    data = []

    # Iteramos sobre cada periodo
    for periodo in pot_con.keys():
        rango_potencias = pot_rangos[periodo]  # Rango de potencias para este periodo
        
        for potencia in rango_potencias:
            # Calculamos los costes para esta potencia, solo optimizando este periodo
            potencias_actuales = pot_con.copy()
            potencias_actuales[periodo] = potencia  # Cambiamos solo la potencia de este periodo
            
            # Calculamos costes por mes, referenciados al periodo
            #_, _, _, df_coste_pot_temp, df_aei_temp = calcular_costes(list(potencias_actuales.values()), df_in, tarifa, pyc_tp, kp, tep, meses, pot_con)
            _, _, _, df_coste_pot_temp, df_aei_temp = calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, potencias_actuales)
            
            # Sumamos los costes de todos los meses para este periodo específico
            coste_potencia_periodo = df_coste_pot_temp[periodo].sum()
            if periodo in df_aei_temp.columns:
                coste_excesos_periodo = df_aei_temp[periodo].sum()
            
                # Añadimos los datos al DataFrame para graficar
                data.append({
                    "Periodo": periodo,
                    "Potencia": potencia,
                    "Coste Potencia": coste_potencia_periodo,
                    "Coste Excesos": coste_excesos_periodo,
                })
    
    # Creamos un DataFrame con los datos referenciados al periodo
    df_plot = pd.DataFrame(data)

    # Gráfico de área apilado
    fig1 = px.area(
        df_plot,
        x="Potencia",
        y=["Coste Potencia", "Coste Excesos"],
        color="variable",  # Diferenciamos costes de potencia y excesos
        facet_col="Periodo",  # Facetas para cada periodo
        labels={
            "Potencia": "Potencia (kW)",
            "value": "Coste (€)",
            "variable": "Tipo de Coste"
        },
        title="Costes de Potencia y Excesos por Periodo"
    )

    fig1.update_layout(
        legend_title_text="Tipo de Coste",
        yaxis_title="Coste (€)",
        xaxis_title="Potencia (kW)",
        margin=dict(l=40, r=20, t=40, b=40),
        #width = 1600
        height = 600
    )

    data_graf_resumen_opt = {
        'coste del tp': ['contratado', 'optimizado'],
        'coste en €' : [coste_tp_potcon, coste_tp_potopt]
    }
    df_resumen_costes_tp = pd.DataFrame(data_graf_resumen_opt)
    df_resumen_costes_tp['coste en €'] = df_resumen_costes_tp['coste en €'].round(0)
    

    
    colores = {
        'contratado': 'blue',
        'optimizado': 'green'
    }

    
    graf_resumen_costes_tp = px.bar(
        df_resumen_costes_tp,
        x = 'coste del tp',
        y = 'coste en €',
        color = 'coste del tp',
        color_discrete_map = colores,
        text = 'coste en €',
        #width=500
        )
    
    fig2 = go.Figure()

    # 🔵 CONTRATADO – Potencia
    fig2.add_trace(
        go.Bar(
            x=["Contratado"],
            y=[coste_potfra_potcon],
            name="Potencia (Contratado)",
            marker_color="lightblue"
        )
    )

    # 🔵 CONTRATADO – Excesos
    fig2.add_trace(
        go.Bar(
            x=["Contratado"],
            y=[coste_excesos_potcon],
            name="Excesos (Contratado)",
            marker_color="blue"
        )
    )

    # 🟢 OPTIMIZADO – Potencia
    fig2.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_potfra_potopt],
            name="Potencia (Optimizado)",
            marker_color="lightgreen"
        )
    )

    # 🟢 OPTIMIZADO – Excesos
    fig2.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_excesos_potopt],
            name="Excesos (Optimizado)",
            marker_color="green"
        )
    )

    fig2.update_layout(
        barmode="stack",
        title="Resumen de costes: Contratado vs Optimizado",
        yaxis_title="Coste (€)",
        xaxis_title="Situación",
        legend_title_text="Tipo de coste",
        #height=600,
        margin=dict(t=60, b=40, l=40, r=40)
    )
    #coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt

    
    ahorro_opt = coste_tp_potcon - coste_tp_potopt
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon
    

    
    colors = [
        "rgba(255, 0, 0, 0.6)",  # Red for low
        "rgba(255, 165, 0, 0.6)",  # Orange for medium
        "rgba(255, 255, 0, 0.6)",  # Yellow for average
        "rgba(144, 238, 144, 0.6)",  # Light green for good
        "rgba(154, 205, 50, 0.6)"  # Green for excellent
    ]

    colors = [
        "rgba(204, 255, 204, 0.6)",  # Very light green
        "rgba(144, 238, 144, 0.6)",  # Light green
        "rgba(34, 139, 34, 0.6)",    # Medium green
        "rgba(0, 128, 0, 0.6)",      # Dark green
        "rgba(0, 100, 0, 0.6)"       # Very dark green
    ]

    
    fig_ahorro = go.Figure(go.Indicator(
        mode = "gauge+number",  # Agregar número y delta
        value = ahorro_opt_porc,  # El valor del indicador
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Ahorro Obtenido (%)", 'font': {'size': 30}},
        gauge = {
            'axis': {'range': [None, 50]},  # Rango de 0 a 100
            'bar': {'color': "green"},  # Color de la barra
            'bgcolor': "white",  # Fondo blanco
            'steps': [
                {'range': [0, 10], 'color': colors[0]},
                {'range': [10, 20], 'color': colors[1]},
                {'range': [20, 30], 'color': colors[2]},
                {'range': [30, 40], 'color': colors[3]},
                {'range': [40, 50], 'color': colors[4]},
            ],
            #'threshold': {
            #    'line': {'color': "red", 'width': 4},  # Línea roja para indicar el valor
            #    'thickness': 0.75,
            #    'value': value  # El valor que se indica en el gráfico
            #}
        }
    ))

    fig_ahorro.update_traces(number_suffix='%', selector=dict(type='indicator'))

    fig = go.Figure()
    # 🔵 Anillo interior: situación actual
    fig.add_trace(
        go.Pie(
            labels=["Potencia", "Excesos"],
            values=[
                coste_potfra_potcon, 
                coste_excesos_potcon,
                
            ],
            hole=0.6,
            name="Actual",
            marker_colors=["deepskyblue", "blue"],
            domain={"x": [0, 1], "y": [0, 1]},
            textinfo="label+percent",
            textposition="inside"
        )
    )

    # 🟢 Anillo exterior: optimizado
    fig.add_trace(
        go.Pie(
            labels=["Potencia", "Excesos"],
            values=[
                coste_potfra_potopt, 
                coste_excesos_potopt,
            ],
            hole=0.8,
            name="Optimizado",
            marker_colors=["lightgreen", "green"],
            domain={"x": [0, 1], "y": [0, 1]},
            textinfo="label+percent",
            textposition="outside"
        )
    )
    fig.update_layout(
        title="Distribución de costes: Actual vs Optimizado",
        annotations=[
            dict(
                text="Costes<br>Anuales",
                x=0.5,
                y=0.5,
                font_size=14,
                showarrow=False
            )
        ],
        legend_title_text="Tipo de coste",
        margin=dict(t=60, b=40, l=40, r=40)
    )

    return graf_costes_potcon, fig2, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, fig_ahorro, fig1, fig









