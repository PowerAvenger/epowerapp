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
color_media_futuro = "#CC8DF0"

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
    tipo="M" -> futuros mensuales
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
    if tipo == "M":
        col_periodo = "mes"

        df_mg[col_periodo] = df_mg["fecha_entrega"].dt.strftime("%Y-%m")

        def _key(lbl):
            return pd.Period(lbl, freq="M")

        titulo = "Evolución de MIBGAS para los próximos meses"
        nombre_leyenda = "Mes"
        num_periodos = 6

    elif tipo == "Q":
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
        num_periodos = 4

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
        num_periodos = 4

    else:
        raise ValueError("tipo debe ser 'M', 'Q' o 'Y'")

    # =====================================================
    # 2. Ordenar y quedarnos con los últimos periodos
    # =====================================================
    labels = sorted(df_mg[col_periodo].dropna().unique(), key=_key)
    labels = labels[-num_periodos:]

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
    palette = px.colors.sequential.Blues[2:8]

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
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        ),

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
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
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
        ),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
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


def obtener_mibgas_mensual(df_mg_da):
    df = df_mg_da.copy()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df.dropna(subset=["fecha_entrega", "precio_gas"])

    df_mensual = (
        df
        .set_index("fecha_entrega")
        .resample("MS")["precio_gas"]
        .mean()
        .reset_index()
    )
    df_mensual["precio_gas"] = df_mensual["precio_gas"].round(2)
    df_mensual = df_mensual.dropna(subset=["precio_gas"])

    return df_mensual


