import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import statsmodels.api as sm
import streamlit as st
import numpy as np
from backend_comun import aplicar_estilo, aplicar_texto_pie_porcentaje


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

# NO USADO
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

# media RAD3 del 2026 hasta abril incluido, usado para complementar hasta nuevo C2
SRAD = {
    2026: {
        1: 0.000, 2: 0.000, 3: 0.000, 4: 0.000,
        5: 0.000, 6: 0.000, 7: 0.000, 8: 2.374,
        9: 2.228, 10: 2.183, 11: 2.196, 12: 2.244,
        13: 2.284, 14: 2.289, 15: 2.301, 16: 2.339,
        17: 2.351, 18: 2.320, 19: 2.260, 20: 2.165,
        21: 2.117, 22: 3.210, 23: 3.472, 24: 3.788,
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
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.date

    # convertir tramos a date
    tramos = [(pd.to_datetime(f).date(), v) for f, v in FNEE_TRAMOS]

    df["fnee"] = 0.0

    for i, (fecha_inicio, valor) in enumerate(tramos):

        if i < len(tramos) - 1:
            fecha_fin = tramos[i + 1][0]
            mask = (df["fecha"] >= fecha_inicio) & (df["fecha"] < fecha_fin)
        else:
            mask = df["fecha"] >= fecha_inicio

        df.loc[mask, "fnee"] = valor

    return df



def calcular_precios_atr_yanoseusaqui(df):
    
    tm_rate = 0.015
    cf = st.session_state.get("cf_pct", 0.0) / 100
    margen = st.session_state.get("margen_telemindex", 0.0)
    df = df.copy()

    for atr in ["2.0", "3.0", "6.1"]:

        base = (
            df["spot"]
            + df["ssaa"]
            + df[f"ppcc_{atr}"]
            + df["osom"]
        )

        # ajuste manual por diferencia de los SSAA id esios con los C2
        base += 0.0

        # componente fijo antes de pérdidas
        base += st.session_state.get("desvios_apant", 0.0)

        # FNEE en pérdidas
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "perdidas":
            base += df["fnee"]

        # duplicamos base: una para coste y otra para precio
        base_coste = base.copy()
        base_precio = base.copy()

        # margen en pérdidas: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "perdidas":
            df[f"margen_{atr}"] = margen * (1 + df[f"perd_{atr}"]) * (1 + tm_rate) * (1 + cf)
            base_precio += margen

        # pérdidas
        base_coste *= (1 + df[f"perd_{atr}"])
        base_precio *= (1 + df[f"perd_{atr}"])

        # margen en tm: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "tm":
            df[f"margen_{atr}"] = margen * (1 + tm_rate) * (1 + cf)
            base_precio += margen

        # FNEE en tm
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "tm":
            base_coste += df["fnee"]
            base_precio += df["fnee"]

        # tm
        base_coste *= (1 + tm_rate)
        base_precio *= (1 + tm_rate)

        # cf
        base_coste *= (1 + cf)
        base_precio *= (1 + cf)

        # FNEE en neto
        if st.session_state.get("cfg_fnee", False) and st.session_state.get("cfg_fnee_pos") == "neto":
            base_coste += df["fnee"]
            base_precio += df["fnee"]

        # margen en neto: solo entra en precio
        if st.session_state.get("cfg_margen_pos") == "neto":
            df[f"margen_{atr}"] = margen
            base_precio += margen

        # coste sin margen
        df[f"coste_{atr}"] = base_coste

        # precio final con margen y pyc
        df[f"precio_{atr}"] = base_precio + df[f"pyc_{atr}"]

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

    pt2 = tabla_precios_medios_horarios(df_filtrado)

    # =========================
    # Curva personalizada
    # =========================
    atr = None
    col_curva = None

    

    if (
        "df_curva_sheets" in st.session_state
        and st.session_state.df_curva_sheets is not None
        and "coste_total" in st.session_state.df_curva_sheets.columns
    ):
        atr = st.session_state.atr_dfnorm
        col_curva = f"precio_{atr}_curva"
        dfc = st.session_state.df_curva_sheets.copy()

        # Consumo en MWh
        dfc["consumo_MWh"] = dfc["consumo_neto_kWh"] / 1000
        
        # Evitar divisiones por cero
        curva = (
            dfc.groupby("hora")
            .apply(
                lambda g: (
                    g["coste_total"].sum() / g["consumo_MWh"].sum()
                    if g["consumo_MWh"].sum() != 0
                    else None
                )
            )
            .reset_index(name=col_curva)
        )

        pt2 = pt2.merge(curva, on="hora", how="left")

    # =========================
    # Columnas para hover
    # =========================
    columnas_hover = [
        "hora",
        "spot",
        "ssaa",
        "precio_2.0",
        "precio_3.0",
        "precio_6.1"
    ]

    if col_curva in pt2.columns:
        columnas_hover.append(col_curva)

    customdata = pt2[columnas_hover].to_numpy()
    idx = {col: i for i, col in enumerate(columnas_hover)}

    hovertemplate = (
        "<b>Hora %{customdata[" + str(idx["hora"]) + "]:02.0f}:00</b><br><br>"
        "spot: %{customdata[" + str(idx["spot"]) + "]:.2f} €/MWh<br>"
        "ssaa: %{customdata[" + str(idx["ssaa"]) + "]:.2f} €/MWh<br>"
        "precio_2.0: %{customdata[" + str(idx["precio_2.0"]) + "]:.2f} €/MWh<br>"
        "precio_3.0: %{customdata[" + str(idx["precio_3.0"]) + "]:.2f} €/MWh<br>"
        "precio_6.1: %{customdata[" + str(idx["precio_6.1"]) + "]:.2f} €/MWh"
    )

    if col_curva in idx:
        hovertemplate += (
            "<br>" + col_curva + ": "
            "%{customdata[" + str(idx[col_curva]) + "]:.2f} €/MWh"
        )

    hovertemplate += "<extra></extra>"

    # =========================
    # Figura base: líneas ATR
    # =========================
    graf_pt1 = px.line(
        pt2,
        x="hora",
        y=["precio_2.0", "precio_3.0", "precio_6.1"],
        height=600,
        labels={
            "value": "€/MWh",
            "variable": "Precios según ATR"
        },
        color_discrete_map=colores_precios,
    )

    # Quitamos hover de las líneas reales
    graf_pt1.update_traces(
        line=dict(width=4),
        hoverinfo="skip",
        hovertemplate=None
    )

    # =========================
    # Layout
    # =========================
    graf_pt1.update_layout(
        margin=dict(t=10),
        xaxis=dict(
            tickmode="array",
            tickvals=pt2["hora"]
        ),
        barmode="relative",
        #hovermode="x unified",
        hovermode="x",
        title=""
    )

    # =========================
    # Barras spot y ssaa
    # =========================
    graf_pt1.add_bar(
        x=pt2["hora"],
        y=pt2["spot"],
        name="spot",
        marker_color="green",
        width=0.5,
        hoverinfo="skip",
        hovertemplate=None
    )

    graf_pt1.add_bar(
        x=pt2["hora"],
        y=pt2["ssaa"],
        name="ssaa",
        marker_color="#5f259f",
        width=0.5,
        hoverinfo="skip",
        hovertemplate=None
    )

    # =========================
    # Línea curva personalizada
    # =========================
    if col_curva in pt2.columns:

        clave_color = f"precio_{atr}"
        color_curva = colores_precios.get(clave_color, "white")

        graf_pt1.add_scatter(
            x=pt2["hora"],
            y=pt2[col_curva],
            mode="lines",
            name=col_curva,
            line=dict(
                color=color_curva,
                width=6,
                dash="dot"
            ),
            hoverinfo="skip",
            hovertemplate=None
        )

    # =========================
    # Traza invisible SOLO para hover unificado
    # =========================
    graf_pt1.add_scatter(
        x=pt2["hora"],
        y=pt2["precio_2.0"],
        mode="markers",
        marker=dict(
            size=1,
            color="rgba(0,0,0,0)"
        ),
        name="",
        showlegend=False,
        customdata=customdata,
        hovertemplate=hovertemplate
    )

    graf_pt1 = aplicar_estilo(graf_pt1)

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
        df_filtrado,
        "2.0",
        golden_seq_r,
        "Peaje de acceso 2.0"
    )

    graf20.update_traces(
        hovertemplate=(
            "<b>Componente:</b> %{label}<br>"
            "<b>Coste:</b> %{value:.2f} €"
            "<extra></extra>"
        )
    )
    graf20 = aplicar_texto_pie_porcentaje(graf20, size=18)

    graf20 = aplicar_estilo(graf20)


    graf30 = construir_pie_atr_generico(
        df_filtrado,
        "3.0",
        px.colors.sequential.Reds_r,
        "Peaje de acceso 3.0"
    )
    graf30 = aplicar_texto_pie_porcentaje(graf30, size=18)
    graf30.update_traces(
        hovertemplate=(
            "<b>Componente:</b> %{label}<br>"
            "<b>Coste:</b> %{value:.2f} €"
            "<extra></extra>"
        )
    )

    graf30 = aplicar_estilo(graf30)


    graf61 = construir_pie_atr_generico(
        df_filtrado,
        "6.1",
        px.colors.sequential.Blues_r,
        "Peaje de acceso 6.1"
    )
    graf61 = aplicar_texto_pie_porcentaje(graf61, size=18)
    graf61.update_traces(
        hovertemplate=(
            "<b>Componente:</b> %{label}<br>"
            "<b>Coste:</b> %{value:.2f} €"
            "<extra></extra>"
        )
    )

    graf61 = aplicar_estilo(graf61)

    return graf20, graf30, graf61

def graficar_queso_componentes_old(df_filtrado):

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
    graf20=aplicar_estilo(graf20)

    graf30 = construir_pie_atr_generico(
        df_filtrado, "3.0",
        px.colors.sequential.Reds_r,
        "Peaje de acceso 3.0"
    )
    graf30=aplicar_estilo(graf30)

    graf61 = construir_pie_atr_generico(
        df_filtrado, "6.1",
        px.colors.sequential.Blues_r,
        "Peaje de acceso 6.1"
    )
    graf61=aplicar_estilo(graf61)

    return graf20, graf30, graf61


def construir_tabla_resumen(
    df,
    col_base_prefix,      # "precio", "coste", "pyc", "margen"
    col_curva,            # "coste_total", "coste_base", "coste_pyc", "coste_margen"
    etiqueta,             # "precio", "coste", "pyc", "margen"
    decimals=4
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
        decimals=4
    )

def tabla_pyc(df):
    return construir_tabla_resumen(
        df,
        col_base_prefix="pyc",
        col_curva="coste_pyc",
        etiqueta="pyc",
        decimals=4
    )

def tabla_margen(df):
    return construir_tabla_resumen(
        df,
        col_base_prefix="margen",
        col_curva="coste_margen",
        etiqueta="margen",
        decimals=4
    )

        
def evol_mensual(df, colores_precios):

    dffm = df.copy()

    orden_meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    mes_a_num = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }

    dffm["mes_nombre"] = pd.Categorical(
        dffm["mes_nombre"],
        categories=orden_meses,
        ordered=True
    )

    # =====================================================
    # 0. COMPROBAR SI HAY CURVA CARGADA
    # =====================================================
    hay_curva_sheets = (
        "df_curva_sheets" in st.session_state
        and st.session_state.df_curva_sheets is not None
        and not st.session_state.df_curva_sheets.empty
    )

    # =====================================================
    # 1. PRECIOS MEDIOS MENSUALES SIN PONDERAR
    # =====================================================
    df_precios_mensuales = dffm.pivot_table(
        values=["spot", "precio_2.0", "precio_3.0", "precio_6.1"],
        index=["año", "mes_nombre"],
        aggfunc="mean"
    ).reset_index()

    # =====================================================
    # 2. PRECIO CURVA: COSTE TOTAL / CONSUMO
    #    Solo si existe curva cargada
    # =====================================================
    if hay_curva_sheets:

        cols_necesarias = [
            "año",
            "mes_nombre",
            "consumo_neto_kWh",
            "coste_total"
        ]

        if all(col in dffm.columns for col in cols_necesarias):

            df_curva = (
                dffm
                .groupby(["año", "mes_nombre"], observed=False)
                .agg(
                    consumo_neto_kWh=("consumo_neto_kWh", "sum"),
                    coste_total=("coste_total", "sum")
                )
                .reset_index()
            )

            df_curva["precio_curva"] = np.where(
                df_curva["consumo_neto_kWh"] > 0,
                df_curva["coste_total"] / df_curva["consumo_neto_kWh"] * 1000,
                np.nan
            )

            df_precios_mensuales = df_precios_mensuales.merge(
                df_curva[["año", "mes_nombre", "precio_curva", "consumo_neto_kWh","coste_total",]],
                on=["año", "mes_nombre"],
                how="left"
            )

    # =====================================================
    # 3. CREAR COLUMNA FECHA
    # =====================================================
    df_precios_mensuales["mes_num"] = (
        df_precios_mensuales["mes_nombre"]
        .astype(str)
        .map(mes_a_num)
    )

    df_precios_mensuales["año"] = pd.to_numeric(
        df_precios_mensuales["año"],
        errors="coerce"
    ).astype("Int64")

    df_precios_mensuales["mes_num"] = pd.to_numeric(
        df_precios_mensuales["mes_num"],
        errors="coerce"
    ).astype("Int64")

    df_precios_mensuales["fecha"] = pd.to_datetime(
        dict(
            year=df_precios_mensuales["año"],
            month=df_precios_mensuales["mes_num"],
            day=1
        ),
        errors="coerce"
    )

    # =====================================================
    # 4. PASAR DE €/MWh A c€/kWh
    # =====================================================
    columnas_precio = [
        "spot",
        "precio_2.0",
        "precio_3.0",
        "precio_6.1"
    ]

    if hay_curva_sheets and "precio_curva" in df_precios_mensuales.columns:
        columnas_precio.append("precio_curva")

    for col in columnas_precio:
        if col in df_precios_mensuales.columns:
            df_precios_mensuales[col] = df_precios_mensuales[col] / 10
            df_precios_mensuales[col] = df_precios_mensuales[col].round(2)

    # =====================================================
    # 5. ATR ACTUAL
    # =====================================================
    atr_actual = st.session_state.get("atr_dfnorm", None)
    print (f'atr actual: {atr_actual}')

    # =====================================================
    # 6. COLORES
    # =====================================================
    colores_precios = {
        "Peaje 2.0": "goldenrod",
        "Peaje 3.0": "darkred",
        "Peaje 6.1": "#1C83E1",
        "Precio curva": "white"
    }

    # =====================================================
    # 7. GRÁFICO MIXTO: SPOT BARRA + PRECIOS LÍNEAS
    # =====================================================
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=df_precios_mensuales["fecha"],
            y=df_precios_mensuales["spot"],
            name="SPOT",
            marker_color="green",
            width=1000 * 60 * 60 * 24 * 8,
            opacity=0.65,
            hovertemplate="SPOT: %{y:.2f} c€/kWh<extra></extra>"
        )
    )

    series_lineas = {
        "Peaje 2.0": "precio_2.0",
        "Peaje 3.0": "precio_3.0",
        "Peaje 6.1": "precio_6.1"
    }

    for nombre, col in series_lineas.items():
        fig.add_trace(
            go.Scatter(
                x=df_precios_mensuales["fecha"],
                y=df_precios_mensuales[col],
                mode="lines",
                name=nombre,
                line=dict(
                    color=colores_precios[nombre],
                    width=3
                ),
                marker=dict(size=7),
                hovertemplate=f"{nombre}: " + "%{y:.2f} c€/kWh<extra></extra>"
            )
        )

    # =====================================================
    # 8. PRECIO CURVA
    #    Solo se pinta si hay curva cargada
    # =====================================================
    if hay_curva_sheets and "precio_curva" in df_precios_mensuales.columns:

        nombre_curva = (
            f"Curva {atr_actual}"
            if atr_actual is not None
            else "Precio curva"
        )

        fig.add_trace(
            go.Scatter(
                x=df_precios_mensuales["fecha"],
                y=df_precios_mensuales["precio_curva"],
                mode="lines+markers",
                name=nombre_curva,
                line=dict(
                    color=colores_precios["Precio curva"],
                    width=4,
                    dash="dot"
                ),
                marker=dict(size=8),
                hovertemplate=(
                    nombre_curva + ": %{y:.2f} c€/kWh"
                    "<extra></extra>"
                )
            )
        )

        st.session_state.precios_mensuales = df_precios_mensuales

    fig.update_yaxes(
        rangemode="tozero",
        showgrid=True,
        title_text="Precio medio c€/kWh"
    )

    fig.update_xaxes(
        showgrid=True,
        dtick="M1",
        tickformat="%b%y",
        title_text="Mes"
    )

    fig.update_layout(
        title="",
        hovermode="x unified",
        barmode="overlay",
        legend_title_text="",
        bargap=0.65
    )

    fig = aplicar_estilo(fig)

    return df_precios_mensuales, fig

