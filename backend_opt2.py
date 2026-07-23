
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from scipy.optimize import minimize
import plotly.graph_objects as go
import math
import streamlit as st
import gc
from backend_comun import aplicar_estilo
import re
from datetime import datetime, date 

pyc_tp = {
    # Peajes de transporte y distribución CNMC + cargos del sistema.
    # Valores anuales en €/kW año.
    2023: {
        '2.0': {
            'P1': 25.383055, 'P2': 1.342713,
            'P3': None, 'P4': None, 'P5': None, 'P6': None
        },
        '3.0': {
            'P1': 13.982509, 'P2': 11.899074, 'P3': 4.002045,
            'P4': 3.653973, 'P5': 2.732707, 'P6': 2.001136
        },
        '6.1': {
            'P1': 22.965215, 'P2': 19.841178, 'P3': 10.327582,
            'P4': 8.560662, 'P5': 1.908583, 'P6': 1.148958
        },
        '6.2': {
            'P1': 15.826387, 'P2': 14.660345, 'P3': 6.244350,
            'P4': 4.918409, 'P5': 1.197731, 'P6': 0.751653
        },
        '6.3': {
            'P1': 11.693507, 'P2': 10.378653, 'P3': 5.456201,
            'P4': 4.251289, 'P5': 1.146336, 'P6': 0.789272
        },
        '6.4': {
            'P1': 9.330085, 'P2': 7.722984, 'P3': 3.913267,
            'P4': 3.073874, 'P5': 0.672280, 'P6': 0.497567
        },
    },
    2024: {
        '2.0': {
            'P1': 25.391661, 'P2': 0.968852,
            'P3': None, 'P4': None, 'P5': None, 'P6': None
        },
        '3.0': {
            'P1': 15.713047, 'P2': 9.547036, 'P3': 4.658211,
            'P4': 4.142560, 'P5': 2.285209, 'P6': 1.553638
        },
        '6.1': {
            'P1': 24.414407, 'P2': 14.692911, 'P3': 11.328635,
            'P4': 9.250764, 'P5': 1.727525, 'P6': 0.967900
        },
        '6.2': {
            'P1': 15.403115, 'P2': 9.884764, 'P3': 6.439198,
            'P4': 5.494646, 'P5': 1.062003, 'P6': 0.615925
        },
        '6.3': {
            'P1': 12.287597, 'P2': 7.417845, 'P3': 5.901005,
            'P4': 4.798116, 'P5': 1.000746, 'P6': 0.643755
        },
        '6.4': {
            'P1': 8.197568, 'P2': 4.560304, 'P3': 3.484370,
            'P4': 3.199933, 'P5': 0.517041, 'P6': 0.342328
        },
    },
    2025: {
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
    },
    2026: {
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
}

# tipos 1, 2 y 3
tepp123 = {
    2025: {
        '2.0': {
            'P1': 2.953979,
            'P2': 0.056891,
            'P3': None,
            'P4': None,
            'P5': None,
            'P6': None
        },
        '3.0': {
            'P1': 3.361213,
            'P2': 1.776546,
            'P3': 0.563477,
            'P4': 0.430844,
            'P5': 0.121880,
            'P6': 0.121880
        },
        '6.1': {
            'P1': 3.332942,
            'P2': 1.762138,
            'P3': 0.661311,
            'P4': 0.465989,
            'P5': 0.011745,
            'P6': 0.010432
        },
        '6.2': {
            'P1': 3.292963,
            'P2': 1.867567,
            'P3': 0.491658,
            'P4': 0.299575,
            'P5': 0.011745,
            'P6': 0.010432
        },
        '6.3': {
            'P1': 3.099043,
            'P2': 1.867297,
            'P3': 0.608334,
            'P4': 0.396461,
            'P5': 0.013018,
            'P6': 0.011460
        },
        '6.4': {
            'P1': 2.732620,
            'P2': 1.633705,
            'P3': 0.396742,
            'P4': 0.275775,
            'P5': 0.008201,
            'P6': 0.005465
        }
    },

    2026: {
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
            'P4': 0.424794,
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
}

tepp45 = {
    2025: {
        '2.0': {
            'P1': 0.275041,
            'P2': 0.005297,
            'P3': None,
            'P4': None,
            'P5': None,
            'P6': None
        },
        '3.0': {
            'P1': 0.168944,
            'P2': 0.089294,
            'P3': 0.028322,
            'P4': 0.021656,
            'P5': 0.000806,
            'P6': 0.000717
        },
        '6.1': {
            'P1': 0.272540,
            'P2': 0.144093,
            'P3': 0.054076,
            'P4': 0.038105,
            'P5': 0.009852,
            'P6': 0.008771
        },
        '6.2': {
            'P1': 0.171493,
            'P2': 0.097260,
            'P3': 0.025605,
            'P4': 0.015601,
            'P5': 0.000612,
            'P6': 0.000543
        },
        '6.3': {
            'P1': 0.247625,
            'P2': 0.149204,
            'P3': 0.048608,
            'P4': 0.031679,
            'P5': 0.001040,
            'P6': 0.000916
        },
        '6.4': {
            'P1': 0.185913,
            'P2': 0.111149,
            'P3': 0.026992,
            'P4': 0.018762,
            'P5': 0.000558,
            'P6': 0.000372
        }
    },

    2026: {
        '2.0': {
            'P1': 0.279426,
            'P2': 0.005316,
            'P3': None,
            'P4': None,
            'P5': None,
            'P6': None
        },
        '3.0': {
            'P1': 0.171373,
            'P2': 0.090584,
            'P3': 0.028721,
            'P4': 0.021891,
            'P5': 0.006142,
            'P6': 0.006142
        },
        '6.1': {
            'P1': 0.275735,
            'P2': 0.146094,
            'P3': 0.054668,
            'P4': 0.038455,
            'P5': 0.000817,
            'P6': 0.000722
        },
        '6.2': {
            'P1': 0.173206,
            'P2': 0.097562,
            'P3': 0.025825,
            'P4': 0.015703,
            'P5': 0.000612,
            'P6': 0.000542
        },
        '6.3': {
            'P1': 0.238584,
            'P2': 0.143616,
            'P3': 0.048105,
            'P4': 0.031355,
            'P5': 0.001018,
            'P6': 0.000889
        },
        '6.4': {
            'P1': 0.186364,
            'P2': 0.111026,
            'P3': 0.027859,
            'P4': 0.019355,
            'P5': 0.000575,
            'P6': 0.000394
        }
    }
}

meses = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']

def leer_curva_normalizada(pot_con):
    df_in = st.session_state.df_norm.copy()
    
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
    if st.session_state.frec == 'QH':
        df_in['potencia'] = df_in['consumo'] * 4
    else:
        df_in['potencia'] = df_in['consumo']

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


def detectar_entrada_potencia(df):
    cols = set(df.columns)

    cols_maximetros = {"mes_nom", "P1", "P2", "P3", "P4", "P5", "P6"}
    cols_curva = {"mes_nom", "periodo", "potencia"}

    if cols_maximetros.issubset(cols):
        print('fichero de maximetros')
        return "maximetros"

    if cols_curva.issubset(cols):
        print('fichero de curva')
        return "curva"

    raise ValueError(
        "No se reconoce el formato de entrada. "
        "Debe ser curva con columnas ['mes_nom', 'periodo', 'potencia'] "
        "o tabla de maxímetros con ['mes_nom', 'P1', ..., 'P6']."
    )


def normalizar_tabla_maximetros(df, meses):
    df = df.copy()

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    posibles_col_mes = [
        "mes_nom", "mes", "meses", "fecha", "fechas",
        "periodo", "periodo_facturacion", "rango"
    ]

    col_mes = None
    for c in posibles_col_mes:
        if c in df.columns:
            col_mes = c
            break

    if col_mes is None:
        raise ValueError(
            "No encuentro columna de mes/fecha. Usa una columna tipo MES, mes_nom, fecha o periodo."
        )

    renombrar_periodos = {}

    for c in df.columns:
        c_limpio = c.upper().replace(" ", "").replace("_", "")
        if c_limpio in ["P1", "P2", "P3", "P4", "P5", "P6"]:
            renombrar_periodos[c] = c_limpio

    df = df.rename(columns=renombrar_periodos)

    periodos = ["P1", "P2", "P3", "P4", "P5", "P6"]
    columnas_faltantes = [p for p in periodos if p not in df.columns]

    if columnas_faltantes:
        raise ValueError(
            f"Faltan columnas de periodos: {columnas_faltantes}. "
            "El Excel debe tener P1, P2, P3, P4, P5 y P6."
        )

    mapa_num_mes = dict(zip(range(1, 13), meses))

    mapa_txt_mes = {
        "ene": "ene", "enero": "ene",
        "feb": "feb", "febrero": "feb",
        "mar": "mar", "marzo": "mar",
        "abr": "abr", "abril": "abr",
        "may": "may", "mayo": "may",
        "jun": "jun", "junio": "jun",
        "jul": "jul", "julio": "jul",
        "ago": "ago", "agosto": "ago",
        "sep": "sep", "sept": "sep", "septiembre": "sep",
        "oct": "oct", "octubre": "oct",
        "nov": "nov", "noviembre": "nov",
        "dic": "dic", "diciembre": "dic",
    }

    def convertir_a_mes_nom(valor):
        if pd.isna(valor):
            return None

        if isinstance(valor, (pd.Timestamp, datetime, date)):
            return mapa_num_mes.get(valor.month)

        txt = str(valor).strip().lower()

        # Caso número de mes: 1, 01, 12...
        if txt.isdigit():
            mes_num = int(txt)
            return mapa_num_mes.get(mes_num)

        txt_limpio = (
            txt.replace(".", "")
               .replace("-", " ")
               .replace("_", " ")
               .strip()
        )

        # Caso nombre o abreviatura: enero, ene, feb...
        if txt_limpio in mapa_txt_mes:
            return mapa_txt_mes[txt_limpio]

        # Caso rango o fecha dentro del texto:
        # "01/01/2025 - 31/01/2025"
        # "del 1/1/25 al 31/1/25"
        fechas = re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", txt)

        if fechas:
            fecha = pd.to_datetime(
                fechas[0],
                dayfirst=True,
                errors="coerce"
            )

            if pd.notna(fecha):
                return mapa_num_mes.get(fecha.month)

        # Caso fecha interpretable por pandas
        fecha = pd.to_datetime(
            txt,
            dayfirst=True,
            errors="coerce"
        )

        if pd.notna(fecha):
            return mapa_num_mes.get(fecha.month)

        return None

    df["mes_nom"] = df[col_mes].apply(convertir_a_mes_nom)

    if df["mes_nom"].isna().any():
        filas_malas = df[df["mes_nom"].isna()].index.tolist()
        raise ValueError(
            f"No he podido interpretar el mes en estas filas: {filas_malas}"
        )

    df = df[["mes_nom"] + periodos].copy()

    for p in periodos:
        df[p] = pd.to_numeric(df[p], errors="coerce").fillna(0)

    # Si hay meses duplicados, nos quedamos con el máximo por periodo
    df = (
        df.groupby("mes_nom", as_index=False)[periodos]
        .max()
    )

    df["mes_nom"] = pd.Categorical(
        df["mes_nom"],
        categories=meses,
        ordered=True
    )

    df = df.sort_values("mes_nom").reset_index(drop=True)

    df["mes_nom"] = df["mes_nom"].astype(str)

    return df


# Función para calcular los costes a partir de las potencias
def calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, potencias):
    df_temp = df_in.copy()
    modo_calc = detectar_entrada_potencia(df_temp)
    # ============================================================
    # 1. Coste de potencia facturada
    # ============================================================
    df_coste_potfra_temp = pd.DataFrame(index=meses, columns=potencias.keys())
    for periodo, pot_opt_value in potencias.items():
        df_coste_potfra_temp[periodo] = pot_opt_value * pyc_tp[periodo] / 12
    coste_potfra_temp = df_coste_potfra_temp.sum().sum()
    
    # ============================================================
    # 2. Coste de excesos
    # ============================================================
    if modo_calc == 'curva':
        
        
        # Actualizamos las potencias optimizadas en la columna 'pot_opt'
        df_temp['pot_opt'] = df_temp['periodo'].map(potencias)
        
        # Calculamos los excesos y excesos_cuadrado
        df_temp['excesos_opt'] = np.maximum(df_temp['potencia'] - df_temp['pot_opt'], 0)
        df_temp['excesos_cuad_opt'] = df_temp['excesos_opt'] ** 2
        
        
        
        # Calculamos el coste de excesos
        df_excesos_temp = pd.pivot_table(df_temp, values='excesos_cuad_opt', index='mes_nom', columns='periodo', aggfunc='sum')
        df_excesos_temp = np.sqrt(df_excesos_temp)
        for periodo, x in tepp.items():
            if periodo in df_excesos_temp.columns:
                df_excesos_temp[periodo] = df_excesos_temp[periodo] * x 
    
    elif modo_calc == "maximetros":
        # --------------------------------------------------------
        # Nuevo caso: tabla mensual de maxímetros tipos 4 y 5
        # Espera columnas: mes_nom, P1, P2, P3, P4, P5, P6
        # --------------------------------------------------------

        periodos = list(potencias.keys())

        columnas_necesarias = ["mes_nom"] + periodos
        columnas_faltantes = [c for c in columnas_necesarias if c not in df_temp.columns]

        if columnas_faltantes:
            raise ValueError(
                f"Faltan columnas en la tabla de maxímetros: {columnas_faltantes}"
            )

        df_excesos_temp = df_temp.set_index("mes_nom")[periodos].copy()

        # Convertir maxímetros a numérico por seguridad
        for periodo in periodos:
            df_excesos_temp[periodo] = pd.to_numeric(
                df_excesos_temp[periodo],
                errors="coerce"
            ).fillna(0)

        # Exceso = maxímetro mensual - potencia contratada/optimizada
        for periodo in periodos:
            df_excesos_temp[periodo] = np.maximum(
                df_excesos_temp[periodo] - potencias[periodo],
                0
            )

        # Aplicar coeficientes de exceso específicos, por ejemplo tepp_45
        for periodo, x in tepp.items():
            if periodo in df_excesos_temp.columns:
                df_excesos_temp[periodo] = df_excesos_temp[periodo] * x * 30

    else:
        raise ValueError(f"Modo de cálculo no reconocido: {modo_calc}")


            
    df_excesos_temp.index = pd.Categorical(df_excesos_temp.index, categories=meses, ordered=True)
    #ordenamos
    df_excesos_temp = df_excesos_temp.sort_index()
    coste_excesos_temp = df_excesos_temp.sum().sum()
    # Coste total
    coste_tp_temp = round(coste_potfra_temp + coste_excesos_temp, 2)

    return coste_potfra_temp, coste_excesos_temp, coste_tp_temp, df_coste_potfra_temp, df_excesos_temp


def funcion_objetivo(pot_opt, df_in, tarifa, pyc_tp, tepp, meses, pot_con):
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



#FUNCIÓN GLOBAL PARA OPTIMIZAR++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
def calcular_optimizacion(df_in, fijar_P6, tarifa, pot_con, pyc_tp, tepp):
    coste_potfra_potcon, coste_excesos_potcon, coste_tp_potcon, df_coste_potfra_potcon, df_coste_excesos_potcon = calcular_costes(df_in, tarifa, pyc_tp, tepp, meses, pot_con)
    df_coste_potfra_potcon['coste_pot_mes'] = df_coste_potfra_potcon.sum(axis=1)
    totales_potfra_potcon = df_coste_potfra_potcon.sum()
    totales_potfra_potcon.name = 'total año'
        
    df_coste_excesos_potcon['coste_excesos_mes'] = df_coste_excesos_potcon.sum(axis=1)
    totales_excesos_potcon = df_coste_excesos_potcon.sum()
    totales_excesos_potcon.name = 'total año'
        
    df_coste_tp_mes = pd.concat([df_coste_potfra_potcon['coste_pot_mes'], df_coste_excesos_potcon['coste_excesos_mes']], axis=1)

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
        
    df_coste_potfra_potopt['coste_pot_mes_opt'] = df_coste_potfra_potopt.sum(axis=1)
    df_coste_excesos_potopt['coste_excesos_mes_opt'] = df_coste_excesos_potopt.sum(axis=1)
    totales_potfra_potopt = df_coste_potfra_potopt.sum()
    print(f'total coste potencia a facturar OPTIMIZADA: {totales_potfra_potopt}')
    totales_potfra_potopt.name = 'total año'
        
    totales_excesos_potopt = df_coste_excesos_potopt.sum()
    totales_excesos_potopt.name = 'total año'
    
    df_coste_tp_mes_opt = pd.concat([df_coste_potfra_potopt['coste_pot_mes_opt'], df_coste_excesos_potopt['coste_excesos_mes_opt']], axis=1)
 
    df_coste_tp_mes = pd.concat([df_coste_tp_mes, df_coste_tp_mes_opt,], axis=1)
    
    ahorro_opt = round(coste_tp_potcon - coste_tp_potopt, 2)
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon

    df_potencias = pd.DataFrame({
        'Potencias (kW)': ['Contratadas', 'Optimizadas'],
        'P1': [pot_con['P1'], pot_opt['P1']],
        'P2': [pot_con['P2'], pot_opt['P2']],
        'P3': [pot_con['P3'], pot_opt['P3']],
        'P4': [pot_con['P4'], pot_opt['P4']],
        'P5': [pot_con['P5'], pot_opt['P5']],
        'P6': [pot_con['P6'], pot_opt['P6']],
        'Coste Total (€)': [coste_tp_potcon, coste_tp_potopt]
    })

    df_potencias["Coste Total (€)"] = (
        df_potencias["Coste Total (€)"]
        .astype(float)
        .round(2)
        .apply(lambda x: f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    )
    for columna in ("P1", "P2", "P3", "P4", "P5", "P6"):
        df_potencias[columna] = df_potencias[columna].apply(
            lambda x: f"{float(x):,.0f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )


    #======================================================================
    # DIAGRAMA DE AREAS APILADAS CON FACET COLS
    #======================================================================
    pot_rangos = {}
    for periodo in pot_con.keys():
        min_pot = min(pot_con[periodo], pot_opt[periodo])
        max_pot = max(pot_con[periodo], pot_opt[periodo])
        intervalo = max(1, (max_pot - min_pot) // 10)
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
    fig_periodos = px.area(
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
        color_discrete_map={
            "Coste Potencia": "#636efa",   # azul
            "Coste Excesos":  "#19d3f3",   # verde
        },
        title="Costes de Potencia y Excesos por Periodo"
    )

    fig_periodos.update_layout(
        legend_title_text="Tipo de Coste",
        yaxis_title="Coste (€)",
        xaxis_title="Potencia (kW)",
        margin=dict(l=40, r=20, t=60, b=0),
        #width = 1600
        height = 600,
        autosize = True,
        
    )
    fig_periodos.for_each_annotation(
        lambda a: a.update(text=a.text.replace("Periodo=", ""))
    )
    fig_periodos = aplicar_estilo(fig_periodos)
    fig_periodos.update_layout(
        legend_title_text="",
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.08,
            yanchor="bottom",
        ),
        margin=dict(l=40, r=20, t=105, b=0),
    )

    

    
    
    ahorro_opt = coste_tp_potcon - coste_tp_potopt
    ahorro_opt_porc = ahorro_opt * 100 / coste_tp_potcon
    


    #======================================================================
    # DIAGRAMA DE QUESO CIRCULAR CON DOBLE ANILLO. ES UN GRÁFICO SECUNDARIO
    #======================================================================
    fig_anillo = go.Figure()
    # 🔵 Anillo interior: situación actual
    fig_anillo.add_trace(
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
    fig_anillo.add_trace(
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
    fig_anillo.update_layout(
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

    del df_plot
    del data
    gc.collect()

    return df_coste_tp_mes, coste_tp_potcon, coste_tp_potopt, ahorro_opt, ahorro_opt_porc, df_potencias, fig_periodos, fig_anillo, coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt


#======================================================================
# DIAGRAMA GAUGE DE AHORRO EN %. TIPO VELOCIMETRO
#======================================================================
def graficar_gauge_ahorro(ahorro_opt, ahorro_opt_porc):
    
    
    ahorro_opt_fmt = f"{ahorro_opt:,.0f}".replace(",", ".")
    
    colors = [
        "rgba(204, 255, 204, 0.6)",  # Very light green
        "rgba(144, 238, 144, 0.6)",  # Light green
        "rgba(34, 139, 34, 0.6)",    # Medium green
        "rgba(0, 128, 0, 0.6)",      # Dark green
        "rgba(0, 100, 0, 0.6)"       # Very dark green
    ]
    ahorro_porc_fmt = f"{ahorro_opt_porc:.1f}".replace(".", ",")
    fig_ahorro = go.Figure(go.Indicator(
        mode = "gauge",
        value = ahorro_opt_porc,  # El valor del indicador
        domain = {'x': [0, 1], 'y': [0, 1]},
        #title = {'text': "Ahorro Obtenido (%)", 'font': {'size': 30}},
        title={
            'text': f"Ahorro previsto: {ahorro_opt_fmt} €",
            'font': {'size': 20}
        },
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
        }
    ))
    fig_ahorro.add_annotation(
        x=0.53,
        y=0.17,
        xref="paper",
        yref="paper",
        text=f"<b>{ahorro_porc_fmt} %</b>",
        showarrow=False,
        xanchor="center",
        yanchor="middle",
        font=dict(size=64, color="#00a651"),
    )
    fig_ahorro.update_layout(
        height=250,
        margin=dict(l=5, r=5, t=60, b=5)
    )
    return fig_ahorro


#======================================================================
# DIAGRAMA DE BARRAS RESUMEN COMPARATIVO CONTRATADO VS OPTIMIZADO
#======================================================================
    
def graficar_resumen (coste_potfra_potcon, coste_excesos_potcon, coste_potfra_potopt, coste_excesos_potopt):
    fig_resumen = go.Figure()


    # 🔵 CONTRATADO – Potencia
    fig_resumen.add_trace(
        go.Bar(
            x=["Previsto"],
            y=[coste_potfra_potcon],
            name="Potencia (Previsto)",
            marker_color="lightblue"
        )
    )

    # 🔵 CONTRATADO – Excesos
    fig_resumen.add_trace(
        go.Bar(
            x=["Previsto"],
            y=[coste_excesos_potcon],
            name="Excesos (Previsto)",
            marker_color="blue"
        )
    )

    # 🟢 OPTIMIZADO – Potencia
    fig_resumen.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_potfra_potopt],
            name="Potencia (Optimizado)",
            marker_color="lightgreen"
        )
    )

    # 🟢 OPTIMIZADO – Excesos
    fig_resumen.add_trace(
        go.Bar(
            x=["Optimizado"],
            y=[coste_excesos_potopt],
            name="Excesos (Optimizado)",
            marker_color="green"
        )
    )

    fig_resumen.update_layout(
        barmode="stack",
        title="Resumen de costes: Previsto vs Optimizado",
        yaxis_title="Coste (€)",
        #xaxis_title="Situación",
        legend_title_text="Tipo de coste",
        #height=600,
        margin=dict(t=60, b=40, l=40, r=40)
    )
    fig_resumen = aplicar_estilo(fig_resumen)

    return fig_resumen


def graficar_comparacion_mensual(df_coste_tp_mes):

    fig = go.Figure()

    df = df_coste_tp_mes.copy()

    meses = df.index.astype(str).tolist()
    x = np.arange(len(df))

    ancho = 0.35
    x_actual = x - ancho / 2
    x_opt = x + ancho / 2

    # ACTUAL - potencia
    fig.add_trace(
        go.Bar(
            x=x_actual,
            y=df["coste_pot_mes"],
            width=ancho,
            name="Potencia previsto",
            marker_color="deepskyblue",
            customdata=np.column_stack([meses, df["coste_pot_mes"]]),
            hovertemplate=(
                "<b>Mes:</b> %{customdata[0]}<br>"
                "<b>Escenario:</b> Actual<br>"
                "<b>Coste potencia PREVISTO:</b> %{customdata[1]:,.2f} €"
                "<extra></extra>"
            ),
        )
    )

    # ACTUAL - excesos
    fig.add_trace(
        go.Bar(
            x=x_actual,
            y=df["coste_excesos_mes"],
            width=ancho,
            name="Excesos previsto",
            marker_color="blue",
            base=df["coste_pot_mes"],
            customdata=np.column_stack([meses, df["coste_excesos_mes"]]),
            hovertemplate=(
                "<b>Mes:</b> %{customdata[0]}<br>"
                "<b>Escenario:</b> Actual<br>"
                "<b>Coste de los excesos PREVISTO:</b> %{customdata[1]:,.2f} €"
                "<extra></extra>"
            ),
        )
    )

    # OPTIMIZADO - potencia
    fig.add_trace(
        go.Bar(
            x=x_opt,
            y=df["coste_pot_mes_opt"],
            width=ancho,
            name="Potencia optimizado",
            marker_color="lightgreen",
            customdata=np.column_stack([meses, df["coste_pot_mes_opt"]]),
            hovertemplate=(
                "<b>Mes:</b> %{customdata[0]}<br>"
                "<b>Escenario:</b> Optimizado<br>"
                "<b>Coste potencia OPTIMIZADO:</b> %{customdata[1]:,.2f} €"
                "<extra></extra>"
            ),
        )
    )

    # OPTIMIZADO - excesos
    fig.add_trace(
        go.Bar(
            x=x_opt,
            y=df["coste_excesos_mes_opt"],
            width=ancho,
            name="Coste excesos optimizados",
            marker_color="green",
            base=df["coste_pot_mes_opt"],
            customdata=np.column_stack([meses, df["coste_excesos_mes_opt"]]),
            hovertemplate=(
                "<b>Mes:</b> %{customdata[0]}<br>"
                "<b>Escenario:</b> Optimizado<br>"
                "<b>Coste excesos optimizados:</b> %{customdata[1]:,.2f} €"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        title={
            "text": "Comparativa mensual de costes de potencia: prevista vs optimizada",
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 24}
        },
        xaxis=dict(
            tickmode="array",
            tickvals=x,
            ticktext=meses,
            title="Mes",
        ),
        yaxis_title="Coste (€)",
        barmode="overlay",
        margin=dict(l=40, r=20, t=60, b=40),
        bargap=0.25,
        legend_title=None,
        hovermode="closest",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=.98,
            xanchor="center",
            x=0.5
        )
    )

    fig = aplicar_estilo(fig)

    return fig





