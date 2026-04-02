import pandas as pd
import plotly.express as px
import streamlit as st
from backend_comun import aplicar_estilo


COMPONENTES_SSAA_TOTAL = [
    "balx",
    "bs3",
    "cfp",
    "ct2",
    "ct3",
    "dsv",
    "erad",
    "eradx",
    "exd",
    "in3",
    "in7",
    "mi",
    "pc3",
    "rad1",
    "rad1x",
    "rad3",
    "rt3",
    "rt6",
    "secx"
]

COMPONENTES_SSAA_FORMULA = [
    "balx",
    "bs3",
    "cfp",
    "ct2",
    "ct3",
    "dsv",
    "exd",
    "in7",
    "rad3",
    "rt3",
    "rt6"
]


SRAD_OLD = {
    2022: {
        1: 0.000, 2: 0.000, 3: 0.000, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.000, 8: 0.000,
        9: 0.110, 10: 0.110, 11: 0.110, 12: 0.110,
        13: 0.110, 14: 0.110, 15: 0.110, 16: 0.110,
        17: 0.110, 18: 0.110, 19: 0.110, 20: 0.110,
        21: 0.110, 22: 0.110, 23: 0.110, 24: 0.110,
    },

    2023: {
        1: 0.000, 2: 0.000, 3: 0.000, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.000, 8: 0.000,
        9: 0.225, 10: 0.225, 11: 0.225, 12: 0.225,
        13: 0.225, 14: 0.225, 15: 0.225, 16: 0.225,
        17: 0.225, 18: 0.225,
        19: 0.573, 20: 0.573, 21: 0.573, 22: 0.573,
        23: 0.573, 24: 0.573,
    },

    2024: {
        1: 0.968, 2: 0.688, 3: 0.720, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.657, 8: 0.583,
        9: 0.549, 10: 0.536, 11: 0.537, 12: 0.541,
        13: 0.542, 14: 0.540, 15: 0.544, 16: 0.553,
        17: 0.554, 18: 0.547, 19: 0.535, 20: 0.517,
        21: 0.503, 22: 0.770, 23: 0.829, 24: 0.906,
    },

    2025: {
        1: 1.598, 2: 1.698, 3: 1.777, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 1.599, 8: 1.418,
        9: 1.330, 10: 1.299, 11: 1.294, 12: 1.299,
        13: 1.305, 14: 0.000, 15: 0.000, 16: 0.000,
        17: 0.000, 18: 0.000, 19: 1.284, 20: 1.249,
        21: 1.227, 22: 1.858, 23: 2.003, 24: 2.181,
    },

    2026: {
        1: 0.000, 2: 0.000, 3: 0.000, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.000, 8: 1.984,
        9: 1.831, 10: 1.786, 11: 1.775, 12: 1.796,
        13: 1.819, 14: 1.815, 15: 1.819, 16: 1.844,
        17: 1.860, 18: 1.853, 19: 1.785, 20: 1.732,
        21: 1.711, 22: 2.689, 23: 2.922, 24: 3.244,
    }
}
SRAD = {
    2026: {
        1: 0.000, 2: 0.000, 3: 0.000, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.000, 8: 1.984,
        9: 1.831, 10: 1.786, 11: 1.775, 12: 1.796,
        13: 1.819, 14: 1.815, 15: 1.819, 16: 1.844,
        17: 1.860, 18: 1.853, 19: 1.785, 20: 1.732,
        21: 1.711, 22: 2.689, 23: 2.922, 24: 3.244,
    }
}

FNEE_TRAMOS = [
    ("2023-01-01", 0.264),
    ("2023-03-31", 0.498),
    ("2024-03-24", 0.975),
    ("2025-03-05", 1.429),
    ("2026-03-01", 2.658),
]

