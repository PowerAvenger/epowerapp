import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import requests
import glob
import numpy as np
from datetime import datetime,date
from backend_comun import aplicar_estilo
# Definimos los colores manualmente
COLOR_MIBGAS_2026 = "#ff69b4"

colores = {
    2024: "lightblue",
    2025: "#1E90FF",
    2026: COLOR_MIBGAS_2026
    #2025: "darkblue"
}




# función para crear un df según el producto
def filtrar_por_producto(df, producto):
    df_f = df[df['producto'] == producto].copy()
    #df_f['fecha'] = pd.to_datetime(df_f['fecha'], dayfirst=True, errors='coerce')
    #df_f['fecha_entrega'] = pd.to_datetime(df_f['fecha_entrega'], dayfirst=False, errors='coerce').dt.date
    #df_f['año_entrega'] = df_f['fecha_entrega'].dt.year
    return df_f

def graficar_futuros_mibgas(df_mg, tipo="Q"):
    """
    tipo="Q" -> futuros trimestrales
    tipo="Y" -> futuros anuales
    """

    df_mg = df_mg.copy()

    # Asegurar fechas
    df_mg["Trading day"] = pd.to_datetime(df_mg["Trading day"])
    df_mg["fecha_entrega"] = pd.to_datetime(df_mg["fecha_entrega"])

    # =====================================================
    # 1. Crear etiqueta de producto según tipo
    # =====================================================
    if tipo == "Q":
        col_periodo = "trimestre"

        df_mg[col_periodo] = (
            "Q"
            + df_mg["fecha_entrega"].dt.quarter.astype(str)
            + "-"
            + df_mg["fecha_entrega"].dt.year.astype(str)
        )

        def _key(lbl):
            q, y = lbl.split("-")
            return (int(y), int(q[1]))

        titulo = "Evolución de MIBGAS para los próximos trimestres"
        nombre_leyenda = "Trimestre"

    elif tipo == "Y":
        col_periodo = "año"

        df_mg[col_periodo] = (
            "Y-"
            + df_mg["fecha_entrega"].dt.year.astype(str)
        )

        def _key(lbl):
            return int(lbl.split("-")[1])

        titulo = "Evolución de MIBGAS para los próximos años"
        nombre_leyenda = "Año"

    else:
        raise ValueError("tipo debe ser 'Q' o 'Y'")

    # =====================================================
    # 2. Ordenar y quedarnos con los últimos 4 periodos
    # =====================================================
    labels = sorted(df_mg[col_periodo].dropna().unique(), key=_key)
    labels = labels[-4:]

    df_win = df_mg[df_mg[col_periodo].isin(labels)].copy()

    cat = pd.api.types.CategoricalDtype(categories=labels, ordered=True)
    df_win[col_periodo] = df_win[col_periodo].astype(cat)

    df_win = df_win.sort_values(["Trading day", col_periodo])

    # =====================================================
    # 3. Pivotar
    # =====================================================
    df_pivot = (
        df_win
        .pivot(index="Trading day", columns=col_periodo, values="precio_gas")
        .reset_index()
    )

    # =====================================================
    # 4. Colores
    # =====================================================
    palette = px.colors.sequential.Blues[3:7]

    color_map = {
        labels[i]: palette[i]
        for i in range(len(labels))
    }

    # =====================================================
    # 5. Gráfico
    # =====================================================
    fig = px.line(
        df_pivot,
        x="Trading day",
        y=df_pivot.columns[1:],
        labels={
            "value": "€/MWh",
            "variable": nombre_leyenda
        },
        color_discrete_map=color_map,
        title=titulo,
    )

    fig.update_layout(
        hovermode="x unified",
        title_font_size=28,
        title={
            "x": 0.5,
            "xanchor": "center"
        },
        hoverlabel=dict(font_size=18)
    )

    fig.update_xaxes(
        hoverformat="%Y-%m-%d"
    )

    fig.update_traces(
        hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>"
    )

    return fig