def evol_mensual_old(df, colores_precios):

    dffm = df.copy()

    orden_meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    mes_a_num = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
    }

    dffm["mes_nombre"] = pd.Categorical(
        dffm["mes_nombre"],
        categories=orden_meses,
        ordered=True
    )

    df_precios_mensuales = dffm.pivot_table(
        values=["spot", "precio_2.0", "precio_3.0", "precio_6.1"],
        index=["año", "mes_nombre"],
        aggfunc="mean"
    ).reset_index()

    # Crear columna fecha
    df_precios_mensuales["mes_num"] = df_precios_mensuales["mes_nombre"].map(mes_a_num)

    df_precios_mensuales["fecha"] = pd.to_datetime(
        df_precios_mensuales["año"].astype(str)
        + "-"
        + df_precios_mensuales["mes_num"].astype(str)
        + "-01"
    )

    # Pasar de €/MWh a c€/kWh
    columnas_precio = ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]

    for col in columnas_precio:
        df_precios_mensuales[col] = df_precios_mensuales[col] / 10
        df_precios_mensuales[col] = df_precios_mensuales[col].round(2)

    # Colores
    colores_precios = {
        "Peaje 2.0": "goldenrod",
        "Peaje 3.0": "darkred",
        "Peaje 6.1": "#1C83E1"
    }

    # =====================================================
    # GRÁFICO MIXTO: SPOT BARRA + PRECIOS LÍNEAS
    # =====================================================
    fig = go.Figure()

    # SPOT en barras verdes estrechas
    fig.add_trace(
        go.Bar(
            x=df_precios_mensuales["fecha"],
            y=df_precios_mensuales["spot"],
            name="SPOT",
            marker_color="green",
            width=1000 * 60 * 60 * 24 * 8,  # aprox. 8 días en milisegundos
            opacity=0.65,
            hovertemplate="SPOT: %{y:.2f} c€/kWh<extra></extra>"
        )
    )

    # Líneas de precios finales
    series_lineas = {
        "Peaje 2.0": "precio_2.0",
        "Peaje 3.0": "precio_3.0",
        "Peaje 6.1": "precio_6.1"
    }

    for nombre, col in series_lineas.items():
        fig.add_trace(
            go.Scatter(
                x=df_precios_mensuales["fecha"],
                y=df_precios_mensuales[col],
                #mode="lines+markers",
                mode="lines",
                name=nombre,
                line=dict(
                    color=colores_precios[nombre],
                    width=3
                ),
                marker=dict(size=7),
                hovertemplate=f"{nombre}: " + "%{y:.2f} c€/kWh<extra></extra>"
            )
        )

    fig.update_yaxes(
        rangemode="tozero",
        showgrid=True,
        title_text="Precio medio c€/kWh"
    )

    fig.update_xaxes(
        showgrid=True,
        dtick="M1",
        tickformat="%b%y",
        title_text="Mes"
    )

    fig.update_layout(
        title="",
        hovermode="x unified",
        barmode="overlay",
        legend_title_text="",
        bargap=0.65
    )

    fig = aplicar_estilo(fig)

    return df_precios_mensuales, fig



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
    df["coste_margen"] = df[f"margen_{atr}"] * cons
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