def filtrar_datos():
   
    if st.session_state.rango_temporal == 'Por años': 
        df_filtrado = st.session_state.df_sheets[st.session_state.df_sheets['año'] == st.session_state.año_seleccionado]
        lista_meses = df_filtrado['mes_nombre'].unique().tolist()
        print('Filtrado por año')
    elif st.session_state.rango_temporal == 'Por meses': 
        df_filtrado_año = st.session_state.df_sheets[st.session_state.df_sheets['año'] == st.session_state.año_seleccionado]
        df_filtrado = st.session_state.df_sheets[(st.session_state.df_sheets['año'] == st.session_state.año_seleccionado) & (st.session_state.df_sheets['mes_nombre'] == st.session_state.mes_seleccionado)]
        #print('df_filtrado AÑO')
        #print(df_filtrado)
        lista_meses = df_filtrado_año['mes_nombre'].unique().tolist()
        print('Filtrado por mes')
    else:
        #forzamos de nuevo la columna fecha a date para evitar error en el filtrado, ya que dia seleccionado debe ser un date
        #st.session_state.df_sheets['fecha'] = pd.to_datetime(st.session_state.df_sheets['fecha']).dt.date
        
        inicio, fin = st.session_state.dias_seleccionados
        df_filtrado = st.session_state.df_sheets[
            (st.session_state.df_sheets['fecha'] >= inicio) &
            (st.session_state.df_sheets['fecha'] <= fin)
        ]
        lista_meses = None
        print('Filtrado por dia')

    #print('dias seleccionados')
    #print(st.session_state.dias_seleccionados)
    #print("DEBUG tipo dia_seleccionado:", type(st.session_state.get("dias_seleccionados")))
    #print('st session df sheets')
    #print(st.session_state.df_sheets)

    #print ('df_filtrado')
    #print (df_filtrado)
             
    return df_filtrado, lista_meses


# de momento no usado, pero lo dejamos para más adelante
def calcular_ssaa_formula(df):

    df = df.copy()
    df["ssaa"] = df[COMPONENTES_SSAA_FORMULA].sum(axis=1)

    return df


# MONTAMOS UN DF CON SPOT Y SSAA PARA ESCALA CV
def construir_df_spot_ssaa():

    # 🔹 CSV (modelo)
    df_csv = st.session_state.csv_componentes.copy()
    df_csv["ssaa"] = df_csv[COMPONENTES_SSAA_FORMULA].sum(axis=1)

    df_csv = df_csv[["fecha", "año", "mes", "spot", "ssaa"]]

    # 🔹 Sheets (real)
    df_sheets = st.session_state.df_sheets.copy()
    df_sheets = df_sheets[["fecha", "año", "mes", "spot", "ssaa"]]

    # 🔹 última fecha CSV
    fecha_corte = df_csv["fecha"].max()

    # 🔹 cogemos SOLO lo posterior en sheets
    df_sheets = df_sheets[df_sheets["fecha"] > fecha_corte]

    # 🔹 unión limpia
    df_total = pd.concat([df_csv, df_sheets], ignore_index=True)

    print('df spot ssaa total')
    print(df_total)

    return df_total

# NO USADO para sheets original esos id
def construir_df_srad():

    filas = []

    for year, horas in SRAD.items():
        for hora, valor in horas.items():
            filas.append({"año": year, "hora": hora, "srad": valor})

    return pd.DataFrame(filas)

# NO USADO para sheets original esos id
def añadir_srad(df):

    df_srad = construir_df_srad()

    return df.merge(df_srad, on=["año", "hora"], how="left").fillna({"srad": 0.0})

# USADO para añadir RAD3 a los valores provisionales post C2 (en la misma columna). Ver utilidades.py
def construir_df_rad3_manual():

    filas = []

    for year, horas in SRAD.items():
        for hora, valor in horas.items():
            filas.append({
                "año": year,
                "hora": hora,
                "rad3": valor
            })

    return pd.DataFrame(filas)

def añadir_fnee(df):

    df = df.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])

    # convertir tramos a datetime
    tramos = [(pd.to_datetime(f), v) for f, v in FNEE_TRAMOS]

    df["fnee"] = 0.0

    for i, (fecha_inicio, valor) in enumerate(tramos):

        if i < len(tramos) - 1:
            fecha_fin = tramos[i + 1][0]
            mask = (df["fecha"] >= fecha_inicio) & (df["fecha"] < fecha_fin)
        else:
            mask = df["fecha"] >= fecha_inicio

        df.loc[mask, "fnee"] = valor

    return df