def graficar_qs(df_mg_q):
    #df_mg_q['Trading day'] = pd.to_datetime(df_mg_q['Trading day'])
    #df_mg_q['fecha_entrega'] = pd.to_datetime(df_mg_q['fecha_entrega'])

    # Crear columna 'trimestre'
    df_mg_q["trimestre"] = ("Q" + df_mg_q["fecha_entrega"].dt.quarter.astype(str) + "-" + df_mg_q["fecha_entrega"].dt.year.astype(str))

    def _key(lbl):
        q, y = lbl.split("-")
        return (int(y), int(q[1]))  # (año, nº de Q)

    uniq = sorted(df_mg_q["trimestre"].unique(), key=_key)
    labels = uniq[-4:]  # últimos 4 trimestres que haya en el df

    df_win = df_mg_q[df_mg_q["trimestre"].isin(labels)].copy()
    cat = pd.api.types.CategoricalDtype(categories=labels, ordered=True)
    df_win["trimestre"] = df_win["trimestre"].astype(cat)
    df_win = df_win.sort_values(["Trading day", "trimestre"])

    # Pivotar para tener cada trimestre en una columna
    df_pivot = df_win.pivot(index="Trading day", columns="trimestre", values="precio_gas").reset_index()


    #escala de azules (oscuro → claro)
    palette = px.colors.sequential.Blues[3:7]  # 4 tonos (ajusta si necesitas más/menos)

    # tus trimestres ya están en orden en 'labels'
    color_map = {labels[i]: palette[i] for i in range(len(labels))}
    # Gráfico con varias columnas como "wide form"
    fig = px.line(
        df_pivot,
        x="Trading day",
        y=df_pivot.columns[1:], 
        #color="trimestre",
        labels={'value':'€/MWh', 'variable':'Trimestre'},
        color_discrete_map=color_map, # todas las columnas de trimestres
        title='Evolución de MIBGAS para los próximos trimestres',
        #height=800
    )

    # Ajustar el tooltip para que muestre todas las series
    # 1) Un solo tooltip por x (Trading day)
    fig.update_layout(
        hovermode="x unified",
        title_font_size=28, 
        title={'x':0.5, 'xanchor':'center'},
        hoverlabel=dict(font_size=18)
        )

    # 2) Formato de la fecha en el encabezado del tooltip
    fig.update_xaxes(
        hoverformat="%Y-%m-%d",
        
    )

    # 3) Contenido de cada fila del tooltip (nombre del Q y su valor)
    fig.update_traces(hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>")

  
    
    return fig

def graficar_da_corrido(df):

    df = df.copy()

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])

    fig = px.line(
        df,
        x="fecha_entrega",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        title="Evolución del precio de MIBGAS D+1 por año",
    )

    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Fecha",
        yaxis_title="Precio gas (€/MWh)",

        xaxis=dict(
            showgrid=True,
            gridwidth=1,
            tickmode="linear",
            dtick="M1",
        ),

        hoverlabel=dict(
            font_size=18,
            # bgcolor="rgba(255,255,255,0.75)",  # opcional si quieres transparencia
        )
    )

    fig.update_traces(
        hovertemplate=(
            "<b>%{x|%d/%m/%Y}</b><br>"
            "MIBGAS D+1: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_da_2026_acumulado(df, año=2026):

    df = df.copy()
    inicio_año = pd.Timestamp(year=año, month=1, day=1)
    fin_año = pd.Timestamp(year=año, month=12, day=31)

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df[df["fecha_entrega"].dt.year == año].copy()
    df = df.sort_values("fecha_entrega")

    if df.empty:
        fig = go.Figure()
        fig.update_layout(
            title_font_size=28,
            title={
                "text": f"No hay datos MIBGAS D+1 disponibles para {año}",
                "x": 0.5,
                "xanchor": "center"
            },
            xaxis_title="Fecha",
            yaxis_title="Precio gas (€/MWh)",
            hoverlabel=dict(font_size=18)
        )
        fig.update_xaxes(range=[inicio_año, fin_año])
        fig = aplicar_estilo(fig)
        return fig

    df["media_acumulada_gas"] = df["precio_gas"].expanding().mean()

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["fecha_entrega"],
        y=df["precio_gas"],
        mode="lines",
        name="Precio diario",
        line=dict(color=colores.get(año, COLOR_MIBGAS_2026), width=2),
        hovertemplate=(
            "MIBGAS D+1: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    ))

    fig.add_trace(go.Scatter(
        x=df["fecha_entrega"],
        y=df["media_acumulada_gas"],
        mode="lines",
        name="Media acumulada diaria",
        line=dict(color="gold", width=3, dash="dot"),
        hovertemplate=(
            "Media acumulada: %{y:.2f} €/MWh"
            "<extra></extra>"
        )
    ))

    fig.update_layout(
        title_font_size=28,
        title={
            "text": f"Evolución diaria y media acumulada MIBGAS D+1 {año}",
            "x": 0.5,
            "xanchor": "center"
        },
        xaxis_title="Fecha",
        yaxis_title="Precio gas (€/MWh)",
        hovermode="x unified",
        hoverlabel=dict(font_size=18),
        legend=dict(
            orientation="h",
            y=1.02,
            x=0.5,
            xanchor="center"
        )
    )

    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        tickmode="linear",
        dtick="M1",
        range=[inicio_año, fin_año],
        hoverformat="%d/%m/%Y"
    )

    fig = aplicar_estilo(fig)

    return fig

def graficar_da_comparado(df):

    df = df.copy()

    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"])

    # Clave interna para ordenar: 01-01, 01-02, ..., 12-31
    df["mmdd"] = df["fecha_entrega"].dt.strftime("%m-%d")

    # Etiqueta visible día-mes
    if "fecha_corta" not in df.columns:
        df["fecha_corta"] = df["fecha_entrega"].dt.strftime("%d-%m")

    # Orden cronológico real por mes-día
    orden_mmdd = sorted(
        df["mmdd"].unique(),
        key=lambda s: (int(s[:2]), int(s[3:]))
    )

    # Mapa mmdd -> fecha_corta
    mapa_fechas = (
        df.drop_duplicates("mmdd")
          .set_index("mmdd")["fecha_corta"]
          .to_dict()
    )

    orden_fechas = [mapa_fechas[v] for v in orden_mmdd]

    # Esta será la X visible y también la cabecera del hover
    df["dia_mes"] = df["mmdd"].map(mapa_fechas)

    fig = px.line(
        df,
        x="dia_mes",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        category_orders={"dia_mes": orden_fechas},
        title="Comparación anual del precio del gas (2024 al 2026)",
    )

    # Etiquetas del eje X cada 15 días
    tickvals = orden_fechas[::15]

    fig.update_xaxes(
        tickmode="array",
        tickvals=tickvals,
        ticktext=tickvals,
        tickangle=0,
        type="category"
    )

    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
        hovermode="x unified",
        hoverlabel=dict(
            font_size=18,
        )
    )

    # En el hover saldrán todos los años juntos para ese día-mes
    fig.update_traces(
        hovertemplate="%{fullData.name}: %{y:.2f} €/MWh<extra></extra>"
    )

    # Líneas verticales al inicio de cada mes
    cortes_mes = [mapa_fechas[v] for v in orden_mmdd if v.endswith("-01")]

    for dia_mes in cortes_mes:
        fig.add_vline(
            x=dia_mes,
            line_width=1,
            line_dash="dot",
            line_color="rgba(200,200,200,0.2)"
        )

    fig = aplicar_estilo(fig)

    return fig

def graficar_da_comparado_old(df):

    df = df.copy()

      # Claves para orden y etiqueta
    df["mmdd"] = df["fecha_entrega"].dt.strftime("%m-%d")  # '02-29', '10-21', ...
    # Linux/Mac: %-d ; Windows: %#d  (elige el que corresponda)
    

    # Orden cronológico sin datetime: (MM, DD)
    orden_mmdd = sorted(
        df["mmdd"].unique(),
        key=lambda s: (int(s[:2]), int(s[3:]))
    )

    print('df da comparado')
    print(df)
    
    fig = px.line(
        df,
        x="mmdd",
        y="precio_gas",
        color="año_entrega",
        color_discrete_map=colores,
        category_orders={"mmdd": orden_mmdd},
        title="Comparación anual del precio del gas (2024 al 2026)",
        #height=600
    )

     # Forzar eje categórico y aplicar etiquetas legibles
    # Reducimos el número de etiquetas visibles en el eje X
    tickvals = orden_mmdd[::15]  # uno cada 15 días
    ticktext = [df.loc[df["mmdd"] == v, "fecha_corta"].iloc[0] for v in tickvals]
    
    fig.update_xaxes(
        tickmode="array",
        #tickvals=orden_mmdd,
        #ticktext=df.drop_duplicates("mmdd").sort_values("mmdd")["fecha_corta"].tolist(),
        tickvals=tickvals,
        ticktext=ticktext,
        tickangle=0,  # puedes probar 45 si quieres inclinar
        type="category"
    )


    fig.update_layout(
        title_font_size=28, 
        title={'x':0.5, 'xanchor':'center'},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
    )

    cortes_mes = (
        df
        .drop_duplicates("mmdd")
        .loc[df["mmdd"].str.endswith("-01"), "mmdd"]
        .tolist()
    )
    for mmdd in cortes_mes:
        fig.add_vline(
            x=mmdd,
            line_width=1,
            line_dash="dot",
            #line_color="lightgrey",
            line_color="rgba(200,200,200,0.2)"
        )

    return fig


def descargar_sendeco(año):
    url=f'https://www.sendeco2.com/site_sendeco/service/download-csv.php?year={año}'
    res=requests.get(url)
    with open(f'local_bbdd/sendeco_files/sendeco_{año}.csv', 'wb') as file:
            file.write(res.content)
            
    return

def obtener_sendeco():
    #OBTENEMOS UN DATAFRAME CON TODOS LOS HISTÓRICOS DE SENDECO
    ruta_sendeco='local_bbdd/sendeco_files/*.csv'
    #listado de ficheros históricos
    sendecos_csv=glob.glob(ruta_sendeco)
    #dataframe vacio
    df_sendecos=[]
    #creamos dataframes a combinar
    for file in sendecos_csv:
        df=pd.read_csv(file,sep=';')
        df_sendecos.append(df)
    #combinamos
    df_sendeco_combinado=pd.concat(df_sendecos, ignore_index=True)
    #eliminamos columnas innecesarias
    df_sendeco=df_sendeco_combinado.drop(df_sendeco_combinado.columns[[2,3]], axis=1)
    #renombramos
    df_sendeco=df_sendeco.rename(columns={'Fecha':'fecha_entrega','EUA':'co2_€ton'})
    #pasamos fecha a datetime
    #df_sendeco['fecha']=pd.to_datetime(df_sendeco['fecha'],dayfirst=True)
    #df_sendeco['fecha_entrega']=pd.to_datetime(df_sendeco['fecha_entrega'],dayfirst=True).dt.date
    df_sendeco['fecha_entrega']=pd.to_datetime(df_sendeco['fecha_entrega'],dayfirst=True)   
    df_sendeco['año'] = pd.to_datetime(df_sendeco['fecha_entrega']).dt.year

    return df_sendeco




def graficar_gas_co2(df_total_data_gas_co2):
    graf=px.line(df_total_data_gas_co2,
        x='fecha_entrega',
        y=['precio_gas','co2_€ton'],
        labels={'value':'gas €/MWh - CO2 €/Ton','precio_gas':'Mibgas D+1','co2_€ton':'CO2'},
        title='Evolución mibgas D+1 y CO2',
        #width=1000
        
    )

    graf.update_traces(line=dict(color='lightblue'), selector=dict(name='precio_gas'))
    graf.update_traces(line=dict(color='orange'), selector=dict(name='co2_€ton'))

    ymax=max(df_total_data_gas_co2['precio_gas'].max(),df_total_data_gas_co2['co2_€ton'].max())
    graf.update_yaxes(range=[0,ymax+5])
    graf.update_layout(
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
            ),
        title_font_size=28,            
        title={'x':0.5, 'xanchor':'center'},
        xaxis_title="Día del año",
        yaxis_title="Precio gas (€/MWh)",
    )
    

    return graf