def analizar_dependencia_omie(df_sheets, atr="2.0"):


    df = df_sheets.copy()

    # -----------------------------
    # COLUMNA DE PRECIO SEGÚN ATR
    # -----------------------------
    col_precio = f"precio_{atr}"

    if col_precio not in df.columns:
        raise ValueError(
            f"No existe la columna '{col_precio}' en df_sheets. "
            f"Columnas disponibles: {list(df.columns)}"
        )

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
            col_precio: "mean"
        })
    )

    resultados = []

    # -----------------------------
    # CÁLCULO POR AÑO
    # -----------------------------
    for año in sorted(df_mensual["año"].unique()):

        df_year = df_mensual[df_mensual["año"] == año].copy()

        # evitar años con pocos datos
        if len(df_year) < 2:
            continue

        X = sm.add_constant(df_year["spot"])
        y = df_year[col_precio]

        model = sm.OLS(y, X).fit()

        slope = model.params["spot"]

        elasticidad = (
            slope * df_year["spot"].mean()
        ) / df_year[col_precio].mean()

        peso_spot = (
            df_year["spot"].mean()
        ) / df_year[col_precio].mean()

        resultados.append({
            "año": año,
            "atr": atr,
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
        title=f"Evolución de la dependencia del SPOT - ATR {atr}"
    )

    fig.update_layout(
        title={"x": 0.5, "xanchor": "center"},
        yaxis_title="Ratio",
        xaxis_title="Año",
        xaxis=dict(
            dtick=1,
            tickformat="d"
        ),
        legend_title_text=""
    )
    fig = aplicar_estilo(fig)

    return df_res, fig





def graficar_elasticidad_lineal(df_res, atr="2.0", spot_ref=None, n_puntos=101):

    
    import plotly.graph_objects as go

    fig = go.Figure()

    # Rango eje X: variación relativa del SPOT
    # 0.50 = +50%
    x_vals = np.linspace(0, 1, n_puntos)

    hovertemplate = (
        "<b>Año:</b> %{customdata[0]}<br>"
        "<b>ATR:</b> %{customdata[1]}<br>"
        "<b>Elasticidad:</b> %{customdata[2]:.3f}<br>"
        "<b>Variación SPOT:</b> %{x:.1%}<br>"
        "<b>Variación precio final:</b> %{y:.1%}"
        "<extra></extra>"
    )

    for _, row in df_res.iterrows():

        año = int(row["año"])
        elasticidad = row["elasticidad"]

        y_vals = x_vals * elasticidad

        customdata = np.column_stack([
            np.repeat(año, len(x_vals)),
            np.repeat(atr, len(x_vals)),
            np.repeat(elasticidad, len(x_vals))
        ])

        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines",
            name=str(año),
            customdata=customdata,
            hovertemplate=hovertemplate
        ))

        # Etiqueta del año al final de cada línea
        fig.add_trace(go.Scatter(
            x=[x_vals[-1]],
            y=[y_vals[-1]],
            mode="markers+text",
            name=f"{año}_label",
            text=[str(año)],
            textposition="top right",
            textfont=dict(size=20),
            marker=dict(size=8),
            customdata=np.array([[año, atr, elasticidad]]),
            hovertemplate=hovertemplate,
            showlegend=False
        ))

    # -----------------------------
    # MARCADOR DE REFERENCIA
    # -----------------------------
    if spot_ref is not None:

        for _, row in df_res.iterrows():

            año = int(row["año"])
            elasticidad = row["elasticidad"]
            precio_ref = spot_ref * elasticidad

            fig.add_trace(go.Scatter(
                x=[spot_ref],
                y=[precio_ref],
                mode="markers",
                name=f"{año} - punto seleccionado",
                marker=dict(size=12),
                customdata=np.array([[año, atr, elasticidad]]),
                hovertemplate=hovertemplate,
                showlegend=False
            ))

        fig.add_vline(
            x=spot_ref,
            line_width=2,
            line_dash="dot",
            annotation_text=f"SPOT +{spot_ref:.0%}",
            annotation_position="top"
        )

    fig.update_layout(
        title=f"Relación SPOT → Precio final (elasticidad) - ATR {atr}",
        xaxis_title="Variación relativa SPOT (%)",
        yaxis_title="Variación relativa Precio final (%)",
        title_x=0.5,
        showlegend=False,
        width=700,
        margin=dict(r=90)
    )

    fig.update_xaxes(
        range=[0, 1.2],
        tickformat=".0%"
    )

    fig.update_yaxes(
        range=[0, 1.0],
        tickformat=".0%"
    )

    fig = aplicar_estilo(fig)

    return fig