def calcular_precios_atr(df):
    
    tm_rate = 0.015
    df = df.copy()
    
    #cols_drop = [c for c in df.columns if c.startswith("coste_") or c.startswith("precio_")]
    #df = df.drop(columns=cols_drop, errors="ignore")

    for atr in ["2.0", "3.0", "6.1"]:

        #if not st.session_state.get("modo_formula_custom", False):

        #    base = (
        #        df["spot"]
        #        + df["ssaa"]
        #        + df[f"ppcc_{atr}"]
        #        + df["osom"]
        #        + df["otros"]
        #    )

        #else:

        base = (
            df["spot"]
            + df["ssaa"]
            + df[f"ppcc_{atr}"]
            + df["osom"]
        )

        #ajuste manual por diferencia de los SSAA id esios con los C2
        base += 0.0

        # componentes opcionales a pérdidas
        base += st.session_state.get("desvios_apant", 0.0)
        #base += df["srad"]
        
        if st.session_state.get("cfg_fnee_pos") == "perdidas":
            base += df["fnee"]

        if st.session_state.get("cfg_margen_pos") == "perdidas":
            base += st.session_state.get("margen_telemindex", 0.0)

        # base pérdidas
        base *= (1 + df[f"perd_{atr}"])

        # componentes opcionales a tm
        if st.session_state.get("cfg_margen_pos") == "tm":
            base += st.session_state.get("margen_telemindex", 0.0)
        
        if st.session_state.get("cfg_fnee_pos") == "tm":
            base += df["fnee"]

        # base tm
        base *= (1 + tm_rate)

        # CF
        cf = st.session_state.get("cf_pct", 0.0) / 100
        base *= (1 + cf)

        # coste de la energía según atr
        df[f"coste_{atr}"] = base


        # componentes opcionales en neto

        if st.session_state.get("cfg_fnee_pos") == "neto":
            base += df["fnee"]
        
        if st.session_state.get("cfg_margen_pos") == "neto":
            base += st.session_state.get("margen_telemindex", 0.0)

        # precio final con pycs según atr
        df[f"precio_{atr}"] = base + df[f"pyc_{atr}"]
        
        #precio = base + df[f"pyc_{atr}"]

        #if (not st.session_state.get("modo_formula_custom", False) or st.session_state.get("cfg_margen_pos") == "neto"):
        #    precio += st.session_state.get("margen_telemindex", 0.0)

        # precio final según atr
        #df[f"precio_{atr}"] = precio

        print('df sheets con costes y precios')
        print(df)

    return df






# CREAMOS TABLA CON PRECIOS MEDIOS HORARIOS
def tabla_precios_medios_horarios(df):
    return df.pivot_table(
        values=['spot', 'ssaa', 'precio_2.0', 'precio_3.0', 'precio_6.1'],
        index='hora',
        aggfunc='mean'
    ).reset_index()


# GRAFICO PRINCIPAL CON LAS BARRAS DE OMIE Y SSAA Y LAS LINEAS DE PRECIO FINAL. HORARIAS
def graficar_precios_medios_horarios(df_filtrado, colores_precios):
    #pt2 = pt1(df_filtrado)[0]
    pt2 = tabla_precios_medios_horarios(df_filtrado)
    #print('pt2')
    #print(pt2)
    
    graf_pt1=px.line(pt2,x='hora',y=['precio_2.0','precio_3.0','precio_6.1'],
        height=600,
        labels={'value':'€/MWh','variable':'Precios según ATR'},
        color_discrete_map=colores_precios,
    )
    graf_pt1.update_traces(line=dict(width=4))
   
    graf_pt1.update_layout(
        margin=dict(t=100),
        #title_font_size=16,
        #title={'x':.5,'xanchor':'center'},
        xaxis=dict(
              tickmode='array',
              tickvals=pt2['hora']
        ),
        #barmode = 'stack'
        barmode = 'relative'
    )
    graf_pt1 = graf_pt1.add_bar(y = pt2['spot'], name = 'spot', marker_color = 'green', width = 0.5)
    #graf_pt1 = graf_pt1.add_bar(y = pt2['ssaa'], name = 'ssaa', marker_color = 'lightgreen', width = 0.5)
    graf_pt1 = graf_pt1.add_bar(y = pt2['ssaa'], name = 'ssaa', marker_color = '#5f259f', width = 0.5)

        # ---- LÍNEA CURVA PERSONALIZADA ----
    if ("df_curva_sheets" in st.session_state and st.session_state.df_curva_sheets is not None and "coste_total" in st.session_state.df_curva_sheets.columns):
        dfc = st.session_state.df_curva_sheets.copy()

        # consumo en MWh
        dfc["consumo_MWh"] = dfc["consumo_neto_kWh"] / 1000

        # precio medio ponderado horario real en €/MWh
        curva = (
            dfc.groupby("hora")
            .apply(lambda g: g["coste_total"].sum() / g["consumo_MWh"].sum())
            .reset_index(name="precio_medio_horario")
        )

        #curva = curva_sin_margen.copy()
        #curva['precio_medio_horario']+=st.session_state.margen_telemindex

        # ---- Color dinámico según ATR seleccionado ----
        atr = st.session_state.atr_dfnorm           # "2.0", "3.0" o "6.1"
        clave_color = f"precio_{atr}"               # "precio_2.0", ...
        color_curva = colores_precios[clave_color]  # color correcto    

        graf_pt1.add_scatter(
            x=curva["hora"],
            y=curva["precio_medio_horario"],
            mode="lines",
            name=f'precio_{atr}_curva',
            line=dict(color=color_curva, width=6, dash="dot")
        )

    return graf_pt1