# DF CON LOS VALORES MEDIOS MENSUALES DEL SPOT DE TODO EL HISTÓRICO
# SE USAN PARA VISUALIZARLOS CON LINEAS HORIZONTALES FRENTE A LA EVOLUCIÓN DE OMIP
@st.cache_data
def obtener_spot_mensual():
   
    df = st.session_state.df_sheets.copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    df = df.rename(columns={"fecha": "fecha_entrega"})

    df = df.set_index('fecha_entrega')

    df_spot_mensual = (
        df[['spot']]
        .resample('M')
        .mean()
        .sort_index()
        .reset_index()
    )

    df_spot_mensual['spot'] = df_spot_mensual['spot'].round(2)

    print('df spot diario')
    print(df_spot_mensual)

    return df_spot_mensual

def construir_df_mensual(df):
    # Poner 'fecha' como índice
    df_total_data = df.copy()
    df_total_data = df_total_data.set_index("fecha_entrega").sort_index()
    df_total_data.index = pd.to_datetime(df_total_data.index)

    df_mensual = df_total_data.resample('M').mean(numeric_only=True)
    df_mensual['ratio_omie_gas'] = df_mensual['spot'] / df_mensual['precio_gas']
    df_mensual['mes'] = df_mensual.index.month
    df_mensual['año'] = df_mensual.index.year
    meses_data = {
        'mes': list(range(1, 13)),
        'nombre_mes': ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
    }
    df_meses = pd.DataFrame(meses_data)
    #creamos una columna con el nombre del mes
    df_mensual = pd.merge(df_mensual, df_meses, how='left', on='mes')
    df_mensual['mes_año']=df_mensual['nombre_mes'].astype(str) + '_' + df_mensual['año'].astype(str)

    return df_mensual