def graficar_mibgas_mensual_historico(df_mibgas_mensual):
    df = df_mibgas_mensual.copy()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    df = df.dropna(subset=["fecha_entrega", "precio_gas"]).copy()

    meses = {
        1: "Enero",
        2: "Febrero",
        3: "Marzo",
        4: "Abril",
        5: "Mayo",
        6: "Junio",
        7: "Julio",
        8: "Agosto",
        9: "Septiembre",
        10: "Octubre",
        11: "Noviembre",
        12: "Diciembre",
    }
    orden_meses = list(meses.values())

    df["año"] = df["fecha_entrega"].dt.year
    df["mes_num"] = df["fecha_entrega"].dt.month
    df["mes_nombre"] = df["mes_num"].map(meses)
    df = df.sort_values(["año", "mes_num"])

    fig = go.Figure()

    for año in sorted(df["año"].dropna().unique()):
        df_año = df[df["año"] == año].copy()
        fig.add_trace(
            go.Bar(
                x=df_año["mes_nombre"],
                y=df_año["precio_gas"],
                name=str(año),
                marker=dict(color=colores.get(int(año), None)),
                text=[f"{v:.2f}" for v in df_año["precio_gas"]],
                textposition="outside",
                textfont=dict(size=13, color="white"),
                hovertemplate=(
                    "%{fullData.name}: %{y:.2f} €/MWh"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=dict(
            text="Precio medio mensual MIBGAS D+1",
            x=0.5,
            xanchor="center",
            font=dict(size=28)
        ),
        xaxis=dict(
            title="Mes",
            categoryorder="array",
            categoryarray=orden_meses,
            tickfont=dict(size=14)
        ),
        yaxis=dict(
            title="€/MWh",
            range=[0, df["precio_gas"].max() * 1.18],
            title_font=dict(size=16),
            tickfont=dict(size=14)
        ),
        legend=dict(
            title_text="",
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.03,
            yanchor="bottom",
            font=dict(size=14)
        ),
        barmode="group",
        bargap=0.18,
        bargroupgap=0.06,
        barcornerradius=4,
        hovermode="x unified",
        hoverlabel=dict(font_size=16),
        template="plotly_dark",
        height=500
    )

    fig = aplicar_estilo(fig)

    return fig


def normalizar_futuros_mibgas_mensuales(df_mg_m):
    df = df_mg_m.copy()
    df["Trading day"] = pd.to_datetime(df["Trading day"], errors="coerce").dt.normalize()
    df["fecha_entrega"] = (
        pd.to_datetime(df["fecha_entrega"], errors="coerce")
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    return df.dropna(subset=["Trading day", "fecha_entrega", "precio_gas"])


def normalizar_futuros_mibgas_trimestrales(df_mg_q):
    df = df_mg_q.copy()
    df["Trading day"] = pd.to_datetime(df["Trading day"], errors="coerce").dt.normalize()
    df["fecha_entrega"] = pd.to_datetime(df["fecha_entrega"], errors="coerce")
    df["inicio_trimestre"] = df["fecha_entrega"].dt.to_period("Q").dt.start_time
    df["precio_gas"] = pd.to_numeric(df["precio_gas"], errors="coerce")
    return df.dropna(subset=["Trading day", "inicio_trimestre", "precio_gas"])


def _ultimo_precio_hasta(df, col_fecha, col_entrega, entrega, fecha_ref):
    df_filtrado = (
        df[
            (df[col_fecha] <= fecha_ref) &
            (df[col_entrega] == entrega)
        ]
        .sort_values(col_fecha)
    )

    if df_filtrado.empty:
        return np.nan, pd.NaT

    fila = df_filtrado.iloc[-1]
    return fila["precio_gas"], fila[col_fecha]


def _precio_futuro_mibgas_para_mes(df_m, df_q, mes_entrega, fecha_ref):
    precio_m, fecha_m = _ultimo_precio_hasta(
        df_m,
        "Trading day",
        "fecha_entrega",
        mes_entrega,
        fecha_ref,
    )

    if pd.notna(precio_m):
        return precio_m, "MIBGAS mensual", fecha_m

    trimestre = (mes_entrega.month - 1) // 3 + 1
    inicio_trimestre = pd.Timestamp(
        mes_entrega.year,
        (trimestre - 1) * 3 + 1,
        1,
    )
    precio_q, fecha_q = _ultimo_precio_hasta(
        df_q,
        "Trading day",
        "inicio_trimestre",
        inicio_trimestre,
        fecha_ref,
    )

    if pd.notna(precio_q):
        return precio_q, "MIBGAS trimestral", fecha_q

    return np.nan, "Sin dato", pd.NaT


def construir_curva_mibgas_2026(df_mibgas_mensual, df_mg_m, df_mg_q, fecha_ref=None, año=2026):
    df_hist = df_mibgas_mensual.copy()
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    if fecha_ref is None:
        fechas_ref = pd.concat([df_m["Trading day"], df_q["Trading day"]]).dropna()
        fecha_ref = fechas_ref.max()

    fecha_ref = pd.to_datetime(fecha_ref).normalize()
    df_hist["fecha_entrega"] = pd.to_datetime(df_hist["fecha_entrega"]).dt.to_period("M").dt.to_timestamp()

    filas = []
    for mes in range(1, 13):
        fecha_mes = pd.Timestamp(año, mes, 1)
        df_hist_mes = df_hist[df_hist["fecha_entrega"] == fecha_mes]

        if not df_hist_mes.empty:
            precio = df_hist_mes["precio_gas"].iloc[-1]
            tipo = "MIBGAS D+1"
            fecha_dato = fecha_mes
        else:
            precio, tipo, fecha_dato = _precio_futuro_mibgas_para_mes(df_m, df_q, fecha_mes, fecha_ref)

        filas.append({
            "fecha": fecha_mes,
            "precio": round(float(precio), 2) if pd.notna(precio) else np.nan,
            "tipo": tipo,
            "fecha_dato": fecha_dato,
        })

    return pd.DataFrame(filas)


def graficar_curva_mibgas_2026(df_curva, precio_medio=None):
    df = df_curva.copy()
    df_hist = df[df["tipo"] == "MIBGAS D+1"]
    df_fut = df[df["tipo"] != "MIBGAS D+1"]
    df_union = df_hist.tail(1)
    df_fut_plot = pd.concat([df_union, df_fut])

    fig = go.Figure()

    if not df_hist.empty:
        fig.add_scatter(
            x=df_hist["fecha"],
            y=df_hist["precio"],
            mode="lines+markers+text",
            name="MIBGAS D+1",
            line=dict(color="seagreen", width=3),
            marker=dict(size=10, symbol="square"),
            text=[f"{v:.1f}" for v in df_hist["precio"]],
            textposition="top center",
            textfont=dict(size=14, color="white"),
            customdata=df_hist["tipo"],
            hovertemplate="<b>%{customdata}</b><br>%{y:.1f} €/MWh<extra></extra>"
        )

    if not df_fut_plot.empty:
        fig.add_scatter(
            x=df_fut_plot["fecha"],
            y=df_fut_plot["precio"],
            mode="lines+markers+text",
            name="MIBGAS futuros",
            line=dict(color="darkorange", width=3, dash="dash"),
            marker=dict(size=10, symbol="square"),
            text=[f"{v:.1f}" if pd.notna(v) else "" for v in df_fut_plot["precio"]],
            textposition="top center",
            textfont=dict(size=14, color="white"),
            customdata=df_fut_plot["tipo"],
            hovertemplate="<b>%{customdata}</b><br>%{x|%b %Y}<br>%{y:.1f} €/MWh<extra></extra>"
        )
        if not df_union.empty:
            fig.data[-1].marker.color = ["rgba(0,0,0,0)"] + ["darkorange"] * (len(df_fut_plot) - 1)

    if precio_medio is not None and pd.notna(precio_medio):
        fig.add_hline(
            y=precio_medio,
            line_dash="dot",
            line_color=color_media_futuro,
            annotation_text=f"Media ≈ {precio_medio:.1f} €/MWh",
            annotation_position="top right",
            annotation_font_size=20,
            annotation_font_color=color_media_futuro
        )

    fig.update_layout(
        title=dict(
            text="PREVISIÓN MIBGAS 2026: Curva híbrida D+1-futuros",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        yaxis=dict(title="€/MWh", range=[0, None]),
        xaxis=dict(tickformat="%b %Y"),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


@st.cache_data()
def construir_media_prevista_mibgas_2026_diaria(df_mg_da, df_mg_m, df_mg_q, año=2026):
    df_da = df_mg_da.copy()
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    df_da["fecha_entrega"] = pd.to_datetime(df_da["fecha_entrega"], errors="coerce").dt.normalize()
    df_da["precio_gas"] = pd.to_numeric(df_da["precio_gas"], errors="coerce")
    df_da = df_da.dropna(subset=["fecha_entrega", "precio_gas"])

    fecha_ini = pd.Timestamp(año, 1, 1)
    fecha_ref_max = df_da.loc[
        df_da["fecha_entrega"].dt.year == año,
        "fecha_entrega"
    ].max()

    fechas_ref = sorted(
        df_da.loc[
            (df_da["fecha_entrega"] >= fecha_ini) &
            (df_da["fecha_entrega"] <= fecha_ref_max),
            "fecha_entrega"
        ].dropna().unique()
    )

    filas = []

    for fecha_ref in fechas_ref:
        fecha_ref = pd.Timestamp(fecha_ref).normalize()
        mes_actual = fecha_ref.month
        precios_mes = []

        for mes in range(1, 13):
            fecha_mes = pd.Timestamp(año, mes, 1)

            if mes < mes_actual:
                filtro_da = (
                    (df_da["fecha_entrega"].dt.year == año) &
                    (df_da["fecha_entrega"].dt.month == mes)
                )
                precio = df_da.loc[filtro_da, "precio_gas"].mean()

            elif mes == mes_actual:
                filtro_da = (
                    (df_da["fecha_entrega"] >= fecha_mes) &
                    (df_da["fecha_entrega"] <= fecha_ref)
                )
                precio = df_da.loc[filtro_da, "precio_gas"].mean()

            else:
                precio, _, _ = _precio_futuro_mibgas_para_mes(
                    df_m,
                    df_q,
                    fecha_mes,
                    fecha_ref,
                )

            precios_mes.append(precio)

        precios_mes = pd.Series(precios_mes, dtype="float")

        if precios_mes.notna().sum() == 12:
            filas.append({
                "fecha_cotizacion": fecha_ref,
                "media_2026": precios_mes.mean(),
            })
        else:
            print(
                f"No se pudo calcular media MIBGAS completa para {fecha_ref.date()}: "
                f"{precios_mes.notna().sum()}/12 meses válidos"
            )

    df_media = pd.DataFrame(filas)

    if not df_media.empty:
        df_media = df_media.sort_values("fecha_cotizacion").reset_index(drop=True)
        df_media["media_2026"] = df_media["media_2026"].round(2)

    return df_media


def graficar_media_prevista_mibgas_2026(df_media_2026, año=2026):
    df = df_media_2026.copy()

    fig = go.Figure()
    inicio_año = pd.Timestamp(año, 1, 1)
    fin_año = pd.Timestamp(año, 12, 31)

    if df.empty:
        fig.update_layout(
            title=dict(
                text=f"Evolución diaria de la media MIBGAS prevista {año}",
                x=0.5,
                xanchor="center",
                font=dict(size=20)
            ),
            yaxis=dict(title="€/MWh"),
            xaxis=dict(title="Fecha de cotización", tickformat="%b-%y", range=[inicio_año, fin_año]),
            template="plotly_dark",
            height=500
        )
        fig = aplicar_estilo(fig)
        return fig

    df["fecha_cotizacion"] = pd.to_datetime(df["fecha_cotizacion"])
    df = df.sort_values("fecha_cotizacion")

    fig.add_scatter(
        x=df["fecha_cotizacion"],
        y=df["media_2026"],
        mode="lines",
        name="Media prevista 2026",
        line=dict(
            color=color_media_futuro,
            width=2,
        ),
        showlegend=True,
        hovertemplate=(
            "<b>Media prevista 2026</b><br>"
            "%{x|%d/%m/%Y}<br>"
            "%{y:.1f} €/MWh"
            "<extra></extra>"
        )
    )

    fig.update_layout(
        title=dict(
            text=f"Evolución diaria de la media MIBGAS prevista {año}",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        yaxis=dict(
            title="€/MWh",
            range=[
                max(0, df["media_2026"].min() - 5),
                df["media_2026"].max() + 5
            ],
            title_font=dict(size=14),
            tickfont=dict(size=14)
        ),
        xaxis=dict(
            title="Fecha de cotización",
            tickformat="%b-%y",
            range=[inicio_año, fin_año],
            tickfont=dict(size=14)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


def construir_curva_mibgas_mensual_12m(df_mg_m, df_mg_q, fecha_ref=None):
    df_m = normalizar_futuros_mibgas_mensuales(df_mg_m)
    df_q = normalizar_futuros_mibgas_trimestrales(df_mg_q)

    if fecha_ref is None:
        fechas_ref = pd.concat([df_m["Trading day"], df_q["Trading day"]]).dropna()
        fecha_ref = fechas_ref.max()

    fecha_ref = pd.to_datetime(fecha_ref).normalize()
    filas = []

    for i in range(1, 13):
        fecha = fecha_ref + pd.DateOffset(months=i)
        fecha = pd.Timestamp(fecha.year, fecha.month, 1)
        precio, tipo, fecha_dato = _precio_futuro_mibgas_para_mes(df_m, df_q, fecha, fecha_ref)

        filas.append({
            "fecha": fecha,
            "precio": round(float(precio), 2) if pd.notna(precio) else np.nan,
            "tipo": tipo,
            "fecha_dato": fecha_dato,
        })

    df_curva = pd.DataFrame(filas)
    print("DEBUG MIBGAS curva 12M")
    print("Fecha ref:", fecha_ref)
    print("Productos M:", sorted(df_mg_m["producto"].dropna().unique().tolist()))
    print("Productos Q:", sorted(df_mg_q["producto"].dropna().unique().tolist()))
    print(df_curva)
    print("Meses con precio:", df_curva["precio"].notna().sum(), "/ 12")

    return df_curva


def graficar_curva_mibgas_mensual_12m(df_mibgas, precio_medio=None):
    fig = go.Figure()

    fig.add_scatter(
        x=df_mibgas["fecha"],
        y=df_mibgas["precio"],
        mode="lines+markers+text",
        name="MIBGAS forward 12M",
        line=dict(color="darkorange", width=3, dash="dash"),
        marker=dict(size=10, symbol="square"),
        text=[f"{v:.1f}" if pd.notna(v) else "" for v in df_mibgas["precio"]],
        textposition="top center",
        textfont=dict(size=14, color="white"),
        customdata=df_mibgas["tipo"],
        hovertemplate="<b>%{customdata}</b><br>%{x|%b %Y}<br>%{y:.1f} €/MWh<extra></extra>"
    )

    if precio_medio is not None and pd.notna(precio_medio):
        fig.add_hline(
            y=precio_medio,
            line_dash="dot",
            line_color="white",
            annotation_text=f"Media ≈ {precio_medio:.1f} €/MWh",
            annotation_position="top right",
            annotation_font_size=18
        )

    fig.update_layout(
        title=dict(
            text="Curva MIBGAS año móvil",
            x=0.5,
            xanchor="center",
            font=dict(size=20)
        ),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=14)
        ),
        yaxis=dict(title="€/MWh", range=[0, None]),
        xaxis=dict(tickformat="%b %Y"),
        hoverlabel=dict(font_size=14),
        template="plotly_dark",
        hovermode="x unified",
        height=500
    )
    fig = aplicar_estilo(fig)

    return fig


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
    


 