def construir_pie_atr_generico(df, atr, color_scale, titulo):

    pt = df.pivot_table(
        values=['spot', 'ssaa', 'osom', f'ppcc_{atr}', f'perd_{atr}', f'pyc_{atr}'],
        index='año',
        aggfunc='mean'
    )

    pt['comp_perd'] = (
        pt['spot'] + pt['ssaa'] + pt['osom'] + pt[f'ppcc_{atr}']
        #pt['spot'] + pt['ssaa'] + pt['osom'] + pt['otros'] + pt[f'ppcc_{atr}']
        #pt['otros'] + pt[f'ppcc_{atr}']
    )

    pt[f'perdidas_{atr}'] = pt['comp_perd'] * pt[f'perd_{atr}']

    pt['precio_total'] = df.pivot_table(
        values=f'precio_{atr}',
        index='año',
        aggfunc='mean'
    )

    pt['otros'] = (
        pt['precio_total']
        - (
            pt['spot'] +
            pt['ssaa'] +
            pt['osom'] +
            pt[f'ppcc_{atr}'] +
            pt[f'perdidas_{atr}'] +
            pt[f'pyc_{atr}']
        )
    )

    #pt = pt.drop(columns=[f'perd_{atr}', 'comp_perd'])
    pt = pt.drop(columns=[f'perd_{atr}', 'comp_perd', 'precio_total'])

    pt_trans = pt.transpose().reset_index()
    pt_trans = pt_trans.rename(columns={'index': 'componente', pt_trans.columns[1]: 'valor'})

    pt_trans = pt_trans.sort_values(by='valor', ascending=False)

    graf = px.pie(
        pt_trans,
        names='componente',
        values='valor',
        hole=.3,
        color_discrete_sequence=color_scale
    )

    graf.update_layout(
        title={'text': titulo, 'x': .5, 'xanchor': 'center'}
    )

    return graf


def graficar_queso_componentes(df_filtrado):

    golden_seq_r = [
            "#8B6508",
            "#B8860B",
            "#DAA520",
            "#F4C430",
            "#FFD700",
            "#FFF4B0"
        ]
    
    graf20 = construir_pie_atr_generico(
        df_filtrado, "2.0",
        #px.colors.sequential.Oranges_r,
        golden_seq_r,
        "Peaje de acceso 2.0"
    )

    graf30 = construir_pie_atr_generico(
        df_filtrado, "3.0",
        px.colors.sequential.Reds_r,
        "Peaje de acceso 3.0"
    )

    graf61 = construir_pie_atr_generico(
        df_filtrado, "6.1",
        px.colors.sequential.Blues_r,
        "Peaje de acceso 6.1"
    )

    return graf20, graf30, graf61