import numpy as np
import pandas as pd
import plotly.graph_objects as go


def graficar_diferencial_precios_mensuales(
    df_mensual,
    anio_base,
    anio_comp,
    convertir_a_cent_kwh=True
):
    """
    Compara dos años a nivel mensual y genera un gráfico de diferenciales:

    Δ SPOT
    Δ Precio 2.0
    Δ Precio 3.0
    Δ Precio 6.1

    El gráfico muestra diferenciales absolutos en c€/kWh.
    En hover muestra valores base, valores comparados, Δ absoluto, Δ % y elasticidad.

    Parámetros
    ----------
    df_mensual : DataFrame
        Debe contener al menos:
        año, mes_num, spot, precio_2.0, precio_3.0, precio_6.1

    anio_base : int
        Año contra el que se compara. Ejemplo: 2025

    anio_comp : int
        Año comparado. Ejemplo: 2026

    convertir_a_cent_kwh : bool
        True si los precios vienen en €/MWh.
        False si ya vienen en c€/kWh.

    Returns
    -------
    df_delta : DataFrame
        Tabla con diferenciales absolutos, porcentuales y elasticidades.

    fig_delta : plotly.graph_objects.Figure
        Gráfico de barras agrupadas.
    """

    df = df_mensual.copy()

    columnas = ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]

    nombres = {
        "spot": "SPOT",
        "precio_2.0": "Precio 2.0",
        "precio_3.0": "Precio 3.0",
        "precio_6.1": "Precio 6.1"
    }

    colores = {
        "spot": "green",
        "precio_2.0": "goldenrod",
        "precio_3.0": "darkred",
        "precio_6.1": "#1C83E1"
    }

    num_a_mes = {
        1: "Ene",
        2: "Feb",
        3: "Mar",
        4: "Abr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Ago",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dic"
    }

    # Asegurar mes_num si no viniera creado
    if "mes_num" not in df.columns:
        mes_a_num = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }

        df["mes_num"] = df["mes_nombre"].map(mes_a_num)

    # Pasar de €/MWh a c€/kWh
    if convertir_a_cent_kwh:
        for col in columnas:
            df[col] = df[col] / 1
        

    df_base = df[df["año"] == anio_base][["mes_num"] + columnas].copy()
    df_comp = df[df["año"] == anio_comp][["mes_num"] + columnas].copy()

    if df_base.empty:
        raise ValueError(f"No hay datos para el año base {anio_base}.")

    if df_comp.empty:
        raise ValueError(f"No hay datos para el año comparado {anio_comp}.")

    df_delta = df_comp.merge(
        df_base,
        on="mes_num",
        how="inner",
        suffixes=("_comp", "_base")
    )

    df_delta = df_delta.sort_values("mes_num")
    df_delta["Mes"] = df_delta["mes_num"].map(num_a_mes)

    meses_orden = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

    

    #df_delta = df_delta.sort_values("Mes")

    # =====================================================
    # DIFERENCIALES ABSOLUTOS Y PORCENTUALES
    # =====================================================
    for col in columnas:
        delta_abs = df_delta[f"{col}_comp"] - df_delta[f"{col}_base"]
        delta_pct = np.where(
            df_delta[f"{col}_base"] != 0,
            delta_abs / df_delta[f"{col}_base"] * 100,
            np.nan
        )
        df_delta[f"{col}_delta"] = delta_abs.round(2)
        df_delta[f"{col}_delta_pct"] = pd.Series(delta_pct, index=df_delta.index).round(2)

        delta_log_pct = np.where(
            (df_delta[f"{col}_base"] > 0) & (df_delta[f"{col}_comp"] > 0),
            np.log(df_delta[f"{col}_comp"] / df_delta[f"{col}_base"]) * 100,
            np.nan
        )
        df_delta[f"{col}_delta_log_pct"] = pd.Series(delta_log_pct, index=df_delta.index).round(2)

    # =====================================================
    # ELASTICIDADES VS SPOT
    # =====================================================
    for col in ["precio_2.0", "precio_3.0", "precio_6.1"]:
        df_delta[f"{col}_elasticidad"] = np.where(
            df_delta["spot_delta_pct"] != 0,
            df_delta[f"{col}_delta_pct"] / df_delta["spot_delta_pct"],
            np.nan
        )

    # =====================================================
    # GRÁFICO
    # =====================================================
    fig_delta = go.Figure()

    for col in columnas:

        if col == "spot":
            customdata = np.stack(
                [
                    df_delta[f"{col}_base"],       # 0
                    df_delta[f"{col}_comp"],       # 1
                    df_delta[f"{col}_delta"],      # 2 abs c€/kWh
                    df_delta[f"{col}_delta_pct"],  # 3 %
                ],
                axis=-1
            )

            hovertemplate = (
                f"<b>{nombres[col]}</b><br>"
                f"{anio_base}: %{{customdata[0]:.2f}} c€/kWh<br>"
                f"{anio_comp}: %{{customdata[1]:.2f}} c€/kWh<br>"
                "Δ absoluto: %{customdata[2]:+.2f} c€/kWh<br>"
                "Δ porcentual: %{customdata[3]:+.2f} %"
                "<extra></extra>"
            )

        else:
            customdata = np.stack(
                [
                    df_delta[f"{col}_base"],          # 0
                    df_delta[f"{col}_comp"],          # 1
                    df_delta[f"{col}_delta"],         # 2 abs c€/kWh
                    df_delta[f"{col}_delta_pct"],     # 3 %
                    df_delta[f"{col}_elasticidad"],   # 4
                ],
                axis=-1
            )

            hovertemplate = (
                f"<b>{nombres[col]}</b><br>"
                f"{anio_base}: %{{customdata[0]:.2f}} c€/kWh<br>"
                f"{anio_comp}: %{{customdata[1]:.2f}} c€/kWh<br>"
                "Δ absoluto: %{customdata[2]:+.2f} c€/kWh<br>"
                "Δ porcentual: %{customdata[3]:+.2f} %<br>"
                "Elasticidad vs SPOT: %{customdata[4]:.2f}"
                "<extra></extra>"
            )

        fig_delta.add_trace(
            go.Bar(
                #x=df_delta["Mes"],
                x=df_delta["mes_num"],
                #y=df_delta[f"{col}_delta"],
                #y=df_delta[f"{col}_delta_pct"],
                y=df_delta[f"{col}_delta_log_pct"],
                name=nombres[col],
                marker_color=colores[col],
                width=0.08,
                customdata=customdata,
                hovertemplate=hovertemplate
            )
        )

    fig_delta.add_hline(
        y=0,
        line_dash="dash",
        line_color="gray",
        line_width=1
    )

    fig_delta.update_layout(
        title=dict(
            text=f"Diferencial mensual de precios (%): {anio_comp} vs {anio_base}",
            x=0.5,
            xanchor="center"
        ),
        xaxis_title="Mes",
        yaxis_title="Diferencial en %",
        barmode="group",
        bargap=0.55,
        bargroupgap=1,
        hovermode="x unified",
        legend_title_text="",
        
    )

    fig_delta.update_yaxes(
        showgrid=True,
        zeroline=True,
        zerolinewidth=1,
        zerolinecolor="gray"
    )

    fig_delta.update_xaxes(
        tickmode="array",
        tickvals=list(range(1, 13)),
        ticktext=["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
        range=[0.5, 12.5]
    )

    fig_delta=aplicar_estilo(fig_delta)
    fig_delta.update_layout(height=600)

    return df_delta, fig_delta


def tabla_evol_mes_por_años(df_mensual, meses_orden):
    df = df_mensual.copy()

    #columnas_precio = ["spot", "precio_2.0", "precio_3.0", "precio_6.1"]

    NUM_A_MES = {
        1: "enero",
        2: "febrero",
        3: "marzo",
        4: "abril",
        5: "mayo",
        6: "junio",
        7: "julio",
        8: "agosto",
        9: "septiembre",
        10: "octubre",
        11: "noviembre",
        12: "diciembre"
    }

    if "mes_num" not in df.columns:
        mes_a_num = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
        }
        df["mes_num"] = df["mes_nombre"].str.lower().map(mes_a_num)

    df["Mes"] = df["mes_num"].map(NUM_A_MES)


    print(st.session_state.mes_select_evol)

    mes_num_sel = meses_orden.index(st.session_state.mes_select_evol) + 1

    df_tabla = (
        df[df["mes_num"] == mes_num_sel]
        .sort_values("año")
        [["año", "spot", "precio_2.0", "precio_3.0", "precio_6.1"]]
        .rename(columns={
            "año": "Año",
            "spot": "SPOT",
            "precio_2.0": "Precio 2.0",
            "precio_3.0": "Precio 3.0",
            "precio_6.1": "Precio 6.1"
        })
    )

    df_tabla["Ratio 2.0 / SPOT"] = df_tabla["Precio 2.0"] / df_tabla["SPOT"]
    df_tabla["Ratio 3.0 / SPOT"] = df_tabla["Precio 3.0"] / df_tabla["SPOT"]
    df_tabla["Ratio 6.1 / SPOT"] = df_tabla["Precio 6.1"] / df_tabla["SPOT"]

    

    

    return df_tabla