def graf_simul_spot(df, df_validacion, mibgas, omie_media_2026=None, gas_media_2026=None):

    fig = px.scatter(
        df,
        x="precio_gas",
        y="spot",
        height=800,
        width=1500,
        title="Simulación del precio medio SPOT a partir de MIBGAS - Año 2026 (€/MWh)",
        custom_data=["mes_año"],
    )

    fig.update_traces(
        name="Valores mensuales",
        showlegend=True,
        marker=dict(symbol="square", color="orange"),
        hovertemplate=(
            "<b>Valores mensuales</b><br>"
            "Mes = %{customdata[0]}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
    )

    # =====================================================
    # CURVA HINGE
    # =====================================================
    x0 = 31.0

    x_val = df_validacion["precio_gas"].to_numpy(float)
    y_val = df_validacion["omie"].to_numpy(float)

    # Nivel base: media OMIE cuando gas <= x0
    base = x_val <= x0
    c_hinge = float(y_val[base].mean())

    # Ajuste derecha: y = c + a*(x-x0)^2 + b*(x-x0)
    mask = x_val > x0
    x_r = x_val[mask] - x0
    y_r = y_val[mask]

    X = np.column_stack([x_r**2, x_r])
    a_h, b_h = np.linalg.lstsq(X, y_r - c_hinge, rcond=None)[0]
    a_h, b_h = float(a_h), float(b_h)

    def hinge(x):
        x = np.asarray(x, dtype=float)

        m_left = 0.6
        y = c_hinge + m_left * (x - x0)

        idx = x > x0
        y[idx] = c_hinge + a_h * (x[idx] - x0) ** 2 + b_h * (x[idx] - x0)

        return y

    # Curva hinge en el rango del histórico
    x_fit = np.linspace(df["precio_gas"].min(), df["precio_gas"].max(), 300)
    y_fit = hinge(x_fit)

    # =====================================================
    # VALORES ANUALES REALES
    # =====================================================
    fig.add_scatter(
        x=df_validacion["precio_gas"],
        y=df_validacion["omie"],
        mode="markers",
        marker=dict(
            symbol="circle",
            size=12,
            color="royalblue",
            line=dict(width=2, color="cyan")
        ),
        name="Valores anuales",
        hovertemplate=(
            "<b>Valores anuales</b><br>"
            "Año %{customdata}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
        customdata=df_validacion["año"]
    )

    # =====================================================
    # PUNTO REAL 2026 YTD: GAS MEDIO 2026 / OMIE MEDIO 2026
    # =====================================================
    if omie_media_2026 is not None and gas_media_2026 is not None:

        fig.add_trace(go.Scatter(
            x=[gas_media_2026],
            y=[omie_media_2026],
            mode="markers+text",
            name="Media 2026",
            marker=dict(
                symbol="diamond",
                size=18,
                color="yellow",
                line=dict(width=3, color="white")
            ),
            text=["Media 2026"],
            textposition="top center",
            hovertemplate=(
                "<b>Media real 2026</b><br>"
                "MIBGAS medio 2026 = %{x:.2f} €/MWh<br>"
                "OMIE medio 2026 = %{y:.2f} €/MWh"
                "<extra></extra>"
            )
        ))

    # =====================================================
    # CURVA DE AJUSTE
    # =====================================================
    fig.add_trace(go.Scatter(
        x=x_fit,
        y=y_fit,
        mode="lines",
        name="Ajuste suave",
        line=dict(color="lime", width=2, dash="dot"),
        hoverinfo="skip"
    ))

    # =====================================================
    # PUNTO PREVISTO HINGE EN MIBGAS
    # =====================================================
    omie_hinge = float(hinge([mibgas])[0])

    fig.add_trace(go.Scatter(
        x=[mibgas],
        y=[omie_hinge],
        mode="markers",
        name="Simulación OMIE",
        marker=dict(
            color="rgba(255,255,255,0)",
            size=20,
            line=dict(width=5, color="lightgreen")
        ),
        hovertemplate=(
            "<b>Simulación OMIE</b><br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        )
    ))

    # Línea vertical simulación OMIE
    fig.add_shape(
        type="line",
        x0=mibgas,
        y0=0,
        x1=mibgas,
        y1=omie_hinge,
        line=dict(color="lightgreen", width=1, dash="dash"),
    )

    # =====================================================
    # SIMULACIÓN INVERSA: OMIE OBJETIVO -> GAS NECESARIO
    # =====================================================
    omie_obj = st.session_state.get("precio_omie_previsto", None)
    mibgas_obj = None

    if omie_obj:

        x_search = np.linspace(0, 120, 2000)
        y_search = hinge(x_search)

        idx = np.argmin(np.abs(y_search - omie_obj))
        mibgas_obj = float(x_search[idx])

        fig.add_trace(go.Scatter(
            x=[mibgas_obj],
            y=[omie_obj],
            mode="markers",
            name="Simulación GAS",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=22,
                line=dict(width=5, color="magenta")
            ),
            hovertemplate=(
                "<b>Simulación GAS</b><br>"
                "OMIE = %{y:.1f} €/MWh<br>"
                "MIBGAS = %{x:.1f} €/MWh"
                "<extra></extra>"
            )
        ))

        xmin = min(df["precio_gas"].min(), df_validacion["precio_gas"].min())

        fig.add_shape(
            type="line",
            x0=xmin,
            y0=omie_obj,
            x1=mibgas_obj,
            y1=omie_obj,
            line=dict(color="magenta", width=1, dash="dash"),
        )

    # =====================================================
    # LAYOUT
    # =====================================================
    fig.update_layout(
        title_font_size=28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Precio MIBGAS (€/MWh)",
        yaxis_title="Precio OMIE (€/MWh)",
        xaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        yaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        legend=dict(
            font=dict(size=18)
        ),
        hoverlabel=dict(font_size=18)
    )

    if mibgas_obj is not None:
        mibgas_obj = round(mibgas_obj, 2)

    return fig, round(omie_hinge, 2), mibgas_obj


def graf_simul_spot_old(df, df_validacion, mibgas):
    fig = px.scatter(
        df,
        x="precio_gas",
        y="spot",
        height=800,
        width=1500,
        title="Simulación del precio medio SPOT a partir de MIBGAS - Año 2026 (€/MWh)",
        custom_data=["mes_año"],
    )
    fig.update_traces(
        name="Valores mensuales",              # 👈 aparece en leyenda
        showlegend=True,               # 👈 forzado
        marker=dict(symbol="square", color="orange"),
        hovertemplate=(
            "<b>Valores mensuales</b><br>"
            "Mes = %{customdata[0]}<br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        ),
    )

    # curva hinge
    x0=31.0
    #x0=28.0


    x_val = df_validacion["precio_gas"].to_numpy(float)
    y_val = df_validacion["omie"].to_numpy(float)

    # Nivel base: media OMIE cuando gas <= x0
    base = x_val <= x0
    c_hinge = float(y_val[base].mean())

    # Ajuste derecha: y = c + a*(x-x0)^2 + b*(x-x0)
    mask = x_val > x0
    x_r = x_val[mask] - x0
    y_r = y_val[mask]

    X = np.column_stack([x_r**2, x_r])
    a_h, b_h = np.linalg.lstsq(X, y_r - c_hinge, rcond=None)[0]
    a_h, b_h = float(a_h), float(b_h)

    def hinge(x):
        x = np.asarray(x, dtype=float)
        #y = np.full_like(x, c_hinge, dtype=float)
        m_left = +.6  # pendiente suave hacia abajo
        y = c_hinge + m_left*(x - x0)
        idx = x > x0
        y[idx] = c_hinge + a_h*(x[idx]-x0)**2 + b_h*(x[idx]-x0)
        return y

    # Curva hinge en el rango del histórico
    x_fit = np.linspace(df["precio_gas"].min(), df["precio_gas"].max(), 300)
    y_fit = hinge(x_fit)


    # Valores anuales reales
    fig.add_scatter(
            x=df_validacion['precio_gas'],
            y=df_validacion['omie'],
            mode='markers',
            marker=dict(
                symbol='circle',
                size=12,
                color='royalblue',
                line=dict(width=2, color='cyan')
            ),
            name='Valores anuales',
            hovertemplate=(
                "Año %{customdata}<br>"
                "MIBGAS = %{x:.1f} €/MWh<br>"
                "OMIE = %{y:.1f} €/MWh"
                "<extra></extra>"
            ),
            customdata=df_validacion['año']
        )
    
    fig.add_trace(go.Scatter(
        x=x_fit, y=y_fit,
        mode="lines",
        name="Ajuste suave",
        line=dict(color="lime", width=2, dash="dot"),
        hoverinfo="skip"
    ))

    # Punto previsto hinge en mibgas
    omie_hinge = float(hinge([mibgas])[0])

    fig.add_trace(go.Scatter(
        x=[mibgas], y=[omie_hinge],
        mode="markers",
        name="Simulación OMIE",
        marker=dict(
            color="rgba(255,255,255,0)",
            size=20,
            line=dict(width=5, color="lightgreen")
        ),
        hovertemplate=(
            "<b>Simulación</b><br>"
            "MIBGAS = %{x:.1f} €/MWh<br>"
            "OMIE = %{y:.1f} €/MWh"
            "<extra></extra>"
        )
    ))

    # Línea vertical
    fig.add_shape(
        type="line",
        x0=mibgas, y0=0,
        x1=mibgas, y1=omie_hinge,
        line=dict(color="lightgreen", width=1, dash="dash"),
    )

    
    omie_obj = st.session_state.get("precio_omie_previsto", None)
    mibgas_obj = None
    if omie_obj:

        # resolver inversa numéricamente
        x_search = np.linspace(0, 120, 2000)
        y_search = hinge(x_search)

        idx = np.argmin(np.abs(y_search - omie_obj))
        mibgas_obj = float(x_search[idx])
        fig.add_trace(go.Scatter(
            x=[mibgas_obj],
            y=[omie_obj],
            mode="markers",
            name="Simulación GAS",
            marker=dict(
                color="rgba(255,255,255,0)",
                size=22,
                line=dict(width=5, color="magenta")
            ),
            hovertemplate=(
                "<b>Simulación GAS</b><br>"
                "OMIE = %{y:.1f} €/MWh<br>"
                "MIBGAS = %{x:.1f} €/MWh<br>"
                
                "<extra></extra>"
            )
        ))
        xmin = min(df["precio_gas"].min(), df_validacion["precio_gas"].min())
        fig.add_shape(
            type="line",
            x0=xmin,
            y0=omie_obj,
            x1=mibgas_obj,
            y1=omie_obj,
            line=dict(color="magenta", width=1, dash="dash"),
        )

    fig.update_layout(
        title_font_size = 28,
        title={"x": 0.5, "xanchor": "center"},
        xaxis_title="Precio MIBGAS (€/MWh)",
        yaxis_title="Precio OMIE (€/MWh)",
        xaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        yaxis=dict(
            title_font=dict(size=20),
            tickfont=dict(size=18)
        ),
        legend=dict(
            font=dict(size=18)
        ),
        hoverlabel=dict(font_size=18)
    )

    if mibgas_obj is not None:
        mibgas_obj = round(mibgas_obj, 2)

    

    return fig, round(omie_hinge, 2), mibgas_obj


@st.cache_data
def obtener_spot_diario():
    
    df = st.session_state.df_sheets.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.set_index("fecha")

    df_spot_diario = (
        df[["spot"]]
        .resample("D")
        .mean()
        .sort_index()
        .reset_index()
    )

    df_spot_diario["spot"] = df_spot_diario["spot"].round(2)

    return df_spot_diario
    


 