def construir_tabla_resumen(
    df,
    col_base_prefix,      # "precio", "coste", "pyc"
    col_curva,            # "coste_total", "coste_base", "coste_pyc"
    etiqueta,             # "precio", "coste", "pyc"
    decimals=1
):

    dffm = df.copy()

    # --- Pivot 3P ---
    pt3 = dffm.pivot_table(
        values=[f"{col_base_prefix}_2.0"],
        aggfunc="mean",
        index="dh_3p"
    )

    # --- Pivot 6P ---
    pt4 = dffm.pivot_table(
        values=[f"{col_base_prefix}_3.0", f"{col_base_prefix}_6.1"],
        aggfunc="mean",
        index="dh_6p"
    )

    pt = pd.concat([pt3, pt4], axis=1)

    medias = [
        dffm[f"{col_base_prefix}_2.0"].mean(),
        dffm[f"{col_base_prefix}_3.0"].mean(),
        dffm[f"{col_base_prefix}_6.1"].mean()
    ]

    pt_trans = pt.transpose()
    pt_trans["Media"] = medias

    media_curva = None
    
    # ---- CURVA ----
    if "df_curva_sheets" in st.session_state and st.session_state.df_curva_sheets is not None:

        dfc = st.session_state.df_curva_sheets.copy()

        media_curva = (
            dfc[col_curva].sum() /
            dfc["consumo_neto_kWh"].sum()
        ) * 1000

        atr = st.session_state.atr_dfnorm

        if atr == "2.0":
            fila_curva = (
                dfc.groupby("dh_3p")
                .apply(lambda g: (g[col_curva].sum() / g["consumo_neto_kWh"].sum()) * 1000)
            )
        else:
            fila_curva = (
                dfc.groupby("dh_6p")
                .apply(lambda g: (g[col_curva].sum() / g["consumo_neto_kWh"].sum()) * 1000)
            )

        periodos = pt_trans.columns[:-1]
        fila_curva = fila_curva.reindex(periodos)

        pt_trans.loc[f"{etiqueta}_{atr}_curva", periodos] = fila_curva.values
        pt_trans.loc[f"{etiqueta}_{atr}_curva", "Media"] = media_curva

    pt_trans = pt_trans.div(10)
    pt_trans = pt_trans.round(decimals)
    pt_trans = pt_trans.apply(pd.to_numeric, errors="coerce")

    return pt_trans, media_curva

def tabla_precios(df):
    return construir_tabla_resumen(
        df,
        col_base_prefix="precio",
        col_curva="coste_total",
        etiqueta="precio",
        decimals=4
    )

def tabla_costes(df):
    return construir_tabla_resumen(
        df,
        col_base_prefix="coste",
        col_curva="coste_base",
        etiqueta="coste",
        decimals=1
    )

def tabla_pyc(df):
    return construir_tabla_resumen(
        df,
        col_base_prefix="pyc",
        col_curva="coste_pyc",
        etiqueta="pyc",
        decimals=1
    )



        
def evol_mensual (df, colores_precios):

    #dffm = aplicar_margen(df)
    dffm = df

    orden_meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    mes_a_num = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio":7, "agosto":8,
        "septiembre":9, "octubre":10, "noviembre":11, "diciembre":12
    }

    # Asegúrate de que los nombres de meses estén ordenados
    dffm["mes_nombre"] = pd.Categorical(
        dffm["mes_nombre"],
        categories=orden_meses,
        ordered=True
    )
    
    df_precios_mensuales = dffm.pivot_table(
        values = ['precio_2.0', 'precio_3.0', 'precio_6.1'],
        index = ['año','mes_nombre'],
        aggfunc = 'mean'
    ).reset_index()

    # Crear columna fecha
    df_precios_mensuales["mes_num"] = df_precios_mensuales["mes_nombre"].map(mes_a_num)
    df_precios_mensuales["fecha"] = pd.to_datetime(
        df_precios_mensuales["año"].astype(str) + "-" + df_precios_mensuales["mes_num"].astype(str) + "-01"
    )

    # Convertir a formato largo
    df_melted = df_precios_mensuales.melt(
        #id_vars=['año','mes_nombre'],
        id_vars=['fecha'],
        value_vars=['precio_2.0','precio_3.0','precio_6.1'],
        var_name='Tarifa',
        value_name='Precio medio'
    )

    # Limpiar etiquetas
    df_melted["Tarifa"] = df_melted["Tarifa"].str.replace("precio_", "Peaje ")
    df_melted['Precio medio'] /= 10
    df_melted['Precio medio'] = df_melted['Precio medio'].round(1)

    print('df medias mensuales')
    print(df_melted)

    colores_precios = {'Peaje 2.0': 'goldenrod', 'Peaje 3.0': 'darkred', 'Peaje 6.1': '#1C83E1'}

    graf_mensual = px.line(df_melted, #df_precios_mensuales,
        #x=[df_precios_mensuales["año"], df_precios_mensuales["mes_nombre"]],
        #x = 'año_mes',
        #x=['año','mes_nombre'],
        x='fecha',
        #y=['precio_2.0','precio_3.0','precio_6.1'],
        y='Precio medio',
        color='Tarifa',
        #height=600,
        #title=f'Telemindex {st.session_state.año_seleccionado}: Precios medios horarios de indexado según tarifas de acceso',
        #labels={'value':'c€/kWh','variable':'Precios según ATR'},
        color_discrete_map=colores_precios,
        
    )
    graf_mensual.update_yaxes(
        rangemode="tozero",
        showgrid = True,
        title_text ='Precio medio c€/kWh'
        )
    
    graf_mensual.update_xaxes(
        showgrid = True,
        dtick = 'M1', 
        tickformat="%b%y",  # formato tipo Jan25
        title_text ='Mes'
        )
    
    # 🔥 Activar modo de hover unificado por eje X
    graf_mensual.update_layout(hovermode="x unified")
    

    return df_precios_mensuales, graf_mensual


def construir_df_curva_sheets(df_filtrado):
    """
    Construye un nuevo df combinando la curva normalizada (df_norm_h)
    con los datos filtrados del Sheets.
    """
    
    df_norm = st.session_state.df_norm_h.copy()
    #df_norm = df_norm_h.copy()

    # Asegurar que 'fecha' es date en ambos DF
    df_norm["fecha"] = pd.to_datetime(df_norm["fecha"]).dt.date
    df_filtrado["fecha"] = pd.to_datetime(df_filtrado["fecha"]).dt.date

    # Unión por fecha + hora
    df = df_norm.merge(
        df_filtrado,
        on=["fecha", "hora"],
        how="left"
    )

    print('df curva sheets construida en la función')
    print(df)

    return df


def añadir_costes_curva(df):
    df = df.copy()

    cons = df["consumo_neto_kWh"] / 1000
    atr = st.session_state.atr_dfnorm
    col_precio = f"precio_{atr}"

    # Costes ponderados
    df["coste_spot"] = df["spot"] * cons #usado para apuntamiento
    df["coste_ssaa"] = df["ssaa"] * cons #usado para apuntamiento
    df["coste_pyc"] = df[f"pyc_{atr}"] * cons #usado para tablas
    df["coste_base"] = df[f"coste_{atr}"] * cons #sin pycs ni margen
    df["coste_total"] = df[col_precio] * cons

    return df


def check_medias(df, atr="2.0"):
    
    print("---- MEDIAS COMPONENTES ----")
    
    print("SPOT:", df["spot"].mean())
    print("SSAA:", df["ssaa"].mean())
    print("RAD3:", df["rad3"].mean())
    print("CT2:", df["ct2"].mean())
    print("OSOM:", df["osom"].mean())
    print(f"PPCC_{atr}:", df[f"ppcc_{atr}"].mean())
    print(f"PYC_{atr}:", df[f"pyc_{atr}"].mean())


import pandas as pd
import statsmodels.api as sm
import plotly.express as px

def analizar_dependencia_omie(df_sheets):

    df = df_sheets.copy()

    # -----------------------------
    # PREPARACIÓN
    # -----------------------------
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["año"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month

    # agregación mensual
    df_mensual = (
        df.groupby(["año", "mes"], as_index=False)
        .agg({
            "spot": "mean",
            "precio_2.0": "mean"
        })
    )

    resultados = []

    # -----------------------------
    # CÁLCULO POR AÑO
    # -----------------------------
    for año in sorted(df_mensual["año"].unique()):

        df_year = df_mensual[df_mensual["año"] == año]

        # evitar años con pocos datos
        if len(df_year) < 2:
            continue

        X = sm.add_constant(df_year["spot"])
        y = df_year["precio_2.0"]

        model = sm.OLS(y, X).fit()

        slope = model.params["spot"]

        elasticidad = (slope * df_year["spot"].mean()) / df_year["precio_2.0"].mean()

        #peso_spot = (df_year["spot"] * slope).mean() / df_year["precio_2.0"].mean()
        peso_spot = df_year["spot"].mean() / df_year["precio_2.0"].mean()

        resultados.append({
            "año": año,
            "elasticidad": elasticidad,
            "peso_spot": peso_spot,
            "slope": slope
        })

    df_res = pd.DataFrame(resultados)

    # -----------------------------
    # GRÁFICO
    # -----------------------------
    fig = px.line(
        df_res,
        x="año",
        y=["elasticidad", "peso_spot"],
        markers=True,
        title="Evolución de la dependencia del OMIE"
    )

    fig.update_layout(
        title={"x": 0.5, "xanchor": "center"},
        yaxis_title="Ratio",
        xaxis_title="Año"
    )

    return df_res, fig


import pandas as pd
import statsmodels.api as sm
import plotly.express as px

def visualizar_impacto_omie(df_sheets, atr="2.0"):

    df = df_sheets.copy()

    # -----------------------------
    # PREPARACIÓN
    # -----------------------------
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["año"] = df["fecha"].dt.year
    df["mes"] = df["fecha"].dt.month

    df_mensual = (
        df.groupby(["año", "mes"], as_index=False)
        .agg({
            "spot": "mean",
            f"precio_{atr}": "mean"
        })
    )

    resultados = []

    # -----------------------------
    # CÁLCULO POR AÑO
    # -----------------------------
    for año in sorted(df_mensual["año"].unique()):

        df_year = df_mensual[df_mensual["año"] == año]

        if len(df_year) < 2:
            continue

        X = sm.add_constant(df_year["spot"])
        y = df_year[f"precio_{atr}"]

        model = sm.OLS(y, X).fit()

        intercept = model.params["const"]
        slope = model.params["spot"]

        # -----------------------------
        # EJEMPLO AUTOMÁTICO
        # -----------------------------
        omie_ini = df_year["spot"].max()
        omie_fin = df_year["spot"].min()

        precio_ini = intercept + slope * omie_ini
        precio_fin = intercept + slope * omie_fin

        var_omie = (omie_fin - omie_ini) / omie_ini * 100
        var_precio = (precio_fin - precio_ini) / precio_ini * 100

        resultados.append({
            "año": año,
            "omie_ini": omie_ini,
            "omie_fin": omie_fin,
            "precio_ini": precio_ini,
            "precio_fin": precio_fin,
            "var_omie": var_omie,
            "var_precio": var_precio
        })

    df_res = pd.DataFrame(resultados)

    # -----------------------------
    # GRÁFICO
    # -----------------------------
    fig = px.bar(
        df_res,
        x="año",
        y=["var_omie", "var_precio"],
        barmode="group",
        title="Impacto del OMIE en el precio final"
    )

    fig.update_layout(
        title={'x':0.5, 'xanchor':'center'},
        yaxis_title="Variación (%)",
        xaxis_title="Año"
    )

    return df_res, fig

import plotly.graph_objects as go

def grafico_elasticidad_lineal(df_res):

    fig = go.Figure()

    # rango en eje X (variación OMIE)
    x_vals = [0, 1]  # 1 = 100% cambio relativo

    for _, row in df_res.iterrows():

        año = int(row["año"])
        elasticidad = row["elasticidad"]

        y_vals = [0, elasticidad]

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='lines+markers+text',
            name=str(año),
            text=[None, f"{año}"],
            textposition="top right",
            textfont=dict(size=20)  #
        ))

    fig.update_layout(
        title="Relación OMIE → Precio final (elasticidad)",
        xaxis_title="Variación relativa OMIE (%)",
        yaxis_title="Variación relativa Precio (%)",
        title_x=0.5,
        showlegend=False,
        width=700,
        height=500
    )
    fig = aplicar_estilo(fig)

    fig.update_layout(margin=dict(r=80))
    fig.update_xaxes(range=[0, 1.2])
    fig.update_yaxes(range=[0, 0.7])

    return fig